#!/usr/bin/env python3
"""
HDC-host protocol implementation.
"""
from __future__ import annotations

import enum
import logging
import struct
import threading
import time
import typing

import serial


class PacketizerBase:
    """
    Packetizers transform an incoming stream of bytes into individual messages and vice-versa.
    """
    _received_messages: list[bytes]

    def __init__(self):
        self._received_messages = list()

    def get_received_messages(self) -> list[bytes]:
        """
        Returns all messages received so far and forgets about them each time it's called.
        """
        tmp = self._received_messages
        self._received_messages = list()
        return tmp

    def data_received(self, data: bytes):
        """
        Called whenever a chunk of bytes is received.
        To be overridden by subclassing.
        """
        raise NotImplementedError()

    @staticmethod
    def packetize_message(message: bytes) -> list[bytes]:
        """
        Will packetize the given message and return a list of packets.
        """
        raise NotImplementedError()

    def clear(self):
        """Clear and reset any internal state, e.g. buffers"""
        raise NotImplementedError()


class Packetizer(PacketizerBase):
    """
    Packetizer of the HDC protocol.
    First byte announces the number of bytes of the subsequent payload, after which
    a checksum byte and a terminator byte are appended.
    """

    TERMINATOR = 0x1E         # "Record Separator" as defined by the ASCII standard
    MAX_PAYLOAD_SIZE = 0xFF   # Maximum payload that can be sent in a single package
    EMPTY_PACKET = bytearray([0, 0, TERMINATOR])  # payload_size=0 ; checksum=0 ; terminator

    incoming_raw_data_bytes: bytearray
    incoming_multi_package_message: bytearray
    reading_frame_error_count: int
    logger: logging.Logger

    def __init__(self):
        super().__init__()
        self.incoming_raw_data_bytes = bytearray()
        self.incoming_multi_package_message = bytearray()
        self.reading_frame_error_count = 0
        self.logger = logging.getLogger("HDC.packetizer")

    def clear(self):
        del self.incoming_raw_data_bytes[:]
        del self.incoming_multi_package_message[:]

    def data_received(self, data):
        """
        Received either additional bytes or nothing, which means that
        the timeout elapsed and thus any data burst is over.
        """

        if self.logger.isEnabledFor(logging.DEBUG):  # Because data.hex() is expensive!
            self.logger.debug("Received a chunk of %d bytes: [%s]", len(data), data.hex(sep=','))

        self.incoming_raw_data_bytes.extend(data)
        data_burst_is_over = (len(data) == 0)
        while self.incoming_raw_data_bytes:
            payload_length = self.incoming_raw_data_bytes[0]
            terminator_index = payload_length + 2
            if terminator_index >= len(self.incoming_raw_data_bytes) and not data_burst_is_over:
                # Message is larger than the amount of data we currently have in the incoming_raw_data_bytes.
                # Wait for next data chunk or for a read-timeout that would mean that the data burst is over.
                self.logger.debug("Waiting for remainder of the message.")
                return
            if terminator_index < len(self.incoming_raw_data_bytes):
                if self.incoming_raw_data_bytes[terminator_index] == Packetizer.TERMINATOR:
                    # Uint8 sum of payload-bytes and two's complement checksum-byte must always yield zero
                    checksum = sum(self.incoming_raw_data_bytes[1:payload_length + 2]) & 0xFF
                    if checksum == 0x00:
                        payload = self.incoming_raw_data_bytes[1:payload_length + 1]
                        del self.incoming_raw_data_bytes[0:terminator_index + 1]
                        if self.incoming_multi_package_message or payload_length == self.MAX_PAYLOAD_SIZE:
                            self.incoming_multi_package_message.extend(payload)
                            if payload_length < self.MAX_PAYLOAD_SIZE:
                                self._received_messages.append(bytes(self.incoming_multi_package_message))
                                del self.incoming_multi_package_message[:]
                        else:
                            self._received_messages.append(bytes(payload))
                        continue
                    else:
                        self.logger.debug("Incorrect checksum!")
                else:
                    self.logger.debug("Incorrect terminator!")
            else:
                self.logger.debug("Incorrect packet-size! "
                                  "(Larger than the actual bytes received after completion of the burst of chunks.)")

            # ... otherwise it's very likely a reading-frame error!
            self.reading_frame_error_count += 1
            del self.incoming_raw_data_bytes[0:1]  # Skip first byte and try again.
            self.logger.debug("Assuming a reading-frame error. "
                              "(reading frame error counter: %d)", self.reading_frame_error_count)
            # Abort any ongoing multi-package message that we might have been receiving
            if self.incoming_multi_package_message:
                self.logger.debug("Aborting multi-package message reception, due to reading-frame-error.")
                del self.incoming_multi_package_message[:]
            # ToDo: Signal reading-frame error!

    @staticmethod
    def compute_checksum(payload: bytes):
        """Returns the 8-bit two's complement checksum of the given block of bytes"""
        return (0xFF - sum(payload) + 1) & 0xFF

    @staticmethod
    def packetize_message(message: bytes) -> list[bytes]:
        packets = list()

        # The following works for empty messages and also single and multi-packet messages
        multi_packet_payloads = (message[pos:pos + Packetizer.MAX_PAYLOAD_SIZE]
                                 for pos in range(0, len(message), Packetizer.MAX_PAYLOAD_SIZE))
        last_payload_size = Packetizer.MAX_PAYLOAD_SIZE
        for payload in multi_packet_payloads:
            packet = bytearray()
            last_payload_size = len(payload)
            packet.append(last_payload_size)
            packet.extend(payload)
            packet.append(Packetizer.compute_checksum(payload))
            packet.append(Packetizer.TERMINATOR)
            packets.append(packet)

        if last_payload_size == Packetizer.MAX_PAYLOAD_SIZE:
            # Send empty packet to signal either:
            #    - ...the end of a multi-package message whose payload size is an exact multiple of 255 bytes.
            #    - ...or it might have been an empty message to begin with.
            packets.append(Packetizer.EMPTY_PACKET)

        return packets


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

    def connect(self):
        raise NotImplementedError()

    def send_message(self, message: bytes):
        """Transmits a chunk of raw bytes to the device"""
        raise NotImplementedError()

    def flush(self):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()

    def __str__(self):
        raise NotImplementedError()


