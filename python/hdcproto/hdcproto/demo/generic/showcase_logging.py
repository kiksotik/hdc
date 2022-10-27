"""
Showcases the HDC LogEvent and the Python loggers.

Note how the mandatory property LogLevelThreshold of each HDC-feature controls how much bandwidth
we may devote to LogEvents raised by each feature.

This script has also been handy to debug the C implementation of the HDC-device.
"""

import logging
import time

import hdcproto.transport.serialport
from hdcproto.host.proxy import DeviceProxyBase


def provoke_some_log_events(transport: hdcproto.transport.serialport.SerialTransport):
    transport.serial_port.write(bytes([0, 0, 0]))  # Provoke reading-frame warning
    transport.send_message(bytes([0, 0, 0]))  # Provoke unknown message type error
    time.sleep(2)  # Wait for some "heart-beat" LogEvents to happen


def showcase_logging():
    #########################################################
    # This example uses python logging to explain the
    # demonstration, but also show internals of the HDC-host
    demo_logger = logging.getLogger('showcase_logging')
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
    device_proxy = DeviceProxyBase(connection_url="COM10")
    device_proxy.router.connect()

    #########################################################
    # Note how granular the logging configuration can be.
    # Here we only enable the LogEvent proxy which is how
    # log messages emitted by the device's firmware are
    # translated into regular python log records.
    device_proxy.core._evt_log.logger.setLevel(logging.DEBUG)

    demo_logger.info("__________________________________________________________________________________________")
    demo_logger.info("This demonstration will intentionally send some corrupt request to the HDC-device, for it")
    demo_logger.info("to complain via LogEvents about different degrees of severity. ")
    demo_logger.info("__________________________________________________________________________________________")
    demo_logger.info(f"Setting LogLevelThreshold of Core-Feature to DEBUG (To receive some heart-beat LogEvents)")
    demo_logger.info("Note: The Demo_Minimal firmware emits a DEBUG LogEvent once a second; a heartbeat for demo.")
    device_proxy.core.prop_log_event_threshold.set(logging.DEBUG)
    provoke_some_log_events(device_proxy.router.transport)

    demo_logger.info("__________________________________________________________________________________________")
    demo_logger.info(f"Setting LogLevelThreshold of Core-Feature to WARNING")
    device_proxy.core.prop_log_event_threshold.set(logging.WARNING)
    provoke_some_log_events(device_proxy.router.transport)

    demo_logger.info("________________________________________________________________________________________")
    demo_logger.info(f"Setting LogLevelThreshold of Core-Feature to ERROR")
    device_proxy.core.prop_log_event_threshold.set(logging.ERROR)
    provoke_some_log_events(device_proxy.router.transport)

    demo_logger.info("________________________________________________________________________________________")
    demo_logger.info(f"Re-setting LogLevelThreshold of Core-Feature to INFO "
                     f"and checking whether device does proper trimming of LogLevelThreshold values")
    device_proxy.core.prop_log_event_threshold.set(logging.INFO)

    assert (device_proxy.core.prop_log_event_threshold.set(logging.DEBUG - 1) == logging.DEBUG)
    assert (device_proxy.core.prop_log_event_threshold.set(logging.CRITICAL + 1) == logging.CRITICAL)

    # Example of how numeric LogLevelThreshold values can be obtained as standard python names
    demo_logger.info("________________________________________________________________________________________")
    demo_logger.info(f"LogLevelThreshold of Core-Feature is currently set "
                     f"to {device_proxy.core.prop_log_event_threshold.get_value_name()}")

    device_proxy.router.close()


if __name__ == '__main__':
    showcase_logging()
