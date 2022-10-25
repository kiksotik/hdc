"""
Proxy classes to communicate with i.e. a NUCLEO prototype board running any of the Demo_Minimal STM32 firmware examples.
"""
import enum
from datetime import datetime

from hdcproto.common import HdcDataType
from hdcproto.host.proxy import (DeviceProxyBase, CoreFeatureProxyBase, VoidWithoutArgsCommandProxy, EventProxyBase,
                                 PropertyProxy_RO_UINT32, PropertyProxy_RO_BLOB, PropertyProxy_RW_UINT8)


class MinimalCore(CoreFeatureProxyBase):

    def __init__(self, device_proxy: DeviceProxyBase):
        super().__init__(device_proxy=device_proxy)

        # Commands
        self.cmd_reset = VoidWithoutArgsCommandProxy(self, command_id=0xC1, default_timeout=1.23)

        # Events
        self.evt_button = EventProxyBase(self, event_id=0x01, payload_parser=self.ButtonEventPayload)

        # Properties
        self.prop_microcontroller_devid = PropertyProxy_RO_UINT32(self, property_id=0x010)
        self.prop_microcontroller_revid = PropertyProxy_RO_UINT32(self, property_id=0x11)
        self.prop_microcontroller_uid = PropertyProxy_RO_BLOB(self, property_id=0x12)
        self.prop_led_blinking_rate = PropertyProxy_RW_UINT8(self, property_id=0x13)

    class FeatureStateEnum(enum.IntEnum):
        """Used by FeatureProxyBase.resolve_state_name() to resolve names of states of the MinimalCore feature."""
        OFF = 0
        INITIALIZING = 1
        READY = 2
        ERROR = 0xFF

    class ButtonEventPayload:
        """Used by the self.evt_button proxy to parse raw event messages into custom event payload objects."""

        def __init__(self, event_message: bytes):
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


class MinimalDevice(DeviceProxyBase):
    core: MinimalCore

    def __init__(self, connection_url: str):
        super().__init__(connection_url=connection_url)

        # Demo_Minimal only implements the mandatory Core feature
        self.core = MinimalCore(self)  # Override base Core-Feature proxy with a more specific one.
