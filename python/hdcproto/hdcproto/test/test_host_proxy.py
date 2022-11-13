from __future__ import annotations

import unittest

from hdcproto.common import CommandErrorCode, MessageTypeID, MetaID
from hdcproto.host.proxy import (DeviceProxyBase, FeatureProxyBase, VoidWithoutArgsCommandProxy,
                                 PropertyProxy_RW_INT32, EventProxyBase)
from hdcproto.transport.mock import MockTransport


class TestableDeviceProxy(DeviceProxyBase):
    def __init__(self):
        # Mock the transport-layer by connecting with the MockTransport class, which allows tests to
        # intercept any HDC-request messages emitted by the proxy classes that are under scrutiny.
        super().__init__(connection_url="mock://")


class TestConnection(unittest.TestCase):

    def test_connect_without_context(self):
        echo_payload = b'Just some arbitrary payload'
        my_proxy = TestableDeviceProxy()

        self.assertFalse(my_proxy.is_connected)
        with self.assertRaises(RuntimeError):
            my_proxy.get_echo(echo_payload, timeout=0.001)

        my_proxy.connect(connection_url="mock://")
        self.assertTrue(my_proxy.is_connected)
        conn_mock: MockTransport = my_proxy.router.transport
        self.assertTrue(len(conn_mock.outbound_messages) == 0)
        with self.assertRaises(TimeoutError):
            my_proxy.get_echo(echo_payload, timeout=0.001)
        self.assertTrue(len(conn_mock.outbound_messages) == 1)
        expected_request = bytes([MessageTypeID.ECHO]) + echo_payload
        self.assertEqual(expected_request, conn_mock.outbound_messages.pop())

        my_proxy.close()
        self.assertFalse(my_proxy.is_connected)
        with self.assertRaises(RuntimeError):
            my_proxy.get_echo(echo_payload, timeout=0.001)

    def test_connect_with_context(self):
        echo_payload = b'Just some arbitrary payload'
        my_proxy = TestableDeviceProxy()

        self.assertFalse(my_proxy.is_connected)
        with self.assertRaises(RuntimeError):
            my_proxy.get_echo(echo_payload, timeout=0.001)

        with my_proxy:
            self.assertTrue(my_proxy.is_connected)
            conn_mock: MockTransport = my_proxy.router.transport
            self.assertTrue(len(conn_mock.outbound_messages) == 0)
            with self.assertRaises(TimeoutError):
                my_proxy.get_echo(echo_payload, timeout=0.001)
            self.assertTrue(len(conn_mock.outbound_messages) == 1)
            expected_request = bytes([MessageTypeID.ECHO]) + echo_payload
            self.assertEqual(expected_request, conn_mock.outbound_messages.pop())

        self.assertFalse(my_proxy.is_connected)
        with self.assertRaises(RuntimeError):
            my_proxy.get_echo(echo_payload, timeout=0.001)


class TestMessages(unittest.TestCase):
    def setUp(self) -> None:
        self.my_proxy = TestableDeviceProxy()
        self.my_proxy.connect()
        self.conn_mock: MockTransport = self.my_proxy.router.transport

    def test_echo(self):
        self.conn_mock.reply_mocking = lambda req: req if req[0] == MessageTypeID.ECHO else None
        sent_payload = b'Just some arbitrary payload'
        received_payload = self.my_proxy.get_echo(sent_payload)
        self.assertEqual(sent_payload, received_payload)

    def test_meta_hdc_version(self):
        mocked_version = 'HDC 1.0.0-alpha.11'

        def reply_mocking(req: bytes) -> bytes | None:
            if req[0] == MessageTypeID.META and req[1] == MetaID.HDC_VERSION:
                return bytes([MessageTypeID.META, MetaID.HDC_VERSION]) + mocked_version.encode()

        self.conn_mock.reply_mocking = reply_mocking
        received_version_str = self.my_proxy.get_hdc_version_string()
        self.assertEqual(mocked_version, received_version_str)

    def test_meta_max_req(self):
        mocked_max_req = 128

        def reply_mocking(req: bytes) -> bytes | None:
            if req[0] == MessageTypeID.META and req[1] == MetaID.MAX_REQ:
                return bytes([MessageTypeID.META, MetaID.MAX_REQ]) + mocked_max_req.to_bytes(length=4,
                                                                                                 byteorder='little')

        self.conn_mock.reply_mocking = reply_mocking
        received_max_req = self.my_proxy.get_max_req_msg_size()
        self.assertEqual(mocked_max_req, received_max_req)

    def test_meta_idl_json(self):
        mocked_idl_json = '''
        {
            "version": "HDC 1.0.0-alpha.11",
            "MaxReq": 128,
            "features": []
        }
        '''

        def reply_mocking(req: bytes) -> bytes | None:
            if req[0] == MessageTypeID.META and req[1] == MetaID.IDL_JSON:
                return bytes([MessageTypeID.META, MetaID.IDL_JSON]) + mocked_idl_json.encode()

        self.conn_mock.reply_mocking = reply_mocking
        received_idl_json = self.my_proxy.get_idl_json()
        self.assertEqual(mocked_idl_json, received_idl_json)


class TestCommandErrorCodeRegistration(unittest.TestCase):
    def setUp(self) -> None:
        my_device = TestableDeviceProxy()
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
        my_device = TestableDeviceProxy()

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
        my_device = TestableDeviceProxy()

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
        my_device = TestableDeviceProxy()

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
        my_device = TestableDeviceProxy()

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
