---
name: search-term-methodology
description: Metodologia para avaliar search terms de Google Ads — quando é negativa candidata, quando é keyword nova, quando é "deixa quieto". Triggers em "search terms", "negative keywords", "search term report", "mine", "wasted spend", "irrelevant queries", "keyword opportunities".
---

# Search Term Mining Methodology

Como avaliar search terms de uma conta Google Ads. O objetivo NÃO é apenas "zero conversions = ruim" — é **relevância ao tema** do ad group + ROI.

Esta skill é **base teórica**. Skills operacionais (`mine-search-terms`, `investigate-campaign`, `weekly-review`) referenciam esta para decisões.

## Core approach

1. **Filtrar pra termos não-acionados** — só olhar search terms com `status = NONE` (não foi adicionada como keyword nem como negativa). Termos já tratados não precisam reavaliação.
2. **Ordenar por spend descendente** — onde o dinheiro tá indo. Um termo com 200 clicks a R$0,10 importa menos que um com 20 clicks a R$5.
3. **Cross-reference 3 dimensões** pra cada candidato:
   - **Search term** (o que o usuário digitou)
   - **Matched keyword** (qual keyword acionou o ad)
   - **Campaign + ad group name** (em que tema isso vive)

A pergunta é sempre: **"essa search term cabe no tema desse ad group?"**

## Relevance evaluation — categorias

### Clear Negative
Search term claramente fora do tema do ad group, gastou dinheiro, zero ou baixa conversão. **Ação:** adicionar como negativa (ver "Nível da negativa" abaixo).

Exemplos:
- Ad group "Meeting Notes" recebeu busca "free notepad app" → fora do tema (não é sobre meeting).
- Ad group "Audio Quality" recebeu busca "audio book recommendation" → áudio sim, mas contexto errado.

### Off-theme but ambiguous
Pode estar relacionado mas o ad group errado pegou. **Ação:** negativa no ad group atual + considerar se outro ad group da conta deveria captar.

### New Keyword Candidate
Search term performa bem (conversão, CTR alto, CPA aceitável) e cabe no tema. **Ação:** propor adicionar como keyword no ad group correto, com match type apropriado (geralmente Phrase ou Exact).

### Bottom-funnel signal
Search term contém intenção comercial forte (marca + "preço", "comprar", "trial", "vs concorrente"). **Ação:** propor keyword exact match + bid mais agressivo se ROI permite.

### No action / monitor
Volume baixo, sem sinal claro. Deixa passar mais uma semana.

## Nível da negativa — campaign vs ad group

Decisão crítica que muda o blast radius:

- **Ad group level:** termo é ruim só nesse contexto, pode ser ok em outro ad group da mesma campanha. Default conservador.
- **Campaign level:** termo é ruim na campanha inteira, mas pode ser relevante em outra campanha (ex: branded vs non-brand).
- **Account level (negative list):** termo é universalmente irrelevante pra esse cliente (ex: "free", "grátis", "vagas" pra um SaaS pago). Mais agressivo.

**Regra:** quando em dúvida entre dois níveis, escolher o mais conservador (ad group < campaign < account). Mais fácil promover depois do que reverter um bloqueio amplo.

## Match types — pra negativas

- **Negative exact:** bloqueia apenas a query exata. Mais cirúrgico.
- **Negative phrase:** bloqueia qualquer query que contenha essa frase. Default pra termos com cauda repetida.
- **Negative broad:** bloqueia qualquer query com todos os tokens em qualquer ordem. Cuidado — pode bloquear demais.

**Regra:** começar com **phrase** se o termo tem um padrão claro repetível (ex: "free", "grátis", "tutorial gratis"). Usar **exact** se é uma query isolada.

## Output esperado

Toda análise de search term produz CSV com **uma linha por termo avaliado** e estas colunas mínimas:

```
Campaign | Ad Group | Keyword | Search Term | Match Type | Cost | Clicks | Impressions | CPC | CTR | Conversions | Action | Negative Level | Negative Match Type | Reasoning
```

- **Action:** `add_negative` | `add_keyword` | `monitor` | `no_action`
- **Negative Level:** `ad_group` | `campaign` | `account` (vazio se action != add_negative)
- **Negative Match Type:** `exact` | `phrase` | `broad` (vazio se action != add_negative)
- **Reasoning:** frase explicando por quê — sem isso, recomendação é rejeitada.

## Anti-padrões

- ❌ "Zero conversões = negativa." Pode ter recebido só 5 clicks — sample size baixo demais.
- ❌ Avaliar search term sem ler o nome do ad group. Contexto é metade da decisão.
- ❌ Recomendar negativa account-level sem checar todas as campanhas (pode quebrar outra).
- ❌ Reasoning genérico tipo "irrelevante" — precisa dizer **por que** é irrelevante (fora do tema X, sample baixo, etc).
