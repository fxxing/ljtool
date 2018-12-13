from typing import Union, List, Tuple

from bc.data import Ins

UN_OP = {
    Ins.NOT.NAME: 'not',
    Ins.UNM.NAME: 'neg',
    Ins.LEN.NAME: '#',
}

BIN_OP = {
    Ins.ISLT.NAME: '<',
    Ins.ISGE.NAME: '>=',
    Ins.ISLE.NAME: '<=',
    Ins.ISGT.NAME: '>',
    Ins.ISEQV.NAME: '==',
    Ins.ISNEV.NAME: '~=',
    Ins.ISEQS.NAME: '==',
    Ins.ISNES.NAME: '~=',
    Ins.ISEQN.NAME: '==',
    Ins.ISNEN.NAME: '~=',
    Ins.ISEQP.NAME: '==',
    Ins.ISNEP.NAME: '~=',
    Ins.ADDVN.NAME: '+',
    Ins.SUBVN.NAME: '-',
    Ins.MULVN.NAME: '*',
    Ins.DIVVN.NAME: '/',
    Ins.MODVN.NAME: '%',
    Ins.ADDNV.NAME: '+',
    Ins.SUBNV.NAME: '-',
    Ins.MULNV.NAME: '*',
    Ins.DIVNV.NAME: '/',
    Ins.MODNV.NAME: '%',
    Ins.ADDVV.NAME: '+',
    Ins.SUBVV.NAME: '-',
    Ins.MULVV.NAME: '*',
    Ins.DIVVV.NAME: '/',
    Ins.MODVV.NAME: '%',
    Ins.POW.NAME: '^',
}

OP_NOT = {
    '<': '>=',
    '>=': '<',
    '<=': '>',
    '>': '<=',
    '==': '~=',
    '~=': '==',
    '': 'not',
    'not': '',
}

OP_PRECEDENCE = {
    'or': 0,
    'and': 1,
    '<': 2,
    '>': 2,
    '<=': 2,
    '>=': 2,
    '~=': 2,
    '==': 2,
    '..': 3,
    '+': 4,
    '-': 4,
    '*': 5,
    '/': 5,
    '%': 5,
    'not': 6,
    '#': 6,
    'neg': 6,
    '^': 7,
}


class MyList(list):
    def __new__(self, *args, **kwargs):
        return super(MyList, self).__new__(self, args, kwargs)

    def __init__(self, *args, **kwargs):
        if len(args) == 1 and hasattr(args[0], '__iter__'):
            list.__init__(self, args[0])
        else:
            list.__init__(self, args)
        self.__dict__.update(kwargs)

    def __call__(self, **kwargs):
        self.__dict__.update(kwargs)
        return self


class Node(object):
    FIELDS = ()

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.__dict__)


class Exp(Node):
    pass


class Statement(Node):
    addr = 0


class ExpList(object):
    FIELDS = ('content',)

    def __init__(self, content: Union[List[Exp], Exp]):
        self.content = MyList(content if isinstance(content, list) else [content])

    def __repr__(self):
        return ', '.join(str(t) for t in self.content)


class StatementList(Statement):
    FIELDS = ('content',)

    def __init__(self, content: List[Statement]):
        self.content = MyList(content)
        self.addr = self.content[0].addr


class UnExp(Exp):
    FIELDS = ('value',)

    def __init__(self, op: str, value: Exp):
        self.op = op
        self.value = value

    def reverse(self):
        assert self.op in OP_NOT
        self.op = OP_NOT[self.op]

    def __repr__(self):
        return '{} {}'.format(self.op, self.value)


class BinExp(Exp):
    FIELDS = ('left', 'right')

    def __init__(self, op: str, left: Exp, right: Exp):
        self.op = op
        self.left = left
        self.right = right

    def reverse(self):
        assert self.op in OP_NOT
        self.op = OP_NOT[self.op]

    def __repr__(self):
        return '{} {} {}'.format(self.left, self.op, self.right)


class Slot(Exp):
    def __init__(self, slot):
        self.slot = slot

    def __repr__(self):
        return 'slot{}'.format(self.slot)


class Upvalue(Exp):
    def __init__(self, slot):
        self.slot = slot

    def __repr__(self):
        return 'uv{}'.format(self.slot)


class Constant(Exp):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        if isinstance(self.value, str):
            return '"{}"'.format(self.value)
        return str(self.value)


class Literal(Exp):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return str(self.value)


class Primitive(Exp):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return str(self.value)


class TableConstructor(Exp):
    FIELDS = ('array', 'dictionary')

    def __init__(self, array: ExpList = None, dictionary: List[Tuple[Exp, Exp]] = None):
        self.array = array
        self.dictionary = dictionary

    def __repr__(self):
        value = []
        if self.array:
            value.extend([str(v) for v in self.array.content])
        if self.dictionary:
            value.extend(['[{}]={}'.format(k, v) for k, v in self.dictionary])
        return '{%s}' % ', '.join(value)


class TableElement(Exp):
    FIELDS = ('table', 'key')

    def __init__(self, table: Exp, key: Exp):
        self.table = table
        self.key = key

    def __repr__(self):
        if isinstance(self.table, Constant) and self.table.value == '_env':
            return '{}'.format(self.key)[1:-1]
        if isinstance(self.key, Constant) and isinstance(self.key.value, str):
            return '{}.{}'.format(self.table, self.key.value)
        return '{}[{}]'.format(self.table, self.key)


