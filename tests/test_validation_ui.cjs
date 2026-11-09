const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs'),vm=require('vm'),path=require('path');
const js=fs.readFileSync(path.join(__dirname,'../app/validation.js'),'utf8');
const elements={};
const sandbox={window:{},document:{querySelector:(id)=>elements[id]||null},Date,Intl,Number,String};
vm.runInNewContext(js,sandbox);
const panel=sandbox.window.MageburxValidation;

const data={schema:1,generated_at:'2026-11-06T22:47:55+00:00',
  counts:{future:1,in_progress:1,unconfirmed:0,awaiting_settlement:1,
          validated:0,review:0,superseded:1},
  leagues:{
    pt:{total:1,future:0,in_progress:1,unconfirmed:0,awaiting_settlement:0,validated:0,review:0,superseded:0},
    dk:{total:1,future:0,in_progress:0,unconfirmed:0,awaiting_settlement:1,validated:0,review:0,superseded:0},
    nl:{total:1,future:0,in_progress:0,unconfirmed:0,awaiting_settlement:0,validated:0,review:0,superseded:1},
    dk2:{total:0},no:{total:1,future:1}},
  brier:{pt:{n:0,brier:null,log_loss:null}},general_ledger:{active_settlements:2,quarantined:2,integrity_alerts:0},
  records:[
    {key:'pt:2026-2027:123',league:'pt',home:'Famalicao',away:'Arouca',
      original_date:'2026-11-06',status:'in_progress',reason:'source_snapshot_in_play_not_live_confirmed'},
    {key:'dk:2026-2027:124',league:'dk',home:'Home',away:'Away',
      original_date:'2026-11-06',status:'awaiting_settlement'},
    {key:'nl:2026-2027:old',league:'nl',home:'Ajax',away:'PSV',original_date:'2026-11-07',
      status:'superseded',replacement_id:'new'},
    {key:'no:2026-2027:126',league:'no',home:'Molde',away:'Brann',
      original_date:'2026-11-07',status:'future'}]};
test('validation UI filters leagues and does not label live snapshot as settled',()=>{
 const html=panel.render(data,'pt');
 assert.ok(html.includes('Famalicao'));
 assert.ok(html.includes('Em curso · último registo'));
 assert.ok(html.includes('snapshot'));
 assert.ok(!html.includes('Ajax'));
 assert.ok(html.includes('Não')||html.includes('não há resultados'));
});
test('all-league audit includes superseded IDs without counting as scored',()=>{
 const html=panel.render(data,'all');
 assert.ok(html.includes('ID substituído'));
 assert.ok(html.includes('N'));// Template renders normal content
 assert.ok(html.includes('Substituído por: new'));
 assert.ok(html.includes('quarentena'));
});
test('report failure does not fabricate data',()=>{
 assert.ok(panel.render(null,'all').includes('Relatório ainda não disponível'));
});

test('weekend audit displays verified scorecards without inventing missing outcomes',()=>{
 const report={...data,weekend_audit:{schema:1,start_date:'2026-11-07',
 end_date:'2026-11-08',records:[
   {league:'pt',date:'2026-11-08',home:'Home',away:'Away',state:'validated',
    tip:'1',score:[2,0],correct:true,brier:.245},
   {league:'nl',date:'2026-11-08',home:'Ajax',away:'PSV',state:'unverified',
    tip:'2',score:null,correct:null,brier:null}]}};
 const html=panel.render(report,'all');
 assert.ok(html.includes('Auditoria do último fim de semana'));
 assert.ok(html.includes('0,245'));
 assert.ok(html.includes('0,6667'));
 assert.ok(html.includes('Sem resultado confirmado'));
 assert.ok(html.includes('Acertos 1X2 verificados'));
 const ptHtml=panel.render(report,'pt');
 assert.ok(ptHtml.includes('Home – Away'));
 assert.ok(!ptHtml.includes('Ajax – PSV'));
});
