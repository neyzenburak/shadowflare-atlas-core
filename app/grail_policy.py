"""Shared, character-bound native Premium lookup for loot and cosmetic effects."""
import struct
from live_drop import Code,GAME_MODE

MAX_ENTRIES=4096
HEADER=64
RECORD=12

def found_keys(entries):
    return frozenset(k for k,e in entries.items() if e.get('first_pickup') or e.get('first_owned') or e.get('manual'))

def policy_image(keys,found=(),player=0,filename=b'',name=b'',ready=False):
    rows=sorted(set(tuple(map(int,k.split(':'))) for k in keys))
    if len(rows)>MAX_ENTRIES or any(c>2 or c<0 or not 0<=i<=0xffffffff for c,i in rows):
        raise ValueError('Invalid Premium policy catalogue')
    found=set(found);out=bytearray(HEADER+len(rows)*RECORD)
    struct.pack_into('<2I',out,0,int(ready),player)
    out[8:22]=filename[:14].ljust(14,b'\0');out[24:36]=name[:12].ljust(12,b'\0')
    struct.pack_into('<I',out,36,len(rows))
    for n,(cat,ident) in enumerate(rows):struct.pack_into('<3I',out,HEADER+n*RECORD,cat,ident,int(f'{cat}:{ident}' in found))
    return bytes(out)

def make_lookup(address,pointer_slot):
    """ECX=item -> EAX=matching record, or 0 for unknown/stale character policy.

    Only reads data. The pickup observer alone sets the record's found DWORD.
    Binding checks run in the game thread, before every use of a found flag.
    """
    c=Code(address).emit('53 56 57 55 8b f1 8b 3d').u32(pointer_slot)
    c.emit('85 ff').branch('0f 84','fail').emit('83 3f 01').branch('0f 85','fail')
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85','fail')
    c.emit('a1').u32(0x48ce0c).emit('85 c0').branch('0f 84','fail')
    c.emit('8b 08 85 c9').branch('0f 84','fail').emit('83 f9 04').branch('0f 87','fail')
    c.emit('8b 50 08 3b d1').branch('0f 83','fail')
    c.emit('8b 40 04 85 c0').branch('0f 84','fail')
    c.emit('8b 2c 90 85 ed').branch('0f 84','fail').emit('3b 6f 04').branch('0f 85','fail')
    for off in (0,4,8):c.emit('8b 45').emit(f'{0x10+off:02x}').emit('3b 47').emit(f'{24+off:02x}').branch('0f 85','fail')
    c.emit('a1').u32(0x482dcc).emit('85 c0').branch('0f 84','fail')
    c.emit('8b 00 85 c0').branch('0f 84','fail')
    for off in (0,4,8):c.emit('8b 50').emit(f'{off:02x}').emit('3b 57').emit(f'{8+off:02x}').branch('0f 85','fail')
    c.emit('0f b7 50 0c 66 3b 57 14').branch('0f 85','fail')
    c.emit('33 db 8b 6f 24 81 fd').u32(MAX_ENTRIES).branch('0f 87','fail')
    c.mark('search').emit('3b dd').branch('0f 83','fail')
    c.emit('8d 0c 2b d1 e9 6b c1 0c 8d 44 07 40')
    c.emit('8b 56 0c 3b 10').branch('0f 82','lower').branch('0f 87','higher')
    c.emit('8b 56 14 3b 50 04').branch('0f 82','lower').branch('0f 87','higher')
    c.branch('e9','done')
    c.mark('lower').emit('8b e9').branch('e9','search')
    c.mark('higher').emit('8d 59 01').branch('e9','search')
    c.mark('fail').emit('33 c0').mark('done').emit('5d 5f 5e 5b c3')
    return c.finish()
