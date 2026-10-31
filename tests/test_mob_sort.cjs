'use strict';
const assert=require('node:assert/strict');
const {AtlasModel}=require('../app/model.js');
const v=(xp,map)=>({experience:xp===null?undefined:[xp,xp],locations:[[map,1]]});
const mobs=[
  {id:0,name:'Early Weak',variants:[v(10,0)]},
  {id:1,name:'Later Strong',variants:[v(100000,3),v(800,1)]},
  {id:2,name:'Early Strong',variants:[v(100000,2)]},
  {id:3,name:'Unknown',variants:[v(null,4)]},
  {id:4,name:'Zero EXP',variants:[v(0,0)]},
  {id:5,name:'Late Unknown Map',variants:[v(200,4)]}
];
const world={maps:[{episode:1,order:0},{episode:1,order:20},{episode:1,order:10},{episode:4,order:0}]};
const data={items:[],mobs,maps:[{},{},{},{},{}],provenance:{}};
const model=new AtlasModel(data);
const sorted=sort=>[...mobs].sort((a,b)=>model.compareMobs(a,b,sort,world)).map(m=>m.id);
assert.deepEqual(sorted('exp-desc'),[2,1,5,0,4,3]);
assert.deepEqual(sorted('exp-asc'),[4,0,5,2,1,3]);
assert.deepEqual(sorted('progression'),[0,4,2,1,5,3]);
assert.deepEqual(model.mobExperience(mobs[1]),{min:800,max:100000,variant:0});
assert.deepEqual(model.firstAppearance(mobs[1],world),{map:1,variant:1,episode:1,order:20});
assert.equal(model.firstAppearance(mobs[0],world).order,0);
assert.deepEqual(model.mobExperience(mobs[3]),{min:null,max:null,variant:0});
assert.equal(model.firstAppearance({variants:[]},world).map,null);
assert.deepEqual(model.mobMatches('Strong').sort((a,b)=>model.compareMobs(a,b,'exp-desc',world)).map(m=>m.id),[2,1]);
console.log('PASS: mob raw EXP, variant selection, first map progression, zero and unknown values');
