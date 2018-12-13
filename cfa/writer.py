#!/usr/bin/env python
# coding: utf-8
from typing import TextIO

from cfa.ast import Slot, FuncCall, \
    Assign, StatementList, BinCondition, If, For, ForIn, While, Repeat, ExpList, Constant, Literal, TableElement, Nop, Condition, BinExp, UnExp, Return, Primitive, FuncDef, OP_PRECEDENCE, Decision, \
    TableConstructor, Vararg, Upvalue
from cfa.visitor import Visitor


class LuaWriter(Visitor):
    def __init__(self, node: FuncDef, file: TextIO):
        super().__init__()
        self.node = node
        self.file = file
        self.indent = 0
        self.scopes = [set(node.args.content)]

    def write(self):
        self.visit(self.node)

    def has_define(self, slot):
        for scope in self.scopes:
            if slot in scope:
                return True
        return False

    def visit_assign(self, s: Assign):
        if len(s.targets.content) == 1 and isinstance(s.targets.content[0], TableElement) and isinstance(s.targets.content[0].key, Vararg):
            self.visit_all('ljtool.table_set_multi(', s.targets.content[0].table, ', ', s.values, ')')
        else:
            if s.targets.content:
                for v in s.targets.content:
                    if isinstance(v, Slot):
                        if not self.has_define(v.slot):
                            self.file.write('local ')
                            self.scopes[0].add(v.slot)
                            break
                self.visit(s.targets)
                self.file.write(' = ')
            self.visit(s.values)

    def visit_statement_list(self, s: StatementList):
        has_statement = False
        for i, v in enumerate(s.content):
            if has_statement and not isinstance(v, Nop):
                self.new_line()
            self.visit(v)
            if not isinstance(v, Nop):
                has_statement = True

    def _missing(self, node):
        raise Exception('writer for {} is missing'.format(type(node)))

    def visit_nop(self, _):
        pass

    def visit_loop_body(self, _):
        pass

    def visit_upvalue(self, s: Upvalue):
        self.file.write('slot{}'.format(s.slot))

    def visit_func_def(self, s: FuncDef):
        if s.is_root:
            self.visit(s.statements)
        else:
            self.file.write('function (')
            self.visit(s.args)
            self.file.write(')')
            self.new_line(1)
            self.visit_block(s.statements)
            self.new_line(-1)
            self.file.write('end')

    def visit_break(self, _):
        self.file.write('break')

    def visit_vararg(self, _):
        self.file.write('...')

    def visit_return(self, s: Return):
        self.file.write('return ')
        self.visit(s.returns)

    def visit_table_constructor(self, s: TableConstructor):
        self.file.write(str(s))

    def visit_condition(self, s: Condition):
        self.visit(s.value)

    def visit_bin_exp(self, s: BinExp):
        if isinstance(s.left, (UnExp, BinExp, BinCondition)) and OP_PRECEDENCE[s.op] > OP_PRECEDENCE[s.left.op]:
            self.visit_all('(', s.left, ')')
        else:
            self.visit(s.left)
        self.visit_all(' ', s.op, ' ')
        if isinstance(s.right, (UnExp, BinExp, BinCondition)) and OP_PRECEDENCE[s.op] > OP_PRECEDENCE[s.right.op] or s.op in {'-', '/', '%'}:
            self.visit_all('(', s.right, ')')
        else:
            self.visit(s.right)

    def visit_un_exp(self, s: UnExp):
        if s.op == 'not':
            self.file.write('not ')
        elif s.op == 'neg':
            self.file.write('-')
        else:
            self.file.write(s.op)

        if isinstance(s.value, (UnExp, BinExp, BinCondition)) and OP_PRECEDENCE[s.op] > OP_PRECEDENCE[s.value.op] or s.op in {'-', '/', '%'}:
            self.visit_all('(', s.value, ')')
        else:
            self.visit(s.value)

    def visit_bin_condition(self, s: BinCondition):

        if isinstance(s.left, (UnExp, BinExp, BinCondition)) and OP_PRECEDENCE[s.op] > OP_PRECEDENCE[s.left.op]:
            self.visit_all('(', s.left, ')')
        else:
            self.visit(s.left)
        self.visit_all(' ', s.op, ' ')
        if len(s.right.content) != 1:
            self.file.write('ljtool.mutli_line_condition(--[[')
            self.visit(s.right)
            self.file.write(']]')
        else:
            right = s.right.content[-1]
            if isinstance(right, (UnExp, BinExp, BinCondition)) and OP_PRECEDENCE[s.op] > OP_PRECEDENCE[right.op] or s.op in {'-', '/', '%'}:
                self.visit_all('(', right, ')')
            else:
                self.visit(right)

    def visit_primitive(self, s: Primitive):
        if s.value is None:
            self.file.write('nil')
        elif s.value is True:
            self.file.write('true')
        else:
            self.file.write('false')

    def visit_exp_list(self, s: ExpList):
        for i, v in enumerate(s.content):
            if i > 0:
                self.file.write(', ')
            self.visit(v)

    def visit_if(self, s: If):
        self.visit_all('if ', s.condition, ' then')
        self.new_line(1)
        self.visit_block(s.then)
        if s.other:
            self.new_line(-1)
            self.file.write('else')
            self.new_line(1)
            self.visit_block(s.other)
        self.new_line(-1)
        self.file.write('end')

    def visit_slot(self, s: Slot):
        self.file.write('slot{}'.format(s.slot))

    def visit_literal(self, s: Literal):
        self.file.write(str(s.value))

    def visit_constant(self, s: Constant):
        self.file.write(str(s))

    def visit_table_element(self, s: TableElement):
        self.file.write(str(s))

    def visit_multi_res(self, _):
        self.file.write('ljtool.mutli_res')
        # raise Exception('All MultiRes should be eliminated')

    def visit_func_call(self, s: FuncCall):
        if s.args.content and isinstance(s.args.content[-1], FuncCall) and not s.is_variadic:
            self.visit(s.func)
            self.file.write('(')
            for i, arg in enumerate(s.args.content):
                if i > 0:
                    self.file.write(', ')
                if i == len(s.args.content) - 1:
                    self.visit_all('ljtool.single_return_value(', arg, ')')
                else:
                    self.visit(arg)
            self.file.write(')')

        else:
            self.visit_all(s.func, '(', s.args, ')')

    def visit_for(self, s: For):
        self.visit_all('for ', s.init.index, ' = ', s.init.start, ', ', s.init.stop)
        if not (isinstance(s.init.step, Constant) and s.init.step.value == 1):
            self.visit_all(', ', s.init.step)
        self.file.write(' do')
        self.new_line(1)
        self.visit_block(s.body)
        self.new_line(-1)
        self.file.write('end')

    def visit_for_in(self, s: ForIn):
        self.visit_all('for ', s.call.values, ' in ', s.call.iterator, ' do')
        self.new_line(1)
        self.visit_block(s.body)
        self.new_line(-1)
        self.file.write('end')

    def visit_while(self, s: While):
        self.visit_all('while ', s.condition, ' do')
        self.new_line(1)
        self.visit_block(s.body)
        self.new_line(-1)
        self.file.write('end')

    def visit_repeat(self, s: Repeat):
        self.file.write('repeat')
        self.new_line(1)
        self.visit_block(s.body)
        self.new_line(-1)
        self.file.write('until ')
        self.visit(s.condition)

    def visit_block(self, node):
        self.scopes.insert(0, set())
        self.visit(node)
        self.scopes.pop(0)

    def visit_all(self, *args):
        for arg in args:
            if isinstance(arg, str):
                self.file.write(arg)
            else:
                self.visit(arg)

    def new_line(self, indent=None):
        self.indent = self.indent if indent is None else self.indent + indent
        self.file.write('\n')
        self.file.write('\t' * self.indent)
