import unittest

from common import ReplyErrorCode
import host.proxy


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

