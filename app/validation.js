/* Mageburx · signed forecast validation, read-only client. */
(() => {
  'use strict';
  const $=(s)=>document.querySelector(s);
  const safe=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const leagues={pt:['🇵🇹','Liga Portugal'],dk:['🇩🇰','Superliga'],nl:['🇳🇱','Eredivisie'],
    dk2:['🇩🇰','1. Division'],no:['🇳🇴','Eliteserien']};
  const status={future:'Por jogar',in_progress:'Em curso · último registo',
    unconfirmed:'Por confirmar',awaiting_settlement:'Final por liquidar',
    validated:'Final confirmado',review:'Requer revisão',superseded:'ID substituído'};
  const explanations={
    future:'À espera do encontro',in_progress:'Estado do último snapshot, não live',
    unconfirmed:'Resultado ou estado sem confirmação final',
    awaiting_settlement:'Resultado final verificado, liquidação ainda pendente',
    validated:'Previsão assinada e resultado verificado',
    review:'Assinatura, data ou resultado exigem revisão',
    superseded:'Mantido para auditoria, excluído da precisão'};
  const order=['review','awaiting_settlement','in_progress','unconfirmed','future','validated','superseded'];
  let filter='all',search='',limit=60;
  const num=v=>Number(v)||0;
  const dt=v=>{let n=new Date(v);return Number.isFinite(n.valueOf())?n.toLocaleString('pt-PT',
    {timeZone:'Europe/Lisbon',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):'—';};
  const day=v=>{let n=new Date(String(v||'')+'T12:00:00Z');return Number.isFinite(n.valueOf())?
    n.toLocaleDateString('pt-PT',{day:'2-digit',month:'short'}):'—';};
  const score=v=>Number.isFinite(v)?v.toLocaleString('pt-PT',{maximumFractionDigits:4}):'—';
  const weekendStates={validated:'Validado',confirmed_pending:'Final confirmado · por liquidar',
    unverified:'Sem resultado confirmado',postponed:'Adiado/cancelado',
    rescheduled:'Data alterada · excluído',superseded:'ID substituído',review:'Rever dados'};
  function weekendMarkup(weekend,ids){
    if(!weekend?.records||weekend.schema!==1)return '';
    const rows=weekend.records.filter(x=>ids.includes(x.league));
    const settled=rows.filter(x=>x.state==='validated');
    const accuracy=settled.length?settled.filter(x=>x.correct===true).length+' / '+settled.length:'—';
    const avg=settled.length?settled.reduce((v,x)=>v+Number(x.brier),0)/settled.length:null;
    const count=key=>rows.filter(x=>x.state===key).length;
    const top=[
      ['Previsões do fim de semana',rows.length,'Previsões assinadas no período'],
      ['Acertos 1X2 verificados',accuracy,'Não inclui jogos sem final confirmado'],
      ['Brier validado',avg==null?'—':score(avg),'Comparação: uniformemente 0,6667'],
      ['Dados pendentes',count('unverified')+count('confirmed_pending')+
        count('rescheduled')+count('postponed')+count('review'),
        'Não usados para calcular precisão']
    ];
    const table=rows.map(x=>'<tr><td><strong>'+safe(x.home+' – '+x.away)+
      '</strong><small>'+safe(leagues[x.league]?.[0]+' '+leagues[x.league]?.[1])+'</small></td>'+
      '<td>'+safe(day(x.date))+'</td><td><span class="vc-chip vc-'+
      safe(x.state)+'">'+safe(weekendStates[x.state]||x.state)+'</span></td>'+
      '<td>'+safe(x.tip||'—')+'</td><td>'+(x.score?
      safe(x.score[0]+'–'+x.score[1]):'—')+'</td><td>'+
      (x.correct===true?'✓':x.correct===false?'✕':'—')+'</td></tr>').join('');
    return '<section class="panel vc-weekend"><div class="panel-header"><div>'+
      '<h2>Auditoria do último fim de semana</h2><p>'+
      safe(day(weekend.start_date)+' – '+day(weekend.end_date))+
      ' · previsões registadas antes dos jogos, sem reconstrução retroativa</p></div></div>'+
      '<div class="vc-weekend-stats">'+top.map(([k,v,note])=>
        '<div><small>'+safe(k)+'</small><strong>'+safe(v)+
        '</strong><span>'+safe(note)+'</span></div>').join('')+'</div>'+
      '<p class="vc-note">Amostra reduzida: nenhum ranking ou vantagem estatística comprovada. '+
      'Apenas previsões assinadas e resultados finais validados entram nas métricas. '+
      'Brier mais baixo é melhor; referência uniforme (1/X/2 = 33,3%): 0,6667.</p>'+
      '<div class="table-scroll"><table class="vc-table"><thead><tr><th>Jogo</th>'+
      '<th>Data</th><th>Verificação</th><th>Tip</th><th>Final</th><th>Acerto</th>'+
      '</tr></thead><tbody>'+
      (table||'<tr><td colspan="6">Sem previsões assinadas nesta seleção.</td></tr>')+
      '</tbody></table></div></section>';
  }
  function render(data,selected='all'){
    if(data?.schema!==1||!Array.isArray(data.records))
      return '<section class="panel"><div class="empty"><b>Relatório ainda não disponível</b>Aguardamos a publicação de validation_center.json. Não mostramos números fictícios.</div></section>';
    const ids=selected==='all'?Object.keys(leagues):[selected];
    const n=k=>ids.reduce((s,lid)=>s+num(data.leagues?.[lid]?.[k]),0);
    const total=ids.reduce((s,lid)=>s+num(data.leagues?.[lid]?.total),0);
    const cards=[['Previsões assinadas',total,'Histórico original'],
      ['IDs ativos',total-n('superseded'),'Exclui IDs substituídos'],
      ['1X2 validados',n('validated'),'Resultado final verificado'],
      ['A rever',n('review'),'Exige validação manual']];
    const statusMarkup=order.map(k=>'<div class="vc-status-row"><span class="vc-chip vc-'+k+'">'+
      safe(status[k])+'</span><strong>'+n(k)+'</strong></div>').join('');
    const leaguerows=ids.map(k=>{
      const x=data.leagues?.[k]||{};return '<tr><td>'+safe(leagues[k][0]+' '+leagues[k][1])+
      '</td><td class="text-right">'+num(x.total)+'</td><td class="text-right">'+num(x.validated)+
      '</td><td class="text-right">'+num(x.awaiting_settlement)+'</td>'+
      '<td class="text-right">'+num(x.review)+'</td><td class="text-right">'+num(x.superseded)+'</td></tr>';
    }).join('');
    const q=search.toLocaleLowerCase('pt-PT').trim();
    const items=data.records.filter(x=>ids.includes(x.league)&&
      (filter==='all'||x.status===filter)&&
      (!q||[x.home,x.away,x.key].some(v=>String(v||'').toLocaleLowerCase('pt-PT').includes(q))))
      .sort((a,b)=>order.indexOf(a.status)-order.indexOf(b.status)||
        String(a.original_date).localeCompare(String(b.original_date)));
    const itemrows=items.slice(0,limit).map(x=>'<tr>'+
      '<td><strong>'+safe(x.home+' – '+x.away)+'</strong><small>'+
      safe((leagues[x.league]||['',''])[0]+' '+(leagues[x.league]||['',''])[1])+'</small></td>'+
      '<td>'+safe(day(x.original_date))+(x.current_date&&x.current_date!==x.original_date?
        '<small>Atual: '+safe(day(x.current_date))+'</small>':'')+'</td>'+
      '<td><span class="vc-chip vc-'+safe(x.status)+'">'+safe(status[x.status]||x.status)+
      '</span><small>'+safe(explanations[x.status]||x.reason)+'</small></td>'+
      '<td>'+(x.score?safe(x.score.home+'–'+x.score.away):'—')+'</td>'+
      '<td class="vc-key">'+safe(x.key)+(x.replacement_id?'<small>Substituído por: '+
      safe(x.replacement_id)+'</small>':'')+'</td></tr>').join('');
    const options=['all',...order].map(k=>'<option value="'+k+'" '+(filter===k?'selected':'')+
      '>'+safe(k==='all'?'Todos os estados':status[k])+'</option>').join('');
    const stats=data.brier?.[selected]||{};
    const general=data.general_ledger||{};
    return '<div class="vc-head"><span class="pill-label">AUDITORIA 1X2 · 5 LIGAS</span>'+
      '<span class="muted">Atualizado: '+safe(dt(data.generated_at))+'</span></div>'+
      '<div class="vc-counters">'+cards.map(([k,v,label])=>'<div class="vc-counter"><span>'+
        safe(k)+'</span><strong>'+v+'</strong><small>'+safe(label)+'</small></div>').join('')+'</div>'+
      weekendMarkup(data.weekend_audit,ids)+
      '<div class="vc-grid"><section class="panel"><div class="panel-header"><div><h2>Ciclo de validação</h2>'+
      '<p>Estados mutuamente exclusivos</p></div></div><div class="vc-status-list">'+statusMarkup+
      '</div></section><section class="panel"><div class="panel-header"><div><h2>Precisão real</h2>'+
      '<p>Apenas previsões 1X2 validadas</p></div></div>'+
      '<div class="vc-score"><div><small>Brier ↓</small><strong>'+
      (stats.n?score(stats.brier):'—')+'</strong></div><div><small>Log Loss ↓</small><strong>'+
      (stats.n?score(stats.log_loss):'—')+'</strong></div></div>'+
      '<p class="vc-note">'+(n('validated')?'Métricas preliminares; não provam rentabilidade.':
      'Aguardamos os primeiros resultados válidos. Não apresentamos precisão inventada.')+
      ' Seleciona uma liga para ver as métricas individuais.</p>'+
      '<div class="vc-general"><b>Ledger geral · outros mercados</b><small>'+
      (general.active_settlements??'—')+' liquidações · '+(general.quarantined??'—')+
      ' em quarentena · '+(general.integrity_alerts??'—')+' alertas</small></div></section></div>'+
      '<section class="panel vc-section"><div class="panel-header"><div><h2>Por campeonato</h2>'+
      '<p>IDs substituídos não geram acertos duplicados</p></div></div><div class="table-scroll">'+
      '<table><thead><tr><th>Liga</th><th class="text-right">Assinadas</th>'+
      '<th class="text-right">Válidas</th><th class="text-right">Por liquidar</th>'+
      '<th class="text-right">A rever</th><th class="text-right">Substituídas</th></tr></thead><tbody>'+
      leaguerows+'</tbody></table></div></section>'+
      '<section class="panel vc-section"><div class="panel-header"><div><h2>Registos individuais</h2>'+
      '<p>Previsões originais preservadas · apenas leitura</p></div></div>'+
      '<div class="vc-controls"><select id="vc-filter" class="filter-select">'+options+'</select>'+
      '<input type="search" id="vc-search" class="searchbox" placeholder="Equipa ou ID…" '+
      'aria-label="Pesquisar previsão" value="'+safe(search)+'"/><span class="muted">'+
      items.length+' registos</span></div>'+
      '<div class="table-scroll"><table class="vc-table"><thead><tr><th>Confronto</th>'+
      '<th>Data</th><th>Estado</th><th>Resultado</th><th>ID original</th></tr></thead>'+
      '<tbody>'+(itemrows||'<tr><td colspan="5">Nenhum registo encontrado.</td></tr>')+
      '</tbody></table></div>'+
      (items.length>limit?'<div class="ux-more"><button type="button" class="ux-link" id="vc-more">Mostrar mais →</button></div>':'')+
      '</section><p class="vc-footnote">O estado em curso vem do último snapshot e pode estar atrasado. '+
      'A liquidação é exclusiva do pipeline, após verificação do resultado final e do ID original. Sem odds reais não há demonstração de rentabilidade.</p>';
  }
  function bind(redraw){
    const f=$('#vc-filter'),s=$('#vc-search'),more=$('#vc-more');
    if(f)f.addEventListener('change',e=>{filter=e.target.value;limit=60;redraw();});
    if(s)s.addEventListener('input',e=>{const c=e.target.selectionStart;search=e.target.value;limit=60;redraw();
      const x=$('#vc-search');if(x){x.focus();x.setSelectionRange(c,c);}});
    if(more)more.addEventListener('click',()=>{limit+=60;redraw();});
  }
  window.MageburxValidation={render,bind};
})();
