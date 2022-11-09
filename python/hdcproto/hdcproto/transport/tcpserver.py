from __future__ import annotations

import logging
import socket
import threading
import typing
from urllib.parse import urlparse

from hdcproto.transport.base import TransportBase
from hdcproto.transport.packetizer import Packetizer

logger = logging.getLogger(__name__)  # Logger-name: "hdcproto.transport.tcpserver"


class SocketServerTransport(TransportBase):
    """
    Starts a TCP socket server that accepts connections from hosts to receive and send messages.
    Internally it uses the HDC-packetizer to allow transmission of HDC-messages, because TCP sockets
    are only able to transmit raw streams of bytes.
    
    Only to be used by device implementations, because HDC-hosts are "clients", not "servers".
    Host should use the SerialTransport, instead, which is able to connect to devices via TCP sockets.
    
    Warning: Message handler callbacks will be called directly from a dedicated data-receiver-thread!
    """
    hostname: str
    port: int
    _client_socket: socket.socket | None
    _receiver_thread: threading.Thread | None
    _keep_thread_alive: bool
    _packetizer: Packetizer
    _writing_lock = threading.RLock

    TIMEOUT_READ = 0.5  # Period of time after which we can be sure that an incoming data burst is completed

    def __init__(self,
                 connection_url: str,
                 message_received_handler: typing.Callable[[bytes], None],
                 connection_lost_handler: typing.Callable[[Exception | None], None]):

        url = urlparse(connection_url)
        if url.scheme != "socket" \
                or url.hostname is None \
                or url.port is None \
                or url.username is not None \
                or url.password is not None \
                or url.path != '' \
                or url.params != '' \
                or url.query != '' \
                or url.fragment != '':
            raise ValueError(f"Connection URL '{connection_url}' is not supported by {self.__class__.__name__}")

        super().__init__(connection_url=connection_url,
                         message_received_handler=message_received_handler,
                         connection_lost_handler=connection_lost_handler)
        self.hostname = url.hostname
        self.port = url.port
        self._client_socket = None  # Will be initialized on connection
        self._receiver_thread = None  # Will be initialized on connection
        self._keep_thread_alive = True
        self._packetizer = Packetizer()
        self._writing_lock = threading.RLock()

    def connect(self) -> None:
        if self.is_connected:
            raise RuntimeError("Already connected")

        logger.info(f"Accepting connections at {self.connection_url}")
        self._receiver_thread = threading.Thread(target=self._receiver_thread_loop,
                                                 kwargs={'transport': self},
                                                 daemon=True)
        self._keep_thread_alive = True
        self._receiver_thread.start()

    @property
    def is_connected(self) -> bool:
        # ToDo: This is ambiguous! Is it just "listening", or is at least one client connected to this server?
        return self._client_socket is not None

    def write(self, data: bytes):
        if not self.is_connected:
            raise RuntimeError("Not connected")

        with self._writing_lock:
            return self._client_socket.sendall(data)

    def send_message(self, message: bytes) -> None:
        with self._writing_lock:
            for packet in self._packetizer.pack_message(message):
                self.write(packet)  # ToDo: Maybe we should concatenate all packets and just call this once?

    def flush(self) -> None:
        if not self.is_connected:
            raise RuntimeError("Not connected")

        with self._writing_lock:  # Wait for any ongoing transmission to complete
            pass  # Nothing to do, since we sent data with socket.sendall()

    def close(self) -> None:
        """
        Disconnects any clients and stops the (listening-)receiver-thread.
        """
        if not self.is_connected and self._receiver_thread is None:
            raise RuntimeError("Not connected")

        # use the lock to let other threads finish writing
        with self._writing_lock:
            self._keep_thread_alive = False
            self._receiver_thread.join(2 * SocketServerTransport.TIMEOUT_READ)
            self._receiver_thread = None

    def __enter__(self) -> SocketServerTransport:
        """Enter context handler. May raise RuntimeError in case the connection could not be created."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Leave context handler"""
        if self.is_connected:
            self.flush()
        if self._receiver_thread is not None:
            self.close()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}('{self.connection_url}')"

    def _receiver_thread_loop(self, transport: SocketServerTransport) -> None:
        """
        Two nested loops:
          - Outer loop: Listening for incoming TCP connections and accepting only a single one
          - Inner loop: Receiving, unpacking and handling request messages.
        """
        logger.info(f"Started receiver-thread with native id: {threading.get_native_id()}")
        packetizer = Packetizer()

        # Inspired by: https://eecs485staff.github.io/p4-mapreduce/threads-sockets.html#tcp-socket-server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listening_socket:
            logger.info(f"Binding to host:{transport.hostname} and "
                        f"port:{transport.port}")
            listening_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listening_socket.settimeout(self.TIMEOUT_READ)  # Applies to accept() and recv() behaviour!
            listening_socket.bind((transport.hostname, transport.port))
            logger.info(f"Listening for client connections...")
            listening_socket.listen()

            while transport._keep_thread_alive:
                try:
                    transport._client_socket, client_address = listening_socket.accept()  # blocking, but times out
                except socket.timeout:
                    continue
                logger.info(f"Connection started with client at {client_address[0]}")

                with transport._client_socket:
                    while transport._keep_thread_alive:

                        try:
                            # Read all bytes received or wait for one byte (blocking, timing out after TIMEOUT_READ)
                            data = transport._client_socket.recv(1024)
                            if not data:
                                # This is how a proper client disconnection behaves
                                break
                        except socket.timeout:
                            data = bytes()  # This is how the packetizer is told that a burst is over.
                        except ConnectionResetError:
                            # This happens when client disconnected between calls to recv()
                            break
                        except Exception as e:
                            logger.exception("TCP socket connection has failed.")
                            # probably some network problem such as disconnected LAN cable -> exit
                            logger.info("About to call the connection_lost_handler.")
                            transport.connection_lost_handler(e)
                            return

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
                logger.info(f"Connection lost to client at {client_address[0]}")
                transport._client_socket = None
                transport.connection_lost_handler(None)


