import logging

from pynput import keyboard

from hdcproto.common import HdcDataType, is_valid_uint8, CommandErrorCode
from hdcproto.device.descriptor import (DeviceDescriptorBase, CoreFeatureDescriptorBase,
                                        TypedCommandDescriptor, EventDescriptorBase, PropertyDescriptorBase,
                                        FeatureDescriptorBase)


class MinimalDeviceDescriptor(DeviceDescriptorBase):
    def __init__(self, connection_url: str):
        super().__init__(connection_url, core_feature_descriptor_class=MinimalCoreDescriptor)

    def main_loop(self):
        self.router.connect()
        kb_listener = keyboard.Listener(on_press=self.core.evt_button.press_callback,
                                        on_release=self.core.evt_button.release_callback)
        kb_listener.start()
        kb_listener.join()

        while True:
            # ToDo: Delayed processing of requests in the app's main thread should be happening here.
            pass


class MinimalCoreDescriptor:
    def __init__(self, device_descriptor: DeviceDescriptorBase):
        # We could "inherit" from CoreFeatureDescriptor, but we choose "composition", instead, because
        # it allows us to separate more cleanly our custom descriptors from those defined in FeatureDescriptorBase.
        # This is for example useful to keep the autocompletion list short and readable while coding.
        self.hdc = CoreFeatureDescriptorBase(device_descriptor=device_descriptor)

        # Mocking of name and revision number
        # of device implementation which we are emulating here.
        self.hdc.feature_type_name = "MinimalCore"
        self.hdc.feature_type_revision = 1

        # Custom attributes
        self.led_blinking_rate = 5

        # Commands
        self.cmd_reset = TypedCommandDescriptor(
            feature_descriptor=self.hdc,
            command_id=0xC1,
            command_name="Reset",
            command_description="Reinitializes the whole device.",  # Human-readable docstring
            command_implementation=self.reset,
            command_arguments=None,
            command_returns=None,
            command_raises=None
        )

        # Events
        self.evt_button = ButtonEventDescriptor(feature_descriptor=self.hdc)  # Example of a custom event

        # Properties
        self.prop_microcontroller_devid = PropertyDescriptorBase(
            feature_descriptor=self.hdc,
            property_id=0x10,
            property_name="uC_DEVID",
            property_description="32bit Device-ID of STM32 microcontroller.",
            property_type=HdcDataType.UINT32,
            property_getter=lambda: 12345,  # bogus
            property_setter=None
        )

        self.prop_microcontroller_revid = PropertyDescriptorBase(
            feature_descriptor=self.hdc,
            property_id=0x11,
            property_name="uC_REVID",
            property_description="32bit Revision-ID of STM32 microcontroller.",
            property_type=HdcDataType.UINT32,
            property_getter=lambda: 67890,  # bogus
            property_setter=None
        )

        self.prop_microcontroller_uid = PropertyDescriptorBase(
            feature_descriptor=self.hdc,
            property_id=0x12,
            property_name="uC_UID",
            property_description="96bit unique-ID of STM32 microcontroller.",
            property_type=HdcDataType.BLOB,
            property_getter=lambda: bytes(range(12)),  # bogus
            property_setter=None
        )

        # ToDo: We could use the following property
        self.prop_led_blinking_rate = PropertyDescriptorBase(
            feature_descriptor=self.hdc,
            property_id=0x13,
            property_name="LedBlinkingRate",
            property_description="Blinking frequency of the LED given in Herz.",
            property_type=HdcDataType.UINT32,
            property_getter=lambda: self.led_blinking_rate,
            property_setter=self.led_blinking_rate_setter
        )

    def reset(self) -> None:
        # ToDo: Would be interesting to experiment with restarting this script and see how the connection behaves.
        self.hdc.hdc_logger.warning("Just pretending to be restarting the device.")

    def led_blinking_rate_setter(self, new_rate: int) -> int:
        if new_rate < 0 or new_rate > 20:
            raise self.hdc.cmd_set_property_value.build_cmd_error(CommandErrorCode.INVALID_PROPERTY_VALUE)
        self.led_blinking_rate = new_rate
        return self.led_blinking_rate


class ButtonEventDescriptor(EventDescriptorBase):
    def __init__(self, feature_descriptor: FeatureDescriptorBase):
        super().__init__(feature_descriptor=feature_descriptor,
                         event_id=0x01,
                         event_name="ButtonEvent",
                         event_description="Showcases implementation of a custom HDC-event: "
                                           "Notify host about the button being pressed on the device.",
                         event_arguments=[(HdcDataType.UINT8, "ButtonID"),
                                          (HdcDataType.UINT8, "ButtonState")])

    def emit(self, button_id: int, button_state: int):
        self._send_event_message([button_id, button_state])

    def press_callback(self, key: keyboard.Key):
        if isinstance(key, keyboard.KeyCode):
            button_id = ord(key.char)
            if is_valid_uint8(button_id):
                self.emit(button_id, button_state=1)

    def release_callback(self, key: keyboard.Key):
        if isinstance(key, keyboard.KeyCode):
            button_id = ord(key.char)
            if is_valid_uint8(button_id):
                self.emit(button_id, button_state=0)


def launch_device(connection_url: str):
    device = MinimalDeviceDescriptor(connection_url=connection_url)
    device.main_loop()


if __name__ == '__main__':
    ######################################################################
    # This example uses python logging to show internals of the HDC-device
    hdc_root_logger = logging.getLogger()
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)7s - %(name)s - %(message)s',
                                               datefmt='%M:%S'))
    hdc_root_logger.addHandler(log_handler)

    # You can tweak the following log-levels to tune verbosity of HDC internals:
    logging.getLogger("hdcproto.transport.packetizer").setLevel(logging.DEBUG)
    logging.getLogger("hdcproto.transport.tcpserver").setLevel(logging.DEBUG)
    logging.getLogger("hdcproto.device.router").setLevel(logging.DEBUG)
    logging.getLogger("hdcproto.device.descriptor").setLevel(logging.DEBUG)

    launch_device(connection_url="socket://localhost:55555")
