import enum
import logging
import time

from pynput import keyboard

from hdcproto.common import HdcDataType, is_valid_uint8, HdcCmdExc_InvalidArgs, HdcCmdException
from hdcproto.descriptor import ArgD, RetD, PropertyDescriptor, CommandDescriptor, EventDescriptor
from hdcproto.device.service import (DeviceService, CoreFeatureService,
                                     CommandService, PropertyService,
                                     FeatureService, EventService)


class MinimalDeviceService(DeviceService):
    def __init__(self, connection_url: str):
        super().__init__(connection_url,
                         device_name="MinimalCore",
                         device_version="0.0.1",  # Mocking a SemVer for this implementation
                         device_doc="Python implementation of the 'Minimal' HDC-device demonstration")

        self.core = MinimalCoreService(self)


class MyDivZeroError(HdcCmdException):
    def __init__(self):
        super().__init__(exception_id=0x01, exception_name="MyDivZero")


class MinimalCoreService(CoreFeatureService):
    def __init__(self, device_service: DeviceService):
        super().__init__(device_service=device_service,
                         feature_states=self.States)

        # Custom attributes
        self.led_blinking_rate = 5

        # Commands
        self.cmd_reset = CommandService(
            command_descriptor=CommandDescriptor(
                id_=0x01,
                name="Reset",
                arguments=None,
                returns=None,
                raises_also=None,
                doc="Reinitializes the whole device.",
            ),
            feature_service=self,
            command_implementation=self.reset,
        )

        self.cmd_divide = CommandService(
            command_descriptor=CommandDescriptor(
                id_=0x02,
                name="Divide",
                arguments=[ArgD(HdcDataType.FLOAT, "numerator"),
                           ArgD(HdcDataType.FLOAT, "denominator", "Beware of the zero!")],
                returns=RetD(HdcDataType.DOUBLE, doc="Quotient of numerator/denominator"),  # May omit name
                raises_also=[MyDivZeroError()],
                doc="Divides numerator by denominator."
            ),
            feature_service=self,
            command_implementation=self.divide,
        )

        # Events
        self.evt_button = ButtonEventService(feature_service=self)  # Example of a custom event

        # Properties
        self.prop_microcontroller_devid = PropertyService(
            property_descriptor=PropertyDescriptor(
                id_=0x10,
                name="uC_DEVID",
                dtype=HdcDataType.UINT32,
                is_readonly=True,
                doc="32bit Device-ID of STM32 microcontroller."
            ),
            feature_service=self,
            property_getter=lambda: 12345,  # bogus
            property_setter=None
        )

        self.prop_microcontroller_revid = PropertyService(
            property_descriptor=PropertyDescriptor(
                id_=0x11,
                name="uC_REVID",
                dtype=HdcDataType.UINT32,
                is_readonly=True,
                doc="32bit Revision-ID of STM32 microcontroller."
            ),
            feature_service=self,
            property_getter=lambda: 67890,  # bogus
            property_setter=None
        )

        self.prop_microcontroller_uid = PropertyService(
            property_descriptor=PropertyDescriptor(
                id_=0x12,
                name="uC_UID",
                dtype=HdcDataType.BLOB,
                is_readonly=True,
                doc="96bit unique-ID of STM32 microcontroller."
            ),
            feature_service=self,
            property_getter=lambda: bytes(range(12)),  # bogus
            property_setter=None
        )

        self.prop_led_blinking_rate = PropertyService(
            property_descriptor=PropertyDescriptor(
                id_=0x13,
                name="LedBlinkingRate",
                dtype=HdcDataType.UINT8,
                is_readonly=False,
                doc="Blinking frequency of the LED given in Herz."
            ),
            feature_service=self,
            property_getter=lambda: self.led_blinking_rate,
            property_setter=self.led_blinking_rate_setter
        )

    @enum.unique
    class States(enum.IntEnum):
        OFF = 0x00
        INIT = 0x01
        READY = 0x02
        ERROR = 0xFF

    def reset(self) -> None:
        # ToDo: Would be interesting to experiment with restarting this script and see how the connection behaves.
        self.hdc_logger.warning("Just pretending to be restarting the device.")
        self.switch_state(new_feature_state_id=self.States.OFF)
        time.sleep(0.2)
        self.switch_state(new_feature_state_id=self.States.INIT)
        time.sleep(0.2)
        self.switch_state(new_feature_state_id=self.States.READY)

    def divide(self, numerator: float, denominator: float) -> float:
        """The actual implementation of the command"""
        if denominator == 0:
            raise MyDivZeroError()

        self.hdc_logger.debug(f"Dividing {numerator} by {denominator}.")

        return numerator / denominator

    def led_blinking_rate_setter(self, new_rate: int) -> int:
        if new_rate < 0 or new_rate > 20:
            raise HdcCmdExc_InvalidArgs(exception_message=f"led_blinking_rate of {new_rate} is invalid, because "
                                                          f"it's beyond valid range [0..20]")
        self.led_blinking_rate = new_rate
        return self.led_blinking_rate


class ButtonEventService(EventService):
    def __init__(self, feature_service: FeatureService):
        super().__init__(
            event_descriptor=EventDescriptor(
                id_=0x01,
                name="ButtonEvent",
                arguments=(ArgD(HdcDataType.UINT8, "ButtonID"),
                           ArgD(HdcDataType.UINT8, "ButtonState")),
                doc="Notify host about the button being pressed on the device."
            ),
            feature_service=feature_service)

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
    device = MinimalDeviceService(connection_url=connection_url)
    device.router.connect()
    kb_listener = keyboard.Listener(on_press=device.core.evt_button.press_callback,
                                    on_release=device.core.evt_button.release_callback)
    kb_listener.start()
    kb_listener.join()

    while True:
        # ToDo: Delayed processing of requests in the app's main thread should be happening here.
        pass


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
    logging.getLogger("hdcproto.device.service").setLevel(logging.DEBUG)

    launch_device(connection_url="socket://localhost:55555")
