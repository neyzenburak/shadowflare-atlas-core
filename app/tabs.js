(function(){
  'use strict';
  const names=['atlas','controls','maps','grail','scenario'];
  function show(name,focus=false){
    if(!names.includes(name))return;
    for(const key of names){
      const selected=key===name,button=document.getElementById(key+'Tab');
      document.getElementById(key+'Page').hidden=!selected;
      button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;
      if(selected&&focus)button.focus();
    }
    document.body.classList.toggle('controls-open',name==='controls');
    document.body.classList.toggle('maps-open',name==='maps');
    document.body.classList.toggle('grail-open',name==='grail');
    document.body.classList.toggle('scenario-open',name==='scenario');
    if(name==='grail'&&location.hash!=='#grail')history.replaceState(null,'','#grail');
    else if(name!=='grail'&&location.hash==='#grail')history.replaceState(null,'','#');
    if(name!=='scenario'&&new URLSearchParams(location.hash.slice(1)).has('scenario'))history.replaceState(null,'','#');
    if(name!=='atlas'){document.getElementById('detail').classList.remove('mobile-open');document.body.style.overflow='';}
    window.dispatchEvent(new CustomEvent('atlas:tabchange',{detail:{name}}));
  }
  names.forEach((name,index)=>{
    const button=document.getElementById(name+'Tab');button.addEventListener('click',()=>show(name));
    button.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      event.preventDefault();const target=event.key==='Home'?0:event.key==='End'?names.length-1:(index+(event.key==='ArrowRight'?1:-1)+names.length)%names.length;
      show(names[target],true);
    });
  });
  document.addEventListener('click',event=>{if(event.target.closest('a[href="#catalogue"],a.brand'))show('atlas');});
  window.addEventListener('hashchange',()=>{const p=new URLSearchParams(location.hash.slice(1));if(p.has('scenario'))show('scenario');else if(p.has('grail'))show('grail');else if(p.has('map'))show('maps');else if(p.has('mob')||p.has('item'))show('atlas');});
  window.AtlasTabs={show};
  if(location.hash==='#grail')show('grail');
})();
