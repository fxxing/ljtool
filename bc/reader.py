import sys

from bc.data import Table, Prototype, BytecodeDump, VariableInfo, DebugInfo, INSTRUCTIONS, Instruction, ConstRef, Const, Ins, InsType
from bc.stream import Stream


class Sequence(object):
    def __init__(self):
        self.value = 0

    def next(self):
        v = self.value
        self.value += 1
        return v


class Reader(object):
    def __init__(self, filename, encoding):
        self.encoding = encoding
        self.filename = filename
        self.stream: Stream = None
        self.dump: BytecodeDump = None
        self.prototype_number = Sequence()
        self.const_number: Sequence = None

    def read(self):
        self.stream = Stream.open(self.filename)
        self.dump = BytecodeDump()
        self.dump.origin = self.stream.name
        self._read_header()
        self._read_prototypes()
        self.stream.close()

    def _read_header(self):
        self._check_magic()
        self._read_version()
        self._read_flags()
        self._read_name()
        self.stream.byteorder = 'big' if self.dump.is_big_endian else 'little'

    def _check_magic(self):
        if self.stream.read_bytes(3) != Const.MAGIC:
            raise Exception("Invalid magic, not a LuaJIT format")

    def _read_version(self):
        self.dump.version = self.stream.read_byte()

        if self.dump.version > Const.MAX_VERSION:
            raise Exception("Version {0}: proprietary modifications".format(self.dump.version))

    def _read_flags(self):
        bits = self.stream.read_uleb128()

        self.dump.is_big_endian, bits = bits & Const.FLAG_IS_BIG_ENDIAN, bits & ~Const.FLAG_IS_BIG_ENDIAN
        self.dump.is_stripped, bits = bits & Const.FLAG_IS_STRIPPED, bits & ~Const.FLAG_IS_STRIPPED
        self.dump.has_ffi, bits = bits & Const.FLAG_HAS_FFI, bits & ~Const.FLAG_HAS_FFI

        if bits != 0:
            raise Exception("Unknown flags set: {0:08b}".format(bits))

    def _read_name(self):
        if self.dump.is_stripped:
            self.dump.name = self.stream.name
        else:
            length = self.stream.read_uleb128()
            self.dump.name = self.stream.read_bytes(length).decode(self.encoding)

    def _read_prototypes(self):
        while True:
            prototype = self._read_prototype()
            if not prototype:
                break
            self.dump.prototypes.append(prototype)

    def _read_prototype(self):
        size = self.stream.read_uleb128()
        if size == 0:
            return None

        prototype = Prototype(number=self.prototype_number.next())
        self.const_number = Sequence()
        self._read_prototype_flags(prototype)
        self._read_counts_and_sizes(prototype)
        self._read_instructions(prototype)
        self._read_upvalue_references(prototype)
        self._read_complex_constants(prototype)
        self._read_numeric_constants(prototype)
        self._read_debug_info(prototype)

        return prototype

    def _read_prototype_flags(self, prototype: Prototype):
        bits = self.stream.read_byte()

        prototype.has_ffi, bits = bits & Const.FLAG_HAS_FFI, bits & ~Const.FLAG_HAS_FFI
        prototype.has_iloop, bits = bits & Const.FLAG_HAS_ILOOP, bits & ~Const.FLAG_HAS_ILOOP
        prototype.is_jit_disabled, bits = bits & Const.FLAG_JIT_DISABLED, bits & ~Const.FLAG_JIT_DISABLED
        prototype.has_sub_prototypes, bits = bits & Const.FLAG_HAS_CHILD, bits & ~Const.FLAG_HAS_CHILD
        prototype.is_variadic, bits = bits & Const.FLAG_IS_VARIADIC, bits & ~Const.FLAG_IS_VARIADIC

        if bits != 0:
            raise Exception("Unknown prototype flags: {0:08b}".format(bits))

    def _read_counts_and_sizes(self, prototype: Prototype):
        prototype.argument_count = self.stream.read_byte()
        prototype.frame_size = self.stream.read_byte()
        prototype.upvalue_count = self.stream.read_byte()
        prototype.constant_count = self.stream.read_uleb128()
        prototype.numeric_count = self.stream.read_uleb128()
        prototype.instruction_count = self.stream.read_uleb128()
        prototype.debug_info_size = 0 if self.dump.is_stripped else self.stream.read_uleb128()

        if prototype.debug_info_size > 0:
            prototype.first_line_number = self.stream.read_uleb128()
            prototype.line_count = self.stream.read_uleb128()

    def _read_instructions(self, prototype: Prototype):
        head = Ins.FUNCV() if prototype.is_variadic else Ins.FUNCF()
        head.a = prototype.frame_size
        prototype.instructions.append(head)
        prototype.instructions.extend([self._read_instruction(prototype) for _ in range(prototype.instruction_count)])

    def _read_instruction(self, prototype: Prototype) -> Instruction:
        codeword = self.stream.read_uint(4)
        opcode = codeword & 0xFF
        instruction_class = INSTRUCTIONS[opcode]

        if instruction_class is None:
            raise Exception("Warning: unknown opcode {0:08x}", opcode)

        ins: Instruction = instruction_class()

        arg_count = 0
        if ins.A_TYPE is not None:
            arg_count += 1
        if ins.B_TYPE is not None:
            arg_count += 1
        if ins.CD_TYPE is not None:
            arg_count += 1

        if arg_count == 3:
            a = (codeword >> 8) & 0xFF
            cd = (codeword >> 16) & 0xFF
            b = (codeword >> 24) & 0xFF
        else:
            a = (codeword >> 8) & 0xFF
            b = None
            cd = (codeword >> 16) & 0xFFFF

        if ins.A_TYPE is not None:
            ins.a = self._process_operand(prototype, ins.A_TYPE, a)
        if ins.B_TYPE is not None:
            ins.b = self._process_operand(prototype, ins.B_TYPE, b)
        if ins.CD_TYPE is not None:
            ins.cd = self._process_operand(prototype, ins.CD_TYPE, cd)

        return ins

    def _process_operand(self, prototype: Prototype, op_type, op):
        if op_type in (InsType.STR, InsType.TAB, InsType.FUN, InsType.CDT):
            return prototype.constant_count - op - 1
        elif op_type == InsType.JMP:
            return op - 0x8000
        elif op_type == InsType.SLIT:
            return op - 0x10000 if op & 0x8000 else op
        else:
            return op

    def _read_upvalue_references(self, prototype: Prototype):
        prototype.upvalues.extend(self.stream.read_uint(2) for _ in range(prototype.upvalue_count))

    def _read_complex_constants(self, prototype: Prototype):
        for _ in range(prototype.constant_count):
            constant_type = self.stream.read_uleb128()
            const_number = '{}_{}'.format(prototype.number, self.const_number.next())

            if constant_type >= Const.BCDUMP_KGC_STR:
                length = constant_type - Const.BCDUMP_KGC_STR
                prototype.constants.append(ConstRef(self.stream.read_bytes(length).decode(self.encoding), const_number))

            elif constant_type == Const.BCDUMP_KGC_TAB:
                prototype.constants.append(ConstRef(self._read_table(), const_number))

            elif constant_type != Const.BCDUMP_KGC_CHILD:
                number = self.stream.read_float()

                if constant_type == Const.BCDUMP_KGC_COMPLEX:
                    prototype.constants.append(ConstRef((number, self.stream.read_float()), const_number))
                else:
                    prototype.constants.append(ConstRef(number, const_number))

            else:
                prototype.constants.append(ConstRef(self.dump.prototypes.pop(), const_number))

    def _read_numeric_constants(self, prototype: Prototype):
        for _ in range(prototype.numeric_count):
            prototype.numerics.append(self.stream.read_uleb128_33())

    def _read_table(self) -> Table:
        table = Table()
        array_items_count = self.stream.read_uleb128()
        hash_items_count = self.stream.read_uleb128()

        for _ in range(array_items_count):
            table.array.append(self._read_table_item())

        for _ in range(hash_items_count):
            table.dictionary.append(((self._read_table_item()), (self._read_table_item())))

        return table

    def _read_table_item(self):
        data_type = self.stream.read_uleb128()

        if data_type >= Const.BCDUMP_KTAB_STR:
            length = data_type - Const.BCDUMP_KTAB_STR

            return self.stream.read_bytes(length).decode(self.encoding)

        elif data_type == Const.BCDUMP_KTAB_INT:
            return self.stream.read_signed_int()

        elif data_type == Const.BCDUMP_KTAB_NUM:
            return self.stream.read_float()

        elif data_type == Const.BCDUMP_KTAB_TRUE:
            return True

        elif data_type == Const.BCDUMP_KTAB_FALSE:
            return False

        else:  # Const.BCDUMP_KTAB_NIL
            return None

    def _read_debug_info(self, prototype: Prototype):
        if prototype.debug_info_size > 0:
            prototype.debug_info = DebugInfo()
            self._read_line_info(prototype)
            self._read_upvalue_names(prototype)
            self._read_variable_info(prototype)

    def _read_line_info(self, prototype: Prototype):
        if prototype.line_count >= 65536:
            line_info_size = 4
        elif prototype.line_count >= 256:
            line_info_size = 2
        else:
            line_info_size = 1

        prototype.debug_info.addr_to_line_map.append(0)
        prototype.debug_info.addr_to_line_map.extend([prototype.first_line_number + self.stream.read_uint(line_info_size) for _ in range(prototype.instruction_count)])

    def _read_upvalue_names(self, prototype: Prototype):
        prototype.debug_info.upvalue_variable_names.extend([self.stream.read_zstring().decode(self.encoding) for _ in range(prototype.upvalue_count)])

    def _read_variable_info(self, prototype: Prototype):
        # pc - program counter
        last_addr = 0

        while True:
            info = VariableInfo()
            internal_var_type = self.stream.read_byte()

            if internal_var_type >= Const.VARNAME_MAX:
                prefix = internal_var_type.to_bytes(1, sys.byteorder)
                suffix = self.stream.read_zstring()

                info.name = (prefix + suffix).decode(self.encoding)
                info.type = info.T_VISIBLE

            elif internal_var_type == Const.VARNAME_END:
                break
            else:
                index = internal_var_type
                info.name = Const.INTERNAL_VARNAMES[index]
                info.type = info.T_INTERNAL

            start_addr = last_addr + self.stream.read_uleb128()
            end_addr = start_addr + self.stream.read_uleb128()

            info.start_addr = start_addr
            info.end_addr = end_addr
            last_addr = start_addr

            prototype.debug_info.variable_infos.append(info)
