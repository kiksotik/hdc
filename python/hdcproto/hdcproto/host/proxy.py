"""
Proxy classes for the device and its features and properties
"""
from __future__ import annotations

import collections
import logging
import time
import typing
from datetime import datetime

import hdcproto.host.router
import hdcproto.transport.serialport
from hdcproto.common import (HdcError, MessageType, FeatureID, CmdID, ReplyErrorCode, EvtID, PropID, HdcDataType,
                             is_valid_uint8)

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.host.proxy"

DEFAULT_REPLY_TIMEOUT = 0.2


class CommandProxyBase:
    feature_proxy: FeatureProxyBase
    command_id: int
    default_timeout: float
    known_errors: dict[int, str]
    msg_prefix: bytes

    def __init__(self,
                 feature_proxy: FeatureProxyBase,
                 command_id: int,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy.MyCommandProxy"
        self.logger = feature_proxy.logger.getChild(self.__class__.__name__)

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for CommandID=0x{command_id:02X} on FeatureID=0x{feature_proxy.feature_id:02X}")

        if not is_valid_uint8(command_id):
            raise ValueError(f"command_id value of {command_id} is beyond valid range from 0x00 to 0xFF")

        self.feature_proxy = feature_proxy
        self.command_id = command_id
        self.default_timeout = default_timeout
        self.known_errors = dict()

        self.msg_prefix = bytes([int(MessageType.CMD_FEATURE),
                                 self.feature_proxy.feature_id,
                                 self.command_id])

        # Register mandatory error codes
        self.register_error(ReplyErrorCode.NO_ERROR)
        self.register_error(ReplyErrorCode.UNKNOWN_FEATURE)
        self.register_error(ReplyErrorCode.UNKNOWN_COMMAND)
        self.register_error(ReplyErrorCode.INCORRECT_COMMAND_ARGUMENTS)
        self.register_error(ReplyErrorCode.COMMAND_NOT_ALLOWED_NOW)
        self.register_error(ReplyErrorCode.COMMAND_FAILED)

    def register_error(self, code: int | ReplyErrorCode, error_name: str | None = None) -> None:
        if isinstance(code, ReplyErrorCode):
            code = int(code)
            error_name = str(code)
        else:
            # Disallow overriding ReplyErrorCodes whose meaning is already predefined and thus reserved by HDC-spec
            try:
                code_as_defined_by_hdc_spec = ReplyErrorCode(code)
            except ValueError:
                pass  # Meaning this code is *not* defined by HDC-spec, thus it's available for custom use.
            else:
                raise ValueError(f"Failed to register ReplyErrorCode 0x{code:02X}:'{error_name}', because that it's "
                                 f"already defined by HDC-spec to mean '{code_as_defined_by_hdc_spec}'")

        code = int(code)

        if not is_valid_uint8(code):
            raise ValueError(f"Reply error code of {code} is beyond valid range from 0x00 to 0xFF")

        if error_name is None:
            error_name = f"Error 0x{code:02X}"  # Fallback for lazy callers

        if code in self.known_errors:
            raise ValueError(f'Already registered ErrorCode {code} as "{self.known_errors[code]}"')
        self.known_errors[code] = error_name

    def _send_request_and_get_reply(self, request_message: bytes, timeout: float) -> bytes:

        if not request_message.startswith(self.msg_prefix):
            raise ValueError("Request does not match the expected prefix")

        p = self.feature_proxy.router_feature.router  # Just an alias for readability

        reply_message = p.send_request_and_get_reply(request_message, timeout)

        if not reply_message.startswith(self.msg_prefix):
            # ToDo: Might be a delayed reply to a previous request that timed-out. Maybe we should just ignore it?
            raise HdcError("Reply does not match the expected prefix")

        if len(reply_message) < 4:
            raise HdcError(f"Expected a reply size of 4 or more bytes, "
                           f"but received {len(reply_message)}")

        error_code = reply_message[3]
        if error_code != ReplyErrorCode.NO_ERROR:
            error_name = self.known_errors.get(error_code, f"Unknown error code 0x{error_code:02X}")
            raise HdcReplyError(error_name, reply_message)

        return reply_message

    def _call_cmd(self,
                  cmd_args: list[tuple[HdcDataType, bool | int | float | str | bytes]] | None,
                  return_types: HdcDataType | list[HdcDataType] | None,
                  timeout: float | None = None) -> typing.Any:
        request_message = bytearray(self.msg_prefix)

        if cmd_args is None:
            cmd_args = list()

        for arg_data_type, arg_value in cmd_args:
            arg_as_raw_bytes = arg_data_type.value_to_bytes(arg_value)
            request_message.extend(arg_as_raw_bytes)

        if timeout is None:
            timeout = self.default_timeout

        self.logger.info(f"Executing CommandID=0x{self.command_id:02X}")
        reply_message = self._send_request_and_get_reply(request_message=request_message,
                                                         timeout=timeout)
        self.logger.debug(f"Finished executing CommandID=0x{self.command_id:02X}")

        try:
            return_values = HdcDataType.parse_reply_msg(reply_message=reply_message,
                                                        expected_data_types=return_types)
        except ValueError as e:
            raise HdcError(f"Failed to parse reply to CommandID={self.command_id:02X}, because: {e}")

        if isinstance(return_values, list):
            # Be more pythonic by returning a tuple, instead of a list
            return_values = tuple(return_values)

        return return_values


class VoidWithoutArgsCommandProxy(CommandProxyBase):
    """Convenience proxy-class for FeatureCommands that neither have arguments nor return values."""

    def __init__(self, feature_proxy: FeatureProxyBase, command_id: int, default_timeout: float | None = None):
        super().__init__(feature_proxy, command_id=command_id, default_timeout=default_timeout)

    def __call__(self, timeout: float | None = None):
        return super()._call_cmd(cmd_args=None, return_types=None, timeout=timeout)


class GetPropertyNameCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_PROP_NAME)
        self.register_error(ReplyErrorCode.UNKNOWN_PROPERTY)

    def __call__(self, property_id: int, timeout: float | None = None) -> str:
        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, property_id), ],
            return_types=HdcDataType.UTF8,
            timeout=timeout
        )


class GetPropertyTypeCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_PROP_TYPE)
        self.register_error(ReplyErrorCode.UNKNOWN_PROPERTY)

    def __call__(self, property_id: int, timeout: float | None = None) -> HdcDataType:
        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        property_type_id = super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, property_id), ],
            return_types=HdcDataType.UINT8,
            timeout=timeout
        )
        property_type = HdcDataType(property_type_id)
        return property_type


class GetPropertyReadonlyCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_PROP_RO)
        self.register_error(ReplyErrorCode.UNKNOWN_PROPERTY)

    def __call__(self, property_id: int, timeout: float | None = None) -> bool:
        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, property_id), ],
            return_types=HdcDataType.BOOL,
            timeout=timeout
        )


class GetPropertyValueCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_PROP_VALUE)
        self.register_error(ReplyErrorCode.UNKNOWN_PROPERTY)

    def __call__(self,
                 property_id: int,
                 property_data_type: HdcDataType,
                 timeout: float | None = None) -> typing.Any:
        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, property_id), ],
            return_types=property_data_type,
            timeout=timeout
        )


class SetPropertyValueCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.SET_PROP_VALUE)
        self.register_error(ReplyErrorCode.UNKNOWN_PROPERTY)
        self.register_error(ReplyErrorCode.INVALID_PROPERTY_VALUE)
        self.register_error(ReplyErrorCode.PROPERTY_IS_READ_ONLY)

    def __call__(self,
                 property_id: int,
                 property_data_type: HdcDataType,
                 new_value: bool | int | float | str | bytes,
                 timeout: float | None = None) -> bool | int | float | str | bytes:
        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        return super()._call_cmd(
            cmd_args=[
                (HdcDataType.UINT8, property_id),
                (property_data_type, new_value),
            ],
            return_types=property_data_type,
            timeout=timeout
        )


class GetPropertyDescriptionCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_PROP_DESCR)
        self.register_error(ReplyErrorCode.UNKNOWN_PROPERTY)

    def __call__(self, property_id: int, timeout: float | None = None) -> str:
        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, property_id), ],
            return_types=HdcDataType.UTF8,
            timeout=timeout
        )


class GetCommandNameCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_CMD_NAME)
        # Reuses ReplyErrorCode.UNKNOWN_COMMAND to also mean we requested the name for an unknown CommandID

    def __call__(self, command_id: int, timeout: float | None = None) -> str:
        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, command_id), ],
            return_types=HdcDataType.UTF8,
            timeout=timeout
        )


class GetCommandDescriptionCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_CMD_DESCR)
        # Reuses ReplyErrorCode.UNKNOWN_COMMAND to also mean we requested the description for an unknown CommandID

    def __call__(self, command_id: int, timeout: float | None = None) -> str:
        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, command_id), ],
            return_types=HdcDataType.UTF8,
            timeout=timeout
        )


class GetEventNameCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_EVT_NAME)
        self.register_error(ReplyErrorCode.UNKNOWN_EVENT)

    def __call__(self, event_id: int, timeout: float | None = None) -> str:
        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, event_id), ],
            return_types=HdcDataType.UTF8,
            timeout=timeout
        )


class GetEventDescriptionCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=CmdID.GET_EVT_DESCR)
        self.register_error(ReplyErrorCode.UNKNOWN_EVENT)

    def __call__(self, event_id: int, timeout: float | None = None) -> str:
        return super()._call_cmd(
            cmd_args=[(HdcDataType.UINT8, event_id), ],
            return_types=HdcDataType.UTF8,
            timeout=timeout
        )


class EventProxyBase:
    feature_proxy: FeatureProxyBase
    event_id: int
    most_recently_received_event_payloads: collections.deque
    payload_parser: typing.Callable[[bytes], typing.Any]

    def __init__(self,
                 feature_proxy: FeatureProxyBase,
                 event_id: int,
                 payload_parser: typing.Type[object] | None = None,
                 deque_capacity: int = 100):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy.MyEventProxy"
        self.logger = feature_proxy.logger.getChild(self.__class__.__name__)

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for EventID=0x{event_id:02X} on FeatureID=0x{feature_proxy.feature_id:02X}")

        if not is_valid_uint8(event_id):
            raise ValueError(f"event_id value of 0x{event_id:02X} is beyond valid range from 0x00 to 0xFF")

        self.event_id = event_id
        self.feature_proxy = feature_proxy

        if payload_parser is None:
            payload_parser = self.RawEventPayload  # Default payload parser for very lazy people

        self.payload_parser = payload_parser

        self.most_recently_received_event_payloads = collections.deque(maxlen=deque_capacity)

        self.event_payload_handlers = list()

        self.feature_proxy.router_feature.register_event_handler(self.event_id, self._event_message_handler)

    def _event_message_handler(self, event_message: bytes) -> None:
        """
        The one and only event handler actually registered with the RouterFeature.
        WARNING: This handler will be executed in the receiver-thread!
        """
        event_payload = self.payload_parser(event_message)
        self.most_recently_received_event_payloads.append(event_payload)
        for handler in self.event_payload_handlers:
            handler(event_payload)

    def register_event_payload_handler(self, event_payload_handler: typing.Callable[[typing.Any], None]):
        """
        Users of this proxy can register their own event-handlers.
        Event handlers should be a callable that takes the parsed event-payload object as an argument.
        Multiple handlers can be registered. They will be executed in the same order as registered.

        WARNING: Event handlers will be executed in the receiver-thread. Ensure they are fast and thread-safe!
        """
        self.event_payload_handlers.append(event_payload_handler)

    class RawEventPayload:
        """
        Default event payload parser that simply strips the message header away, keeping the raw bytes of the payload.
        It also keeps a reception timestamp.
        """

        def __init__(self, event_message: bytes):
            self.received_at = datetime.utcnow()
            self.raw_payload = event_message[3:]  # Strip 3 leading bytes: MsgID + FeatureID + EvtID


class LogEventProxy(EventProxyBase):
    logger: logging.Logger

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy,
                         event_id=EvtID.LOG,
                         payload_parser=LogEventProxy.LogEventPayload)
        # This is how HDC-logging is mapped directly into python logging:
        self.register_event_payload_handler(lambda e: self.logger.log(level=e.log_level, msg=e.log_message))

    class LogEventPayload:
        def __init__(self, event_message: bytes):
            self.received_at = datetime.utcnow()
            self.log_level = event_message[3]
            self.log_message = event_message[4:].decode(encoding="utf-8", errors="strict")


class StateTransitionEventProxy(EventProxyBase):
    logger: logging.Logger

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy,
                         event_id=EvtID.STATE_TRANSITION,
                         payload_parser=StateTransitionEventProxy.StateTransitionEventPayload)
        self.register_event_payload_handler(self.event_payload_handler)

    class StateTransitionEventPayload:
        def __init__(self, event_message: bytes):
            self.received_at = datetime.utcnow()
            self.previous_state_id = event_message[3]
            self.current_state_id = event_message[4]

    def event_payload_handler(self, event_payload: StateTransitionEventProxy.StateTransitionEventPayload):
        self.logger.info(f"%s → %s",
                         self.feature_proxy.resolve_state_name(event_payload.previous_state_id),
                         self.feature_proxy.resolve_state_name(event_payload.current_state_id))
        # Inject new state into the cache for the FeatureState property
        self.feature_proxy.prop_feature_state._update_cached_value(event_payload.current_state_id)


