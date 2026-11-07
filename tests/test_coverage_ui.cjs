const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs'),vm=require('vm'),path=require('path');
const code=fs.readFileSync(path.join(__dirname,'../app/coverage.js'),'utf8');
const ctx={window:{},Date,Intl,Number,String};
vm.runInNewContext(code,ctx);
const render=ctx.window.MageburxCoverage.render;
function report(){
 const hist={complete_seasons:4,seasons:[{season:'2021-2022',status:'source_complete'},
 {season:'2022-2023',status:'source_complete'},
 {season:'2023-2024',status:'source_complete'},
 {season:'2024-2025',status:'source_complete'},
 {season:'2025-2026',status:'incomplete',expected:306,completed_matches:305}]};
 return {schema:1,generated_at:'2026-11-07T00:15:00+00:00',leagues:{
  nl:{name:'Eredivisie',status:'partial',
      inventory:{observed_unique:306,expected_reference:306,verified_final:99,
        past_unverified:2,potential_duplicate_pairs:[],
        past_unverified_sample:[{date:'2026-11-05',home:'Ajax',away:'PSV'}]},
      rounds:{verification:'source_checked_subset',verified:30,total_reference:34,
        unverified:[4,5,6,7],unverified_count:4},
      history:hist,stats:{sample_checked:0,research_xg_recorded:0},
      sources:{source:'OpenFootball',conflicts:0},issues:[
        {code:'unverified_rounds',count:4,priority:'high'}]},
  pt:{name:'Portugal',status:'partial',inventory:{observed_unique:244,verified_final:100,past_unverified:0},
      rounds:{verification:'not_persisted',total_reference:34,verified:null},
      history:{complete_seasons:5,seasons:[]},stats:{sample_checked:2},sources:{source:'TheSportsDB'},
      issues:[]}},queue:[{league:'nl',priority:'high',code:'unverified_rounds',count:4,
        action:'Recheck source'}]};
}
test('separates observed fixture count from verified round coverage',()=>{
 const html=render(report(),'nl');
 assert.ok(html.includes('306 / 306'));
 assert.ok(html.includes('30 / 34'));
 assert.ok(html.includes('Jornadas por verificar (4)'));
 assert.ok(html.includes('4, 5, 6, 7'));
 assert.ok(html.includes('não garante completude'));
 assert.ok(html.includes('2025-2026'));
 assert.ok(!html.includes('Liga Portugal'));
});
test('shows missing sample and genuine alerts without claiming xG',()=>{
 const html=render(report(),'all');
 assert.ok(html.includes('Sem amostra'));
 assert.ok(html.includes('Jornadas ainda por verificar'));
 assert.ok(html.includes('Remates / xG'));
 assert.ok(html.includes('não foram alteradas'));
 assert.ok(html.includes('Liga Portugal'));
});
test('invalid report fails closed',()=>{
 assert.ok(render(null).includes('Auditoria não disponível'));
 assert.ok(render({schema:1}).includes('não disponível'));
});
