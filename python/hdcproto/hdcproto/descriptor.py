from __future__ import annotations

import enum
import json
import typing

import semver

from hdcproto.common import (HdcDataType, is_valid_uint8, HdcCmdException, HdcCmdExc_CommandFailed,
                             HdcCmdExc_UnknownFeature, HdcCmdExc_UnknownCommand, HdcCmdExc_InvalidArgs,
                             HdcCmdExc_NotNow, CmdID, HdcCmdExc_UnknownProperty, HdcCmdExc_ReadOnlyProperty, EvtID, PropID)


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
                 arguments: typing.Iterable[ArgD] | None,
                 returns: RetD | typing.Iterable[RetD] | None,
                 raises: typing.Iterable[HdcCmdException | enum.IntEnum] | None,
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

        if raises is None:
            raises = []
        self.raises = dict()
        for exc in raises:
            if isinstance(exc, enum.IntEnum):
                exc = HdcCmdException(exc)
            self._register_exception(exc)
        # Strictly speaking all Commands also bear the potential to raise:
        #    HdcCmdExc_CommandFailed
        #    HdcCmdExc_UnknownFeature
        #    HdcCmdExc_UnknownCommand
        #    HdcCmdExc_InvalidArgs
        #  ... but it's not helpful to include those into every command-descriptor

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
            raises=[HdcCmdExc_UnknownProperty()],
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
            raises=[HdcCmdExc_UnknownProperty(),
                    HdcCmdExc_ReadOnlyProperty()],
            doc=None
        )


