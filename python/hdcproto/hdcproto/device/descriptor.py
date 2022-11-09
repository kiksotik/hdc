from __future__ import annotations

import enum
import logging
import typing
import uuid

import hdcproto.device
import hdcproto.device.router
import hdcproto.transport.serialport
from hdcproto.common import (is_valid_uint8, CommandErrorCode, HdcDataType, HdcCommandError,
                             MessageTypeID, FeatureID, CmdID, EvtID, PropID, HdcDataTypeError)

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.device.descriptor"


class FeatureDescriptorBase:
    feature_id: int
    feature_name: str
    feature_type_name: str
    feature_type_revision: int
    feature_description: str | None
    feature_tags: str | None
    feature_states_description: str | None
    device_descriptor: DeviceDescriptorBase
    command_descriptors: dict[int, CommandDescriptorBase]
    event_descriptors: dict[int, EventDescriptorBase]
    property_descriptors: dict[int, PropertyDescriptorBase]

    feature_state_id: int

    def __init__(self,
                 device_descriptor: DeviceDescriptorBase,
                 feature_id: int,
                 feature_name: str,
                 feature_type_name: str,
                 feature_type_revision: int,
                 feature_description: str | None = None,
                 feature_tags: str | None = None,
                 feature_states_description: str | None = None
                 ):
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
            raise ValueError("feature_name must be a non-empty string")
        self.feature_name = feature_name

        if not feature_type_name:
            raise ValueError("feature_type_name must be a non-empty string")
        self.feature_type_name = feature_type_name

        if not is_valid_uint8(feature_type_revision):
            raise ValueError(f"feature_type_revision value of 0x{feature_id:02X} "
                             f"is beyond valid range from 0x00 to 0xFF")
        self.feature_type_revision = feature_type_revision

        if feature_description is None:
            feature_description = ""
        self.feature_description = feature_description

        if feature_tags is None:
            feature_tags = ""
        self.feature_tags = feature_tags

        # ToDo: Also use descriptors for FeatureState IDs, instead of a docstring!
        if feature_states_description is None:
            feature_states_description = ""
        self.feature_states_description = feature_states_description

        self.feature_state_id = 0
        self.log_event_threshold = logging.WARNING

        # Commands
        self.command_descriptors = dict()
        self.cmd_get_property_name = GetPropertyNameCommandDescriptor(self)
        self.cmd_get_property_type = GetPropertyTypeCommandDescriptor(self)
        self.cmd_get_property_readonly = GetPropertyReadonlyCommandDescriptor(self)
        self.cmd_get_property_value = GetPropertyValueCommandDescriptor(self)
        self.cmd_set_property_value = SetPropertyValueCommandDescriptor(self)
        self.cmd_get_property_description = GetPropertyDescriptionCommandDescriptor(self)
        self.cmd_get_command_name = GetCommandNameCommandDescriptor(self)
        self.cmd_get_command_description = GetCommandDescriptionCommandDescriptor(self)
        self.cmd_get_event_name = GetEventNameCommandDescriptor(self)
        self.cmd_get_event_description = GetEventDescriptionCommandDescriptor(self)

        # Events
        self.event_descriptors = dict()
        self.evt_state_transition = FeatureStateTransitionEventDescriptor(self)
        self.evt_log = LogEventDescriptor(self)

        # Use a dedicated logger for this feature-instance, whose logs will be forwarded as HDC Log-events to the host.
        self.hdc_logger = logging.getLogger(str(uuid.uuid4()))
        self.hdc_logger.addHandler(HdcLoggingHandler(log_event_descriptor=self.evt_log))

        # Properties
        self.property_descriptors = dict()
        self.prop_feature_name = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.FEAT_NAME,
            property_name='FeatureName',
            property_description="Unique label of this feature-instance.",
            property_type=HdcDataType.UTF8,
            property_getter=lambda: self.feature_name,
            property_setter=None
        )

        self.prop_feature_type_name = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.FEAT_TYPE_NAME,
            property_name='FeatureTypeName',
            property_description="Unique label of this feature's class.",
            property_type=HdcDataType.UTF8,
            property_getter=lambda: self.feature_type_name,
            property_setter=None
        )

        self.prop_feature_type_revision = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.FEAT_TYPE_REV,
            property_name='FeatureTypeRevision',
            property_description="Revision number of this feature's class-implementation.",
            property_type=HdcDataType.UINT8,
            property_getter=lambda: self.feature_type_revision,
            property_setter=None
        )

        self.prop_feature_description = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.FEAT_DESCR,
            property_name='FeatureDescription',
            property_description="Human readable documentation about this feature.",
            property_type=HdcDataType.UTF8,
            property_getter=lambda: self.feature_description,
            property_setter=None
        )

        self.prop_feature_tags = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.FEAT_TAGS,
            property_name='FeatureTags',
            property_description="Semicolon-delimited list of tags and categories associated with this feature.",
            property_type=HdcDataType.UTF8,
            property_getter=lambda: self.feature_tags,
            property_setter=None
        )

        self.prop_available_commands = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.AVAIL_CMD,
            property_name='AvailableCommands',
            property_description="List of IDs of commands available on this feature.",
            property_type=HdcDataType.BLOB,
            property_getter=lambda: bytes(cmd.command_id for cmd in self.command_descriptors.values()),
            property_setter=None
        )

        self.prop_available_events = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.AVAIL_EVT,
            property_name='AvailableEvents',
            property_description="List of IDs of events available on this feature.",
            property_type=HdcDataType.BLOB,
            property_getter=lambda: bytes(evt.event_id for evt in self.event_descriptors.values()),
            property_setter=None
        )

        self.prop_available_properties = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.AVAIL_PROP,
            property_name='AvailableProperties',
            property_description="List of IDs of properties available on this feature.",
            property_type=HdcDataType.BLOB,
            property_getter=lambda: bytes(prop.property_id for prop in self.property_descriptors.values()),
            property_setter=None
        )

        self.prop_feature_state = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.FEAT_STATE,
            property_name='FeatureState',
            property_description=self.feature_states_description,
            property_type=HdcDataType.UINT8,
            property_getter=lambda: self.feature_state_id,
            property_setter=None  # Not exposing a setter on HDC interface does *not* mean this is immutable. ;-)
        )

        self.prop_log_event_threshold = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.LOG_EVT_THRESHOLD,
            property_name='LogEventThreshold',
            property_description="Suppresses LogEvents with lower log-levels.",
            property_type=HdcDataType.UINT8,
            property_getter=lambda: self.log_event_threshold,
            property_setter=self.prop_log_event_threshold_setter
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

    def feature_state_transition(self, new_feature_state_id: int):  # ToDo: Improve naming!
        previous_state_id = self.feature_state_id
        self.logger.info(f"Transitioning FeatureState from previously 0x{previous_state_id:02X} to "
                         f"now 0x{new_feature_state_id:02X}.")
        self.feature_state_id = new_feature_state_id
        self.evt_state_transition.emit(previous_state_id=previous_state_id,
                                       current_state_id=new_feature_state_id)


