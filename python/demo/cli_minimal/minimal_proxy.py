"""
Proxy classes to communicate with i.e. a NUCLEO prototype board running any of the Demo_Minimal STM32 firmware examples.
"""
import enum
from datetime import datetime

import hdc_host.proxy_base as proxy_base


class MinimalCore(proxy_base.CoreFeatureProxyBase):

    def __init__(self, device_proxy: proxy_base.DeviceProxyBase):
        super().__init__(device_proxy=device_proxy)

        # Commands
        self.cmd_reset = proxy_base.RawCommandProxy(self, command_id=0xC1)

        # Events
        self.evt_button = proxy_base.EventProxyBase(self, event_id=0x01, payload_parser=self.ButtonEventPayload)

        # Properties
        self.prop_microcontroller_devid = proxy_base.PropertyProxy_RO_UINT32(self, property_id=0x010)
        self.prop_microcontroller_revid = proxy_base.PropertyProxy_RO_UINT32(self, property_id=0x11)
        self.prop_microcontroller_uid = proxy_base.PropertyProxy_RO_BLOB(self, property_id=0x12)
        self.prop_led_blinking_rate = proxy_base.PropertyProxy_RW_UINT8(self, property_id=0x13)

    class FeatureStateEnum(enum.IntEnum):
        """Used by FeatureProxyBase.resolve_state_name() to resolve names of states of the MinimalCore feature."""
        OFF = 0
        INITIALIZING = 1
        READY = 2
        ERROR = 0xFF

    class ButtonEventPayload:
        """Used by the self.evt_button proxy to parse raw event messages into custom event payload objects."""
        def __init__(self, event_message: bytes):
            self.received_at = datetime.utcnow()
            self.button_id = event_message[3]
            self.button_state = event_message[4]


class MinimalDevice(proxy_base.DeviceProxyBase):
    core: MinimalCore

    def __init__(self, connection_url: str):
        super().__init__(connection_url=connection_url)

        # Demo_Minimal only implements the mandatory Core feature
        self.core = MinimalCore(self)  # Override base Core-Feature proxy with a more specific one.
