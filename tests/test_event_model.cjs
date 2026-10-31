'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {AtlasModel}=require('../app/model.js');
const {AtlasMapModel}=require('../app/map-model.js');
const items=[['0:1',0],['0:2',1],['0:3',2],['1:3',2],['2:3',2],['3:1',0],['4:0',0],['4:1',0]]
  .map(([key,rarity],id)=>({id,key,rarity,name:'Item '+id,base:'Base',cat:Number(key[0])}));
const data={items,provenance:{goldItem:6},maps:[{id:'test',name:'Test'}],
  groups:[{data:{1:items.map(i=>[i.id,.01,.02])}}],
  mobs:[{id:0,name:'Mob',variants:[{group:0,gold:[20],count:3,locations:[[0,3]]}]}]};
const model=new AtlasModel(data),maps=new AtlasMapModel(data,model);
const variant=data.mobs[0].variants[0];
assert.equal(model.rawExperience(variant),null);
assert.equal(model.rawExperience({sample:{values:Array(13).fill(0).concat(100000)}}),100000);
assert.equal(model.rawExperience({experience:[0,0]}),0);
assert.equal(model.rawExperience({experience:[600,800]}),600);
assert.equal(model.rawExperienceMax({experience:[600,800]}),800);
assert.equal(model.setMultiplier(100),true);
const ordinary=maps.lootAt(0),ordinarySources=maps.sourceMaps(0);
const premiumChance=-Math.expm1(100*Math.log1p(-.01));
assert.equal(model.chance(variant,0),premiumChance);
assert.equal(model.chance(variant,6),1-(1-.01)*.8);
assert.equal(model.chance(variant,7),.01);
assert.equal(model.setMultiplier(100,true),true);
assert.notEqual(maps.lootAt(0),ordinary);
assert.notEqual(maps.sourceMaps(0),ordinarySources);
for(const id of [0,1,5,7]){
  assert.equal(model.itemMultiplier(id),1);
  assert.equal(model.chance(variant,id),.01);
  assert.equal(model.sources(id)[0].expected,.02);
  assert.equal(maps.lootAt(0).find(x=>x.item===id).chance,.01);
}
for(const id of [2,3,4]){
  assert.equal(model.itemMultiplier(id),100);
  assert.equal(model.chance(variant,id),premiumChance);
  assert.equal(model.sources(id)[0].expected,2);
}
assert.equal(model.chance(variant,6),1-(1-.01)*.8);
assert.equal(model.setMultiplier(100,true),false);
assert.equal(model.setMultiplier(1,true),true);
for(const id of [0,1,2,3,4,5,7])assert.equal(model.chance(variant,id),.01);
assert.throws(()=>model.setMultiplier(100,1),TypeError);
assert.throws(()=>model.setMultiplier(1001,true),RangeError);
model.setMultiplier(100,false);
assert.equal(model.chance(variant,0),premiumChance);
const beforeFilter=maps.lootAt(0);
model.setMultiplier(100,true,true,['0:3']);
assert.equal(model.chance(variant,2),0);assert.equal(model.isSuppressed(2),true);
assert.equal(model.chance(variant,3),premiumChance);assert.equal(model.chance(variant,1),.01);
assert.notEqual(maps.lootAt(0),beforeFilter);assert.equal(maps.lootAt(0).some(r=>r.item===2),false);
assert.deepEqual(maps.sourceMaps(2),[]);
model.setMultiplier(1,true,true,['1:3']);
assert.equal(model.chance(variant,3),0);assert.equal(model.chance(variant,2),.01);
model.setMultiplier(1,true,false,['1:3']);assert.equal(model.chance(variant,3),.01);

