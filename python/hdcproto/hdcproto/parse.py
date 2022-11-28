from __future__ import annotations

import struct
import typing

from hdcproto.exception import HdcDataTypeError
from hdcproto.spec import DTypeID


def dtype_struct_format(dtype: DTypeID) -> str | None:
    """Format character used to (de-)serialize this data type with the struct.pack() and struct.unpack() methods"""
    if dtype == DTypeID.BOOL:
        return "?"
    if dtype == DTypeID.UINT8:
        return "B"
    if dtype == DTypeID.UINT16:
        return "<H"
    if dtype == DTypeID.UINT32:
        return "<I"
    if dtype == DTypeID.INT8:
        return "<b"
    if dtype == DTypeID.INT16:
        return "<h"
    if dtype == DTypeID.INT32:
        return "<i"
    if dtype == DTypeID.FLOAT:
        return "<f"
    if dtype == DTypeID.DOUBLE:
        return "<d"
    if dtype == DTypeID.BLOB:
        return None  # Meaning: Variable size. Inferred from the size of the received payload.
    if dtype == DTypeID.UTF8:
        return None  # Meaning: Variable size. Inferred from the size of the received payload.
    if dtype == DTypeID.DTYPE:
        return "B"  # Equivalent to a UINT8 value at the bytes level
    raise NotImplemented(f"Unknown DTypeID {dtype}")


def dtype_size(dtype: DTypeID) -> int | None:
    """
    Number of bytes of the given data type.
    Returns None for variable size types, e.g. UTF8 or BLOB
    """
    fmt = dtype_struct_format(dtype)
    if fmt is None:
        return None

    return struct.calcsize(fmt)


def is_variable_size_dtype(dtype: DTypeID) -> bool:
    return dtype_size(dtype) is None


def value_to_bytes(dtype: DTypeID, value: int | float | str | bytes | DTypeID) -> bytes:
    if isinstance(value, str):
        if dtype == DTypeID.UTF8:
            return value.encode(encoding="utf-8", errors="strict")
        raise HdcDataTypeError(f"Improper target data type {dtype.name} for a str value")

    if isinstance(value, bytes):
        if dtype == DTypeID.BLOB:
            return value
        raise HdcDataTypeError(f"Improper target data type {dtype.name} for a bytes value")

    fmt = dtype_struct_format(dtype)

    if fmt is None:
        raise HdcDataTypeError(f"Don't know how to convert into {dtype.name}")

    if isinstance(value, bool):
        if dtype == DTypeID.BOOL:
            return struct.pack(fmt, value)
        else:
            raise HdcDataTypeError(f"Vale of type {value.__class__} is unsuitable "
                                   f"for a property of type {dtype.name}")

    if isinstance(value, DTypeID):  # Check before int, because DTypeID is also an int
        if dtype == DTypeID.DTYPE:
            return struct.pack(fmt, value)
        else:
            raise HdcDataTypeError(f"Vale of type {value.__class__} is unsuitable "
                                   f"for a property of type {dtype.name}")

    if isinstance(value, int):
        if dtype in (DTypeID.UINT8,
                     DTypeID.UINT16,
                     DTypeID.UINT32,
                     DTypeID.INT8,
                     DTypeID.INT16,
                     DTypeID.INT32):
            return struct.pack(fmt, value)
        else:
            raise HdcDataTypeError(f"Vale of type {value.__class__} is unsuitable "
                                   f"for a property of type {dtype.name}")

    if isinstance(value, float):
        if dtype in (DTypeID.FLOAT,
                     DTypeID.DOUBLE):
            return struct.pack(fmt, value)
        else:
            raise HdcDataTypeError(f"Vale of type {value.__class__} is unsuitable "
                                   f"for a property of type {dtype.name}")

    raise HdcDataTypeError(f"Don't know how to convert value of type {value.__class__} "
                           f"into property of type {dtype.name}")


