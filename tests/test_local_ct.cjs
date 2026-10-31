'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../app');
const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'http://localhost/',runScripts:'outside-only'});
const w=dom.window,d=w.document,requests=[];
const empty={version:1,source:'Local table',sha256:null,records:[],structures:[],comments:'',counts:{entries:0,structures:0}};
const imported={...empty,source:'example.ct',sha256:'local-example',records:[
  {id:'ct:1',parent:null,kind:'group',label:'Example group',description:'Example group'},
  {id:'ct:2',parent:'ct:1',kind:'value',label:'Example value',description:'Example value',type:'4 Bytes',readOnly:false}
],counts:{entries:2,structures:0,supported:1,unsupported:0}};
let serverTable=empty;
w.AtlasLive={request:async(endpoint,body)=>{requests.push({endpoint,body});return endpoint.endsWith('/import')?imported:endpoint.endsWith('/table')?serverTable:empty;},refresh:async()=>{}};
for(const file of ['trainer-data.js','trainer-extras.js','trainer.js'])w.eval(fs.readFileSync(path.join(root,file),'utf8'));
const pause=()=>new Promise(r=>setTimeout(r,30));
(async()=>{
  assert.equal(w.TRAINER_DATA.records.length,0);
  assert(d.querySelector('[data-toggle="atlas-blackjack"]'));
  assert.equal(d.querySelector('.source-download[href]'),null,'No bundled CT download link');
  w.dispatchEvent(new w.CustomEvent('atlas:live-state',{detail:{connected:true,ready:false,protocol:19,trainer:{version:3,active:[],frozen:[],table:{sha256:null}}}}));
  const input=d.getElementById('trainerCTFile');assert.equal(input.disabled,false,'Import does not require a loaded character');
  Object.defineProperty(input,'files',{value:[{name:'example.ct',size:50,text:async()=>'<CheatTable/>'}],configurable:true});
  input.dispatchEvent(new w.Event('change'));await pause();
  assert(requests.some(r=>r.endpoint==='/api/trainer/import'&&r.body.filename==='example.ct'&&r.body.content==='<CheatTable/>'));
  d.querySelector('[data-category="table"]').click();
  assert(d.getElementById('trainerRecords').textContent.includes('Example value'));
  assert.equal(d.getElementById('trainerCTRemove').disabled,false);
  d.getElementById('trainerCTRemove').click();await pause();
  assert(requests.some(r=>r.endpoint==='/api/trainer/remove'));
  assert.equal(d.getElementById('trainerCTRemove').disabled,true);
  assert(!d.getElementById('trainerRecords').textContent.includes('Example value'));
  d.querySelector('[data-category="atlas"]').click();
  assert(d.querySelector('[data-toggle="atlas-blackjack"]'),'Atlas controls survive CT removal');
  w.dispatchEvent(new w.CustomEvent('atlas:live-state',{detail:{connected:true,ready:false,protocol:19,trainer:{version:4,table:{sha256:null,discoveryMessage:'Multiple CT files: choose one.'}}}}));
  assert(d.getElementById('trainerTableSummary').textContent.includes('Multiple CT files'));
  serverTable=imported;
  w.dispatchEvent(new w.CustomEvent('atlas:live-state',{detail:{connected:true,ready:false,protocol:19,trainer:{version:4,table:{sha256:imported.sha256}}}}));
  await pause();d.querySelector('[data-category="table"]').click();
  assert(requests.some(r=>r.endpoint==='/api/trainer/table'),'Discovered tables load from the companion');
  assert(d.getElementById('trainerRecords').textContent.includes('Example value'));
  assert(!requests.some(r=>r.endpoint.endsWith('/toggle')||r.endpoint.endsWith('/write')),'Discovery must not enable cheats');
  assert.equal(w.TRAINER_DATA.records.length,0,'Bundled catalogue stays empty');
  console.log('PASS: local CT upload/removal/discovery, no automatic cheats, empty bundle and independent Atlas controls');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>w.close());
