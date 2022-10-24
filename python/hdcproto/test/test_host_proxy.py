import unittest

import host.proxy
from common import ReplyErrorCode


class TestableDeviceProxy(host.proxy.DeviceProxyBase):
    pass


class TestReplyErrorCodeRegistration(unittest.TestCase):
    def setUp(self) -> None:
        my_device = TestableDeviceProxy(connection_url="loop:")
        self.some_command_proxy = my_device.core._cmd_get_property_value

    def test_predefined_replyerrorcode_which_is_not_yet_registered(self):
        replyerrorcode_not_yet_registered = ReplyErrorCode.UNKNOWN_EVENT
        try:
            self.some_command_proxy.register_error(replyerrorcode_not_yet_registered)
        except ValueError:
            self.fail("Failed to register predefined ReplyErrorCode!")

    def test_predefined_replyerrorcode_which_is_already_registered(self):
        replyerrorcode_already_registered = ReplyErrorCode.UNKNOWN_PROPERTY
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(replyerrorcode_already_registered)

    def test_custom_replyerrorcode_which_is_available(self):
        replyerrorcode_not_predefined_by_hdc = 0xDD
        try:
            self.some_command_proxy.register_error(replyerrorcode_not_predefined_by_hdc)
        except ValueError:
            self.fail("Failed to register custom ReplyErrorCode!")

    def test_custom_replyerrorcode_which_is_not_available(self):
        replyerrorcode_predefined_by_hdc = int(ReplyErrorCode.UNKNOWN_FEATURE)
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(replyerrorcode_predefined_by_hdc)

    def test_custom_replyerrorcode_which_is_below_valid_range(self):
        replyerrorcode_negative = -1
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(replyerrorcode_negative)

    def test_custom_replyerrorcode_which_is_beyond_valid_range(self):
        replyerrorcode_too_big = 256
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(replyerrorcode_too_big)


class TestIdValidation(unittest.TestCase):
    def test_validation_of_feature_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            host.proxy.FeatureProxyBase(my_device, feature_id=-1)

        with self.assertRaises(ValueError):
            host.proxy.FeatureProxyBase(my_device, feature_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            host.proxy.FeatureProxyBase(my_device, feature_id='42')

        # Does *not* fail with a valid feature_id
        host.proxy.FeatureProxyBase(my_device, feature_id=0x42)

    def test_validation_of_command_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            host.proxy.VoidWithoutArgsCommandProxy(my_device.core, command_id=-1)

        with self.assertRaises(ValueError):
            host.proxy.VoidWithoutArgsCommandProxy(my_device.core, command_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            host.proxy.VoidWithoutArgsCommandProxy(my_device.core, command_id='42')

        # Does *not* fail with a valid command_id
        host.proxy.VoidWithoutArgsCommandProxy(my_device.core, command_id=0x42)

    def test_validation_of_property_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            host.proxy.PropertyProxy_RW_INT32(my_device.core, property_id=-1)

        with self.assertRaises(ValueError):
            host.proxy.PropertyProxy_RW_INT32(my_device.core, property_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            host.proxy.PropertyProxy_RW_INT32(my_device.core, property_id='42')

        # Does *not* fail with a valid property_id
        host.proxy.PropertyProxy_RW_INT32(my_device.core, property_id=0x42)

    def test_validation_of_event_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            host.proxy.EventProxyBase(my_device.core, event_id=-1)

        with self.assertRaises(ValueError):
            host.proxy.EventProxyBase(my_device.core, event_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            host.proxy.EventProxyBase(my_device.core, event_id='42')

        # Does *not* fail with a valid event_id
        host.proxy.EventProxyBase(my_device.core, event_id=0x42)
