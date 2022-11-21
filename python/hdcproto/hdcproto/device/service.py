from __future__ import annotations

import enum
import logging
import typing
import uuid

import semver

import hdcproto.device
import hdcproto.device.router
import hdcproto.transport.serialport
from hdcproto.common import (is_valid_uint8, ExcID, HdcDataType, MessageTypeID, FeatureID,
                             HdcDataTypeError, HdcCmdException, HdcCmdExc_CommandFailed, HdcCmdExc_InvalidArgs,
                             HdcCmdExc_UnknownProperty, )
from hdcproto.descriptor import StateDescriptor, PropertyDescriptor, CommandDescriptor, \
    GetPropertyValueCommandDescriptor, SetPropertyValueCommandDescriptor, EventDescriptor, LogEventDescriptor, \
    FeatureStateTransitionEventDescriptor, FeatureDescriptor, LogEventThresholdPropertyDescriptor, \
    FeatureStatePropertyDescriptor, DeviceDescriptor

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.device.service"


class CommandService:
    command_descriptor: CommandDescriptor
    feature_service: FeatureService
    command_implementation: typing.Callable[[typing.Any], typing.Any]
    _command_request_handler: typing.Callable[[bytes], None]
    msg_prefix: bytes

    def __init__(self,
                 command_descriptor: CommandDescriptor,
                 feature_service: FeatureService,
                 command_implementation: typing.Callable[[typing.Any], typing.Any]):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.service.MyDeviceService.MyFeatureService.MyCommandService"
        self.logger = feature_service.logger.getChild(self.__class__.__name__)

        if not isinstance(command_descriptor, CommandDescriptor):
            raise TypeError
        self.command_descriptor = command_descriptor

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"to service {command_descriptor} "
                          f"on {feature_service.feature_descriptor}")

        # Reference from feature --> command
        if command_descriptor.id in feature_service.command_services:
            self.logger.warning(f"Replacing previous instance of type "
                                f"{feature_service.command_services[command_descriptor.id].__class__.__name__} with "
                                f"new instance of type {self.__class__.__name__} to service {command_descriptor}")
        feature_service.command_services[command_descriptor.id] = self

        self.feature_service = feature_service  # Reference from command --> feature

        # Ensure the descriptor of the feature includes this command's descriptor
        self.feature_service.feature_descriptor.commands[command_descriptor.id] = command_descriptor

        # Let message router know that this Service will handle requests addressed at this FeatureID & CommandID
        feature_service.router.register_command_request_handler(
            feature_id=feature_service.feature_descriptor.id,
            command_id=command_descriptor.id,
            command_request_handler=self._command_request_handler)

        # ToDo: Validate signature of implementation to be compatible with HDC args and returns
        self.command_implementation = command_implementation

        self.msg_prefix = bytes([int(MessageTypeID.COMMAND),
                                 self.feature_service.feature_descriptor.id,
                                 self.command_descriptor.id])

    @property
    def router(self) -> hdcproto.device.router.MessageRouter:
        return self.feature_service.device_service.router

    def _command_request_handler(self, request_message: bytes) -> None:
        try:
            if self.command_descriptor.arguments is None:
                parsed_arguments = None
            else:
                parsed_arguments = HdcDataType.parse_command_request_msg(
                    request_message=request_message,
                    expected_data_types=[arg.dtype for arg in self.command_descriptor.arguments])
        except HdcDataTypeError as e:
            raise HdcCmdExc_InvalidArgs(exception_message=str(e))

        try:
            if parsed_arguments is None:
                return_values = self.command_implementation()
            else:
                return_values = self.command_implementation(*parsed_arguments)
        except HdcCmdException as e:
            # Sanity-checking against exception descriptors registered for this command
            registered_exception_descriptor = self.command_descriptor.raises.get(e.exception_id)
            if registered_exception_descriptor is None:
                # Dear developer: Have you forgotten to declare this kind of exception in this command's descriptor? :-)
                self.logger.warning(f"Raising Exception.id=0x{e.exception_id:02X}, "
                                    f"although it has not been registered for {self.__class__.__name__}")
            elif e.exception_name != registered_exception_descriptor.exception_name:
                self.logger.warning(f"Raising Exception.id=0x{e.exception_id:02X} with name '{e.exception_name}', "
                                    f"although it had been registered with a different name "
                                    f"of {registered_exception_descriptor.exception_name}")
            raise
        except ValueError as e:
            raise HdcCmdExc_InvalidArgs(exception_message=str(e))
        except Exception as e:
            raise HdcCmdExc_CommandFailed(exception_message=str(e))
        else:
            reply = bytearray(self.msg_prefix)
            reply.append(ExcID.NO_ERROR)

        if return_values is None:
            return_values = tuple()
        elif not isinstance(return_values, tuple) and not isinstance(return_values, list):
            return_values = tuple([return_values])

        if len(return_values) != len(self.command_descriptor.returns):
            raise RuntimeError("Command implementation did not return the expected number of return values")

        for i, return_descriptor in enumerate(self.command_descriptor.returns):
            ret_value = return_values[i]
            reply.extend(return_descriptor.dtype.value_to_bytes(ret_value))
        reply = bytes(reply)
        self.router.send_reply_for_pending_request(reply)