// Exercise the actual controls: polling must not discard a staged checkbox,
// and the applied probability event must use the server-confirmed policy.
async function controls(){
  const nodes=new Map(),events=[],posts=[],delegates={},preferences=new Map();let showMob=false,validityReports=0,travelSaved=false,saleSaved=false;
  class Node{
    constructor(){this.value='10';this.checked=false;this.disabled=false;this.listeners={};this.classList={toggle(){}};}
    addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
    async emit(name){await Promise.all((this.listeners[name]||[]).map(fn=>fn({target:this})));}
    reportValidity(){validityReports++;}
  }
  const node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
  const mobBlock={querySelector:s=>node(s==='button'?'#mobButton':s)};
  let live={ready:true,protocol:10,token:'test',event:{version:5,active:true,multiplier:100,premiumOnly:false,excludeFound:false,foundKeys:[]}},fail=false;
  const windowListeners={};
  const window={ATLAS_DATA:data,addEventListener:(name,fn)=>{windowListeners[name]=fn;},dispatchEvent:e=>{events.push(e);windowListeners[e.type]?.(e);}};
  const context={window,AtlasModel,location:{protocol:'http:',hostname:'127.0.0.1',port:'8770'},
    localStorage:{getItem:key=>preferences.get(key)??null,setItem:(key,value)=>preferences.set(key,value)},
    document:{querySelector:node,querySelectorAll:s=>showMob&&s==='.live-mob-block'?[mobBlock]:[],addEventListener(name,fn){delegates[name]=fn;},activeElement:null},
    MutationObserver:class{observe(){}},CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail;}},
    setInterval(){},setTimeout,
    fetch:async(url,options={})=>{
      if(url==='/api/live/job/sale-test')return {ok:true,json:async()=>({state:'success',result:{sold:25,gold:51234,bags:1,saved:saleSaved}})};
      if(options.method==='POST'){
        const body=JSON.parse(options.body);posts.push(body);
        if(fail)return {ok:false,json:async()=>({message:'Test rejection'})};
        if(url==='/api/live/omega-beam'||url==='/api/live/special-skill'){live.omegaBeam={...live.omegaBeam,...body,...('enabled' in body?{requested:body.enabled}:{}),message:'Yetenek ayarlandı'};return {ok:true,json:async()=>structuredClone(live.omegaBeam)};}
        if(url==='/api/live/experience'){live.experience={...live.experience,...body,active:body.multiplier>1};return {ok:true,json:async()=>structuredClone(live.experience)};}
        if(url==='/api/live/level-rewind')return {ok:true,json:async()=>({job:'level-test'})};
        if(url==='/api/live/map-travel'){travelSaved=body.saveBefore;return {ok:true,json:async()=>({job:'travel-test'})};}
        if(url==='/api/live/mob-spawn')return {ok:true,json:async()=>({job:'mob-test'})};
        if(url==='/api/live/mob-cleanup')return {ok:true,json:async()=>({job:'cleanup-test'})};
        if(url==='/api/live/ground-visibility'){live.groundLoot={version:2,requested:body.hidden,hidden:body.hidden,active:true};return {ok:true,json:async()=>structuredClone(live.groundLoot)};}
        if(url==='/api/live/ground-sale'){saleSaved=body.saveBefore;return {ok:true,json:async()=>({job:'sale-test'})};}
        live.event={...live.event,...body,active:body.multiplier>1};
        return {ok:true,json:async()=>structuredClone(live.event)};
      }
      if(url==='/api/live/job/level-test'){live.levelControl={...live.levelControl,level:78,binding:'lv78',exp:0};return {ok:true,json:async()=>({state:'success',result:{name:'Test Character',previousLevel:79,level:78,statsPreserved:true}})};}
      if(url==='/api/live/job/travel-test'){live.mapTravel={...live.mapTravel,currentMap:'00000001',binding:'map1'};return {ok:true,json:async()=>({state:'success',result:{name:'Test Map',map:'00000001',entranceVerified:true,saved:travelSaved}})};}
      if(url==='/api/live/job/mob-test')return {ok:true,json:async()=>({state:'success',result:{kind:'mob',name:'Test Mob',quantity:2000}})};
      if(url==='/api/live/job/cleanup-test')return {ok:true,json:async()=>({state:'success',result:{kind:'mob-cleanup',removed:2000}})};
      return {ok:true,json:async()=>structuredClone(live)};
    }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../app/live.js'),'utf8'),context);
  await new Promise(setImmediate);
  assert.equal(node('#mapTravelSave').checked,false);assert.equal(node('#groundSaleSave').checked,false);
  assert.equal(node('#eventPremiumOnly').disabled,false);
  assert.equal(Number(node('#eventMultiplierNumber').value),100);
  node('#eventPremiumOnly').checked=true;
  await node('#eventPremiumOnly').emit('change');
  await window.AtlasLive.refresh();
  assert.equal(node('#eventPremiumOnly').checked,true);
  assert.equal(events.filter(e=>e.type==='atlas:drop-multiplier').at(-1).detail.premiumOnly,false);
  await node('#applyDropEvent').emit('click');
  assert.deepEqual(posts.at(-1),{multiplier:100,premiumOnly:true,excludeFound:false});
  assert.equal(events.filter(e=>e.type==='atlas:drop-multiplier').at(-1).detail.premiumOnly,true);
  node('#eventExcludeFound').checked=true;await node('#eventExcludeFound').emit('change');
  await window.AtlasLive.refresh();assert.equal(node('#eventExcludeFound').checked,true);
  await node('#applyDropEvent').emit('click');assert.equal(posts.at(-1).excludeFound,true);
  live.event.foundKeys=['0:3'];await window.AtlasLive.refresh();
  assert.deepEqual([...events.filter(e=>e.type==='atlas:drop-multiplier').at(-1).detail.foundKeys],['0:3']);
  node('#eventMultiplierNumber').value='250';await node('#eventMultiplierNumber').emit('input');
  await window.AtlasLive.refresh();assert.equal(node('#eventMultiplierNumber').value,'250');
  node('#eventPremiumOnly').checked=false;await node('#eventPremiumOnly').emit('change');
  fail=true;await node('#applyDropEvent').emit('click');await window.AtlasLive.refresh();
  assert.equal(node('#eventPremiumOnly').checked,false);
  assert.equal(events.filter(e=>e.type==='atlas:drop-multiplier').at(-1).detail.premiumOnly,true);
  fail=false;await node('#stopDropEvent').emit('click');
  assert.deepEqual(posts.at(-1),{multiplier:1,premiumOnly:false,excludeFound:true});
  live.event.version=4;await window.AtlasLive.refresh();
  assert.equal(node('#eventPremiumOnly').disabled,true);
  assert.equal(node('#applyDropEvent').disabled,true);
  // Mob requests preserve the selected variant and exact quantity; invalid
  // quantities never leave the browser, and old helpers cannot enable spawning.
  showMob=true;live.mobSpawn={version:3};live.protocol=11;
  const mobButton=node('#mobButton'),quantity=node('#liveMobQuantity');
  mobButton.dataset={liveMob:'0',liveVariant:'2'};quantity.id='liveMobQuantity';
  await window.AtlasLive.refresh();assert.equal(mobButton.disabled,false);
  quantity.value='2000';delegates.input({target:quantity});
  const click={target:{closest:s=>s==='[data-live-mob]'?mobButton:null}};
  await delegates.click(click);await new Promise(setImmediate);
  assert.deepEqual(posts.at(-1),{mob:0,variant:2,quantity:2000});
  assert.match(node('.live-mob-status').textContent,/2\.000 Test Mob/);
  const before=posts.length;quantity.value='2001';await delegates.click(click);
  assert.equal(posts.length,before);assert.equal(validityReports,1);
  live.mobSpawn.version=4;await window.AtlasLive.refresh();
  const undo=node('[data-live-mob-cleanup]');assert.equal(undo.disabled,false);
  await delegates.click({target:{closest:s=>s==='[data-live-mob-cleanup]'?undo:null}});
  await new Promise(setImmediate);
  assert.deepEqual(posts.at(-1),{});
  assert.match(node('.live-mob-status').textContent,/2\.000 yaratık ganimet üretmeden kaldırıldı/);
  live.mobSpawn.version=3;await window.AtlasLive.refresh();assert.equal(undo.disabled,true);
  live.mobSpawn.version=2;await window.AtlasLive.refresh();assert.equal(mobButton.disabled,true);
  assert.equal(node('#applyExperience').disabled,true);
  assert.equal(node('#applyLevelRewind').disabled,true);
  live.protocol=12;live.experience={version:1,multiplier:1,active:false};
  live.levelControl={version:1,ready:true,level:79,name:'Test Character',exp:123,required:20000000,binding:'lv79'};
  await window.AtlasLive.refresh();
  assert.equal(node('#applyExperience').disabled,false);
  assert.equal(node('#applyLevelRewind').disabled,false);
  assert.equal(Number(node('#levelRewindNumber').value),78);
  node('#experienceNumber').value='1000';await node('#experienceNumber').emit('input');
  await window.AtlasLive.refresh();assert.equal(node('#experienceNumber').value,'1000');
  await node('#applyExperience').emit('click');assert.deepEqual(posts.at(-1),{multiplier:1000});
  assert.match(node('#experienceStatus').textContent,/1\.000/);
  await node('#stopExperience').emit('click');assert.deepEqual(posts.at(-1),{multiplier:1});
  const beforeInvalidXP=posts.length;
  node('#experienceNumber').value='1001';await node('#applyExperience').emit('click');
  assert.equal(posts.length,beforeInvalidXP);
  node('#levelRewindNumber').value='79';await node('#applyLevelRewind').emit('click');
  assert.equal(posts.length,beforeInvalidXP);
  node('#levelRewindNumber').value='78';await node('#applyLevelRewind').emit('click');
  await new Promise(setImmediate);
  assert.deepEqual(posts.at(-1),{level:78,binding:'lv79'});
  assert.match(node('#levelRewindStatus').textContent,/79 → 78/);
  assert.match(node('#levelRewindCurrent').textContent,/78/);
  live.levelControl.level=1;await window.AtlasLive.refresh();assert.equal(node('#applyLevelRewind').disabled,true);
  assert.equal(node('#travelToMap').disabled,true);
  live.protocol=13;live.mapTravel={version:2,ready:true,canTravel:true,binding:'map0',currentName:'Old Map'};
  await window.AtlasLive.refresh();assert.equal(node('#travelToMap').disabled,true);
  windowListeners['atlas:map-selection']({detail:{id:'00000001',name:'Test Map',playable:true}});
  assert.equal(node('#travelToMap').disabled,true);
  live.protocol=17;live.mapTravel.version=4;await window.AtlasLive.refresh();
  assert.equal(node('#travelToMap').disabled,false);
  await node('#travelToMap').emit('click');await new Promise(setImmediate);
  assert.deepEqual(posts.at(-1),{map:'00000001',binding:'map0',saveBefore:false});
  assert.match(node('#mapTravelStatus').textContent,/Test Map girişine/);
  assert.doesNotMatch(node('#mapTravelStatus').textContent,/kayıt ve yedek/);
  node('#mapTravelSave').checked=true;await node('#mapTravelSave').emit('change');
  assert.equal(node('#groundSaleSave').checked,false);
  await node('#travelToMap').emit('click');await new Promise(setImmediate);
  assert.deepEqual(posts.at(-1),{map:'00000001',binding:'map1',saveBefore:true});
  assert.match(node('#mapTravelStatus').textContent,/kayıt ve yedek alındı/);
  node('#mapTravelSave').checked=false;await node('#mapTravelSave').emit('change');
  windowListeners['atlas:map-selection']({detail:{id:'f00_03',name:'Unused',playable:false}});
  assert.equal(node('#travelToMap').disabled,true);
  const beforeUnused=posts.length;await node('#travelToMap').emit('click');assert.equal(posts.length,beforeUnused);
  windowListeners['atlas:map-selection']({detail:{id:'00000001',name:'Test Map',playable:true}});
  live.mapTravel.canTravel=false;await window.AtlasLive.refresh();assert.equal(node('#travelToMap').disabled,true);
  assert.equal(node('#applyOmegaBeam').disabled,true);
  live.omegaBeam={version:1,requested:false,active:false,message:'Omega kapalı'};
  await window.AtlasLive.refresh();assert.equal(node('#applyOmegaBeam').disabled,true);
  live.omegaBeam.version=3;
  await window.AtlasLive.refresh();assert.equal(node('#applyOmegaBeam').disabled,false);
  await node('#applyOmegaBeam').emit('click');assert.deepEqual(posts.at(-1),{enabled:true});
  assert.equal(node('#applyOmegaBeam').disabled,true);assert.equal(node('#stopOmegaBeam').disabled,false);
  await node('#stopOmegaBeam').emit('click');assert.deepEqual(posts.at(-1),{enabled:false});
  assert.equal(node('#stopOmegaBeam').disabled,true);
  node('#specialSkillSelect').value='meteor';await node('#specialSkillSelect').emit('change');
  assert.deepEqual(posts.at(-1),{skill:'meteor'});assert.equal(node('#specialSurprise').disabled,false);
  node('#specialSurprise').checked=true;await node('#specialSurprise').emit('change');
  assert.deepEqual(posts.at(-1),{surprise:true});assert.equal(live.omegaBeam.surprise,true);
  node('#specialSkillSelect').value='omega';await node('#specialSkillSelect').emit('change');
  assert.equal(node('#specialSurprise').disabled,true);assert.equal(node('#specialSurpriseWrap').hidden,true);
  assert.equal(node('#hideGroundLoot').disabled,true);
  live.groundLoot={version:1,requested:false,active:false};live.pid=123;live.player=456;live.map=789;
  live.lootQoL={version:6,active:true};await window.AtlasLive.refresh();
  assert.equal(node('#sellGroundLoot').disabled,true);
  live.lootQoL.version=7;await window.AtlasLive.refresh();assert.equal(node('#sellGroundLoot').disabled,true);
  live.groundLoot.version=2;await window.AtlasLive.refresh();assert.equal(node('#sellGroundLoot').disabled,false);
  await node('#hideGroundLoot').emit('click');assert.deepEqual(posts.at(-1),{hidden:true});
  assert.equal(node('#hideGroundLoot').disabled,true);assert.equal(node('#showGroundLoot').disabled,false);
  await node('#showGroundLoot').emit('click');assert.deepEqual(posts.at(-1),{hidden:false});
  await node('#sellGroundLoot').emit('click');await new Promise(setImmediate);
  assert.deepEqual(posts.at(-1),{binding:'123:456:789',saveBefore:false});
  assert.match(node('#groundSaleStatus').textContent,/25 eşya satıldı/);
  assert.match(node('#groundSaleStatus').textContent,/51\.234 altın/);
  assert.doesNotMatch(node('#groundSaleStatus').textContent,/kayıt ve yedek/);
  node('#groundSaleSave').checked=true;await node('#groundSaleSave').emit('change');
  assert.equal(node('#mapTravelSave').checked,false);
  await node('#sellGroundLoot').emit('click');await new Promise(setImmediate);
  assert.deepEqual(posts.at(-1),{binding:'123:456:789',saveBefore:true});
  assert.match(node('#groundSaleStatus').textContent,/kayıt ve yedek alındı/);
  node('#mapTravelSave').checked=true;await node('#mapTravelSave').emit('change');
  node('#mapTravelSave').checked=node('#groundSaleSave').checked=false;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../app/live.js'),'utf8'),context);
  await new Promise(setImmediate);
  assert.equal(node('#mapTravelSave').checked,true);assert.equal(node('#groundSaleSave').checked,true);
}
controls().then(()=>console.log('PASS: Premium-only probabilities, map caches and live checkbox controls'))
  .catch(error=>{console.error(error);process.exitCode=1;});
