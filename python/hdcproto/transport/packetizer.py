import logging


class Packetizer:
    """
    Packetizer of the HDC protocol.
    It transforms an incoming stream of bytes into individual messages and vice-versa.
    For details, please refer to the HDC-spec: https://github.com/kiksotik/hdc/blob/main/doc/spec/HDC-Spec.pdf
    """

    TERMINATOR = 0x1E         # "Record Separator" as defined by the ASCII standard
    MAX_PAYLOAD_SIZE = 0xFF   # Maximum payload that can be sent in a single package
    EMPTY_PACKET = bytearray([0, 0, TERMINATOR])  # payload_size=0 ; checksum=0 ; terminator

    incoming_raw_data_bytes: bytearray
    incoming_multi_package_message: bytearray
    reading_frame_error_count: int
    logger: logging.Logger
    _received_messages: list[bytes]

    def __init__(self):
        self._received_messages = list()
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

    def get_received_messages(self) -> list[bytes]:
        """
        Returns all messages received so far and forgets about them each time it's called.
        """
        tmp = self._received_messages
        self._received_messages = list()
        return tmp

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