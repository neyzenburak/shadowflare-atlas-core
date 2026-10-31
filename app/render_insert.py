"""Skip redundant native bounds scans only where insertion is already valid.

Zero is always a valid insertion position. InsertSort obtains its index and
cursor by traversing this same list immediately before Insert, so its count
check and predecessor lookup can reuse that work. All other calls retain the
original count/index routines. Allocation and linking stay native.
"""
import struct
from live_drop import Code

INSERT_OFFSETS=(0x583a,0x68aa,0x6923)
STUB_OFFSETS=(0x400,0x480,0x500)
TARGET_OFFSETS=(0x59e0,0x6a20,0x6a00)

def make_count_stub(base,native,sorted_return=None):
    c=Code(base)
    # Native Insert saved SEH + EBX/ESI/EDI. This stub adds one return address.
    c.emit('83 7c 24 20 00').branch('0f 84','zero')
    if sorted_return is not None:
        c.emit('81 7c 24 1c').u32(sorted_return).branch('0f 85','native')
        c.emit('8b 44 24 20 85 c0').branch('0f 88','native')
        c.emit('33 c9 c3') # the caller only needs index <= count, known true
    c.mark('native').branch('e9',native)
    c.mark('zero').emit('33 c0 33 c9 c3')
    return c.finish()

def make_previous_stub(base,native,sorted_return):
    c=Code(base)
    c.emit('81 7c 24 20').u32(sorted_return).branch('0f 85','native')
    # Original InsertSort's ESI is the cell at the insertion point, saved by
    # Insert at entry ESP-20. This call has an extra argument + return address.
    c.emit('8b 44 24 0c 85 c0').branch('0f 84','native')
    c.emit('8b 40 0c c2 04 00')
    c.mark('native').branch('e9',native)
    return c.finish()

def make_insert_image(base,dll):
    return [(STUB_OFFSETS[0],make_count_stub(base+STUB_OFFSETS[0],dll+TARGET_OFFSETS[0])),
            (STUB_OFFSETS[1],make_count_stub(base+STUB_OFFSETS[1],dll+TARGET_OFFSETS[1],dll+0x6b18)),
            (STUB_OFFSETS[2],make_previous_stub(base+STUB_OFFSETS[2],dll+TARGET_OFFSETS[2],dll+0x6b18))]

def patches(base,dll):
    return [(dll+site,b'\xe8'+struct.pack('<i',target-site-5),
             b'\xe8'+struct.pack('<i',base+offset-(dll+site+5)))
            for site,target,offset in zip(INSERT_OFFSETS,TARGET_OFFSETS,STUB_OFFSETS)]
