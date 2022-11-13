"""
Showcases how the (atypical) Echo-command works

This script has also been handy to debug the C implementation of the HDC-device.
"""

import logging
import time

from hdcproto.host.proxy import DeviceProxyBase


def showcase_echo():
    #########################################################
    # This example uses python logging to explain the
    # demonstration, but also show internals of the HDC-host
    demo_logger = logging.getLogger('showcase_echo')
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
    logging.getLogger("hdcproto.host.proxy").setLevel(logging.WARNING)

    #################################################
    # Connect to HDC-device at a specific serial port
    device_proxy = DeviceProxyBase(connection_url="COM10")
    device_proxy.connect()

    num_requests = 100
    # Warning: HDC-device has limited buffer size for receiving a request message!
    #          Larger messages will raise reading-frame-error LogEvents!
    # Find out what the largest request message size is that this device can cope with.
    max_req_msg_size = device_proxy.get_max_req_msg_size()
    payload_size = max_req_msg_size - 1  # Because of the MessageType byte that the Echo-request will prepend

    demo_logger.info(f"Device reports to be compliant with: '{device_proxy.get_hdc_version_string()}'")
    demo_logger.info("______________________________________________________________________")
    demo_logger.info(f"Showcasing ECHO command:")
    demo_logger.info(f"Sending {num_requests} requests with a payload of {payload_size} bytes each ...")
    timestamp_start = time.time_ns()
    sent_data = bytes(range(payload_size))
    for i in range(num_requests):
        replied_data = device_proxy.get_echo(sent_data)
        assert replied_data == sent_data
    timestamp_stop = time.time_ns()
    duration_total_ms = (timestamp_stop - timestamp_start) / 1000000.0
    demo_logger.info(f"... completed in {duration_total_ms:.1f}ms "
                     f"--> {duration_total_ms / num_requests:.1f} ms/request")

    device_proxy.router.close()


if __name__ == '__main__':
    showcase_echo()
