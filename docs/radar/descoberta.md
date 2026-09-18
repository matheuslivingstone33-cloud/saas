> **ESTADO INTEGRADO NA VERSÃO PRINCIPAL — 15/09/2026**
>
> De 12 a 15/09 as rotinas trabalharam em cópias separadas e não enxergavam o
> trabalho umas das outras — a mesma correção chegou a ser feita quatro vezes.
> As correções abaixo foram escolhidas, testadas juntas e integradas no `main`.
> **Leia esta lista antes de agir: o que coincidir com ela já está resolvido e
> não deve ser refeito.** Os hashes citados são dos commits originais; no `main`
> eles têm hash novo, com a mesma mensagem.
>
> - **Recusa do provedor no meio do plano não derruba mais a rodada** (versão de 12/09, `dd5676a`). Pula a consulta recusada e só interrompe depois de **3 falhas seguidas**. A versão de 14/09 (`be0cb0c`) foi descartada: contava 3 falhas no total e abortaria rodadas saudáveis em planos de centenas de consultas. Emite `erro_busca` e `interrompido`, que a tela ao vivo já sabe rotular.
> - **UF do endereço real do Places** (versão de 15/09, `871ace8`). Só aceita sigla depois de `-` ou `,` e validada contra as 27 UFs; sem certeza, devolve `None`. A de 13/09 (`90b4338`) foi descartada por arriscar palpite: UF errada zera o enriquecimento, `None` só amplia a busca.
>
> O que vem abaixo é o diário da execução de 15/09, mantido como estava.

---

# Radar — Descoberta e Cérebro

> A rotina que cuida de `cerebro.py`, `descoberta.py`, `query_builder.py`,
> `scoring.py`, `google_places.py` e `anthropic_llm.py` escreve aqui.
>
> O objetivo dela é achar e fechar, **um por execução**, o que quebra quando a
> descoberta deixa de rodar em mock (10 empresas, formato limpo) e passa a falar
> com o Places de verdade (centenas, com paginação, campos ausentes, nomes
> sujos e rate limit). Sem ligar chave nenhuma e sem fazer requisição real.
>
> Cada execução: escolhe o maior risco que consegue fechar inteiro, escreve
> teste que falha antes e passa depois, deixa `pytest` e `ruff` verdes, e
> registra aqui o que fez, o que achou e não fez, e o que depende de decisão.

---

## Histórico de execuções

### 2026-09-18 — o raio da busca não tinha teto e derrubava a consulta no real

**Corrigido.** Em `google_places.py`, o `buscar` monta o `locationBias` com
`"radius": float(query.raio_m or 20_000)` — o raio ia **cru** para o Google. A
Places API (New) só aceita raio de círculo entre **0 e 50.000 m**; acima disso
responde **400 (INVALID_ARGUMENT)** e a consulta inteira falha.

Por que importa na virada: o raio vem do filtro do usuário (`raio_km`, em
`query_builder.py`: `int(raio * 1000)`) **sem nenhum teto**. Uma campanha com
"raio de 100 km" manda `raio_m=100000` — válido no mock (que **ignora** o raio),
mas 400 no real. E como o raio é o mesmo em todas as consultas do plano, o 400
se repete: a rodada bate em `BUSCAS_COM_ERRO_MAX` e para com `interrompido_por
_erro`, sem entregar nada — tudo por um limite que o `maxResultCount` já respeita
(`min(20, ...)`, na linha logo acima) e o raio não respeitava.

A correção grampeia na **fronteira com o Google** (não no QueryBuilder: o limite
é da API, não do domínio, e o DTO é agnóstico de provedor): `min(RAIO_MAX_M,
max(1.0, raio))`, com `RAIO_MAX_M = 50_000.0`. Raio válido (e o default de 20 km)
passa intacto; raio absurdo vira 50 km em vez de matar a rodada — resultado mais
amplo é melhor que resultado nenhum, o mesmo princípio do `_uf_do_endereco`
(UF nenhuma > UF errada).

Dois testes novos em `test_fase7_adaptadores_reais.py`: um com `raio_m=100_000`
que falhava (mandava 100.000 cru) e agora afirma 50.000 no corpo; outro com
`raio_m=15_000` provando que raio válido não é mexido. `pytest` (417 passa,
3 skip) e `ruff` verdes. Commit + push feitos.

---

### 2026-09-16 — um resultado sujo do Places derrubava a rodada inteira

**Corrigido.** `_para_dto` (em `google_places.py`) converte cada place cru do
Google num `PlaceResult`. Três campos não aguentavam o formato real:

