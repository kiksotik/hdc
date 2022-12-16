"""
Host-side API (a.k.a. "proxy classes") to communicate with any device that implements the Demo_Minimal example.

This is the now obsolete way of building a custom proxy class.
Please use the "proxy factory" & "descriptor-driven" approach, instead.

Device can be::
    - A NUCLEO prototype board running any of the Demo_Minimal STM32 firmware examples.
    - A Python process running the minimal_device.py example.
"""
from __future__ import annotations

import enum
from datetime import datetime

from hdcproto.descriptor import FeatureDescriptor, CommandDescriptor, ArgD, RetD, EventDescriptor, PropertyDescriptor
from hdcproto.exception import HdcCmdException
from hdcproto.host.proxy import (DeviceProxyBase, EventProxyBase,
                                 PropertyProxy_RO_UINT32, PropertyProxy_RO_BLOB, PropertyProxy_RW_UINT8,
                                 CommandProxyBase, FeatureProxyBase)
from hdcproto.parse import parse_event_payload
from hdcproto.spec import FeatureID, DTypeID
from hdcproto.transport.base import TransportBase


class MinimalCore(FeatureProxyBase):

    def __init__(self, device_proxy: DeviceProxyBase):
        super().__init__(
            feature_descriptor=FeatureDescriptor(
                id=FeatureID.CORE,
                name="core",
                cls="DontCare",  # ToDo: Attribute optionality. #25
                # Registration of states allows proxy to resolve names and produce more readable logs
                states=MinimalCore.FeatureStateEnum
            ),
            device_proxy=device_proxy)

        ###########
        # Commands

        # A simple command with void signature
        self.cmd_reset = CommandProxyBase(
            command_descriptor=CommandDescriptor(
                id=0x01,
                name="DontCare",  # ToDo: Attribute optionality. #25
                args=[],
                returns=[],
                raises=None  # ToDo: Attribute optionality. #25
            ),
            feature_proxy=self,
            default_timeout=2.0)

        # A custom command proxy class can expose a proper call signature (and encapsulate the descriptor)
        self.cmd_division = self.DivisionCommandProxy(self)  # Command with custom signature

        #########
        # Events
        self.evt_button = EventProxyBase(
            event_descriptor=EventDescriptor(id=0x01,
                                             name="DontCare",  # ToDo: Attribute optionality. #25),
                                             args=None,
                                             doc=None),
            feature_proxy=self,
            payload_parser=self.ButtonEventPayload)

        # Properties
        self.prop_uc_devid = PropertyProxy_RO_UINT32(
            property_descriptor=PropertyDescriptor(
                id=0x010,
                name="DontCare",  # ToDo: Attribute optionality. #25),
                # ToDo: The following is redundant!
                dtype=DTypeID.UINT32,
                is_readonly=True),
            feature_proxy=self)

        self.prop_uc_uid = PropertyProxy_RO_BLOB(
            property_descriptor=PropertyDescriptor(
                id=0x011,
                name="DontCare",  # ToDo: Attribute optionality. #25),
                # ToDo: The following is redundant!
                dtype=DTypeID.BLOB,
                is_readonly=True),
            feature_proxy=self)

        self.prop_led_blinking_rate = PropertyProxy_RW_UINT8(
            property_descriptor=PropertyDescriptor(
                id=0x012,
                name="DontCare",  # ToDo: Attribute optionality. #25),
                # ToDo: The following is redundant!
                dtype=DTypeID.UINT8,
                is_readonly=False),
            feature_proxy=self)

    class FeatureStateEnum(enum.IntEnum):
        """Custom states of the Core-feature of the Demo_Minimal firmware."""
        OFF = 0
        INITIALIZING = 1
        READY = 2
        ERROR = 0xFF

    class DivisionCommandProxy(CommandProxyBase):
        """
        A custom command proxy class can:
          - expose a proper call signature with named arguments and type hints
          - Apply custom validation on arguments and return value
          - Encapsulate the bloated descriptor
        """

        def __init__(self, feature_proxy: FeatureProxyBase):
            super().__init__(
                command_descriptor=CommandDescriptor(id=0x02,
                                                     name="DontCare",  # ToDo: Attribute optionality. #25
                                                     args=[ArgD(DTypeID.FLOAT, "numerator"),
                                                           ArgD(DTypeID.FLOAT, "denominator")],
                                                     returns=[RetD(DTypeID.DOUBLE)],
                                                     # Let proxy raise custom exception class
                                                     raises=[MyDivZeroError()]),
                feature_proxy=feature_proxy)

        def __call__(self,
                     numerator: float,
                     denominator: float) -> float:
            # Call the baseclass __call__ implementation
            return super().__call__(float(numerator), float(denominator))

    class ButtonEventPayload:
        """Used by the self.evt_button proxy to parse raw event messages into custom event payload objects."""

        def __init__(self, event_message: bytes):
            """Warning: This will be executed from within the SerialTransport.receiver_thread"""
            # Timestamp that might be handy when processing this event in a delayed manner
            self.received_at = datetime.utcnow()

            # In simple cases like this and knowing some internals of the HDC-spec, it might be better to do this:
            #     self.button_id = event_message[3]
            #     self.button_state = event_message[4]

            # Otherwise, it might be better to do this:
            self.button_id, self.button_state = parse_event_payload(
                event_message=event_message,
                expected_data_types=[DTypeID.UINT8, DTypeID.UINT8]
            )


class MyDivZeroError(HdcCmdException):
    def __init__(self,
                 exception_message: str | None = None):
        super().__init__(id=0x01,
                         name="MyDivZero",
                         exception_message=exception_message)


class MinimalDevice(DeviceProxyBase):
    core: MinimalCore

    def __init__(self, transport: TransportBase | str | None = None):
        super().__init__(transport=transport)
        self.core = MinimalCore(self)  # This device only has a Core feature.