class GetPropertyValueCommandService(CommandService):
    def __init__(self, feature_service: FeatureService):
        super().__init__(command_descriptor=GetPropertyValueCommandDescriptor(),
                         feature_service=feature_service,
                         command_implementation=self._command_implementation)

    def _command_implementation(self, property_id: int) -> bytes:
        """
        Returns variable data-type, depending on the requested property_id.
        Therefore, returning a still serialized result as BLOB.
        """
        prop_service = self.feature_service.property_services.get(property_id, None)
        if prop_service is None:
            raise HdcCmdExc_UnknownProperty()

        prop_value = prop_service.property_getter()
        value_as_bytes = prop_service.property_descriptor.dtype.value_to_bytes(prop_value)

        self.logger.info(f"Replying with {self.command_descriptor.name}({prop_service.property_descriptor}) "
                         f"-> {repr(prop_value)}")
        return value_as_bytes


class SetPropertyValueCommandService(CommandService):
    def __init__(self, feature_service: FeatureService):
        super().__init__(command_descriptor=SetPropertyValueCommandDescriptor(),
                         feature_service=feature_service,
                         command_implementation=self._command_implementation)

    def _command_implementation(self, property_id: int, new_value_as_bytes: bytes) -> bytes:
        """
        Receives and returns variable data-type, depending on the requested property_id.
        Therefore, de-serializing argument from bytes and returning a still serialized result as BLOB.
        """

        prop_service = self.feature_service.property_services.get(property_id, None)
        if prop_service is None:
            raise HdcCmdExc_UnknownProperty()

        prop_type = prop_service.property_descriptor.dtype
        try:
            new_value = prop_type.bytes_to_value(new_value_as_bytes)
            actual_new_value = prop_service.property_setter(new_value)
        except (HdcDataTypeError, ValueError) as e:
            raise HdcCmdExc_InvalidArgs(exception_message=str(e))

        actual_new_value_as_bytes = prop_type.value_to_bytes(actual_new_value)

        self.logger.log(level=logging.INFO if new_value == actual_new_value else logging.WARNING,
                        msg=f"Replying with {self.command_descriptor.name}"
                            f"({prop_service.property_descriptor}, {repr(new_value)}) "
                            f"-> {repr(actual_new_value)}")

        return actual_new_value_as_bytes


