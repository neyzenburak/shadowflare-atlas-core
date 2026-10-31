"""Opt-in local crash capture for the exact authorized single-player game.

Uses the Windows debugging API, continues exceptions normally, and does not
alter instructions, registers, exception disposition or system settings.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import msvcrt
import threading
import time
import traceback
from live_drop import (Game,api,check,ROOT,OpenThread,CloseHandle,GetContext,
                       WOW64_CONTEXT)

class EXCEPTION_RECORD(C.Structure):
    _fields_=[('code',W.DWORD),('flags',W.DWORD),('next',C.c_void_p),
              ('address',C.c_void_p),('count',W.DWORD),('information',C.c_size_t*15)]
class EXCEPTION_INFO(C.Structure):
    _fields_=[('record',EXCEPTION_RECORD),('first',W.DWORD)]
class DEBUG_UNION(C.Union):
    _fields_=[('exception',EXCEPTION_INFO),('file',W.HANDLE),('raw',C.c_ubyte*160)]
class DEBUG_EVENT(C.Structure):
    _fields_=[('code',W.DWORD),('pid',W.DWORD),('tid',W.DWORD),('u',DEBUG_UNION)]

Attach=api('DebugActiveProcess',W.BOOL,[W.DWORD])
Detach=api('DebugActiveProcessStop',W.BOOL,[W.DWORD])
KeepAlive=api('DebugSetProcessKillOnExit',W.BOOL,[W.BOOL])
Wait=api('WaitForDebugEvent',W.BOOL,[C.POINTER(DEBUG_EVENT),W.DWORD])
Continue=api('ContinueDebugEvent',W.BOOL,[W.DWORD,W.DWORD,W.DWORD])
Dump=C.WinDLL('dbghelp',use_last_error=True).MiniDumpWriteDump
Dump.restype=W.BOOL
Dump.argtypes=[W.HANDLE,W.DWORD,W.HANDLE,W.DWORD,C.c_void_p,C.c_void_p,C.c_void_p]

class CrashWatch:
    def __init__(self):
        self.stop=threading.Event();self.thread=None;self.pid=None
        self.message='Kapalı';self.captures=[]
    def info(self):
        return dict(armed=bool(self.thread and self.thread.is_alive()),pid=self.pid,
                    message=self.message,captures=self.captures[-3:])
    def start(self):
        if not self.thread or not self.thread.is_alive():
            self.stop.clear();self.thread=threading.Thread(target=self._worker,daemon=True);self.thread.start()
        return self.info()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(3)
    def _worker(self):
        while not self.stop.is_set():
            game=None;attached=False
            try:
                self.message='Yüklenmiş tek oyunculu ShadowFlare bekleniyor.'
                game=Game();game.state()
                check(Attach(game.pid),'Attach local crash capture');attached=True
                check(KeepAlive(False),'Keep game alive if capture helper exits')
                self.pid=game.pid;self.message='Çöküş izleyicisi bağlı.'
                target=game.words(0x47345c)[0];captured=set()
                while not self.stop.is_set():
                    event=DEBUG_EVENT()
                    if not Wait(C.byref(event),500):
                        if C.get_last_error()==121:continue
                        raise C.WinError(C.get_last_error())
                    disposition=0x00010002 # DBG_CONTINUE
                    try:
                        if event.code in (3,6) and event.u.file:CloseHandle(event.u.file)
                        if event.code==1:
                            exception=event.u.exception;record=exception.record
                            disposition=0x80010001 # let the game's exception handlers run
                            if record.code in (0x80000003,0x4000001f):disposition=0x00010002
                            if (record.code==0xc0000005 and (record.address==target or not exception.first)
                                and record.address not in captured):
                                captured.add(record.address);self._capture(game,event)
                        if event.code==5:break
                    finally:check(Continue(event.pid,event.tid,disposition),'Continue game debug event')
            except Exception as error:
                self.message=str(error)
                # A missing game is normal between restarts; keep the log quiet.
                if attached:
                    with (ROOT/'crash-watch-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)
            finally:
                if attached:Detach(game.pid)
                if game:game.close()
                self.pid=None
            self.stop.wait(.8)
    def _capture(self,game,event):
        folder=ROOT/'crash-captures'/f'{game.pid}-{time.time_ns()}'
        folder.mkdir(parents=True)
        record=event.u.exception.record
        output=dict(pid=game.pid,thread=event.tid,code=record.code,address=record.address,
                    firstChance=bool(event.u.exception.first),information=list(record.information)[:record.count])
        try:
            h=OpenThread(0x4a,False,event.tid);check(h,'Open faulting game thread')
            try:
                context=WOW64_CONTEXT();context.ContextFlags=0x10007
                check(GetContext(h,C.byref(context)),'Read faulting game context')
                output['registers']={name:getattr(context,name) for name in
                    ('Eax','Ebx','Ecx','Edx','Esi','Edi','Ebp','Esp','Eip','EFlags')}
                output['stack']=list(game.words(context.Esp,256))
                for name in ('Ecx','Esi','Edi','Ebp'):
                    pointer=getattr(context,name)
                    if pointer:
                        try:(folder/f'{name}-{pointer:08x}.bin').write_bytes(game.read(pointer,1024))
                        except OSError:pass
            finally:CloseHandle(h)
            try:
                output['game']=game.state()
                output['game']['groundItems']=len(game.ground_items(output['game']['map']))
            except Exception as error:output['gameError']=str(error)
            (folder/'runtime-text.bin').write_bytes(game.read(0x401000,0x71574))
            (folder/'runtime-data.bin').write_bytes(game.read(0x47d000,0x129c8))
            # Context/stack above remain useful even if DbgHelp cannot dump.
            with (folder/'game.dmp').open('wb') as dump:
                if not Dump(game.h,game.pid,msvcrt.get_osfhandle(dump.fileno()),0x1802,None,None,None):
                    output['dumpError']=C.get_last_error()
        except Exception:output['captureError']=traceback.format_exc()
        finally:
            (folder/'exception.json').write_text(json.dumps(output,indent=2),'utf-8')
            self.captures.append(str(folder));self.message='Ayrıntılı çöküş kopyası alındı.'
