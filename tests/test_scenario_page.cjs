'use strict';
// DOM integration; no real browser, helper API, game writes or external assets.
// npm install --no-save jsdom (or provide it through NODE_PATH).
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../app');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const dom=new JSDOM(html,{url:'http://localhost/#scenario=4%3A99000016',runScripts:'outside-only'});
const w=dom.window,d=w.document;
w.matchMedia=()=>({matches:false});w.HTMLElement.prototype.scrollIntoView=function(){};
for(const file of ['data.js','assets/visuals.js','model.js','map-model.js','assets/world/world.js','assets/maps/index.js','assets/maps/manifest.js','assets/scenario-items.js','scenario-model.js'])w.eval(fs.readFileSync(path.join(root,file),'utf8'));
w.AtlasApp={model:new w.AtlasModel(w.ATLAS_DATA),getPlayers:()=>1,getSelection:()=>({type:'mob',id:0,variant:0}),setPlayers(){},select(type,id){this.selected={type,id};}};
w.AtlasMapViewer=class{
  constructor(options){Object.assign(this,options);this.markers=[];this.width=800;this.height=600;}
  async setMap(asset){this.asset=asset;this.markers=[];return true;}
  resize(){}request(){}fit(){}focus(){}zoomAt(){}
  setMarkers(markers){this.markers=markers;}
  focusMarker(id){this.markerFocus=id;return this.markers.some(p=>p.id===id);}
};
for(const file of ['tabs.js','maps.js','scenario.js'])w.eval(fs.readFileSync(path.join(root,file),'utf8'));
const style=d.createElement('style');style.textContent=fs.readFileSync(path.join(root,'scenario.css'),'utf8');d.head.append(style);assert(style.sheet.cssRules.length>50,'scenario stylesheet must parse');
const tick=()=>new Promise(resolve=>setTimeout(resolve,15));
const click=selector=>{const element=d.querySelector(selector);assert(element,'missing: '+selector);element.click();};
const select=(id,value)=>{const e=d.getElementById(id);e.value=value;e.dispatchEvent(new w.Event('change',{bubbles:true}));};
(async()=>{
  assert.equal(d.getElementById('scenarioPage').hidden,false);
  assert.equal(d.getElementById('scenarioTab').getAttribute('aria-selected'),'true');
  assert.equal(d.querySelector('#scenarioDetail h2').textContent,'Queen');
  assert(d.getElementById('scenarioDetail').textContent.includes('Jurg'));
  assert.equal(d.querySelectorAll('.scenario-card').length,39);
  select('scenarioKind','trade');assert.equal(d.querySelectorAll('.scenario-card').length,4);
  const search=d.getElementById('scenarioSearch');search.value='Quina';search.dispatchEvent(new w.Event('input'));assert.equal(d.querySelectorAll('.scenario-card').length,1);
  search.value='';search.dispatchEvent(new w.Event('input'));select('scenarioKind','all');
  click('#scenarioDetail [data-scenario-item="3:40000009"]');
  assert.equal(d.querySelector('#scenarioDetail h2').textContent,'Akebi Fruit');
  assert(w.location.hash.includes('3%3A40000009'));
  click('#scenarioDetail [data-scenario-map="03000405"]');await tick();
  assert.equal(d.getElementById('mapsPage').hidden,false);
  assert.equal(w.AtlasMaps.model.maps[w.AtlasMaps.state.map].id,'03000405');
  assert.equal(w.AtlasMaps.viewer.markers.length,7);
  assert.equal(d.querySelectorAll('#mapScenarioFocus [data-map-scenario-point]').length,7);
  click('#mapScenarioFocus [data-map-scenario-point]');assert(w.AtlasMaps.viewer.markerFocus);
  assert(w.location.hash.includes('mapPoint='));
  click('#mapScenarioFocus [data-scenario-item]');assert.equal(d.getElementById('scenarioPage').hidden,false);
  assert.equal(d.querySelector('#scenarioDetail h2').textContent,'Akebi Fruit');
  w.location.hash='#scenario=4%3A99000015';await tick();assert.equal(d.querySelector('#scenarioDetail h2').textContent,'Jack');
  w.location.hash='#scenario=4%3A99000016';await tick();assert.equal(d.querySelector('#scenarioDetail h2').textContent,'Queen');
  w.location.hash='#map=03040000&mapScenario=3%3A40000000';await tick();assert.equal(w.AtlasMaps.viewer.markers.length,7);assert.equal(d.getElementById('mapsPage').hidden,false);
  click('#mapScenarioFocus [data-scenario-item]');assert.equal(d.querySelector('#scenarioDetail h2').textContent,'Vitality Source');
  select('scenarioKind','unresolved');assert.equal(d.querySelectorAll('.scenario-card').length,3);
  click('[data-scenario-item="4:99000019"]');assert(d.getElementById('scenarioDetail').textContent.includes('Mrs. Morris'));
  click('#scenarioDetail [data-scenario-map]');await tick();assert(w.AtlasMaps.viewer.markers.some(p=>p.kind==='usage'));
  // Normal map navigation must clear the previous guide overlay.
  w.AtlasMaps.open(0);await tick();assert.equal(w.AtlasMaps.viewer.markers.length,0);assert(d.getElementById('mapScenarioFocus').hidden);
  click('#scenarioTab');d.getElementById('scenarioTab').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Home',bubbles:true}));
  assert.equal(d.getElementById('atlasTab').getAttribute('aria-selected'),'true');
  d.getElementById('atlasTab').dispatchEvent(new w.KeyboardEvent('keydown',{key:'End',bubbles:true}));assert.equal(d.getElementById('scenarioTab').getAttribute('aria-selected'),'true');
  assert.equal(w.AtlasMaps.openScenario('missing','4:99000015'),false);
  const vitality=w.ATLAS_DATA.items.find(i=>i.key==='3:40000000');
  w.AtlasApp.getSelection=()=>({type:'item',id:vitality.id});
  if(!d.querySelector('#detail .detail-body')){const body=d.createElement('div');body.className='detail-body';d.getElementById('detail').append(body);}
  w.dispatchEvent(new w.CustomEvent('atlas:selection',{detail:{players:1}}));
  click('#detail .scenario-archive-link [data-scenario-item]');assert.equal(d.querySelector('#scenarioDetail h2').textContent,'Vitality Source');
  click('#scenarioDetail [data-scenario-catalogue]');assert.deepEqual(w.AtlasApp.selected,{type:'item',id:vitality.id});
  console.log('Scenario page DOM: deep links, filters, ingredient chain, real-map markers, point focus, return links and keyboard tabs passed.');
  dom.window.close();
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1;});
