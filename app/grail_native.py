"""Observe successful ground-to-backpack transfers, including cursor placement.

The hooks only write a private event buffer. Native loot, inventory and price
behavior is unchanged. No journal event is emitted for a failed pickup or buy.
"""
import struct
from live_drop import Code,GAME_MODE
from grail_policy import policy_image,make_lookup,MAX_ENTRIES,HEADER,RECORD as POLICY_RECORD

PICKUP=0x449ef0;INSERT=0x466bc0;DELETE=0x465640
PICKUP_BYTES=bytes.fromhex('8b44240483ec08')
INSERT_BYTES=bytes.fromhex('8b4424048b1189908c0000008901b801000000c20400')
DELETE_BYTES=bytes.fromhex('568b742408')
DATA=0x1000;RING=0x2000;CAPACITY=2048;RECORD=64
POLICY=RING+CAPACITY*RECORD;POLICY_LOOKUP=0xa00;POLICY_SLOT=DATA+80
SIZE=(POLICY+HEADER+MAX_ENTRIES*POLICY_RECORD+4095)&~4095
INSERT_STUB=0x400;DELETE_STUB=0x700;TRAMPOLINE=0x900

def enter(c,data):return c.emit('9c f0 ff 05').u32(data).emit('9d')
def leave(c,data):return c.emit('9c f0 ff 0d').u32(data).emit('9d')

def make_image(base,premium_keys=()):
    data=base+DATA;meta=data+16
    c=enter(Code(base),data).emit('55 8b ec 53 56 57 8b d9 8b 75 0c 33 ff')
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85','native')
    c.emit('83 7d 08 ff').branch('0f 84','native')
    c.emit('83 3d').u32(0x48ce34).emit('00').branch('0f 85','native')
    c.emit('85 f6').branch('0f 84','native')
    c.emit('83 7e 18 02').branch('0f 85','native')
    c.emit('83 7e 0c 02').branch('0f 87','native')
    c.emit('a1').u32(0x482dcc).emit('85 c0').branch('0f 84','native')
    c.emit('8b 00 85 c0').branch('0f 84','native')
    for off in (0,4,8):c.emit('8b 50').emit(f'{off:02x}').emit('89 15').u32(meta+off)
    c.emit('0f b7 50 0c 89 15').u32(meta+12)
    for off in (0,4,8):c.emit('8b 53').emit(f'{0x10+off:02x}').emit('89 15').u32(meta+16+off)
    for off,dest in ((0xc,28),(0x14,32),(0x1c,48)):
        c.emit('8b 56').emit(f'{off:02x}').emit('89 15').u32(meta+dest)
    c.emit('8b 83 58 04 00 00 8b 50 04 89 15').u32(meta+36)
    for off,dest in ((0x2e0,40),(0x2e4,44),(0x34,52)):
        c.emit('8b 93').u32(off).emit('89 15').u32(meta+dest)
    c.emit('89 1d').u32(meta+56).emit('89 35').u32(data+8).emit('89 1d').u32(data+12).emit('bf 01 00 00 00')
    c.mark('native').emit('ff 75 0c ff 75 08 8b cb').branch('e8',base+TRAMPOLINE)
    c.emit('85 ff').branch('0f 84','return')
    c.emit('83 f8 01').branch('0f 84','return')
    c.emit('3b 35').u32(data+8).branch('0f 85','return')
    c.emit('c7 05').u32(data+8).u32(0)
    c.mark('return').emit('5f 5e 5b 5d');leave(c,data).emit('c2 08 00')
    pickup=c.finish();assert len(pickup)<INSERT_STUB
    # Perform exactly the native list insertion, then observe its outcome.
    c=enter(Code(base+INSERT_STUB),data).emit(INSERT_BYTES[:-3].hex()).emit('9c 60')
    c.emit('83 3d').u32(GAME_MODE).emit('00').branch('0f 85','done')
    c.emit('8b 44 24 28 3b 05').u32(data+8).branch('0f 85','done')
    c.emit('8b 15').u32(data+12).emit('81 c2 14 05 00 00 3b ca').branch('0f 85','done')
    c.emit('8b 1d').u32(data+4).emit('43 8d 7b ff 81 e7').u32(CAPACITY-1)
    c.emit('c1 e7 06 81 c7').u32(base+RING).emit('c7 07 00 00 00 00 83 c7 04')
    c.emit('be').u32(meta).emit('b9 0f 00 00 00 fc f3 a5')
    c.emit('c7 05').u32(data+8).u32(0).emit('89 5f c0 89 1d').u32(data+4)
    # The successful backpack insertion commits the collection immediately,
    # before Python persists the journal. Subsequent deaths/frames see it now.
    c.emit('8b 4c 24 28').branch('e8',base+POLICY_LOOKUP).emit('85 c0').branch('0f 84','done')
    c.emit('c7 40 08 01 00 00 00')
    c.mark('done').emit('61 9d');leave(c,data).emit('c2 04 00')
    insertion=c.finish();assert INSERT_STUB+len(insertion)<DELETE_STUB
    # An item destroyed while on the cursor cannot later match a reused pointer.
    c=enter(Code(base+DELETE_STUB),data).emit('9c 60 8b 44 24 28 85 c0').branch('0f 84','done')
    c.emit('8b 00 3b 05').u32(data+8).branch('0f 85','done')
    c.emit('c7 05').u32(data+8).u32(0)
    c.mark('done').emit('61 9d');leave(c,data).emit(DELETE_BYTES.hex()).branch('e9',DELETE+len(DELETE_BYTES))
    deletion=c.finish();assert DELETE_STUB+len(deletion)<TRAMPOLINE
    trampoline=Code(base+TRAMPOLINE).emit(PICKUP_BYTES.hex()).branch('e9',PICKUP+len(PICKUP_BYTES)).finish()
    raw=bytearray(SIZE)
    for offset,part in ((0,pickup),(INSERT_STUB,insertion),(DELETE_STUB,deletion),(TRAMPOLINE,trampoline)):raw[offset:offset+len(part)]=part
    lookup=make_lookup(base+POLICY_LOOKUP,base+POLICY_SLOT);assert POLICY_LOOKUP+len(lookup)<DATA
    raw[POLICY_LOOKUP:POLICY_LOOKUP+len(lookup)]=lookup
    initial=policy_image(premium_keys);raw[POLICY:POLICY+len(initial)]=initial
    struct.pack_into('<I',raw,POLICY_SLOT,base+POLICY)
    return bytes(raw)

def patches(base):
    return [(at,old,b'\xe9'+struct.pack('<i',base+offset-at-5)+b'\x90'*(len(old)-5))
        for at,old,offset in ((INSERT,INSERT_BYTES[:6],INSERT_STUB),(DELETE,DELETE_BYTES,DELETE_STUB),(PICKUP,PICKUP_BYTES,0))]

def decode_record(raw,sequence):
    if len(raw)!=RECORD or struct.unpack_from('<I',raw)[0]!=sequence:raise ValueError('Grail olay sırası değişti.')
    filename=raw[4:20].split(b'\0',1)[0].decode('ascii')
    name=raw[20:32].split(b'\0',1)[0].decode('cp1252',errors='replace')
    kind,ident,map_id,x,y,instance,level,player=struct.unpack_from('<8I',raw,32)
    return dict(filename=filename,name=name,key=f'{kind}:{ident}',map=map_id,x=x,y=y,instance=instance,level=level,player=player)
