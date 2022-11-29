from __future__ import annotations


def is_valid_uint8(value_to_check: int) -> bool:
    if not isinstance(value_to_check, int):
        raise TypeError(f"Expected int, but got {value_to_check.__class__.__name__}")
    return 0x00 <= value_to_check <= 0xFF


def is_custom_id(message_type_id: int):
    if not is_valid_uint8(message_type_id):
        raise ValueError(f"message_type_id value of {message_type_id} is beyond valid range from 0x00 to 0xFF")
    return message_type_id < 0xF0


def validate_uint8(value_to_check: int) -> int:
    if not is_valid_uint8(value_to_check):
        raise ValueError(f"Value {value_to_check} is beyond valid range from 0x00 to 0xFF")
    return value_to_check
