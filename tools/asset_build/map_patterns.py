"""Original NJP + one-bit SDW map resource decoder.

Uses the existing verified NJP compositor. SDW has the same v003 container;
RKC_UPDIB_UPD::Read branches on ShadowLowPat and forces one-bit DIB pixels.
"""
from pathlib import Path
from functools import lru_cache
import struct
import sys
from PIL import Image

from paths import WORK as ROOT
from decode_visuals import NJP,Reader,Part,Pattern
from decode_data import lz_decode


class MapNJP(NJP):
    def __init__(self,path):
        self.path=Path(path)
        r=Reader(self.path.read_bytes())
        signature=r.take(16)
        assert signature.startswith((b'NJudgeUniPat',b'ShadowLowPat')), (path,signature)
        self.shadow=signature.startswith(b'ShadowLowPat')
        self.version=int(signature[12:15])
        assert self.version in (1,2,3),(path,self.version)
        count,=r.get('i')
        if self.version>=3:total_bytes,=r.get('i')
        self.parts=[]
        for _ in range(count):
            bpp,w,h,compressed=r.get('4i')
            # ShadowLowPat stores the color-atlas bpp in its header; the
            # native reader overrides it to one bit for the actual mask.
            if self.shadow:bpp=1
            assert bpp in (1,4,8),(path,bpp)
            stride=((w*bpp+31)//32)*4
            if compressed:
                hdr=r.take(16)
                expected,packed=struct.unpack_from('<II',hdr,8)
                raw=lz_decode(hdr+r.take(packed))
            else:raw=r.take(stride*h)
            assert len(raw)==stride*h,(str(path),bpp,w,h,compressed,len(raw),stride*h)
            if not w or not h:
                im=Image.new('P',(1,1))
            elif bpp==1:
                # DIB bits are MSB first, aligned to four-byte rows, bottom up.
                mask=Image.frombytes('1',(w,h),raw,'raw','1',stride,-1)
                im=mask.convert('P').point(lambda p: 1 if p else 0)
            else:
                pix=bytearray(w*h)
                for y in range(h):
                    row=raw[(h-1-y)*stride:(h-y)*stride]
                    if bpp==8:pix[y*w:(y+1)*w]=row[:w]
                    else:pix[y*w:(y+1)*w]=bytes((row[x//2]>>(4 if x%2==0 else 0))&15 for x in range(w))
                im=Image.frombytes('P',(w,h),bytes(pix))
            self.parts.append(Part(bpp,w,h,im))
        count,=r.get('i')
        if self.version>=3:total_cells,=r.get('i')
        self.patterns=[]
        for _ in range(count):
            n,*rect=r.get('5i')
            palette,=r.get('i')
            self.patterns.append(Pattern(tuple(rect),palette,[r.get('7i') for _ in range(n)]))
        count,=r.get('i')
        self.palettes=[]
        for _ in range(count):
            raw=r.take(1024)
            self.palettes.append([tuple(raw[i:i+3]) for i in range(0,1024,4)])
        if r.offset<len(r.data):
            for pattern in self.patterns:
                length,=r.get('i')
                pattern.name=r.take(length).decode('cp932',errors='replace')
        assert r.offset==len(r.data),(path,r.offset,len(r.data))

    @lru_cache(maxsize=4096)
    def piece_image(self,part_index,palette,rgb=(1000,1000,1000)):
        """Palette transform from VSPACKET::Render 0x10003c56–0x10003d9c."""
        part=self.parts[part_index]
        if not part.width or not part.height:return Image.new('RGBA',(1,1))
        if self.shadow:
            # SDW patterns can have palette=-1 and no palette records at all.
            # The native floor-shadow path uses the bit mask, never a color
            # palette. Alpha strength is assigned by the shadow pass.
            alpha=Image.frombytes('L',(part.width,part.height),part.image.tobytes()).point(lambda p:255 if p else 0)
            out=Image.new('RGBA',alpha.size);out.putalpha(alpha);return out
        im=part.image.copy()
        def tint(c,m):
            delta=m-1000
            product=(255-c)*delta if delta>0 else c*delta
            change=product//1000 if product>=0 else -((-product)//1000)
            return max(0,min(255,c+change))
        colors=[tuple(tint(c,m) for c,m in zip(color,rgb)) for color in self.palettes[palette]]
        im.putpalette([c for color in colors for c in color])
        im.info['transparency']=0
        return im.convert('RGBA')


if __name__=='__main__':
    p=MapNJP(sys.argv[1])
    print(p.path.name,len(p.parts),'parts',len(p.patterns),'patterns',len(p.palettes),'palettes',p.shadow)
