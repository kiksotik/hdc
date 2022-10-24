import typing
import unittest

from common import HdcDataType


class TestPayloadParser(unittest.TestCase):

    def test_expecting_void_and_getting_empty_payload(self):
        empty_payload = bytes()

        self.assertIsNone(
            HdcDataType.parse_payload(
                raw_payload=empty_payload,
                expected_data_types=None)
        )

        self.assertIsNone(
            HdcDataType.parse_payload(
                raw_payload=empty_payload,
                expected_data_types=[])
        )

        # noinspection PyTypeChecker
        self.assertIsNone(
            HdcDataType.parse_payload(
                raw_payload=empty_payload,
                expected_data_types=[None])  # Very weird, I know. But why not?
        )

    def test_expecting_void_but_getting_non_empty_payload(self):
        non_empty_payload = bytes(range(1))

        with self.assertRaises(ValueError):
            HdcDataType.parse_payload(
                raw_payload=non_empty_payload,
                expected_data_types=None
            )

        with self.assertRaises(ValueError):
            HdcDataType.parse_payload(
                raw_payload=non_empty_payload,
                expected_data_types=[]
            )

        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            HdcDataType.parse_payload(
                raw_payload=non_empty_payload,
                expected_data_types=[None]  # Very weird, I know. But why not?
            )

    def test_validation_of_expected_type_argument(self):
        uint8_payload = bytes(range(1))

        with self.assertRaises(TypeError):
            # noinspection PyTypeChecker
            HdcDataType.parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=int
            )

        with self.assertRaises(TypeError):
            # noinspection PyTypeChecker
            HdcDataType.parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=[int]
            )

        with self.assertRaises(TypeError):
            HdcDataType.parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=[HdcDataType.UINT8, int]
            )

    def test_result_as_list_or_scalar(self):
        uint8_value = 0x42
        uint8_payload = HdcDataType.UINT8.value_to_bytes(uint8_value)

        self.assertIsInstance(
            HdcDataType.parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=HdcDataType.UINT8  # Not a list...
            ),
            int  # ... thus expecting a scalar as result!
        )

        self.assertIsInstance(
            HdcDataType.parse_payload(
                raw_payload=uint8_payload,
                expected_data_types=[HdcDataType.UINT8]  # A list...
            ),
            list  # ... thus expecting a list as result!
        )

    def test_parsing_of_uint8(self):
        uint8_value = 0x42
        uint8_payload = HdcDataType.UINT8.value_to_bytes(uint8_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=uint8_payload, expected_data_types=HdcDataType.UINT8),
            uint8_value
        )

    def test_parsing_of_uint16(self):
        uint16_value = 0x4242
        uint16_payload = HdcDataType.UINT16.value_to_bytes(uint16_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=uint16_payload, expected_data_types=HdcDataType.UINT16),
            uint16_value
        )

    def test_parsing_of_uint32(self):
        uint32_value = 0x42424242
        uint32_payload = HdcDataType.UINT32.value_to_bytes(uint32_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=uint32_payload, expected_data_types=HdcDataType.UINT32),
            uint32_value
        )

    def test_parsing_of_int8(self):
        int8_value = -0x42
        int8_payload = HdcDataType.INT8.value_to_bytes(int8_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=int8_payload, expected_data_types=HdcDataType.INT8),
            int8_value
        )

    def test_parsing_of_int16(self):
        int16_value = -0x4242
        int16_payload = HdcDataType.INT16.value_to_bytes(int16_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=int16_payload, expected_data_types=HdcDataType.INT16),
            int16_value
        )

    def test_parsing_of_int32(self):
        int32_value = -0x42424242
        int32_payload = HdcDataType.INT32.value_to_bytes(int32_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=int32_payload, expected_data_types=HdcDataType.INT32),
            int32_value
        )

    def test_parsing_of_float(self):
        float_value = -42.424242
        float_payload = HdcDataType.FLOAT.value_to_bytes(float_value)

        self.assertAlmostEqual(
            HdcDataType.parse_payload(raw_payload=float_payload, expected_data_types=HdcDataType.FLOAT),
            float_value,
            places=5  # Note the limited numeric precision of FLOAT !!!
        )

    def test_parsing_of_double(self):
        double_value = -42.424242
        double_payload = HdcDataType.DOUBLE.value_to_bytes(double_value)

        self.assertAlmostEqual(
            HdcDataType.parse_payload(raw_payload=double_payload, expected_data_types=HdcDataType.DOUBLE),
            double_value,
            places=6  # Note the better numeric precision of DOUBLE
        )

    def test_parsing_of_bool_true(self):
        true_value = True
        true_payload = HdcDataType.BOOL.value_to_bytes(true_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=true_payload, expected_data_types=HdcDataType.BOOL),
            true_value
        )

    def test_parsing_of_bool_false(self):
        false_value = False
        false_payload = HdcDataType.BOOL.value_to_bytes(false_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=false_payload, expected_data_types=HdcDataType.BOOL),
            false_value
        )

    def test_parsing_of_nonempty_blob(self):
        blob_value = bytes(range(42))
        blob_payload = HdcDataType.BLOB.value_to_bytes(blob_value)

        self.assertEqual(blob_value, blob_payload)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=blob_payload, expected_data_types=HdcDataType.BLOB),
            blob_value
        )

    def test_parsing_of_empty_blob(self):
        blob_value = bytes(range(0))
        blob_payload = HdcDataType.BLOB.value_to_bytes(blob_value)

        self.assertEqual(blob_value, blob_payload)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=blob_payload, expected_data_types=HdcDataType.BLOB),
            blob_value
        )

    def test_parsing_of_nonempty_utf8(self):
        utf8_value = "Lorem ipsum ùոïċọɗẹ"
        utf8_payload = HdcDataType.UTF8.value_to_bytes(utf8_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=utf8_payload, expected_data_types=HdcDataType.UTF8),
            utf8_value
        )

    def test_parsing_of_empty_utf8(self):
        utf8_value = ""
        utf8_payload = HdcDataType.UTF8.value_to_bytes(utf8_value)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=utf8_payload, expected_data_types=HdcDataType.UTF8),
            utf8_value
        )

    def test_parsing_multiple_values(self):  # Without any variable size types!
        types_and_values: list[tuple[HdcDataType, typing.Any]] = [
            (HdcDataType.UINT8, 0x42),
            (HdcDataType.INT32, -0x42424242),
            (HdcDataType.DOUBLE, -42.424242),
            (HdcDataType.BOOL, True)
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(datatype.value_to_bytes(value))
            multiple_values.append(value)
            expected_data_types.append(datatype)
        payload = bytes(payload)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=payload, expected_data_types=expected_data_types),
            multiple_values
        )

    def test_parsing_multiple_values_with_longer_payload_than_expected(self):
        types_and_values: list[tuple[HdcDataType, typing.Any]] = [
            (HdcDataType.UINT8, 0x42),
            (HdcDataType.INT32, -0x42424242),
            (HdcDataType.DOUBLE, -42.424242),
            (HdcDataType.BOOL, True)
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(datatype.value_to_bytes(value))
            multiple_values.append(value)
            expected_data_types.append(datatype)

        payload.append(0x42)  # This is the one bogus byte that the parser should be complaining about!
        payload = bytes(payload)

        with self.assertRaises(ValueError):
            HdcDataType.parse_payload(raw_payload=payload, expected_data_types=expected_data_types)

    def test_parsing_multiple_values_with_shorter_payload_than_expected(self):
        types_and_values: list[tuple[HdcDataType, typing.Any]] = [
            (HdcDataType.UINT8, 0x42),
            (HdcDataType.INT32, -0x42424242),
            (HdcDataType.DOUBLE, -42.424242),
            (HdcDataType.BOOL, True)
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(datatype.value_to_bytes(value))
            multiple_values.append(value)
            expected_data_types.append(datatype)

        payload = payload[:-1]  # This is the one missing byte that the parser should be complaining about!
        payload = bytes(payload)

        with self.assertRaises(ValueError):
            HdcDataType.parse_payload(raw_payload=payload, expected_data_types=expected_data_types)

    def test_parsing_multiple_values_and_last_is_of_variable_size(self):
        types_and_values: list[tuple[HdcDataType, typing.Any]] = [
            (HdcDataType.UINT8, 0x42),
            (HdcDataType.INT32, -0x42424242),
            (HdcDataType.DOUBLE, -42.424242),
            (HdcDataType.BOOL, True),
            (HdcDataType.UTF8, "Lorem ipsum ùոïċọɗẹ")
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(datatype.value_to_bytes(value))
            multiple_values.append(value)
            expected_data_types.append(datatype)
        payload = bytes(payload)

        self.assertEqual(
            HdcDataType.parse_payload(raw_payload=payload, expected_data_types=expected_data_types),
            multiple_values
        )

    def test_parsing_multiple_values_and_first_is_of_variable_size(self):
        types_and_values: list[tuple[HdcDataType, typing.Any]] = [
            (HdcDataType.UTF8, "Lorem ipsum ùոïċọɗẹ"),
            (HdcDataType.UINT8, 0x42),
        ]

        payload = bytearray()
        multiple_values = list()
        expected_data_types = list()
        for datatype, value in types_and_values:
            payload.extend(datatype.value_to_bytes(value))
            multiple_values.append(value)
            expected_data_types.append(datatype)
        payload = bytes(payload)

        with self.assertRaises(ValueError):
            # Should fail, because variable size can only be inferred for the last argument!
            HdcDataType.parse_payload(raw_payload=payload, expected_data_types=expected_data_types)
