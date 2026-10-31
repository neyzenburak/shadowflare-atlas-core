"""Native viewport hooks authored against the original executable.

The scene always uses the complete client rectangle. Inventory and status
windows overlay that view; opening them does not change camera projection.
No configurator format, replacement NJP or third-party helper code is used.
"""
from pathlib import Path
import json
import struct
from resolution_layout import geometry
from live_drop import Code

PLAN=Path(__file__).with_name('viewport-plan.json')
MARKER=b'Atlas native viewport 1\0'


def detour(source,target,size=5):
    return b'\xe9'+struct.pack('<i',target-source-5)+b'\x90'*(size-5)


def scene_clip(base,width,height):
    c=Code(base).emit('8d 44 24 50')
    c.emit('68').u32(height-1).emit('68').u32(width-1).emit('6a 00 6a 00 50')
    c.emit('ff 15').u32(0x473624)
    c.emit('c7 44 24 24').u32(0).emit('c7 44 24 10').u32(width)
    # Retain the original non-layout transition that shared this native block.
    c.emit('8b 44 24 60')
    for mode in (1,16,17):c.emit('83 f8').emit(f'{mode:02x}').branch('0f 84','ready')
    c.emit('83 3d').u32(0x48d70c).emit('02').branch('0f 85','ready')
    c.emit('8b ce').call(0x44e830).emit('c7 05').u32(0x48d70c).u32(0)
    c.mark('ready')
    c.branch('e9',0x41ea11)
    return c.finish()


def scene_camera(base,width,height):
    c=Code(base).emit('8b 0f 8b 06 81 e9').u32(width//2).emit('2d').u32(height//2)
    c.emit('89 0f 89 06 c7 85 08 a0 00 00').u32(0)
    c.emit('c7 85 0c a0 00 00').u32(0).branch('e9',0x41eac1)
    return c.finish()


def build_changes(base,width,height):
    values=geometry(width,height);plan=json.loads(PLAN.read_text('utf8'));changes=[]
    for row in plan['immediates']:
        before=bytes.fromhex(row['before']);after=bytearray(before)
        struct.pack_into('<I',after,row['offset'],(values[row['value']]+row['add'])&0xffffffff)
        changes.append(dict(address=row['address'],before=before,after=bytes(after),label=row['label']))
    chunks=[(base+0x300,MARKER)]
    for address,offset,build in ((0x41e95b,0,scene_clip),(0x41ea5e,0x100,scene_camera)):
        before=bytes.fromhex(plan['entries'][str(address)])
        chunks.append((base+offset,build(base+offset,width,height)))
        changes.append(dict(address=address,before=before,after=detour(address,base+offset,len(before)),label='native full viewport'))
    for name in ('magicRender','magicInput'):
        row=plan[name];before=bytes.fromhex(row['before'])
        after=b'\xbe'+struct.pack('<I',224)+b'\x90'*(len(before)-5)
        changes.append(dict(address=row['address'],before=before,after=after,label='stable spell bar origin'))
    return changes,chunks


def installed(game):
    raw=game.read(0x41e95b,5)
    if raw[:1]!=b'\xe9':return False
    target=0x41e960+struct.unpack_from('<i',raw,1)[0]
    try:return game.read(target+0x300,len(MARKER))==MARKER
    except OSError:return False
