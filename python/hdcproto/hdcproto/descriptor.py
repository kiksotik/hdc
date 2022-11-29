from __future__ import annotations

import enum
import json
import logging
import typing

import semver

from hdcproto.exception import HdcCmdException, HdcCmdExc_UnknownProperty, HdcCmdExc_ReadOnlyProperty
from hdcproto.parse import is_variable_size_dtype
from hdcproto.spec import (CmdID, EvtID, PropID, DTypeID)
from hdcproto.validate import validate_uint8

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.descriptor"


def prune_none_values(d: typing.MutableMapping[str, typing.Any]) -> None:
    """Removes elements with a None value"""
    keys_of_none_items = [key for key, value in d.items() if value is None]
    for k in keys_of_none_items:
        del (d[k])


class ArgD:
    """
    Argument descriptor

    As used to describe the arguments that an HDC-Command takes or that an HDC-Event carries.
    """
    dtype: DTypeID
    name: str
    doc: str | None

    def __init__(self,
                 dtype: DTypeID,
                 name: str,
                 doc: str | None = None):

        if not isinstance(dtype, DTypeID):
            raise ValueError
        self.dtype = dtype

        if not name:
            raise ValueError("Argument name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        self.doc = doc

    def to_idl_dict(self) -> dict:
        result = dict(
            dtype=self.dtype.name,
            name=self.name,
            doc=self.doc
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> ArgD:
        kwargs = dict(
            dtype=DTypeID[d['dtype']],  # Convert DType name into IntEnum value!
            name=d['name'],
            doc=d.get('doc')  # Optional
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys())
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)


class RetD:
    """
    Return-Value descriptor

    Describes the value(s) that an HDC-Command returns.
    """
    dtype: DTypeID
    name: str | None
    doc: str | None

    def __init__(self,
                 dtype: DTypeID,
                 name: str | None = None,
                 doc: str | None = None):

        if not isinstance(dtype, DTypeID):
            raise ValueError
        self.dtype = dtype

        if name is not None and len(name) < 1:
            raise ValueError("Return Value name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        self.doc = doc

    def to_idl_dict(self) -> dict:
        result = dict(
            dtype=self.dtype.name,
            name=self.name,
            doc=self.doc
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> RetD:
        kwargs = dict(
            dtype=DTypeID[d['dtype']],  # Convert DType name into IntEnum value!
            name=d.get('name'),  # Optional
            doc=d.get('doc')  # Optional
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys())
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)


class StateDescriptor:
    id: int
    name: str
    doc: str | None

    # noinspection PyShadowingBuiltins
    def __init__(self,
                 id: int,
                 name: str,
                 doc: str | None = None):

        self.id = validate_uint8(id)

        if not name:
            raise ValueError("name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        self.doc = doc

    def to_idl_dict(self) -> dict:
        result = dict(
            id=self.id,
            name=self.name,
            doc=self.doc
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> StateDescriptor:
        kwargs = dict(
            id=d['id'],
            name=d['name'],
            doc=d.get('doc')  # Optional
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys())
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)


class CommandDescriptor:
    id: int
    name: str
    args: tuple[ArgD, ...]  # ToDo: Attribute optionality. #25
    returns: tuple[RetD, ...]  # ToDo: Attribute optionality. #25
    raises: dict[int, HdcCmdException]  # Not optional, because of mandatory exceptions
    doc: str | None

    # noinspection PyShadowingBuiltins
    def __init__(self,
                 id: int,
                 name: str,
                 args: typing.Iterable[ArgD] | None,
                 returns: RetD | typing.Iterable[RetD] | None,
                 raises: typing.Iterable[HdcCmdException | enum.IntEnum] | None,
                 doc: str | None = None):

        self.id = validate_uint8(id)

        if not name:  # ToDo: Validate name with RegEx
            raise ValueError("name must be a non-empty string")
        self.name = name

        if not args:
            # ToDo: Attribute optionality. #25
            # Harmonize it into an empty tuple to simplify remainder of this implementation
            self.args = tuple()
        else:
            if any(not isinstance(arg, ArgD) for arg in args):
                raise TypeError("command_arguments must be an iterable of ArgD objects")

            if any(is_variable_size_dtype(arg.dtype) for arg in args[:-1]):
                raise ValueError("Only last argument may be of a variable-size data-type")

            self.args = tuple(args)

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

            if any(is_variable_size_dtype(ret.dtype) for ret in returns[:-1]):
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
        return f"Command_0x{self.id:02X}_{self.name}"

    def to_idl_dict(self) -> dict:
        result = dict(
            id=self.id,
            name=self.name,
            doc=self.doc,
            args=[arg.to_idl_dict()
                  for arg in self.args
                  ] if self.args is not None else None,
            returns=[ret.to_idl_dict()
                     for ret in self.returns
                     ] if self.returns is not None else None,
            raises=[exc.to_idl_dict()
                    for exc in sorted(self.raises.values(), key=lambda d: d.exception_id)
                    ] if self.raises is not None else None
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> CommandDescriptor:
        kwargs = dict(
            id=d['id'],
            name=d['name'],
            args=[ArgD.from_idl_dict(arg)
                  for arg in d['args']] if 'args' in d.keys() else None,
            returns=[RetD.from_idl_dict(ret)
                     for ret in d['returns']] if 'returns' in d.keys() else None,
            raises=[HdcCmdException.from_idl_dict(exc)
                    for exc in d['raises']] if 'raises' in d.keys() else None,
            doc=d.get('doc')
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys())
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)


class GetPropertyValueCommandDescriptor(CommandDescriptor):
    def __init__(self):
        super().__init__(
            id=CmdID.GET_PROP_VALUE,
            name="get_property_value",
            args=[ArgD(DTypeID.UINT8, name="property_id")],
            # Returns 'BLOB', because data-type depends on requested property
            returns=[RetD(DTypeID.BLOB, doc="Actual data-type depends on property")],
            raises=[HdcCmdExc_UnknownProperty()],
            doc=None
        )


class SetPropertyValueCommandDescriptor(CommandDescriptor):
    def __init__(self):
        super().__init__(
            id=CmdID.SET_PROP_VALUE,
            name="set_property_value",
            # Signature uses 'BLOB', because data-type depends on requested property
            args=[ArgD(DTypeID.UINT8, "property_id"),
                  ArgD(DTypeID.BLOB, "new_value", "Actual data-type depends on property")],
            returns=[RetD(DTypeID.BLOB, "actual_new_value", "May differ from NewValue!")],
            raises=[HdcCmdExc_UnknownProperty(),
                    HdcCmdExc_ReadOnlyProperty()],
            doc=None
        )


class EventDescriptor:
    id: int
    name: str
    args: tuple[ArgD, ...] | None
    doc: str

    # noinspection PyShadowingBuiltins
    def __init__(self,
                 id: int,
                 name: str,
                 args: typing.Iterable[ArgD] | None,
                 doc: str | None):

        self.id = validate_uint8(id)

        if not name:
            raise ValueError("Event name must be a non-empty string")  # ToDo: Validate name with RegEx
        self.name = name

        if args is None:
            # ToDo: Attribute optionality. #25
            args = None
        else:
            args = tuple(args)
            if any(is_variable_size_dtype(arg.dtype) for arg in args[:-1]):
                raise ValueError("Only last argument may be of a variable-size data-type")
        self.args = args

        self.doc = doc

    def __str__(self):
        return f"Event_0x{self.id:02X}_{self.name}"

    def to_idl_dict(self) -> dict:
        result = dict(
            id=self.id,
            name=self.name,
            doc=self.doc,
            args=[arg.to_idl_dict()
                  for arg in self.args] if self.args is not None else None,
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> EventDescriptor:
        kwargs = dict(
            id=d['id'],
            name=d['name'],
            args=[ArgD.from_idl_dict(arg)
                  for arg in d['args']] if 'args' in d.keys() else None,
            doc=d.get('doc')
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys())
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)


class LogEventDescriptor(EventDescriptor):
    def __init__(self):
        super().__init__(id=EvtID.LOG,
                         name="log",
                         args=[ArgD(DTypeID.UINT8, 'log_level', doc="Same as in Python"),
                               ArgD(DTypeID.UTF8, 'log_msg')],
                         doc="Forwards software event log to the host.")


class FeatureStateTransitionEventDescriptor(EventDescriptor):
    def __init__(self):
        super().__init__(id=EvtID.FEATURE_STATE_TRANSITION,
                         name="feature_state_transition",
                         args=(ArgD(DTypeID.UINT8, 'previous_state_id'),
                               ArgD(DTypeID.UINT8, 'current_state_id')),
                         doc="Notifies host about transitions of this feature's state-machine."
                         )


class PropertyDescriptor:
    id: int
    name: str
    dtype: DTypeID
    is_readonly: bool
    doc: str | None

    # noinspection PyShadowingBuiltins
    def __init__(self,
                 id: int,
                 name: str,
                 dtype: DTypeID,
                 is_readonly: bool,
                 doc: str | None = None):

        self.id = validate_uint8(id)

        if not name:  # ToDo: Validate name with RegEx
            raise ValueError("name must be a non-empty string")
        self.name = str(name)

        if not isinstance(dtype, DTypeID):
            raise ValueError("dtype must be specified as DTypeID")
        self.dtype = dtype

        self.is_readonly = bool(is_readonly)
        self.doc = None if doc is None else str(doc)

    def __str__(self):
        return f"Property_0x{self.id:02X}_{self.name}"

    def to_idl_dict(self) -> dict:
        result = dict(
            id=self.id,
            name=self.name,
            dtype=self.dtype.name,
            # ToDo: ValueSize attribute, as in STM32 implementation
            ro=self.is_readonly,
            doc=self.doc
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> PropertyDescriptor:
        kwargs = dict(
            id=d['id'],
            name=d['name'],
            dtype=DTypeID[d['dtype']],
            is_readonly=d['ro'],  # Different attribute name!
            doc=d.get('doc')
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys()) - {'ro'}
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)


class LogEventThresholdPropertyDescriptor(PropertyDescriptor):
    def __init__(self):
        super().__init__(
            id=PropID.LOG_EVT_THRESHOLD,
            name='log_event_threshold',
            dtype=DTypeID.UINT8,
            is_readonly=False,
            doc="Suppresses LogEvents with lower log-levels."
        )


class FeatureStatePropertyDescriptor(PropertyDescriptor):
    def __init__(self):
        super().__init__(
            id=PropID.FEAT_STATE,
            name='feature_state',
            dtype=DTypeID.UINT8,
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

    # noinspection PyShadowingBuiltins
    def __init__(self,
                 id: int,
                 name: str,
                 cls: str,
                 version: str | semver.VersionInfo | None = None,
                 states: typing.Type[enum.IntEnum] | typing.Iterable[StateDescriptor] | None = None,
                 commands: typing.Iterable[CommandDescriptor] | None = None,
                 events: typing.Iterable[EventDescriptor] | None = None,
                 properties: typing.Iterable[PropertyDescriptor] | None = None,
                 doc: str | None = None):

        self.id = validate_uint8(id)

        if not name:  # ToDo: Validate name with RegEx
            raise ValueError("name must be a non-empty string")
        self.name = name

        if not cls:  # ToDo: Validate name with RegEx
            raise ValueError("cls must be a non-empty string")
        self.class_name = cls

        if version is not None and not isinstance(version, semver.VersionInfo):
            version = semver.VersionInfo.parse(version)
        self.class_version = version

        if doc is None:
            doc = ""
        self.doc = doc

        if states is None:
            self.states = None
        else:
            self.states: dict[int, StateDescriptor] = dict()
            for d in states:
                if isinstance(d, enum.IntEnum):
                    d = StateDescriptor(id=d, name=d.name)
                if d.id in self.states.keys():
                    ValueError("states contains duplicate ID values")
                self.states[d.id] = d

        # Commands
        self.commands = dict()
        if commands is None:
            commands = []
        for d in commands:
            if d.id in self.commands.keys():
                ValueError("commands contains duplicate ID values")
            self.commands[d.id] = d

        # Events
        self.events = dict()
        if events is None:
            events = []
        for d in events:
            if d.id in self.events.keys():
                ValueError("events contains duplicate ID values")
            self.events[d.id] = d

        # Properties
        self.properties = dict()
        if properties is None:
            properties = []
        for d in properties:
            if d.id in self.properties.keys():
                ValueError("properties contains duplicate ID values")
            self.properties[d.id] = d

    def __str__(self):
        return f"Feature_0x{self.id:02X}_{self.name}"

    def to_idl_dict(self) -> dict:
        result = dict(
            id=self.id,
            name=self.name,
            cls=self.class_name,
            version=str(self.class_version) if self.class_version is not None else None,
            doc=self.doc,
            states=[
                d.to_idl_dict()
                for d in sorted(self.states.values(), key=lambda d: d.id)
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
            ]
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> FeatureDescriptor:
        kwargs = dict(
            id=d['id'],
            name=d['name'],
            cls=d['cls'],
            version=d['version'],
            states=[StateDescriptor.from_idl_dict(state)
                    for state in d['states']] if 'states' in d.keys() else None,
            commands=[CommandDescriptor.from_idl_dict(cmd)
                      for cmd in d['commands']] if 'commands' in d.keys() else None,
            events=[EventDescriptor.from_idl_dict(evt)
                    for evt in d['events']] if 'events' in d.keys() else None,
            properties=[PropertyDescriptor.from_idl_dict(prop)
                        for prop in d['properties']] if 'properties' in d.keys() else None,
            doc=d.get('doc')
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys())
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)


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
        result = dict(
            version=self.version,
            max_req=self.max_req,
            features=[d.to_idl_dict()
                      for d in sorted(self.features.values(), key=lambda d: d.id)]
        )
        prune_none_values(result)
        return result

    @classmethod
    def from_idl_dict(cls, d: typing.Mapping[str, typing.Any]) -> DeviceDescriptor:
        kwargs = dict(
            version=d['version'],
            max_req=d['max_req'],
            features=[FeatureDescriptor.from_idl_dict(state)
                      for state in d['features']] if 'features' in d.keys() else None
        )
        unexpected_keys = set(d.keys()) - set(kwargs.keys())
        if unexpected_keys:
            logger.warning(f"Ignoring unexpected {cls.__name__} attributes: {repr(unexpected_keys)}")
        return cls(**kwargs)

    def to_idl_json(self) -> str:
        idl_dict = self.to_idl_dict()
        return json.dumps(idl_dict)

    @classmethod
    def from_idl_json(cls, idl_json) -> DeviceDescriptor:
        idl_dict = json.loads(idl_json)
        return cls.from_idl_dict(idl_dict)
