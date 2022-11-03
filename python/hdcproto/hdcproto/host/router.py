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
    transport: TransportBase
    request_reply_lock: threading.Lock
    received_reply_event: threading.Event
    last_reply_message: bytes
    strict_event_handling: bool
    event_message_handlers: dict[typing.Tuple[int, int], typing.Callable[[bytes], None]]

    def __init__(self, transport: TransportBase):
        self.transport = transport
        transport.message_received_handler = self.handle_message
        transport.connection_lost_handler = self.handle_lost_connection
        self.request_reply_lock = threading.Lock()
        self.received_reply_event = threading.Event()
        self.last_reply_message = bytes()
        self.strict_event_handling = False
        self.event_message_handlers = dict()

    def connect(self):
        logger.info(f"Connecting via {self.transport}")
        self.transport.connect()

    def close(self):
        logger.info(f"Closing connection via {self.transport}")
        self.transport.close()

    def register_event_message_handler(self,
                                       feature_id: int,
                                       event_id: int,
                                       event_handler: typing.Callable[[bytes], None]) -> None:
        if not is_valid_uint8(feature_id):
            raise ValueError(f"feature_id value of {feature_id} is beyond valid range from 0x00 to 0xFF")
        if not is_valid_uint8(event_id):
            raise ValueError(f"feature_id value of {event_id} is beyond valid range from 0x00 to 0xFF")
        key = (feature_id, event_id)
        if key in self.event_message_handlers:
            logger.warning(f"Replacing the event-message handler for "
                           f"FeatureID=0x{feature_id:02X} / EventID=0x{event_id:02X}")
        self.event_message_handlers[key] = event_handler

    def handle_lost_connection(self):
        logger.error(f"Lost connection via {self.transport}")
        raise NotImplementedError()

    def handle_message(self, message: bytes):
        """
        Executed within the ReceiverThread!
        """
        if len(message) == 0:
            return  # Ignore empty messages, for now!

        message_type_id = message[0]

        if message_type_id in [MessageTypeID.HDC_VERSION, MessageTypeID.ECHO, MessageTypeID.COMMAND]:
            self.handle_requested_reply(message)
        elif message_type_id == MessageTypeID.EVENT:
            self.handle_event_message(message)
        elif MessageTypeID.is_custom(message_type_id=message_type_id):
            self.handle_custom_message(message)
        else:
            # ToDo: Should we fail silently, instead, to be forward-compatible with future versions of HDC-spec?
            raise HdcError(f"Don't know how to handle MessageTypeID=0x{message_type_id:02X}")

    def handle_requested_reply(self, message: bytes):
        """
        Handler for any kind reply that has been explicitly requested,
           i.e.: VersionMessages, EchoMessages, CommandMessages

        Note how replies to Command-requests do not need to look up neither FeatureID nor CommandID, because
        whatever command issued the request is currently blocking and awaiting the received_reply_event.
        """
        # Note how we do

        if not self.request_reply_lock.locked():
            # If the lock is not currently taken, then no-one is awaiting this reply (anymore)!
            # i.e. requester has meanwhile timed out
            # i.e. device sent a reply that we did not request (e.g. reconnecting to an active device)
            return

        self.last_reply_message = message
        self.received_reply_event.set()

    def handle_event_message(self, message: bytes) -> None:
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

    # noinspection PyMethodMayBeStatic
    def handle_custom_message(self, message: bytes):
        """
        This method is meant to be overriden by derived classes
        that know the specifics of any custom message in a given application.

        If the message was explicitly requested via this MessageRouter, then it should
        be processed via the handle_requested_reply() method.
        """
        msg_type_id = message[0]
        logger.warning(f"Don't know how to handle MessageTypeID={msg_type_id} (nor any other custom ID)")

    def send_request_and_get_reply(self, request_message: bytes, timeout: float) -> bytes:

        # ToDo: We might need to make the following blocking=True with a timeout if the caller is multi-threaded.
        if not self.request_reply_lock.acquire(blocking=False):
            raise HdcError("Mustn't send a request if no reply was yet received for a preceding request")
        try:
            if self.received_reply_event.is_set():
                raise HdcError("Did not expect the received_reply_event to be signaled before sending a request")

            self.transport.send_message(request_message)

            if not self.received_reply_event.wait(timeout=timeout):
                raise TimeoutError(f'Did not receive any reply after {timeout} seconds.')

            self.received_reply_event.clear()

            return self.last_reply_message

        finally:
            self.request_reply_lock.release()
