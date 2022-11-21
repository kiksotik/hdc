"""
Host-side API (a.k.a. "proxy classes") to communicate with any device that implements the Demo_Minimal example.

Device can be::
    - A NUCLEO prototype board running any of the Demo_Minimal STM32 firmware examples.
    - A Python process running the minimal_device.py example.
"""
from __future__ import annotations

import enum
from datetime import datetime

from hdcproto.common import HdcDataType, HdcCmdException
from hdcproto.host.proxy import (DeviceProxyBase, CoreFeatureProxyBase, EventProxyBase,
                                 PropertyProxy_RO_UINT32, PropertyProxy_RO_BLOB, PropertyProxy_RW_UINT8,
                                 CommandProxyBase, FeatureProxyBase, VoidWithoutArgsCommandProxy)


class MinimalCore(CoreFeatureProxyBase):

    def __init__(self, device_proxy: DeviceProxyBase):
        super().__init__(
            device_proxy,
            # Registration of states allows DeviceProxyBase to resolve names and produce more readable logs
            states=MinimalCore.FeatureStateEnum)

        # Commands
        self.cmd_reset = VoidWithoutArgsCommandProxy(self, command_id=0x01)  # A simple command with void signature
        self.cmd_division = self.DivisionCommandProxy(self)  # Command with custom signature

        # Events
        self.evt_button = EventProxyBase(self, event_id=0x01, payload_parser=self.ButtonEventPayload)

        # Properties
        self.prop_microcontroller_devid = PropertyProxy_RO_UINT32(self, property_id=0x010)
        self.prop_microcontroller_uid = PropertyProxy_RO_BLOB(self, property_id=0x11)
        self.prop_led_blinking_rate = PropertyProxy_RW_UINT8(self, property_id=0x12)

    class FeatureStateEnum(enum.IntEnum):
        """Custom states of the Core-feature of the Demo_Minimal firmware."""
        OFF = 0
        INITIALIZING = 1
        READY = 2
        ERROR = 0xFF

    class DivisionCommandProxy(CommandProxyBase):
        def __init__(self, feature_proxy: FeatureProxyBase):
            super().__init__(feature_proxy,
                             command_id=0x02,
                             raises_also=[MyDivZeroError()])

        def __call__(self,
                     numerator: float,
                     denominator: float,
                     timeout: float | None = None) -> float:
            return super()._call_cmd(
                cmd_args=[(HdcDataType.FLOAT, float(numerator)),
                          (HdcDataType.FLOAT, float(denominator))],
                return_types=HdcDataType.DOUBLE,
                timeout=timeout)

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
            self.button_id, self.button_state = HdcDataType.parse_event_msg(
                event_message=event_message,
                expected_data_types=[HdcDataType.UINT8, HdcDataType.UINT8]
            )


class MyDivZeroError(HdcCmdException):
    def __init__(self,
                 exception_message: str | None = None):
        super().__init__(exception_id=0x01,
                         exception_name="MyDivZero",
                         exception_message=exception_message)


class MinimalDevice(DeviceProxyBase):
    core: MinimalCore

    def __init__(self, connection_url: str):
        super().__init__(connection_url=connection_url)
        self.core = MinimalCore(self)  # This device only has a Core feature.
