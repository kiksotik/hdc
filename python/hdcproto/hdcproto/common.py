from __future__ import annotations

import enum
import struct
import typing


class HdcError(Exception):
    error_name: str

    def __init__(self, error_description: str):
        self.error_name = error_description


@enum.unique
class MessageType(enum.IntEnum):
    """HDC-message types as defined by HDC-spec"""
    CMD_ECHO = 0xCE
    CMD_FEATURE = 0xCF
    EVENT_FEATURE = 0xEF


@enum.unique
class FeatureID(enum.IntEnum):
    """Reserved ID of the only mandatory HDC-feature required by HDC-spec: the Core feature."""
    CORE = 0x00


@enum.unique
class CmdID(enum.IntEnum):
    """Reserved IDs of mandatory FeatureCommands required by HDC-spec"""
    GET_PROP_NAME = 0xF1
    GET_PROP_TYPE = 0xF2
    GET_PROP_RO = 0xF3
    GET_PROP_VALUE = 0xF4
    SET_PROP_VALUE = 0xF5
    GET_PROP_DESCR = 0xF6
    GET_CMD_NAME = 0xF7
    GET_CMD_DESCR = 0xF8
    GET_EVT_NAME = 0xF9
    GET_EVT_DESCR = 0xFA


@enum.unique
class ReplyErrorCode(enum.IntEnum):
    """Reserved IDs and names of error codes used in replies to FeatureCommands as defined by HDC-spec"""
    NO_ERROR = 0x00
    UNKNOWN_FEATURE = 0x01
    UNKNOWN_COMMAND = 0x02
    INCORRECT_COMMAND_ARGUMENTS = 0x03
    COMMAND_NOT_ALLOWED_NOW = 0x04
    COMMAND_FAILED = 0x05
    UNKNOWN_PROPERTY = 0xF0
    INVALID_PROPERTY_VALUE = 0xF1
    PROPERTY_IS_READ_ONLY = 0xF2
    UNKNOWN_EVENT = 0xF3

    def __str__(self):
        if self == ReplyErrorCode.NO_ERROR:
            return "No error"
        elif self == ReplyErrorCode.UNKNOWN_FEATURE:
            return "Unknown feature"
        elif self == ReplyErrorCode.UNKNOWN_COMMAND:
            return "Unknown command"
        elif self == ReplyErrorCode.INCORRECT_COMMAND_ARGUMENTS:
            return "Incorrect command arguments"
        elif self == ReplyErrorCode.COMMAND_NOT_ALLOWED_NOW:
            return "Command not allowed now"
        elif self == ReplyErrorCode.COMMAND_FAILED:
            return "Command failed"
        elif self == ReplyErrorCode.UNKNOWN_PROPERTY:
            return "Unknown property"
        elif self == ReplyErrorCode.INVALID_PROPERTY_VALUE:
            return "Invalid property value"
        elif self == ReplyErrorCode.PROPERTY_IS_READ_ONLY:
            return "Property is read-only"
        elif self == ReplyErrorCode.UNKNOWN_EVENT:
            return "Unknown event"


@enum.unique
class EvtID(enum.IntEnum):
    """Reserved IDs of mandatory Events required by HDC-spec"""
    LOG = 0xF0
    STATE_TRANSITION = 0xF1


@enum.unique
class HdcDataType(enum.IntEnum):
    """
    All IDs of data-types defined by HDC-spec.
    Mainly used to define data-type of FeatureProperties, but also used
    to parse arguments and return values of FeatureCommands.
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
            raise HdcError(f"Improper target data type {self.name} for a str value")

        if isinstance(value, bytes):
            if self == HdcDataType.BLOB:
                return value
            raise HdcError(f"Improper target data type {self.name} for a bytes value")

        fmt = self.struct_format()

        if fmt is None:
            raise HdcError(f"Don't know how to convert into {self.name}")

        if isinstance(value, bool):
            if self == HdcDataType.BOOL:
                return struct.pack(fmt, value)
            else:
                raise HdcError(f"Vale of type {value.__class__} is unsuitable "
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
                raise HdcError(f"Vale of type {value.__class__} is unsuitable "
                               f"for a property of type {self.name}")

        if isinstance(value, float):
            if self in (HdcDataType.FLOAT,
                        HdcDataType.DOUBLE):
                return struct.pack(fmt, value)
            else:
                raise HdcError(f"Vale of type {value.__class__} is unsuitable "
                               f"for a property of type {self.name}")

        raise HdcError(f"Don't know how to convert value of type {value.__class__} "
                       f"into property of type {self.name}")

    def bytes_to_value(self, value_as_bytes: bytes) -> int | float | str | bytes:

        if self == HdcDataType.UTF8:
            return value_as_bytes.decode(encoding="utf-8", errors="strict")

        if self == HdcDataType.BLOB:
            return value_as_bytes

        fmt = self.struct_format()

        if fmt is None:
            raise HdcError(f"Don't know how to convert bytes of property type {self.name} "
                           f"into a python type")

        # Sanity check data size
        expected_size = self.size()
        if len(value_as_bytes) != expected_size:
            raise HdcError(
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
                raise ValueError("Payload was expected to be empty, but it isn't.")
            return None

        return_as_list = True  # unless...
        if isinstance(expected_data_types, HdcDataType):
            return_as_list = False  # Reminder about caller not expecting a list, but a single value, instead.
            expected_data_types = [expected_data_types, ]  # Just for it to work in the for-loops below

        if any(not isinstance(t, HdcDataType) for t in expected_data_types):
            raise TypeError("Only knows how to parse for HdcDataType. (Build-in python types are not supported)")

        return_values = list()
        for idx, return_data_type in enumerate(expected_data_types):
            size = return_data_type.size()
            if size is None:
                # A size of None means it's variable length, which
                # is only allowed as last of the expected values!
                if idx != len(expected_data_types) - 1:
                    raise ValueError("Variable size values (UTF8, BLOB) are only allowed as last item")
                else:
                    size = len(raw_payload)  # Assume that the remainder of the payload is the actual value size
            if size > len(raw_payload):
                raise ValueError("Payload is shorter than expected.")
            return_value_as_bytes = raw_payload[:size]
            return_value = return_data_type.bytes_to_value(return_value_as_bytes)
            return_values.append(return_value)
            raw_payload = raw_payload[size:]

        if len(raw_payload) > 0:
            raise ValueError("Payload is longer than expected.")

        if not return_as_list:
            assert len(expected_data_types) == 1
            return return_values[0]  # Return first item, without enclosing it in a list.

        return return_values

    @staticmethod
    def parse_reply_msg(reply_message: bytes,
                        expected_data_types: HdcDataType | list[HdcDataType] | None) -> typing.Any:
        raw_payload = reply_message[4:]  # Strip 4 leading bytes: MsgID + FeatureID + EvtID + ReplyErrorCode
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
    """Reserved IDs of mandatory FeatureProperties required by HDC-spec"""
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
