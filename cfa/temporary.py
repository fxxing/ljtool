#!/usr/bin/env python
# coding: utf-8
from collections import defaultdict
from typing import List, Dict, Optional, Set, Union

from bc.reader import Sequence
from cfa.ast import Statement, ForInit, IterCall, Slot, MultiRes, FuncCall, \
    Assign, Vararg, StatementList, BinCondition, If, For, ForIn, While, Repeat, TableElement, Constant, Return, Break, Node, MyList, TableConstructor
from cfa.visitor import Visitor, Path
from util import class_name


class Complete(Exception):
    pass


class Define(object):
    def __init__(self, statement: Optional[Statement], var, value):
        self.statement = statement
        self.var = var
        self.value = value

    def __repr__(self):
        return 'Define({}, {}, {}, {})'.format(self.statement.addr if self.statement else -1, self.var, self.value, self.statement)

    def __hash__(self):
        return hash((self.statement, self.var))

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __ne__(self, other):
        return self.__hash__() != other.__hash__()


class Usage(object):
    def __init__(self, statement: Statement, ref: Path):
        self.statement = statement
        self.ref = ref

    def __repr__(self):
        return 'Usage({}, {}, {})'.format(self.statement.addr, self.ref, self.statement)

    def __hash__(self):
        return hash(self.ref)

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __ne__(self, other):
        return self.__hash__() != other.__hash__()


class SlotVisitor(Visitor):
    def __init__(self):
        super().__init__()
        self.usages = set()

    def enter_slot(self, v: Slot):
        self.usages.add(v)

    def enter_multi_res(self, v: MultiRes):
        self.enter_slot(v)


class FuncCallVisitor(Visitor):
    def __init__(self):
        super().__init__()
        self.calls = set()

    def enter_func_call(self, v: FuncCall):
        self.calls.add(v)


class HashFuncCallVisitor(Visitor):
    def __init__(self, terminal):
        super().__init__()
        self.terminal = terminal
        self.has_func_call = False

    def visit(self, node: Node):
        if node == self.terminal:
            raise Complete()
        if isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                self.visit(v)
        else:
            getattr(self, 'enter_' + class_name(node))(node)

            for f in node.FIELDS:
                v = getattr(node, f)
                if v:
                    self.visit(v)

            getattr(self, 'leave_' + class_name(node))(node)

    def __getattr__(self, name):
        return self._missing

    def _missing(self, *args, **kwargs):
        pass

    def leave_func_call(self, _):
        self.has_func_call = True

    def enter_break(self, _):
        self.has_func_call = True

    def leave_return(self, _):
        self.has_func_call = True


class Prev(object):
    def __init__(self, statement: Statement, loop=False):
        self.statement = statement
        self.loop = loop


class Transformer(Visitor):
    def enter_repeat(self, s: Repeat):
        if isinstance(s.condition, BinCondition):
            assert s.condition.op == 'or'
            s.body.content.append(If(s.condition.left, StatementList([Break()])))
            s.body.content.extend(s.condition.right.content[:-1])
            s.condition = s.condition.right.content[-1]

    def enter_statement_list(self, sl: StatementList):
        i = 0
        while i < len(sl.content):
            s = sl.content[i]
            if isinstance(s, If):
                self.process_if(s, sl.content)
            i += 1

    def process_if(self, s: If, l):
        if s.other and s.other.addr < s.then.addr:
            s.condition.reverse()
            s.then, s.other = s.other, s.then

        if s.other and len(s.then.content) == 1 and isinstance(s.then.content[-1], (Break, Return)):
            l.extend(s.other.content)
            s.other = None

        if s.other and len(s.other.content) == 1 and isinstance(s.other.content[-1], (Break, Return)):
            s.condition.reverse()
            l.extend(s.then.content)
            s.then = s.other
            s.other = None

        if s.other and len(s.other.content) == 1 and isinstance(s.other.content[-1], If):
            if not s.else_ifs:
                s.else_ifs = []
            c: If = s.other.content[-1]
            self.process_if(c, s.other.content)
            s.else_ifs.append((c.condition, c.then))
            if c.other:
                s.other = c.other
            else:
                c.other = None


