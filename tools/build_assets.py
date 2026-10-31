"""Rebuild a complete local Atlas from a verified, user-owned game folder.

All game files are read only. Build products and resumable caches stay under
the chosen Atlas installation. No existing Atlas ZIP or research directory.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parents[1]
VERSION=3
EXE_SHA256='82011dcc94fd0ba3c9a9447f1c42d24fc334f3574da0d76962aece267821efef'
CRITICAL=('data.js','trainer-data.js','assets/visuals.js','assets/fonts/game-font.js',
          'assets/fonts/stone-texture.png','assets/maps/index.js','assets/maps/manifest.js',
          'assets/world/world.js','assets/scenario-items.js')


def read_js(path):return json.loads(Path(path).read_text('utf8').split('=',1)[1].strip().removesuffix(';'))
def write_js(path,name,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('window.'+name+'='+json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</',r'<\/')+';\n','utf8')


def validate_game(game):
    game=Path(game).expanduser().resolve()
    required=('ShadowFlare.exe','System/Game/Parameter/Item.Ibn','System/Game/Parameter/Table.Tbd',
              'System/Game/Pattern/Item0000.njp','System/Game/Pattern/Status.njp',
              'System/Common/Pattern/Font00.njp','System/Common/Pattern/Font01.njp')
    missing=[n for n in required if not (game/n).is_file()]
    missing += [n for n in ('Scenario','Map','Character/ENEMY') if not (game/n).is_dir()]
    if missing:raise ValueError('Select the ShadowFlare installation folder. Missing: '+', '.join(missing))
    if hashlib.sha256((game/'ShadowFlare.exe').read_bytes()).hexdigest()!=EXE_SHA256:
        raise ValueError('This executable is not the verified ShadowFlare v2.004 build. Game files were not changed.')
    scenarios=len(list((game/'Scenario').glob('*/Scenario.Mct')))
    maps=len(list((game/'Map').glob('*.map')))
    if (scenarios,maps)!=(209,165):
        raise ValueError(f'Atlas requires the complete Episode 1-4 dataset (209 scenarios, 165 map resources); found {scenarios} scenarios and {maps} maps.')
    return game


def is_ready(app):
    app=Path(app)
    return all((app/name).is_file() and (app/name).stat().st_size>0 for name in CRITICAL)


def source_stamp(game):
    files=[game/'ShadowFlare.exe']
    for folder in ('Scenario','Map','Character/ENEMY','System/Game/Parameter','System/Game/Pattern','System/Common/Pattern'):
        files.extend(p for p in (game/folder).rglob('*') if p.is_file() and p.suffix.lower() in ('.mct','.scs','.map','.gnd','.obl','.lst','.njp','.sdw','.caf','.ibn','.tbd'))
    digest=hashlib.sha256()
    for p in sorted(set(files)):
        st=p.stat();digest.update(json.dumps([p.relative_to(game).as_posix(),st.st_size,st.st_mtime_ns],separators=(',',':')).encode())
    # A source/tool change starts a new cache; never reuse another installation's
    # partial manifests merely because file names coincide.
    for p in sorted((ROOT/'tools/asset_build').rglob('*')):
        if p.is_file() and p.suffix in ('.py','.json'):digest.update(p.read_bytes())
    for p in (Path(__file__),ROOT/'tools/build_scenario_items.py',ROOT/'app/resource_tables.py',ROOT/'app/ct_table.py'):
        digest.update(p.read_bytes())
    digest.update(str(game).casefold().encode('utf8'))
    digest.update(str(VERSION).encode())
    return digest.hexdigest()


def catalogue():
    import build_data
    from paths import WORK,OUTPUT
    target=WORK/'atlas';target.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'tools/asset_build/reference/item-guide.json',target/'guide-metadata.json')
    build_data.build()
    data=json.loads((OUTPUT/'data.json').read_text('utf8'))
    scenes=json.loads((WORK/'scenarios.json').read_text('utf8'))
    xp={f'{s["scenario"]}:{e["identifier"]}':e['values'][13] for s in scenes for e in s['entities'] if e['category']==2}
    for mob in data['mobs']:
        for variant in mob['variants']:
            values=[xp[ref] for ref in variant['references']];variant['experience']=[min(values),max(values)]
    write_js(OUTPUT/'data.js','ATLAS_DATA',data)
    (OUTPUT/'data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),'utf8')


def visuals():
    import export_visuals as e
    e.WORK.mkdir(parents=True,exist_ok=True)
    items=e.item_icons();sprites,keys=e.enemy_sprites();e.write_manifest(items,sprites,keys)


def fonts():
    import export_fonts as f
    from decode_visuals import NJP
    from paths import GAME,OUTPUT
    f.OUT.mkdir(parents=True,exist_ok=True)
    main=f.export('Font00');alt=f.export('Font01')
    main.update(name='ShadowFlare original Font00',alternateSrc=alt['src'],glyphFormat='[sourceX,sourceY,width,height,advance]',encoding='CP932 / Shift-JIS',fallback='Unsupported characters use the original ? glyph')
    (f.OUT/'game-font.js').write_text('window.SF_FONT_DATA='+json.dumps(main,ensure_ascii=False,separators=(',',':'))+';\n'+f.HELPER,'utf8')
    texture=NJP(GAME/'System/Game/Pattern/Status.njp').render(6)[0].crop((24,80,280,336))
    texture.save(OUTPUT/'assets/fonts/stone-texture.png',optimize=True)


def map_links():
    import build_map_links as b
    from map_scene import project_world
    from paths import OUTPUT,GAME
    b.OUT.mkdir(parents=True,exist_ok=True);b.main()
    links=json.loads((b.OUT/'map-links.json').read_text('utf8'));maps=[]
    for m in links['maps']:
        maps.append(dict(id=m['id'],name=m['name'],resource=Path(m['resource']).stem.lower(),
            spawns=[[*project_world(p['x'],p['y']),p['mob'],p['variant'],int(bool(p.get('conditional')))] for p in m['spawns']],scriptControlledCount=m['scriptControlledCount']))
    used={m['resource'] for m in maps}
    extra=[dict(id='file:'+p.stem.lower(),name=p.stem,resource=p.stem.lower(),spawns=[]) for p in sorted((GAME/'Map').glob('*.map')) if p.stem.lower() not in used]
    write_js(OUTPUT/'assets/maps/index.js','SF_MAPS',dict(version=1,maps=maps,extraMaps=extra,summary=links['summary']))


def world():
    from PIL import Image
    from paths import OUTPUT
    from research_judge import playable_mask
    data=json.loads((ROOT/'tools/asset_build/reference/world-guide.json').read_text('utf8'))
    directory=OUTPUT/'assets/world';directory.mkdir(parents=True,exist_ok=True)
    resources=data['footprints']['resources']
    for i,(name,old) in enumerate(resources.items()):
        image=Image.open(OUTPUT/'assets/maps/overviews'/(name+'.jpg')).convert('RGBA')
        meta,mask=playable_mask(name,image.size);crop=mask.getbbox()
        if crop is None:raise ValueError('Could not reconstruct world footprint: '+name)
        image.putalpha(mask);image=image.crop(crop);image.thumbnail((512,384),Image.Resampling.LANCZOS)
        image.save(directory/(name+'.png'),optimize=True)
        old.update(meta,src=name+'.png',file=name+'.png',exportWidth=image.width,exportHeight=image.height,width=meta['width'],height=meta['height'])
        if i%10==0:print(f'World terrain {i+1}/{len(resources)}',flush=True)
    write_js(directory/'world.js','SF_WORLD',data)


def trainer():
    from paths import OUTPUT
    sys.path.insert(0,str(ROOT/'app'))
    from ct_table import empty_table
    write_js(OUTPUT/'trainer-data.js','TRAINER_DATA',empty_table())


def scenario():
    from paths import GAME,OUTPUT
    from build_scenario_items import build
    write_js(OUTPUT/'assets/scenario-items.js','SF_SCENARIO_ITEMS',build(GAME,read_js(OUTPUT/'data.js')))


def validate_output(output):
    if not is_ready(output):raise ValueError('Asset generation did not produce all required entry points.')
    data=read_js(output/'data.js');visual=read_js(output/'assets/visuals.js')
    maps=read_js(output/'assets/maps/manifest.js');index=read_js(output/'assets/maps/index.js')
    if len(data['maps'])!=209 or len(data['items'])!=2860:raise ValueError('Unexpected catalogue size for this game build.')
    required=set(CRITICAL)
    for row in visual['items'].values():required.add(row['src'])
    for row in visual['sprites'].values():
        if row.get('available'):required.update((row['poster'],row['sheet']))
    for row in maps['patterns'].values():required.add(row['src'])
    for row in maps['resources'].values():required.update((row['scene'],row['overview']['src']))
    for m in index['maps']+index['extraMaps']:
        if m['resource'] not in maps['resources']:raise ValueError('Map resource missing: '+m['resource'])
    world_data=read_js(output/'assets/world/world.js')
    for row in world_data['footprints']['resources'].values():required.add('assets/world/'+row['src'])
    for source in [*world_data['sources'].values(),*world_data['questRequirements']]:
        if source.get('src'):required.add(source['src'])
    required.update(('assets/fonts/font00.png','assets/fonts/font01.png'))
    missing=[name for name in required if not (output/name).is_file()]
    if missing:raise ValueError('Generated file references are incomplete: '+str(missing[:8]))
    return dict(items=len(data['items']),monsters=len(data['mobs']),scenarios=len(data['maps']),mapResources=len(maps['resources']),visuals=len(visual['sprites']),checkedReferences=len(required))


def publish(output,app,report,stamp):
    app.mkdir(parents=True,exist_ok=True)
    files=[p for p in output.rglob('*') if p.is_file() and p.name!='data.json'
           and p.relative_to(output).parts[:2]!=('assets','turkish')]
    # Publish the catalogue last. A failed extraction never exposes partial data.
    files.sort(key=lambda p:(p.name=='data.js',p.as_posix()))
    for p in files:
        relative=p.relative_to(output);target=app/relative;target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(target.name+'.setup-new');shutil.copyfile(p,temp);os.replace(temp,target)
    manifest=dict(version=VERSION,sourceStamp=stamp,summary=report,files=[dict(path=p.relative_to(output).as_posix(),bytes=p.stat().st_size)for p in files])
    path=app/'assets/setup-manifest.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(manifest,indent=2),'utf8')


@contextmanager
def build_lock():
    directory=ROOT/'.setup-cache';directory.mkdir(parents=True,exist_ok=True)
    with (directory/'build.lock').open('a+b') as handle:
        if handle.seek(0,os.SEEK_END)==0:handle.write(b'1');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise RuntimeError('Atlas setup is already running. Keep its first window open.') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'app')
    parser.add_argument('--work',type=Path)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args();game=validate_game(args.game)
    if args.check:print(json.dumps(dict(game=str(game),compatible=True,ready=is_ready(args.output))));return
    with build_lock():build(args,game)


def build(args,game):
    stamp=source_stamp(game);work=(args.work or ROOT/'.setup-cache'/stamp[:20]).resolve();output=work/'output'
    if output==args.output.resolve():raise ValueError('Build and installation folders must differ.')
    work.mkdir(parents=True,exist_ok=True);output.mkdir(exist_ok=True)
    identity=work/'source-stamp.txt'
    if identity.exists() and identity.read_text('ascii')!=stamp:
        raise ValueError('This --work folder belongs to a different source/tool version. Choose another work folder.')
    identity.write_text(stamp,'ascii')
    os.environ.update(ATLAS_BUILD_WORK=str(work),ATLAS_GAME_ROOT=str(game),ATLAS_BUILD_OUTPUT=str(output))
    sys.path[:0]=[str(ROOT/'tools/asset_build'),str(ROOT/'tools')]
    def extract_phase():
        import extract
        extract.main()
    def maps_phase():
        import export_maps
        export_maps.HERE.mkdir(parents=True,exist_ok=True);export_maps.main(resume=True)
    phases=[('extract',extract_phase),('catalogue',catalogue),('visuals',visuals),('fonts',fonts),('maps',maps_phase),('map-links',map_links),('world',world),('trainer',trainer),('scenario',scenario)]
    start=time.monotonic()
    for i,(name,action) in enumerate(phases):
        marker=work/(name+'.done')
        cached=marker.exists() and marker.read_text('ascii')==stamp
        print(f'[{i+1}/{len(phases)}] {name}'+(' (completed cache)' if cached else ''),flush=True)
        if not cached:
            action();marker.write_text(stamp,'ascii')
    report=validate_output(output);publish(output,args.output.resolve(),report,stamp)
    print('SETUP COMPLETE '+json.dumps(dict(**report,seconds=round(time.monotonic()-start,1))),flush=True)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:
        print('SETUP INTERRUPTED. Run start.cmd again to resume.',file=sys.stderr);sys.exit(130)
    except Exception as error:
        if '--check' not in sys.argv:
            try:
                import traceback
                folder=ROOT/'.setup-cache';folder.mkdir(parents=True,exist_ok=True)
                (folder/'build-error.log').write_text(traceback.format_exc(),'utf8')
            except OSError:pass
        print('SETUP FAILED: '+str(error),file=sys.stderr);sys.exit(1)
