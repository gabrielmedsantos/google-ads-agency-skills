---
name: investigate-campaign
description: Diagnóstico aprofundado de uma campanha Google Ads específica que está performando mal ou mudou de comportamento. Triggers em "investigate", "diagnosticar campanha", "campanha caiu", "por que a campanha X", "audit campaign".
---

# Investigate Campaign

Skill operacional pra diagnosticar **uma campanha específica** que tá com problema — CPA subiu, conversões caíram, CTR despencou, impression share virou.

## Pré-requisitos

- Nome da campanha (matching `account-conventions.md`)
- Window de análise (default: últimos 14 dias vs 14 dias anteriores — ajustar se a campanha for nova/baixo volume, ver "Cuidados" abaixo)
- Export de campaign-level + ad-group-level + keyword-level metrics em `<Cliente>/exports/` (ou GAQL via MCP quando disponível)

## Severidade — quando uma mudança é "significativa"

Não tratar qualquer flutuação como sinal. Usar como referência (ajustar por volume — sample pequeno tem ruído natural maior):

| Métrica | Atenção | Crítico |
|---|---|---|
| CPA | +15% a +30% | > +30% |
| Conversões (volume) | -15% a -30% | > -30% |
| CTR | -10% a -25% (relativo) | > -25% relativo |
| CPC médio | +15% a +30% sem mudança de bid | > +30% sem mudança de bid |
| Impression share | -10 a -20 pontos | > -20 pontos |

Com menos de ~30 clicks ou ~5 conversões no período, tratar qualquer delta com cautela — pedir mais dias de dado antes de concluir.

## Passos

### 1. Puxar e comparar métricas

Campaign-level: cost, impressions, clicks, CTR, CPC médio, conversões, CPA, impression share, IS lost (budget), IS lost (rank) — período atual vs período anterior de mesma duração.

### 2. Quebrar por ad group

Qual ad group específico está puxando a métrica pra baixo — raramente é a campanha inteira uniformemente.

### 3. Quebrar por keyword (top 20 por spend)

Ordenar por custo desc (regra global). Ver quem perdeu CTR/CPC/conversão especificamente.

### 4. Testar cada hipótese com dado, não suposição

- **Search terms degradaram** — auction ficou mais cara, termos irrelevantes novos entrando e roubando budget de termos bons. Verificação: puxar search terms do período (mesma lógica de `mine-search-terms`) e ver se a % de termos fora-do-tema subiu vs período anterior.
- **Quality Score / relevância caiu** — Google não expõe QS bruto em todo report, mas os sintomas aparecem indiretos: CTR caiu sem mudança de anúncio, CPC subiu pra manter a mesma posição, Ad Strength caiu. Verificação: checar se a landing page mudou, se o anúncio foi editado, se CTR caiu mais que a média da conta.
- **Bid strategy re-entrou em learning** — mudança de budget, de target (tCPA/tROAS) ou de landing page reinicia a fase de aprendizado (~1-2 semanas de instabilidade). Verificação: checar se houve mudança de configuração nos últimos 7-14 dias — se sim, a hipótese "algo quebrou" pode ser só "está reaprendendo", tratamento é esperar, não reagir.
- **Budget cap** — perdendo impressão por falta de orçamento, não por performance. Verificação: IS lost (budget) > 10% consistente nos últimos dias (cruzar com `budget-optimize`).
- **Auction insights mudou** — concorrente novo entrou no leilão ou aumentou lance. Verificação: comparar overlap rate / outranking share do relatório de Auction Insights entre os dois períodos.
- **Sazonalidade / mudança de mix** — evento externo (feriado, campanha de concorrente, mudança de oferta do próprio cliente). Verificação: comparar contra o mesmo período do ano anterior se houver dado, ou contra conhecimento do calendário do negócio.

### 5. Ranquear hipóteses

Ordenar as 3-5 hipóteses mais prováveis pela evidência encontrada no passo 4 — não listar todas com peso igual. A hipótese no topo precisa ter dado que a sustente, não só ser "a mais comum em geral".

## Output esperado

Markdown em `<Cliente>/relatorios/investigate-<campanha>-YYYY-MM-DD.md` com seções:

1. **TL;DR** — o que está errado em 2 frases.
2. **Métricas comparadas** — tabela período atual vs anterior, deltas absolutos e %.
3. **Quebra por ad group** — qual subconjunto da campanha está puxando o resultado.
4. **Quebra por keyword (top 20 por spend)** — quem ganhou ou perdeu performance.
5. **Hipóteses ranqueadas** — 3-5 hipóteses ordenadas por probabilidade, cada uma com a evidência que a sustenta (não só o nome da hipótese).
6. **Recomendações propostas** — sempre com Reasoning, sempre como proposta (não apply).

## Cuidados

- **Campanha com menos de 2-3 semanas de idade:** volatilidade é esperada (learning phase). Não tratar como "problema" sem separar sinal de ruído de fase inicial.
- **Não rodar sem comparativo temporal** — número absoluto sozinho não diz nada.
- **Não pular pra recomendação sem investigar** — confirmar hipótese com dado primeiro (passo 4), não intuição.
- **Cruzar com skills relacionadas** quando aplicável: `mine-search-terms` pra hipótese de search term, `budget-optimize` pra hipótese de budget cap.
