const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'app/index.html'),'utf8');
const src=fs.readFileSync(path.join(root,'app/app.js'),'utf8');
const season=JSON.parse(fs.readFileSync(path.join(root,'data/season.json'),'utf8'));
function mock(){
  return {classList:{add(){},remove(){},toggle(){return false}},addEventListener(){},
    querySelector(){return mock()},textContent:'',innerHTML:'',dataset:{},title:'',setAttribute(){}};
}
class Clock extends Date {
  constructor(...args){super(...(args.length?args:['2026-11-06T12:00:00Z']));}
  static now(){return Date.parse('2026-11-06T12:00:00Z');}
}
const scope={window:{scrollTo(){},innerWidth:1200},document:{
  querySelector(){return mock()},querySelectorAll(){return []},addEventListener(){}},
  Intl,Date:Clock,Math,Number,String,Map,Promise,
  fetch(){return Promise.resolve({ok:false,status:404})},
  localStorage:{getItem(){return null},setItem(){}},
};
vm.runInNewContext(src,scope);
const app=scope.window.FootballLabTest;
function loadFixtures(){
  // initialize() also resolves an asynchronous fallback; restore fixtures for
  // each test after that asynchronous setup has completed.
  app.parseData(season);
  app.setXGData({total_shadow_predictions:0,leagues:{pt:{xg_observations:3},dk:{xg_observations:3}}});
}

test('primary navigation is focused and advanced features remain accessible',()=>{
  const main=html.match(/<nav class="side-nav" aria-label="Secções principais">([\s\S]*?)<\/nav>/);
  assert.ok(main);
  assert.equal((main[1].match(/data-view=/g)||[]).length,5);
  for(const name of ['overview','briefings','matches','live','reliability'])
    assert.ok(main[1].includes('data-view="'+name+'"'));
  assert.ok(html.includes('id="advanced-menu"'));
  assert.ok(html.includes('data-view="value"'));
});

test('home prioritizes a selected game and no longer shows legacy charts',()=>{
  loadFixtures();
  const out=app.renderOverview();
  assert.ok(out.includes('JOGO EM DESTAQUE'));
  assert.ok(out.includes('data-open-match='));
  assert.ok(out.includes('Próximos jogos'));
  assert.ok(out.includes('Fiabilidade'));
  assert.ok(!out.includes('Golos por jornada'));
  assert.ok(!out.includes('Como usamos os dados'));
  assert.ok(!out.includes('Últimos 5'));
});

test('game detail exposes one clear analysis with optional full report',()=>{
  loadFixtures();
  const out=app.renderBriefing();
  assert.ok(out.includes('id="model-match"'));
  assert.ok(out.includes('ux-analysis'));
  assert.ok(out.includes('<details class="ux-details">'));
  assert.ok(out.includes('Ver análise completa'));
});

test('reliability shows distinct prospective and xG research counts',()=>{
  loadFixtures();
  const out=app.renderReliability();
  assert.ok(out.includes('Previsões antes do jogo'));
  assert.ok(out.includes('Poisson + xG'));
  assert.ok(out.includes('xg') || out.includes('xG'));
  assert.ok(out.includes('Consultar relatório técnico'));
});

test('game action listeners attach to every selected fixture',()=>{
  assert.match(src,/\$\$\('\[data-open-match\]'\)\.forEach/);
  assert.match(src,/\$\$\('\[data-goto\]'\)\.forEach/);
  assert.match(src,/\$\$\('\[data-more-games\]'\)\.forEach/);
});