########################
# Showcase this module

def showcase_serial_transport():
    from serialport import SerialTransport

    def server_handle_message(message: bytes):
        print(f'TCP server received {len(message):3d} byte message: [{message.hex(sep=",")}]')

    def server_handle_lost_connection(exception):
        print(f'TCP server lost connection, because: {exception}')

    def client_handle_message(message: bytes):
        print(f'TCP client received {len(message):3d} byte message: [{message.hex(sep=",")}]')

    def client_handle_lost_connection(exception):
        print(f'TCP client lost connection, because: {exception}')

    with SocketServerTransport(connection_url="socket://localhost:55555",
                               message_received_handler=server_handle_message,
                               connection_lost_handler=server_handle_lost_connection) as server:
        print(f"Server is connected: {server.is_connected}")
        with SerialTransport(connection_url="socket://localhost:55555",
                             message_received_handler=client_handle_message,
                             connection_lost_handler=client_handle_lost_connection) as client:
            print(f"Server is connected: {server.is_connected}")
            client.send_message(bytes())  # Empty packet.
            client.send_message(bytes(range(1)))
            client.send_message(bytes(range(10)))
            client.send_message(bytes(range(254)))
            client.send_message(bytes(range(255)))  # Multi-packet message of 255 bytes.
            client.send_message(bytes(i % 255 for i in range(400)))  # Multi-packet message of 400 bytes.
            client.send_message(bytes(i % 255 for i in range(510)))  # Multi-packet message of 510 bytes.
            client.flush()

            server.send_message(bytes())  # Empty packet.
            server.send_message(bytes(range(1)))
            server.send_message(bytes(range(10)))
            server.send_message(bytes(range(254)))
            server.send_message(bytes(range(255)))  # Multi-packet message of 255 bytes.
            server.send_message(bytes(i % 255 for i in range(400)))  # Multi-packet message of 400 bytes.
            server.send_message(bytes(i % 255 for i in range(510)))  # Multi-packet message of 510 bytes.
            server.flush()
        print(f"Server is connected: {server.is_connected}")


if __name__ == '__main__':
    showcase_serial_transport()
