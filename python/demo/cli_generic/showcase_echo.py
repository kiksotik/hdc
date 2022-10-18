"""
Showcases how the (atypical) Echo-command works

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
logging.getLogger("HDC.proxy").setLevel(logging.INFO)

deviceProxy = proxy_base.DeviceProxyBase(connection_url="COM10")
deviceProxy.protocol.connect()

num_requests = 100
# Warning: HDC-device has limited buffer size for receiving a request message!
#          Larger messages will raise reading-frame-error LogEvents!
# Find out what the largest request message size is that this device can cope with.
max_req_msg_size = deviceProxy.core.prop_max_req_msg_size.get()
payload_size = max_req_msg_size - 1  # Because of the MessageType byte that the Echo-request will prepend

logger.info(f"Showcasing ECHO command. Sending {num_requests} requests with a payload of {payload_size} bytes each:")
timestamp_start = time.time_ns()
sent_data = bytes(range(payload_size))
for i in range(num_requests):
    replied_data = deviceProxy.protocol.cmd_echo(sent_data)
    assert replied_data == sent_data
timestamp_stop = time.time_ns()
duration_total_ms = (timestamp_stop - timestamp_start) / 1000000.0
logger.info(f"Completed in {duration_total_ms:.1f}ms --> {duration_total_ms/num_requests:.1f} ms/request")

deviceProxy.protocol.close()
