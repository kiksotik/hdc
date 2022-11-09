from __future__ import annotations

import logging
import time
import typing
import unittest

from hdcproto.transport.serialport import SerialTransport
from hdcproto.transport.tcpserver import SocketServerTransport

CONNECTION_URL = "socket://localhost:55555"


logger = logging.getLogger(__name__)


class EchoingTcpServerTransport(SocketServerTransport):
    def __init__(self):
        super().__init__(connection_url=CONNECTION_URL,
                         message_received_handler=self.handle_message,
                         connection_lost_handler=self.handle_connection_loss)

    def handle_message(self, message: bytes):
        self.send_message(message)  # Echo received message back to the client who sent it.
        logger.info(f"Server received one message and echoed it back to the client.")

    def handle_connection_loss(self, e: Exception):
        logger.info(f"Server lost connection to client.")
        if e:
            raise e  # Re-raise exception


class TcpClientTransport(SerialTransport):
    received_messages: list[bytes]

    def __init__(self):
        super().__init__(connection_url=CONNECTION_URL,
                         message_received_handler=self.handle_message,
                         connection_lost_handler=self.handle_connection_loss)
        self.received_messages = list()
        self.logger = logging.getLogger(self.__class__.__name__)

    def handle_message(self, message: bytes):
        self.received_messages.append(message)
        logger.info(f"Client received one message. There's now {len(self.received_messages)} in the buffer.")

    def handle_connection_loss(self, e: Exception):
        logger.info(f"Client lost connection to server.")
        if e:
            raise e  # Re-raise exception


class TestMessageRoundTrip(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.INFO)
        logger.setLevel(logging.INFO)

    def assertEqualAfterRoundTrip(self, messages: typing.List[bytes]):
        with EchoingTcpServerTransport() as server:
            with TcpClientTransport() as client:
                for message in messages:
                    client.send_message(message)
                client.flush()  # Wait for transmission to complete
                server.flush()  # Wait for reception and echoing back to complete
                time.sleep(0.01)
                client.flush()  # Wait for reception to complete

                self.assertSequenceEqual(messages, client.received_messages)

    def test_one_empty_message(self):
        self.assertEqualAfterRoundTrip([b''])

    def test_two_empty_messages(self):
        self.assertEqualAfterRoundTrip([b'', b''])

    def test_one_1byte_message(self):
        self.assertEqualAfterRoundTrip([b'\x00'])

    def test_two_1byte_messages(self):
        self.assertEqualAfterRoundTrip([b'\x00', b'\x00'])

    def test_one_254byte_message(self):
        self.assertEqualAfterRoundTrip([bytes(range(254))])

    def test_two_254byte_messages(self):
        self.assertEqualAfterRoundTrip([bytes(range(254)), bytes(range(254))])

    def test_one_255byte_message(self):
        self.assertEqualAfterRoundTrip([bytes(range(255))])

    def test_two_255byte_messages(self):
        self.assertEqualAfterRoundTrip([bytes(range(255)), bytes(range(255))])

    def test_one_256byte_message(self):
        self.assertEqualAfterRoundTrip([bytes(range(256))])

    def test_two_256byte_messages(self):
        self.assertEqualAfterRoundTrip([bytes(range(256)), bytes(range(256))])

    def test_one_2000byte_message(self):
        self.assertEqualAfterRoundTrip([bytes(i % 255 for i in range(2000))])

    def test_two_2000byte_messages(self):
        self.assertEqualAfterRoundTrip([bytes(i % 255 for i in range(2000)), bytes(i % 255 for i in range(2000))])

    def test_hundred_60byte_messages(self):
        self.assertEqualAfterRoundTrip([bytes(range(60))] * 100)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
