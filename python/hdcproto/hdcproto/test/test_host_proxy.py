import unittest

from hdcproto.common import CommandErrorCode
from hdcproto.host.proxy import (DeviceProxyBase, FeatureProxyBase, VoidWithoutArgsCommandProxy,
                                 PropertyProxy_RW_INT32, EventProxyBase)


class TestableDeviceProxy(DeviceProxyBase):
    pass


class TestCommandErrorCodeRegistration(unittest.TestCase):
    def setUp(self) -> None:
        my_device = TestableDeviceProxy(connection_url="loop:")
        self.some_command_proxy = my_device.core.cmd_get_property_value

    def test_predefined_code_which_is_not_yet_registered(self):
        code_not_yet_registered = CommandErrorCode.UNKNOWN_EVENT
        try:
            self.some_command_proxy.register_error(code_not_yet_registered)
        except ValueError:
            self.fail("Failed to register predefined CommandErrorCode!")

    def test_predefined_code_which_is_already_registered(self):
        code_already_registered = CommandErrorCode.UNKNOWN_PROPERTY
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(code_already_registered)

    def test_custom_code_which_is_available(self):
        code_not_predefined_by_hdc = 0xDD
        name = "My custom error name"
        try:
            self.some_command_proxy.register_error(code_not_predefined_by_hdc, error_name=name)
        except ValueError:
            self.fail("Failed to register custom CommandErrorCode!")
        self.assertEqual(self.some_command_proxy.known_command_error_codes[code_not_predefined_by_hdc], name)

    def test_custom_code_which_is_available_but_name_is_missing(self):
        code_not_predefined_by_hdc = 0xDD
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(code_not_predefined_by_hdc, error_name=None)

    def test_custom_code_which_is_available_but_name_is_empty(self):
        code_not_predefined_by_hdc = 0xDD
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(code_not_predefined_by_hdc, error_name="")

    def test_custom_code_which_is_not_available(self):
        code_predefined_by_hdc = int(CommandErrorCode.UNKNOWN_FEATURE)
        name = "My custom error name"
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(code_predefined_by_hdc, error_name=name)

    def test_custom_code_which_is_below_valid_range(self):
        code_negative = -1
        name = "My custom error name"
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(code_negative, error_name=name)

    def test_custom_code_which_is_beyond_valid_range(self):
        code_too_big = 256
        name = "My custom error name"
        with self.assertRaises(ValueError):
            self.some_command_proxy.register_error(code_too_big, error_name=name)


class TestIdValidation(unittest.TestCase):
    def test_validation_of_feature_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            FeatureProxyBase(my_device, feature_id=-1)

        with self.assertRaises(ValueError):
            FeatureProxyBase(my_device, feature_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            FeatureProxyBase(my_device, feature_id='42')

        # Does *not* fail with a valid feature_id
        FeatureProxyBase(my_device, feature_id=0x42)

    def test_validation_of_command_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            VoidWithoutArgsCommandProxy(my_device.core, command_id=-1)

        with self.assertRaises(ValueError):
            VoidWithoutArgsCommandProxy(my_device.core, command_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            VoidWithoutArgsCommandProxy(my_device.core, command_id='42')

        # Does *not* fail with a valid command_id
        VoidWithoutArgsCommandProxy(my_device.core, command_id=0x42)

    def test_validation_of_property_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            PropertyProxy_RW_INT32(my_device.core, property_id=-1)

        with self.assertRaises(ValueError):
            PropertyProxy_RW_INT32(my_device.core, property_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            PropertyProxy_RW_INT32(my_device.core, property_id='42')

        # Does *not* fail with a valid property_id
        PropertyProxy_RW_INT32(my_device.core, property_id=0x42)

    def test_validation_of_event_id(self):
        my_device = TestableDeviceProxy(connection_url="loop:")

        with self.assertRaises(ValueError):
            EventProxyBase(my_device.core, event_id=-1)

        with self.assertRaises(ValueError):
            EventProxyBase(my_device.core, event_id=256)

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            EventProxyBase(my_device.core, event_id='42')

        # Does *not* fail with a valid event_id
        EventProxyBase(my_device.core, event_id=0x42)


if __name__ == '__main__':
    unittest.main()
