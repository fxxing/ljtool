#!/usr/bin/env python
# coding: utf-8
import array
import os
import struct
import sys


class Stream(object):
    def __init__(self):
        self.byteorder = sys.byteorder
        self.name = ''
        self.fd = None

    @classmethod
    def open(cls, filename, mode='rb'):
        self = cls()
        if hasattr(filename, 'write'):
            self.name = None
            self.fd = filename
        else:
            self.name = filename
            self.fd = open(filename, mode)
        return self

    def close(self):
        self.fd.close()

    def read_bytes(self, size=1):
        return self.fd.read(size)

    def read_byte(self):
        data = self.fd.read(1)
        return int.from_bytes(data, byteorder=sys.byteorder, signed=False)

    def read_zstring(self):
        string = b''
        while True:
            byte = self.read_bytes(1)
            if byte == b'\x00':
                return string
            else:
                string += byte

    def read_uleb128(self):
        value = self.read_byte()

        if value >= 0x80:
            shift = 0
            value &= 0x7f

            while True:
                byte = self.read_byte()

                shift += 7
                value |= (byte & 0x7f) << shift

                if byte < 0x80:
                    break

        return value

    def read_uleb128_33(self):
        lo = self.read_uleb128()
        is_float, lo = lo & 0x1, lo >> 1
        if is_float:
            hi = self.read_uleb128()
            return self._assemble_float(lo, hi)
        else:
            return self._process_sign(lo)

    def read_uint(self, size=4):
        value = self.read_bytes(size)

        return int.from_bytes(value, byteorder=self.byteorder, signed=False)

    def read_float(self):
        lo = self.read_uleb128()
        hi = self.read_uleb128()
        return self._assemble_float(lo, hi)

    def read_signed_int(self):
        return self._process_sign(self.read_uleb128())

    def _assemble_float(self, lo, hi):
        if sys.byteorder == 'big':
            float_as_int = lo << 32 | hi
        else:
            float_as_int = hi << 32 | lo

        return struct.unpack("=d", struct.pack("=Q", float_as_int))[0]

    def _process_sign(self, number):
        if number & 0x80000000:
            return -0x100000000 + number
        else:
            return number

    def write_byte(self, b):
        self.fd.write(bytes(chr(b), 'ascii'))

    def write_bytes(self, bs):
        self.fd.write(bs)

    def write_uleb128(self, value):
        bs = []
        while value != 0:
            bs.append(value & 0x7F | 0x80)
            value >>= 7
        if not bs:
            bs.append(0)
        bs[-1] &= 0x7F
        self.fd.write(array.array('B', bs).tobytes())

    def write_uint(self, value, size=4):
        value = int.to_bytes(value, size, byteorder=self.byteorder, signed=False)
        self.write_bytes(value)

    def write_float(self, value):
        lo, hi = self._dissemble_float(value)
        self.write_uleb128(lo)
        self.write_uleb128(hi)

    def _dissemble_float(self, value):
        value = struct.unpack("=Q", struct.pack("=d", value))[0]
        if sys.byteorder == 'big':
            return (value >> 32) & 0xFFFFFFFF, value & 0xFFFFFFFF
        else:
            return value & 0xFFFFFFFF, (value >> 32) & 0xFFFFFFFF

    def write_signed_int(self, value):
        if value >= 0:
            self.write_uleb128(value)
        else:
            self.write_uleb128(value + 0x100000000)

    def write_zstring(self, value):
        self.write_bytes(value + b'\x00')

    def write_uleb128_33(self, value):
        if isinstance(value, int):
            if value < 0:
                value += 0x100000000
            self.write_uleb128(value << 1)
        else:
            lo, hi = self._dissemble_float(value)
            self.write_uleb128((lo << 1) | 1)
            self.write_uleb128(hi)
