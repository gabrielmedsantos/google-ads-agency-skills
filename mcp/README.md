# Google Ads MCP — setup

Conecta o Claude direto à Google Ads API via um servidor MCP local (`mcp/server.py`), pra que as skills leiam dado real e apliquem mutations (sempre com aprovação explícita) sem depender de export/import CSV manual.

**Status: 34 tools, cobertura de Search + Performance Max + Display + Demand Gen + Video + Shopping + listas de negativa compartilhada + portfolio bidding strategies.** A maioria testada ponta a ponta contra uma conta de produção real (criação, edição, extensions, remoção — sempre limpando os artefatos de teste depois). Duas exceções documentadas abaixo (Video e Shopping) por falta de pré-requisito externo (vídeo do YouTube de propriedade do anunciante; Merchant Center linkado), não por bug.

## Pré-requisitos do Google

### 1. Developer token

- Aplicar em: https://ads.google.com/aw/apicenter (precisa ter MCC manager account)
- Nível inicial: **Basic Access** (limitado a contas dentro do MCC, sem acessar contas externas — suficiente pra agência)
- Tempo de aprovação: geralmente 1-3 dias úteis, mas pode demorar mais.
- Salvar token em variável de ambiente, NÃO commitar.

### 2. MCC (Manager) account

- Se ainda não existe, criar em https://ads.google.com/intl/pt-BR/home/tools/manager-accounts/
- Pedir aos clientes pra **linkar** a conta deles ao MCC (eles aprovam pelo painel).
- A autenticação é sempre no nível da MCC (`GOOGLE_ADS_LOGIN_CUSTOMER_ID`) — qualquer conta linkada fica acessível automaticamente, sem credencial nova por cliente. `list_accounts()` lista tudo que está acessível no momento.

### 3. OAuth2 credentials

- Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID (**tipo Web**, com `http://localhost:8765/` — com a barra final — cadastrado em "URIs de redirecionamento autorizados". Tipo Desktop não deixa cadastrar redirect URI customizado e quebra o fluxo do script).
- Habilitar **Google Ads API** no projeto.
- Gerar refresh token: `python mcp/get_refresh_token.py` — abre o navegador, pede login/consent, grava direto no `.env`.

## Variáveis de ambiente esperadas

Copiar `.env.example` pra `.env` na raiz do workspace (gitignored):

```
GOOGLE_ADS_DEVELOPER_TOKEN=...
GOOGLE_ADS_CLIENT_ID=...
GOOGLE_ADS_CLIENT_SECRET=...
GOOGLE_ADS_REFRESH_TOKEN=...
GOOGLE_ADS_LOGIN_CUSTOMER_ID=... # MCC ID, sem hifens
```

Customer ID do cliente final vai por chamada (não no `.env`) — todo tool pede `customer_id` explícito.

## Servidor MCP (`mcp/server.py`) — 34 tools

### Leitura (sempre livres, sem approval)

| Tool | Pra que serve |
|---|---|
| `list_accounts()` | Contas acessíveis com o refresh token atual |
| `get_campaign_metrics(customer_id, days, compare_previous)` | Métricas por campanha, comparativo de período — alimenta `weekly-review`/`investigate-campaign` |
| `get_search_terms(customer_id, days, status_filter, limit)` | Search terms por custo desc, filtrável por `status = NONE` — alimenta `mine-search-terms` |
| `get_budget_pacing(customer_id, days)` | Série diária de impression share / lost-to-budget / lost-to-rank — alimenta `budget-optimize` |
| `list_ad_groups(customer_id, campaign_id, days)` | Ad groups com métricas e status |
| `list_keywords(customer_id, ad_group_id, campaign_id, days)` | Keywords positivas com métricas, quality score, `criterion_id` |
| `list_extensions(customer_id, campaign_id)` | Sitelinks/callouts/snippets já anexados a uma campanha |
| `list_negative_keyword_lists(customer_id)` | Listas de negativa compartilhada, membros e campanhas anexadas |
| `list_bidding_strategies(customer_id)` | Portfolio bidding strategies da conta |
| `find_geo_target(query, country_code)` | Resolve nome de local → `geoTargetConstant` ID |
| `list_languages()` | IDs dos idiomas mais comuns |
| `research_keywords(customer_id, seed_keywords, geo_target_ids, language_id, limit)` | Keyword Planner: volume real de busca mensal, competição, faixa de CPC |
| `run_gaql(customer_id, query)` | GAQL arbitrária — escape hatch, só SELECT |
| `get_resource_metadata(resource_name)` | Campos válidos de um resource + metrics/segments compatíveis, pra não chutar campo no `run_gaql` |

### Mutation (sempre gated por approval)

**Criação de campanha (compostas — budget + campanha + estrutura completa, sempre PAUSED):**

