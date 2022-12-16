from __future__ import annotations

import logging
import threading
import time
import typing

import serial

from hdcproto.transport.base import TransportBase
from hdcproto.transport.packetizer import Packetizer

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.transport.serialport"


class SerialTransport(TransportBase):
    """
    Sends and receives messages via a serial port (typically a Virtual Com Port of a USB-CDC connection).
    Internally it uses the HDC-packetizer to allow transmission of HDC-messages, because serial-communication
    is only able to transmit raw streams of bytes.

    Can also be used by a host to connect via TCP socket to a device, because pyserial is capable of that:
       https://pyserial.readthedocs.io/en/latest/url_handlers.html
    But it won't work for a device to connect via TCP socket, because pyserial is not able to behave as a TCP server!

    Warning: Message handler callbacks will be called directly from a dedicated data-receiver-thread!
    """
    pyserial_url: str
    baudrate: int
    _serial_port: serial.Serial | None
    _receiver_thread: threading.Thread | None
    _keep_thread_alive: bool
    _packetizer: Packetizer
    _writing_lock = threading.RLock

    TIMEOUT_READ = 0.5  # Period of time after which we can be sure that an incoming data burst is completed

    def __init__(self,
                 pyserial_url: str,
                 baudrate: int = 115200):
        self.pyserial_url = pyserial_url
        self.baudrate = baudrate
        self.message_received_handler = None
        self.connection_lost_handler = None
        self._serial_port = None  # Will be initialized on connection
        self._receiver_thread = None  # Will be initialized on connection
        self._keep_thread_alive = True
        self._packetizer = Packetizer()
        self._writing_lock = threading.RLock()

    def connect(self,
                message_received_handler: typing.Callable[[bytes], None],
                connection_lost_handler: typing.Callable[[Exception | None], None]
                ) -> None:
        if self.is_connected:
            raise RuntimeError("Already connected")

        logger.info(f"Connecting to {self.pyserial_url}")
        self._serial_port = serial.serial_for_url(url=self.pyserial_url,
                                                  timeout=self.TIMEOUT_READ,
                                                  baudrate=self.baudrate)
        self._receiver_thread = threading.Thread(target=self._receiver_thread_loop,
                                                 kwargs={'transport': self},
                                                 daemon=True)
        self.message_received_handler = message_received_handler
        self.connection_lost_handler = connection_lost_handler
        self._keep_thread_alive = True
        self._receiver_thread.start()

    @property
    def is_connected(self) -> bool:
        return self._receiver_thread is not None

    def write(self, data: bytes) -> int:
        if not self.is_connected:
            raise RuntimeError("Not connected")

        with self._writing_lock:
            return self._serial_port.write(data)

    def send_message(self, message: bytes) -> None:
        with self._writing_lock:
            for packet in self._packetizer.pack_message(message):
                self.write(packet)  # ToDo: Maybe we should concatenate all packets and just call this once?

    def flush(self) -> None:
        if not self.is_connected:
            raise RuntimeError("Not connected")

        if not hasattr(self._serial_port, "out_waiting"):
            # Ugly workaround for bug in pyserial when connection url starts with "socket://"
            # https://github.com/pyserial/pyserial/pull/639/commits/74c452070f4586dcd43bb597de6ba0812e12009f
            self._serial_port.out_waiting = False

        with self._writing_lock:
            while self._serial_port.out_waiting or self._serial_port.in_waiting:
                time.sleep(0.001)

    def close(self) -> None:
        """
        Stops the receiver-thread and close the serial port.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        # use the lock to let other threads finish writing
        with self._writing_lock:
            # first stop receiver-thread, so that closing can be done on idle port
            self._keep_thread_alive = False
            if hasattr(self._serial_port, 'cancel_read'):
                self._serial_port.cancel_read()
            self._receiver_thread.join(2 * SerialTransport.TIMEOUT_READ)
            self._receiver_thread = None

            # now it's safe to close the port
            self._serial_port.close()
            self._serial_port = None

        self.connection_lost_handler(None)

        self.message_received_handler = None
        self.connection_lost_handler = None

    def __str__(self) -> str:
        return f"{self.__class__.__name__}('{self.pyserial_url}', baudrate={self.baudrate})"

    def _receiver_thread_loop(self, transport: SerialTransport) -> None:
        """
        This will be executed in a dedicated Thread, to ensure that any received messages are being handled as
        soon as they are being received.
        """
        logger.info(f"Started receiver-thread with native id: {threading.get_native_id()}")

        if transport._serial_port is None:
            transport.connection_lost_handler(Exception("Failed to start receiver-thread, because port is not open"))
            return

        packetizer = Packetizer()

        while transport._keep_thread_alive and self._serial_port.is_open:
            try:
                # Read all bytes received or wait for one byte (blocking, timing out after TIMEOUT_READ)
                # Empty data means we reached the timeout without any new bytes
                data = transport._serial_port.read(transport._serial_port.in_waiting or 1)
            except serial.SerialException as e:
                logger.exception("Serial connection has failed.")
                # probably some I/O problem such as disconnected USB serial adapters -> exit
                logger.info("About to call the connection_lost_handler.")
                transport.connection_lost_handler(e)
                return
            else:

                # No need for DEBUG logging here, because it would be redundant with what the packetizer logs.

                packetizer.data_received(data)
                received_messages = packetizer.get_received_messages()

                try:  # Catch any exception thrown by user-code that processes the received messages
                    for message in received_messages:
                        transport.message_received_handler(message)
                except Exception as e:
                    # ToDo: Should we log and ignore or disconnect with an exception?
                    logger.info("About to call the connection_lost_handler.")
                    transport.connection_lost_handler(e)
                    return


########################
# Showcase this module

def showcase_serial_transport():
    def handle_message(message: bytes):
        print(f'Received {len(message):3d} byte message: [{message.hex(sep=",")}]')

    def handle_lost_connection(exception):
        print(f'Lost connection, because: {exception}')

    transport = SerialTransport(pyserial_url="loop://")
    transport.connect(message_received_handler=handle_message,
                      connection_lost_handler=handle_lost_connection)
    transport.send_message(bytes())  # Empty packet.
    transport.send_message(bytes(range(1)))
    transport.send_message(bytes(range(10)))
    transport.send_message(bytes(range(254)))
    transport.send_message(bytes(range(255)))  # Multi-packet message of 255 bytes.
    transport.send_message(bytes(i % 255 for i in range(400)))  # Multi-packet message of 400 bytes.
    transport.send_message(bytes(i % 255 for i in range(510)))  # Multi-packet message of 510 bytes.
    transport.flush()
    transport.close()


if __name__ == '__main__':
    showcase_serial_transport()
