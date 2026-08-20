# Google Ads Agency Skills

Kit de skills do [Claude Code](https://claude.com/claude-code) pra gestão de contas Google Ads em agência — planejar e subir campanha, minerar search terms, revisar performance semanal, diagnosticar queda de campanha, e otimizar budget. Cada ação que muda a conta do cliente sai como **proposta auditável**, nunca como mutation automática.

Baseado no workflow do time de Growth Marketing da Anthropic (Austin Lau / [@helloitsaustin](https://twitter.com/helloitsaustin)), adaptado e expandido pra uso de agência com múltiplos clientes.

## O que tem aqui

```
google-ads-agency-skills/
├── CLAUDE.md              ← regras globais (lidas automaticamente pelo Claude Code)
├── .claude/skills/        ← as 7 skills (ver tabela abaixo)
├── _template/              ← copiar pra criar um cliente novo
│   ├── CLAUDE.md
│   ├── briefing.md         ← negócio, ICP, oferta, KPIs
│   ├── account-conventions.md  ← naming, themes de campanha, negativas universais
│   ├── campanhas/
│   ├── keywords/
│   ├── exports/            ← CSVs do Google Ads (sempre gitignored)
│   └── relatorios/
└── mcp/                    ← setup opcional de integração direta via Google Ads API
    ├── README.md
    ├── .env.example
    └── get_refresh_token.py
```

## Skills

| Skill | Pra que serve |
|---|---|
| `client-onboarding` | Onboarda cliente novo — copia o template, guia o preenchimento de briefing/conventions, monta checklist de acesso |
| `launch-campaign` | Desenha e sobe estrutura de campanha nova (geo, budget, ad groups, keywords, RSAs, extensions, negativas) + bundle de import pro Google Ads Editor, incluindo as armadilhas conhecidas dele |
| `search-term-methodology` | Metodologia base de avaliação de search term (referenciada pelas outras) |
| `mine-search-terms` | Minera search terms → CSV com negativas candidatas + keyword opportunities, sempre com coluna `Reasoning` |
| `investigate-campaign` | Diagnóstico aprofundado de uma campanha que caiu de performance — hipóteses ranqueadas com evidência |
| `weekly-review` | Review semanal estruturado — números comparativos, sinais de atenção, ações sugeridas |
| `budget-optimize` | Recomendação de ajuste de budget baseado em impression share lost-to-budget |

Cada skill tem seu próprio `SKILL.md` em `.claude/skills/<nome>/` com triggers e instruções completas — o Claude Code carrega automaticamente quando a conversa bate com o trigger.

## Como usar

### Opção 1 — clonar como workspace de agência

```bash
git clone <url-deste-repo> google-ads
cd google-ads
```

Abra essa pasta no Claude Code e peça pra onboardar um cliente novo (a skill `client-onboarding` guia o resto). **Se for gerenciar clientes reais aqui, mantenha o clone privado** — dado de cliente (telefone, Customer ID, briefing de negócio) não deveria ficar num repo compartilhado publicamente. O `.gitignore` já cobre exports e credenciais, mas as pastas de cliente em si (`<Cliente>/briefing.md`, etc.) não são ignoradas por padrão.

### Opção 2 — só copiar as skills pro seu projeto

```bash
cp -r .claude/skills/* /caminho/do/seu/projeto/.claude/skills/
```

Funciona standalone — as skills não dependem de nada fora de `.claude/skills/`, exceto pela leitura opcional de `account-conventions.md` do cliente (se você seguir a mesma convenção de pasta por cliente).

## Regras invioláveis (resumo — detalhe completo em `CLAUDE.md`)

1. **Mutation nenhuma acontece sem aprovação explícita do usuário.** Toda mudança de conta sai como proposta (tabela/CSV) com justificativa.
2. **Toda recomendação tem coluna `Reasoning`.** Sem isso, a recomendação é rejeitada por padrão.
3. **Search terms:** filtrar `status = NONE`, ordenar por spend desc, cruzar search term + keyword + ad group antes de decidir.
4. **Não misturar dado entre clientes.** Um cliente = uma pasta, nunca compartilhada.
5. **Não inventar métrica.** Se não está no export/API, é "não disponível" — não estimativa.

## Integração com a Google Ads API (opcional)

O workflow funciona 100% com export/import manual de CSV. Se quiser automatizar leitura e mutation via MCP, ver `mcp/README.md` — cobre developer token, MCC, OAuth2, e opções de servidor MCP (comunitário ou custom).
