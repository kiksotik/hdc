"""
Message router of the HDC-device implementation
"""
from __future__ import annotations

import logging
import typing

from hdcproto.exception import HdcCmdException
from hdcproto.parse import value_to_bytes
from hdcproto.spec import MessageTypeID, ExcID, HDC_VERSION, MetaID, DTypeID
from hdcproto.transport.base import TransportBase
from hdcproto.validate import is_custom_id, validate_uint8

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.device.router"


class MessageRouter:
    """
    Interfaces the proxy-classes with the message transport:
        - Sending of request-messages to the device and block until reception
          of the corresponding reply, while considering a timeout.

        - Routing of event-messages received from the device
    """
    transport: TransportBase | None
    idl_json_generator: typing.Callable[[], str] | None
    max_req_msg_size: int
    pending_request_message: bytes | None
    command_request_handlers: dict[typing.Tuple[int, int], typing.Callable[[bytes], None]]
    custom_message_handlers: dict[int, typing.Callable[[bytes], None]]

    def __init__(self,
                 transport: TransportBase | str | None = None,
                 idl_json_generator: typing.Callable[[], str] | None = None,
                 max_req: int = 2048):
        if isinstance(transport, str):
            transport = TransportBase.transport_factory(transport_url=transport, is_server=True)
        self.transport = transport
        self.idl_json_generator = idl_json_generator
        if max_req < 5:
            raise ValueError("Less than 5 bytes surely is wrong! "
                             "(e.g. request of a UINT8 property-setter requires 5 byte)")
        self.max_req_msg_size = max_req  # ToDo: Pass MaxReq limit to the Transport. Issue #19
        self.pending_request_message = None
        self.command_request_handlers = dict()
        self.custom_message_handlers = dict()

    @property
    def is_connected(self) -> bool:
        return self.transport is not None and self.transport.is_connected

    def connect(self, transport: TransportBase | str | None = None):
        if self.is_connected:
            raise RuntimeError("Already connected")

        if transport is not None:
            if isinstance(transport, str):
                transport = TransportBase.transport_factory(transport_url=transport, is_server=True)
            self.transport = transport
        elif self.transport is None:
            raise ValueError("No transport provided neither via constructor nor in this call.")

        logger.info(f"Connecting via {self.transport}")
        self.transport.connect(message_received_handler=self._handle_message,
                               connection_lost_handler=self._handle_lost_connection)
        logger.debug("Connected")

    def close(self):
        if self.transport is None:
            return

        logger.info(f"Closing connection via {self.transport}")
        self.transport.close()
        self.transport = None

    def _handle_lost_connection(self, exception: Exception | None):
        if exception:
            logger.exception(f"Lost connection via {self.transport}")
        else:
            logger.info("Lost connection, in an orderly manner.")

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
        key = (validate_uint8(feature_id), validate_uint8(command_id))
        if key in self.command_request_handlers:
            logger.warning(f"Replacing the event-message handler for "
                           f"FeatureID=0x{feature_id:02X} / CommandID=0x{command_id:02X}")
        self.command_request_handlers[key] = command_request_handler

    def register_custom_message_handler(self,
                                        message_type_id: int,
                                        message_handler: typing.Callable[[bytes], None]) -> None:
        """
        Mainly intended for the tunneling of other protocols through the HDC connection, by encapsulating data into
        a custom message which the given handler will know how to de-encapsulate and re-route.
        Tunneling of other HDC connections can alternatively and more efficiently be done by MessageTypeID translation.

        Although custom messages are exempt from obeying the strict Request-Reply sequence which HDC-spec mandates for
        any other kind of message type, it's the application's responsibility to
        """
        validate_uint8(message_type_id)
        if message_type_id in self.custom_message_handlers:
            logger.warning(f"Replacing the custom-message handler for MessageTypeID=0x{message_type_id:02X}")
        self.custom_message_handlers[message_type_id] = message_handler

    def send_event_message(self, event_message: bytes) -> None:
        assert event_message[0] == MessageTypeID.EVENT

        if not self.is_connected:
            logger.warning("Suppressing event message, because currently not connected!")
            return

        logger.info("Sending EVENT message")
        self.transport.send_message(event_message)

    def send_reply_for_pending_request(self, reply_message: bytes) -> None:
        """
        Will send a reply message and release the lock on reception of further requests.
        """
        if not self.is_connected:
            logger.error("Suppressing reply message, because currently not connected!")
            return

        if self.pending_request_message is None:
            # Raise an exception, because Device implementation is to blame for this
            raise RuntimeError("Mustn't send a reply if no request is pending to be replied to")

        logger.info(f"Sending reply message")
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

        if is_custom_id(message_type_id):
            self._handle_custom_message(message)
            return

        # Only custom messages are exempt from the strict
        # Request-Reply sequence that HDC-spec enforces on hosts.
        if self.pending_request_message is not None:
            # Do *not* raise an exception, but log and ignore, because Host implementation is to blame for this
            logger.warning("Hosts should not send a request before the previous one has been replied to")
            return

        self.pending_request_message = message

        if message_type_id == MessageTypeID.META:
            return self._handle_meta_request(message)
        if message_type_id == MessageTypeID.ECHO:
            return self._handle_echo_request(message)
        if message_type_id == MessageTypeID.COMMAND:
            return self._handle_command_request(message)
        else:
            # Do *not* raise an exception, but log and ignore, because Host implementation is to blame for this
            logger.warning(f"Don't know how to handle MessageTypeID=0x{message_type_id:02X}")
            self.pending_request_message = None

    def _handle_meta_hdc_version_request(self, request_message: bytes) -> None:
        assert request_message[0] == MessageTypeID.META
        assert request_message[1] == MetaID.HDC_VERSION
        logger.info("Replying to a Meta.HDC_VERSION request message.")
        reply_message = bytearray()
        reply_message.append(MessageTypeID.META)
        reply_message.append(MetaID.HDC_VERSION)
        reply_message.extend(HDC_VERSION.encode(encoding="utf-8", errors="strict"))
        reply_message = bytes(reply_message)
        self.send_reply_for_pending_request(reply_message)

    def _handle_meta_max_req_request(self, request_message: bytes) -> None:
        assert request_message[0] == MessageTypeID.META
        assert request_message[1] == MetaID.MAX_REQ
        logger.info("Replying to a Meta.MAX_REQ request message.")
        reply_message = bytearray()
        reply_message.append(MessageTypeID.META)
        reply_message.append(MetaID.MAX_REQ)
        reply_message.extend(self.max_req_msg_size.to_bytes(length=4, byteorder='little'))
        reply_message = bytes(reply_message)
        self.send_reply_for_pending_request(reply_message)

    def _handle_meta_idl_json_request(self, request_message: bytes) -> None:
        assert request_message[0] == MessageTypeID.META
        assert request_message[1] == MetaID.IDL_JSON
        logger.info("Replying to a Meta.IDL_JSON request message.")
        reply_message = bytearray()
        reply_message.append(MessageTypeID.META)
        reply_message.append(MetaID.IDL_JSON)
        idl_json = "" if self.idl_json_generator is None else self.idl_json_generator()
        reply_message.extend(idl_json.encode(encoding="utf-8", errors="strict"))
        reply_message = bytes(reply_message)
        self.send_reply_for_pending_request(reply_message)

    def _handle_meta_request(self, request_message: bytes) -> None:
        """Warning: This will be executed from within the SerialTransport.receiver_thread"""
        assert request_message[0] == MessageTypeID.META
        meta_id = request_message[1]

        if meta_id == MetaID.HDC_VERSION:
            return self._handle_meta_hdc_version_request(request_message)

        if meta_id == MetaID.MAX_REQ:
            return self._handle_meta_max_req_request(request_message)

        if meta_id == MetaID.IDL_JSON:
            return self._handle_meta_idl_json_request(request_message)

    def _handle_echo_request(self, request_message: bytes) -> None:
        assert request_message[0] == MessageTypeID.ECHO
        logger.info("Replying to an ECHO request message.")
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
            logger.info("Routing COMMAND request message to its handler.")
            try:
                return self.command_request_handlers[key](request_message)
            except HdcCmdException as e:  # Translate it into a command-error-reply
                cmd_reply_message = bytes([MessageTypeID.COMMAND, feature_id, command_id, e.exception_id])
                if e.exception_message:
                    cmd_reply_message += value_to_bytes(DTypeID.UTF8, e.exception_message)
                return self.send_reply_for_pending_request(cmd_reply_message)

        # ... else, there's no handler for this command
        error_reply = bytearray(request_message[:3])  # Header: MsgTypeID + FeatureID + CmdID
        is_known_feature = any(ids[0] == feature_id for ids in self.command_request_handlers.keys())
        if is_known_feature:
            command_error_code = ExcID.UnknownCommand
            logger.warning(f"Failed to route COMMAND request message, because CommandID=0x{command_id:02X} is unknown "
                           f"for FeatureID=0x{feature_id:02X}.")
        else:
            command_error_code = ExcID.UnknownFeature
            logger.warning(f"Failed to route COMMAND request message, because FeatureID=0x{feature_id:02X} is unknown.")
        error_reply.append(command_error_code)
        error_reply = bytes(error_reply)
        self.send_reply_for_pending_request(error_reply)

    def _handle_custom_message(self, message: bytes) -> None:
        """Warning: This will be executed from within the SerialTransport.receiver_thread"""
        message_type_id = message[0]
        assert is_custom_id(message_type_id)
        if message_type_id in self.custom_message_handlers:
            logger.info("Routing custom message request to its handler.")
            return self.custom_message_handlers[message_type_id](message)
        # Do *not* raise an exception, but log and ignore, because Host implementation might be to blame for this
        logger.warning(f"Ignoring custom-message, because no handler has been registered for "
                       f"MessageTypeID={message_type_id}")
