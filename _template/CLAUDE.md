# <Cliente> — contexto Google Ads

Pasta de gestão Google Ads do cliente **<Cliente>**. Carregado automaticamente quando trabalhando dentro de `<Cliente>/`.

Para regras globais (workflow, padrões de output, regras invioláveis), ver `../CLAUDE.md`.

## Arquivos deste cliente

- **briefing.md** — negócio, ICP, oferta, geo, idioma, budget, KPIs. Lê primeiro pra qualquer análise.
- **account-conventions.md** — naming de campanha/ad group, themes, lista de negativas universais. Lê toda vez que avaliar relevância de termo.
- **campanhas/** — docs markdown de estrutura de campanha (uma campanha = um arquivo, opcional).
- **keywords/** — listas de keywords positivas/negativas em markdown ou CSV.
- **exports/** — CSVs baixados do Google Ads. **Gitignored.**
- **relatorios/** — outputs gerados por skills. Convenção: `<skill>-YYYY-MM-DD.csv` ou `.md`.

## Conta Google Ads

- **Customer ID:** `<preencher: 123-456-7890>`
- **MCC manager:** `<preencher: ID do MCC se aplicável>`
- **Login email:** `<preencher>`
- **Moeda:** `<preencher: BRL / USD>`
- **Timezone:** `<preencher: America/Sao_Paulo>`

## Acesso

- [ ] MCC tem acesso à conta
- [ ] Developer token Google Ads API aprovado (ver `../mcp/README.md`)
- [ ] Conversion tracking validado (sources: Google Ads, GA4, server-side?)

## Notas de operação

<adicionar contexto que não cabe nos outros arquivos — incidentes, decisões recentes, ajustes manuais que o cliente fez fora do Claude, etc.>
