import logging
import unittest

from hdcproto.common import MessageTypeID, FeatureID, EvtID, CmdID, PropID, CommandErrorCode, HdcDataType
from hdcproto.device.descriptor import DeviceDescriptorBase
from hdcproto.transport.mock import MockTransport


class TestableDeviceDescriptor(DeviceDescriptorBase):
    def __init__(self):
        # Mock the transport-layer by connecting with the MockTransport class, which allows tests to
        # intercept any HDC-request messages emitted by the proxy classes that are under scrutiny.
        super().__init__(connection_url="mock://")


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


class TestCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.my_device = TestableDeviceDescriptor()
        self.my_device.connect()
        self.conn_mock: MockTransport = self.my_device.router.transport

    def test_get_property_name(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_NAME, PropID.LOG_EVT_THRESHOLD])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_NAME, CommandErrorCode.NO_ERROR])
        expected_reply += 'LogEventThreshold'.encode(encoding='utf-8')
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_get_property_type(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_TYPE, PropID.LOG_EVT_THRESHOLD])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_TYPE,
                                CommandErrorCode.NO_ERROR, HdcDataType.UINT8])
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_get_property_readonly(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_RO, PropID.LOG_EVT_THRESHOLD])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_RO,
                                CommandErrorCode.NO_ERROR, int(False)])
        self.assertSequenceEqual(expected_reply, received_reply)

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

    def test_get_command_name(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_CMD_NAME, CmdID.GET_PROP_NAME])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_CMD_NAME, CommandErrorCode.NO_ERROR])
        expected_reply += 'GetPropertyName'.encode(encoding='utf-8')
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_get_command_description(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_CMD_DESCR, CmdID.GET_PROP_NAME])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_CMD_DESCR, CommandErrorCode.NO_ERROR])
        expected_reply += '(UINT8 PropertyID) -> UTF8 Name'.encode(encoding='utf-8')
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_get_event_name(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_EVT_NAME, EvtID.FEATURE_STATE_TRANSITION])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_EVT_NAME, CommandErrorCode.NO_ERROR])
        expected_reply += 'FeatureStateTransition'.encode(encoding='utf-8')
        self.assertSequenceEqual(expected_reply, received_reply)

    def test_get_event_description(self):
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_EVT_DESCR, EvtID.FEATURE_STATE_TRANSITION])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_EVT_DESCR, CommandErrorCode.NO_ERROR])
        expected_reply += '(UINT8 PreviousStateID, UINT8 CurrentStateID)'.encode(encoding='utf-8')
        self.assertSequenceEqual(expected_reply, received_reply)


class TestCommandErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.my_device = TestableDeviceDescriptor()
        self.my_device.connect()
        self.conn_mock: MockTransport = self.my_device.router.transport

    def test_unknown_feature(self):
        bogus_feature_id = 0x42
        cmd_req = bytes([MessageTypeID.COMMAND, bogus_feature_id, CmdID.GET_PROP_NAME, PropID.LOG_EVT_THRESHOLD])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes(
            [MessageTypeID.COMMAND, bogus_feature_id, CmdID.GET_PROP_NAME, CommandErrorCode.UNKNOWN_FEATURE])
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
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_NAME])  # Omitting PropID argument!
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_NAME,
                                CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS])
        expected_reply += "Payload is shorter than expected.".encode(encoding='utf-8')

        self.assertSequenceEqual(expected_reply, received_reply)

    def test_excess_command_arguments(self):
        unexpected_argument = 0x42
        cmd_req = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_NAME,
                         PropID.FEAT_NAME, unexpected_argument])
        self.conn_mock.receive_message(cmd_req)
        received_reply = self.conn_mock.outbound_messages.pop()
        expected_reply = bytes([MessageTypeID.COMMAND, FeatureID.CORE, CmdID.GET_PROP_NAME,
                                CommandErrorCode.INCORRECT_COMMAND_ARGUMENTS])
        expected_reply += "Payload is longer than expected.".encode(encoding='utf-8')

        self.assertSequenceEqual(expected_reply, received_reply)


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
        new_feature_state_id = previous_state_id + 3  # Arbitrary
        self.my_device.core.feature_state_transition(new_feature_state_id)
        sent_msg = self.conn_mock.outbound_messages.pop()
        expected_msg = bytes([MessageTypeID.EVENT, FeatureID.CORE, EvtID.FEATURE_STATE_TRANSITION,
                              previous_state_id, new_feature_state_id])
        self.assertEqual(expected_msg, sent_msg)
