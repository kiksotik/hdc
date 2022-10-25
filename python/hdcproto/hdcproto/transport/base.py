import typing


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
