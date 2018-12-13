#!/usr/bin/env python
# coding: utf-8

from cfa.ast import Node, Statement
from util import class_name


class Visitor(object):
    def __init__(self):
        self.parents = []

    def visit(self, node: Node):
        if isinstance(node, Statement):
            self.parents.append(node)

        if 'visit_' + class_name(node) in dir(self):
            getattr(self, 'visit_' + class_name(node))(node)

        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                self.visit(v)
        else:
            getattr(self, 'enter_' + class_name(node))(node)

            for f in node.FIELDS:
                v = getattr(node, f)
                if v:
                    self.visit(v)

            getattr(self, 'leave_' + class_name(node))(node)

        if isinstance(node, Statement):
            self.parents.pop()

    def __getattr__(self, name):
        return self._missing

    def _missing(self, node):
        pass


class Path(object):
    def __init__(self, parent, key):
        self.parent = parent
        self.key = key

    def set(self, value):
        if isinstance(self.key, int):
            self.parent[self.key] = value
        else:
            setattr(self.parent, self.key, value)

    def get(self):
        if isinstance(self.key, int):
            return self.parent[self.key]
        else:
            return getattr(self.parent, self.key)

    def __repr__(self):
        return self.get().__repr__()

    def __hash__(self):
        if isinstance(self.parent, list):
            return hash((tuple(self.parent), self.key))
        return hash((self.parent, self.key))

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()