def bytes_to_value(dtype, value_as_bytes: bytes) -> int | float | str | bytes | DTypeID:
    if dtype == DTypeID.UTF8:
        return value_as_bytes.decode(encoding="utf-8", errors="strict")

    if dtype == DTypeID.BLOB:
        return value_as_bytes

    fmt = dtype_struct_format(dtype)

    if fmt is None:
        raise HdcDataTypeError(f"Don't know how to convert bytes of property type {dtype.name} "
                               f"into a python type")

    # Sanity check data size
    expected_size = dtype_size(dtype)
    if len(value_as_bytes) != expected_size:
        raise HdcDataTypeError(
            f"Mismatch of data size. "
            f"Expected {expected_size} bytes, "
            f"but attempted to convert {len(value_as_bytes)}")

    value_as_python_type = struct.unpack(fmt, value_as_bytes)[0]

    if dtype == DTypeID.DTYPE:
        try:
            return DTypeID(value_as_python_type)
        except ValueError:
            raise HdcDataTypeError(f"ID of 0x{value_as_python_type:02X} is not a valid DTypeID")

    return value_as_python_type


def parse_payload(raw_payload: bytes,
                  expected_data_types: DTypeID | list[DTypeID] | None
                  ) -> typing.Any:
    if expected_data_types == [None]:  # Being tolerant with weird ways of saying 'void'
        expected_data_types = None

    if not expected_data_types:
        if len(raw_payload) > 0:
            raise HdcDataTypeError("Payload was expected to be empty, but it isn't.")
        return None

    return_as_list = True  # unless...
    if isinstance(expected_data_types, DTypeID):
        return_as_list = False  # Reminder about caller not expecting a list, but a single value, instead.
        expected_data_types = [expected_data_types, ]  # Just for it to work in the for-loops below

    if any(not isinstance(t, DTypeID) for t in expected_data_types):
        raise HdcDataTypeError("Only knows how to parse for DTypeID. (Build-in python types are not supported)")

    if any(is_variable_size_dtype(dt) for dt in expected_data_types[:-1]):
        raise HdcDataTypeError("Variable size values (UTF8, BLOB) are only allowed as last item")

    return_values = list()
    for idx, return_data_type in enumerate(expected_data_types):
        if is_variable_size_dtype(return_data_type):
            # A size of None means it is variable length,
            size = len(raw_payload)  # Assume that the remainder of the payload is the actual value size
        else:
            size = dtype_size(return_data_type)
            if size > len(raw_payload):
                raise HdcDataTypeError("Payload is shorter than expected.")
        return_value_as_bytes = raw_payload[:size]
        return_value = bytes_to_value(return_data_type, return_value_as_bytes)
        return_values.append(return_value)
        raw_payload = raw_payload[size:]

    if len(raw_payload) > 0:
        raise HdcDataTypeError("Payload is longer than expected.")

    if not return_as_list:
        assert len(expected_data_types) == 1
        return return_values[0]  # Return first item, without enclosing it in a list.

    return return_values


def parse_command_request_payload(request_message: bytes,
                                  expected_data_types: DTypeID | list[DTypeID] | None) -> typing.Any:
    raw_payload = request_message[3:]  # Strip 3 leading bytes: MsgID + FeatureID + CmdID
    return parse_payload(raw_payload=raw_payload, expected_data_types=expected_data_types)


def parse_command_reply_payload(reply_message: bytes,
                                expected_data_types: DTypeID | list[DTypeID] | None) -> typing.Any:
    raw_payload = reply_message[4:]  # Strip 4 leading bytes: MsgID + FeatureID + CmdID + ExcID
    return parse_payload(raw_payload=raw_payload, expected_data_types=expected_data_types)


def parse_event_payload(event_message: bytes,
                        expected_data_types: DTypeID | list[DTypeID] | None) -> typing.Any:
    raw_payload = event_message[3:]  # Strip 3 leading bytes: MsgID + FeatureID + EvtID
    return parse_payload(raw_payload=raw_payload, expected_data_types=expected_data_types)
