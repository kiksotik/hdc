"""
Showcases how the capabilities of an unknown device can be explored
by requesting it to produce a JSON representation of its HDC API.

https://en.wikipedia.org/wiki/Interface_description_language

This script has also been handy to debug the C implementation of the HDC-device.
"""
import json
import logging

from hdcproto.host.proxy import DeviceProxyBase


def showcase_meta():
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
    idl_json = device_proxy.get_idl_json(timeout=2)

    print(f"Size of message payload: {len(idl_json)} bytes")

    print(f"Saving {len(idl_json)} bytes of IDL-JSON to file: showcase_meta_idl_raw.json")
    with open('showcase_meta_idl_raw.json', 'w', encoding='utf-8') as f:
        print(idl_json, file=f)

    print(f"Saving pretty printed IDL-JSON to file: showcase_meta_idl_pretty.json")
    idl_dict = json.loads(idl_json)
    with open('showcase_meta_idl_pretty.json', 'w', encoding='utf-8') as f:
        json.dump(idl_dict, f, ensure_ascii=False, indent=4)


if __name__ == '__main__':
    showcase_meta()
