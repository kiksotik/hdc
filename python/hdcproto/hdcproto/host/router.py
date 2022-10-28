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
    Plugs things together:
        - receiving and sending of raw bytes over a specific transport,
        - packing and unpacking of messages to/from a stream of raw bytes
        - routing of messages received from the device
        - sending of messages to the device
    Not to be confused with the Device-Proxy classes!
    """
    features: dict[int, RouterFeature]
    transport: TransportBase
    request_reply_lock: threading.Lock
    received_reply_event: threading.Event
    last_reply_message: bytes
    strict_event_handling: bool

    def __init__(self, transport: TransportBase):
        self.features = dict()
        self.transport = transport
        transport.message_received_handler = self.handle_message
        transport.connection_lost_handler = self.handle_lost_connection
        self.request_reply_lock = threading.Lock()
        self.received_reply_event = threading.Event()
        self.last_reply_message = bytes()
        self.strict_event_handling = False

    def connect(self):
        logger.info(f"Connecting via {self.transport}")
        self.transport.connect()

    def close(self):
        logger.info(f"Closing connection via {self.transport}")
        self.transport.close()

    def handle_lost_connection(self):
        logger.error(f"Lost connection via {self.transport}")
        raise NotImplementedError()

    def handle_message(self, message: bytes):
        """
        Executed within the ReceiverThread!
        Do not use this for message processing!
        This is just about receiving and signalling it to the main thread, where the actual processing will happen!
        """
        if len(message) == 0:
            return  # Ignore empty messages, for now!

        msg_type_id = message[0]

        if msg_type_id in [MessageTypeID.HDC_VERSION, MessageTypeID.ECHO, MessageTypeID.COMMAND]:
            self.handle_requested_reply(message)
        elif msg_type_id == MessageTypeID.EVENT:
            self.handle_event(message)
        else:
            # ToDo: Should we fail silently, instead, to be forward-compatible with future versions of HDC-spec?
            raise HdcError(f"Don't know how to handle MessageTypeID=0x{msg_type_id:02X}")

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

    def handle_event(self, message: bytes) -> None:
        feature_id = message[1]
        if feature_id not in self.features:
            event_id = message[2]
            if self.strict_event_handling:
                raise HdcError(f"EventID=0x{event_id:02X} raised by unknown FeatureID=0x{feature_id:02X}")
            else:
                logger.debug(f"Ignoring EventID=0x{event_id:02X} raised by unknown FeatureID=0x{feature_id:02X}")
                return

        self.features[feature_id].handle_event(message)

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


class RouterFeature:
    """
    This class is about everything the MessageRouter needs to know about a feature of a device.
    Not to be confused with the Feature-Proxy classes, which are meant as the actual API.
    """
    feature_id: int
    router: MessageRouter
    event_handlers: dict[int, typing.Callable[[bytes], None]]  # Handlers implemented on the proxy class

    def __init__(self, router: MessageRouter, feature_id: int):
        if not is_valid_uint8(feature_id):
            raise ValueError(f"feature_id value of {feature_id} is beyond valid range from 0x00 to 0xFF")
        self.event_handlers = dict()
        self.feature_id = feature_id
        self.router = router
        if feature_id in router.features:
            logger.warning(f"Re-registering a feature with ID {feature_id}")
        router.features[feature_id] = self

    def register_event_handler(self, event_id: int, event_handler: typing.Callable[[bytes], None]) -> None:
        if event_id in self.event_handlers:
            raise HdcError(f"Feature {self.feature_id} already has EventID {event_id}")
        self.event_handlers[event_id] = event_handler

    def handle_event(self, message: bytes):
        """
        Executed within the ReceiverThread!
        Do not use this for message processing!
        This is just about receiving and signalling it to the main thread, where the actual processing will happen!
        """
        event_id = message[2]
        if event_id not in self.event_handlers:
            if self.router.strict_event_handling:
                raise HdcError(f"Unknown EventID=0x{event_id:02X} raised by FeatureID=0x{self.feature_id:02X}")
            else:
                logger.debug(f"Ignoring EventID=0x{event_id:02X} "
                             f"raised by FeatureID=0x{self.feature_id:02X}")
                return

        event_handler = self.event_handlers[event_id]
        event_handler(message)
