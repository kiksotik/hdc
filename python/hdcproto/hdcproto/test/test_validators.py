import unittest

from hdcproto.validate import validate_uint8


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
