"""Reuse sequential lookups inside four verified immutable-list loops.

Cache keys include caller, stack frame, list, head and completed-sort generation.
Other callers and all nonsequential accesses execute the original native Get.
The loops only change object/cell properties; their list links stay unchanged.
"""
from live_drop import Code
IMPORT=0x473350
CODE_OFFSET=0x1800
CACHE_OFFSET=0x700
CALLERS=(0x403331,0x40340a,0x403435)
LOOP_SHA256='3e0fa7b3d7da0166896de8984fcfa91af9909d50753cc113b6d9162dc0462230'
BLOCK_IMPORT=0x473318
BLOCK_CODE=0x1c00
BLOCK_CACHE=0x1f00
BLOCK_CALLERS=(0x40f892,)
BLOCK_LOOP_SHA256='e8742122c8f180f9f7913bd4a1b2fb16c7167570a28d4f81f9c6058b4b4a8839'

def make_stub(base,native,data,cache,callers=CALLERS,next_offset=0x10):
    assert 0<next_offset<128
    c=Code(base).emit('9c f0 ff 05').u32(data).emit('9d')
    c.emit('55 8b ec 53 56 57 8b f1 8b 7d 08 8b 45 04')
    for i,caller in enumerate(callers):c.emit('3d').u32(caller).branch('0f 84',f'caller{i}')
    c.branch('e9','native')
    for i in range(len(callers)):
        c.mark(f'caller{i}').emit('bb').u32(cache+i*28).branch('e9','lookup')
    c.mark('lookup').emit('b8 01 00 00 00 87 03 85 c0').branch('0f 85','native')
    c.emit('39 73 04').branch('0f 85','miss')
    c.emit('8b 4b 08 41 3b cf').branch('0f 85','miss')
    c.emit('a1').u32(data+4).emit('39 43 10').branch('0f 85','miss')
    c.emit('8b 46 04 39 43 14').branch('0f 85','miss')
    c.emit('39 6b 18').branch('0f 85','miss')
    c.emit('8b 43 0c 85 c0').branch('0f 84','miss')
    c.emit(f'8b 40 {next_offset:02x} 8b d7').branch('e9','remember')
    c.mark('miss').emit('57 8b ce').branch('e8',native)
    c.mark('remember').emit('89 43 0c 89 73 04 89 7b 08')
    c.emit('8b 0d').u32(data+4).emit('89 4b 10 8b 4e 04 89 4b 14 89 6b 18 c7 03 00 00 00 00')
    c.branch('e9','return')
    c.mark('native').emit('57 8b ce').branch('e8',native)
    c.mark('return').emit('5f 5e 5b 5d 9c f0 ff 0d').u32(data).emit('9d c2 04 00')
    raw=c.finish();assert len(raw)<0x300
    return raw

def make_block_stub(base,native,data,cache):
    # The validated highlight loop starts at index zero and only changes RGB
    # properties. Index zero always refreshes the cursor through native Get;
    # subsequent requests follow the same object links directly.
    return make_stub(base,native,data,cache,BLOCK_CALLERS,0x3c)