class SerialTransport(TransportBase):
    """
    Send and receive messages via a serial port (typically a USB Virtual Com Port)
    On connecting it will spawn a Thread to poll for any data received and call reply handlers from said thread.
    """
    serial_url: str
    serial_port: serial.Serial | None
    receiver_thread: threading.Thread | None
    keep_thread_alive: bool
    packetizer: Packetizer
    port_access_lock = threading.Lock

    TIMEOUT_READ = 0.5  # Period of time after which we can be sure that an incoming data burst is completed

    def __init__(self,
                 serial_url: str,
                 message_received_handler: typing.Callable[[bytes], None] | None = None,
                 connection_lost_handler: typing.Callable[[Exception], None] | None = None):
        super().__init__(message_received_handler=message_received_handler,
                         connection_lost_handler=connection_lost_handler)
        self.serial_url = serial_url
        self.serial_port = None      # Will be initialized on connection
        self.receiver_thread = None  # Will be initialized on connection
        self.keep_thread_alive = True
        self.packetizer = Packetizer()
        self.port_access_lock = threading.Lock()

    def connect(self):
        if not self.message_received_handler or not self.connection_lost_handler:
            raise RuntimeError("Must assign message_received_handler and connection_lost_handler before connecting")
        self.serial_port = serial.serial_for_url(self.serial_url, timeout=self.TIMEOUT_READ, baudrate=115200)
        self.receiver_thread = threading.Thread(target=self.receiver_thread_loop,
                                                kwargs={'transport': self},
                                                daemon=True)
        self.keep_thread_alive = True
        self.receiver_thread.start()

    def send_message(self, message: bytes):
        with self.port_access_lock:
            for packet in self.packetizer.packetize_message(message):
                self.serial_port.write(packet)  # ToDo: Maybe we should concatenate all packets and just call this once?

    def flush(self):
        with self.port_access_lock:
            while self.serial_port.out_waiting or self.serial_port.in_waiting:
                time.sleep(0.001)

    def close(self):
        """
        Stops the receiver-thread and close the serial port.
        Does so immediately without caring for any ongoing communication
        """
        # use the lock to let other threads finish writing
        with self.port_access_lock:
            # first stop receiver-thread, so that closing can be done on idle port
            self.keep_thread_alive = False
            if hasattr(self.serial_port, 'cancel_read'):
                self.serial_port.cancel_read()
            self.receiver_thread.join(2 * SerialTransport.TIMEOUT_READ)
            self.receiver_thread = None

            # now it's safe to close the port
            self.serial_port.close()
            self.serial_port = None

    # - -  context manager
    def __enter__(self) -> SerialTransport:
        """Enter context handler. May raise RuntimeError in case the connection could not be created."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Leave context handler"""
        self.flush()
        self.close()

    def __str__(self):
        return f"{self.__class__.__name__}('{self.serial_url}')"

    # - -  Receiver-Thread
    def receiver_thread_loop(self, transport: SerialTransport) -> None:
        """
        This will be executed in a dedicated Thread, to ensure that any received messages are being handled as
        soon as they are being received.
        """

        if transport.serial_port is None and transport.connection_lost_handler:
            transport.connection_lost_handler(Exception("Failed to start receiver-thread, because port is not open"))
            return

        packetizer = Packetizer()

        while transport.keep_thread_alive and self.serial_port.is_open:
            try:
                # Read all bytes received or wait for one byte (blocking, timing out after TIMEOUT_READ)
                # Empty data means we reached the timeout without any new bytes
                data = transport.serial_port.read(transport.serial_port.in_waiting or 1)
            except serial.SerialException as e:
                # probably some I/O problem such as disconnected USB serial adapters -> exit
                if transport.connection_lost_handler:
                    transport.connection_lost_handler(e)
                return
            else:
                # make a separated try-except for called user code
                try:
                    packetizer.data_received(data)
                    received_messages = packetizer.get_received_messages()
                    for message in received_messages:
                        transport.message_received_handler(message)
                except Exception as e:
                    # ToDo: Should we log and ignore or disconnect with an exception?
                    if transport.connection_lost_handler:
                        transport.connection_lost_handler(e)
                    return


