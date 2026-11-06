# Mageburx Football Intelligence · análise probabilística de futebol

**Dashboard web de pré-jogo para Portugal, Dinamarca (duas divisões), Países Baixos e Noruega.**

## Estado verificado em 06/11/2026

- **Produção:** repositório público `mageburx/mageburx-football-intelligence`, com GitHub Actions e GitHub Pages. O workflow executa a recolha e a publicação a cada hora (sujeito a atrasos do GitHub), além de aceitar execução manual.
- **Ligas:** cinco épocas históricas por campeonato (Portugal e Dinamarca, 2021/22–2025/26). A qualidade e a elegibilidade dos jogos para o modelo são auditadas separadamente.
- **Taças e UEFA:** recolha complementar de Taça de Portugal, Taça da Liga, Taça da Dinamarca e provas UEFA; o calendário histórico extra-liga permanece **parcial**. O painel discrimina jogos adicionais nacionais e europeus.
- **Backtesting de fadiga:** o ensaio v5.3 testa separadamente 2024/25 e 2025/26, mas **não demonstrou melhoria robusta**; por isso não altera probabilidades de produção.
- **Fiabilidade:** há backtests históricos, mas o registo prospetivo precisa de jogos terminados e liquidados antes de sustentar afirmações sobre fiabilidade futura.
- **Apostas:** não executa apostas, não recolhe odds de casas de apostas nem demonstra rentabilidade. As estimativas são apenas investigativas.

Os números de cobertura e desempenho variam a cada recolha. A fonte de verdade é a branch persistente `football-data` e os JSON publicados no GitHub Pages.

## Histórico recente e evidência separada nas novas ligas

