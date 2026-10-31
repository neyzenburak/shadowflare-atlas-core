'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../app'),dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'http://127.0.0.1:8770/',runScripts:'outside-only'});
const w=dom.window,d=w.document,requests=[];w.setInterval=()=>0;
w.eval(fs.readFileSync(path.join(root,'model.js'),'utf8'));
w.ATLAS_DATA={items:[],mobs:[],maps:[],groups:{},provenance:{goldItem:0}};
let state={protocol:19,ready:false,token:'test',launcher:{version:1,width:1920,height:900,gamePath:'C:\\Games\\ShadowFlare',running:false}};
w.fetch=async(url,options={})=>{
  if(options.method==='POST'){
    const body=JSON.parse(options.body);requests.push({url,body});
    state.launcher={...state.launcher,...body,running:url==='/api/game/launch'};
    return {ok:true,json:async()=>structuredClone(state.launcher)};
  }
  return {ok:true,json:async()=>structuredClone(state)};
};
const tick=()=>new Promise(r=>setTimeout(r,15));
(async()=>{
  try{
    w.eval(fs.readFileSync(path.join(root,'live.js'),'utf8'));await tick();
    assert.equal(d.getElementById('startGame').disabled,false,'launch must work before a character is loaded');
    for(const [id,value]of [['gameLaunchWidth','1366'],['gameLaunchHeight','768']]){d.getElementById(id).value=value;d.getElementById(id).dispatchEvent(new w.Event('input'));}
    await w.AtlasLive.refresh();assert.equal(d.getElementById('gameLaunchWidth').value,'1366','polling must preserve edits');
    d.getElementById('saveGameLaunch').click();await tick();
    assert.deepEqual(requests[0],{url:'/api/game/configure',body:{width:1366,height:768,gamePath:'C:\\Games\\ShadowFlare'}});
    d.getElementById('startGame').click();await tick();
    assert.equal(requests[1].url,'/api/game/launch');assert.equal(d.getElementById('startGame').disabled,true);
    assert.equal(d.getElementById('saveGameLaunch').disabled,false,'next-start preferences can be saved while playing');
    state={...state,protocol:18};await w.AtlasLive.refresh();assert(d.getElementById('saveGameLaunch').disabled,'old helpers cannot accept launch commands');
    console.log('PASS: startup before character load, preserved edits, save/launch requests and running-game protection');
  }finally{w.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