| Tool | Tipo | Status |
|---|---|---|
| `create_search_campaign(...)` | Search | ✅ testada ponta a ponta |
| `create_pmax_campaign(...)` | Performance Max | ✅ testada ponta a ponta (com imagens reais) |
| `create_display_campaign(...)` | Display | ✅ testada ponta a ponta (com imagens reais) |
| `create_demand_gen_campaign(...)` | Demand Gen (ex-Discovery) | ✅ testada ponta a ponta — **geo/idioma não aplicados** (limitação da API, ver gotcha #12) |
| `create_video_campaign(...)` | Video (YouTube) | ⚠️ estrutura validada via introspecção, **não testada contra API real** — precisa de `youtube_video_id` de um vídeo de propriedade do cliente |
| `create_shopping_campaign(...)` | Shopping | ⚠️ estrutura validada via introspecção, **não testada contra API real** — precisa de Merchant Center linkado |

**Edição granular:**

| Tool | Pra que serve |
|---|---|
| `add_positive_keyword(customer_id, ad_group_id, text, match_type, cpc_bid_brl, approval)` | Adiciona keyword a um ad group existente |
| `update_keyword_bid(customer_id, ad_group_id, criterion_id, new_cpc_bid_brl, approval)` | Muda CPC bid de uma keyword |
| `set_keyword_status(customer_id, ad_group_id, criterion_id, status, approval)` | `ENABLED`/`PAUSED`/`REMOVED` de uma keyword |
| `add_negative_keyword(customer_id, level, scope_id, text, match_type, approval)` | Negativa em nível `ad_group` ou `campaign` |
| `set_ad_group_status(customer_id, ad_group_id, status, approval)` | `ENABLED`/`PAUSED`/`REMOVED` de um ad group inteiro |
| `update_campaign_budget(customer_id, campaign_id, new_budget_brl, approval)` | Muda orçamento diário |
| `set_campaign_status(customer_id, campaign_id, status, approval)` | `ENABLED`/`PAUSED`/`REMOVED` de uma campanha |
| `add_sitelinks` / `add_callouts` / `add_structured_snippet` | Extensions de campanha |
| `create_negative_keyword_list(customer_id, list_name, keywords, approval)` | Lista de negativa compartilhada (shared set) |
| `attach_negative_keyword_list(customer_id, shared_set_id, campaign_ids, approval)` | Anexa a lista a campanhas |
| `create_portfolio_bidding_strategy(...)` | Target CPA/ROAS/Impression Share/Maximize Conversions compartilhável entre campanhas |
| `assign_bidding_strategy(customer_id, campaign_id, bidding_strategy_id, approval)` | Aplica a portfolio strategy numa campanha |

Padrão de aprovação: primeira chamada sem `approval` (ou valor errado) devolve só um preview + a frase exata `CONFIRMO: <ação>` que precisa vir em `approval` na segunda chamada pra executar. Nenhuma mutation aplica sem essa segunda chamada.

Nas tools compostas de criação de campanha, se um passo no meio falhar, os passos anteriores **não são desfeitos automaticamente** — o retorno mostra `created_so_far`/o que já foi criado, pra revisão e limpeza manual (`set_campaign_status ... REMOVED`).

## Armadilhas reais encontradas (validando contra a API de produção)

Nenhuma estava documentada em lugar óbvio — cada uma custou pelo menos um round-trip de debug contra uma conta real:

1. **`campaign.contains_eu_political_advertising` é obrigatório em toda campanha nova** (compliance de transparência de ads político da UE). Sem ele, a API recusa com `field_error: REQUIRED` **sem dizer qual campo** — só aparece investigando `error.location.field_path_elements`.
2. **Remover uma campanha/ad group/keyword/budget/bidding strategy não é `update.status = REMOVED`** — a API recusa com `Enum value 'REMOVED' cannot be used`. É um tipo de operação separado: `Operation.remove = <resource_name>`.
3. **`client.get_type(nome)` já retorna uma instância pronta, não uma classe** (SDK `google-ads` 31.x / API v25). Chamar `client.get_type("FieldMask")(paths=[...])` quebra com `TypeError: object is not callable`. Usar direto: `operation.update_mask.paths.append("campo")`.
4. **Campos `int64` vêm como `string`** via `proto.Message.to_dict()` (cost_micros, impressions, clicks) — dividir/somar sem `int()` primeiro quebra com `TypeError`. Acesso direto ao atributo (sem passar por `to_dict`) já vem como `int` nativo.
5. **`GoogleAdsFieldService` não aceita `FROM` na query** — é sempre implícito.
6. **Reverse lookup de enum:** `client.enums.<Nome>(valor_int).name` funciona direto — não precisa de dict manual.
7. **"Brand Guidelines" bloqueia criação de campanha PMax** se ligado por padrão na conta — exige logo/business name linkados *antes* de a campanha existir (circular). Solução: `campaign.brand_guidelines_enabled = False` na criação. **Só existe pra PMax** — setar em Display/outros dá `BRAND_GUIDELINES_UNSUPPORTED_CHANNEL`.
8. **`AssetGroupService` valida os mínimos de asset NA CRIAÇÃO** (PMax e só PMax — Demand Gen não usa AssetGroup, ver #13) — não dá pra criar vazio e popular depois. Exige tudo numa única operação atômica via `GoogleAdsService.mutate` com resource names temporários (IDs negativos, ex: `customers/{cid}/assets/-1`).
9. **PMax exige as 3 imagens pra valer** (`MARKETING_IMAGE` 1.91:1, `SQUARE_MARKETING_IMAGE` 1:1, `LOGO` 1:1 mín. 128px) — `NOT_ENOUGH_MARKETING_IMAGE_ASSET` etc. são erros bloqueantes reais.
10. **`Asset` de imagem exige campo `name`** (`asset_error: NAME_REQUIRED_FOR_ASSET_TYPE`) — assets de texto não precisam, `image_asset` sim.
11. **Imagens com bytes idênticos em duas roles diferentes conflitam** (`DUPLICATE_ASSETS_WITH_DIFFERENT_FIELD_VALUE`) — a API dedupe por conteúdo em toda a conta; usar arquivos fisicamente diferentes por role.
12. **Demand Gen + `CampaignCriterionService` (geo/idioma) retorna `request_error: UNKNOWN — The error code is not in this version`** de forma consistente — testado com geo de estado, geo de país, sozinho, em lote, com e sem AssetGroup. Não é bug do código (mesmo padrão funciona em Search/PMax/Display); parece limitação real de versão da API/SDK ou do nível de acesso do token pra esse tipo específico. `create_demand_gen_campaign` sobe a campanha sem geo/idioma — configurar manualmente pela UI.
13. **Demand Gen não usa AssetGroup** (`CANNOT_ADD_ASSET_GROUP_FOR_CAMPAIGN_TYPE`) — diferente do que a analogia com PMax sugere. Usa o modelo clássico AdGroup + `AdGroupAd.demand_gen_multi_asset_ad` (mesmo formato do `responsive_display_ad`).
14. **Demand Gen tem budget mínimo diário mais alto que Search/PMax/Display** — testar com valores baixos (~R$10/dia) pode disparar `BUDGET_BELOW_PER_DAY_MINIMUM`; valores mais altos (~R$50/dia) funcionaram. Valor exato do mínimo não extraído (está em `error.details.budget_per_day_minimum_error_details`).
15. **Vídeo/Shopping em `ad.video_responsive_ad`/`shopping_product_ad` e `youtube_video_asset`/`shopping_setting.merchant_id` foram implementados só via introspecção do SDK** (campos confirmados existir e ter o shape esperado) — nunca rodaram contra a API real por falta de pré-requisito (vídeo do YouTube de propriedade do cliente; Merchant Center linkado). Testar antes de confiar em produção.

## Cobertura por tipo de campanha

| Tipo | Tool | Testado ponta a ponta? |
|---|---|---|
| Search | `create_search_campaign` | ✅ |
| Performance Max | `create_pmax_campaign` | ✅ |
| Display | `create_display_campaign` | ✅ |
| Demand Gen (Discovery) | `create_demand_gen_campaign` | ✅ (sem geo/idioma — gotcha #12) |
| Video | `create_video_campaign` | ⚠️ não testado — falta `youtube_video_id` real |
| Shopping | `create_shopping_campaign` | ⚠️ não testado — falta Merchant Center |

## Configurar no Claude Code

Adicionar em `.mcp.json` na raiz do seu workspace:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "python",
      "args": ["mcp/server.py"]
    }
  }
}
```

O script lê o `.env` sozinho (relativo à raiz do workspace) — não precisa passar credencial via env do MCP config.

Depois de qualquer mudança no `.mcp.json` ou no `server.py`, o Claude Code precisa recarregar a conexão (reiniciar a sessão, ou `/mcp` se a versão suportar reload) pra pegar o estado novo.

## Checklist de progresso

- [ ] MCC criado
- [ ] Developer token gerado e aprovado (**Basic Access**)
- [ ] OAuth2 client ID criado — tipo Web, redirect URI `http://localhost:8765/`
- [ ] Refresh token gerado (via `mcp/get_refresh_token.py`)
- [ ] `.env` completo (5/5 campos)
- [ ] MCP server registrado em `.mcp.json`
- [ ] Testado pelo menos 1 tool de leitura contra conta real
- [ ] Testado pelo menos 1 tool de mutation (com approval real, numa campanha de teste, limpando depois)
- [ ] Video: testar com `youtube_video_id` real de algum cliente antes de confiar
- [ ] Shopping: testar quando algum cliente tiver Merchant Center linkado antes de confiar

## Enquanto o MCP não está pronto

O workflow inteiro roda igual com CSV manual — só o passo final de "apply" muda (CSV pro Google Ads Editor em vez de chamada API). Ver a skill `launch-campaign` pro passo a passo de import via Google Ads Editor, incluindo as armadilhas conhecidas dele.
