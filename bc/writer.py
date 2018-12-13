from bc.data import Table, Prototype, BytecodeDump, Instruction, InsType, Const
from bc.stream import Stream


class DumpWriter(object):
    def __init__(self, dump: BytecodeDump, filename, encoding):
        self.dump = dump
        self.encoding = encoding
        self.filename = filename
        self.stream: Stream = None
        self.prototype_datas = {}

    def write(self):
        self.stream = Stream.open(self.filename, 'wb')
        # self.stream = Stream.open(BytesIO())
        self._write_header()
        self._write_prototypes()
        self.stream.close()

    def _write_header(self):
        self.stream.write_bytes(Const.MAGIC)
        self.stream.write_byte(self.dump.version)
        self.stream.write_uleb128(self.dump.is_big_endian | self.dump.is_stripped | self.dump.has_ffi)
        if not self.dump.is_stripped:
            name = self.dump.name.encode(self.encoding)
            self.stream.write_uleb128(len(name))
            self.stream.write_bytes(name)
        self.stream.byteorder = 'big' if self.dump.is_big_endian else 'little'

    def _write_prototypes(self):
        for prototype in self._sorted_prototypes():
            self._write_prototype(prototype)

        # end of prototypes
        self.stream.write_uleb128(0)

    def _write_prototype(self, prototype: Prototype):
        self.stream.write_byte(prototype.has_ffi | prototype.has_iloop | prototype.is_jit_disabled | prototype.has_sub_prototypes | prototype.is_variadic)
        self._write_counts(prototype)
        self._write_instructions(prototype)
        self._write_upvalues(prototype)
        self._write_constants(prototype)
        self._write_numerics(prototype)
        self._write_debug_info(prototype)

    def _write_counts(self, prototype: Prototype):
        self.stream.write_byte(len(prototype.argument_count))
        self.stream.write_byte(prototype.frame_size)
        self.stream.write_byte(len(prototype.upvalues))
        self.stream.write_uleb128(len(prototype.constants))
        self.stream.write_uleb128(len(prototype.numerics))
        self.stream.write_uleb128(len(prototype.instructions) - 1)

        if prototype.debug_info_size > 0:
            self.stream.write_uleb128(prototype.debug_info_size)
            self.stream.write_uleb128(prototype.first_line_number)
            self.stream.write_uleb128(prototype.line_count)

    def _write_instructions(self, prototype: Prototype):
        for ins in prototype.instructions[1:]:  # ignore head
            self._write_instruction(prototype, ins)

    def _write_instruction(self, prototype: Prototype, ins: Instruction):
        a, b, cd = 0, 0, 0
        arg_count = 0
        if ins.A_TYPE is not None:
            a = self._process_operand(prototype, ins.A_TYPE, ins.a)
            arg_count += 1
        if ins.B_TYPE is not None:
            b = self._process_operand(prototype, ins.B_TYPE, ins.b)
            arg_count += 1
        if ins.CD_TYPE is not None:
            cd = self._process_operand(prototype, ins.CD_TYPE, ins.cd)
            arg_count += 1
        if arg_count == 3:
            codeword = ins.OPCODE | (a << 8) | (b << 24) | (cd << 16)
        else:
            codeword = ins.OPCODE | (a << 8) | (cd << 16)
        self.stream.write_uint(codeword)

    def _process_operand(self, prototype: Prototype, operand_type, operand):
        if operand_type in (InsType.STR, InsType.TAB, InsType.FUN, InsType.CDT):
            return len(prototype.constants) - operand - 1
        elif operand_type == InsType.JMP:
            return operand + 0x8000
        elif operand_type == InsType.NUM:
            return operand
        else:
            return operand

    def _write_upvalues(self, prototype: Prototype):
        for uv in prototype.upvalues:
            self.stream.write_uint(uv, 2)

    def _write_constants(self, prototype: Prototype):
        for c in prototype.constants:
            ref = c.ref
            if isinstance(ref, str):
                ref = ref.encode(self.encoding)
                self.stream.write_uleb128(len(ref) + Const.BCDUMP_KGC_STR)
                self.stream.write_bytes(ref)
            elif isinstance(ref, Table):
                self.stream.write_uleb128(Const.BCDUMP_KGC_TAB)
                self._write_table(ref)
            elif isinstance(ref, Prototype):
                self.stream.write_uleb128(Const.BCDUMP_KGC_CHILD)

            # elif isinstance(ref, tuple):
            #     stream.write_uleb128(Const.BCDUMP_KGC_COMPLEX)
            #     stream.write_float(ref[0])
            #     stream.write_float(ref[1])
            # elif isinstance(ref, tuple):
            #     stream.write_uleb128(Const.BCDUMP_KGC_I64)
            #     stream.write_float(ref)

    def _write_numerics(self, prototype: Prototype):
        for n in prototype.numerics:
            self.stream.write_uleb128_33(n)

    def _write_table(self, table: Table):
        self.stream.write_uleb128(len(table.array))
        self.stream.write_uleb128(len(table.dictionary))
        for item in table.array:
            self._write_table_item(item)
        for item in table.dictionary:
            self._write_table_item(item[0])
            self._write_table_item(item[1])

        return table

    def _write_table_item(self, value):
        if value is True:
            self.stream.write_uleb128(Const.BCDUMP_KTAB_TRUE)

        elif value is False:
            self.stream.write_uleb128(Const.BCDUMP_KTAB_FALSE)

        elif value is None:
            self.stream.write_uleb128(Const.BCDUMP_KTAB_NIL)
        elif isinstance(value, str):
            value = value.encode(self.encoding)
            self.stream.write_uleb128(len(value) + Const.BCDUMP_KTAB_STR)
            self.stream.write_bytes(value)

        elif isinstance(value, int):
            self.stream.write_uleb128(Const.BCDUMP_KTAB_INT)
            self.stream.write_signed_int(value)

        elif isinstance(value, float):
            self.stream.write_uleb128(Const.BCDUMP_KTAB_NUM)
            self.stream.write_float(value)

        else:
            print(type(value))

    def _write_debug_info(self, prototype: Prototype):
        if prototype.debug_info:
            self._write_line_info(prototype)
            self._write_upvalue_names(prototype)
            self._write_variable_info(prototype)

    def _write_line_info(self, prototype: Prototype):
        if prototype.line_count >= 65536:
            line_info_size = 4
        elif prototype.line_count >= 256:
            line_info_size = 2
        else:
            line_info_size = 1

        for v in prototype.debug_info.addr_to_line_map[1:]:
            self.stream.write_uint(v - prototype.first_line_number, line_info_size)

    def _write_upvalue_names(self, prototype: Prototype):
        for v in prototype.debug_info.upvalue_variable_names:
            self.stream.write_zstring(v.encode(self.encoding))

    def _write_variable_info(self, prototype: Prototype):
        last_addr = 0

        for info in prototype.debug_info.variable_infos:
            if info.type == info.T_VISIBLE:
                self.stream.write_zstring(info.name.encode(self.encoding))
            else:
                self.stream.write_byte(Const.INTERNAL_VARNAMES.index(info.name))

            self.stream.write_uleb128(info.start_addr - last_addr)
            self.stream.write_uleb128(info.end_addr - info.start_addr)
            last_addr = info.start_addr
        self.stream.write_byte(Const.VARNAME_END)

    def _sorted_prototypes(self):
        def get_prototypes(pt: Prototype):
            children = []
            for c in pt.constants:
                if isinstance(c.ref, Prototype):
                    children = get_prototypes(c.ref) + children
            return children + [pt]

        prototypes = []
        for prototype in self.dump.prototypes:
            prototypes.extend(get_prototypes(prototype))
        return prototypes
