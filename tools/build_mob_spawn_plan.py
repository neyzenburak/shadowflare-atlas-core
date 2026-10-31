"""Rebuild the passive enemy plan from an original ShadowFlare v2.004 EXE.
Usage: python tools/build_mob_spawn_plan.py [path/to/ShadowFlare.exe]
Requires the development dependencies; never used by the runtime helper.
"""
import sys,json,struct,hashlib
from pathlib import Path
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1]
fixture=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT.parent/'shadowflare-drop-analysis/resolution-fix/ShadowFlare.exe'
im=pefile.PE(str(fixture)).get_memory_mapped_image()
md=Cs(CS_ARCH_X86,CS_MODE_32);md.detail=True
start=0x45b600;end=0x45b7b6;raw=im[start-0x400000:end-0x400000];relocs=[];attacks=[]
for i in md.disasm(raw,start):
 if i.imm_size==4 and i.mnemonic.startswith(('j','call')):
  target=i.operands[0].imm
  if i.mnemonic=='call' and target==0x45a2a0:attacks.append(i.address-start)
  else:relocs.append(dict(offset=i.address-start+i.imm_offset,end=i.address-start+i.size,target=target))
u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x100000);u.mem_write(0x400000,im)
sp=0x30008000;u.mem_map(0x30000000,0x10000);u.mem_map(0x31000000,4096)
u.mem_write(sp+0x3b4,struct.pack('<79I',*(0x10000000+n for n in range(79))))
u.mem_write(0x473480,struct.pack('<I',0x31000000));u.mem_write(0x473484,struct.pack('<I',0x31000010))
def hook(u,a,size,user):
 if a not in (0x31000000,0x31000010):return
 esp=u.reg_read(UC_X86_REG_ESP);ret=struct.unpack('<I',u.mem_read(esp,4))[0]
 u.reg_write(UC_X86_REG_ESP,esp+8);u.reg_write(UC_X86_REG_EAX,0);u.reg_write(UC_X86_REG_EIP,ret)
u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_X86_REG_ESP,sp)
u.emu_start(0x428c95,0x428f19,count=10000)
out=struct.unpack('<72I',u.mem_read(sp+0x294,288));mapping=[v-0x10000000 if 0x10000000<=v<0x10000000+79 else None for v in out]
assert mapping[4]==8 and mapping[(0x180-0xc4)//4]==14 and mapping[56] is None
verified=[]
for a,n in [(0x4298c0,0x110),(0x453aa0,0x1bb),(0x458f40,0x2d),(0x458f70,0x317),(0x459f60,0x9e),(start,end-start),(0x455ee0,0x22),(0x456080,0xf9),(0x454130,0x50),(0x4145b0,0x3d1),(0x476d98,40)]:
 verified.append(dict(address=a,size=n,sha256=hashlib.sha256(im[a-0x400000:a-0x400000+n]).hexdigest()))
plan=dict(version=1,idle=dict(address=start,bytes=raw.hex(),relocations=relocs,suppressedCalls=attacks),configMap=mapping,
          vtable=list(struct.unpack_from('<10I',im,0x76d98)),verified=verified)
(ROOT/'app/mob-spawn-plan.json').write_text(json.dumps(plan,indent=2),'utf8')
print(json.dumps({'mapping':mapping,'suppressedCalls':attacks,'idleBytes':len(raw)},indent=2))
