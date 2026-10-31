(function(root){
  'use strict';
  const clamp=(n,lo,hi)=>Math.max(lo,Math.min(hi,n));
  function nativeObjectOrder(objects){
    const source=[...objects].sort((a,b)=>a[8]-b[8]),n=source.length;
    if(!n||source.some(o=>o.length<9))return objects;
    const nearX=[],nearY=[],farX=[],farY=[],groups=[];
    source.forEach((o,i)=>{const r=o[7];nearX[i]=o[5]+r[0];nearY[i]=o[6]+r[1];farX[i]=o[5]+r[2];farY[i]=o[6]+r[3];groups[i]=o[4]&0x20?3:o[4]&0x80?2:o[4]&0x100?1:0;});
    const edges=Array.from({length:n},()=>[]),incoming=new Int32Array(n),remaining=new Uint8Array(n).fill(1),result=[];
    for(let i=0;i<n;i++)for(let j=0;j<n;j++)if(i!==j&&(groups[i]>groups[j]||(groups[i]===groups[j]&&farX[j]>nearX[i]&&farY[j]>nearY[i]&&(farX[j]>farX[i]||farY[j]>farY[i])))){edges[i].push(j);incoming[j]++;}
    for(let step=0;step<n;step++){let chosen=-1,first=-1;for(let i=0;i<n;i++)if(remaining[i]){if(first<0)first=i;if(incoming[i]===0){chosen=i;break;}}if(chosen<0)chosen=first;remaining[chosen]=0;result.push(source[chosen]);for(const next of edges[chosen])incoming[next]--;}
    return result;
  }
  const scripts=new Map(),sceneRegistry=()=>root.SF_MAP_SCENES||(root.SF_MAP_SCENES={});
  function sceneFor(asset){return sceneRegistry()[asset.name]||sceneRegistry()[asset.name.toLowerCase()]||sceneRegistry()[asset.key];}
  function loadScene(asset){
    if(sceneFor(asset))return Promise.resolve(sceneFor(asset));
    if(!scripts.has(asset.scene))scripts.set(asset.scene,new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src=asset.scene;
      script.onload=()=>sceneFor(asset)?resolve(sceneFor(asset)):reject(new Error('Harita verisi bulunamadı.'));
      script.onerror=()=>{scripts.delete(asset.scene);script.remove();reject(new Error('Harita dosyası açılamadı.'));};document.head.append(script);
    }));
    return scripts.get(asset.scene);
  }
  function loadImage(src){return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Harita görseli açılamadı.'));img.src=src;});}
  class AtlasMapViewer {
    constructor({viewport,canvas,patterns,onSelect,onHover,onView}){
      this.viewport=viewport;this.canvas=canvas;this.ctx=canvas.getContext('2d',{alpha:false});this.patterns=patterns;
      this.onSelect=onSelect;this.onHover=onHover;this.onView=onView;this.scene=null;this.overview=null;this.asset=null;
      this.spawns=[];this.markers=[];this.markerFocus=null;this.highlight=null;this.showMobs=true;this.edgePan=true;this.cx=0;this.cy=0;this.zoom=1;this.fitZoom=1;
      this.images=new Map();this.queue=[];this.loading=0;this.epoch=0;this.width=0;this.height=0;this.dirty=true;this.raf=0;
      this.pointer=null;this.pointers=new Map();this.drag=null;this.pinch=null;this.lastTime=0;this.hover=null;
      this.detailState=document.createElement('span');this.detailState.className='map-detail-loading';viewport.append(this.detailState);
      new ResizeObserver(()=>this.resize()).observe(viewport);
      viewport.addEventListener('wheel',event=>{if(!this.scene)return;event.preventDefault();const p=this.local(event);this.zoomAt(Math.exp(-clamp(event.deltaY,-150,150)*.004),p.x,p.y);},{passive:false});
      viewport.addEventListener('pointerdown',event=>this.down(event));viewport.addEventListener('pointermove',event=>this.move(event));
      for(const name of ['pointerup','pointercancel'])viewport.addEventListener(name,event=>this.up(event,name==='pointercancel'));
      viewport.addEventListener('pointerleave',()=>{if(!this.drag){this.pointer=null;this.setHover(null);}});
      viewport.addEventListener('keydown',event=>this.key(event));
      document.addEventListener('visibilitychange',()=>{this.lastTime=0;if(!document.hidden)this.request();});
    }
    local(event){const r=this.viewport.getBoundingClientRect();return {x:event.clientX-r.left,y:event.clientY-r.top};}
    bounds(){return this.scene?.bounds||this.asset?.bounds||[0,0,this.scene?.width||1,this.scene?.height||1];}
    resize(){
      const r=this.viewport.getBoundingClientRect();if(!r.width||!r.height)return;
      const wasFit=Math.abs(this.zoom-this.fitZoom)<.0001;this.width=r.width;this.height=r.height;
      const dpr=Math.min(devicePixelRatio||1,2);this.canvas.width=Math.round(r.width*dpr);this.canvas.height=Math.round(r.height*dpr);this.dpr=dpr;
      const [x0,y0,x1,y1]=this.bounds();this.fitZoom=Math.min(r.width/(x1-x0),r.height/(y1-y0))*.97;
      if(wasFit&&this.scene)this.fit();else this.constrain();this.request();
    }
    async setMap(asset,spawns=[]){
      const epoch=++this.epoch;this.scene=null;this.overview=null;this.asset=asset;this.spawns=spawns;this.markers=[];this.markerFocus=null;this.highlight=null;this.setHover(null);
      for(const entry of this.queue)if(!entry.img)this.images.delete(entry.key);
      this.queue=[];this.detailState.textContent='';this.request();
      const [scene,overview]=await Promise.all([loadScene(asset),loadImage(asset.overview.src||asset.overview)]);
      if(epoch!==this.epoch)return false;
      this.scene=scene;this.overview=overview;this.resize();this.fit();return true;
    }
    fit(){const [x0,y0,x1,y1]=this.bounds();this.fitZoom=Math.min(this.width/(x1-x0),this.height/(y1-y0))*.97;this.zoom=this.fitZoom;this.cx=(x0+x1)/2;this.cy=(y0+y1)/2;this.request();}
    constrain(){const [x0,y0,x1,y1]=this.bounds(),hw=this.width/this.zoom/2,hh=this.height/this.zoom/2;this.cx=x1-x0<=hw*2?(x0+x1)/2:clamp(this.cx,x0+hw,x1-hw);this.cy=y1-y0<=hh*2?(y0+y1)/2:clamp(this.cy,y0+hh,y1-hh);}
    zoomAt(factor,x=this.width/2,y=this.height/2){
      const wx=this.cx+(x-this.width/2)/this.zoom,wy=this.cy+(y-this.height/2)/this.zoom;
      this.zoom=clamp(this.zoom*factor,this.fitZoom,Math.max(4,this.fitZoom*8));this.cx=wx-(x-this.width/2)/this.zoom;this.cy=wy-(y-this.height/2)/this.zoom;this.constrain();this.request();
    }
    pan(dx,dy){this.cx+=dx/this.zoom;this.cy+=dy/this.zoom;this.constrain();this.request();}
    focus(mob,variant=null){
      this.highlight=mob===null?null:{mob,variant};
      const positions=this.spawns.filter(p=>p[2]===mob&&(variant===null||p[3]===variant));
      if(positions.length){const xs=positions.map(p=>p[0]),ys=positions.map(p=>p[1]);this.cx=(Math.min(...xs)+Math.max(...xs))/2;this.cy=(Math.min(...ys)+Math.max(...ys))/2;this.zoom=Math.max(this.zoom,this.fitZoom*1.8);this.constrain();}
      this.showMobs=true;this.request();
    }
    world(x,y){return {x:this.cx+(x-this.width/2)/this.zoom,y:this.cy+(y-this.height/2)/this.zoom};}
    setMarkers(markers=[]){this.markers=markers;this.markerFocus=null;this.request();}
    focusMarker(id){
      const marker=this.markers.find(p=>p.id===id);if(!marker)return false;
      this.markerFocus=id;this.cx=marker.x;this.cy=marker.y;this.zoom=Math.max(this.zoom,this.fitZoom*3);this.constrain();this.request();return true;
    }
    nearestMarker(point){
      if(!this.scene)return null;let found=null,best=225;
      for(const marker of this.markers||[]){const at=this.screen(marker.x,marker.y),d=(at.x-point.x)**2+(at.y-point.y)**2;if(d<best){best=d;found=marker;}}
      return found;
    }
    screen(x,y){return {x:(x-this.cx)*this.zoom+this.width/2,y:(y-this.cy)*this.zoom+this.height/2};}
    nearest(point){if(!this.showMobs||!this.scene)return null;const w=this.world(point.x,point.y);let found=null,best=144;for(const p of this.spawns){const d=((p[0]-w.x)**2+(p[1]-w.y)**2)*this.zoom**2;if(d<best){best=d;found=p;}}return found;}
    setHover(spawn){if(spawn===this.hover)return;this.hover=spawn;this.onHover?.(spawn,this.pointer);this.request();}
    down(event){
      if(event.button!==0)return;const p=this.local(event);this.pointers.set(event.pointerId,p);this.pointer=p;
      this.viewport.setPointerCapture(event.pointerId);this.viewport.focus({preventScroll:true});
      this.drag={id:event.pointerId,x:p.x,y:p.y,startX:p.x,startY:p.y,moved:false};this.viewport.classList.add('is-dragging');this.setHover(null);
      if(this.pointers.size===2){const [a,b]=[...this.pointers.values()];this.pinch={distance:Math.hypot(a.x-b.x,a.y-b.y)};this.drag.moved=true;}
    }
    move(event){
      const p=this.local(event);this.pointer=p;if(this.pointers.has(event.pointerId))this.pointers.set(event.pointerId,p);
      if(this.pointers.size===2&&this.pinch){const [a,b]=[...this.pointers.values()],distance=Math.hypot(a.x-b.x,a.y-b.y);this.zoomAt(distance/Math.max(1,this.pinch.distance),(a.x+b.x)/2,(a.y+b.y)/2);this.pinch.distance=distance;return;}
      if(this.drag&&this.drag.id===event.pointerId){const d=this.drag;this.pan(d.x-p.x,d.y-p.y);d.x=p.x;d.y=p.y;d.moved=d.moved||Math.hypot(p.x-d.startX,p.y-d.startY)>5;}
      else this.setHover(this.nearest(p));this.request();
    }
    up(event,cancel){
      const drag=this.drag;this.pointers.delete(event.pointerId);if(this.pointers.size<2)this.pinch=null;
      if(drag?.id===event.pointerId){if(!cancel&&!drag.moved){const point=this.local(event),marker=this.nearestMarker(point);if(marker){this.focusMarker(marker.id);this.onMarkerSelect?.(marker);}else{const spawn=this.nearest(point);if(spawn)this.onSelect?.(spawn);}}this.drag=null;this.viewport.classList.remove('is-dragging');}
      if(this.pointers.size===1){const [id,p]=[...this.pointers.entries()][0];this.drag={id,x:p.x,y:p.y,startX:p.x,startY:p.y,moved:true};this.viewport.classList.add('is-dragging');}
      if(this.viewport.hasPointerCapture(event.pointerId))this.viewport.releasePointerCapture(event.pointerId);
      if(event.pointerType==='touch')this.pointer=null;this.request();
    }
    key(event){
      const moves={ArrowLeft:[-70,0],ArrowRight:[70,0],ArrowUp:[0,-70],ArrowDown:[0,70]};
      if(moves[event.key]){event.preventDefault();this.pan(...moves[event.key]);}
      else if(['+','=','-','0','Home'].includes(event.key)){event.preventDefault();if(event.key==='0'||event.key==='Home')this.fit();else this.zoomAt(event.key==='-'?1/1.4:1.4);}
    }
    request(){this.dirty=true;if(!this.raf)this.raf=requestAnimationFrame(time=>this.frame(time));}
    frame(time){
      this.raf=0;if(!this.viewport.getBoundingClientRect().width||document.hidden){this.lastTime=0;return;}
      const dt=this.lastTime?Math.min(time-this.lastTime,40):16;this.lastTime=time;let edge=false;
      if(this.scene&&this.edgePan&&this.pointer&&!this.drag&&this.zoom>this.fitZoom*1.02){
        const p=this.pointer,margin=36;const velocity=(n,size)=>n<margin?-(margin-n)/margin:n>size-margin?(n-size+margin)/margin:0;
        const dx=velocity(p.x,this.width),dy=velocity(p.y,this.height);if(dx||dy){this.pan(dx*dt*.42,dy*dt*.42);edge=true;}
      }
      if(this.dirty){this.draw();this.dirty=false;}
      if(edge&&!this.raf)this.raf=requestAnimationFrame(t=>this.frame(t));
    }
    image(key){
      let entry=this.images.get(key);if(entry){entry.used=performance.now();return entry;}
      const pattern=this.patterns[key];if(!pattern)return {error:true};
      entry={ready:false,error:false,used:performance.now(),key,pattern};this.images.set(key,entry);this.queue.push(entry);this.pump();return entry;
    }
    pump(){while(this.loading<10&&this.queue.length){const entry=this.queue.shift();this.loading++;const img=new Image();entry.img=img;
      img.onload=()=>{entry.ready=true;this.loading--;this.prune();this.pump();this.request();};
      img.onerror=()=>{entry.error=true;this.loading--;this.pump();this.request();};img.src=entry.pattern.src;
    }}
    prune(){if(this.images.size<1200)return;const oldest=[...this.images.values()].filter(e=>e.ready&&performance.now()-e.used>15000).sort((a,b)=>a.used-b.used);for(const entry of oldest.slice(0,Math.max(0,this.images.size-1000)))this.images.delete(entry.key);}
    visible(){
      const scene=this.scene,tl=this.world(0,0),br=this.world(this.width,this.height),draws=[];
      const x0=Math.max(0,Math.floor(tl.x/scene.tileWidth)-1),x1=Math.min(scene.cols-1,Math.ceil(br.x/scene.tileWidth)+1),y0=Math.max(0,Math.floor(tl.y/scene.tileHeight)-1),y1=Math.min(scene.rows-1,Math.ceil(br.y/scene.tileHeight)+1);
      for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){const key=scene.ground[y*scene.cols+x];if(key)draws.push([x*scene.tileWidth,y*scene.tileHeight,key,1000,0]);}
      const visible=layer=>layer.filter(obj=>{const p=this.patterns[obj[2]];return p&&obj[0]+p.x+p.w>=tl.x&&obj[0]+p.x<=br.x&&obj[1]+p.y+p.h>=tl.y&&obj[1]+p.y<=br.y;});
      draws.push(...visible(scene.shadows||[]));
      const objects=visible(scene.objects),key=scene.name+':'+objects.map(o=>o[8]).join(',');
      if(key!==this.objectOrderKey){this.objectOrderKey=key;this.objectOrder=nativeObjectOrder(objects);}
      draws.push(...this.objectOrder);
      return draws;
    }
    draw(){
      const ctx=this.ctx;ctx.setTransform(this.dpr||1,0,0,this.dpr||1,0,0);ctx.fillStyle='#030503';ctx.fillRect(0,0,this.width,this.height);
      if(!this.scene||!this.overview)return;
      const bounds=this.bounds(),top=this.screen(bounds[0],bounds[1]);ctx.imageSmoothingEnabled=true;
      const detail=this.zoom>Math.max(this.overview.width/(bounds[2]-bounds[0])*1.5,.22);
      let draws=[],complete=false;
      if(detail){draws=this.visible();const keys=[...new Set(draws.map(d=>d[2]))],loaded=keys.filter(k=>this.image(k).ready).length;complete=loaded===keys.length;
        this.detailState.textContent=complete?'':`Özgün detaylar hazırlanıyor · ${loaded} / ${keys.length}`;
      }else this.detailState.textContent='';
      if(!complete)ctx.drawImage(this.overview,top.x,top.y,(bounds[2]-bounds[0])*this.zoom,(bounds[3]-bounds[1])*this.zoom);
      else{
        ctx.imageSmoothingEnabled=this.zoom<1;
        for(const [x,y,key,opacity=1000,flags=0] of draws){const p=this.patterns[key],entry=this.images.get(key),at=this.screen(x+p.x,y+p.y);ctx.globalCompositeOperation=flags&0x10?'lighter':flags&0x4?'multiply':'source-over';ctx.globalAlpha=flags&0x4?1:clamp(opacity/1000,0,1);ctx.drawImage(entry.img,at.x,at.y,p.w*this.zoom,p.h*this.zoom);}
        ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
      }
      if(this.showMobs){
        for(const p of this.spawns){const at=this.screen(p[0],p[1]);if(at.x<0||at.x>this.width||at.y<0||at.y>this.height)continue;
          const focused=this.highlight&&p[2]===this.highlight.mob&&(this.highlight.variant===null||p[3]===this.highlight.variant);
          ctx.beginPath();ctx.arc(at.x,at.y,focused?5:this.zoom<.13?1.7:2.7,0,Math.PI*2);ctx.fillStyle=focused?'#ffe3a4':p[4]?'#ba93ed':'#e79a6a';ctx.fill();
          if(focused||this.zoom>.14){ctx.strokeStyle='#211209';ctx.lineWidth=focused?2:1;ctx.stroke();}
        }
      }
      for(const marker of this.markers){
        const at=this.screen(marker.x,marker.y);if(at.x<-20||at.x>this.width+20||at.y<-20||at.y>this.height+20)continue;
        const selected=marker.id===this.markerFocus,r=selected?12:10;
        ctx.beginPath();ctx.arc(at.x,at.y,r,0,Math.PI*2);ctx.fillStyle=selected?'#f0cd89':'#22291c';ctx.fill();ctx.strokeStyle='#e9c27b';ctx.lineWidth=selected?3:1.5;ctx.stroke();
        ctx.font='bold 11px "Segoe UI",sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle=selected?'#18190e':'#f5d89e';ctx.fillText(String(marker.number),at.x,at.y+.5);
        if(selected){const label=marker.label,tw=ctx.measureText(label).width;ctx.fillStyle='#10160eee';ctx.fillRect(at.x-tw/2-8,at.y-r-27,tw+16,21);ctx.fillStyle='#f4dfa8';ctx.fillText(label,at.x,at.y-r-16);}
      }
      this.onView?.({zoom:this.zoom,cx:Math.round(this.cx),cy:Math.round(this.cy),detail:complete});
    }
  }
  root.AtlasMapViewer=AtlasMapViewer;
  if(typeof module!=='undefined')module.exports={nativeObjectOrder,AtlasMapViewer};
})(typeof window!=='undefined'?window:globalThis);
