import unittest

from hdcproto.descriptor import CommandDescriptor, ArgD, RetD
from hdcproto.spec import DTypeID
from hdcproto.util.docgen import build_command_signature


class TestCommandSignature(unittest.TestCase):

    def test_0arg_0ret(self):
        cmd = CommandDescriptor(id=0,
                                name="MyCommand",
                                args=[],
                                returns=[],
                                raises=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(VOID) -> VOID"
        )

    def test_1arg_1ret(self):
        cmd = CommandDescriptor(id=0,
                                name="MyCommand",
                                args=[ArgD(DTypeID.UINT8, "first_arg")],
                                returns=[RetD(DTypeID.UINT32, "first_ret")],
                                raises=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(UINT8 first_arg) -> UINT32 first_ret"
        )

    def test_2arg_2ret(self):
        cmd = CommandDescriptor(id=0,
                                name="MyCommand",
                                args=[ArgD(DTypeID.UINT8, "first_arg"),
                                      ArgD(DTypeID.FLOAT, "second_arg")],
                                returns=[RetD(DTypeID.UINT32, "first_ret"),
                                         RetD(DTypeID.DOUBLE, "second_ret")],
                                raises=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(UINT8 first_arg, FLOAT second_arg) -> (UINT32 first_ret, DOUBLE second_ret)"
        )

    # ToDo: Attribute optionality. #25
    @unittest.skip
    def test_unspecified(self):
        cmd = CommandDescriptor(id=0,
                                name="MyCommand",
                                args=None,
                                returns=None,
                                raises=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(?) -> ?"
        )
