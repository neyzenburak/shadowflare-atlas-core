"""Discover a user-owned installation without a machine-specific default."""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os

HERE=Path(__file__).resolve().parent
SETTINGS=HERE/'installation.json'
EXE_SHA256='82011dcc94fd0ba3c9a9447f1c42d24fc334f3574da0d76962aece267821efef'


def normalize(path):
    p=Path(os.path.expandvars(str(path).strip().strip('"'))).expanduser().resolve()
    return p.parent if p.name.lower()=='shadowflare.exe' else p


def validate(path):
    game=normalize(path)
    required=('ShadowFlare.exe','System/Game/Parameter/Item.Ibn','System/Game/Parameter/Table.Tbd',
              'System/Game/Pattern/Item0000.njp','System/Common/Pattern/Font00.njp',
              'Scenario','Map','Character/ENEMY')
    missing=[n for n in required if not (game/n).exists()]
    if missing:raise ValueError('Select ShadowFlare.exe in the game installation folder. Missing: '+', '.join(missing))
    if hashlib.sha256((game/'ShadowFlare.exe').read_bytes()).hexdigest()!=EXE_SHA256:
        raise ValueError('Unsupported ShadowFlare.exe. Atlas supports the verified English v2.004 executable.')
    return game


def running_games():
    if os.name!='nt':return []
    k=C.WinDLL('kernel32',use_last_error=True)
    class Entry(C.Structure):
        _fields_=[('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',C.c_size_t),
                  ('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),('priority',W.LONG),
                  ('flags',W.DWORD),('name',W.WCHAR*260)]
    k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];k.CreateToolhelp32Snapshot.restype=W.HANDLE
    k.Process32FirstW.argtypes=[W.HANDLE,C.POINTER(Entry)];k.Process32NextW.argtypes=k.Process32FirstW.argtypes
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
    k.CloseHandle.argtypes=[W.HANDLE]
    snapshot=k.CreateToolhelp32Snapshot(2,0);answer=[]
    if snapshot in (None,C.c_void_p(-1).value):return answer
    try:
        entry=Entry();entry.size=C.sizeof(entry);ok=k.Process32FirstW(snapshot,C.byref(entry))
        while ok:
            if entry.name.lower()=='shadowflare.exe':
                process=k.OpenProcess(0x1000,False,entry.pid)
                if process:
                    try:
                        buf=C.create_unicode_buffer(32768);size=W.DWORD(len(buf))
                        if k.QueryFullProcessImageNameW(process,0,buf,C.byref(size)):answer.append(Path(buf.value).parent)
                    finally:k.CloseHandle(process)
            ok=k.Process32NextW(snapshot,C.byref(entry))
    finally:k.CloseHandle(snapshot)
    return answer


def registry_games():
    if os.name!='nt':return []
    import winreg as R
    answer=[]
    for hive in (R.HKEY_CURRENT_USER,R.HKEY_LOCAL_MACHINE):
        for view in (R.KEY_WOW64_64KEY,R.KEY_WOW64_32KEY):
            try:
                with R.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',0,R.KEY_READ|view) as root:
                    for i in range(R.QueryInfoKey(root)[0]):
                        try:
                            with R.OpenKey(root,R.EnumKey(root,i)) as entry:
                                if 'shadowflare' not in str(R.QueryValueEx(entry,'DisplayName')[0]).lower():continue
                                answer.append(R.QueryValueEx(entry,'InstallLocation')[0])
                        except OSError:pass
            except OSError:pass
    return answer


def load_settings(path=SETTINGS):
    try:
        data=json.loads(Path(path).read_text('utf8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}


def locate(explicit=None,settings=SETTINGS):
    if explicit:return validate(explicit)
    configured=[os.environ.get('SHADOWFLARE_GAME'),load_settings(settings).get('gamePath')]
    for candidate in configured:
        if candidate:
            try:return validate(candidate)
            except (OSError,ValueError):pass
    candidates=running_games()
    if not candidates:candidates=registry_games()
    # Only inspect plausible neighbouring/default folders; never scan a drive.
    if not candidates:
        candidates=[HERE.parent,HERE.parent.parent,HERE.parent.parent/'ShadowFlare']
        for env in ('ProgramFiles','ProgramFiles(x86)'):
            if os.environ.get(env):candidates += [Path(os.environ[env])/'ShadowFlare',Path(os.environ[env])/'Emurasoft'/'ShadowFlare']
    valid={}
    for candidate in candidates:
        try:
            game=validate(candidate);valid[str(game).casefold()]=game
        except (OSError,ValueError):pass
    return next(iter(valid.values())) if len(valid)==1 else None


def remember(game,path=SETTINGS):
    game=validate(game);path=Path(path);data=load_settings(path)
    data.update(version=1,gamePath=str(game));path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.setup-new');temp.write_text(json.dumps(data,ensure_ascii=True,indent=2),'utf8');temp.replace(path)
    return game


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('locate','remember'))
    p.add_argument('--game');args=p.parse_args()
    if args.action=='remember' and not args.game:p.error('--game is required')
    try:game=remember(args.game) if args.action=='remember' else locate(args.game)
    except (OSError,ValueError) as error:p.error(str(error))
    print(json.dumps({'gamePath':str(game) if game else None},ensure_ascii=True))


if __name__=='__main__':main()
