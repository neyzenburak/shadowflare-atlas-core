"""Recover serialized item schemas from this executable's loader, then extract items."""
from pathlib import Path
import re
import struct
import json
import csv
from collections import Counter
import capstone
import pefile

from paths import WORK as ROOT
RANGES = [(0x463D60,0x46422F),(0x464381,0x46472E),
          (0x464880,0x464B6B),(0x464CBD,0x464F6B),(0x4650BD,0x465331)]

def schemas():
    pe = pefile.PE(str(ROOT/'input'/'ShadowFlare.exe'))
    md = capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
    result = []
    for start,end in RANGES:
        # Start at a verified instruction boundary before the first fixed field.
        ins = list(md.disasm(pe.get_data(start-0x400000,end-start),start))
        fields = []
        previous_call = 0
        for n,i in enumerate(ins):
            if i.mnemonic != 'call' or i.op_str != '0x44b540':continue
            prev = ins[max(previous_call,n-12):n]
            destinations = []
            for j in prev:
                match = re.fullmatch(r'\w+, \[esi \+ (0x[0-9a-f]+)\]',j.op_str) if j.mnemonic=='lea' else None
                if match: destinations.append(int(match[1],16))
                if j.mnemonic=='add' and j.op_str.startswith('esi, '): destinations.append(int(j.op_str.split(', ')[1],0))
            sizes = [int(j.op_str,0) for j in prev if j.mnemonic=='push' and re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)',j.op_str)]
            assert destinations and sizes, (hex(i.address),destinations,sizes)
            fields.append((destinations[-1],sizes[-1]))
            previous_call = n+1
        result.append(fields)
    return result

def extract():
    data=(ROOT/'Item.Ibn.decoded').read_bytes()
    cursor=0
    def integer():
        nonlocal cursor
        v=struct.unpack_from('<i',data,cursor)[0];cursor+=4;return v
    def string():
        nonlocal cursor
        length=integer();assert 0<=length<10000,(cursor,length)
        b=data[cursor:cursor+length];cursor+=length
        return bytes(x^255 for x in b).decode('cp932',errors='replace')
    items=[]
    for category,fields in enumerate(schemas()):
        count=integer()
        assert 0<=count<10000
        for index in range(count):
            name,base_name=string(),string()
            values={}
            for offset,size in fields:
                raw=data[cursor:cursor+size];cursor+=size
                assert len(raw)==size
                for delta in range(0,size,4):values[f'{offset+delta:03x}']=struct.unpack_from('<i',raw,delta)[0]
            items.append(dict(category=category,index=index,name=name,base_name=base_name,fields=values))
        print(f'Item category {category+1}/5: {count} records',flush=True)
    assert cursor==len(data),(cursor,len(data))
    return items

if __name__=='__main__':
    items=extract()
    (ROOT/'items.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
    keys=sorted({k for i in items for k in i['fields']})
    with (ROOT/'items.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['category','index','name','base_name']+['field_'+k for k in keys])
        for i in items:w.writerow([i[k] for k in ['category','index','name','base_name']]+[i['fields'].get(k,'') for k in keys])
    print('TOTAL',len(items),'COLORS',Counter(i['fields']['018'] for i in items))
    for i in items[:5]:print(i['name'],i['fields'])
