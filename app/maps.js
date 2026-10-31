(function(){
  'use strict';
  const D=window.ATLAS_DATA,meta=window.SF_MAPS,assets=window.SF_MAP_ASSETS,app=window.AtlasApp;
  const model=new AtlasMapModel(D,app.model,meta),$=s=>document.querySelector(s);
  const scenario=new AtlasScenarioModel(D,window.SF_SCENARIO_ITEMS,window.SF_WORLD);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number(n).toLocaleString('tr-TR');
  const percent=p=>'%'+(p*100).toLocaleString('tr-TR',{maximumFractionDigits:p>=.1?2:p>=.001?4:7});
  const state={map:0,item:null,mob:null,variant:null,scenarioItem:null,scenarioPoint:null,query:'',lootQuery:'',quality:'all',limit:35,mobLimit:35,players:app.getPlayers(),episode:0,sort:'progression'};
  let loadId=0,opened=false;
  const mapMeta=index=>meta.maps[index]||model.maps[index];
  const resource=index=>assets.resources[mapMeta(index).resource];
  const spawns=index=>mapMeta(index).spawns||[];
  const icon=item=>window.SF_VISUALS.items[item.key]?.src;
  const portrait=(mob,vi)=>window.SF_VISUALS.sprites[mob.variants[vi].visual]?.poster;
  function chooseEntity(type,id,variant=0){window.AtlasTabs.show('atlas');app.select(type,id,variant);$('#catalogue').scrollIntoView({block:'start'});}
  function hash(){const params=new URLSearchParams({map:model.maps[state.map].id});if(state.item!==null)params.set('mapItem',state.item);if(state.mob!==null){params.set('mapMob',state.mob);if(state.variant!==null)params.set('mapVariant',state.variant);}if(state.scenarioItem){params.set('mapScenario',state.scenarioItem);if(state.scenarioPoint)params.set('mapPoint',state.scenarioPoint);}history.replaceState(null,'','#'+params);}
  function readHash(){
    const params=new URLSearchParams(location.hash.slice(1));if(!params.has('map'))return false;
    const index=model.byId.get(params.get('map'));if(index===undefined)return false;state.map=index;
    const item=Number(params.get('mapItem'));state.item=params.has('mapItem')&&D.items[item]?item:null;
    const mob=Number(params.get('mapMob'));state.mob=params.has('mapMob')&&D.mobs[mob]?mob:null;
    const vi=Number(params.get('mapVariant'));state.variant=state.mob!==null&&params.has('mapVariant')&&D.mobs[state.mob].variants[vi]?vi:null;
    state.scenarioItem=scenario.byKey.has(params.get('mapScenario'))?params.get('mapScenario'):null;state.scenarioPoint=state.scenarioItem?params.get('mapPoint'):null;
    return true;
  }
  function renderDirectory(){
    $('#mapSort option[value=chance]').disabled=state.item===null;
    if(state.sort==='chance'&&state.item===null){state.sort='progression';$('#mapSort').value='progression';}
    const results=model.matches(state.query,state.item,state.players,{episode:state.episode==='extra'?0:state.episode,sort:state.sort,world:window.SF_WORLD}).filter(r=>state.episode!=='extra'||r.map>=D.maps.length);
    window.dispatchEvent(new CustomEvent('atlas:mapfilter',{detail:{maps:results.map(r=>r.map),item:state.item,episode:state.episode}}));$('#mapResultCount').textContent=fmt(results.length)+' kayıt';
    const filter=$('#mapItemFilter');filter.hidden=state.item===null;
    if(state.item!==null){const item=D.items[state.item];filter.innerHTML=`<b>${esc(item.name)}${item.level?' · Seviye '+item.level:''}</b><br>Bu eşyanın düşebildiği bölgeler<button data-map-clear-item>Harita filtresini kaldır ×</button>`;}
    $('#mapList').innerHTML=results.length?results.map(({map,record,source})=>{
      const asset=resource(map),count=model.entries[map].reduce((n,e)=>n+e.count,0),extra=map>=D.maps.length;
      return `<button class="map-card" data-map-index="${map}" aria-pressed="${map===state.map}">${asset?`<img class="map-thumb" src="${esc(asset.overview.src||asset.overview)}" alt="" loading="lazy">`:'<span class="map-thumb"></span>'}<b>${esc(record.name)}<small>${extra?'Senaryoya bağlı olmayan harita':('EP. '+window.SF_WORLD.maps[map].episode+' · '+(window.SF_WORLD.maps[map].towerFloor?'Kule '+window.SF_WORLD.maps[map].towerFloor+'. kat · ':'')+fmt(count)+' yaratık yerleşimi · '+record.id)}</small>${source?`<em>${percent(source.chance)} · en iyi kaynak</em>`:''}</b></button>`;
    }).join(''):'<p class="map-empty">Bu aramayla eşleşen harita yok. Başka bir ad deneyebilirsin.</p>';
    const list=$('#mapList'),selected=list.querySelector('[aria-pressed="true"]');
    if(selected){if(matchMedia('(max-width:760px)').matches)list.scrollLeft=selected.offsetLeft-list.offsetLeft;else list.scrollTop=Math.max(0,selected.offsetTop-list.offsetTop-80);}
  }
  const viewer=new AtlasMapViewer({viewport:$('#mapViewport'),canvas:$('#mapCanvas'),patterns:assets.patterns,
    onSelect:p=>{state.mob=p[2];state.variant=p[3];viewer.focus(p[2],p[3]);renderMobs();renderFocus();$('#mapShowMobs').checked=true;hash();},
    onHover:(p,point)=>{const hover=$('#mapHover');hover.hidden=!p;if(!p)return;const mob=D.mobs[p[2]];hover.innerHTML=`${esc(mob.name)}<small>${p[4]?'Görev durumuyla açılıp kapanan yerleşim':'Senaryodaki yaratık konumu'} · seçmek için tıkla</small>`;hover.style.left=Math.max(5,Math.min(point.x+12,viewer.width-240))+'px';hover.style.top=Math.max(5,point.y-55)+'px';},
    onView:v=>{$('#mapScale').textContent=Math.round(v.zoom*100)+'%';$('#mapCoordinates').textContent=fmt(v.cx)+' , '+fmt(v.cy);}
  });
  viewer.onMarkerSelect=marker=>{state.scenarioPoint=marker.id;hash();renderScenarioFocus();};
  function renderScenarioFocus(){
    const panel=$('#mapScenarioFocus'),record=scenario.byKey.get(state.scenarioItem);
    const markers=scenario.markers(model.maps[state.map].id,state.scenarioItem);panel.hidden=!record;
    if(!record)return;
    panel.innerHTML=`<strong>${esc(record.name)} · ${markers.length} eşya / NPC / yaratık noktası</strong><p>Altın numaralar rehberdeki konumları gösterir. Koordinatlar oyun dünyasının X / Y değerleridir; NPC işaretleri başlangıç konumlarıdır.</p>${markers.length?`<div class="scenario-points">${markers.map(p=>`<button class="scenario-point" data-map-scenario-point="${esc(p.id)}" aria-pressed="${p.id===state.scenarioPoint}"><b>${p.number}</b><span>${esc(p.label)}<br>X ${fmt(p.worldX)} · Y ${fmt(p.worldY)}</span></button>`).join('')}</div>`:'<p>Bu haritada seçili eşyanın doğrulanmış bir noktası yok.</p>'}<button data-scenario-item="${esc(record.key)}">Elde etme adımlarına dön ↗</button>`;
  }
  function applyScenarioFocus(){
    viewer.setMarkers(scenario.markers(model.maps[state.map].id,state.scenarioItem));
    if(state.scenarioPoint)viewer.focusMarker(state.scenarioPoint);renderScenarioFocus();
  }
  function renderFocus(){
    const panel=$('#mapFocusInfo'),entries=state.item===null?[]:model.sourcesAt(state.map,state.item,state.players);
    if(state.item!==null){const item=D.items[state.item];panel.hidden=false;panel.innerHTML=`<b>${esc(item.name)}${item.level?' · Seviye '+item.level:''}</b> için ${entries.length?fmt(entries.length)+' kaynak varyantı bu bölgede var.':'bu bölgede standart yaratık kaynağı yok.'}${entries.length?` En yüksek tek öldürme oranı: <b>${percent(entries[0].chance)}</b>.`:''}<button data-map-open-item="${item.id}">Eşya paneline dön ↗</button>`;}
    else if(state.mob!==null){panel.hidden=false;const mob=D.mobs[state.mob],count=model.entries[state.map].filter(e=>e.mob===state.mob&&(state.variant===null||state.variant===e.variant)).reduce((n,e)=>n+e.count,0);panel.innerHTML=`<b>${esc(mob.name)}</b> · Bu bölgede ${fmt(count)} yerleşim vurgulanıyor.<button data-map-open-mob="${mob.id}" data-variant="${state.variant??0}">Yaratığın animasyonunu ve drop havuzunu aç ↗</button><button data-map-clear-focus>Vurguyu kaldır ×</button>`;}
    else panel.hidden=true;
    renderScenarioFocus();
  }
  function renderMobs(){
    let entries=[...model.entries[state.map]];
    const rates=state.item===null?null:new Map(model.sourcesAt(state.map,state.item,state.players).map(e=>[e.mob+':'+e.variant,e.chance]));
    if(rates)entries.sort((a,b)=>(rates.get(b.mob+':'+b.variant)||0)-(rates.get(a.mob+':'+a.variant)||0)||b.count-a.count);
    else entries.sort((a,b)=>b.count-a.count||a.mob-b.mob);
    $('#mapMobCount').textContent=fmt(new Set(entries.map(e=>e.mob)).size)+' tür · '+fmt(entries.reduce((n,e)=>n+e.count,0))+' yerleşim';
    $('#mapMobList').innerHTML=entries.length?entries.slice(0,state.mobLimit).map(e=>{
      const mob=D.mobs[e.mob],variant=mob.variants[e.variant],src=portrait(mob,e.variant),chance=rates?.get(e.mob+':'+e.variant),focused=e.mob===state.mob&&(state.variant===null||e.variant===state.variant);
      return `<article class="map-mob-card${focused?' is-focused':''}">${src?`<img class="map-mob-portrait" src="${esc(src)}" alt="" loading="lazy">`:'<span class="fallback-art">◇</span>'}<button class="map-mob-name" data-map-open-mob="${mob.id}" data-variant="${e.variant}">${esc(mob.name)}<small>${fmt(e.count)} yerleşim · Grup ${variant.group}${rates?' · '+(chance?percent(chance):'hedef eşya yok'):''}</small></button><button class="map-locate" data-map-locate="${mob.id}" data-variant="${e.variant}" aria-label="${esc(mob.name)} konumlarını haritada göster">Konum ↗</button></article>`;
    }).join('')+(entries.length>state.mobLimit?`<button class="map-more" data-map-more-mobs>${fmt(entries.length-state.mobLimit)} varyantı daha göster ↓</button>`:''):'<div class="no-drops">Bu bölgenin senaryo kaydında düşman yerleşimi yok.</div>';
  }
  function renderLoot(){
    const q=atlasNormalize(state.lootQuery),rows=model.lootAt(state.map,state.players).filter(row=>{
      const item=D.items[row.item];return (!q||atlasNormalize(item.name+' '+item.base).includes(q))&&(state.quality==='all'||item.rarity===Number(state.quality));
    });
    $('#mapLootCount').textContent=fmt(rows.length)+' eşya'+(app.model.multiplier>1?' · ×'+app.model.multiplier+(app.model.premiumOnly?' Premium':''):'')+(app.model.excludeFound?' · Grail filtresi':'');
    $('#mapLootList').innerHTML=rows.length?rows.slice(0,state.limit).map(row=>{
      const item=D.items[row.item],src=icon(item),best=[...row.sources].sort((a,b)=>b.chance-a.chance)[0];
      return `<button class="map-loot-card" data-map-open-item="${item.id}" data-quality="${item.rarity}">${src?`<img src="${esc(src)}" alt="" loading="lazy">`:'<span>◇</span>'}<span><b>${esc(item.name)}</b><small>${item.level?'Seviye '+item.level+' · ':''}${esc(D.mobs[best.mob].name)}${row.sources.length>1?' +'+(row.sources.length-1)+' kaynak':''}</small></span><span>${percent(row.chance)}<small>tek öldürmede</small></span></button>`;
    }).join('')+(rows.length>state.limit?`<button class="map-more" data-map-more-loot>${fmt(rows.length-state.limit)} eşyayı daha göster ↓</button>`:''):'<div class="no-drops">Bu filtreyle eşleşen standart yaratık drobu yok.</div>';
  }
  async function renderMap(){
    const token=++loadId,map=model.maps[state.map],info=mapMeta(state.map),asset=resource(state.map);
    window.dispatchEvent(new CustomEvent('atlas:map-selection',{detail:{id:map.id,name:map.name,playable:state.map<D.maps.length}}));
    $('#mapTitle').textContent=map.name;$('#mapRegionCode').textContent=state.map<D.maps.length?'BÖLGE '+map.id:'EK HARİTA DOSYASI';
    const entries=model.entries[state.map];$('#mapSummary').textContent=state.map<D.maps.length?fmt(new Set(entries.map(e=>e.mob)).size)+' yaratık türü · '+fmt(entries.reduce((n,e)=>n+e.count,0))+' senaryo yerleşimi':'Kurulumda mevcut; bu dosyaya bağlı bir senaryo kaydı bulunamadı.';
    const guide=window.SF_WORLD.maps[state.map];$('#mapGuideInfo').textContent=guide?'Episode '+guide.episode+(guide.guideNameVerified?' · Rehber: '+guide.guideName:'')+(guide.towerFloor?' · Tower '+guide.towerFloor+'. kat'+(guide.episode<4?' · Episode '+guide.episode+' tamamlanınca açılır':''):'')+(guide.annexFloor?' · Annex '+guide.annexFloor+'. kat':''):'';
    $('#mapCanvas').setAttribute('aria-label',map.name+' · orijinal oyun haritası');state.limit=35;state.mobLimit=35;
    $('#mapPlayers').value=state.players;renderDirectory();renderMobs();renderLoot();renderFocus();
    window.SF_WORLD.questRequirements.forEach((q,i)=>{if(q.involvedScenarioIDs.includes(map.id))$('#mapGuideInfo').insertAdjacentHTML('beforeend',`<br><button class="map-quest-source" ${q.src?`data-world-quest="${i}"`:'disabled'}>${esc(q.name)} · görev açılışı: seviye ${q.questLevelMin}${q.src?' ↗':''}</button> (bölgeye giriş şartı değil)`);});
    const loading=$('#mapLoadState');loading.hidden=false;loading.classList.remove('error');loading.textContent='Bölgenin tamamı açılıyor…';
    if(!asset){loading.classList.add('error');loading.textContent='Bu harita için oyun görseli bulunamadı.';return;}
    try{const done=await viewer.setMap(asset,info.spawns||[]);if(token!==loadId||!done)return;loading.hidden=true;if(state.mob!==null)viewer.focus(state.mob,state.variant);applyScenarioFocus();}
    catch(error){if(token===loadId){loading.classList.add('error');loading.textContent=error.message+' Atlas dosyalarının aynı klasörde olduğundan emin ol.';}}
  }
  function openMap(index,{item=null,mob=null,variant=null,scenarioItem=null,scenarioPoint=null}={}){
    if(!model.maps[index])return;state.map=index;state.item=item;state.mob=mob;state.variant=variant;state.scenarioItem=scenarioItem;state.scenarioPoint=scenarioPoint;state.query='';state.episode=0;$('#mapSearch').value='';$('#mapEpisode').value='0';
    opened=true;window.AtlasTabs.show('maps');hash();renderMap();$('.map-content').scrollIntoView({block:'start'});
  }
  function openScenario(id,key,point=null){
    const index=model.byId.get(id);if(index===undefined||!scenario.byKey.has(key))return false;
    openMap(index,{scenarioItem:key,scenarioPoint:point});return true;
  }
  function decorateDetail(){
    const selection=app.getSelection();if(selection.type==='mob'){
      const variant=D.mobs[selection.id].variants[selection.variant];
      document.querySelectorAll('#detail .locations li').forEach((li,i)=>{const [map,count]=variant.locations[i];li.innerHTML=`<button data-atlas-map="${map}" data-map-from-mob="${selection.id}" data-variant="${selection.variant}">${esc(D.maps[map].name)} ↗</button><span>× ${count}</span>`;});
      return;
    }
    const body=$('#detail .detail-body');if(!body)return;body.querySelector('.item-map-section')?.remove();
    const maps=model.sourceMaps(selection.id,app.getPlayers()),section=document.createElement('section');section.className='item-map-section';
    section.innerHTML=`<h3>Hangi haritalarda?</h3>${maps.length?`<div class="item-map-links">${maps.slice(0,5).map(row=>`<button data-atlas-map="${row.map}" data-map-from-item="${selection.id}">${esc(D.maps[row.map].name)} ↗</button>`).join('')}</div><button class="text-button" data-map-all-item="${selection.id}">${fmt(maps.length)} bölgenin tamamını haritada gör ↗</button><p>Aynı isimli eşyaların seviye ve kayıt farkları ayrı izlenir.</p>`:'<p>Bu eşya için standart yaratık drobuna bağlı harita bulunamadı.</p>'}`;
    const players=body.querySelector('.players-setting');if(players)players.before(section);else body.append(section);
  }
  document.addEventListener('click',event=>{
    let b=event.target.closest('[data-atlas-map]');if(b){openMap(Number(b.dataset.atlasMap),{item:b.dataset.mapFromItem===undefined?null:Number(b.dataset.mapFromItem),mob:b.dataset.mapFromMob===undefined?null:Number(b.dataset.mapFromMob),variant:b.dataset.variant===undefined?null:Number(b.dataset.variant)});return;}
    b=event.target.closest('[data-map-all-item]');if(b){const item=Number(b.dataset.mapAllItem),maps=model.sourceMaps(item,state.players);if(maps.length)openMap(maps[0].map,{item});return;}
    b=event.target.closest('[data-map-index]');if(b){state.map=Number(b.dataset.mapIndex);state.mob=null;state.variant=null;state.scenarioItem=null;state.scenarioPoint=null;hash();renderMap();return;}
    b=event.target.closest('[data-map-scenario-point]');if(b){if(viewer.focusMarker(b.dataset.mapScenarioPoint)){state.scenarioPoint=b.dataset.mapScenarioPoint;hash();renderScenarioFocus();}return;}
    b=event.target.closest('[data-map-open-item]');if(b){chooseEntity('item',Number(b.dataset.mapOpenItem));return;}
    b=event.target.closest('[data-map-open-mob]');if(b){chooseEntity('mob',Number(b.dataset.mapOpenMob),Number(b.dataset.variant)||0);return;}
    b=event.target.closest('[data-map-locate]');if(b){state.mob=Number(b.dataset.mapLocate);state.variant=Number(b.dataset.variant);viewer.focus(state.mob,state.variant);$('#mapShowMobs').checked=true;renderMobs();renderFocus();hash();$('#mapViewer').scrollIntoView({block:'center',behavior:'smooth'});return;}
    if(event.target.closest('[data-map-clear-item]')){state.item=null;hash();renderDirectory();renderMobs();renderFocus();return;}
    if(event.target.closest('[data-map-clear-focus]')){state.mob=null;state.variant=null;viewer.highlight=null;viewer.request();renderMobs();renderFocus();hash();return;}
    if(event.target.closest('[data-map-more-loot]')){state.limit+=70;renderLoot();}
    if(event.target.closest('[data-map-more-mobs]')){state.mobLimit+=50;renderMobs();}
  });
  $('#mapEpisode').addEventListener('change',event=>{state.episode=event.target.value==='extra'?'extra':Number(event.target.value);renderDirectory();});
  $('#mapSort').addEventListener('change',event=>{state.sort=event.target.value;renderDirectory();});
  $('#mapSearch').addEventListener('input',event=>{state.query=event.target.value;renderDirectory();});
  $('#mapLootSearch').addEventListener('input',event=>{state.lootQuery=event.target.value;state.limit=35;renderLoot();});
  $('#mapLootQuality').addEventListener('change',event=>{state.quality=event.target.value;state.limit=35;renderLoot();});
  $('#mapPlayers').addEventListener('change',event=>{state.players=Number(event.target.value);app.setPlayers(state.players);renderDirectory();renderMobs();renderLoot();renderFocus();});
  $('#mapShowMobs').addEventListener('change',event=>{viewer.showMobs=event.target.checked;viewer.request();});
  $('#mapEdgePan').addEventListener('change',event=>{viewer.edgePan=event.target.checked;viewer.request();});
  $('#mapZoomIn').addEventListener('click',()=>viewer.zoomAt(1.5));$('#mapZoomOut').addEventListener('click',()=>viewer.zoomAt(1/1.5));$('#mapFit').addEventListener('click',()=>viewer.fit());
  $('#mapFullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('#mapViewer').requestFullscreen();}catch{$('.map-help').textContent='Tarayıcı tam ekranı açamadı; yakınlaştırma ve sürükleme kullanılabilir.';}});
  document.addEventListener('fullscreenchange',()=>{$('#mapFullscreen').textContent=document.fullscreenElement?'Tam ekrandan çık ↙':'Tam ekran ↗';$('#mapFullscreen').setAttribute('aria-label',document.fullscreenElement?'Tam ekrandan çık':'Haritayı tam ekran aç');viewer.resize();});
  window.addEventListener('atlas:selection',event=>{state.players=event.detail.players;$('#mapPlayers').value=state.players;decorateDetail();});
  window.addEventListener('atlas:drop-multiplier',()=>{decorateDetail();if(opened){renderDirectory();renderMobs();renderLoot();renderFocus();}});
  window.addEventListener('atlas:tabchange',event=>{if(event.detail.name==='maps'){if(!opened){opened=true;renderMap();}else{viewer.resize();$('#mapPlayers').value=state.players;renderDirectory();renderMobs();renderLoot();renderFocus();}}});
  window.addEventListener('hashchange',()=>{if(readHash()){window.AtlasTabs.show('maps');opened=true;renderMap();}});
  document.addEventListener('keydown',event=>{if(event.key==='/'&&!$('#mapsPage').hidden&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){event.preventDefault();$('#mapSearch').focus();}});
  $('#mapTotal').textContent=fmt(model.maps.length);decorateDetail();
  window.AtlasMaps={open:openMap,openScenario,model,viewer,state,refresh:renderDirectory};
  if(readHash()){opened=true;window.AtlasTabs.show('maps');renderMap();}
})();
