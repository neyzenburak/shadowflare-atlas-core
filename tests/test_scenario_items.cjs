'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {AtlasScenarioModel}=require('../app/scenario-model.js');
const {AtlasMapViewer}=require('../app/map-viewer.js');
const root=path.resolve(__dirname,'..');
const read=name=>{const t=fs.readFileSync(path.join(root,'app',name),'utf8');return JSON.parse(t.slice(t.indexOf('=')+1).trim().replace(/;$/,''));};
const data=read('data.js'),guide=read('assets/scenario-items.js'),world=read('assets/world/world.js');
const assets=read('assets/maps/manifest.js');
const model=new AtlasScenarioModel(data,guide,world);
assert.equal(guide.scenarioCount,209);
assert.equal(model.records.length,39);
assert.equal(guide.fixedPlacements,84);
assert.equal(model.matches({kind:'ground'}).length,15);
assert.equal(model.matches({kind:'trade'}).length,4);
assert.equal(model.matches({kind:'scenario'}).length,4);
assert.equal(model.matches({kind:'unresolved'}).length,3);
assert.equal(model.matches({category:3}).length,10);
assert.equal(model.matches({category:4}).length,29);
assert.equal(model.records.reduce((n,r)=>n+r.sources.filter(s=>s.kind==='ground').reduce((v,s)=>v+s.points.length,0),0),84);
const meta=read('assets/maps/index.js');
const projected=(x,y)=>[Math.trunc((x-y)*15/100),Math.trunc((x+y)*10/100)];
let checked=0;
for(const record of model.records){
  assert.equal(record.item.key,record.key);
  assert.equal(record.unresolved,record.sources.length===0);
  assert.equal(record.autoPickup,record.category===3);
  for(const source of record.sources){
    assert(source.steps.length>=2);
    assert(source.points.length>0);
    if(source.ingredient)assert(model.byKey.has(source.ingredient));
    if(source.kind==='mob')assert(data.mobs[source.mob].variants[source.variant]);
    for(const p of source.points){
      assert(model.maps.has(p.map));assert.deepEqual([p.x,p.y],projected(p.worldX,p.worldY));
      const asset=assets.resources[meta.maps.find(m=>m.id===p.map).resource];
      assert(p.x>=asset.bounds[0]&&p.x<=asset.bounds[2]&&p.y>=asset.bounds[1]&&p.y<=asset.bounds[3],JSON.stringify(p));
      assert(model.markers(p.map,record.key).some(m=>m.id===p.id));checked++;
      if(source.kind==='mob')assert(meta.maps.find(m=>m.id===p.map).spawns.some(q=>q[0]===p.x&&q[1]===p.y&&q[2]===source.mob&&q[3]===source.variant),'source marker must agree with existing native monster projection');
    }
  }
  for(const usage of record.uses)for(const point of usage.points)assert(model.markers(usage.map,record.key).some(p=>p.id===point.id),'turn-in marker missing');
}
for(const [key,ingredient,npc,map] of [
  ['4:99000015','3:40000008','Oscar','03900003'],
  ['4:99000016','3:40000009','Quina','03900004'],
  ['4:99000017','3:40000000','Buzzed','03900001'],
  ['4:99000018','3:40000001','Barmera','03900002']]){
  const rec=model.byKey.get(key),source=rec.sources.find(s=>s.kind==='trade');
  assert.deepEqual([source.ingredient,source.npc,source.map,source.quest],[ingredient,npc,map,32]);
  assert(model.usedFor(ingredient).some(r=>r.key===key));
  assert(source.steps[0].includes('Jurg'));
}
assert(model.matches({query:'Gungstonwald'}).some(r=>r.name==='Queen'),'search must follow ingredient locations');
assert(model.matches({query:'Quina'}).some(r=>r.name==='Queen'));
assert(model.matches({query:'MATRIMONY vine'}).some(r=>r.name==='Chinese Matrimony Vine'));
assert.equal(model.matches({query:'not an item xyzzy'}).length,0);
assert.equal(model.matches({kind:'unresolved',category:'3'}).length,0);
assert.equal(model.byKey.get('3:40000000').sources[0].points.length,7);
assert.equal(model.byKey.get('3:40000001').sources[0].points.length,10);
assert.equal(model.byKey.get('4:99000019').uses[0].npc,'Mrs. Morris');
assert(!model.byKey.get('4:99000019').sources.length,'a consumer is not an acquisition source');
assert.deepEqual(model.markers('bad','missing'),[]);
// Map selection uses screen-space distances at any zoom, including overlaps.
const viewer=Object.create(AtlasMapViewer.prototype);
Object.assign(viewer,{scene:{},markers:[{id:'a',x:200,y:400,number:1}],cx:200,cy:400,width:800,height:600,zoom:.2,fitZoom:.1,constrain(){},request(){}});
assert.equal(viewer.nearestMarker({x:400,y:300}).id,'a');
assert.equal(viewer.nearestMarker({x:440,y:300}),null);
assert.equal(viewer.focusMarker('a'),true);
assert.equal(viewer.markerFocus,'a');
assert.equal(viewer.focusMarker('absent'),false);
viewer.setMarkers([]);assert.equal(viewer.markerFocus,null);assert.equal(viewer.nearestMarker({x:400,y:300}),null);
console.log(`Scenario guide: 39 records, 84 fixed placements, ${checked} source positions and map-selection checks passed.`);
