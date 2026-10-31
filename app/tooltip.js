(function(){
  'use strict';
  const WIDTH=352, TOP=218, ROW=13;
  const colors=['#e4e2cd','#a9b9ff','#d6c28d','#a7d498'];
  const elementColors=['#c16b5b','#92b6cb','#b09a6b','#d6ce75','#c4d0c9','#9294b4','#6f9a74','#aaa8a8'];
  const images=new Map();
  function load(src){if(!src)return Promise.resolve(null);if(!images.has(src))images.set(src,new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('Panel asset could not be loaded: '+src));i.src=src;}));return images.get(src);}
  function value(lo,hi,percent=false){const sign=n=>n>0?'+'+n:String(n);return (lo===hi?sign(lo):sign(lo)+'..'+hi)+(percent?'%':'');}
  function displayAddition(label,lo,hi,pct){if(label==='Life Recovery'||label==='Mental Recovery'){const a=Number((lo/10).toFixed(1)),b=Number((hi/10).toFixed(1));return (a===b?String(a):a+'..'+b)+'%/s';}if(label==='Mental Consumption')return value(-hi,-lo,pct);return value(lo,hi,pct);}
  function layout(item){const additions=(item.tooltip?.additions||[]).map(a=>{const [label,lo,hi,rate,kind,pct]=a;const text=displayAddition(label,lo,hi,pct)+(rate<100?' ('+rate+'%)':'');const name=kind==='element'?label+' Element':label;return {name,text,split:(name.length+text.length)*6>322};});return {width:WIDTH,height:TOP+(additions.length?20+additions.reduce((n,a)=>n+(a.split?2:1)*ROW,0):0)+9,additions};}
  function wrap(text,maxWidth){const lines=[];let line='';for(const word of String(text).split(' ')){const candidate=line?line+' '+word:word;if(line&&SF_FONT.measure(candidate)>maxWidth){lines.push(line);line=word;}else line=candidate;}if(line)lines.push(line);return lines;}
  async function render(canvas,item){
    const meta=layout(item),icon=window.SF_VISUALS.items[item.key];
    const [,texture,art]=await Promise.all([SF_FONT.ready(),load('assets/fonts/stone-texture.png'),load(icon?.src)]);
    if(!canvas.isConnected)return;
    canvas.width=meta.width*2;canvas.height=meta.height*2;
    canvas.dataset.ready='true';
    const ctx=canvas.getContext('2d');ctx.scale(2,2);ctx.imageSmoothingEnabled=false;
    const pattern=ctx.createPattern(texture,'repeat');ctx.fillStyle=pattern;ctx.fillRect(0,0,meta.width,meta.height);
    ctx.fillStyle='#02030766';ctx.fillRect(0,0,meta.width,meta.height);
    function line(x,y,w,h=1,color='#605d51'){ctx.fillStyle=color;ctx.fillRect(x,y,w,h);}
    function frame(x,y,w,h){line(x,y,w);line(x,y+1,w,1,'#25282b');line(x,y,1,h);line(x+w-1,y,1,h,'#242629');line(x,y+h-1,w,1,'#303438');}
    frame(0,0,meta.width,meta.height);line(2,2,meta.width-4,1,'#a18c61');line(2,3,meta.width-4,1,'#36332a');
    ctx.fillStyle='#080b0c99';ctx.fillRect(4,9,272,17);frame(4,9,272,17);
    // The guide's item-type tab is red, while item names retain their class color.
    ctx.fillStyle='#4e2020';ctx.fillRect(8,12,10,10);frame(8,12,10,10);
    ctx.strokeStyle='#e3dcc5';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(10,20);ctx.lineTo(16,14);ctx.moveTo(10,14);ctx.lineTo(16,20);ctx.stroke();
    let title=item.name;
    while(SF_FONT.measure(title)>248)title=title.slice(0,-2);
    if(title!==item.name)title=title.slice(0,-3)+'...';
    SF_FONT.draw(ctx,title,24,11,colors[item.rarity]||colors[0]);
    const textColor='#d0c6a0';let y=35;
    for(const [label,raw] of item.tooltip?.base||[]){SF_FONT.draw(ctx,label,8,y,textColor);SF_FONT.draw(ctx,':',168,y,textColor);const text=String(raw);SF_FONT.draw(ctx,text,258-SF_FONT.measure(text),y,'#e5d7a6');y+=12;}
    frame(281,9,67,TOP-15);line(281,151,67,1,'#79705a');
    if(art){const scale=Math.min(1,59/art.width,132/art.height);const w=Math.round(art.width*scale),h=Math.round(art.height*scale);ctx.drawImage(art,Math.round(314.5-w/2),Math.round(79-h/2),w,h);}
    for(let n=0;n<8;n++){
      const ey=157+n*6;ctx.fillStyle=elementColors[n];ctx.fillRect(283,ey,4,4);line(289,ey+3,55,1,'#817b66');
      for(let k=0;k<=10;k++)line(289+k*5,ey+1,1,k===5?4:2,'#625f52');
      const added=(item.tooltip?.additions||[]).find(a=>a[4]==='element'&&a[0]===['Fire','Water','Earth','Thunder','Sacred','Dark','Gel','Metal'][n]&&a[3]===100&&a[1]===a[2]);
      const v=(item.tooltip?.elements?.[n]||0)+(added?.[1]||0);
      if(v){const end=316+Math.max(-25,Math.min(25,v));line(Math.min(316,end),ey+1,Math.max(1,Math.abs(end-316)),2,elementColors[n]);}
    }
    line(4,TOP-3,344,1,'#666759');line(4,TOP-2,344,1,'#252b2e');
    if(meta.additions.length){y=TOP+7;for(const {name,text,split} of meta.additions){
      SF_FONT.draw(ctx,name,8,y,textColor);
      if(split)y+=ROW;else SF_FONT.draw(ctx,':',246,y,textColor);
      SF_FONT.draw(ctx,text,342-SF_FONT.measure(text),y,'#e5d7a6');
      y+=ROW;
    }}
    return meta;
  }
  window.SF_TOOLTIP={render,layout,value,displayAddition};
})();
