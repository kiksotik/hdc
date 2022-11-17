from __future__ import annotations

import typing
from urllib.parse import urlparse, ParseResult


class TransportBase:
    """
    Base class of any transport capable to sending and receiving messages to/from a device.
    """
    connection_url: str
    message_received_handler: typing.Callable[[bytes], None]
    connection_lost_handler: typing.Callable[[Exception | None], None]

    def __init__(self,
                 connection_url: str,
                 message_received_handler: typing.Callable[[bytes], None],
                 connection_lost_handler: typing.Callable[[Exception | None], None]):
        self.connection_url = connection_url
        self.message_received_handler = message_received_handler
        self.connection_lost_handler = connection_lost_handler

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError()

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

    @classmethod
    def resolve_transport_class(cls,
                                connection_url: str | ParseResult,
                                is_server: bool = False) -> typing.Type[TransportBase]:
        if isinstance(connection_url, str):
            connection_url = urlparse(connection_url)

        if connection_url.scheme == "socket":
            if is_server:
                from hdcproto.transport.tcpserver import SocketServerTransport
                return SocketServerTransport
            else:  # ... is_client
                from hdcproto.transport.serialport import SerialTransport
                return SerialTransport
        elif connection_url.scheme == "mock":
            from hdcproto.transport.mock import MockTransport
            return MockTransport

        # Since pyserial can deal with device names like 'COM5' and linux device nodes
        # So we'll just use it as a catch-all fallback
        from hdcproto.transport.serialport import SerialTransport
        return SerialTransport