class PropertyProxyBase:
    feature_proxy: FeatureProxyBase
    property_id: int
    property_data_type: HdcDataType
    is_readonly: bool
    default_freshness: float
    default_timeout: float
    _cached_value: bool | int | float | str | bytes | None
    _timestamp_of_cached_value: float

    def __init__(self,
                 feature_proxy: FeatureProxyBase,
                 property_id: int,
                 property_data_type: HdcDataType,
                 is_readonly: bool,
                 default_freshness: float,
                 default_timeout: float):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy.MyPropertyProxy"
        self.logger = feature_proxy.logger.getChild(self.__class__.__name__)

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for PropertyID=0x{property_id:02X} on FeatureID=0x{feature_proxy.feature_id:02X}")

        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        self.feature_proxy = feature_proxy
        self.property_id = property_id
        self.property_data_type = property_data_type
        self.is_readonly = is_readonly

        # Keep defaults per instance, since each property may need to tweak its own sensible defaults
        self.default_freshness = default_freshness
        self.default_timeout = default_timeout

        self._cached_value = None
        self._timestamp_of_cached_value = 0.0

    def _update_cached_value(self, new_value: bool | int | float | str | bytes):
        self._cached_value = new_value
        self._timestamp_of_cached_value = time.perf_counter()

    def _get(self,
             freshness: float | None = None,
             timeout: float | None = None
             ) -> bool | int | float | str | bytes:

        if freshness is None:
            freshness = self.default_freshness

        if timeout is None:
            timeout = self.default_timeout

        age_of_cached_value = time.perf_counter() - self._timestamp_of_cached_value
        if age_of_cached_value > freshness or self._cached_value is None:
            self.logger.debug(f"Getting value of PropertyID=0x{self.property_id:02X}")
            property_value = self.feature_proxy._cmd_get_property_value(property_id=self.property_id,
                                                                        property_data_type=self.property_data_type,
                                                                        timeout=timeout)
            self.logger.info(f"PropertyID=0x{self.property_id:02X} getter returns {property_value}")
            self._update_cached_value(property_value)
        else:
            self.logger.info(f"PropertyID=0x{self.property_id:02X} getter "
                             f"returns {self._cached_value} from cache "
                             f"which was updated {age_of_cached_value:.3f}s ago "
                             f"and thus is fresher than {freshness:.3f}s")

        return self._cached_value

    def _set(self,
             new_value: bool | int | float | str | bytes,
             timeout: float | None = None
             ) -> bool | int | float | str | bytes:

        self.logger.info(f"Setting PropertyID=0x{self.property_id:02X} to a value of {new_value}")

        if self.is_readonly:
            raise RuntimeError()

        if timeout is None:
            timeout = self.default_timeout

        # Note how the value returned with the reply is the actual value set on
        # the device, and it may differ from the value sent in the request!
        property_value = self.feature_proxy._cmd_set_property_value(
            property_id=self.property_id,
            property_data_type=self.property_data_type,
            new_value=new_value,
            timeout=timeout)

        self._update_cached_value(property_value)

        if property_value != new_value:
            self.logger.warning(f"Attempted to set PropertyID=0x{self.property_id:02X} "
                                f"to a value of {new_value}, but "
                                f"effectively a value of {property_value} was set.")

        self.logger.debug(f"Completed setting value of PropertyID=0x{self.property_id:02X}")

        return self._cached_value


