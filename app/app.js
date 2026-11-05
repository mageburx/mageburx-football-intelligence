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
  const state = {data: null, intelligence: null, model: null, reliability: null, ledger: null, quality: null, validation: null, storageStatus: null, reliabilityMarket:'over_2_5', league: saved('footballlab-league','all'), view:'overview', search:'', newsFilter:'all', matchFilter:'all', modelMatch:''};
  const leagueNames = {pt:'Liga Portugal',dk:'Superliga'};
  const views = {
    overview:['Visão geral','Cada resultado tem <em>um contexto.</em>','Acompanha forma, calendário e os sinais que podem mudar o próximo jogo.'],
    matches:['Jogos e resultados','Todos os jogos. <em>Uma só vista.</em>','Resultados, calendário e jornadas da época 2026/27.'],
    table:['Classificações','Cada ponto <em>conta.</em>','Classificações calculadas a partir dos jogos efetivamente recolhidos.'],
    briefings:['Dossiê pré-jogo','O que mudou <em>antes do apito?</em>','Descanso, forma, ausências reportadas e manchetes associadas às equipas.'],
    news:['Notícias & sinais','A informação certa. <em>Com origem.</em>','Títulos recolhidos por RSS, ligados à fonte original e sujeitos a confirmação.'],
    absences:['Lesões & castigos','Disponibilidade <em>sob escrutínio.</em>','Diferencia baixa confirmada pelo fornecedor, dúvida e ausência de dados.'],
    model:['Modelo estatístico','Probabilidades, <em>não certezas.</em>','Poisson, Dixon–Coles, Elo e testes cronológicos de qualidade das previsões.'],
    reliability:['Painel de fiabilidade','Evidência antes de <em>confiar.</em>','Histórico, validação temporal, calibração e registo de previsões anteriores aos jogos.']
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
  function overview(){const s=getStats(),finish=scored(),next=forthcoming().slice(0,5), last=[...finish].sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,5);
    const chosen = state.league === 'all'?'pt':state.league;
    const lg = state.data?.leagues?.[chosen];
    const table = rows(chosen);
    const rounds = [...new Set(finish.map(e=>e.round).filter(Boolean))].sort((a,b)=>a-b).slice(-9);
    const bars = rounds.map(n=>({n,v:finish.filter(e=>e.round===n).reduce((a,e)=>a+e.home_score+e.away_score,0)}));
    const max=Math.max(1,...bars.map(b=>b.v));
    return `<div class="cards">
      <div class="stat-card featured"><div class="stat-top">Jogos disputados <span class="stat-icon">▦</span></div><div class="stat-num">${s.finished}</div><div class="stat-detail"><b>${s.loaded}</b> jogos no calendário recolhido</div></div>
      <div class="stat-card"><div class="stat-top">Golos por jogo <span class="stat-icon">⚽</span></div><div class="stat-num">${numberPT.format(s.avg)}</div><div class="stat-detail">${s.goals} golos nos jogos terminados</div></div>
      <div class="stat-card"><div class="stat-top">Vitórias da casa <span class="stat-icon">⌂</span></div><div class="stat-num">${s.finished?percent(s.homeWon/s.finished):'—'}</div><div class="stat-detail">${s.homeWon} em ${s.finished} jogos concluídos</div></div>
      <div class="stat-card"><div class="stat-top">Próximos jogos <span class="stat-icon">↗</span></div><div class="stat-num">${s.upcoming}</div><div class="stat-detail">no calendário atualmente recolhido</div></div>
    </div>
    <div class="split">
      <section class="panel"><div class="panel-header"><div><h2>Classificação · ${safe(leagueNames[chosen])}</h2><p>Calculada com os jogos disponíveis</p></div><button class="link-button" data-goto="table">Ver tabela completa ↗</button></div>${tableMarkup(table,8)}</section>
      <section class="panel"><div class="panel-header"><div><h2>Próximos encontros</h2><p>Calendário da época 2026/27</p></div><button class="link-button" data-goto="matches">Ver todos ↗</button></div><div class="match-list">${next.length?next.map(e=>matchRow(e)).join(''):`<div class="empty"><b>Sem próximos jogos nos dados carregados</b>A atualização da cloud procura todas as jornadas da época.</div>`}</div></section>
    </div>
    <div class="split">
      <section class="panel"><div class="panel-header"><div><h2>Golos por jornada</h2><p>Distribuição dos golos das jornadas terminadas na seleção atual</p></div><span class="tag">ÉPOCA 26/27</span></div><div class="body-pad" style="padding-top:5px">${bars.length?`<div class="chart-bars">${bars.map(b=>`<div class="chart-bar-wrap"><span class="chart-val">${b.v}</span><div class="chart-bar" style="height:${Math.max(3,b.v/max*93)}px"></div><span class="chart-label">J${b.n}</span></div>`).join('')}</div>`:`<div class="empty">Sem resultados disponíveis.</div>`}</div></section>
      <section class="panel"><div class="panel-header"><div><h2>Últimos resultados</h2><p>Jogos mais recentes da seleção</p></div></div><div class="match-list">${last.length?last.map(e=>matchRow(e)).join(''):'<div class="empty">Sem jogos terminados.</div>'}</div></section>
    </div><div class="panel intel-banner"><div class="panel-header"><div><h2>◉  Inteligência pré-jogo</h2><p>Forma · descanso · notícias · ausências</p></div><button class="link-button" data-goto="briefings">Abrir dossiês ↗</button></div><div class="body-pad" style="padding-top:0"><p class="muted">Os sinais qualitativos são apresentados com evidência e data. Não são convertidos automaticamente em probabilidades sem validação histórica.</p></div></div><div class="section-heading"><h2>Como usamos os dados</h2><small>Fonte aberta · Sem operações financeiras</small></div>
    <div class="insights"><div class="insight-card"><div class="insight-icon">◎</div><h3>Dados verificáveis</h3><p>Calendário, resultados e classificação calculada. Se a API falhar, o painel sinaliza informação incompleta.</p></div><div class="insight-card"><div class="insight-icon">⌁</div><h3>Modelo experimental</h3><p>Estimativas Poisson 1X2, golos e ambas marcam, suavizadas para evitar extrapolações fortes de poucos jogos.</p></div><div class="insight-card"><div class="insight-icon">◉</div><h3>Dossiê pré-jogo</h3><p>Forma recente, descanso na liga, notícias com fonte e disponibilidade dos jogadores. Sem preencher lacunas com suposições.</p></div></div>`;
  }
  function matchView(){let items=games();let q=state.search.toLocaleLowerCase('pt-PT').trim();if(q)items=items.filter(e=>(e.home+' '+e.away).toLocaleLowerCase('pt-PT').includes(q));
    if(state.matchFilter==='finished')items=items.filter(isFinished);
    if(state.matchFilter==='upcoming')items=items.filter(e=>!isFinished(e)&&e.date>=new Date().toISOString().slice(0,10));
    if(state.matchFilter==='upcoming')items.sort((a,b)=>String(a.utc||a.date).localeCompare(String(b.utc||b.date)));
    else items.sort((a,b)=>String(b.date).localeCompare(String(a.date)));
    return `<div class="toolbar"><div><span class="pill-label">${items.length} encontros</span> <span class="muted">· Época 2026/27</span></div><div style="display:flex;gap:9px;flex-wrap:wrap"><input id="match-search" class="searchbox" aria-label="Pesquisar clube" placeholder="Pesquisar por clube…" value="${safe(state.search)}" /><select id="match-filter" class="filter-select" aria-label="Filtrar jogos"><option value="all" ${state.matchFilter==='all'?'selected':''}>Todos os jogos</option><option value="finished" ${state.matchFilter==='finished'?'selected':''}>Resultados finais</option><option value="upcoming" ${state.matchFilter==='upcoming'?'selected':''}>Por jogar</option></select></div></div><section class="panel"><div class="panel-header"><div><h2>Calendário e resultados</h2><p>Fonte: TheSportsDB; datas apresentadas no fuso da informação recolhida</p></div></div><div class="match-list">${items.length?items.slice(0,130).map(e=>matchRow(e)).join(''):'<div class="empty"><b>Nenhum jogo encontrado</b>Altera os filtros ou aguarda a próxima atualização.</div>'}</div></section>`;
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
  function briefingsView(){return `<section class="panel" style="margin-bottom:18px"><div class="panel-header"><div><h2>Seleciona um encontro</h2><p>O painel agrega quatro dimensões: forma, descanso, ausências e notícias</p></div><span class="tag">PRE-MATCH</span></div><div class="body-pad">${modelSelect()}</div></section><div id="briefing-result">${briefingResult()}</div>`;}
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
    const status=storage?.persisted?'Backup Git gravado na branch football-data':
      'Backup Git não confirmado — apenas recuperação temporária';
    return '<section class="panel fi-v41-panel"><div class="panel-header"><div><h2>Integridade e validação independente</h2>'+
      '<p>Sem custos · dados auditáveis · decisões separadas dos jogos de teste</p></div><span class="tag">v4.1</span></div>'+
      '<div class="body-pad"><div class="fi-v41-storage"><strong>'+safe(status)+'</strong>'+
      '<p>O repositório pode ser alterado pelo proprietário; o histórico Git não constitui armazenamento imutável contra manipulação deliberada.</p></div>'+
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
      '<p class="muted">Estas são previsões preservadas no Git antes da data dos jogos; não confundimos a reconstrução histórica com previsões verdadeiramente emitidas antecipadamente. Alterações ao repositório ainda dependem das permissões do seu proprietário.</p></div>'+
      '<div class="limit-note">Sem previsões de rentabilidade: os testes não utilizam odds de mercado. O histórico foi importado retrospectivamente e continua sujeito a limitações de qualidade e seleção do modelo.</div></div></section>'+integrityView(lid,state.reliabilityMarket);
  }
  function render(){const page=views[state.view]||views.overview;$('#view-breadcrumb').textContent=page[0];$('#page-title').innerHTML=page[1];$('#page-subtitle').textContent=page[2];
    $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));
    $$('.league-pill').forEach(b=>b.classList.toggle('active',b.dataset.league===state.league));
    const warning=$('#warning');const selected=activeLeagues();const incomplete=selected.filter(lid=>state.data?.leagues?.[lid]?.partial);
    if(!state.data?.updated_at){warning.textContent='Ainda não existe uma recolha completa. A primeira execução do GitHub Actions irá importar os resultados das duas ligas. O painel pode mostrar uma amostra de arranque incompleta.';warning.classList.remove('hidden');}
    else if(incomplete.length){warning.textContent=`Dados parciais para ${incomplete.map(x=>leagueNames[x]).join(' e ')}. Uma ou mais jornadas podem estar em falta; não uses esta classificação como oficial.`;warning.classList.remove('hidden');}
    else{warning.classList.add('hidden');}
    $('#view').innerHTML=({overview, matches:matchView,table:tableView,briefings:briefingsView,news:newsView,absences:absencesView,model:modelView,reliability:reliabilityView})[state.view]();
    $('#updated-at').textContent=state.data?.updated_at?fullDate(state.data.updated_at):'Sem atualização completa';
    $('#side-status').textContent=state.data?.updated_at?`${games().length} jogos na seleção`:'À espera da 1.ª recolha';
    bindLocal();
  }
  function bindLocal(){
    $$('[data-goto]').forEach(b=>b.addEventListener('click',()=>goto(b.dataset.goto)));
    const filter=$('#match-filter'), search=$('#match-search'), sel=$('#model-match');
    if(filter)filter.addEventListener('change',e=>{state.matchFilter=e.target.value;render();});
    if(search)search.addEventListener('input',e=>{const caret=e.target.selectionStart;state.search=e.target.value;render();const n=$('#match-search');if(n){n.focus();n.setSelectionRange(caret,caret);}});
    if(sel)sel.addEventListener('change',e=>{state.modelMatch=e.target.value;render();});
    const nf=$('#news-filter');if(nf)nf.addEventListener('change',e=>{state.newsFilter=e.target.value;render();});
    const rm=$('#reliability-market');if(rm)rm.addEventListener('change',e=>{state.reliabilityMarket=e.target.value;render();});
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
      for(const [key,file] of [['quality','quality.json'],['validation','validation.json'],['storageStatus','storage_status.json']]){
        try{const r=await fetch(`data/${file}?v=${Date.now()}`,{cache:'no-store'});if(r.ok)state[key]=await r.json();}catch{state[key]=null;}
      }
    }catch(e){state.data={updated_at:null,leagues:{pt:{events:[],partial:true},dk:{events:[],partial:true}}};$('#warning').title=String(e);}
    render();
  }
  // Funções matemáticas expostas exclusivamente para testes locais.
  window.FootballLabTest = {standings,poisson,predict,teamForm,parseData:d=>{state.data=d},parseIntelligence:d=>{state.intelligence=d},getStats};
  initialize();
})();
