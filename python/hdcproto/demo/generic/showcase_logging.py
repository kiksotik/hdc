"""
Showcases the HDC LogEvent and the Python loggers.

Note how the mandatory property LogLevelThreshold of each HDC-feature controls how much bandwidth
we may devote to LogEvents raised by each feature.

This script has also been handy to debug the C implementation of the HDC-device.
"""

import logging
import time

import host.proxy

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
logging.getLogger("HDC.proxy").setLevel(logging.DEBUG)


#################################################
# Connect to HDC-device at a specific serial port
deviceProxy = host.proxy.DeviceProxyBase(connection_url="COM10")
deviceProxy.router.connect()


def provoke_some_log_events():
    deviceProxy.router.transport.serial_port.write(bytes([0, 0, 0]))  # Provoke reading-frame warning
    deviceProxy.router.transport.send_message(bytes([0, 0, 0]))  # Provoke unknown message type error
    time.sleep(2)  # Wait for some "heart-beat" LogEvents to happen


demo_logger.info(f"LogLevelThreshold of Core-Feature is currently set "
                 f"to {deviceProxy.core.prop_log_event_threshold.get_value_name()}")

demo_logger.info("________________________________________________________________________________________")
demo_logger.info(f"Setting LogLevelThreshold of Core-Feature to DEBUG (Expecting to receive some heart-beat LogEvents)")
deviceProxy.core.prop_log_event_threshold.set(logging.DEBUG)
provoke_some_log_events()

demo_logger.info("________________________________________________________________________________________")
demo_logger.info(f"Setting LogLevelThreshold of Core-Feature to WARNING")
deviceProxy.core.prop_log_event_threshold.set(logging.WARNING)
provoke_some_log_events()

demo_logger.info("________________________________________________________________________________________")
demo_logger.info(f"Setting LogLevelThreshold of Core-Feature to ERROR")
deviceProxy.core.prop_log_event_threshold.set(logging.ERROR)
provoke_some_log_events()

demo_logger.info("________________________________________________________________________________________")
demo_logger.info(f"Re-setting LogLevelThreshold of Core-Feature to INFO "
                 f"and checking whether device does proper trimming of LogLevelThreshold values")
deviceProxy.core.prop_log_event_threshold.set(logging.INFO)

assert(deviceProxy.core.prop_log_event_threshold.set(logging.DEBUG - 1) == logging.DEBUG)
assert(deviceProxy.core.prop_log_event_threshold.set(logging.CRITICAL + 1) == logging.CRITICAL)

deviceProxy.router.close()
