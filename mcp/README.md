# Google Ads MCP — setup

Objetivo: conectar Claude diretamente à Google Ads API via MCP, pra que as skills possam ler dados (GAQL queries) e aplicar mutations (com aprovação explícita).

**Isso é opcional.** Todo o workflow das skills funciona 100% sem MCP, com export/import de CSV manual (Google Ads UI + Google Ads Editor). MCP é um upgrade de conveniência — automatiza o passo de "pull data" e "apply" — não um requisito.

## Pré-requisitos do Google

### 1. Developer token

- Aplicar em: https://ads.google.com/aw/apicenter (precisa ter MCC manager account)
- Nível inicial: **Basic Access** (limitado a contas dentro do MCC, sem acessar contas externas — suficiente pra agência)
- Tempo de aprovação: geralmente 1-3 dias úteis, mas pode demorar mais.
- Salvar token em variável de ambiente, NÃO commitar.

### 2. MCC (Manager) account

- Se ainda não existe, criar em https://ads.google.com/intl/pt-BR/home/tools/manager-accounts/
- Pedir aos clientes pra **linkar** a conta deles ao MCC (eles aprovam pelo painel).

### 3. OAuth2 credentials

- Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID (tipo Desktop ou Web).
- Habilitar **Google Ads API** no projeto.
- Gerar refresh token via flow OAuth — o script `mcp/get_refresh_token.py` deste repo faz isso (abre o navegador, pede login/consent, grava o refresh token no `.env`).

## Variáveis de ambiente esperadas

Copiar `.env.example` (deste diretório) pra `.env` na raiz do workspace (gitignored):

```
GOOGLE_ADS_DEVELOPER_TOKEN=...
GOOGLE_ADS_CLIENT_ID=...
GOOGLE_ADS_CLIENT_SECRET=...
GOOGLE_ADS_REFRESH_TOKEN=...
GOOGLE_ADS_LOGIN_CUSTOMER_ID=... # MCC ID, sem hifens
```

Customer ID de cada conta cliente vai por chamada (não fica fixo no `.env` — uma agência com múltiplos clientes passa o `customer_id` certo em cada request).

## Opções de MCP server

### A) Comunitário existente

Pesquisar antes de construir do zero:
- https://github.com/modelcontextprotocol/servers (lista oficial)
- GitHub search: `google-ads mcp` — vários repos de terceiros com implementações prontas.

Avaliar: aceita GAQL? Suporta mutations? Como gerencia auth multi-cliente?

### B) Construir custom (Python ou Node)

Stack sugerida:
- Python + `google-ads-python` SDK + `mcp` package
- Wrapper expõe tools:
  - `get_search_terms(customer_id, date_range, status_filter='NONE')` → CSV/JSON
  - `get_campaign_metrics(customer_id, date_range)` → CSV/JSON
  - `get_budget_pacing(customer_id, days=7)` → série diária
  - `add_negative_keyword(customer_id, ad_group_id, text, match_type)` → MUTATION
  - `update_campaign_budget(customer_id, campaign_id, new_budget_micros)` → MUTATION

Decisões de design:
- **Tools de leitura:** sempre OK rodar direto.
- **Tools de mutation:** marcar como tal no MCP, e exigir confirmação explícita do usuário antes de chamar (regra global do `CLAUDE.md`).
- **Output:** preferir CSV (auditável) sobre JSON quando o usuário vai revisar.

## Configurar no Claude Code

Quando o server estiver pronto, adicionar em `~/.claude/mcp.json` (ou settings.json):

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "python",
      "args": ["caminho/para/server.py"],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "${env:GOOGLE_ADS_DEVELOPER_TOKEN}",
        "GOOGLE_ADS_CLIENT_ID": "${env:GOOGLE_ADS_CLIENT_ID}",
        "GOOGLE_ADS_CLIENT_SECRET": "${env:GOOGLE_ADS_CLIENT_SECRET}",
        "GOOGLE_ADS_REFRESH_TOKEN": "${env:GOOGLE_ADS_REFRESH_TOKEN}",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "${env:GOOGLE_ADS_LOGIN_CUSTOMER_ID}"
      }
    }
  }
}
```

## Checklist de progresso

- [ ] MCC criado
- [ ] Developer token gerado (nível Test Access)
- [ ] Basic Access solicitado
- [ ] Basic Access aprovado
- [ ] OAuth2 client ID criado (Google Cloud Console)
- [ ] Refresh token gerado (`python mcp/get_refresh_token.py`)
- [ ] MCP server escolhido (comunitário) ou construído (custom)
- [ ] MCP rodando localmente
- [ ] Claude Code conectado ao MCP
- [ ] Primeira query GAQL retornando dados reais
- [ ] Primeira mutation testada em conta de teste (não cliente real)

## Enquanto o MCP não está pronto

O workflow inteiro roda igual com CSV manual — só o passo final de "apply" muda (CSV pro Google Ads Editor em vez de chamada API). Ver a skill `launch-campaign` pro passo a passo de import via Google Ads Editor, incluindo as armadilhas conhecidas dele.
