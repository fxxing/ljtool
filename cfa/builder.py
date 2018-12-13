#!/usr/bin/env python
# coding: utf-8
from functools import reduce
from typing import List, Union

from bc.data import Prototype, Instruction, Ins, InsType, Table
from cfa.ast import UnExp, UN_OP, BinExp, BIN_OP, Upvalue, Constant, Literal, Primitive, TableConstructor, TableElement, MultiRes, \
    Vararg, Assign, Return, FuncCall, Statement, ForInit, ForLoop, IterLoop, Slot, IterCall, FuncDef, Exp, ExpList, StatementList, LoopBody, Condition, MyList
from cfa.graph import Block, Edge, Graph
from cfa.temporary import TemporaryEliminator, Transformer


class Builder(object):
    def __init__(self, prototype: Prototype):
        self.prototype = prototype

    def build(self, is_root=False) -> FuncDef:
        graph = self.build_graph()
        statements = StatementList(graph.root.statements)

        try:
            changed = True
            while changed:
                eliminator = TemporaryEliminator(statements)
                eliminator.process()
                changed = len(eliminator.delete_slots) > 0
        except RecursionError:
            pass

        Transformer().visit(statements)

        if self.prototype.is_variadic:
            args = ExpList(Vararg())
        else:
            args = ExpList([Slot(i) for i in range(self.prototype.argument_count)])
        return FuncDef(args, statements, is_root)

    def build_graph(self) -> Graph:
        # split instructions to blocks
        leaders = {1}
        for addr, ins in enumerate(self.prototype.instructions):
            if Ins.ISLT.OPCODE <= ins.OPCODE <= Ins.ISF.OPCODE:
                leaders.add(addr + 1)  # if true goto next instruction. next instruction is usually jump
                leaders.add(addr + 2)  # if false goto the instruction after next
            elif isinstance(ins, (Ins.UCLO, Ins.ISNEXT, Ins.JMP)) and ins.cd != 0:  # only branch if target is not 0
                leaders.add(addr + 1)
                leaders.add(addr + ins.cd + 1)  # unconditional jump
            elif Ins.FORI.OPCODE <= ins.OPCODE <= Ins.JITERL.OPCODE and ins.cd != 0:  # only branch if target is not 0
                leaders.add(addr + ins.cd + 1)  # if true goto jump
                leaders.add(addr + 1)  # if false goto next instruction
            elif Ins.RETM.OPCODE <= ins.OPCODE <= Ins.RET1.OPCODE:
                leaders.add(addr + 1)

        leaders = sorted(filter(None, list(leaders)))
        next_leaders = leaders[1:] + [len(self.prototype.instructions)]
        blocks = []
        leader_to_blocks = {}
        for leader, next_leader in zip(leaders, next_leaders):
            blocks.append(Block(self.translate_statements(leader, next_leader)))
            leader_to_blocks[leader] = blocks[-1]

        # build block edges
        for i, block in enumerate(blocks):
            addr = next_leaders[i] - 1
            ins = self.prototype.instructions[addr]
            if Ins.ISLT.OPCODE <= ins.OPCODE <= Ins.ISF.OPCODE:
                block.succ.append(Edge(leader_to_blocks[addr + 1], True))  # if true goto next instruction
                block.succ.append(Edge(leader_to_blocks[addr + 2], False))  # if false goto the instruction after next
            elif isinstance(ins, (Ins.UCLO, Ins.ISNEXT, Ins.JMP)) and ins.cd != 0:  # only branch if target is not 0
                block.succ.append(Edge(leader_to_blocks[addr + ins.cd + 1]))  # unconditional jump
            elif Ins.FORI.OPCODE <= ins.OPCODE <= Ins.JITERL.OPCODE and ins.cd != 0:  # only branch if target is not 0
                block.succ.append(Edge(leader_to_blocks[addr + ins.cd + 1], True))  # if true goto jump
                block.succ.append(Edge(leader_to_blocks[addr + 1], False))  # if false goto next instruction.
            elif next_leaders[i] in leader_to_blocks:
                block.succ.append(Edge(leader_to_blocks[next_leaders[i]]))  # flow

            if block.statements and isinstance(block.statements[-1], Return):
                block.succ = []

        return Graph(blocks[0])

    def translate_statements(self, start, end) -> List[Statement]:
        statements = []
        for addr in range(start, end):
            ss = self.build_statement(self.prototype.instructions[addr])
            if ss:
                for s in ss if isinstance(ss, list) else [ss]:
                    s.addr = addr
                    statements.append(s)
        return statements

    def build_statement(self, ins: Instruction) -> Union[Statement, List[Statement]]:
        if Ins.ISLT.OPCODE <= ins.OPCODE <= Ins.ISNEP.OPCODE:
            return Condition(BinExp(BIN_OP[ins.NAME], Slot(ins.a), self.build_operand(ins.CD_TYPE, ins.cd)))

        if Ins.ISTC.OPCODE <= ins.OPCODE <= Ins.ISFC.OPCODE:
            return [Assign(ExpList(Slot(ins.a)), ExpList(Slot(ins.cd))), Condition(UnExp('' if ins.OPCODE == Ins.ISTC.OPCODE else 'not', Slot(ins.cd)))]

        if Ins.IST.OPCODE <= ins.OPCODE <= Ins.ISF.OPCODE:
            return Condition(UnExp('' if ins.OPCODE == Ins.IST.OPCODE else 'not', Slot(ins.cd)))

        if Ins.MOV.OPCODE <= ins.OPCODE <= Ins.LEN.OPCODE:
            return Assign(ExpList(Slot(ins.a)), ExpList(Slot(ins.cd) if isinstance(ins, Ins.MOV) else UnExp(UN_OP[ins.NAME], Slot(ins.cd))))

        if Ins.ADDVN.OPCODE <= ins.OPCODE <= Ins.POW.OPCODE:
            return Assign(ExpList(Slot(ins.a)), ExpList(BinExp(BIN_OP[ins.NAME], Slot(ins.b), self.build_operand(ins.CD_TYPE, ins.cd))))

        if isinstance(ins, Ins.CAT):
            # noinspection PyTypeChecker
            return Assign(ExpList(Slot(ins.a)), ExpList(reduce(lambda l, r: BinExp('..', l, r), [Slot(i) for i in range(ins.b, ins.cd + 1)])))

        if Ins.KSTR.OPCODE <= ins.OPCODE <= Ins.KPRI.OPCODE:
            return Assign(ExpList(Slot(ins.a)), ExpList(self.build_operand(ins.CD_TYPE, ins.cd)))

        if isinstance(ins, Ins.KNIL):
            return Assign(ExpList([Slot(i) for i in range(ins.a, ins.cd + 1)]), ExpList([Primitive(None)] * (ins.cd - ins.a + 1)))

        if Ins.UGET.OPCODE <= ins.OPCODE <= Ins.USETP.OPCODE:
            return Assign(ExpList(self.build_operand(ins.A_TYPE, ins.a)), ExpList(self.build_operand(ins.CD_TYPE, ins.cd)))

        if isinstance(ins, Ins.FNEW):
            return Assign(ExpList(Slot(ins.a)), ExpList(Builder(self.prototype.constants[ins.cd].ref).build()))

        if isinstance(ins, Ins.TNEW):
            return Assign(ExpList(Slot(ins.a)), ExpList(TableConstructor()))

        if isinstance(ins, Ins.TDUP):
            table: Table = self.prototype.constants[ins.cd].ref
            return Assign(ExpList(Slot(ins.a)), ExpList(TableConstructor(ExpList([self.build_table_operand(v) for v in table.array]),
                                                                         MyList([MyList([self.build_table_operand(k), self.build_table_operand(v)]) for k, v in table.dictionary]))))

        if isinstance(ins, (Ins.GGET, Ins.TGETV, Ins.TGETS, Ins.TGETB)):
            return Assign(ExpList(self.build_operand(ins.A_TYPE, ins.a)),
                          ExpList(TableElement(Slot(ins.b) if ins.B_TYPE else Constant('_env'), self.build_operand(ins.CD_TYPE, ins.cd))))

        if isinstance(ins, (Ins.GSET, Ins.TSETV, Ins.TSETS, Ins.TSETB)):
            return Assign(ExpList(TableElement(Slot(ins.b) if ins.B_TYPE else Constant('_env'), self.build_operand(ins.CD_TYPE, ins.cd))),
                          ExpList(self.build_operand(ins.A_TYPE, ins.a)))

        if isinstance(ins, Ins.TSETM):
            return Assign(ExpList(TableElement(Slot(ins.a - 1), Vararg())), ExpList(MultiRes()))

        if Ins.CALLM.OPCODE <= ins.OPCODE <= Ins.CALLT.OPCODE:
            is_variadic = isinstance(ins, (Ins.CALLM, Ins.CALLMT))
            args = ExpList([Slot(i) for i in range(ins.a + 1, ins.a + ins.cd + is_variadic)] + ([MultiRes()] if is_variadic else []))

            if ins.OPCODE <= Ins.CALL.OPCODE:
                if ins.b > 0:
                    return Assign(ExpList([Slot(i) for i in range(ins.a, ins.a + ins.b - 1)]), ExpList(FuncCall(Slot(ins.a), args)))
                else:
                    return Assign(ExpList(MultiRes()), ExpList(FuncCall(Slot(ins.a), args)))
            else:
                return Return(ExpList(FuncCall(Slot(ins.a), args)))

        if isinstance(ins, Ins.VARG):
            if ins.b - 2 < 0:
                return Assign(ExpList(MultiRes()), ExpList(Vararg()))
            return Assign(ExpList([Slot(i) for i in range(ins.a, ins.a + ins.b - 1)]), ExpList(Vararg()))

        if Ins.RETM.OPCODE <= ins.OPCODE <= Ins.RET.OPCODE:
            # noinspection PyTypeChecker
            return Return(ExpList([Slot(i) for i in range(ins.a, ins.a + ins.cd)] + [MultiRes()]))

        if Ins.RET.OPCODE <= ins.OPCODE <= Ins.RET1.OPCODE:
            return Return(ExpList([Slot(i) for i in range(ins.a, ins.a + ins.cd - 1)]))

        if isinstance(ins, (Ins.FORI, Ins.JFORI)):
            return ForInit(Slot(ins.a + 3), Slot(ins.a), Slot(ins.a + 1), Slot(ins.a + 2))

        if isinstance(ins, (Ins.FORL, Ins.IFORL, Ins.JFORL)):
            return ForLoop(Slot(ins.a + 3), Slot(ins.a), Slot(ins.a + 1), Slot(ins.a + 2))

        if isinstance(ins, (Ins.ITERC, Ins.ITERN)):
            return IterCall(Slot(ins.a - 3), Slot(ins.a - 2), Slot(ins.a - 1), ExpList([Slot(i) for i in range(ins.a, ins.a + ins.b - 1)]))

        if isinstance(ins, (Ins.ITERL, Ins.IITERL, Ins.JITERL)):
            return IterLoop(Slot(ins.a), Slot(ins.a - 1))
        if isinstance(ins, (Ins.LOOP, Ins.ILOOP, Ins.JLOOP)):
            return LoopBody()

        # ignore ISNEXT, JMP, *LOOP, *FUNC*, UCLO
        assert isinstance(ins, (Ins.ISNEXT, Ins.JMP, Ins.UCLO, Ins.LOOP, Ins.ILOOP, Ins.JLOOP,
                                Ins.FUNCF, Ins.IFUNCF, Ins.JFUNCF, Ins.FUNCV,
                                Ins.IFUNCV, Ins.JFUNCV, Ins.FUNCC, Ins.FUNCCW))

    def build_table_operand(self, value) -> Exp:
        if value is None:
            return Primitive(None)
        elif value is True:
            return Primitive(True)
        elif value is False:
            return Primitive(False)
        elif isinstance(value, int):
            return Constant(value)
        elif isinstance(value, float):
            return Constant(value)
        elif isinstance(value, str):
            return Constant(value)

    def build_operand(self, op_type, op) -> Exp:
        if op_type in (InsType.STR, InsType.CDT):
            return Constant(self.prototype.constants[op].ref)
        if op_type == InsType.NUM:
            return Constant(self.prototype.numerics[op])
        if op_type == InsType.PRI:
            if op == 0:
                return Primitive(None)
            if op == 1:
                return Primitive(False)
            return Primitive(True)
        if op_type in (InsType.VAR, InsType.DST):
            return Slot(op)
        if op_type == InsType.UV:
            return Upvalue(op)
        if op_type in (InsType.LIT, InsType.SLIT):
            return Literal(op)
