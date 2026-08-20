---
name: mine-search-terms
description: Minera search terms de um cliente Google Ads para identificar negativas candidatas e keyword opportunities. Produz CSV auditável com coluna Reasoning. Triggers em "mine search terms", "minerar termos", "audit search terms", "find negatives", "search term report" + nome de cliente.
---

# Mine Search Terms

Skill operacional: roda análise completa de search terms de **um cliente** e produz CSV com recomendações.

**Metodologia base:** ver `search-term-methodology` (filtros, evaluation, níveis de negativa). Esta skill é o "como executar"; aquela é o "como avaliar".

## Pré-requisitos

Antes de rodar:
1. Saber o nome do cliente (ex: `Duana`) — todo path é relativo a `<Cliente>/`.
2. Ter o `account-conventions.md` do cliente preenchido (themes, naming, regras específicas).
3. Ter export atualizado de search terms em `<Cliente>/exports/`, OU MCP do Google Ads conectado.

Se algum dos 3 faltar, **pedir** ao usuário antes de prosseguir.

## Passos

### 1. Ler contexto do cliente

```
<Cliente>/CLAUDE.md
<Cliente>/briefing.md
<Cliente>/account-conventions.md
```

`account-conventions.md` é o mais crítico — define os **temas** de cada campanha/ad group e a **lista de negativas universais** do cliente.

### 2. Carregar dados

**Via CSV (modo atual, sem API):**
- Procurar arquivo mais recente em `<Cliente>/exports/` matching `search-terms-*.csv`.
- Se não existir, instruir o usuário a baixar do Google Ads:
  - Reports → Search terms
  - Date range: últimos 30 dias (default)
  - Download CSV
  - Salvar em `<Cliente>/exports/search-terms-YYYY-MM-DD.csv`

**Via MCP (quando disponível):**
- Usar GAQL: `SELECT search_term_view.search_term, segments.keyword.info.text, segments.keyword.info.match_type, campaign.name, ad_group.name, metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions FROM search_term_view WHERE segments.date DURING LAST_30_DAYS AND search_term_view.status = 'NONE'`
- `status = 'NONE'` filtra termos não-acionados na origem.

### 3. Filtrar

- Manter apenas linhas com `status = NONE` (se vier do CSV, filtrar; via MCP, já vem filtrado).
- Ordenar por **Cost desc** (não por clicks/impressions).
- Top N: começar com top 200 por custo. Se conta pequena, todos.

### 4. Avaliar cada termo

Aplicar `search-term-methodology` linha a linha:
- Categoria (Clear Negative / Off-theme / Keyword Candidate / Bottom-funnel / Monitor)
- Se negativa: nível (ad_group / campaign / account) + match type (exact / phrase / broad)
- Reasoning específico (não genérico)

Cruzar com `account-conventions.md` do cliente — usa o vocabulário e os themes corretos.

### 5. Produzir output CSV

Path: `<Cliente>/relatorios/search-term-negatives-YYYY-MM-DD.csv`

Colunas (ordem obrigatória):
```
Campaign,Ad Group,Keyword,Search Term,Match Type,Cost,Clicks,Impressions,CPC,CTR,Conversions,Action,Negative Level,Negative Match Type,Reasoning
```

Linha exemplo:
```
Search-Use Case,Meeting Notes,meeting notes,meeting minute,Exact,544.00,58,611,$16.28,9.49%,0,add_negative,ad_group,phrase,"Too generic; 'minute' doesn't tie to meeting notes — likely consumer/legal/medical context"
```

### 6. Apresentar resumo + propor batches

Antes de qualquer apply, **resumir** ao usuário:
- Total de termos avaliados, total recomendado pra negativar, wasted spend somado.
- Quebrar em batches por escopo (ad group / campaign / account) — Austin chama de "batches".
- Pedir confirmação batch por batch.

Exemplo de resumo:
> Avaliados 187 termos. Recomendações:
> - **Batch 1** (account-level): 12 negativas, R$ 4.2k wasted spend → universais ("free", "tutorial", "vagas")
> - **Batch 2** (campaign-level Search-Use Case): 41 negativas, R$ 7.8k wasted spend
> - **Batch 3** (ad group-level): 88 negativas, R$ 5.1k wasted spend
>
> Posso confirmar batch 1 primeiro?

### 7. Apply (somente com confirmação explícita)

- **Sem MCP:** gerar CSV no formato Google Ads Editor (bulk upload) com colunas que o Editor entende. Usuário sobe manualmente.
- **Com MCP:** chamar mutations uma batch por vez, parar após cada batch pra confirmar próximo.

**Nunca aplicar sem o usuário dizer explicitamente "yes apply" ou equivalente.** Tabular palpite ≠ confirmação.

## Output adicional — keyword candidates

Search terms categorizadas como `add_keyword` ou `Bottom-funnel signal` vão pra CSV separado:

Path: `<Cliente>/relatorios/keyword-candidates-YYYY-MM-DD.csv`

Colunas:
```
Search Term,Suggested Ad Group,Suggested Match Type,Cost,Clicks,Conversions,CPA,Reasoning
```

Esse CSV é input pra próxima skill de keyword expansion (a criar) ou pra upload manual.

## Erros comuns a evitar

- ❌ Rodar sem ler `account-conventions.md` → reasoning fica genérico, sem conhecer os themes do cliente.
- ❌ Avaliar termos com `status != NONE` → re-trabalho, recomendação já foi acionada.
- ❌ Ordenar por impressions/clicks em vez de cost → prioriza ruído.
- ❌ Recomendar account-level negative sem checar se quebra outra campanha do mesmo cliente.
- ❌ Coluna Reasoning vazia ou genérica ("irrelevante") → output rejeitado pelo CLAUDE.md.
