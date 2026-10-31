(function(){
  'use strict';
  const $=s=>document.querySelector(s),D=window.ATLAS_DATA,V=window.SF_VISUALS,items=D.items.filter(i=>i.rarity===2);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize=window.atlasNormalize,fmt=n=>Number(n).toLocaleString('tr-TR');
  const standardDrops=new Set();
  for(const group of new Set(D.mobs.flatMap(m=>m.variants.map(v=>v.group))))for(const rows of Object.values(D.groups[group]?.data||{}))for(const row of rows)if(row[1]>0)standardDrops.add(row[0]);
  let data=null,connected=false,busy=false,loading=false,again=false,selected=null,page=1,follow=true,toastEvent=null,errorMessage='';
  const noticeSeen=new Set();let noticeReady=false;
  const date=value=>value?new Date(value).toLocaleString('tr-TR',{dateStyle:'short',timeStyle:'short'}):'';
  const evidence=e=>e?.first_pickup?'pickup':e?.manual?'manual':e?.first_owned?'owned':'missing';
  const labels={pickup:'✦ YERDEN TOPLANDI',manual:'✓ ELLE İŞARETLENDİ',owned:'◇ TAKİP ÖNCESİNDE MEVCUT',missing:'KAYDI YOK'};
  const mapName=id=>D.maps.find(m=>m.id===String(id).padStart(8,'0'))?.name||('Bölge '+id);
  function render(){
    const profiles=data?.profiles||[],profile=profiles.find(p=>p.id===selected),entries=data?.selected===selected?data?.entries||{}:{};
    const known=items.filter(i=>evidence(entries[i.key])!=='missing').length,picked=items.filter(i=>evidence(entries[i.key])==='pickup').length,owned=items.filter(i=>evidence(entries[i.key])==='owned').length,manual=known-picked-owned;
    const options=profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)} · Lv ${p.level} · ${esc(p.save_file)}${p.id===data.current?' · açık':''}</option>`).join('')||'<option value="">Karakter bekleniyor…</option>';
    if($('#grailCharacter').innerHTML!==options)$('#grailCharacter').innerHTML=options;
    $('#grailCharacter').value=selected||'';$('#grailCharacter').disabled=!profiles.length||busy;
    $('#grailRefresh').disabled=!connected||loading||busy;$('#grailExport').disabled=!profile;
    $('#grailKnown').textContent=fmt(known);$('#grailTotal').textContent=fmt(items.length);$('#grailProgress').max=items.length;$('#grailProgress').value=known;
    $('#grailBreakdown').textContent=profile?`${fmt(picked)} yerden toplandı · ${fmt(owned)} takip öncesinde mevcut · ${fmt(manual)} elle işaretli · ${fmt(items.length-known)} eksik`:'Karakter seçerek koleksiyonunu gör.';
    $('#grailStatus').textContent=errorMessage||(!connected?'Grail için start.cmd ile yerel yardımcıyı aç.':data?.missedEvents?`Takip kaydında ${fmt(data.missedEvents)} olay kaçırıldı; liste eksik olabilir.`:data?.active?`${data.message} ${profile?.id!==data.current?'Şu anda başka bir karakterin günlüğünü görüntülüyorsun.':''}`:data?.message||'Karakter bekleniyor.');
    const query=normalize($('#grailSearch').value.trim()),filter=$('#grailFilter').value,cat=$('#grailCategory').value,sort=$('#grailSort').value;
    let result=items.filter(i=>{const state=evidence(entries[i.key]);return (!query||normalize(i.name+' '+i.base+' '+i.key).includes(query))&&(cat==='all'||String(i.cat)===cat)&&(filter==='all'||filter===state||filter==='found'&&state!=='missing'||filter==='no-source'&&!standardDrops.has(i.id));});
    result.sort((a,b)=>sort==='level'?(a.level??999)-(b.level??999)||a.name.localeCompare(b.name):sort==='recent'?String(entries[b.key]?.first_pickup||'').localeCompare(String(entries[a.key]?.first_pickup||''))||a.name.localeCompare(b.name):a.name.localeCompare(b.name));
    const pages=Math.max(1,Math.ceil(result.length/48));page=Math.min(page,pages);$('#grailResultCount').textContent=fmt(result.length)+' / '+fmt(items.length)+' kayıt';
    $('#grailGrid').innerHTML=result.slice((page-1)*48,page*48).map(i=>{const e=entries[i.key],state=evidence(e),icon=V.items[i.key];return `<article class="grail-card ${state==='missing'?'missing':'found'}" data-grail-key="${esc(i.key)}"><span class="grail-evidence">${labels[state]}</span><a class="grail-art" href="#item=${i.id}" aria-label="${esc(i.name)} ayrıntıları">${icon?`<img src="${esc(icon.src)}" alt="${esc(i.name)}" loading="lazy">`:'◇'}</a><h3>${esc(i.name)}</h3><p class="grail-meta">${['Silah','Zırh','Aksesuar'][i.cat]} · Seviye ${i.level??'—'} · #${esc(i.key)}</p>${standardDrops.has(i.id)?'':'<p class="grail-source-note">Standart yaratık drop havuzunda yok.</p>'}<p class="grail-when">${state==='pickup'?esc(date(e.first_pickup))+'<br>'+esc(mapName(e.first_map)):state==='owned'?'Bulunma tarihi bilinmiyor.':state==='manual'?'Kendi hatırana göre işaretlendi.':'Bu karakterin günlüğünde henüz yok.'}</p><div class="grail-actions"><a href="#item=${i.id}">İncele ↗</a><button data-grail-mark="${esc(i.key)}" aria-label="${esc(i.name)} ${e?.manual?'elle işaretini kaldır':'buldum olarak işaretle'}" aria-pressed="${Boolean(e?.manual)}"${!profile||!connected||busy||e?.first_pickup||e?.first_owned?' disabled':''}>${e?.manual?'✓ Buldum':'Buldum'}</button></div></article>`;}).join('')||'<div class="grail-empty">Bu filtrelerle eşleşen Premium yok.</div>';
    $('#grailPagination').innerHTML=pages>1?`<button id="grailPrev"${page===1?' disabled':''}>← Önceki</button><span>${page} / ${pages}</span><button id="grailNext"${page===pages?' disabled':''}>Sonraki →</button>`:'';
    const journal=items.filter(i=>entries[i.key]?.first_pickup).sort((a,b)=>entries[b.key].first_pickup.localeCompare(entries[a.key].first_pickup)).slice(0,12);
    $('#grailJournal').innerHTML=journal.map(i=>{const e=entries[i.key];return `<a class="grail-journal-entry" href="#item=${i.id}"><b>${esc(i.name)}</b><small>${esc(date(e.first_pickup))}<br>${esc(mapName(e.first_map))} · ${fmt(e.pickups)} toplama</small></a>`;}).join('')||'<p>İlk Premium’un çantaya girdiğinde bu sayfa yazılmaya başlayacak.</p>';
  }
  async function refresh(){
    if(!connected)return;
    if(loading){again=true;return;}loading=true;
    try{const next=await window.AtlasLive.request('/api/live/grail',{action:'read',profile:follow?null:selected});const changed=JSON.stringify(next)!==JSON.stringify(data);data=next;selected=data.selected;errorMessage='';if(changed)render();}
    catch(error){errorMessage=error.message;$('#grailStatus').textContent=errorMessage;}
    finally{loading=false;$('#grailRefresh').disabled=!connected||busy;if(again){again=false;refresh();}}
  }
  function notify(info){
    for(const event of info?.recent||[]){
      const id=event.profile+'|'+event.key+'|'+event.time;
      if(!noticeSeen.has(id)&&noticeReady&&event.first){toastEvent=event;$('#grailToastName').textContent=event.name;const character=data?.profiles.find(p=>p.id===event.profile)?.name;$('#grailToastCharacter').textContent=(character?character+' · ':'')+date(event.time);$('#grailToast').hidden=false;}
      noticeSeen.add(id);
    }
    noticeReady=true;
  }
  window.addEventListener('atlas:live-state',event=>{const b=event.detail;connected=Boolean(b.connected&&b.grail?.version>=1);notify(b.grail);if(!connected){render();return;}if(!$('#grailPage').hidden||!data)refresh();});
  window.addEventListener('atlas:tabchange',event=>{if(event.detail.name==='grail')refresh();});
  $('#grailCharacter').addEventListener('change',()=>{selected=$('#grailCharacter').value;follow=false;$('#grailFollow').checked=false;page=1;refresh();});
  $('#grailFollow').addEventListener('change',()=>{follow=$('#grailFollow').checked;page=1;refresh();});
  for(const id of ['grailSearch','grailFilter','grailCategory','grailSort'])$('#'+id).addEventListener(id==='grailSearch'?'input':'change',()=>{page=1;render();});
  $('#grailRefresh').addEventListener('click',refresh);
  document.addEventListener('keydown',event=>{if(event.key==='/'&&!$('#grailPage').hidden&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){event.preventDefault();$('#grailSearch').focus();}});
  document.addEventListener('click',async event=>{
    if(event.target.closest('#grailPrev')){page--;render();return;}if(event.target.closest('#grailNext')){page++;render();return;}
    const button=event.target.closest('[data-grail-mark]');if(!button||button.disabled||busy)return;
    busy=true;errorMessage='';const key=button.dataset.grailMark,found=!data.entries[key]?.manual;render();
    try{data=await window.AtlasLive.request('/api/live/grail',{action:'mark',profile:selected,key,found});}
    catch(error){errorMessage=error.message;}
    finally{busy=false;render();}
  });
  $('#grailExport').addEventListener('click',()=>{if(!data?.selected)return;const p=data.profiles.find(p=>p.id===data.selected);const body={format:'shadowflare-grail-v1',exported:new Date().toISOString(),profile:p,entries:data.entries};const url=URL.createObjectURL(new Blob([JSON.stringify(body,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='ShadowFlare-Grail-'+p.save_file+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  // The notice follows the script in HTML; defer binding until parsing completes.
  document.addEventListener('DOMContentLoaded',()=>{
    $('#grailToastClose').addEventListener('click',()=>{$('#grailToast').hidden=true;});
    $('#grailToastOpen').addEventListener('click',()=>{if(toastEvent){selected=toastEvent.profile;follow=false;$('#grailFollow').checked=false;}$('#grailToast').hidden=true;window.AtlasTabs.show('grail');});
  });
  render();
})();
