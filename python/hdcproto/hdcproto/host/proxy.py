"""
Proxy classes for the device and its features and properties
"""
from __future__ import annotations

import collections
import enum
import logging
import time
import typing
from datetime import datetime

import semver

import hdcproto.host.router
from hdcproto.common import (MessageTypeID, FeatureID, CmdID, ExcID, EvtID, PropID, HdcDataType,
                             is_valid_uint8, MetaID, HdcError, HdcCmdException, HdcCmdExc_CommandFailed,
                             HdcCmdExc_UnknownProperty, HdcCmdExc_ReadOnlyProperty, HdcCmdExc_UnknownFeature,
                             HdcCmdExc_UnknownCommand, HdcCmdExc_InvalidArgs, HdcCmdExc_NotNow)

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.host.proxy"

DEFAULT_REPLY_TIMEOUT = 0.2


class CommandProxyBase:
    feature_proxy: FeatureProxyBase
    command_id: int
    default_timeout: float
    command_raises: dict[int, HdcCmdException]
    msg_prefix: bytes

    def __init__(self,
                 feature_proxy: FeatureProxyBase,
                 command_id: int,
                 raises_also: typing.Iterable[HdcCmdException | enum.IntEnum] | None = None,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy.MyCommandProxy"
        self.logger = feature_proxy.logger.getChild(self.__class__.__name__)

        if not is_valid_uint8(command_id):
            raise ValueError(f"command_id value of {command_id} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for CommandID=0x{command_id:02X} on FeatureID=0x{feature_proxy.feature_id:02X}")

        self.feature_proxy = feature_proxy
        self.command_id = command_id
        self.default_timeout = default_timeout

        raised_by_all_commands = [
            HdcCmdExc_CommandFailed(),
            HdcCmdExc_UnknownFeature(),
            HdcCmdExc_UnknownCommand(),
            HdcCmdExc_InvalidArgs(),
            HdcCmdExc_NotNow()
        ]
        if raises_also is None:
            raises_also = []
        elif isinstance(raises_also, HdcCmdException):
            raises_also = [raises_also]
        self.command_raises = dict()
        for exc in raised_by_all_commands + raises_also:
            if isinstance(exc, enum.IntEnum):
                exc = HdcCmdException(exc)
            self._register_exception(exc)

        self.msg_prefix = bytes([int(MessageTypeID.COMMAND),
                                 self.feature_proxy.feature_id,
                                 self.command_id])

    @property
    def router(self) -> hdcproto.host.router.MessageRouter:
        return self.feature_proxy.device_proxy.router

    def _register_exception(self, exception: HdcCmdException) -> None:
        if exception.exception_id in self.command_raises:
            raise ValueError(f'Already registered Exception.id=0x{exception.exception_id:02X} '
                             f'as "{self.command_raises[exception.exception_id]}"')
        self.command_raises[exception.exception_id] = exception

    def _send_request_and_get_reply(self, request_message: bytes, timeout: float) -> bytes:

        if not request_message.startswith(self.msg_prefix):
            raise ValueError("Request does not match the expected prefix")

        reply_message = self.router.send_request_and_get_reply(request_message, timeout)

        if not reply_message.startswith(self.msg_prefix):
            raise HdcError("Reply does not match the expected prefix")

        if len(reply_message) < 4:
            raise HdcError(f"Expected a reply size of 4 or more bytes, "
                           f"but received {len(reply_message)}")

        exception_id = reply_message[3]
        if exception_id == ExcID.NO_ERROR:
            return reply_message

        # ... else it's an HDC-exception.
        # Translate HDC-message into the exception class that has been registered for that Exception.id
        try:
            exc_descriptor = self.command_raises[exception_id]
        except KeyError:
            self.logger.warning(f"Received an unexpected Exception.id=0x{exception_id:02X}. Raising it anyway")
            exc_descriptor = HdcCmdException(exception_id=exception_id,
                                             exception_name=f"Exception_0x{exception_id:02X}")

        # Use the "descriptor" just as a template to create the actual exception instance being raised.
        exception = exc_descriptor.clone_with_hdc_message(reply_message)

        # Hello debuggers: This exception was actually raised by the HDC-device! Don't blame the proxy!
        raise exception

    def _call_cmd(self,
                  cmd_args: list[tuple[HdcDataType, bool | int | float | str | bytes | HdcDataType]] | None,
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
            return_values = HdcDataType.parse_command_reply_msg(reply_message=reply_message,
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
        return super()._call_cmd(cmd_args=[], return_types=[], timeout=timeout)


class GetPropertyValueCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy,
                         command_id=CmdID.GET_PROP_VALUE,
                         raises_also=[HdcCmdExc_UnknownProperty()])

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
        super().__init__(feature_proxy,
                         command_id=CmdID.SET_PROP_VALUE,
                         raises_also=[HdcCmdExc_UnknownProperty(),
                                      HdcCmdExc_ReadOnlyProperty()])

    def __call__(self,
                 property_id: int,
                 property_data_type: HdcDataType,
                 new_value: bool | int | float | str | bytes | HdcDataType,
                 timeout: float | None = None) -> bool | int | float | str | bytes | HdcDataType:
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

        if not is_valid_uint8(event_id):
            raise ValueError(f"event_id value of 0x{event_id:02X} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for EventID=0x{event_id:02X} on FeatureID=0x{feature_proxy.feature_id:02X}")

        self.event_id = event_id
        self.feature_proxy = feature_proxy

        if payload_parser is None:
            payload_parser = self.RawEventPayload  # Default payload parser for very lazy people

        self.payload_parser = payload_parser

        self.most_recently_received_event_payloads = collections.deque(maxlen=deque_capacity)

        self.event_payload_handlers = list()

        self.router.register_event_message_handler(
            self.feature_proxy.feature_id,
            self.event_id,
            self._event_message_handler)

    @property
    def router(self) -> hdcproto.host.router.MessageRouter:
        return self.feature_proxy.device_proxy.router

    def _event_message_handler(self, event_message: bytes) -> None:
        """
        The one and only event handler actually registered at the MessageRouter.

        Warning: This will be executed from within the SerialTransport.receiver_thread
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

        Warning: Event handlers will be executed from within the SerialTransport.receiver_thread.
                 Ensure they are fast and thread-safe!
        """
        self.event_payload_handlers.append(event_payload_handler)

    class RawEventPayload:
        """
        Default event payload parser that simply strips the message header away, keeping the raw bytes of the payload.
        It also keeps a reception timestamp.
        """

        def __init__(self, event_message: bytes):
            """Warning: This will be executed from within the SerialTransport.receiver_thread"""
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
            """Warning: This will be executed from within the SerialTransport.receiver_thread"""
            self.received_at = datetime.utcnow()
            self.log_level = event_message[3]
            self.log_message = event_message[4:].decode(encoding="utf-8", errors="strict")

    def set_log_threshold(self, log_level: int) -> None:
        """
        This will set the same log-level on both: the HDC-LogEvent and the Python logger in this proxy.
        """
        if log_level not in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]:
            raise ValueError(f"A log_level of {log_level} is invalid")

        self.logger.setLevel(log_level)
        self.feature_proxy.prop_log_event_threshold.set(log_level)

    def get_log_threshold(self) -> int:
        # Note how the LogEventProxy is configured to an infinite default_freshness, thus
        # its value will always be taken from the cache.
        return self.feature_proxy.prop_log_event_threshold.get()


class StateTransitionEventProxy(EventProxyBase):
    logger: logging.Logger

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy,
                         event_id=EvtID.FEATURE_STATE_TRANSITION,
                         payload_parser=StateTransitionEventProxy.StateTransitionEventPayload)
        self.register_event_payload_handler(self.event_payload_handler)

    class StateTransitionEventPayload:
        def __init__(self, event_message: bytes):
            """Warning: This will be executed from within the SerialTransport.receiver_thread"""
            self.received_at = datetime.utcnow()
            self.previous_state_id = event_message[3]
            self.current_state_id = event_message[4]

    def event_payload_handler(self, event_payload: StateTransitionEventProxy.StateTransitionEventPayload):
        self.logger.info(f"%s → %s",
                         self.feature_proxy.resolve_state_name(event_payload.previous_state_id),
                         self.feature_proxy.resolve_state_name(event_payload.current_state_id))
        # Inject new state into the cache for the FeatureState property
        self.feature_proxy.prop_feature_state.update_cached_value(event_payload.current_state_id)


