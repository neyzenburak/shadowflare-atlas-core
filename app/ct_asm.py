"""Small declarative x86 encoder for user-supplied tables; never runs Lua/AA.

This is deliberately not an Auto Assembler interpreter. Only the operations
implemented below are accepted; all other source remains an unsupported note.
"""
import re
import struct

REG={name:i for i,name in enumerate(('eax','ecx','edx','ebx','esp','ebp','esi','edi'))}
JCC={'je':4,'jz':4,'jne':5,'jnz':5,'jl':12,'jge':13,'jnl':13,'jle':14,'jg':15,'jb':2,'jae':3}


def integer(text):
    text=text.strip().lower()
    if not re.fullmatch(r'-?(?:0x)?[0-9a-f]+',text):raise ValueError('Unsupported integer: '+text)
    return int(text,16)


def address(text,labels=None):
    text=text.strip().replace('"','')
    labels=labels or {}
    if text in labels:return labels[text]
    match=re.fullmatch(r'ShadowFlare\.exe(\.text)?\+([0-9a-fA-F]+)',text,re.I)
    if match:return (0x401000 if match[1] else 0x400000)+int(match[2],16)
    if re.fullmatch(r'[0-9a-fA-F]{6,8}',text):return int(text,16)
    raise ValueError('Unsupported address: '+text)


def memory(text,reg):
    match=re.fullmatch(r'\[([a-z]+)(?:\+([a-z]+)\*([1248]))?(?:\+([0-9a-fA-F]+))?\]',text)
    if not match or match[1] not in REG:raise ValueError('Unsupported memory operand: '+text)
    base=REG[match[1]];index=match[2];disp=int(match[4] or '0',16)
    mode=0 if disp==0 and base!=5 else 1 if -128<=disp<=127 else 2
    tail=b'' if mode==0 else struct.pack('<b',disp) if mode==1 else struct.pack('<I',disp&0xffffffff)
    if index or base==4:
        idx=REG[index] if index else 4
        scale={1:0,2:1,4:2,8:3}[int(match[3] or '1')]
        return bytes([(mode<<6)|(reg<<3)|4,(scale<<6)|(idx<<3)|base])+tail
    return bytes([(mode<<6)|(reg<<3)|base])+tail


def encode(line,pc,labels=None):
    parts=line.strip().split(None,1);op=parts[0].lower();args=[] if len(parts)==1 else [a.strip().lower() for a in parts[1].split(',')]
    if op=='nop':
        count=integer(args[0])if args else 1
        if not 1<=count<=128:raise ValueError('NOP count is outside the supported range')
        return b'\x90'*count
    if op=='db':return bytes(integer(a) for a in re.split(r'[ ,]+',parts[1].strip()))
    if op in ('jmp',*JCC):
        target=address(parts[1],labels);short=target-(pc+2)
        if -128<=short<=127:return bytes([0xeb if op=='jmp'else 0x70+JCC[op],short&255])
        prefix=b'\xe9' if op=='jmp'else bytes([0x0f,0x80+JCC[op]])
        return prefix+struct.pack('<i',target-pc-len(prefix)-4)
    if op in ('push','pop'):
        if args[0] in REG:return bytes([(0x50 if op=='push'else 0x58)+REG[args[0]]])
        if op=='push':return b'\x68'+struct.pack('<I',integer(args[0])&0xffffffff)
    if op=='mov' and len(args)==2:
        dest,src=args
        if dest in REG:
            if src in REG:return b'\x8b'+bytes([0xc0+REG[dest]*8+REG[src]])
            if src.startswith('['):return b'\x8b'+memory(src,REG[dest])
            return bytes([0xb8+REG[dest]])+struct.pack('<I',integer(src)&0xffffffff)
        if dest.startswith('['):
            if src in REG:return b'\x89'+memory(dest,REG[src])
            return b'\xc7'+memory(dest,0)+struct.pack('<I',integer(src)&0xffffffff)
    if op in ('xor','sub','add','cmp') and len(args)==2:
        dest,src=args;opcode={'xor':0x31,'sub':0x29,'add':0x01,'cmp':0x39}[op]
        if src in REG:
            if dest in REG:return bytes([opcode,0xc0+REG[src]*8+REG[dest]])
            if dest.startswith('['):return bytes([opcode])+memory(dest,REG[src])
    raise ValueError('Unsupported instruction: '+line)


