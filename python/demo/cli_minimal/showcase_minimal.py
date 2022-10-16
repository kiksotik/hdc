"""
Showcases how a HDC-host can communicate with a HDC-device which is running the Demo_Minimal firmware example.
"""
import logging
import time

from minimal_proxy import MinimalDevice

#########################################################
# This example uses python logging to explain the 
# demonstration, but also show internals of the HDC-host
hdc_root_logger = logging.getLogger("HDC")
log_handler = logging.StreamHandler()
log_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)7s - %(name)s - %(message)s',
                                           datefmt='%M:%S'))
hdc_root_logger.addHandler(log_handler)
#
demo_logger = hdc_root_logger.getChild("demo")
demo_logger.setLevel(logging.INFO)
# You can tweak the following log-levels to tune verbosity of HDC internals:
logging.getLogger("HDC.packetizer").setLevel(logging.INFO)
logging.getLogger("HDC.protocol").setLevel(logging.INFO)
logging.getLogger("HDC.proxy").setLevel(logging.INFO)


#################################################
# Connect to HDC-device at a specific serial port
dev = MinimalDevice(connection_url="COM10")  # Note how this implements all HDC specifics of a given device type
dev.protocol.connect()  # Will fail if your device is connected at a different port.


###########################################################
# Handling of events that might be raised by the HDC-device
def button_event_handler(message: bytes):
    button_id = message[3]
    button_state = bool(message[4])
    demo_logger.info(f"ButtonID:0x{button_id:02x} ButtonState:{button_state}")
    # ToDo: HDC-event handlers as currently implemented are extremely error-prone, because
    #       they are currently called directly from the "receiver-thread" in hdc_host.protocol.SerialTransport
    #       Therefore the following will fail:
    #           dev.core.prop_led_blinking_rate.set(5 if button_state else 10)


dev.core.evt_button.register_event_handler(button_event_handler)

##################################################################
# Example of how the host requests the device to execute a command
# This is essentially a "remote procedure call".
# Resetting the device will raise some StateTransition-events.
# ToDo: A more instructive example with arguments and return value.
demo_logger.info("_____________________________")
demo_logger.info("Resetting the Core-feature...")
dev.core.cmd_reset()  # Blocks until it receives reply from HDC-device or the default timeout elapses.
time.sleep(0.5)  # Allow for some time for the actual firmware reset to happen.


##################################################################
# Example of how the host gets property values
demo_logger.info("______________________________")
demo_logger.info("Obtain some property values...")
demo_logger.info(f"   Microcontroller REVID: 0x{dev.core.prop_microcontroller_revid.get():08x}")
demo_logger.info(f"   Microcontroller DEVID: 0x{dev.core.prop_microcontroller_devid.get():08x}")
demo_logger.info(f"   Microcontroller   UID: 0x{dev.core.prop_microcontroller_uid.get().hex()}")


##################################################################
# Example of how the host sets property values
demo_logger.info("________________________________________________________________________________")
demo_logger.info("Alternating LED blinking rate, while waiting for device to send button events...")
try:
    while True:
        dev.core.prop_led_blinking_rate.set(5)
        time.sleep(5)
        dev.core.prop_led_blinking_rate.set(10)
        time.sleep(5)
finally:
    dev.protocol.close()
