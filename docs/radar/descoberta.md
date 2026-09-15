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

### 1. Uma consulta que falha derruba a rodada inteira — `descoberta.py`
`executar_plano` chama `self.portas.places.buscar(consulta)` **sem try/except**.
No mock nenhuma consulta falha. No real, uma consulta pode estourar por rate
limit persistente, 5xx transitório ou circuito aberto — e a exceção sobe,
abortando a descoberta e **perdendo os leads já achados** nas consultas
anteriores daquela rodada. Um `429` numa consulta não deveria matar a rodada
toda.

Pronto para fechar por uma rotina: envolver cada consulta, registrar a falha,
seguir para a próxima e devolver o resultado parcial. **Atenção ao limite de
escopo:** o *mecanismo* de espera/retry/circuito vive no `HttpClient`
(`app/core/http_client.py`), que é de **outra rotina** — aqui trata-se só de não
deixar uma consulta que falhou levar a rodada junto.

### 2. `_para_dto` do Places real não aguenta campo ausente/nulo — `google_places.py`
Dois furos que só aparecem com dado real:

- **`types` nulo estoura.** `list(bruto.get("types", []))` só usa o `[]` quando a
  chave está **ausente**. Se a API mandar `"types": null` (chave presente, valor
  nulo), vira `list(None)` → `TypeError`, e a conversão do resultado quebra.
  Repare que `location` já se protege com `or {}`, mas `types` não — é a mesma
  armadilha, tratada num lugar e não no outro.
- **`id` ausente vira `place_id` vazio.** `place_id=bruto.get("id", "")`. Um
  `place_id` vazio é *falsy*, então o dedup por `place_id` some
  (`encontrar_duplicado` faz `if place_id:`), e resultados sem id nem outro
  identificador (CNPJ/telefone/domínio) passam a nunca deduplicar entre si.

Pronto para fechar: normalizar os campos na entrada (tratar nulo como ausente;
decidir descartar resultado sem `id` em vez de criar lead sem identificador).

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
