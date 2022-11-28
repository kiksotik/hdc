"""
Proxy classes for the device and its features and properties
"""
from __future__ import annotations

import collections
import logging
import sys
import time
import typing
from datetime import datetime

import semver

import hdcproto.host.router
from hdcproto.descriptor import (DeviceDescriptor, FeatureDescriptor, CommandDescriptor, EventDescriptor,
                                 PropertyDescriptor, FeatureStatePropertyDescriptor,
                                 LogEventThresholdPropertyDescriptor, GetPropertyValueCommandDescriptor,
                                 SetPropertyValueCommandDescriptor, LogEventDescriptor,
                                 FeatureStateTransitionEventDescriptor)
from hdcproto.exception import (HdcError, HdcCmdException, HdcCmdExc_CommandFailed, HdcCmdExc_UnknownFeature,
                                HdcCmdExc_UnknownCommand, HdcCmdExc_InvalidArgs, HdcCmdExc_NotNow,
                                HdcCmdExc_UnknownProperty, HdcCmdExc_ReadOnlyProperty)
from hdcproto.parse import value_to_bytes, bytes_to_value, parse_command_reply_payload, parse_event_payload
from hdcproto.spec import (MessageTypeID, CmdID, ExcID, EvtID, PropID, MetaID, DTypeID)
from hdcproto.validate import is_valid_uint8

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.host.proxy"

DEFAULT_REPLY_TIMEOUT = 0.2


