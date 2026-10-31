(function(root){
  'use strict';
  class AtlasMapModel {
    constructor(data,dropModel,metadata={}){
      this.data=data;this.dropModel=dropModel;this.metadata=metadata;
      this.maps=[...data.maps,...(metadata.extraMaps||[])];
      this.entries=this.maps.map(()=>[]);this.byId=new Map(this.maps.map((m,i)=>[String(m.id),i]));
      this.sourceCache=new Map();this.lootCache=new Map();
      for(const mob of data.mobs)mob.variants.forEach((variant,vi)=>{
        for(const [map,count] of variant.locations)this.entries[map].push({mob:mob.id,variant:vi,count});
      });
      this.names=this.maps.map((m,i)=>root.atlasNormalize([m.name,m.id,...this.entries[i].map(e=>data.mobs[e.mob].name)].join(' ')));
    }
    key(value,players){return [value,players,this.dropModel.multiplier,this.dropModel.premiumOnly,this.dropModel.excludeFound,this.dropModel.policyKey].join(':');}
    sourcesAt(map,item,players=1){
      return this.entries[map].map(e=>({...e,chance:this.dropModel.chance(this.data.mobs[e.mob].variants[e.variant],item,players)}))
        .filter(e=>e.chance>0).sort((a,b)=>b.chance-a.chance||b.count-a.count||a.mob-b.mob);
    }
    sourceMaps(item,players=1){
      const key=this.key(item,players);if(this.sourceCache.has(key))return this.sourceCache.get(key);
      const maps=new Map();
      for(const source of this.dropModel.sources(item,players)){
        const variant=this.data.mobs[source.mob].variants[source.variant];
        for(const [map,count] of variant.locations){
          if(!maps.has(map))maps.set(map,{map,chance:0,count:0,sources:[]});
          const row=maps.get(map);row.chance=Math.max(row.chance,source.chance);row.count+=count;
          row.sources.push({...source,count});
        }
      }
      const result=[...maps.values()].sort((a,b)=>b.chance-a.chance||b.count-a.count||a.map-b.map);
      this.sourceCache.set(key,result);return result;
    }
    lootAt(map,players=1){
      const key=this.key(map,players);if(this.lootCache.has(key))return this.lootCache.get(key);
      const items=new Map();
      for(const entry of this.entries[map]){
        const variant=this.data.mobs[entry.mob].variants[entry.variant];
        const candidates=new Set(this.dropModel.rows(variant.group,players).map(r=>r[0]));
        if(variant.gold[0]>0)candidates.add(this.data.provenance.goldItem);
        for(const item of candidates){
          const chance=this.dropModel.chance(variant,item,players);if(chance<=0)continue;
          let row=items.get(item);if(!row){row={item,chance:0,count:0,sources:[]};items.set(item,row);}
          row.chance=Math.max(row.chance,chance);row.count+=entry.count;row.sources.push({...entry,chance});
        }
      }
      const rows=[...items.values()].sort((a,b)=>b.chance-a.chance||this.data.items[a.item].name.localeCompare(this.data.items[b.item].name));
      this.lootCache.set(key,rows);return rows;
    }
    matches(query='',item=null,players=1,options={}){
      const q=root.atlasNormalize(query).trim();
      const sources=item===null?null:new Map(this.sourceMaps(item,players).map(s=>[s.map,s]));
      return this.maps.map((map,index)=>({map:index,record:map,source:sources?.get(index)}))
        .filter(row=>(!q||this.names[row.map].includes(q)||root.atlasNormalize(options.world?.maps[row.map]?.guideName||'').includes(q))&&(!sources||sources.has(row.map))&&(!options.episode||options.world?.maps[row.map]?.episode===Number(options.episode)))
        .sort((a,b)=>{
          if(options.sort==='progression'){
            const am=options.world?.maps[a.map],bm=options.world?.maps[b.map];
            return (am?.episode??9)-(bm?.episode??9)||(am?.order??99999)-(bm?.order??99999)||a.map-b.map;
          }
          if(options.sort!=='name'&&sources)return b.source.chance-a.source.chance||a.map-b.map;
          return a.record.name.localeCompare(b.record.name,'en')||a.map-b.map;
        });
    }
  }
  root.AtlasMapModel=AtlasMapModel;
  if(typeof module!=='undefined')module.exports={AtlasMapModel};
})(typeof window!=='undefined'?window:globalThis);
