(function(){
  'use strict';
  const $=s=>document.querySelector(s),D=window.ATLAS_DATA;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>Number(n).toLocaleString('tr-TR');
  const model=new AtlasScenarioModel(D,window.SF_SCENARIO_ITEMS,window.SF_WORLD);
  const state={key:model.byKey.has('3:40000000')?'3:40000000':model.records[0]?.key,query:'',kind:'all',category:'all'};
  const icon=r=>window.SF_VISUALS?.items[r.key]?.src;
  const image=(r,attr='')=>icon(r)?`<img src="${esc(icon(r))}" alt="" ${attr}>`:'';
  const tags=r=>model.kinds(r).length?model.kinds(r).map(k=>`<span class="scenario-tag">${esc(model.label(k))}</span>`).join(''):'<span class="scenario-tag is-unknown">Kaynak doğrulanmadı</span>';
  const link=(record,map,point=null,label=null)=>`<button class="scenario-map-link" data-scenario-map="${esc(map)}" data-scenario-key="${esc(record.key)}"${point?` data-scenario-point="${esc(point)}"`:''}>${esc(label||model.mapLabel(map))} ↗<small>Oyun haritasında işaretle</small></button>`;
  function writeHash(){if(!$('#scenarioPage').hidden)history.replaceState(null,'','#'+new URLSearchParams({scenario:state.key||''}));}
  function renderList(){
    const rows=model.matches(state);$('#scenarioResultCount').textContent=fmt(rows.length)+' / '+fmt(model.records.length)+' eşya';
    $('#scenarioGrid').innerHTML=rows.length?rows.map(r=>{
      const count=r.sources.filter(s=>s.kind==='ground').reduce((n,s)=>n+s.points.length,0);
      return `<button class="scenario-card" data-scenario-item="${esc(r.key)}" aria-pressed="${r.key===state.key}">${image(r,'loading="lazy"')}<span><b>${esc(r.name)}</b><small${r.unresolved?' class="scenario-unknown"':''}>${esc(model.kinds(r).map(k=>model.label(k)).join(' · ')||'Kaynak doğrulanmadı')}${count?' · '+count+' konum':''}</small></span></button>`;
    }).join(''):'<p class="scenario-empty">Bu aramayla eşleşen eşya yok. Eşya, NPC veya harita adıyla arayabilirsin.</p>';
  }
  function sourceHTML(record,source,index){
    const maps=model.sourceMaps(source),ingredient=model.byKey.get(source.ingredient);
    const mob=source.mob===undefined?null:D.mobs[source.mob];
    const points=source.points.length>1&&source.kind==='ground'?`<div class="scenario-points">${source.points.map((p,i)=>`<button class="scenario-point" data-scenario-map="${esc(p.map)}" data-scenario-key="${esc(record.key)}" data-scenario-point="${esc(p.id)}"><b>${i+1}</b><span>X ${fmt(p.worldX)} · Y ${fmt(p.worldY)} ↗</span></button>`).join('')}</div>`:'';
    const required=ingredient?`<button class="scenario-ingredient" data-scenario-item="${esc(ingredient.key)}">${image(ingredient)}<span><b>Gereken: ${esc(ingredient.name)} ↗</b><small>Malzemenin konumlarını ve edinme yolunu aç</small></span></button>`:'';
    const percent=source.kind==='mob'?' · Temel tek öldürme oranı %'+(source.chance*100).toLocaleString('tr-TR',{maximumFractionDigits:5}):'';
    return `<section class="scenario-source"><p class="eyebrow">${index+1}. YOL · ${esc(model.label(source.kind))}</p><h3>${esc(source.npc||mob?.name||record.name)}${percent}</h3>${maps.map(m=>link(record,m.id,source.points.filter(p=>p.map===m.id).length===1?source.points.find(p=>p.map===m.id)?.id:null)).join('')}${required}<ol>${source.steps.map(t=>`<li>${esc(t)}</li>`).join('')}</ol>${points}${source.note?`<p class="scenario-note">${esc(source.note)}</p>`:''}</section>`;
  }
  function renderDetail(){
    const r=model.byKey.get(state.key),detail=$('#scenarioDetail');if(!r){detail.innerHTML='<p class="scenario-empty">Rehber verileri bulunamadı. Yerel Atlas paketindeki assets klasörünü kontrol et.</p>';return;}
    const usedFor=model.usedFor(r.key);
    detail.innerHTML=`<div class="scenario-detail-heading">${image(r)}<div><p class="eyebrow">${r.category===3?'TÜKETİLEBİLİR':'ÖZEL / GÖREV EŞYASI'}</p><h2>${esc(r.name)}</h2><div class="scenario-tags">${tags(r)}</div></div></div><p class="scenario-map-help">Harita düğmeleri gerçek oyun haritasını açar. Numaralı işareti seçerek konuma odaklanabilirsin; oyunda yolculuk etmek için Haritalar’daki “Giriş noktasına ışınlan” düğmesini kullanabilirsin.</p>${r.sources.length?r.sources.map((s,i)=>sourceHTML(r,s,i)).join(''):'<section class="scenario-source"><h3>Edinme yolu henüz doğrulanmadı.</h3><p>Eşya katalogda mevcut; taranan hazır yerleşimlerde, standart yaratık tablolarında ve doğrulanan ödül yollarında üretim kaydı bulunamadı. Bu, oyunda hiç kullanılmadığının kanıtı değildir.</p></section>'}${usedFor.length?`<section class="scenario-source"><h3>Bu malzemeyle ne alınır?</h3>${usedFor.map(target=>`<button class="scenario-ingredient" data-scenario-item="${esc(target.key)}">${image(target)}<span><b>${esc(target.name)} ↗</b><small>${esc(target.sources.find(s=>s.ingredient===r.key)?.npc)} · takas / görev yolunu aç</small></span></button>`).join('')}</section>`:''}${r.uses.length?`<section class="scenario-source"><h3>Teslim / kullanıldığı NPC’ler</h3>${r.uses.map(u=>link(r,u.map,u.points[0]?.id,u.npc+' · '+model.maps.get(u.map)?.name)).join('')}<p class="scenario-note">İlgili NPC’nin senaryosunda bu eşyayı alan bir konuşma dalı var. Hangi dalın açılacağı karakterinin görev ilerlemesine bağlıdır.</p></section>`:''}<section class="scenario-source"><p class="scenario-note">${r.autoPickup?'Otomatik toplama bu tüketilebilir türünü destekler; ayarın açık ve eşyanın toplama halkası içinde olması gerekir.':esc(r.note)} ${r.sources.some(s=>s.kind!=='mob')?'Hazır yerleşimler ve NPC / senaryo ödülleri mob drop çarpanından bağımsızdır.':''}</p><button class="scenario-catalogue-link" data-scenario-catalogue="${r.item.id}">Envanter görünümünü ve eşya panelini aç ↗</button></section>`;
    detail.scrollTop=0;
  }
  function select(key,{scroll=false}={}){
    if(!model.byKey.has(key))return;state.key=key;window.AtlasTabs.show('scenario');renderList();renderDetail();writeHash();
    if(scroll)$('#scenarioDetail').scrollIntoView({block:'start',behavior:'smooth'});
  }
  function readHash(){const params=new URLSearchParams(location.hash.slice(1));if(!params.has('scenario'))return false;const key=params.get('scenario');if(model.byKey.has(key))state.key=key;return true;}
  function decorateDetail(){
    const selection=window.AtlasApp.getSelection();document.querySelector('#detail .scenario-archive-link')?.remove();
    if(selection.type!=='item')return;const r=model.byKey.get(D.items[selection.id]?.key),body=$('#detail .detail-body');if(!r||!body)return;
    const section=document.createElement('section');section.className='scenario-archive-link';
    section.innerHTML=`<button data-scenario-item="${esc(r.key)}">Özel eşya rehberi: konumlar ve görev yolları ↗</button>`;body.append(section);
  }
  document.addEventListener('click',event=>{
    let b=event.target.closest('[data-scenario-item]');if(b){select(b.dataset.scenarioItem,{scroll:matchMedia('(max-width:760px)').matches});return;}
    b=event.target.closest('[data-scenario-map]');if(b){window.AtlasMaps.openScenario(b.dataset.scenarioMap,b.dataset.scenarioKey,b.dataset.scenarioPoint||null);return;}
    b=event.target.closest('[data-scenario-catalogue]');if(b){window.AtlasTabs.show('atlas');window.AtlasApp.select('item',Number(b.dataset.scenarioCatalogue));$('#detail').scrollIntoView({block:'start'});}
  });
  for(const [id,key,event] of [['scenarioSearch','query','input'],['scenarioKind','kind','change'],['scenarioCategory','category','change']])$('#'+id).addEventListener(event,e=>{state[key]=e.target.value;renderList();});
  window.addEventListener('atlas:tabchange',event=>{if(event.detail.name==='scenario'){if(!new URLSearchParams(location.hash.slice(1)).has('scenario'))writeHash();renderList();}});
  window.addEventListener('atlas:selection',decorateDetail);
  window.addEventListener('hashchange',()=>{if(readHash()){renderList();renderDetail();}});
  document.addEventListener('keydown',event=>{if(event.key==='/'&&!$('#scenarioPage').hidden&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)){event.preventDefault();$('#scenarioSearch').focus();}});
  const guide=window.SF_SCENARIO_ITEMS;
  $('#scenarioTotals').innerHTML=`<div><b>${model.records.length}</b><span>EŞYA KAYDI</span></div><div><b>${guide?.fixedPlacements||0}</b><span>HAZIR KONUM</span></div><div><b>${model.records.filter(r=>r.sources.some(s=>s.kind==='trade')).length}</b><span>KART TAKASI</span></div>`;
  const routed=readHash();renderList();renderDetail();decorateDetail();
  window.AtlasScenario={model,state,select};if(routed)window.AtlasTabs.show('scenario');
})();
