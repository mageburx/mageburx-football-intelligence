/* Afonso OS Football Lab · 2026/27
 * Dados de pré-jogo, RSS de notícias, ausências verificáveis e modelo Poisson exploratório.
 * Não comunica nem opera contas de apostas.
 */
(() => {
  'use strict';
  const $ = (sel, parent = document) => parent.querySelector(sel);
  const $$ = (sel, parent = document) => [...parent.querySelectorAll(sel)];
  const safe = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const numberPT = new Intl.NumberFormat('pt-PT', {maximumFractionDigits: 1});
  const percent = v => `${numberPT.format(v * 100)}%`;
  const formatDate = str => {
    if (!str) return '—';
    const d = new Date(`${str.slice(0,10)}T12:00:00Z`);
    return Number.isFinite(d.valueOf()) ? d.toLocaleDateString('pt-PT', {day:'2-digit',month:'short'}) : '—';
  };
  const fullDate = str => {
    const date = new Date(str);
    return Number.isFinite(date.valueOf()) ? date.toLocaleString('pt-PT', {day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Lisbon'}) : 'Não disponível';
  };
  const saved = (key, fallback) => { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } };
  const store = (key, val) => { try { localStorage.setItem(key, val); } catch {} };
  const state = {data: null, intelligence: null, model: null, reliability: null, ledger: null, quality: null, validation: null, storageStatus: null, scrapeReport: null, statsCoverage: null, shotsResearch: null, xgExperiment: null, valueEngine: null, featureImpact: null, scheduleContext: null, prematchLineups: null, multiImpact: null, ledgerHealth: null, europeanCoverage: null, valueMarket:'over_2_5', valueOdds:'', reliabilityMarket:'over_2_5', league: saved('footballlab-league','all'), view:'overview', search:'', newsFilter:'all', matchFilter:'upcoming', modelMatch:'', matchLimit:30};
  const leagueNames = {pt:'Liga Portugal',dk:'Superliga'};
  const views = {
    overview:['Início','Os próximos jogos, <em>sem ruído.</em>','Escolhe um jogo. Consulta as probabilidades e aprofunda apenas quando precisares.'],
    matches:['Jogos','Calendário e <em>resultados.</em>','Pesquisa uma equipa ou abre a análise de um encontro.'],
    table:['Classificações','Cada ponto <em>conta.</em>','Classificações calculadas a partir dos jogos efetivamente recolhidos.'],
    briefings:['Analisar jogo','Uma previsão, <em>de cada vez.</em>','Probabilidades primeiro. Os detalhes técnicos ficam à escolha.'],
    news:['Notícias & sinais','A informação certa. <em>Com origem.</em>','Títulos recolhidos por RSS, ligados à fonte original e sujeitos a confirmação.'],
    absences:['Lesões & castigos','Disponibilidade <em>sob escrutínio.</em>','Diferencia baixa confirmada pelo fornecedor, dúvida e ausência de dados.'],
    model:['Modelo estatístico','Probabilidades, <em>não certezas.</em>','Poisson, Dixon–Coles, Elo e testes cronológicos de qualidade das previsões.'],
    value:['Value & Confidence','O preço importa. <em>A evidência ainda mais.</em>','Simulador de odds reais introduzidas manualmente e probabilidades calibradas experimentalmente.'],
    reliability:['Fiabilidade','Até que ponto <em>podemos confiar?</em>','Resultados reais e histórico, sem confundir simulações com previsões antecipadas.']
  };
  const isFinished = e => e.finished === true && Number.isInteger(e.home_score) && Number.isInteger(e.away_score);
  const rows = league => (state.data?.leagues?.[league]?.events || []).filter(e => e && e.home && e.away && e.date);
  function activeLeagues() { return state.league === 'all' ? ['pt','dk'] : [state.league]; }
  function games() {return activeLeagues().flatMap(lid=>rows(lid).map(e=>({...e,league:lid}))).sort((a,b)=>String(a.date).localeCompare(String(b.date)));}
  function scored() {return games().filter(isFinished);}
  function forthcoming() {return games().filter(e=>!isFinished(e) && e.date >= new Date().toISOString().slice(0,10)).sort((a,b)=>String(a.utc||a.date).localeCompare(String(b.utc||b.date)));}
  function standings(events) {
    const tab = new Map();
    const get = team => {
      if (!tab.has(team)) tab.set(team,{name:team,played:0,wins:0,draws:0,losses:0,gf:0,ga:0,points:0,form:[],home:{p:0,gf:0,ga:0},away:{p:0,gf:0,ga:0}});
      return tab.get(team);
    };
    for(const e of events){
      const h=get(e.home),a=get(e.away);
      if(!isFinished(e)) continue;
      h.played++;a.played++;h.gf+=e.home_score;h.ga+=e.away_score;a.gf+=e.away_score;a.ga+=e.home_score;
      h.home.p++;h.home.gf+=e.home_score;h.home.ga+=e.away_score;
      a.away.p++;a.away.gf+=e.away_score;a.away.ga+=e.home_score;
      if(e.home_score>e.away_score){h.wins++;h.points+=3;a.losses++;h.form.push('w');a.form.push('l');}
      else if(e.home_score<e.away_score){a.wins++;a.points+=3;h.losses++;h.form.push('l');a.form.push('w');}
      else {h.draws++;a.draws++;h.points++;a.points++;h.form.push('d');a.form.push('d');}
    }
    return [...tab.values()].filter(t=>t.played).sort((a,b)=>b.points-a.points||(b.gf-b.ga)-(a.gf-a.ga)||b.gf-a.gf||a.name.localeCompare(b.name));
  }
  function factorial(n) {let r=1;for(let i=2;i<=n;i++)r*=i;return r;}
  function poisson(k,lambda){return Math.exp(-lambda)*Math.pow(lambda,k)/factorial(k);}
  // Valores suavizados com a média do campeonato e cinco jogos anteriores implícitos.
  function predict(match, leagueEvents) {
    const completed=leagueEvents.filter(isFinished), N=completed.length;
    if(!N) return null;
    const homeMean = completed.reduce((s,e)=>s+e.home_score,0)/N;
    const awayMean = completed.reduce((s,e)=>s+e.away_score,0)/N;
    const tab = standings(completed);
    const h = tab.find(t=>t.name===match.home),a=tab.find(t=>t.name===match.away);
    if(!h||!a) return null;
    const prior=5;
    const smoothed=(sum,count,mean)=>(sum+prior*mean)/(count+prior);
    const hOff=smoothed(h.home.gf,h.home.p,homeMean);
    const aDef=smoothed(a.away.ga,a.away.p,homeMean);
    const aOff=smoothed(a.away.gf,a.away.p,awayMean);
    const hDef=smoothed(h.home.ga,h.home.p,awayMean);
    const lambdaH=Math.max(.15,Math.min(4.1,(hOff*aDef)/Math.max(.5,homeMean)));
    const lambdaA=Math.max(.15,Math.min(4.1,(aOff*hDef)/Math.max(.5,awayMean)));
    let p1=0,px=0,p2=0,over=0,btts=0,total=0;
    for(let i=0;i<=12;i++)for(let j=0;j<=12;j++){
      const p=poisson(i,lambdaH)*poisson(j,lambdaA);total+=p;
      if(i>j)p1+=p;else if(i===j)px+=p;else p2+=p;
      if(i+j>=3)over+=p;
      if(i>0&&j>0)btts+=p;
    }
    const count=Math.min(h.played,a.played);
    return {p1:p1/total,px:px/total,p2:p2/total,over:over/total,btts:btts/total,
      lambdaH,lambdaA,homeMatches:h.played,awayMatches:a.played,leagueMatches:N,
      note:count<10?'Amostra reduzida — baixa confiança':count<20?'Amostra ainda limitada':'Estimativa sujeita a erros e vieses'};
  }
  function getStats(){const finished=scored(),all=games(),g=finished.reduce((sum,e)=>sum+e.home_score+e.away_score,0);
    return {finished:finished.length,goals:g,avg:finished.length?g/finished.length:0,
      homeWon:finished.filter(e=>e.home_score>e.away_score).length,
      draws:finished.filter(e=>e.home_score===e.away_score).length,
      awayWon:finished.filter(e=>e.home_score<e.away_score).length,
      upcoming:forthcoming().length,loaded:all.length};}
  function tableMarkup(e, max=9){const teams=standings(e);if(!teams.length)return `<div class="empty"><b>A recolher resultados</b>A tabela aparece assim que existirem jogos terminados.</div>`;
    return `<div class="table-scroll"><table><thead><tr><th># &nbsp; Clube</th><th class="text-right">J</th><th class="text-right">V</th><th class="text-right">E</th><th class="text-right">D</th><th class="text-right">DG</th><th class="text-right">PTS</th><th>Últimos 5</th></tr></thead><tbody>${teams.slice(0,max).map((t,i)=>`<tr><td class="team-cell"><span class="rank ${i<3?'top':''}">${i+1}.</span><span class="team-name"><span class="tiny-shield">${safe(t.name.slice(0,2).toUpperCase())}</span>${safe(t.name)}</span></td><td class="text-right">${t.played}</td><td class="text-right">${t.wins}</td><td class="text-right">${t.draws}</td><td class="text-right">${t.losses}</td><td class="text-right">${(t.gf-t.ga)>0?'+':''}${t.gf-t.ga}</td><td class="text-right points">${t.points}</td><td><span class="form-cell">${t.form.slice(-5).map(x=>`<span class="form-dot ${x}">${x==='w'?'V':x==='d'?'E':'D'}</span>`).join('')}</span></td></tr>`).join('')}</tbody></table></div>`;}
  const matchRow=(e,includeLeague=true)=>`<div class="match-item"><div class="match-date">${formatDate(e.date)}<br/><span class="match-league">J${e.round||'—'}${includeLeague?' · '+safe((e.league||'').toUpperCase()):''}</span></div><div class="match-clubs"><div><strong>${safe(e.home)}</strong><span class="score">${isFinished(e)?e.home_score:'–'}</span></div><div><strong>${safe(e.away)}</strong><span class="score">${isFinished(e)?e.away_score:'–'}</span></div></div><span class="match-pill">${isFinished(e)?'FINAL':'POR JOGAR'}</span></div>`;
  // Focus view: one prediction + shortlist. All diagnostics are elsewhere.
  function publicForecast(e){
    const item=state.model?.leagues?.[e.league]?.predictions?.[String(e.id)];
    const fresh=state.model?.generated_at && state.data?.updated_at &&
      state.model.generated_at>=state.data.updated_at;
    return fresh && item && [item.p1,item.px,item.p2].every(Number.isFinite)?item:null;
  }
  function conciseProbabilities(p){
    if(!p)return '<p class="ux-note">Previsão ainda indisponível para este encontro.</p>';
    const total=p.p1+p.px+p.p2;
    if(!Number.isFinite(total)||total<=0)return '<p class="ux-note">Probabilidade indisponível.</p>';
    const values=[p.p1/total,p.px/total,p.p2/total];
    return '<div class="ux-prob-grid">'+[['Casa',values[0]],['Empate',values[1]],['Fora',values[2]]].map(([name,v])=>
      '<div class="ux-prob"><small>'+name+'</small><strong>'+percent(v)+'</strong></div>').join('')+
      '</div><div class="ux-prob-track" role="img" aria-label="Casa '+percent(values[0])+', empate '+percent(values[1])+', fora '+percent(values[2])+'">'+
      values.map(v=>'<span style="width:'+(100*v).toFixed(3)+'%"></span>').join('')+'</div>';
  }
  function compactFixture(e){
    return '<button type="button" class="ux-fixture" data-open-match="'+safe(e.league+':'+e.id)+'" aria-label="Analisar '+safe(e.home)+' contra '+safe(e.away)+'">'+
      '<small>'+safe(leagueNames[e.league])+' · '+formatDate(e.date)+'</small>'+
      '<strong>'+safe(e.home)+' <span>vs</span> '+safe(e.away)+'</strong>'+
      '<span class="ux-fixture-link">Analisar →</span></button>';
  }
  function overview(){
    const next=forthcoming().slice(0,7);
    const selected=next.find(e=>publicForecast(e))||next[0];
    const others=next.filter(e=>e!==selected).slice(0,5);
    const p=selected?publicForecast(selected):null;
    const past=state.reliability?.prospective;
    const xg=state.xgExperiment;
    const observed=Object.values(xg?.leagues||{}).reduce((n,a)=>n+(a.xg_observations||0),0);
    return '<section class="panel ux-hero"><div class="ux-hero-top"><span>JOGO EM DESTAQUE</span>'+
      (selected?'<small>'+safe(leagueNames[selected.league])+' · '+formatDate(selected.date)+'</small>':'')+'</div>'+
      (selected?'<h2>'+safe(selected.home)+' <em>vs</em> '+safe(selected.away)+'</h2>'+
      '<p>Probabilidades estimadas para o resultado final</p>'+conciseProbabilities(p)+
      '<div class="ux-hero-actions"><button class="ux-primary" type="button" data-open-match="'+safe(selected.league+':'+selected.id)+'">Analisar este jogo →</button>'+
      '<small>Modelo experimental, sem garantia de resultado.</small></div>':
      '<div class="empty"><b>Sem próximos jogos</b>Seleciona outra liga ou consulta o calendário.</div>')+'</section>'+
      '<section class="ux-home-section"><div class="ux-heading"><div><h2>Próximos jogos</h2><p>Escolhe um jogo para ver a previsão.</p></div>'+
      '<button data-goto="matches" class="ux-link">Ver todos →</button></div>'+
      (others.length?'<div class="ux-fixtures">'+others.map(compactFixture).join('')+'</div>':
      '<p class="ux-note">Ainda não existem outros encontros na seleção.</p>')+'</section>'+
      '<section class="ux-home-section ux-muted-section"><div class="ux-heading"><div><h2>Fiabilidade</h2><p>O que já foi medido, sem promessas.</p></div>'+
      '<button data-goto="reliability" class="ux-link">Ver detalhe →</button></div>'+
      '<div class="ux-stats"><span><b>'+(past?.logged??'—')+'</b> previsões guardadas</span>'+
      '<span><b>'+(past?.settled??'—')+'</b> resultados avaliados</span>'+
      '<span><b>'+observed+'</b> observações xG</span></div>'+
      '<p class="ux-note">O xG está a ser estudado separadamente e ainda não altera as probabilidades.</p></section>';
  }
  function matchView(){let items=games();let q=state.search.toLocaleLowerCase('pt-PT').trim();if(q)items=items.filter(e=>(e.home+' '+e.away).toLocaleLowerCase('pt-PT').includes(q));
    if(state.matchFilter==='finished')items=items.filter(isFinished);
    if(state.matchFilter==='upcoming')items=items.filter(e=>!isFinished(e)&&e.date>=new Date().toISOString().slice(0,10));
    if(state.matchFilter==='upcoming')items.sort((a,b)=>String(a.utc||a.date).localeCompare(String(b.utc||b.date)));
    else items.sort((a,b)=>String(b.date).localeCompare(String(a.date)));
    return `<div class="toolbar"><div><span class="pill-label">${items.length} encontros</span> <span class="muted">· Época 2026/27</span></div><div style="display:flex;gap:9px;flex-wrap:wrap"><input id="match-search" class="searchbox" aria-label="Pesquisar clube" placeholder="Pesquisar por clube…" value="${safe(state.search)}" /><select id="match-filter" class="filter-select" aria-label="Filtrar jogos"><option value="all" ${state.matchFilter==='all'?'selected':''}>Todos os jogos</option><option value="finished" ${state.matchFilter==='finished'?'selected':''}>Resultados finais</option><option value="upcoming" ${state.matchFilter==='upcoming'?'selected':''}>Por jogar</option></select></div></div><section class="panel"><div class="panel-header"><div><h2>Calendário e resultados</h2><p>Fonte: TheSportsDB; datas apresentadas no fuso da informação recolhida</p></div></div><div class="match-list">${items.length?items.slice(0,state.matchLimit).map(e=>!isFinished(e)&&e.date>=new Date().toISOString().slice(0,10)?compactFixture(e):matchRow(e)).join(''):'<div class="empty"><b>Nenhum jogo encontrado</b>Altera os filtros ou aguarda a próxima atualização.</div>'}</div>${items.length>state.matchLimit?'<div class="ux-more"><button type="button" class="ux-link" data-more-games="1">Mostrar mais jogos →</button></div>':''}</section>`;
  }
  function tableView(){return activeLeagues().map(lid=>`<section class="panel" style="margin-bottom:20px"><div class="panel-header"><div><h2>${lid==='pt'?'🇵🇹':'🇩🇰'} ${safe(leagueNames[lid])}</h2><p>${rows(lid).filter(isFinished).length} jogos concluídos na fonte · classificação calculada</p></div><span class="tag">2026 / 27</span></div>${tableMarkup(rows(lid),99)}${lid==='dk'?`<div class="body-pad muted">Nota: a Superliga dinamarquesa divide-se em fases; esta classificação é uma soma simples dos jogos disponíveis e não substitui as tabelas oficiais após a divisão.</div>`:''}</section>`).join('');}
  function modelSelect(){const options=forthcoming().filter(e=>rows(e.league).filter(isFinished).length>0).slice(0,90);
    if(!options.length)return `<div class="empty"><b>Faltam jogos futuros ou resultados de referência</b>A recolha completa permite gerar análises para os próximos encontros.</div>`;
    if(!state.modelMatch||!options.some(e=>e.league+':'+e.id===state.modelMatch))state.modelMatch=options[0].league+':'+options[0].id;
    return `<label class="choice-label" for="model-match">SELECIONAR ENCONTRO</label><select id="model-match" class="input">${options.map(e=>`<option value="${safe(e.league+':'+e.id)}" ${state.modelMatch===e.league+':'+e.id?'selected':''}>${safe(e.league.toUpperCase())} · ${safe(e.home)} — ${safe(e.away)} · ${formatDate(e.date)}</option>`).join('')}</select>`;
  }
  function currentModel(){const [lid,...id] = state.modelMatch.split(':');const event=rows(lid).find(e=>e.id===id.join(':'));
    if(!event) return null;
    const fresh = state.model?.generated_at && state.data?.updated_at &&
      state.model.generated_at >= state.data.updated_at;
    const next = fresh ? state.model?.leagues?.[lid]?.predictions?.[String(event.id)] : null;
    return {event,pred: next || predict(event,rows(lid)),lid, v3:!!next};}
  function probMarkup(p){return [['Vitória casa',p.p1],['Empate',p.px],['Vitória fora',p.p2]].map(([n,v])=>`<div class="prob-row"><span>${n}</span><div class="prob-bar"><span style="width:${Math.min(100,Math.max(0,v*100))}%"></span></div><b>${percent(v)}</b></div>`).join('');}
  function probabilityStrip(p){
    const values=[Number(p.p1),Number(p.px),Number(p.p2)];
    if(values.some(v=>!Number.isFinite(v)||v<0))return '';
    const sum=values.reduce((a,b)=>a+b,0);
    if(sum<=0)return '';
    const widths=values.map(v=>100*v/sum);
    return '<div class="fi-prob-section" aria-label="Probabilidades de vitória casa, empate e vitória visitante">'+
      '<div class="fi-prob-legend"><span><i class="fi-dot fi-home"></i>1 · Casa <strong>'+percent(values[0]/sum)+'</strong></span>'+
      '<span><i class="fi-dot fi-draw"></i>X · Empate <strong>'+percent(values[1]/sum)+'</strong></span>'+
      '<span><i class="fi-dot fi-away"></i>2 · Fora <strong>'+percent(values[2]/sum)+'</strong></span></div>'+
      '<div class="fi-prob-strip" role="img" aria-label="Casa '+percent(widths[0]/100)+', empate '+percent(widths[1]/100)+', fora '+percent(widths[2]/100)+'">'+
      '<span class="fi-home" style="width:'+widths[0].toFixed(4)+'%"></span>'+
      '<span class="fi-draw" style="width:'+widths[1].toFixed(4)+'%"></span>'+
      '<span class="fi-away" style="width:'+widths[2].toFixed(4)+'%"></span></div></div>';
  }
  function marketSuggestion(m){
    if(!m?.pred||!m.v3)return {text:'Sem sugestão: é necessário um modelo v3 atualizado.',odd:null};
    const p=m.pred;
    const league=state.model?.leagues?.[m.lid];
    if(league?.data_partial || state.data?.leagues?.[m.lid]?.partial)
      return {text:'Sem sugestão: a cobertura dos resultados desta liga está incompleta.',odd:null};
    if(!Number.isFinite(p.leagueMatches)||p.leagueMatches<60)
      return {text:'Sem sugestão: amostra histórica insuficiente (mínimo operacional: 60 jogos).',odd:null};
    const choices=[
      {name:'Vitória da equipa da casa (1)',prob:Number(p.p1)},
      {name:'Empate (X)',prob:Number(p.px)},
      {name:'Vitória da equipa visitante (2)',prob:Number(p.p2)}
    ].filter(c=>Number.isFinite(c.prob)&&c.prob>0&&c.prob<1);
    choices.sort((a,b)=>b.prob-a.prob);
    const best=choices[0];
    if(!best||best.prob<.65)return {text:'Sem aposta sugerida: nenhuma seleção 1X2 atinge o limiar exploratório de 65%.',odd:null};
    return {text:best.name,prob:best.prob,odd:1/best.prob};
  }
  function suggestionMarkup(m){
    const bet=marketSuggestion(m);
    const selected=bet.odd!==null;
    return '<div class="fi-market-card"><div class="fi-market-title"><span>Mercado para análise</span><span class="fi-market-tag">'+(selected?'SINAL ESTATÍSTICO':'SEM SINAL')+'</span></div>'+
      '<strong>'+safe(bet.text)+'</strong>'+
      (selected?'<div class="fi-market-details">Probabilidade estimada: <b>'+percent(bet.prob)+'</b> · Odd justa teórica: <b>'+numberPT.format(bet.odd)+'</b></div>':'')+
      '<p>Não é garantia nem demonstra vantagem económica. Sem odds reais verificadas e calibração independente, não é possível afirmar que existe uma aposta de valor. Não executar apostas automaticamente.</p></div>';
  }
  function extraMarketsMarkup(m){
    if(!m?.v3||!m.pred?.markets)return '<div class="limit-note">Os mercados adicionais requerem dados v3 atualizados.</div>';
    const market=m.pred.markets;
    const marketAudit=state.model?.leagues?.[m.lid]?.market_audit?.metrics||{};
    const rows=[
      ['Dupla oportunidade 1X','double_1x','1X2'],
      ['Dupla oportunidade X2','double_x2','1X2'],
      ['Dupla oportunidade 12','double_12','1X2'],
      ['Over 0.5 golos','over_0_5','Golos'],
      ['Under 0.5 golos','under_0_5','Golos'],
      ['Over 1.5 golos','over_1_5','Golos'],
      ['Under 1.5 golos','under_1_5','Golos'],
      ['Over 2.5 golos','over_2_5','Golos'],
      ['Under 2.5 golos','under_2_5','Golos'],
      ['Over 3.5 golos','over_3_5','Golos'],
      ['Under 3.5 golos','under_3_5','Golos'],
      ['Ambas marcam — Sim','btts_yes','Golos'],
      ['Ambas marcam — Não','btts_no','Golos'],
      ['Casa mais de 0.5 golos','home_over_0_5','Equipa'],
      ['Casa mais de 1.5 golos','home_over_1_5','Equipa'],
      ['Fora mais de 0.5 golos','away_over_0_5','Equipa'],
      ['Fora mais de 1.5 golos','away_over_1_5','Equipa']
    ];
    const items=rows.filter(r=>Number.isFinite(market[r[1]]) && market[r[1]]>0 && market[r[1]]<1);
    if(!items.length)return '';
    return '<section class="fi-extra"><div class="fi-extra-head"><h3>Mercados adicionais · dados gratuitos</h3><p>Probabilidades teóricas e odds justas, não recomendações de aposta.</p></div>'+
      '<div class="fi-extra-grid">'+items.map(([name,key,group])=>{
        const p=market[key];
        const backtest=marketAudit[key];
        const label=!backtest?'Aguardando backtesting':backtest.n<100?'Amostra pequena · sem validação':backtest.brier_skill>0?'Supera referência no histórico · por validar':'Não supera a referência';
        return '<div class="fi-extra-item"><small>'+group+'</small><strong>'+name+'</strong><div><b>'+percent(p)+'</b><span>Odd justa: '+numberPT.format(1/p)+'</span></div><em>'+safe(label)+'</em></div>';
      }).join('')+'</div>'+
      '<p class="muted fi-extra-note">Golos calculados pela distribuição Dixon–Coles de resultados; dupla oportunidade pelo modelo 1X2 selecionado. Sem odds reais, validação independente ou dados de cantos/cartões.</p></section>';
  }
  function modelResult(){const m=currentModel();if(!m||!m.pred)return `<div class="empty"><b>Modelo sem dados suficientes</b>É necessário pelo menos um jogo concluído e informação das duas equipas.</div>`;
    const {event:e,pred:p}=m;return `<div class="detail-stack"><span class="pill-label">${safe(leagueNames[m.lid])}</span><span class="tag">${formatDate(e.date)} · Jornada ${e.round}</span></div><h3 class="subhead" style="font-size:18px;margin-top:15px">${safe(e.home)} <span style="color:#7896a8">vs</span> ${safe(e.away)}</h3><div class="stat-caption">Golos esperados estimados: ${numberPT.format(p.lambdaH)} — ${numberPT.format(p.lambdaA)} · ${m.v3?"Motor v3 ("+safe(p.model)+")":"Poisson legado — v3 indisponível"}</div>${probabilityStrip(p)}${probMarkup(p)}${suggestionMarkup(m)}${extraMarketsMarkup(m)}
      <div class="big-prob"><div><b>${percent(p.over)}</b><small>Mais de 2,5 golos</small></div><div><b>${percent(p.btts)}</b><small>Ambas marcam</small></div></div><div class="limit-note"><b>${safe(p.note)}.</b> As probabilidades NÃO são ajustadas por ausências, notícias ou descanso, porque ainda não existe calibração histórica. Consulta o dossiê pré-jogo.</div>`;
  }
  function marketAuditView(data){
    const audit=data?.market_audit;
    if(!audit?.metrics)return '<div class="limit-note">A auditoria por mercado ainda não está disponível.</div>';
    const metrics=audit.metrics;
    const sets=[
      ['Dupla oportunidade',[['1X','double_1x'],['X2','double_x2'],['12','double_12']]],
      ['Golos e ambas marcam',[['Over 0.5','over_0_5'],['Under 0.5','under_0_5'],['Over 1.5','over_1_5'],['Under 1.5','under_1_5'],['Over 2.5','over_2_5'],['Under 2.5','under_2_5'],['Over 3.5','over_3_5'],['Under 3.5','under_3_5'],['Ambas marcam Sim','btts_yes'],['Ambas marcam Não','btts_no']]],
      ['Golos por equipa',[['Casa Over 0.5','home_over_0_5'],['Casa Over 1.5','home_over_1_5'],['Fora Over 0.5','away_over_0_5'],['Fora Over 1.5','away_over_1_5']]]
    ];
    const fmt=v=>Number.isFinite(v)?numberPT.format(v):'—', pct=v=>Number.isFinite(v)?percent(v):'—';
    const buildRow=([label,key])=>{
      const a=metrics[key]||{};
      const status=a.n<100?'Amostra reduzida':a.brier_skill>0?'Exploratório':'Não supera referência';
      const bins=(a.calibration_bins||[]).map(b=>'<span>'+safe(b.range)+' · N='+b.n+' · Previsto '+pct(b.mean_prediction)+' · Observado '+pct(b.observed_frequency)+'</span>').join('');
      return '<tr><td class="fi-market-name">'+safe(label)+'<small>'+safe(status)+'</small>'+
        (bins?'<details class="fi-bin-details"><summary>Calibração</summary><div>'+bins+'</div></details>':'')+
        '</td><td class="text-right">'+(a.n??0)+'</td><td class="text-right">'+fmt(a.brier)+'</td>'+
        '<td class="text-right">'+fmt(a.baseline_brier)+'</td><td class="text-right">'+pct(a.brier_skill)+'</td>'+
        '<td class="text-right">'+pct(a.calibration_error)+'</td></tr>';
    };
    return '<section class="panel fi-audit-panel"><div class="panel-header"><div><h2>Backtesting por mercado</h2><p>Resultados previstos exclusivamente com jogos anteriores</p></div><span class="tag">AUDITORIA</span></div><div class="body-pad">'+
      '<p class="muted">Brier e ECE: mais baixos são melhores. A referência usa a frequência histórica do mercado, conhecida antes do jogo. Skill positivo indica Brier menor que essa referência, <b>não indica rentabilidade</b>.</p>'+
      (data?.data_partial?'<div class="limit-note">Cobertura de resultados parcialmente incompleta nesta liga.</div>':'')+
      sets.map(([name,rows],i)=>'<details class="fi-audit-group" '+(i===1?'open':'')+'><summary>'+safe(name)+' <span>'+rows.length+' mercados</span></summary><div class="table-scroll"><table><thead><tr><th>Mercado</th><th class="text-right">N</th><th class="text-right">Brier ↓</th><th class="text-right">Base ↓</th><th class="text-right">Skill</th><th class="text-right">ECE ↓</th></tr></thead><tbody>'+rows.map(buildRow).join('')+'</tbody></table></div></details>').join('')+
      '<p class="muted fi-extra-note">Dupla oportunidade avaliada com Dixon–Coles fixo, não necessariamente com o modelo 1X2 atualmente selecionado. Todos os resultados são exploratórios; ainda é necessária validação independente.</p></div></section>';
  }
  const VALUE_MARKETS=[
    ['over_0_5','Mais de 0,5 golos'],['under_0_5','Menos de 0,5 golos'],
    ['over_1_5','Mais de 1,5 golos'],['under_1_5','Menos de 1,5 golos'],
    ['over_2_5','Mais de 2,5 golos'],['under_2_5','Menos de 2,5 golos'],
    ['over_3_5','Mais de 3,5 golos'],['under_3_5','Menos de 3,5 golos'],
    ['btts_yes','Ambas marcam — Sim'],['btts_no','Ambas marcam — Não'],
    ['home_over_0_5','Casa: mais de 0,5 golos'],['home_over_1_5','Casa: mais de 1,5 golos'],
    ['away_over_0_5','Fora: mais de 0,5 golos'],['away_over_1_5','Fora: mais de 1,5 golos'],
    ['double_1x','Dupla oportunidade 1X'],['double_x2','Dupla oportunidade X2'],['double_12','Dupla oportunidade 12'],
    ['home_win','Vitória da equipa da casa (1)'],['draw','Empate (X)'],['away_win','Vitória visitante (2)']
  ];
  function v5Probability(m,market){
    if(!m?.pred)return null;
    const raw=market==='home_win'?m.pred.p1:market==='draw'?m.pred.px:
      market==='away_win'?m.pred.p2:m.pred.markets?.[market];
    if(typeof raw!=='number'||!Number.isFinite(raw)||raw<=0||raw>=1)return null;
    const audit=state.valueEngine?.leagues?.[m.lid];
    const entry=audit?.markets?.[market];
    const goalMarket=!market.startsWith('double_')&&!['home_win','draw','away_win'].includes(market);
    const sameModel=goalMarket||(market.startsWith('double_')&&m.pred.model==='dc');
    const params=entry?.params;
    const canCalibrate=!!(sameModel&&m.v3&&audit?.status==='calibration_research_ready'&&
      params?.source_model==='fixed_dixon_coles'&&params.fit_n>=120&&
      Number.isFinite(params.intercept)&&Number.isFinite(params.slope));
    let calibrated=null;
    if(canCalibrate){
      const logodds=Math.log(Math.max(.000001,Math.min(.999999,raw))/(1-Math.max(.000001,Math.min(.999999,raw))));
      const z=params.intercept+params.slope*logodds;
      calibrated=Math.max(.000001,Math.min(.999999,1/(1+Math.exp(-z))));
    }
    const holdout=entry?.holdout?.calibrated;
    const n=holdout?.n||0;
    const evidence=n>=200?'Teste histórico disponível; vantagem não demonstrada':'Amostra independente insuficiente';
    return {raw,calibrated,used:calibrated??raw,evidence,n,
      holdout,entry,source:calibrated!==null?'Calibração experimental · Dixon–Coles':'Probabilidade não calibrada'};
  }
  function valueResult(){
    const m=currentModel();
    if(!m?.pred)return '<div class="limit-note">Não há previsão disponível para este encontro.</div>';
    const market=state.valueMarket;
    const p=v5Probability(m,market);
    if(!p)return '<div class="limit-note">O modelo não suporta este mercado para o jogo selecionado.</div>';
    const input=String(state.valueOdds||'').trim().replace(',','.');
    const odd=input?Number(input):NaN;
    const valid=Number.isFinite(odd)&&odd>=1.01&&odd<=1000;
    const breakEven=valid?1/odd:null;
    const expected=valid?(p.used*odd-1)*100:null;
    const fair=1/p.used;
    const info=p.entry?.holdout;
    const fmt=v=>Number.isFinite(v)?numberPT.format(v):'—';
    const pct=v=>Number.isFinite(v)?percent(v):'—';
    const comparison=valid?'<div class="fi-v5-result">'+
      '<div><small>Probabilidade mínima exigida pela odd</small><strong>'+pct(breakEven)+'</strong></div>'+
      '<div><small>EV matemático, não validado</small><strong>'+fmt(expected)+'%</strong></div>'+
      '</div><p class="muted">EV = (probabilidade estimada × odd − 1) × 100. Não inclui incerteza do modelo ou regras particulares da casa. Sem histórico de odds, não comprova rentabilidade.</p>':
      '<p class="muted">Introduz uma odd decimal real entre 1,01 e 1000 para comparar o preço. Não guardamos nem procuramos odds automaticamente.</p>';
    const warnings=[];
    if(!m.v3)warnings.push('Previsão v3 indisponível ou desatualizada.');
    if(!p.calibrated)warnings.push('Este mercado não possui calibração aplicável ao modelo ao vivo.');
    if(p.n<200)warnings.push('Amostra de teste reservada inferior a 200 jogos.');
    const prospective=state.reliability?.prospective?.metrics?.[m.lid]?.[market]?.n||0;
    if(prospective<200)warnings.push('Ainda sem 200 previsões prospetivas verificadas neste mercado.');
    if(state.data?.leagues?.[m.lid]?.partial)warnings.push('Cobertura de resultados da época atual incompleta.');
    const brier=info?.calibrated?.brier;
    return '<div class="fi-v5-analysis"><div class="fi-v5-top"><div><small>Mercado escolhido</small><h3>'+
      safe(VALUE_MARKETS.find(x=>x[0]===market)?.[1]||market)+'</h3></div>'+
      '<span class="fi-v5-state">APENAS SIMULAÇÃO</span></div>'+
      '<div class="fi-v5-prob"><div><small>Probabilidade original</small><strong>'+pct(p.raw)+'</strong></div>'+
      '<div><small>Probabilidade ajustada (experimental)</small><strong>'+
      (p.calibrated!==null?pct(p.calibrated):'Não aplicável')+'</strong></div>'+
      '<div><small>Odd justa teórica</small><strong>'+fmt(fair)+'</strong></div></div>'+
      '<p class="muted fi-v5-source">Base da estimativa: '+safe(p.source)+'. Calibração ajustada com 2024/25, nunca com jogos de 2025/26.</p>'+
      '<div class="fi-v5-odds"><label for="value-odd">Odd decimal introduzida manualmente</label>'+
      '<input id="value-odd" class="input" inputmode="decimal" type="text" autocomplete="off" placeholder="Ex.: 1,85" value="'+safe(state.valueOdds)+'" />'+
      '</div>'+comparison+
      '<div class="fi-v5-confidence"><strong>Estado: SEM APOSTA RECOMENDADA</strong>'+
      '<p>Não existe evidência prospetiva suficiente para afirmar vantagem econômica, mesmo que o EV teórico seja positivo.</p>'+
      '<p>Teste histórico do mercado: N='+p.n+' · Brier original: '+fmt(info?.raw?.brier)+' · Brier calibrado: '+fmt(brier)+' · Brier de referência: '+
      fmt(info?.calibrated?.baseline_brier)+' · '+safe(p.evidence)+'.</p>'+
      '<ul>'+warnings.map(x=>'<li>'+safe(x)+'</li>').join('')+'</ul></div></div>';
  }
  function contextSinceLeagueMatch(match){
    const played=rows(match.league).filter(e=>isFinished(e)&&e.date<match.date);
    function teamContext(team){
      const games=played.filter(e=>e.home===team||e.away===team)
        .sort((a,b)=>String(b.date).localeCompare(String(a.date)));
      const last=games.slice(0,5);
      const dateDiff=games.length?Math.round((Date.parse(match.date+'T12:00:00Z')-Date.parse(games[0].date+'T12:00:00Z'))/86400000):null;
      const rest=Number.isFinite(dateDiff)&&dateDiff>=1&&dateDiff<=60?dateDiff:null;
      const points=last.map(e=>{
        if(e.home_score===e.away_score)return 1;
        return (e.home===team?e.home_score>e.away_score:e.away_score>e.home_score)?3:0;
      });
      const pointsTotal=points.reduce((a,b)=>a+b,0);
      const last14=games.filter(e=>{
        const d=Math.round((Date.parse(match.date+'T12:00:00Z')-Date.parse(e.date+'T12:00:00Z'))/86400000);
        return d>0&&d<=14;
      }).length;
      return {rest,last14,ppg:last.length?pointsTotal/last.length:null,n:last.length};
    }
    return {home:teamContext(match.home),away:teamContext(match.away)};
  }
  function featureImpactView(){
    const active=currentModel();
    const lid=active?.lid||(state.league==='all'?'pt':state.league);
    const lab=state.featureImpact?.leagues?.[lid];
    const names={baseline:'Dixon–Coles sem novos fatores',
      rest:'Descanso entre jogos da liga',
      strength_adjusted_form:'Forma ajustada ao adversário',
      rest_plus_form:'Descanso + forma ajustada'};
    if(!lab)return '<section class="panel fi-factor-panel"><div class="panel-header"><h2>Laboratório de fatores · v5.1</h2></div><div class="body-pad"><p class="muted">Aguardando o estudo histórico.</p></div></section>';
    const fmt=v=>Number.isFinite(v)?numberPT.format(v):'—';
    const labels=Object.entries(lab.variants||{}).map(([key,stats])=>{
      const h=stats.holdout||{};
      return '<tr><td>'+safe(names[key]||key)+(key===lab.selected_on_2024_25?' <small>Selecionado em 2024/25</small>':'')+
        '</td><td class="text-right">'+(h.n??0)+'</td><td class="text-right">'+fmt(h.brier)+'</td>'+
        '<td class="text-right">'+fmt(h.log_loss)+'</td></tr>';
    }).join('');
    const selected=lab.selected_on_2024_25;
    const ci=lab.selected_holdout_ci95;
    const selectedCandidate=lab.variants?.[selected]?.holdout;
    const base=lab.variants?.baseline?.holdout;
    let status=lab.status==='blocked_incomplete_history'?'Histórico insuficiente':
      lab.status==='historical_lift_requires_prospective_replication'?'Melhoria histórica por confirmar':
      lab.status==='inconclusive_historical_lift'?'Melhoria não conclusiva':
      lab.status==='feature_model_worse_on_holdout'?'Pior do que o modelo simples':
      'Sem melhoria demonstrada';
    const context=active?.event?contextSinceLeagueMatch({...active.event,league:lid}):null;
    const formatTeam=(team,label)=>!team?'':('<div class="fi-factor-team"><b>'+safe(label)+'</b>'+
      '<span>Desde último jogo da liga: '+(team.rest===null?'Sem dados':team.rest+' dias')+'</span>'+
      '<span>Jogos da liga nos últimos 14 dias: '+team.last14+'</span>'+
      '<span>Forma simples dos últimos '+team.n+' jogos: '+(team.ppg===null?'—':fmt(team.ppg)+' pontos/jogo')+'</span></div>');
    return '<section class="panel fi-factor-panel"><div class="panel-header"><div><h2>Laboratório de fatores pré-jogo · v5.1</h2>'+
      '<p>O valor preditivo dos novos fatores é avaliado sem alterar o modelo em produção.</p></div><span class="tag">PESQUISA</span></div>'+
      '<div class="body-pad"><div class="fi-factor-kpis"><div><small>Modelo selecionado em 2024/25</small><strong>'+safe(names[selected]||'—')+'</strong></div>'+
      '<div><small>Teste reservado 2025/26</small><strong>'+safe(status)+'</strong></div></div>'+
      '<p class="muted">Brier 1X2 sem fatores: '+fmt(base?.brier)+' · Brier 1X2 do selecionado: '+fmt(selectedCandidate?.brier)+
      ' · Diferença: '+fmt(lab.selected_holdout_brier_gain)+' (menor Brier é melhor).'+
      (Array.isArray(ci)?' Intervalo aproximado de 95% para a diferença: '+ci.map(fmt).join(' a ')+'.':'')+'</p>'+
      '<div class="table-scroll"><table><thead><tr><th>Fatores ensaiados</th><th class="text-right">Jogos</th><th class="text-right">Brier 1X2 ↓</th><th class="text-right">Log Loss ↓</th></tr></thead>'+
      '<tbody>'+labels+'</tbody></table></div>'+
      (context?'<h3 class="fi-factor-subtitle">Contexto do encontro selecionado</h3><div class="fi-factor-teams">'+
       formatTeam(context.home,active.event.home)+formatTeam(context.away,active.event.away)+'</div>':'')+
      '<p class="muted fi-factor-note">Este estudo histórico v5.1 considera apenas jogos da liga. O novo painel v5.2 abaixo acrescenta os jogos de Taça e UEFA que conseguimos recolher, sem assumir cobertura completa. A forma simples acima não está ajustada ao adversário; o teste histórico utiliza uma medida separada baseada em Elo anterior a cada jogo. Isto mede utilidade preditiva, não causalidade. Lesões, onzes confirmados e xG ainda não estão integrados automaticamente.</p>'+
      '<div class="limit-note">Sem alteração das probabilidades ou das sugestões de aposta. Qualquer eventual melhoria precisa de replicação prospetiva e verificação de cobertura dos dados.</div></div></section>';
  }
  function multiCompetitionContextView(){
    const m=currentModel();
    const ctx=m?.event&&m?.lid?
      state.scheduleContext?.leagues?.[m.lid]?.fixtures?.[String(m.event.id)]:null;
    const report=state.scheduleContext;
    const observations=state.prematchLineups?.observations||[];
    const lining=observations.find(x=>m&&x.league===m.lid&&String(x.id)===String(m.event?.id));
    const fmt=v=>Number.isFinite(v)?String(v):'—';
    const quote=v=>safe(String(v??'—'));
    const teamCard=(x,label)=>'<div class="fi-factor-team"><b>'+safe(label)+'</b>'+
      '<span>Último encontro conhecido: '+quote(x?.last_known_match_date)+
      (x?.last_known_competition?' · '+quote(x.last_known_competition):'')+'</span>'+
      '<span>Dias desde último jogo conhecido: '+fmt(x?.days_since_last_known_match)+'</span>'+
      '<span>Jogos conhecidos nos últimos 7 / 14 dias: '+fmt(x?.matches_last_7)+' / '+fmt(x?.matches_last_14)+'</span>'+
      '<span>Taças e jogos UEFA conhecidos nos últimos 21 dias: '+fmt(x?.cup_europe_last_21)+'</span></div>';
    const games=report?.covered_competitions||{};
    const label={pt_cup:'Taça de Portugal',pt_league_cup:'Taça da Liga',
      uefa_cl:'Champions League',uefa_el:'Europa League',uefa_ecl:'Conference League',dk_cup:'Taça da Dinamarca'};
    const comps=Object.entries(games).filter(([key,value])=>value>0).map(([key,n])=>
       '<span class="fi-comp-source">'+safe(label[key]||key)+' · '+n+' jogos</span>').join('');
    const status=lining?.status==='observed_complete_pre_kickoff'?
      'Onze completo observado antes do início':
      lining?.status==='partial_lineup_not_for_absence_inference'?
      'Alinhamento parcial — não permite determinar ausências':
      lining?.status==='unverifiable_pre_kickoff_timestamp'?
      'Sem confirmação da hora de divulgação do onze':
      'Sem onze completo confirmado pela fonte gratuita';
    return '<section class="panel fi-multi-panel"><div class="panel-header"><div>'+
       '<h2>Descanso e calendário · Liga + Taças + UEFA</h2>'+
       '<p>Jogos conhecidos antes do encontro · fontes gratuitas</p></div><span class="tag">v5.2</span></div>'+
       '<div class="body-pad">'+
       (ctx?'<div class="fi-factor-teams">'+
          teamCard(ctx.home,m.event.home)+teamCard(ctx.away,m.event.away)+'</div>':
          '<div class="limit-note">Sem contexto de calendário adicional para este encontro.</div>')+
       '<div class="fi-comp-sources">'+(comps||'<span>Sem resultados adicionais recolhidos até agora.</span>')+'</div>'+
       '<div class="fi-lineup-status"><strong>Onzes pré-jogo</strong><p>'+safe(status)+
       (lining?' · '+fmt(lining.home_n)+' / '+fmt(lining.away_n)+' jogadores detetados.':'')+
       '</p></div>'+
       '<p class="muted fi-factor-note">Cobertura parcial: os números são um <b>mínimo de jogos conhecidos</b>. Podem faltar partidas de taças e UEFA, pelo que o descanso real pode ser menor. Não consideramos um jogador lesionado por não aparecer num alinhamento incompleto. Nenhum destes fatores altera automaticamente as probabilidades 1X2.</p>'+
       '</div></section>';
  }
  function multiImpactView(){
    const active=currentModel();
    const lid=active?.lid||(state.league==='all'?'pt':state.league);
    const result=state.multiImpact?.leagues?.[lid];
    const q=v=>Number.isFinite(v)?numberPT.format(v):'—';
    if(!result)return '<section class="panel fi-factor-panel"><div class="panel-header"><h2>Teste de carga competitiva · v5.3</h2></div><div class="body-pad"><p class="muted">Sem relatório histórico publicado.</p></div></section>';
    const status=result.status;
    const cup=(result.coverage||{});
    const coverage=Object.entries(cup).map(([season,c])=>
      '<tr><td>'+safe(season.replace('-','/'))+'</td><td class="text-right">'+
      (c.known_cross_matches??0)+'</td><td class="text-right">'+
      (c.known_domestic_cup_matches??'—')+'</td><td class="text-right">'+
      (c.known_european_matches??'—')+'</td><td class="text-right">'+
      (c.teams_with_additional_fixtures??0)+'/'+(c.league_teams??0)+
      '</td><td>'+(c.adequate_minimum_sample?'Amostra mínima':'Incompleta')+'</td></tr>').join('');
    const europe=state.europeanCoverage?.leagues||{};
    const euroRows=Object.values(europe).filter(x=>x.season==='2024-2025'||x.season==='2025-2026').map(x=>
      '<tr><td>'+safe(x.competition.replace('uefa_','').toUpperCase())+'</td>'+
      '<td>'+safe(x.season.replace('-','/'))+'</td>'+
      '<td class="text-right">'+(x.observed_matches??0)+'</td>'+
      '<td class="text-right">'+(x.unqueried_rounds_in_trial_window?.length??'—')+'</td></tr>').join('');
    const europeanAudit=euroRows?'<h3>Calendário UEFA histórico · cobertura observada</h3>'+
      '<div class="table-scroll"><table><thead><tr><th>Competição</th><th>Época</th><th class="text-right">Jogos</th><th class="text-right">Rondas não verificadas*</th></tr></thead><tbody>'+euroRows+'</tbody></table></div>'+
      '<p class="muted fi-factor-note">* Dentro das 10 rondas que o coletor tenta consultar, não do calendário oficial completo. A contagem de jogos é parcial e inclui equipas fora de Portugal e Dinamarca.</p>':'';
    const models=result.models||{};
    const candidates={baseline:'Sem calendário adicional',
      all_competitions_rest:'Descanso considerando taças/UEFA',
      rest_plus_cup_uefa_load:'Descanso + jogos extra'};
    const table=Object.entries(models).map(([key,v])=>
      '<tr><td>'+safe(candidates[key]||key)+'</td>'+
      '<td class="text-right">'+q(v.holdout?.brier)+'</td>'+
      '<td class="text-right">'+(v.holdout?.n??0)+'</td></tr>').join('');
    const success=status==='historical_lift_not_yet_prospective';
    return '<section class="panel fi-factor-panel"><div class="panel-header"><div>'+
      '<h2>Teste histórico de carga competitiva · v5.3</h2>'+
      '<p>Separação das épocas 2024/25 e 2025/26, sem alterar previsões.</p></div><span class="tag">EXPERIMENTAL</span></div>'+
      '<div class="body-pad"><p><strong>'+safe(success?'Sinal histórico a replicar':
        status==='blocked_sparse_cross_competition_history'?'Teste bloqueado: faltam jogos de taças/UEFA':
        status==='blocked_insufficient_exposed_fixtures'?'Teste bloqueado: amostra exposta insuficiente':
        'Sem melhoria robusta demonstrada')+'</strong></p>'+
      '<div class="table-scroll"><table><thead><tr><th>Época</th><th class="text-right">Jogos adicionais</th><th class="text-right">Taças</th><th class="text-right">UEFA</th><th class="text-right">Equipas abrangidas</th><th>Qualidade</th></tr></thead><tbody>'+coverage+'</tbody></table></div>'+
      (table?'<div class="table-scroll"><table><thead><tr><th>Variante</th><th class="text-right">Brier ↓</th><th class="text-right">Jogos</th></tr></thead><tbody>'+table+'</tbody></table></div>':'')+
      europeanAudit+
      '<p class="muted fi-factor-note">A cobertura histórica de competições extra não é certificada completa. Não transformamos jogos em falta em dias de descanso confirmados, nem apresentamos melhorias sem um teste independente e replicação prospetiva.</p></div></section>';
  }
  function valueView(){
    const options=VALUE_MARKETS.map(([k,name])=>'<option value="'+k+'" '+(state.valueMarket===k?'selected':'')+'>'+safe(name)+'</option>').join('');
    const active=state.league==='all'?'pt':state.league;
    const v=state.valueEngine?.leagues?.[active];
    const available=v?.status==='calibration_research_ready';
    return '<div class="fi-v5-grid"><section class="panel"><div class="panel-header"><div><h2>Value & Confidence Engine · v5</h2>'+
      '<p>Escolhe um jogo, um mercado e introduz uma odd real</p></div><span class="tag">SEM APOSTAS AUTOMÁTICAS</span></div>'+
      '<div class="body-pad">'+modelSelect()+
      '<div class="fi-v5-field"><label for="value-market">MERCADO PARA SIMULAÇÃO</label><select class="input" id="value-market">'+options+'</select></div>'+
      '<div id="value-result">'+valueResult()+'</div></div></section>'+
      '<section class="panel"><div class="panel-header"><div><h2>Calibração & limites</h2><p>Treino histórico sem antecipação de resultados</p></div></div>'+
      '<div class="body-pad"><div class="fi-v5-steps"><div><b>2021–24</b><span>Histórico anterior</span></div>'+
      '<div><b>2024/25</b><span>Ajuste da calibração</span></div>'+
      '<div><b>2025/26</b><span>Teste independente</span></div></div>'+
      '<div class="limit-note">'+(available?'Parâmetros de calibração disponíveis para estudo, não validados comercialmente.':
      'Dados históricos insuficientes para uma calibração aplicável.')+'</div>'+
      '<p class="muted">Comparamos Brier Score e Log Loss antes e depois do ajuste. Os parâmetros são fixados antes da época reservada para teste. Sem odds históricas e validação prospetiva, uma odd aparentemente favorável não representa uma oportunidade comprovada.</p>'+
      '<p class="muted">O modelo atual pode escolher Poisson ou Dixon–Coles com Elo para 1X2. Por isso só aplicamos a calibração Dixon–Coles quando a previsão ao vivo usa exatamente esse modelo; nos restantes casos mostramos a probabilidade original.</p>'+
      '<div class="fi-v5-steps"><div><b>'+((v?.validation_games)??'—')+'</b><span>Jogos para calibrar</span></div>'+
      '<div><b>'+((v?.test_games)??'—')+'</b><span>Jogos de teste</span></div></div></div></section></div>'+featureImpactView()+multiCompetitionContextView()+multiImpactView();
  }
  function modelView(){
    const chosen=state.league==='all'?'pt':state.league;
    const data=state.model?.leagues?.[chosen];
    const methods=[['poisson','Poisson independente'],['dc','Dixon–Coles'],['blend','Dixon–Coles + Elo']];
    const scores=data?.evaluations||{};
    const backtest=methods.map(([key,label])=>{const m=scores[key];return '<tr><td>'+label+'</td><td class="text-right">'+(m?.n??'—')+'</td><td class="text-right">'+(m?numberPT.format(m.brier):'—')+'</td><td class="text-right">'+(m?numberPT.format(m.log_loss):'—')+'</td></tr>';}).join('');
    const audit=data?'<div class="insight-card" style="margin-bottom:14px"><h3>Backtesting cronológico · '+safe(leagueNames[chosen])+'</h3><p>Cada jogo é previsto exclusivamente com dados de datas anteriores. A seleção é exploratória, sem teste independente.</p><div class="table-scroll"><table><thead><tr><th>Modelo</th><th class="text-right">Testes</th><th class="text-right">Brier ↓</th><th class="text-right">Log Loss ↓</th></tr></thead><tbody>'+backtest+'</tbody></table></div><p class="muted">Modelo selecionado: <b>'+safe(data.selected)+'</b> · '+data.played+' resultados disponíveis</p></div>':'<div class="limit-note">O motor v3 ainda não foi gerado. Mantém-se o Poisson legado.</div>';
    return '<div class="grid-2"><section class="panel"><div class="panel-header"><div><h2>Motor probabilístico · 1X2</h2><p>Golos e análise pré-jogo</p></div><span class="tag">MODELO v3</span></div><div class="body-pad">'+modelSelect()+'<div id="model-result" style="padding-top:22px">'+modelResult()+'</div></div></section><section class="panel"><div class="panel-header"><div><h2>Auditoria do modelo</h2><p>Verificar desempenho em resultados passados</p></div></div><div class="body-pad">'+audit+'<p class="muted model-note">Brier Score e Log Loss: quanto menores, melhores. Estimativas ainda sem calibração independente. Não incluem xG ou lesões por falta de cobertura verificada.</p></div></section></div>'+marketAuditView(data);
  }
  const dateOnly = v => String(v||'').slice(0,10);
  const safeLink = v => /^https:\/\/[^\s"'<>]+$/i.test(String(v||'')) ? safe(v) : '#';
  const intelligence = () => state.intelligence || {news:[],absences:[],warnings:[],news_status:'not_loaded',absences_status:'not_connected_or_unavailable'};
  const newsRows = () => (intelligence().news || []).filter(n => activeLeagues().includes(n.league));
  const absenceRows = () => (intelligence().absences || []).filter(a => activeLeagues().includes(a.league));
  const labelCategory = {lesao:'Possível lesão',castigo:'Possível castigo',onze:'Alinhamento',treinador:'Treinador',mercado:'Transferência',descanso:'Rotação/descanso',geral:'Geral'};
  const matchingNews = (lid, teams=[]) => newsRows().filter(n => n.league===lid && (!teams.length || (n.teams||[]).some(t=>teams.includes(t))));
  const matchingAbsences = (lid, teams=[]) => absenceRows().filter(a => a.league===lid && (!teams.length || teams.includes(a.team)));
  const badgeStatus = text => `<span class="chip">${safe(text)}</span>`;
  function headlineCard(n){return `<article class="news-item"><div class="news-meta"><span class="chip chip-dark">${safe(leagueNames[n.league]||'')}</span><span class="chip">${safe(labelCategory[n.category]||'Notícia')}</span><span>${safe(formatDate(n.published_at))}</span></div><a href="${safeLink(n.url)}" target="_blank" rel="noopener noreferrer" class="news-title">${safe(n.title)}</a><div class="news-detail">${safe(n.source||'Fonte original')} · ${(n.teams||[]).length?safe(n.teams.join(' · ')):'Sem equipa automaticamente identificada'} · <b>Manchete por confirmar</b></div></article>`;}
  function absenceCard(a){let type=String(a.status||'');return `<article class="absence-row"><div><strong>${safe(a.player||'Jogador')}</strong><div class="news-detail">${safe(a.team||'')} · ${safe(leagueNames[a.league]||'')} · ${formatDate(a.fixture_date)}</div></div><div class="absence-info"><span class="chip">${safe(type)}</span><span class="muted">${safe(a.reason||'Motivo não indicado')}</span><a href="${safeLink(a.source_url)}" target="_blank" rel="noopener noreferrer" class="news-source">Fonte: ${safe(a.source||'Fornecedor')}</a></div></article>`;}
  function absencesView(){let a=absenceRows().slice().sort((x,y)=>dateOnly(x.fixture_date).localeCompare(dateOnly(y.fixture_date)));
    return `<div class="callout intel-callout"><b>Disponibilidade: ${intelligence().absences_status==='provider_available'?'ligação ao fornecedor ativa na última recolha':'sem cobertura automática confirmada'}</b><div>Uma lista vazia significa <b>dados insuficientes</b>, nunca “todos aptos”. As notícias só são pistas a verificar. Uma baixa é registada apenas por API especializada ou entrada editorial acompanhada de fonte.</div></div>
    <div class="cards compact-cards"><div class="stat-card"><div class="stat-top">Registos com fonte</div><div class="stat-num">${a.length}</div><div class="stat-detail">Não equivale ao total real de indisponíveis</div></div><div class="stat-card"><div class="stat-top">Fonte especializada</div><div class="stat-num text-status">${intelligence().absences_status==='provider_available'?'Ativa':'Por configurar'}</div><div class="stat-detail">API-Football, chave opcional na cloud</div></div></div>
    <section class="panel"><div class="panel-header"><div><h2>Registos de indisponibilidade</h2><p>Próximos 15 dias quando reportados</p></div>${badgeStatus('Dados com origem')}</div>${a.length?`<div class="intelligence-list">${a.map(absenceCard).join('')}</div>`:`<div class="empty"><b>Não existem ausências verificadas carregadas</b>Ainda não há ligação a uma fonte com cobertura comprovada. Isso não significa que não existam lesões ou castigos.</div>`}</section><div class="source-note">Fontes potenciais: API-Football, comunicados oficiais. A cobertura de 2026/27 e das duas ligas tem de ser confirmada através da chave do fornecedor.</div>`;
  }
  function newsView(){let n=newsRows();if(state.newsFilter!=='all')n=n.filter(x=>x.category===state.newsFilter);
    return `<div class="callout intel-callout"><b>Notícias são sinais, não diagnósticos.</b><div>O título pode estar incompleto, incorreto ou desatualizado. Abre a fonte para confirmar e nunca assume que um jogador está indisponível só por aparecer numa manchete.</div></div><div class="toolbar"><span class="pill-label">${n.length} títulos · ${safe(leagueNames[state.league]||'Duas ligas')}</span><select id="news-filter" class="filter-select" aria-label="Tipo de notícia"><option value="all">Todos os temas</option>${Object.keys(labelCategory).map(k=>`<option value="${k}" ${state.newsFilter===k?'selected':''}>${labelCategory[k]}</option>`).join('')}</select></div>
    <section class="panel"><div class="panel-header"><div><h2>Monitor de notícias</h2><p>Google Notícias via RSS · sujeito à disponibilidade dos feeds</p></div>${badgeStatus(intelligence().news_status==='feed_ok'?'Feed consultado':'Feed por atualizar')}</div>${n.length?`<div class="intelligence-list">${n.slice(0,80).map(headlineCard).join('')}</div>`:`<div class="empty"><b>Sem notícias recolhidas nesta demonstração</b>O processo cloud tenta consultar os RSS e identifica manchetes, equipas e temas. A demonstração não inclui notícias inventadas.</div>`}</section>`;
  }
  function teamForm(team,lid, beforeDate){const prev=rows(lid).filter(e=>isFinished(e)&&e.date<beforeDate&&(e.home===team||e.away===team)).sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,5);
    let win=0,draw=0,loss=0,gf=0,ga=0;
    for(const e of prev){const home=e.home===team;const a=home?e.home_score:e.away_score,b=home?e.away_score:e.home_score;gf+=a;ga+=b;if(a>b)win++;else if(a===b)draw++;else loss++;}
    let days=null;if(prev.length){const t=Date.parse(beforeDate+'T12:00:00Z'),p=Date.parse(prev[0].date+'T12:00:00Z');days=Math.round((t-p)/86400000);}
    return {count:prev.length,win,draw,loss,gf,ga,days,score:win*3+draw};
  }
  function teamSnapshot(name,lid,matchDate){const f=teamForm(name,lid,matchDate),a=matchingAbsences(lid,[name]),n=matchingNews(lid,[name]);
    const coverageComplete=!state.data?.leagues?.[lid]?.partial;
    return `<div class="team-snapshot"><h3>${safe(name)}</h3><div class="snap-grid"><div><strong>${f.count?`${f.win}V · ${f.draw}E · ${f.loss}D`:'—'}</strong><small>${f.count} jogos da liga recolhidos</small></div><div><strong>${f.count?`${f.gf} – ${f.ga}`:'—'}</strong><small>Golos marcados / sofridos</small></div><div><strong>${!coverageComplete?'Não fiável':f.days===null?'Sem dado':f.days+' dias'}</strong><small>Desde o último jogo da liga recolhido</small></div><div><strong>${a.length?`${a.length} registos`:'Por verificar'}</strong><small>Disponibilidade de jogadores</small></div></div>
    ${coverageComplete&&f.days!==null&&f.days<=3?'<div class="risk-strip">Atenção: até três dias desde o último jogo da liga — verificar rotação e outras competições.</div>':''}
    <div class="snap-foot">${n.length?`${n.length} título(s) ligado(s) à equipa`:'Nenhuma manchete ligada à equipa nos dados carregados.'}</div></div>`;
  }
  function briefingMatch(){let m=currentModel();return m?.event?m:null;}
  function briefingResult(){const m=briefingMatch();if(!m)return `<div class="empty"><b>Não há jogos futuros disponíveis para análise.</b>Recolhe jornadas completas no GitHub Actions.</div>`;
    const e=m.event,lid=m.lid, ns=matchingNews(lid,[e.home,e.away]).slice(0,7),
      as=matchingAbsences(lid,[e.home,e.away]);
    const p=m.pred;
    return `<div class="brief-head"><span class="pill-label">${safe(leagueNames[lid])}</span><span class="muted">Jornada ${e.round} · ${formatDate(e.date)}</span><h2>${safe(e.home)} <span class="versus">vs</span> ${safe(e.away)}</h2><div class="muted">Dossiê baseado nos dados disponíveis, não uma previsão garantida.</div></div>
    ${state.data?.leagues?.[lid]?.partial?'<div class="limit-note" style="margin-bottom:18px">Dados desta liga <b>incompletos</b>: forma, descanso e probabilidades podem estar incorretos até à recolha integral.</div>':''}
    ${p?`<section class="panel" style="margin-bottom:18px"><div class="panel-header"><div><h2>Probabilidades e mercado</h2><p>Modelo pré-jogo · sem garantia de valor</p></div></div><div class="body-pad">${probabilityStrip(p)}${suggestionMarkup(m)}${extraMarketsMarkup(m)}</div></section>`:''}
    <div class="snapshot-pair">${teamSnapshot(e.home,lid,e.date)}${teamSnapshot(e.away,lid,e.date)}</div>
    <div class="grid-2"><section class="panel"><div class="panel-header"><div><h2>⊘ Ausências reportadas</h2><p>Jogadores indisponíveis ou em dúvida</p></div></div>${as.length?`<div class="intelligence-list">${as.map(absenceCard).join('')}</div>`:`<div class="empty"><b>Sem registos confirmados</b>Cobertura não assegurada. Não interpretar como equipas completas.</div>`}</section>
    <section class="panel"><div class="panel-header"><div><h2>▧ Manchetes associadas</h2><p>RSS — sinais por verificar</p></div></div>${ns.length?`<div class="intelligence-list">${ns.map(headlineCard).join('')}</div>`:`<div class="empty"><b>Sem manchetes associadas</b>O feed pode estar indisponível ou a equipa pode não estar mencionada no título.</div>`}</section></div>
    <div class="callout intel-callout" style="margin-top:18px"><b>Interpretação</b><div>${p?`Modelo apenas com golos: casa ${percent(p.p1)}, empate ${percent(p.px)}, fora ${percent(p.p2)}. Estes valores <b>não incluem</b> lesões, castigos, notícias nem cansaço fora da liga. O número de jogos da amostra e a falta de calibração limitam a fiabilidade.`:'Dados insuficientes para o modelo 1X2.'} A fadiga não foi calculada a partir de taças, competições europeias ou seleções.</div></div>`;
  }
  function conciseBriefing(){
    const m=currentModel();
    if(!m||!m.pred)return '<div class="empty"><b>Previsão indisponível</b>O jogo ainda não tem dados suficientes.</div>';
    const e=m.event,p=m.pred;
    const ctx=state.scheduleContext?.leagues?.[m.lid]?.fixtures?.[String(e.id)];
    const h=ctx?.home?.days_since_last_known_match,a=ctx?.away?.days_since_last_known_match;
    const rest=Number.isFinite(h)&&Number.isFinite(a)?h+' dias casa · '+a+' dias fora':'Cobertura insuficiente';
    const shot=state.shotsResearch?.leagues?.[m.lid]?.candidates?.find(x=>x.match_id===String(e.id));
    const research=shot?.status==='observational_signal_only'?'Em estudo':'Amostra insuficiente';
    return '<section class="panel ux-analysis"><div class="body-pad">'+
      '<small class="ux-eyebrow">'+safe(leagueNames[m.lid])+' · '+formatDate(e.date)+'</small>'+
      '<h2>'+safe(e.home)+' <em>vs</em> '+safe(e.away)+'</h2>'+
      '<p class="ux-desc">Probabilidades 1X2 · '+safe(p.model||'modelo experimental')+'</p>'+
      conciseProbabilities(p)+
      '<div class="ux-context-grid">'+
      '<div><small>Descanso conhecido</small><b>'+safe(rest)+'</b></div>'+
      '<div><small>Remates / xG</small><b>'+safe(research)+'</b></div></div>'+
      '<p class="ux-note">Descanso e outras competições podem ter cobertura parcial. Notícias, lesões e xG não alteram esta previsão.</p>'+
      '</div></section>';
  }
  function briefingsView(){
    return '<section class="panel ux-picker"><div class="body-pad">'+modelSelect()+'</div></section>'+
      '<div id="briefing-result">'+conciseBriefing()+'</div>'+
      '<details class="ux-details"><summary>Ver análise completa <small>Forma, notícias, ausências e mercados</small></summary>'+
      '<div class="ux-expanded">'+briefingResult()+'</div></details>';
  }
  function integrityView(lid,market){
    const qa=state.quality?.leagues?.[lid];
    const validate=state.validation?.leagues?.[lid];
    const storage=state.storageStatus;
    const num=v=>typeof v==='number'&&Number.isFinite(v)?numberPT.format(v):'—';
    const pct=v=>typeof v==='number'&&Number.isFinite(v)?percent(v):'—';
    const metric=validate?.markets?.[market];
    const holdout=metric?.holdout||{};
    const enough=validate?.status==='historical_holdout_completed'&&metric?.chosen_on_validation;
    const expected=['2021-2022','2022-2023','2023-2024','2024-2025','2025-2026'];
    const coverage=expected.map(season=>{
      const c=qa?.seasons?.[season];
      return '<tr><td>'+safe(season.replace('-','/'))+'</td><td class="text-right">'+(c?.matches??0)+'/'+(c?.expected??'—')+'</td>'+
        '<td>'+(c?.complete?'Auditada · completa':'Parcial / em validação')+'</td></tr>';
    }).join('');
    const qualityTitle=qa?qa.complete_count+' de 5 épocas completas':'Auditoria ainda não publicada';
    const scraper=state.scrapeReport;
    const advanced=state.statsCoverage?.leagues?.[lid];
    const shots=state.shotsResearch?.leagues?.[lid];
    const shotsPreview=shots?.candidates?.find(x=>x.status==='observational_signal_only')||shots?.candidates?.[0];
    const status=storage?.persisted?'Backup Git gravado na branch football-data':
      'Backup Git não confirmado — apenas recuperação temporária';
    return '<section class="panel fi-v41-panel"><div class="panel-header"><div><h2>Integridade e validação independente</h2>'+
      '<p>Sem custos · dados auditáveis · decisões separadas dos jogos de teste</p></div><span class="tag">v4.1</span></div>'+
      '<div class="body-pad"><div class="fi-v41-storage"><strong>'+safe(status)+'</strong>'+
      '<p>O repositório pode ser alterado pelo proprietário; o histórico Git não constitui armazenamento imutável contra manipulação deliberada.</p></div>'+
      '<div class="fi-v41-scraper"><h3>Scraper DBU · fonte oficial</h3>'+
      '<p class="muted">Última execução: '+(scraper?.generated_at?safe(scraper.generated_at.slice(0,16).replace("T"," "))+' UTC':'sem relatório')+
      ' · Novos jogos: <b>'+(scraper?.imported??0)+'</b> · Confirmados: <b>'+(scraper?.confirmed??0)+'</b> · Conflitos: <b>'+(scraper?.conflicts?.length??0)+'</b>.</p>'+
      '<p class="muted">'+(scraper?.attempts?.some(a=>a.status==="skipped")?'A fonte esteve indisponível ou não permitiu recolha; os jogos existentes foram preservados.':
       'Não foram detetadas falhas no último relatório. O scraper só recolhe resultados públicos permitidos.')+'</p></div>'+
      '<div class="fi-v41-scraper"><h3>Estatísticas avançadas · estudo de cobertura</h3>'+
      '<p class="muted">'+(advanced?.status==='sample_available'?'Amostra válida':advanced?.status==='sample_incomplete'?'Amostra parcialmente disponível':advanced?.status==='unavailable'?'Fonte indisponível':'Recolha ainda não efetuada')+
      ' · Jogos na fonte: '+(advanced?.match_count??'—')+
      ' · Amostras analisadas: '+(advanced?.sample_checked??0)+'.</p>'+
      '<p class="muted">Cantos: '+(advanced?.stats_fields_validated?.Corners??0)+
      ' · Cartões amarelos: '+(advanced?.stats_fields_validated?.["Yellow Cards"]??0)+
      ' · Remates: '+(advanced?.stats_fields_validated?.Shots??0)+
      ' jogos com os dois valores disponíveis na amostra.</p>'+
      '<p class="muted">Fonte: <a href="https://cornerflick.com/data" target="_blank" rel="noopener noreferrer">Cornerflick</a> (compilação CC BY 4.0). Direitos subjacentes por verificar para distribuição comercial. Sem apostas ou modelos novos ativados.</p></div>'+
      '<div class="fi-v41-scraper"><h3>Laboratório de remates e xG · versão experimental</h3>'+
      '<p class="muted">Jogos observados: <b>'+(shots?.sample_matches??0)+'</b> · Com remates: <b>'+(shots?.shots_recorded??0)+
      '</b> · Com remates à baliza: <b>'+(shots?.shots_on_target_recorded??0)+
      '</b> · Com xG real: <b>'+(shots?.xg_recorded??0)+'</b>.</p>'+
      (shotsPreview?'<p class="muted">Exemplo: '+safe(shotsPreview.home)+' – '+safe(shotsPreview.away)+
      ' ('+safe(shotsPreview.date)+') · amostras: '+shotsPreview.recent_samples_home+'/'+shotsPreview.recent_samples_away+
      '. '+(shotsPreview.status==='observational_signal_only'?
      'Pressão de remates à baliza (indicador, não probabilidade): '+num(shotsPreview.pressure_home)+' / '+num(shotsPreview.pressure_away)+'.':
      'Amostra insuficiente para calcular pressão.')+'</p>':'')+
      '<p class="muted">xG em falta significa desconhecido, não zero. Observações incompletas e sem validação retrospetiva: nenhuma alteração às previsões ou apostas. Fonte com atribuição: <a href="https://cornerflick.com/data" target="_blank" rel="noopener noreferrer">Cornerflick</a>.</p></div>'+
      '<div class="fi-v41-two"><div class="fi-v41-box"><h3>Qualidade do histórico</h3><p class="muted">'+
      qualityTitle+' · '+(qa?.total_matches??0)+' resultados importados</p>'+
      '<div class="table-scroll"><table><thead><tr><th>Época</th><th class="text-right">Jogos</th><th>Estado</th></tr></thead><tbody>'+coverage+'</tbody></table></div></div>'+
      '<div class="fi-v41-box"><h3>Treino / seleção / teste</h3>'+
      '<div class="fi-v41-stages"><span>Treino<br><b>2021–24</b></span><span>Afinação<br><b>2024/25</b></span><span>Teste<br><b>2025/26</b></span></div>'+
      (enough?
        '<p>Modelo escolhido sem consultar o teste: <b>'+safe(metric.chosen_on_validation)+'</b>.</p>'+
        '<div class="fi-v41-kpis"><div><small>Jogos no teste</small><b>'+num(holdout.n)+'</b></div>'+
        '<div><small>Brier no teste ↓</small><b>'+num(holdout.brier)+'</b></div>'+
        '<div><small>Brier referência ↓</small><b>'+num(holdout.baseline_brier)+'</b></div>'+
        '<div><small>Skill histórico</small><b>'+pct(holdout.brier_skill)+'</b></div></div>'+
        '<p class="muted">Limite 95% para a melhoria absoluta do Brier: '+(Array.isArray(holdout.brier_gain_ci95)?holdout.brier_gain_ci95.map(num).join(' a '):'—')+
        '. '+(holdout.status==='historical_signal_to_replicate'?'Sinal histórico ainda não confirmado prospetivamente.':'Sem evidência robusta de vantagem independente.')+'</p>'
        :'<div class="limit-note">Teste independente indisponível: '+(validate?.incomplete_seasons?.length?'faltam épocas completas e auditadas ('+validate.incomplete_seasons.map(x=>safe(x.replace('-','/'))).join(', ')+').':'a validação ainda não foi gerada.')+'</div>')+
      '</div></div><p class="muted fi-extra-note">Este teste histórico seleciona entre Poisson e Dixon–Coles usando apenas 2024/25. Não altera automaticamente as previsões ao vivo, não incorpora odds e não comprova rentabilidade.</p></div></section>';
  }
  function reliabilityView(){
    const lid=state.league==='all'?'pt':state.league;
    const audit=state.reliability?.history?.[lid];
    const prospective=state.reliability?.prospective;
    const ledgerHealth=state.ledgerHealth;
    const health=ledgerHealth?.states||{};
    const titles={double_1x:'Dupla oportunidade 1X',double_x2:'Dupla oportunidade X2',double_12:'Dupla oportunidade 12',
      over_0_5:'Over 0.5',under_0_5:'Under 0.5',over_1_5:'Over 1.5',under_1_5:'Under 1.5',
      over_2_5:'Over 2.5',under_2_5:'Under 2.5',over_3_5:'Over 3.5',under_3_5:'Under 3.5',
      btts_yes:'Ambas marcam — Sim',btts_no:'Ambas marcam — Não',
      home_over_0_5:'Casa Over 0.5',home_over_1_5:'Casa Over 1.5',
      away_over_0_5:'Fora Over 0.5',away_over_1_5:'Fora Over 1.5'};
    if(!audit)return '<div class="limit-note">Aguardando a primeira publicação do relatório de fiabilidade.</div>';
    const options=Object.entries(titles).map(([key,name])=>'<option value="'+key+'" '+(key===state.reliabilityMarket?'selected':'')+'>'+safe(name)+'</option>').join('');
    const m=audit.metrics?.[state.reliabilityMarket]||{};
    const validNumber=v=>typeof v==='number'&&Number.isFinite(v);
    const val=v=>validNumber(v)?numberPT.format(v):'—';
    const pct=v=>validNumber(v)?percent(v):'—';
    const status={
      insuficiente:'Sem dados suficientes',historico_parcial:'Histórico incompleto',
      amostra_insuficiente:'Amostra insuficiente',preliminar:'Preliminar',
      pior_que_referencia:'Pior que referência',sinal_historico_a_confirmar:'Sinal histórico por confirmar',
      inconclusivo:'Inconclusivo'
    }[m.status]||'Ainda não avaliado';
    const seasons=Object.entries(audit.coverage||{}).map(([season,c])=>
      '<div class="fi-season"><strong>'+safe(season.replace('-','/'))+'</strong>'+
      '<span>'+c.games+' jogos</span><small>'+(c.complete?'Completa':'Parcial / em recolha')+'</small></div>').join('');
    const missing=['2021-2022','2022-2023','2023-2024','2024-2025','2025-2026'].filter(y=>!audit.coverage?.[y]);
    const rows=(m.calibration_bins||[]).map(b=>{
      const predicted=Math.max(0,Math.min(100,Number(b.mean_prediction)*100));
      const observed=Math.max(0,Math.min(100,Number(b.observed_frequency)*100));
      return '<div class="fi-calibration-row"><div class="fi-calib-meta"><span>'+safe(b.range)+'</span><span>N='+b.n+' · Previsto '+pct(b.mean_prediction)+' / Real '+pct(b.observed_frequency)+'</span></div>'+
        '<div class="fi-calib-track"><span class="fi-calib-pred" style="width:'+predicted.toFixed(2)+'%"></span></div>'+
        '<div class="fi-calib-track"><span class="fi-calib-real" style="width:'+observed.toFixed(2)+'%"></span></div></div>';
    }).join('');
    const monthly=(m.monthly||[]).map(e=>'<tr><td>'+safe(e.month)+'</td><td class="text-right">'+e.n+'</td><td class="text-right">'+val(e.brier)+'</td></tr>').join('');
    const holdout=audit.holdout;
    const ci=m.brier_gain_ci95;
    const ciText=Array.isArray(ci)?val(ci[0])+' a '+val(ci[1]):'—';
    return '<section class="panel fi-rel-panel"><div class="panel-header"><div><h2>Qualidade estatística · '+safe(leagueNames[lid])+'</h2><p>Épocas antigas para treino; época seguinte reservada para teste histórico</p></div><span class="tag">v4 · EXPERIMENTAL</span></div>'+
      '<div class="body-pad"><div class="fi-reliability-top"><div class="fi-reliability-primary"><label for="reliability-market">Mercado a avaliar</label><select id="reliability-market" class="input">'+options+'</select>'+
      '<p class="muted">Teste: '+(holdout?safe(holdout.season.replace('-','/')):'sem época suficiente')+
      ' · '+(holdout?holdout.train_games:0)+' jogos anteriores para treino · '+
      (holdout?.complete?'época de teste completa':'época de teste incompleta')+'</p></div>'+
      '<div class="fi-rel-status"><small>ESTADO DE FIABILIDADE</small><strong>'+safe(status)+'</strong>'+
      '<span>'+((m.n||0))+' previsões avaliadas</span></div></div>'+
      '<div class="fi-reliability-kpis"><div><small>Brier modelo ↓</small><strong>'+val(m.brier)+'</strong></div>'+
      '<div><small>Brier referência ↓</small><strong>'+val(m.baseline_brier)+'</strong></div>'+
      '<div><small>Variação face à referência</small><strong>'+pct(m.brier_skill)+'</strong></div>'+
      '<div><small>Erro de calibração ECE ↓</small><strong>'+pct(m.ece)+'</strong></div></div>'+
      '<p class="muted fi-rel-caveat">Intervalo de confiança de 95% para a melhoria absoluta do Brier: '+ciText+
      '. Se incluir zero, não existe evidência estatística clara de melhoria. É uma aproximação que não ajusta a dependência entre jogos.</p>'+
      '<div class="fi-rel-grid"><div class="fi-rel-column"><h3>Calibração prevista vs observada</h3>'+
      '<div class="fi-calib-legend"><span class="fi-calib-pred-color"></span> Probabilidade prevista <span class="fi-calib-real-color"></span> Frequência observada</div>'+
      (rows||'<p class="muted">Sem previsões avaliadas.</p>')+'</div>'+
      '<div class="fi-rel-column"><h3>Desempenho por mês</h3><div class="table-scroll"><table><thead><tr><th>Mês</th><th class="text-right">Jogos</th><th class="text-right">Brier ↓</th></tr></thead><tbody>'+
      (monthly||'<tr><td colspan="3">Sem testes disponíveis</td></tr>')+'</tbody></table></div></div></div>'+
      '<div class="fi-rel-seasons"><h3>Cobertura das épocas históricas</h3><div class="fi-season-grid">'+seasons+
      missing.map(y=>'<div class="fi-season"><strong>'+safe(y.replace('-','/'))+'</strong><span>0 jogos</span><small>Por importar</small></div>').join('')+
      '</div></div><div class="fi-rel-ledger"><h3>Registo de previsões reais</h3><div class="fi-reliability-kpis"><div><small>Previsões guardadas</small><strong>'+(prospective?.logged??0)+'</strong></div>'+
      '<div><small>Jogos com resultado</small><strong>'+(prospective?.settled??0)+'</strong></div></div>'+
      (ledgerHealth?'<div class="fi-reliability-kpis"><div><small>Por jogar</small><strong>'+(health.future??0)+'</strong></div>'+
        '<div><small>Jogos hoje</small><strong>'+(health.today??0)+'</strong></div>'+
        '<div><small>Passados sem resultado</small><strong>'+(health.past_due_missing_result??0)+'</strong></div>'+
        '<div><small>Terminado por liquidar</small><strong>'+(health.finished_awaiting_settlement??0)+'</strong></div></div>'+
        (ledgerHealth.issue_count?'<div class="limit-note">Integridade do registo: '+ledgerHealth.issue_count+' alerta(s) para verificar na fonte.</div>':''):
        '<p class="muted">Auditoria de pendências ainda não publicada.</p>')+
      '<p class="muted">Estas são previsões preservadas no Git antes da data dos jogos; não confundimos a reconstrução histórica com previsões verdadeiramente emitidas antecipadamente. Alterações ao repositório ainda dependem das permissões do seu proprietário.</p></div>'+
      '<div class="limit-note">Sem previsões de rentabilidade: os testes não utilizam odds de mercado. O histórico foi importado retrospectivamente e continua sujeito a limitações de qualidade e seleção do modelo.</div></div></section>'+integrityView(lid,state.reliabilityMarket);
  }
  function conciseReliabilityView(){
    const lid=state.league==='all'?'pt':state.league;
    const future=state.ledgerHealth?.states||{};
    const p=state.reliability?.prospective;
    const xg=state.xgExperiment?.leagues?.[lid];
    return '<section class="panel ux-reliability"><div class="body-pad"><h2>Previsões antes do jogo</h2>'+
      '<p class="ux-desc">Só podemos avaliar previsões depois do resultado final.</p>'+
      '<div class="ux-metric-grid">'+
      '<div><small>Previsões registadas</small><strong>'+(p?.logged??'—')+'</strong></div>'+
      '<div><small>Resultados disponíveis</small><strong>'+(p?.settled??'—')+'</strong></div>'+
      '<div><small>Por jogar</small><strong>'+(future.future??'—')+'</strong></div>'+
      '<div><small>Passados sem resultado</small><strong>'+(future.past_due_missing_result??'—')+'</strong></div></div>'+
      '<p class="ux-note">'+((p?.settled??0)<100?'A amostra prospetiva ainda é pequena: não existe precisão comprovada.':'Existem avaliações prospetivas; confirma os intervalos de incerteza no relatório técnico.')+'</p>'+
      '</div></section>'+
      '<section class="panel ux-reliability ux-xg-card"><div class="body-pad"><h2>Poisson + xG · laboratório</h2>'+
      '<div class="ux-stats"><span><b>'+(xg?.xg_observations??0)+'</b> jogos com xG observado</span>'+
      '<span><b>'+(state.xgExperiment?.total_shadow_predictions??0)+'</b> previsões experimentais</span>'+
      '<span><b>'+(xg?.paired_evaluation?.n??0)+'</b> jogos comparados</span></div>'+
      '<p class="ux-note">Estado: '+(xg?.status==='prospective_shadow_running'?'recolha prospetiva em curso':'faltam observações por equipa')+
      '. Não altera o modelo publicado nem gera recomendações de aposta.</p>'+
      '</div></section>'+
      '<details class="ux-details"><summary>Consultar relatório técnico <small>Brier, calibração, métodos e épocas</small></summary>'+
      '<div class="ux-expanded">'+reliabilityView()+'</div></details>';
  }
  function render(){const page=views[state.view]||views.overview;$('#view-breadcrumb').textContent=page[0];$('#page-title').innerHTML=page[1];$('#page-subtitle').textContent=page[2];
    $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));
    $$('.league-pill').forEach(b=>b.classList.toggle('active',b.dataset.league===state.league));
    const warning=$('#warning');const selected=activeLeagues();const incomplete=selected.filter(lid=>state.data?.leagues?.[lid]?.partial);
    if(!state.data?.updated_at){warning.textContent='Ainda não existe uma recolha completa. A primeira execução do GitHub Actions irá importar os resultados das duas ligas. O painel pode mostrar uma amostra de arranque incompleta.';warning.classList.remove('hidden');}
    else if(incomplete.length){warning.textContent=`Dados parciais para ${incomplete.map(x=>leagueNames[x]).join(' e ')}. Uma ou mais jornadas podem estar em falta; não uses esta classificação como oficial.`;warning.classList.remove('hidden');}
    else{warning.classList.add('hidden');}
    $('#view').innerHTML=({overview, matches:matchView,table:tableView,briefings:briefingsView,news:newsView,absences:absencesView,model:modelView,value:valueView,reliability:conciseReliabilityView})[state.view]();
    const advanced=$('#advanced-menu');
    if(advanced&&['table','model','news','absences','value'].includes(state.view))advanced.open=true;
    $('#updated-at').textContent=state.data?.updated_at?fullDate(state.data.updated_at):'Sem atualização completa';
    $('#side-status').textContent=state.data?.updated_at?`${games().length} jogos na seleção`:'À espera da 1.ª recolha';
    bindLocal();
  }
  function bindLocal(){
    $$('[data-goto]').forEach(b=>b.addEventListener('click',()=>goto(b.dataset.goto)));
    $$('[data-open-match]').forEach(b=>b.addEventListener('click',()=>{
      state.modelMatch=b.dataset.openMatch;
      goto('briefings');
    }));
    $$('[data-more-games]').forEach(b=>b.addEventListener('click',()=>{state.matchLimit+=30;render();}));
    const filter=$('#match-filter'), search=$('#match-search'), sel=$('#model-match');
    if(filter)filter.addEventListener('change',e=>{state.matchFilter=e.target.value;state.matchLimit=30;render();});
    if(search)search.addEventListener('input',e=>{const caret=e.target.selectionStart;state.search=e.target.value;render();const n=$('#match-search');if(n){n.focus();n.setSelectionRange(caret,caret);}});
    if(sel)sel.addEventListener('change',e=>{state.modelMatch=e.target.value;render();});
    const nf=$('#news-filter');if(nf)nf.addEventListener('change',e=>{state.newsFilter=e.target.value;render();});
    const rm=$('#reliability-market');if(rm)rm.addEventListener('change',e=>{state.reliabilityMarket=e.target.value;render();});
    const vm=$('#value-market');if(vm)vm.addEventListener('change',e=>{state.valueMarket=e.target.value;render();});
    const vo=$('#value-odd');if(vo)vo.addEventListener('change',e=>{state.valueOdds=e.target.value;render();});
  }
  function goto(next){state.view=next;render();$('#sidebar').classList.remove('open');window.scrollTo({top:0,behavior:'smooth'});}
  $$('.nav-item').forEach(b=>b.addEventListener('click',()=>goto(b.dataset.view)));
  $$('.league-pill').forEach(b=>b.addEventListener('click',()=>{state.league=b.dataset.league;state.modelMatch='';store('footballlab-league',state.league);render();}));
  $('#menu-button').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
  document.addEventListener('click',e=>{if(window.innerWidth<=800 && !e.target.closest('.sidebar')&&!e.target.closest('#menu-button'))$('#sidebar').classList.remove('open');});
  async function initialize(){try{
      if(window.FOOTBALL_LAB_DATA){state.data=window.FOOTBALL_LAB_DATA;state.intelligence=window.FOOTBALL_INTELLIGENCE_DATA||null;render();return;}
      const response=await fetch(`data/season.json?v=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const d=await response.json();if(!d.leagues?.pt||!d.leagues?.dk)throw new Error('Formato de dados inesperado');
      state.data=d;
      try{const r=await fetch(`data/intelligence.json?v=${Date.now()}`,{cache:'no-store'});if(r.ok)state.intelligence=await r.json();}catch{state.intelligence=null;}
      try{const r=await fetch(`data/model.json?v=${Date.now()}`,{cache:"no-store"});if(r.ok)state.model=await r.json();}catch{state.model=null;}
      try{const r=await fetch(`data/reliability.json?v=${Date.now()}`,{cache:"no-store"});if(r.ok)state.reliability=await r.json();}catch{state.reliability=null;}
      for(const [key,file] of [['quality','quality.json'],['validation','validation.json'],['storageStatus','storage_status.json'],['scrapeReport','scrape_report.json'],['statsCoverage','stats_coverage.json'],['shotsResearch','shots_research.json'],['xgExperiment','xg_experiment.json'],['valueEngine','value_engine.json'],['featureImpact','feature_impact.json'],['scheduleContext','schedule_context.json'],['prematchLineups','prematch_lineups.json'],['multiImpact','multi_competition_impact.json'],['ledgerHealth','ledger_health.json'],['europeanCoverage','european_coverage.json']]){
        try{const r=await fetch(`data/${file}?v=${Date.now()}`,{cache:'no-store'});if(r.ok)state[key]=await r.json();}catch{state[key]=null;}
      }
    }catch(e){state.data={updated_at:null,leagues:{pt:{events:[],partial:true},dk:{events:[],partial:true}}};$('#warning').title=String(e);}
    render();
  }
  // Funções matemáticas expostas exclusivamente para testes locais.
  window.FootballLabTest = {standings,poisson,predict,teamForm,parseData:d=>{state.data=d},parseIntelligence:d=>{state.intelligence=d},
    setModelData:d=>{state.model=d},setXGData:d=>{state.xgExperiment=d},
    renderOverview:overview,renderBriefing:briefingsView,renderReliability:conciseReliabilityView,getStats};
  initialize();
})();
