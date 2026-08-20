---
name: launch-campaign
description: Planeja e sobe a estrutura de uma campanha Google Ads nova (ou uma expansão) — geo, budget, ad groups, keywords, RSAs, extensions, negativas — e gera o bundle de import pro Google Ads Editor ou aplica via MCP. Triggers em "criar campanha", "nova campanha", "subir campanha", "estrutura de campanha", "lançar campanha", "expandir campanha", "montar ad groups" + nome de cliente.
---

# Launch Campaign

Skill operacional pra desenhar e subir a estrutura de **uma campanha Search nova** (ou expansão de uma existente) na conta de um cliente.

**Pré-requisito:** cliente já onboarded (ver `client-onboarding`) — `briefing.md` e `account-conventions.md` preenchidos. Sem isso, a estrutura fica sem tema definido e sem lista de negativas base.

## Passo 0 — Conversion tracking é blocker, não detalhe

**Regra inegociável: não subir campanha ATIVA sem conversion tracking funcionando e testado.** Sem isso, o Google Ads (e qualquer bid strategy automatizada) otimiza às cegas — gasta o mesmo dinheiro e entrega pior resultado. Campanha pode ser criada e ficar **PAUSADA** enquanto o tracking não está pronto; nunca ativar antes.

Opções, em ordem de preferência pra conta nova/pequena:

| Opção | Quando usar | Trade-off |
|---|---|---|
| **gtag.js direto no site** | Site simples, sem outras tags planejadas | Mais rápido, sem delay de propagação |
| **Google Tag Manager (GTM)** | Cliente já vai crescer o stack de tags (Meta Pixel, GA4 custom events, etc.) | Mais setup inicial, mais flexível depois |
| **GA4 event → import pro Ads** | Cliente já tem GA4 maduro e quer um único event source | Delay de 24-72h entre evento e Ads enxergar — pior pra fase de aprendizado |

Passos genéricos (gtag direto):
1. Criar **Conversion Action** no Google Ads (categoria adequada — Lead, Purchase, etc.; **Count = One** se o evento é binário tipo "iniciou conversa", `Count = Every` se cada ocorrência vale, ex: compra).
2. Instalar o snippet `gtag('event', 'conversion', {...})` no evento certo do site (clique em botão, submit de formulário, thank-you page).
3. Testar com a extensão **Google Tag Assistant** antes de considerar pronto.
4. Esperar **24-48h** após a primeira conversão real disparar antes de confiar no relatório do Ads — não testar e ativar campanha no mesmo minuto.

## Passo 1 — Definir a estrutura (quantas campanhas, quantos ad groups)

**Regra: budget pequeno não pulveriza.** 1 campanha Search bem feita com poucos ad groups temáticos > 3 campanhas famintas de budget. Cada ad group compete pelo mesmo orçamento diário — dividir demais mata o algoritmo de dados suficientes por variante.

Heurística de split:
- **Branded sempre separado de non-branded** — CPC e intenção são completamente diferentes; misturar no mesmo ad group distorce o Quality Score médio.
- **1 ad group por tema/produto específico**, não por palavra-chave individual nem por "geral demais". Ex: "Cadeira Presidente" é um ad group; "Cadeira Presidente Fortaleza" não precisa ser outro — vira variação de keyword dentro do mesmo ad group.
- Budget mínimo saudável por campanha: se o budget diário total dividido pelo número de ad groups fica abaixo de ~3-5x o CPC médio esperado, tem ad group demais pro dinheiro disponível — cortar.

## Passo 2 — Settings de campanha (armadilhas conhecidas)

| Campo | Valor / regra | Por quê |
|---|---|---|
| **Status inicial** | `Pausada` | Nunca publica ativo — ver checklist final |
| **Geo target** | Definir o estado/cidade certo **na criação** — default do Editor/UI é país inteiro | Esquecer = queima budget fora do território atendido |
| **Networks** | Desmarcar **Search Partners** e **Display Network** — vêm marcados por padrão | Tráfego barato e de baixa qualidade, quase nunca converte no mesmo nível que Google Search |
| **Idioma** | Idioma do público-alvo, não assumir | — |
| **Bid strategy inicial** | **Manual CPC** ou **Maximize Clicks** com bid cap | Conta/campanha nova sem histórico de conversão não tem dado suficiente pra tCPA/tROAS aprenderem — sai caro e instável. Migrar pra automação **só depois de ≥15 conversões** na campanha (mínimo recomendado pelo Google pra sair da fase de aprendizado) |
| **Ad schedule** | 24h/7 dias inicialmente | Restringir cedo demais corta dado; reavaliar depois de 2-3 semanas com base em quando as conversões de fato acontecem |
| **Device adjustment** | Sem ajuste inicial | Reavaliar com dado real |

