from __future__ import annotations

import typing


class TransportBase:
    """
    Base class of any transport capable to sending and receiving messages to/from a device.
    """

    message_received_handler: typing.Callable[[bytes], None] | None
    connection_lost_handler: typing.Callable[[Exception], None] | None

    def __init__(self,
                 message_received_handler: typing.Callable[[bytes], None] | None = None,
                 connection_lost_handler: typing.Callable[[Exception], None] | None = None):
        self.message_received_handler = message_received_handler
        self.connection_lost_handler = connection_lost_handler

    def connect(self) -> None:
        raise NotImplementedError()

    def send_message(self, message: bytes) -> None:
        """Transmits a chunk of raw bytes to the device"""
        raise NotImplementedError()

    def flush(self) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        raise NotImplementedError()

    def __str__(self) -> str:
        raise NotImplementedError()
