import enum
import logging
import time

from pynput import keyboard

from hdcproto.common import HdcDataType, is_valid_uint8, HdcCmdExc_InvalidArgs, HdcCmdException
from hdcproto.descriptor import CommandDescriptor, EventDescriptor, PropertyDescriptor, ArgD, RetD
from hdcproto.device.service import (DeviceService, CoreFeatureService, FeatureService, CommandService, EventService,
                                     PropertyService)


class MyDivZeroError(HdcCmdException):
    """Example of a custom exception that can be raised here and received on the Host"""
    def __init__(self):
        super().__init__(id=0x01, name="MyDivZero")


class MinimalCoreService(CoreFeatureService):
    """The only HDC-feature on this device. Exposes some example commands, events and properties."""
    def __init__(self, device_service: DeviceService):
        super().__init__(device_service=device_service,
                         feature_states=self.States)

        # Commands
        self.cmd_reset = CommandService(
            command_descriptor=CommandDescriptor(
                id=0x01,
                name="reset",
                args=None,
                returns=None,
                raises=None,
                doc="Reinitializes the whole device.",
            ),
            feature_service=self,
            command_implementation=self.reset,
        )

        self.cmd_division = CommandService(
            command_descriptor=CommandDescriptor(
                id=0x02,
                name="division",
                args=[ArgD(HdcDataType.FLOAT, "numerator"),
                      ArgD(HdcDataType.FLOAT, "denominator", "Beware of the zero!")],
                returns=RetD(HdcDataType.DOUBLE, doc="Quotient of numerator/denominator"),  # May omit name
                raises=[MyDivZeroError()],
                doc="Divides numerator by denominator."
            ),
            feature_service=self,
            command_implementation=self.division,
        )

        # Events
        self.evt_button = ButtonEventService(feature_service=self)  # Example of a custom event

        #############
        # Properties

        # Example of exposing a constant/immutable UINT32 value as a property
        self.prop_uc_devid = PropertyService(
            property_descriptor=PropertyDescriptor(
                id=0x10,
                name="uc_devid",
                dtype=HdcDataType.UINT32,
                is_readonly=True,
                doc="32bit Device-ID of STM32 microcontroller."
            ),
            feature_service=self,
            property_getter=lambda: 12345,  # bogus value
            property_setter=None
        )

        # Example of exposing a constant/immutable BLOB value as a property
        self.prop_uc_uid = PropertyService(
            property_descriptor=PropertyDescriptor(
                id=0x11,
                name="uc_uid",
                dtype=HdcDataType.BLOB,
                is_readonly=True,
                doc="96bit unique-ID of STM32 microcontroller."
            ),
            feature_service=self,
            property_getter=lambda: bytes(range(12)),  # bogus value of a constant/immutable BLOB property
            property_setter=None
        )

        # Example of exposing a mutable UINT8 value as a property
        self.led_blinking_rate = 5  # Instance attribute that's being exposed by the property below
        self.prop_led_blinking_rate = PropertyService(
            property_descriptor=PropertyDescriptor(
                id=0x12,
                name="led_blinking_rate",
                dtype=HdcDataType.UINT8,
                is_readonly=False,
                doc="Blinking frequency of the LED given in Herz."
            ),
            feature_service=self,
            property_getter=lambda: self.led_blinking_rate,  # Attribute
            property_setter=self.led_blinking_rate_setter  # Setter method implements value validation, etc
        )

    @enum.unique
    class States(enum.IntEnum):
        """Example of custom states used by this feature's state-machine."""
        OFF = 0x00
        INIT = 0x01
        READY = 0x02
        ERROR = 0xFF

    def reset(self) -> None:
        """Actual implementation of the HDC-command. Simulates a restart and shows API of the feature-state"""
        # ToDo: Would be interesting to experiment with restarting this script and see how the connection behaves.
        self.hdc_logger.warning("Just pretending to be restarting the device.")
        self.switch_state(new_feature_state_id=self.States.OFF)
        assert self.current_state_id == self.States.OFF
        time.sleep(0.2)
        self.switch_state(new_feature_state_id=self.States.INIT)
        assert self.current_state_id == self.States.INIT
        time.sleep(0.2)
        self.switch_state(new_feature_state_id=self.States.READY)
        assert self.current_state_id == self.States.READY

    def division(self, numerator: float, denominator: float) -> float:
        """Actual implementation of the HDC-command"""
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
                id=0x01,
                name="button",
                args=(ArgD(HdcDataType.UINT8, "button_id"),
                      ArgD(HdcDataType.UINT8, "button_state")),
                doc="Notify host about the button being pressed on the device."
            ),
            feature_service=feature_service)

    def emit(self, button_id: int, button_state: int):
        super().emit([button_id, button_state])

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


class MinimalDeviceService(DeviceService):
    def __init__(self, connection_url: str):
        super().__init__(connection_url,
                         device_name="MinimalCore",
                         device_version="0.0.1",  # Mocking a SemVer for this implementation
                         device_doc="Python implementation of the 'Minimal' HDC-device demonstration",
                         max_req=128)

        self.core = MinimalCoreService(self)


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
