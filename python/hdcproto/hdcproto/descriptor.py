from __future__ import annotations

import enum
import typing

from hdcproto.common import (HdcDataType, is_valid_uint8, HdcCmdException, HdcCmdExc_CommandFailed,
                             HdcCmdExc_UnknownFeature, HdcCmdExc_UnknownCommand, HdcCmdExc_InvalidArgs,
                             HdcCmdExc_NotNow, CmdID, HdcCmdExc_UnknownProperty, HdcCmdExc_RoProperty, EvtID)


class ArgD:
    """
    Argument descriptor

    As used to describe the arguments that an HDC-Command takes or that an HDC-Event carries.
    """
    dtype: HdcDataType
    name: str
    doc: str | None

    def __init__(self,
                 dtype: HdcDataType,
                 name: str,
                 doc: str | None = None):

        if not isinstance(dtype, HdcDataType):
            raise ValueError
        self.dtype = dtype

        if not name:
            raise ValueError("Argument name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        self.doc = doc

    def to_idl_dict(self) -> dict:
        return dict(
            dtype=self.dtype.name,
            name=self.name,
            doc=self.doc
        )


class RetD:
    """
    Return-Value descriptor

    Describes the value(s) that an HDC-Command returns.
    """
    dtype: HdcDataType
    name: str | None
    doc: str | None

    def __init__(self,
                 dtype: HdcDataType,
                 name: str | None = None,
                 doc: str | None = None):

        if not isinstance(dtype, HdcDataType):
            raise ValueError
        self.dtype = dtype

        if name is not None and len(name) < 1:
            raise ValueError("Return Value name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        self.doc = doc

    def to_idl_dict(self) -> dict:
        return dict(
            dtype=self.dtype.name,
            name=self.name,
            doc=self.doc
        )


class StateDescriptor:
    state_id: int
    state_name: str
    state_doc: str | None

    def __init__(self,
                 state_id: int,
                 state_name: str,
                 state_doc: str | None = None):

        if not is_valid_uint8(state_id):
            raise ValueError(f"state_id value of {state_id} is beyond valid range from 0x00 to 0xFF")

        self.state_id = state_id

        if not state_name:
            raise ValueError("State name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.state_name = state_name

        self.state_doc = state_doc

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.state_id,
            name=self.state_name,
            doc=self.state_doc
        )


class CommandDescriptor:
    id: int
    name: str
    arguments: tuple[ArgD, ...]  # ToDo: Attribute optionality. #25
    returns: tuple[RetD, ...]  # ToDo: Attribute optionality. #25
    raises: dict[int, HdcCmdException]  # Not optional, because of mandatory exceptions
    doc: str | None

    def __init__(self,
                 id_: int,
                 name: str,
                 arguments: typing.Iterable[ArgD, ...] | None,
                 returns: RetD | typing.Iterable[RetD, ...] | None,
                 raises_also: typing.Iterable[HdcCmdException | enum.IntEnum] | None,
                 doc: str | None):

        if not is_valid_uint8(id_):
            raise ValueError(f"id value of {id_} is beyond valid range from 0x00 to 0xFF")
        self.id = id_

        if not name:  # ToDo: Validate name with RegEx
            raise ValueError("name must be a non-empty string")
        self.name = name

        if not arguments:
            # ToDo: Attribute optionality. #25
            # Harmonize it into an empty tuple to simplify remainder of this implementation
            self.arguments = tuple()
        else:
            if any(not isinstance(arg, ArgD) for arg in arguments):
                raise TypeError("command_arguments must be an iterable of ArgD objects")

            if any(arg.dtype.is_variable_size() for arg in arguments[:-1]):
                raise ValueError("Only last argument may be of a variable-size data-type")

            self.arguments = tuple(arguments)

        if not returns:
            # ToDo: Attribute optionality. #25
            # Harmonize it into a tuple to simplify remainder of this implementation
            self.returns = tuple()
        elif isinstance(returns, RetD):
            # Meaning it returns a single value.
            # Harmonize it into a tuple to simplify remainder of this implementation
            self.returns = tuple([returns])
        else:
            if any(not isinstance(ret, RetD) for ret in returns):
                raise TypeError("command_returns must be an iterable of RetD objects")

            if any(ret.dtype.is_variable_size() for ret in returns[:-1]):
                raise ValueError("Only last return value may be of a variable-size data-type")

            self.returns = tuple(returns)

        raised_by_all_commands = [
            HdcCmdExc_CommandFailed(),
            HdcCmdExc_UnknownFeature(),  # Technically raised by the router, but proxy doesn't care
            HdcCmdExc_UnknownCommand(),  # Technically raised by the router, but proxy doesn't care
            HdcCmdExc_InvalidArgs(),
            HdcCmdExc_NotNow(), ]

        if raises_also is None:
            raises_also = []
        self.raises = dict()
        for exc in raised_by_all_commands + raises_also:
            if isinstance(exc, enum.IntEnum):
                exc = HdcCmdException(exc)
            self._register_exception(exc)

        if doc is None:  # ToDo: Attribute optionality. #25
            doc = ""
        description_already_contains_command_signature = doc.startswith('(')
        if not description_already_contains_command_signature:
            cmd_signature = "("
            if not self.arguments:
                cmd_signature += "VOID"
            else:
                cmd_signature += ', '.join(f"{arg.dtype.name} {arg.name}"
                                           for arg in self.arguments)
            cmd_signature += ") -> "

            if len(self.returns) == 0:
                cmd_signature += "VOID"
            elif len(self.returns) == 1:
                cmd_signature += f"{self.returns[0].dtype.name}"
                if self.returns[0].name:
                    cmd_signature += f" {self.returns[0].name}"
            else:
                cmd_signature += "("
                cmd_signature += ', '.join(f"{ret.dtype.name}{f' ret.name' if ret.name else ''}"
                                           for ret in self.returns)
                cmd_signature += ")"
            if doc:
                doc = cmd_signature + '\n' + doc
            else:
                doc = cmd_signature

        self.doc = doc

    def _register_exception(self, exception: HdcCmdException) -> None:
        if exception.exception_id in self.raises:
            raise ValueError(f'Already registered Exception.id=0x{exception.exception_id:02X} '
                             f'as "{self.raises[exception.exception_id]}"')
        self.raises[exception.exception_id] = exception

    def __str__(self):
        return f"Command_0x{self.id}_{self.name}"

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.id,
            name=self.name,
            doc=self.doc,
            args=[arg.to_idl_dict()
                  for arg in self.arguments
                  ] if self.arguments is not None else None,
            returns=[ret.to_idl_dict()
                     for ret in self.returns
                     ] if self.returns is not None else None,
            raises=[exc.to_idl_dict()
                    for exc in sorted(self.raises.values(), key=lambda d: d.exception_id)
                    ] if self.raises is not None else None
        )


class GetPropertyValueCommandDescriptor(CommandDescriptor):
    def __init__(self):
        super().__init__(
            id_=CmdID.GET_PROP_VALUE,
            name="GetPropertyValue",
            arguments=[ArgD(HdcDataType.UINT8, name="PropertyID")],
            # Returns 'BLOB', because data-type depends on requested property
            returns=[RetD(HdcDataType.BLOB, doc="Actual data-type depends on property")],
            raises_also=[HdcCmdExc_UnknownProperty()],
            doc=None
        )


class SetPropertyValueCommandDescriptor(CommandDescriptor):
    def __init__(self):
        super().__init__(
            id_=CmdID.SET_PROP_VALUE,
            name="SetPropertyValue",
            # Signature uses 'BLOB', because data-type depends on requested property
            arguments=[ArgD(HdcDataType.UINT8, "PropertyID"),
                       ArgD(HdcDataType.BLOB, "NewValue", "Actual data-type depends on property")],
            returns=[RetD(HdcDataType.BLOB, "ActualNewValue", "May differ from NewValue!")],
            raises_also=[HdcCmdExc_UnknownProperty(),
                         HdcCmdExc_RoProperty()],
            doc="Returned value might differ from NewValue argument, "
                "i.e. because of trimming to valid range or discretization."
        )


class EventDescriptor:
    id: int
    name: str
    arguments: tuple[ArgD, ...] | None
    doc: str

    def __init__(self,
                 id_: int,
                 name: str,
                 arguments: typing.Iterable[ArgD, ...] | None,
                 doc: str | None):

        if not is_valid_uint8(id_):
            raise ValueError(f"id_ value of {id_} is beyond valid range from 0x00 to 0xFF")

        self.id = id_

        if not name:
            raise ValueError("Event name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        if arguments is None:
            # ToDo: Attribute optionality. #25
            arguments = None
        else:
            arguments = tuple(arguments)
            if any(arg.dtype.is_variable_size() for arg in arguments[:-1]):
                raise ValueError("Only last argument may be of a variable-size data-type")
        self.arguments = arguments

        if doc is None:
            # ToDo: Attribute optionality. #25
            doc = ""
        description_already_contains_signature = doc.startswith('(')
        if not description_already_contains_signature:
            evt_signature = "("
            evt_signature += ', '.join(f"{arg.dtype.name} {arg.name}" for arg in self.arguments)
            evt_signature += ")"
            if doc:
                doc = evt_signature + '\n' + doc
            else:
                doc = evt_signature
        self.doc = doc

    def __str__(self):
        return f"Event_0x{self.id}_{self.name}"

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.id,
            name=self.name,
            doc=self.doc,
            args=[arg.to_idl_dict()
                  for arg in self.arguments])


class LogEventDescriptor(EventDescriptor):
    def __init__(self):
        super().__init__(id_=EvtID.LOG,
                         name="Log",
                         arguments=[ArgD(HdcDataType.UINT8, 'LogLevel', doc="Same as in Python"),
                                    ArgD(HdcDataType.UTF8, 'LogMsg')],
                         doc="Forwards software event log to the host.")


class FeatureStateTransitionEventDescriptor(EventDescriptor):
    def __init__(self):
        super().__init__(id_=EvtID.FEATURE_STATE_TRANSITION,
                         name="FeatureStateTransition",
                         arguments=(ArgD(HdcDataType.UINT8, 'PreviousStateID'),
                                    ArgD(HdcDataType.UINT8, 'CurrentStateID')),
                         doc="Notifies host about transitions of this feature's state-machine."
                         )


class PropertyDescriptor:
    id: int
    name: str
    dtype: HdcDataType
    is_readonly: bool
    doc: str | None

    def __init__(self,
                 id_: int,
                 name: str,
                 dtype: HdcDataType,
                 is_readonly: bool,
                 doc: str | None = None):

        if not is_valid_uint8(id_):
            raise ValueError(f"id_ value of {id_} is beyond valid range from 0x00 to 0xFF")
        self.id = int(id_)

        if not name:  # ToDo: Validate name with RegEx
            raise ValueError("name must be a non-empty string")
        self.name = str(name)

        if not isinstance(dtype, HdcDataType):
            raise ValueError("dtype must be specified as HdcDataType")
        self.dtype = dtype

        self.is_readonly = bool(is_readonly)
        self.doc = None if doc is None else str(doc)

    def __str__(self):
        return f"Property_0x{self.id}_{self.name}"

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.id,
            name=self.name,
            dtype=self.dtype.name,
            # ToDo: ValueSize attribute, as in STM32 implementation
            ro=self.is_readonly,
            doc=self.doc)
