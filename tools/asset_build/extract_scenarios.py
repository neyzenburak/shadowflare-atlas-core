from pathlib import Path
import struct
import json
import csv
from collections import Counter

from paths import WORK as ROOT
PART_COUNTS={}

def parse(path):
    data=path.read_bytes();cursor=16
    assert data[:15]==b'MCED DATA v0000'
    def take(n):
        nonlocal cursor
        assert n>=0 and cursor+n<=len(data),(path,cursor,n,len(data))
        b=data[cursor:cursor+n];cursor+=n;return b
    def integer():return struct.unpack('<i',take(4))[0]
    def fixed_string(n):return take(n).split(b'\0')[0].decode('cp932',errors='replace')
    ai_path=fixed_string(260);map_path=fixed_string(260)
    header=struct.unpack('<3i',take(12));map_name=fixed_string(256)
    preload=[]
    for _ in range(3):
        n=integer();assert 0<=n<10000
        preload.append(list(struct.unpack('<'+'i'*n,take(4*n))))
    entities=[]
    for category,size in enumerate([52,44,316,16]):
        count=integer();assert 0<=count<100000,(path,cursor,count)
        for _ in range(count):
            record_start=cursor
            identifier,pattern,length=integer(),integer(),integer()
            assert 0<=length<10000,(path,cursor,length)
            name=take(length).decode('cp932',errors='replace')
            name_flag=integer() if length else None
            common_flag=integer()
            position=struct.unpack('<2i',take(8))
            rectangle=struct.unpack('<4i',take(16))
            misc=integer();flag_count=integer();assert 0<=flag_count<10000
            flags=struct.unpack('<'+'i'*flag_count,take(flag_count*4))
            has_animation=integer()
            parts=[]
            if has_animation==1:
                animation_count=integer();assert 0<=animation_count<10000
                visible=struct.unpack('<'+'i'*animation_count,take(animation_count*4))
                red=struct.unpack('<'+'h'*animation_count,take(animation_count*2))
                green=struct.unpack('<'+'h'*animation_count,take(animation_count*2))
                blue=struct.unpack('<'+'h'*animation_count,take(animation_count*2))
                limit=PART_COUNTS.get(pattern,0) if category==2 else 0
                parts=[dict(visible=v,r=r,g=g,b=b) for v,r,g,b in list(zip(visible,red,green,blue))[:limit]]
            tail=integer()
            payload=take(size)
            entities.append(dict(category=category,identifier=identifier,pattern=pattern,
                name=name,position=position,file_offset=record_start,has_animation=has_animation,parts=parts,
                values=list(struct.unpack('<'+'i'*(size//4),payload)),
                drop_group=struct.unpack_from('<i',payload,0x38)[0] if category==2 else None))
    waypoint_count=integer();assert 0<=waypoint_count<10000
    take(waypoint_count*16)
    footer=struct.unpack('<3i',take(12))
    assert cursor==len(data),(path,cursor,len(data))
    return dict(scenario=path.parent.name,map_name=map_name,map_path=map_path,header=header,entities=entities)

if __name__=='__main__':
    scenarios=[parse(p) for p in sorted((ROOT/'input'/'Scenario').glob('*/Scenario.Mct'))]
    (ROOT/'scenarios.json').write_text(json.dumps(scenarios,ensure_ascii=False,indent=2),encoding='utf-8')
    enemies=[]
    for s in scenarios:
        for e in s['entities']:
            if e['category']==2: enemies.append(dict(scenario=s['scenario'],map_name=s['map_name'],map_path=s['map_path'],**e))
    with (ROOT/'enemies.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['scenario','map_name','map_path','identifier','pattern','name','x','y','drop_group','payload_hex_offset']+[f'payload_{i*4:03x}' for i in range(79)])
        for e in enemies:w.writerow([e[k] for k in ['scenario','map_name','map_path','identifier','pattern','name']]+list(e['position'])+[e['drop_group'],hex(e['file_offset'])]+e['values'])
    print('SCENARIOS',len(scenarios),'ENEMIES',len(enemies),'NAMED',sum(bool(e['name']) for e in enemies))
    print('GROUPS',Counter(e['drop_group'] for e in enemies))
    print('EXAMPLES',[(e['map_name'],e['name'],e['drop_group']) for e in enemies if e['name']][:25])
