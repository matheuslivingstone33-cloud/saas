# Declaração de uso de Inteligência Artificial

*Prospector AI — versão 1.0*

## O que é automatizado

Este produto usa um agente de inteligência artificial para:

1. **Interpretar** o serviço que o prestador descreve em texto livre;
2. **Selecionar** ramos de atividade (CNAE) que costumam consumir esse serviço;
3. **Buscar** empresas desses ramos via API oficial do Google Places;
4. **Pontuar** cada empresa por aderência ao serviço;
5. **Redigir** a mensagem de primeiro contato.

## O que NÃO é automatizado

- Não há decisão automatizada que produza efeito jurídico ou afete
  significativamente uma pessoa natural (LGPD, art. 20).
- O agente não fecha negócio, não assina, não cobra e não altera contrato.
- No **modo assistido**, nenhuma mensagem sai sem aprovação humana explícita.

## Declaração ao destinatário

Toda mensagem enviada carrega, no corpo, a frase:

> *"Esta mensagem foi redigida por um agente de inteligência artificial a
> serviço de [empresa]. Responda a este e-mail para falar com uma pessoa."*

Isso não é rodapé escondido: é parte do corpo da mensagem, e responder ao e-mail
coloca o destinatário em contato com uma pessoa.

## Direito à explicação

Toda decisão do agente é registrada e pode ser consultada:

- **por que este ramo foi escolhido** — `GET /v1/cerebro/expandir` devolve os
  CNAEs, os pesos, a distância semântica e a justificativa em texto;
- **por que este lead foi priorizado** — cada lead guarda `score_breakdown` com
  cada componente, seu peso e sua contribuição em pontos;
- **de onde veio cada dado** — cada lead guarda `provenance` campo a campo;
- **o que o agente fez e quando** — a trilha de auditoria registra cada decisão
  de IA como evento `decisao_ia`, encadeado por hash e imutável.

## Supervisão humana

| Nível de autonomia | Quem decide o envio |
|---|---|
| **Assistido** | Uma pessoa aprova cada mensagem antes do disparo |
| **Automático** | O agente dispara, dentro de tetos diários, com opt-out e auditoria |

O nível é escolhido pelo cliente, pode ser trocado a qualquer momento, e a troca
é registrada na auditoria como uma transição de estado da assinatura.

## Limites assumidos

- O agente pode errar ao classificar um ramo. Por isso o score é explicável e
  revisável, e o modo assistido existe.
- O texto gerado é uma apresentação comercial, não uma promessa contratual.
- Sinais de intenção vindos de busca web são indícios públicos, não verdades.

## Contato

Dúvidas sobre o uso de IA neste produto: **privacidade@prospector.local**
