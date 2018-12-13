#!/usr/bin/env python
# coding: utf-8
from typing import List, Dict, Type


class Const(object):
    MAGIC = b'\x1bLJ'

    MAX_VERSION = 0x80

    FLAG_IS_BIG_ENDIAN = 1 << 0
    FLAG_IS_STRIPPED = 1 << 1
    FLAG_HAS_FFI = 1 << 2

    FLAG_HAS_CHILD = 1 << 0
    FLAG_IS_VARIADIC = 1 << 1
    FLAG_JIT_DISABLED = 1 << 3
    FLAG_HAS_ILOOP = 1 << 4

    BCDUMP_KGC_CHILD = 0
    BCDUMP_KGC_TAB = 1
    BCDUMP_KGC_I64 = 2
    BCDUMP_KGC_U64 = 3
    BCDUMP_KGC_COMPLEX = 4
    BCDUMP_KGC_STR = 5

    BCDUMP_KTAB_NIL = 0
    BCDUMP_KTAB_FALSE = 1
    BCDUMP_KTAB_TRUE = 2
    BCDUMP_KTAB_INT = 3
    BCDUMP_KTAB_NUM = 4
    BCDUMP_KTAB_STR = 5

    VARNAME_END = 0
    VARNAME_FOR_IDX = 1
    VARNAME_FOR_STOP = 2
    VARNAME_FOR_STEP = 3
    VARNAME_FOR_GEN = 4
    VARNAME_FOR_STATE = 5
    VARNAME_FOR_CTL = 6
    VARNAME_MAX = 7

    INTERNAL_VARNAMES = [
        None,
        "<index>",
        "<limit>",
        "<step>",
        "<generator>",
        "<state>",
        "<control>"
    ]


class BytecodeDump(object):
    def __init__(self, **kwargs):
        self.number = 0
        self.origin = ''
        self.name = ''

        self.is_stripped = False
        self.is_big_endian = False
        self.has_ffi = False
        self.version = 0

        self.prototypes: List[Prototype] = []
        for key, value in kwargs.items():
            setattr(self, key, value)


class Prototype(object):
    def __init__(self, **kwargs):
        self.number = 0
        self.has_sub_prototypes = False
        self.is_variadic = False
        self.has_ffi = False
        self.is_jit_disabled = False
        self.has_iloop = False

        self.upvalue_count = 0
        self.constant_count = 0
        self.numeric_count = 0
        self.instruction_count = 0
        self.debug_info_size = 0
        self.argument_count = 0
        self.frame_size = 0
        self.first_line_number = 0
        self.line_count = 0
        self.instructions: List[Instruction] = []
        self.upvalues = []
        self.numerics = []
        self.constants: List[ConstRef] = []
        self.debug_info: DebugInfo = None
        for key, value in kwargs.items():
            setattr(self, key, value)
        for ins in self.instructions:
            ins.process_operand(self)


class ConstRef(object):
    def __init__(self, ref, number=None):
        self.number = number
        self.ref = ref


class Table(object):
    def __init__(self, **kwargs):
        self.array = []
        self.dictionary = []
        for key, value in kwargs.items():
            setattr(self, key, value)


class DebugInfo(object):
    def __init__(self, **kwargs):
        self.addr_to_line_map = []
        self.upvalue_variable_names = []
        self.variable_infos: List[VariableInfo] = []
        for key, value in kwargs.items():
            setattr(self, key, value)


class VariableInfo(object):
    T_VISIBLE = 0
    T_INTERNAL = 1

    def __init__(self, **kwargs):
        self.start_addr = 0
        self.end_addr = 0
        self.type = -1
        self.name = ""
        for key, value in kwargs.items():
            setattr(self, key, value)