class PropertyProxyBase:
    feature_proxy: FeatureProxyBase
    property_id: int
    property_data_type: HdcDataType
    is_readonly: bool
    default_freshness: float
    default_timeout: float
    _cached_value: bool | int | float | str | bytes | HdcDataType | None
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

        if not is_valid_uint8(property_id):
            raise ValueError(f"property_id value of {property_id} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for PropertyID=0x{property_id:02X} on FeatureID=0x{feature_proxy.feature_id:02X}")

        self.feature_proxy = feature_proxy
        self.property_id = property_id
        self.property_data_type = property_data_type
        self.is_readonly = is_readonly

        # Keep defaults per instance, since each property may need to tweak its own sensible defaults
        self.default_freshness = default_freshness
        self.default_timeout = default_timeout

        self._cached_value = None
        self._timestamp_of_cached_value = 0.0

    def update_cached_value(self, new_value: bool | int | float | str | bytes | HdcDataType):
        self._cached_value = new_value
        self._timestamp_of_cached_value = time.perf_counter()

    def _get(self,
             freshness: float | None = None,
             timeout: float | None = None
             ) -> bool | int | float | str | bytes | HdcDataType:

        if freshness is None:
            freshness = self.default_freshness

        if timeout is None:
            timeout = self.default_timeout

        age_of_cached_value = time.perf_counter() - self._timestamp_of_cached_value
        if age_of_cached_value > freshness or self._cached_value is None:
            self.logger.debug(f"Getting value of PropertyID=0x{self.property_id:02X}")
            property_value = self.feature_proxy.cmd_get_property_value(property_id=self.property_id,
                                                                       property_data_type=self.property_data_type,
                                                                       timeout=timeout)
            self.logger.info(f"PropertyID=0x{self.property_id:02X} getter returns {property_value}")
            self.update_cached_value(property_value)
        else:
            self.logger.info(f"PropertyID=0x{self.property_id:02X} getter "
                             f"returns {self._cached_value} from cache "
                             f"which was updated {age_of_cached_value:.3f}s ago "
                             f"and thus is fresher than {freshness:.3f}s")

        return self._cached_value

    def _set(self,
             new_value: bool | int | float | str | bytes | HdcDataType,
             timeout: float | None = None
             ) -> bool | int | float | str | bytes | HdcDataType:

        self.logger.info(f"Setting PropertyID=0x{self.property_id:02X} to a value of {new_value}")

        if self.is_readonly:
            raise RuntimeError()

        if timeout is None:
            timeout = self.default_timeout

        # Note how the value returned with the reply is the actual value set on
        # the device, and it may differ from the value sent in the request!
        property_value = self.feature_proxy.cmd_set_property_value(
            property_id=self.property_id,
            property_data_type=self.property_data_type,
            new_value=new_value,
            timeout=timeout)

        self.update_cached_value(property_value)

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
class PropertyProxy_RO_DTYPE(PropertyProxyBase):
    """Yes, this is confusing: It's a proxy for a property whose *value* is a HdcDataType"""

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.DTYPE, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> HdcDataType:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_DTYPE(PropertyProxyBase):
    """Yes, this is confusing: It's a proxy for a property whose *value* is a HdcDataType"""

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, HdcDataType.DTYPE, is_readonly=False,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> HdcDataType:
        return self._get(freshness=freshness, timeout=timeout)

    def set(self, new_value: HdcDataType, timeout: float | None = None) -> HdcDataType:
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


