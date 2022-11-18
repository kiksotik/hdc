from __future__ import annotations

import logging
import threading
import typing
from collections import deque

from hdcproto.transport.base import TransportBase

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.transport.mock"


class MockTransport(TransportBase):
    """
    Pretends to be a transport, but simply keeps all sent messages in a buffer.
    It's main purpose is testing of Device and Host implementations.

    Might also be used to relay messages into other kinds of transports that may need to be fed with a spoon.
        e.g. https://datatracker.ietf.org/doc/html/rfc1149
    """
    outbound_messages: deque[bytes] | None
    inbound_messages: deque[bytes] | None
    reply_mocking: typing.Callable[[bytes], bytes] | None
    _writing_lock: threading.Lock
    _is_mock_connected: bool

    def __init__(self,
                 connection_url: str,
                 message_received_handler: typing.Callable[[bytes], None],
                 connection_lost_handler: typing.Callable[[Exception | None], None]):
        if not connection_url.lower().startswith('mock:'):
            raise ValueError(f"Connection URL '{connection_url}' is not supported by {self.__class__.__name__}")

        super().__init__(connection_url=connection_url,
                         message_received_handler=message_received_handler,
                         connection_lost_handler=connection_lost_handler)

        self.outbound_messages = None
        self.inbound_messages = None
        self.reply_mocking = None
        self._writing_lock = threading.Lock()
        self._is_mock_connected = False

    def connect(self) -> None:
        if self.is_connected:
            raise RuntimeError("Already connected")

        logger.info(f"Pretending to connect.")
        self.outbound_messages = deque()  # Discard any previous buffer of messages
        self.inbound_messages = deque()  # Discard any previous buffer of messages
        self._is_mock_connected = True

    @property
    def is_connected(self) -> bool:
        return self._is_mock_connected

    def send_message(self, message: bytes) -> None:
        if not self.is_connected:
            raise RuntimeError("Not connected")

        with self._writing_lock:
            self.outbound_messages.append(message)

        logger.info(f"Pretending to be sending a message. There's now {len(self.outbound_messages)} in the buffer.")

        if self.reply_mocking is None:
            return  # Skip remainder, which is only about mocking a reply

        logger.info(f"Mocking reception of a reply to the request message we just 'sent' ...")

        try:
            mocked_reply = self.reply_mocking(message)
        except Exception as e:
            self._is_mock_connected = False
            self.connection_lost_handler(e)
            return

        if isinstance(mocked_reply, (bytes, bytearray)):
            self.receive_message(mocked_reply)
        elif mocked_reply is not None:
            raise TypeError("Reply mocking callable must either return a bytes or a None result")

    def receive_message(self, message: bytes) -> None:
        if not self.is_connected:
            raise RuntimeError("Not connected")

        self.inbound_messages.append(message)
        self.message_received_handler(message)

    def flush(self) -> None:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        logger.info(f"Pretending to be flushing the inbound and outbound transmission of messages.")

    def close(self) -> None:
        """
        Stops the receiver-thread and close the serial port.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        logger.info(f"Pretending to disconnect.")
        # Not clearing in/outbound_messages buffers as a courtesy for unit-tests
        self._is_mock_connected = False
        self.connection_lost_handler(None)

    def __enter__(self) -> MockTransport:
        """Enter context handler. May raise RuntimeError in case the connection could not be created."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Leave context handler"""
        self.flush()
        self.close()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}('{self.connection_url}')"


########################
# Showcase this module

def showcase_mock_transport():
    def handle_message(message: bytes):
        # This is the handler we intend to scrutinize via the MockTransport hack
        print(f'Message handler received this message: {message}')

    def handle_lost_connection(exception):
        if exception:
            print(f'Disconnection handler received this exception: {exception}. '
                  f'Do some damage containment, if necessary.')
        else:
            print(f'Disconnection handler dealing with a normal disconnect. '
                  f'Do some house-keeping, if necessary.')

    with MockTransport(connection_url="mock://",
                       message_received_handler=handle_message,
                       connection_lost_handler=handle_lost_connection) as transport:
        assert transport.is_connected

        msg0 = b'Received messages will be passed to the handler that we intend to test.'
        transport.receive_message(msg0)
        assert len(transport.inbound_messages) == 1  # ... and also be kept in a log
        assert transport.inbound_messages[0] == msg0
        transport.inbound_messages.clear()  # We can clear the log, or popleft(), ...

        # The following lambda simulates/mocks a reaction to outbound messages, like those sent further below
        transport.reply_mocking = lambda req: b'pong' if req == b'ping' else None

        assert len(transport.outbound_messages) == 0
        msg1 = b'Sent messages can elicit a custom reply, as defined by the reply-mocking function.'
        transport.send_message(msg1)
        assert len(transport.outbound_messages) == 1
        assert transport.outbound_messages[0] == msg1
        assert len(transport.inbound_messages) == 0  # Mocking of replies ignored request, because it wasn't 'ping'
        #
        msg2 = b'ping'
        transport.send_message(msg2)
        assert len(transport.outbound_messages) == 2
        assert transport.outbound_messages[1] == msg2
        assert len(transport.inbound_messages) == 1  # Mocking of replies produced a 'pong' reply
        assert transport.inbound_messages[0] == b'pong'


if __name__ == '__main__':
    showcase_mock_transport()
