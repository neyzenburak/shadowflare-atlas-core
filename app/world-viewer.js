(function(){
  'use strict';
  const W=window.SF_WORLD,A=window.AtlasMaps,D=window.ATLAS_DATA,$=s=>document.querySelector(s);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const roman=['','I','II','III','IV'],colors=['','#9ebed0','#d9b17b','#b7c28b','#b0a0cb'];
  const layout={1:[1800,0,1.4],2:[650,490,1.4],3:[900,950,1.4],4:[0,100,1.2]};
  const headings={1:[2380,75,'REMOTE TOWN'],2:[1450,530,'KANFORE & FANANN'],3:[1360,1075,'ANTALUSIA'],4:[400,180,'WEST CALADO']};
  const svg=$('#worldSvg'),stage=$('#worldStage'),full=[-80,-60,2980,1690];
  const state={episode:0,selected:null,allowed:null,item:null,view:[...full],drag:null};
  let footprintTable=W.footprints.resources||W.footprints.footprints||W.footprints;
  const pos=n=>{const [x,y,s]=layout[n.episode];return [x+n.anchor[0]*s,y+n.anchor[1]*s];};
  const footprint=n=>{
    const key=window.SF_MAPS.maps[n.maps[0]].resource;
    const f=Array.isArray(footprintTable)?footprintTable.find(f=>f.resource===key||f.key===key):footprintTable[key];
    return f&&{...f,src:'assets/world/'+(f.src||f.file||key+'.png'),width:f.exportWidth,height:f.exportHeight};
  };
  function render(){
    const edges=new Set();
    for(const [a,b] of W.edges){const na=W.maps[a]?.node,nb=W.maps[b]?.node;if(na===null||nb===null||na===nb)continue;edges.add([Math.min(na,nb),Math.max(na,nb)].join(':'));}
    const lines=[...edges].map(pair=>{const [a,b]=pair.split(':').map(Number),na=W.nodes[a],nb=W.nodes[b],[x,y]=pos(na),[u,v]=pos(nb);return `<path class="world-road" data-world-road="${a}:${b}" d="M${x} ${y} Q${(x+u)/2+12} ${(y+v)/2-15} ${u} ${v}"/>`;}).join('');
    svg.innerHTML=`<defs><filter id="worldGlow"><feGaussianBlur stdDeviation="7"/></filter><radialGradient id="realmFog"><stop stop-color="#85936a" stop-opacity=".1"/><stop offset="1" stop-color="#85936a" stop-opacity="0"/></radialGradient></defs>
      <g class="world-grid" aria-hidden="true">${[1,2,3,4].map(ep=>{const [x,y]=headings[ep];return `<ellipse cx="${x}" cy="${y+240}" rx="600" ry="480" fill="url(#realmFog)"/>`;}).join('')}</g>
      <g class="world-roads" aria-hidden="true">${lines}</g>
      <g class="world-terrain" aria-hidden="true">${W.nodes.map(n=>{const f=footprint(n);if(!f)return '';const [x,y]=pos(n);const nearest=Math.min(...W.nodes.filter(m=>m.id!==n.id&&m.episode===n.episode).map(m=>{const [u,v]=pos(m);return Math.hypot(x-u,y-v);}));const w=Math.max(70,Math.min(240,nearest*1.65)),h=w*(f.height||f.size?.[1]||384)/(f.width||f.size?.[0]||512);return `<image data-world-terrain="${n.id}" href="${esc(f.src)}" x="${x-w/2}" y="${y-h/2}" width="${w}" height="${h}"/>`;}).join('')}</g>
      <g class="world-realm-headings" aria-hidden="true">${[1,2,3,4].map(ep=>{const [x,y,t]=headings[ep];return `<g data-world-heading="${ep}" transform="translate(${x},${y})" fill="${colors[ep]}"><text class="realm-number" text-anchor="middle">${roman[ep]}</text><text class="realm-name" y="32" text-anchor="middle">${t}</text></g>`;}).join('')}</g>
      <g class="world-markers">${W.nodes.map(n=>{const [x,y]=pos(n);return `<g class="world-node" data-world-node="${n.id}" transform="translate(${x},${y})" style="--realm:${colors[n.episode]}"><title>${esc(n.guideName)} · Episode ${n.episode}</title><circle class="node-halo" r="19" role="button" tabindex="0" aria-label="Episode ${n.episode} · ${esc(n.guideName)} · ${n.maps.length} bölge kaydı"/><circle class="node-dot" r="6"/><text class="node-label" x="12" y="-12">${esc(n.guideName)}</text></g>`;}).join('')}</g>`;
    update();
  }
  function setView(view){state.view=view;svg.setAttribute('viewBox',view.join(' '));stage.classList.toggle('world-close',view[2]<1700);}
  function fit(ep=state.episode){
    if(!ep){setView([...full]);return;}
    const points=W.nodes.filter(n=>n.episode===ep).map(pos),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const minX=Math.min(...xs)-160,minY=Math.min(...ys)-150;
    setView([minX,minY,Math.max(...xs)-minX+160,Math.max(...ys)-minY+150]);
  }
  function point(e){const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(svg.getScreenCTM().inverse());}
  function zoom(factor,at){const [x,y,w,h]=state.view,p=at||{x:x+w/2,y:y+h/2},nw=Math.max(330,Math.min(full[2]*1.6,w/factor)),ratio=nw/w;setView([p.x+(x-p.x)*ratio,p.y+(y-p.y)*ratio,nw,h*ratio]);}
  function setEpisode(ep,write=true){
    if(state.selected!==null&&W.nodes[state.selected].episode!==ep&&ep){state.selected=null;$('#worldSelection').hidden=true;}
    state.episode=ep;document.querySelectorAll('[data-world-episode]').forEach(b=>b.setAttribute('aria-pressed',Number(b.dataset.worldEpisode)===ep));
    $('#mapEpisode').value=String(ep);A.state.episode=ep;A.refresh();fit(ep);update();
    if(write)history.replaceState(null,'','#world='+ep);
  }
  function update(){
    $('#worldGuide').hidden=!W.sources[state.episode||'all']?.src;
    let visible=0;
    for(const n of W.nodes){const allowed=(!state.episode||n.episode===state.episode)&&(!state.allowed||n.maps.some(i=>state.allowed.has(i))),selected=n.id===state.selected;visible+=allowed?1:0;
      const outside=state.episode&&n.episode!==state.episode;
      const g=svg.querySelector(`[data-world-node="${n.id}"]`);g.style.display=outside?'none':'';g?.classList.toggle('is-dim',!allowed);g?.classList.toggle('is-selected',selected);g?.querySelector('.node-halo').setAttribute('aria-pressed',String(selected));
      const terrain=svg.querySelector(`[data-world-terrain="${n.id}"]`);if(terrain){terrain.style.display=outside?'none':'';terrain.classList.toggle('is-dim',!allowed);}
    }
    svg.querySelectorAll('[data-world-heading]').forEach(g=>g.style.display=state.episode&&Number(g.dataset.worldHeading)!==state.episode?'none':'');
    svg.querySelectorAll('[data-world-road]').forEach(g=>{const [a,b]=g.dataset.worldRoad.split(':').map(Number);g.style.display=state.episode&&(W.nodes[a].episode!==state.episode||W.nodes[b].episode!==state.episode)?'none':'';});
    $('#worldStatus').textContent=visible+' / '+W.nodes.length+' rehber bölgesi'+(state.item!==null?' · '+D.items[state.item].name:'');
    if(state.selected!==null)selection(state.selected,false);
  }
  function selection(id,focus=true){
    state.selected=id;const n=W.nodes[id],panel=$('#worldSelection'),all=n.maps,matched=all.filter(i=>!state.allowed||state.allowed.has(i)),maps=matched.length?matched:all;
    panel.hidden=false;
    panel.innerHTML=`<div><p class="eyebrow">EPISODE ${roman[n.episode]}${n.guideLabel?' · REHBER '+esc(n.guideLabel):''}</p><h3>${esc(n.guideName)}</h3><p>${all.length} bölge / kat kaydı${state.item!==null?(matched.length?' · hedef eşyanın '+matched.length+' kaynağı':' · bu işarette hedef eşya kaynağı yok'):''}</p></div><div class="world-destinations">${maps.map(i=>`<button data-atlas-map="${i}"${state.item!==null&&matched.length?` data-map-from-item="${state.item}"`:''}>${esc(D.maps[i].name)}<small>${D.maps[i].id}${W.maps[i].towerFloor?' · '+W.maps[i].towerFloor+'. kat':''}</small><span>Haritayı aç ↗</span></button>`).join('')}</div><button id="worldSelectionClose" class="world-selection-close" aria-label="Bölge seçimini kapat">×</button>`;
    svg.querySelectorAll('[data-world-node]').forEach(g=>{const active=Number(g.dataset.worldNode)===id;g.classList.toggle('is-selected',active);g.querySelector('.node-halo').setAttribute('aria-pressed',String(active));});
    if(focus)panel.scrollIntoView({block:'nearest',behavior:'smooth'});
  }
  stage.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.2:1/1.2,point(e));},{passive:false});
  stage.addEventListener('pointerdown',e=>{if(e.button!==0)return;const p=point(e);state.drag={id:e.pointerId,x:e.clientX,y:e.clientY,start:p,view:[...state.view],node:e.target.closest('[data-world-node]')?.dataset.worldNode};stage.setPointerCapture(e.pointerId);stage.classList.add('is-dragging');});
  stage.addEventListener('pointermove',e=>{const drag=state.drag;if(!drag)return;const matrix=svg.getScreenCTM(),dx=(e.clientX-drag.x)/matrix.a,dy=(e.clientY-drag.y)/matrix.d;setView([drag.view[0]-dx,drag.view[1]-dy,drag.view[2],drag.view[3]]);});
  stage.addEventListener('pointerup',e=>{const drag=state.drag;if(!drag)return;state.drag=null;stage.classList.remove('is-dragging');if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<5&&drag.node!==undefined)selection(Number(drag.node));});
  stage.addEventListener('pointercancel',()=>{state.drag=null;stage.classList.remove('is-dragging');});
  stage.addEventListener('keydown',e=>{const node=e.target.closest('[data-world-node]');if(node&&['Enter',' '].includes(e.key)){e.preventDefault();selection(Number(node.dataset.worldNode));return;}const keys={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};if(keys[e.key]){e.preventDefault();const [a,b]=keys[e.key],[x,y,w,h]=state.view;setView([x+a*w*.08,y+b*h*.08,w,h]);}else if(['+','=','-','0'].includes(e.key)){e.preventDefault();if(e.key==='0')fit();else zoom(e.key==='-'?1/1.4:1.4);}});
  $('#worldZoomIn').addEventListener('click',()=>zoom(1.5));$('#worldZoomOut').addEventListener('click',()=>zoom(1/1.5));$('#worldFit').addEventListener('click',()=>{fit();stage.scrollIntoView({block:'center',behavior:'smooth'});});
  $('#worldEpisodes').addEventListener('click',e=>{const b=e.target.closest('[data-world-episode]');if(b)setEpisode(Number(b.dataset.worldEpisode));});
  $('#worldSelection').addEventListener('click',e=>{if(e.target.closest('#worldSelectionClose')){$('#worldSelection').hidden=true;state.selected=null;update();}});
  $('#worldGuide').addEventListener('click',()=>{const source=W.sources[state.episode||'all'];if(!source?.src)return;$('#worldGuideImage').src=source.src;$('#worldGuideSource').textContent=source.page;$('#worldGuideTitle').textContent=state.episode?'Episode '+roman[state.episode]+' · özgün rehber':'Tüm dünya · özgün rehber';$('#worldGuideDialog').showModal();});
  $('#worldGuideClose').addEventListener('click',()=>$('#worldGuideDialog').close());
  const locate=document.createElement('button');locate.id='mapWorldLocate';locate.className='world-locate-current';locate.textContent='Dünyada göster ↑';$('.map-heading').append(locate);
  locate.addEventListener('click',()=>{const n=W.maps[A.state.map]?.node;if(n!==undefined&&n!==null){setEpisode(W.nodes[n].episode);selection(n,false);const [x,y]=pos(W.nodes[n]);setView([x-500,y-320,1000,640]);}else{setEpisode(W.maps[A.state.map]?.episode||0);$('#worldStatus').textContent='Bu kaydın rehberde kesin bir dünya konumu yok; bölge listesinden açılabilir.';}stage.scrollIntoView({block:'center',behavior:'smooth'});});
  document.addEventListener('click',e=>{const b=e.target.closest('[data-world-quest]');if(!b)return;const q=W.questRequirements[Number(b.dataset.worldQuest)];if(!q?.src)return;$('#worldGuideImage').src=q.src;$('#worldGuideSource').textContent=q.sourcepage;$('#worldGuideTitle').textContent=q.name+' · görev seviye şartı '+q.questLevelMin;$('#worldGuideDialog').showModal();});
  window.addEventListener('atlas:mapfilter',e=>{const ep=Number(e.detail.episode)||0;if(ep!==state.episode){state.episode=ep;document.querySelectorAll('[data-world-episode]').forEach(b=>b.setAttribute('aria-pressed',Number(b.dataset.worldEpisode)===ep));fit(ep);}state.allowed=new Set(e.detail.maps);state.item=e.detail.item;update();});
  function readHash(){const p=new URLSearchParams(location.hash.slice(1));if(!p.has('world'))return;window.AtlasTabs.show('maps');setEpisode(Math.max(0,Math.min(4,Number(p.get('world'))||0)),false);}
  window.addEventListener('hashchange',readHash);
  render();A.refresh();readHash();
})();