class CommandProxyBase:
    command_descriptor: CommandDescriptor
    feature_proxy: FeatureProxyBase
    default_timeout: float
    msg_prefix: bytes

    def __init__(self,
                 command_descriptor: CommandDescriptor,
                 feature_proxy: FeatureProxyBase,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy.MyCommandProxy"
        self.logger = feature_proxy.logger.getChild(self.__class__.__name__)

        if not isinstance(command_descriptor, CommandDescriptor):
            raise TypeError
        self.command_descriptor = command_descriptor

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for {command_descriptor} on {feature_proxy.feature_descriptor}")

        self.feature_proxy = feature_proxy
        self.default_timeout = default_timeout

        self.msg_prefix = bytes([int(MessageTypeID.COMMAND),
                                 self.feature_proxy.feature_descriptor.id,
                                 self.command_descriptor.id])

    @property
    def router(self) -> hdcproto.host.router.MessageRouter:
        return self.feature_proxy.device_proxy.router

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
            exc_descriptor = self.command_descriptor.raises[exception_id]
        except KeyError:
            self.logger.warning(f"Received an unexpected Exception.id=0x{exception_id:02X}. Raising it anyway")
            exc_descriptor = HdcCmdException(id=exception_id,
                                             name=f"Exception_0x{exception_id:02X}")

        # Use the "descriptor" just as a template to create the actual exception instance being raised.
        exception = exc_descriptor.clone_with_hdc_message(reply_message)

        # Hello debuggers: This exception was actually raised by the HDC-device! Don't blame the proxy!
        raise exception

    def __call__(self, *args, **kwargs):
        request_message = bytearray(self.msg_prefix)

        expected_args = self.command_descriptor.args
        num_expected_args = len(expected_args)

        if len(args) > num_expected_args:
            raise ValueError(f"Unexpected positional arguments. "
                             f"Expected {num_expected_args}, but {len(args)} were given.")

        for i, d in enumerate(expected_args):
            if i < len(args):
                arg_value = args[i]
            else:
                if d.name not in kwargs.keys():
                    raise ValueError(f"Missing argument {d.name}")
                arg_value = kwargs.pop(d.name)
            arg_as_raw_bytes = value_to_bytes(d.dtype, arg_value)
            request_message.extend(arg_as_raw_bytes)

        if kwargs:
            raise ValueError(f"Unexpected keyword arguments: {repr(kwargs.keys())}")

        self.logger.info(f"Executing {self.command_descriptor}")
        reply_message = self._send_request_and_get_reply(request_message=request_message,
                                                         timeout=self.default_timeout)
        self.logger.debug(f"Finished executing {self.command_descriptor}")

        expected_return_dtypes = [ret.dtype for ret in self.command_descriptor.returns]

        if len(expected_return_dtypes) == 1:
            expected_return_dtypes = expected_return_dtypes[0]  # Tell parser to produce a scalar result!

        try:
            return_values = parse_command_reply_payload(reply_message=reply_message,
                                                        expected_data_types=expected_return_dtypes)
        except ValueError as e:
            raise HdcError(f"Failed to parse reply to {self.command_descriptor}, because: {e}")

        if isinstance(return_values, list):
            # Be more pythonic by returning a tuple, instead of a list
            return_values = tuple(return_values)

        return return_values


class EventProxyBase:
    feature_proxy: FeatureProxyBase
    most_recently_received_event_payloads: collections.deque
    payload_parser: typing.Callable[[bytes], typing.Any]

    def __init__(self,
                 event_descriptor: EventDescriptor,
                 feature_proxy: FeatureProxyBase,
                 payload_parser: typing.Type[object] | None = None,
                 deque_capacity: int = 100):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy.MyEventProxy"
        self.logger = feature_proxy.logger.getChild(self.__class__.__name__)

        if not isinstance(event_descriptor, EventDescriptor):
            raise TypeError
        self.event_descriptor = event_descriptor

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for {event_descriptor} on {feature_proxy.feature_descriptor}")

        self.feature_proxy = feature_proxy

        if payload_parser is None:
            payload_parser = self.default_event_payload_parser

        self.payload_parser = payload_parser

        self.most_recently_received_event_payloads = collections.deque(maxlen=deque_capacity)

        self.event_payload_handlers = list()

        self.router.register_event_message_handler(
            self.feature_proxy.feature_descriptor.id,
            self.event_descriptor.id,
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

    def default_event_payload_parser(self, event_message: bytes):
        """Warning: This will be executed from within the SerialTransport.receiver_thread"""
        if self.event_descriptor.args is None:  # ToDo: Attribute optionality. #25
            raw_payload = parse_event_payload(event_message=event_message,
                                              expected_data_types=DTypeID.BLOB)  # Raw payload as BLOB
            return raw_payload

        expected_data_types = [arg_descriptor.dtype for arg_descriptor in self.event_descriptor.args]
        if len(expected_data_types) == 1:
            expected_data_types = expected_data_types[0]  # Tell parser to produce a scalar result!

        return parse_event_payload(
            event_message=event_message,
            expected_data_types=expected_data_types
        )


class LogEventProxy(EventProxyBase):
    logger: logging.Logger

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(event_descriptor=LogEventDescriptor(),
                         feature_proxy=feature_proxy,
                         payload_parser=LogEventProxy.LogEventPayload)
        # This is how HDC-logging is mapped directly into python logging:
        self.register_event_payload_handler(lambda e: self.logger.log(level=e.log_level, msg=e.log_message))

    class LogEventPayload:
        def __init__(self, event_message: bytes):
            """Warning: This will be executed from within the SerialTransport.receiver_thread"""
            self.received_at = datetime.utcnow()
            (self.log_level,
             self.log_message) = parse_event_payload(event_message=event_message,
                                                     expected_data_types=[DTypeID.UINT8,
                                                                          DTypeID.UTF8])

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
        super().__init__(event_descriptor=FeatureStateTransitionEventDescriptor(),
                         feature_proxy=feature_proxy,
                         payload_parser=StateTransitionEventProxy.StateTransitionEventPayload)
        self.register_event_payload_handler(self.event_payload_handler)

    class StateTransitionEventPayload:
        def __init__(self, event_message: bytes):
            """Warning: This will be executed from within the SerialTransport.receiver_thread"""
            self.received_at = datetime.utcnow()
            (self.previous_state_id,
             self.current_state_id) = parse_event_payload(event_message=event_message,
                                                          expected_data_types=[DTypeID.UINT8,
                                                                               DTypeID.UINT8])

    def event_payload_handler(self, event_payload: StateTransitionEventProxy.StateTransitionEventPayload):
        self.logger.info(f"%s → %s",
                         self.feature_proxy.resolve_state_name(event_payload.previous_state_id),
                         self.feature_proxy.resolve_state_name(event_payload.current_state_id))
        # Inject new state into the cache for the FeatureState property
        self.feature_proxy.prop_feature_state.update_cached_value(event_payload.current_state_id)


class PropertyProxyBase:
    feature_proxy: FeatureProxyBase
    default_freshness: float
    default_timeout: float
    _cached_value: bool | int | float | str | bytes | DTypeID | None
    _timestamp_of_cached_value: float

    def __init__(self,
                 property_descriptor: PropertyDescriptor,
                 feature_proxy: FeatureProxyBase,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):

        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy.MyPropertyProxy"
        self.logger = feature_proxy.logger.getChild(self.__class__.__name__)

        if not isinstance(property_descriptor, PropertyDescriptor):
            raise TypeError

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for {property_descriptor} on {feature_proxy.feature_descriptor}")

        self.property_descriptor = property_descriptor
        self.feature_proxy = feature_proxy

        # Keep defaults per instance, since each property may need to tweak its own sensible defaults
        self.default_freshness = default_freshness
        self.default_timeout = default_timeout

        self._cached_value = None
        self._timestamp_of_cached_value = 0.0

    def update_cached_value(self, new_value: bool | int | float | str | bytes | DTypeID):
        self._cached_value = new_value
        self._timestamp_of_cached_value = time.perf_counter()

    def _get(self,
             freshness: float | None = None
             ) -> bool | int | float | str | bytes | DTypeID:

        if freshness is None:
            freshness = self.default_freshness

        age_of_cached_value = time.perf_counter() - self._timestamp_of_cached_value
        if age_of_cached_value > freshness or self._cached_value is None:
            self.logger.debug(f"Getting value of {self.property_descriptor}")
            property_value_as_blob = self.feature_proxy.cmd_get_property_value(property_id=self.property_descriptor.id)
            property_value = bytes_to_value(self.property_descriptor.dtype, property_value_as_blob)
            self.logger.info(f"Getter of {self.property_descriptor} returns {property_value}")
            self.update_cached_value(property_value)
        else:
            self.logger.info(f"Getter of {self.property_descriptor} getter "
                             f"returns {self._cached_value} from cache "
                             f"which was updated {age_of_cached_value:.3f}s ago "
                             f"and thus is fresher than {freshness:.3f}s")

        return self._cached_value

    def _set(self,
             new_value: bool | int | float | str | bytes | DTypeID
             ) -> bool | int | float | str | bytes | DTypeID:

        self.logger.info(f"Setting {self.property_descriptor} to a value of {new_value}")

        if self.property_descriptor.is_readonly:
            raise RuntimeError()

        new_value_as_blob = value_to_bytes(self.property_descriptor.dtype, new_value)

        # Note how the value returned with the reply is the actual value set on
        # the device, and it may differ from the value sent in the request!
        property_value_as_blob = self.feature_proxy.cmd_set_property_value(
            self.property_descriptor.id,
            new_value_as_blob)

        property_value = bytes_to_value(self.property_descriptor.dtype, property_value_as_blob)

        self.update_cached_value(property_value)

        if property_value != new_value:
            self.logger.warning(f"Attempted to set {self.property_descriptor} "
                                f"to a value of {new_value}, but "
                                f"effectively a value of {property_value} was set.")

        self.logger.debug(f"Completed setting value of {self.property_descriptor}")

        return self._cached_value


# noinspection PyPep8Naming
class PropertyProxy_RO_BOOL(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> bool:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_BOOL(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> bool:
        return self._get(freshness=freshness)

    def set(self, new_value: bool) -> bool:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_UINT8(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT8(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)

    def set(self, new_value: int) -> int:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_UINT16(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT16(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)

    def set(self, new_value: int) -> int:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_UINT32(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT32(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)

    def set(self, new_value: int) -> int:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_INT8(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT8(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)

    def set(self, new_value: int) -> int:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_INT16(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT16(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)

    def set(self, new_value: int) -> int:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_INT32(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT32(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> int:
        return self._get(freshness=freshness)

    def set(self, new_value: int) -> int:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_FLOAT(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> float:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_FLOAT(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> float:
        return self._get(freshness=freshness)

    def set(self, new_value: float) -> float:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_DOUBLE(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> float:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_DOUBLE(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> float:
        return self._get(freshness=freshness)

    def set(self, new_value: float) -> float:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_UTF8(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> str:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_UTF8(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> str:
        return self._get(freshness=freshness)

    def set(self, new_value: str) -> str:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_BLOB(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> bytes:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_BLOB(PropertyProxyBase):
    def get(self, freshness: float | None = None) -> bytes:
        return self._get(freshness=freshness)

    def set(self, new_value: bytes) -> bytes:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_RO_DTYPE(PropertyProxyBase):
    """Yes, this is confusing: It's a proxy for a property whose *value* is a DTypeID"""

    def get(self, freshness: float | None = None) -> DTypeID:
        return self._get(freshness=freshness)


# noinspection PyPep8Naming
class PropertyProxy_RW_DTYPE(PropertyProxyBase):
    """Yes, this is confusing: It's a proxy for a property whose *value* is a DTypeID"""

    def get(self, freshness: float | None = None) -> DTypeID:
        return self._get(freshness=freshness)

    def set(self, new_value: DTypeID) -> DTypeID:
        return self._set(new_value=new_value)


# noinspection PyPep8Naming
class PropertyProxy_LogEventThreshold(PropertyProxy_RW_UINT8):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(property_descriptor=LogEventThresholdPropertyDescriptor(),
                         feature_proxy=feature_proxy,
                         default_freshness=0.0,
                         default_timeout=DEFAULT_REPLY_TIMEOUT)

    def get_value_name(self, freshness: float | None = None) -> str:
        """Human-readable name of the numeric LogLevel-Threshold."""
        uint8_level = self.get(freshness=freshness)
        return logging.getLevelName(uint8_level)


# noinspection PyPep8Naming
class PropertyProxy_FeatureState(PropertyProxy_RO_UINT8):
    """
    Special handling for the FeatureState property, for which we know that we can rely on
    the cached value to be kept up to date by the FeatureStateTransitionEvent.
    This proxy will by default return the cached value and thus avoid unnecessary requests.
    Callers may explicitly force a request by calling .get(freshness=0.0)
    """

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(property_descriptor=FeatureStatePropertyDescriptor(),
                         feature_proxy=feature_proxy,
                         # Infinity, meaning that the cached value will not expire (by default)
                         default_freshness=float('inf'),
                         default_timeout=DEFAULT_REPLY_TIMEOUT)

    def get_value_name(self, freshness: float | None = None) -> str:
        """Human-readable name of the numeric FeatureState."""
        return self.feature_proxy.resolve_state_name(self.get(freshness=freshness))


class FeatureProxyBase:
    feature_descriptor: FeatureDescriptor
    device_proxy: DeviceProxyBase

    def __init__(self,
                 feature_descriptor: FeatureDescriptor,
                 device_proxy: DeviceProxyBase):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy.MyFeatureProxy"
        self.logger = device_proxy.logger.getChild(self.__class__.__name__)

        if not isinstance(feature_descriptor, FeatureDescriptor):
            raise TypeError

        self.logger.debug(f"Initializing instance of {self.__class__.__name__} "
                          f"as proxy for {feature_descriptor}")

        self.feature_descriptor = feature_descriptor
        self.device_proxy = device_proxy

        # Commands
        self.cmd_get_property_value = CommandProxyBase(command_descriptor=GetPropertyValueCommandDescriptor(),
                                                       feature_proxy=self)
        self.cmd_set_property_value = CommandProxyBase(command_descriptor=SetPropertyValueCommandDescriptor(),
                                                       feature_proxy=self)

        # Events
        self.event_handlers = dict()  # Event-proxies will register themselves into this dict
        self.evt_state_transition = StateTransitionEventProxy(self)
        self.evt_log = LogEventProxy(self)

        # Properties
        self.prop_feature_state = PropertyProxy_FeatureState(self)
        self.prop_log_event_threshold = PropertyProxy_LogEventThreshold(self)

    @property
    def router(self) -> hdcproto.host.router.MessageRouter:
        return self.device_proxy.router

    def resolve_state_name(self, state_id: int) -> str:
        if self.feature_descriptor.states is None:  # ToDo: Attribute optionality. #25
            self.logger.warning(f"Can't resolve name of FeatureStateID 0x{state_id:02X}, because "
                                f"no states were registered with this proxy.")
            return f"0x{state_id:02X}"  # Use hexadecimal representation as a fallback

        if state_id not in self.feature_descriptor.states:
            self.logger.error(f"Can't resolve name of unexpected FeatureStateID 0x{state_id:02X}")
            return f"0x{state_id:02X}"  # Use hexadecimal representation as a fallback

        return self.feature_descriptor.states[state_id].name

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


class DeviceProxyBase:
    router: hdcproto.host.router.MessageRouter

    def __init__(self,
                 connection_url: str | None = None,
                 device_descriptor: DeviceDescriptor | None = None):
        # Looks like an instance-attribute, but it's more of a class-attribute, actually. ;-)
        # Logger-name like: "hdcproto.host.proxy.MyDeviceProxy"
        self.logger = logger.getChild(self.__class__.__name__)

        self.router = hdcproto.host.router.MessageRouter(connection_url=connection_url)
        self.device_descriptor = device_descriptor

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

        return bytes_to_value(DTypeID.UINT32, reply_payload)

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

    @classmethod
    def build_from_descriptor(
            cls,
            device_descriptor: DeviceDescriptor,
            custom_proxy_factory: typing.Callable[[object, object], object] | None = None) -> DeviceProxyBase:

        device_proxy = cls.proxy_factory(descriptor=device_descriptor,
                                         parent_proxy=None,
                                         custom_proxy_factory=custom_proxy_factory)

        if not device_proxy:
            raise ValueError("Failed to lookup device proxy")

        for feature_descriptor in device_descriptor.features.values():
            feature_descriptor: FeatureDescriptor
            feature_proxy = cls.proxy_factory(feature_descriptor, device_proxy, custom_proxy_factory)
            if feature_proxy:
                setattr(device_proxy, feature_descriptor.name, feature_proxy)
            for command_descriptor in feature_descriptor.commands.values():
                command_descriptor: CommandDescriptor
                command_proxy = cls.proxy_factory(command_descriptor, feature_proxy, custom_proxy_factory)
                if command_proxy:
                    setattr(feature_proxy, f"cmd_{command_descriptor.name}", command_proxy)
            for event_descriptor in feature_descriptor.events.values():
                event_descriptor: CommandDescriptor
                event_proxy = cls.proxy_factory(event_descriptor, feature_proxy, custom_proxy_factory)
                if event_proxy:
                    setattr(feature_proxy, f"evt_{event_descriptor.name}", event_proxy)
            for property_descriptor in feature_descriptor.properties.values():
                property_descriptor: CommandDescriptor
                property_proxy = cls.proxy_factory(property_descriptor, feature_proxy, custom_proxy_factory)
                if property_proxy:
                    setattr(feature_proxy, f"prop_{property_descriptor.name}", property_proxy)

        return device_proxy

    @classmethod
    def connect_and_build(cls,
                          connection_url,
                          custom_proxy_factory: typing.Callable[[typing.Any, typing.Any], typing.Any | None | False] | None = None
                          ) -> DeviceProxyBase:
        with DeviceProxyBase(connection_url=connection_url) as dev:
            idl_json = dev.get_idl_json()
        idl_python = DeviceDescriptor.from_idl_json(idl_json=idl_json)
        device_proxy = cls.build_from_descriptor(device_descriptor=idl_python,
                                                 custom_proxy_factory=custom_proxy_factory)
        if not device_proxy:
            raise ValueError("Failed to lookup device proxy")

        # ToDo: Fix method name, because we are actually returning an "un-connected" instance. :-P
        return device_proxy

    @classmethod
    def proxy_factory(cls,
                      descriptor,
                      parent_proxy,
                      custom_proxy_factory: typing.Callable[[object, object], object | None | False]):
        """May return None whenever a given descriptor may need to be ignored"""

        if custom_proxy_factory:
            custom_proxy = custom_proxy_factory(descriptor, parent_proxy)
            if custom_proxy is not False:
                # Note how None is a valid result, meaning that no proxy should be instantiated!
                return custom_proxy
            # ... else use default proxy factory below:

        ################
        # Device
        if isinstance(descriptor, DeviceDescriptor):
            # ToDo: Adapt to given HDC-version. Issue #11
            return cls(connection_url=None, device_descriptor=descriptor)

        ################
        # Features
        if isinstance(descriptor, FeatureDescriptor):
            return FeatureProxyBase(feature_descriptor=descriptor, device_proxy=parent_proxy)

        ################
        # Commands
        if isinstance(descriptor, CommandDescriptor):
            if descriptor.id in [CmdID.GET_PROP_VALUE, CmdID.SET_PROP_VALUE]:
                return None  # Ignore, because feature-proxies already implement proxies for mandatory commands

            if descriptor.raises:
                ################
                # Exceptions
                more_specific_exceptions: dict[int, HdcCmdException] = dict()
                for exc_id, exc_descriptor in descriptor.raises.items():
                    more_specific_exception = cls.proxy_factory(exc_descriptor,
                                                                parent_proxy=None,
                                                                custom_proxy_factory=custom_proxy_factory)
                    more_specific_exceptions[exc_id] = more_specific_exception
                descriptor.raises = more_specific_exceptions  # Warning: We are modifying the descriptor here!

            return CommandProxyBase(command_descriptor=descriptor, feature_proxy=parent_proxy)

        ################
        # Events
        if isinstance(descriptor, EventDescriptor):
            if descriptor.id in [EvtID.LOG, EvtID.FEATURE_STATE_TRANSITION]:
                return None  # Ignore, because feature-proxies already implement proxies for mandatory events

            return EventProxyBase(event_descriptor=descriptor, feature_proxy=parent_proxy)

        ################
        # Properties
        if isinstance(descriptor, PropertyDescriptor):
            if descriptor.id == PropID.LOG_EVT_THRESHOLD:
                return PropertyProxy_LogEventThreshold(feature_proxy=parent_proxy)
            if descriptor.id == PropID.FEAT_STATE:
                return PropertyProxy_FeatureState(feature_proxy=parent_proxy)

            class_name = "PropertyProxy_"
            if descriptor.is_readonly:
                class_name += 'RO_'
            else:
                class_name += 'RW_'
            class_name += descriptor.dtype.name
            prop_proxy_class = getattr(sys.modules[__name__], class_name)
            return prop_proxy_class(property_descriptor=descriptor, feature_proxy=parent_proxy)

        ##############
        # Exceptions
        # Special case, because HdcCmdException and its subclasses serve as descriptor, service *and* proxy !
        if descriptor.__class__ == HdcCmdException:  # If not already subclassed, then look-up more specialized class
            exc_id = descriptor.exception_id
            if exc_id == ExcID.CommandFailed:
                return HdcCmdExc_CommandFailed()
            if exc_id == ExcID.UnknownFeature:
                return HdcCmdExc_UnknownFeature()
            if exc_id == ExcID.UnknownCommand:
                return HdcCmdExc_UnknownCommand()
            if exc_id == ExcID.InvalidArgs:
                return HdcCmdExc_InvalidArgs()
            if exc_id == ExcID.NotNow:
                return HdcCmdExc_NotNow()
            if exc_id == ExcID.UnknownProperty:
                return HdcCmdExc_UnknownProperty()
            if exc_id == ExcID.ReadOnlyProperty:
                return HdcCmdExc_ReadOnlyProperty()
            # ... else, baseclass instance will also work
            return descriptor

        if isinstance(descriptor, HdcCmdException):  # ... and any unknown subclass will also work
            return descriptor

        ##############
        # Exceptions

        raise TypeError(f"Unknown descriptor type: {descriptor.__class__.__name__}")