class StateProxy:
    state_id: int
    state_name: str
    state_doc: str

    def __init__(self,
                 state_id: int,
                 state_name: str,
                 state_doc: str | None = None):

        if not is_valid_uint8(state_id):
            raise ValueError(f"state_id value of {state_id} is beyond valid range from 0x00 to 0xFF")

        self.state_id = state_id

        if not state_name:
            raise ValueError("State name must be a non-empty string")
        self.state_name = state_name

        self.state_doc = state_doc


class FeatureProxyBase:
    feature_id: int
    device_proxy: DeviceProxyBase
    state_proxies: dict[int, StateProxy] | None

    def __init__(self,
                 device_proxy: DeviceProxyBase,
                 feature_id: int,
                 feature_states: typing.Type[enum.IntEnum] | list[StateProxy] | None = None):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy"
        self.logger = device_proxy.logger.getChild(self.__class__.__name__)

        if not is_valid_uint8(feature_id):
            raise ValueError(f"feature_id value of 0x{feature_id:02X} is beyond valid range from 0x00 to 0xFF")

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for FeatureID=0x{feature_id:02X}")

        self.feature_id = feature_id
        self.device_proxy = device_proxy
        self.event_handlers = dict()

        if feature_states is None:
            # Meaning "None documented". Do not confuse with "Has no states", which would be an empty list.
            self.state_proxies = None
        else:
            self.state_proxies: dict[int, StateProxy] = dict()
            for d in feature_states:
                if isinstance(d, enum.IntEnum):
                    d = StateProxy(state_id=d, state_name=d.name)
                if d.state_id in self.state_proxies:
                    ValueError("feature_states contains duplicate ID values")
                self.state_proxies[d.state_id] = d

        # Commands
        self.cmd_get_property_value = GetPropertyValueCommandProxy(self)
        self.cmd_set_property_value = SetPropertyValueCommandProxy(self)

        # Events
        self.evt_state_transition = StateTransitionEventProxy(self)
        self.evt_log = LogEventProxy(self)

        # Properties
        self.prop_feature_state = PropertyProxy_FeatureState(self)
        self.prop_log_event_threshold = PropertyProxy_LogEventThreshold(self)

    @property
    def router(self) -> hdcproto.host.router.MessageRouter:
        return self.device_proxy.router

    def resolve_state_name(self, state_id: int) -> str:
        if self.state_proxies is None:
            self.logger.warning(f"Can't resolve name of FeatureStateID 0x{state_id:02X}, because "
                                f"no states were registered with this proxy.")
            return f"0x{state_id:02X}"  # Use hexadecimal representation as a fallback

        if state_id not in self.state_proxies:
            self.logger.error(f"Can't resolve name of unexpected FeatureStateID 0x{state_id:02X}")
            return f"0x{state_id:02X}"  # Use hexadecimal representation as a fallback

        return self.state_proxies[state_id].state_name

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
    def __init__(self,
                 device_proxy: DeviceProxyBase,
                 states: typing.Type[enum.IntEnum] | list[StateProxy] | None = None):
        super().__init__(device_proxy=device_proxy,
                         feature_id=FeatureID.CORE,
                         feature_states=states)

        # HDC-spec does not require any mandatory properties, commands nor events for the Core feature, other than
        # what's already mandatory for any feature, which has been inherited from the FeatureProxyBase base class.


