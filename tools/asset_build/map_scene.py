"""Read ShadowFlare's original static maps without loading any game code.

Reconstructed from RKC_RPGSCRN.dll ReadFile ground 0x10004270,
ReadFile objects 0x100060d0, CalcRealPos 0x10001600, and SetPacket 0x10004e40.
All original .map/.Gnd/.Obl/.Lst source files are only read.
"""
from pathlib import Path
from functools import lru_cache
import struct
import sys
import heapq

from paths import WORK as ROOT, GAME
from decode_data import lz_decode




def trunc_div(n, d):
    return n // d if n >= 0 else -((-n) // d)


def project_world(x, y, z=0):
    """Native screen projection; constructor's base parameters are 15,10,10."""
    return trunc_div((x-y)*15, 100), trunc_div((x+y)*10, 100) - trunc_div(z*10,100)


class Reader:
    def __init__(self, data): self.data, self.offset = data, 0
    def take(self, n):
        assert n >= 0
        b=self.data[self.offset:self.offset+n]
        assert len(b)==n, (self.offset,n,len(self.data))
        self.offset += n
        return b
    def get(self, fmt): return struct.unpack('<'+fmt,self.take(struct.calcsize('<'+fmt)))
    def block(self, expected=None):
        compressed,=self.get('B')
        assert compressed in (0,1)
        if compressed:
            hdr=self.take(16)
            assert hdr.startswith(b'RCLIB-L')
            size,packed=struct.unpack_from('<II',hdr,8)
            data=lz_decode(hdr+self.take(packed))
            assert size==len(data)
        else:
            # The final judge plane has no separate on-disk size. When plain,
            # its extent is the remaining file; renderer never consumes it.
            data=self.take(expected if expected is not None else len(self.data)-self.offset)
        if expected is not None: assert len(data)==expected,(len(data),expected)
        return data


def read_ground(path):
    r=Reader(Path(path).read_bytes())
    assert r.take(16)==b'RPGSCRN_GNDv000\x1a'
    w,h,tw,th,mx,my=r.get('6i')
    assert 0<w<=10000 and 0<h<=10000 and tw>0 and th>0
    n=w*h
    data=r.block(n*6)
    planes=struct.unpack('<'+str(n*3)+'h',data)
    ground=[list(row) for row in zip(planes[:n],planes[n:2*n],planes[2*n:])]
    # Judge grid is collision data; dimensions follow the native projected bounds.
    judge=r.block()
    assert len(judge)%2==0
    assert r.offset==len(r.data),(path,r.offset,len(r.data))
    return dict(width=w,height=h,tileWidth=tw,tileHeight=th,
                baseMagX=mx,baseMagY=my,ground=ground,judgeBytes=len(judge))


def read_objects(path):
    r=Reader(Path(path).read_bytes())
    signature=r.take(16)
    assert signature.startswith(b'RPGSCRN_OBJv')
    version=int(signature[12:15])
    assert version in (0,1)
    count,=r.get('i')
    objects=[]
    for i in range(count):
        wx,wy,atlas,pattern,palette,opacity,flags,z=r.get('2i6h')
        rgb=r.get('3h') if version>=1 else (1000,1000,1000)
        rect=list(r.get('4i'))
        x,y=project_world(wx,wy,z)
        objects.append(dict(x=x,y=y,worldX=wx,worldY=wy,atlas=atlas,
            pattern=pattern,palette=palette,opacity=opacity,flags=flags,z=z,
            r=rgb[0],g=rgb[1],b=rgb[2],rect=rect,index=i))
    assert r.offset==len(r.data),(path,r.offset,len(r.data))
    return objects


def object_group(obj):
    flags=obj['flags']
    return 3 if flags&0x20 else 2 if flags&0x80 else 1 if flags&0x100 else 0


def sort_objects_slow(objects):
    """Mirror OBJECTDISP::SortDisplayObject's stable partial order (0x10006d00)."""
    out=list(objects)
    for i in range(len(out)):
        for j in range(i,len(out)):
            obj=out[j]
            ox=obj['worldX']+obj['rect'][2]
            oy=obj['worldY']+obj['rect'][3]
            group=object_group(obj)
            accepted=True
            for other in out[i:]:
                if other is obj:continue
                og=object_group(other)
                if og!=group:
                    if og>group:accepted=False;break
                else:
                    sx,sy=other['worldX'],other['worldY']
                    l,t,r,b=other['rect']
                    if ox>sx+l and oy>sy+t and (ox>sx+r or oy>sy+b):
                        accepted=False;break
            if accepted:
                if j!=i:out.insert(i,out.pop(j))
                break
    return out