class CoreFeatureDescriptorBase(FeatureDescriptorBase):
    def __init__(self, device_descriptor: DeviceDescriptorBase):
        super().__init__(
            device_descriptor=device_descriptor,
            feature_id=FeatureID.CORE.CORE,
            feature_name="Core",
            feature_type_name=self.__class__.__name__,
            feature_type_revision=0  # To be overriden in specific subclass!
        )

        # Mandatory properties of a Core feature as required by HDC-spec

        self.prop_available_features = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.AVAIL_FEAT,
            property_name='AvailableFeatures',
            property_description="List of IDs of features available on this device.",
            property_type=HdcDataType.BLOB,
            property_getter=lambda: bytes(feat.feature_id
                                          for feat in self.device_descriptor.feature_descriptors.values()),
            property_setter=None
        )

        self.prop_max_req_msg_size = PropertyDescriptorBase(
            feature_descriptor=self,
            property_id=PropID.MAX_REQ_MSG_SIZE,
            property_name='MaxReqMsgSize',
            property_description="Maximum number of bytes of a request message that this device can cope with.",
            property_type=HdcDataType.UINT32,
            property_getter=lambda: self.device_descriptor.max_req_msg_size,
            property_setter=None
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
    command_request_handler: typing.Callable[[bytes], None]
    command_raises: dict[int, str]
    msg_prefix: bytes

    def __init__(self,
                 feature_descriptor: FeatureDescriptorBase,
                 command_id: int,
                 command_name: str,
                 command_description: str | None,
                 command_request_handler: typing.Callable[[bytes], None],
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
            command_request_handler=command_request_handler)

        self.command_id = command_id

        if not command_name:
            raise ValueError("Command name must be a non-empty string")
        self.command_name = command_name

        if command_raises is None:
            command_raises = list()
        self.command_raises = dict()
        for error_enum in command_raises:
            if not isinstance(error_enum, CommandErrorCode) and CommandErrorCode.is_custom(int(error_enum)):
                raise ValueError(f"Mustn't override meaning of predefined or reserved "
                                 f"CommandErrorCode 0x{error_enum:02X}")
            self.command_raises[int(error_enum)] = str(error_enum)

        self.command_description = command_description

        self.msg_prefix = bytes([int(MessageTypeID.COMMAND),
                                 self.feature_descriptor.feature_id,
                                 self.command_id])

    def build_cmd_error(self,
                        error_code: enum.IntEnum,
                        error_message: str | None = None) -> HdcCommandError:
        """
        Either for any of the predefined CommandErrorCode, or for custom CommandErrorCodes as defined for each Command.

        Both usages allow for an optional message, which should only be used to supply any additional context, but
        should not merely duplicate what the CommandErrorCode's name is already expressing.
        """
        if not isinstance(error_code, CommandErrorCode) and CommandErrorCode.is_custom(int(error_code)):
            raise ValueError(f"Mustn't override meaning of predefined or reserved "
                             f"CommandErrorCode 0x{error_code:02X}")
        if error_code not in self.command_raises:
            raise ValueError(f"Mustn't reply with any CommandErrorCode not declared in the Command-descriptor")

        return HdcCommandError(
            feature_id=self.feature_descriptor.feature_id,
            command_id=self.command_id,
            error_code=error_code,
            error_name=self.command_raises[error_code],
            error_message=error_message
        )

    @property
    def router(self) -> hdcproto.device.router.MessageRouter:
        return self.feature_descriptor.device_descriptor.router


class TypedCommandDescriptor(CommandDescriptorBase):
    """
    Descriptor which also takes care to parse arguments and reply in a type-safe manner.
    Will also inject documentation of command-signature into the docstring of this command.
    """
    command_implementation: typing.Callable[[typing.Any], typing.Any]
    command_arguments: list[tuple[HdcDataType, str]] | None
    command_returns: list[tuple[HdcDataType, str]] | None

    def __init__(self,
                 feature_descriptor: FeatureDescriptorBase,
                 command_id: int,
                 command_name: str,
                 command_description: str | None,
                 command_implementation: typing.Callable[[typing.Any], typing.Any],
                 command_arguments: list[tuple[HdcDataType, str]] | None,
                 command_returns: list[tuple[HdcDataType, str]] | None,
                 command_raises: list[enum.IntEnum] | None):

        super().__init__(feature_descriptor=feature_descriptor,
                         command_id=command_id,
                         command_name=command_name,
                         command_description=command_description,
                         command_request_handler=self._command_request_handler,
                         command_raises=command_raises)

        if command_arguments is None:
            command_arguments = list()
        if any(arg_type.size is None for arg_type, arg_name in command_arguments[:-1]):
            raise ValueError("Only last argument may be of a variable-size data-type")
        self.command_arguments = command_arguments

        if command_returns is None:
            command_returns = list()
        if any(return_type.size is None for return_type, return_name in command_returns[:-1]):
            raise ValueError("Only last return-value may be of a variable-size data-type")
        self.command_returns = command_returns

        # Validate signature of implementation to be compatible with HDC args and returns
        self.command_implementation = command_implementation

        description_already_contains_command_signature = command_description.startswith('(')
        if not description_already_contains_command_signature:
            cmd_signature = "("
            cmd_signature += ', '.join(f"{arg_type.name} {arg_name}" for arg_type, arg_name in self.command_arguments)
            cmd_signature += ") -> "
            if not self.command_returns:
                cmd_signature += "VOID"
            elif len(self.command_returns) == 1:
                return_type, return_name = self.command_returns[0]
                cmd_signature += f"{return_type.name} {return_name}"
            else:
                cmd_signature += "("
                cmd_signature += ', '.join(f"{ret_type.name} {ret_name}" for ret_type, ret_name in self.command_returns)
                cmd_signature += ")"
            if command_description:
                self.command_description = cmd_signature + '\n' + command_description
            else:
                self.command_description = cmd_signature

    def _command_request_handler(self, request_message: bytes) -> None:
        reply = bytearray(self.msg_prefix)
        parsed_arguments = HdcDataType.parse_payload(
            raw_payload=request_message[3:],  # MsgID + FeatureID + CmdID
            expected_data_types=[arg_type for arg_type, arg_name in self.command_arguments]
        )
        try:
            return_values = self.command_implementation(*parsed_arguments)
        except HdcCommandError:
            raise
        except ValueError as e:
            raise self.build_cmd_error(error_code=CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS, error_message=str(e))
        except Exception as e:
            raise self.build_cmd_error(error_code=CommandErrorCode.COMMAND_FAILED, error_message=str(e))
        else:
            reply.append(CommandErrorCode.NO_ERROR)

        if return_values is None:
            return_values = tuple()

        if not isinstance(return_values, tuple) and not isinstance(return_values, list):
            return_values = tuple([return_values])

        if len(return_values) != len(self.command_returns):
            raise RuntimeError("Command implementation did not return the expected number of return values")

        for i, (ret_type, ret_name) in enumerate(self.command_returns):
            ret_type: HdcDataType
            ret_value = return_values[i]
            reply.extend(ret_type.value_to_bytes(ret_value))
        reply = bytes(reply)
        self.router.send_reply_for_pending_request(reply)


class GetPropertyNameCommandDescriptor(TypedCommandDescriptor):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_PROP_NAME,
                         command_name="GetPropertyName",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'PropertyID')],
                         command_returns=[(HdcDataType.UTF8, 'Name')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_PROPERTY,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, property_id: int) -> str:
        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_PROPERTY)

        self.logger.info(f"Replying with {self.command_name}(0x{property_id:02X}) "
                         f"-> '{prop_descr.property_name}'")
        return prop_descr.property_name


