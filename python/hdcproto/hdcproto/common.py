from __future__ import annotations

import enum
import logging
import struct
import typing

HDC_VERSION = "HDC 1.0.0-alpha.10"  # ToDo: How should we manage the HDC version?


class HdcError(Exception):
    error_message: str

    def __init__(self, error_message: str):
        self.error_message = error_message


class HdcDataTypeError(HdcError):
    pass


class HdcCommandError(HdcError):
    """Exception class raised whenever a device replies with an error-code to a request for executing a command."""
    cmd_reply_message: bytes | None
    error_code: int
    error_name: str

    def __init__(self,
                 feature_id: int,
                 command_id: int,
                 error_code: int,
                 error_name: str,
                 error_message: str | None = None):
        self.feature_id = feature_id
        self.command_id = command_id
        self.error_code = error_code
        self.error_name = error_name
        if error_message is None:
            error_message = ""
        self.error_message = error_message

        self.cmd_reply_message = bytes([MessageTypeID.COMMAND,
                                        self.feature_id,
                                        self.command_id,
                                        self.error_code]) + HdcDataType.UTF8.value_to_bytes(self.error_message)

    @classmethod
    def from_reply(cls, cmd_reply_message: bytes, known_errors: dict[int, str], proxy_logger: logging.Logger):
        """Factory as used by proxies on the host side"""
        feature_id = cmd_reply_message[1]
        command_id = cmd_reply_message[2]
        error_code = cmd_reply_message[3]
        error_message = cmd_reply_message[3:].decode(encoding="utf-8", errors="strict")  # Might be empty
        try:
            error_name = known_errors[error_code]
        except KeyError:
            error_name = f"CommandErrorCode=0x{error_code:02X}"  # Fallback to numeric value
            proxy_logger.warning(f"Unknown CommandErrorCode=0x{error_code:02X}.")

        result = cls(
            feature_id=feature_id,
            command_id=command_id,
            error_code=error_code,
            error_name=error_name,
            error_message=error_message)
        assert cmd_reply_message == result.cmd_reply_message  # Sanity check

        return result


@enum.unique
class MessageTypeID(enum.IntEnum):
    """As defined by HDC-spec"""
    HDC_VERSION = 0xF0
    ECHO = 0xF1
    COMMAND = 0xF2
    EVENT = 0xF3
    META = 0xF4

    @staticmethod
    def is_custom(message_type_id: int):
        if not is_valid_uint8(message_type_id):
            raise ValueError(f"message_type_id value of {message_type_id} is beyond valid range from 0x00 to 0xFF")
        return message_type_id < 0xF0


@enum.unique
class FeatureID(enum.IntEnum):
    """Reserved ID of the only mandatory HDC-feature required by HDC-spec: the Core feature."""
    CORE = 0x00


@enum.unique
class CmdID(enum.IntEnum):
    """Reserved IDs of mandatory Commands required by HDC-spec"""
    GET_PROP_NAME = 0xF0
    GET_PROP_TYPE = 0xF1
    GET_PROP_RO = 0xF2
    GET_PROP_VALUE = 0xF3
    SET_PROP_VALUE = 0xF4
    GET_PROP_DESCR = 0xF5
    GET_CMD_NAME = 0xF6
    GET_CMD_DESCR = 0xF7
    GET_EVT_NAME = 0xF8
    GET_EVT_DESCR = 0xF9


@enum.unique
class CommandErrorCode(enum.IntEnum):
    """Reserved IDs and names of error codes used in replies to Commands as defined by HDC-spec"""
    NO_ERROR = 0x00
    UNKNOWN_FEATURE = 0xF0
    UNKNOWN_COMMAND = 0xF1
    UNKNOWN_PROPERTY = 0xF2
    UNKNOWN_EVENT = 0xF3
    INCORRECT_COMMAND_ARGUMENTS = 0xF4
    COMMAND_NOT_ALLOWED_NOW = 0xF5
    COMMAND_FAILED = 0xF6
    INVALID_PROPERTY_VALUE = 0xF7
    PROPERTY_IS_READ_ONLY = 0xF8

    def __str__(self):
        if self == CommandErrorCode.NO_ERROR:
            return "No error"
        elif self == CommandErrorCode.UNKNOWN_FEATURE:
            return "Unknown feature"
        elif self == CommandErrorCode.UNKNOWN_COMMAND:
            return "Unknown command"
        elif self == CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS:
            return "Incorrect command arguments"
        elif self == CommandErrorCode.COMMAND_NOT_ALLOWED_NOW:
            return "Command not allowed now"
        elif self == CommandErrorCode.COMMAND_FAILED:
            return "Command failed"
        elif self == CommandErrorCode.UNKNOWN_PROPERTY:
            return "Unknown property"
        elif self == CommandErrorCode.INVALID_PROPERTY_VALUE:
            return "Invalid property value"
        elif self == CommandErrorCode.PROPERTY_IS_READ_ONLY:
            return "Property is read-only"
        elif self == CommandErrorCode.UNKNOWN_EVENT:
            return "Unknown event"

    @staticmethod
    def is_custom(command_error_code: int):
        if not is_valid_uint8(command_error_code):
            raise ValueError(f"command_error_code value of {command_error_code} is beyond "
                             f"valid range from 0x00 to 0xFF")
        return command_error_code < 0xF0 and command_error_code != 0


