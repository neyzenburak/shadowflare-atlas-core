"""Export original ShadowFlare images for the offline atlas. Source is read-only."""
from pathlib import Path
import json
import hashlib
import shutil
import math
from collections import defaultdict

from PIL import Image
from decode_visuals import NJP, CAF

from paths import WORK as ROOT, GAME, OUTPUT
WORK = ROOT/'visual-assets-work'

OUT = OUTPUT/'assets'


def item_icons():
    out=OUT/'items';out.mkdir(parents=True,exist_ok=True)
    source=WORK/'source'/'items';source.mkdir(parents=True,exist_ok=True)
    items=json.loads((ROOT/'items.json').read_text(encoding='utf8'))
    atlases={};cache={};manifest={}
    for item in items:
        f=item['fields'];key=(f['02c'],f['030'],f['03c'],f['020'],f['024'])
        if key not in cache:
            atlas,pattern,palette,columns,rows=key
            if atlas not in atlases:
                name=f'Item{atlas:04d}.njp';local=source/name
                if not local.exists():shutil.copyfile(GAME/'System'/'Game'/'Pattern'/name,local)
                atlases[atlas]=NJP(local)
            image,(x,y)=atlases[atlas].render(pattern,palette)
            # Inventory draw function uses a 32px grid and original piece offsets.
            canvas=Image.new('RGBA',(max(1,columns*32),max(1,rows*32)))
            canvas.alpha_composite(image,(x,y))
            name=hashlib.sha256(str(key).encode()).hexdigest()[:16]+'.png'
            canvas.save(out/name,optimize=True)
            cache[key]={'src':f'assets/items/{name}','w':canvas.width,'h':canvas.height,'atlas':atlas,'pattern':pattern,'palette':palette,'columns':columns,'rows':rows}
        manifest[f"{item['category']}:{f['014']}"]=cache[key]
    (WORK/'items-manifest.json').write_text(json.dumps(manifest,separators=(',',':')),encoding='utf8')
    print(f'ITEMS: {len(manifest)} records, {len(cache)} original images from {len(atlases)} NJP atlases',flush=True)
    return manifest


def write_manifest(items,sprites=None,enemy_keys=None):
    data={'items':items,'sprites':sprites or {},'enemyKeys':enemy_keys or {},'provenance':{'images':'Original ShadowFlare NJP indexed DIB assets; CAF animation timeline; extracted locally, no generated imagery','inventoryGrid':32,'directions':8}}
    (OUT/'visuals.js').write_text('window.SF_VISUALS='+json.dumps(data,separators=(',',':'))+';\n',encoding='utf8')
    (OUT/'visuals.json').write_text(json.dumps(data,separators=(',',':')),encoding='utf8')


def export_sprite(key,spec,njp,caf):
    out=OUT/'mobs';out.mkdir(parents=True,exist_ok=True)
    cache=WORK/'sprite-cache';cache.mkdir(parents=True,exist_ok=True)
    cachefile=cache/(key+'.json')
    if cachefile.exists():return json.loads(cachefile.read_text(encoding='utf8'))
    parts=spec['parts']
    visible=[p['visible']for p in parts]
    colors=[(p['r'],p['g'],p['b'])for p in parts]
    state=0
    if not any(d['max_frame'] for d in caf.states[state]['directions'][:8]):
        state=next((i for i,s in enumerate(caf.states) if any(d['max_frame']for d in s['directions'][:8])),0)
    frames=[];directions=[];unique=[];hashes={}
    for direction in range(8):
        count=caf.states[state]['directions'][direction]['max_frame']
        indices=[]
        for frame in range(count):
            im,xy=caf.frame(njp,state,direction,frame,visible=visible,part_rgb=colors)
            digest=hashlib.sha256(str((xy,im.size)).encode()+im.tobytes()).hexdigest()
            if digest not in hashes:
                hashes[digest]=len(unique);unique.append((im,xy))
            indices.append(hashes[digest])
        directions.append(indices)
    if not unique:
        result={'available':False,'reason':'No original CAF animation frames','pattern':spec['pattern']}
        cachefile.write_text(json.dumps(result),encoding='utf8');return result
    x0=min(xy[0]for im,xy in unique);y0=min(xy[1]for im,xy in unique)
    x1=max(xy[0]+im.width for im,xy in unique);y1=max(xy[1]+im.height for im,xy in unique)
    cw=x1-x0;ch=y1-y0
    columns=min(16,max(1,math.ceil(math.sqrt(len(unique)*ch/cw))))
    sheet=Image.new('RGBA',(cw*columns,ch*math.ceil(len(unique)/columns)))
    tiles=[]
    for i,(im,xy) in enumerate(unique):
        x=(i%columns)*cw;y=(i//columns)*ch
        sheet.alpha_composite(im,(x+xy[0]-x0,y+xy[1]-y0))
        tiles.append({'x':x,'y':y,'w':cw,'h':ch})
    sheet.save(out/(key+'.png'),compress_level=6)
    poster_direction=3 if directions[3] else next(i for i,d in enumerate(directions)if d)
    t=tiles[directions[poster_direction][0]]
    sheet.crop((t['x'],t['y'],t['x']+cw,t['y']+ch)).save(out/(key+'-poster.png'),compress_level=6)
    result={'available':True,'pattern':spec['pattern'],'poster':f'assets/mobs/{key}-poster.png','sheet':f'assets/mobs/{key}.png','cellWidth':cw,'cellHeight':ch,'origin':[-x0,-y0],'fps':20,'state':state,'posterDirection':poster_direction,'directions':[{'frames':[tiles[i]for i in d],'mirror':False}for d in directions],'uniqueFrames':len(unique)}
    cachefile.write_text(json.dumps(result,separators=(',',':')),encoding='utf8')
    return result


def enemy_sprites():
    mapping=json.loads((ROOT/'visual-mapping-work'/'enemy-visual-mapping.json').read_text(encoding='utf8'))
    grouped=defaultdict(list)
    for key,spec in mapping['visuals'].items():grouped[spec['pattern']].append((key,spec))
    sprites={}
    for pattern,specs in sorted(grouped.items()):
        if pattern<0:
            for key,spec in specs:sprites[key]={'available':False,'reason':'Scenario has no character graphic','pattern':pattern}
            continue
        source=GAME/'Character/ENEMY'/f'{pattern:08d}'
        njp=NJP(source/'Animation.Njp');caf=CAF(source/'Animation.Caf')
        print(f'PATTERN {pattern}: {len(specs)} variants',flush=True)
        for i,(key,spec) in enumerate(specs):
            sprites[key]=export_sprite(key,spec,njp,caf)
            if (i+1)%25==0:print(f'  {i+1}/{len(specs)}',flush=True)
        NJP.render.cache_clear();NJP.piece_image.cache_clear()
    keys={key:v['visualKey']for key,v in mapping['entities'].items()}
    (WORK/'sprites-manifest.json').write_text(json.dumps(sprites,separators=(',',':')),encoding='utf8')
    return sprites,keys


if __name__=='__main__':
    import sys
    items=item_icons()
    if '--mobs' in sys.argv:
        sprites,keys=enemy_sprites();write_manifest(items,sprites,keys)
        print(f'MOBS: {len(sprites)} visuals, {len(keys)} entities',flush=True)
    else:write_manifest(items)
