"""Import a local CT as data. No shipped records, Lua or downloaded tables."""
from pathlib import Path
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET
from ct_asm import address,assemble,integer,script_blocks,patch_span

MAX_BYTES=4*1024*1024


def empty_table():
    return dict(version=1,author='',source='Kendi .CT dosyanı ekleyebilirsin.',sha256=None,
                records=[],patches={},actions={},structures=[],comments='',counts=dict(entries=0,structures=0))


def image_bytes(executable,va,size):
    data=Path(executable).read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
    if data[pe:pe+4]!=b'PE\0\0':raise ValueError('Invalid executable')
    count=struct.unpack_from('<H',data,pe+6)[0];optional=struct.unpack_from('<H',data,pe+20)[0]
    image_base=struct.unpack_from('<I',data,pe+24+28)[0];rva=va-image_base
    for i in range(count):
        at=pe+24+optional+i*40
        virtual_size,virtual,raw_size,raw=struct.unpack_from('<4I',data,at+8)
        if virtual<=rva and rva+size<=virtual+raw_size:return data[raw+rva-virtual:raw+rva-virtual+size]
    raise ValueError('Address is not backed by the original executable')


def pointer_action(script):
    writes=[];target=None
    for line in script_blocks(script)['enable']:
        match=re.fullmatch(r'\[(fallbackPtr|fallbackComPtr)\]\+([0-9a-fA-F]+):',line)
        if match:target=(match[1],int(match[2],16));continue
        if not target or not line.lower().startswith('db '):raise ValueError('Unsupported pointer action')
        data=bytes(integer(n)for n in re.split(r'[ ,]+',line[3:].strip()))
        root,offset=target
        if not 0<=offset<=0x2000 or not 1<=len(data)<=16:raise ValueError('Pointer action is outside its object')
        writes.append(dict(root=root,offset=offset,data=data.hex()));target=None
    if not writes:raise ValueError('Empty action')
    return writes


def parse(raw,executable,filename='local.ct'):
    if not isinstance(raw,bytes)or not 0<len(raw)<=MAX_BYTES:raise ValueError('CT dosyası 4 MB sınırını aşamaz.')
    if b'<!DOCTYPE'in raw.upper()or b'<!ENTITY'in raw.upper():raise ValueError('XML entity definitions are not accepted')
    tree=ET.fromstring(raw)
    if tree.tag!='CheatTable':raise ValueError('Bu bir Cheat Engine tablosu değil.')
    result=empty_table();result.update(source=Path(filename).name,sha256=hashlib.sha256(raw).hexdigest(),comments=tree.findtext('Comments')or'')
    seen=set()
    def entries(parent,parent_id=None):
        for entry in parent.findall('./CheatEntry'):
            ident=entry.findtext('ID')or str(len(seen));ident='ct:'+ident
            if ident in seen or len(seen)>=3000:raise ValueError('Duplicate or excessive CT records')
            seen.add(ident)
            label=(entry.findtext('Description')or ident).strip('"')
            record=dict(id=ident,parent=parent_id,label=label,description=label,type=entry.findtext('VariableType')or'',kind='group')
            script=entry.findtext('AssemblerScript')
            if script:
                record['script']=script
                try:
                    if len(script)>250000:raise ValueError('Script is too large')
                    if 'registersymbol('in script.lower()or 'mov [fallbackPtr]'in script:
                        record.update(kind='connection',note='Bağlantı adresleri Atlas tarafından otomatik çözülür; bu betik çalıştırılmaz.')
                        raise StopIteration
                    if '[fallback'in script:
                        result['actions'][ident]=pointer_action(script);record['kind']='action'
                    else:
                        changes,allocated=assemble(script)
                        result['patches'][ident]=[]
                        for c in changes:
                            original=image_bytes(executable,c['address'],128)
                            size=patch_span(original,len(c['after']))
                            result['patches'][ident].append(dict(address=c['address'],before=original[:size].hex(),after=c['after'].ljust(size,b'\x90').hex()))
                        record['kind']='toggle';record['allocated']=bool(allocated)
                except StopIteration:pass
                except (ValueError,KeyError,struct.error)as error:
                    result['patches'].pop(ident,None);result['actions'].pop(ident,None)
                    record['kind']='unsupported';record['note']='Çalıştırılmadı: '+str(error)
            elif entry.findtext('Address'):
                root=entry.findtext('Address').replace('"','').strip()
                try:
                    if root not in ('fallbackPtr','fallbackComPtr'):
                        root=hex(address(root))
                        if not 0x47d000<=int(root,16)<0x4b0000:raise ValueError('Value address is outside game data')
                    offset_text=[o.text or ''for o in entry.findall('./Offsets/Offset')]
                    if any(not re.fullmatch(r'[0-9a-fA-F]+(?:\+[0-9a-fA-F]+)*',o)for o in offset_text):raise ValueError('Unsupported offset expression')
                    offsets=[sum(int(n,16)for n in o.split('+'))for o in offset_text]
                    if len(offsets)>8 or any(not 0<=o<=0x2000 for o in offsets):raise ValueError('Pointer chain is too large')
                    if record['type']not in ('4 Bytes','String'):raise ValueError('Only 32-bit values and bounded strings are supported')
                    record.update(kind='value',address=root,offsets=offsets,hex=entry.findtext('ShowAsHex')=='1',signed=entry.findtext('ShowAsSigned')=='1',readOnly=not offsets and root.startswith('fallback'))
                    if record['type']=='String':record['length']=min(256,max(1,int(entry.findtext('Length')or'32')))
                    choices=[]
                    for line in (entry.findtext('DropDownList')or'').splitlines():
                        if ':'in line:
                            number,text=line.split(':',1)
                            try:choices.append([int(number,10),text])
                            except ValueError:pass
                    if choices:record['choices']=choices
                except (ValueError,KeyError)as error:record.update(kind='unsupported',note=str(error))
            result['records'].append(record)
            child=entry.find('CheatEntries')
            if child is not None:entries(child,ident)
    root=tree.find('CheatEntries')
    if root is None:raise ValueError('Tabloda kayıt yok.')
    entries(root)
    for node in tree.findall('./Structures/Structure'):
        result['structures'].append(dict(name=node.get('Name','Structure'),elements=len(node.findall('./Element')),xml=ET.tostring(node,encoding='unicode')))
    result['counts']=dict(entries=len(seen),structures=len(result['structures']),supported=sum(r['kind']in('value','toggle','action')for r in result['records']),unsupported=sum(r['kind']=='unsupported'for r in result['records']))
    return result


def load(folder):
    try:return json.loads((Path(folder)/'table.json').read_text('utf8'))
    except (OSError,ValueError):return empty_table()