- **`types: null` → `TypeError`.** `list(bruto.get("types", []))` só cai no
  default `[]` quando a chave está **ausente**. O Places real manda a chave
  **presente com valor `null`**, e `list(None)` estoura. Como isso acontece
  dentro do list comprehension de `buscar`, a resposta **inteira** morre — e a
  exceção não é nenhuma das que `executar_plano` intercepta
  (`RateLimited`/`UpstreamError`/`CircuitOpen`), então sobe, **aborta a rodada**
  e perde os leads já achados nas consultas anteriores mais o SKU já gasto. Um
  resultado sujo entre 20 não pode custar a rodada.
- **`id: null` / `displayName: null` → `ValidationError`.** `place_id` e `nome`
  são `str` **obrigatórios** no DTO. `bruto.get("id", "")` devolve `None` quando
  a chave vem com valor `null` (o default só vale para chave ausente), e
  `PlaceResult(place_id=None)` estoura na validação — o mesmo caminho de morte da
  resposta inteira.

A correção normaliza **ausente e nulo de uma vez** com `... or <default>` —
`bruto.get("types") or []`, `bruto.get("id") or ""` —, o mesmo padrão que
`location` e `displayName` já usavam (`or {}`). Um place degenerado (sem id nem
nome) vira strings vazias e o filtro B2B a jusante (`eh_empresa`) o descarta;
o que **não** pode é a conversão derrubar a resposta.

Dois testes novos, que falhavam com `TypeError` antes e passam depois: um place
`types: null` no meio de uma resposta boa (prova que os leads bons sobrevivem ao
sujo) e um place com id/displayName/types/location todos `null` (prova que não
vira `ValidationError`). Commit + push feitos. `pytest` (389 passa, 3 skip) e
`ruff` verdes.

