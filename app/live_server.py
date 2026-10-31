"""Loopback-only companion for the offline Atlas. Python standard library only."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import argparse
import ctypes
import hashlib
import json
import os
import secrets
import subprocess
import struct
import sys
import threading
import time
import traceback
import webbrowser
from urllib.parse import urlsplit
from urllib.request import urlopen,Request
from live_drop import status,drop_one,catalogue,DIST,ROOT
from drop_event import DropEvent,VERSION as EVENT_VERSION
from display_fix import DisplayFix,VERSION as DISPLAY_VERSION
from crash_watch import CrashWatch
from trainer import Trainer,VERSION as TRAINER_VERSION
from hover_lifetime import HoverLifetimeFix
from render_sort import RenderSortFix
from quick_sell import QuickSellFix,inventory_snapshot
from grail import Grail,VERSION as GRAIL_VERSION
from premium_beam import PremiumBeam,VERSION as BEAM_VERSION
from gold_capacity import GoldCapacity,VERSION as GOLD_VERSION,original_bytes as gold_original_bytes
from loot_qol import LootQoL,VERSION as LOOT_QOL_VERSION
from homing_shots import HomingShots,VERSION as HOMING_VERSION
from ctrl_teleport import CtrlTeleport,VERSION as TELEPORT_VERSION
from mob_spawn import spawn as spawn_mob,selection as mob_selection,upgrade_existing,VERSION as MOB_SPAWN_VERSION
from experience import ExperienceEvent, character_info, VERSION as EXPERIENCE_VERSION
from map_travel import info as map_travel_info, selection as map_travel_selection, VERSION as MAP_TRAVEL_VERSION
from omega_beam import OmegaBeam,VERSION as OMEGA_VERSION
from ground_loot import GroundVisibility,SaleGoldLedger,GroundSaleError,sell_ground,VERSION as GROUND_VERSION
from operation_save import save_choice
from game_launch import GameLauncher

PORT=8770
INSTALLATION_ID=hashlib.sha256(str(ROOT.resolve()).casefold().encode('utf8')).hexdigest()[:24]
TOKEN=secrets.token_hex(32)
JOBS={}
JOBS_LOCK=threading.Lock()
DISPLAY=DisplayFix()
WATCH=CrashWatch()
TRAINER=Trainer()
STABILITY=HoverLifetimeFix(start_worker=False)
RENDER_PERFORMANCE=RenderSortFix()
GRAIL=Grail()
EVENT=DropEvent(verified_reader=GRAIL.original_bytes,grail_policy=GRAIL.policy)
GROUND=GroundVisibility()
SALE_GOLD=SaleGoldLedger()
PREMIUM_BEAM=PremiumBeam(grail_policy=GRAIL.policy,visibility_policy=GROUND.policy)
LOOT_QOL=LootQoL(gold_policy=SALE_GOLD.policy)
HOMING=HomingShots()
TELEPORT=CtrlTeleport()
OMEGA=OmegaBeam()
EXPERIENCE=ExperienceEvent()
GOLD=GoldCapacity()
QUICK_SELL=QuickSellFix(verified_reader=lambda game,a,n:gold_original_bytes(game,a,n,GRAIL.original_bytes))
LAUNCHER=GameLauncher()
RESTART=False
RESTART_DISPLAY=False
RESTART_QUICK_SELL=True
RESTART_PREMIUM_BEAM=True


def perform_ground_sale(job,binding,identifiers=None,save_before=False):
    try:
        with LOOT_QOL.pause_pickup():
            try:result=sell_ground(binding,SALE_GOLD,LOOT_QOL.refresh_gold_policy,identifiers=identifiers,verified_reader=GRAIL.original_bytes,save_before=save_before)
            except GroundSaleError as error:
                # Never let an incomplete sale result resume unattended gold
                # collection before the currency exclusion has been published.
                LOOT_QOL.set({'autoPickup':False})
                raise RuntimeError(str(error)+' Satış altını doğrulanamadığından otomatik toplama kapatıldı.') from error
        with JOBS_LOCK:JOBS[job]={'state':'success','result':result}
    except Exception as e:
        with JOBS_LOCK:JOBS[job]={'state':'error','message':str(e)}
        with (ROOT/'live-server-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)


def perform_level_rewind(job, target, binding):
    try:
        from level_rewind import rewind
        with TRAINER.lock, LOOT_QOL.pause_pickup():
            result=rewind(target,binding,TRAINER.info())
        with JOBS_LOCK:JOBS[job]={'state':'success','result':result}
    except Exception as e:
        with JOBS_LOCK:JOBS[job]={'state':'error','message':str(e)}
        with (ROOT/'live-server-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)


def perform_map_travel(job, sid, binding, save_before=False):
    try:
        from map_travel import travel
        with LOOT_QOL.pause_pickup():result=travel(sid,binding,save_before=save_before)
        with JOBS_LOCK:JOBS[job]={'state':'success','result':result}
    except Exception as e:
        with JOBS_LOCK:JOBS[job]={'state':'error','message':str(e)}
        with (ROOT/'live-server-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)

def perform_mob(job,mob,variant,quantity=1):
    try:
        with LOOT_QOL.pause_pickup():result=spawn_mob(mob,variant,quantity=quantity)
        with JOBS_LOCK:JOBS[job]={'state':'success','result':result}
    except Exception as e:
        with JOBS_LOCK:JOBS[job]={'state':'error','message':str(e)}
        with (ROOT/'live-server-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)


def perform_mob_cleanup(job,batch=None):
    try:
        from mob_cleanup import cleanup_last
        with LOOT_QOL.pause_pickup():result=cleanup_last(batch=batch)
        with JOBS_LOCK:JOBS[job]={'state':'success','result':result}
    except Exception as e:
        with JOBS_LOCK:JOBS[job]={'state':'error','message':str(e)}
        with (ROOT/'live-server-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)


def perform(job,key,quantity=1,maximum_roll=False):
    try:
        with LOOT_QOL.pause_pickup():result=drop_one(key,quantity=quantity,maximum_roll=maximum_roll)
        with JOBS_LOCK:JOBS[job]={'state':'success','result':result}
    except Exception as e:
        with JOBS_LOCK:JOBS[job]={'state':'error','message':str(e)}
        with (ROOT/'live-server-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(DIST),**kw)
    def log_message(self,*args):pass
    def local(self):return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def json(self,data,code=200):
        body=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.local():self.send_error(403);return
        path=urlsplit(self.path).path
        if path=='/api/live/state':self.json({'bridge':'ShadowFlare Atlas Live Drop 1','protocol':19,'installationId':INSTALLATION_ID,'helperPid':os.getpid(),**status(),'launcher':LAUNCHER.info(),'event':EVENT.info(),'display':DISPLAY.info(),'watch':WATCH.info(),'trainer':TRAINER.info(),'stability':STABILITY.info(),'renderPerformance':RENDER_PERFORMANCE.info(),'quickSell':QUICK_SELL.info(),'groundLoot':GROUND.info(),'grail':GRAIL.info(),'premiumBeam':PREMIUM_BEAM.info(),'magicBeam':PREMIUM_BEAM.magic_info(),'goldCapacity':GOLD.info(),'lootQoL':LOOT_QOL.info(),'homingShots':HOMING.info(),'ctrlTeleport':TELEPORT.info(),'omegaBeam':OMEGA.info(),'experience':EXPERIENCE.info(),'levelControl':character_info(),'mapTravel':map_travel_info(),'mobSpawn':{'version':MOB_SPAWN_VERSION,'noAI':True},'token':TOKEN});return
        if path.startswith('/api/live/job/'):
            if self.headers.get('X-Atlas-Token')!=TOKEN:self.json({'error':'Unauthorized'},403);return
            with JOBS_LOCK:result=JOBS.get(path.rsplit('/',1)[-1])
            self.json(result or {'state':'missing'},200 if result else 404);return
        if path.startswith('/api/'):self.json({'error':'Unknown endpoint'},404);return
        super().do_GET()
    def do_POST(self):
        global RESTART,RESTART_DISPLAY,RESTART_QUICK_SELL,RESTART_PREMIUM_BEAM
        if not self.local():self.send_error(403);return
        expected=(f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}')
        if self.headers.get('Origin') not in expected or self.headers.get('X-Atlas-Token')!=TOKEN:
            self.json({'error':'Unauthorized local request'},403);return
        try:
            n=int(self.headers.get('Content-Length','0'))
            limit=24*1024*1024 if self.path=='/api/trainer/import'else 32768
            if not 0<n<=limit:raise ValueError('Invalid body')
            body=json.loads(self.rfile.read(n))
            if not isinstance(body,dict):raise ValueError('Invalid request')
            if self.path=='/api/game/configure':self.json(LAUNCHER.configure(body));return
            if self.path=='/api/game/launch':self.json(LAUNCHER.launch(body,display=DISPLAY));return
            if self.path=='/api/trainer/table':self.json(TRAINER.table());return
            if self.path=='/api/trainer/import':
                content=body.get('content');filename=body.get('filename','local.ct')
                if not isinstance(content,str)or not isinstance(filename,str):raise ValueError('Geçersiz CT içeriği.')
                self.json(TRAINER.import_table(content.encode('utf8'),filename));return
            if self.path=='/api/trainer/remove':self.json(TRAINER.remove_table());return
            if self.path=='/api/trainer/read':self.json(TRAINER.read(body.get('ids')));return
            if self.path=='/api/trainer/write':self.json(TRAINER.write(body.get('id'),body.get('value'),body.get('binding'),body.get('freeze',False)));return
            if self.path=='/api/trainer/toggle':self.json(TRAINER.toggle(body.get('id'),body.get('enabled')));return
            if self.path=='/api/trainer/action':self.json(TRAINER.action(body.get('id')));return
            if self.path=='/api/trainer/unfreeze':self.json(TRAINER.unfreeze(body.get('id')));return
            if self.path=='/api/trainer/undo':self.json(TRAINER.revert());return
            if self.path=='/api/trainer/reset':self.json(TRAINER.reset());return
            if self.path=='/api/live/event':
                if not isinstance(body,dict):raise ValueError('Invalid event settings')
                self.json(EVENT.set(body.get('multiplier'),body.get('premiumOnly'),body.get('excludeFound')));return
            if self.path=='/api/live/loot-qol':self.json(LOOT_QOL.set(body));return
            if self.path=='/api/live/ground-visibility':self.json(GROUND.set(body.get('hidden')));return
            if self.path=='/api/live/ground-sale':
                from ground_loot import selected_ids
                save_before=save_choice(body.get('saveBefore',False))
                binding=body.get('binding')
                selected_ids(body.get('identifiers'))
                if not isinstance(binding,str) or len(binding)>80:raise ValueError('Karakter ve harita durumu yenilenmeli.')
                if not LOOT_QOL.info()['active']:raise ValueError('Otomatik toplama istisnası için ganimet yardımcısının bağlanmasını bekle.')
                with JOBS_LOCK:
                    if any(j['state']=='pending' for j in JOBS.values()):self.json({'message':'Önceki oyun işlemi sürüyor.'},409);return
                    job=secrets.token_hex(12);JOBS[job]={'state':'pending','started':time.time()}
                threading.Thread(target=perform_ground_sale,args=(job,binding,body.get('identifiers'),save_before),daemon=True).start()
                self.json({'job':job,'state':'pending'},202);return
            if self.path=='/api/live/experience':self.json(EXPERIENCE.set(body.get('multiplier')));return
            if self.path=='/api/live/map-travel':
                save_before=save_choice(body.get('saveBefore',False))
                sid=body.get('map');map_travel_selection(sid)
                current=map_travel_info()
                if not current.get('canTravel'):raise ValueError(current.get('message','Karakter yüklü değil.'))
                binding=body.get('binding')
                if binding!=current['binding']:raise ValueError('Karakter veya bulunduğun harita değişmiş. Durumu yenile.')
                with JOBS_LOCK:
                    if any(j['state']=='pending' for j in JOBS.values()):
                        self.json({'message':'Önceki oyun işlemi sürüyor.'},409);return
                    job=secrets.token_hex(12);JOBS[job]={'state':'pending','started':time.time()}
                threading.Thread(target=perform_map_travel,args=(job,sid,binding,save_before),daemon=True).start()
                self.json({'job':job,'state':'pending'},202);return
            if self.path=='/api/live/level-rewind':
                from level_rewind import target_level,validate_controls
                current=character_info()
                if not current.get('ready'):raise ValueError(current.get('message','Karakter yüklü değil.'))
                target=target_level(body.get('level'),current['level'])
                binding=body.get('binding')
                if binding!=current['binding']:raise ValueError('Karakter veya seviye değişmiş. Durumu yenile.')
                validate_controls(TRAINER.info())
                with JOBS_LOCK:
                    if any(j['state']=='pending' for j in JOBS.values()):
                        self.json({'message':'Önceki oyun işlemi sürüyor.'},409);return
                    job=secrets.token_hex(12);JOBS[job]={'state':'pending','started':time.time()}
                threading.Thread(target=perform_level_rewind,args=(job,target,binding),daemon=True).start()
                self.json({'job':job,'state':'pending'},202);return
            if self.path=='/api/live/save':
                from native_save import save_current
                self.json(save_current());return
            if self.path=='/api/live/homing-shots':self.json(HOMING.set(body.get('enabled')));return
            if self.path=='/api/live/ctrl-teleport':self.json(TELEPORT.set(body.get('enabled')));return
            if self.path in ('/api/live/omega-beam','/api/live/special-skill'):
                self.json(OMEGA.set(body.get('enabled'),body.get('skill'),body.get('surprise')));return
            if self.path=='/api/live/magic-beam':self.json(PREMIUM_BEAM.set_magic(body.get('enabled')));return
            if self.path=='/api/live/quick-sell':
                if body.get('enabled') is True:self.json(QUICK_SELL.enable())
                elif body.get('enabled') is False:self.json(QUICK_SELL.disable())
                else:raise ValueError('Invalid quick sale setting')
                return
            if self.path=='/api/live/premium-beam':
                if body.get('enabled') is True:self.json(PREMIUM_BEAM.enable())
                elif body.get('enabled') is False:self.json(PREMIUM_BEAM.disable())
                else:raise ValueError('Invalid Premium beam setting')
                return
            if self.path=='/api/live/grail':
                action=body.get('action','read')
                if action=='read':self.json(GRAIL.view(body.get('profile')))
                elif action=='mark':self.json(GRAIL.mark(body.get('profile'),body.get('key'),body.get('found')))
                else:raise ValueError('Geçersiz grail işlemi.')
                return
            if self.path=='/api/live/display':
                if body.get('enabled') is True:self.json(DISPLAY.enable())
                elif body.get('enabled') is False:DISPLAY.close();self.json(DISPLAY.info())
                else:raise ValueError('Invalid display settings')
                return
            if self.path=='/api/live/watch':
                if body.get('enabled') is True:self.json(WATCH.start())
                elif body.get('enabled') is False:WATCH.close();self.json(WATCH.info())
                else:raise ValueError('Invalid crash capture setting')
                return
            if self.path=='/api/live/diagnostic':
                if body.get('groundLoot') is True:
                    from ground_loot import binding
                    with LOOT_QOL.pause_pickup():self.json(sell_ground(binding(status()),SALE_GOLD,LOOT_QOL.refresh_gold_policy,identifiers=body.get('identifiers'),dry_run=True,verified_reader=GRAIL.original_bytes))
                    return
                if body.get('omegaBeam') is True:self.json(OMEGA.inspect());return
                if body.get('ctrlTeleport') is True:self.json(TELEPORT.inspect());return
                if body.get('rain') is True:self.json(DISPLAY.inspect_rain());return
                if body.get('homingShots') is True:
                    from homing_shots import snapshot
                    self.json(snapshot());return
                if body.get('premiumBeam') is True:self.json(PREMIUM_BEAM.snapshot());return
                if body.get('inventorySnapshot') is True:self.json(inventory_snapshot());return
                if body.get('framePacing') is True:
                    from performance_probe import sample_frame_pacing
                    self.json(sample_frame_pacing(body.get('seconds',10),lambda:STABILITY.info().get('framesRefreshed')));return
                if body.get('sortCache') is True:
                    self.json({'caches':RENDER_PERFORMANCE.inspect_cache()});return
                if body.get('profile') is True:
                    from performance_probe import sample_profile
                    self.json(sample_profile(body.get('seconds',5),lambda:STABILITY.info().get('framesRefreshed')));return
                from live_drop import Game
                game=Game()
                try:
                    if body.get('groundItems') is True:
                        game_state=game.state();items=[]
                        for pointer in game.ground_items(game_state['map']):
                            try:
                                ident=game.words(pointer+0x14)[0]
                                x,y=struct.unpack('<ii',game.read(pointer+0x48,8))
                                items.append(dict(pointer=pointer,id=ident,x=x,y=y))
                            except (OSError,RuntimeError):continue
                        extra={}
                        if body.get('terrain') is True:
                            from performance_probe import inspect_terrain
                            extra['terrain']=inspect_terrain(game,items)
                        self.json({**game_state,'items':items,'event':EVENT.info(),**extra});return
                    folder=ROOT/'display-diagnostics';folder.mkdir(exist_ok=True)
                    (folder/'runtime-text.bin').write_bytes(game.read(0x401000,0x71574))
                    (folder/'runtime-data.bin').write_bytes(game.read(0x47d000,0x129c8))
                    game_state=game.state();game_state['groundItems']=len(game.ground_items(game_state['map']))
                    player=game_state['player']
                    (folder/'runtime-player.bin').write_bytes(game.read(player,0x1680))
                    for name,offset,size in (('mouse',0x3fc,0x40),('input',0x3f8,0x180)):
                        pointer=game.words(player+offset)[0]
                        if pointer:(folder/f'runtime-{name}.bin').write_bytes(game.read(pointer,size))
                    (folder/'state.json').write_text(json.dumps(game_state,indent=2),'utf-8')
                    self.json(game_state)
                finally:game.close()
                return
            if self.path in ('/api/live/stop','/api/live/restart'):
                with JOBS_LOCK:
                    if any(j['state']=='pending' for j in JOBS.values()):self.json({'message':'Drop isteği bitmeden yardımcı kapanmaz.'},409);return
                RESTART=self.path.endswith('/restart')
                RESTART_DISPLAY=DISPLAY.requested
                RESTART_QUICK_SELL=QUICK_SELL.requested
                RESTART_PREMIUM_BEAM=PREMIUM_BEAM.requested
                self.json({'state':'stopping'});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            if self.path=='/api/live/mob-inspect':
                from mob_spawn import inspect
                self.json(inspect(body.get('detail') is True));return
            if self.path=='/api/live/mob-refresh':self.json(upgrade_existing());return
            if self.path=='/api/live/mob-cleanup':
                batch=body.get('batch')
                if batch is not None and (not isinstance(batch,str) or len(batch)>500):raise ValueError('Geçersiz doğurma grubu.')
                with JOBS_LOCK:
                    if any(j['state']=='pending' for j in JOBS.values()):
                        self.json({'message':'Önceki oyun işlemi sürüyor.'},409);return
                    job=secrets.token_hex(12);JOBS[job]={'state':'pending','started':time.time()}
                threading.Thread(target=perform_mob_cleanup,args=(job,batch),daemon=True).start()
                self.json({'job':job,'state':'pending'},202);return
            if self.path=='/api/live/mob-spawn':
                mob,variant=body.get('mob'),body.get('variant',0)
                mob_selection(catalogue(),mob,variant)
                from mob_spawn import spawn_quantity as mob_quantity
                quantity=mob_quantity(body.get('quantity',1))
                with JOBS_LOCK:
                    if any(j['state']=='pending' for j in JOBS.values()):
                        self.json({'message':'Another game request is pending.'},409);return
                    job=secrets.token_hex(12);JOBS[job]={'state':'pending','mob':mob,'variant':variant,'started':time.time()}
                threading.Thread(target=perform_mob,args=(job,mob,variant,quantity),daemon=True).start()
                self.json({'job':job,'state':'pending'},202);return
            if self.path!='/api/live/drop':self.json({'error':'Unknown endpoint'},404);return
            key=body.get('key')
            if not isinstance(key,str) or len(key)>30:raise ValueError('Invalid item key')
            quantity=body.get('quantity',1)
            from live_drop import spawn_quantity
            spawn_quantity(int(key.split(':')[0]),quantity)
            maximum_roll=body.get('maximumRoll',False)
            from live_drop import maximum_roll_fields
            maximum_roll_fields(*map(int,key.split(':')),maximum_roll)
            if quantity>1 and not LOOT_QOL.info()['active']:raise ValueError('Yığın oluşturmak için güncel ganimet yardımcısı oyuna bağlı olmalı.')
            with JOBS_LOCK:
                if any(j['state']=='pending' for j in JOBS.values()):self.json({'message':'Önceki drop isteği sürüyor.'},409);return
                job=secrets.token_hex(12);JOBS[job]={'state':'pending','key':key,'started':time.time()}
            threading.Thread(target=perform,args=(job,key,quantity,maximum_roll),daemon=True).start()
            self.json({'job':job,'state':'pending'},202)
        except Exception as e:self.json({'message':str(e)},400)

def launch_body(args):
    body={}
    if args.width is not None:body['width']=args.width
    if args.height is not None:body['height']=args.height
    if args.game is not None:body['gamePath']=args.game
    return body


def launch_arguments(args):
    result=['--launch-game'] if args.launch_game else []
    for flag,value in (('--width',args.width),('--height',args.height),('--game',args.game)):
        if value is not None:result.extend((flag,str(value)))
    return result


def select_existing_helper(existing,url,timeout=10):
    """Do not reuse or self-restart a helper belonging to another checkout."""
    if existing.get('bridge')!='ShadowFlare Atlas Live Drop 1':return existing
    if existing.get('protocol',0)>=19 and existing.get('installationId')==INSTALLATION_ID:return existing
    request=Request(url+'api/live/stop',data=b'{}',headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
    with urlopen(request,timeout=5)as response:json.load(response)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        time.sleep(.2)
        try:
            with urlopen(url+'api/live/state',timeout=1)as response:current=json.load(response)
        except OSError:return {}
        if current.get('helperPid')!=existing.get('helperPid'):raise RuntimeError('Başka bir Atlas yardımcısı başlatıldı; yeniden dene.')
    raise RuntimeError('Önceki Atlas yardımcısının kapanması tamamlanamadı. Oyun kapatılmadı.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--elevate',action='store_true');p.add_argument('--no-browser',action='store_true');p.add_argument('--display-fix',action='store_true');p.add_argument('--no-quick-sell',action='store_true');p.add_argument('--no-premium-beam',action='store_true');p.add_argument('--launch-game',action='store_true');p.add_argument('--width',type=int);p.add_argument('--height',type=int);p.add_argument('--game');args=p.parse_args()
    # Reopening the launcher reuses our existing helper without another UAC prompt.
    url=f'http://127.0.0.1:{PORT}/'
    try:
        with urlopen(url+'api/live/state',timeout=2) as response:existing=json.load(response)
    except Exception:existing={}
    existing=select_existing_helper(existing,url)
    if existing.get('bridge')=='ShadowFlare Atlas Live Drop 1':
        previous_experience=1
        if existing.get('protocol',0)>=3:
            if existing.get('protocol',0)<19 or existing.get('trainer',{}).get('version',0)<TRAINER_VERSION or existing.get('groundLoot',{}).get('version',0)<GROUND_VERSION or existing.get('omegaBeam',{}).get('version',0)<OMEGA_VERSION or existing.get('mapTravel',{}).get('version',0)<MAP_TRAVEL_VERSION or existing.get('experience',{}).get('version',0)<EXPERIENCE_VERSION or existing.get('mobSpawn',{}).get('version',0)<MOB_SPAWN_VERSION or existing.get('premiumBeam',{}).get('version',0)<BEAM_VERSION or existing.get('goldCapacity',{}).get('version',0)<GOLD_VERSION or existing.get('homingShots',{}).get('version',0)<HOMING_VERSION or existing.get('ctrlTeleport',{}).get('version',0)<TELEPORT_VERSION or existing.get('lootQoL',{}).get('version',0)<LOOT_QOL_VERSION or existing.get('event',{}).get('version',0)<EVENT_VERSION or existing.get('renderPerformance',{}).get('version',0)<11 or existing.get('quickSell',{}).get('version',0)<1 or existing.get('grail',{}).get('version',0)<GRAIL_VERSION or (args.display_fix and existing.get('display',{}).get('version',0)<DISPLAY_VERSION):
                previous_experience=existing.get('experience',{}).get('multiplier',1)
                previous_factor=existing.get('event',{}).get('multiplier',1) if existing.get('event',{}).get('active') else 1
                previous_premium_only=existing.get('event',{}).get('premiumOnly',False)
                previous_exclude_found=existing.get('event',{}).get('excludeFound',False)
                request=Request(url+'api/live/restart',data=b'{}',headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
                with urlopen(request,timeout=5) as response:json.load(response)
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    time.sleep(.2)
                    try:
                        with urlopen(url+'api/live/state',timeout=2) as response:updated=json.load(response)
                        if updated.get('helperPid')!=existing.get('helperPid') and updated.get('protocol',0)>=19 and updated.get('trainer',{}).get('version',0)>=TRAINER_VERSION and updated.get('groundLoot',{}).get('version',0)>=GROUND_VERSION and updated.get('omegaBeam',{}).get('version',0)>=OMEGA_VERSION and updated.get('mapTravel',{}).get('version',0)>=MAP_TRAVEL_VERSION and updated.get('experience',{}).get('version',0)>=EXPERIENCE_VERSION and updated.get('mobSpawn',{}).get('version',0)>=MOB_SPAWN_VERSION and updated.get('premiumBeam',{}).get('version',0)>=BEAM_VERSION and updated.get('goldCapacity',{}).get('version',0)>=GOLD_VERSION and updated.get('homingShots',{}).get('version',0)>=HOMING_VERSION and updated.get('ctrlTeleport',{}).get('version',0)>=TELEPORT_VERSION and updated.get('lootQoL',{}).get('version',0)>=LOOT_QOL_VERSION and updated.get('event',{}).get('version',0)>=EVENT_VERSION and updated.get('renderPerformance',{}).get('version',0)>=11 and updated.get('quickSell',{}).get('version',0)>=1 and updated.get('grail',{}).get('version',0)>=GRAIL_VERSION and updated.get('display',{}).get('version',0)>=DISPLAY_VERSION:
                            existing=updated;break
                    except OSError:continue
                else:raise RuntimeError('Arayüz yardımcısı güncellenemedi; ARAYUZ-DUZELT.cmd dosyasını güncel Atlas klasöründen aç.')
                if previous_factor>1 or previous_exclude_found:
                    request=Request(url+'api/live/event',data=json.dumps({'multiplier':previous_factor,'premiumOnly':previous_premium_only,'excludeFound':previous_exclude_found}).encode(),headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
                    with urlopen(request,timeout=10) as response:json.load(response)
            if previous_experience>1:
                request=Request(url+'api/live/experience',data=json.dumps({'multiplier':previous_experience}).encode(),headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
                with urlopen(request,timeout=10) as response:json.load(response)
            if args.display_fix:
                request=Request(url+'api/live/display',data=b'{"enabled":true}',headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
                with urlopen(request,timeout=5) as response:json.load(response)
            if args.no_quick_sell:
                request=Request(url+'api/live/quick-sell',data=b'{"enabled":false}',headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
                with urlopen(request,timeout=12) as response:json.load(response)
            if args.no_premium_beam:
                request=Request(url+'api/live/premium-beam',data=b'{"enabled":false}',headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
                with urlopen(request,timeout=12) as response:json.load(response)
            if args.launch_game:
                endpoint='api/game/configure' if existing.get('launcher',{}).get('running') else 'api/game/launch'
                request=Request(url+endpoint,data=json.dumps(launch_body(args)).encode(),headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
                with urlopen(request,timeout=20) as response:json.load(response)
            if not args.no_browser:webbrowser.open(url)
            print('Atlas yardımcısı zaten açık: '+url);return
        # Upgrade our previous one-item helper through its authenticated stop API.
        request=Request(url+'api/live/stop',data=b'{}',headers={'Origin':url.rstrip('/'),'Content-Type':'application/json','X-Atlas-Token':existing['token']},method='POST')
        with urlopen(request,timeout=3) as response:json.load(response)
        time.sleep(.6)
    if args.elevate and not ctypes.windll.shell32.IsUserAnAdmin():
        executable=str(Path(sys.executable).with_name('pythonw.exe'))
        parameters=subprocess.list2cmdline([str(Path(__file__).resolve()),*(['--no-browser'] if args.no_browser else []),*(['--display-fix'] if args.display_fix else []),*(['--no-quick-sell'] if args.no_quick_sell else []),*(['--no-premium-beam'] if args.no_premium_beam else []),*launch_arguments(args)])
        shell=ctypes.WinDLL('shell32',use_last_error=True)
        shell.ShellExecuteW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
        shell.ShellExecuteW.restype=ctypes.c_void_p
        result=shell.ShellExecuteW(None,'runas',executable,parameters,str(ROOT),0)
        if not result or result<=32:raise RuntimeError('Yönetici onayı verilmedi; oyun belleğine dokunulmadı.')
        print('Windows yönetici onayı istendi. Yardımcı onaydan sonra localhost:8770 üzerinde açılır.');return
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    upgrade_existing()
    GOLD.start()
    GROUND.start()
    PREMIUM_BEAM.start()
    STABILITY.enable()
    RENDER_PERFORMANCE.enable()
    if not args.no_quick_sell:QUICK_SELL.enable()
    GRAIL.start()
    LOOT_QOL.start()
    HOMING.start()
    TELEPORT.start()
    OMEGA.start()
    EXPERIENCE.start()
    if not args.no_premium_beam:PREMIUM_BEAM.enable()
    if args.display_fix:
        try:DISPLAY.enable()
        except Exception as error:DISPLAY.message=str(error)
    if args.launch_game:
        if LAUNCHER.info()['running']:LAUNCHER.configure(launch_body(args))
        else:LAUNCHER.launch(launch_body(args),display=DISPLAY)
    print(f'Atlas Live Drop: http://127.0.0.1:{PORT}/',flush=True)
    if not args.no_browser:
        chosen=next(i['id'] for i in catalogue()['items'] if i['key']=='0:80000127')
        webbrowser.open(f'http://127.0.0.1:{PORT}/#item={chosen}')
    try:server.serve_forever()
    finally:WATCH.close();OMEGA.close();EXPERIENCE.close();TELEPORT.close();EVENT.close();GOLD.close();HOMING.close();LOOT_QOL.close();PREMIUM_BEAM.close();GROUND.close();GRAIL.close();QUICK_SELL.close();TRAINER.close();DISPLAY.shutdown();STABILITY.close();RENDER_PERFORMANCE.close();server.server_close()
    if RESTART:os.execv(sys.executable,[sys.executable,str(Path(__file__).resolve()),'--no-browser',*(['--display-fix'] if RESTART_DISPLAY else []),*(['--no-quick-sell'] if not RESTART_QUICK_SELL else []),*(['--no-premium-beam'] if not RESTART_PREMIUM_BEAM else [])])

if __name__=='__main__':
    try:main()
    except Exception:
        with (ROOT/'live-server-errors.log').open('a',encoding='utf-8') as f:traceback.print_exc(file=f)
        raise
