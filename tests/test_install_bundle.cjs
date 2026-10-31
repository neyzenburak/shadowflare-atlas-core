'use strict';
// Load the complete browser application against a freshly generated bundle.
// Usage: NODE_PATH=... node tests/test_install_bundle.cjs path/to/app
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(process.argv[2]||path.join(__dirname,'../app'));
const errors=[],console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e));
const dom=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8'),{
  url:'http://127.0.0.1:8770/',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console
});
const w=dom.window,d=w.document,noop=()=>{};
w.requestAnimationFrame=()=>0;w.cancelAnimationFrame=noop;
w.fetch=()=>Promise.reject(new Error('Offline installation smoke test'));
w.matchMedia=()=>({matches:false,addEventListener:noop,removeEventListener:noop});
w.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
w.HTMLElement.prototype.scrollIntoView=noop;w.HTMLElement.prototype.setPointerCapture=noop;
w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
w.HTMLDialogElement.prototype.close=function(){this.open=false;};
w.HTMLCanvasElement.prototype.getContext=function(){return new Proxy({
  canvas:this,measureText:t=>({width:String(t).length*6}),
  createLinearGradient:()=>({addColorStop:noop}),createRadialGradient:()=>({addColorStop:noop}),
  getImageData:()=>({data:new Uint8ClampedArray(4)}),createImageData:()=>({data:new Uint8ClampedArray(4)})
},{get:(o,k)=>k in o?o[k]:noop});};

(async()=>{
  try {
    for(const script of d.querySelectorAll('script[src]')){
      const file=script.getAttribute('src').split('?')[0];
      assert(fs.existsSync(path.join(root,file)),'Missing application script: '+file);
      // Exercise the optional-CT case as well as the generated trainer records.
      if(file==='trainer.js')w.TRAINER_DATA.structures=[];
      w.eval(fs.readFileSync(path.join(root,file),'utf8'));
    }
    await new Promise(resolve=>setTimeout(resolve,30));
    assert.equal(w.ATLAS_DATA.items.length,2860);
    assert.equal(w.ATLAS_DATA.mobs.length,572);
    assert.equal(w.SF_MAPS.maps.length,209);
    assert.equal(w.SF_MAPS.extraMaps.length,3);
    assert.equal(d.querySelectorAll('[data-world-node]').length,80);
    assert(d.getElementById('worldGuide').hidden,'An absent guide scan must not be offered');
    d.querySelector('[data-category="reference"]').click();
    assert.equal(w.TRAINER_DATA.records.length,0);
    assert(d.getElementById('trainerRecords').textContent.includes('Yerel tablo'));
    assert.equal(d.querySelectorAll('.structure-source').length,0);
    assert.equal(errors.length,0,errors.map(e=>e.message).join('\n'));
    process.stdout.write('PASS: complete generated browser bundle, 80 world nodes, optional guide images and CT-free trainer UI\n');
  } finally {w.close();}
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
