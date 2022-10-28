"""
Showcases how a HDC-host can communicate with a HDC-device which is running the Demo_Minimal firmware example.
"""
import logging
import time

from minimal_proxy import MinimalDevice, MinimalCore


def showcase_minimal():
    #########################################################
    # This example uses python logging to explain the
    # demonstration, but also show internals of the HDC-host
    demo_logger = logging.getLogger('showcase_minimal')
    demo_logger.setLevel(logging.INFO)
    #
    hdc_root_logger = logging.getLogger()
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)7s - %(name)s - %(message)s',
                                               datefmt='%M:%S'))
    hdc_root_logger.addHandler(log_handler)

    # You can tweak the following log-levels to tune verbosity of HDC internals:
    logging.getLogger("hdcproto.transport.packetizer").setLevel(logging.WARNING)
    logging.getLogger("hdcproto.transport.serialport").setLevel(logging.WARNING)
    logging.getLogger("hdcproto.host.router").setLevel(logging.WARNING)
    logging.getLogger("hdcproto.host.proxy").setLevel(logging.NOTSET)

    #################################################
    # Connect to HDC-device at a specific serial port
    dev = MinimalDevice(connection_url="COM10")  # Note how this implements all HDC specifics of a given device type
    dev.router.connect()  # Will fail if your device is connected at a different port.

    ######################################################################################
    # Example of how "inheritance" mixes-in the stuff defined in DeviceProxyBase into self
    demo_logger.info("--------------------------------------------------------------")
    demo_logger.info("Asking device about the HDC-spec version it is compliant with:")
    demo_logger.info(f"Raw version string: '{dev.get_hdc_version_string()}'")
    demo_logger.info(f"    Parsed version: '{repr(dev.get_hdc_version())}'")

    ########################################################################
    # Example of how to react to an event on the very moment it is received.
    # WARNING: This handler will be executed in the "receiver thread"
    #          and thus must be fast and thread-safe!
    #          Note how the HDC-host driver is neither, thus refrain from
    #          using the HDC-host driver from within this kind of handler!
    #
    #          See example further below on how to react to events in a delayed, but much safer manner.
    def button_event_handler(event_payload: MinimalCore.ButtonEventPayload):
        demo_logger.info(f"ButtonID:0x{event_payload.button_id:02X} ButtonState:{event_payload.button_state}")

    dev.core.evt_button.register_event_payload_handler(button_event_handler)

    ##################################################################
    # Example of how the host requests the device to execute a command
    # This is essentially a "remote procedure call".
    # Resetting the device will raise some StateTransition-events.
    # ToDo: A more instructive example with arguments and return value.
    demo_logger.info("_____________________________")
    demo_logger.info("Resetting the Core-feature...")
    dev.core.cmd_reset()  # Blocks until it receives reply from HDC-device or the default timeout elapses.
    time.sleep(0.5)  # Allow for some time for the actual firmware reset to happen.

    #############################################################################################
    # Example of how "composition" keeps stuff defined in FeatureProxyBase separate in self.hdc
    demo_logger.info("_____________________________________")
    demo_logger.info("Obtain some mandatory property values...")
    demo_logger.info(f"       LogEventThreshold: {dev.core.hdc.prop_log_event_threshold.get_value_name()}")

    ##################################################################
    # Example of how the host gets property values
    demo_logger.info("_____________________________________")
    demo_logger.info("Obtain some custom property values...")
    demo_logger.info(f"   Microcontroller REVID: 0x{dev.core.prop_microcontroller_revid.get():08x}")
    demo_logger.info(f"   Microcontroller DEVID: 0x{dev.core.prop_microcontroller_devid.get():08x}")
    demo_logger.info(f"   Microcontroller   UID: 0x{dev.core.prop_microcontroller_uid.get().hex()}")

    ##################################################################
    # Example of how the host sets property values
    demo_logger.info("_____________________________________________________________________________")
    demo_logger.info("Change LED blinking rate, depending on most recently received button event...")
    try:
        while True:

            time.sleep(2)

            #######################################################################################################
            # Example of how a host can process events at a more suitable point in time and a more suitable thread.
            event_payload_deque = dev.core.evt_button.most_recently_received_event_payloads  # Just for readability
            if not event_payload_deque:
                continue  # No button-events have been received, thus we can skip the remainder.

            most_recent_button_event: MinimalCore.ButtonEventPayload = event_payload_deque.pop()
            event_payload_deque.clear()  # Get rid of any other, prior events.

            ##############################################
            # Example of how the host sets property values
            new_led_blinking_rate = 5 if most_recent_button_event.button_state else 20
            dev.core.prop_led_blinking_rate.set(new_led_blinking_rate)
    finally:
        dev.router.close()


if __name__ == '__main__':
    showcase_minimal()
