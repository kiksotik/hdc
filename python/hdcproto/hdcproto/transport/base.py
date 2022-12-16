from __future__ import annotations

import typing


class TransportBase:
    """
    Base class of any transport capable of sending and receiving messages to/from a device.
    """
    message_received_handler: typing.Callable[[bytes], None] | None
    connection_lost_handler: typing.Callable[[Exception | None], None] | None

    @property
    def is_connected(self) -> bool:
        raise NotImplementedError()

    def connect(self,
                message_received_handler: typing.Callable[[bytes], None],
                connection_lost_handler: typing.Callable[[Exception | None], None]
                ) -> None:
        raise NotImplementedError()

    def send_message(self, message: bytes) -> None:
        """Transmits a chunk of raw bytes to the device"""
        raise NotImplementedError()

    def flush(self) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        raise NotImplementedError()

    @staticmethod
    def transport_factory(transport_url: str,
                          is_server: bool) -> TransportBase:
        if '://' in transport_url:
            url_scheme = transport_url.split('://')[0]
        else:
            url_scheme = None

        if url_scheme == "socket":
            if is_server:
                from hdcproto.transport.tcpserver import SocketServerTransport
                return SocketServerTransport.from_url(transport_url=transport_url)
            else:  # ... is_client
                from hdcproto.transport.serialport import SerialTransport
                return SerialTransport(pyserial_url=transport_url)
        elif url_scheme == "mock":
            from hdcproto.transport.mock import MockTransport
            return MockTransport()

        # Since pyserial can deal with device names like 'COM5' and linux device nodes
        # So we'll just use it as a catch-all fallback
        from hdcproto.transport.serialport import SerialTransport
        return SerialTransport(pyserial_url=str(transport_url))
