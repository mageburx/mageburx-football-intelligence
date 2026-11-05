const fs = require('fs'), path=require('path'), vm=require('vm'), assert=require('assert');
const root=path.resolve(__dirname,'..');
const json=JSON.parse(fs.readFileSync(path.join(root,'data/season.json'),'utf8'));
const mock=()=>({classList:{add(){},remove(){},toggle(){}},addEventListener(){},querySelector(){return mock()},textContent:'',innerHTML:'',dataset:{},title:''});
const sandbox={
  window:{scrollTo(){},innerWidth:1440},
  document:{querySelector(){return mock()},querySelectorAll(){return []},addEventListener(){}},
  Intl,Date,Math,Number,String,Map,Promise,
  fetch(){return Promise.resolve({ok:false,status:404})},
  localStorage:{getItem(){return null},setItem(){}},
};
vm.runInNewContext(fs.readFileSync(path.join(root,'app/app.js'),'utf8'),sandbox);
const app=sandbox.window.FootballLabTest;
app.parseData(json);
const stats=app.getStats();
assert(stats.finished>0 && stats.loaded>50, 'Snapshot real de ambas as ligas');
for(const lid of ['pt','dk']){
  const matches=json.leagues[lid].events;
  const full=app.standings(matches);
  assert(full.length>=12,'Diversidade de equipas');
  assert.strictEqual(full.reduce((s,t)=>s+t.played,0),2*matches.filter(e=>e.finished).length);
  const future=matches.find(e=>!e.finished);
  const p=app.predict(future,matches);
  assert(p && Math.abs(p.p1+p.px+p.p2-1)<1e-7,'Poisson normalizado');
  for(const k of ['p1','px','p2','over','btts']) assert(p[k]>=0 && p[k]<=1,k);
}
console.log('OK: snapshot, classificação de ambas as ligas, Poisson e limites probabilísticos');
