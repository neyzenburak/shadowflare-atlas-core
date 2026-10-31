"""Export the original game bitmap glyphs and a dependency-free canvas API."""
from pathlib import Path
import json
import sys
import hashlib

from PIL import Image

from paths import WORK as ROOT, GAME, OUTPUT
WORK=GAME/'System/Common/Pattern'
OUT=OUTPUT/'assets/fonts'
from decode_visuals import NJP


def export(name):
    njp=NJP(WORK/(name+'.njp'))
    atlas=Image.new('RGBA',(192*8,192*9))
    pages=[]
    for index in range(len(njp.patterns)):
        im,xy=njp.render(index)
        x=(index%8)*192;y=(index//8)*192
        atlas.alpha_composite(im,(x,y));pages.append({'x':x,'y':y,'w':im.width,'h':im.height})
    atlas.save(OUT/(name.lower()+'.png'),optimize=True)
    glyphs={}
    # The DLL's Shift-JIS lead-byte calculation selects NJP pages 1..64;
    # the trailing byte selects the 16x16 cell within a 192x192 page.
    for codepoint in range(32,65536):
        c=chr(codepoint)
        try:encoded=c.encode('cp932')
        except UnicodeEncodeError:continue
        if len(encoded)==1:
            code=encoded[0]
            if code<32 or code==127:continue
            page=0;column=code%16;row=code//16;width=6
        elif len(encoded)==2:
            lead,trail=encoded
            page=lead-0x7f if 0x80<=lead<=0x9f else lead-0xbf
            if not 0<page<len(pages):continue
            column=trail%16;row=trail//16;width=12
        else:continue
        p=pages[page]
        glyphs[c]=[p['x']+column*width,p['y']+row*12,width,12,width]
    return {'src':'assets/fonts/'+name.lower()+'.png','height':12,'latinAdvance':6,'japaneseAdvance':12,'glyphs':glyphs,'pages':pages,'sourceSha256':hashlib.sha256((WORK/(name+'.njp')).read_bytes()).hexdigest()}


HELPER=r'''
;(function(data){
  'use strict';
  let bitmap=null, pending=null;
  const replacement=data.glyphs['?'];
  function glyph(c){return data.glyphs[c]||replacement;}
  function measure(text){
    let width=0, maximum=0;
    for(const c of String(text)){
      if(c==='\n'){maximum=Math.max(maximum,width);width=0;}
      else if(c==='\t')width+=data.latinAdvance*4;
      else if(c!=='\r')width+=glyph(c)[4];
    }
    return Math.max(maximum,width);
  }
  function ready(){
    if(pending)return pending;
    pending=new Promise((resolve,reject)=>{
      bitmap=new Image();
      bitmap.onload=()=>resolve();
      bitmap.onerror=()=>reject(new Error('Original ShadowFlare bitmap font could not be loaded'));
      bitmap.src=data.src;
    });
    return pending;
  }
  function draw(ctx,text,x,y,color='#d3bf88'){
    if(!bitmap||!bitmap.complete||!bitmap.naturalWidth)throw new Error('Await SF_FONT.ready() before drawing');
    text=String(text);
    const width=measure(text), lines=text.split('\n').length;
    if(!width)return 0;
    const mask=document.createElement('canvas');
    mask.width=Math.ceil(width);mask.height=data.height*lines;
    const paint=mask.getContext('2d');
    paint.imageSmoothingEnabled=false;
    let dx=0,dy=0;
    for(const c of text){
      if(c==='\n'){dx=0;dy+=data.height;continue;}
      if(c==='\r')continue;
      if(c==='\t'){dx+=data.latinAdvance*4;continue;}
      const g=glyph(c);
      paint.drawImage(bitmap,g[0],g[1],g[2],g[3],dx,dy,g[2],g[3]);dx+=g[4];
    }
    paint.globalCompositeOperation='source-in';
    paint.fillStyle=color;paint.fillRect(0,0,mask.width,mask.height);
    ctx.save();ctx.imageSmoothingEnabled=false;
    ctx.drawImage(mask,Math.round(x),Math.round(y));ctx.restore();
    return width;
  }
  window.SF_FONT=Object.assign(data,{ready,measure,draw});
})(window.SF_FONT_DATA);
'''
