"""
EXPERIMENTAL: Proxy classes that generate themselves by using HDC introspection
"""
import ast
import enum

from hdcproto.host.proxy import FeatureProxyBase, DeviceProxyBase


class IntrospectedFeatureProxy(FeatureProxyBase):

    def __init(self, device_proxy: DeviceProxyBase, feature_id: int):

        super().__init__(device_proxy=device_proxy, feature_id=feature_id)

        """
        ToDo: EXPERIMENTAL: Update this proxy with introspected meta-data
        """

        # ToDo: Introspect Commands, Properties and Events

        # FeatureStateEnum
        # As documented in dict syntax in the description of the FeatureState property
        # The FeatureStateEnum class is defined as class property, because keeping them as instance properties would be
        # too confusing! But it might be problematic when introspecting multiple devices with differing state-machines.
        self.prop_feature_state.update_proxy_with_introspected()
        states_descr = self.prop_feature_state.description
        try:
            states_descr = states_descr[states_descr.find('{'):states_descr.find('}')]  # Trim away anything beyond {}

            state_id_and_names: dict[int, str] = ast.literal_eval(states_descr)

            # Dynamic definition of enum types: https://docs.python.org/3/library/enum.html#functional-api
            type(self).FeatureStateEnum = enum.IntEnum(
                'FeatureStateEnum',
                {str(v).upper(): int(k) for k, v in state_id_and_names.items()},  # Note how enums invert the mapping
                module=__name__,
                qualname=type(self).__name__ + '.FeatureStateEnum'
            )
        except Exception:
            self.logger.error("Failed to parse description of FeatureState property. Can't introspect state values.")
