const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'app/index.html'),'utf8');
const script=fs.readFileSync(path.join(root,'app/app.js'),'utf8');
const original=JSON.parse(fs.readFileSync(path.join(root,'data/season.json'),'utf8'));
const stub=()=>({classList:{add(){},remove(){},toggle(){return false}},
 addEventListener(){},setAttribute(){},querySelector(){return stub()},
 innerHTML:'',textContent:'',dataset:{},title:''});
class Clock extends Date{
 constructor(...x){super(...(x.length?x:['2026-11-06T16:00:00Z']));}
 static now(){return Date.parse('2026-11-06T16:00:00Z');}
}
const sandbox={
 window:{scrollTo(){},innerWidth:1360},document:{
 querySelector(){return stub()},querySelectorAll(){return []},addEventListener(){}},
 Intl,Date:Clock,Math,Number,String,Map,Promise,
 fetch(){return Promise.resolve({ok:false,status:404})},
 localStorage:{getItem(){return null},setItem(){}},
};
vm.runInNewContext(script,sandbox);
const app=sandbox.window.FootballLabTest;
function snapshot(){
 const obj=JSON.parse(JSON.stringify(original));
 for(const [lid,id,home,away,day] of [
  ['nl',4337,'Ajax','PSV','2026-11-22'],
  ['dk2',4683,'AaB','Vejle','2026-11-20'],
  ['no',4358,'Bodø/Glimt','Rosenborg','2026-11-28']
 ]){
   obj.leagues[lid]={id,partial:true,events:[
    {id:lid+'-done',date:'2026-10-20',round:8,home,away,
     home_score:1,away_score:0,finished:true},
    {id:lid+'-upcoming',date:day,round:21,home,away,
     home_score:null,away_score:null,finished:false}
   ]};
 }
 return obj;
}
test('new leagues available as distinct filters',()=>{
 for(const [code,label] of [['nl','Eredivisie'],['dk2','1. Division'],['no','Eliteserien']]){
  assert.ok(html.includes('data-league="'+code+'"'),code);
  assert.ok(html.includes(label),label);
 }
 assert.ok(html.includes('Noruega 2026'));
});
test('five league dashboard includes new fixtures without requiring invented history',()=>{
 const d=snapshot();
 app.parseData(d);
 const summary=app.getStats();
 assert.equal(summary.loaded,
  Object.values(d.leagues).reduce((n,l)=>n+l.events.length,0));
 const home=app.renderOverview();
 assert.ok(home.includes('Próximos jogos'));
 assert.ok(home.includes('data-open-match='));
 assert.ok(home.includes('em recolha') || home.includes('recolha'));
});
test('existing PT/DK fixtures and forecasts remain usable',()=>{
 const d=snapshot();
 app.parseData(d);
 assert.ok(d.leagues.pt.events.length>0);
 assert.ok(d.leagues.dk.events.length>0);
 assert.ok(app.renderBriefing().includes('model-match'));
});
