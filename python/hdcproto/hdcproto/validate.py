from __future__ import annotations

import re

import semver

from hdcproto.spec import DTypeID


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


def is_valid_dtype(dtype_to_check: DTypeID | int | str) -> bool:
    if isinstance(dtype_to_check, DTypeID):
        return True

    try:
        if isinstance(dtype_to_check, int):
            _ = DTypeID(dtype_to_check)
            return True

        if isinstance(dtype_to_check, str):
            _ = DTypeID[dtype_to_check]
            return True
    except (ValueError, KeyError):
        return False

    raise TypeError(f"Expected DTypeID or int or str, but got {dtype_to_check.__class__.__name__}")


def validate_dtype(dtype_to_check: DTypeID | int | str) -> DTypeID:
    if isinstance(dtype_to_check, DTypeID):
        return dtype_to_check

    try:
        if isinstance(dtype_to_check, int):
            return DTypeID(dtype_to_check)  # May raise a ValueError

        if isinstance(dtype_to_check, str):
            return DTypeID[dtype_to_check]  # May raise a KeyError
    except (ValueError, KeyError):
        raise ValueError(f"The value {repr(dtype_to_check)} is not a valid DTypeID, nor an equivalent ID or name")

    raise TypeError(f"Expected DTypeID or int or str, but got {dtype_to_check.__class__.__name__}")


regex_name = re.compile("^[a-zA-Z_][a-zA-Z_0-9]*$")  # ToDo: Should HDC-spec allow Unicode in identifiers?


def is_valid_name(name_to_check: str) -> bool:
    if not isinstance(name_to_check, str):
        raise TypeError(f"Expected str, but got {name_to_check.__class__.__name__}")
    return bool(regex_name.fullmatch(name_to_check))


def validate_mandatory_name(name_to_check: str) -> str:
    if not is_valid_name(name_to_check):
        raise ValueError(f"The string '{name_to_check}' is not a valid name")
    return name_to_check


def validate_optional_name(name_to_check: str | None) -> str | None:
    if name_to_check is None:
        return None
    return validate_mandatory_name(name_to_check)


def is_valid_version(version_to_check: semver.VersionInfo | str) -> bool:
    if isinstance(version_to_check, semver.VersionInfo):
        return True

    if isinstance(version_to_check, str):
        return semver.VersionInfo.isvalid(version_to_check)

    raise TypeError(f"Expected VersionInfo or str, but got {version_to_check.__class__.__name__}")


def validate_mandatory_version(version_to_check: semver.VersionInfo | str) -> semver.VersionInfo:
    if isinstance(version_to_check, semver.VersionInfo):
        return version_to_check

    if isinstance(version_to_check, str):
        return semver.VersionInfo.parse(version_to_check)

    raise TypeError(f"Expected VersionInfo or str, but got {version_to_check.__class__.__name__}")


def validate_optional_version(version_to_check: semver.VersionInfo | str | None) -> semver.VersionInfo | None:
    if version_to_check is None:
        return None
    return validate_mandatory_version(version_to_check)
