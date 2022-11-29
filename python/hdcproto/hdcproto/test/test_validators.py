import unittest

from hdcproto.spec import DTypeID
from hdcproto.validate import validate_uint8, is_valid_name, validate_mandatory_name, validate_optional_name, \
    validate_dtype, is_valid_dtype


class TestUint8Validator(unittest.TestCase):

    def test_min(self):
        self.assertEqual(0, validate_uint8(0))

    def test_max(self):
        self.assertEqual(255, validate_uint8(255))

    def test_below(self):
        with self.assertRaises(ValueError):
            validate_uint8(-1)

    def test_above(self):
        with self.assertRaises(ValueError):
            validate_uint8(256)

    def test_none(self):
        with self.assertRaises(TypeError):
            # noinspection PyTypeChecker
            validate_uint8(None)

    def test_float(self):
        with self.assertRaises(TypeError):
            # noinspection PyTypeChecker
            validate_uint8(128.0)

    def test_str(self):
        with self.assertRaises(TypeError):
            # noinspection PyTypeChecker
            validate_uint8("128")


class TestDTypeIdValidator(unittest.TestCase):

    def test_valid_dtype(self):
        for dt in DTypeID:
            with self.subTest(dt_value=dt):
                self.assertTrue(is_valid_dtype(dt))
                self.assertEqual(dt, validate_dtype(dt))

    def test_valid_int(self):
        for dt in DTypeID:
            int_value = int(dt)
            with self.subTest(int_value=int_value):
                self.assertTrue(is_valid_dtype(int_value))
                self.assertEqual(int_value, validate_dtype(int_value))

    def test_valid_str(self):
        for dt in DTypeID:
            str_value = dt.name
            with self.subTest(str_value=str_value):
                self.assertTrue(is_valid_dtype(str_value))
                self.assertEqual(DTypeID[str_value], validate_dtype(str_value))

    # noinspection PyTypeChecker
    def test_invalid(self):
        with self.assertRaises(TypeError):
            validate_dtype(1.0)  # Invalid type

        with self.assertRaises(ValueError):
            validate_dtype(42)  # Undefined ID

        with self.assertRaises(ValueError):
            validate_dtype(256)  # Invalid UINT8

        with self.assertRaises(ValueError):
            validate_dtype('banana')  # Undefined name


class TestNameValidator(unittest.TestCase):

    def test_valid_names(self):
        valid_names = [
            "my_name",
            "MyName",
            "my_name22",
            "_my_name",
            "__my_name",
            "n",
            "N",
            "_"
        ]
        for name in valid_names:
            with self.subTest(name=name):
                self.assertTrue(is_valid_name(name))
                self.assertEqual(name, validate_mandatory_name(name))
                self.assertEqual(name, validate_optional_name(name))

    def test_invalid_names(self):
        invalid_names = [
            "",
            "22name",
            "my name",
            " my_name",
            "my_name ",
            "my-name",
            "my=name",
            "MyNämé"
        ]
        for name in invalid_names:
            with self.subTest(name=name):
                self.assertFalse(is_valid_name(name))

                with self.assertRaises(ValueError):
                    validate_mandatory_name(name)

                with self.assertRaises(ValueError):
                    validate_optional_name(name)

    # noinspection PyTypeChecker
    def test_invalid_name_type(self):
        invalid_names = [
            True,
            False,
            42,
            42.42
        ]
        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(TypeError):
                    is_valid_name(name)

                with self.assertRaises(TypeError):
                    validate_mandatory_name(name)

                with self.assertRaises(TypeError):
                    validate_optional_name(name)

    # noinspection PyTypeChecker
    def test_name_optionality(self):

        self.assertEqual(None, validate_optional_name(None))

        with self.assertRaises(TypeError):
            validate_mandatory_name(None)

        with self.assertRaises(TypeError):
            is_valid_name(None)
