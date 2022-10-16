#!/usr/bin/env python3
"""
Proxy classes for the device and its features and properties
"""
from __future__ import annotations

import logging
import time
import typing

import hdc_host.protocol as protocol

DEFAULT_REPLY_TIMEOUT = 0.2


class CommandProxyBase:
    feature_proxy: FeatureProxyBase
    command_id: int
    known_errors: dict[int, str]
    msg_prefix: bytes

    def __init__(self, feature_proxy: FeatureProxyBase, command_id: int):
        self.feature_proxy = feature_proxy
        self.command_id = command_id
        self.known_errors = dict()

        self.msg_prefix = bytes([int(protocol.MessageType.CMD_FEATURE),
                                 self.feature_proxy.protocol_feature.feature_id,
                                 self.command_id])

        # Register mandatory error codes
        self.register_error(code=0x00, error_name="No error")
        self.register_error(code=0x01, error_name="Unknown feature")
        self.register_error(code=0x02, error_name="Unknown command")
        self.register_error(code=0x03, error_name="Incorrect command arguments")
        self.register_error(code=0x04, error_name="Command not allowed now")
        self.register_error(code=0x05, error_name="Command failed")

    def register_error(self, code: int, error_name: str) -> None:
        if code in self.known_errors:
            raise RuntimeError(f'Already registered ErrorCode {code} as "{self.known_errors[code]}"')
        self.known_errors[code] = error_name

    def _send_request_and_get_reply(self, request_message: bytes, timeout: float) -> bytes:

        if not request_message.startswith(self.msg_prefix):
            raise ValueError("Request does not match the expected prefix")

        p = self.feature_proxy.protocol_feature.protocol  # Just an alias for readability

        reply_message = p.send_request_and_get_reply(request_message, timeout)

        if not reply_message.startswith(self.msg_prefix):
            # ToDo: Might be a delayed reply to a previous request that timed-out. Maybe we should just ignore it?
            raise protocol.ProtocolError("Reply does not match the expected prefix")

        if len(reply_message) < 4:
            raise protocol.ProtocolError(f"Expected a reply size of 4 or more bytes, "
                                         f"but received {len(reply_message)}")

        error_code = reply_message[3]
        if error_code != 0x00:
            error_name = self.known_errors.get(error_code, f"Unknown error code 0x{error_code:02x}")
            raise protocol.ProtocolReplyError(error_name, reply_message)

        return reply_message


class RawCommandProxy(CommandProxyBase):
    """
    Convenient CommandProxy for commands for which the caller takes care of providing arguments already serialized
    into raw bytes and also of processing the raw bytes of the return value.
    Instances of this class are callable and will be blocking while awaiting the reply.
    """
    def __init__(self,
                 feature_proxy: FeatureProxyBase,
                 command_id: int,
                 known_errors: dict[int, str] | None = None,
                 reply_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, command_id=command_id)
        if known_errors:
            for code, description in known_errors.items():
                self.register_error(code, description)
        self.reply_timeout = reply_timeout

    def __call__(self, arguments_as_raw_bytes: bytes | None = None) -> bytes:
        request_message = bytearray(self.msg_prefix)
        if arguments_as_raw_bytes:
            request_message.extend(arguments_as_raw_bytes)

        self.feature_proxy.logger.info(f"Executing CommandID=0x{self.command_id:02X}")
        reply_message = self._send_request_and_get_reply(request_message, timeout=self.reply_timeout)
        self.feature_proxy.logger.debug(f"Finished executing CommandID=0x{self.command_id:02X}")
        return reply_message[4:]


class GetPropertyNameCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF1)
        self.register_error(code=0xF0, error_name="Unknown property")

    def __call__(self, property_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> str:
        request_message = bytearray(self.msg_prefix)
        request_message.append(property_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) < 5:  # We expect at least a one-letter name, because empty name strings are illegal.
            raise protocol.ProtocolError(f"Expected a reply size of 5 or more bytes, but received {len(reply_message)}")
        property_name = reply_message[4:].decode('utf-8')
        return property_name


class GetPropertyTypeCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF2)
        self.register_error(code=0xF0, error_name="Unknown property")

    def __call__(self, property_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> protocol.PropertyDataType:
        request_message = bytearray(self.msg_prefix)
        request_message.append(property_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) != 5:
            raise protocol.ProtocolError(f"Expected a reply size of 5 bytes, but received {len(reply_message)}")
        property_type_id = reply_message[4]
        property_type = protocol.PropertyDataType(property_type_id)
        return property_type


class GetPropertyReadonlyCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF3)
        self.register_error(code=0xF0, error_name="Unknown property")

    def __call__(self, property_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> bool:
        request_message = bytearray(self.msg_prefix)
        request_message.append(property_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) != 5:
            raise protocol.ProtocolError(f"Expected a reply size of 5 bytes, but received {len(reply_message)}")
        property_is_readonly = bool(reply_message[4])
        return property_is_readonly


class GetPropertyValueCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF4)
        self.register_error(code=0xF0, error_name="Unknown property")

    def __call__(self, property_id: int, timeout: float) -> bytes:
        """Returns the property value as raw bytes"""
        request_message = bytearray(self.msg_prefix)
        request_message.append(property_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        return reply_message[4:]


class SetPropertyValueCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF5)
        self.register_error(code=0xF0, error_name="Unknown property")
        self.register_error(code=0xF1, error_name="Invalid property value")
        self.register_error(code=0xF2, error_name="Property is read-only")

    def __call__(self,
                 property_id: int,
                 new_value_as_raw_bytes: bytes,
                 timeout: float = DEFAULT_REPLY_TIMEOUT) -> bytes:
        """Returns the property value as raw bytes"""
        request_message = bytearray(self.msg_prefix)
        request_message.append(property_id)
        request_message.extend(new_value_as_raw_bytes)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        return reply_message[4:]


class GetPropertyDescriptionCommandProxy(CommandProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF6)
        self.register_error(code=0xF0, error_name="Unknown property")

    def __call__(self, property_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> str:
        request_message = bytearray(self.msg_prefix)
        request_message.append(property_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) < 4:  # Empty description strings are legal.
            raise protocol.ProtocolError(f"Expected a reply size of 4 or more bytes, but received {len(reply_message)}")
        property_description = reply_message[4:].decode('utf-8')
        return property_description


class GetCommandNameCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF7)
        # Reuses ErrorCode 0x02 "Unknown command" to also mean we requested the name for an unknown CommandID

    def __call__(self, command_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> str:
        request_message = bytearray(self.msg_prefix)
        request_message.append(command_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) < 5:  # We expect at least a one-letter name, because empty name strings are illegal.
            raise protocol.ProtocolError(f"Expected a reply size of 5 or more bytes, but received {len(reply_message)}")
        command_name = reply_message[4:].decode('utf-8')
        return command_name


class GetCommandDescriptionCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF8)
        # Reuses ErrorCode 0x02 "Unknown command" to also mean we requested the description for an unknown CommandID

    def __call__(self, command_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> str:
        request_message = bytearray(self.msg_prefix)
        request_message.append(command_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) < 4:  # Empty description strings are legal.
            raise protocol.ProtocolError(f"Expected a reply size of 4 or more bytes, but received {len(reply_message)}")
        command_description = reply_message[4:].decode('utf-8')
        return command_description


class GetEventNameCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xF9)
        self.register_error(code=0xF3, error_name="Unknown event")

    def __call__(self, event_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> str:
        request_message = bytearray(self.msg_prefix)
        request_message.append(event_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) < 5:  # We expect at least a one-letter name, because empty name strings are illegal.
            raise protocol.ProtocolError(f"Expected a reply size of 5 or more bytes, but received {len(reply_message)}")
        event_name = reply_message[4:].decode('utf-8')
        return event_name


class GetEventDescriptionCommandProxy(CommandProxyBase):
    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, command_id=0xFA)
        self.register_error(code=0xF3, error_name="Unknown event")

    def __call__(self, event_id: int, timeout: float = DEFAULT_REPLY_TIMEOUT) -> str:
        request_message = bytearray(self.msg_prefix)
        request_message.append(event_id)
        reply_message = self._send_request_and_get_reply(request_message, timeout)
        if len(reply_message) < 4:  # Empty description strings are legal.
            raise protocol.ProtocolError(f"Expected a reply size of 4 or more bytes, but received {len(reply_message)}")
        event_description = reply_message[4:].decode('utf-8')
        return event_description


class EventProxyBase:
    feature_proxy: FeatureProxyBase
    event_id: int

    def __init__(self,
                 feature_proxy: FeatureProxyBase,
                 event_id: int,
                 event_handler: typing.Callable[[bytes], None] | None = None):
        self.event_id = event_id
        self.feature_proxy = feature_proxy
        if event_handler is not None:
            self.register_event_handler(event_handler)

    def register_event_handler(self, event_handler: typing.Callable[[bytes], None]):
        self.feature_proxy.protocol_feature.register_event_handler(self.event_id, event_handler)


class LogEventProxy(EventProxyBase):
    logger: logging.Logger

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, event_id=0xF0, event_handler=self._handle_event)
        self.logger = feature_proxy.logger.getChild("LogEvent")

    def _handle_event(self, message: bytes) -> None:
        log_level = message[3]
        log_message = message[4:].decode(encoding="utf-8", errors="strict")
        self.logger.log(level=log_level, msg=log_message)