> **Nota para a próxima execução:** o item 1 da fila abaixo ("uma consulta que
> falha derruba a rodada") **já está resolvido no `main`** — `executar_plano` já
> tem o try/except com `BUSCAS_COM_ERRO_MAX` (3 falhas seguidas) e emite
> `erro_busca`/`interrompido`. Marcado como integrado; não refazer.

---

### 2026-09-15 — a UF do endereço real quebrava o enriquecimento

**Corrigido.** `_uf_do_endereco` (em `descoberta.py`) tirava a UF pegando os dois
últimos caracteres do endereço. No mock isso funciona, porque o endereço termina
limpo na UF: *"...Fortaleza - CE"*. O Google real anexa CEP e país:
*"...Fortaleza - CE, 60150-160, Brasil"* — então a cauda virava **"il"** (de
"Brasil"), ou um pedaço do CEP.

Por que importa: a UF é usada para casar a empresa com a base da Receita, e o
enriquecimento **descarta** qualquer registro cuja UF não bata
(`registro.uf != uf`). Uma UF inventada como "IL" não bate com nada — então
**todo lead real** cairia em "sem enriquecimento" (sem CNPJ, sem porte, sem os
dados que alimentam o score), de forma silenciosa, no dia em que
`PLACES_MODE=real`. Uma UF errada é pior que UF nenhuma: nenhuma UF ainda casa
por nome.

A correção procura o padrão "Cidade - UF" e só aceita uma das 27 UFs reais; se
não achar, devolve `None` (busca sem filtro de UF). Teste novo cobre: formato
limpo do mock, formato real com CEP+país (em português e inglês), endereço que
termina em CEP, e endereço sem estado nenhum (não inventa UF a partir de
"Brasil"). Commit + push feitos. `pytest` (348 passa, 3 skip) e `ruff` verdes.

---

## Achado e NÃO corrigido — fila para as próximas execuções

> Ordem sugerida: do que mais quebra e é mais fácil de fechar, para o que
> depende de decisão. **Uma por execução.**

### 1. ~~Uma consulta que falha derruba a rodada inteira~~ — INTEGRADO no `main`
Já resolvido. `executar_plano` (em `descoberta.py`) envolve cada `buscar` num
try/except de `RateLimited`/`UpstreamError`/`CircuitOpen`, pula a consulta que
falhou preservando o que já foi achado, e só interrompe após
`BUSCAS_COM_ERRO_MAX` (3) falhas **seguidas**, emitindo `erro_busca` e
`interrompido`. O mecanismo de espera/retry/circuito continua no `HttpClient`
(outra rotina). **Não refazer.**

### 2. `_para_dto` sem id: dedup enfraquecido (o resto foi corrigido em 16/09)
O **crash** deste item foi fechado em 16/09 (ver histórico): `types`/`id`/
`displayName` nulos não derrubam mais a conversão. **Sobra a semântica do
dedup**, que é de menor severidade agora que não há mais crash:

- Um resultado sem `id` vira `place_id=""` (string vazia, *falsy*), e
  `encontrar_duplicado` faz `if place_id:` — então o dedup por `place_id` some
  para esse registro. Se ele **também** não tiver CNPJ, telefone nem domínio,
  dois desses nunca deduplicam entre si.

**Por que NÃO despachei "descartar resultado sem id":** parece a saída óbvia,
mas está errada. Um place sem `id` mas **com telefone ou site** é um lead B2B
de verdade e ainda deduplica por telefone/domínio — descartá-lo perde lead bom.
O caso realmente órfão (sem id **e** sem nenhum outro identificador) é raro e o
filtro B2B (`eh_empresa`) já derruba o que vier sem nome. A escolha entre
"descartar id-less" e "aceitar dedup fraco no caso órfão" é um **trade-off de
qualidade de dado, não de crash** — deixei para uma execução futura ou decisão,
com esta análise, em vez de despachar o palpite fácil que perde leads.

### 3. `includedType` inválido derruba a consulta inteira — `google_places.py`
`corpo["includedType"] = query.tipos_incluidos[0]`. A Places API (New) só aceita
tipos de uma tabela fechada; um tipo fora dela responde **400** e a consulta
inteira falha. Hoje esse valor vem do filtro do usuário sem validação. No mock
isso nunca é exercido. Fechável validando contra o conjunto de tipos conhecidos
(ou tolerando o 400 sem o filtro), mas precisa da lista de tipos válidos da
Google.

### 4. Nomes sujos afetam o match na Receita — `descoberta.py` / `google_places.py`
`nome` vem de `displayName.text` e desce cru para o `enriquecer` (que busca por
nome na base da Receita). Nomes reais vêm com espaço extra, caixa alta, emoji,
sufixo de unidade. A tokenização já normaliza bastante, então o risco é de
**qualidade** do casamento, não de quebra. Observação, não urgência — medir
antes de mexer.

### 5. `places` no topo da resposta com valor `null` — `google_places.py` (baixa)
`dados.get("places", [])` em `buscar` cai no default `[]` só quando a chave está
**ausente**. É exatamente o padrão "chave presente com valor `null`" que já
derrubava os campos internos (corrigido em 16/09 com `... or <default>`): se o
Google mandar `"places": null`, `list()` sobre `None` no list comprehension
estoura `TypeError` e aborta a rodada. **Não corrigido nesta execução (uma por
vez).** Severidade baixa: a doc do Text Search (New) diz que resultado vazio vem
como `{}` (chave omitida), não `null` — então é seguro por hoje, mas frágil pela
mesma razão dos campos internos. Fecha trocando por `dados.get("places") or []`
(e o mesmo para `nextPageToken`, já tolerante). Sem decisão, sem dependência.

---

## Precisa de decisão humana — a rotina NÃO decide

### Paginação: quantas páginas por consulta e quanto gastar
Este é o maior buraco funcional da virada, mas o miolo dele é **custo**, então
fica aqui. Hoje `executar_plano` consome **só a primeira página** de cada
consulta e **ignora `resposta.proximo_token`**. No mock isso não aparece: o mock
devolve tudo de uma vez e `proximo_token` é sempre `None`. No real, o Places
limita `maxResultCount` a **20 por requisição** e devolve `nextPageToken` para o
resto — ou seja, **centenas de empresas ficam atrás da paginação e nunca são
buscadas**, mesmo com a região cheia.

A parte de código (encadear `proximo_token` → `PlacesQuery.page_token` na próxima
chamada) é simples e está pronta para ser ligada. O que **falta decidir** é o
limite: **cada página é um SKU cobrado do Google**, então "quantas páginas por
consulta" e "quanto uma campanha pode gastar buscando" é decisão de preço/produto
— exatamente o tipo de coisa que esta rotina não decide sozinha. Sem esse teto,
ligar paginação troca "traz de menos" por "gasta de mais". **Decidir o teto,
depois a rotina liga.**

### Falha parcial: entregar o que achou, ou falhar a rodada?
Ligado ao item 1 acima. Quando uma consulta falha no meio de uma rodada real, o
produto deve **entregar os leads já encontrados** (resultado parcial, com aviso
na tela) ou **falhar a rodada inteira** e pedir para tentar de novo? A resposta
muda o que o usuário vê e o que ele espera. É julgamento de UX/produto — a rotina
trata a robustez técnica (não derrubar a rodada), mas o comportamento visível
precisa ser escolhido.

> Fora do escopo desta rotina, já registrado no HANDOFF (§0.2): **ligar os
> provedores reais (Fase 7)** exige chave e cartão — decisão humana. Esta rotina
> prepara a virada; não a executa.
