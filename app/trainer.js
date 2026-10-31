(function(){
  'use strict';
  const extras=window.TRAINER_EXTRAS||[];
  let D={...window.TRAINER_DATA,records:[...window.TRAINER_DATA.records,...extras]};
  const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const records=new Map(D.records.map(r=>[r.id,r])),children=new Map(),snap=new Map(),drafts=new Map();
  for(const r of D.records){if(!children.has(r.parent))children.set(r.parent,[]);children.get(r.parent).push(r);}
  const categories=[['atlas','Atlas','Özel kontroller'],['table','CT tablosu','Kendi dosyan'],['reference','Kaynak & notlar','Yerel kaynak']];
  let category='atlas',query='',bridge=null,trainer={},busy=false,message='',reading=false,readAgain=false,readTimer=null,tableLoading=false;
  const normalize=v=>String(v).toLocaleLowerCase('tr-TR').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ı/g,'i');
  const ready=()=>bridge?.connected&&bridge?.ready&&bridge?.protocol>=19;
  const num=n=>Number(n).toLocaleString('tr-TR');
  window.addEventListener('atlas:tabchange',e=>{if(e.detail.name==='controls'){queueRead();window.AtlasLive?.refresh();}});
  document.addEventListener('click',e=>{const b=e.target.closest('[data-control-jump]');if(b){const target=document.getElementById(b.dataset.controlJump);(target?.closest('section')||target)?.scrollIntoView({behavior:'smooth',block:'start'});}});
  function path(r){const names=[];for(let p=records.get(r.parent);p;p=records.get(p.parent))names.unshift(p.label+' '+p.description);return names.join(' ');}
  function matches(r){return !query||normalize(r.label+' '+r.description+' '+path(r)).includes(normalize(query));}
  function descendants(r){return [r,...(children.get(r.id)||[]).flatMap(descendants)];}
  function hasMatch(r){return r.kind!=='group'&&matches(r)||(children.get(r.id)||[]).some(hasMatch);}
  function source(r){return r.script?`<details class="trainer-source"><summary>Kaynak betik</summary><pre>${esc(r.script)}</pre></details>`:'';}
  function leaf(r){
    if(!matches(r))return '';
    const title=`<div class="trainer-label"><b>${esc(r.label)}</b>${r.label!==r.description?`<small>${esc(r.description)}</small>`:''}${r.note?`<p>${esc(r.note)}</p>`:''}</div>`;
    if(r.kind==='toggle')return `<article class="cheat-card" data-record="${r.id}">${title}<button class="cheat-switch" data-toggle="${r.id}" role="switch" aria-checked="false" aria-label="${esc(r.label)}" disabled><span></span><b>Kapalı</b></button>${source(r)}</article>`;
    if(r.kind==='action')return `<article class="cheat-card action-card" data-record="${r.id}">${title}<button class="trainer-apply" data-action="${r.id}" disabled>Bir kez uygula</button>${source(r)}</article>`;
    if(r.kind==='connection')return `<article class="trainer-connection-note">${title}${source(r)}</article>`;
    if(r.kind==='unsupported')return `<article class="trainer-connection-note">${title}${source(r)}</article>`;
    if(r.kind!=='value')return '';
    const input=r.readOnly?'':r.choices?`<select data-input="${r.id}" aria-label="${esc(r.label)}">${r.choices.map(([v,n])=>`<option value="${v}">${esc(n)} · ${v}</option>`).join('')}</select>`:`<input data-input="${r.id}" type="text" inputmode="${r.type==='String'?'text':'numeric'}" aria-label="${esc(r.label)}" autocomplete="off" spellcheck="false" placeholder="${r.hex?'0x…':'Değer'}">`;
    return `<article class="trainer-value" data-record="${r.id}">${title}<div class="trainer-current"><span>OYUNDA</span><output data-current="${r.id}">—</output></div>${r.readOnly?'<span class="read-only-label">Adres · salt okunur</span>':`<div class="trainer-edit">${input}<button data-write="${r.id}" class="trainer-apply" disabled>Uygula</button>${r.type!=='String'?`<label class="freeze-label"><input type="checkbox" data-freeze="${r.id}" disabled> Sabitle</label>`:''}</div>`}<span class="value-message" data-error="${r.id}"></span></article>`;
  }
  function renderRecord(r,depth=0){
    if(!hasMatch(r))return '';
    const kids=children.get(r.id)||[];
    if(!kids.length)return leaf(r);
    const total=descendants(r).filter(x=>!['group','connection'].includes(x.kind)&&matches(x)).length;
    return `<details class="trainer-group" data-group="${r.id}" ${query||category==='cheats'||depth===0&&r.id==='953'?'open':''}><summary><span>${esc(r.label)}</span><small>${num(total)} kayıt</small></summary><div class="trainer-group-body">${r.kind!=='group'?leaf(r):''}${kids.map(x=>renderRecord(x,depth+1)).join('')}</div></details>`;
  }
  function render(){
    $('#trainerCategories').innerHTML=categories.map(([id,label,n])=>`<button data-category="${id}" class="${category===id?'active':''}" aria-pressed="${category===id}"><span>${label}</span><small>${n}</small></button>`).join('');
    let roots=[],body='';
    if(query){roots=D.records.filter(r=>r.parent===null||r.parent==='atlas-extras');}
    else if(category==='atlas'){roots=extras;}
    else if(category==='table'){roots=D.records.filter(r=>r.parent===null);}
    if(category==='reference'&&!query){
      body=`<div class="trainer-reference"><h4>Yerel tablo</h4><p>${esc(D.source)}</p><p>${num(D.counts.entries)} CT kaydı; ${D.structures.length} yapı tanımı. Tablo bu bilgisayarda tutulur ve paketlenmez. Lua çalıştırılmaz; desteklenmeyen komutlar uygulanmaz.</p><h4>Tablo notları</h4><pre>${esc(D.comments)}</pre><h4>Yapı tanımları</h4>${D.structures.map(s=>`<details class="trainer-source structure-source"><summary>${esc(s.name)} <small>${num(s.elements)} alan tanımı</small></summary><pre>${esc(s.xml)}</pre></details>`).join('')}</div>`;
    }
    else body=roots.map(r=>renderRecord(r)).join('');
    $('#trainerRecords').innerHTML=body||'<div class="trainer-empty">Bu adla kayıt bulunamadı. Türkçe veya özgün İngilizce adla arayabilirsin.</div>';
    $('#trainerGroupTitle').textContent=query?'Tablonun tamamında arama':categories.find(c=>c[0]===category)[1];
    $('#trainerCount').textContent=category==='reference'&&!query?D.structures.length+' yapı · kaynak notları':num(roots.flatMap(descendants).filter(r=>!['group','connection'].includes(r.kind)&&matches(r)).length)+' kayıt';
    $('#trainerTableSummary').textContent=D.sha256?`${D.counts.entries} CT kaydı · ${D.counts.supported} desteklenen denetim`:trainer.table?.discoveryMessage||'CT dosyanı oyun klasörüne koyabilir veya buradan seçebilirsin; Atlas kontrolleri hazır.';
    for(const [id,draft] of drafts){const input=$(`[data-input="${id}"]`);if(input)input.value=draft;}
    paint();queueRead();
  }
  function paint(){
    const available=ready(),connected=bridge?.connected&&bridge?.protocol>=19;
    $('#trainerCTFile').disabled=!connected||busy;
    $('#trainerCTRemove').disabled=!connected||busy||!D.sha256;
    const chip=$('#trainerConnection');chip.classList.toggle('connected',available);
    chip.querySelector('span').textContent=available?'Oyun bağlı · tek oyunculu':connected?'Karakterin oyuna girmesi bekleniyor':bridge?.connected?'Yardımcı güncellenmeli · başlatıcıyı tekrar aç':'Yerel yardımcı bekleniyor';
    $('#trainerRefresh').disabled=!available||busy||reading;$('#trainerUndo').disabled=!available||busy||!trainer.undoCount;
    $('#trainerReset').disabled=!connected||busy||!((trainer.active||[]).length+(trainer.frozen||[]).length);
    $('#trainerMessage').textContent=message||(!connected?'Canlı kontroller için CANLI-DROP-BASLAT.cmd veya ARAYUZ-DUZELT.cmd dosyasını çalıştır.':!available?bridge?.message||'Karakterini oyuna yükle.':trainer.message||'Değerler bağlı karakterden okunur. Değişiklikler Uygula’ya bastığında yapılır.');
    const active=new Set(trainer.active||[]),frozen=new Set(trainer.frozen||[]);
    $('#trainerActiveCount').textContent=active.size||frozen.size?`${active.size} hile açık · ${frozen.size} değer sabitleniyor.`:'Hiçbir hile açık değil.';
    for(const b of document.querySelectorAll('[data-toggle]')){const on=active.has(b.dataset.toggle),supported=!(records.get(b.dataset.toggle).minimumTrainerVersion>Number(trainer.version||0));b.disabled=busy||(!available&&!on)||!connected||!supported;b.title=supported?'':'Bu denetim için Atlas yardımcısını yeniden başlat.';b.setAttribute('aria-checked',String(on));b.classList.toggle('on',on);b.querySelector('b').textContent=on?'Açık':'Kapalı';b.closest('.cheat-card').classList.toggle('enabled',on);}
    for(const b of document.querySelectorAll('[data-action]'))b.disabled=!available||busy;
    for(const row of document.querySelectorAll('.trainer-value')){
      const id=row.dataset.record,r=records.get(id),v=available?snap.get(id):null,input=row.querySelector('[data-input]'),output=row.querySelector('output'),button=row.querySelector('[data-write]'),check=row.querySelector('[data-freeze]');
      const displayed=v&&(r.readOnly&&['Base address','Base pointer'].includes(r.description)?v.address:v.value);
      output.textContent=v&&!v.error?r.hex||r.readOnly?'0x'+Number(displayed).toString(16).toUpperCase():r.type==='String'?displayed:num(displayed):'—';
      row.querySelector('.value-message').textContent=v?.error||(!r.readOnly&&r.type==='String'&&v?`Ad alanı: en fazla ${v.maxBytes} bayt.`:'');
      if(input){input.disabled=!available||busy||!v||!!v.error;if(v&&!v.error&&!drafts.has(id)&&document.activeElement!==input)input.value=r.hex?'0x'+Number(v.value).toString(16):String(v.value);if(r.type==='String'&&v)input.maxLength=v.maxBytes;}
      if(button)button.disabled=!available||busy||!v||!!v.error;
      if(check){check.disabled=!available||busy||!v||!!v.error;if(document.activeElement!==check&&!drafts.has('freeze:'+id))check.checked=frozen.has(id);}
    }
  }
  function visibleIds(){
    if($('#controlsPage').hidden)return [];
    return [...document.querySelectorAll('.trainer-value')].filter(row=>{for(let p=row.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open)return false;return true;}).map(row=>row.dataset.record);
  }
  function queueRead(){clearTimeout(readTimer);readTimer=setTimeout(read,100);}
  async function read(){
    if(reading){readAgain=true;return;}const ids=visibleIds();if(!ready()||!ids.length)return;
    reading=true;paint();
    try{const result=await window.AtlasLive.request('/api/trainer/read',{ids});for(const [id,value] of Object.entries(result.values))snap.set(id,value);trainer=result;}
    catch(error){message=error.message;}
    finally{reading=false;paint();if(readAgain){readAgain=false;queueRead();}}
  }
  async function command(path,body,success){
    if(busy)return;busy=true;message='Oyuna uygulanıyor…';paint();
    try{trainer=await window.AtlasLive.request('/api/trainer/'+path,body);message=success||trainer.message;await window.AtlasLive.refresh();queueRead();}
    catch(error){message=error.message;}
    finally{busy=false;paint();}
  }
  $('#trainerSearch').addEventListener('input',e=>{query=e.target.value;render();});
  $('#trainerCategories').addEventListener('click',e=>{const b=e.target.closest('[data-category]');if(!b)return;category=b.dataset.category;query='';$('#trainerSearch').value='';render();});
  $('#trainerRecords').addEventListener('toggle',e=>{if(e.target.matches('.trainer-group'))queueRead();},true);
  $('#trainerRecords').addEventListener('input',e=>{if(e.target.dataset.input)drafts.set(e.target.dataset.input,e.target.value);});
  $('#trainerRecords').addEventListener('change',e=>{
    const id=e.target.dataset.freeze;if(!id)return;drafts.set('freeze:'+id,String(e.target.checked));
    if(!e.target.checked&&(trainer.frozen||[]).includes(id))command('unfreeze',{id},'Sabitleme kapatıldı.');
  });
  $('#trainerRecords').addEventListener('click',e=>{
    const toggle=e.target.closest('[data-toggle]'),action=e.target.closest('[data-action]'),write=e.target.closest('[data-write]');
    if(toggle&&!toggle.disabled)command('toggle',{id:toggle.dataset.toggle,enabled:toggle.getAttribute('aria-checked')!=='true'});
    else if(action&&!action.disabled)command('action',{id:action.dataset.action});
    else if(write&&!write.disabled){
      const id=write.dataset.write,r=records.get(id),input=$(`[data-input="${id}"]`),value=r.type==='String'?input.value:Number(input.value.trim());
      if(r.type!=='String'&&(!input.value.trim()||!Number.isInteger(value))){message='Geçerli bir tam sayı gir.';paint();return;}
      command('write',{id,value,binding:snap.get(id)?.binding,freeze:!!$(`[data-freeze="${id}"]`)?.checked},'Değer uygulandı.').then(()=>{drafts.delete('freeze:'+id);});
    }
  });
  $('#trainerRefresh').addEventListener('click',()=>{message='';queueRead();});
  $('#trainerUndo').addEventListener('click',()=>command('undo',{},'Son değer işlemi geri alındı.'));
  $('#trainerReset').addEventListener('click',()=>command('reset',{},'Açık trainer hileleri ve sabitlemeler kapatıldı.'));
  function installTable(data){
    D={...data,records:[...data.records,...extras]};records.clear();children.clear();snap.clear();drafts.clear();
    for(const r of D.records){records.set(r.id,r);if(!children.has(r.parent))children.set(r.parent,[]);children.get(r.parent).push(r);}
    render();
  }
  async function tableRequest(route,body){
    if(busy)return;busy=true;paint();
    try{const data=await window.AtlasLive.request('/api/trainer/'+route,body);installTable(data);message=route==='import'?'CT eklendi; kayıtlar bu bilgisayarda saklanır.':'Yerel CT kaldırıldı.';await window.AtlasLive.refresh();}
    catch(error){message=error.message;}
    finally{busy=false;paint();}
  }
  $('#trainerCTFile').addEventListener('change',async e=>{
    const file=e.target.files?.[0];if(!file)return;
    try{if(file.size>4*1024*1024)throw new Error('CT dosyası 4 MB sınırını aşamaz.');await tableRequest('import',{filename:file.name,content:await file.text()});}
    catch(error){message=error.message;paint();}finally{e.target.value='';}
  });
  $('#trainerCTRemove').addEventListener('click',()=>tableRequest('remove',{}));
  window.addEventListener('atlas:live-state',e=>{
    const changed=bridge?.pid!==e.detail.pid||bridge?.player!==e.detail.player;bridge=e.detail;if(changed){snap.clear();drafts.clear();message='';}trainer=bridge.trainer||{};paint();queueRead();
    if(!D.sha256)$('#trainerTableSummary').textContent=trainer.table?.discoveryMessage||'CT dosyanı oyun klasörüne koyabilir veya buradan seçebilirsin; Atlas kontrolleri hazır.';
    if(bridge.protocol>=19&&trainer.table&&trainer.table.sha256!==D.sha256&&!tableLoading){
      tableLoading=true;window.AtlasLive.request('/api/trainer/table',{}).then(installTable).catch(error=>{message=error.message;}).finally(()=>{tableLoading=false;paint();});
    }
  });
  document.addEventListener('keydown',e=>{if(!$('#controlsPage').hidden&&e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){e.preventDefault();$('#trainerSearch').focus();}});
  render();setInterval(()=>{if(!busy&&!$('#controlsPage').hidden)queueRead();},4000);
})();
