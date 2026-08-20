---
name: client-onboarding
description: Onboarda um cliente novo no workspace de Google Ads — copia o template, guia o preenchimento de briefing.md e account-conventions.md via perguntas, monta checklist de acesso. Triggers em "onboard cliente", "novo cliente", "adicionar cliente", "cliente novo", "primeiro cliente" + nome do cliente.
---

# Client Onboarding

Skill operacional pra dar entrada em **um cliente novo** no workspace. Produz a pasta `<Cliente>/` completa e pronta pra qualquer outra skill (`launch-campaign`, `mine-search-terms`, etc.) rodar em cima.

## Quando rodar

- Usuário menciona um cliente que ainda não tem pasta em `google ads/<Cliente>/`.
- Antes de qualquer outra skill, se `<Cliente>/briefing.md` não existe ou está com campos vazios (`<preencher>`), rodar (ou pelo menos revisar) esta skill primeiro.

## Passo 1 — Copiar o template

1. Confirmar o nome exato do cliente com o usuário (vira o nome da pasta — usar o nome fantasia, sem acentos problemáticos se possível, ex: `Duana`, `BZR-Energia`).
2. Copiar `_template/` → `<Cliente>/` (todos os arquivos: `CLAUDE.md`, `briefing.md`, `account-conventions.md`, e as pastas vazias `campanhas/`, `keywords/`, `exports/`, `relatorios/`).
3. Se o sistema de arquivos não copiar pastas vazias, criá-las manualmente — as outras skills esperam que existam.

## Passo 2 — Preencher `briefing.md` via perguntas

Não preencher com suposição. Perguntar ao usuário em bloco (ou várias perguntas curtas), cobrindo pelo menos:

- **Negócio:** nome legal/fantasia, site, o que vende, modelo (B2B/B2C/e-commerce/SaaS/serviço/infoproduto), ticket médio, ciclo de venda.
- **ICP:** quem compra, onde mora, dor que resolve, concorrentes diretos.
- **Oferta:** promo ativa, CTA principal (comprar / agendar / trial / WhatsApp), landing page de destino.
- **Geo & idioma:** países/estados/cidades-alvo, idioma das campanhas.
- **Budget & metas:** budget mensal, KPI primário (CPA / ROAS / leads), meta numérica do KPI.
- **Conversões:** que evento(s) contam como conversão, fonte de tracking (pixel, GA4, server-side), valor por conversão se aplicável.
- **Histórico:** conta já existe? Gestor anterior fez o quê? Restrições contratuais (ex: não pode branded de concorrente).

Se o usuário não souber alguma resposta agora, deixar `<preencher>` no arquivo e marcar explicitamente na conversa — **não inventar número ou meta**.

## Passo 3 — Preencher `account-conventions.md`

Este é o arquivo mais crítico pras skills de avaliação (`search-term-methodology`, `mine-search-terms`, `investigate-campaign`). Sem ele, toda avaliação de relevância fica genérica.

1. **Naming convention** — usar o padrão default (`<Tipo>-<Tema>-<Geo opcional>` pra campanha, `<Tema específico>` pra ad group) a menos que o cliente já tenha convenção própria de conta existente.
2. **Themes de campanha** — perguntar: quantas campanhas fazem sentido pro orçamento? (lembrar a regra "budget pequeno não pulveriza" — ver `launch-campaign`). Cada campanha vira um bloco com tema central, quem deve/não deve ver, e a lista de ad groups previstos.
3. **Lista de negativas universais (account-level)** — começar de uma base genérica por vertical e ajustar com o usuário:
   - Termos informacionais/educacionais: `tutorial`, `como fazer`, `o que é`, `curso` (se o cliente não vende curso)
   - Termos de emprego: `vaga`, `vagas`, `emprego`, `currículo`
   - Termos de segunda mão/gratuito: `usado`, `grátis`, `gratis`, `de graça`, `doação`
   - Termos de reparo/peças (se o cliente vende produto novo, não conserto): `conserto`, `peça`, `manutenção`
   - Ajustar/complementar com o que o usuário souber da vertical específica.
4. **Good signals (intenção comercial forte)** — padrões tipo `<marca> + preço`, `<marca> + vs + concorrente`, `comprar + <produto>`, `<cidade> + <produto>` se geo importa.
5. **Regras específicas do cliente** — restrições contratuais, categorias sem margem, horário de bidding, etc. (vem do briefing).

## Passo 4 — Preencher `CLAUDE.md` do cliente

Campos de conta: Customer ID, MCC manager (se aplicável), login email, moeda, timezone, site, canal de conversão (ex: WhatsApp, formulário). Se algum dado não existe ainda (ex: conta Google Ads não foi criada), marcar como pendente no checklist de acesso, não deixar em branco silencioso.

## Passo 5 — Checklist de acesso

Sempre incluir e revisar com o usuário:

- [ ] Conta Google Ads criada
- [ ] MCC tem acesso à conta (linkado e aprovado pelo cliente)
- [ ] Developer token Google Ads API aprovado (ver `../mcp/README.md` — só bloqueia se for usar MCP; CSV manual funciona sem isso)
- [ ] Conversion tracking configurado e testado (blocker pra subir qualquer campanha — ver `launch-campaign`)
- [ ] Faturamento/billing configurado na conta
- [ ] GA4 instalado no site (recomendado, não obrigatório)

## Passo 6 — Próximo passo

Depois do onboarding, informar claramente ao usuário o estado:

- Se briefing + conventions completos e sem blocker de tracking → sugerir rodar `launch-campaign` pra desenhar a primeira campanha.
- Se falta algo (ex: conta Google Ads não existe, tracking não configurado) → listar os blockers explicitamente antes de seguir. Não propor estrutura de campanha em cima de uma conta que não existe ainda.

## Não fazer

- Não inventar ICP, budget, ou meta de KPI — se o usuário não souber, perguntar ou deixar `<preencher>`.
- Não copiar convenções/negativas de outro cliente sem adaptar — cada vertical tem termos ruins diferentes.
- Não pular a etapa de checklist de acesso — é o que evita subir campanha numa conta sem billing ou sem tracking.