class GetPropertyTypeCommandDescriptor(TypedCommandDescriptor):

    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_PROP_TYPE,
                         command_name="GetPropertyType",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'PropertyID')],
                         command_returns=[(HdcDataType.UINT8, 'DataTypeID')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_PROPERTY,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, property_id: int) -> int:
        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_PROPERTY)

        self.logger.info(f"Replying with {self.command_name}('{prop_descr.property_name}') "
                         f"-> {prop_descr.property_type.name}")
        return prop_descr.property_type


class GetPropertyReadonlyCommandDescriptor(TypedCommandDescriptor):

    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_PROP_RO,
                         command_name="GetPropertyReadonly",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'PropertyID')],
                         command_returns=[(HdcDataType.BOOL, 'IsReadonly')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_PROPERTY,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, property_id: int) -> bool:
        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_PROPERTY)

        self.logger.info(f"Replying with {self.command_name}('{prop_descr.property_name}') "
                         f"-> {prop_descr.property_is_readonly}")
        return prop_descr.property_is_readonly


class GetPropertyValueCommandDescriptor(CommandDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_PROP_VALUE,
                         command_name="GetPropertyValue",
                         # Signature uses 'var' to express that data-type depends on requested property
                         command_description="(UINT8 PropertyID) -> var Value",
                         command_request_handler=self._command_request_handler,
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_PROPERTY,
                                         CommandErrorCode.COMMAND_FAILED])

    def _command_request_handler(self, request_message: bytes) -> None:
        """
        Custom request handler, because GetPropertyValue-command returns
        variable data-types, depending on the requested PropertyID.
        """
        if len(request_message) != 4:  # MsgID + FeatID + CmdID + PropID
            raise self.build_cmd_error(error_code=CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS)
        property_id = request_message[3]

        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_PROPERTY)

        prop_type = prop_descr.property_type
        prop_value = prop_descr.property_getter()
        value_as_bytes = prop_type.value_to_bytes(prop_value)

        reply = bytearray(self.msg_prefix)
        reply.append(CommandErrorCode.NO_ERROR)
        reply.extend(value_as_bytes)

        reply = bytes(reply)
        self.logger.info(f"Replying with {self.command_name}('{prop_descr.property_name}') "
                         f"-> {repr(prop_value)}")
        self.router.send_reply_for_pending_request(reply)


