"""Build the offline scenario-item guide from a local ShadowFlare installation.

Read-only. Parses every MCT/SCS to EOF; checks curated script rewards against
the installed instructions and numeric drop tables. No save/game writes.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from resource_tables import tbd_data, table_records


class Reader:
    def __init__(self, data): self.data, self.at = data, 0
    def take(self, n):
        if n < 0 or self.at + n > len(self.data): raise ValueError('Truncated scenario')
        result = self.data[self.at:self.at+n]; self.at += n
        return result
    def ints(self, n=1): return list(struct.unpack('<' + 'i'*n, self.take(n*4)))
    def integer(self): return self.ints()[0]
    def count(self):
        n = self.integer()
        if not 0 <= n < 1000000: raise ValueError('Invalid scenario count')
        return n
    def string(self, n): return self.take(n).split(b'\0')[0].decode('cp932')
    def done(self):
        if self.at != len(self.data): raise ValueError('Trailing scenario data')


def read_mct(data):
    r = Reader(data)
    if r.take(16) != b'MCED DATA v0000\x1a': raise ValueError('Unsupported MCT')
    r.take(520 + 12 + 256)
    for _ in range(3): r.take(r.count()*4)
    entities = []
    for category, size in enumerate((52, 44, 316, 16)):
        for _ in range(r.count()):
            ident, pattern, length = r.ints(3); name = r.string(length)
            if length: r.integer()
            common = r.integer(); x, y = r.ints(2); r.take(20)
            flags = r.ints(r.count()); animated = r.integer()
            if animated == 1: r.take(r.count()*10)
            tail = r.integer(); payload = r.ints(size//4)
            entities.append(dict(category=category, identifier=ident, name=name,
                                 x=x, y=y, flags=flags, common=common,
                                 tail=tail, pattern=pattern, payload=payload))
    r.take(r.count()*16); r.take(12); r.done()
    return entities


def read_scs(data):
    r = Reader(data)
    if r.take(16) != b'ScenaScriptV000\0': raise ValueError('Unsupported SCS')
    temp = dict(r.ints(2) for _ in range(r.count()))
    r.take(r.count()*8)
    for _ in range(r.count()): r.integer(); r.take(r.count())
    statuses = [r.ints(4) for _ in range(r.count())]
    sentences = []
    for _ in range(r.count()):
        cmds = []
        for _ in range(r.count()):
            opcode = r.integer(); operands = [r.ints(2) for _ in range(r.count())]
            cmds.append((opcode, operands))
        sentences.append(cmds)
    r.done()
    return dict(temp=temp, statuses=statuses, sentences=sentences)


def project(x, y):
    # Native projection uses C signed division (towards zero).
    def trunc(n, d): return n//d if n >= 0 else -((-n)//d)
    return trunc((x-y)*15, 100), trunc((x+y)*10, 100)


def read_js(path): return json.loads(path.read_text('utf8').split('=', 1)[1].strip().removesuffix(';'))


def build(game, atlas):
    selected = [i for i in atlas['items'] if
                i['cat'] == 3 and 40000000 <= int(i['key'].split(':')[1]) <= 40000009 or
                i['cat'] == 4 and 99000000 <= int(i['key'].split(':')[1]) <= 99000028]
    records = {i['key']: dict(key=i['key'], item=i['id'], name=i['name'].strip(),
                             category=i['cat'], sources=[], uses=[]) for i in selected}
    def load(m):
        folder = game / 'Scenario' / m['id']
        mct = (folder/'Scenario.Mct').read_bytes(); scs = (folder/'Scenario.Scs').read_bytes()
        return m['id'], dict(entities=read_mct(mct), script=read_scs(scs),
                             mctHash=hashlib.sha256(mct).hexdigest(), scsHash=hashlib.sha256(scs).hexdigest())
    with ThreadPoolExecutor(max_workers=8) as pool: scenes = dict(pool.map(load, atlas['maps']))

    def point(sid, entity, prefix):
        x, y = project(entity['x'], entity['y'])
        return dict(id=f'{prefix}:{sid}:{entity["identifier"]}', map=sid, x=x, y=y,
                    worldX=entity['x'], worldY=entity['y'])
    def entity(sid, category, ident):
        return next(e for e in scenes[sid]['entities'] if e['category']==category and e['identifier']==ident)
    def values(sid, operands):
        flags = scenes[sid]['script']['temp']
        return [flags.get(n) if t==4 else n if t==1 else None for t,n in operands]
    def require(sid, sentence, command, opcode, args):
        op, operands = scenes[sid]['script']['sentences'][sentence][command]
        if op != opcode or values(sid, operands) != args:
            raise ValueError(f'Unrecognised script reward: {sid}:{sentence}:{command}')

    for sid, scene in scenes.items():
        for e in scene['entities']:
            if e['category'] != 3: continue
            key = ':'.join(map(str, e['payload'][:2]))
            if key not in records: continue
            if e['common']!=0 or e['flags']!=[1,1,1]:
                raise ValueError(f'Unexpected initial-item activation flags: {sid}:{e["identifier"]}')
            rec = records[key]
            source = next((s for s in rec['sources'] if s['kind']=='ground' and s['map']==sid), None)
            if source is None:
                source = dict(id=f'ground:{sid}', kind='ground', map=sid, points=[],
                              steps=['Haritayı açıp numaralı eşya noktalarından birine git.',
                                     'Eşya haritanın hazır yerleşiminde bulunur; yaratık öldürmen gerekmez.'])
                rec['sources'].append(source)
            source['points'].append(point(sid, e, 'ground'))

    for mob in atlas['mobs']:
        for vi, variant in enumerate(mob['variants']):
            group = atlas['groups'].get(str(variant['group']), {})
            for item_id, chance, expected in group.get('data', {}).get('1', []):
                item = atlas['items'][item_id]
                if item['key'] not in records: continue
                points = []
                for ref in variant['references']:
                    sid, ident = ref.split(':'); e = entity(sid, 2, int(ident))
                    points.append(point(sid, e, f'mob:{mob["id"]}:{vi}'))
                records[item['key']]['sources'].append(dict(id=f'mob:{mob["id"]}:{vi}', kind='mob',
                    mob=mob['id'], variant=vi, group=variant['group'], chance=chance, points=points,
                    steps=[f'{mob["name"]} yaratığının işaretli varyantını bul ve yen.',
                           'Bu bağlantı standart yaratık drop tablosundan gelir. Görev durumu yaratığın etkinliğini değiştirebilir.']))

    for key, sid, npc_id, ingredient, sentence in [
        ('4:99000015','03900003',12,'3:40000008',359),
        ('4:99000016','03900004',8,'3:40000009',166),
        ('4:99000017','03900001',9,'3:40000000',217),
        ('4:99000018','03900002',8,'3:40000001',153),
    ]:
        npc = entity(sid,1,npc_id); cat, ident = map(int,key.split(':'))
        cost_cat, cost_id = map(int,ingredient.split(':'))
        require(sid,sentence,0,59,[cost_cat,cost_id])
        # CREATEITEM's x/y operands refer to variables set from this NPC.
        cmds = scenes[sid]['script']['sentences'][sentence]
        if cmds[1] != (1,[[4,1000003],[6,12000000+npc_id]]) or cmds[2] != (1,[[4,1000004],[7,12000000+npc_id]]):
            raise ValueError('Unrecognised card position')
        require(sid,sentence,3,11,[0,200])
        require(sid,sentence,4,10,[cat,ident,0,0,-1,-1])
        start=next(start for _,typ,subject,start in scenes[sid]['script']['statuses'] if typ==0 and subject==12000000+npc_id)
        if not any(op==0 and ops[:3]==[[12,32],[0,0],[1,2]] for op,ops in scenes[sid]['script']['sentences'][start]):
            raise ValueError('Missing Jurg completion requirement')
        records[key]['sources'].append(dict(id=f'trade:{sid}:{npc_id}',kind='trade',map=sid,
            npc=npc['name'], ingredient=ingredient, points=[point(sid,npc,'npc')], sentence=sentence,
            quest=32,
            steps=['Önce “Jurg’u durdur” görevini tamamla; kart takası bu aşamadan sonra açılır.',
                   f'{records[ingredient]["name"]} bul ve çantanda tut.',
                   f'{npc["name"]} ile konuşup takas konuşmasını tamamla. Bir adet malzeme kullanılır.',
                   f'{records[key]["name"]} NPC’nin yanına yere bırakılır. Kartı elle al.'],
            note='Üzerinde aynı kart zaten varsa NPC yeni takas önermeyebilir. İşaret NPC’nin başlangıç konumudur. Kart, NPC’nin o anki konumunda X + 200, Y noktasında oluşturulur.'))

    # Table groups are not all exported to the monster-only catalogue.
    tables = {t['number']:t for t in table_records(tbd_data((game/'System/Game/Parameter/Table.Tbd').read_bytes()))}
    def row(number, n):
        t=tables[number]; return struct.unpack_from('<'+'i'*t['cols'],t['numeric'],12+n*t['cols']*4)
    rewards = [
        ('4:99000007','03120000',156,407,9,0,2),
        ('4:99000013','03180000',160,411,9,0,0),
        ('4:99000014','03220000',161,412,9,0,0),
        ('4:99000022','03240000',166,420,19,10000,10004),
    ]
    for key,sid,gid,selector,sentence,first,last in rewards:
        require(sid,sentence,0,24,[gid,0,0])
        if row(31,selector)[0]!=4 or row(31,selector)[3]!=int(key.split(':')[1]) or set(row(30,gid)[2::2])!={selector} or row(30,gid)[1]<99:
            raise ValueError('Script reward table mismatch')
        script=scenes[sid]['script']; guard=[(op,ops) for cs in script['sentences'][:sentence] for op,ops in cs if op==31 and ops[:2]==[[1,14000000+first],[1,14000000+last]]]
        if not guard: raise ValueError('Missing guardian check')
        prior=[command for commands in script['sentences'][:sentence] for command in commands]
        if any(expected not in prior for expected in [(1,[[4,1000000],[6,10021000]]),(1,[[4,1000001],[7,10021000]])]):
            raise ValueError('Missing reward chest position')
        bosses=[entity(sid,2,n) for n in range(first,last+1)]
        names=list(dict.fromkeys(e['name'] for e in bosses)); chest=entity(sid,0,21000)
        records[key]['sources'].append(dict(id=f'reward:{sid}',kind='scenario',map=sid,
            points=[point(sid,chest,'reward')], guardians=names, group=gid, sentence=sentence,
            steps=[f'Bölgedeki koruyucuları yen: {", ".join(names)} ({len(bosses)} yaratık).',
                   'Koruyucuların tamamı yenilince ödül, işaretli sandığın bulunduğu yerde oluşturulur.',
                   'Yere çıkan görev eşyasını elle al.'],
            note='Senaryo ödülüdür; doğrudan koruyucunun standart drop havuzu değildir. Aynı ödülün tekrar oluşturulmasını önleyen ayrı bir senaryo durumu vardır.'))

    sid='03900004';npc=entity(sid,1,0)
    require(sid,30,0,75,[4,99000009]);require(sid,31,0,75,[4,99000009])
    records['4:99000009']['sources'].append(dict(id='dialog:antidote',kind='dialog',map=sid,npc=npc['name'],
        ingredient='4:99000008',points=[point(sid,npc,'npc')],sentence=30,
        steps=['Barshival’in zehirlenmesinin ardından “Panzehir bul” görevini al.',
               'Ponse’de Dorojan ile konuş. İstediği Fruit of Poreno’yu Ponero Cave’den getir.',
               'Meyve çantandayken Dorojan ile yeniden konuş; Antidote özel eşya alanına doğrudan verilir.'],
        note='Görev etkin olmalı. Panzehir kaybolursa görevdeki diyalog dalı, meyve karşılığında yeniden verme işlemini de içerir.'))
    for ci,ident in enumerate((99000005,99000006,99000007),2):
        sid='03900003';npc=entity(sid,1,0);require(sid,120,ci,75,[4,ident])
        records[f'4:{ident}']['sources'].append(dict(id=f'dialog:relic:{ident}',kind='dialog',map=sid,npc=npc['name'],
            points=[point(sid,npc,'npc')],sentence=120,
            steps=['Ana hikâyeyi Jurg olaylarının sonrasına kadar ilerlet.',
                   'Barshival ile konuşarak “Kutsal emanetleri Aziz Sena’ya götür” görevini al.',
                   'Sacred Wing, Angel’s Hair ve Angel’s Nail bu teslim görevi için özel eşya alanına doğrudan eklenir.'],
            note='Bu bir görev teslim paketi; erken aşamada sınırsız emanet almak için kullanılan bir takas değildir.'))

    # Consumers are extracted only from explicit NPC script sections. These are
    # usages, never acquisition sources. Do not mislabel DELETEITEM as a grant.
    for sid,scene in scenes.items():
        script=scene['script'];contexts=sorted((start,subject) for _,typ,subject,start in script['statuses'] if typ in (0,1))
        for si,cmds in enumerate(script['sentences']):
            for op,ops in cmds:
                if op!=59:continue
                args=values(sid,ops)
                if len(args)!=2:continue
                key=':'.join(map(str,args))
                if key not in records:continue
                preceding=[(start,subject) for start,subject in contexts if start<=si]
                if not preceding or not 12000000<=preceding[-1][1]<13000000:continue
                npc=entity(sid,1,preceding[-1][1]-12000000)
                if any(u['map']==sid and u['npc']==npc['name'] for u in records[key]['uses']):continue
                records[key]['uses'].append(dict(map=sid,npc=npc['name'],points=[point(sid,npc,'npc')],sentence=si))
    for rec in records.values():
        rec['unresolved']=not rec['sources']
        rec['autoPickup']=rec['category']==3
        if rec['category']==4:rec['note']='Özel/görev eşyaları otomatik toplama kapsamına girmez. Hikâye durumu konuşmaları ve teslimleri etkileyebilir.'
    return dict(version=1,scenarioCount=len(scenes),items=list(records.values()),
        fixedPlacements=sum(len(s['points']) for r in records.values() for s in r['sources'] if s['kind']=='ground'),
        provenance={sid:dict(mct=s['mctHash'],scs=s['scsHash']) for sid,s in scenes.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'app/assets/scenario-items.js')
    args=parser.parse_args();result=build(args.game,read_js(ROOT/'app/data.js'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text('window.SF_SCENARIO_ITEMS='+json.dumps(result,ensure_ascii=False,separators=(',',':'))+';\n','utf8')
    print(json.dumps(dict(items=len(result['items']),fixedPlacements=result['fixedPlacements'],
                         unresolved=[r['key'] for r in result['items'] if r['unresolved']])))


if __name__=='__main__':main()
