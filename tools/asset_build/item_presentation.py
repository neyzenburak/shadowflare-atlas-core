"""Original item-panel values and conservative equipment grouping.

The displayed base values stay separate from the rolled additions, as in the
archived guide screenshots. Source offsets are shared with the executable's
item schema and the local Cheat Engine table; no live game state is read.
"""
from pathlib import Path
import json

from paths import WORK
ROOT = WORK/'atlas'
BASE_LABELS = ['Attack', 'Hit Rate', 'Defense', 'Evasion Rate', 'Magical Attack',
               'Magical Hit Rate', 'Magical Defense', 'Magical Evasion Rate',
               'Speed of Attack', 'Walking Speed']
AFFIX_LABELS = ['Attack', 'Defense', 'Hit Rate', 'Evasion Rate', 'Magical Attack',
 'Magical Defense', 'Magical Hit Rate', 'Magical Evasion Rate', 'Speed of Attack',
 'Walking Speed', 'Maximum HP', 'Maximum MP', 'Strength', 'Magic Level',
 'Probability of Stiffness', 'Duration of Stiffness', 'Avoidance of Counterattacks',
 'Life Recovery', 'Mental Recovery', 'Mental Consumption', 'Generation of Reflection',
 'Reflection Rate', 'Effect of Stamina Medicine', 'Effect of Mental Medicine',
 'Incidents of Absorption', 'Absorption Rate', 'Amount of Gold', 'Effect of Mine',
 'Number of Mines', 'Speed of Chant', 'Companion HP', 'Companion Attack',
 'Companion Defense', 'Companion Hit Rate', 'Companion Evasion Rate',
 'Companion Magical Attack', 'Companion Magical Defense', 'Companion Magical Hit Rate',
 'Companion Magical Evasion Rate']
ELEMENTS = ['Fire', 'Water', 'Earth', 'Thunder', 'Sacred', 'Dark', 'Gel', 'Metal']
TYPES = [
 ('onehand', 'Tek el kılıçları'), ('twohand', 'Çift el kılıçları'), ('katana', 'Katanalar'),
 ('axe', 'Baltalar'), ('bowgun', 'Arbaletler'), ('staff', 'Asalar ve çubuklar'),
 ('weapon-other', 'Diğer silahlar'), ('body', 'Gövde zırhları'), ('helm', 'Başlıklar'),
 ('greaves', 'Çizmeler ve bacaklıklar'), ('shield', 'Kalkanlar'), ('book', 'Kitaplar'),
 ('armguard', 'Kol koruyucuları'), ('armor-other', 'Diğer zırhlar'),
 ('accessory', 'Aksesuarlar'), ('consumable', 'Tüketilebilirler'), ('other', 'Diğer nesneler')]
WEAPON_TYPES = {12: 'onehand', 14: 'onehand', 17: 'onehand', 20: 'twohand',
                19: 'katana', 21: 'axe', 16: 'bowgun', 15: 'staff', 18: 'staff'}

def native_type(source):
    c, f = source['category'], source['fields']
    if c == 0:
        return WEAPON_TYPES.get(f.get('0c4'), 'weapon-other')
    if c == 1:
        bucket = f['014'] // 1000000
        if bucket in range(5):
            return ['body', 'shield', 'helm', 'greaves', 'book'][bucket]
        if f.get('0c4') in [9, 10, 11]: return 'shield'
        if f.get('0c4') == -1: return 'book'
        if f.get('0c4') == -6: return 'armguard'
        # Special records do not share the regular ID buckets. Guide matches
        # may refine their group; avoid guessing from their English name.
        return 'armor-other'
    return {2: 'accessory', 3: 'consumable', 4: 'other'}[c]

def enrich_payload(payload, sources):
    source_by_key = {f"{i['category']}:{i['fields']['014']}": i for i in sources}
    guide_path = ROOT / 'guide-metadata.json'
    guide = json.loads(guide_path.read_text('utf-8')) if guide_path.exists() else {'items': {}}
    for item in payload['items']:
        source = source_by_key[item['key']]
        c, f = source['category'], source['fields']
        level = f.get('0e8') if c <= 1 else f.get('2c8') if c == 2 else None
        item['level'] = level
        base = []
        if c <= 1:
            for k, label in enumerate(BASE_LABELS):
                value = f[f'{0x90 + k * 4:03x}']
                if value: base.append([label, value])
            base.append(['Durability', f['0b8']])
        base.append(['Weight', f['028']])
        if level: base.append(['Required Level', level])
        base.append(['Sale Price', f['040']])
        additions = []
        if c <= 2:
            for kind, start, labels in [('stat', [0x114, 0xec, 0x94][c], AFFIX_LABELS),
                                        ('element', [0x2e8, 0x2c0, 0x268][c], ELEMENTS)]:
                for k, label in enumerate(labels):
                    lo, hi, rate = [f[f'{start + k * 12 + d:03x}'] for d in (0, 4, 8)]
                    if rate > 0 and (lo or hi):
                        additions.append([label, lo, lo + abs(hi - lo + 1) - 1, rate,
                                          kind, k in (14, 16, 20, 21, 24, 25) if kind == 'stat' else False])
        item['kind'] = native_type(source)
        item['guide'] = guide.get('items', {}).get(item['key'], {'status': 'unreviewed'})
        if item['kind'] in ('armor-other','weapon-other') and item['guide'].get('kind'):
            item['kind'] = item['guide']['kind']
        item['tooltip'] = {'base': base, 'additions': additions,
            'elements': [f[f'{0xc8 + k * 4:03x}'] for k in range(8)] if c <= 1 else None}
    payload['itemTypes'] = [{'id': key, 'name': name} for key, name in TYPES]
    payload['guideSummary'] = guide.get('summary', {})

def update_dist():
    dist = ROOT / 'dist'
    payload = json.loads((dist / 'data.json').read_text('utf-8'))
    sources = json.loads((ROOT.parent / 'items.json').read_text('utf-8'))
    enrich_payload(payload, sources)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', r'<\/')
    (dist / 'data.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), 'utf-8')
    (dist / 'data.js').write_text('window.ATLAS_DATA=' + encoded + ';\n', 'utf-8')
    print(f"Enriched {len(payload['items'])} item panels; probabilities unchanged.")

if __name__ == '__main__': update_dist()
