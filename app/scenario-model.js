(function(root){
  'use strict';
  const normalize=value=>String(value??'').toLocaleLowerCase('tr-TR').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ı/g,'i');
  const kinds={ground:'Hazır yerde',trade:'NPC takası',scenario:'Senaryo ödülü',dialog:'Görev diyaloğu',mob:'Yaratık drobu'};
  class AtlasScenarioModel{
    constructor(data,guide,world={maps:[]}){
      this.data=data;this.guide=guide;this.world=world;
      this.maps=new Map(data.maps.map((m,i)=>[m.id,{...m,index:i,...world.maps?.[i]}]));
      this.records=(guide?.items||[]).map(r=>({...r,item:data.items.find(i=>i.key===r.key)})).filter(r=>r.item);
      this.byKey=new Map(this.records.map(r=>[r.key,r]));
      this.searchText=new Map(this.records.map(r=>[r.key,normalize([
        r.name,r.key,...r.sources.flatMap(s=>[s.npc,this.byKey.get(s.ingredient)?.name,...(this.byKey.get(s.ingredient)?.sources||[]).flatMap(ingredientSource=>ingredientSource.points.map(p=>this.maps.get(p.map)?.name)),
          s.mob===undefined?'':data.mobs[s.mob]?.name,...s.points.map(p=>this.maps.get(p.map)?.name)]),
        ...r.uses.flatMap(u=>[u.npc,this.maps.get(u.map)?.name])].join(' '))]));
    }
    label(kind){return kinds[kind]||'Kaynak doğrulanmadı';}
    kinds(record){return [...new Set(record.sources.map(s=>s.kind))];}
    matches({query='',kind='all',category='all'}={}){
      const terms=normalize(query).trim().split(/\s+/).filter(Boolean);
      return this.records.filter(r=>terms.every(t=>this.searchText.get(r.key).includes(t))&&
        (kind==='all'||kind==='unresolved'&&r.unresolved||r.sources.some(s=>s.kind===kind))&&
        (category==='all'||r.category===Number(category))).sort((a,b)=>a.name.localeCompare(b.name,'en'));
    }
    sourceMaps(source){return [...new Set(source.points.map(p=>p.map))].map(id=>this.maps.get(id)).filter(Boolean);}
    markers(map,key){
      const record=this.byKey.get(key);if(!record)return [];
      const seen=new Set(),result=[];
      for(const source of record.sources){
        for(const point of source.points){
          if(point.map!==map||seen.has(point.id))continue;seen.add(point.id);
          result.push({...point,key,kind:source.kind,label:source.npc||(source.mob===undefined?record.name:this.data.mobs[source.mob]?.name),number:result.length+1});
        }
      }
      // A turn-in-only map is also navigable, without pretending it creates loot.
      for(const usage of record.uses){
        if(usage.map!==map)continue;
        for(const point of usage.points){if(seen.has(point.id))continue;seen.add(point.id);result.push({...point,key,kind:'usage',label:usage.npc,number:result.length+1});}
      }
      return result;
    }
    mapLabel(id){const m=this.maps.get(id);return m?'EP. '+m.episode+' · '+(m.towerFloor?'Kule '+m.towerFloor+'. kat · ':'')+m.name:id;}
    usedFor(key){return this.records.filter(r=>r.sources.some(s=>s.ingredient===key));}
  }
  root.AtlasScenarioModel=AtlasScenarioModel;
  if(typeof module!=='undefined')module.exports={AtlasScenarioModel,scenarioNormalize:normalize};
})(typeof window!=='undefined'?window:globalThis);
