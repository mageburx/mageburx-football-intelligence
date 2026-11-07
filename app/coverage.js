/* Mageburx Data Coverage: transparent observed vs verified data. Read-only. */
(() => {
  'use strict';
  const safe=x=>String(x==null?'':x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const names={pt:['🇵🇹','Liga Portugal'],dk:['🇩🇰','Superliga'],
    nl:['🇳🇱','Eredivisie'],dk2:['🇩🇰','1. Division'],no:['🇳🇴','Eliteserien']};
  const stateNames={requires_review:'Revisão necessária',partial:'Cobertura parcial',
    audit_indicators_ok_not_certified:'Indicadores verificados · não certificado'};
  const urgency={critical:'Crítica',high:'Alta',medium:'Média'};
  const descriptions={
    duplicate_identifiers:'IDs de jogos repetidos',
    potential_duplicate_fixtures:'Possíveis duplicados',
    source_result_conflicts:'Resultados contraditórios entre fontes',
    past_not_final:'Jogos passados sem resultado final verificado',
    unverified_rounds:'Jornadas ainda por verificar',
    history_incomplete:'Épocas históricas não completas',
    missing_reference_inventory:'Jogos abaixo da referência',
    shots_no_verified_sample:'Sem amostra de remates verificada'
  };
  const number=x=>Number.isInteger(x)?x.toLocaleString('pt-PT'):'—';
  const when=x=>{const d=new Date(x);return Number.isFinite(d.valueOf())?
    d.toLocaleString('pt-PT',{timeZone:'Europe/Lisbon',dateStyle:'short',timeStyle:'short'}):'—';};
  function render(data,selected='all'){
    if(data?.schema!==1||!data.leagues){
      return '<section class="panel"><div class="empty"><b>Auditoria não disponível</b>'+
        'O relatório de cobertura ainda não foi publicado. Não são apresentados números simulados.</div></section>';
    }
    const ids=(selected==='all'?Object.keys(names):[selected]).filter(x=>data.leagues[x]);
    const leagues=ids.map(id=>[id,data.leagues[id]]);
    const sum=f=>leagues.reduce((n,[id,l])=>n+Number(f(l)||0),0);
    const observed=sum(l=>l.inventory?.observed_unique);
    const finals=sum(l=>l.inventory?.verified_final);
    const fullHistory=sum(l=>l.history?.complete_seasons);
    const highAlerts=sum(l=>(l.issues||[]).filter(x=>x.priority==='high'||x.priority==='critical').length);
    const cards=[
      ['Jogos identificados',number(observed),'Não é cobertura certificada'],
      ['Finais verificados',number(finals),'Marcadores finais explicitamente confirmados'],
      ['Épocas históricas completas',fullHistory+' / '+(leagues.length*5),'Critério documental da fonte'],
      ['Categorias de alertas',number(highAlerts),'Falhas de cobertura e conflitos prioritários']];
    const rows=leagues.map(([lid,l])=>{
      const ref=l.inventory?.expected_reference,obs=l.inventory?.observed_unique;
      const rounds=l.rounds||{}, hist=l.history||{}, shots=l.stats||{};
      const status=l.status||'partial';
      return '<article class="dc-league-card"><div class="dc-league-head"><strong>'+
        safe(names[lid][0]+' '+names[lid][1])+'</strong><span class="dc-status dc-'+
        safe(status)+'">'+safe(stateNames[status]||status)+'</span></div>'+
        '<div class="dc-metrics"><div><small>Jogos registados</small><b>'+
        number(obs)+(Number.isInteger(ref)?' / '+number(ref):'')+'</b>'+
        '<em>'+(Number.isInteger(ref)?'Referência de formato; não garante completude':
             'Formato variável · sem total certificado')+'</em></div>'+
        '<div><small>Jornadas confirmadas pela fonte</small><b>'+
        (Number.isInteger(rounds.verified)?rounds.verified+' / '+rounds.total_reference:
         'Não auditáveis')+'</b><em>'+
        (rounds.verification==='not_persisted'?
         'A recolha não preserva prova de todas as jornadas':
         'Jornadas observadas na fonte primária')+'</em></div>'+
        '<div><small>Histórico completo</small><b>'+
        number(hist.complete_seasons)+' / 5</b><em>Épocas 2021/22 a 2025/26</em></div>'+
        '<div><small>Remates / xG</small><b>'+
        (shots.sample_checked?'Amostra: '+shots.sample_checked:'Sem amostra')+'</b>'+
        '<em>xG em investigação; nunca assumir disponibilidade</em></div></div>'+
        '<div class="dc-sources"><b>Fontes e integridade</b> '+
        safe(l.sources?.source||'Por verificar')+' · '+
        number(l.inventory?.past_unverified)+' resultados passados sem confirmação · '+
        number(l.sources?.conflicts||0)+' conflitos de fonte</div>'+
        ((l.rounds?.unverified_count||0)>0?
          '<div class="dc-detail"><b>Jornadas por verificar ('+
          l.rounds.unverified_count+')</b> '+safe(l.rounds.unverified.slice(0,18).join(', '))+
          (l.rounds.unverified_count>18?'…':'')+'</div>':'')+
        ((l.inventory?.past_unverified_sample||[]).length?
          '<div class="dc-detail"><b>Exemplos de resultados por confirmar</b><span>'+
          l.inventory.past_unverified_sample.slice(0,4).map(x=>safe(
            x.date+' · '+x.home+' – '+x.away)).join(' | ')+'</span></div>':'')+
        '<div class="dc-detail"><b>Histórico</b><span>'+
        (hist.seasons||[]).map(x=>'<span class="dc-season">'+
          safe(x.season)+' · '+(x.status==='source_complete'?'Completa':
            x.status==='incomplete'?number(x.completed_matches)+' / '+number(x.expected):'Sem dados')+
          '</span>').join('')+'</span></div>'+
        '<div class="dc-issues">'+(l.issues||[]).slice(0,6).map(x=>
          '<span class="dc-issue">'+safe(descriptions[x.code]||x.code)+
          ' · '+number(x.count)+'</span>').join('')+
        (!(l.issues||[]).length?'<span class="muted">Nenhum alerta desta auditoria</span>':'')+
        '</div></article>';
    }).join('');
    const queue=(data.queue||[]).filter(x=>ids.includes(x.league)).slice(0,12);
    const queueRows=queue.map(x=>'<tr><td>'+safe(names[x.league][0]+' '+names[x.league][1])+
      '</td><td><span class="dc-priority dc-priority-'+safe(x.priority)+'">'+
      safe(urgency[x.priority]||x.priority)+'</span></td><td>'+
      safe(descriptions[x.code]||x.code)+' · '+number(x.count)+'</td><td>'+
      safe(x.action)+'</td></tr>').join('');
    return '<div class="dc-topline"><span class="pill-label">DATA COVERAGE ENGINE</span>'+
      '<span class="muted">Auditoria: '+safe(when(data.generated_at))+'</span></div>'+
      '<div class="dc-counters">'+cards.map(([label,value,note])=>
        '<article class="dc-counter"><span>'+safe(label)+'</span><strong>'+safe(value)+
        '</strong><small>'+safe(note)+'</small></article>').join('')+'</div>'+
      '<div class="dc-banner"><b>Dados encontrados ≠ dados validados</b>'+
      '<p>Recolha automática existente, sujeita a limites. Não inventamos resultados, xG ou jornadas em falta. '+
      'Uma amostra de remates não representa uma época inteira. As probabilidades publicadas não foram alteradas.</p></div>'+
      '<div class="dc-leagues">'+rows+'</div>'+
      '<section class="panel dc-queue"><div class="panel-header"><div><h2>Fila de verificações</h2>'+
      '<p>Prioridades calculadas automaticamente; não realiza alterações sem validação</p></div></div>'+
      '<div class="table-scroll"><table><thead><tr><th>Liga</th><th>Urgência</th>'+
      '<th>Diagnóstico</th><th>Próxima ação</th></tr></thead><tbody>'+
      (queueRows||'<tr><td colspan="4">Sem verificações prioritárias com estes filtros.</td></tr>')+
      '</tbody></table></div></section>'+
      '<p class="dc-footnote">O motor apenas lê os snapshots existentes. Fontes oficiais e secundárias '+
      'não são assumidas como completas ou livres de restrições de reutilização. '+
      'Nenhum jogo é fundido ou liquidado automaticamente por este relatório.</p>';
  }
  window.MageburxCoverage={render};
})();
