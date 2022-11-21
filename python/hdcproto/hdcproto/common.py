from __future__ import annotations

import enum
import struct
import typing

HDC_VERSION = "HDC 1.0.0-alpha.11"  # ToDo: How should we manage the HDC version?


@enum.unique
class MessageTypeID(enum.IntEnum):
    """As defined by HDC-spec"""
    META = 0xF0
    ECHO = 0xF1
    COMMAND = 0xF2
    EVENT = 0xF3

    @staticmethod
    def is_custom(message_type_id: int):
        if not is_valid_uint8(message_type_id):
            raise ValueError(f"message_type_id value of {message_type_id} is beyond valid range from 0x00 to 0xFF")
        return message_type_id < 0xF0


@enum.unique
class MetaID(enum.IntEnum):
    """As defined by HDC-spec"""
    HDC_VERSION = 0xF0
    MAX_REQ = 0xF1
    IDL_JSON = 0xF2


@enum.unique
class FeatureID(enum.IntEnum):
    """Reserved ID of the only mandatory HDC-feature required by HDC-spec: the Core feature."""
    CORE = 0x00


@enum.unique
class CmdID(enum.IntEnum):
    """Reserved IDs of mandatory Commands required by HDC-spec"""
    GET_PROP_VALUE = 0xF0
    SET_PROP_VALUE = 0xF1