class MultiRes(Slot):
    def __init__(self):
        super().__init__(-1)

    def __repr__(self):
        return 'MultiRes'


class Vararg(Exp):
    def __repr__(self):
        return 'Vararg'


class FuncDef(Exp):
    def __init__(self, args: ExpList, statements: StatementList, is_root):
        self.args = args
        self.statements = statements
        self.is_root = is_root

    def __repr__(self):
        return 'FuncDef'


class Assign(Statement):
    FIELDS = ('targets', 'values')

    def __init__(self, targets: ExpList, values: ExpList):
        self.targets = targets
        self.values = values

    def __repr__(self):
        return '{} = {}'.format(self.targets, self.values)


class Return(Statement):
    FIELDS = ('returns',)

    def __init__(self, returns: ExpList):
        self.returns = returns

    def __repr__(self):
        return 'return {}'.format(self.returns)


class FuncCall(Exp):
    FIELDS = ('func', 'args')

    def __init__(self, func: Slot, args: ExpList):
        self.func = func
        self.args = args
        self.is_variadic = self.args.content and isinstance(self.args.content[-1], MultiRes)

    def __repr__(self):
        return '{}({})'.format(self.func, self.args)


class Decision(Statement):
    def reverse(self):
        return NotImplementedError


class Condition(Decision):
    FIELDS = ('value',)

    def __init__(self, value: Union[UnExp, BinExp]):
        self.value = value

    def reverse(self):
        return self.value.reverse()

    def __repr__(self):
        return 'condition ({})'.format(self.value)


class BinCondition(Decision):
    FIELDS = ('left', 'right')

    def __init__(self, op: str, left: Decision, right: StatementList):
        self.op = op
        self.left = left
        self.right = right
        self.addr = self.left.addr

    def reverse(self):
        self.op = 'and' if self.op == 'or' else 'or'
        self.left.reverse()
        right: Decision = self.right.content[-1]
        right.reverse()

    def __repr__(self):
        return '{} {} {}'.format(self.left, self.op, self.right)


class If(Statement):
    FIELDS = ('condition', 'then', 'other')

    def __init__(self, condition: Decision, then: StatementList, other: StatementList = None):
        self.condition = condition
        self.then = then
        self.other = other
        self.else_ifs: List[Tuple[Decision, StatementList]] = None
        self.addr = condition.addr

    def reverse(self):
        self.condition.reverse()

    def __repr__(self):
        return 'if ({})'.format(self.condition)


class ForInit(Statement):
    FIELDS = ('index', 'start', 'stop', 'step')

    def __init__(self, index: Slot, start: Slot, stop: Slot, step: Slot):
        self.index = index
        self.start = start
        self.stop = stop
        self.step = step

    def __repr__(self):
        return 'for init {}={}, {}, {}'.format(self.index, self.start, self.stop, self.step)


class ForLoop(Statement):
    FIELDS = ('index', 'start', 'stop', 'step')

    def __init__(self, index: Slot, start: Slot, stop: Slot, step: Slot):
        self.index = index
        self.start = start
        self.stop = stop
        self.step = step

    def __repr__(self):
        return 'for loop {}={}, {}, {}'.format(self.index, self.start, self.stop, self.step)


class IterCall(Statement):
    FIELDS = ('generator', 'state', 'control', 'values')

    def __init__(self, generator: Slot, state: Slot, control: Slot, values: ExpList):
        self.generator = generator
        self.state = state
        self.control = control
        self.values = values
        self.iterator = None

    def __repr__(self):
        return 'iter call {} {} {} {}'.format(self.generator, self.state, self.control, self.values)


class IterLoop(Statement):
    FIELDS = ('index', 'control')

    def __init__(self, index: Slot, control: Slot):
        self.index = index
        self.control = control

    def __repr__(self):
        return 'iter loop {} {}'.format(self.index, self.control)


class Loop(Statement):
    def __init__(self, body: StatementList):
        self.body = body


class For(Loop):
    FIELDS = ('init', 'body')

    def __init__(self, init: ForInit, body: StatementList):
        super().__init__(body)
        self.init = init
        self.addr = init.addr

    def __repr__(self):
        return 'for {}={}, {}, {} then'.format(self.init.index, self.init.start, self.init.stop, self.init.step)


class ForIn(Loop):
    FIELDS = ('call', 'body')

    def __init__(self, call: IterCall, body: StatementList):
        super().__init__(body)
        self.call = call
        self.addr = call.addr

    def __repr__(self):
        return 'for in {}'.format(self.call)


class While(Loop):
    FIELDS = ('condition', 'body')

    def __init__(self, condition: StatementList, body: StatementList):
        super().__init__(body)
        self.condition = condition
        self.addr = condition.addr

    def __repr__(self):
        return 'while {}'.format(self.condition)


class Repeat(Loop):
    FIELDS = ('body', 'condition')

    def __init__(self, condition: Decision, body: StatementList):
        super().__init__(body)
        self.condition = condition
        self.addr = body.addr

    def __repr__(self):
        return 'repeat {}'.format(self.condition)


class Break(Statement):
    pass


class LoopBody(Statement):
    """Marker for loop body start"""


class Nop(Statement):
    pass
