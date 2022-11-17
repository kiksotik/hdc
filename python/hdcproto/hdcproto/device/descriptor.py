from __future__ import annotations

import enum
import json
import logging
import typing
import uuid

import semver

import hdcproto.device
import hdcproto.device.router
import hdcproto.transport.serialport
from hdcproto.common import (is_valid_uint8, ExcID, HdcDataType, MessageTypeID, FeatureID, CmdID, EvtID, PropID,
                             HdcDataTypeError, HdcCmdException, HdcCmdExc_CommandFailed, HdcCmdExc_InvalidArgs,
                             HdcCmdExc_UnknownProperty)

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.device.descriptor"


class ArgD:
    """
    Argument descriptor

    As used to describe the arguments that an HDC-Command takes.
    """
    dtype: HdcDataType
    name: str
    doc: str | None

    def __init__(self,
                 dtype: HdcDataType,
                 name: str,
                 doc: str | None = None):

        if not isinstance(dtype, HdcDataType):
            raise ValueError
        self.dtype = dtype

        if not name:
            raise ValueError("Argument name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        self.doc = doc

    def to_idl_dict(self) -> dict:
        return dict(
            dtype=self.dtype.name,
            name=self.name,
            doc=self.doc
        )


class RetD:
    """
    Return-Value descriptor

    Describes the value(s) that an HDC-Command returns.
    """
    dtype: HdcDataType
    name: str | None
    doc: str | None

    def __init__(self,
                 dtype: HdcDataType,
                 name: str | None = None,
                 doc: str | None = None):

        if not isinstance(dtype, HdcDataType):
            raise ValueError
        self.dtype = dtype

        if name is not None and len(name) < 1:
            raise ValueError("Return Value name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        self.doc = doc

    def to_idl_dict(self) -> dict:
        return dict(
            dtype=self.dtype.name,
            name=self.name,
            doc=self.doc
        )


class CommandDescriptorBase:
    """
    Derive from this *only* if custom handling of
    arguments and return values is required, i.e.:
      - Variable data-types in arguments and/or reply, like SetPropertyValue()
      - Variable number of arguments and/or reply items

    Otherwise, you might be better off using the TypedCommandDescriptor class.
    """
    feature_descriptor: FeatureDescriptorBase
    command_id: int
    command_name: str
    command_description: str
    command_implementation: typing.Callable[[typing.Any], typing.Any]
    command_arguments: tuple[ArgD, ...]  # ToDo: Argument optionality. #25
    command_returns: tuple[RetD, ...]  # ToDo: Argument optionality. #25
    command_raises: dict[int, str]  # ToDo: Argument optionality. #25

    _command_request_handler: typing.Callable[[bytes], None]
    msg_prefix: bytes

    def __init__(self,
                 feature_descriptor: FeatureDescriptorBase,
                 command_id: int,
                 command_name: str,
                 command_implementation: typing.Callable[[typing.Any], typing.Any],
                 command_description: str | None,
                 command_arguments: tuple[ArgD, ...] | None,
                 command_returns: RetD | tuple[RetD, ...] | None,
                 command_raises: list[enum.IntEnum] | None):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.descriptor.MyDeviceDescriptor.MyFeatureDescriptor.MyCommandDescriptor"
        self.logger = feature_descriptor.logger.getChild(self.__class__.__name__)

        if not is_valid_uint8(command_id):
            raise ValueError(f"command_id value of {command_id} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as descriptor for CommandID=0x{command_id:02X} "
                          f"on FeatureID=0x{feature_descriptor.feature_id:02X}")

        # Reference from feature --> command
        if command_id in feature_descriptor.command_descriptors:
            self.logger.warning(f"Replacing previous descriptor instance of type "
                                f"{feature_descriptor.command_descriptors[command_id].__class__.__name__} with new"
                                f"instance of type {self.__class__.__name__} for "
                                f"CommandID=0x{command_id:02X}")
        feature_descriptor.command_descriptors[command_id] = self

        self.feature_descriptor = feature_descriptor  # Reference from command --> feature

        # Let message router know that this Descriptor will handle requests addressed at this FeatureID & CommandID
        feature_descriptor.router.register_command_request_handler(
            feature_id=feature_descriptor.feature_id,
            command_id=command_id,
            command_request_handler=self._command_request_handler)

        self.command_id = command_id

        if not command_name:
            raise ValueError("Command name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.command_name = command_name

        if command_raises is None:
            command_raises = list()
        self.command_raises = dict()
        for error_enum in command_raises:
            if not isinstance(error_enum, ExcID) and ExcID.is_custom(int(error_enum)):
                raise ValueError(f"Mustn't override meaning of predefined or reserved "
                                 f"Exception-id=0x{error_enum:02X}")
            self.command_raises[int(error_enum)] = error_enum.name

        self.command_description = command_description

        if not command_arguments:
            # Meaning "Has no args".
            # Harmonize it into an empty tuple to simplify remainder of this implementation
            self.command_arguments = tuple()
        else:
            if any(not isinstance(arg, ArgD) for arg in command_arguments):
                raise TypeError("command_arguments must be an iterable of ArgD objects")

            if any(arg.dtype.size is None for arg in command_arguments[:-1]):
                raise ValueError("Only last argument may be of a variable-size data-type")

            self.command_arguments = tuple(command_arguments)

        if not command_returns:
            # Meaning "Returns nothing".
            # Harmonize it into a tuple to simplify remainder of this implementation
            self.command_returns = tuple()
        elif isinstance(command_returns, RetD):
            # Meaning it returns a single value.
            # Harmonize it into a tuple to simplify remainder of this implementation
            self.command_returns = tuple([command_returns])
        else:
            if any(not isinstance(ret, RetD) for ret in command_returns):
                raise TypeError("command_returns must be an iterable of RetD objects")

            if any(ret.dtype.size is None for ret in command_returns[:-1]):
                raise ValueError("Only last return value may be of a variable-size data-type")

            self.command_returns = tuple(command_returns)

        # Validate signature of implementation to be compatible with HDC args and returns
        self.command_implementation = command_implementation

        description_already_contains_command_signature = command_description.startswith('(')
        if not description_already_contains_command_signature:
            cmd_signature = "("
            if not self.command_arguments:
                cmd_signature += "VOID"
            else:
                cmd_signature += ', '.join(f"{arg.dtype.name} {arg.name}"
                                           for arg in self.command_arguments)
            cmd_signature += ") -> "

            if len(self.command_returns) == 0:
                cmd_signature += "VOID"
            elif len(self.command_returns) == 1:
                cmd_signature += f"{self.command_returns[0].dtype.name}"
                if self.command_returns[0].name:
                    cmd_signature += f" {self.command_returns[0].name}"
            else:
                cmd_signature += "("
                cmd_signature += ', '.join(f"{ret.dtype.name}{f' ret.name' if ret.name else ''}"
                                           for ret in self.command_returns)
                cmd_signature += ")"
            if command_description:
                self.command_description = cmd_signature + '\n' + command_description
            else:
                self.command_description = cmd_signature

        self.msg_prefix = bytes([int(MessageTypeID.COMMAND),
                                 self.feature_descriptor.feature_id,
                                 self.command_id])

    @property
    def router(self) -> hdcproto.device.router.MessageRouter:
        return self.feature_descriptor.device_descriptor.router

    def _command_request_handler(self, request_message: bytes) -> None:
        try:
            if self.command_arguments is None:
                parsed_arguments = None
            else:
                parsed_arguments = HdcDataType.parse_command_request_msg(
                    request_message=request_message,
                    expected_data_types=[arg.dtype for arg in self.command_arguments])
        except HdcDataTypeError as e:
            raise HdcCmdExc_InvalidArgs(exception_message=str(e))

        try:
            if parsed_arguments is None:
                return_values = self.command_implementation()
            else:
                return_values = self.command_implementation(*parsed_arguments)
        except HdcCmdException as e:
            if e.exception_id not in self.command_raises:
                self.logger.warning(f"Raising HDC-exception.id=0x{e.exception_id:02X}, although "
                                    f"it has not been registered for {self.__class__.__name__}")
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

        if len(return_values) != len(self.command_returns):
            raise RuntimeError("Command implementation did not return the expected number of return values")

        for i, return_descriptor in enumerate(self.command_returns):
            ret_value = return_values[i]
            reply.extend(return_descriptor.dtype.value_to_bytes(ret_value))
        reply = bytes(reply)
        self.router.send_reply_for_pending_request(reply)

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.command_id,
            name=self.command_name,
            doc=self.command_description,
            args=[arg.to_idl_dict()
                   for arg in self.command_arguments
                   ] if self.command_arguments is not None else None,
            returns=[ret.to_idl_dict()
                     for ret in self.command_returns
                    ] if self.command_returns is not None else None,
            raises=[
                dict(id=error_id, name=error_name)
                for error_id, error_name in self.command_raises.items()
            ]
        )


class GetPropertyValueCommandDescriptor(CommandDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_PROP_VALUE,
                         command_name="GetPropertyValue",
                         command_implementation=self._command_implementation,
                         command_description="",  # ToDo: Argument optionality. #25
                         command_arguments=(ArgD(HdcDataType.UINT8, name="PropertyID"),),
                         # Returns 'BLOB', because data-type depends on requested property
                         command_returns=(RetD(HdcDataType.BLOB, doc="Actual data-type depends on property"),),
                         command_raises=[ExcID.INVALID_ARGS,
                                         ExcID.UNKNOWN_PROPERTY,
                                         ExcID.COMMAND_FAILED])

    def _command_implementation(self, property_id: int) -> bytes:
        """
        Returns variable data-type, depending on the requested PropertyID.
        Therefore, returning a serialized result as BLOB.
        """
        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise HdcCmdExc_UnknownProperty()

        prop_type = prop_descr.property_type
        prop_value = prop_descr.property_getter()
        value_as_bytes = prop_type.value_to_bytes(prop_value)

        self.logger.info(f"Replying with {self.command_name}('{prop_descr.property_name}') "
                         f"-> {repr(prop_value)}")
        return value_as_bytes


class SetPropertyValueCommandDescriptor(CommandDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.SET_PROP_VALUE,
                         command_name="SetPropertyValue",
                         command_implementation=self._command_implementation,
                         command_description="Returned value might differ from NewValue argument, "
                                             "i.e. because of trimming to valid range or discretization.",
                         # Signature uses 'BLOB', because data-type depends on requested property
                         command_arguments=(ArgD(HdcDataType.UINT8, "PropertyID"),
                                            ArgD(HdcDataType.BLOB, "NewValue", "Actual data-type depends on property")),
                         command_returns=(RetD(HdcDataType.BLOB, "ActualNewValue", "May differ from NewValue!"),),
                         command_raises=[ExcID.INVALID_ARGS,
                                         ExcID.UNKNOWN_PROPERTY,
                                         ExcID.RO_PROPERTY])

    def _command_implementation(self, property_id: int, new_value_as_bytes: bytes) -> bytes:
        """
        Receives and returns variable data-type, depending on the requested PropertyID.
        Therefore, de-serializing argument from bytes and returning a serialized result as BLOB.
        """

        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise HdcCmdExc_UnknownProperty()

        prop_type = prop_descr.property_type
        try:
            new_value = prop_type.bytes_to_value(new_value_as_bytes)
            actual_new_value = prop_descr.property_setter(new_value)
        except (HdcDataTypeError, ValueError) as e:
            raise HdcCmdExc_InvalidArgs(exception_message=str(e))

        actual_new_value_as_bytes = prop_type.value_to_bytes(actual_new_value)

        self.logger.log(level=logging.INFO if new_value == actual_new_value else logging.WARNING,
                        msg=f"Replying with {self.command_name}('{prop_descr.property_name}', {repr(new_value)}) "
                            f"-> {repr(actual_new_value)}")

        return actual_new_value_as_bytes


class EventDescriptorBase:
    feature_descriptor: FeatureDescriptorBase
    event_id: int
    event_name: str
    event_description: str
    event_arguments: tuple[ArgD, ...] | None
    msg_prefix: bytes

    def __init__(self,
                 feature_descriptor: FeatureDescriptorBase,
                 event_id: int,
                 event_name: str,
                 event_description: str | None,
                 event_arguments: tuple[ArgD, ...] | None):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.descriptor.MyDeviceDescriptor.MyFeatureDescriptor.MyEventDescriptor"
        self.logger = feature_descriptor.logger.getChild(self.__class__.__name__)

        if not is_valid_uint8(event_id):
            raise ValueError(f"event_id value of {event_id} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as descriptor for EventID=0x{event_id:02X} "
                          f"on FeatureID=0x{feature_descriptor.feature_id:02X}")

        # Reference from feature --> event
        if event_id in feature_descriptor.event_descriptors:
            self.logger.warning(f"Replacing previous descriptor instance of type "
                                f"{feature_descriptor.event_descriptors[event_id].__class__.__name__} with new"
                                f"instance of type {self.__class__.__name__} for "
                                f"EventID=0x{event_id:02X}")
        feature_descriptor.event_descriptors[event_id] = self

        self.feature_descriptor = feature_descriptor  # Reference from event --> feature
        self.event_id = event_id

        if not event_name:
            raise ValueError("Event name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.event_name = event_name

        if event_description is None:
            event_description = ""
        self.event_description = event_description

        if event_arguments is None:
            event_arguments = None
        if any(arg.dtype.size is None for arg in event_arguments[:-1]):
            raise ValueError("Only last argument may be of a variable-size data-type")
        self.event_arguments = event_arguments

        description_already_contains_event_signature = event_description.startswith('(')
        if not description_already_contains_event_signature:
            evt_signature = "("
            evt_signature += ', '.join(f"{arg.dtype.name} {arg.name}" for arg in self.event_arguments)
            evt_signature += ")"
            if event_description:
                self.event_description = evt_signature + '\n' + event_description
            else:
                self.event_description = evt_signature

        self.msg_prefix = bytes([int(MessageTypeID.EVENT),
                                 self.feature_descriptor.feature_id,
                                 self.event_id])

    @property
    def router(self) -> hdcproto.device.router.MessageRouter:
        return self.feature_descriptor.device_descriptor.router

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
            assert self.event_arguments is None
        else:
            assert len(event_args) == len(self.event_arguments)

            for arg_value, arg_descriptor in zip(event_args, self.event_arguments):
                arg_as_raw_bytes = arg_descriptor.dtype.value_to_bytes(arg_value)
                event_message.extend(arg_as_raw_bytes)

        event_message = bytes(event_message)

        self._send_event_message_raw(event_message=event_message)

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.event_id,
            name=self.event_name,
            doc=self.event_description,
            args=[arg.to_idl_dict()
                  for arg in self.event_arguments])


class LogEventDescriptor(EventDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         event_id=EvtID.LOG,
                         event_name="Log",
                         event_description="Forwards software event log to the host.",
                         event_arguments=(ArgD(HdcDataType.UINT8, 'LogLevel', doc="Same as in Python"),
                                          ArgD(HdcDataType.UTF8, 'LogMsg')))

    def emit(self, log_level: int, log_msg: str) -> None:
        if log_level >= self.feature_descriptor.log_event_threshold:
            self.logger.info(f"Sending {self.event_name}-event -> ({logging.getLevelName(log_level)}, '{log_msg}')")
            self._send_event_message(event_args=[log_level, log_msg])


class HdcLoggingHandler(logging.Handler):
    """Python logging handler which emits HDC Log-events on a given HDC-feature."""

    def __init__(self, log_event_descriptor: LogEventDescriptor):
        super().__init__()
        self.log_event_descriptor = log_event_descriptor

    def emit(self, record):
        # noinspection PyBroadException
        try:
            msg = self.format(record)
            self.log_event_descriptor.emit(record.levelno, msg)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


class FeatureStateTransitionEventDescriptor(EventDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         event_id=EvtID.FEATURE_STATE_TRANSITION,
                         event_name="FeatureStateTransition",
                         event_description="Notifies host about transitions of this feature's state-machine.",
                         event_arguments=(ArgD(HdcDataType.UINT8, 'PreviousStateID'),
                                          ArgD(HdcDataType.UINT8, 'CurrentStateID')))

    def emit(self, previous_state_id: int, current_state_id: int) -> None:
        if not is_valid_uint8(previous_state_id):
            raise ValueError(f"previous_state_id of {previous_state_id} is beyond valid range from 0x00 to 0xFF")
        if not is_valid_uint8(current_state_id):
            raise ValueError(f"current_state_id of {current_state_id} is beyond valid range from 0x00 to 0xFF")
        self.logger.info(f"Sending {self.event_name}-event -> (0x{previous_state_id:02X}, 0x{current_state_id:02X}')")
        self._send_event_message(event_args=[previous_state_id, current_state_id])


class PropertyDescriptorBase:
    feature_descriptor: FeatureDescriptorBase
    property_id: int
    property_name: str
    property_description: str
    property_type: HdcDataType
    property_implementation: int | float | str | bytes | HdcDataType | None
    property_getter: typing.Callable[[None], int | float | str | bytes | HdcDataType]
    property_setter: typing.Callable[[int | float | str | bytes], int | float | str | bytes | HdcDataType] | None

    def __init__(self,
                 feature_descriptor: FeatureDescriptorBase,
                 property_id: int,
                 property_name: str,
                 property_description: str | None,
                 property_type: HdcDataType,
                 property_getter: typing.Callable[[], int | float | str | bytes | HdcDataType],
                 property_setter: typing.Callable[[int | float | str | bytes], int | float | str | bytes | HdcDataType] | None
                 ):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.descriptor.MyDeviceDescriptor.MyFeatureDescriptor.MyPropertyDescriptor"
        self.logger = feature_descriptor.logger.getChild(self.__class__.__name__)

        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as descriptor for PropertyID=0x{property_id:02X} "
                          f"on FeatureID=0x{feature_descriptor.feature_id:02X}")

        # Reference from feature --> property
        if property_id in feature_descriptor.property_descriptors:
            self.logger.warning(f"Replacing previous descriptor instance of type "
                                f"{feature_descriptor.property_descriptors[property_id].__class__.__name__} with new"
                                f"instance of type {self.__class__.__name__} for "
                                f"PropertyID=0x{property_id:02X}")
        feature_descriptor.property_descriptors[property_id] = self

        self.feature_descriptor = feature_descriptor  # Reference from property --> feature
        self.property_id = property_id

        if not property_name:
            raise ValueError("Property name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.property_name = property_name

        if property_description is None:
            property_description = ""
        self.property_description = property_description

        if not isinstance(property_type, HdcDataType):
            raise ValueError("property_type must be specified as HdcDataType")
        self.property_type = property_type

        self.property_getter = property_getter  # ToDo: Validate getter signature
        self.property_setter = property_setter  # ToDo: Validate setter signature

    @property
    def property_is_readonly(self) -> bool:
        return self.property_setter is None

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.property_id,
            name=self.property_name,
            dtype=self.property_type.name,
            # ToDo: ValueSize attribute, as in STM32 implementation
            ro=self.property_is_readonly,
            doc=self.property_description)


class StateDescriptor:
    feature_descriptor: FeatureDescriptorBase
    state_id: int
    state_name: str
    state_description: str | None

    def __init__(self,
                 state_id: int,
                 state_name: str,
                 state_description: str | None = None):

        if not is_valid_uint8(state_id):
            raise ValueError(f"state_id value of {state_id} is beyond valid range from 0x00 to 0xFF")

        self.state_id = state_id

        if not state_name:
            raise ValueError("State name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.state_name = state_name

        self.state_description = state_description

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.state_id,
            name=self.state_name,
            doc=self.state_description
        )


class FeatureDescriptorBase:
    feature_id: int
    feature_name: str
    feature_class_name: str
    feature_class_version: str | semver.VersionInfo | None
    feature_description: str | None
    device_descriptor: DeviceDescriptorBase
    state_descriptors: dict[int, StateDescriptor] | None
    command_descriptors: dict[int, CommandDescriptorBase]
    event_descriptors: dict[int, EventDescriptorBase]
    property_descriptors: dict[int, PropertyDescriptorBase]

    feature_state_id: int

    def __init__(self,
                 device_descriptor: DeviceDescriptorBase,
                 feature_id: int,
                 feature_name: str,
                 feature_class_name: str,
                 feature_class_version: str | semver.VersionInfo | None = None,
                 feature_description: str | None = None,
                 feature_states: typing.Type[enum.IntEnum] | list[StateDescriptor] | None = None):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.descriptor.MyDeviceDescriptor.MyFeatureDescriptor"
        self.logger = device_descriptor.logger.getChild(self.__class__.__name__)

        if not is_valid_uint8(feature_id):
            raise ValueError(f"feature_id value of 0x{feature_id:02X} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as descriptor for FeatureID=0x{feature_id:02X}")

        # Reference from device --> feature
        if feature_id in device_descriptor.feature_descriptors:
            self.logger.warning(f"Replacing previous descriptor instance of type "
                                f"{device_descriptor.feature_descriptors[feature_id].__class__.__name__} with new"
                                f"instance of type {self.__class__.__name__} for "
                                f"FeatureID=0x{feature_id:02X}")
        device_descriptor.feature_descriptors[feature_id] = self

        self.device_descriptor = device_descriptor  # Reference from feature --> device
        self.feature_id = feature_id

        if not feature_name:
            raise ValueError("feature_name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.feature_name = feature_name

        if not feature_class_name:
            raise ValueError("feature_class_name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.feature_class_name = feature_class_name

        if feature_class_version is not None and not isinstance(feature_class_version, semver.VersionInfo):
            feature_class_version = semver.VersionInfo.parse(feature_class_version)
        self.feature_class_version = feature_class_version

        if feature_description is None:
            feature_description = ""
        self.feature_description = feature_description

        if feature_states is None:
            # Meaning "None documented". Do not confuse with "Has no states", which would be an empty list.
            self.state_descriptors = None
        else:
            self.state_descriptors: dict[int, StateDescriptor] = dict()
            for d in feature_states:
                if isinstance(d, enum.IntEnum):
                    d = StateDescriptor(state_id=d, state_name=d.name)
                if d.state_id in self.state_descriptors.keys():
                    ValueError("feature_states contains duplicate ID values")
                self.state_descriptors[d.state_id] = d

        self.feature_state_id = 0  # ToDo: Should we establish a convention about initializing states to zero? Nah...
        self.log_event_threshold = logging.WARNING

        # Commands
        self.command_descriptors = dict()
        self.cmd_get_property_value = GetPropertyValueCommandDescriptor(self)
        self.cmd_set_property_value = SetPropertyValueCommandDescriptor(self)

        # Events
        self.event_descriptors = dict()
        self.evt_state_transition = FeatureStateTransitionEventDescriptor(self)
        self.evt_log = LogEventDescriptor(self)

        # Use a dedicated logger for this feature-instance, whose logs will be forwarded as HDC Log-events to the host.
        self.hdc_logger = logging.getLogger(str(uuid.uuid4()))
        self.hdc_logger.addHandler(HdcLoggingHandler(log_event_descriptor=self.evt_log))

        # Properties
        self.property_descriptors = dict()

        self.prop_log_event_threshold = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.LOG_EVT_THRESHOLD,
            property_name='LogEventThreshold',
            property_description="Suppresses LogEvents with lower log-levels.",
            property_type=HdcDataType.UINT8,
            property_getter=lambda: self.log_event_threshold,
            property_setter=self.prop_log_event_threshold_setter
        )

        self.prop_feature_state = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.FEAT_STATE,
            property_name='FeatureState',
            property_description="Current feature-state",
            property_type=HdcDataType.UINT8,
            property_getter=lambda: self.feature_state_id,
            property_setter=None  # Not exposing a setter on HDC interface does *not* mean this is immutable. ;-)
        )

    def prop_log_event_threshold_setter(self, new_threshold: int) -> int:
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
        return self.device_descriptor.router

    def feature_state_transition(self, new_feature_state_id: int):  # ToDo: Improve naming: Imperative verb
        if self.state_descriptors is None:
            raise RuntimeError("Cannot switch feature state if none were registered for this feature")

        if new_feature_state_id not in self.state_descriptors:
            raise ValueError(f"Unknown state_id {new_feature_state_id}")

        previous_state_id = self.feature_state_id
        self.logger.info(f"Transitioning FeatureState from previously 0x{previous_state_id:02X} to "
                         f"now 0x{new_feature_state_id:02X}.")
        self.feature_state_id = new_feature_state_id
        self.evt_state_transition.emit(previous_state_id=previous_state_id,
                                       current_state_id=new_feature_state_id)

    def to_idl_dict(self) -> dict:
        return {  # Using alternative syntax, because ...
            "id": self.feature_id,
            "name": self.feature_name,
            "class": self.feature_class_name,  # ... 'class' is a reserved keyword in Python!
            "version": str(self.feature_class_version) if self.feature_class_version is not None else None,
            "doc": self.feature_description,
            "states": [
                d.to_idl_dict()
                for d in sorted(self.state_descriptors.values(), key=lambda d: d.state_id)
            ] if self.state_descriptors is not None else None,
            "commands": [
                d.to_idl_dict()
                for d in sorted(self.command_descriptors.values(), key=lambda d: d.command_id)
            ],
            "events": [
                d.to_idl_dict()
                for d in sorted(self.event_descriptors.values(), key=lambda d: d.event_id)
            ],
            "properties": [
                d.to_idl_dict()
                for d in sorted(self.property_descriptors.values(), key=lambda d: d.property_id)
            ]
        }


class CoreFeatureDescriptorBase(FeatureDescriptorBase):
    def __init__(self,
                 device_descriptor: DeviceDescriptorBase,
                 feature_states: typing.Type[enum.IntEnum] | list[StateDescriptor] | None = None):
        super().__init__(
            device_descriptor=device_descriptor,
            feature_id=FeatureID.CORE.CORE,
            feature_name="Core",
            feature_class_name=device_descriptor.device_name,
            feature_class_version=device_descriptor.device_version,
            feature_description=device_descriptor.device_description,
            feature_states=feature_states
        )


class DeviceDescriptorBase:
    device_name: str
    device_version: semver.VersionInfo | None
    device_description: str | None
    router: hdcproto.device.router.MessageRouter
    feature_descriptors: dict[int, FeatureDescriptorBase]

    def __init__(self,
                 connection_url: str,
                 device_name: str,
                 device_version: str | semver.VersionInfo | None,
                 device_description: str | None,
                 core_feature_descriptor_class=CoreFeatureDescriptorBase,
                 max_req_msg_size: int = 2048):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.descriptor.MyDeviceDescriptor"
        self.device_name = device_name

        if device_version is not None and not isinstance(device_version, semver.VersionInfo):
            device_version = semver.VersionInfo.parse(device_version)
        self.device_version = device_version
        self.device_description = device_description
        self.logger = logger.getChild(self.__class__.__name__)

        self.router = hdcproto.device.router.MessageRouter(connection_url=connection_url,
                                                           max_req_msg_size=max_req_msg_size,
                                                           idl_json_generator=self.to_idl_json)

        self.feature_descriptors = dict()

        # The Core feature is quite essential for basic HDC operation, thus this constructor enforces it
        self.core = core_feature_descriptor_class(self)

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

    def __enter__(self) -> DeviceDescriptorBase:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def to_idl_dict(self) -> dict:
        return dict(
            version=hdcproto.common.HDC_VERSION,
            max_req=self.router.max_req_msg_size,
            features=[
                d.to_idl_dict()
                for d in sorted(self.feature_descriptors.values(), key=lambda d: d.feature_id)
            ]
        )

    def to_idl_json(self) -> str:
        idl_dict = self.to_idl_dict()

        def prune_none_values(d: dict[str, typing.Any]) -> int:
            """Removes attribute with a None value.
            Dives recursively into values of type dict and list[dict]"""
            keys_of_none_items = [key for key, value in d.items() if value is None]
            num_deleted_items = len(keys_of_none_items)
            for k in keys_of_none_items:
                del (d[k])
            for key, value in d.items():
                if isinstance(value, dict):
                    num_deleted_items += prune_none_values(value)
                elif isinstance(value, list):
                    for list_item in value:
                        if isinstance(list_item, dict):
                            num_deleted_items += prune_none_values(list_item)

            return num_deleted_items

        prune_none_values(idl_dict)
        return json.dumps(idl_dict)
