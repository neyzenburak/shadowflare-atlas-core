"""Read native RCLIB and table resources without changing game files."""
import struct


def lz_decode(data):
    """Decode the shipped RCLIB-L format; no game code is loaded."""
    if data[:7] != b'RCLIB-L' or len(data)<16: raise ValueError('Invalid RCLIB header')
    expected, packed = struct.unpack_from('<II',data,8)
    if packed != len(data)-16 or expected>64000000: raise ValueError('Invalid RCLIB size')
    ring=bytearray(4096); cursor=16; at=0xfee; out=bytearray()
    while cursor<len(data):
        flags=data[cursor];cursor+=1
        for bit in (128,64,32,16,8,4,2,1):
            if cursor>=len(data):break
            if flags&bit:
                if cursor+2>len(data):raise ValueError('Truncated RCLIB reference')
                a,b=data[cursor:cursor+2];cursor+=2;offset=a|((b&0xf0)<<4)
                for j in range((b&15)+3):
                    value=ring[(offset+j)&4095];out.append(value);ring[at]=value;at=(at+1)&4095
            else:
                value=data[cursor];cursor+=1;out.append(value);ring[at]=value;at=(at+1)&4095
            if len(out)>expected:raise ValueError('RCLIB output exceeds declared length')
    if len(out)!=expected:raise ValueError('RCLIB output length mismatch')
    return bytes(out)


def table_records(data):
    """Expose string cells while retaining each numeric table block verbatim."""
    pos=0
    def integer():
        nonlocal pos
        value,=struct.unpack_from('<i',data,pos);pos+=4;return value
    total=integer()
    if not 0<=total<=10000:raise ValueError('Invalid table count')
    tables=[]
    for _ in range(total):
        start=pos;number=integer();rows=integer();cols=integer()
        if not 0<=rows<10000 or not 0<=cols<1000:raise ValueError('Invalid table dimensions')
        pos+=rows*cols*4
        if pos>len(data):raise ValueError('Truncated numeric table')
        numeric=data[start:pos];cells=[]
        for _ in range(rows*cols):
            n=integer()
            if not 0<=n<=1000000 or pos+n>len(data):raise ValueError('Invalid table cell length')
            cells.append(bytes(x^255 for x in data[pos:pos+n]));pos+=n
        tables.append(dict(number=number,rows=rows,cols=cols,numeric=numeric,cells=cells))
    if pos!=len(data):raise ValueError('Trailing table data')
    return tables


def tbd_data(data):
    if data[:16]!=b'TABLE DATA V000\x1a':raise ValueError('Unsupported table signature')
    compressed,=struct.unpack_from('<i',data,16)
    if compressed not in (0,1):raise ValueError('Unknown table compression flag')
    if compressed:return lz_decode(data[20:])
    if len(data)<24:raise ValueError('Missing uncompressed table size')
    size,=struct.unpack_from('<I',data,20)
    if size!=len(data)-24:raise ValueError('Uncompressed table length mismatch')
    return data[24:]