class SetPropertyValueCommandDescriptor(CommandDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.SET_PROP_VALUE,
                         command_name="SetPropertyValue",
                         command_request_handler=self._command_request_handler,
                         # Signature uses 'var' to express that data-type depends on requested property
                         command_description="(UINT8 PropertyID, var NewValue) -> var ActualNewValue",
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_PROPERTY,
                                         CommandErrorCode.PROPERTY_IS_READ_ONLY,
                                         CommandErrorCode.INVALID_PROPERTY_VALUE])

    def _command_request_handler(self, request_message: bytes) -> None:
        """
        Custom request handler, because GetPropertyValue-command returns
        variable data-types, depending on the requested PropertyID.
        """

        if len(request_message) < 4:  # MsgID + FeatID + CmdID + PropID + var NewValue
            raise self.build_cmd_error(error_code=CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS)
        property_id = request_message[3]

        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_PROPERTY)

        prop_type = prop_descr.property_type
        if len(request_message) != 4 + prop_type.size():  # MsgID + FeatID + CmdID + PropID + var NewValue
            raise self.build_cmd_error(error_code=CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS)

        new_value_as_bytes = request_message[4:]
        try:
            new_value = prop_type.bytes_to_value(new_value_as_bytes)
            actual_new_value = prop_descr.property_setter(new_value)
        except (HdcDataTypeError, ValueError) as e:
            raise self.build_cmd_error(CommandErrorCode.INVALID_PROPERTY_VALUE, error_message=str(e))

        actual_new_value_as_bytes = prop_type.value_to_bytes(actual_new_value)

        reply = bytearray(self.msg_prefix)
        reply.append(CommandErrorCode.NO_ERROR)
        reply.extend(actual_new_value_as_bytes)

        reply = bytes(reply)

        self.logger.log(level=logging.INFO if new_value == actual_new_value else logging.WARNING,
                        msg=f"Replying with {self.command_name}('{prop_descr.property_name}', {repr(new_value)}) "
                            f"-> {repr(actual_new_value)}")

        self.router.send_reply_for_pending_request(reply)