def sort_objects(objects):
    """Exact native partial order, using a compact dependency graph.

Native chooses the first remaining object with no blocking predecessor. If
there is a dependency cycle it keeps the first remaining object in place.
That is stable Kahn sorting with the same cycle fallback, avoiding cubic scans.
NumPy is an extraction dependency only; browser/package does not require it.
"""
    if len(objects)<32:return sort_objects_slow(objects)
    try:import numpy as np
    except ImportError:return sort_objects_slow(objects)
    n=len(objects)
    nearx=np.array([o['worldX']+o['rect'][0] for o in objects],dtype=np.int64)
    neary=np.array([o['worldY']+o['rect'][1] for o in objects],dtype=np.int64)
    farx=np.array([o['worldX']+o['rect'][2] for o in objects],dtype=np.int64)
    fary=np.array([o['worldY']+o['rect'][3] for o in objects],dtype=np.int64)
    groups=np.array([object_group(o) for o in objects],dtype=np.int8)
    packed=np.empty((n,(n+7)//8),dtype=np.uint8)
    incoming=np.zeros(n,dtype=np.int32)
    # Rows are blockers, columns are candidate objects. Build only 256 rows
    # at once; a 20,000-object map therefore needs about50MB instead of400MB.
    for start in range(0,n,256):
        stop=min(n,start+256)
        same=groups[start:stop,None]==groups[None,:]
        blocked=(groups[start:stop,None]>groups[None,:]) | (same &
            (farx[None,:]>nearx[start:stop,None]) &
            (fary[None,:]>neary[start:stop,None]) &
            ((farx[None,:]>farx[start:stop,None]) | (fary[None,:]>fary[start:stop,None])))
        blocked[np.arange(stop-start),np.arange(start,stop)]=False
        incoming+=blocked.sum(axis=0,dtype=np.int32)
        packed[start:stop]=np.packbits(blocked,axis=1)
    remaining=np.ones(n,dtype=bool)
    queue=np.flatnonzero(incoming==0).tolist()
    heapq.heapify(queue)
    answer=[];first=0
    for _ in range(n):
        while queue and not remaining[queue[0]]:heapq.heappop(queue)
        while first<n and not remaining[first]:first+=1
        index=heapq.heappop(queue) if queue else first
        answer.append(objects[index]);remaining[index]=False
        edges=np.unpackbits(packed[index],count=n).astype(bool)
        became_zero=np.flatnonzero(edges & remaining & (incoming==1))
        incoming-=edges
        for target in became_zero:heapq.heappush(queue,int(target))
    return answer


def read_scene(name,game=GAME,sort_mode='native'):
    game=Path(game)
    name=Path(name.replace('\\','/')).stem
    root=game/'Map'
    mapfile=root/(name+'.map')
    b=mapfile.read_bytes()
    assert b[:16]==b'MAPED_FILE v000\x1a' and len(b)==36
    layers=struct.unpack_from('<4i',b,16)
    scene=read_ground(root/'Ground'/(name+'.Gnd'))
    objects=read_objects(root/'Object'/(name+'.Obl'))
    if sort_mode=='native':objects=sort_objects(objects)
    elif sort_mode=='depth':
        # Native sorts only the visible list; global sorting is needlessly cubic.
        # This deterministic full-scene order is suitable for overview previews.
        objects.sort(key=lambda o:(-object_group(o),o['worldX']+o['worldY'],o['index']))
    else:assert sort_mode=='none'
    scene.update(name=name,layers=list(layers),projection=[15,10,100],
                 resources=(root/'Pattern'/(name+'.Lst')).read_text(encoding='cp932').splitlines(),
                 objects=objects,objectSort=sort_mode)
    return scene


if __name__=='__main__':
    import json
    name=sys.argv[1] if len(sys.argv)>1 else 'Coalmine_01'
    scene=read_scene(name)
    out=Path(__file__).with_name(name+'.scene.json')
    out.write_text(json.dumps(scene,separators=(',',':')),encoding='utf-8')
    print(out,scene['width'],scene['height'],len(scene['objects']))
