"""
Showcases how a HDC-host can communicate with a HDC-device which is running the Demo_Minimal firmware example.
"""
import logging
import time

from hdcproto.common import HdcCmdException
from hdcproto.descriptor import FeatureDescriptor, StateDescriptor, EventDescriptor
from hdcproto.host.proxy import DeviceProxyBase, EventProxyBase
from minimal_proxy import MinimalDevice, MinimalCore, MyDivZeroError


def custom_proxy_factory(descriptor, parent_proxy):
    if isinstance(descriptor, FeatureDescriptor):
        # Example of how to "tweak" / "edit" a descriptor. In this case we inject our custom FeatureStates
        descriptor.states = {d.id: d for d in (StateDescriptor(e, e.name) for e in MinimalCore.FeatureStateEnum)}
        return False  # Returning False, to produce default proxy, but with the "tweaked" descriptor

    if isinstance(descriptor, EventDescriptor) and descriptor.id == 0x01:
        return EventProxyBase(
            event_descriptor=descriptor,
            feature_proxy=parent_proxy,
            # Note how we override default parser with our custom one
            payload_parser=MinimalCore.ButtonEventPayload)

    if isinstance(descriptor, HdcCmdException) and descriptor.exception_id == 0x01:
        # Example of how to use a fully customized proxy.
        # Note that Exceptions are special, because their instances serve all three purposes: descriptor, service, proxy
        return MyDivZeroError()

    return False  # Instantiate default proxy class


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
    connection_url = "COM10"
    # connection_url = "socket://localhost:55555"
    demo_logger.info("--------------------------------------------------------------")
    demo_logger.info(f"About to connect to device at {connection_url}")
    # dev = MinimalDevice()  # Use a hardcoded proxy, instead of auto-generating it in the line below.
    dev = DeviceProxyBase.connect_and_build(connection_url=connection_url, custom_proxy_factory=custom_proxy_factory)
    dev.router.connect(connection_url=connection_url)  # Will fail if your device is connected at a different port.
    demo_logger.info(f"Using {'manually-authored' if isinstance(dev, MinimalDevice) else 'auto-generated'} proxy")

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
    demo_logger.info("_____________________________")
    demo_logger.info("Resetting the Core-feature...")
    dev.core.evt_state_transition.logger.setLevel(logging.INFO)  # Note the very granular logging capabilities
    dev.core.cmd_reset.default_timeout = 5.0  # ToDo: Include timeout in the descriptor? Also per property s/getters?
    dev.core.cmd_reset()  # Blocks until it receives reply from HDC-device or the default timeout elapses.
    time.sleep(0.5)  # Allow for some time for the actual firmware reset to happen.

    ##################################################################
    # Example of a command with arguments a return value
    demo_logger.info("_____________________________")
    result = dev.core.cmd_division(numerator=10.0, denominator=3.0)
    demo_logger.info(f"Dividing 10 by 3 returns {result}")

    ##################################################################
    # Example of receiving an exception raised by the device
    demo_logger.info("_____________________________")
    try:
        dev.core.cmd_division(numerator=10.0, denominator=0.0)
    except MyDivZeroError:
        demo_logger.info("Dividing 10 by 0 made the device raise a custom exception which was forwarded to this proxy.")
    else:
        raise RuntimeError("Failed to receive the expected custom exception!")

    ##################################################################
    # Example of how the host gets property values
    demo_logger.info("_____________________________________")
    demo_logger.info("Obtain some mandatory property values...")
    demo_logger.info(f"       LogEventThreshold: {dev.core.prop_log_event_threshold.get_value_name()}")
    demo_logger.info("_____________________________________")
    demo_logger.info("Obtain some custom property values...")
    demo_logger.info(f"   Microcontroller DEVID: 0x{dev.core.prop_uc_devid.get():08x}")
    demo_logger.info(f"   Microcontroller   UID: 0x{dev.core.prop_uc_uid.get().hex()}")

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

            ##############################################
            # Example of how the host sets property values

    finally:
        dev.router.close()


if __name__ == '__main__':
    showcase_minimal()
