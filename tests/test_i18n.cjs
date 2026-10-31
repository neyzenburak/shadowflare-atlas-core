'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'../app'),errors=[],requests=[];
const virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',e=>errors.push(e));
const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{url:'http://127.0.0.1:8770/',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole});
const w=dom.window,d=w.document,noop=()=>{},wait=()=>new Promise(r=>setTimeout(r,60));
w.requestAnimationFrame=()=>0;w.cancelAnimationFrame=noop;
w.fetch=(url,options)=>{requests.push({url,options});return Promise.reject(new Error('Offline UI check'));};
w.matchMedia=()=>({matches:false,addEventListener:noop,removeEventListener:noop});
w.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
w.HTMLElement.prototype.scrollIntoView=noop;w.HTMLElement.prototype.setPointerCapture=noop;
w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
w.HTMLCanvasElement.prototype.getContext=function(){return new Proxy({canvas:this,measureText:t=>({width:String(t).length*6}),createLinearGradient:()=>({addColorStop:noop}),createRadialGradient:()=>({addColorStop:noop}),getImageData:()=>({data:new Uint8ClampedArray(4)}),createImageData:()=>({data:new Uint8ClampedArray(4)})},{get:(o,k)=>k in o?o[k]:noop});};
function remainingTurkish(){
  const result=[];const walker=d.createTreeWalker(d.documentElement,w.NodeFilter.SHOW_TEXT);
  const sources=w.ATLAS_TRANSLATIONS.entries.filter(([tr,en])=>tr!==en&&tr.length>=4&&!/[{}<>]/.test(tr)).map(([tr])=>tr);
  while(walker.nextNode()){
    const node=walker.currentNode;
    if(node.parentElement.closest('script,style,pre,code,noscript,[data-i18n-ignore]'))continue;
    const text=node.nodeValue.replace(/\s+/g,' ').trim();
    if(/[çğıİöşüÇĞÖŞÜ]/.test(text))result.push(text);
    for(const source of sources){const at=text.indexOf(source);if(at<0)continue;const before=text[at-1]||'',after=text[at+source.length]||'';if(/[\p{L}\p{N}]/u.test(source[0])&&/[\p{L}\p{N}]/u.test(before)||/[\p{L}\p{N}]/u.test(source.at(-1))&&/[\p{L}\p{N}]/u.test(after))continue;result.push(text);break;}
  }
  for(const el of d.querySelectorAll('[title],[placeholder],[aria-label],[alt]')){
    if(el.closest('[data-i18n-ignore]'))continue;
    for(const attr of ['title','placeholder','aria-label','alt'])if(/[çğıİöşüÇĞÖŞÜ]/.test(el.getAttribute(attr)||''))result.push(attr+': '+el.getAttribute(attr));
  }
  return [...new Set(result)];
}
(async()=>{
  for(const script of d.querySelectorAll('script[src]'))w.eval(fs.readFileSync(path.join(root,script.getAttribute('src').split('?')[0]),'utf8'));
  await wait();
  assert.equal(d.documentElement.lang,'tr');assert.equal(w.AtlasI18n.language,'tr');
  const title=d.getElementById('heroTitle'),em=title.querySelector('em'),original=title.textContent;
  const item=w.ATLAS_DATA.items.find(i=>i.stats.length>12);w.AtlasApp.select('item',item.id);await wait();
  const selected=w.AtlasApp.getSelection();
  d.getElementById('search').value='Tesla';d.getElementById('search').dispatchEvent(new w.Event('input'));
  const multiplier=d.getElementById('eventMultiplierNumber');multiplier.value='137';multiplier.dispatchEvent(new w.Event('input'));
  const premium=d.getElementById('eventPremiumOnly');premium.checked=true;
  const source=d.createElement('pre');source.textContent='CT betiği değişmesin';d.body.append(source);
  const custom=d.createElement('input');custom.value='Özel karakter adı';d.body.append(custom);
  d.querySelector('[data-language="en"]').click();await wait();
  assert.equal(d.documentElement.lang,'en');assert.equal(w.localStorage.getItem('sf-atlas-language'),'en');
  assert.equal(d.querySelector('[data-language="en"]').getAttribute('aria-pressed'),'true');
  assert(d.getElementById('controlsTab').textContent.includes('Live controls'));
  assert(d.getElementById('search').placeholder.includes('Search'));
  assert.equal(title.querySelector('em'),em,'Changing language preserves markup and node identity');
  assert.deepEqual(w.AtlasApp.getSelection(),selected,'Selected item is preserved');
  assert.equal(multiplier.value,'137');assert.equal(premium.checked,true);assert.equal(d.getElementById('search').value,'Tesla');
  assert.equal(custom.value,'Özel karakter adı');assert.equal(source.textContent,'CT betiği değişmesin');
  assert.equal(w.AtlasI18n.t('Tesla Blade'),'Tesla Blade');assert.equal(w.AtlasI18n.t('ShadowFlare v2.004'),'ShadowFlare v2.004');
  for(const entry of [...w.ATLAS_DATA.items,...w.ATLAS_DATA.mobs,...w.ATLAS_DATA.maps])assert.equal(w.AtlasI18n.t(entry.name),entry.name,'Native item, monster and map names stay unchanged');
  assert.equal(w.AtlasI18n.t('1.155 eşya'),'1,155 items');
  assert.equal(w.AtlasI18n.t('%0,000123'),'0.000123%');
  assert.equal(w.AtlasI18n.t('2.147.483.647 altın'),'2,147,483,647 gold');
  assert.equal(w.AtlasI18n.t('Değer 1–999 aralığında olmalı.'),'Value must be between 1 and 999.');
  const dynamic=d.createElement('p');dynamic.textContent='Karakter yüklenmiş değil; oyunun içine gir.';d.body.append(dynamic);await wait();
  assert.equal(dynamic.textContent,'No character is loaded; enter the game.');
  dynamic.textContent='Oyun klasöründe birden fazla CT var; CT dosyası ekle ile birini seç.';await wait();
  assert(dynamic.textContent.includes('Multiple CT files'));
  // Exercise each tab and the scenario route descriptions while English is active.
  for(const tab of ['mapsTab','grailTab','scenarioTab','controlsTab']){d.getElementById(tab).click();await wait();}
  for(const record of w.SF_SCENARIO_ITEMS.items){const button=d.querySelector(`#scenarioGrid [data-scenario-item="${record.key}"]`);if(button){button.click();await wait();}}
  const missing=remainingTurkish();if(missing.length){console.error('Untranslated UI:',JSON.stringify(missing,null,2));}
  assert.equal(missing.length,0,'All rendered interface and accessibility text is translated');
  assert(!requests.some(r=>r.options?.method==='POST'),'Language changes must not issue game commands');
  d.querySelector('[data-language="tr"]').click();await wait();
  assert.equal(d.documentElement.lang,'tr');assert.equal(title.textContent,original,'Switching back restores the original Turkish');
  assert.equal(title.querySelector('em'),em);assert.equal(multiplier.value,'137');
  assert.equal(d.getElementById('search').placeholder,'Bir yaratık veya eşya ara…');
  const sourceCode=fs.readFileSync(path.join(root,'i18n.js'),'utf8'),catalogue=fs.readFileSync(path.join(root,'translations.js'),'utf8');
  const restarted=new JSDOM('<html lang="tr"><head><title>Arşiv</title></head><body><p>Eşyalar</p></body></html>',{url:'http://localhost/',runScripts:'outside-only'});
  restarted.window.localStorage.setItem('sf-atlas-language','en');restarted.window.eval(catalogue);restarted.window.eval(sourceCode);await wait();
  assert.equal(restarted.window.document.documentElement.lang,'en');assert.equal(restarted.window.document.querySelector('p').textContent,'Items');restarted.window.close();
  const portable=new JSDOM('<html><body><p>Eşyalar</p></body></html>',{url:'file:///atlas/index.html',runScripts:'outside-only'});
  portable.window.eval(catalogue);portable.window.eval(sourceCode);portable.window.AtlasI18n.setLanguage('en');
  assert.equal(portable.window.document.querySelector('p').textContent,'Items','Works even when localStorage is unavailable');portable.window.close();
  assert.equal(errors.length,0,errors.map(e=>e.message).join('\n'));
  console.log('PASS: full TR/EN UI, dynamic status, accessible labels, numbers, persistence and unchanged game controls');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>w.close());
