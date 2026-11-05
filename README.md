# Afonso OS — Football Intelligence v2 · 2026/27

**Dashboard web de pré-jogo para Liga Portugal Betclic e 3F Superliga dinamarquesa.**

## Estado real

- **Construído e testado localmente:** app responsiva em HTML/JS/CSS, análise de forma e descanso, separadores de notícias e ausências e dossiê pré-jogo. Recolha de resultados a partir de TheSportsDB (API oficial do fornecedor).
- **Demonstração offline:** contém um snapshot PARCIAL de 60 jogos consultados em 05/11/2026. As estatísticas derivadas dessa amostra NÃO são estatísticas oficiais da época; o painel avisa.
- **Notícias RSS:** detetor preparado para consultar buscas do Google Notícias quando a cloud executar `scripts/update_intelligence.py`. No ficheiro de demonstração não há notícias reais, porque não foi executada uma recolha RSS neste ambiente. As manchetes são apenas indicadores para abrir e verificar a fonte, nunca dados confirmados.
- **Lesões e castigos:** API-Football opcional. Sem chave, a app mostra *cobertura desconhecida*, não «zero lesões». A API de lesões contém jogadores ausentes e «questionable» quando há cobertura; o acesso da época 2026/27 não está garantido no plano gratuito.
- **Cloud:** ficheiro GitHub Actions preparado para atualizar o dashboard duas vezes por dia, mas **NÃO está publicado**. Precisa de um repositório GitHub e ativação do Pages.
- **Solverde:** removida do projeto. Não consulta odds, não autentica contas nem executa apostas.

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

1. Cria um repositório público vazio em [github.com/new](https://github.com/new), por exemplo `afonso-os-football-intelligence`.
2. Carrega o conteúdo do projeto (não apenas o ZIP). O GitHub já está conectado ao ChatGPT, mas o repositório deve ser criado pelo proprietário.
3. Em **Settings → Pages → Build and deployment**, seleciona **GitHub Actions**.
4. Em **Actions**, executa `Football Intelligence — atualizar e publicar` (`workflow_dispatch`).
5. Depois de a execução terminar com sucesso, poderás aceder a `https://TEU_UTILIZADOR.github.io/afonso-os-football-intelligence/` (substitui o utilizador e verifica o URL real apresentado nas definições do Pages).
6. O workflow está configurado para executar duas vezes por dia, às **07:17 e 19:17 UTC**, não em tempo real. Os horários programados da GitHub podem sofrer atrasos e estão sujeitos a quotas.
7. No iPhone, abre o URL no Safari e usa **Partilhar → Adicionar ao ecrã principal**.

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
- As estatísticas de forma e descanso consideram **só jogos recolhidos da liga**, não taças, provas europeias, jogos de seleções ou dias de viagem. **Se os dados da liga estiverem incompletos, o descanso não é considerado fiável.**
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
