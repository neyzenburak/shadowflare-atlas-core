"""Import assets from either the old flat ZIP or the packaged app/ layout."""
from pathlib import Path
import sys,zipfile

def import_assets(archive,root):
    root=Path(root);count=0
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            name=entry.filename;p=Path(name)
            if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:raise ValueError('Invalid archive path')
            if entry.is_dir():continue
            if name.startswith('app/'):name=name[4:]
            if name.startswith('assets/turkish/'):continue
            if name.startswith('assets/') or name=='data.js':
                out=root/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(entry));count+=1
    if not count:raise ValueError('Archive contains no Atlas assets')
    return count

if __name__=='__main__':
    print('Local assets imported:',import_assets(sys.argv[1],Path(__file__).resolve().parents[1]/'app'))
