"""
Message router of the HDC-host implementation
"""
from __future__ import annotations

import logging
import threading
import typing

from hdcproto.common import MessageTypeID, HdcError, is_valid_uint8
from hdcproto.transport.base import TransportBase

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.host.router"


class MessageRouter:
    """
    Interfaces the proxy-classes with the message transport:
        - Sending of request-messages to the device and block until reception
          of the corresponding reply, while considering a timeout.

        - Routing of event-messages received from the device
    """
    connection_url: str | None
    transport: TransportBase | None
    request_reply_lock: threading.Lock
    received_reply_event: threading.Event
    last_reply_message: bytes
    strict_event_handling: bool
    event_message_handlers: dict[typing.Tuple[int, int], typing.Callable[[bytes], None]]
    custom_message_handlers: dict[int, typing.Callable[[bytes], None]]

    def __init__(self, connection_url: str | None):
        self.connection_url = connection_url
        self.transport = None
        self.request_reply_lock = threading.Lock()
        self.received_reply_event = threading.Event()
        self.last_reply_message = bytes()
        self.strict_event_handling = False
        self.event_message_handlers = dict()
        self.custom_message_handlers = dict()

    @property
    def is_connected(self) -> bool:
        return self.transport is not None

    def connect(self, connection_url: str | None = None):
        if connection_url is None and self.connection_url is None:
            raise ValueError("No connection_url provided neither via constructor nor in this call.")

        if self.is_connected:
            raise RuntimeError("Already connected")

        if connection_url is not None:
            self.connection_url = connection_url
        transport_class = TransportBase.resolve_transport_class(connection_url=self.connection_url, is_server=False)
        self.transport = transport_class(connection_url=self.connection_url,
                                         message_received_handler=self._handle_message,
                                         connection_lost_handler=self._handle_lost_connection)
        logger.info(f"Connecting via {self.transport}")
        self.transport.connect()
        logger.debug("Connected")

    def close(self):
        if not self.is_connected:
            return

        logger.info(f"Closing connection via {self.transport}")
        self.transport.close()
        self.transport = None

    def _handle_lost_connection(self, exception: Exception):
        if exception:
            logger.exception(f"Lost connection via {self.transport}")
            raise exception  # ToDo: Should we re-raise it?
        else:
            logger.info(f"Lost connection via {self.transport} in an orderly manner.")

    def register_event_message_handler(self,
                                       feature_id: int,
                                       event_id: int,
                                       event_handler: typing.Callable[[bytes], None]) -> None:
        if not is_valid_uint8(feature_id):
            raise ValueError(f"feature_id value of {feature_id} is beyond valid range from 0x00 to 0xFF")
        if not is_valid_uint8(event_id):
            raise ValueError(f"event_id value of {event_id} is beyond valid range from 0x00 to 0xFF")
        key = (feature_id, event_id)
        if key in self.event_message_handlers:
            logger.warning(f"Replacing the event-message handler for "
                           f"FeatureID=0x{feature_id:02X} / EventID=0x{event_id:02X}")
        self.event_message_handlers[key] = event_handler

    def register_custom_message_handler(self,
                                        message_type_id: int,
                                        event_handler: typing.Callable[[bytes], None]) -> None:
        """
        Mainly intended for the tunneling of other protocols through the HDC connection, by encapsulating data into
        a custom message which the given handler will know how to de-encapsulate and re-route.
        Tunneling of other HDC connections can alternatively and more efficiently be done by MessageTypeID translation.

        Warning: Whenever a custom message type was explicitly requested via send_request_and_get_reply(), then
        its reply *must* be handled by _handle_requested_reply(), otherwise the former will time-out and fail.
        """
        if not is_valid_uint8(message_type_id):
            raise ValueError(f"message_type_id value of {message_type_id} is beyond valid range from 0x00 to 0xFF")
        if message_type_id in self.custom_message_handlers:
            logger.warning(f"Replacing the custom-message handler for MessageTypeID=0x{message_type_id:02X}")
        self.custom_message_handlers[message_type_id] = event_handler

    def send_request_and_get_reply(self, request_message: bytes, timeout: float) -> bytes:
        """
        Will send a request message and block until either a reply is received or the timeout elapses.

        Caller is responsible to validate the received reply.
        """
        # ToDo: Proper handling of time-outs, reading-frame-errors reported by device, post-time-out replies, ...

        # ToDo: We might need to make the following blocking=True with a timeout if the caller is multi-threaded.
        if not self.request_reply_lock.acquire(blocking=False):
            raise HdcError("Mustn't send a request if no reply was yet received for a preceding request")
        try:
            if self.received_reply_event.is_set():
                raise HdcError("Did not expect the received_reply_event to be signaled before sending a request")

            if self.transport is None:
                raise RuntimeError("Not connected")

            self.transport.send_message(request_message)

            if not self.received_reply_event.wait(timeout=timeout):
                raise TimeoutError(f'Did not receive any reply after {timeout} seconds.')

            self.received_reply_event.clear()

            return self.last_reply_message

        finally:
            self.request_reply_lock.release()

    def _handle_message(self, message: bytes):
        """
        Main routing of received messages of whatever kind.

        Warning: This will be executed from within the SerialTransport.receiver_thread
        """
        if len(message) == 0:
            return  # Ignore empty messages, for now!

        message_type_id = message[0]

        if message_type_id in [MessageTypeID.META, MessageTypeID.ECHO, MessageTypeID.COMMAND]:
            self._handle_requested_reply(message)
        elif message_type_id == MessageTypeID.EVENT:
            self._handle_event_message(message)
        elif MessageTypeID.is_custom(message_type_id=message_type_id):
            self._handle_custom_message(message)
        else:
            # ToDo: Should we fail silently, instead, to be forward-compatible with future versions of HDC-spec?
            raise HdcError(f"Don't know how to handle MessageTypeID=0x{message_type_id:02X}")

    def _handle_requested_reply(self, message: bytes):
        """
        Handler for any kind of reply-message that has been explicitly requested via send_request_and_get_reply()
           i.e.: VersionMessages, EchoMessages, CommandMessages

        Note how replies to Command-requests do not need to look up neither FeatureID nor CommandID, because
        whatever command issued the request is currently blocking and awaiting the received_reply_event.

        Warning: This will be executed from within the SerialTransport.receiver_thread
        """

        if not self.request_reply_lock.locked():
            # If the lock is not currently taken, then no-one is awaiting this reply (anymore)!
            # i.e. requester has meanwhile timed out
            # i.e. device sent a reply that we did not request (e.g. reconnecting to an active device)
            return

        self.last_reply_message = message
        self.received_reply_event.set()

    def _handle_event_message(self, message: bytes) -> None:
        """Warning: This will be executed from within the SerialTransport.receiver_thread"""
        feature_id = message[1]
        event_id = message[2]
        key = (feature_id, event_id)
        if key in self.event_message_handlers:
            return self.event_message_handlers[key](message)

        if self.strict_event_handling:
            raise HdcError(f"No event-message handler registered for "
                           f"FeatureID=0x{feature_id:02X} / EventID=0x{event_id:02X}")
        else:
            logger.debug(f"Ignoring event-message, because no handler has been registered for "
                         f"FeatureID=0x{feature_id:02X} / EventID=0x{event_id:02X}")
            return

    def _handle_custom_message(self, message: bytes) -> None:
        """Warning: This will be executed from within the SerialTransport.receiver_thread"""
        message_type_id = message[0]
        if message_type_id in self.custom_message_handlers:
            return self.custom_message_handlers[message_type_id](message)
        logger.warning(f"Ignoring custom-message, because no handler has been registered for "
                       f"MessageTypeID={message_type_id}")
