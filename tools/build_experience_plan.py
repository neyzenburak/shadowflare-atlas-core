"""Rebuild native EXP fingerprints and audit every Atlas placement's raw EXP."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def build(research, app):
    import pefile
    image = pefile.PE(str(research/'resolution-fix/ShadowFlare.exe')).get_memory_mapped_image()
    spans = [(0x413518, 0x413579), (0x412fb0, 0x413490),
             (0x450080, 0x4501b3), (0x44ea60, 0x44ea8d)]

    def table(number):
        with (research/f'tables/table_{number:04d}.csv').open(encoding='utf-8-sig', newline='') as f:
            return [int(row['col_0']) for row in csv.DictReader(f)]

    plan = dict(version=1, hook=0x413579, original=image[0x13579:0x13581].hex(),
                sourceField=13, nativeEnemyField=0x17c, contribution=table(14),
                levelRequirements=table(13), verified=[dict(address=a, length=b-a,
                    sha256=hashlib.sha256(image[a-0x400000:b-0x400000]).hexdigest()) for a, b in spans])
    (app/'experience-plan.json').write_text(json.dumps(plan, indent=2)+'\n', 'utf8')
    with (research/'enemies.csv').open(encoding='utf-8-sig', newline='') as f:
        index = {f"{row['scenario']}:{row['identifier']}": int(row['payload_034']) for row in csv.DictReader(f)}
    text = (app/'data.js').read_text('utf8')
    data = json.loads(text.split('=', 1)[1].strip().removesuffix(';'))
    variants = ranged = 0
    for mob in data['mobs']:
        for variant in mob['variants']:
            values = [index[ref] for ref in variant['references']]
            assert min(values) >= 0
            variant['experience'] = [min(values), max(values)]
            variants += 1
            ranged += min(values) != max(values)
    (app/'data.js').write_text('window.ATLAS_DATA='+json.dumps(data, ensure_ascii=False, separators=(',', ':'))+';\n', 'utf8')
    return dict(placements=len(index), variants=variants, rangedVariants=ranged)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--research', type=Path, default=root.parent/'shadowflare-drop-analysis')
    parser.add_argument('--app', type=Path, default=root/'app')
    args = parser.parse_args()
    print(json.dumps(build(args.research, args.app)))
