"""
Showcases how the capabilities of an unknown device can be explored
by requesting it to produce a JSON representation of its HDC API.

https://en.wikipedia.org/wiki/Interface_description_language

This script has also been handy to debug the C implementation of the HDC-device.
"""
import logging

from hdcproto.host.proxy import DeviceProxyBase


def showcase_introspection():
    ###################
    # SSetup logging
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

    ###################
    device_proxy = DeviceProxyBase(connection_url="COM10")
    # device_proxy = DeviceProxyBase(connection_url="socket://localhost:55555")
    device_proxy.connect()

    print(f"Device describes its HDC-API as follows:")
    meta = device_proxy.get_meta(timeout=2)
    print(meta)
    print(f"Size of message payload: {len(meta)} bytes")


if __name__ == '__main__':
    showcase_introspection()