@enum.unique
class ExcID(enum.IntEnum):
    """Reserved IDs and names of exception IDs used in replies to failed Commands as defined by HDC-spec"""
    NO_ERROR = 0x00
    CommandFailed = 0xF0
    UnknownFeature = 0xF1
    UnknownCommand = 0xF2
    InvalidArgs = 0xF3
    NotNow = 0xF4
    UnknownProperty = 0xF5
    ReadOnlyProperty = 0xF6

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

    The ID values (roughly) obey the following mnemonic system:
    Upper Nibble: Kind of HdcDataType
          0x0_ --> Unsigned integer number
          0x1_ --> Signed integer number
          0x2_ --> Floating point number
          0xA_ --> UTF-8 encoded string (Always variable size: 0xFF)
          0xB_ --> Binary data (Either variable size 0xBF, or boolean 0xB1)
          0xD_ --> DataType (Currently only 0xD1, encoding for HdcDataType itself)

    Lower Nibble: Size of the data type, given in number of bytes
                  i.e. 0x14 --> INT32, whose size is 4 bytes
                  (Exception to the rule: 0x_F denotes a variable size HdcDataType)
                  (Special case 0xB1 --> BOOL size is 1 byte, although only using 1 bit)
    """

    UINT8 = 0x01
    UINT16 = 0x02
    UINT32 = 0x04
    INT8 = 0x11
    INT16 = 0x12
    INT32 = 0x14
    FLOAT = 0x24
    DOUBLE = 0x28
    UTF8 = 0xAF
    BOOL = 0xB1
    BLOB = 0xBF
    DTYPE = 0xD1  # Yes, this is confusing, because it's self-referential: It's the data type ID of HdcDataType itself.

    def struct_format(self) -> str | None:
        """Format character used to (de-)serialize this data type with the struct.pack() and struct.unpack() methods"""
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
            return None  # Meaning: Variable size. Inferred from the size of the received payload.
        if self == HdcDataType.UTF8:
            return None  # Meaning: Variable size. Inferred from the size of the received payload.
        if self == HdcDataType.DTYPE:
            return "B"  # Equivalent to a UINT8 value at the bytes level

    def size(self) -> int | None:
        """
        Number of bytes of the given data type.
        Returns None for variable size types, e.g. UTF8 or BLOB
        """
        fmt = self.struct_format()
        if fmt is None:
            return None

        return struct.calcsize(fmt)

    def is_variable_size(self) -> bool:
        return self.size() is None

    def value_to_bytes(self, value: int | float | str | bytes | HdcDataType) -> bytes:

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

        if isinstance(value, HdcDataType):  # Check before int, because HdcDataType is also an int
            if self == HdcDataType.DTYPE:
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

    def bytes_to_value(self, value_as_bytes: bytes) -> int | float | str | bytes | HdcDataType:

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

        value_as_python_type = struct.unpack(fmt, value_as_bytes)[0]

        if self == HdcDataType.DTYPE:
            try:
                return HdcDataType(value_as_python_type)
            except ValueError:
                raise HdcDataTypeError(f"ID of 0x{value_as_python_type:02X} is not a valid HdcDataType")

        return value_as_python_type

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

        if any(dtype.is_variable_size() for dtype in expected_data_types[:-1]):
            raise HdcDataTypeError("Variable size values (UTF8, BLOB) are only allowed as last item")

        return_values = list()
        for idx, return_data_type in enumerate(expected_data_types):
            if return_data_type.is_variable_size():
                # A size of None means it is variable length,
                size = len(raw_payload)  # Assume that the remainder of the payload is the actual value size
            else:
                size = return_data_type.size()
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
        raw_payload = reply_message[4:]  # Strip 4 leading bytes: MsgID + FeatureID + CmdID + ExcID
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
    LOG_EVT_THRESHOLD = 0xF0
    FEAT_STATE = 0xF1


class HdcError(Exception):
    """Base-class of all exceptions that the HDC package may raise."""
    exception_message: str | None

    def __init__(self, exception_message: str | None = None):
        self.exception_message = exception_message


class HdcDataTypeError(HdcError):
    pass


class HdcCmdException(HdcError):
    """
    (Base)-class of objects that can be:
        - … used as "descriptors" that describe which kind of exceptions each HDC-command may raise.
        - … used to raise an exception in the command-implementation of an HDC-device which the command-service
            will translate into an error-reply-message that gets transmitted to the HDC-host.
        - … used as template to create a cloned object based on the payload parsed from a received
            error-reply-message, which is raised by the proxy-class for the host software to handle.
            Note how the cloned object will also be of the same subclass that the template is.
    """

    exception_id: int
    exception_name: str
    exception_doc: str | None
    exception_message: str | None

    # noinspection PyShadowingBuiltins
    def __init__(self,
                 id: int | enum.IntEnum,
                 name: str | None = None,
                 doc: str | None = None,
                 exception_message: str | None = None):
        super().__init__(exception_message=exception_message)

        if not is_valid_uint8(id):
            raise ValueError(f"exception_id value of {id} is beyond valid range from 0x00 to 0xFF")

        if isinstance(id, enum.IntEnum):
            if name is None:
                name = id.name
            id = int(id)
        elif name is None:
            raise TypeError("Exception.name may only be omitted if the first argument is an IntEnum")

        if not isinstance(name, str) or len(name) < 1:  # ToDo: Validate name with RegEx
            raise ValueError("Invalid exception_name")

        self.exception_id = id
        self.exception_name = name
        self.exception_doc = doc

    def __str__(self):
        if self.__class__ == HdcCmdException:
            return f"{self.__class__.__name__}(id=0x{self.exception_id:02X}, name='{self.exception_name}')"
        return f"{self.__class__.__name__}()"

    def clone_with_hdc_message(self, hdc_message: bytes):
        """
        Uses this instance as a "descriptor" that serves as a template to create a new instance.
        But first it validates the given HDC-exception-message to match the expected ID
        and finally extracts whatever payload the message might contain.

        Override this implementation in any subclass that may
        need to parse custom data from the given message.
        """
        exc_id = hdc_message[3]
        if exc_id != self.exception_id:
            raise ValueError(f"Mismatching Exception-id in HDC reply message. "
                             f"Expected 0x{self.exception_id:02X}, but received 0x{exc_id:02X}")

        exc_text = hdc_message[4:].decode(encoding="utf-8", errors="strict")  # Might be empty

        if self.__class__ == HdcCmdException:  # Does not apply to subclasses!
            return HdcCmdException(id=self.exception_id,
                                   name=self.exception_name,
                                   exception_message=exc_text)

        # The following is meant to work for any subclass whose constructor just takes a single str argument.
        # Subclasses that need anything else should override this baseclass implementation.
        # noinspection PyTypeChecker
        # Disabled inspection, because the following constructor refers to the one of the subclass
        return self.__class__(exc_text)

    def to_idl_dict(self):
        return dict(
            id=self.exception_id,
            name=self.exception_name,
            doc=self.exception_doc  # This is a crazy experiment.
        )

    @classmethod
    def from_idl_dict(cls, d: dict) -> HdcCmdException:
        return cls(**d)


# noinspection PyPep8Naming
class HdcCmdExc_CommandFailed(HdcCmdException):
    def __init__(self, exception_message: str | None = None):
        super().__init__(id=ExcID.CommandFailed,
                         exception_message=exception_message)


# noinspection PyPep8Naming
class HdcCmdExc_UnknownFeature(HdcCmdException):
    def __init__(self, exception_message: str | None = None):
        super().__init__(id=ExcID.UnknownFeature,
                         exception_message=exception_message)


# noinspection PyPep8Naming
class HdcCmdExc_UnknownCommand(HdcCmdException):
    def __init__(self, exception_message: str | None = None):
        super().__init__(id=ExcID.UnknownCommand,
                         exception_message=exception_message)


# noinspection PyPep8Naming
class HdcCmdExc_InvalidArgs(HdcCmdException):
    def __init__(self, exception_message: str | None = None):
        super().__init__(id=ExcID.InvalidArgs,
                         exception_message=exception_message)


# noinspection PyPep8Naming
class HdcCmdExc_NotNow(HdcCmdException):
    def __init__(self, exception_message: str | None = None):
        super().__init__(id=ExcID.NotNow,
                         doc="Command can't be executed at this moment.",
                         exception_message=exception_message)


# noinspection PyPep8Naming
class HdcCmdExc_UnknownProperty(HdcCmdException):
    def __init__(self, exception_message: str | None = None):
        super().__init__(id=ExcID.UnknownProperty,
                         exception_message=exception_message)


# noinspection PyPep8Naming
class HdcCmdExc_ReadOnlyProperty(HdcCmdException):
    def __init__(self, exception_message: str | None = None):
        super().__init__(id=ExcID.ReadOnlyProperty,
                         exception_message=exception_message)
