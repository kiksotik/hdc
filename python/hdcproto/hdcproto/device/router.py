"""
Message router of the HDC-device implementation
"""
from __future__ import annotations

import logging
import typing

from hdcproto.common import MessageTypeID, is_valid_uint8, CommandErrorCode, HDC_VERSION
from hdcproto.transport.base import TransportBase

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.device.router"


class MessageRouter:
    """
    Interfaces the proxy-classes with the message transport:
        - Sending of request-messages to the device and block until reception
          of the corresponding reply, while considering a timeout.

        - Routing of event-messages received from the device
    """
    transport: TransportBase
    pending_request_message: bytes | None
    command_request_handlers: dict[typing.Tuple[int, int], typing.Callable[[bytes], None]]
    custom_message_handlers: dict[int, typing.Callable[[bytes], None]]

    def __init__(self, transport: TransportBase):
        self.transport = transport
        transport.message_received_handler = self._handle_message
        transport.connection_lost_handler = self._handle_lost_connection
        self.pending_request_message = None
        self.command_request_handlers = dict()
        self.custom_message_handlers = dict()

    def connect(self):
        logger.info(f"Connecting via {self.transport}")
        self.transport.connect()

    def close(self):
        logger.info(f"Closing connection via {self.transport}")
        self.transport.close()

    def _handle_lost_connection(self):
        logger.error(f"Lost connection via {self.transport}")
        raise NotImplementedError()

    def register_command_request_handler(self,
                                         feature_id: int,
                                         command_id: int,
                                         command_request_handler: typing.Callable[[bytes], None]) -> None:
        """
        Each handler is responsible to reply via MessageRouter.send_reply_for_pending_request().
        Otherwise, this router will refuse to process any further requests.

        Warning: Handlers will be called directly from within the SerialTransport.receiver_thread
                 It's up to each individual handler to either reply straight away from within said thread, or
                 to delay its reply into another context, i.e. main application thread.
        """
        if not is_valid_uint8(feature_id):
            raise ValueError(f"feature_id value of {feature_id} is beyond valid range from 0x00 to 0xFF")
        if not is_valid_uint8(command_id):
            raise ValueError(f"command_id value of {command_id} is beyond valid range from 0x00 to 0xFF")
        key = (feature_id, command_id)
        if key in self.command_request_handlers:
            logger.warning(f"Replacing the event-message handler for "
                           f"FeatureID=0x{feature_id:02X} / CommandID=0x{command_id:02X}")
        self.command_request_handlers[key] = command_request_handler

    def register_custom_message_handler(self,
                                        message_type_id: int,
                                        event_handler: typing.Callable[[bytes], None]) -> None:
        """
        Mainly intended for the tunneling of other protocols through the HDC connection, by encapsulating data into
        a custom message which the given handler will know how to de-encapsulate and re-route.
        Tunneling of other HDC connections can alternatively and more efficiently be done by MessageTypeID translation.

        Although custom messages are exempt from obeying the strict Request-Reply sequence which HDC-spec mandates for
        any other kind of message type, it's the application's responsibility to
        """
        if not is_valid_uint8(message_type_id):
            raise ValueError(f"message_type_id value of {message_type_id} is beyond valid range from 0x00 to 0xFF")
        if message_type_id in self.custom_message_handlers:
            logger.warning(f"Replacing the custom-message handler for MessageTypeID=0x{message_type_id:02X}")
        self.custom_message_handlers[message_type_id] = event_handler

    def send_event_message(self, event_message: bytes) -> None:
        assert event_message[0] == MessageTypeID.EVENT
        self.transport.send_message(event_message)

    def send_reply_for_pending_request(self, reply_message: bytes) -> None:
        """
        Will send a reply message and release the lock on reception of further requests.
        """
        if self.pending_request_message is None:
            # Raise an exception, because Device implementation is to blame for this
            raise RuntimeError("Mustn't send a reply if no request is pending to be replied to")

        self.pending_request_message = None
        self.transport.send_message(reply_message)

    def _handle_message(self, message: bytes) -> None:
        """
        Main routing of received messages of whatever kind.

        Warning: This will be executed from within the SerialTransport.receiver_thread
        """
        if len(message) == 0:
            return  # Ignore empty messages, for now!

        message_type_id = message[0]

        if MessageTypeID.is_custom(message_type_id=message_type_id):
            self._handle_custom_message(message)
            return

        # Only custom messages are exempt from the strict
        # Request-Reply sequence that HDC-spec enforces on hosts.
        if self.pending_request_message is not None:
            # Do *not* raise an exception, but log and ignore, because Host implementation is to blame for this
            logger.warning("Hosts should not send a request before the previous one has been replied to")
            return

        self.pending_request_message = message

        if message_type_id == MessageTypeID.HDC_VERSION:
            return self._handle_hdc_version_request(message)
        if message_type_id == MessageTypeID.ECHO:
            return self._handle_echo_request(message)
        if message_type_id == MessageTypeID.COMMAND:
            return self._handle_command_request(message)
        else:
            # Do *not* raise an exception, but log and ignore, because Host implementation is to blame for this
            logger.warning(f"Don't know how to handle MessageTypeID=0x{message_type_id:02X}")
            self.pending_request_message = None

    def _handle_hdc_version_request(self, request_message: bytes) -> None:
        assert request_message[0] == MessageTypeID.HDC_VERSION
        reply_message = bytearray()
        reply_message.append(MessageTypeID.HDC_VERSION)
        reply_message.extend(HDC_VERSION.encode(encoding="utf-8", errors="strict"))
        reply_message = bytes(reply_message)
        self.send_reply_for_pending_request(reply_message)

    def _handle_echo_request(self, request_message: bytes) -> None:
        assert request_message[0] == MessageTypeID.ECHO
        reply_message = request_message  # As mandated by HDC-spec
        self.send_reply_for_pending_request(reply_message)

    def _handle_command_request(self, request_message: bytes) -> None:
        """Warning: This will be executed from within the SerialTransport.receiver_thread"""
        assert request_message[0] == MessageTypeID.COMMAND
        feature_id = request_message[1]
        command_id = request_message[2]
        key = (feature_id, command_id)
        if key in self.command_request_handlers:
            # Note how it's up to each individual handler to either reply straight away from within
            # this SerialTransport.receiver_thread context, or to delay its reply into another context.
            return self.command_request_handlers[key](request_message)

        # ... else, reply with CommandErrorCode as mandated by HDC-spec
        error_reply = bytearray(request_message[:3])  # Header: MsgTypeID + FeatureID + CmdID
        is_known_feature = any(ids[0] == feature_id for ids in self.command_request_handlers.keys())
        if is_known_feature:
            command_error_code = CommandErrorCode.UNKNOWN_COMMAND
        else:
            command_error_code = CommandErrorCode.UNKNOWN_FEATURE
        error_reply.append(command_error_code)
        error_reply = bytes(error_reply)
        self.send_reply_for_pending_request(error_reply)

    def _handle_custom_message(self, message: bytes) -> None:
        """Warning: This will be executed from within the SerialTransport.receiver_thread"""
        message_type_id = message[0]
        if message_type_id in self.custom_message_handlers:
            return self.custom_message_handlers[message_type_id](message)
        # Do *not* raise an exception, but log and ignore, because Host implementation might be to blame for this
        logger.warning(f"Ignoring custom-message, because no handler has been registered for "
                       f"MessageTypeID={message_type_id}")
