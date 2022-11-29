import unittest

from hdcproto.validate import validate_uint8, is_valid_name, validate_mandatory_name, validate_optional_name


class TestUint8Validator(unittest.TestCase):

    def test_min(self):
        validate_uint8(0)

    def test_max(self):
        validate_uint8(255)

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