def script_blocks(script):
    sections={'enable':[],'disable':[]};section=None
    for raw in script.splitlines():
        line=raw.split('//',1)[0].strip()
        if not line:continue
        if line.lower() in ('[enable]','[disable]'):section=line[1:-1].lower();continue
        if section is None:raise ValueError('Missing ENABLE section')
        if line.lower().startswith(('dealloc(','unregistersymbol(','label(')):continue
        sections[section].append(line)
    return sections


def assemble(script,base=0x2000000):
    """Return code writes plus an optional local allocation image.

    Allocation contents are assembled again at the actual remote address by
    the trainer. Native sites must be inside the verified executable's text.
    """
    lines=script_blocks(script)['enable'];allocations={};labels={};blocks=[];current=None
    for line in lines:
        if line.lower().startswith('alloc('):
            m=re.fullmatch(r'alloc\(([a-zA-Z_]\w*),([0-9a-fA-F]+)\)',line,re.I)
            if not m or allocations:raise ValueError('Only one bounded allocation is supported')
            size=integer(m[2])
            if not 1<=size<=4096:raise ValueError('Allocation is too large')
            allocations[m[1]]=size;labels[m[1]]=base;continue
        if line.endswith(':'):
            label=line[:-1].strip()
            if label in allocations:current=[base,[]];blocks.append(current)
            else:
                try:site=address(label)
                except ValueError:
                    if current is None:raise
                    current[1].append(('label',label));continue
                if not 0x401000<=site<0x473000:raise ValueError('Patch is outside game code')
                current=[site,[]];blocks.append(current)
            continue
        if current is None:raise ValueError('Instruction has no address')
        current[1].append(('instruction',line))
    # Resolve forward labels to a stable layout. Label jumps start as near jumps.
    for _ in range(8):
        previous=dict(labels)
        for start,body in blocks:
            pc=start
            for kind,line in body:
                if kind=='label':labels[line]=pc;continue
                try:pc+=len(encode(line,pc,labels))
                except ValueError:
                    if line.lower().split()[0] in ('jmp',*JCC):pc+=5 if line.lower().startswith('jmp ')else 6
                    else:raise
        if previous==labels:break
    writes=[];allocated=b''
    for start,body in blocks:
        raw=bytearray()
        for kind,line in body:
            if kind=='instruction':raw.extend(encode(line,start+len(raw),labels))
        if not raw:continue
        if start==base:
            if len(raw)>4096:raise ValueError('Generated allocation is too large')
            allocated=bytes(raw)
        else:
            if start+len(raw)>0x473000:raise ValueError('Patch ends outside game code')
            writes.append(dict(address=start,after=bytes(raw)))
    if not writes:raise ValueError('No supported code patch')
    return writes,allocated


def instruction_length(data):
    """Length decoder for the x86 subset accepted at imported patch sites.

    Unknown opcodes are rejected rather than guessing a boundary. This is not
    an execution engine and does not accept 16-bit/address-size prefixes.
    """
    op=data[0];at=1;immediate=0;modrm=False
    if 0x40<=op<=0x5f or op in (0x90,0x99,0xc3,0xcc):return 1
    if 0xb8<=op<=0xbf or op in (0x68,0xa1,0xa3,0xe8,0xe9,0x05,0x2d,0x3d):return 5
    if 0x70<=op<=0x7f or op in (0x6a,0xeb):return 2
    if op==0x0f:
        second=data[at];at+=1
        if 0x80<=second<=0x8f:return 6
        if second in (0xaf,0xb6,0xb7,0xbe,0xbf):modrm=True
        else:raise ValueError('Unsupported native opcode at patch boundary')
    elif op in (0x01,0x03,0x09,0x0b,0x21,0x23,0x29,0x2b,0x31,0x33,0x39,0x3b,0x84,0x85,0x89,0x8b,0x8d,0x8f,0xd1,0xd3,0xff):modrm=True
    elif op in (0x80,0x83,0xc1):modrm=True;immediate=1
    elif op in (0x81,0xc7,0x69):modrm=True;immediate=4
    else:raise ValueError('Unsupported native opcode at patch boundary')
    if modrm:
        value=data[at];at+=1;mode=value>>6;rm=value&7
        if mode!=3 and rm==4:
            sib=data[at];at+=1
            if mode==0 and sib&7==5:at+=4
        elif mode==0 and rm==5:at+=4
        if mode==1:at+=1
        elif mode==2:at+=4
    return at+immediate


def patch_span(data,minimum):
    at=0
    while at<minimum:
        at+=instruction_length(data[at:])
        if at>len(data):raise ValueError('Truncated native instruction')
    return at