class Instruction(object):
    NAME = None
    OPCODE = None
    A_TYPE = None
    B_TYPE = None
    CD_TYPE = None

    def __init__(self, *args, **kwargs):
        operands = list(args)
        if self.A_TYPE is not None:
            self.a = operands.pop(0) if operands else kwargs.pop('a', 0)
        if self.B_TYPE is not None:
            self.b = operands.pop(0) if operands else kwargs.pop('b', 0)
        if self.CD_TYPE is not None:
            self.cd = operands.pop(0) if operands else kwargs.pop('cd', 0)

    def process_operand(self, prototype: Prototype):
        if hasattr(self, 'a') and isinstance(self.a, ConstRef):
            self.a = prototype.constants.index(self.a)
        if hasattr(self, 'b') and isinstance(self.b, ConstRef):
            self.b = prototype.constants.index(self.b)
        if hasattr(self, 'cd') and isinstance(self.cd, ConstRef):
            self.cd = prototype.constants.index(self.cd)

    def __str__(self):
        arguments = []
        if hasattr(self, 'a'):
            arguments.append(str(self.a))
        if hasattr(self, 'b'):
            arguments.append(str(self.b))
        if hasattr(self, 'cd'):
            arguments.append(str(self.cd))
        return '{}({})'.format(self.NAME, ', '.join(arguments))

    def __repr__(self):
        return str(self)


INSTRUCTIONS: Dict[int, Type] = {}


def _define_instruction(name, a_type, b_type, cd_type) -> Type:
    def __init__(self, *args, **kwargs):
        Instruction.__init__(self, *args, **kwargs)

    new_class = type(name, (Instruction,), {"__init__": __init__})
    new_class.NAME = name
    new_class.OPCODE = len(INSTRUCTIONS)
    new_class.A_TYPE = a_type
    new_class.B_TYPE = b_type
    new_class.CD_TYPE = cd_type
    INSTRUCTIONS[new_class.OPCODE] = new_class
    return new_class


class InsType(object):
    VAR = 1  # variable slot number
    DST = 2  # variable slot number, used as a destination
    BS = 3  # base slot number, read-write
    RBS = 4  # base slot number, read-only
    UV = 5  # upvalue number (slot number, but specific to upvalues)
    LIT = 6  # literal
    SLIT = 7  # signed literal
    PRI = 8  # primitive type (0 = nil, 1 = false, 2 = true)
    NUM = 9  # numeric constant, index into constant table
    STR = 10  # string constant, negated index into constant table
    TAB = 11  # template table, negated index into constant table
    FUN = 12  # function prototype, negated index into constant table
    CDT = 13  # cdata constant, negated index into constant table
    JMP = 14  # branch target, relative to next instruction, biased with 0x8000


