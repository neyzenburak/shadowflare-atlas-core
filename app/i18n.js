(function(root){
  'use strict';
  const KEY='sf-atlas-language',ATTRS=['title','aria-label','aria-description','aria-valuetext','placeholder','alt','content'];
  const entries=root.ATLAS_TRANSLATIONS?.entries||[],normalize=s=>String(s).replace(/\s+/g,' ').trim();
  const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const exact=new Map(),patterns=[],textSources=new WeakMap(),attributeSources=new WeakMap(),cache=new Map();
  for(const [source,target] of entries){
    const key=normalize(source);if(!key||key===target)continue;
    if(/\{\d+\}/.test(key)){
      const slots=[];let at=0,expression='';
      for(const match of key.matchAll(/\{(\d+)\}/g)){const literal=key.slice(at,match.index);expression+=escape(literal)+(/[\p{L}\p{N}]$/u.test(literal)?'(?![\\p{L}\\p{N}])':'')+'([\\s\\S]*?)';slots.push(match[1]);at=match.index+match[0].length;}
      expression+=escape(key.slice(at));const weight=key.replace(/\{\d+\}/g,'').length;
      if(weight>=4)patterns.push({regex:new RegExp('^'+expression+'$','u'),slots,target,weight});
    }else{exact.set(key,target);if(key.length<80)exact.set(key.toLocaleUpperCase('tr-TR'),target.toLocaleUpperCase('en-US'));}
  }
  patterns.sort((a,b)=>b.weight-a.weight);
  const fragments=[...exact.keys()].filter(s=>s.length>=4).sort((a,b)=>b.length-a.length);
  const fragmentRE=fragments.length?new RegExp(fragments.map(escape).join('|'),'g'):null;
  let language='tr';try{if(localStorage.getItem(KEY)==='en')language='en';}catch{}
  function numbers(text){
    return text.replace(/(^|[^\p{L}\p{N}_.,/\\])([+-]?(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+))(?![\p{L}\p{N}_.,/\\])/gu,(_,prefix,value)=>{const [integer,fraction]=value.replace(/\./g,'').split(',');return prefix+integer.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction===undefined?'':'.'+fraction);})
      .replace(/%([+-]?\d[\d.,]*)/g,'$1%');
  }
  function english(source,depth=0){
    if(depth>5)return source;
    const clean=normalize(source);if(!clean)return source;
    if(source!==clean)return source.match(/^\s*/)[0]+english(clean,depth)+source.match(/\s*$/)[0];
    if(exact.has(source))return exact.get(source);
    for(const pattern of patterns){
      const found=pattern.regex.exec(source);if(!found)continue;
      const values={};pattern.slots.forEach((slot,i)=>{values[slot]=english(found[i+1],depth+1);});
      return pattern.target.replace(/\{(\d+)\}/g,(_,slot)=>values[slot]??'');
    }
    if(!fragmentRE)return numbers(source);
    let result='',last=0;
    source.replace(fragmentRE,(match,offset,all)=>{
      const before=all[offset-1]||'',after=all[offset+match.length]||'';
      if(/[\p{L}\p{N}]/u.test(match[0])&&/[\p{L}\p{N}]/u.test(before)||/[\p{L}\p{N}]/u.test(match.at(-1))&&/[\p{L}\p{N}]/u.test(after))return match;
      result+=numbers(source.slice(last,offset))+exact.get(match);last=offset+match.length;return match;
    });
    return result+numbers(source.slice(last));
  }
  function t(value,lang=language){
    const raw=String(value??'');if(lang!=='en'||!raw.trim())return raw;
    if(cache.has(raw))return cache.get(raw);
    const clean=normalize(raw),result=english(clean);
    const output=result===clean?raw:/^[.,!?;:]$/.test(result)?result:raw.match(/^\s*/)[0]+result+raw.match(/\s*$/)[0];
    if(cache.size>5000)cache.clear();cache.set(raw,output);return output;
  }
  function ignored(node){return node.parentElement?.closest('script,style,pre,code,textarea,input,[data-i18n-ignore]');}
  function text(node){
    if(ignored(node))return;
    const value=node.nodeValue;let record=textSources.get(node);
    if(!record||value!==record.last){record={source:value,last:value};textSources.set(node,record);}
    const result=language==='en'&&node.parentElement?.hasAttribute('data-i18n-en')?node.parentElement.dataset.i18nEn:t(record.source);record.last=result;if(value!==result)node.nodeValue=result;
  }
  function attributes(el){
    if(el.closest('script,style,pre,code,[data-i18n-ignore]'))return;
    let records=attributeSources.get(el);if(!records){records=new Map();attributeSources.set(el,records);}
    for(const name of ATTRS){
      if(!el.hasAttribute(name)||name==='content'&&!(el.tagName==='META'&&el.name==='description'))continue;
      const value=el.getAttribute(name);let record=records.get(name);
      if(!record||value!==record.last){record={source:value,last:value};records.set(name,record);}
      const result=t(record.source);record.last=result;if(result!==value)el.setAttribute(name,result);
    }
  }
  function localize(node=document.documentElement){
    if(node.nodeType===Node.TEXT_NODE){text(node);return;}
    if(node.nodeType!==Node.ELEMENT_NODE&&node.nodeType!==Node.DOCUMENT_FRAGMENT_NODE)return;
    if(node.id==='languageSwitch')controls();
    if(node.nodeType===Node.ELEMENT_NODE){if(node.matches('script,style,pre,code,textarea,input,[data-i18n-ignore]')){if(node.matches('input,textarea'))attributes(node);return;}attributes(node);}
    for(const child of node.childNodes)localize(child);
  }
  function controls(){
    document.documentElement.lang=language;
    const group=document.getElementById('languageSwitch');if(!group)return;
    group.setAttribute('aria-label',language==='en'?'Interface language':'Arayüz dili');
    for(const button of group.querySelectorAll('[data-language]'))button.setAttribute('aria-pressed',String(button.dataset.language===language));
  }
  function setLanguage(value){
    if(!['tr','en'].includes(value))throw new RangeError('Unsupported language');
    language=value;try{localStorage.setItem(KEY,value);}catch{}
    controls();localize();root.dispatchEvent(new CustomEvent('atlas:languagechange',{detail:{language,locale:language==='en'?'en-US':'tr-TR'}}));
    return language;
  }
  root.AtlasI18n={t,setLanguage,refresh:localize,get language(){return language;},get locale(){return language==='en'?'en-US':'tr-TR';}};
  controls();
  document.addEventListener('click',event=>{const button=event.target.closest('[data-language]');if(button)setLanguage(button.dataset.language);});
  const observer=new MutationObserver(records=>{
    const roots=new Set();
    for(const record of records){
      if(record.type==='characterData')text(record.target);
      else if(record.type==='attributes')attributes(record.target);
      else for(const node of record.addedNodes)roots.add(node);
    }
    for(const node of roots)if(node.isConnected)localize(node);
  });
  observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:ATTRS});
  document.addEventListener('DOMContentLoaded',()=>{controls();localize();});
})(window);