class StateTransitionEventProxy(EventProxyBase):
    logger: logging.Logger

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, event_id=0xF1, event_handler=self._handle_event)
        self.logger = feature_proxy.logger.getChild("StateTransitionEvent")

    def _handle_event(self, message: bytes):
        previous_state_id = message[3]
        current_state_id = message[4]
        self.logger.info(f"%s → %s",
                         self.feature_proxy.resolve_state_name(previous_state_id),
                         self.feature_proxy.resolve_state_name(current_state_id))
        # Inject new state into the cache for the FeatureState property
        self.feature_proxy.prop_feature_state._update_cached_value(current_state_id)


class PropertyProxyBase:
    feature_proxy: FeatureProxyBase
    property_id: int
    property_data_type: protocol.PropertyDataType
    is_readonly: bool
    default_freshness: float
    default_timeout: float
    _cached_value: bool | int | float | str | bytes | None
    _timestamp_of_cached_value: float

    def __init__(self,
                 feature_proxy: FeatureProxyBase,
                 property_id: int,
                 property_data_type: protocol.PropertyDataType,
                 is_readonly: bool,
                 default_freshness: float,
                 default_timeout: float):
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
            property_value_as_raw_bytes = self.feature_proxy._cmd_get_property_value(property_id=self.property_id,
                                                                                     timeout=timeout)
            property_value = self.property_data_type.bytes_to_value(property_value_as_raw_bytes)
            self._update_cached_value(property_value)
            self.feature_proxy.logger.debug(f"PropertyID=0x{self.property_id:02X} getter "
                                            f"returns {self._cached_value}")
        else:
            self.feature_proxy.logger.debug(f"PropertyID=0x{self.property_id:02X} getter "
                                            f"returns {self._cached_value} from cache "
                                            f"which was updated {age_of_cached_value:.3f}s ago "
                                            f"and thus is fresher than {freshness:.3f}s")

        return self._cached_value

    def _set(self,
             new_value: bool | int | float | str | bytes,
             timeout: float | None = None
             ) -> bool | int | float | str | bytes:

        if self.is_readonly:
            raise RuntimeError()

        if timeout is None:
            timeout = self.default_timeout

        self.feature_proxy.logger.info(f"Setting PropertyID=0x{self.property_id:02X} to a value of {new_value}")

        request_value_as_raw_bytes = self.property_data_type.value_to_bytes(new_value)
        # Note how the value returned with the reply is the actual value set on
        # the device and it may differ from the value sent in the request!
        reply_value_as_raw_bytes = self.feature_proxy._cmd_set_property_value(
            property_id=self.property_id,
            new_value_as_raw_bytes=request_value_as_raw_bytes,
            timeout=timeout)
        property_value = self.property_data_type.bytes_to_value(reply_value_as_raw_bytes)

        self._update_cached_value(property_value)

        if property_value != new_value:
            self.feature_proxy.logger.warning(f"Attempted to set PropertyID=0x{self.property_id:02X} "
                                              f"to a value of {new_value}, but "
                                              f"effectively a value of {property_value} was set.")

        return self._cached_value


