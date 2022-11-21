from __future__ import annotations

import typing

from hdcproto.descriptor import ArgD, CommandDescriptor, RetD


def build_args(args: typing.Iterable[ArgD] | None) -> str:
    if args is None:
        return "(?)"  # ToDo: Attribute optionality. #25

    if len(args) == 0:
        return "(VOID)"

    result = "("
    result += ', '.join(f"{arg.dtype.name} {arg.name}" for arg in args)
    result += ")"
    return result


def build_ret_single(ret: RetD) -> str:
    if ret.name is None:
        return ret.dtype.name
    return f"{ret.dtype.name} {ret.name}"


def build_command_signature(cmd: CommandDescriptor) -> str:
    result = f"{cmd.name}{build_args(cmd.args)} -> "
    if cmd.returns is None:
        return result + "?"  # ToDo: Attribute optionality. #25
    if len(cmd.returns) == 0:
        return result + "VOID"
    if len(cmd.returns) == 1:
        return result + build_ret_single(cmd.returns[0])
    result += "("
    result += ', '.join(build_ret_single(ret) for ret in cmd.returns)
    result += ")"
    return result
