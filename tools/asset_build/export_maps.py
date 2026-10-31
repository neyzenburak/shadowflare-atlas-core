"""Export original static ShadowFlare zones for the offline Atlas.

Reads original assets only. No native game code is executed. PNGs retain native
pattern pixels and offsets; only whole-zone overviews are reduced. The browser
loads per-zone classic scripts, so file:// viewing needs no fetch/server.
"""
from pathlib import Path
from functools import lru_cache
from collections import Counter
import hashlib
import json
import shutil
import sys
import time

from PIL import Image, ImageChops

from paths import WORK, OUTPUT
HERE = WORK/'map-work/asset-export'
ROOT = WORK
from map_scene import read_scene, project_world, GAME
from map_patterns import MapNJP

OUT = OUTPUT/'assets/maps'
CACHE = HERE / 'source-cache'
PREFIX = 'assets/maps/'
MAX_OVERVIEW = 1536


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def cache_sources():
    """Small local read-only-source cache; source game files are never changed."""
    manifest = HERE / 'source-manifest.json'
    if manifest.exists() and '--refresh-source-cache' not in sys.argv:
        entries = json.loads(manifest.read_text(encoding='utf-8'))
        assert all((CACHE / e['path']).stat().st_size == e['bytes'] for e in entries)
        return entries
    entries = []
    for source in sorted((GAME / 'Map').rglob('*')):
        if not source.is_file() or source.suffix.lower() not in ('.map', '.gnd', '.obl', '.lst', '.njp', '.sdw'):
            continue
        rel = source.relative_to(GAME)
        dest = CACHE / rel
        if not dest.exists() or dest.stat().st_size != source.stat().st_size:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        raw = dest.read_bytes()
        entries.append(dict(path=str(rel).replace('\\', '/'), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    manifest.write_text(compact(entries), encoding='utf-8')
    return entries


class Exporter:
    def __init__(self):
        self.patterns = {}
        self.sources = {}
        self.invalid = []
        self.stats = Counter()
        self.flags = Counter()
        self.opacities = Counter()
        self.ground_flags = Counter()
        self.resource_paths = {p.name.lower(): p for p in (CACHE / 'Map/Pattern').iterdir() if p.is_file()}

    @lru_cache(maxsize=16)
    def resource(self, name):
        path = self.resource_paths[name.lower()]
        return MapNJP(path)

    def pattern(self, scene, atlas, pattern, palette=-1, rgb=(1000, 1000, 1000), monochrome=False):
        if atlas < 0 or pattern < 0:
            self.stats['emptyReferences'] += 1
            return None
        if atlas >= len(scene['resources']):
            reference=dict(map=scene['name'],atlas=atlas,pattern=pattern,reason='native empty atlas slot outside map list')
            if reference not in self.invalid:self.invalid.append(reference)
            return None
        name = scene['resources'][atlas]
        if name == '?':
            self.invalid.append(dict(map=scene['name'], atlas=atlas, pattern=pattern, reason='unassigned atlas'))
            return None
        njp = self.resource(name)
        if pattern >= len(njp.patterns):
            self.invalid.append(dict(map=scene['name'], atlas=name, pattern=pattern, count=len(njp.patterns), reason='pattern out of range'))
            return None
        palette = -1 if njp.shadow else njp.patterns[pattern].palette if palette < 0 else palette
        assert njp.shadow or 0 <= palette < len(njp.palettes), (scene['name'], name, pattern, palette)
        signature = (name.lower(), pattern, palette, *rgb, *([1] if monochrome else []))
        encoded = compact(signature)
        key = hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:20]
        if key in self.patterns:
            assert key not in self.sources or self.sources[key] == signature
            self.sources[key]=signature
            return key
        path = OUT / 'patterns' / (key + '.png')
        if path.exists() and tuple(rgb) == (1000, 1000, 1000):
            try:
                with Image.open(path) as previous:
                    width, height = previous.size
                    previous.verify()
                cells = [(xx, yy) for flags, index, xx, yy, depth, sx, sy in njp.patterns[pattern].cells
                         if 0 <= index < len(njp.parts) and njp.parts[index].width and njp.parts[index].height]
                x = min((p[0] for p in cells), default=0)
                y = min((p[1] for p in cells), default=0)
                self.patterns[key] = dict(src=PREFIX + 'patterns/' + key + '.png', x=x, y=y, w=width, h=height, shadow=njp.shadow, monochrome=monochrome)
                self.sources[key] = signature
                self.stats['patterns'] += 1
                self.stats['pngBytes'] += path.stat().st_size
                return key
            except (OSError, SyntaxError):
                pass
        im, (x, y) = njp.render(pattern, palette, tuple(rgb))
        if monochrome:
            alpha = im.getchannel('A')
            r, g, b, _ = im.split()
            mono = ImageChops.lighter(ImageChops.lighter(r, g), b)
            im = Image.merge('RGBA', (mono, mono, mono, alpha))
        if njp.shadow:
            # Native SDW is a separate one-bit half-black floor mask.
            alpha = im.getchannel('A').point(lambda p: p // 2)
            im = Image.new('RGBA', im.size)
            im.putalpha(alpha)
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path, optimize=True)
        self.patterns[key] = dict(src=PREFIX + 'patterns/' + key + '.png', x=x, y=y, w=im.width, h=im.height, shadow=njp.shadow, monochrome=monochrome)
        self.sources[key] = signature
        self.stats['patterns'] += 1
        self.stats['pngBytes'] += path.stat().st_size
        # The inherited caches hold strong references to large image composites.
        # PNGs become the persistent cache; keep export memory bounded.
        njp.render.cache_clear()
        if self.stats['patterns'] % 128 == 0:
            njp.piece_image.cache_clear()
        return key

    def scene(self, name):
        source = read_scene(name, game=CACHE)
        cols, rows = source['width'], source['height']
        tw, th = source['tileWidth'], source['tileHeight']
        scene = dict(name=source['name'].lower(), width=cols * tw, height=rows * th,
            cols=cols, rows=rows, tileWidth=tw, tileHeight=th,
            baseMagX=source['baseMagX'], baseMagY=source['baseMagY'],
            layers=source['layers'], objectSort=source.get('objectSort', 'native'), ground=[], shadows=[], objects=[])
        # The native ground grid is the camera/canvas domain. Some original
        # object records are parked at sentinel-like world coordinates (e.g.
        # f00_01 object 223 at world X=999507). Preserve them in scene data,
        # but never inflate the map/fit canvas to those unreachable positions.
        bounds = [0, 0, scene['width'], scene['height']]
        object_bounds = bounds.copy()

        def bound(key, x, y):
            if key is None:
                return
            p = self.patterns[key]
            object_bounds[0] = min(object_bounds[0], x + p['x'])
            object_bounds[1] = min(object_bounds[1], y + p['y'])
            object_bounds[2] = max(object_bounds[2], x + p['x'] + p['w'])
            object_bounds[3] = max(object_bounds[3], y + p['y'] + p['h'])

        for i, (flags, atlas, pattern) in enumerate(source['ground']):
            self.ground_flags[flags] += 1
            key = self.pattern(source, atlas, pattern)
            scene['ground'].append(key)
            bound(key, i % cols * tw, i // cols * th)
        for obj in source['objects']:
            self.flags[obj['flags']] += 1
            self.opacities[obj['opacity']] += 1
            # Native SetShadowObject (10005B60) automatically pairs color
            # atlas N with shadow atlas N+1. Shadow masks are already baked
            # at 50% alpha by pattern(); retain 1000 instance opacity here.
            shadow_atlas=obj['atlas']+1
            if obj['flags']&8 and obj['atlas']>=0 and shadow_atlas<len(source['resources']):
                shadow_name=source['resources'][shadow_atlas]
                if shadow_name!='?' and self.resource(shadow_name).shadow:
                    shadow=self.pattern(source,shadow_atlas,obj['pattern'])
                    if shadow:
                        sx,sy=project_world(obj['worldX'],obj['worldY'])
                        scene['shadows'].append([sx,sy,shadow,1000,0])
            key = self.pattern(source, obj['atlas'], obj['pattern'], obj['palette'], (obj['r'], obj['g'], obj['b']), bool(obj['flags'] & 0x4000))
            if key is None:
                continue
            scene['objects'].append([obj['x'], obj['y'], key, obj['opacity'], obj['flags'],
                obj['worldX'], obj['worldY'], obj['rect'], obj['index']])
            bound(key, obj['x'], obj['y'])
        scene['bounds'] = bounds
        scene['sourceBounds'] = object_bounds
        assert len(scene['ground']) == cols * rows
        self.stats['groundCells'] += len(scene['ground'])
        self.stats['objects'] += len(scene['objects'])
        self.stats['shadows'] += len(scene['shadows'])
        return scene

    def overview(self, scene):
        left, top, right, bottom = scene['bounds']
        scale = min(1, MAX_OVERVIEW / max(right - left, bottom - top))
        size = (max(1, round((right - left) * scale)), max(1, round((bottom - top) * scale)))
        out = Image.new('RGBA', size, (0, 0, 0, 255))

        @lru_cache(maxsize=512)
        def image(key, opacity, width, height):
            p = self.patterns[key]
            im = Image.open(OUT / 'patterns' / (key + '.png')).convert('RGBA')
            if opacity != 1000:
                im.putalpha(im.getchannel('A').point(lambda a: min(255, max(0, a * opacity // 1000))))
            target = (max(1, width), max(1, height))
            if target != im.size:
                im = im.resize(target, Image.Resampling.LANCZOS)
            return im

        def put(key, x, y, opacity=1000, flags=0):
            if key is None:
                return
            p = self.patterns[key]
            px = round((x + p['x'] - left) * scale)
            py = round((y + p['y'] - top) * scale)
            x1 = round((x + p['x'] + p['w'] - left) * scale)
            y1 = round((y + p['y'] + p['h'] - top) * scale)
            if x1 <= 0 or y1 <= 0 or px >= size[0] or py >= size[1]:
                return
            im = image(key, opacity, x1-px, y1-py)
            out.alpha_composite(im, (px, py))

        for i, key in enumerate(scene['ground']):
            put(key, i % scene['cols'] * scene['tileWidth'], i // scene['cols'] * scene['tileHeight'])
        for x,y,key,opacity,flags in scene['shadows']:
            put(key,x,y,opacity,flags)
        for x, y, key, opacity, flags, *_ in scene['objects']:
            put(key, x, y, opacity, flags)
        path = OUT / 'overviews' / (scene['name'] + '.jpg')
        path.parent.mkdir(parents=True, exist_ok=True)
        out.convert('RGB').save(path, quality=90, subsampling=0, optimize=True)
        return dict(src=PREFIX + 'overviews/' + path.name, width=size[0], height=size[1], scale=scale)


def main(resume=False):
    start = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    sources = cache_sources()
    print('Cached', len(sources), 'source files', sum(x['bytes'] for x in sources), 'bytes', flush=True)
    exporter = Exporter()
    priorities = {'f00_01': 0, 'coalmine_01': 1, 'f01_00': 2}
    maps = sorted((CACHE / 'Map').glob('*.[mM][aA][pP]'), key=lambda p: (priorities.get(p.stem.lower(), 3), p.name.lower()))
    resources = {}
    checkpoint=OUT/'manifest.js'
    resume=resume or '--resume' in sys.argv
    if resume and checkpoint.exists():
        text=checkpoint.read_text('utf-8')
        saved=json.loads(text.split('=',1)[1].strip().removesuffix(';'))
        exporter.patterns=saved['patterns'];resources=saved['resources']
        exporter.stats['patterns']=len(exporter.patterns)
        exporter.stats['pngBytes']=sum((OUT/'patterns'/(key+'.png')).stat().st_size for key in exporter.patterns)
        print('Resume checkpoint',len(resources),'maps',flush=True)
    for i, path in enumerate(maps):
        target=OUT/'scenes'/(path.stem.lower()+'.js')
        scene=None
        if resume and path.stem.lower() in resources and target.exists():
            candidate=json.loads(target.read_text('utf-8').split(']=',1)[1].strip().removesuffix(';'))
            if 'shadows' in candidate:
                scene=candidate;overview=resources[scene['name']]['overview']
                exporter.stats['groundCells']+=len(scene['ground']);exporter.stats['objects']+=len(scene['objects']);exporter.stats['shadows']+=len(scene['shadows'])
                exporter.flags.update(o[4] for o in scene['objects']);exporter.opacities.update(o[3] for o in scene['objects'])
        if scene is None:
            scene = exporter.scene(path.stem)
            overview = exporter.overview(scene)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('(window.SF_MAP_SCENES=window.SF_MAP_SCENES||{})[' + compact(scene['name']) + ']=' + compact(scene) + ';\n', encoding='utf-8')
        resources[scene['name']] = dict(key=scene['name'], name=path.stem, source=path.name, width=scene['width'], height=scene['height'],
            bounds=scene['bounds'], cols=scene['cols'], rows=scene['rows'], tileWidth=scene['tileWidth'], tileHeight=scene['tileHeight'],
            baseMagX=scene['baseMagX'], baseMagY=scene['baseMagY'], groundCells=len(scene['ground']), objects=len(scene['objects']),
            scene=PREFIX + 'scenes/' + target.name, overview=overview)
        if i < 3 or i % 10 == 0 or i == len(maps) - 1:
            print(f"{i+1}/{len(maps)} {path.stem} patterns={len(exporter.patterns)} PNG={exporter.stats['pngBytes']/1048576:.1f}MiB elapsed={time.monotonic()-start:.1f}s", flush=True)
            partial = dict(version=1, partial=True, resources=resources, patterns=exporter.patterns,
                objectFields=['x', 'y', 'pattern', 'opacity1000', 'nativeObjectFlags', 'worldX', 'worldY', 'rect', 'sourceIndex'])
            (OUT / 'manifest.js').write_text('window.SF_MAP_ASSETS=' + compact(partial) + ';\n', encoding='utf-8')
    manifest = dict(version=1, provenance='Original Map/*.map, Ground/*.Gnd, Object/*.Obl, Pattern/*.Lst + NJP/SDW; static original terrain and scenery only.',
        objectFields=['x', 'y', 'pattern', 'opacity1000', 'nativeObjectFlags', 'worldX', 'worldY', 'rect', 'sourceIndex'],
        emptyGround='Black; no invented or filled terrain.', maxOverview=MAX_OVERVIEW,
        resources=resources, patterns=exporter.patterns)
    (OUT / 'manifest.json').write_text(compact(manifest), encoding='utf-8')
    (OUT / 'manifest.js').write_text('window.SF_MAP_ASSETS=' + compact(manifest) + ';\n', encoding='utf-8')
    summary = dict(resources=len(resources), stats=dict(exporter.stats), invalidReferences=exporter.invalid,
        objectFlags=dict(exporter.flags), opacities=dict(exporter.opacities), groundFlags=dict(exporter.ground_flags),
        bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()), elapsed=round(time.monotonic()-start, 2))
    (HERE / 'summary.json').write_text(compact(summary), encoding='utf-8')
    (HERE / 'pattern-sources.json').write_text(compact(exporter.sources), encoding='utf-8')
    print(f"Maps complete: {len(resources)} resources, {len(exporter.patterns)} original patterns ({summary['elapsed']}s).",flush=True)
    assert len(resources) == 165
    # Native GetUpd/GetPattern returns NULL for empty or unresolved source slots.
    # These stay black, matching the game; retain the source audit in summary.


if __name__ == '__main__':
    main()
