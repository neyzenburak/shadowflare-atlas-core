"""Source-verified scenario links for the offline Atlas.

Does not modify game assets or the existing Atlas bundle.
"""
from pathlib import Path
import collections
import hashlib
import json
import struct

from paths import WORK as ROOT, GAME, OUTPUT
OUT = ROOT/'map-work/data-research'



class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0
    def take(self, n):
        assert n >= 0 and self.pos+n <= len(self.data), (self.pos,n,len(self.data))
        result = self.data[self.pos:self.pos+n]
        self.pos += n
        return result
    def ints(self,n=1):
        return list(struct.unpack('<'+'i'*n,self.take(4*n)))
    def integer(self): return self.ints()[0]
    def count(self):
        n=self.integer()
        assert 0 <= n < 100000
        return n
    def string(self,n):return self.take(n).split(b'\0')[0].decode('cp932',errors='replace')
    def done(self):assert self.pos == len(self.data),(self.pos,len(self.data))


def mct(path):
    data=path.read_bytes();r=Reader(data)
    assert r.take(16)==b'MCED DATA v0000\x1a'
    ai_path=r.string(260);map_path=r.string(260);header=r.ints(3);name=r.string(256)
    preload=[r.ints(r.count()) for _ in range(3)]
    entities=[]
    for category,size in enumerate((52,44,316,16)):
        for _ in range(r.count()):
            start=r.pos
            identifier,pattern,length=r.ints(3);entity_name=r.string(length)
            name_flag=r.integer() if length else None
            common_flag=r.integer();position=r.ints(2);rectangle=r.ints(4)
            misc=r.integer();flags=r.ints(r.count())
            has_animation=r.integer()
            if has_animation==1:
                animation_bytes=r.take(r.count()*10)
                animation=dict(bytes=len(animation_bytes),sha256=hashlib.sha256(animation_bytes).hexdigest())
            else:animation=None
            tail=r.integer();payload=r.ints(size//4)
            entities.append(dict(category=category,identifier=identifier,pattern=pattern,name=entity_name,
                nameFlag=name_flag,commonFlag=common_flag,x=position[0],y=position[1],rectangle=rectangle,
                misc=misc,flags=flags,hasAnimation=has_animation,animation=animation,tail=tail,
                fileOffset=start,payload=payload))
    raw_points=[r.ints(4) for _ in range(r.count())]
    footer=r.ints(3);r.done()
    return dict(name=name,mapPath=map_path,aiPath=ai_path,header=header,preload=preload,
        entities=entities,rawPoints=raw_points,footer=footer,sha256=hashlib.sha256(data).hexdigest())


def scs(path):
    data=path.read_bytes();r=Reader(data)
    assert r.take(16)==b'ScenaScriptV000\0'
    temp=[r.ints(2) for _ in range(r.count())]
    net=[r.ints(2) for _ in range(r.count())]
    messages={}
    for _ in range(r.count()):
        ident=r.integer();length=r.count()
        messages[ident]=bytes(b^255 for b in r.take(length)).decode('cp932',errors='replace')
    statuses=[r.ints(4) for _ in range(r.count())]
    sentences=[]
    for sentence in range(r.count()):
        cmds=[]
        for ci in range(r.count()):
            offset=r.pos;opcode=r.integer();ops=[r.ints(2) for _ in range(r.count())]
            cmds.append(dict(opcode=opcode,operands=ops,fileOffset=offset))
        sentences.append(cmds)
    r.done()
    return dict(temp=temp,net=net,messages=messages,statuses=statuses,sentences=sentences,
        sha256=hashlib.sha256(data).hexdigest())


def main():
    data=json.loads((OUTPUT/'data.json').read_text(encoding='utf-8'))
    old=json.loads((ROOT/'scenarios.json').read_text(encoding='utf-8'))
    assert [s['scenario'] for s in old]==[s['id'] for s in data['maps']]
    refs={}
    for mob in data['mobs']:
        for vi,v in enumerate(mob['variants']):
            for ref in v['references']:
                assert ref not in refs,ref
                refs[ref]=(mob['id'],vi)
    maps=[];script_audit={};resources=collections.defaultdict(list)
    counters=collections.Counter();common=collections.Counter();flags=collections.Counter()
    raw_records=[];resource_files={p.name.lower():p.name for p in (GAME/'Map').glob('*.map')}
    for mi,source in enumerate(data['maps']):
        sid=source['id'];parsed=mct(GAME/'Scenario'/sid/'Scenario.Mct')
        assert parsed['name']==source['name']
        native=(GAME/'Scenario'/sid/'Scenario.Mct').read_bytes()
        assert hashlib.sha256(native).hexdigest()==parsed['sha256'],sid
        script=scs(GAME/'Scenario'/sid/'Scenario.Scs')
        cmds=[dict(sentence=si,command=ci,**cmd) for si,s in enumerate(script['sentences']) for ci,cmd in enumerate(s)]
        # Native AnalyzeCharacterNo encodes E<number> as 14,000,000 + number.
        # SETACTIVE=0x16, SETINACTIVE=0x17 (AnalyzeCommand @ 10002517/1000256c).
        activation=collections.defaultdict(list)
        for cmd in cmds:
            if cmd['opcode'] in (0x16,0x17) and cmd['operands']:
                kind,value=cmd['operands'][0]
                if kind==1 and 14_000_000<=value<16_000_000:
                    activation[value-14_000_000].append(dict(opcode=cmd['opcode'],sentence=cmd['sentence'],command=cmd['command']))
        entries=collections.Counter();spawns=[];others=[]
        for e in parsed['entities']:
            counters['category'+str(e['category'])]+=1
            if e['category']!=2:
                others.append({k:e[k] for k in ('category','identifier','pattern','name','x','y','commonFlag','flags')})
                continue
            ref=f"{sid}:{e['identifier']}"
            mob,variant=refs[ref]
            v=data['mobs'][mob]['variants'][variant]
            assert e['payload'][14]==v['group'],ref
            assert e['payload'][49:52]==v['gold'],ref
            entries[mob,variant]+=1
            cond=bool(activation[e['identifier']])
            spawn=dict(x=e['x'],y=e['y'],mob=mob,variant=variant,reference=ref,
                conditional=cond,scriptControlled=cond,commonFlag=e['commonFlag'],flags=e['flags'])
            if cond:spawn['activationCommands']=activation[e['identifier']]
            spawns.append(spawn)
            common[e['commonFlag']]+=1;flags[tuple(e['flags'])]+=1
            counters['scriptControlledPlacements']+=cond
        assert sum(entries.values())==len(spawns)
        resource=Path(parsed['mapPath'].replace('\\','/')).name
        assert resource.lower() in resource_files,(sid,resource)
        resources[resource.lower()].append(mi)
        opcode_counts=collections.Counter(c['opcode'] for c in cmds)
        item_creates=[c for c in cmds if c['opcode'] in (0xa,0x18,0x4b)]
        transitions=[c for c in cmds if c['opcode'] in (0x11,0x25,0x26,0x31)]
        note=[]
        if activation:note.append('Scenario.Scs directly activates/deactivates named enemy records; placements are possible records, not guaranteed simultaneous living mobs.')
        if item_creates:note.append('Scenario.Scs contains item creation/table/direct-give commands; standard monster-drop links do not imply complete quest rewards.')
        maps.append(dict(id=sid,index=mi,name=source['name'],resource=resource,mapPath=parsed['mapPath'],
            entries=[[mid,vi,count] for (mid,vi),count in sorted(entries.items())],spawns=spawns,
            scriptedSpawnNotes=note,scriptControlledCount=sum(s['scriptControlled'] for s in spawns),
            npcAndObjects=others,rawPoints=parsed['rawPoints'],
            source=dict(mctSha256=parsed['sha256'],scsSha256=script['sha256'])))
        script_audit[sid]=dict(tempFlags=script['temp'],netFlags=script['net'],statuses=script['statuses'],
            opcodeCounts=dict(sorted(opcode_counts.items())),activation=dict(activation),
            transitions=transitions,itemCommands=item_creates)
        raw_records.append(dict(id=sid,aiPath=parsed['aiPath'],header=parsed['header'],preload=parsed['preload'],
            footer=parsed['footer'],rawPoints=parsed['rawPoints'],entities=parsed['entities']))
    for mi,m in enumerate(maps):
        from_locations={(mob['id'],vi):count for mob in data['mobs'] for vi,v in enumerate(mob['variants'])
            for index,count in v['locations'] if index==mi}
        assert from_locations=={(mob,vi):count for mob,vi,count in m['entries']}
    assert len(refs)==sum(len(m['spawns']) for m in maps)
    used=set(resources);all_resources=set(resource_files)
    summary=dict(maps=len(maps),namedMaps=sum(bool(m['name']) for m in maps),resources=len(resources),
        unusedMapResources=sorted(resource_files[n] for n in all_resources-used),
        monsters=len(refs),mapVariantPairs=sum(len(m['entries']) for m in maps),
        mapsWithoutMonsterPlacements=[m['id'] for m in maps if not m['spawns']],
        scriptedMaps=[m['id'] for m in maps if m['scriptControlledCount']],
        scriptControlledPlacements=counters['scriptControlledPlacements'],
        categoryCounts=dict(counters),enemyCommonFlags=dict(common),enemyFlagSets={str(k):v for k,v in flags.items()},
        duplicatedResources={name:indices for name,indices in resources.items() if len(indices)>1})
    bundle=dict(version=1,source='Scenario.Mct + Scenario.Scs; links resolved to atlas/dist/data.json IDs',
        spawnMeaning='Possible source records. Scenario state, quest conditions and scripts can control active/living spawns.',
        conditionalMeaning='True only when a constant enemy identifier occurs in SETACTIVE/SETINACTIVE. False does not guarantee unconditional availability.',
        maps=maps,summary=summary)
    for name,payload in [('map-links.json',bundle),('script-audit.json',script_audit),('mct-full-metadata.json',raw_records),('summary.json',summary)]:
        (OUT/name).write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f"Linked {summary['maps']} scenarios and {summary['monsters']} monster placements.",flush=True)


if __name__=='__main__':main()
