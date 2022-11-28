from __future__ import annotations

import enum

HDC_VERSION = "HDC 1.0.0-alpha.12"  # ToDo: How should we manage the HDC version?


@enum.unique
class MessageTypeID(enum.IntEnum):
    """As defined by HDC-spec"""
    META = 0xF0
    ECHO = 0xF1
    COMMAND = 0xF2
    EVENT = 0xF3


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


@enum.unique
class EvtID(enum.IntEnum):
    """Reserved IDs of mandatory Events required by HDC-spec"""
    LOG = 0xF0
    FEATURE_STATE_TRANSITION = 0xF1


@enum.unique
class PropID(enum.IntEnum):
    """Reserved IDs of mandatory Properties required by HDC-spec"""
    LOG_EVT_THRESHOLD = 0xF0
    FEAT_STATE = 0xF1


@enum.unique
class DTypeID(enum.IntEnum):
    """
    All IDs of data-types defined by HDC-spec.
    As used by descriptors to specify data-type of:
      - Properties,
      - Arguments of Commands and Events
      - return values of Commands

    The ID values (roughly) obey the following mnemonic system:
    Upper Nibble: Kind of DTypeID
          0x0_ --> Unsigned integer number
          0x1_ --> Signed integer number
          0x2_ --> Floating point number
          0xA_ --> UTF-8 encoded string (Always variable size: 0xFF)
          0xB_ --> Binary data (Either variable size 0xBF, or boolean 0xB1)
          0xD_ --> DataType (Currently only 0xD1, encoding for DTypeID itself)

    Lower Nibble: Size of the data type, given in number of bytes
                  i.e. 0x14 --> INT32, whose size is 4 bytes
                  (Exception to the rule: 0x_F denotes a variable size data-type)
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
    DTYPE = 0xD1  # Yes, this is confusing, because it's self-referential: It's the ID of DTypeID itself.
