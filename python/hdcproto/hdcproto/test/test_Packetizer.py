from __future__ import annotations

import typing
import unittest

from hdcproto.transport.packetizer import Packetizer


class TestChecksum(unittest.TestCase):
    def test_checksum_computation(self):
        self.assertEqual(
            Packetizer.compute_checksum(b''),
            0x00
        )

        self.assertEqual(
            Packetizer.compute_checksum(b'\x01'),
            0xFF
        )

        self.assertEqual(
            Packetizer.compute_checksum(b'\x02'),
            0xFE
        )

        self.assertEqual(
            Packetizer.compute_checksum(b'\x03'),
            0xFD
        )

        self.assertEqual(
            Packetizer.compute_checksum(b'\x01\x01\x01'),
            0xFD
        )

        self.assertEqual(
            Packetizer.compute_checksum(b'\xFF'),
            0x01
        )

        self.assertEqual(
            Packetizer.compute_checksum(b'\xFF\xFF'),
            0x02
        )

        self.assertEqual(
            Packetizer.compute_checksum(b'\xFF\xFF\xFF'),
            0x03
        )


def single_chunk(packets: list[bytes]) -> list[bytes]:
    """Concatenates all given packets into a single chunk of bytes"""
    return [b''.join(packets)]


def chunk_into_single_bytes(packets: list[bytes]) -> list[bytes]:
    """Concatenates all given packets into a single chunk of bytes and then chunks it into single byte chunks"""
    return [bytes([single_byte]) for single_byte in b''.join(packets)]


class TestMessageRoundTrip(unittest.TestCase):

    def assertEqualAfterRoundTrip(
            self,
            messages: list[bytes],
            chunker: typing.Callable[[list[bytes]], list[bytes]]):

        # messages --> packets
        packets = list()
        for message in messages:
            packets.extend(Packetizer.packetize_message(message))
        self.assertGreaterEqual(len(packets), 1)

        # packets --> messages
        receiving_packetizer = Packetizer()
        for chunk in chunker(packets):
            receiving_packetizer.data_received(chunk)
        received_messages = receiving_packetizer.get_received_messages()

        self.assertSequenceEqual(
            received_messages,
            messages)

        self.assertEqual(
            len(receiving_packetizer.get_received_messages()),
            0,
            "Expected to auto-clear list of received messages!")

        self.assertEqual(
            receiving_packetizer.reading_frame_error_count,
            0)

    def test_one_empty_message(self):
        messages = [bytes()]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_two_empty_messages(self):
        messages = [bytes(), bytes()]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_one_1byte_message(self):
        messages = [bytes(range(1))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_two_1byte_messages(self):
        messages = [bytes(range(1)), bytes(range(1))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_one_254byte_message(self):
        messages = [bytes(range(254))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_two_254byte_messages(self):
        messages = [bytes(range(254)), bytes(range(254))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_one_255byte_message(self):
        messages = [bytes(range(255))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_two_255byte_messages(self):
        messages = [bytes(range(255)), bytes(range(255))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_one_256byte_message(self):
        messages = [bytes(range(256))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_two_256byte_messages(self):
        messages = [bytes(range(256)), bytes(range(256))]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_one_2550byte_message(self):
        message = bytes(i % 256 for i in range(2550))
        messages = [message]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_two_2550byte_message(self):
        message = bytes(i % 256 for i in range(2550))
        messages = [message, message]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_one_2551byte_message(self):
        message = bytes(i % 256 for i in range(2551))
        messages = [message]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)

    def test_two_2551byte_message(self):
        message = bytes(i % 256 for i in range(2551))
        messages = [message, message]
        self.assertEqualAfterRoundTrip(messages, single_chunk)
        self.assertEqualAfterRoundTrip(messages, chunk_into_single_bytes)


class TestReadingFrameErrors(unittest.TestCase):
    def test_bogus_first_byte_caught_by_terminator_mismatch(self):
        message = bytes(range(32))
        packetizer = Packetizer()
        packets = packetizer.packetize_message(message)
        raw_data = single_chunk(packets)[0]

        # The bogus byte fools packetizer into expecting a much shorter message
        # but it won't find any terminator where expected.
        bogus_byte = b'\x05'
        packetizer.data_received(bogus_byte + raw_data)
        self.assertEqual(len(packetizer._received_messages), 1)  # It realized something is wrong and skipped bogus byte
        unpacked_messages = packetizer.get_received_messages()
        self.assertEqual(len(packetizer._received_messages), 0)  # Auto-cleared internal message buffer
        self.assertEqual(len(unpacked_messages), 1)
        self.assertSequenceEqual(unpacked_messages[0], message)
        self.assertEqual(packetizer.reading_frame_error_count, 1)

    def test_bogus_first_byte_caught_by_checksum_mismatch(self):
        message = bytes([Packetizer.TERMINATOR] * 32)
        packetizer = Packetizer()
        packets = packetizer.packetize_message(message)
        raw_data = single_chunk(packets)[0]

        # The bogus byte fools packetizer into expecting a much shorter message
        # and it coincidentally will even find a terminator where expected, but the checksum will not match.
        bogus_byte = b'\x05'
        packetizer.data_received(bogus_byte + raw_data)
        self.assertEqual(len(packetizer._received_messages), 1)  # It realized something is wrong and skipped bogus byte
        unpacked_messages = packetizer.get_received_messages()
        self.assertEqual(len(packetizer._received_messages), 0)  # Auto-cleared internal message buffer
        self.assertEqual(len(unpacked_messages), 1)
        self.assertSequenceEqual(unpacked_messages[0], message)
        self.assertEqual(packetizer.reading_frame_error_count, 1)

    def test_bogus_first_byte_caught_by_end_of_burst(self):
        message = bytes(range(32))
        packetizer = Packetizer()
        packets = packetizer.packetize_message(message)
        raw_data = single_chunk(packets)[0]

        # The bogus byte fools packetizer into expecting a much longer message
        bogus_byte = b'\x99'
        packetizer.data_received(bogus_byte + raw_data)
        self.assertEqual(len(packetizer._received_messages), 0)  # Packetizer is still hoping for more chunks to arrive
        packetizer.data_received(b'')  # End of a data burst is signalled to packetizer with an empty chunk
        self.assertEqual(len(packetizer._received_messages), 1)  # It realized something is wrong and skipped bogus byte
        unpacked_messages = packetizer.get_received_messages()
        self.assertEqual(len(packetizer._received_messages), 0)  # Auto-cleared internal message buffer
        self.assertEqual(len(unpacked_messages), 1)
        self.assertSequenceEqual(unpacked_messages[0], message)
        self.assertEqual(packetizer.reading_frame_error_count, 1)

    def test_bogus_first_5bytes(self):
        message = bytes(range(32))
        packetizer = Packetizer()
        packets = packetizer.packetize_message(message)
        raw_data = single_chunk(packets)[0]
        bogus_byte = b'\x00\x00\x00\x00\x00'  # A typical burst of bogus zeroes
        packetizer.data_received(bogus_byte + raw_data)
        packetizer.data_received(b'')  # End of a data burst is signalled to packetizer with an empty chunk
        self.assertEqual(len(packetizer._received_messages), 1)  # It realized something is wrong and skipped all bogus
        unpacked_messages = packetizer.get_received_messages()
        self.assertEqual(len(packetizer._received_messages), 0)  # Auto-cleared internal message buffer
        self.assertEqual(len(unpacked_messages), 1)
        self.assertSequenceEqual(unpacked_messages[0], message)
        self.assertEqual(packetizer.reading_frame_error_count, 5)


if __name__ == '__main__':
    unittest.main()