class EventService:
    event_descriptor: EventDescriptor
    feature_service: FeatureService
    msg_prefix: bytes

    def __init__(self,
                 event_descriptor: EventDescriptor,
                 feature_service: FeatureService):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.service.MyDeviceService.MyFeatureService.MyEventService"
        self.logger = feature_service.logger.getChild(self.__class__.__name__)

        if not isinstance(event_descriptor, EventDescriptor):
            raise TypeError
        self.event_descriptor = event_descriptor

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"to {event_descriptor} "
                          f"on {feature_service.feature_descriptor}")

        # Reference from feature --> event
        if event_descriptor.id in feature_service.event_services:
            self.logger.warning(f"Replacing previous instance of type "
                                f"{feature_service.event_services[event_descriptor.id].__class__.__name__} with new"
                                f"instance of type {self.__class__.__name__} to service {event_descriptor}")
        feature_service.event_services[event_descriptor.id] = self

        self.feature_service = feature_service  # Reference from event --> feature

        # Ensure the descriptor of the feature includes this event's descriptor
        self.feature_service.feature_descriptor.events[event_descriptor.id] = event_descriptor

        self.msg_prefix = bytes([int(MessageTypeID.EVENT),
                                 self.feature_service.feature_descriptor.id,
                                 self.event_descriptor.id])

    @property
    def router(self) -> hdcproto.device.router.MessageRouter:
        return self.feature_service.device_service.router

    def _send_event_message_raw(self, event_message: bytes) -> None:
        if not isinstance(event_message, (bytes, bytearray)):
            raise TypeError()

        if len(event_message) < len(self.msg_prefix) \
                or event_message[:len(self.msg_prefix)] != self.msg_prefix:
            raise ValueError()

        self.router.send_event_message(event_message=event_message)

    def _send_event_message(self, event_args: list[typing.Any] | None) -> None:
        event_message = bytearray(self.msg_prefix)

        if event_args is None:
            assert self.event_descriptor.arguments is None
        else:
            assert len(event_args) == len(self.event_descriptor.arguments)

            for arg_value, arg_descriptor in zip(event_args, self.event_descriptor.arguments):
                arg_as_raw_bytes = arg_descriptor.dtype.value_to_bytes(arg_value)
                event_message.extend(arg_as_raw_bytes)

        event_message = bytes(event_message)

        self._send_event_message_raw(event_message=event_message)


class LogEventService(EventService):
    def __init__(self, feature_service: FeatureService):
        super().__init__(event_descriptor=LogEventDescriptor(),
                         feature_service=feature_service)

    def emit(self, log_level: int, log_msg: str) -> None:
        if log_level >= self.feature_service.log_event_threshold:
            self.logger.info(f"Sending {self.event_descriptor} -> ({logging.getLevelName(log_level)}, '{log_msg}')")
            self._send_event_message(event_args=[log_level, log_msg])


class HdcLoggingHandler(logging.Handler):
    """Python logging handler which emits HDC Log-events on a given HDC-feature."""

    def __init__(self, log_event_service: LogEventService):
        super().__init__()
        self.log_event_service = log_event_service

    def emit(self, record):
        # noinspection PyBroadException
        try:
            msg = self.format(record)
            self.log_event_service.emit(record.levelno, msg)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


class FeatureStateTransitionEventService(EventService):
    def __init__(self, feature_service: FeatureService):
        super().__init__(event_descriptor=FeatureStateTransitionEventDescriptor(),
                         feature_service=feature_service)

    def emit(self, previous_state_id: int, current_state_id: int) -> None:
        if not is_valid_uint8(previous_state_id):
            raise ValueError(f"previous_state_id of {previous_state_id} is beyond valid range from 0x00 to 0xFF")
        if not is_valid_uint8(current_state_id):
            raise ValueError(f"current_state_id of {current_state_id} is beyond valid range from 0x00 to 0xFF")
        self.logger.info(f"Sending {self.event_descriptor} -> (0x{previous_state_id:02X}, 0x{current_state_id:02X}')")
        self._send_event_message(event_args=[previous_state_id, current_state_id])


