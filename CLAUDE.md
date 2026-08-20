# Google Ads — workspace de gestão por cliente

Este diretório centraliza a gestão de campanhas Google Ads de múltiplos clientes. Um cliente = uma pasta. Workflow baseado no setup do time de Growth Marketing da Anthropic (Austin Lau / @helloitsaustin, Mar 2026).

## Layout

```
google ads/
├── CLAUDE.md             ← este arquivo (regras globais)
├── .claude/skills/       ← skills de metodologia, compartilhadas entre clientes
├── mcp/                  ← config do Google Ads MCP (credenciais ficam fora do git)
├── _template/            ← copiar pra criar cliente novo
└── <Cliente>/            ← um por cliente
    ├── CLAUDE.md         ← contexto específico do cliente
    ├── briefing.md       ← negócio, ICP, oferta, KPIs
    ├── account-conventions.md  ← naming, themes, regras desse cliente
    ├── campanhas/        ← docs da estrutura de campanha
    ├── keywords/         ← positivas, negativas, pesquisa
    ├── exports/          ← CSVs baixados do Google Ads (gitignored)
    └── relatorios/       ← análises produzidas por skill
```

## Regras invioláveis

### 1. Mutations require explicit approval

Toda mudança que altera a conta do cliente — adicionar negativa, mudar lance, pausar ad group, ajustar budget — é **proposta**, nunca aplicada automaticamente. Output: tabela ou CSV com a mudança proposta + coluna de justificativa. Usuário confirma com "yes apply" antes de qualquer mutation via MCP.

**Por que:** auditoria, reversibilidade, e evitar estrago em conta de cliente. Padrão direto do Austin: "all mutations require explicit approval".

### 2. Toda recomendação tem coluna `Reasoning`

Qualquer output (CSV, tabela, lista) que sugere ação sobre a conta inclui uma coluna ou campo **Reasoning** explicando por quê. Exemplo do output de `mine-search-terms`:

| Campaign | Ad Group | Keyword | Search Term | Match | Cost | Conversions | Reasoning |
|---|---|---|---|---|---|---|---|
| Search-Use Case | Meeting Notes | meeting notes | meeting minute | Broad | $544 | 0 | Too generic, single-word "minutemate" doesn't relate to meeting notes or the CRM theme |

Sem `Reasoning`, a recomendação é rejeitada — usuário precisa poder auditar cada decisão sem ter que perguntar "por quê?".

### 3. Filtrar `status = NONE` ao minerar search terms

Search terms já adicionadas como keyword OU como negativa têm `status != NONE`. Ao procurar candidatas a negativa nova ou keyword nova, **filtrar para status = NONE** primeiro. Evita re-trabalho e duplicação.

### 4. Ordenar por spend descending

Ao avaliar performance, sempre ordenar por **custo gasto** (desc), não por número de impressions ou clicks. R$ é o recurso escasso. Um termo com 200 clicks a R$0,10 importa menos que um termo com 20 clicks a R$5.

### 5. Cross-reference de 3 dimensões pra search terms

Pra cada search term, avaliar **três coisas em conjunto**:
- A **search term** em si (o que o usuário digitou)
- A **keyword matched** (qual keyword foi acionada)
- O **campaign + ad group name** (em que tema/contexto isso vive)

A pergunta sempre é: **"essa search term cabe no tema desse ad group?"**

## Workflow padrão

1. **Onboarding cliente:** skill `client-onboarding` — copia `_template/` → renomeia pra `<Cliente>/` → guia o preenchimento de `briefing.md` e `account-conventions.md`.
2. **Primeira campanha (ou expansão):** skill `launch-campaign` — desenha estrutura (geo, budget, ad groups, keywords, RSAs, negativas), garante conversion tracking configurado, gera bundle de import.
3. **Pull data:** export CSV do Google Ads (ou via MCP quando o developer token estiver aprovado) → salva em `<Cliente>/exports/` com nome `<skill>-<YYYY-MM-DD>.csv`.
4. **Run skill:** invocar a skill apropriada (ex: `mine-search-terms`, `weekly-review`, `budget-optimize`, `investigate-campaign`). Skill lê `account-conventions.md` do cliente + métricas do export → produz output em `<Cliente>/relatorios/`.
5. **Review humano:** usuário confere o output, aceita/rejeita linhas, marca quais aplicar.
6. **Apply:** com MCP conectado, Claude aplica as mutations aprovadas (uma a uma ou em batch confirmado). Sem MCP, gera CSV pra upload manual no Google Ads Editor.

## Estado de integração

- **Google Ads API direta (via MCP):** decidido como caminho de longo prazo. Pré-requisitos pendentes (ver `mcp/README.md`):
  - [ ] Developer token aprovado pelo Google
  - [ ] MCC (Manager) account com acesso à conta do cliente
  - [ ] OAuth2 client_id/secret + refresh token

- **Enquanto API não está liberada:** workflow com CSV export/import manual. Skills funcionam igual — só o passo final de "apply" muda (CSV pro Google Ads Editor em vez de chamada API).

## Skills disponíveis

Em `.claude/skills/`. Cada uma tem `SKILL.md` com triggers e instruções.

| Skill | Pra que serve |
|---|---|
| `client-onboarding` | Onboarda cliente novo — copia template, guia preenchimento de briefing/conventions, checklist de acesso |
| `launch-campaign` | Desenha e sobe estrutura de campanha nova (geo, ad groups, keywords, RSAs, extensions, negativas) + bundle de import |
| `search-term-methodology` | Metodologia base de avaliação (referenciada pelas outras) |
| `mine-search-terms` | Minera search terms → CSV com negativas candidatas + keywords novas |
| `investigate-campaign` | Diagnóstico de uma campanha específica |
| `weekly-review` | Review semanal estruturado |
| `budget-optimize` | Recomendação de ajuste de budget baseado em impression share |

## Não fazer

- **Não misturar dados entre clientes.** Export de cliente A nunca vai pra pasta de cliente B.
- **Não commitar `exports/`** — `.gitignore` já cobre, mas conferir.
- **Não inventar métrica.** Se um número não tá no CSV/MCP, dizer "não disponível", não estimar.
- **Não aplicar mutation sem confirmação.** Mesmo que pareça óbvio.
