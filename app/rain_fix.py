"""Resolution-aware native rain: retain the game's particles, lines and timing."""
import math
import struct
from live_drop import Code

HOOK=0x41fe20
ORIGINAL=bytes.fromhex('8b 44 24 04 83 ec 10')
# State: in-flight calls, fractional births, owner, native intensity,
# births in last call, completed frames, total births (wrapping diagnostic).
STATE_SIZE=28
OBJECT=0x48d7a0


def rain_geometry(width,height):
    # Rain falls down-left. The old 180px margins cover its full 480px fall;
    # taller screens need the same wind allowance scaled with their height.
    margin=(180*height+479)//480
    return width+2*margin,margin


def patches(width,height):
    span,margin=rain_geometry(width,height)
    return (
        (0x41fe62,bytes.fromhex('b9 e8 03 00 00'),b'\xb9'+struct.pack('<I',span),'rain birth width'),
        (0x41fe69,bytes.fromhex('81 ea b4 00 00 00'),b'\x81\xea'+struct.pack('<I',margin),'rain wind margin'),
        (0x41ff59,bytes.fromhex('3d df 01 00 00'),b'\x3d'+struct.pack('<I',height-1),'rain lifetime height'),
    )


def rain_wrapper(base,trampoline,state,width,height):
    """Call the original thiscall once, with an exact fractional birth rate.

    The native loop re-reads this+4 after each birth, so both of its reads
    must see the scaled count. Restore the original weather intensity before
    returning. No extra random calls, new particle type or alternative clock.
    """
    span,_=rain_geometry(width,height)
    c=Code(base).emit('55 8b ec 53 56 57 8b f1 8b 7e 04')
    c.emit('f0 ff 05').u32(state)
    c.emit('c7 05').u32(state+16).u32(0)
    c.emit('83 7d 08 00').branch('0f 84','native')
    c.emit('85 ff').branch('0f 8e','native')
    c.emit('39 35').u32(state+8).branch('0f 85','reset')
    c.emit('39 3d').u32(state+12).branch('0f 84','scale')
    c.mark('reset').emit('89 35').u32(state+8).emit('89 3d').u32(state+12)
    c.emit('c7 05').u32(state+4).u32(0)
    c.mark('scale').emit('8b c7 b9').u32(span).emit('f7 e1') # EDX:EAX=rate*span
    c.emit('03 05').u32(state+4).emit('83 d2 00 b9').u32(1000).emit('f7 f1')
    c.emit('89 15').u32(state+4).emit('89 46 04 a3').u32(state+16)
    c.emit('01 05').u32(state+24)
    c.mark('native').emit('ff 75 0c ff 75 08 8b ce').call(trampoline)
    c.emit('89 7e 04 ff 05').u32(state+20)
    c.emit('f0 ff 0d').u32(state).emit('5f 5e 5b 5d c2 08 00')
    return c.finish()


def snapshot(game,width,height,state):
    """Read a suspended game's existing particles; never alter its weather."""
    tick,intensity,color,node=game.words(OBJECT,4)
    calls,remainder,owner,rate,births,frames,total=game.words(state,7)
    if calls and owner==OBJECT:intensity=rate
    seen=set();visible=[];grid=[[0]*3 for unused in range(3)]
    while node:
        if node in seen:raise RuntimeError('Cyclic native rain list')
        seen.add(node)
        raw=game.read(node,48)
        age,x,y=struct.unpack_from('<iii',raw)
        angle=struct.unpack_from('<d',raw,16)[0]
        speed=struct.unpack_from('<i',raw,24)[0]
        # The native loop increments age after submitting the current line.
        distance=speed*max(age-1,0)//100
        x+=int(math.cos(angle)*distance);y-=int(math.sin(angle)*distance)
        if 0<=x<width and 0<=y<height:
            visible.append((x,y));grid[y*3//height][x*3//width]+=1
        node=struct.unpack_from('<I',raw,44)[0]
    return dict(width=width,height=height,tick=tick,nativeIntensity=intensity,color=color,
                particles=len(seen),visible=len(visible),thirds=grid,
                bounds=([min(x for x,y in visible),min(y for x,y in visible),
                         max(x for x,y in visible),max(y for x,y in visible)] if visible else None),
                birthsLastFrame=births,completedFrames=frames,totalBirths=total,
                fractionalRemainder=remainder)
