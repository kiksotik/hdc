"""
Showcases how the capabilities of an unknown device can be explored
by means of the introspection capabilities of the HDC protocol.

https://en.wikipedia.org/wiki/Type_introspection

This script has also been handy to debug the C implementation of the HDC-device.
"""
from hdcproto.common import HdcDataType
from hdcproto.host.proxy import DeviceProxyBase, FeatureProxyBase

skip_mandatory_members = False


def skip_it(member_id: int) -> bool:
    return skip_mandatory_members and (member_id & 0xF0) == 0xF0


deviceProxy = DeviceProxyBase(connection_url="COM10")
deviceProxy.router.connect()

# Introspection: Available Features
available_featureIDs = deviceProxy.core.prop_available_features.get(timeout=6)
print(f"Features: {available_featureIDs}")

for featureID in available_featureIDs:
    featureProxy = FeatureProxyBase(device_proxy=deviceProxy, feature_id=featureID)
    print(f"Feature[0x{featureID:02X}]: {featureProxy.prop_feature_name.get(timeout=600)}")

    # Introspection: Available Commands on Core feature
    available_commandIDs = featureProxy.prop_available_commands.get(timeout=600)

    for cmdID in available_commandIDs:
        if skip_it(cmdID):
            continue
        cmdName = featureProxy._cmd_get_command_name(cmdID, timeout=600)
        cmdDesc = featureProxy._cmd_get_command_description(cmdID, timeout=600).replace("\n", "\n\t\t\t")
        print(f"\tCommand[0x{cmdID:02X}]: {cmdName} {cmdDesc}")

    # Introspection: Available Events on Core feature
    available_eventIDs = featureProxy.prop_available_events.get(timeout=600)

    for evtID in available_eventIDs:
        if skip_it(evtID):
            continue
        evtName = featureProxy._cmd_get_event_name(evtID, timeout=600)
        evtDesc = featureProxy._cmd_get_event_description(evtID, timeout=600).replace("\n", "\n\t\t\t")
        print(f"\tEvent[0x{evtID:02X}]: {evtName} {evtDesc}")

    # Introspection: Available Properties on Core feature
    available_propertyIDs = featureProxy.prop_available_properties.get(timeout=600)

    for propID in available_propertyIDs:
        if skip_it(propID):
            continue
        propRO = featureProxy._cmd_get_property_readonly(propID, timeout=600)
        propType: HdcDataType = featureProxy._cmd_get_property_type(propID, timeout=600)
        propName = featureProxy._cmd_get_property_name(propID, timeout=600)
        propValue = featureProxy._cmd_get_property_value(propID, propType, timeout=600)
        if isinstance(propValue, bytes):
            propValue = ', '.join(f'0x{byte:02x}' for byte in propValue)
            propValue = '[' + propValue + ']'
        propDesc = featureProxy._cmd_get_property_description(propID, timeout=600).replace("\n", "\n\t\t\t")
        print(f"\tProperty[0x{propID:02X}]: "
              f"{'RO' if propRO else 'RW'} "
              f"{propType.name} {propName} = {propValue} {propDesc}")
