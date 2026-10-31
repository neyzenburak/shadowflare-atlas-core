"""Nominal probabilities reconstructed from ShadowFlare.exe v2.004 data.

The branching/filtering matches the executable. Percentages assume independent,
uniform RNG buckets; the original CRT rand/modulo and nine-digit sampler have
small biases and state correlations. Quest scripts are outside this model.
"""
from pathlib import Path
from collections import defaultdict
from functools import lru_cache
import argparse
import json

from paths import WORK as ROOT
ITEMS=json.loads((ROOT/'items.json').read_text(encoding='utf-8'))
TABLES={t['number']:t['values'] for t in json.loads((ROOT/'tables.json').read_text(encoding='utf-8'))}
SCENARIOS=json.loads((ROOT/'scenarios.json').read_text(encoding='utf-8'))
BY_KEY={(i['category'],i['fields']['014']):i for i in ITEMS}
CATEGORY_NAMES=['Weapon','Armor','Accessory','Consumable','Other']

def rarity_bits(decimal):
    return (1 if decimal%10 else 0)|(2 if decimal//10%10 else 0)|(4 if decimal//100%10 else 0)

def eligible(item,selector,flags):
    category,max_level,min_level,fixed_id,mask=selector
    f=item['fields']
    if category!=-1 and item['category']!=category:return False
    if category==-1 and item['category']>2:return False
    if not ((flags | 8) & (1<<f['018'])):return False
    if not (f['088'] & mask):return False
    if item['category']<=3:
        level=f['0c0'] if item['category']<=1 else f['090']
        if max_level!=-1 and level>max_level:return False
        if min_level!=-1 and level<min_level:return False
    return True

@lru_cache(None)
def pool(selector_id,flags):
    selector=TABLES[31][selector_id]
    category,max_level,min_level,fixed_id,mask=selector
    if fixed_id!=-1:
        item=BY_KEY.get((category,fixed_id))
        return ((category,fixed_id,1),) if item else ()
    return tuple((i['category'],i['fields']['014'],i['fields']['078']) for i in ITEMS
                 if eligible(i,selector,flags) and i['fields']['078']>0)

def group_steps(group,players=1):
    row=TABLES[30][group]
    attempts=row[0] or players
    p=max(0,min(100,row[1]+1))/100
    return row,attempts,p

@lru_cache(None)
def expected_drops(group,players=1):
    """Expected number of each item per drop-function invocation."""
    result=defaultdict(float)
    if group<0:return dict(result)
    row,attempts,pass_chance=group_steps(group,players)
    states={0:1.0}
    for _ in range(attempts):
        next_states=defaultdict(float)
        for flags,mass in states.items():
            next_states[flags]+=mass*(1-pass_chance)
            for slot in range(10):
                sid,decimal=row[2+slot*2:4+slot*2]
                updated=flags|rarity_bits(decimal) if sid!=-1 else flags
                next_states[updated]+=mass*pass_chance/10
                if sid==-1:continue
                candidates=pool(sid,updated)
                total=sum(w for c,i,w in candidates)
                if total:
                    for cat,ident,weight in candidates:
                        result[(cat,ident)]+=mass*pass_chance/10*weight/total
        states=next_states
    return dict(result)

def probability(group,targets,players=1):
    """Nominal chance of at least one target across all attempts, with flag carry."""
    if group<0:return 0.0
    row,attempts,p=group_steps(group,players)
    states={0:1.0}
    for _ in range(attempts):
        next_states=defaultdict(float)
        for flags,mass in states.items():
            next_states[flags]+=mass*(1-p)
            for slot in range(10):
                sid,decimal=row[2+slot*2:4+slot*2]
                updated=flags|rarity_bits(decimal) if sid!=-1 else flags
                hit=0
                if sid!=-1:
                    a=pool(sid,updated);total=sum(w for c,i,w in a)
                    if total:hit=sum(w for c,i,w in a if (c,i) in targets)/total
                next_states[updated]+=mass*p/10*(1-hit)
        states=next_states
    chance=max(0,min(1,1-sum(states.values())))
    return 0.0 if chance<1e-14 else chance

def sources():
    result=defaultdict(list)
    for s in SCENARIOS:
        counts=defaultdict(int)
        for e in s['entities']:
            if e['category']==2:counts[(e['name'],e['drop_group'])]+=1
        for (name,gid),count in counts.items():
            result[gid].append(dict(scenario=s['scenario'],map=s['map_name'],enemy=name,count=count))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True)
    for name in ['item','enemy']:
        p=sub.add_parser(name);p.add_argument('query');p.add_argument('--limit',type=int,default=20);p.add_argument('--players',type=int,default=1,choices=range(1,5))
        if name=='item':
            p.add_argument('--id',type=int,help='Only this item ID, to distinguish identical names')
            p.add_argument('--category',type=int,choices=range(5))
    p=sub.add_parser('group');p.add_argument('id',type=int);p.add_argument('--players',type=int,default=1,choices=range(1,5));p.add_argument('--limit',type=int,default=20)
    args=ap.parse_args();src=sources()
    if args.command=='item':
        matches=[i for i in ITEMS if args.query.casefold() in i['name'].casefold()]
        if args.id is not None:matches=[i for i in matches if i['fields']['014']==args.id]
        if args.category is not None:matches=[i for i in matches if i['category']==args.category]
        targets={(i['category'],i['fields']['014']) for i in matches}
        for i in matches:print(f"{i['name']} | {CATEGORY_NAMES[i['category']]} ID={i['fields']['014']} rarity={i['fields']['018']} weight={i['fields']['078']}")
        rows=[]
        for group,locs in src.items():
            if group<0:continue
            if not any(k in expected_drops(group,args.players) for k in targets):continue
            chance=probability(group,targets,args.players)
            rows.extend((chance,group,loc) for loc in locs)
        rows.sort(key=lambda x:(-x[0],-x[2]['count']))
        print(f'\nNOMINAL chance of any of the {len(matches)} matching records per kill; static map placements shown.')
        for chance,gid,loc in rows[:args.limit]:
            print(f"{chance*100:.8f}% | ~1/{1/chance:.1f} | group {gid} | {loc['enemy']} x{loc['count']} | {loc['map']} [{loc['scenario']}]")
        if not rows:print('No source in the standard enemy-drop model. Quest/script sources are not included.')
    elif args.command=='enemy':
        for gid,locs in src.items():
            for loc in locs:
                if args.query.casefold() not in loc['enemy'].casefold():continue
                print(f"\n{loc['enemy']} x{loc['count']} | {loc['map']} [{loc['scenario']}] | group {gid}")
                for (cat,ident),expected in sorted(expected_drops(gid,args.players).items(),key=lambda x:-x[1])[:args.limit]:
                    print(f"  E={expected:.8f}/kill | {BY_KEY[(cat,ident)]['name']} [{cat}:{ident}]")
    else:
        row,n,p=group_steps(args.id,args.players)
        print('group',args.id,'attempts',n,'threshold',row[1],'nominal pass',p,'slots',list(zip(row[2::2],row[3::2])))
        for (cat,ident),expected in sorted(expected_drops(args.id,args.players).items(),key=lambda x:-x[1])[:args.limit]:
            chance=probability(args.id,{(cat,ident)},args.players)
            print(f"{chance*100:.8f}% at least one | E={expected:.8f} | {BY_KEY[(cat,ident)]['name']}")

if __name__=='__main__':main()
