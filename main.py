import os
from io import StringIO

from bc.formatter import Formatter
from bc.reader import Reader
from bc.writer import DumpWriter
from cfa.builder import Builder
from cfa.writer import LuaWriter


def get_dump(filename):
    reader = Reader(filename, 'utf-8')
    reader.read()
    return reader.dump


def write_python(dump, target):
    formatter = Formatter(dump, 'utf-8')
    with open(target, 'w') as f:
        f.write(formatter.format())


def write_dump(dump, target):
    writer = DumpWriter(dump, target, 'utf-8')
    writer.write()


def build_ast(dump):
    return Builder(dump.prototypes[0]).build(True)


def write_lua(dump, target):
    out = StringIO()
    LuaWriter(build_ast(dump), out).write()
    target_dir = os.path.dirname(os.path.abspath(target))
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    with open(target, 'w') as f:
        f.write(out.getvalue())


def decompile(src, target):
    write_lua(get_dump(src), target)


if __name__ == "__main__":
    decompile('test/loop.luajit', 'loop_out.lua')
