# Account Conventions — <Cliente>

**Documento mais crítico do cliente.** Skills de avaliação (search-term-methodology, mine-search-terms, etc.) leem este arquivo pra entender os **themes** da conta e tomar decisões de relevância.

## Naming convention de campanha

Formato: `<Tipo>-<Tema>-<Geo opcional>`

Tipos: `Search`, `PMax`, `Display`, `Video`, `Discovery`, `Shopping`.

Exemplos:
- `Search-Branded`
- `Search-NonBrand-MeetingNotes`
- `PMax-Geral-BR`

## Naming convention de ad group

Formato: `<Tema específico>` (dentro do escopo da campanha).

Exemplo, dentro de `Search-Use Case`:
- `Meeting Notes`
- `Audio Quality`
- `Action Items`
- `Calendar Integration`
- `CRM Sync`

## Themes / contextos de cada campanha

> **Esta seção é o coração do arquivo.** Cada campanha = um bloco. Skills cruzam isso com o ad group name pra avaliar relevância de search term.

### Campanha: `<Nome>`

- **Tema central:** <ex: usuários buscando ferramenta de transcrição de reuniões>
- **Quem deve ver:** <perfil>
- **Quem NÃO deve ver:** <perfil>
- **Ad groups:**
  - `<Ad Group A>` — sub-tema: <descrição em 1 frase>
  - `<Ad Group B>` — sub-tema: <descrição>
- **Match types preferidos:** Phrase + Exact (Broad só em ad group de teste isolado)
- **Bid strategy atual:** <ex: tCPA R$ 80>

### Campanha: `<próxima>`

(repetir bloco)

## Lista de negativas universais (account-level)

Termos que NUNCA devem entrar em nenhuma campanha desse cliente. Skill `mine-search-terms` deve filtrar pra esses primeiro como base.

| Termo | Match | Por que |
|---|---|---|
| free | phrase | Cliente é pago, busca grátis é fora do perfil |
| grátis | phrase | idem |
| tutorial | phrase | Buscas educacionais, não comprador |
| vagas | phrase | Pessoas procurando emprego, não cliente |
| <adicionar> | | |

## Lista de "good signals" (intenção comercial forte)

Termos/padrões que indicam fundo de funil — quando aparecem em search terms, viram keyword candidate prioritário.

| Padrão | Por que é bom |
|---|---|
| <marca> + "preço" | Comparação de preço = decisão |
| <marca> + "vs" + concorrente | Comparativo = decisão |
| "comprar" + <produto> | Intenção transacional explícita |
| <cidade> + <produto/serviço> | Local intent (se geo importa) |

## Regras específicas desse cliente

<Tudo que é particular dessa conta e não vale como regra global. Exemplos:>

- Não rodar branded de concorrente <X> por contrato.
- Categoria <Y> de produto não tem margem — bloquear via negativa de campaign-level.
- Horário comercial de bidding: <ex: 8h-22h apenas, fora desse horário bid -50%>.

## Histórico de mudanças relevantes

| Data | Mudança | Por que | Quem aprovou |
|---|---|---|---|
| | | | |
