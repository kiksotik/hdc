"""
Showcases the resetting of features.

This script has been used to investigate the resetting behavior.
"""
import logging
import time

from minimal_proxy import MinimalDevice


def showcase_reset():
    #########################################################
    # This example uses python logging to explain the
    # demonstration, but also show internals of the HDC-host
    demo_logger = logging.getLogger('showcase_reset')
    demo_logger.setLevel(logging.INFO)
    #
    hdc_root_logger = logging.getLogger()
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)7s - %(name)s - %(message)s',
                                               datefmt='%M:%S'))
    hdc_root_logger.addHandler(log_handler)

    # You can tweak the following log-levels to tune verbosity of HDC internals:
    logging.getLogger("hdcproto.transport.packetizer").setLevel(logging.DEBUG)
    logging.getLogger("hdcproto.transport.serialport").setLevel(logging.DEBUG)
    logging.getLogger("hdcproto.host.router").setLevel(logging.DEBUG)
    logging.getLogger("hdcproto.host.proxy").setLevel(logging.DEBUG)

    #################################################
    # Connect to HDC-device at a specific serial port
    dev = MinimalDevice(connection_url="COM10")
    dev.router.connect()

    demo_logger.info("____________________________________")
    demo_logger.info("Resetting the Core-feature...")
    dev.core.cmd_reset()
    time.sleep(1)

    demo_logger.info("____________________________________")
    demo_logger.info("Resetting the Core-feature, again...")
    dev.core.cmd_reset()
    time.sleep(1)

    dev.router.close()


if __name__ == '__main__':
    showcase_reset()
