from __future__ import annotations

import typing

from hdcproto.device.router import MessageRouter as ServiceMessageRouter
from hdcproto.host.router import MessageRouter as ProxyMessageRouter
from hdcproto.transport.base import TransportBase
from hdcproto.validate import validate_custom_id


class TunnelTransport(TransportBase):
    tunnel_id: int
    parent_router: ServiceMessageRouter | ProxyMessageRouter

    def __init__(self,
                 tunnel_id: int,
                 tunnel_through_router: ServiceMessageRouter | ProxyMessageRouter):
        self.tunnel_id = validate_custom_id(tunnel_id)
        if not isinstance(tunnel_through_router, (ServiceMessageRouter, ProxyMessageRouter)):
            raise TypeError
        self.parent_router = tunnel_through_router

        self.message_received_handler = None
        self.connection_lost_handler = None

        if self.tunnel_id in self.parent_router.custom_message_handlers.keys():
            raise ValueError(f"Tunnel 0x{self.tunnel_id:02X} is already in use")

        self.parent_router.register_custom_message_handler(
            message_type_id=self.tunnel_id,
            message_handler=self._handle_message_as_received_by_parent_router)

    def _handle_message_as_received_by_parent_router(self, encapsulated_message: bytes):
        if self.tunnel_id != encapsulated_message[0]:
            raise RuntimeError(f"Expected message to be prefixed with TunnelID=0x{self.tunnel_id:02X}, but "
                               f"got forwarded a message whose first byte is 0x{encapsulated_message[0]:02X}")
        if self.message_received_handler is None:
            # Tunnel is currently disconnected, thus can't forward message
            return
        message = encapsulated_message[1:]
        self.message_received_handler(message)

    def connect(self,
                message_received_handler: typing.Callable[[bytes], None],
                connection_lost_handler: typing.Callable[[Exception | None], None]
                ) -> None:
        if self.is_connected:
            raise RuntimeError("Already connected")
        self.message_received_handler = message_received_handler
        self.connection_lost_handler = connection_lost_handler
        if not self.parent_router.is_connected:
            self.parent_router.connect()

    @property
    def is_connected(self) -> bool:
        return self.message_received_handler is not None and self.parent_router.is_connected

    def send_message(self, message: bytes) -> None:
        encapsulated_message = bytes([self.tunnel_id]) + message
        self.parent_router.transport.send_message(encapsulated_message)

    def flush(self) -> None:
        self.parent_router.transport.flush()

    def close(self) -> None:
        # Nothing to be done here.
        # WARNING: Do not close router through which we were tunneling, because it's a shared resource!
        self.connection_lost_handler(None)

        self.message_received_handler = None
        self.connection_lost_handler = None