**Eredivisie:** a fonte OpenFootball [football.json](https://github.com/openfootball/football.json) disponibiliza dados sob **CC0-1.0**. `scripts/collect_openfootball_nl.py` reconcilia os resultados da época 2026/27 com o calendário TheSportsDB, conserva os IDs existentes, bloqueia resultados divergentes e nunca introduz resultados de partidas futuras. Também guarda separadamente até cinco épocas anteriores em `data/nl_history.json`, com bandeira `complete` apenas quando há 306 jogos concluídos e 18 clubes com 34 partidas. Os anos incompletos são explicitamente excluídos do teste histórico reservado.

**Dinamarca 1. Division e Noruega Eliteserien:** continuam a recolher resultados pela API gratuita, sem exceder o limite de chamadas. Depois de haver pelo menos 30 resultados de referência, o motor pode criar previsões exploratórias; a amostra cronológica da própria época **não é** uma validação independente. O motor não inventa jogos nem extrapola histórico de outra liga.

**Fiabilidade por campeonato:** `scripts/build_expansion_reliability.py` publica `data/expansion_reliability.json`, com jogos disponíveis, antecipações guardadas, Brier/Log Loss 1X2 cronológicos e, no caso da Eredivisie, teste numa época completa reservada depois de treinar só em épocas anteriores. A avaliação prospetiva depende de partidas com previsões emitidas antes do início e efetivamente concluídas. A comparação com odds comerciais / ROI permanece **não verificada**.

A recolha CC0 tem intervalo mínimo de 22 horas, é gratuita e não reclama utilização exclusiva dos dados. Relatórios e arquivo são guardados na branch `football-data`, sujeitos à licença das fontes e à integridade dos resultados.

## Jogos futuros oficiais dinamarqueses e previsões 1X2 prospetivas

A página pública e única da [DBU, Betinia Liga 2026/27](https://www.dbu.dk/resultater/pulje/507530/kampprogramFuld) inclui resultados e partidas agendadas. O novo `scripts/parse_dbu_schedule.py` lê **apenas datas futuras** da mesma página que já era consultada pela recolha oficial com verificação de `robots.txt`: valida o número do jogo e as equipas, converte horas do fuso `Europe/Copenhagen`, não inventa horários em falta e **nunca atribui resultados a encontros futuros**. A reconciliação preserva resultados e identificadores anteriores, evita duplicados e marca remarcações apenas quando o número oficial coincide. As jornadas pós-fase regular ainda podem não estar publicadas.

As probabilidades de resultado final **1/X/2** passam a ter um registo próprio: `data/expansion_1x2_ledger.json` (persistido na branch `football-data`). O módulo `scripts/record_expansion_1x2.py` guarda valores `p1/px/p2` **só para jogos de data posterior à emissão**, com carimbo temporal e SHA-256, e nunca altera registos já emitidos. Só liquida resultados depois da data do jogo, com placares válidos e chave original. As previsões de outros mercados guardadas no registo anterior **não são retroativamente convertidas em previsões 1X2**.

A página *Fiabilidade* distingue o número de previsões 1X2 efetivamente guardadas das métricas históricas, e publica **Brier** e **Log Loss** apenas à medida que existirem jogos realmente concluídos. São indicadores experimentais, não uma demonstração de vantagem monetária ou aconselhamento de apostas. O algoritmo não foi reajustado por esta mudança; custo adicional **0 €**.

## Fontes alternativas 2026 (Noruega e Dinamarca)

- **Noruega / Eliteserien:** `scripts/collect_norwegian_fantasy.py` lê exclusivamente o CSV público de calendário/resultados 2026 de [TopMarx/eliteserien](https://github.com/TopMarx/eliteserien), reconcilia pares de equipas e datas com a API principal e guarda apenas os factos necessários para o modelo. O projeto de código é MIT, **mas os dados são propriedade da liga/fornecedores**; a disponibilização no GitHub não concede direitos de exploração comercial. Não usar este feed como produto comercial sem autorização. O coletor exige 16 clubes, um mínimo de 100 partidas na fonte, verifica a época, respeita o limite diário e não aceita resultados do próprio dia nem posteriores.
- **Dinamarca / Betinia Liga (1. Division):** `scripts/collect_danish_first_official.py` tenta consultar **uma página pública da DBU** (grupo 507530, 2026/27) uma vez por dia, **apenas se robots.txt permitir**. Um erro, formato não reconhecido ou bloqueio preserva integralmente o calendário anterior. Os resultados oficiais encontrados são verificados e reconciliados sem ultrapassar o ritmo de recolha autorizado; conflitos de marcadores ficam em quarentena. A recolha TheSportsDB mantém-se ativa e recebe prioridade no orçamento gratuito de pedidos assim que a Noruega tem calendário suficiente.

As estatísticas de xG, notícias, odds e disponibilidade de jogadores **não** são acrescentadas por estes módulos. Continuam a ser necessárias amostras independentes e avaliações prospetivas antes de atribuir fiabilidade ou rentabilidade às previsões de qualquer uma destas ligas.

## Auditoria de integridade das previsões 1X2

O sistema mantém dois conceitos distintos: **testes históricos** e **previsões realmente guardadas antes do jogo**. O ficheiro `data/expansion_1x2_ledger.json` preserva a primeira previsão 1X2 emitida para cada encontro futuro; uma previsão passada nunca é reconstruída a partir dos resultados.

O relatório `data/expansion_1x2_audit.json`, produzido por `scripts/audit_expansion_1x2.py`, verifica por liga assinaturas SHA-256, duplicações, cronologia, probabilidades, resultados contraditórios e alterações de datas. Apresenta jogos futuros, no próprio dia, atrasados sem resultado, adiados e previsões invalidadas. Só calcula Brier e Log Loss para resultados confirmados com previsão anterior à data original, integridade válida e sem conflitos.

O dashboard mostra o estado resumido em **Fiabilidade**, e não no ecrã inicial. A contagem de jogos previstos não corresponde a apostas nem a retorno financeiro. Ligações das fontes e regras de uso continuam sujeitas a revisão.

## Cinco campeonatos monitorizados

| ID interno | Competição | ID TheSportsDB | Época da fonte |
|---|---|---:|---|
| `pt` | Liga Portugal | 4344 | 2026-2027 |
| `dk` | 3F Superliga | 4340 | 2026-2027 |
| `dk2` | Danish 1st Division / Betinia Liga | 4683 | 2026-2027 |
| `nl` | Eredivisie (Países Baixos) | 4337 | 2026-2027 |
| `no` | Eliteserien (Noruega) | 4358 | **2026** |

A recolha de `dk2`, `nl` e `no` está em `scripts/collect_expanded_leagues.py`, com orçamento de **até seis consultas por execução**, intervalo entre pedidos, interrupção no HTTP 429 e progresso guardado em `season.json` na branch `football-data`. A nova recolha corre depois das duas ligas iniciais e antes do modelo, reutilizando Poisson/Dixon–Coles/Elo com resultados efetivamente disponíveis. O endpoint da época pode devolver um subconjunto de resultados; por isso não confirma automaticamente a completude. São consultadas jornadas aos poucos, sem inventar as que faltam.

**Atenção aos limites:** o histórico auditado de cinco épocas, a calibração independente, as estatísticas xG, e os feeds específicos de notícias/lesões continuam inicialmente limitados às ligas anteriormente suportadas. A cobertura histórica das três novas ligas é **parcial e não certificada**; nunca interpretar probabilidades iniciais como validação de rentabilidade. Na Dinamarca os play-offs podem reutilizar numeração de jornadas; a classificação é indicativa, não a oficial após o desdobramento.

Testes: `python -m unittest tests.test_expanded_leagues -v`.

## Laboratório de estatísticas avançadas (remates/xG)

O GitHub Actions executa o coletor `scripts/collect_advanced_signals.py` após a auditoria leve de fontes. O módulo verifica `robots.txt`, usa uma amostra máxima de **3 jogos por liga** e respeita um intervalo mínimo de **22 horas** entre pedidos por liga, restaurando as observações anteriores a partir da branch `football-data`. Se as condições da fonte não puderem ser verificadas, falha sem inserir dados falsos.

- Apenas observa **remates, remates à baliza e xG explicitamente presente**. xG ausente é `null`, nunca uma estimativa automática.
- Guarda um registo mínimo de cada amostra, com ligação, atribuição e primeira hora de observação. Não copia o ficheiro integral do fornecedor.
- O `shots_research.json` calcula pressão ofensiva **descritiva** para encontros futuros, a partir de jogos anteriores já observados e de amostras mínimas de 3 partidas por equipa nos últimos 90 dias. Trata-se de um laboratório, **não** de uma alteração aos resultados previstos.
- Não existem ainda estatísticas avançadas historicamente auditadas para 2024/25–2025/26 em ambas as ligas, pelo que não é possível demonstrar melhoria fora da amostra nem alterar o modelo de produção.
- A compilação Cornerflick é CC BY 4.0, mas os direitos dos dados subjacentes são distintos. Para utilização comercial ou redistribuição de grandes volumes, confirmar previamente os direitos e as autorizações relevantes.

Testar sem rede: `python -m unittest tests.test_advanced_signals -v`.
Dados gerados: `data/advanced_signals.json` e `data/shots_research.json`; o dashboard apresenta os respetivos estados. Sem despesas de fornecedores.

## Nova interface e ensaio Poisson + xG

A interface principal foi simplificada: **Início**, **Analisar jogo**, **Jogos** e **Fiabilidade**. Classificações, modelo detalhado, notícias, ausências e simulador estão dentro de **Mais análises**. O início mostra um jogo em destaque, próximos encontros e um resumo compacto. Os relatórios extensos são expansíveis, não são o ecrã inicial.

O motor de produção **não foi alterado**. O ficheiro `scripts/build_xg_experiment.py` prepara uma experiência prospetiva independente: exige **3 jogos com xG para cada equipa**, observados antes do encontro, nos últimos 90 dias. Quando o critério é cumprido, congela uma previsão Poisson/Dixon–Coles base e uma alternativa conservadora com 20% de contribuição de xG em `xg_shadow_ledger.json`. Só compara os resultados após os jogos terminarem. O limiar indicativo para rever os resultados é 100 encontros liquidados por liga; mesmo nesse caso, a publicação do modelo depende de revisão humana e dos direitos de utilização dos dados.

A falta de cobertura significa **sem experiência disponível**, nunca xG=0 ou melhoria provada. O registo de previsões experimentais é separado do registo oficial. A experiência é gratuita e não envolve contas de apostas.

Testes: `python -m unittest discover -s tests -p 'test_*.py' -v`, `node --test tests/test_model.cjs tests/test_clean_ui.cjs` e `node --check app/app.js`.

## Dashboard

- **Visão geral** com calendário, classificação e estatísticas por competição.
- **Dossiê pré-jogo** para cada encontro futuro, comparando golos marcados/sofridos e últimas partidas recolhidas, descanso conhecido na **mesma liga**, notícias ligadas às equipas e registos de indisponibilidade.
- **Notícias & sinais** com RSS, categorias como lesões/castigos/treinador/onze, data e ligação para a fonte. Categorização por palavras-chave — **não comprova a notícia**.
- **Lesões & castigos** com `player`, `status`, `reason`, `fixture_date` e fonte verificável; se a fonte não estiver configurada, é mostrado claramente «sem cobertura».
- **Modelo** Poisson 1X2 para explorar hipóteses com golos; NÃO ajusta probabilidades por notícias ou lesões sem backtesting. Não é previsão calibrada nem recomendação de aposta.

## Testar sem instalar bibliotecas extras

```bash
python scripts/preview.py
```

Abre `http://localhost:8742`, ou utiliza o ficheiro standalone `Afonso_OS_Football_Intelligence_PREVIEW.html` (pré-visualização offline com dados parciais, sem notícias inventadas). Os dados reais ficam em `data/season.json` e `data/intelligence.json`.

## Atualizar dados quando houver Internet

```bash
python scripts/update_data.py
python scripts/update_intelligence.py
python scripts/preview.py
```

`update_data.py` procura todas as jornadas da época; a API TheSportsDB pode impor limites. `update_intelligence.py` pesquisa manchetes RSS num número limitado de consultas, identifica clubes e termos-chave e guarda referências com data. Mantém um pequeno cache de manchetes recentes quando os RSS falham. Se uma busca não recuperar notícias, o bot indica falta de dados.

### Ativar fornecedor de lesões (opcional)

1. Regista uma conta na [API-Football](https://www.api-football.com/) e verifica se o plano cobre *injuries* para a **temporada 2026/27** nas ligas de Portugal e Dinamarca.
2. No GitHub, em **Settings → Secrets and variables → Actions**, cria o secret `API_FOOTBALL_KEY` com a chave de acesso. **Nunca** coloques a chave diretamente no JavaScript, no JSON publicado ou no repositório.
3. O workflow usa a chave na recolha de dados no servidor da GitHub Actions e publica apenas os resultados. Se a API não devolver cobertura, o dashboard não assume que não existem ausências.
4. Os identificadores usados no módulo para as ligas são ajustáveis por `API_FOOTBALL_LEAGUE_PT` e `API_FOOTBALL_LEAGUE_DK`. Confirma os IDs no endpoint `/leagues` do teu fornecedor antes de depender deles; a identificação dos clubes pode necessitar de expandir `ALIASES`.

Também é possível acrescentar manualmente **apenas factos verificados** no ficheiro `data/verified_absences.json`, com o formato de `data/verified_absences.example.json`, inserindo obrigatoriamente a URL da fonte e a data do jogo. As notícias por si só não entram nessa lista.

## Publicação GitHub Pages (cloud)

- Repositório: [mageburx/mageburx-football-intelligence](https://github.com/mageburx/mageburx-football-intelligence).
- Execuções: [Actions](https://github.com/mageburx/mageburx-football-intelligence/actions).
- URL do dashboard: [mageburx.github.io/mageburx-football-intelligence](https://mageburx.github.io/mageburx-football-intelligence/) (confirmar o endereço publicado nas definições do Pages).
- O workflow `.github/workflows/update-and-deploy.yml` usa `cron: '17 * * * *'` (uma vez por hora); a execução real pode atrasar.
- Os dados são persistidos na branch `football-data` e os relatórios de execução são arquivados como artefactos durante 90 dias.
- No iPhone, abrir o URL no Safari e escolher **Partilhar → Adicionar ao ecrã principal**.

## Estrutura

```text
app/                 # Interface, estilos e JavaScript
scripts/update_data.py          # Jornadas / resultados / calendário
scripts/update_intelligence.py  # RSS de notícias + ausências opcionais com fonte
scripts/build_standalone.py     # Demonstração HTML autónoma
data/season.json      # Snapshot parcial incluído
data/intelligence.json # Sem notícias/lesões inventadas no preview
data/verified_absences.json # Entradas editoriais verificáveis (vazio por defeito)
.github/workflows/update-and-deploy.yml # Recolha e publicação
```

## Qualidade dos dados / limitações

- A fonte TheSportsDB é comunitária e pode ter resultados incompletos ou errados.
- O motor de probabilidades continua a usar resultados da liga; o painel experimental de descanso inclui jogos conhecidos de taças e UEFA, mas nunca assume calendários externos completos. Não contabiliza jogos das seleções nem viagens.
- A classificação da Dinamarca pode divergir da oficial após a divisão em grupos.
- RSS apenas apresenta manchetes, sem interpretação do artigo completo; menções, rumores e duplicados podem ocorrer. Verificar artigos e comunicados de clubes antes de agir.
- Não existe uma ponderação validada sobre impacto de jogadores indisponíveis nem prova de retorno financeiro.
- Os dados da API-Football podem estar indisponíveis por planos, quotas ou cobertura de uma liga; não inferir ausência de lesões a partir de resposta vazia.
- Nunca utilizar estes dados para apostar automaticamente.

## Testes

```bash
python -m pytest -q
node --test tests/test_model.cjs
node --check app/app.js
```

As rotinas de recolha foram testadas com dados sintéticos de teste e o HTML standalone foi gerado. **Não foi possível verificar a interação visual no browser** neste ambiente devido às restrições do browser automático.

## Fontes

- [TheSportsDB](https://www.thesportsdb.com/docs/api)
- [API-Football / documentação](https://www.api-football.com/documentation_v3) e [planos](https://www.api-football.com/pricing)
- [Google News RSS (formato de pesquisa, não API oficial estável)](https://feeder.co/pt/knowledge-base/rss-feed-creation/google-news-rss-feeds/)
- [Sportmonks — dados de ausências](https://www.sportmonks.com/glossary/injuries-and-suspensions/) (alternativa possível para integração futura)

Sem parceria com ligas, operadores ou fornecedores de dados. As licenças e termos das fontes devem ser respeitados antes de publicação comercial.