class ProtocolError(Exception):
    error_name: str

    def __init__(self, error_description: str):
        self.error_name = error_description


class ProtocolReplyError(ProtocolError):
    reply_message: bytes

    def __init__(self, error_name: str, reply_message: bytes):
        self.reply_message = reply_message
        super().__init__(error_name)

    @property
    def error_code(self) -> int:
        return self.reply_message[3]

    @property
    def error_description(self) -> str:
        return self.reply_message[4:].decode(encoding="utf-8", errors="strict")


@enum.unique
class MessageType(enum.IntEnum):
    CMD_ECHO = 0xCE
    CMD_FEATURE = 0xCF
    EVENT_FEATURE = 0xEF


@enum.unique
class PropertyDataType(enum.IntEnum):
    """
    The ID values of each DataType can be interpreted as follows:

    Upper Nibble: Kind of DataType
          0x0_ --> Unsigned integer number
          0x1_ --> Signed integer number
          0x2_ --> Floating point number
          0xB_ --> Binary data
                   (Either variable size 0xBF, or boolean 0xB0)
          0xF_ --> UTF-8 encoded string
                   (Always variable size: 0xFF)

    Lower Nibble: Size of DataType, given in number of bytes
                  i.e. 0x14 --> INT32, whose size is 4 bytes
                  (Exception to the rule: 0x_F denotes a variable size DataType)
                  (Exception to the rule: 0xB0 --> BOOL, whose size is 1 bytes)
    """
    
    UINT8 = 0x01
    UINT16 = 0x02
    UINT32 = 0x04
    INT8 = 0x11
    INT16 = 0x12
    INT32 = 0x14
    FLOAT = 0x24
    DOUBLE = 0x28
    BOOL = 0xB0
    BLOB = 0xBF
    UTF8 = 0xFF

    def struct_format(self) -> str | None:
        if self == PropertyDataType.BOOL:
            return "?"
        if self == PropertyDataType.UINT8:
            return "B"
        if self == PropertyDataType.UINT16:
            return "<H"
        if self == PropertyDataType.UINT32:
            return "<I"
        if self == PropertyDataType.INT8:
            return "<b"
        if self == PropertyDataType.INT16:
            return "<h"
        if self == PropertyDataType.INT32:
            return "<i"
        if self == PropertyDataType.FLOAT:
            return "<f"
        if self == PropertyDataType.DOUBLE:
            return "<d"
        if self == PropertyDataType.BLOB:
            return None
        if self == PropertyDataType.UTF8:
            return None

    def size(self) -> int | None:
        """
        Number of bytes of the given data type.
        Returns None for variable size types, e.g. UTF8 or BLOB
        """
        fmt = self.struct_format()
        if fmt is None:
            return None

        return struct.calcsize(fmt)

    def value_to_bytes(self, value: int | float | str | bytes) -> bytes:

        if isinstance(value, str):
            if self == PropertyDataType.UTF8:
                return value.encode(encoding="utf-8", errors="strict")
            raise ProtocolError(f"Improper target data type {self.name} for a str value")

        if isinstance(value, bytes):
            if self == PropertyDataType.BLOB:
                return value
            raise ProtocolError(f"Improper target data type {self.name} for a bytes value")

        fmt = self.struct_format()

        if fmt is None:
            raise ProtocolError(f"Don't know how to convert into {self.name}")

        if isinstance(value, bool):
            if self == PropertyDataType.BOOL:
                return struct.pack(fmt, value)
            else:
                raise ProtocolError(f"Vale of type {value.__class__} is unsuitable "
                                    f"for a property of type {self.name}")

        if isinstance(value, int):
            if self in (PropertyDataType.UINT8,
                        PropertyDataType.UINT16,
                        PropertyDataType.UINT32,
                        PropertyDataType.INT8,
                        PropertyDataType.INT16,
                        PropertyDataType.INT32):
                return struct.pack(fmt, value)
            else:
                raise ProtocolError(f"Vale of type {value.__class__} is unsuitable "
                                    f"for a property of type {self.name}")

        if isinstance(value, float):
            if self in (PropertyDataType.FLOAT,
                        PropertyDataType.DOUBLE):
                return struct.pack(fmt, value)
            else:
                raise ProtocolError(f"Vale of type {value.__class__} is unsuitable "
                                    f"for a property of type {self.name}")

        raise ProtocolError(f"Don't know how to convert value of type {value.__class__} "
                            f"into property of type {self.name}")

    def bytes_to_value(self, value_as_bytes: bytes) -> int | float | str | bytes:

        if self == PropertyDataType.UTF8:
            return value_as_bytes.decode(encoding="utf-8", errors="strict")

        if self == PropertyDataType.BLOB:
            return value_as_bytes

        fmt = self.struct_format()

        if fmt is None:
            raise ProtocolError(f"Don't know how to convert bytes of property type {self.name} "
                                f"into a python type")

        # Sanity check data size
        expected_size = self.size()
        if len(value_as_bytes) != expected_size:
            raise ProtocolError(
                f"Mismatch of data size. "
                f"Expected {expected_size} bytes, "
                f"but attempted to convert {len(value_as_bytes)}")

        return struct.unpack(fmt, value_as_bytes)[0]


