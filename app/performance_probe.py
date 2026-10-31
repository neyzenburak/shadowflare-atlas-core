"""Short, read-only statistical sampling of the game's threads.

Threads are resumed immediately after each context/stack read. This diagnostic
does not install hooks, change game data, or keep the process suspended while
waiting. CPU time and the existing frame counter bracket the sampling window.
"""
import ctypes as C
import random,struct,time
import statistics
from live_drop import Game,W,api,OpenThread,CloseHandle,Suspend,Resume,GetContext,WOW64_CONTEXT,check
from drop_event import MODULEENTRY32W,Snapshot,ModuleFirst,ModuleNext

GetThreadTimes=api('GetThreadTimes',W.BOOL,[W.HANDLE]+[C.POINTER(W.FILETIME)]*4)

def sample_frame_pacing(seconds,frame_reader):
    """Poll the existing completion counter; never suspend game threads.

    Intervals are approximate to the polling period. Counter jumps are reported
    separately instead of inventing individual frame durations for missed reads.
    """
    if not isinstance(seconds,(int,float)) or isinstance(seconds,bool) or not 1<=seconds<=30:
        raise ValueError('Frame pacing duration must be between 1 and 30 seconds')
    game=Game()
    try:
        state=game.state();before=len(game.ground_items(state['map']))
        initial=previous=frame_reader();start=time.perf_counter();last=None;intervals=[];missed=0
        while time.perf_counter()-start<seconds:
            current=frame_reader();now=time.perf_counter()
            if current<previous:raise RuntimeError('Frame counter restarted during measurement')
            if current!=previous:
                delta=current-previous
                if last is not None and delta==1:intervals.append((now-last)*1000)
                if delta>1:missed+=delta-1
                last=now;previous=current
            time.sleep(.002)
        elapsed=time.perf_counter()-start
        ordered=sorted(intervals)
        def percentile(q):return ordered[min(len(ordered)-1,int((len(ordered)-1)*q))] if ordered else None
        return dict(pid=game.pid,seconds=elapsed,frames=previous-initial,fps=(previous-initial)/elapsed,
                    groundItemsBefore=before,groundItemsAfter=len(game.ground_items(state['map'])),
                    frameMs=dict(median=statistics.median(intervals) if intervals else None,p95=percentile(.95),
                                 p99=percentile(.99),maximum=max(intervals) if intervals else None),
                    over50ms=sum(v>50 for v in intervals),over100ms=sum(v>100 for v in intervals),
                    missedFrameTransitions=missed,intervalsMs=intervals,
                    diagnostic='passive completion-counter polling at approximately 2 ms; no thread suspension')
    finally:game.close()

def inspect_terrain(game,items):
    screen=game.words(0x482d1c)[0];ground=game.words(screen+0x30)[0]
    mx,my,width,height,ox,oy,rows=struct.unpack('<7i',game.read(ground+0x18,28))
    if not (mx>0 and my>0 and 0<width<100000 and 0<height<100000):raise RuntimeError('Unknown ground grid')
    pointers=game.words(rows,height);cache={};blocked=0;outside=0
    for item in items:
        x=item['x']//mx-ox;y=item['y']//my-oy
        if not (0<=x<width and 0<=y<height):item['terrainBlocked']=True;outside+=1
        else:
            if y not in cache:cache[y]=game.read(pointers[y],width*2)
            item['terrainBlocked']=bool(struct.unpack_from('<H',cache[y],x*2)[0]&1)
        blocked+=item['terrainBlocked']
    return dict(baseMag=[mx,my],size=[width,height],offset=[ox,oy],blockedItems=blocked,outsideItems=outside)

def sample_profile(seconds=5,frame_reader=None):
    if not isinstance(seconds,(int,float)) or isinstance(seconds,bool) or not 1<=seconds<=10:
        raise ValueError('Profile duration must be between 1 and 10 seconds')
    game=Game();handles={};rows={};modules=[]
    def cpu(handle):
        values=[W.FILETIME() for _ in range(4)]
        check(GetThreadTimes(handle,*(C.byref(v) for v in values)),'Read game thread CPU times')
        return sum((v.dwHighDateTime<<32)|v.dwLowDateTime for v in values[2:])/10000000
    try:
        snapshot=Snapshot(0x18,game.pid)
        try:
            e=MODULEENTRY32W();e.dwSize=C.sizeof(e);ok=ModuleFirst(snapshot,C.byref(e))
            while ok:
                modules.append(dict(name=e.szModule,base=e.modBaseAddr,size=e.modBaseSize))
                ok=ModuleNext(snapshot,C.byref(e))
        finally:CloseHandle(snapshot)
        for tid in game.threads():
            handle=OpenThread(0x4a,False,tid)
            if handle:
                handles[tid]=handle;rows[tid]=dict(tid=tid,cpuStart=cpu(handle),samples=[])
        state=game.state();itemsBefore=len(game.ground_items(state['map']))
        framesBefore=frame_reader() if frame_reader else None
        start=time.perf_counter();rounds=0
        while time.perf_counter()-start<seconds:
            for tid,handle in handles.items():
                if Suspend(handle)==0xffffffff:continue
                try:
                    ctx=WOW64_CONTEXT();ctx.ContextFlags=0x10007
                    if GetContext(handle,C.byref(ctx)):
                        try:stack=list(game.words(ctx.Esp,32))
                        except OSError:stack=[]
                        rows[tid]['samples'].append(dict(ip=ctx.Eip,sp=ctx.Esp,bp=ctx.Ebp,stack=stack))
                finally:Resume(handle)
            rounds+=1;time.sleep(random.uniform(.005,.013))
        elapsed=time.perf_counter()-start
        framesAfter=frame_reader() if frame_reader else None
        for tid,handle in handles.items():rows[tid]['cpuSeconds']=cpu(handle)-rows[tid].pop('cpuStart')
        return dict(pid=game.pid,seconds=elapsed,rounds=rounds,threads=list(rows.values()),modules=modules,
                    map=state['map'],groundItemsBefore=itemsBefore,
                    groundItemsAfter=len(game.ground_items(state['map'])),framesBefore=framesBefore,framesAfter=framesAfter,
                    diagnostic='statistical thread sampling; brief suspension may lower measured FPS')
    finally:
        for handle in handles.values():CloseHandle(handle)
        game.close()
