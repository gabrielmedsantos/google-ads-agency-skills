---
name: budget-optimize
description: Recomendação de ajuste de budget em campanha Google Ads baseado em impression share lost-to-budget. Padrão Austin Lau — se IS lost (budget) > 30%, há headroom para aumentar. Triggers em "budget", "impression share", "lost to budget", "aumentar budget", "otimizar budget".
---

# Budget Optimize

Skill operacional pra recomendar ajuste de budget em uma campanha (ou todas) baseado em **impression share lost to budget**.

Padrão direto do Austin Lau: ele aumentou budget de uma campanha de $6.800 → $8.160/dia (+20%) porque IS lost (budget) estava entre 38-52%.

## Pré-requisitos

- Cliente (ex: `Duana`)
- Window: últimos 7 dias (precisa de dado dia-a-dia, não agregado)
- Export com colunas: `Campaign`, `Date`, `Impression share`, `Search lost IS (budget)`, `Search lost IS (rank)`, `Cost`

## Heurística

Avaliar **por campanha**:

| IS lost (budget) | Diagnóstico | Ação |
|---|---|---|
| < 10% | Budget não é gargalo | Não mexer |
| 10-25% | Pouco gargalo, ROI primeiro | Só aumentar se CPA tá ok |
| 25-50% | **Headroom claro** | Propor +15-25% e medir |
| > 50% | Subfundeado | Propor +30-50%, mas testar em 2 etapas |

Ao mesmo tempo cruzar com **CPA / ROAS atual**:
- Se CPA já está acima da meta → não aumentar budget, ajustar bid antes.
- Se CPA está abaixo da meta E IS lost (budget) > 25% → forte caso pra aumentar.

## Output esperado

Path: `<Cliente>/relatorios/budget-recommendations-YYYY-MM-DD.md`

```markdown
# Budget Recommendations — <Cliente> — <data>

| Campanha | Budget atual | IS lost (budget) 7d | CPA 7d | Recomendação | Novo budget | Reasoning |
|---|---|---|---|---|---|---|
| Search-Use Case | R$ 6.800/dia | 47% | R$ 72 (meta R$ 80) | Aumentar +20% | R$ 8.160/dia | IS lost budget consistente 38-52% diariamente. CPA abaixo da meta. Headroom claro. |
| | | | | | | |
```

Mostrar **breakdown diário** quando recomendar mudança (igual o screenshot do Austin):

```
Date       | Imp. Share | Lost to Budget
Mon 3/17   | 38.3%      | 52.0%
Tue 3/18   | 41.8%      | 48.0%
...
```

## Apply

- **Sem MCP:** instruir mudança manual no Google Ads (Settings → Daily budget).
- **Com MCP:** propor mutation, esperar `"yes apply"` ou `"yes increase it to X"`, então aplicar.

**Nunca** ajustar budget sem confirmação — é uma das mutations mais sensíveis (impacta gasto imediato).

## Cuidados

- **Campanha com < 2 semanas de idade ou < 15 conversões:** ainda em learning phase — aumento de budget agora reinicia o aprendizado do bid strategy automatizado. Se o caso for forte (IS lost alto + CPA ok), avisar esse trade-off explicitamente em vez de recomendar direto.
- **Depois de qualquer aumento aplicado:** esperar pelo menos 3-5 dias antes de medir o efeito — mudança de budget também pode reiniciar parte do learning se a bid strategy for automatizada.

## Não fazer

- Não aumentar budget só porque IS lost (budget) é alto, sem checar CPA / ROAS.
- Não usar média semanal de IS — usar série diária pra ver consistência.
- Não recomendar +100% de uma vez. Etapas de 20-30% pra dar tempo de medir.