class PropertyService:
    property_descriptor: PropertyDescriptor
    feature_service: FeatureService
    property_getter: typing.Callable[[None], int | float | str | bytes | HdcDataType]
    property_setter: typing.Callable[[int | float | str | bytes], int | float | str | bytes | HdcDataType] | None

    def __init__(self,
                 property_descriptor: PropertyDescriptor,
                 feature_service: FeatureService,
                 property_getter: typing.Callable[[], int | float | str | bytes | HdcDataType],
                 property_setter: typing.Callable[[int | float | str | bytes], int | float | str | bytes | HdcDataType] | None
                 ):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.service.MyDeviceService.MyFeatureService.MyPropertyService"
        self.logger = feature_service.logger.getChild(self.__class__.__name__)

        if not isinstance(property_descriptor, PropertyDescriptor):
            raise TypeError
        self.property_descriptor = property_descriptor

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"to service {property_descriptor} "
                          f"on {feature_service.feature_descriptor}")

        # Reference from feature --> property
        if property_descriptor.id in feature_service.property_services:
            self.logger.warning(f"Replacing previous instance of type "
                                f"{feature_service.property_services[property_descriptor.id].__class__.__name__} with "
                                f"new instance of type {self.__class__.__name__} to service "
                                f"{property_descriptor}")
        feature_service.property_services[property_descriptor.id] = self

        self.feature_service = feature_service  # Reference from property --> feature

        # Ensure the descriptor of the feature includes this property's descriptor
        self.feature_service.feature_descriptor.properties[property_descriptor.id] = property_descriptor

        self.property_getter = property_getter  # ToDo: Validate getter signature
        self.property_setter = property_setter  # ToDo: Validate setter signature


