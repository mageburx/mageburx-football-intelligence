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

test('separate reliability distinguishes historical Dutch testing from untested leagues',()=>{
  app.parseData(snapshot());
  app.setExpansionReliability({leagues:{
    nl:{completed:65,upcoming:230,partial:true,
        holdout:{season:'2024-2025',metrics:{n:230}},
        best_available_1x2:{n:230,brier:0.59},
        prospective:{settled:0},prospective_1x2:{issued:18,settled:0,brier:null},
        quality:'historical_holdout_available_not_proof_of_profit'},
    dk2:{completed:16,upcoming:0,partial:true,
         best_available_1x2:{n:0,brier:null},prospective:{settled:0},
         quality:'insufficient_independent_holdout'},
    no:{completed:16,upcoming:0,partial:true,
         best_available_1x2:{n:0,brier:null},prospective:{settled:0},
         quality:'insufficient_independent_holdout'},
  }});
  const view=app.renderReliability();
  for(const label of ['Fiabilidade por campeonato','Eredivisie','Eliteserien','1. Division',
                      'Teste histórico reservado','Histórico independente ainda insuficiente'])
    assert.ok(view.includes(label),label);
  assert.ok(view.includes('2024-2025'));
  assert.ok(view.includes('1X2 registado antes do jogo'));
  assert.ok(view.includes('18 · resultados avaliados: 0'));
  assert.ok(!view.includes('ROI positivo'));
});

test('prospective integrity audit separates pending from settled football predictions',()=>{
 app.parseData(snapshot());
 app.setExpansionReliability({leagues:{
  nl:{completed:63,upcoming:243,partial:true,best_available_1x2:{n:304,brier:.57},
      prospective:{settled:0},prospective_1x2:{issued:207,settled:0,brier:null},
      quality:'historical_holdout_available_not_proof_of_profit'},
  dk2:{completed:81,upcoming:51,partial:true,best_available_1x2:{n:48,brier:.7},
      prospective:{settled:0},prospective_1x2:{issued:51,settled:0,brier:null},
      quality:'insufficient_independent_holdout'},
  no:{completed:200,upcoming:40,partial:true,best_available_1x2:{n:169,brier:.6},
      prospective:{settled:0},prospective_1x2:{issued:40,settled:0,brier:null},
      quality:'insufficient_independent_holdout'}
 }});
 app.setExpansionAudit({status:'monitoring',leagues:{
  nl:{future:207,today:0,past_due:0,rescheduled:0,invalid:0,status:'awaiting_results'},
  dk2:{future:51,today:0,past_due:0,rescheduled:0,invalid:0,status:'awaiting_results'},
  no:{future:40,today:0,past_due:0,rescheduled:1,invalid:0,status:'schedule_change_review'}
 }});
 const view=app.renderReliability();
 assert.ok(view.includes('Integridade 1X2:'));
 assert.ok(view.includes('207 por jogar'));
 assert.ok(view.includes('1 reagendados'));
 assert.ok(view.includes('Conferir calendário atualizado.'));
});
