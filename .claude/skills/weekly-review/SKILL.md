---
name: weekly-review
description: Review semanal estruturado de uma conta Google Ads — performance vs período anterior, mudanças relevantes, ações sugeridas para a semana. Triggers em "weekly review", "review semanal", "como tá a conta", "status semanal".
---

# Weekly Review

Skill operacional pra produzir o **relatório semanal** de uma conta. Output em markdown padrão.

## Pré-requisitos

- Cliente (ex: `Duana`)
- Window: últimos 7 dias vs 7 dias anteriores (default)
- Exports atualizados em `<Cliente>/exports/`: campaign metrics, ad group metrics, conversion data

## Estrutura do relatório

Path: `<Cliente>/relatorios/weekly-YYYY-MM-DD.md`

```markdown
# Weekly Review — <Cliente> — semana de <data inicio> a <data fim>

## TL;DR
<2 frases: o que aconteceu de relevante essa semana>

## Números
| Métrica | Esta semana | Semana anterior | Δ | Δ% |
|---|---|---|---|---|
| Spend | | | | |
| Impressions | | | | |
| Clicks | | | | |
| CTR | | | | |
| CPC médio | | | | |
| Conversões | | | | |
| CPA | | | | |
| ROAS (se aplicável) | | | | |
| Impression share | | | | |
| IS lost (budget) | | | | |
| IS lost (rank) | | | | |

## Por campanha
<tabela ou bullets — qual campanha puxou pra cima, qual puxou pra baixo>

## Mudanças aplicadas essa semana
<o que foi aprovado e aplicado — para auditoria>

## Sinais de atenção
- <ex: CPA da campanha X subiu 30%>
- <ex: impression share lost-to-rank da Y subiu — concorrente entrou>

## Ações sugeridas pra próxima semana
| Ação | Campanha/Ad Group | Reasoning | Impacto esperado |
|---|---|---|---|
| | | | |
```

## O que vira "sinal de atenção"

Usar os mesmos limiares de `investigate-campaign` pra decidir o que entra nessa seção (evita virar lista subjetiva):

- CPA piorou > 15% vs semana anterior
- Conversões caíram > 15% vs semana anterior
- CTR caiu > 10% relativo
- IS lost (budget) > 25% de forma consistente (não um dia isolado)
- Qualquer campanha nova entrando/saindo de learning phase (mudança de budget/target/LP nos últimos 7-14 dias)

Se algum sinal cruzar o limiar "crítico" de `investigate-campaign`, **recomendar rodar essa skill** na campanha específica em vez de tentar diagnosticar dentro do review semanal.

## Quando NÃO gerar um weekly-review "normal"

- **Conta muito nova (< 2 semanas de dado):** ainda em learning phase — reportar volume/gasto, mas não tirar conclusão de tendência de CPA/conversão.
- **Semana com feriado ou evento atípico do negócio:** anotar isso explicitamente no TL;DR pra não comparar contra uma semana normal como se fosse igual.

## Princípios

- **Comparativo, não absoluto.** Spend isolado não diz nada — sempre vs período anterior.
- **Toda ação sugerida tem Reasoning + impacto esperado** (ainda que estimativa).
- **Apply nunca acontece nesta skill.** Só registra recomendações. Aprovação + execução é separado.
- **Cadência:** rodar semanalmente, mesmo dia da semana, pra manter comparação limpa. Se pular uma semana, avisar no TL;DR que a comparação é de 14 dias, não 7.
