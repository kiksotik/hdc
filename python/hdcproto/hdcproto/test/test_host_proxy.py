from __future__ import annotations

import unittest

from hdcproto.descriptor import FeatureDescriptor
from hdcproto.exception import HdcCmdException, HdcCmdExc_UnknownProperty
from hdcproto.host.proxy import (DeviceProxyBase, FeatureProxyBase, )
from hdcproto.spec import (ExcID, MessageTypeID, MetaID, PropID, FeatureID, CmdID)
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
        mocked_version = 'HDC 1.0.0-alpha.12'

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
            "version": "HDC 1.0.0-alpha.12",
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


class TestExceptionConstructor(unittest.TestCase):

    def test_normal_case_without_message(self):
        exc_id = 0xDD
        exc_name = "MyName"
        exc = HdcCmdException(id=0xDD,
                              name="MyName")
        self.assertEqual(exc.exception_name, exc_name)
        self.assertEqual(exc.exception_id, exc_id)
        self.assertIsNone(exc.exception_message)

    def test_normal_case_with_message(self):
        exc_id = 0xDD
        exc_name = "MyName"
        exc_msg = "This is a text message."
        exc = HdcCmdException(id=0xDD,
                              name="MyName",
                              exception_message=exc_msg)
        self.assertEqual(exc.exception_name, exc_name)
        self.assertEqual(exc.exception_id, exc_id)
        self.assertEqual(exc.exception_message, exc_msg)

    def test_custom_code_which_is_below_valid_range(self):
        with self.assertRaises(ValueError):
            HdcCmdException(id=-1,
                            name="MyName")

    def test_custom_code_which_is_beyond_valid_range(self):
        with self.assertRaises(ValueError):
            HdcCmdException(id=256,
                            name="MyName")

    # ToDo: Test for invalid names, once HDC-spec settles for a naming style.
    def test_custom_code_which_is_available_but_name_is_missing(self):
        with self.assertRaises(ValueError):
            HdcCmdException(id=256,
                            name=None)

        with self.assertRaises(ValueError):
            HdcCmdException(id=256,
                            name="")


class TestExceptionCloning(unittest.TestCase):

    def test_cloning_baseclass(self):
        custom_exc_id = 0xDD
        exc_descriptor = HdcCmdException(id=0xDD,
                                         name="MyName")
        exception_text = "Text message brought as payload by the HDC-error-message"
        mocked_hdc_error_msg = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_VALUE, custom_exc_id])
        mocked_hdc_error_msg += exception_text.encode()

        exc_clone = exc_descriptor.clone_with_hdc_message(mocked_hdc_error_msg)

        self.assertIsNot(exc_clone, exc_descriptor)
        self.assertIsInstance(exc_clone, HdcCmdException)
        self.assertEqual(exc_clone.exception_id, exc_descriptor.exception_id)
        self.assertEqual(exc_clone.exception_name, exc_descriptor.exception_name)
        self.assertEqual(exc_clone.exception_message, exception_text)

    def test_cloning_custom_class(self):
        custom_exc_id = 0xDD
        custom_exc_name = "MyExc"

        class MyCustomExceptionClass(HdcCmdException):
            def __init__(self, txt_msg=None):
                super().__init__(id=custom_exc_id, name=custom_exc_name, exception_message=txt_msg)

        exc_descriptor = MyCustomExceptionClass()
        exception_text = "Text message brought as payload by the HDC-error-message"
        mocked_hdc_error_msg = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_VALUE, custom_exc_id])
        mocked_hdc_error_msg += exception_text.encode()

        exc_clone = exc_descriptor.clone_with_hdc_message(mocked_hdc_error_msg)

        self.assertIsNot(exc_clone, exc_descriptor)
        self.assertIsInstance(exc_clone, MyCustomExceptionClass)
        self.assertEqual(exc_clone.exception_id, exc_descriptor.exception_id)
        self.assertEqual(exc_clone.exception_name, exc_descriptor.exception_name)
        self.assertEqual(exc_clone.exception_message, exception_text)


class TestExceptionHandling(unittest.TestCase):
    def setUp(self) -> None:
        self.my_proxy = TestableDeviceProxy()
        self.my_proxy.core = FeatureProxyBase(
            feature_descriptor=FeatureDescriptor(
                id=FeatureID.CORE,
                name="core",
                cls="DontCare",  # ToDo: Attribute optionality. #25
            ),
            device_proxy=self.my_proxy)
        self.some_command_proxy = self.my_proxy.core.cmd_get_property_value
        self.my_proxy.connect()
        self.conn_mock: MockTransport = self.my_proxy.router.transport

    def test_raises_predefined_exception(self):
        predefined_exc_id = ExcID.UnknownProperty
        mocked_exc_text = "Terrible!"
        self.assertTrue(predefined_exc_id in self.some_command_proxy.command_descriptor.raises.keys())

        def reply_mocking(req: bytes) -> bytes | None:
            if req[:3] == self.some_command_proxy.msg_prefix:
                return self.some_command_proxy.msg_prefix + bytes([predefined_exc_id]) + mocked_exc_text.encode()

        self.conn_mock.reply_mocking = reply_mocking

        with self.assertRaises(HdcCmdExc_UnknownProperty) as cm:
            self.some_command_proxy(property_id=PropID.LOG_EVT_THRESHOLD)

        raised_exception = cm.exception
        self.assertEqual(mocked_exc_text, raised_exception.exception_message)

    def test_raises_custom_exception(self):
        custom_exc_id = 0x42
        custom_exc_name = "MY_EXCEPTION"
        mocked_exc_text = "Terrible!"

        class MyCustomException(HdcCmdException):
            def __init__(self, exception_message=None):
                super().__init__(id=custom_exc_id,
                                 name=custom_exc_name,
                                 exception_message=exception_message)

        # Inject custom exception instance as a descriptor into the command_descriptor
        custom_exception = MyCustomException()
        self.some_command_proxy.command_descriptor.raises[custom_exception.exception_id] = custom_exception

        def reply_mocking(req: bytes) -> bytes | None:
            if req[:3] == self.some_command_proxy.msg_prefix:
                return self.some_command_proxy.msg_prefix + bytes([custom_exc_id]) + mocked_exc_text.encode()

        self.conn_mock.reply_mocking = reply_mocking

        with self.assertRaises(MyCustomException) as cm:
            self.some_command_proxy(property_id=PropID.LOG_EVT_THRESHOLD)

        raised_exception = cm.exception
        self.assertEqual(custom_exc_id, raised_exception.exception_id)
        self.assertEqual(custom_exc_name, raised_exception.exception_name)
        self.assertEqual(mocked_exc_text, raised_exception.exception_message)


if __name__ == '__main__':
    unittest.main()
