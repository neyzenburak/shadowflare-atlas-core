(function(){
  'use strict';
  let bridge=null,bridgeConnected=false,busy=false,job=null,lastMessage='',selectedKey='',eventBusy=false,eventMessage='',appliedPolicy='',eventOptionsEdited=false,eventFactorEdited=false,displayMessage='',quickSellMessage='',beamMessage='',homingMessage='',launchMessage='',launchEdited=false,launchLoaded=false;
  const isLocal=location.protocol==='http:'&&['127.0.0.1','localhost'].includes(location.hostname)&&location.port==='8770';
  const $=s=>document.querySelector(s),range=$('#eventMultiplierRange'),number=$('#eventMultiplierNumber'),premiumOnly=$('#eventPremiumOnly'),excludeFound=$('#eventExcludeFound');
  const text=(node,value)=>{if(node&&node.textContent!==value)node.textContent=value;};
  const format=n=>Math.round(n).toLocaleString('tr-TR');
  let qolMessage='',radiusEdited=false;
  let magicMessage='';
  let teleportMessage='';
  let omegaMessage='';
  let mobMessage='',jobKind='item',mobQuantity=1;
  let experienceMessage='',experienceEdited=false,levelMessage='',levelBinding='';
  let travelMap=null,travelMessage='';
  let groundMessage='',groundSaleMessage='';
  if(window.AtlasMaps){const maps=window.AtlasMaps,index=maps.state.map,record=maps.model.maps[index];if(record)travelMap={id:record.id,name:record.name,playable:index<window.ATLAS_DATA.maps.length};}
  const experienceRange=$('#experienceRange'),experienceNumber=$('#experienceNumber'),levelNumber=$('#levelRewindNumber');
  const pickupRange=$('#pickupRadiusRange'),pickupNumber=$('#pickupRadiusNumber');
  for(const [id,key] of [['mapTravelSave','shadowflare.saveBefore.mapTravel'],['groundSaleSave','shadowflare.saveBefore.groundSale']]){
    const checkbox=$('#'+id);
    try{checkbox.checked=localStorage.getItem(key)==='true';}catch{checkbox.checked=false;}
    checkbox.addEventListener('change',()=>{
      try{localStorage.setItem(key,String(checkbox.checked));}catch{}
      paint();
    });
  }
  const baseline=new AtlasModel(window.ATLAS_DATA),tesla=baseline.itemByKey.get('0:80000127');
  const boss=window.ATLAS_DATA.mobs.find(m=>m.name==='Devil Dignosis'),bossVariant=boss?.variants.find(v=>v.group===292);
  const reference=tesla&&bossVariant?baseline.chance(bossVariant,tesla.id):0;
  function preview(){
    const m=Number(number.value);
    if(!Number.isInteger(m)||m<1||m>1000){text($('#eventPreview'),'1–1000 arasında bir tam sayı gir.');return;}
    const p=reference?-Math.expm1(m*Math.log1p(-reference)):0;
    text($('#eventPreview'),`Önizleme ×${format(m)} · 1 normal tur → ${format(m)} tur; 10 denemeli boss → ${format(10*m)} deneme.`+(p?` Tesla Blade 80 / Devil Dignosis: yaklaşık 1 / ${format(1/reference)} → 1 / ${format(1/p)} öldürme.`:'')+(premiumOnly.checked?' Ek turlardan yalnızca Premium çıkar.':' Mine ve altın normal oranında kalır.')+(excludeFound.checked?' Grail’de bulunan Premium sonuçlar ilk tur dahil elenir.':' İlk normal tur korunur.'));
  }
  function paint(){
    const travel=bridgeConnected?bridge?.mapTravel:null,travelReady=isLocal&&bridgeConnected&&bridge?.ready&&bridge?.protocol>=17&&travel?.version>=4&&travel?.canTravel;
    $('#travelToMap').disabled=!travelReady||!travelMap?.playable||busy||eventBusy;
    $('#mapTravelSave').disabled=$('#groundSaleSave').disabled=busy||eventBusy;
    text($('#mapTravelCurrent'),travel?.ready?`Şu an: ${travel.currentName}.`:'');
    text($('#mapTravelStatus'),travelMap&&!travelMap.playable?'Bu görselin oynanabilir senaryosu ve giriş noktası yok.':travelMessage||(!isLocal?'Oyunda ışınlanmak için start.cmd ile yerel Atlas’ı aç.':!travelMap?'Önce bir harita seç.':!(bridge?.protocol>=17&&travel?.version>=4)?'İsteğe bağlı kayıt için start.cmd dosyasını yeniden aç.':travel.message||`${travelMap.name} girişine git. `+($('#mapTravelSave').checked?'Önce kaydedilip yedeklenir. ':'')+'İşlem sırasında oyuna dön.'));
    const experience=bridgeConnected?bridge?.experience:null,experienceReady=isLocal&&bridgeConnected&&bridge?.ready&&experience?.version>=1;
    $('#applyExperience').disabled=!experienceReady||busy||eventBusy;
    $('#stopExperience').disabled=!isLocal||!bridgeConnected||busy||eventBusy||!experience?.active;
    experienceRange.disabled=experienceNumber.disabled=!experienceReady||busy||eventBusy;
    if(experience&&!experienceEdited&&!eventBusy)experienceRange.value=experienceNumber.value=experience.multiplier;
    $('#experienceEvent').classList.toggle('active',experience?.active===true);
    text($('#experienceStatus'),experienceMessage||(experience?.message|| (experience?`Uygulanan EXP çarpanı: ×${format(experience.multiplier)}.`+(experience.awards?` Son kazanım: ${format(experience.lastRaw)} → ${format(experience.lastAwarded)} EXP.`:''):isLocal?'EXP etkinliği için start.cmd dosyasını yeniden aç.':'Canlı EXP etkinliği için yerel başlatıcıyı aç.')));
    const character=bridgeConnected?bridge?.levelControl:null,levelReady=isLocal&&bridgeConnected&&bridge?.ready&&character?.ready&&character?.version>=1;
    $('#applyLevelRewind').disabled=!levelReady||character.level<=1||busy||eventBusy;
    levelNumber.disabled=!levelReady||busy||eventBusy;
    if(levelReady){
      levelNumber.max=character.level-1;
      if(levelBinding!==character.binding){levelBinding=character.binding;levelNumber.value=Math.max(1,character.level-1);}
    }
    text($('#levelRewindCurrent'),levelReady?`${character.name} · Seviye ${character.level}`:'');
    text($('#levelRewindStatus'),levelMessage||(levelReady?`Mevcut EXP: ${format(character.exp)}`+(character.required?` / ${format(character.required)}.`:' · En yüksek seviye.'):(character?.message||'Karakter bekleniyor.')));
    const omega=bridgeConnected?bridge?.omegaBeam:null,omegaReady=isLocal&&bridgeConnected&&omega?.version>=3;
    $('#applyOmegaBeam').disabled=!omegaReady||busy||eventBusy||omega?.requested;
    $('#stopOmegaBeam').disabled=!omegaReady||busy||eventBusy||!omega?.requested;
    text($('#omegaBeamStatus'),omegaMessage||(omega?.message||'Omega ışını için güncel başlatıcıyı aç.'));
    const meteor=omega?.skill==='meteor';
    $('#specialSkillSelect').disabled=!omegaReady||busy||eventBusy;
    $('#specialSurprise').disabled=!omegaReady||!meteor||busy||eventBusy;
    if(!eventBusy){$('#specialSkillSelect').value=omega?.skill||'omega';$('#specialSurprise').checked=omega?.surprise===true;}
    $('#specialSurpriseWrap').hidden=!meteor;
    text($('#specialSkillDescription'),meteor?'Warrior · sol Alt + sağ tık. Ekrandaki her yaratığı izleyen '+(omega?.surprise?'nükleer başlıklar.':'meteorlar.'):'Warrior · sol Alt + hedefe sağ tık. Omega ışını yaklaşık 1 saniyede ulaşır.');
    text($('#specialSkillNote'),meteor?'Yere düştüğü anda yeniden atabilirsin. '+(omega?.surprise?'Mantar bulutu':'Alev')+' 3 saniye kalır. Her hedefe kullanım başına bir kez Attack ×3; örtüşen efektler ek hasar vermez.':'Paneller kapalıyken kullan. Duvarları dolaşır; yol yoksa engelde söner.');
    const teleport=bridgeConnected?bridge?.ctrlTeleport:null,teleportReady=isLocal&&bridgeConnected&&teleport?.version>=1;
    $('#applyCtrlTeleport').disabled=!teleportReady||busy||eventBusy||teleport?.requested;
    $('#stopCtrlTeleport').disabled=!teleportReady||busy||eventBusy||!teleport?.requested;
    text($('#ctrlTeleportStatus'),teleportMessage||(teleport?.active?`Açık · ${format(teleport.teleports)} kez ışınlandın.`:teleport?.message||'Güncel başlatıcıyı aç.'));
    const gold=bridgeConnected?bridge?.goldCapacity:null;
    text($('#goldCapacityStatus'),gold?.active?'Açık · kese başına 2.147.483.647 altın.':gold?.message||'Altın kesesi için güncel başlatıcıyı aç.');
    const magic=bridgeConnected?bridge?.magicBeam:null,magicReady=isLocal&&bridgeConnected&&magic?.version>=1;
    $('#applyMagicBeam').disabled=!magicReady||busy||eventBusy||magic?.requested;
    $('#stopMagicBeam').disabled=!magicReady||busy||eventBusy||!magic?.requested;
    text($('#magicBeamStatus'),magicMessage||(magic?.active?`Açık · Görünen mavi ışın: ${format(magic.visible)} · bütün değişken bonuslar %80+.`:magic?.message||'Mavi ışın için güncel başlatıcıyı aç.'));
    const homing=bridgeConnected?bridge?.homingShots:null,homingReady=isLocal&&bridgeConnected&&homing?.version>=1;
    $('#applyHomingShots').disabled=!homingReady||busy||eventBusy||homing?.requested;
    $('#stopHomingShots').disabled=!homingReady||busy||eventBusy||!homing?.requested;
    text($('#homingShotsStatus'),homingMessage||(homing?.active?`Açık · ${format(homing.converted)} ok/taş takibe alındı.`:homing?.message||'Güdümlü atış için güncel başlatıcıyı aç.'));
    const qol=bridgeConnected?bridge?.lootQoL:null,qolReady=isLocal&&bridgeConnected&&qol?.version>=6,qolOutdated=qol&&qol.version<6;
    for(const [id,property,enabled] of [['applyAutoPickup','autoPickup',true],['stopAutoPickup','autoPickup',false],['applyPotionStack','potionStacks',true],['stopPotionStack','potionStacks',false]])$('#'+id).disabled=!qolReady||busy||eventBusy||qol[property]===enabled;
    $('#applyPickupRadius').disabled=!qolReady||busy||eventBusy;
    if(qol&&!radiusEdited&&document.activeElement!==pickupNumber&&document.activeElement!==pickupRange)pickupNumber.value=pickupRange.value=qol.radius;
    text($('#autoPickupStatus'),qolMessage||(qolOutdated?'Ganimet düzeltmesi için start.cmd dosyasını yeniden aç.':qol?.active?(qol.autoPickup?`Açık · ×${qol.radius} halka · ${format(qol.pickedUp)} eşya toplandı.`:'Otomatik toplama kapalı.'):qol?.message||'Yerel yardımcı bekleniyor.'));
    text($('#potionStackStatus'),qolMessage||(qolOutdated?'Identify düzeltmesi için start.cmd dosyasını yeniden aç.':qol?.active?(qol.potionStacks?`Açık · ${format(qol.mergedUnits)} adet birleştirildi · yığın başına 999.`:'Yeni birleştirme kapalı; mevcut yığınlar kullanılabilir.'):qol?.message||'Yerel yardımcı bekleniyor.'));
    const beam=bridgeConnected?bridge?.premiumBeam:null,beamReady=isLocal&&bridgeConnected&&beam?.version>=1;
    $('#applyPremiumBeam').disabled=!beamReady||busy||eventBusy||beam?.requested;
    $('#stopPremiumBeam').disabled=!beamReady||busy||eventBusy||!beam?.requested;
    text($('#premiumBeamStatus'),beamMessage||(beam?.active?`Açık · Görünen Premium ışını: ${format(beam.visible)} · Grail’de eksik, kırmızı yörüngeli: ${format(beam.missingVisible||0)}.`:beam?.message||'Premium ışını için güncel başlatıcıyı aç.'));
    const display=bridgeConnected?bridge?.display:null,displayReady=isLocal&&bridgeConnected&&bridge?.protocol>=3;
    $('#applyDisplayFix').disabled=!displayReady||busy||eventBusy||display?.active||display?.pending;
    $('#stopDisplayFix').disabled=!displayReady||busy||eventBusy||!(display?.active||display?.pending);
    text($('#displayFixStatus'),displayMessage||(display?.active?`Düzeltme açık · ${display.width} × ${display.height}. Envanter sağda; potların sağ tık alanı HUD ile aynı konumda.${display.rainFullScreen?' Yağmur tüm ekranda.':''}`:display?.message|| (displayReady?'Oyuna bağlı. Düzeltme uygulanabilir.':'Güncel yardımcı için ARAYUZ-DUZELT.cmd dosyasını çalıştır.')));
    const stability=bridgeConnected?bridge?.stability:null;
    text($('#hoverLifetimeStatus'),stability?.active?'Yoğun drop düzeltmesi açık · eşya sayısı sınırlandırılmıyor.':stability?.message?('Yoğun drop düzeltmesi: '+stability.message):isLocal?'Yoğun drop düzeltmesi için güncel başlatıcıyı yeniden aç.':'Yoğun drop düzeltmesi, yerel yardımcıyla otomatik etkinleşir.');
    const performance=bridgeConnected?bridge?.renderPerformance:null;
    text($('#renderSortStatus'),performance?.active?'Yoğun drop performans düzeltmesi açık · bütün eşyalar özgün çizim sırasıyla gösterilir.':performance?.message?('Çizim performansı: '+performance.message):isLocal?'Performans düzeltmesi için güncel başlatıcıyı yeniden aç.':'Performans düzeltmesi, yerel yardımcıyla otomatik etkinleşir.');
    const quick=bridgeConnected?bridge?.quickSell:null,quickReady=isLocal&&bridgeConnected&&quick?.version>=1;
    $('#applyQuickSell').disabled=!quickReady||busy||eventBusy||quick?.requested;
    $('#stopQuickSell').disabled=!quickReady||busy||eventBusy||!quick?.requested;
    text($('#quickSellStatus'),quickSellMessage||(quick?.active?`Açık · Bu oturumda ${format(quick.sold)} eşya satıldı.`:quick?.message||'Sağ tıkla satış için güncel başlatıcıyı aç.'));
    const ground=bridgeConnected?bridge?.groundLoot:null,groundReady=isLocal&&bridgeConnected&&ground?.version>=1;
    $('#hideGroundLoot').disabled=!groundReady||busy||eventBusy||ground?.requested;
    $('#showGroundLoot').disabled=!groundReady||busy||eventBusy||!ground?.requested;
    $('#sellGroundLoot').disabled=!groundReady||!(bridge?.protocol>=17&&ground?.version>=2)||!bridge?.ready||qol?.version<7||!qol?.active||busy||eventBusy;
    text($('#groundLootStatus'),groundMessage||(ground?.message||'Ganimet görünürlüğü için güncel başlatıcıyı aç.'));
    text($('#groundSaleStatus'),groundSaleMessage);
    for(const block of document.querySelectorAll('.live-drop-block:not(.live-mob-block)')){
      const button=block.querySelector('button'),message=block.querySelector('.live-drop-status');
      button.disabled=!isLocal||!bridge?.ready||busy||eventBusy;
      text(message,lastMessage||(!isLocal?'Canlı drop için CANLI-DROP-BASLAT.cmd dosyasını çalıştır.':bridge?.ready?'Oyun bağlı. Her tıklama seçili kayıttan bir eşya bırakır.':bridge?.message||'Oyun bağlantısı kontrol ediliyor…'));
    }
    for(const block of document.querySelectorAll('.live-mob-block')){
      const supported=bridgeConnected&&bridge?.mobSpawn?.version>=3;
      block.querySelector('button').disabled=!isLocal||!supported||!bridge?.ready||busy||eventBusy;
      const input=block.querySelector('#liveMobQuantity');input.disabled=busy||eventBusy;
      if(document.activeElement!==input)input.value=mobQuantity;
      const undo=block.querySelector('[data-live-mob-cleanup]');
      if(undo)undo.disabled=!isLocal||!bridgeConnected||!bridge?.ready||bridge?.mobSpawn?.version<4||busy||eventBusy;
      text(block.querySelector('.live-mob-status'),mobMessage||(!isLocal?'Canlı doğurma için start.cmd dosyasını aç.':!supported?'Güncel yardımcı için start.cmd dosyasını yeniden aç.':bridge?.ready?'Oyun bağlı. Her tıklama AI kapalı bir yaratık doğurur.':bridge?.message||'Oyun bağlantısı bekleniyor…'));
    }
    const event=bridge?.event,available=isLocal&&bridgeConnected&&bridge?.ready&&bridge?.protocol>=2&&event?.version>=5;
    $('#applyDropEvent').disabled=!available||busy||eventBusy;
    $('#stopDropEvent').disabled=!isLocal||!event?.active||busy||eventBusy;
    premiumOnly.disabled=!available||busy||eventBusy;
    excludeFound.disabled=!available||busy||eventBusy;
    if(event){
      const multiplier=event.active?event.multiplier:1,mode=event.premiumOnly===true,exclude=event.excludeFound===true;
      if(!eventFactorEdited&&!eventBusy&&Number(number.value)!==multiplier){number.value=multiplier;range.value=Math.min(100,multiplier);preview();}
      if(!eventOptionsEdited&&!eventBusy&&premiumOnly.checked!==mode){premiumOnly.checked=mode;preview();}
      if(!eventOptionsEdited&&!eventBusy&&excludeFound.checked!==exclude){excludeFound.checked=exclude;preview();}
      text($('#eventActiveFactor'),'×'+format(multiplier));text($('#eventBadgeLabel'),event.active?(mode?'YALNIZCA PREMIUM':'ETKİNLİK AÇIK'):event.filterActive?'GRAİL FİLTRESİ':'NORMAL DROP');
      $('#dropEvent').classList.toggle('active',event.active||event.filterActive);
      const foundKeys=event.foundKeys||[],signature=JSON.stringify([multiplier,mode,exclude,foundKeys]);
      if(signature!==appliedPolicy){appliedPolicy=signature;window.dispatchEvent(new CustomEvent('atlas:drop-multiplier',{detail:{multiplier,premiumOnly:mode,excludeFound:exclude,foundKeys}}));}
    }
    text($('#eventStatus'),eventMessage||(!isLocal?'Canlı çarpan için CANLI-DROP-BASLAT.cmd dosyasını çalıştır.':!bridge?'Oyun bağlantısı kontrol ediliyor…':!(event?.version>=5)?'Grail filtresi için start.cmd dosyasını yeniden aç.':event?.active||event?.filterActive?`×${format(event.multiplier)} etkin. Düşman dropları: ${format(event.monsterDrops)} · tamamlanan turlar: ${format(event.nativeRounds)}.`+(event.premiumOnly&&event.active?` Ek turlar: ${format(event.bonusPremiumsAccepted||0)} Premium kabul edildi, ${format(event.bonusNonPremiumsSkipped||0)} diğer eşya elendi.`:' Mine ve altın ×1.')+(event.excludeFound?(event.grailReady?` Grail filtresi: ${format(event.duplicatesSkipped||0)} bulunan Premium elendi.`:' Grail kaydı bekleniyor; sonuçlar henüz elenmez.'):''):event?.message||bridge.message||'Yerel yardımcıya erişilemiyor.'));
  }
  function paintLauncher(){
    const l=bridgeConnected?bridge?.launcher:null,ok=isLocal&&bridgeConnected&&bridge?.protocol>=19&&l;
    if(l&&!launchEdited&&!launchLoaded){$('#gameLaunchWidth').value=l.width;$('#gameLaunchHeight').value=l.height;$('#gameLaunchPath').value=l.gamePath||'';launchLoaded=true;}
    $('#startGame').disabled=!ok||busy||eventBusy||l?.running;
    $('#saveGameLaunch').disabled=!ok||busy||eventBusy;
    text($('#gameLaunchStatus'),launchMessage||(l?.running?'ShadowFlare açık. Kaydettiğin çözünürlük sonraki açılışta uygulanır.':l?.message|| (ok?'Çözünürlüğü seçip oyunu buradan açabilirsin.':'Oyunu Atlas’tan açmak için start.cmd dosyasını yeniden aç.')));
  }
  for(const id of ['gameLaunchWidth','gameLaunchHeight','gameLaunchPath'])$('#'+id).addEventListener('input',()=>{launchEdited=true;launchMessage='';});
  for(const [id,path] of [['saveGameLaunch','/api/game/configure'],['startGame','/api/game/launch']])$('#'+id).addEventListener('click',async()=>{
    if(busy||eventBusy)return;
    for(const id of ['gameLaunchWidth','gameLaunchHeight'])if(!$('#'+id).reportValidity())return;
    eventBusy=true;launchMessage=id==='startGame'?'Oyun başlatılıyor…':'Ayar kaydediliyor…';paintLauncher();
    try{const body={width:Number($('#gameLaunchWidth').value),height:Number($('#gameLaunchHeight').value)},folder=$('#gameLaunchPath').value.trim();if(folder)body.gamePath=folder;bridge.launcher=await post(path,body);launchEdited=false;launchLoaded=false;launchMessage=id==='saveGameLaunch'?'Sonraki açılış için kaydedildi.':bridge.launcher.message;}
    catch(error){launchMessage=error.message;}
    finally{eventBusy=false;paint();paintLauncher();}
  });
  async function state(){
    if(!isLocal)return;
    try{const r=await fetch('/api/live/state',{cache:'no-store'});if(!r.ok)throw new Error();bridge=await r.json();bridgeConnected=true;if(eventMessage.startsWith('Yerel yardımcıya erişilemiyor.'))eventMessage='';}
    catch{bridgeConnected=false;if(bridge)bridge.ready=false;eventMessage='Yerel yardımcıya erişilemiyor. Etkinliğin durumu yeniden bağlantıda doğrulanacak.';}
    paint();paintLauncher();
    window.dispatchEvent(new CustomEvent('atlas:live-state',{detail:{...bridge,token:undefined,connected:bridgeConnected}}));
  }
  async function post(path,body){
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Atlas-Token':bridge.token},body:JSON.stringify(body)});
    const result=await r.json();if(!r.ok)throw new Error(result.message||'İstek kabul edilmedi.');return result;
  }
  async function changeEvent(multiplier){
    if(eventBusy||busy)return;
    if(!Number.isInteger(multiplier)||multiplier<1||multiplier>1000){number.reportValidity();return;}
    eventBusy=true;eventMessage='Çarpan oyuna uygulanıyor…';paint();
    try{bridge.event=await post('/api/live/event',{multiplier,premiumOnly:premiumOnly.checked,excludeFound:excludeFound.checked});eventOptionsEdited=false;eventFactorEdited=false;eventMessage='';}
    catch(error){eventMessage=error.message;}
    finally{eventBusy=false;paint();}
  }
  async function poll(){
    if(!job)return;
    try{
      const r=await fetch('/api/live/job/'+job,{headers:{'X-Atlas-Token':bridge.token},cache:'no-store'}),result=await r.json();
      if(result.state==='pending'){setTimeout(poll,700);return;}
      busy=false;job=null;
      if(jobKind==='ground-sale'){
        groundSaleMessage=result.state==='success'?(result.result.sold?`${format(result.result.sold)} eşya satıldı · ${format(result.result.gold)} altın, ${format(result.result.bags)} kese içinde yerde. Elle alabilirsin.`:'Satılacak beyaz/mavi ekipman yok.')+(result.result.saved?' İşlem öncesi kayıt ve yedek alındı.':''):result.message||'Satış sonucu doğrulanamadı.';
        await state();
      }
      else if(jobKind==='map-travel'){
        travelMessage=result.state==='success'?(result.result.entranceVerified===false?`${result.result.name} haritasına geçildi; girişteki konum doğrulanamadı. Oyundaki konumunu kontrol et.`:`${result.result.name} girişine ışınlandın.`)+(result.result.saved?' İşlem öncesi kayıt ve yedek alındı.':''):result.message||'Haritaya varış doğrulanamadı.';
        await state();
      }
      else if(jobKind==='level-rewind'){
        levelMessage=result.state==='success'?`${result.result.name}: ${result.result.previousLevel} → ${result.result.level}. Statlar korundu, EXP sıfırlandı; önceki ilerleme kaydedilip yedeklendi.`:result.message||'Seviye değişikliği doğrulanamadı.';
        await state();
      }
      else if(jobKind==='mob-cleanup')mobMessage=result.state==='success'?(result.result.removed?`${format(result.result.removed)} yaratık ganimet üretmeden kaldırıldı.`:'Son doğurduğun grup zaten kaldırılmış.'):result.message||'Temizleme doğrulanamadı.';
      else if(jobKind==='mob')mobMessage=result.state==='success'?`${format(result.result.quantity||1)} ${result.result.name} aynı noktada doğdu · AI kapalı.`+(result.result.partial?' İstenen adedin yalnızca bir kısmı oluşturulabildi.':''):result.message||'İşlem doğrulanamadı.';
      else lastMessage=result.state==='success'?result.result.name+' karakterinin yanına bırakıldı.':result.message||'İşlem doğrulanamadı.';
      paint();
    }catch{busy=false;job=null;const message='İşlem sonucu alınamadı. Yeniden tıklamadan önce oyunu kontrol et.';if(jobKind==='ground-sale')groundSaleMessage=message;else if(jobKind==='map-travel')travelMessage=message;else if(jobKind==='level-rewind')levelMessage=message;else if(jobKind.startsWith('mob'))mobMessage=message;else lastMessage=message;paint();}
  }
  window.addEventListener('atlas:map-selection',event=>{if(travelMap?.id!==event.detail.id&&!busy)travelMessage='';travelMap=event.detail;paint();});
  $('#travelToMap').addEventListener('click',async()=>{
    if(busy||eventBusy||!travelMap?.playable||!bridge?.mapTravel?.canTravel)return;
    const saveBefore=$('#mapTravelSave').checked;
    busy=true;jobKind='map-travel';travelMessage=(saveBefore?'İlerleme kaydedilip yedekleniyor; ardından ':'')+`${travelMap.name} girişine gidilecek. Oyuna dön…`;paint();
    try{const result=await post('/api/live/map-travel',{map:travelMap.id,binding:bridge.mapTravel.binding,saveBefore});job=result.job;poll();}
    catch(error){busy=false;travelMessage=error.message;paint();}
  });
  experienceRange.addEventListener('input',()=>{experienceNumber.value=experienceRange.value;experienceEdited=true;});
  experienceNumber.addEventListener('input',()=>{experienceRange.value=Math.max(1,Math.min(1000,Number(experienceNumber.value)||1));experienceEdited=true;});
  async function changeExperience(multiplier){
    if(busy||eventBusy)return;
    if(!Number.isInteger(multiplier)||multiplier<1||multiplier>1000){experienceNumber.reportValidity();return;}
    eventBusy=true;experienceMessage='EXP çarpanı uygulanıyor…';paint();
    try{bridge.experience=await post('/api/live/experience',{multiplier});experienceEdited=false;experienceMessage='';}
    catch(error){experienceMessage=error.message;}
    finally{eventBusy=false;paint();}
  }
  $('#applyExperience').addEventListener('click',()=>changeExperience(Number(experienceNumber.value)));
  $('#stopExperience').addEventListener('click',()=>changeExperience(1));
  $('#applyLevelRewind').addEventListener('click',async()=>{
    if(busy||eventBusy||!bridge?.levelControl?.ready)return;
    const level=Number(levelNumber.value);
    if(!Number.isInteger(level)||level<1||level>=bridge.levelControl.level){levelNumber.reportValidity();return;}
    busy=true;jobKind='level-rewind';levelMessage='Önce güncel ilerleme kaydedilip yedekleniyor. Oyuna dön; ardından seviye düşürülecek…';paint();
    try{const result=await post('/api/live/level-rewind',{level,binding:levelBinding});job=result.job;poll();}
    catch(error){busy=false;levelMessage=error.message;paint();}
  });
  range.addEventListener('input',()=>{number.value=range.value;eventFactorEdited=true;preview();});
  premiumOnly.addEventListener('change',()=>{eventOptionsEdited=true;preview();});
  excludeFound.addEventListener('change',()=>{eventOptionsEdited=true;preview();});
  pickupRange.addEventListener('input',()=>{pickupNumber.value=pickupRange.value;radiusEdited=true;});
  pickupNumber.addEventListener('input',()=>{pickupRange.value=Math.max(1,Math.min(20,Number(pickupNumber.value)||1));radiusEdited=true;});
  async function changeQoL(body){
    if(busy||eventBusy)return;
    if('radius'in body&&(!Number.isInteger(body.radius)||body.radius<1||body.radius>20)){pickupNumber.reportValidity();return;}
    eventBusy=true;qolMessage='';paint();
    try{bridge.lootQoL=await post('/api/live/loot-qol',body);if('radius'in body)radiusEdited=false;}
    catch(error){qolMessage=error.message;}
    finally{eventBusy=false;paint();}
  }
  $('#applyPickupRadius').addEventListener('click',()=>changeQoL({radius:Number(pickupNumber.value)}));
  for(const [id,property,enabled] of [['applyAutoPickup','autoPickup',true],['stopAutoPickup','autoPickup',false],['applyPotionStack','potionStacks',true],['stopPotionStack','potionStacks',false]])$('#'+id).addEventListener('click',()=>changeQoL({[property]:enabled,...(property==='autoPickup'&&enabled?{radius:Number(pickupNumber.value)}:{})}));
  number.addEventListener('input',()=>{range.value=Math.max(1,Math.min(100,Number(number.value)||1));eventFactorEdited=true;preview();});
  $('#applyDropEvent').addEventListener('click',()=>changeEvent(Number(number.value)));
  for(const [id,enabled] of [['applyCtrlTeleport',true],['stopCtrlTeleport',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(busy||eventBusy)return;
      eventBusy=true;teleportMessage='';paint();
      try{bridge.ctrlTeleport=await post('/api/live/ctrl-teleport',{enabled});}
      catch(error){teleportMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  for(const [id,enabled] of [['applyOmegaBeam',true],['stopOmegaBeam',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(eventBusy||busy||!bridgeConnected)return;
      eventBusy=true;omegaMessage='';paint();
      try{bridge.omegaBeam=await post('/api/live/omega-beam',{enabled});}
      catch(error){omegaMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  for(const [id,body] of [['specialSkillSelect',node=>({skill:node.value})],['specialSurprise',node=>({surprise:node.checked})]]){
    $('#'+id).addEventListener('change',async event=>{
      if(eventBusy||busy||!bridgeConnected)return;
      const config=body(event.target);eventBusy=true;omegaMessage='';paint();
      try{bridge.omegaBeam=await post('/api/live/special-skill',config);}
      catch(error){omegaMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  for(const [id,enabled] of [['applyHomingShots',true],['stopHomingShots',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(busy||eventBusy)return;
      eventBusy=true;homingMessage='';paint();
      try{bridge.homingShots=await post('/api/live/homing-shots',{enabled});}
      catch(error){homingMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  for(const [id,enabled] of [['applyMagicBeam',true],['stopMagicBeam',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(busy||eventBusy)return;
      eventBusy=true;magicMessage='';paint();
      try{bridge.magicBeam=await post('/api/live/magic-beam',{enabled});}
      catch(error){magicMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  for(const [id,enabled] of [['applyPremiumBeam',true],['stopPremiumBeam',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(busy||eventBusy)return;
      eventBusy=true;beamMessage='';paint();
      try{bridge.premiumBeam=await post('/api/live/premium-beam',{enabled});}
      catch(error){beamMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  $('#stopDropEvent').addEventListener('click',()=>changeEvent(1));
  for(const [id,enabled] of [['applyDisplayFix',true],['stopDisplayFix',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(busy||eventBusy)return;eventBusy=true;displayMessage='Arayüz güncelleniyor…';paint();
      try{bridge.display=await post('/api/live/display',{enabled});displayMessage='';}
      catch(error){displayMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  for(const [id,enabled] of [['applyQuickSell',true],['stopQuickSell',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(busy||eventBusy)return;eventBusy=true;quickSellMessage='Sağ tıkla satış güncelleniyor…';paint();
      try{bridge.quickSell=await post('/api/live/quick-sell',{enabled});quickSellMessage='';}
      catch(error){quickSellMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  for(const [id,hidden] of [['hideGroundLoot',true],['showGroundLoot',false]]){
    $('#'+id).addEventListener('click',async()=>{
      if(busy||eventBusy)return;eventBusy=true;groundMessage='';paint();
      try{bridge.groundLoot=await post('/api/live/ground-visibility',{hidden});}
      catch(error){groundMessage=error.message;}
      finally{eventBusy=false;paint();}
    });
  }
  $('#sellGroundLoot').addEventListener('click',async()=>{
    if(busy||eventBusy||!bridge?.ready)return;
    const saveBefore=$('#groundSaleSave').checked;
    busy=true;jobKind='ground-sale';groundSaleMessage=(saveBefore?'Önce kayıt ve yedek alınıyor. ':'')+'Oyuna dön; satış altını yerde kalacak…';paint();
    try{const result=await post('/api/live/ground-sale',{binding:[bridge.pid,bridge.player,bridge.map].join(':'),saveBefore});job=result.job;poll();}
    catch(error){busy=false;groundSaleMessage=error.message;paint();}
  });
  document.addEventListener('input',e=>{if(e.target.id==='liveMobQuantity')mobQuantity=Number(e.target.value);});
  document.addEventListener('click',async e=>{
    const undo=e.target.closest('[data-live-mob-cleanup]');
    if(undo){
      if(undo.disabled||busy||eventBusy)return;
      busy=true;jobKind='mob-cleanup';mobMessage='Son doğurduğun grup kaldırılıyor…';paint();
      try{const result=await post('/api/live/mob-cleanup',{});job=result.job;poll();}
      catch(err){busy=false;mobMessage=err.message;paint();}return;
    }
    const mob=e.target.closest('[data-live-mob]');
    if(mob){
      if(mob.disabled||busy||eventBusy)return;
      const quantity=Number($('#liveMobQuantity').value);
      if(!Number.isInteger(quantity)||quantity<1||quantity>2000){$('#liveMobQuantity').reportValidity();return;}
      busy=true;jobKind='mob';mobMessage='İstek sırada. Oyuna dön; seçili yaratık yakınında doğacak.';paint();
      try{const result=await post('/api/live/mob-spawn',{mob:Number(mob.dataset.liveMob),variant:Number(mob.dataset.liveVariant),quantity});job=result.job;poll();}
      catch(err){busy=false;mobMessage=err.message;paint();}return;
    }
    const b=e.target.closest('[data-live-drop]');if(!b||b.disabled||busy||eventBusy)return;
    busy=true;jobKind='item';lastMessage='İstek sırada. Oyuna dön; karakterin yanına tek eşya bırakılacak.';paint();
    try{const result=await post('/api/live/drop',{key:b.dataset.liveDrop});job=result.job;poll();}
    catch(err){busy=false;lastMessage=err.message;paint();}
  });
  new MutationObserver(()=>{const mob=$('[data-live-mob]'),key=mob?'mob:'+mob.dataset.liveMob+':'+mob.dataset.liveVariant:document.querySelector('[data-live-drop]')?.dataset.liveDrop||'';if(key!==selectedKey){selectedKey=key;if(!busy){lastMessage='';mobMessage='';}}paint();}).observe($('#detail'),{childList:true});
  window.AtlasLive={request:post,refresh:state};
  preview();state();paint();if(isLocal)setInterval(()=>{if(!busy&&!eventBusy)state();},4000);
})();
