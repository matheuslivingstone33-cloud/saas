# HANDOFF — Prospector AI

> **Leia isto primeiro ao abrir uma conversa nova.** Este arquivo é a memória do
> projeto: o que estamos construindo, por quê, o que já está pronto, o que falta
> e onde exatamente paramos.
>
> **Regra:** quem trabalhar aqui atualiza este arquivo ao terminar cada etapa.
> Um handoff desatualizado é pior que nenhum, porque leva a decisão errada com
> ar de confiança.

**Última atualização:** 2026-08-31 · Etapa 1 concluída

---

## 1. O que é o produto

SaaS que **descobre, qualifica e conversa** com os clientes ideais de um
prestador de serviço. 100% B2B.

O pulo do gato: o cliente descreve o que ele **faz** ("manutenção de
ar-condicionado") e o sistema encontra quem **consome** isso (supermercado com
câmara fria, hotel, clínica) — não quem faz a mesma coisa. Concorrente é
descartado explicitamente.

**Público:** prestador de serviço pequeno e médio no Brasil — refrigerista,
eletricista, empresa de manutenção predial, engenheiro.

---

## 2. Visão de produto (definida com o Aislan em 30/08/2026)

A estrutura que estamos perseguindo, em ordem da jornada do usuário:

### 2.1 Landing page
Primeira visão do negócio. Tem que passar **alto valor** — parecer algo que vai
impulsionar as vendas de verdade. Dois botões:

- **"Usar de forma gratuita"** → leva ao onboarding por chat
- **Suporte** → WhatsApp com IA (ver 2.5)

### 2.2 Onboarding por chat com IA
**Substitui o formulário.** Em vez de "escolha seu serviço e localização":

- **H1:** "Me conte sobre sua empresa"
- **P:** "precisamos dessas informações para encontrar os melhores clientes para você"
- Abaixo, um chat com a IA.

Roteiro da conversa:
1. **Autônomo ou empresa?** — essa pergunta é triagem, não formalidade: o MVP é
   B2B e não prospecta PF desconhecida.
2. Se **autônomo**: "me conta em uma ou duas linhas o que o seu negócio faz"
3. Se **empresa**: pergunta o nome, depois "me conta em uma ou duas linhas o que
   a {nome_empresa} faz?"
4. A IA configura de forma imersiva os leads que vai procurar, podendo dar dicas
   básicas sobre o negócio.

O usuário fica nessa tela até o negócio estar configurado. Só então avança.

### 2.3 Descoberta
Resultado da busca. Referência visual do protótipo:

