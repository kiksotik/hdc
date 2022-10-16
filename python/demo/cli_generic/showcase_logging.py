"""
Showcases the HDC LogEvent and the Python loggers.

Note how the mandatory property LogLevelThreshold of each HDC-feature controls how much bandwidth
we may devote to LogEvents raised by each feature.

This script has also been handy to debug the C implementation of the HDC-device.
"""

import logging
import time

import hdc_host.proxy_base as proxy_base

logger = logging.getLogger("HDC.showcase")

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)7s - %(name)s - %(message)s', datefmt='%M:%S')
ch.setFormatter(formatter)
root_logger = logging.getLogger("HDC")
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(ch)
logging.getLogger("HDC.packetizer").setLevel(logging.INFO)
logging.getLogger("HDC.protocol").setLevel(logging.INFO)
logging.getLogger("HDC.proxy").setLevel(logging.DEBUG)

deviceProxy = proxy_base.DeviceProxyBase(connection_url="COM10")
deviceProxy.protocol.connect()


def provoke_some_log_events():
    deviceProxy.protocol.transport.serial_port.write(bytes([0, 0, 0]))  # Provoke reading-frame warning
    deviceProxy.protocol.transport.send_message(bytes([0, 0, 0]))  # Provoke unknown message type error
    time.sleep(2)  # Wait for some "heart-beat" LogEvents to happen


logger.info(f"LogLevelThreshold of MinimalCore-Feature is currently set "
            f"to {deviceProxy.core.prop_log_event_threshold.get_value_name()}")

logger.info("________________________________________________________________________________________")
logger.info(f"Setting LogLevelThreshold of MinimalCore-Feature to DEBUG (Expecting to receive some heart-beat LogEvents)")
deviceProxy.core.prop_log_event_threshold.set(logging.DEBUG)
provoke_some_log_events()

logger.info("________________________________________________________________________________________")
logger.info(f"Setting LogLevelThreshold of MinimalCore-Feature to WARNING")
deviceProxy.core.prop_log_event_threshold.set(logging.WARNING)
provoke_some_log_events()

logger.info("________________________________________________________________________________________")
logger.info(f"Setting LogLevelThreshold of MinimalCore-Feature to ERROR")
deviceProxy.core.prop_log_event_threshold.set(logging.ERROR)
provoke_some_log_events()

logger.info("________________________________________________________________________________________")
logger.info(f"Re-setting LogLevelThreshold of MinimalCore-Feature to INFO")
deviceProxy.core.prop_log_event_threshold.set(logging.INFO)

logger.info("________________________________________________________________________________________")
logger.info(f"Checking whether device does proper trimming of LogLevelThreshold values")
assert(deviceProxy.core.prop_log_event_threshold.set(logging.DEBUG - 1) == logging.DEBUG)
assert(deviceProxy.core.prop_log_event_threshold.set(logging.CRITICAL + 1) == logging.CRITICAL)

deviceProxy.protocol.close()
