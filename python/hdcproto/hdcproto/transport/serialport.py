from __future__ import annotations

import threading
import time
import typing

import serial

from hdcproto.transport.base import TransportBase
from hdcproto.transport.packetizer import Packetizer


class SerialTransport(TransportBase):
    """
    Sends and receives messages via a serial port (typically a Virtual Com Port of a USB-CDC connection).
    Internally it uses the HDC-packetizer to allow transmission of HDC-messages, because serial-communication
    is only able to transmit raw streams of bytes.

    WARNING: Message handler callbacks will be called directly from a dedicated data-receiver-thread!
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
        self.serial_port = None  # Will be initialized on connection
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


########################
# Showcase this module

def showcase_serial_transport():
    def handle_message(message: bytes):
        print(f'Received {len(message):3d} byte message: [{message.hex(sep=",")}]')

    def handle_lost_connection(exception):
        print(f'Lost connection, because: {exception}')

    with SerialTransport(serial_url="loop://",
                         message_received_handler=handle_message,
                         connection_lost_handler=handle_lost_connection) as transport:
        transport.send_message(bytes())  # Empty packet.
        transport.send_message(bytes(range(1)))
        transport.send_message(bytes(range(10)))
        transport.send_message(bytes(range(254)))
        transport.send_message(bytes(range(255)))  # Multi-packet message of 255 bytes.
        transport.send_message(bytes(i % 255 for i in range(400)))  # Multi-packet message of 400 bytes.
        transport.send_message(bytes(i % 255 for i in range(510)))  # Multi-packet message of 510 bytes.
        transport.flush()


if __name__ == '__main__':
    showcase_serial_transport()
