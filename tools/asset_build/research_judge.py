"""Reconstruct world footprints from original ground collision data."""
from pathlib import Path
import sys,struct,json,collections
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
from paths import WORK as ROOT
from map_scene import Reader
CACHE=ROOT/'map-work/asset-export/source-cache/Map'
OUT=ROOT/'world-footprints'

def read_judge(name):
    path=CACHE/'Ground'/(name+'.Gnd')
    if not path.exists():path=next(p for p in (CACHE/'Ground').iterdir() if p.stem.lower()==name.lower())
    r=Reader(path.read_bytes()); assert r.take(16)==b'RPGSCRN_GNDv000\x1a'
    w,h,tw,th,mx,my=r.get('6i')
    # The preceding visual ground plane is not needed for collision research.
    # Skip its verified container instead of expanding millions of tile words.
    compressed,=r.get('B')
    assert compressed in (0,1)
    if compressed:
        header=r.take(16);assert header.startswith(b'RCLIB-L')
        size,packed=struct.unpack_from('<II',header,8);assert size==w*h*6
        r.take(packed)
    else:r.take(w*h*6)
    raw=r.block()
    # GetBaseParam 10004bf0: renderer projection factors 15,10 × baseMag /100.
    bx,by=15*mx//100,10*my//100
    # CalcGroundPos 10003500 implements floor of inverse isometric transform.
    def inverse(x,y):return ((by*x+bx*y)//(2*bx*by),(bx*y-by*x)//(2*bx*by))
    corners=[inverse(x,y) for x,y in [(0,0),(w*tw,0),(0,h*th),(w*tw,h*th)]]
    # CalcAreaJudgeFromMap 10004b00 gives min-1, inclusive(max)-min+1.
    x0=min(p[0] for p in corners)-1;y0=min(p[1] for p in corners)-1
    jw=max(p[0] for p in corners)-x0+1;jh=max(p[1] for p in corners)-y0+1
    assert jw*jh*2==len(raw),(name,jw,jh,len(raw))
    plane=np.frombuffer(raw,dtype='<u2').reshape(jh,jw)
    return dict(name=name,width=w*tw,height=h*th,bx=bx,by=by,offset=[x0,y0],judgeWidth=jw,judgeHeight=jh),plane

def project_plane(meta,plane,size):
    w,h=size
    sx=(np.arange(w)+.5)*meta['width']/w
    sy=(np.arange(h)+.5)*meta['height']/h
    bx,by=meta['bx'],meta['by']
    gx=np.floor((by*sx[None,:]+bx*sy[:,None])/(2*bx*by)).astype(np.int32)-meta['offset'][0]
    gy=np.floor((bx*sy[:,None]-by*sx[None,:])/(2*bx*by)).astype(np.int32)-meta['offset'][1]
    valid=(gx>=0)&(gx<meta['judgeWidth'])&(gy>=0)&(gy<meta['judgeHeight'])
    out=np.full((h,w),65535,dtype=np.uint16)
    out[valid]=plane[gy[valid],gx[valid]]
    return out

def components(binary):
    """Four-connected labels via row runs; extraction-only NumPy/Pillow deps."""
    height,width=binary.shape
    out=np.zeros(binary.shape,dtype=np.int32);parent=[0];previous=[]
    def find(a):
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for y in range(height):
        row=np.r_[False,binary[y],False].astype(np.int8)
        diff=np.diff(row);starts=np.flatnonzero(diff==1);ends=np.flatnonzero(diff==-1)
        current=[];pi=0
        for start,end in zip(starts,ends):
            label=len(parent);parent.append(label);current.append((int(start),int(end),label));out[y,start:end]=label
            while pi<len(previous) and previous[pi][1]<=start:pi+=1
            k=pi
            while k<len(previous) and previous[k][0]<end:
                a,b=find(label),find(previous[k][2])
                if a!=b:parent[b]=a
                k+=1
        previous=current
    lookup=np.array([find(a) for a in range(len(parent))],dtype=np.int32)
    return lookup[out]

def playable_mask(name,size):
    """0-bit components with actual scenario actor/point seeds; filled footprint."""
    meta,plane=read_judge(name)
    links=json.loads((ROOT/'map-work/data-research/map-links.json').read_text())
    seeds=[]
    for zone in links['maps']:
        if Path(zone['resource']).stem.lower()!=name.lower():continue
        seeds += [(p['x'],p['y']) for p in zone['spawns']+zone['npcAndObjects'] if p.get('category',2)!=0]
        seeds += [(p[1],p[2]) for p in zone['rawPoints']]
    # Bit0 is collision; other bits (e.g 0x8000) do not exclude walkable cells.
    labels=components((plane&1)==0)
    border=set(map(int,np.r_[labels[0],labels[-1],labels[:,0],labels[:,-1]]));border.add(0)
    selected=set()
    for wx,wy in seeds:
        gx=wx//160-meta['offset'][0];gy=wy//160-meta['offset'][1]
        if 0<=gx<meta['judgeWidth'] and 0<=gy<meta['judgeHeight']:
            label=int(labels[gy,gx])
            if label not in border:selected.add(label)
    occupied=np.isin(labels,list(selected))
    # Ground collisions enclose walls/trees/buildings. Keep these interior holes.
    holes=components(~occupied)
    outer=set(map(int,np.r_[holes[0],holes[-1],holes[:,0],holes[:,-1]]))
    filled=~np.isin(holes,list(outer))
    mask=Image.fromarray(np.uint8(project_plane(meta,filled,size))*255)
    # A small geographic fringe retains scenery sitting just past collision.
    radius=max(1,round(size[0]/meta['width']*180))
    # Exact binary square dilation; separable prefix sums avoid Pillow's
    # quadratic large-kernel MaxFilter cost on broad outdoor regions.
    a=np.asarray(mask)>0;k=radius*2+1
    sums=np.pad(np.pad(a,((0,0),(radius,radius))).cumsum(axis=1,dtype=np.int32),((0,0),(1,0)))
    a=(sums[:,k:]-sums[:,:-k])>0
    sums=np.pad(np.pad(a,((radius,radius),(0,0))).cumsum(axis=0,dtype=np.int32),((1,0),(0,0)))
    mask=Image.fromarray(np.uint8((sums[k:]-sums[:-k])>0)*255)
    meta.update(seedCount=len(seeds),seedComponents=len(selected),footprintBounds=mask.getbbox())
    return meta,mask
