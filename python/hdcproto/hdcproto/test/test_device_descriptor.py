import enum
import json
import logging
import unittest

from hdcproto.common import (MessageTypeID, FeatureID, EvtID, CmdID, PropID, CommandErrorCode, MetaID, HDC_VERSION)
from hdcproto.device.descriptor import DeviceDescriptorBase, CoreFeatureDescriptorBase
from hdcproto.transport.mock import MockTransport


class TestableDeviceDescriptor(DeviceDescriptorBase):
    def __init__(self):
        # Mock the transport-layer by connecting with the MockTransport class, which allows tests to
        # intercept any HDC-request messages emitted by the proxy classes that are under scrutiny.
        super().__init__(connection_url="mock://",
                         device_name="TestDeviceMockup",
                         device_version="0.0.42",
                         device_description="",
                         core_feature_descriptor_class=TestableCoreDescriptor)


class TestableCoreDescriptor(CoreFeatureDescriptorBase):
    def __init__(self, device_descriptor: DeviceDescriptorBase):
        super().__init__(device_descriptor=device_descriptor, feature_states=self.States)

    @enum.unique
    class States(enum.IntEnum):
        OFF = 0x00
        INIT = 0x01
        READY = 0x02
        ERROR = 0xFF


class TestConnection(unittest.TestCase):
    def test_connect_without_context(self):
        my_device = TestableDeviceDescriptor()

        self.assertFalse(my_device.is_connected)
        log_text = "Hello there!"
        with self.assertRaises(RuntimeError):
            my_device.core.evt_log.emit(logging.ERROR, log_text)

        my_device.connect(connection_url="mock://")
        self.assertTrue(my_device.is_connected)
        conn_mock: MockTransport = my_device.router.transport
        self.assertFalse(conn_mock.outbound_messages)
        my_device.core.evt_log.emit(logging.ERROR, log_text)
        self.assertTrue(len(conn_mock.outbound_messages) == 1)
        expected_evt_msg = bytes([MessageTypeID.EVENT, FeatureID.CORE, EvtID.LOG, logging.ERROR])
        expected_evt_msg += log_text.encode(encoding='utf-8')
        self.assertEqual(expected_evt_msg, conn_mock.outbound_messages.pop())

        my_device.close()
        self.assertFalse(my_device.is_connected)
        with self.assertRaises(RuntimeError):
            my_device.core.evt_log.emit(logging.ERROR, log_text)

    def test_connect_with_context(self):
        my_device = TestableDeviceDescriptor()

        self.assertFalse(my_device.is_connected)
        log_text = "Hello there!"
        with self.assertRaises(RuntimeError):
            my_device.core.evt_log.emit(logging.ERROR, log_text)

        with my_device:
            self.assertTrue(my_device.is_connected)
            conn_mock: MockTransport = my_device.router.transport
            self.assertFalse(conn_mock.outbound_messages)
            my_device.core.evt_log.emit(logging.ERROR, log_text)
            self.assertTrue(len(conn_mock.outbound_messages) == 1)
            expected_evt_msg = bytes([MessageTypeID.EVENT, FeatureID.CORE, EvtID.LOG, logging.ERROR])
            expected_evt_msg += log_text.encode(encoding='utf-8')
            self.assertEqual(expected_evt_msg, conn_mock.outbound_messages.pop())

        self.assertFalse(my_device.is_connected)
        with self.assertRaises(RuntimeError):
            my_device.core.evt_log.emit(logging.ERROR, log_text)


class TestMessages(unittest.TestCase):
    def setUp(self) -> None:
        self.my_device = TestableDeviceDescriptor()
        self.my_device.connect()
        self.conn_mock: MockTransport = self.my_device.router.transport

    def test_meta_hdc_version(self):
        cmd_req = bytes([MessageTypeID.META, MetaID.HDC_VERSION])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.META, MetaID.HDC_VERSION])
        expected_reply += HDC_VERSION.encode(encoding='utf-8', errors='strict')
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_meta_max_req(self):
        cmd_req = bytes([MessageTypeID.META, MetaID.MAX_REQ])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.META, MetaID.MAX_REQ])
        expected_reply += self.my_device.router.max_req_msg_size.to_bytes(length=4, byteorder='little')
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_meta_idl_json(self):
        cmd_req = bytes([MessageTypeID.META, MetaID.IDL_JSON])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        self.assertSequenceEqual(cmd_req, received_reply[:2])
        idl_json = received_reply[2:]
        json.loads(idl_json)  # Test whether it's valid JSON syntax.
        # ToDo: Validate IDL-JSON produced by Python descriptors with a JSON-Schema grammar.


class TestCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.my_device = TestableDeviceDescriptor()
        self.my_device.connect()
        self.conn_mock: MockTransport = self.my_device.router.transport

    def test_get_property_value(self):
        self.my_device.core.log_event_threshold = logging.WARNING
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE,
                         CmdID.GET_PROP_VALUE, PropID.LOG_EVT_THRESHOLD])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE,
                                CmdID.GET_PROP_VALUE, CommandErrorCode.NO_ERROR, logging.WARNING])
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_set_property_value(self):
        self.my_device.core.log_event_threshold = logging.WARNING
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE,
                         CmdID.SET_PROP_VALUE, PropID.LOG_EVT_THRESHOLD, logging.INFO])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE,
                                CmdID.SET_PROP_VALUE, CommandErrorCode.NO_ERROR, logging.INFO])
        self.assertSequenceEqual(expected_reply, received_reply)
        self.assertEqual(self.my_device.core.log_event_threshold, logging.INFO)


class TestCommandErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.my_device = TestableDeviceDescriptor()
        self.my_device.connect()
        self.conn_mock: MockTransport = self.my_device.router.transport

    def test_unknown_feature(self):
        bogus_feature_id = 0x42
        cmd_req = bytes([MessageTypeID.COMMAND, bogus_feature_id, CmdID.GET_PROP_VALUE, PropID.LOG_EVT_THRESHOLD])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes(
            [MessageTypeID.COMMAND, bogus_feature_id, CmdID.GET_PROP_VALUE, CommandErrorCode.UNKNOWN_FEATURE])
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_unknown_command(self):
        bogus_cmd_id = 0x42
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, bogus_cmd_id, PropID.LOG_EVT_THRESHOLD])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes(
            [MessageTypeID.COMMAND, FeatureID.CORE, bogus_cmd_id, CommandErrorCode.UNKNOWN_COMMAND])
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_missing_command_arguments(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_VALUE])  # Omitting PropID argument!
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_VALUE,
                                CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS])

        self.assertSequenceEqual(expected_reply, received_reply[:4])

    def test_excess_command_arguments(self):
        unexpected_argument = 0x42
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_VALUE,
                         PropID.LOG_EVT_THRESHOLD, unexpected_argument])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_VALUE,
                                CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS])

        self.assertSequenceEqual(expected_reply, received_reply[:4])


class TestEvents(unittest.TestCase):
    def setUp(self) -> None:
        self.my_device = TestableDeviceDescriptor()
        self.my_device.connect()
        self.conn_mock: MockTransport = self.my_device.router.transport

    def test_log_event(self):
        log_text = "This is a warning"
        self.my_device.core.log_event_threshold = logging.WARNING
        self.my_device.core.hdc_logger.warning(log_text)
        sent_msg = self.conn_mock.outbound_messages.pop()
        expected_msg = bytes([MessageTypeID.EVENT, FeatureID.CORE, EvtID.LOG,
                              logging.WARNING]) + log_text.encode(encoding='utf-8')
        self.assertEqual(expected_msg, sent_msg)

    def test_log_event_suppression(self):
        log_text = "This is a warning"
        self.my_device.core.log_event_threshold = logging.WARNING
        self.my_device.core.hdc_logger.info(log_text)  # <--- INFO is less than WARNING
        self.assertFalse(self.conn_mock.outbound_messages)  # Should suppress it

    def test_feature_state_transition_event(self):
        previous_state_id = self.my_device.core.feature_state_id
        new_feature_state_id = TestableCoreDescriptor.States.READY  # Arbitrary
        self.my_device.core.feature_state_transition(new_feature_state_id)
        sent_msg = self.conn_mock.outbound_messages.pop()
        expected_msg = bytes([MessageTypeID.EVENT, FeatureID.CORE, EvtID.FEATURE_STATE_TRANSITION,
                              previous_state_id, new_feature_state_id])
        self.assertEqual(expected_msg, sent_msg)
