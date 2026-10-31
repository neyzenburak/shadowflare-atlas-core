"""Target-bound falling effects with one native hit per cast and entity."""
import json
import math
import struct
import time

from live_drop import ROOT
from omega_path import project
from special_effects import SPECS,visual_groups

FALL_SECONDS=.85
GROUND_SECONDS=3.0
EFFECT_INDEX={};index=24
for name,spec in SPECS.items():EFFECT_INDEX[name]=index;index+=spec[4]
SPRITE_COUNT=index


def visible_targets(game,map_pointer):
    screen=game.words(0x482d1c)[0];projection=game.words(0x482d14)[0]
    scale=game.words(projection+0x18,2)
    left,top,right,bottom=struct.unpack('<4i',game.read(screen+0x10,16))
    scroll=struct.unpack('<2i',game.read(screen+0x40,8))
    if not all(0<n<=1000 for n in scale) or not (left<right and top<bottom):raise RuntimeError('Görüş alanı doğrulanamadı.')
    manager=game.words(map_pointer+0x30)[0];count,array=game.words(manager,2)
    if count>100000:raise RuntimeError('Yaratık listesi doğrulanamadı.')
    seen=set();targets=[]
    for block in game.words(array,count) if count else ():
        kind,_,pointer=game.words(block,3)
        if kind!=2 or not pointer:continue
        raw=game.read(pointer,0xd8)
        ident=struct.unpack_from('<i',raw,4)[0];hp=struct.unpack_from('<i',raw,0xd4)[0]
        if hp<=0 or ident<0 or struct.unpack_from('<I',raw,0x5c)[0]!=map_pointer:continue
        key=(ident,pointer)
        if key in seen:continue
        xy=struct.unpack_from('<2i',raw,0x18);x,y=project(xy,scale);x-=scroll[0];y-=scroll[1]
        # Include a body crossing the viewport edge, not far-away hidden mobs.
        if x+24<left or x-24>right or y+8<top or y-90>bottom:continue
        seen.add(key);targets.append(dict(id=ident,pointer=pointer,xy=xy,alive=True))
    return targets,scale,(left,top,right,bottom)


def unique_targets(targets):
    result=[];seen=set()
    for target in targets:
        key=(target['id'],target['pointer'])
        if key not in seen:seen.add(key);result.append(target)
    return result