class Ins(object):
    # Comparison ops
    ISLT = _define_instruction("ISLT", InsType.VAR, None, InsType.VAR)
    ISGE = _define_instruction("ISGE", InsType.VAR, None, InsType.VAR)
    ISLE = _define_instruction("ISLE", InsType.VAR, None, InsType.VAR)
    ISGT = _define_instruction("ISGT", InsType.VAR, None, InsType.VAR)
    ISEQV = _define_instruction("ISEQV", InsType.VAR, None, InsType.VAR)
    ISNEV = _define_instruction("ISNEV", InsType.VAR, None, InsType.VAR)
    ISEQS = _define_instruction("ISEQS", InsType.VAR, None, InsType.STR)
    ISNES = _define_instruction("ISNES", InsType.VAR, None, InsType.STR)
    ISEQN = _define_instruction("ISEQN", InsType.VAR, None, InsType.NUM)
    ISNEN = _define_instruction("ISNEN", InsType.VAR, None, InsType.NUM)
    ISEQP = _define_instruction("ISEQP", InsType.VAR, None, InsType.PRI)
    ISNEP = _define_instruction("ISNEP", InsType.VAR, None, InsType.PRI)

    # Unary test and copy ops
    ISTC = _define_instruction("ISTC", InsType.DST, None, InsType.VAR)
    ISFC = _define_instruction("ISFC", InsType.DST, None, InsType.VAR)
    IST = _define_instruction("IST", None, None, InsType.VAR)
    ISF = _define_instruction("ISF", None, None, InsType.VAR)

    # Unary ops
    MOV = _define_instruction("MOV", InsType.DST, None, InsType.VAR)
    NOT = _define_instruction("NOT", InsType.DST, None, InsType.VAR)
    UNM = _define_instruction("UNM", InsType.DST, None, InsType.VAR)
    LEN = _define_instruction("LEN", InsType.DST, None, InsType.VAR)

    # Binary ops
    ADDVN = _define_instruction("ADDVN", InsType.DST, InsType.VAR, InsType.NUM)
    SUBVN = _define_instruction("SUBVN", InsType.DST, InsType.VAR, InsType.NUM)
    MULVN = _define_instruction("MULVN", InsType.DST, InsType.VAR, InsType.NUM)
    DIVVN = _define_instruction("DIVVN", InsType.DST, InsType.VAR, InsType.NUM)
    MODVN = _define_instruction("MODVN", InsType.DST, InsType.VAR, InsType.NUM)
    ADDNV = _define_instruction("ADDNV", InsType.DST, InsType.VAR, InsType.NUM)
    SUBNV = _define_instruction("SUBNV", InsType.DST, InsType.VAR, InsType.NUM)
    MULNV = _define_instruction("MULNV", InsType.DST, InsType.VAR, InsType.NUM)
    DIVNV = _define_instruction("DIVNV", InsType.DST, InsType.VAR, InsType.NUM)
    MODNV = _define_instruction("MODNV", InsType.DST, InsType.VAR, InsType.NUM)
    ADDVV = _define_instruction("ADDVV", InsType.DST, InsType.VAR, InsType.VAR)
    SUBVV = _define_instruction("SUBVV", InsType.DST, InsType.VAR, InsType.VAR)
    MULVV = _define_instruction("MULVV", InsType.DST, InsType.VAR, InsType.VAR)
    DIVVV = _define_instruction("DIVVV", InsType.DST, InsType.VAR, InsType.VAR)
    MODVV = _define_instruction("MODVV", InsType.DST, InsType.VAR, InsType.VAR)
    POW = _define_instruction("POW", InsType.DST, InsType.VAR, InsType.VAR)
    CAT = _define_instruction("CAT", InsType.DST, InsType.RBS, InsType.RBS)

    # Constant ops.
    KSTR = _define_instruction("KSTR", InsType.DST, None, InsType.STR)
    KCDATA = _define_instruction("KCDATA", InsType.DST, None, InsType.CDT)
    KSHORT = _define_instruction("KSHORT", InsType.DST, None, InsType.SLIT)
    KNUM = _define_instruction("KNUM", InsType.DST, None, InsType.NUM)
    KPRI = _define_instruction("KPRI", InsType.DST, None, InsType.PRI)
    KNIL = _define_instruction("KNIL", InsType.BS, None, InsType.BS)

    # Upvalue and function ops.
    UGET = _define_instruction("UGET", InsType.DST, None, InsType.UV)
    USETV = _define_instruction("USETV", InsType.UV, None, InsType.VAR)
    USETS = _define_instruction("USETS", InsType.UV, None, InsType.STR)
    USETN = _define_instruction("USETN", InsType.UV, None, InsType.NUM)
    USETP = _define_instruction("USETP", InsType.UV, None, InsType.PRI)
    UCLO = _define_instruction("UCLO", InsType.RBS, None, InsType.JMP)
    FNEW = _define_instruction("FNEW", InsType.DST, None, InsType.FUN)

    # Table ops.
    TNEW = _define_instruction("TNEW", InsType.DST, None, InsType.LIT)
    TDUP = _define_instruction("TDUP", InsType.DST, None, InsType.TAB)
    GGET = _define_instruction("GGET", InsType.DST, None, InsType.STR)
    GSET = _define_instruction("GSET", InsType.VAR, None, InsType.STR)
    TGETV = _define_instruction("TGETV", InsType.DST, InsType.VAR, InsType.VAR)
    TGETS = _define_instruction("TGETS", InsType.DST, InsType.VAR, InsType.STR)
    TGETB = _define_instruction("TGETB", InsType.DST, InsType.VAR, InsType.LIT)
    TSETV = _define_instruction("TSETV", InsType.VAR, InsType.VAR, InsType.VAR)
    TSETS = _define_instruction("TSETS", InsType.VAR, InsType.VAR, InsType.STR)
    TSETB = _define_instruction("TSETB", InsType.VAR, InsType.VAR, InsType.LIT)
    TSETM = _define_instruction("TSETM", InsType.BS, None, InsType.NUM)

    # Calls and vararg handling. T = tail call.
    CALLM = _define_instruction("CALLM", InsType.BS, InsType.LIT, InsType.LIT)
    CALL = _define_instruction("CALL", InsType.BS, InsType.LIT, InsType.LIT)
    CALLMT = _define_instruction("CALLMT", InsType.BS, None, InsType.LIT)
    CALLT = _define_instruction("CALLT", InsType.BS, None, InsType.LIT)
    ITERC = _define_instruction("ITERC", InsType.BS, InsType.LIT, InsType.LIT)
    ITERN = _define_instruction("ITERN", InsType.BS, InsType.LIT, InsType.LIT)
    VARG = _define_instruction("VARG", InsType.BS, InsType.LIT, InsType.LIT)
    ISNEXT = _define_instruction("ISNEXT", InsType.BS, None, InsType.JMP)

    # Returns.
    RETM = _define_instruction("RETM", InsType.BS, None, InsType.LIT)
    RET = _define_instruction("RET", InsType.RBS, None, InsType.LIT)
    RET0 = _define_instruction("RET0", InsType.RBS, None, InsType.LIT)
    RET1 = _define_instruction("RET1", InsType.RBS, None, InsType.LIT)

    # Loops and branches. I/J = interp/JIT, I/C/L = init/call/loop.
    FORI = _define_instruction("FORI", InsType.BS, None, InsType.JMP)
    JFORI = _define_instruction("JFORI", InsType.BS, None, InsType.JMP)
    FORL = _define_instruction("FORL", InsType.BS, None, InsType.JMP)
    IFORL = _define_instruction("IFORL", InsType.BS, None, InsType.JMP)
    JFORL = _define_instruction("JFORL", InsType.BS, None, InsType.JMP)
    ITERL = _define_instruction("ITERL", InsType.BS, None, InsType.JMP)
    IITERL = _define_instruction("IITERL", InsType.BS, None, InsType.JMP)
    JITERL = _define_instruction("JITERL", InsType.BS, None, InsType.LIT)
    LOOP = _define_instruction("LOOP", InsType.RBS, None, InsType.JMP)
    ILOOP = _define_instruction("ILOOP", InsType.RBS, None, InsType.JMP)
    JLOOP = _define_instruction("JLOOP", InsType.RBS, None, InsType.LIT)
    JMP = _define_instruction("JMP", InsType.RBS, None, InsType.JMP)

    # Function headers. I/J = interp/JIT, F/V/C = fixarg/vararg/C func.
    FUNCF = _define_instruction("FUNCF", InsType.RBS, None, None)
    IFUNCF = _define_instruction("IFUNCF", InsType.RBS, None, None)
    JFUNCF = _define_instruction("JFUNCF", InsType.RBS, None, InsType.LIT)
    FUNCV = _define_instruction("FUNCV", InsType.RBS, None, None)
    IFUNCV = _define_instruction("IFUNCV", InsType.RBS, None, None)
    JFUNCV = _define_instruction("JFUNCV", InsType.RBS, None, InsType.LIT)
    FUNCC = _define_instruction("FUNCC", InsType.RBS, None, None)
    FUNCCW = _define_instruction("FUNCCW", InsType.RBS, None, None)
    UNKNW = _define_instruction("UNKNW", InsType.LIT, InsType.LIT, InsType.LIT),