## Passo 3 — Ad groups

- Nome de cada ad group = tema específico, **documentado em `account-conventions.md` com grafia EXATA** (com/sem acento, maiúsculas). Isso importa de verdade no Passo 8 — nome divergente no CSV cria ad group novo vazio em vez de popular o existente.

## Passo 4 — Keywords

- **Não usar Broad match em budget pequeno.** Broad precisa de volume/dado pra o algoritmo aprender direito; em conta nova ele generaliza mal e gasta rápido em termos fora do tema.
- Default: **Phrase + Exact**. Broad só em ad group de teste isolado, com budget próprio e monitorado de perto.
- Fórmula de geração de keyword por ad group (adaptar à vertical):
  - `[produto]` exact
  - `"produto"` phrase
  - `"produto" + geo` phrase (se geo importa)
  - `"comprar" + produto` phrase / exact (bottom-funnel)
  - `"produto" + dor/atributo` phrase (ex: "confortável", "ergonômica")
- Evitar termo isolado super-amplo (ex: só `"cadeira de escritorio"` sem qualificador) a menos que seja intencional — se usar, marcar pra monitorar gasto de perto.

## Passo 5 — Negativas

- **Account-level:** herdar a lista de `account-conventions.md` (lista compartilhada, aplicada a todas as campanhas do cliente).
- **Campaign-level:** termos específicos do tema dessa campanha que não cabem na lista universal (ex: produto correlato mas diferente — "cadeira de rodas" numa campanha de cadeira de escritório).
- Regra de nível: quando em dúvida entre ad group / campaign / account, escolher o mais conservador (ver `search-term-methodology`).

## Passo 6 — RSAs (Responsive Search Ads)

Por ad group, 1 RSA inicial com o máximo de variação que o algoritmo puder testar (até 15 headlines de 30 caracteres, até 4 descriptions de 90 caracteres — usar pelo menos 8-10 headlines e as 4 descriptions).

Mix recomendado de headlines:
- Produto/tema (2-3): nome do produto, variações
- Geo (1-2): cidade/região, se relevante
- Dor/benefício (2-3): o que resolve
- Oferta/prova social (1-2): garantia, anos de mercado, clientes atendidos
- CTA (1-2): "Fale agora", "Peça pelo WhatsApp"

Descriptions: combinar produto + benefício + CTA + prova social em 2-4 variações, sempre dentro de 90 caracteres.

## Passo 7 — Extensions / Assets

- **Sitelinks:** mínimo 4, apontando pra seções relevantes do site (categorias, prova social, sobre).
- **Callouts:** 5-6, benefícios curtos (garantia, entrega, forma de pagamento, anos de mercado).
- **Structured snippets:** tipo relevante à vertical (ex: `Brands`, `Types`, `Services`) com os valores do catálogo.
- **Call extension:** **não usar** se o canal de conversão real é outro (ex: WhatsApp) — divide o caminho de conversão e some com dado de atribuição.
- **Lead form extension:** **não usar** se já existe um caminho de conversão definido (ex: WhatsApp) — mesmo motivo, evita duplicar/desviar o funil.
- **Location extension:** só ativar se houver endereço físico com Google Business Profile linkado.

## Passo 8 — Gerar o bundle e o plano

Produzir dois artefatos em `<Cliente>/campanhas/`:

1. **Documento do plano** — `0N-plano-<nome-da-campanha>.md`: TL;DR, blocker de tracking, estrutura proposta (settings, ad groups, keywords, negativas, RSAs, extensions), cronograma sugerido, e **pontos pendentes pro cliente confirmar** antes de subir. Isso é proposta — não aplicar sem aprovação (regra global do `CLAUDE.md`).
2. **Bundle de import** — `0N-import-bundle/`, um CSV por tipo de entidade:
   - `01-keywords.csv` — colunas: Campaign, Ad Group, Keyword, Criterion Type
   - `02-ads-rsa.csv` — colunas: Campaign, Ad Group, Headline 1..15, Description 1..4, Final URL
   - `03-sitelinks.csv`
   - `04-callouts.csv`

## Passo 9 — Apply

**Com MCP conectado:** aplicar as mutations (criar campanha → ad groups → keywords → ads → extensions → negativas) uma etapa por vez, sempre com a campanha nascendo `PAUSED`. Confirmar com o usuário antes de qualquer chamada de mutation (regra global).