# noinspection PyPep8Naming
class PropertyProxy_RO_BOOL(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.BOOL, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> bool:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_BOOL(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.BOOL, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> bool:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: bool, timeout: float | None = None) -> bool:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_UINT8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UINT8, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UINT8, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: int, timeout: float | None = None) -> int:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_UINT16(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UINT16, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT16(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UINT16, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: int, timeout: float | None = None) -> int:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_UINT32(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UINT32, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT32(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UINT32, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: int, timeout: float | None = None) -> int:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_INT8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.INT8, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.INT8, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: int, timeout: float | None = None) -> int:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_INT16(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.INT16, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT16(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.INT16, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: int, timeout: float | None = None) -> int:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_INT32(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.INT32, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT32(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.INT32, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: int, timeout: float | None = None) -> int:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_FLOAT(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.FLOAT, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> float:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_FLOAT(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.FLOAT, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> float:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: float, timeout: float | None = None) -> float:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_DOUBLE(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.DOUBLE, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> float:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_DOUBLE(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.DOUBLE, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> float:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: float, timeout: float | None = None) -> float:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_UTF8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UTF8, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> str:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UTF8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.UTF8, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> str:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: str, timeout: float | None = None) -> str:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RO_BLOB(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.BLOB, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> bytes:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_BLOB(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.BLOB, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> bytes:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: bytes, timeout: float | None = None) -> bytes:
        return self._set(new_value=new_value, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_FeatureState(PropertyProxy_RO_UINT8):
    """
    Special handling for the FeatureState property, for which we know that we can rely on
    the cached value to be kept up to date by the FeatureStateTransitionEvent.
    This proxy will by default return the cached value and thus avoid unnecessary requests.
    Callers may explicitly force a request by calling .get(freshness=0.0)
    """

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy,
                         property_id=PropID.FEAT_STATE,
                         # Infinity, meaning that the cached value will not expire (by default)
                         default_freshness=float('inf'))

    def get_value_name(self, freshness: float | None = None, timeout: float | None = None) -> str:
        """Human-readable name of the numeric FeatureState."""
        return self.feature_proxy.resolve_state_name(self.get(freshness=freshness, timeout=timeout))


# noinspection PyPep8Naming
class PropertyProxy_LogEventThreshold(PropertyProxy_RW_UINT8):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, property_id=PropID.LOG_EVT_THRESHOLD)

    def get_value_name(self, freshness: float | None = None, timeout: float | None = None) -> str:
        """Human-readable name of the numeric LogLevel-Threshold."""
        uint8_level = self.get(freshness=freshness, timeout=timeout)
        return logging.getLevelName(uint8_level)


class FeatureProxyBase:
    router_feature: hdcproto.host.router.RouterFeature

    def __init__(self, device_proxy: DeviceProxyBase, feature_id: int):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy"
        self.logger = device_proxy.logger.getChild(self.__class__.__name__)

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for FeatureID=0x{feature_id:02X}")

        if not is_valid_uint8(feature_id):
            raise ValueError(f"feature_id value of 0x{feature_id:02X} is beyond valid range from 0x00 to 0xFF")

        self.router_feature = hdcproto.host.router.RouterFeature(router=device_proxy.router,
                                                                 feature_id=feature_id)
        # Commands
        self._cmd_get_property_name = GetPropertyNameCommandProxy(self)
        self._cmd_get_property_type = GetPropertyTypeCommandProxy(self)
        self._cmd_get_property_readonly = GetPropertyReadonlyCommandProxy(self)
        self._cmd_get_property_value = GetPropertyValueCommandProxy(self)
        self._cmd_set_property_value = SetPropertyValueCommandProxy(self)
        self._cmd_get_property_description = GetPropertyDescriptionCommandProxy(self)
        self._cmd_get_command_name = GetCommandNameCommandProxy(self)
        self._cmd_get_command_description = GetCommandDescriptionCommandProxy(self)
        self._cmd_get_event_name = GetEventNameCommandProxy(self)
        self._cmd_get_event_description = GetEventDescriptionCommandProxy(self)

        # Events
        self._evt_log = LogEventProxy(self)
        self._evt_state_transition = StateTransitionEventProxy(self)

        # Properties (immutable)
        inf = float('inf')  # Infinity, meaning that the cached value will not expire (by default)
        self.prop_feature_name = PropertyProxy_RO_UTF8(self, property_id=PropID.FEAT_NAME,
                                                       default_freshness=inf)
        self.prop_feature_type_name = PropertyProxy_RO_UTF8(self, property_id=PropID.FEAT_TYPE_NAME,
                                                            default_freshness=inf)
        self.prop_feature_type_revision = PropertyProxy_RO_UINT8(self, property_id=PropID.FEAT_TYPE_REV,
                                                                 default_freshness=inf)
        self.prop_feature_description = PropertyProxy_RO_UTF8(self, property_id=PropID.FEAT_DESCR,
                                                              default_freshness=inf)
        self.prop_feature_tags = PropertyProxy_RO_UTF8(self, property_id=PropID.FEAT_TAGS,
                                                       default_freshness=inf)
        self.prop_available_commands = PropertyProxy_RO_BLOB(self, property_id=PropID.AVAIL_CMD,
                                                             default_freshness=inf)
        self.prop_available_events = PropertyProxy_RO_BLOB(self, property_id=PropID.AVAIL_EVT,
                                                           default_freshness=inf)
        self.prop_available_properties = PropertyProxy_RO_BLOB(self, property_id=PropID.AVAIL_PROP,
                                                               default_freshness=inf)
        # Properties (mutable)
        self.prop_feature_state = PropertyProxy_FeatureState(self)
        self.prop_log_event_threshold = PropertyProxy_LogEventThreshold(self)

    @property
    def feature_id(self) -> int:
        return self.router_feature.feature_id

    def resolve_state_name(self, state_id: int) -> str:
        try:
            # The following expects a nested IntEnum as defined within the most derived subclass of FeatureProxyBase!
            # noinspection PyUnresolvedReferences
            return type(self).FeatureStateEnum(state_id).name
        except Exception:
            if type(self) is not FeatureProxyBase:  # Suppress warning in ad-hoc usages of FeatureProxyBase
                # Forgot to define all states in "FeatureStateEnum" nested within the sub-classed feature-proxy?
                self.logger.warning(f"Can't resolve name of FeatureStateID 0x{state_id:02X}")
            return f"0x{state_id:02X}"  # Use hexadecimal representation as a fallback

    def await_state(self,
                    exits: int | typing.Iterable[int] | None = None,
                    enters: int | typing.Iterable[int] | None = None,
                    timeout: float = 5.0,
                    polling_period: float = 0.1):
        """
        Utility method to block execution until the expected FeatureState(s) is/are exited and/or entered.

        Waits until the FeatureState does not match any of the states listed in :param exits:
        Then waits until the FeatureState matches any of the states listed in :param enters:
        Will raise a TimeoutError if the whole process takes longer than :param timeout: seconds.
        """
        if exits is None and enters is None:
            raise ValueError()

        if isinstance(exits, int):
            exits = [exits, ]

        if isinstance(enters, int):
            enters = [enters, ]

        deadline = time.perf_counter() + timeout

        if exits is not None:
            if any(not is_valid_uint8(v) for v in exits):
                raise ValueError("State ID values must be in range 0x00 to 0xFF")

            while self.prop_feature_state.get() in exits:
                if time.perf_counter() > deadline:
                    raise TimeoutError("Timeout before exiting state")
                time.sleep(polling_period)

        if enters is not None:
            if any(not is_valid_uint8(v) for v in enters):
                raise ValueError("State ID values must be in range 0x00 to 0xFF")

            while self.prop_feature_state.get() not in enters:
                if time.perf_counter() > deadline:
                    raise TimeoutError("Timeout before entering state")
                time.sleep(polling_period)


class CoreFeatureProxyBase(FeatureProxyBase):
    def __init__(self, device_proxy: DeviceProxyBase):
        super().__init__(device_proxy=device_proxy, feature_id=FeatureID.CORE)

        # Mandatory properties of a Core feature as required by HDC-spec
        self.prop_available_features = PropertyProxy_RO_BLOB(self, PropID.AVAIL_FEAT)
        self.prop_max_req_msg_size = PropertyProxy_RO_UINT16(self, PropID.MAX_REQ_MSG_SIZE)

        # HDC-spec does not require any mandatory commands nor events for the Core feature, other than what's
        # already mandatory for any feature, which has been inherited from the FeatureProxyBase base class.


class DeviceProxyBase:
    router: hdcproto.host.router.MessageRouter
    core: CoreFeatureProxyBase

    def __init__(self, connection_url: str):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy"
        self.logger = logger.getChild(self.__class__.__name__)

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for device connected at '{connection_url}'")

        serial_transport = hdcproto.transport.serialport.SerialTransport(serial_url=connection_url)
        self.router = hdcproto.host.router.MessageRouter(transport=serial_transport)

        # The following may be needed for introspection when using bare DeviceProxyBase objects.
        # Subclasses will typically override it with a more specific core-feature proxy.
        self.core = CoreFeatureProxyBase(self)


class HdcReplyError(HdcError):
    reply_message: bytes

    def __init__(self, error_name: str, reply_message: bytes):
        self.reply_message = reply_message
        super().__init__(error_name)

    @property
    def error_code(self) -> int:
        return self.reply_message[3]

    @property
    def error_description(self) -> str:
        return self.reply_message[4:].decode(encoding="utf-8", errors="strict")
