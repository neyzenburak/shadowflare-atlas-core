"""Read-only extraction of the game's RCLIB-L compressed data."""
from pathlib import Path
import struct
import capstone
import pefile

from paths import WORK as ROOT

def item_substitution():
    pe = pefile.PE(str(ROOT / 'input' / 'ShadowFlare.exe'))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    table = [None] * 256
    for ins in md.disasm(pe.get_data(0x62F80, 0x7EE), 0x462F80):
        if ins.mnemonic != 'mov' or len(ins.operands) != 2: continue
        dest, src = ins.operands
        if dest.type != capstone.x86.X86_OP_MEM: continue
        value = src.imm if src.type == capstone.x86.X86_OP_IMM else (0 if src.type == capstone.x86.X86_OP_REG and src.reg == capstone.x86.X86_REG_BL else None)
        if value is None: continue
        if dest.size != 1 or dest.mem.base != capstone.x86.X86_REG_ESP: continue
        index = dest.mem.disp - 0x3C - (8 if ins.address >= 0x4635F4 else 0)
        if 0 <= index < 256: table[index] = value
    assert None not in table
    assert len(set(table)) == 256
    return bytes(table)

def lz_decode(data):
    assert data[:7] == b'RCLIB-L'
    expected, packed = struct.unpack_from('<II', data, 8)
    assert packed == len(data) - 16
    ring = bytearray(4096)
    pos, cursor = 0xFEE, 16
    out = bytearray()
    while cursor < len(data):
        flags = data[cursor]
        cursor += 1
        for bit in (128,64,32,16,8,4,2,1):
            if cursor >= len(data): break
            if flags & bit:
                a, b = data[cursor:cursor+2]
                cursor += 2
                source = a | ((b & 0xF0) << 4)
                for j in range((b & 15) + 3):
                    value = ring[(source + j) & 4095]
                    out.append(value)
                    ring[pos] = value
                    pos = (pos + 1) & 4095
            else:
                value = data[cursor]
                cursor += 1
                out.append(value)
                ring[pos] = value
                pos = (pos + 1) & 4095
    assert len(out) == expected, (len(out), expected)
    return bytes(out)

if __name__ == '__main__':
    for name in ['Table.Tbd','Item.Ibn']:
        b = (ROOT / 'input' / 'Parameter' / name).read_bytes()
        start = b.index(b'RCLIB-L')
        compressed = b[start:]
        if name == 'Item.Ibn':
            compressed = compressed[:16] + compressed[16:].translate(item_substitution())
        decoded = lz_decode(compressed)
        (ROOT / (name + '.decoded')).write_bytes(decoded)
        print(name, len(decoded), decoded[:160].hex(' '))
        if name == 'Item.Ibn':
            checksum = sum(x if x < 128 else x - 256 for x in decoded) & 0xFFFFFFFF
            assert checksum == struct.unpack_from('<I', b, 16)[0]
            print('Item signed-byte checksum verified:', hex(checksum))
