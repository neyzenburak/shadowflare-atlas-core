"""Build the complete native-order graph sorter and its no-allocation fallback."""
import struct
from live_drop import Code
from graph_sort_core import CORE
from render_sort_core import CORE as FALLBACK_CORE

DATA_OFFSET=0x300
FALLBACK_OFFSET=0x100
GRAPH_OFFSET=0x800
CACHE_OFFSET=0x600
CACHE_SLOTS=8

def make_stub(base):
    c=Code(base);data=base+DATA_OFFSET
    c.emit('9c f0 ff 05').u32(data).emit('9d').branch('e8',base+GRAPH_OFFSET)
    c.emit('9c f0 ff 05').u32(data+4).emit('f0 ff 0d').u32(data).emit('9d c3')
    return c.finish()

def make_image(base,allocate,free):
    graph=CORE
    for magic,address in (('11111111',allocate),('22222222',free),('df9b5713',base+FALLBACK_OFFSET),('44444444',base+CACHE_OFFSET)):
        graph=graph.replace(bytes.fromhex(magic),struct.pack('<I',address))
    parts=[(0,make_stub(base)),(FALLBACK_OFFSET,FALLBACK_CORE+b'\xc3'),(GRAPH_OFFSET,graph)]
    image=bytearray(GRAPH_OFFSET+len(graph))
    assert len(parts[0][1])<FALLBACK_OFFSET and FALLBACK_OFFSET+len(FALLBACK_CORE)<DATA_OFFSET
    assert len(image)<0x1800
    for offset,raw in parts:image[offset:offset+len(raw)]=raw
    return bytes(image)