class Protocol:
    """
    Encapsulates transport, packetizing and message brokering to the features.
    Not to be confused with the Device-Proxy classes!
    """
    features: dict[int, Feature]
    transport: TransportBase
    request_reply_lock: threading.Lock
    received_reply_event: threading.Event
    last_reply_message: bytes
    strict_event_handling: bool
    logger: logging.Logger
    
    def __init__(self, transport: TransportBase):
        self.features = dict()
        self.transport = transport
        transport.message_received_handler = self.handle_message
        transport.connection_lost_handler = self.handle_lost_connection
        self.request_reply_lock = threading.Lock()
        self.received_reply_event = threading.Event()
        self.last_reply_message = bytes()
        self.strict_event_handling = False
        self.logger = logging.getLogger("HDC.protocol")

    def connect(self):
        self.logger.info(f"Connecting via {self.transport}")
        self.transport.connect()

    def close(self):
        self.logger.info(f"Closing connection via {self.transport}")
        self.transport.close()

    def handle_lost_connection(self):
        self.logger.error(f"Lost connection via {self.transport}")
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

        if msg_type_id == MessageType.CMD_ECHO or msg_type_id == MessageType.CMD_FEATURE:
            self.handle_command_reply(message)

        if msg_type_id == MessageType.EVENT_FEATURE:
            self.handle_event(message)

    def handle_command_reply(self, message: bytes):
        # Note how we do not need to lookup neither FeatureID nor CommandID, because whatever command
        # issued the request is currently blocking and awaiting the received_reply_event.

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
                raise ProtocolError(f"EventID=0x{event_id:02X} raised by unknown FeatureID=0x{feature_id:02X}")
            else:
                self.logger.debug(f"Ignoring EventID=0x{event_id:02X} raised by unknown FeatureID=0x{feature_id:02X}")
                return

        self.features[feature_id].handle_event(message)

    def send_request_and_get_reply(self, request_message: bytes, timeout: float) -> bytes:

        # ToDo: We might need to make the following blocking=True with a timeout if the caller is multi-threaded.
        if not self.request_reply_lock.acquire(blocking=False):
            raise ProtocolError("Mustn't send a request if no reply was yet received for a preceding request")
        try:
            if self.received_reply_event.is_set():
                raise ProtocolError("Did not expect the received_reply_event to be signaled before sending a request")

            self.transport.send_message(request_message)

            if not self.received_reply_event.wait(timeout=timeout):
                raise TimeoutError(f'Did not receive any reply after {timeout} seconds.')

            self.received_reply_event.clear()

            return self.last_reply_message

        finally:
            self.request_reply_lock.release()

    def cmd_echo(self, echo_payload: bytes, timeout: float = 0.2) -> bytes:
        request_message = bytearray()
        request_message.append(MessageType.CMD_ECHO)
        request_message.extend(echo_payload)
        reply_message = self.send_request_and_get_reply(request_message, timeout)
        return reply_message[1:]  # Only return the payload, without the MessageTypeID prefix