@enum.unique
class EvtID(enum.IntEnum):
    """Reserved IDs of mandatory Events required by HDC-spec"""
    LOG = 0xF0
    FEATURE_STATE_TRANSITION = 0xF1


@enum.unique
class HdcDataType(enum.IntEnum):
    """
    All IDs of data-types defined by HDC-spec.
    Mainly used to define data-type of Properties, but also used
    to parse arguments and return values of Commands.
    Also implements serialization and de-serialization from raw bytes.

    The ID value of each HdcDataType can be interpreted as follows:

    Upper Nibble: Kind of HdcDataType
          0x0_ --> Unsigned integer number
          0x1_ --> Signed integer number
          0x2_ --> Floating point number
          0xB_ --> Binary data
                   (Either variable size 0xBF, or boolean 0xB0)
          0xF_ --> UTF-8 encoded string
                   (Always variable size: 0xFF)

    Lower Nibble: Size of HdcDataType, given in number of bytes
                  i.e. 0x14 --> INT32, whose size is 4 bytes
                  (Exception to the rule: 0x_F denotes a variable size HdcDataType)
                  (Exception to the rule: 0xB0 --> BOOL, whose size is 1 bytes)
    """

    UINT8 = 0x01
    UINT16 = 0x02
    UINT32 = 0x04
    INT8 = 0x11
    INT16 = 0x12
    INT32 = 0x14
    FLOAT = 0x24
    DOUBLE = 0x28
    BOOL = 0xB0
    BLOB = 0xBF
    UTF8 = 0xFF

    def struct_format(self) -> str | None:
        if self == HdcDataType.BOOL:
            return "?"
        if self == HdcDataType.UINT8:
            return "B"
        if self == HdcDataType.UINT16:
            return "<H"
        if self == HdcDataType.UINT32:
            return "<I"
        if self == HdcDataType.INT8:
            return "<b"
        if self == HdcDataType.INT16:
            return "<h"
        if self == HdcDataType.INT32:
            return "<i"
        if self == HdcDataType.FLOAT:
            return "<f"
        if self == HdcDataType.DOUBLE:
            return "<d"
        if self == HdcDataType.BLOB:
            return None  # Meaning: Variable size
        if self == HdcDataType.UTF8:
            return None  # Meaning: Variable size

    def size(self) -> int | None:
        """
        Number of bytes of the given data type.
        Returns None for variable size types, e.g. UTF8 or BLOB
        """
        fmt = self.struct_format()
        if fmt is None:
            return None

        return struct.calcsize(fmt)

    def value_to_bytes(self, value: int | float | str | bytes) -> bytes:

        if isinstance(value, str):
            if self == HdcDataType.UTF8:
                return value.encode(encoding="utf-8", errors="strict")
            raise HdcDataTypeError(f"Improper target data type {self.name} for a str value")

        if isinstance(value, bytes):
            if self == HdcDataType.BLOB:
                return value
            raise HdcDataTypeError(f"Improper target data type {self.name} for a bytes value")

        fmt = self.struct_format()

        if fmt is None:
            raise HdcDataTypeError(f"Don't know how to convert into {self.name}")

        if isinstance(value, bool):
            if self == HdcDataType.BOOL:
                return struct.pack(fmt, value)
            else:
                raise HdcDataTypeError(f"Vale of type {value.__class__} is unsuitable "
                                       f"for a property of type {self.name}")

        if isinstance(value, int):
            if self in (HdcDataType.UINT8,
                        HdcDataType.UINT16,
                        HdcDataType.UINT32,
                        HdcDataType.INT8,
                        HdcDataType.INT16,
                        HdcDataType.INT32):
                return struct.pack(fmt, value)
            else:
                raise HdcDataTypeError(f"Vale of type {value.__class__} is unsuitable "
                                       f"for a property of type {self.name}")

        if isinstance(value, float):
            if self in (HdcDataType.FLOAT,
                        HdcDataType.DOUBLE):
                return struct.pack(fmt, value)
            else:
                raise HdcDataTypeError(f"Vale of type {value.__class__} is unsuitable "
                                       f"for a property of type {self.name}")

        raise HdcDataTypeError(f"Don't know how to convert value of type {value.__class__} "
                               f"into property of type {self.name}")

    def bytes_to_value(self, value_as_bytes: bytes) -> int | float | str | bytes:

        if self == HdcDataType.UTF8:
            return value_as_bytes.decode(encoding="utf-8", errors="strict")

        if self == HdcDataType.BLOB:
            return value_as_bytes

        fmt = self.struct_format()

        if fmt is None:
            raise HdcDataTypeError(f"Don't know how to convert bytes of property type {self.name} "
                                   f"into a python type")

        # Sanity check data size
        expected_size = self.size()
        if len(value_as_bytes) != expected_size:
            raise HdcDataTypeError(
                f"Mismatch of data size. "
                f"Expected {expected_size} bytes, "
                f"but attempted to convert {len(value_as_bytes)}")

        return struct.unpack(fmt, value_as_bytes)[0]

    @staticmethod
    def parse_payload(raw_payload: bytes,
                      expected_data_types: HdcDataType | list[HdcDataType] | None
                      ) -> typing.Any:

        if expected_data_types == [None]:  # Being tolerant with weird ways of saying 'void'
            expected_data_types = None

        if not expected_data_types:
            if len(raw_payload) > 0:
                raise HdcDataTypeError("Payload was expected to be empty, but it isn't.")
            return None

        return_as_list = True  # unless...
        if isinstance(expected_data_types, HdcDataType):
            return_as_list = False  # Reminder about caller not expecting a list, but a single value, instead.
            expected_data_types = [expected_data_types, ]  # Just for it to work in the for-loops below

        if any(not isinstance(t, HdcDataType) for t in expected_data_types):
            raise HdcDataTypeError("Only knows how to parse for HdcDataType. (Build-in python types are not supported)")

        return_values = list()
        for idx, return_data_type in enumerate(expected_data_types):
            size = return_data_type.size()
            if size is None:
                # A size of None means it is variable length, which
                # is only allowed as last of the expected values!
                if idx != len(expected_data_types) - 1:
                    raise HdcDataTypeError("Variable size values (UTF8, BLOB) are only allowed as last item")
                else:
                    size = len(raw_payload)  # Assume that the remainder of the payload is the actual value size
            if size > len(raw_payload):
                raise HdcDataTypeError("Payload is shorter than expected.")
            return_value_as_bytes = raw_payload[:size]
            return_value = return_data_type.bytes_to_value(return_value_as_bytes)
            return_values.append(return_value)
            raw_payload = raw_payload[size:]

        if len(raw_payload) > 0:
            raise HdcDataTypeError("Payload is longer than expected.")

        if not return_as_list:
            assert len(expected_data_types) == 1
            return return_values[0]  # Return first item, without enclosing it in a list.

        return return_values

    @staticmethod
    def parse_command_request_msg(request_message: bytes,
                                  expected_data_types: HdcDataType | list[HdcDataType] | None) -> typing.Any:
        raw_payload = request_message[3:]  # Strip 3 leading bytes: MsgID + FeatureID + CmdID
        return HdcDataType.parse_payload(raw_payload=raw_payload, expected_data_types=expected_data_types)

    @staticmethod
    def parse_command_reply_msg(reply_message: bytes,
                                expected_data_types: HdcDataType | list[HdcDataType] | None) -> typing.Any:
        raw_payload = reply_message[4:]  # Strip 4 leading bytes: MsgID + FeatureID + CmdID + CommandErrorCode
        return HdcDataType.parse_payload(raw_payload=raw_payload, expected_data_types=expected_data_types)

    @staticmethod
    def parse_event_msg(event_message: bytes,
                        expected_data_types: HdcDataType | list[HdcDataType] | None) -> typing.Any:
        raw_payload = event_message[3:]  # Strip 3 leading bytes: MsgID + FeatureID + EvtID
        return HdcDataType.parse_payload(raw_payload=raw_payload, expected_data_types=expected_data_types)


def is_valid_uint8(value_to_check: int) -> bool:
    """Utility method to validate whether a given int is a valid UINT8 value in an efficient and readable manner."""
    if not isinstance(value_to_check, int):
        return False  # Be stoic about it. Let caller take care to raise a more specific Exception.
    return 0x00 <= value_to_check <= 0xFF


@enum.unique
class PropID(enum.IntEnum):
    """Reserved IDs of mandatory Properties required by HDC-spec"""
    FEAT_NAME = 0xF0
    FEAT_TYPE_NAME = 0xF1
    FEAT_TYPE_REV = 0xF2
    FEAT_DESCR = 0xF3
    FEAT_TAGS = 0xF4
    AVAIL_CMD = 0xF5
    AVAIL_EVT = 0xF6
    AVAIL_PROP = 0xF7
    FEAT_STATE = 0xF8
    LOG_EVT_THRESHOLD = 0xF9

    AVAIL_FEAT = 0xFA
    """List of available features on a device (Only mandatory for the Core feature)"""

    MAX_REQ_MSG_SIZE = 0xFB
    """Largest request-message a device can cope with (Only mandatory for the Core feature)"""
