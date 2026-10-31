"""Regenerate compact beam thresholds from the local verified affix analysis."""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = '''"""Derived 80%-roll rules from the verified original Item.Ibn templates.

Only Angel, Saint Angel, Conqueror and Legendary Magic equipment qualify.
Every variable nonnegative bonus must meet min+ceil(0.8*(max-min)).
Fixed bonuses and penalties do not participate. Native template values are
used, not base equipment stats or post-identification tooltip strings.
"""

RULES = (
'''


def build(source):
    rows = []
    for item in source['items']:
        if item['prefix'] not in ('Angel', 'Saint Angel', 'Conqueror', 'Legendary'):
            continue
        category, ident = map(int, item['key'].split(':'))
        checks = []
        for stat in item['bonuses']:
            low, high = stat['minimum'], stat['maximum']
            if low >= 0 and high > low:
                checks.append((stat['instanceValueOffset'], low+(80*(high-low)+99)//100, high))
        assert item['rarity'] == 1 and category <= 2 and checks
        rows.append((category, ident, item['name'], tuple(checks)))
    rows.sort()
    assert len(rows) == 133 and sum(len(row[3]) for row in rows) == 512
    assert len({(row[0], row[1]) for row in rows}) == len(rows)
    return HEADER+''.join(f'    ({c}, {i}, {checks!r}),  # {name}\n'
                          for c, i, name, checks in rows)+')\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('analysis', type=Path, help='Local magic-affixes.json')
    args = parser.parse_args()
    target = ROOT/'app/magic_beam_rules.py'
    target.write_text(build(json.loads(args.analysis.read_text('utf8'))), encoding='utf8')
    print(target)