**Sem MCP — Google Ads Editor (bulk import via CSV):**

1. Criar a(s) campanha(s) manualmente na UI do Editor primeiro (nome, budget, geo, networks, bid strategy — ver Passo 2). O Editor **não cria campanha via import de keywords/ads**, só popula entidades dentro de campanhas/ad groups que já existem.
2. Criar os ad groups manualmente também, com o nome **idêntico** ao que vai nos CSVs.
3. **Conta → Importar → Do arquivo** → importar `01-keywords.csv`. Conferir preview (contagem de keywords esperada) antes de confirmar.
4. Repetir pra `02-ads-rsa.csv`, `03-sitelinks.csv`, `04-callouts.csv`.
5. Negativas de **conta/lista compartilhada**: Biblioteca compartilhada → Listas de palavras-chave negativas → criar lista → colar termos (Ctrl+A/Ctrl+C do arquivo, colar na caixa "Fazer várias alterações" do Editor) → anexar a lista às campanhas.
6. Negativas de **campanha isolada** (raras — quando um termo bloqueia só uma campanha específica): adicionar **manualmente pela UI**, nunca por CSV bulk (ver armadilha #1 abaixo).
7. Revisar o painel "Gerenciar" — contagem de campanhas/ad groups/keywords/ads/extensions deve bater com o esperado. **Qualquer ad group vazio com erro é sinal de nome divergente entre CSV e Editor — corrigir antes de publicar.**
8. **Publicar** — Editor envia tudo pra conta como `PAUSADA`. Não ativar ainda.

### Armadilhas conhecidas do Google Ads Editor

1. **Negativas de campanha NÃO importam via CSV bulk.** Um CSV com negativas em nível de campanha (sem coluna "Ad group") é interpretado como **keyword positiva**, e o Editor cria um ad group vazio pra colocá-la — gera dezenas/centenas de erros em cascata. Sempre usar lista compartilhada (funciona via import) ou adicionar manualmente pela UI pras raras negativas de campanha isolada.
2. **CSV precisa de encoding UTF-8 com BOM.** Sem BOM, o Editor lê como Latin-1 no Windows e todo acento vira lixo (`ó` → `Ã³`). Salvar/gerar sempre como "UTF-8 with BOM" (em Python: prefixar o arquivo com `b'\xef\xbb\xbf'`).
3. **Nome de ad group no CSV precisa ser IDÊNTICO ao criado no Editor** — mesmo espaço extra ou acento diferente faz o Editor criar um ad group novo vazio em vez de popular o existente. Copiar o nome, nunca digitar de novo.
4. **"Importar do arquivo" aparece cinza/desabilitado** quando há mudanças pendentes não confirmadas — clicar **"Manter tudo"** na barra de revisão antes de tentar importar.
5. **Geo default é o país inteiro** — sempre definir o geo certo logo na criação da campanha, antes de qualquer outra coisa.
6. **Debug via DB local (Windows):** se o Editor travar ou o erro não for claro, é possível ler o banco SQLite local com o Editor **fechado**: `%LOCALAPPDATA%\Google\Google-AdWords-Editor\<versão>\ape_<CustomerID sem hífen>.db`. Tabelas úteis: `Campaign`, `AdGroup` (parentId & 0xFFFFFFFF = campaign localId), `Keyword` (criterionType: 1=Exact, 2=Phrase, 3=Broad), `Error`/`ErrorInfo`. Sempre copiar o `.db` pra outro lugar antes de abrir — nunca conectar no original.

## Passo 10 — Checklist final antes de ativar

Campanha sobe sempre `PAUSADA`. Antes de mudar pra `Ativa`, confirmar:

- [ ] Conversion tracking testado e disparando (ver Passo 0)
- [ ] Site em HTTPS
- [ ] Billing configurado na conta
- [ ] Lista de negativas account-level anexada
- [ ] Revisão humana do plano aprovada explicitamente pelo cliente/usuário

## Não fazer

- Não ativar campanha sem tracking confirmado — nunca, mesmo sob pressão de "subir logo".
- Não usar Broad match como default em conta sem histórico de conversão.
- Não gerar CSV de negativa de campanha pra import bulk no Editor — sempre falha (armadilha #1).
- Não pulverizar budget pequeno em muitas campanhas/ad groups — concentrar tema e dado.
- Não pular a etapa de nomear ad groups de forma idêntica entre Editor e CSV.
