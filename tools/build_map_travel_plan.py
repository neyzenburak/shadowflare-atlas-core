"""Build an allowlist of native scenarios and their first complete player entrance."""
import argparse
import hashlib
import json
from pathlib import Path


def build(research, app):
    import pefile
    rows = json.loads((research/'map-work/data-research/mct-full-metadata.json').read_text('utf8'))
    source = json.loads((app/'data.js').read_text('utf8').split('=', 1)[1].strip().removesuffix(';'))
    assert [m['id'] for m in rows] == [m['id'] for m in source['maps']]
    maps = []
    for index, row in enumerate(rows):
        points = {p[0]: p for p in row['rawPoints']}
        groups = sorted({ident//4 for ident in points if ident >= 0 and
                         all(ident//4*4+slot in points for slot in range(4))})
        assert groups, row['id']
        entry = 0 if 0 in groups else groups[0]
        raw = (research/'input/Scenario'/row['id']/'Scenario.Mct').read_bytes()
        maps.append(dict(id=row['id'], name=source['maps'][index]['name'], entry=entry,
                         points=[points[entry*4+slot] for slot in range(4)],
                         mctSHA256=hashlib.sha256(raw).hexdigest()))
    image = pefile.PE(str(research/'resolution-fix/ShadowFlare.exe')).get_memory_mapped_image()
    spans = ((0x43218f, 0x4321ba), (0x41e825, 0x41e834),
             (0x4262b7, 0x42631a), (0x426e80, 0x426ea6),
             (0x427930, 0x42795f), (0x429467, 0x4294e3))
    plan = dict(version=1, maps=maps, verified=[dict(address=a, length=b-a,
                sha256=hashlib.sha256(image[a-0x400000:b-0x400000]).hexdigest()) for a, b in spans])
    (app/'map-travel-plan.json').write_text(json.dumps(plan, ensure_ascii=False, separators=(',', ':'))+'\n', 'utf8')
    return dict(maps=len(maps), specialEntrances=[m['id'] for m in maps if m['entry'] != 0])


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--research', type=Path, default=root.parent/'shadowflare-drop-analysis')
    parser.add_argument('--app', type=Path, default=root/'app')
    args = parser.parse_args()
    print(json.dumps(build(args.research, args.app)))