class MeteorSkill:
    def _begin_meteor(self,words):
        player,map_pointer=words[6:8]
        state=self.game.state()
        if state['player']!=player or state['map']!=map_pointer:raise RuntimeError('Yetenek başlamadan karakter veya harita değişti.')
        targets,scale,viewport=visible_targets(self.game,map_pointer)
        now=time.monotonic();surprise=bool(words[42])
        self.flight=dict(kind='meteor',player=player,map=map_pointer,damage=words[14],targets=targets,
                         scale=scale,viewport=viewport,surprise=surprise,started=now,impact=None,hit=False)
        self.last=dict(skill='meteor',surprise=surprise,damage=words[14],targets=len(targets),hitCount=0,
                       viewport=list(viewport),fallSeconds=FALL_SECONDS,groundSeconds=GROUND_SECONDS)
        if not targets:
            self.flight=None;self.game.write(self.base+0x2000+120,b'\0'*4);self._publish([])
            self.message='Görüş alanında yaşayan yaratık yok.'
        else:self.message=f"{'Nükleer başlıklar' if surprise else 'Meteorlar'} {len(targets)} hedefi izliyor."

    def _refresh_meteor_targets(self,f):
        for target in f['targets']:
            if not target['alive']:continue
            try:
                raw=self.game.read(target['pointer'],0xd8)
                target['alive']=(struct.unpack_from('<i',raw,4)[0]==target['id'] and
                    struct.unpack_from('<I',raw,0x5c)[0]==f['map'] and struct.unpack_from('<i',raw,0xd4)[0]>0)
                if target['alive']:target['xy']=struct.unpack_from('<2i',raw,0x18)
            except (OSError,RuntimeError):target['alive']=False

    def _meteor_hits(self,f):
        results=[];targets=unique_targets([t for t in f['targets'] if t['alive']])
        for at in range(0,len(targets),64):
            batch=targets[at:at+64]
            raw=b''.join(struct.pack('<8I',t['id'],t['pointer'],0,0,0,0,0,0) for t in batch)
            self.game.write(self.base+0x2800,raw)
            self.game.write(self.base+0x2000+176,struct.pack('<I',len(batch)))
            if self._command(3)!=3:break
            completed=self.game.read(self.base+0x2800,len(batch)*32)
            for i,target in enumerate(batch):
                ident,pointer,x,y,before,after,status,_=struct.unpack_from('<8I',completed,i*32)
                signed=lambda n:n if n<0x80000000 else n-0x100000000
                if status==1:target['xy']=(signed(x),signed(y));target['impactXY']=target['xy']
                results.append(dict(id=ident,pointer=pointer,hit=status==1,before=before,after=after,
                                    damage=before-after if status==1 else 0))
        self.last.update(hitCount=sum(r['hit'] for r in results),results=results)
        folder=ROOT/'omega-sessions';folder.mkdir(exist_ok=True)
        (folder/f'{self.game.pid}-{time.time_ns()}-meteor.json').write_text(json.dumps(self.last,indent=2),'utf8')

    def _meteor_records(self,f,now):
        records=[]
        if f['impact'] is None:
            phase=max(0,min(1,(now-f['started'])/FALL_SECONDS));kind='missile' if f['surprise'] else 'meteor'
            # Each original target keeps its own following projectile.
            for target in visual_groups([t for t in f['targets'] if t['alive']],f['scale'],cell=12):
                x,y=target['xy'];drop=1-phase
                records.append((x,y,round(-100*drop),round(-480*drop-27),EFFECT_INDEX[kind]+int(phase*7)%8,0))
        else:
            age=now-f['impact']
            # Merge coincident areas visually; damage was already applied once
            # to each unique ID. Flames/clouds never call the damage function.
            anchors=[dict(t,xy=t.get('impactXY',t['xy'])) for t in f['targets'] if 'impactXY' in t]
            cell=58 if f['surprise'] else 28
            for target in visual_groups(anchors,f['scale'],cell=cell):
                x,y=target['xy']
                if age<.45:
                    kind='nuke' if f['surprise'] else 'blast'
                    records.append((x,y,0,-20,EFFECT_INDEX[kind]+min(7,int(age/.45*8)),0))
                if age<GROUND_SECONDS:
                    kind='mushroom' if f['surprise'] else 'fire'
                    frame=min(11,int(age/GROUND_SECONDS*12)) if f['surprise'] else int(age*12)%8
                    records.append((x,y,0,0,EFFECT_INDEX[kind]+frame,0))
        return records

    def _draw_meteor(self,now):
        self._publish(self._meteor_records(self.flight,now))

    def _tick_meteor(self,now):
        f=self.flight;state=self.game.state()
        if state['map']!=f['map'] or state['player']!=f['player'] or self.game.words(f['player']+0x2c)[0]!=6:
            self.flight=None;self.game.write(self.base+0x2000+120,b'\0'*4);self._publish([]);return
        if f['impact'] is None:
            self._refresh_meteor_targets(f)
            if now-f['started']>=FALL_SECONDS:
                self._meteor_hits(f);f['impact']=time.monotonic()
                self.message=f"{'Sürpriz mod' if f['surprise'] else 'Meteor yağmuru'} · {self.last['hitCount']} hedef · Attack ×3."
                # Damage is complete. Ground effects own their remaining
                # lifetime independently; they must not keep the input busy.
                self.aftermaths.append(f)
                self.flight=None
                self.game.write(self.base+0x2000+120,b'\0'*4)
                self._publish([]);return
        self._draw_meteor(time.monotonic())
