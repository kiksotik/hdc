"""
Showcases how the capabilities of an unknown device can be explored
by means of the introspection capabilities of the HDC protocol.

https://en.wikipedia.org/wiki/Type_introspection

This script has also been handy to debug the C implementation of the HDC-device.
"""
from hdcproto.common import HdcDataType
from hdcproto.host.proxy import DeviceProxyBase, FeatureProxyBase


def is_hdc_internal(member_id: int) -> bool:
    return (member_id & 0xF0) == 0xF0


def showcase_introspection(skip_mandatory_members: bool = False):

    device_proxy = DeviceProxyBase(connection_url="COM10")
    device_proxy.router.connect()

    print(f"Device reports to be compliant with: {device_proxy.get_hdc_version_string()}")

    # Introspection: Available Features
    available_feature_ids = device_proxy.core.prop_available_features.get(timeout=6)
    print(f"Features: {available_feature_ids}")

    for featureID in available_feature_ids:
        feature_proxy = FeatureProxyBase(device_proxy=device_proxy, feature_id=featureID)
        print(f"Feature[0x{featureID:02X}]: {feature_proxy.prop_feature_name.get(timeout=600)}")

        # Introspection: Available Commands on Core feature
        available_command_ids = feature_proxy.prop_available_commands.get(timeout=600)

        for cmdID in available_command_ids:
            if skip_mandatory_members and is_hdc_internal(cmdID):
                continue
            cmd_name = feature_proxy.cmd_get_command_name(cmdID, timeout=600)
            cmd_desc = feature_proxy.cmd_get_command_description(cmdID, timeout=600).replace("\n", "\n\t\t\t")
            print(f"\tCommand[0x{cmdID:02X}]: {cmd_name} {cmd_desc}")

        # Introspection: Available Events on Core feature
        available_event_ids = feature_proxy.prop_available_events.get(timeout=600)

        for evtID in available_event_ids:
            if skip_mandatory_members and is_hdc_internal(evtID):
                continue
            evt_name = feature_proxy.cmd_get_event_name(evtID, timeout=600)
            evt_desc = feature_proxy.cmd_get_event_description(evtID, timeout=600).replace("\n", "\n\t\t\t")
            print(f"\tEvent[0x{evtID:02X}]: {evt_name} {evt_desc}")

        # Introspection: Available Properties on Core feature
        available_property_ids = feature_proxy.prop_available_properties.get(timeout=600)

        for propID in available_property_ids:
            if skip_mandatory_members and is_hdc_internal(propID):
                continue
            prop_ro = feature_proxy.cmd_get_property_readonly(propID, timeout=600)
            prop_type: HdcDataType = feature_proxy.cmd_get_property_type(propID, timeout=600)
            prop_name = feature_proxy.cmd_get_property_name(propID, timeout=600)
            prop_value = feature_proxy.cmd_get_property_value(propID, prop_type, timeout=600)
            if isinstance(prop_value, bytes):
                prop_value = ', '.join(f'0x{byte:02X}' for byte in prop_value)
                prop_value = '[' + prop_value + ']'
            prop_desc = feature_proxy.cmd_get_property_description(propID, timeout=600).replace("\n", "\n\t\t\t")
            print(f"\tProperty[0x{propID:02X}]: "
                  f"{'RO' if prop_ro else 'RW'} "
                  f"{prop_type.name} {prop_name} = {prop_value} {prop_desc}")


if __name__ == '__main__':
    showcase_introspection(skip_mandatory_members=False)
