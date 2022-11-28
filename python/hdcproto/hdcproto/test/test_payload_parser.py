import typing
import unittest

from hdcproto.exception import HdcDataTypeError
from hdcproto.parse import value_to_bytes, parse_payload
from hdcproto.spec import DTypeID


class TestPayloadParser(unittest.TestCase):

    def test_expecting_void_and_getting_empty_payload(self):
        empty_payload = bytes()

        self.assertIsNone(
            parse_payload(
                raw_payload=empty_payload,
                expected_data_types=None)
        )

        self.assertIsNone(
            parse_payload(
                raw_payload=empty_payload,
                expected_data_types=[])
        )

        # noinspection PyTypeChecker
        self.assertIsNone(
            parse_payload(
                raw_payload=empty_payload,
                expected_data_types=[None])  # Very weird, I know. But why not?
        )

    def test_expecting_void_but_getting_non_empty_payload(self):
        non_empty_payload = bytes(range(1))

        with self.assertRaises(HdcDataTypeError):
            parse_payload(
                raw_payload=non_empty_payload,
                expected_data_types=None
            )

        with self.assertRaises(HdcDataTypeError):
            parse_payload(
                raw_payload=non_empty_payload,
                expected_data_types=[]
            )

        with self.assertRaises(HdcDataTypeError):
            # noinspection PyTypeChecker
            parse_payload(
                raw_payload=non_empty_payload,
                expected_data_types=[None]  # Very weird, I know. But why not?
            )

    def test_validation_of_expected_type_argument(self):
        uint8_payload = bytes(range(1))

        with self.assertRaises(TypeError):
            # noinspection PyTypeChecker
            parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=int
            )

        with self.assertRaises(HdcDataTypeError):
            # noinspection PyTypeChecker
            parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=[int]
            )

        with self.assertRaises(HdcDataTypeError):
            parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=[DTypeID.UINT8, int]
            )

    def test_result_as_list_or_scalar(self):
        uint8_value = 0x42
        uint8_payload = value_to_bytes(DTypeID.UINT8, uint8_value)

        self.assertIsInstance(
            parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=DTypeID.UINT8  # Not a list...
            ),
            int  # ... thus expecting a scalar as result!
        )

        self.assertIsInstance(
            parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=[DTypeID.UINT8]  # A list...
            ),
            list  # ... thus expecting a list as result!
        )

    def test_parsing_of_uint8(self):
        uint8_value = 0x42
        uint8_payload = value_to_bytes(DTypeID.UINT8, uint8_value)

        parsed_result = parse_payload(raw_payload=uint8_payload, expected_data_types=DTypeID.UINT8)
        self.assertEqual(parsed_result, uint8_value)
        self.assertIsInstance(parsed_result, int)

    def test_parsing_of_uint16(self):
        uint16_value = 0x4242
        uint16_payload = value_to_bytes(DTypeID.UINT16, uint16_value)

        parsed_result = parse_payload(raw_payload=uint16_payload, expected_data_types=DTypeID.UINT16)
        self.assertEqual(parsed_result, uint16_value)
        self.assertIsInstance(parsed_result, int)

    def test_parsing_of_uint32(self):
        uint32_value = 0x42424242
        uint32_payload = value_to_bytes(DTypeID.UINT32, uint32_value)

        parsed_result = parse_payload(raw_payload=uint32_payload, expected_data_types=DTypeID.UINT32)
        self.assertEqual(parsed_result, uint32_value)
        self.assertIsInstance(parsed_result, int)

    def test_parsing_of_int8(self):
        int8_value = -0x42
        int8_payload = value_to_bytes(DTypeID.INT8, int8_value)

        parsed_result = parse_payload(raw_payload=int8_payload, expected_data_types=DTypeID.INT8)
        self.assertEqual(parsed_result, int8_value)
        self.assertIsInstance(parsed_result, int)

    def test_parsing_of_int16(self):
        int16_value = -0x4242
        int16_payload = value_to_bytes(DTypeID.INT16, int16_value)

        parsed_result = parse_payload(raw_payload=int16_payload, expected_data_types=DTypeID.INT16)
        self.assertEqual(parsed_result, int16_value)
        self.assertIsInstance(parsed_result, int)

    def test_parsing_of_int32(self):
        int32_value = -0x42424242
        int32_payload = value_to_bytes(DTypeID.INT32, int32_value)

        parsed_result = parse_payload(raw_payload=int32_payload, expected_data_types=DTypeID.INT32)
        self.assertEqual(parsed_result, int32_value)
        self.assertIsInstance(parsed_result, int)

    def test_parsing_of_float(self):
        float_value = -42.424242
        float_payload = value_to_bytes(DTypeID.FLOAT, float_value)

        parsed_result = parse_payload(raw_payload=float_payload, expected_data_types=DTypeID.FLOAT)
        self.assertAlmostEqual(parsed_result, float_value, places=5)  # Note the limited numeric precision of FLOAT !!!
        self.assertIsInstance(parsed_result, float)

    def test_parsing_of_double(self):
        double_value = -42.424242
        double_payload = value_to_bytes(DTypeID.DOUBLE, double_value)

        parsed_result = parse_payload(raw_payload=double_payload, expected_data_types=DTypeID.DOUBLE)
        self.assertAlmostEqual(parsed_result, double_value, places=6)  # Note the better numeric precision of DOUBLE
        self.assertIsInstance(parsed_result, float)

    def test_parsing_of_bool_true(self):
        true_value = True
        true_payload = value_to_bytes(DTypeID.BOOL, true_value)

        parsed_result = parse_payload(raw_payload=true_payload, expected_data_types=DTypeID.BOOL)
        self.assertEqual(parsed_result, true_value)
        self.assertIsInstance(parsed_result, bool)

    def test_parsing_of_bool_false(self):
        false_value = False
        false_payload = value_to_bytes(DTypeID.BOOL, false_value)

        parsed_result = parse_payload(raw_payload=false_payload, expected_data_types=DTypeID.BOOL)
        self.assertEqual(parsed_result, false_value)
        self.assertIsInstance(parsed_result, bool)

    def test_parsing_of_nonempty_blob(self):
        blob_value = bytes(range(42))
        blob_payload = value_to_bytes(DTypeID.BLOB, blob_value)

        self.assertEqual(blob_value, blob_payload)

        parsed_result = parse_payload(raw_payload=blob_payload, expected_data_types=DTypeID.BLOB)
        self.assertEqual(parsed_result, blob_value)
        self.assertIsInstance(parsed_result, bytes)

    def test_parsing_of_empty_blob(self):
        blob_value = bytes(range(0))
        blob_payload = value_to_bytes(DTypeID.BLOB, blob_value)

        self.assertEqual(blob_value, blob_payload)

        parsed_result = parse_payload(raw_payload=blob_payload, expected_data_types=DTypeID.BLOB)
        self.assertEqual(parsed_result, blob_value)
        self.assertIsInstance(parsed_result, bytes)

    def test_parsing_of_nonempty_utf8(self):
        # noinspection SpellCheckingInspection
        utf8_value = "Lorem ipsum ùոïċọɗẹ"
        utf8_payload = value_to_bytes(DTypeID.UTF8, utf8_value)

        parsed_result = parse_payload(raw_payload=utf8_payload, expected_data_types=DTypeID.UTF8)
        self.assertEqual(parsed_result, utf8_value)
        self.assertIsInstance(parsed_result, str)

    def test_parsing_of_empty_utf8(self):
        utf8_value = ""
        utf8_payload = value_to_bytes(DTypeID.UTF8, utf8_value)

        parsed_result = parse_payload(raw_payload=utf8_payload, expected_data_types=DTypeID.UTF8)
        self.assertEqual(parsed_result, utf8_value)
        self.assertIsInstance(parsed_result, str)

    def test_parsing_of_dtype(self):
        dtype_value = DTypeID.DOUBLE
        dtype_payload = value_to_bytes(DTypeID.DTYPE, dtype_value)

        parsed_result = parse_payload(raw_payload=dtype_payload, expected_data_types=DTypeID.DTYPE)
        self.assertEqual(parsed_result, dtype_value)
        self.assertIsInstance(parsed_result, DTypeID)

    def test_parsing_multiple_values(self):  # Without any variable size types!
        types_and_values: list[tuple[DTypeID, typing.Any]] = [
            (DTypeID.UINT8, 0x42),
            (DTypeID.INT32, -0x42424242),
            (DTypeID.DOUBLE, -42.424242),
            (DTypeID.BOOL, True),
            (DTypeID.DTYPE, DTypeID.FLOAT),
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(value_to_bytes(datatype, value))
            multiple_values.append(value)
            expected_data_types.append(datatype)
        payload = bytes(payload)

        parsed_result = parse_payload(raw_payload=payload, expected_data_types=expected_data_types)

        self.assertSequenceEqual(parsed_result, multiple_values)
        self.assertSequenceEqual(
            [type(i) for i in parsed_result],
            [type(i) for i in multiple_values]
        )

    def test_parsing_multiple_values_with_longer_payload_than_expected(self):
        types_and_values: list[tuple[DTypeID, typing.Any]] = [
            (DTypeID.UINT8, 0x42),
            (DTypeID.INT32, -0x42424242),
            (DTypeID.DOUBLE, -42.424242),
            (DTypeID.BOOL, True)
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(value_to_bytes(datatype, value))
            multiple_values.append(value)
            expected_data_types.append(datatype)

        payload.append(0x42)  # This is the one bogus byte that the parser should be complaining about!
        payload = bytes(payload)

        with self.assertRaises(HdcDataTypeError):
            parse_payload(raw_payload=payload, expected_data_types=expected_data_types)

    def test_parsing_multiple_values_with_shorter_payload_than_expected(self):
        types_and_values: list[tuple[DTypeID, typing.Any]] = [
            (DTypeID.UINT8, 0x42),
            (DTypeID.INT32, -0x42424242),
            (DTypeID.DOUBLE, -42.424242),
            (DTypeID.BOOL, True)
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(value_to_bytes(datatype, value))
            multiple_values.append(value)
            expected_data_types.append(datatype)

        payload = payload[:-1]  # This is the one missing byte that the parser should be complaining about!
        payload = bytes(payload)

        with self.assertRaises(HdcDataTypeError):
            parse_payload(raw_payload=payload, expected_data_types=expected_data_types)

    def test_parsing_multiple_values_and_last_is_of_variable_size(self):
        # noinspection SpellCheckingInspection
        types_and_values: list[tuple[DTypeID, typing.Any]] = [
            (DTypeID.UINT8, 0x42),
            (DTypeID.INT32, -0x42424242),
            (DTypeID.DOUBLE, -42.424242),
            (DTypeID.BOOL, True),
            (DTypeID.DTYPE, DTypeID.FLOAT),
            (DTypeID.UTF8, "Lorem ipsum ùոïċọɗẹ")
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(value_to_bytes(datatype, value))
            multiple_values.append(value)
            expected_data_types.append(datatype)
        payload = bytes(payload)

        parsed_result = parse_payload(raw_payload=payload, expected_data_types=expected_data_types)
        self.assertSequenceEqual(parsed_result, multiple_values)
        self.assertSequenceEqual(
            [type(i) for i in parsed_result],
            [type(i) for i in multiple_values]
        )

    def test_parsing_multiple_values_and_first_is_of_variable_size(self):
        # noinspection SpellCheckingInspection
        types_and_values: list[tuple[DTypeID, typing.Any]] = [
            (DTypeID.UTF8, "Lorem ipsum ùոïċọɗẹ"),
            (DTypeID.UINT8, 0x42),
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(value_to_bytes(datatype, value))
            multiple_values.append(value)
            expected_data_types.append(datatype)
        payload = bytes(payload)

        with self.assertRaises(HdcDataTypeError):
            # Should fail, because variable size can only be inferred for the last argument!
            parse_payload(raw_payload=payload, expected_data_types=expected_data_types)


if __name__ == '__main__':
    unittest.main()
