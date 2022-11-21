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
    # Setup logging
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

    print(f"Device is compliant with: '{device_proxy.get_hdc_version_string()}'")

    print(f"Device can cope with request messages of up to {device_proxy.get_max_req_msg_size()} bytes")

    idl_json = device_proxy.get_idl_json(timeout=2)

    print(f"Saving {len(idl_json)} bytes of IDL-JSON to file: showcase_meta_idl_raw.json")
    with open('showcase_meta_idl_raw.json', 'w', encoding='utf-8') as f:
        print(idl_json, file=f)

    print(f"Saving pretty printed IDL-JSON to file: showcase_meta_idl_pretty.json")
    idl_dict = json.loads(idl_json)
    with open('showcase_meta_idl_pretty.json', 'w', encoding='utf-8') as f:
        json.dump(idl_dict, f, ensure_ascii=False, indent=4)

    print(f"Roundtrip IDL conversion JSON -> Python -> JSON: showcase_meta_idl_pretty_roundtrip.json")
    from hdcproto.descriptor import DeviceDescriptor
    idl_python = DeviceDescriptor.from_idl_json(idl_json)
    with open('showcase_meta_idl_pretty_roundtrip.json', 'w', encoding='utf-8') as f:
        json.dump(idl_python.to_idl_dict(), f, ensure_ascii=False, indent=4)


if __name__ == '__main__':
    showcase_meta()
