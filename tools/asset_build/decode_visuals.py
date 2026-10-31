"""Read-only ShadowFlare NJP/CAF decoder, reconstructed from shipped DLLs.

NJP: RKC_UPDIB_UPD::Read (RKC_UPDIB.dll 0x10002250), render 0x10003550.
CAF: RKC_RPGSCRN_CHARANIM::ReadCafFile (RKC_RPGSCRN.dll 0x10001790).
No game binaries are loaded or executed. Images retain their original pixels.
"""
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
import struct
import sys

from PIL import Image, ImageOps


from decode_data import lz_decode


class Reader:
    def __init__(self, data): self.data, self.offset = data, 0
    def get(self, fmt):
        values = struct.unpack_from('<' + fmt, self.data, self.offset)
        self.offset += struct.calcsize('<' + fmt)
        return values
    def take(self, n):
        data = self.data[self.offset:self.offset+n]
        assert len(data) == n
        self.offset += n
        return data


@dataclass
class Part:
    bpp: int
    width: int
    height: int
    image: Image.Image


@dataclass
class Pattern:
    rect: tuple
    palette: int
    cells: list
    name: str = ''


class NJP:
    def __init__(self, path):
        self.path = Path(path)
        r = Reader(self.path.read_bytes())
        signature = r.take(16)
        assert signature.startswith(b'NJudgeUniPat'), (path, signature)
        self.version = int(signature[12:15])
        assert self.version == 3, (path, self.version)
        count, total_bytes = r.get('2i')
        self.parts = []
        for _ in range(count):
            bpp, width, height, compressed = r.get('4i')
            assert bpp in (4, 8), (path, bpp)
            stride = ((width*bpp + 31) // 32) * 4
            if compressed:
                header = r.take(16)
                expected, packed = struct.unpack_from('<II', header, 8)
                raw = lz_decode(header + r.take(packed))
            else:
                raw = r.take(stride*height)
            assert len(raw) == stride*height
            # Windows DIBs store bottom-up rows; 4-bit pixels use high nibble first.
            pixels = bytearray(width*height)
            for y in range(height):
                row = raw[(height-1-y)*stride:(height-y)*stride]
                if bpp == 8: pixels[y*width:(y+1)*width] = row[:width]
                else:
                    pixels[y*width:(y+1)*width] = bytes((row[x//2] >> (4 if x%2 == 0 else 0)) & 15 for x in range(width))
            im = Image.frombytes('P', (width, height), bytes(pixels)) if width and height else Image.new('P', (1,1))
            self.parts.append(Part(bpp, width, height, im))
        count, total_cells = r.get('2i')
        self.patterns = []
        for _ in range(count):
            count, *rect = r.get('5i')
            palette, = r.get('i')
            # On disk: flags, piece index, x, y, depth, x/y magnification (1000=1).
            cells = [r.get('7i') for _ in range(count)]
            self.patterns.append(Pattern(tuple(rect), palette, cells))
        count, = r.get('i')
        self.palettes = []
        for _ in range(count):
            raw = r.take(1024)
            self.palettes.append([tuple(raw[i:i+3]) for i in range(0,1024,4)])
        if r.offset < len(r.data):
            for pattern in self.patterns:
                length, = r.get('i')
                pattern.name = r.take(length).decode('cp932', errors='replace')
        assert r.offset == len(r.data), (path, r.offset, len(r.data))

    @lru_cache(maxsize=4096)
    def piece_image(self, part_index, palette, rgb=(1000,1000,1000)):
        part = self.parts[part_index]
        if not part.width or not part.height: return Image.new('RGBA', (1,1))
        im = part.image.copy()
        colors = self.palettes[palette]
        colors = [tuple(min(255, max(0, c*m//1000)) for c,m in zip(color,rgb)) for color in colors]
        im.putpalette([c for color in colors for c in color])
        im.info['transparency'] = 0
        return im.convert('RGBA')

    @lru_cache(maxsize=8192)
    def render(self, pattern_index, palette=-1, rgb=(1000,1000,1000)):
        """Return (RGBA, (left, top)) relative to the original pattern origin."""
        pattern = self.patterns[pattern_index]
        if palette < 0: palette = pattern.palette
        pieces = []
        for flags, index, x, y, depth, sx, sy in pattern.cells:
            if index < 0 or index >= len(self.parts): continue
            part = self.parts[index]
            if not part.width or not part.height: continue
            im = self.piece_image(index, palette, rgb)
            if flags & 0x40000000: im = ImageOps.mirror(im)
            if flags & 0x80000000: im = ImageOps.flip(im)
            size = (max(1, part.width*sx//1000), max(1,part.height*sy//1000))
            if im.size != size: im = im.resize(size,Image.Resampling.NEAREST)
            pieces.append((im,x,y))
        if not pieces: return Image.new('RGBA',(1,1)), (0,0)
        x0=min(x for im,x,y in pieces);y0=min(y for im,x,y in pieces)
        x1=max(x+im.width for im,x,y in pieces);y1=max(y+im.height for im,x,y in pieces)
        out=Image.new('RGBA',(x1-x0,y1-y0))
        for im,x,y in pieces: out.alpha_composite(im,(x-x0,y-y0))
        return out,(x0,y0)


class CAF:
    def __init__(self,path):
        r=Reader(Path(path).read_bytes())
        sig=r.take(16)
        assert sig.startswith(b'CHRAnimation'), (path,sig)
        self.version=int(sig[12:15]);assert self.version==2
        count,=r.get('i');self.states=[]
        for _ in range(count):
            status,=r.get('H');directions=[]
            for _ in range(9):
                layers,max_frame=r.get('iH');tracks=[]
                for _ in range(layers):
                    count,=r.get('i')
                    # flags, opacity(1000), pattern index, z priority.
                    tracks.append([r.get('HHIH') for _ in range(count)])
                directions.append({'max_frame':max_frame,'tracks':tracks})
            self.states.append({'status':status,'directions':directions})
        self.extra=r.take(len(r.data)-r.offset)

    def frame(self,njp,state,direction,frame,palette=-1,rgb=(1000,1000,1000),include_shadow=False,visible=None,part_rgb=None):
        tracks=self.states[state]['directions'][direction]['tracks'];layers=[]
        for track_index,track in enumerate(tracks):
            if not track:continue
            if visible is not None and track_index<len(visible) and visible[track_index]!=1:continue
            flags,alpha,pattern,z=track[frame % len(track)]
            # CAF bit 8 means the separate shadow pattern; game paints it on the floor.
            if flags&8 and not include_shadow:continue
            if pattern>=len(njp.patterns):continue
            color=part_rgb[track_index] if part_rgb is not None and track_index<len(part_rgb) else (1000,1000,1000)
            color=tuple(c*g//1000 for c,g in zip(color,rgb))
            im,xy=njp.render(pattern,palette,color)
            if alpha<1000:im=im.copy();im.putalpha(im.getchannel('A').point(lambda x:x*alpha//1000))
            layers.append((z,im,xy))
        if not layers:return Image.new('RGBA',(1,1)),(0,0)
        x0=min(xy[0] for z,im,xy in layers);y0=min(xy[1] for z,im,xy in layers)
        x1=max(xy[0]+im.width for z,im,xy in layers);y1=max(xy[1]+im.height for z,im,xy in layers)
        out=Image.new('RGBA',(x1-x0,y1-y0))
        # SetPacket emits priority parts from last to first (DLL 0x1000248f).
        for z,im,xy in sorted(layers,key=lambda x:x[0],reverse=True):out.alpha_composite(im,(xy[0]-x0,xy[1]-y0))
        return out,(x0,y0)


if __name__=='__main__':
    work=Path(__file__).resolve().parent
    njp=NJP(work/'Item0000.njp')
    contact=Image.new('RGBA',(640,512),(20,24,30,255))
    for i in range(64):
        im,xy=njp.render(i)
        im.thumbnail((60,120),Image.Resampling.NEAREST)
        contact.alpha_composite(im,((i%8)*80+10,(i//8)*64))
    contact.save(work/'item-preview.png')
    njp=NJP(work/'Animation.Njp');caf=CAF(work/'Animation.Caf')
    contact=Image.new('RGBA',(640,200),(20,24,30,255))
    for i in range(8):
        im,xy=caf.frame(njp,0,i,0)
        contact.alpha_composite(im,((i%8)*80+40-im.width//2,100-im.height//2))
    contact.save(work/'mob-preview.png')