# noinspection PyPep8Naming
class PropertyProxy_RO_BOOL(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.BOOL, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> bool:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_BOOL(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.BOOL, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UINT8, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UINT8, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UINT16, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT16(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UINT16, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UINT32, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UINT32(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UINT32, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.INT8, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.INT8, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.INT16, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT16(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.INT16, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.INT32, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> int:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_INT32(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.INT32, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.FLOAT, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> float:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_FLOAT(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.FLOAT, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.DOUBLE, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> float:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_DOUBLE(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.DOUBLE, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UTF8, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> str:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_UTF8(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.UTF8, is_readonly=False,
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
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.BLOB, is_readonly=True,
                         default_freshness=default_freshness,
                         default_timeout=default_timeout)

    def get(self, freshness: float | None = None, timeout: float | None = None) -> bytes:
        return self._get(freshness=freshness, timeout=timeout)


# noinspection PyPep8Naming
class PropertyProxy_RW_BLOB(PropertyProxyBase):

    def __init__(self, feature_proxy: FeatureProxyBase, property_id: int,
                 default_freshness: float = 0.0,
                 default_timeout: float = DEFAULT_REPLY_TIMEOUT):
        super().__init__(feature_proxy, property_id, protocol.PropertyDataType.BLOB, is_readonly=False,
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
                         property_id=0xF8,
                         # Infinity, meaning that the cached value will not expire (by default)
                         default_freshness=float('inf'))

    def get_value_name(self, freshness: float | None = None, timeout: float | None = None) -> str:
        """Human readable name of the numeric FeatureState."""
        return self.feature_proxy.resolve_state_name(self.get(freshness=freshness, timeout=timeout))


# noinspection PyPep8Naming
class PropertyProxy_LogEventThreshold(PropertyProxy_RW_UINT8):

    def __init__(self, feature_proxy: FeatureProxyBase):
        super().__init__(feature_proxy, property_id=0xF9)

    def get_value_name(self, freshness: float | None = None, timeout: float | None = None) -> str:
        """Human readable name of the numeric LogLevel-Threshold."""
        uint8_level = self.get(freshness=freshness, timeout=timeout)
        return logging.getLevelName(uint8_level)


class FeatureProxyBase:
    protocol_feature: protocol.Feature

    def __init__(self, device_proxy: DeviceProxyBase, feature_id: int):
        self.protocol_feature = protocol.Feature(protocol=device_proxy.protocol, feature_id=feature_id)
        self.logger = \
            logging.getLogger("HDC.proxy").getChild(device_proxy.__class__.__name__).getChild(self.__class__.__name__)

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
        self.prop_feature_name = PropertyProxy_RO_UTF8(self, property_id=0xF0, default_freshness=inf)
        self.prop_feature_type_name = PropertyProxy_RO_UTF8(self, property_id=0xF1, default_freshness=inf)
        self.prop_feature_type_revision = PropertyProxy_RO_UINT8(self, property_id=0xF2, default_freshness=inf)
        self.prop_feature_description = PropertyProxy_RO_UTF8(self, property_id=0xF3, default_freshness=inf)
        self.prop_feature_tags = PropertyProxy_RO_UTF8(self, property_id=0xF4, default_freshness=inf)
        self.prop_available_commands = PropertyProxy_RO_BLOB(self, property_id=0xF5, default_freshness=inf)
        self.prop_available_events = PropertyProxy_RO_BLOB(self, property_id=0xF6, default_freshness=inf)
        self.prop_available_properties = PropertyProxy_RO_BLOB(self, property_id=0xF7, default_freshness=inf)
        # Properties (mutable)
        self.prop_feature_state = PropertyProxy_FeatureState(self)
        self.prop_log_event_threshold = PropertyProxy_LogEventThreshold(self)

    def resolve_state_name(self, state_id: int) -> str:
        try:
            # The following expects a nested IntEnum as defined within the most derived sub-class of FeatureProxyBase!
            # noinspection PyUnresolvedReferences
            return type(self).FeatureStateEnum(state_id).name
        except Exception:
            if type(self) is not FeatureProxyBase:  # Suppress warning in ad-hoc usages of FeatureProxyBase
                # Forgot to define all states in "FeatureStateEnum" nested within the sub-classed feature-proxy?
                self.logger.warning(f"Can't resolve name of FeatureState 0x{state_id:02X}")
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
            if any(v > 0xFF for v in exits):
                raise ValueError("State ID values can't be larger than 0xFF")

            while self.prop_feature_state.get() in exits:
                if time.perf_counter() > deadline:
                    raise TimeoutError("Timeout before exiting state")
                time.sleep(polling_period)

        if enters is not None:
            if any(v > 0xFF for v in enters):
                raise ValueError("State ID values can't be larger than 0xFF")

            while self.prop_feature_state.get() not in enters:
                if time.perf_counter() > deadline:
                    raise TimeoutError("Timeout before entering state")
                time.sleep(polling_period)


class CoreFeatureProxyBase(FeatureProxyBase):
    def __init__(self, device_proxy: DeviceProxyBase):
        super().__init__(device_proxy=device_proxy, feature_id=0x00)  # Address must be 0x00 for device-core feature!

        # Commands (No mandatory commands for a Core feature)

        # Events (No mandatory events for a Core feature)

        # Properties
        self.prop_available_features = PropertyProxy_RO_BLOB(self, 0xFA)  # Introspection: Features of this device
        self.prop_max_req_msg_size = PropertyProxy_RO_UINT16(self, 0xFB)  # Largest request-message a device can cope



class DeviceProxyBase:
    protocol: protocol.Protocol
    core: CoreFeatureProxyBase

    def __init__(self, connection_url: str):
        serial_transport = protocol.SerialTransport(serial_url=connection_url)
        self.protocol = protocol.Protocol(transport=serial_transport)

        # The following may be needed for introspection when using bare DeviceProxyBase objects.
        # Sub-classes will typically override it with a more specific core-feature proxy.
        self.core = CoreFeatureProxyBase(self)