class GetPropertyDescriptionCommandDescriptor(TypedCommandDescriptor):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_PROP_DESCR,
                         command_name="GetPropertyDescription",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'PropertyID')],
                         command_returns=[(HdcDataType.UTF8, 'Description')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_PROPERTY,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, property_id: int) -> str:
        prop_descr = self.feature_descriptor.property_descriptors.get(property_id, None)
        if prop_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_PROPERTY)

        self.logger.info(f"Replying with {self.command_name}('{prop_descr.property_name}') "
                         f"-> '{prop_descr.property_description}'")

        return prop_descr.property_description


class GetCommandNameCommandDescriptor(TypedCommandDescriptor):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_CMD_NAME,
                         command_name="GetCommandName",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'CommandID')],
                         command_returns=[(HdcDataType.UTF8, 'Name')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_COMMAND,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, command_id: int) -> str:
        cmd_descr = self.feature_descriptor.command_descriptors.get(command_id, None)
        if cmd_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_COMMAND)

        self.logger.info(f"Replying with {self.command_name}(0x{command_id:02X}) "
                         f"-> '{cmd_descr.command_name}'")

        return cmd_descr.command_name


class GetCommandDescriptionCommandDescriptor(TypedCommandDescriptor):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_CMD_DESCR,
                         command_name="GetCommandDescription",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'CommandID')],
                         command_returns=[(HdcDataType.UTF8, 'Description')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_COMMAND,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, command_id: int) -> str:
        cmd_descr = self.feature_descriptor.command_descriptors.get(command_id, None)
        if cmd_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_COMMAND)

        self.logger.info(f"Replying with {self.command_name}('{cmd_descr.command_name}') "
                         f"-> '{cmd_descr.command_description}'")

        return cmd_descr.command_description


class GetEventNameCommandDescriptor(TypedCommandDescriptor):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_EVT_NAME,
                         command_name="GetEventName",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'EventID')],
                         command_returns=[(HdcDataType.UTF8, 'Name')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_EVENT,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, event_id: int) -> str:
        evt_descr = self.feature_descriptor.event_descriptors.get(event_id, None)
        if evt_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_EVENT)

        self.logger.info(f"Replying with {self.command_name}(0x{event_id:02X}) "
                         f"-> '{evt_descr.event_name}'")

        return evt_descr.event_name


