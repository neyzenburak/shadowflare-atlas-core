"""Build the fully offline explorer's compact, source-derived data bundle."""
from pathlib import Path
from collections import defaultdict
import sys
import json
import math
import hashlib

import numpy as np

from paths import WORK as BASE, OUTPUT as DIST
from drop_model import ITEMS,TABLES,SCENARIOS,pool,rarity_bits,group_steps
from item_presentation import enrich_payload


STATS=['Saldırı','Savunma','İsabet','Kaçınma','Büyüsel saldırı','Büyüsel savunma',
 'Büyü isabeti','Büyüden kaçınma','Saldırı hızı','Yürüme hızı','Maksimum HP',
 'Maksimum MP','Güç','Büyü seviyesi','Sersemletme olasılığı','Sersemletme süresi',
 'Karşı saldırıdan kaçınma','HP yenilenmesi','MP yenilenmesi','MP tüketimi',
 'Yansıtma oluşumu','Yansıtma oranı','HP ilacı etkisi','MP ilacı etkisi',
 'Emilim oluşumu','Emilim oranı','Altın miktarı','Mayın etkisi','Mayın sayısı',
 'Büyü okuma hızı','Yoldaş HP','Yoldaş saldırısı','Yoldaş savunması','Yoldaş isabeti',
 'Yoldaş kaçınması','Yoldaş büyüsel saldırısı','Yoldaş büyüsel savunması',
 'Yoldaş büyü isabeti','Yoldaş büyüden kaçınması']
ELEMENTS=['Ateş','Su','Toprak','Yıldırım','Kutsal','Karanlık','Jel','Metal']

def rounded(v):
    if abs(v)<1e-13:return 0
    return float(f'{v:.11g}')

def group_matrix(gid,players,item_indices):
    row,n,p=group_steps(gid,players)
    # Build an exact branching-state model, with nominal independent RNG buckets.
    possible=set()
    for sid,decimal in zip(row[2::2],row[3::2]):
        if sid<0:continue
        for flags in range(8):
            possible.update(item_indices[(c,i)] for c,i,w in pool(sid,flags|rarity_bits(decimal)))
    indices=sorted(possible)
    local={index:k for k,index in enumerate(indices)}
    size=len(indices)
    if not size:return []
    vectors={}
    for sid,decimal in zip(row[2::2],row[3::2]):
        if sid<0:continue
        for flags in range(8):
            updated=flags|rarity_bits(decimal)
            key=(sid,updated)
            if key in vectors:continue
            candidates=pool(sid,updated);total=sum(w for c,i,w in candidates)
            a=np.zeros(size)
            if total:
                for cat,ident,weight in candidates:a[local[item_indices[(cat,ident)]]]=weight/total
            vectors[key]=a
    nohit={0:np.ones(size)}
    state_mass={0:1.0}
    expected=np.zeros(size)
    for _ in range(n):
        nxt={};next_mass=defaultdict(float)
        for flags,masses in nohit.items():
            nxt.setdefault(flags,np.zeros(size))
            nxt[flags]+=masses*(1-p)
            next_mass[flags]+=state_mass[flags]*(1-p)
            for sid,decimal in zip(row[2::2],row[3::2]):
                updated=flags|rarity_bits(decimal) if sid>=0 else flags
                nxt.setdefault(updated,np.zeros(size))
                next_mass[updated]+=state_mass[flags]*p/10
                if sid<0:nxt[updated]+=masses*p/10;continue
                vector=vectors[(sid,updated)]
                nxt[updated]+=masses*p/10*(1-vector)
                expected+=state_mass[flags]*p/10*vector
        nohit,state_mass=nxt,dict(next_mass)
    chances=1-sum(nohit.values())
    return [[index,rounded(chances[k]),rounded(expected[k])]
        for k,index in enumerate(indices) if expected[k]>1e-13]

