import enum
import logging
import time

from pynput import keyboard

from hdcproto.common import HdcDataType, is_valid_uint8, HdcCmdExc_InvalidArgs, HdcCmdException
from hdcproto.device.service import (DeviceService, CoreFeatureService,
                                     CommandService, PropertyService,
                                     FeatureService, EventService)
from hdcproto.descriptor import ArgD, RetD


class MinimalDeviceService(DeviceService):
    def __init__(self, connection_url: str):
        super().__init__(connection_url,
                         core_feature_service_class=MinimalCoreService,
                         device_name="MinimalCore",
                         device_version="0.0.1",  # Mocking a SemVer for this implementation
                         device_description="Python implementation of the 'Minimal' HDC-device demonstration")

    def main_loop(self):
        self.router.connect()
        kb_listener = keyboard.Listener(on_press=self.core.evt_button.press_callback,
                                        on_release=self.core.evt_button.release_callback)
        kb_listener.start()
        kb_listener.join()

        while True:
            # ToDo: Delayed processing of requests in the app's main thread should be happening here.
            pass


class MyDivZeroError(HdcCmdException):
    def __init__(self):
        super().__init__(exception_id=0x01, exception_name="MyDivZero")


class MinimalCoreService:
    def __init__(self, device_service: DeviceService):
        # We could "inherit" from CoreFeatureService, but we choose "composition", instead, because
        # it allows us to separate more cleanly our custom services from those defined in FeatureService.
        # This is for example useful to keep the autocompletion list short and readable while coding.
        self.hdc = CoreFeatureService(device_service=device_service, feature_states=self.States)

        # Custom attributes
        self.led_blinking_rate = 5

        # Commands
        # Commands
        self.cmd_reset = CommandService(
            feature_service=self.hdc,
            command_id=0x01,
            command_name="Reset",
            command_description="Reinitializes the whole device.",  # Human-readable docstring
            command_implementation=self.reset,
            command_arguments=None,
            command_returns=None,
            command_raises_also=None
        )

        self.cmd_divide = CommandService(
            feature_service=self.hdc,
            command_id=0x02,
            command_name="Divide",
            command_description="Divides numerator by denominator.",  # Human-readable docstring
            command_implementation=self.divide,
            command_arguments=[ArgD(HdcDataType.FLOAT, "numerator"),
                               ArgD(HdcDataType.FLOAT, "denominator", "Beware of the zero!")],
            command_returns=RetD(HdcDataType.DOUBLE, doc="Quotient of numerator/denominator"),  # May omit name
            command_raises_also=[MyDivZeroError()]
        )

        # Events
        self.evt_button = ButtonEventService(feature_service=self.hdc)  # Example of a custom event

        # Properties
        self.prop_microcontroller_devid = PropertyService(
            feature_service=self.hdc,
            property_id=0x10,
            property_name="uC_DEVID",
            property_description="32bit Device-ID of STM32 microcontroller.",
            property_type=HdcDataType.UINT32,
            property_getter=lambda: 12345,  # bogus
            property_setter=None
        )

        self.prop_microcontroller_revid = PropertyService(
            feature_service=self.hdc,
            property_id=0x11,
            property_name="uC_REVID",
            property_description="32bit Revision-ID of STM32 microcontroller.",
            property_type=HdcDataType.UINT32,
            property_getter=lambda: 67890,  # bogus
            property_setter=None
        )

        self.prop_microcontroller_uid = PropertyService(
            feature_service=self.hdc,
            property_id=0x12,
            property_name="uC_UID",
            property_description="96bit unique-ID of STM32 microcontroller.",
            property_type=HdcDataType.BLOB,
            property_getter=lambda: bytes(range(12)),  # bogus
            property_setter=None
        )

        self.prop_led_blinking_rate = PropertyService(
            feature_service=self.hdc,
            property_id=0x13,
            property_name="LedBlinkingRate",
            property_description="Blinking frequency of the LED given in Herz.",
            property_type=HdcDataType.UINT8,
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
        self.hdc.hdc_logger.warning("Just pretending to be restarting the device.")
        self.hdc.feature_state_transition(new_feature_state_id=self.States.OFF)
        time.sleep(0.2)
        self.hdc.feature_state_transition(new_feature_state_id=self.States.INIT)
        time.sleep(0.2)
        self.hdc.feature_state_transition(new_feature_state_id=self.States.READY)

    def divide(self, numerator: float, denominator: float) -> float:
        """The actual implementation of the command"""
        if denominator == 0:
            raise MyDivZeroError()

        self.hdc.hdc_logger.debug(f"Dividing {numerator} by {denominator}.")

        return numerator / denominator

    def led_blinking_rate_setter(self, new_rate: int) -> int:
        if new_rate < 0 or new_rate > 20:
            raise HdcCmdExc_InvalidArgs(exception_message=f"led_blinking_rate of {new_rate} is invalid, because "
                                                          f"it's beyond valid range [0..20]")
        self.led_blinking_rate = new_rate
        return self.led_blinking_rate


class ButtonEventService(EventService):
    def __init__(self, feature_service: FeatureService):
        super().__init__(feature_service=feature_service,
                         event_id=0x01,
                         event_name="ButtonEvent",
                         event_description="Notify host about the button being pressed on the device.",
                         event_arguments=(ArgD(HdcDataType.UINT8, "ButtonID"),
                                          ArgD(HdcDataType.UINT8, "ButtonState")))

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
    logging.getLogger("hdcproto.device.service").setLevel(logging.DEBUG)

    launch_device(connection_url="socket://localhost:55555")