class GetEventDescriptionCommandDescriptor(TypedCommandDescriptor):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         command_id=CmdID.GET_EVT_DESCR,
                         command_name="GetEventDescription",
                         command_implementation=self._cmd_impl,
                         command_description="",
                         command_arguments=[(HdcDataType.UINT8, 'EventID')],
                         command_returns=[(HdcDataType.UTF8, 'Description')],
                         command_raises=[CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS,
                                         CommandErrorCode.UNKNOWN_EVENT,
                                         CommandErrorCode.COMMAND_FAILED])

    def _cmd_impl(self, event_id: int) -> str:
        evt_descr = self.feature_descriptor.event_descriptors.get(event_id, None)
        if evt_descr is None:
            raise self.build_cmd_error(CommandErrorCode.UNKNOWN_EVENT)

        self.logger.info(f"Replying with {self.command_name}('{evt_descr.event_name}') "
                         f"-> '{evt_descr.event_description}'")

        return evt_descr.event_description


class EventDescriptorBase:
    feature_descriptor: FeatureDescriptorBase
    event_id: int
    event_name: str
    event_description: str
    event_arguments: list[tuple[HdcDataType, str]] | None
    msg_prefix: bytes

    def __init__(self,
                 feature_descriptor: FeatureDescriptorBase,
                 event_id: int,
                 event_name: str,
                 event_description: str | None,
                 event_arguments: list[tuple[HdcDataType, str]] | None):

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
            raise ValueError("Event name must be a non-empty string")
        self.event_name = event_name

        if event_arguments is None:
            event_arguments = list()
        if any(arg_type.size is None for arg_type, arg_name in event_arguments[:-1]):
            raise ValueError("Only last argument may be of a variable-size data-type")
        self.event_arguments = event_arguments

        description_already_contains_event_signature = event_description.startswith('(')
        if not description_already_contains_event_signature:
            evt_signature = "("
            evt_signature += ', '.join(f"{arg_type.name} {arg_name}" for arg_type, arg_name in self.event_arguments)
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

    def _send_event_message(self, event_args: list[typing.Any] | None) -> None:
        event_message = bytearray(self.msg_prefix)

        if event_args is None:
            event_args = list()

        assert len(event_args) == len(self.event_arguments)

        for arg_value, (arg_type, arg_name) in zip(event_args, self.event_arguments):
            arg_as_raw_bytes = arg_type.value_to_bytes(arg_value)
            event_message.extend(arg_as_raw_bytes)

        event_message = bytes(event_message)

        self.router.send_event_message(event_message=event_message)


class LogEventDescriptor(EventDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor,
                         event_id=EvtID.LOG,
                         event_name="Log",
                         event_description="",
                         event_arguments=[(HdcDataType.UINT8, 'LogLevel'),
                                          (HdcDataType.UTF8, 'LogMsg')])

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
                         event_description="",
                         event_arguments=[(HdcDataType.UINT8, 'PreviousStateID'),
                                          (HdcDataType.UINT8, 'CurrentStateID')])

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
    property_implementation: int | float | str | bytes | None
    property_getter: typing.Callable[[None], int | float | str | bytes]
    property_setter: typing.Callable[[int | float | str | bytes], int | float | str | bytes] | None

    def __init__(self,
                 feature_descriptor: FeatureDescriptorBase,
                 property_id: int,
                 property_name: str,
                 property_description: str | None,
                 property_type: HdcDataType,
                 property_getter: typing.Callable[[], int | float | str | bytes],
                 property_setter: typing.Callable[[int | float | str | bytes], int | float | str | bytes] | None
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
            raise ValueError("Property name must be a non-empty string")
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


class DeviceDescriptorBase:
    router: hdcproto.device.router.MessageRouter
    feature_descriptors: dict[int, FeatureDescriptorBase]
    max_req_msg_size: int

    def __init__(self,
                 connection_url: str,
                 core_feature_descriptor_class=CoreFeatureDescriptorBase,
                 max_req_msg_size: int = 2048):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.device.descriptor.MyDeviceDescriptor"
        self.logger = logger.getChild(self.__class__.__name__)

        if max_req_msg_size < 5:
            raise ValueError("Configuring HDC_MAX_REQ_MESSAGE_SIZE to less than 5 bytes surely is wrong! "
                             "(e.g. request of a UINT8 property-setter requires 5 byte)")
        self.max_req_msg_size = max_req_msg_size  # ToDo: Pass this limit to the SerialTransport & Packetizer. Issue #19

        self.router = hdcproto.device.router.MessageRouter(connection_url=connection_url)

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
