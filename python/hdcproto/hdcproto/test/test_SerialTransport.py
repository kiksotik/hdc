from __future__ import annotations

import typing
import unittest

from hdcproto.transport.serialport import SerialTransport


class TestableSerialTransport(SerialTransport):
    """
    We use the special 'loop://' feature implemented by pyserial to
    simultaneously test the sending and the receiving of messages via pyserial.
    """
    received_messages: list[bytes]
    connection_loss_exception: Exception | None

    def __init__(self):
        super().__init__(pyserial_url='loop://')
        self.received_messages = list()
        self.connection_loss_exception = None

    def __enter__(self) -> TestableSerialTransport:
        """Enter context handler."""
        self.connect(message_received_handler=self.handle_message,
                     connection_lost_handler=self.handle_connection_loss)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context handler"""
        self.flush()
        self.close()

    def handle_message(self, message: bytes):
        self.received_messages.append(message)

    def handle_connection_loss(self, e: Exception):
        self.connection_loss_exception = e


class TestMessageRoundTrip(unittest.TestCase):

    def assertEqualAfterRoundTrip(self, messages: typing.List[bytes]):
        with TestableSerialTransport() as transport:
            for message in messages:
                transport.send_message(message)

        self.assertSequenceEqual(messages, transport.received_messages)

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
    unittest.main()