class FeatureService:
    feature_descriptor: FeatureDescriptor
    device_service: DeviceService
    command_services: dict[int, CommandService]
    event_services: dict[int, EventService]
    property_services: dict[int, PropertyService]

    _current_state_id: int

    def __init__(self,
                 feature_descriptor: FeatureDescriptor,
                 device_service: DeviceService):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.service.MyDeviceService.MyFeatureService"
        self.logger = device_service.logger.getChild(self.__class__.__name__)

        if not isinstance(feature_descriptor, FeatureDescriptor):
            raise TypeError
        self.feature_descriptor = feature_descriptor

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} to service {feature_descriptor}")

        # Reference from device --> feature
        if feature_descriptor.id in device_service.feature_services:
            self.logger.warning(f"Replacing previous instance of type "
                                f"{device_service.feature_services[feature_descriptor.id].__class__.__name__} with new"
                                f"instance of type {self.__class__.__name__} to service {feature_descriptor}")
        device_service.feature_services[feature_descriptor.id] = self

        self.device_service = device_service  # Reference from feature --> device

        # Ensure the descriptor of the device includes this feature's descriptor
        self.device_service.device_descriptor.features[feature_descriptor.id] = feature_descriptor

        # Actual attributes holding the values for the two mandatory HDC-properties of this feature.
        self._current_state_id = 0  # ToDo: Should we establish a convention about initializing states to zero? Nah...
        self.log_event_threshold = logging.WARNING

        # Commands
        self.command_services = dict()
        self._cmd_get_property_value = GetPropertyValueCommandService(self)
        self._cmd_set_property_value = SetPropertyValueCommandService(self)

        # Events
        self.event_services = dict()
        self._evt_state_transition = FeatureStateTransitionEventService(self)
        self._evt_log = LogEventService(self)

        # Use a dedicated logger for this feature-instance, whose logs will be forwarded as HDC Log-events to the host.
        self.hdc_logger = logging.getLogger(str(uuid.uuid4()))
        self.hdc_logger.addHandler(HdcLoggingHandler(log_event_service=self._evt_log))

        # Properties
        self.property_services = dict()
        self._prop_log_event_threshold = PropertyService(
            feature_service=self,
            property_descriptor=LogEventThresholdPropertyDescriptor(),
            property_getter=lambda: self.log_event_threshold,
            property_setter=self._prop_log_event_threshold_setter
        )

        self._prop_feature_state = PropertyService(
            feature_service=self,
            property_descriptor=FeatureStatePropertyDescriptor(),
            property_getter=lambda: self._current_state_id,
            property_setter=None  # Not exposing a setter on HDC interface does *not* mean this is immutable. ;-)
        )

    def _prop_log_event_threshold_setter(self, new_threshold: int) -> int:
        # Silently constrain to valid log level values, only, because
        # of the same rationale as explained here:
        #      https://docs.python.org/3.10/howto/logging.html#custom-levels

        new_threshold = int(new_threshold)

        if new_threshold < logging.DEBUG:
            new_threshold = logging.DEBUG

        if new_threshold > logging.CRITICAL:
            new_threshold = logging.CRITICAL

        # Rounding to the nearest multiple of 10. https://stackoverflow.com/a/2422723/20337562
        new_threshold = ((new_threshold + 5) // 10) * 10

        self.logger.info(f"Changing LogEventThreshold from "
                         f"previously {logging.getLevelName(self.log_event_threshold)} "
                         f"to now {logging.getLevelName(new_threshold)}.")

        self.log_event_threshold = new_threshold

        return self.log_event_threshold

    @property
    def router(self) -> hdcproto.device.router.MessageRouter:
        return self.device_service.router

    @property
    def current_state_id(self) -> int:
        """Use the switch_state() method to change the current state."""
        return self._current_state_id

    def switch_state(self, new_feature_state_id: int):
        if self.feature_descriptor.states is None:
            raise RuntimeError("Cannot switch feature state if none were registered for this feature")

        if new_feature_state_id not in self.feature_descriptor.states:
            raise ValueError(f"Unknown state_id {new_feature_state_id}")

        previous_state_id = self._current_state_id
        self.logger.info(f"Transitioning FeatureState from previously 0x{previous_state_id:02X} to "
                         f"now 0x{new_feature_state_id:02X}.")
        self._current_state_id = new_feature_state_id
        self._evt_state_transition.emit(previous_state_id=previous_state_id,
                                        current_state_id=new_feature_state_id)


class CoreFeatureService(FeatureService):
    def __init__(self,
                 device_service: DeviceService,
                 feature_states: typing.Type[enum.IntEnum] | list[StateDescriptor] | None = None):
        super().__init__(
            feature_descriptor=FeatureDescriptor(
                id_=FeatureID.CORE.CORE,
                name="Core",
                class_name=device_service.device_name,
                class_version=device_service.device_version,
                doc=device_service.device_doc,
                states=feature_states
            ),
            device_service=device_service
        )


class DeviceService:
    device_name: str
    device_version: semver.VersionInfo | None
    device_doc: str | None
    router: hdcproto.device.router.MessageRouter
    feature_services: dict[int, FeatureService]

    device_descriptor: DeviceDescriptor

    def __init__(self,
                 connection_url: str,
                 device_name: str,
                 device_version: str | semver.VersionInfo | None,
                 device_doc: str | None,
                 max_req_msg_size: int = 2048):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.service.MyDeviceService"
        self.logger = logger.getChild(self.__class__.__name__)

        # Those device attributes will later on be handed down to the Core feature!
        self.device_name = device_name
        if device_version is not None and not isinstance(device_version, semver.VersionInfo):
            device_version = semver.VersionInfo.parse(device_version)
        self.device_version = device_version
        self.device_doc = device_doc

        self.device_descriptor = DeviceDescriptor(
            version=hdcproto.common.HDC_VERSION,
            max_req=max_req_msg_size
        )

        self.router = hdcproto.device.router.MessageRouter(connection_url=connection_url,
                                                           max_req_msg_size=max_req_msg_size,
                                                           idl_json_generator=self.device_descriptor.to_idl_json)
        self.feature_services = dict()

    @property
    def is_connected(self):
        return self.router.is_connected

    @property
    def connection_url(self) -> str | None:
        return self.router.connection_url

    def connect(self, connection_url: str | None = None):
        self.router.connect(connection_url=connection_url)

    def close(self):
        self.router.close()

    def __enter__(self) -> DeviceService:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
