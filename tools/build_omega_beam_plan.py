"""Compile the two reviewed x86 hooks; runtime needs only the stdlib."""
import hashlib,json,struct,sys
from pathlib import Path
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_32,CS_OP_IMM,CS_OP_MEM,CS_GRP_JUMP,CS_GRP_CALL
from keystone import Ks,KS_ARCH_X86,KS_MODE_32
ROOT=Path(__file__).resolve().parents[1]
BASE=0x30000000;SIZE=0x800000
p=pefile.PE(str(ROOT.parent/'shadowflare-drop-analysis/resolution-fix/ShadowFlare.exe'))
engine=Ks(KS_ARCH_X86,KS_MODE_32);decoder=Cs(CS_ARCH_X86,CS_MODE_32);decoder.detail=True
parts=[]
for name,offset in [('input',0),('render',0x1000)]:
    source=(ROOT/'tools'/('omega_'+name+'.asm')).read_text('utf8')
    source='\n'.join(line.split(';')[0] for line in source.splitlines())
    raw=bytes(engine.asm(source,BASE+offset)[0]);fixes=[]
    for i in decoder.disasm(raw,BASE+offset):
        for operand in i.operands:
            if operand.type==CS_OP_MEM and BASE<=operand.mem.disp<BASE+SIZE:
                fixes.append(dict(offset=i.address-BASE-offset+i.disp_offset,kind='absolute'))
            if operand.type==CS_OP_IMM:
                value=operand.imm&0xffffffff
                if i.group(CS_GRP_JUMP) or i.group(CS_GRP_CALL):
                    if not BASE<=value<BASE+SIZE:
                        fixes.append(dict(offset=i.address-BASE-offset+i.imm_offset,kind='relative',target=value,end=i.address-BASE+i.size))
                elif BASE<=value<BASE+SIZE:
                    fixes.append(dict(offset=i.address-BASE-offset+i.imm_offset,kind='absolute'))
    parts.append(dict(name=name,offset=offset,code=raw.hex(),fixes=fixes))
assert len(bytes.fromhex(parts[0]['code']))<0x1000
assert len(bytes.fromhex(parts[1]['code']))<0xc00
spans=[(0x441cf2,6),(0x41ebfd,6),(0x459690,0x8c5),(0x412a40,0x1b),(0x4299e0,0x50),(0x4145b0,0x3cf),(0x434cb0,0x18),(0x441cad,0x2a)]
verified=[dict(address=a,length=n,sha256=hashlib.sha256(p.get_data(a-0x400000,n)).hexdigest()) for a,n in spans]
out=dict(version=1,referenceBase=BASE,size=SIZE,parts=parts,verified=verified)
(ROOT/'app/omega-beam-plan.json').write_text(json.dumps(out,separators=(',',':'))+'\n','utf8')
print({part['name']:len(bytes.fromhex(part['code'])) for part in parts})
