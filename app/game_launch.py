"""Start a verified game at the selected resolution, without external helpers.

The new process starts suspended. Its complete startup patch set is verified,
written and read back before its first thread resumes. A failure terminates
only that new, unresumed process. Existing games are never restarted/closed.
"""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import json
import os
import struct
import threading
from game_paths import validate,locate,remember,load_settings
from resolution_layout import validate_size
from resolution_native import build_changes

ROOT=Path(__file__).resolve().parent
VERSION=2
SETTINGS=ROOT/'game-launch-settings.json'


def create_suspended(executable):
    from live_drop import api,check
    class Startup(C.Structure):
        _fields_=[('cb',W.DWORD),('reserved',W.LPWSTR),('desktop',W.LPWSTR),('title',W.LPWSTR),
                  ('x',W.DWORD),('y',W.DWORD),('cx',W.DWORD),('cy',W.DWORD),
                  ('charsX',W.DWORD),('charsY',W.DWORD),('fill',W.DWORD),('flags',W.DWORD),
                  ('show',W.WORD),('reservedBytes',W.WORD),('reservedPointer',C.c_void_p),
                  ('input',W.HANDLE),('output',W.HANDLE),('error',W.HANDLE)]
    class Process(C.Structure):
        _fields_=[('process',W.HANDLE),('thread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
    create=api('CreateProcessW',W.BOOL,[W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,C.c_void_p,W.LPCWSTR,C.POINTER(Startup),C.POINTER(Process)])
    si=Startup();si.cb=C.sizeof(si);pi=Process()
    cmd=C.create_unicode_buffer('"'+str(executable)+'"')
    check(create(str(executable),cmd,None,None,False,4,None,str(executable.parent),C.byref(si),C.byref(pi)),'Start suspended ShadowFlare')
    return pi


def apply_startup(game,width,height):
    from live_drop import Alloc,Protect,Flush,check
    base=Alloc(game.h,None,4096,0x3000,0x40);check(base,'Allocate native viewport')
    if not 0<base<0x100000000:raise RuntimeError('32 bit başlangıç alanı ayrılamadı.')
    changes,chunks=build_changes(base,width,height)
    for address,code in chunks:game.write(address,code)
    for p in changes:
        if game.read(p['address'],len(p['before']))!=p['before']:raise RuntimeError(f"Başlangıç kodu tanınmadı: {p['address']:08x}")
    for p in changes:
        old=W.DWORD();check(Protect(game.h,p['address'],len(p['after']),0x40,C.byref(old)),'Protect startup code')
        try:game.write(p['address'],p['after'])
        finally:
            previous=W.DWORD();check(Protect(game.h,p['address'],len(p['after']),old.value,C.byref(previous)),'Restore startup code protection')
        if game.read(p['address'],len(p['after']))!=p['after']:raise RuntimeError('Başlangıç yazma doğrulaması başarısız.')
    for address,code in chunks:
        if game.read(address,len(code))!=code:raise RuntimeError('Başlangıç yardımcısı doğrulanamadı.')
    check(Flush(game.h,None,0),'Flush resolution startup')
    return dict(base=base,patches=len(changes))


class GameLauncher:
    def __init__(self):
        self._lock=threading.Lock();self.message='';self.last_pid=None
        try:self.settings=json.loads(SETTINGS.read_text('utf8'));validate_size(self.settings['width'],self.settings['height'])
        except (OSError,ValueError,KeyError,TypeError):self.settings=dict(width=1920,height=900)

    def info(self):
        from live_drop import game_pids
        pids=game_pids()
        return dict(version=VERSION,**self.settings,gamePath=load_settings().get('gamePath',''),
                    running=bool(pids),pids=pids,message=self.message,lastPid=self.last_pid)

    def configure(self,body):
        width,height=validate_size(body.get('width',self.settings['width']),body.get('height',self.settings['height']))
        path=body.get('gamePath')
        if path is not None:
            if not isinstance(path,str) or not path.strip():raise ValueError('Oyun klasörünü seç veya yolunu gir.')
            remember(path)
        self.settings=dict(width=width,height=height)
        temp=SETTINGS.with_suffix('.tmp');temp.write_text(json.dumps(self.settings,indent=2),'utf8');os.replace(temp,SETTINGS)
        return self.info()

    def launch(self,body=None,display=None):
        from live_drop import Game,game_pids,Resume,CloseHandle,api,LOCK
        if not self._lock.acquire(False):raise RuntimeError('Oyun zaten başlatılıyor.')
        pi=None;game=None;resumed=False
        if not LOCK.acquire(False):self._lock.release();raise RuntimeError('Önceki oyun işleminin bitmesini bekle.')
        try:
            if game_pids():raise RuntimeError('ShadowFlare zaten açık. Yeni çözünürlük bir sonraki açılışta uygulanır.')
            self.configure(body or {});width,height=self.settings['width'],self.settings['height']
            folder=locate()
            if folder is None:raise ValueError('Oyun klasörü bulunamadı; ShadowFlare klasörünün yolunu gir.')
            folder=validate(folder)
            pi=create_suspended(folder/'ShadowFlare.exe');game=Game(pid=pi.pid,write=True)
            apply_startup(game,width,height)
            if Resume(pi.thread)==0xffffffff:raise C.WinError(C.get_last_error())
            resumed=True;self.last_pid=pi.pid;self.message=f'Oyun {width} × {height} olarak başlatıldı.'
        except Exception as error:
            self.message=str(error)
            if pi is not None and not resumed:
                terminate=api('TerminateProcess',W.BOOL,[W.HANDLE,W.UINT]);terminate(pi.process,1)
            raise
        finally:
            if game:game.close()
            if pi is not None:CloseHandle(pi.thread);CloseHandle(pi.process)
            LOCK.release();self._lock.release()
        if display is not None:display.enable()
        return self.info()
