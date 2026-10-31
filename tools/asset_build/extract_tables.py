from pathlib import Path
import struct
import json
import csv

from paths import WORK as ROOT

def parse_tables(data):
    cursor = 0
    def integer():
        nonlocal cursor
        value = struct.unpack_from('<i', data, cursor)[0]
        cursor += 4
        return value
    tables = []
    count = integer()
    for _ in range(count):
        number, rows, cols = integer(), integer(), integer()
        assert 0 <= rows < 10000 and 0 <= cols < 1000
        values = [[integer() for c in range(cols)] for r in range(rows)]
        strings = []
        for r in range(rows):
            row = []
            for c in range(cols):
                length = integer()
                assert 0 <= length < 100000
                raw = data[cursor:cursor+length]
                cursor += length
                row.append(bytes(x ^ 255 for x in raw).decode('cp932', errors='replace'))
            strings.append(row)
        tables.append(dict(number=number, rows=rows, cols=cols, values=values, strings=strings))
    assert cursor == len(data), (cursor, len(data))
    return tables

if __name__ == '__main__':
    tables = parse_tables((ROOT / 'Table.Tbd.decoded').read_bytes())
    (ROOT/'tables.json').write_text(json.dumps(tables, ensure_ascii=False, indent=2),encoding='utf-8')
    out = ROOT / 'tables'
    out.mkdir(exist_ok=True)
    for t in tables:
        with (out / f"table_{t['number']:04d}.csv").open('w',newline='',encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['row']+[f'col_{i}' for i in range(t['cols'])]+[f'text_{i}' for i in range(t['cols'])])
            for i,(v,s) in enumerate(zip(t['values'],t['strings'])): w.writerow([i]+v+s)
        samples = [s for row in t['strings'] for s in row if s][:5]
        print(t['number'],t['rows'],t['cols'],repr(samples),repr(t['values'][:2]))
