"""Package the local runnable app, excluding saves, captures and helper logs."""
from pathlib import Path
import hashlib,json,zipfile
from build_assets import is_ready
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'ShadowFlare-Atlas-Core.zip'
TEMP=OUT.with_name(OUT.name+'.setup-new')
if not is_ready(ROOT/'app'):raise SystemExit('Run start.cmd first to generate the complete local asset package.')
files=[ROOT/n for n in ('start.cmd','setup.cmd','make-zip.cmd','launcher.ps1','README.md','LICENSE','requirements.txt','requirements-dev.txt','requirements-setup.txt')]
files += sorted(p for p in (ROOT/'app').iterdir() if p.is_file() and p.suffix.lower() in ('.py','.js','.html','.css','.svg','.txt','.cmd','.json') and p.name!='trainer-plan.json' and (p.suffix!='.json' or p.name.endswith('-plan.json')))
files += sorted(p for p in (ROOT/'app/assets').rglob('*') if p.is_file() and p.suffix.lower()!='.ct' and p.relative_to(ROOT/'app/assets').parts[0]!='turkish')
for folder,suffixes in (('docs',('.md','.asm')),('tools',('.py','.asm')),('tests',('.py','.cjs'))):
    files += sorted(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in suffixes)
files += sorted((ROOT/'tools/asset_build/reference').glob('*.json'))
names=[p.relative_to(ROOT).as_posix() for p in files]
from build_assets import read_js
table=read_js(ROOT/'app/trainer-data.js')
if any(table.get(k)for k in ('records','patches','actions','structures','sha256')):raise SystemExit('Packaging refuses bundled CT data; restore the empty trainer-data.js first.')
assert len(names)==len(set(names)) and all(p.is_file() for p in files)
with zipfile.ZipFile(TEMP,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p,n in zip(files,names):z.write(p,n)
with zipfile.ZipFile(TEMP) as z:
    assert z.testzip() is None
    assert set(z.namelist())==set(names)
    for p,n in zip(files,names):assert z.read(n)==p.read_bytes()
TEMP.replace(OUT)
print(json.dumps(dict(path=str(OUT),files=len(files),bytes=OUT.stat().st_size,sha256=hashlib.sha256(OUT.read_bytes()).hexdigest(),verified=True),indent=2))
