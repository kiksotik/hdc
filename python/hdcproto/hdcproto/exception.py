from __future__ import annotations

import enum
import typing

from hdcproto.spec import ExcID, DTypeID
from hdcproto.validate import is_valid_uint8


class HdcError(Exception):
    """Base-class of all exceptions that the HDC package may raise."""
    exception_message: str | None

    def __init__(self, exception_message: str | None = None):
        self.exception_message = exception_message


class HdcDataTypeError(HdcError):
    pass


def prune_none_values(d: typing.MutableMapping[str, typing.Any]) -> None:
    """Removes elements with a None value"""
    keys_of_none_items = [key for key, value in d.items() if value is None]
    for k in keys_of_none_items:
        del (d[k])


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
        Uses this instance as a "descriptor" that serves as a template to create a new instance, which is then
        initialized further with information extracted from the given HDC-exception-message.
        Verifies that the given message matches the expected exception-ID.

        Override this implementation in any subclass that may need to parse custom data from the given message.
        """
        from hdcproto.parse import parse_payload  # Postponed import to avoid circular dependency

        (exc_id,
         exc_text) = parse_payload(raw_payload=hdc_message[3:],  # Strip 3 leading bytes: MsgID + FeatureID + CmdID
                                   expected_data_types=[DTypeID.UINT8,  # Forth byte is ExcID
                                                        DTypeID.UTF8])  # Remainder is Exception text and may be empty
        if exc_id != self.exception_id:
            raise ValueError(f"Mismatching Exception-ID in HDC reply message. "
                             f"Expected 0x{self.exception_id:02X}, but received 0x{exc_id:02X}")

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
        result = dict(
            id=self.exception_id,
            name=self.exception_name,
            doc=self.exception_doc  # This is a crazy experiment.
        )
        prune_none_values(result)
        return result

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