class EventDescriptor:
    id: int
    name: str
    arguments: tuple[ArgD, ...] | None
    doc: str

    def __init__(self,
                 id_: int,
                 name: str,
                 arguments: typing.Iterable[ArgD] | None,
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


class LogEventThresholdPropertyDescriptor(PropertyDescriptor):
    def __init__(self):
        super().__init__(
            id_=PropID.LOG_EVT_THRESHOLD,
            name='LogEventThreshold',
            dtype=HdcDataType.UINT8,
            is_readonly=False,
            doc="Suppresses LogEvents with lower log-levels."
        )


class FeatureStatePropertyDescriptor(PropertyDescriptor):
    def __init__(self):
        super().__init__(
            id_=PropID.FEAT_STATE,
            name='FeatureState',
            dtype=HdcDataType.UINT8,
            is_readonly=True,
            doc="Current feature-state"
        )


class FeatureDescriptor:
    id: int
    name: str
    class_name: str
    class_version: str | semver.VersionInfo | None
    doc: str | None
    states: dict[int, StateDescriptor] | None
    commands: dict[int, CommandDescriptor]
    events: dict[int, EventDescriptor]
    properties: dict[int, PropertyDescriptor]

    def __init__(self,
                 id_: int,
                 name: str,
                 class_name: str,
                 class_version: str | semver.VersionInfo | None = None,
                 states: typing.Type[enum.IntEnum] | typing.Iterable[StateDescriptor] | None = None,
                 commands: typing.Iterable[CommandDescriptor] | None = None,
                 events: typing.Iterable[EventDescriptor] | None = None,
                 properties: typing.Iterable[PropertyDescriptor] | None = None,
                 doc: str | None = None):

        if not is_valid_uint8(id_):
            raise ValueError(f"id_ value of 0x{id_:02X} is beyond valid range from 0x00 to 0xFF")
        self.id = id_

        if not name:  # ToDo: Validate name with RegEx
            raise ValueError("name must be a non-empty string")
        self.name = name

        if not class_name:  # ToDo: Validate name with RegEx
            raise ValueError("class_name must be a non-empty string")
        self.class_name = class_name

        if class_version is not None and not isinstance(class_version, semver.VersionInfo):
            class_version = semver.VersionInfo.parse(class_version)
        self.class_version = class_version

        if doc is None:
            doc = ""
        self.doc = doc

        if states is None:
            self.states = None
        else:
            self.states: dict[int, StateDescriptor] = dict()
            for d in states:
                if isinstance(d, enum.IntEnum):
                    d = StateDescriptor(state_id=d, state_name=d.name)
                if d.state_id in self.states.keys():
                    ValueError("states contains duplicate ID values")
                self.states[d.state_id] = d

        # Commands
        self.commands = dict()
        if commands is None:
            commands = []
        for d in commands:
            if d.id in self.commands.keys():
                ValueError("commands contains duplicate ID values")
            self.commands[d.id] = d
        if CmdID.GET_PROP_VALUE not in self.commands.keys():
            self.commands[CmdID.GET_PROP_VALUE] = GetPropertyValueCommandDescriptor()
        if CmdID.SET_PROP_VALUE not in self.commands.keys():
            self.commands[CmdID.SET_PROP_VALUE] = SetPropertyValueCommandDescriptor()

        # Events
        self.events = dict()
        if events is None:
            events = []
        for d in events:
            if d.id in self.events.keys():
                ValueError("events contains duplicate ID values")
            self.events[d.id] = d
        if EvtID.FEATURE_STATE_TRANSITION not in self.events.keys():
            self.events[EvtID.FEATURE_STATE_TRANSITION] = FeatureStateTransitionEventDescriptor()
        if EvtID.LOG not in self.events.keys():
            self.events[EvtID.LOG] = self.evt_log = LogEventDescriptor()

        # Properties
        self.properties = dict()
        if properties is None:
            properties = []
        for d in properties:
            if d.id in self.properties.keys():
                ValueError("properties contains duplicate ID values")
            self.properties[d.id] = d
        if PropID.LOG_EVT_THRESHOLD not in self.properties.keys():
            self.properties[PropID.LOG_EVT_THRESHOLD] = LogEventThresholdPropertyDescriptor()
        if PropID.FEAT_STATE not in self.properties.keys():
            self.properties[PropID.FEAT_STATE] = FeatureStatePropertyDescriptor()

    def __str__(self):
        return f"Feature_0x{self.id}_{self.name}"

    def to_idl_dict(self) -> dict:
        return dict(
            id=self.id,
            name=self.name,
            cls=self.class_name,
            version=str(self.class_version) if self.class_version is not None else None,
            doc=self.doc,
            states=[
                d.to_idl_dict()
                for d in sorted(self.states.values(), key=lambda d: d.state_id)
            ] if self.states is not None else None,
            commands=[
                d.to_idl_dict()
                for d in sorted(self.commands.values(), key=lambda d: d.id)
            ],
            events=[
                d.to_idl_dict()
                for d in sorted(self.events.values(), key=lambda d: d.id)
            ],
            properties=[
                d.to_idl_dict()
                for d in sorted(self.properties.values(), key=lambda d: d.id)
            ])


class DeviceDescriptor:
    version: str
    max_req: int
    features: dict[int, FeatureDescriptor]

    def __init__(self,
                 version: str,
                 max_req: int,
                 features: typing.Iterable[FeatureDescriptor] | None = None):

        self.version = version
        self.max_req = max_req

        # Properties
        self.features = dict()
        if features is None:
            features = []
        for d in features:
            if d.id in self.features.keys():
                ValueError("features contains duplicate ID values")
            self.features[d.id] = d

    def to_idl_dict(self) -> dict:
        return dict(
            version=self.version,
            max_req=self.max_req,
            features=[
                d.to_idl_dict()
                for d in sorted(self.features.values(), key=lambda d: d.id)
            ])

    def to_idl_json(self) -> str:
        idl_dict = self.to_idl_dict()

        def prune_none_values(d: dict[str, typing.Any]) -> int:
            """Removes attribute with a None value.
            Dives recursively into values of type dict and list[dict]"""
            keys_of_none_items = [key for key, value in d.items() if value is None]
            num_deleted_items = len(keys_of_none_items)
            for k in keys_of_none_items:
                del (d[k])
            for key, value in d.items():
                if isinstance(value, dict):
                    num_deleted_items += prune_none_values(value)
                elif isinstance(value, list):
                    for list_item in value:
                        if isinstance(list_item, dict):
                            num_deleted_items += prune_none_values(list_item)

            return num_deleted_items

        prune_none_values(idl_dict)
        return json.dumps(idl_dict)