class Feature:
    """
    This class is about everything the communication protocol needs to know about a feature of a device.
    Not to be confused with the Feature-Proxy classes!
    """
    feature_id: int
    protocol: Protocol
    event_handlers: dict[int, typing.Callable[[bytes], None]]  # Handlers implemented on the proxy class

    def __init__(self, protocol: Protocol, feature_id: int):
        if feature_id < 0 or feature_id > 255:
            raise ValueError()
        self.event_handlers = dict()
        self.feature_id = feature_id
        self.protocol = protocol
        if feature_id in protocol.features:
            self.protocol.logger.warning(f"Re-registering a feature with ID {feature_id}")
        protocol.features[feature_id] = self

    def register_event_handler(self, event_id: int, event_handler: typing.Callable[[bytes], None]) -> None:
        if event_id in self.event_handlers:
            raise ProtocolError(f"Feature {self.feature_id} already has EventID {event_id}")
        self.event_handlers[event_id] = event_handler

    def handle_event(self, message: bytes):
        """
        Executed within the ReceiverThread!
        Do not use this for message processing!
        This is just about receiving and signalling it to the main thread, where the actual processing will happen!
        """
        event_id = message[2]
        if event_id not in self.event_handlers:
            if self.protocol.strict_event_handling:
                raise ProtocolError(f"Unknown EventID=0x{event_id:02X} raised by FeatureID=0x{self.feature_id:02X}")
            else:
                self.protocol.logger.debug(f"Ignoring EventID=0x{event_id:02X} "
                                           f"raised by FeatureID=0x{self.feature_id:02X}")
                return

        event_handler = self.event_handlers[event_id]
        event_handler(message)


########################
# Showcase this module

def showcase_transport():

    def handle_message(message: bytes):
        print(f'Received {len(message):3d} byte message: [{ message.hex(sep=",") }]')

    def handle_lost_connection(exception):
        print(f'Lost connection, because: {exception}')

    with SerialTransport(serial_url="loop://",
                         message_received_handler=handle_message,
                         connection_lost_handler=handle_lost_connection) as transport:
        transport.send_message(bytes())                             # Empty packet.
        transport.send_message(bytes(range(1)))
        transport.send_message(bytes(range(10)))
        transport.send_message(bytes(range(254)))
        transport.send_message(bytes(range(255)))                   # Multi-packet message of 255 bytes.
        transport.send_message(bytes(i % 255 for i in range(400)))  # Multi-packet message of 400 bytes.
        transport.send_message(bytes(i % 255 for i in range(510)))  # Multi-packet message of 510 bytes.
        transport.flush()


if __name__ == '__main__':
    showcase_transport()
    