class DeviceProxyBase:
    router: hdcproto.host.router.MessageRouter
    core: CoreFeatureProxyBase

    def __init__(self,
                 connection_url: str | None):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy"
        self.logger = logger.getChild(self.__class__.__name__)

        self.router = hdcproto.host.router.MessageRouter(connection_url=connection_url)

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

    def __enter__(self) -> DeviceProxyBase:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_hdc_version_string(self, timeout: float = 0.2) -> str:
        """Returns the raw string, without attempting to validate nor parsing it."""
        request_message = bytes([MessageTypeID.META, MetaID.HDC_VERSION])
        reply_message = self.router.send_request_and_get_reply(request_message, timeout)
        if reply_message[:2] != request_message:
            raise HdcError("Reply does not match the expected prefix")
        reply_payload = reply_message[2:]  # Skip MessageTypeID + MetaID
        reply_string = reply_payload.decode(encoding="utf-8", errors="strict")
        return reply_string

    def get_hdc_version(self, timeout: float = 0.2) -> semver.VersionInfo:
        """Validates device's reply, parses version and returns it as a semver.VersionInfo object."""
        reply_string = self.get_hdc_version_string(timeout=timeout)
        expected_prefix = "HDC "
        if not reply_string.startswith(expected_prefix):
            raise HdcError(f"Don't know how to handle HDC-spec '{reply_string}'")

        version_string = reply_string[len(expected_prefix):]
        return semver.VersionInfo.parse(version_string)  # Raises ValueError

    def get_max_req_msg_size(self, timeout: float = 0.2) -> int:
        """Returns the maximum size of a request that the device can cope with."""
        request_message = bytes([MessageTypeID.META, MetaID.MAX_REQ])
        reply_message = self.router.send_request_and_get_reply(request_message, timeout)
        if reply_message[:2] != request_message:
            raise HdcError("Reply does not match the expected prefix")

        reply_payload = reply_message[2:]  # Skip MessageTypeID + MetaID
        if not reply_payload:
            raise HdcError("Device did not know how to reply")

        return HdcDataType.UINT32.bytes_to_value(reply_payload)

    def get_idl_json(self, timeout: float = 2.0):  # Increased timeout, because IDL-JSON can take a while to transmit
        """Returns a JSON string representation of the device's HDC API."""
        request_message = bytes([MessageTypeID.META, MetaID.IDL_JSON])
        reply_message = self.router.send_request_and_get_reply(request_message, timeout)
        if reply_message[:2] != request_message:
            raise HdcError("Reply does not match the expected prefix")
        reply_payload = reply_message[2:]  # Skip MessageTypeID + MetaID
        reply_string = reply_payload.decode(encoding="utf-8", errors="strict")
        return reply_string

    def get_echo(self, echo_payload: bytes, timeout: float = 0.2) -> bytes:
        request_message = bytearray()
        request_message.append(MessageTypeID.ECHO)
        request_message.extend(echo_payload)
        reply_message = self.router.send_request_and_get_reply(request_message, timeout)
        message_type_id_of_reply = reply_message[0]
        if message_type_id_of_reply != MessageTypeID.ECHO:
            raise HdcError("Reply does not match the expected prefix")
        reply_payload = reply_message[1:]  # Skip MessageTypeID prefix
        return reply_payload