> **"Encontramos 42 empresas precisando de Manutenção de ar-condicionado na sua região."**
> Foz do Iguaçu – PR · Dados públicos de empresas · LGPD
>
> As 3 melhores oportunidades para você — *39 empresas restantes disponíveis no plano PRO*
>
> Cartões com: nome, ramo, **score %**, **INSIGHT DA IA** ("Possui câmara fria de
> grande porte"), faixa de funcionários, bairro, botão **"Iniciar Abordagem com IA"**

### 2.4 Conversas
A tela onde o produto entrega a promessa. Lista de conversas à esquerda com
estado (**Em negociação**, **Aguardando resposta**, **Primeiro contato enviado**),
thread à direita, alternância **Abordagem IA / Manual**, botões **"Rodar ao vivo"**
e **"Piloto automático"**.

Quando o lead esquenta, aparece a faixa de conversão:
> 🔥 O lead está aquecido e quer fechar! O Prospector AI já preparou a proposta.
> **[Assinar PRO e Agendar Reunião Automaticamente]**
> *Assumir chat manualmente de forma gratuita*

### 2.5 Suporte por WhatsApp com IA
Diferencial: o suporte é feito por IA no WhatsApp, mandando áudio, soando
natural — para o cliente **ver a qualidade da nossa IA na prática**.

> ⚠️ **Restrição que não é negociável:** a IA pode soar natural, mandar áudio e
> ter jeito de gente, mas **precisa dizer que é IA**. Está no Marco da IA e no
> nosso guardrail. Na prática é uma linha na primeira mensagem — e joga a favor:
> mostra a qualidade da automação em vez de escondê-la.
>
> Isso é **inbound** (o cliente procurou a gente), então não esbarra na proibição
> de WhatsApp frio.

### 2.6 Planos
- **Grátis:** 10 leads por mês, sendo **3 com automação gratuita**
- **PRO:** desbloqueia o restante ("39 empresas restantes disponíveis no plano PRO")

---

## 3. Estado atual

### 3.1 O que está pronto e testado

Fases 0 a 7 concluídas (detalhe em [PROGRESS.md](PROGRESS.md)). Em resumo:

| Motor | O que faz | Estado |
|---|---|---|
| **Cérebro** (Motor 2) | serviço livre → ramos que CONSOMEM (CNAE), com peso e exclusão de concorrente | ✅ |
| **Descoberta** (Motor 1) | QueryBuilder → Places → Receita Federal → dedup | ✅ |
| **Abordagem** (Motor 3) | personalização + envio com limites, opt-out e autonomia | ✅ |
| **Conversa** (Motor 4) | receber resposta, negociar | ❌ **não existe** |

Também prontos: compliance LGPD completo (LIA, opt-out de 1 clique, direitos do
titular, retenção, auditoria encadeada por hash), créditos e planos com teto e
bloqueio, custo em dois baldes que nunca se misturam (1 = dados, 2 = IA), painel
de margem, adaptadores reais dos provedores, execução ao vivo por SSE, revisão
por teclado, paleta de comandos (Ctrl+K), tema claro/escuro.

**188 testes verdes · lint limpo.**

### 3.2 A lacuna que importa

O sistema hoje é **de mão única**: gera a mensagem, envia, registra o status. Não
existe recebimento de resposta, thread de conversa, nem IA respondendo.

Os estados `respondido` e `convertido` **existem na máquina de estados do lead e
nunca acontecem** — nada os preenche. É esse buraco que o Motor 4 fecha.

---

## 4. Plano de execução

Decidido em 31/08/2026: fazer **os três**, um por vez, testando cada etapa, na
ordem da jornada do usuário.

| # | Etapa | Estado |
|---|---|---|
| 0 | **Este handoff** | ✅ feito |
| 1 | **Navegação nova** — Busca / Descoberta / Conversas | ✅ feito |
| 2 | **Landing page + onboarding por chat** | ⏳ próximo |
| 3 | **Conversas / Motor 4** — o motor de conversa | ⏸️ aguardando |

### O que a Etapa 1 entregou

- **Busca** (`pages/Busca.tsx`) — "Quem você quer atender hoje?": serviço + região,
  com exemplos clicáveis. Cria a campanha e leva direto para a Descoberta.
- **Descoberta** (`pages/Descoberta.tsx`) — "Encontramos N empresas precisando de
  X na sua região", as 3 melhores em cartões com score, **insight da IA** e
  "por quê?"; diz quantas ficaram para o plano PRO. Abre a execução ao vivo
  sozinha quando a campanha nunca rodou.
- **Conversas** (`pages/Conversas.tsx`) — lista com estado por conversa, thread à
  direita, revisão por teclado. Diz na cara que ainda é de mão única.
- **Menu da conta** — Painel, Créditos e Conformidade saíram do topo. A barra
  principal tem só os três passos da jornada.
- **`scripts/limpar_demo.py`** — devolve o banco ao estado de seed preservando
  usuário, CNAEs e **opt-outs** (apagar opt-out para limpar demo seria voltar a
  contatar quem pediu para não ser contatado).

### Dois defeitos reais corrigidos no caminho

- **Dedup bem-sucedido parecia falha.** Quando a busca encontrava empresas mas
  todas já estavam na base, a tela dizia "Nenhuma empresa ainda" — idêntico a
  não ter achado nada. São resultados opostos. Agora a tela distingue os dois e
  aponta para Conversas.
- **Insight da IA repetia em todo cartão.** Ele escolhia o fator de maior
  pontuação, e "tem contato comercial" (20 pts) ganhava sempre — mas todo lead
  que chega ali tem contato: é pré-requisito, não insight. Agora a ordem é por
  poder de distinção, com o ramo na frente ("Hotéis — ramo que consome esse
  serviço de forma recorrente").

**Ordem escolhida e por quê:** vai do mais barato e visível ao mais complexo.
A casca primeiro dá lugar para o Motor 4 morar e deixa o app parecido com o
protótipo cedo. O Motor 4 é o mais pesado e vem por último, com o resto estável.

### Regras de trabalho combinadas
- **Uma etapa por vez**, com teste a cada coisa feita.
- **Este arquivo é atualizado ao fim de cada etapa** — é o que permite continuar
  numa conversa nova sem perder contexto.
- Nada de chave de API: tudo continua rodando em mock.

---

## 5. Como rodar

O backend serve a interface compilada — **um processo só**.

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir: **http://localhost:8000**

Se mexer no frontend, recompile:

```bash
cd frontend && npm run build
```

Testes e lint:

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests -q && .venv/Scripts/ruff.exe check app tests scripts alembic
```

> **Esta máquina não tem Docker** e vive apertada de memória. O `docker-compose.yml`
> está pronto e correto, mas não dá para validar aqui. O servidor de
> desenvolvimento do Vite (porta 5173) consome centenas de MB e morre quando a
> RAM aperta — por isso o backend serve o `dist/`.

---

## 6. Guardrails que não se negociam

Valem para qualquer etapa, sempre:

1. **Nunca** fazer scraping de Google Maps/Earth. Descoberta só via Places API oficial.
2. **Nunca** disparar WhatsApp frio para pessoa física. Canal padrão é e-mail;
   WhatsApp preferencialmente inbound.
3. **MVP é B2B.** Sem prospecção ativa a PF desconhecida.
4. **Compliance é arquitetura, não item opcional.** Toda mensagem declara ser IA
   e leva link de descadastro. Opt-out é consultado antes de todo envio.
5. **Todo custo externo vira `cost_event`** em dois baldes que nunca se misturam:
   balde 1 = dados (Places, Receita, e-mail), balde 2 = IA (LLM, busca).
6. **Fases 0–6 rodam sem nenhuma chave.** Provedor externo só entra atrás de
   porta com mock; um flag `*_MODE=real` por provedor faz a virada.
7. **Acrescentar valor a enum exige migration.** Já quebrou uma vez: a Fase 4
   adicionou eventos ao `TipoEvento` e só ensinou o PostgreSQL; o SQLite quebrou
   na hora de gerar a LIA. Há teste fixando isso.

---

## 7. Armadilhas já pagas (não repetir)

- **SSE que reexecuta a campanha.** O `EventSource` reconecta sozinho quando o
  servidor fecha o fluxo. Como abrir a rota EXECUTA a campanha, cada reconexão
  virava uma execução nova — um clique gerou **256 execuções e 1020 consultas ao
  Places**. Defesas: o servidor recusa execução concorrente (409), manda
  `retry: 24h`, e o cliente fecha explicitamente.
- **Callback em dependência de efeito.** `aoTerminar` no array de dependências
  fazia o efeito reexecutar a cada renderização — e reabrir o fluxo custa
  execução paga. Vive numa `ref`.
- **Hook dentro de `useState`.** `useState(useAbertura)` faz o hook rodar só na
  primeira renderização e quebra a ordem dos hooks depois.
- **Coringa de SPA engolindo rota de API.** `/v1/` com erro de digitação
  devolveria HTML com status 200 — falha silenciosa. Há lista de prefixos
  reservados e teste.
- **`--reload` do uvicorn** dobra o consumo de memória e já deixou o processo
  em estado onde toda requisição virava 500.
- **Tela em branco com 500 em todo módulo** = falta de RAM. O Vite perde o
  processo filho do esbuild e responde `The service is no longer running`.

---

## 8. Onde as coisas moram

```
backend/app/
  services/cerebro.py       Motor 2 — serviço → ramos que consomem
  services/descoberta.py    Motor 1 — QueryBuilder + Places + Receita + dedup
  services/envio.py         Motor 3 — personalização + SendService
  services/scoring.py       score explicável, com pesos aprendidos
  services/compliance.py    LIA, opt-out, direitos do titular, retenção
  services/observador.py    eventos da execução ao vivo
  domain/lead_state.py      máquina de estados do lead
  adapters/mock/            todos os provedores em mock (sem chave)
  adapters/real/            adaptadores reais (Fase 7)
  api/estatico.py           serve a interface compilada

frontend/src/
  App.tsx                   navegação, tema, paleta
  pages/                    Painel, Campanhas, Créditos, Conformidade, Onboarding
  components/ExecucaoAoVivo.tsx   o SSE narrando o pipeline
  components/Revisao.tsx          triagem por teclado (A/R/E)
  components/Paleta.tsx           Ctrl+K
```

Documentos: [README.md](README.md) · [PROGRESS.md](PROGRESS.md) ·
[docs/ARQUITETURA.md](docs/ARQUITETURA.md) · [docs/RUNBOOK-FASE7.md](docs/RUNBOOK-FASE7.md)

---

## 9. Pendências conhecidas

- **`pages/Campanhas.tsx` ficou órfão.** A tela antiga foi substituída por
  Busca + Descoberta + Conversas e não é mais importada. Ainda está no
  repositório caso algo dela precise ser resgatado; apagar quando a Etapa 3
  estabilizar.
- **Chaves de API.** Nenhum provedor real ligado. O roteiro da virada está em
  [docs/RUNBOOK-FASE7.md](docs/RUNBOOK-FASE7.md): um provedor por vez.
- **Autenticação.** Não existe login: o usuário vem do header `X-User-Email` com
  fallback no usuário de seed. É dev-only e precisa virar JWT antes de qualquer
  exposição pública.
