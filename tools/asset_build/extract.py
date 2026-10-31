"""Decode the chosen installation and retain native visual identities."""
import hashlib
import json
import shutil
import struct
from pathlib import Path
from paths import GAME,WORK


def main():
    import decode_data,extract_items,extract_scenarios,extract_tables
    from decode_visuals import CAF
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'app'))
    from resource_tables import tbd_data
    (WORK/'input').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(GAME/'ShadowFlare.exe',WORK/'input/ShadowFlare.exe')
    raw=(GAME/'System/Game/Parameter/Item.Ibn').read_bytes()
    start=raw.index(b'RCLIB-L');packed=raw[start:]
    packed=packed[:16]+packed[16:].translate(decode_data.item_substitution())
    decoded=decode_data.lz_decode(packed)
    assert sum(x if x<128 else x-256 for x in decoded)&0xffffffff==struct.unpack_from('<I',raw,16)[0]
    (WORK/'Item.Ibn.decoded').write_bytes(decoded)
    items=extract_items.extract()
    (WORK/'items.json').write_text(json.dumps(items,ensure_ascii=False,separators=(',',':')),'utf8')
    tables=extract_tables.parse_tables(tbd_data((GAME/'System/Game/Parameter/Table.Tbd').read_bytes()))
    (WORK/'tables.json').write_text(json.dumps(tables,ensure_ascii=False,separators=(',',':')),'utf8')
    counts={}
    for path in sorted((GAME/'Character/ENEMY').glob('*/Animation.Caf')):
        if path.parent.name.isdecimal():
            caf=CAF(path);counts[int(path.parent.name)]=max(len(d['tracks']) for s in caf.states for d in s['directions'])
    extract_scenarios.PART_COUNTS=counts
    scenarios=[extract_scenarios.parse(p) for p in sorted((GAME/'Scenario').glob('*/Scenario.Mct'))]
    defs={};lookup={}
    for scene in scenarios:
        for e in scene['entities']:
            if e['category']!=2:continue
            n=counts.get(e['pattern'],0)
            parts=e.pop('parts')[:n] if e['has_animation'] else [dict(visible=1,r=1000,g=1000,b=1000)for _ in range(n)]
            spec=dict(pattern=e['pattern'],parts=parts)
            key='v'+hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:15]
            defs[key]=spec;ref=f'{scene["scenario"]}:{e["identifier"]}'
            if ref in lookup:raise ValueError('Duplicate monster identity: '+ref)
            lookup[ref]=dict(visualKey=key,name=e['name'],pattern=e['pattern'],dropGroup=e['drop_group'])
    (WORK/'scenarios.json').write_text(json.dumps(scenarios,ensure_ascii=False,separators=(',',':')),'utf8')
    folder=WORK/'visual-mapping-work';folder.mkdir(exist_ok=True)
    (folder/'enemy-visual-mapping.json').write_text(json.dumps(dict(partsCount=counts,visuals=defs,entities=lookup),ensure_ascii=False,separators=(',',':')),'utf8')
    print(f'Extracted {len(items)} items, {len(scenarios)} scenarios, {len(lookup)} monster placements, {len(defs)} appearances.',flush=True)
