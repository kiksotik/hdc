import enum
import struct


class HdcError(Exception):
    error_name: str

    def __init__(self, error_description: str):
        self.error_name = error_description


@enum.unique
class MessageType(enum.IntEnum):
    CMD_ECHO = 0xCE
    CMD_FEATURE = 0xCF
    EVENT_FEATURE = 0xEF


@enum.unique
class FeatureID(enum.IntEnum):
    CORE = 0x00


@enum.unique
class CmdID(enum.IntEnum):
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
    LOG = 0xF0
    STATE_TRANSITION = 0xF1


@enum.unique
class DataType(enum.IntEnum):
    """
    The ID values of each DataType can be interpreted as follows:

    Upper Nibble: Kind of DataType
          0x0_ --> Unsigned integer number
          0x1_ --> Signed integer number
          0x2_ --> Floating point number
          0xB_ --> Binary data
                   (Either variable size 0xBF, or boolean 0xB0)
          0xF_ --> UTF-8 encoded string
                   (Always variable size: 0xFF)

    Lower Nibble: Size of DataType, given in number of bytes
                  i.e. 0x14 --> INT32, whose size is 4 bytes
                  (Exception to the rule: 0x_F denotes a variable size DataType)
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
        if self == DataType.BOOL:
            return "?"
        if self == DataType.UINT8:
            return "B"
        if self == DataType.UINT16:
            return "<H"
        if self == DataType.UINT32:
            return "<I"
        if self == DataType.INT8:
            return "<b"
        if self == DataType.INT16:
            return "<h"
        if self == DataType.INT32:
            return "<i"
        if self == DataType.FLOAT:
            return "<f"
        if self == DataType.DOUBLE:
            return "<d"
        if self == DataType.BLOB:
            return None
        if self == DataType.UTF8:
            return None

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
            if self == DataType.UTF8:
                return value.encode(encoding="utf-8", errors="strict")
            raise HdcError(f"Improper target data type {self.name} for a str value")

        if isinstance(value, bytes):
            if self == DataType.BLOB:
                return value
            raise HdcError(f"Improper target data type {self.name} for a bytes value")

        fmt = self.struct_format()

        if fmt is None:
            raise HdcError(f"Don't know how to convert into {self.name}")

        if isinstance(value, bool):
            if self == DataType.BOOL:
                return struct.pack(fmt, value)
            else:
                raise HdcError(f"Vale of type {value.__class__} is unsuitable "
                               f"for a property of type {self.name}")

        if isinstance(value, int):
            if self in (DataType.UINT8,
                        DataType.UINT16,
                        DataType.UINT32,
                        DataType.INT8,
                        DataType.INT16,
                        DataType.INT32):
                return struct.pack(fmt, value)
            else:
                raise HdcError(f"Vale of type {value.__class__} is unsuitable "
                               f"for a property of type {self.name}")

        if isinstance(value, float):
            if self in (DataType.FLOAT,
                        DataType.DOUBLE):
                return struct.pack(fmt, value)
            else:
                raise HdcError(f"Vale of type {value.__class__} is unsuitable "
                               f"for a property of type {self.name}")

        raise HdcError(f"Don't know how to convert value of type {value.__class__} "
                       f"into property of type {self.name}")

    def bytes_to_value(self, value_as_bytes: bytes) -> int | float | str | bytes:

        if self == DataType.UTF8:
            return value_as_bytes.decode(encoding="utf-8", errors="strict")

        if self == DataType.BLOB:
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


@enum.unique
class PropID(enum.IntEnum):
    """Property IDs as defined by HDC-spec"""
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
