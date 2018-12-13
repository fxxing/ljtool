#!/usr/bin/env python
# coding: utf-8
import os
from collections import defaultdict
from typing import List, Iterable, Any, Dict

from bc.reader import Sequence
from cfa.ast import Statement, ForLoop, IterLoop, Decision, Repeat, While, ForIn, Break, For, ForInit, If, BinCondition, IterCall, StatementList, Nop, LoopBody, Return, Condition, Primitive, UnExp
from log import logger

block_index = Sequence()


class Block(object):
    def __init__(self, statements: List[Statement]):
        self.index = block_index.next()  # unique id
        self.statements: List[Statement] = statements
        self.succ: List[Edge] = []  # successors

    def find_succ(self, condition):
        # type: (Any) -> Block
        for edge in self.succ:
            if edge.condition is condition:
                return edge.tail

    def __repr__(self):
        return 'Block({})'.format(self.index)


class Edge(object):
    def __init__(self, tail: Block, condition=None):
        self.tail = tail
        self.condition = condition

    def __repr__(self):
        return 'Edge({}, {})'.format(self.tail.index, self.condition)


class Graph(object):
    def __init__(self, root: Block):
        self.root = root
        self.pred: Dict[Block, List[Edge]] = defaultdict(list)

        self.construct()

    def blocks(self) -> Iterable[Block]:
        visited = set()
        stack = [self.root]
        while stack:
            block: Block = stack.pop(0)
            if block in visited:
                continue
            yield block
            visited.add(block)
            stack = [e.tail for e in block.succ if e.tail not in visited] + stack

    def construct(self):
        self.simplify()
        changed = True
        while changed:
            changed = False
            for func in [self.collapse_condition, self.construct_loop, self.construct_if]:
                changed = changed or self.apply(func)
        if self.root.succ:
            raise Exception('Cannot be simplified')

    def apply(self, func):
        changed = True
        while changed:
            changed = False
            op = None
            for block in self.blocks():
                op = func(block)
                if op:
                    break
            # move any operation that will change cfg out block iterator
            if op:
                op[0](*op[1])
                self.simplify()
                changed = True
                break
        return changed

    def construct_loop(self, block: Block):
        true: Block = block.find_succ(True)
        false: Block = block.find_succ(False)

        if isinstance(block.statements[-1], ForLoop):
            assert len(self.pred[true]) == 2  # loop body can have only 2 in edges
            head = list(filter(lambda e: e.tail != block, self.pred[true]))[0].tail
            return self.build_loop, ('for', block, head, true, head.find_succ(True))

        if isinstance(block.statements[-1], ForInit) and isinstance(false.statements[-1], Return):
            return self.build_loop, ('for_return', block, block, false, true)

        if isinstance(block.statements[-1], IterLoop):
            assert isinstance(block.statements[-2], IterCall)
            return self.build_loop, ('iter', block, block, true, false)

        if isinstance(block.statements[0], LoopBody):
            cond = self.find_pred(block, False)
            if cond and isinstance(cond.statements[-1], Decision) and cond.statements[-1].addr < block.statements[0].addr and self.has_path(block, cond):
                return self.build_loop, ('while', cond, cond, block, cond.find_succ(True))

            cond = self.find_pred(block, True)
            if cond and isinstance(cond.statements[-1], Decision) and cond.statements[-1].addr > block.statements[0].addr and self.has_path(block, cond):
                return self.build_loop, ('repeat', cond, block, block, cond.find_succ(False))

            for pred in self.pred[block]:
                if pred.condition is None:
                    if pred.tail and pred.tail.statements[-1].addr > block.statements[0].addr and self.has_path(block, pred.tail):
                        return self.build_loop, ('while_true', block, block, block, None)

    def find_pred(self, block: Block, cond) -> Block:
        for e in self.pred[block]:
            if e.condition is cond:
                return e.tail

    def has_path(self, src: Block, dst: Block):
        stack = [src]
        visited = set()

        while stack:
            block = stack.pop(0)
            if block in visited:
                continue
            visited.add(block)
            if block == dst:
                return True
            stack.extend([e.tail for e in block.succ if e.tail not in visited])

        return False

    def collapse_condition(self, root):
        if len(root.succ) == 2 and isinstance(root.statements[-1], Decision):
            true: Block = root.find_succ(True)
            false: Block = root.find_succ(False)
            if isinstance(false.statements[-1], Decision) and len(self.pred[false]) == 1 and not isinstance(false.statements[0], LoopBody):
                if false.find_succ(True) is true:
                    logger.trace('{} R or F -> T, Ff'.format(root))
                    return self.merge_decision, (root, false, 'or', [Edge(true, True), Edge(false.find_succ(False), False)])

                if false.find_succ(False) is true:
                    logger.trace('{} not R and F -> Ft, T'.format(root))
                    return self.merge_decision, (root, false, 'and', [Edge(false.find_succ(True), True), Edge(true, False)], True)

            if isinstance(true.statements[-1], Decision) and len(self.pred[true]) == 1 and not isinstance(true.statements[0], LoopBody):
                if true.find_succ(True) is false:
                    logger.trace('{} not R or T -> F, Tf'.format(root))
                    return self.merge_decision, (root, true, 'or', [Edge(false, True), Edge(true.find_succ(False), False)], True)

                if true.find_succ(False) is false:
                    logger.trace('{} R and T -> Tt, F'.format(root))
                    return self.merge_decision, (root, true, 'and', [Edge(true.find_succ(True), True), Edge(false, False)])

    def construct_if(self, block: Block):
        if len(block.succ) == 2 and isinstance(block.statements[-1], Decision):
            true = block.find_succ(True)
            false = block.find_succ(False)
            if true == false:
                nothing = Block([Nop()])
                return self.build_decision, (block, nothing, None, true)
            if len(true.succ) == 1 and len(self.pred[true]) == 1 and true.succ[0].tail is false:
                logger.debug('if true')
                return self.build_decision, (block, true, None, false)

            if len(false.succ) == 1 and len(self.pred[false]) == 1 and false.succ[0].tail is true:
                logger.debug('if false')
                return self.build_decision, (block, false, None, true, True)

            if len(true.succ) == 1 and len(false.succ) == 1 and len(self.pred[true]) == 1 and len(self.pred[false]) == 1 and true.succ[0].tail is false.succ[0].tail:
                logger.debug('if true else false')
                return self.build_decision, (block, true, false, true.succ[0].tail)

            if not true.succ and not false.succ and len(self.pred[true]) == 1 and len(self.pred[false]) == 1:
                logger.debug('if true else false')
                return self.build_decision, (block, true, false, None)

            if not true.succ:
                if len(self.pred[true]) == 1:
                    logger.debug('if true')
                    return self.build_decision, (block, true, None, false)
                if len(true.statements) == 1 and isinstance(true.statements[0], Return):
                    logger.debug('if true')
                    r: Return = true.statements[-1]
                    return self.build_decision, (block, Block([Return(r.returns)]), None, false)

            if not false.succ:
                if len(self.pred[false]) == 1:
                    logger.debug('if false')
                    return self.build_decision, (block, false, None, true, True)
                if len(false.statements) == 1 and isinstance(false.statements[0], Return):
                    logger.debug('if false')
                    r: Return = false.statements[-1]
                    return self.build_decision, (block, Block([Return(r.returns)]), None, true, True)

    def create_dot(self, name=None):
        """For debug, use
        self.create_dot(name)
        in PyCharm debug view -> Evaluate Expression to show current control flow graph"""

        from graphviz import Digraph
        dot = Digraph(name=name, node_attr={'shape': 'box', 'margin': '0'}, graph_attr={'rankdir': 'TB', 'labeljust': 'l'})

        for block in self.blocks():
            dot.node('n{}'.format(block.index), '{} {}\n{}'.format(block.index, block.statements[0].addr if block.statements else '', '\n'.join(str(s) for s in block.statements)))
            for edge in block.succ:
                label = ''
                if edge.condition is True:
                    label = 't'
                elif edge.condition is False:
                    label = 'f'
                dot.edge('n{}'.format(block.index), 'n{}'.format(edge.tail.index), label=label)

        dot.view()
        os.unlink('{}.gv'.format(name if name else 'Graph'))

    def build_loop(self, loop_type, loop: Block, entry: Block, body: Block, out: Block):
        logger.debug('build_loop {} is {} loop in graph {}'.format(loop, loop_type, self.root))
        if loop_type in {'for', 'repeat'}:
            loop.succ = []
        if loop_type == 'for_return':
            for_init: ForInit = entry.statements[-1]
            entry.statements[-1] = For(for_init, StatementList(body.statements))
            body_blocks = [body]
        else:
            body_blocks = self.get_loop_body(entry, body, out)
        if loop_type == 'for':
            for_init: ForInit = entry.statements[-1]
            for_loop = loop.statements[-1]
            loop.statements[-1] = Nop()
            assert isinstance(for_loop, ForLoop)
            assert for_loop.start.slot == for_init.start.slot
            entry.statements[-1] = For(for_init, StatementList(Graph(body).root.statements))
        elif loop_type == 'iter':
            iter_loop = entry.statements.pop()
            iter_call: IterCall = entry.statements[-1]
            assert isinstance(iter_loop, IterLoop)
            assert iter_loop.index.slot == iter_call.generator.slot + 3
            entry.statements[-1] = ForIn(iter_call, StatementList(Graph(body).root.statements))
        elif loop_type == 'while':
            body.statements[0] = Nop()
            decision: Decision = entry.statements[-1]
            decision.reverse()
            entry.statements = [While(StatementList(entry.statements), StatementList(Graph(body).root.statements))]
        elif loop_type == 'while_true':
            entry.statements[0] = Nop()
            entry.statements = [While(StatementList([Condition(UnExp('', Primitive(True)))]), StatementList(Graph(body).root.statements))]
        else:
            body.statements[0] = Nop()
            decision: Decision = loop.statements[-1]
            decision.reverse()
            loop.statements[-1] = Nop()
            entry.statements = [Repeat(decision, StatementList(Graph(body).root.statements))]

        entry.succ = [Edge(out)] if out else []
        for b in body_blocks:
            del b

    def get_loop_body(self, entry: Block, body: Block, out: Block) -> List[Block]:
        visited = {entry, out}
        stack = [body]
        body_blocks = []
        exit_block = Block([Nop()])
        while stack:
            block = stack.pop(0)
            visited.add(block)
            body_blocks.append(block)
            for edge in block.succ:
                if edge.tail is entry:
                    edge.tail = exit_block
            if any([e.tail == out for e in block.succ]):
                if isinstance(block.statements[-1], Decision):
                    break_block = Block([Break()])
                    if block.find_succ(False) == out:
                        # reverse the condition so true edge is break
                        decision: Decision = block.statements[-1]
                        decision.reverse()
                        target = block.find_succ(True)
                    else:
                        target = block.find_succ(False)
                    block.succ = [Edge(break_block, True), Edge(target, False)]
                else:
                    assert len(block.succ) == 1 and block.succ[0].condition is None
                    block.statements.append(Break())
                    block.succ = []
            stack = [e.tail for e in block.succ if e.tail not in visited] + stack

        logger.debug('head is {}, out is {}, body is {}'.format(entry, out, body_blocks))
        return body_blocks

    def merge_decision(self, block: Block, merged: Block, op, new_edges, reverse_left=False):
        logger.debug('merge_decision block:{} merged:{} new_edges:{}'.format(block, merged, new_edges))
        merged.succ = []
        left: Decision = block.statements[-1]
        if reverse_left:
            left.reverse()
        block.statements[-1] = BinCondition(op, left, StatementList(Graph(merged).root.statements))
        block.succ = new_edges
        del merged

    def build_decision(self, block: Block, then, other, out, reverse_condition=False):
        logger.debug('build_decision block:{} then:{} other:{} out:{} reverse_condition:{}'.format(block, then, other, out, reverse_condition))
        deleted = []
        condition: Decision = block.statements[-1]
        if then:
            deleted.append(then)
            then.succ = []
            then = StatementList(then.statements)
        if other:
            deleted.append(other)
            other.succ = []
            other = StatementList(other.statements)
        if reverse_condition:
            condition.reverse()
        block.statements[-1] = If(condition, then, other)
        block.succ = [Edge(out)] if out else []
        for b in deleted:
            del b

    def simplify(self):
        """ Remove empty blocks and edges"""
        # remove blocks with no statement
        for block in self.blocks():
            for edge in block.succ:
                while (not edge.tail.statements or all(isinstance(s, Nop) for s in edge.tail.statements)) and len(edge.tail.succ) == 1:
                    logger.trace('remove block {}'.format(edge.tail))
                    empty = edge.tail
                    edge.tail = edge.tail.succ[0].tail
                    del empty

        self.update_pred()
        # remove single in single out edge
        for block in self.blocks():
            while len(block.succ) == 1 and block.succ[0].tail != self.root and len(self.pred[block.succ[0].tail]) == 1:
                merged = block.succ[0].tail
                logger.debug('merge edge {} {}'.format(block, block.succ[0]))
                block.statements += merged.statements
                block.succ = merged.succ
                del merged
        self.update_pred()

    def update_pred(self):
        """
        Update predecessors table
        """
        self.pred.clear()
        for block in self.blocks():
            for edge in block.succ:
                self.pred[edge.tail].append(Edge(block, edge.condition))
