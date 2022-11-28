from __future__ import annotations


def is_valid_uint8(value_to_check: int) -> bool:
    """Utility method to validate whether a given int is a valid UINT8 value in an efficient and readable manner."""
    if not isinstance(value_to_check, int):
        return False  # Be stoic about it. Let caller take care to raise a more specific Exception.
    return 0x00 <= value_to_check <= 0xFF


def is_custom_id(message_type_id: int):
    if not is_valid_uint8(message_type_id):
        raise ValueError(f"message_type_id value of {message_type_id} is beyond valid range from 0x00 to 0xFF")
    return message_type_id < 0xF0
