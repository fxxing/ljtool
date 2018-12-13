from bc.data import Table, Prototype, BytecodeDump, VariableInfo, DebugInfo, Instruction, ConstRef, InsType


class Formatter(object):
    def __init__(self, dump: BytecodeDump, encoding):
        self.dump = dump
        self.encoding = encoding
        self.prototypes = []
        self.code = ''
        self.current_prototype: Prototype = None

    def format(self):
        self._format(self.dump)
        return 'from bc.data import *\n{}\n{}'.format('\n'.join(self.prototypes), self.code)

    def _format(self, obj):
        if isinstance(obj, BytecodeDump):
            self.code = '''dump = BytecodeDump(\n{})'''.format(self._to_arguments(obj.__dict__))
            return 'dump'

        elif isinstance(obj, Prototype):
            self.current_prototype = obj
            name = 'prototype_{}'.format(obj.number)
            self.prototypes.append('{} = Prototype(\n{})'.format(name, self._to_arguments(obj.__dict__)))
            return name

        elif isinstance(obj, Instruction):
            return self._format_instruction(obj)

        elif isinstance(obj, ConstRef):
            name = 'const_{}'.format(obj.number)
            self.prototypes.append('{} = ConstRef({})'.format(name, self._format(obj.ref)))
            return name

        elif isinstance(obj, Table):
            return 'Table(\n{})'.format(self._to_arguments(obj.__dict__))

        elif isinstance(obj, DebugInfo):
            return 'DebugInfo(\n{})'.format(self._to_arguments(obj.__dict__))

        elif isinstance(obj, VariableInfo):
            return 'VariableInfo(\n{})'.format(self._to_arguments(obj.__dict__))

        elif isinstance(obj, str):
            return obj.__repr__()

        elif isinstance(obj, list):
            if not obj:
                return '[]'
            return '[\n{}]'.format(', \n'.join([self._format(o) for o in obj]))

        else:
            return str(obj)

    def _to_arguments(self, data):
        return ', \n'.join(['{}={}'.format(k, self._format(v)) for k, v in data.items()])

    def _format_instruction(self, ins: Instruction):
        arguments = []
        if hasattr(ins, 'a'):
            arguments.append(self._format_operand(ins.A_TYPE, ins.a))
        if hasattr(ins, 'b'):
            arguments.append(self._format_operand(ins.B_TYPE, ins.b))
        if hasattr(ins, 'cd'):
            arguments.append(self._format_operand(ins.CD_TYPE, ins.cd))
        return 'Ins.{}({})'.format(ins.NAME, ', '.join(arguments))

    def _format_operand(self, operand_type, value):
        if operand_type in (InsType.STR, InsType.TAB, InsType.FUN, InsType.CDT):
            c = self.current_prototype.constants[value]
            return 'const_{}'.format(c.number)
        return str(value)

    def _gen_name(self, prefix, value):
        return '{}_{}'.format(prefix, hex(id(value)))

    def _pop(self, data, *keys):
        data = dict(data)
        for key in keys:
            data.pop(key)
        return data