class Scope(object):
    def __init__(self, parent, number):
        self.parent = parent
        self.number = number

    def __repr__(self):
        return 's{}'.format(self.number)


# TODO this is very slow, optimize it
class TemporaryEliminator(object):
    def __init__(self, node: StatementList):
        super().__init__()

        self.parents = []
        self.scope_number = Sequence()
        self.scopes = [Scope(None, self.scope_number.next())]
        self.node = node
        self.assigns: Dict[Statement, Set[Define]] = defaultdict(set)
        self.usages: Dict[Statement, Set[Path]] = defaultdict(set)
        self.define_usages: Dict[Define, Set[Usage]] = defaultdict(set)
        self.usage_defines: Dict[Usage, Set[Define]] = defaultdict(set)
        self.prev: Dict[Statement, List[Prev]] = {}
        self.multi_values = set()
        self.delete_slots: Set[Slot] = set()
        self.iter_calls: Set[IterCall] = set()

    def visit(self, node: Node, path=None):
        if path is None:
            path = []
        if isinstance(node, Statement):
            node.scope = self.scopes[-1]
            self.parents.append(node)

        if 'visit_' + class_name(node) in dir(self):
            getattr(self, 'visit_' + class_name(node))(node, path)

        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                v.path = Path(node, i)
                self.visit(v, path + [v.path])
        else:
            getattr(self, 'enter_' + class_name(node))(node, path)

            for f in node.FIELDS:
                v = getattr(node, f)
                if v:
                    v.path = Path(node, f)
                    self.visit(v, path + [v.path])

            getattr(self, 'leave_' + class_name(node))(node, path)

        if isinstance(node, Statement):
            self.parents.pop()

    def __getattr__(self, name):
        return self._missing

    def _missing(self, *args, **kwargs):
        pass

    def process(self):
        self.collect_scopes()

    def collect_scopes(self):
        self.visit(self.node)

        assign_usages = {d.var for v in self.assigns.values() for d in v}
        for s, usages in self.usages.items():
            for v in usages:
                if v.get() not in assign_usages:
                    defines = self.get_defines(v, s)
                    # if all(not d.statement or not self.is_parent_scope(v.get().scope, d.statement.scope) for d in defines):
                    #     defines |= self.get_defines(v, s, limit_scope=s.scope)
                    # print(len(self.usages), '3')
                    usage = Usage(s, v)
                    self.usage_defines[usage] = defines
                    for define in defines:
                        if define.value is not None:
                            self.define_usages[define].add(usage)
        self.apply_inline()

        for ic in self.iter_calls:
            assign: Assign = list(filter(lambda p: isinstance(p.statement, Assign), self.get_prev(ic)))[0].statement
            assert len(assign.targets.content) == 3 and len(assign.values.content) == 1 and isinstance(assign.values.content[0], FuncCall)
            ic.iterator = assign.values.content[0]
            setattr(assign, '_invalid', True)
            ic.generator = ic.state = ic.control = None

        AssignRemover(self.delete_slots).visit(self.node)

    def apply_inline(self):
        changed = True
        while changed:
            changed = False
            for define, usages in sorted(list(self.define_usages.items()), key=lambda d: d[0].statement.addr)[:]:
                if self.can_inline(define, usages):
                    changed = True
                    for usage in usages:
                        usage.ref.set(define.value.get())
                    self.define_usages.pop(define)
                    self.delete_slots.add(define.var)

    def get_usages(self, value):
        visitor = SlotVisitor()
        visitor.visit(value)
        return visitor.usages

    def get_func_calls(self, value):
        visitor = FuncCallVisitor()
        visitor.visit(value)
        return visitor.calls

    def can_inline(self, define, usages):
        value = define.value.get()
        if value in self.multi_values:
            return False
        if not all(len(self.usage_defines[usage]) == 1 for usage in usages):
            return False
        if not len(usages) == 1 and not (isinstance(value, TableElement) and isinstance(value.key, Constant) and value.key.value == '_env'):
            return False
        if isinstance(value, FuncCall):
            return self.can_inline_func_call(define, usages)
        if isinstance(value, Vararg) and not isinstance(define.statement.targets.content[0], MultiRes):
            return False
        for usage in usages:
            if isinstance(usage.ref.parent, TableElement) and usage.ref.key == 'table' and isinstance(define.value.get(), TableConstructor):
                return False
            for v in self.get_usages(value):
                if self.get_defines(v, usage.statement) != self.get_defines(v, define.statement):
                    return False
        return True

    def can_inline_func_call(self, define, usages):
        sl, index = define.statement.path.parent, define.statement.path.key
        assert isinstance(sl, list)
        for usage in usages:
            if not self.can_inline_func_call_for_usage(sl, index, usage):
                return False
        return True

    def is_parent_scope(self, s1, s2):
        if s1 == s2:
            return True
        parent = s1.parent
        while parent:
            if parent == s2:
                return True
            parent = parent.parent
        return False

    def can_inline_func_call_for_usage(self, sl, index, usage):
        for i in range(index + 1, len(sl)):
            s = sl[i]
            if self.contains(s, usage.ref):
                if isinstance(s, If):
                    return self.contains(s.condition, usage.ref) and not self.has_func_call(s.condition, usage.ref.get())
                elif isinstance(s, For):
                    return self.contains(s.init, usage.ref) and not self.has_func_call(s.init, usage.ref.get())
                elif isinstance(s, ForIn):
                    return self.contains(s.call, usage.ref) and not self.has_func_call(s.call, usage.ref.get())
                elif isinstance(s, While):
                    return self.contains(s.condition, usage.ref) and not self.has_func_call(s.condition, usage.ref.get())
                elif isinstance(s, Repeat):
                    return False
                else:
                    return not self.has_func_call(s, usage.ref.get())
            elif self.has_func_call(s, usage.ref.get()):
                return False
        else:
            return False

    def contains(self, s, path):
        parent = path.parent
        while parent:
            if s is parent:
                return True
            if hasattr(parent, 'path'):
                parent = parent.path.parent
            else:
                parent = None
        return False

    def has_func_call(self, s, terminal):
        visitor = HashFuncCallVisitor(terminal)
        try:
            visitor.visit(s)
        except Complete:
            pass
        return visitor.has_func_call

    def get_defines(self, v: Union[Slot, Path], start, include_start=False, expanded=None, limit_scope=None):
        if isinstance(v, Path):
            v = v.get()
        if expanded is None:
            expanded = set()
        if include_start:
            lasts = [start]
        else:
            lasts, ex = self.get_lasts(self.get_prev(start), expanded)
            expanded |= ex
        while lasts:
            if len(lasts) > 1:
                ds = set()
                for s in lasts:
                    ds |= self.get_defines(v, s, True, expanded, limit_scope)
                return ds

            if not limit_scope or self.is_parent_scope(limit_scope, lasts[0].scope):
                for define in self.assigns[lasts[0]]:
                    if isinstance(define.var, Slot) and isinstance(v, Slot) and v.slot == define.var.slot:
                        return {Define(lasts[0], define.var, define.value)}
            lasts, ex = self.get_lasts(self.get_prev(lasts[0]), expanded)
            expanded |= ex

        return {Define(None, None, None)}

    def get_lasts(self, prev: List[Prev], expanded):
        lasts = []
        ex = set()
        if prev:
            for p in prev:
                if p.loop:
                    if p.statement not in expanded:
                        lasts.extend(self.get_last(p.statement))
                        ex.add(p.statement)
                else:
                    lasts.extend(self.get_last(p.statement))
        return lasts, ex

    def get_last(self, s: Statement) -> List[Statement]:
        if not s:
            return []
        if isinstance(s, BinCondition):
            return self.get_last(s.right)
        if isinstance(s, StatementList):
            return self.get_last(s.content[-1])
        if isinstance(s, If):
            return self.get_last(s.then) + (self.get_last(s.other) if s.other else self.get_last(s.condition))
        if isinstance(s, For):
            return self.get_last(s.init)
        if isinstance(s, ForIn):
            return self.get_last(s.call)
        if isinstance(s, (While, Repeat)):
            return self.get_last(s.condition)
        return [s]

    def get_prev(self, s):
        if s is self.node or s is self.node.content[0]:
            return []
        return self.prev[s]

    def enter_assign(self, s: Assign, _):
        if len(s.targets.content) == len(s.values.content):
            [self.assigns[s].add(Define(s, v, Path(s.values.content, i))) for i, v in enumerate(s.targets.content)]
        else:
            self.multi_values.add(s.values.content[0])
            path = Path(s.values.content, 0)
            [self.assigns[s].add(Define(s, v, path)) for i, v in enumerate(s.targets.content)]

    def enter_slot(self, s: Slot, path: List[Path]):
        s.scope = self.scopes[-1]
        self.usages[self.parents[-1]].add(path[-1])

    def enter_multi_res(self, v: MultiRes, path: List[Path]):
        self.enter_slot(v, path)

    def enter_for_init(self, s: ForInit, _):
        self.assigns[s].add(Define(s, s.index, None))

    def enter_iter_call(self, s: IterCall, _):
        [self.assigns[s].add(Define(s, v, None)) for v in s.values.content]
        if not s.iterator:
            self.iter_calls.add(s)

    def enter_bin_condition(self, s: BinCondition, _):
        self.prev[s.left] = self.get_prev(s)
        self.prev[s.right] = self.get_prev(s)

    def enter_statement_list(self, s: StatementList, _):
        for i, c in enumerate(s.content):
            self.prev[c] = self.get_prev(s) if i == 0 else [Prev(s.content[i - 1])]

    def visit_if(self, s: If, path):
        self.prev[s.condition] = self.get_prev(s)
        self.prev[s.then] = [Prev(s.condition)]
        if s.other:
            self.prev[s.other] = [Prev(s.condition)]
        self.visit_field(s, 'condition', path)
        self.visit_field(s, 'then', path, True)
        if s.other:
            self.visit_field(s, 'other', path, True)

    def visit_for(self, s: For, path):
        self.prev[s.body] = [Prev(s.init)]
        self.prev[s.init] = self.get_prev(s) + [Prev(s.body, True)]
        self.visit_field(s, 'init', path)
        self.visit_field(s, 'body', path, True)

    def visit_for_in(self, s: ForIn, path):
        self.prev[s.body] = [Prev(s.call)]
        self.prev[s.call] = self.get_prev(s) + [Prev(s.body, True)]
        self.visit_field(s, 'call', path)
        self.visit_field(s, 'body', path, True)

    def visit_while(self, s: While, path):
        self.prev[s.body] = [Prev(s.condition)]
        self.prev[s.condition] = self.get_prev(s) + [Prev(s.body, True)]
        self.visit_field(s, 'condition', path)
        self.visit_field(s, 'body', path, True)

    def visit_repeat(self, s: Repeat, path):
        self.prev[s.condition] = [Prev(s.body)]
        self.prev[s.body] = self.get_prev(s) + [Prev(s.condition, True)]
        self.visit_field(s, 'body', path)
        self.visit_field(s, 'condition', path)

    def visit_field(self, s, f, path, new_scope=False):
        if new_scope:
            self.scopes.append(Scope(self.scopes[-1], self.scope_number.next()))
        self.visit(getattr(s, f), path + [Path(s, f)])
        if new_scope:
            self.scopes.pop()


class AssignRemover(Visitor):
    def __init__(self, deleted):
        super().__init__()
        self.deleted = deleted

    def enter_assign(self, s: Assign):
        for v in self.deleted:
            if v in s.targets.content:
                i = s.targets.content.index(v)
                s.targets.content.pop(i)
                s.values.content.pop(i)
                if not s.targets.content:
                    setattr(s, '_invalid', True)

    def leave_statement_list(self, sl: StatementList):
        sl.content = MyList(list(filter(lambda s: not hasattr(s, '_invalid'), sl.content)))
