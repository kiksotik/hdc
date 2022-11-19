from __future__ import annotations

from hdcproto.common import HdcDataType, is_valid_uint8


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