def build():
    DIST.mkdir(parents=True,exist_ok=True)
    indices={(i['category'],i['fields']['014']):n for n,i in enumerate(ITEMS)}
    items=[]
    for n,i in enumerate(ITEMS):
        f=i['fields'];cat=i['category'];stats=[]
        if cat<=2:
            for kind,start,labels in [('stat',[0x114,0xec,0x94][cat],STATS),('element',[0x2e8,0x2c0,0x268][cat],ELEMENTS)]:
                for k,label in enumerate(labels):
                    lo,hi,rate=[f[f'{start+k*12+d:03x}'] for d in [0,4,8]]
                    if rate>0 and (lo or hi):stats.append([label,lo,lo+abs(hi-lo+1)-1,rate,kind,int(lo>hi)])
        items.append(dict(id=n,key=f"{cat}:{f['014']}",name=i['name'],base=i['base_name'],cat=cat,
            rarity=f['018'],weight=f['078'],selection=f.get('0c0' if cat<=1 else '090'),
            level=f.get('0e8') if cat<=1 else None,stats=stats,
            price=f['040'],iconFields=[f.get(x) for x in ['020','024','028','02c','030']]))
    maps=[dict(id=s['scenario'],name=s['map_name']) for s in SCENARIOS]
    visual_mapping=json.loads((BASE/'visual-mapping-work'/'enemy-visual-mapping.json').read_text(encoding='utf-8'))
    grouped={}
    for mi,s in enumerate(SCENARIOS):
        for e in s['entities']:
            if e['category']!=2:continue
            name=e['name']
            mob=grouped.setdefault(name,dict(name=name,variants={}))
            gold=e['values'][49:52]
            # Preserve the visual record until visual mapping is attached later.
            reference=f"{s['scenario']}:{e['identifier']}"
            visual=visual_mapping['entities'][reference]['visualKey']
            vkey=(e['drop_group'],visual,*gold)
            variant=mob['variants'].setdefault(vkey,dict(group=e['drop_group'],pattern=e['pattern'],
                gold=gold,visual=visual,locations=defaultdict(int),references=[],sample=dict(scenario=s['scenario'],identifier=e['identifier'],file_offset=e['file_offset'],values=e['values'],pattern=e['pattern'])))
            variant['locations'][mi]+=1
            variant['references'].append(reference)
    mobs=[]
    priority=['Red Goblin','Goblin','Bat','Black Hammer','Devil Dignosis','Devil Jurg']
    for name,m in sorted(grouped.items(),key=lambda x:(priority.index(x[0]) if x[0] in priority else 100,x[0].casefold())):
        variants=[]
        for v in m['variants'].values():
            v['locations']=[[k,c] for k,c in sorted(v['locations'].items())]
            v['count']=sum(c for k,c in v['locations'])
            variants.append(v)
        variants.sort(key=lambda v:(-v['count'],v['group'],v['pattern']))
        mobs.append(dict(id=len(mobs),name=name,variants=variants,count=sum(v['count'] for v in variants),
            mapCount=len({k for v in variants for k,c in v['locations']})))
    used=sorted({v['group'] for m in mobs for v in m['variants'] if v['group']>=0})
    groups={}
    for gid in used:
        row,n,p=group_steps(gid)
        groups[str(gid)]=dict(attempts=row[0],gate=row[1],data={})
        for players in ([1,2,3,4] if row[0]==0 else [1]):
            groups[str(gid)]['data'][str(players)]=group_matrix(gid,players,indices)
    payload=dict(version=1,title='ShadowFlare · Drop Atlas',generated='2026-10-18',items=items,mobs=mobs,
        maps=maps,groups=groups,summary=dict(items=len(items),mobs=len(mobs),maps=len(maps),
            placements=sum(m['count'] for m in mobs),verifiedChecks=2710),
        categories=['Silahlar','Zırhlar','Aksesuarlar','Tüketilebilirler','Diğer'],
        provenance=dict(exeSha256=hashlib.sha256((BASE/'input'/'ShadowFlare.exe').read_bytes()).hexdigest(),
            probability='nominal',goldItem=indices[(4,0)]))
    enrich_payload(payload, ITEMS)
    # This external classic script works on file:// without a server or fetch.
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</',r'<\/')
    (DIST/'data.js').write_text('window.ATLAS_DATA='+encoded+';\n',encoding='utf-8')
    (DIST/'data.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(dict(items=len(items),mobs=len(mobs),variants=sum(len(m['variants']) for m in mobs),
        groups=len(groups),bytes=len(encoded.encode())),indent=2))

if __name__=='__main__':build()
