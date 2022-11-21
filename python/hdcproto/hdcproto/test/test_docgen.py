
import unittest

from hdcproto.common import HdcDataType
from hdcproto.descriptor import CommandDescriptor, ArgD, RetD
from hdcproto.util.docgen import build_command_signature


class TestCommandSignature(unittest.TestCase):

    def test_0arg_0ret(self):
        cmd = CommandDescriptor(id_=0,
                                name="MyCommand",
                                arguments=[],
                                returns=[],
                                raises_also=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(VOID) -> VOID"
        )

    def test_1arg_1ret(self):
        cmd = CommandDescriptor(id_=0,
                                name="MyCommand",
                                arguments=[ArgD(HdcDataType.UINT8, "first_arg")],
                                returns=[RetD(HdcDataType.UINT32, "first_ret")],
                                raises_also=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(UINT8 first_arg) -> UINT32 first_ret"
        )

    def test_2arg_2ret(self):
        cmd = CommandDescriptor(id_=0,
                                name="MyCommand",
                                arguments=[ArgD(HdcDataType.UINT8, "first_arg"),
                                           ArgD(HdcDataType.FLOAT, "second_arg")],
                                returns=[RetD(HdcDataType.UINT32, "first_ret"),
                                         RetD(HdcDataType.DOUBLE, "second_ret")],
                                raises_also=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(UINT8 first_arg, FLOAT second_arg) -> (UINT32 first_ret, DOUBLE second_ret)"
        )

    # ToDo: Attribute optionality. #25
    @unittest.skip
    def test_unspecified(self):
        cmd = CommandDescriptor(id_=0,
                                name="MyCommand",
                                arguments=None,
                                returns=None,
                                raises_also=None,
                                doc=None)
        self.assertEqual(
            build_command_signature(cmd),
            "MyCommand(?) -> ?"
        )
