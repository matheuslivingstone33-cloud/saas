import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type Cadencia,
  type EstadoCadencia,
  type Lead,
  type Mensagem,
  type NivelAutonomia,
} from "../lib/api";
import { EXPO } from "../components/movimento";
import { Aviso, Badge, Botao, Carregando, Vazio } from "../components/ui";
import Revisao from "../components/Revisao";
import ExplicacaoLead from "../components/ExplicacaoLead";
import SimularResposta from "../components/SimularResposta";

/**
 * Conversas — onde a abordagem vira negocio.
 *
 * Com o Motor 4, a thread e de DUAS PONTAS: o que saiu e o que o lead
 * respondeu, na ordem. O estado da conversa sai do que realmente aconteceu.
 *
 * Quando o lead esquenta, a tela sugere o proximo passo — mas quem decide
 * fechar e a pessoa, nao o agente.
 */

type Conversa = {
  lead: Lead;
  mensagens: Mensagem[];
  ultima: Mensagem | null;
  estado: EstadoConversa;
};

type EstadoConversa =
  | "aguardando_sua_aprovacao"
  | "primeiro_contato_enviado"
  | "aguardando_resposta"
  | "em_negociacao"
  | "encerrada";

const ROTULO: Record<EstadoConversa, string> = {
  aguardando_sua_aprovacao: "Aguardando sua aprovação",
  primeiro_contato_enviado: "Primeiro contato enviado",
  aguardando_resposta: "Aguardando resposta",
  em_negociacao: "Em negociação",
  encerrada: "Encerrada",
};

const TOM: Record<EstadoConversa, string> = {
  aguardando_sua_aprovacao: "atencao",
  primeiro_contato_enviado: "neutro",
  aguardando_resposta: "acento",
  em_negociacao: "positivo",
  encerrada: "neutro",
};

export default function Conversas({ nivel }: { nivel: NivelAutonomia }) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [revisando, setRevisando] = useState(false);
  const [detalhe, setDetalhe] = useState<Lead | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [simulando, setSimulando] = useState<Lead | null>(null);
  const [cadencia, setCadencia] = useState<Cadencia | null>(null);
  const [compondo, setCompondo] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [l, m, c] = await Promise.all([
        api.leads(),
        api.mensagens(),
        api.cadencia(),
      ]);
      setLeads(l.itens);
      setMensagens(m.itens);
      setCadencia(c);
    } catch (e) {
      setErro(String(e));
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const conversas = useMemo<Conversa[]>(() => {
    const porLead = new Map<string, Mensagem[]>();
    for (const m of mensagens) {
      if (!m.lead_id) continue;
      const lista = porLead.get(m.lead_id) ?? [];
      lista.push(m);
      porLead.set(m.lead_id, lista);
    }

    return [...porLead.entries()]
      .map(([leadId, msgs]): Conversa | null => {
        const lead = leads.find((l) => l.id === leadId);
        if (!lead) return null;
        // Ordem da CONVERSA, nao do relogio: pergunta e replica do mesmo turno
        // nascem com carimbo identico e a thread saia invertida.
        const ordenadas = [...msgs].sort(
          (a, b) =>
            a.ordem - b.ordem ||
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
        );
        return {
          lead,
          mensagens: ordenadas,
          ultima: ordenadas[ordenadas.length - 1] ?? null,
          estado: estadoDa(lead, ordenadas),
        };
      })
      .filter((c): c is Conversa => c !== null)
      .sort((a, b) => {
        const ta = a.ultima ? new Date(a.ultima.created_at).getTime() : 0;
        const tb = b.ultima ? new Date(b.ultima.created_at).getTime() : 0;
        return tb - ta;
      });
  }, [leads, mensagens]);

  useEffect(() => {
    if (!selecionada && conversas.length > 0) setSelecionada(conversas[0].lead.id);
  }, [conversas, selecionada]);

  // Trocar de conversa fecha a caixa: um rascunho na tela de outro lead e o
  // jeito mais facil de mandar a mensagem certa para a empresa errada.
  useEffect(() => {
    setCompondo(false);
  }, [selecionada]);

  const atual = conversas.find((c) => c.lead.id === selecionada) ?? null;
  const pendentes = mensagens.filter((m) => m.status === "aguardando_aprovacao");

  async function decidir(mensagemId: string, aprovar: boolean) {
    setOcupado(true);
    setErro(null);
    try {
      if (aprovar) await api.aprovar(mensagemId);
      else await api.rejeitar(mensagemId);
      await carregar();
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  async function rodarCadencia() {
    setOcupado(true);
    setErro(null);
    try {
      // `forcar` pula a espera de 3 dias — e so ela. Opt-out, resposta do
      // lead e campanha pausada continuam segurando o toque.
      await api.rodarCadencia(true);
      await carregar();
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  async function enviarManual(texto: string) {
    if (!atual) return;
    setOcupado(true);
    setErro(null);
    try {
      await api.responder(atual.lead.id, texto);
      setCompondo(false);
      await carregar();
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  async function devolverParaIA() {
    if (!atual) return;
    setOcupado(true);
    setErro(null);
    try {
      await api.devolverParaIA(atual.lead.id);
      await carregar();
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  if (carregando) return <Carregando />;

  if (conversas.length === 0) {
    return (
      <Vazio>
        Nenhuma conversa ainda. Vá em <strong>Descoberta</strong> e clique em
        "Iniciar abordagem com IA" numa das empresas encontradas.
      </Vazio>
    );
  }

  return (
    <div>
      {erro && (
        <div className="mb-4">
          <Aviso tom="erro">{erro}</Aviso>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[19rem_1fr]">
        {/* Lista de conversas */}
        <aside className="realce-topo overflow-hidden rounded-2xl border border-borda bg-superficie">
          <header className="flex items-center justify-between gap-2 border-b border-borda px-4 py-3">
            <h2 className="text-sm font-semibold text-texto">Suas conversas</h2>
            <span className="num text-xs text-texto-fraco">{conversas.length}</span>
          </header>

          {pendentes.length > 0 && (
            <div className="border-b border-borda p-3">
              <Botao tamanho="sm" onClick={() => setRevisando(true)} className="w-full">
                revisar {pendentes.length} pendente{pendentes.length === 1 ? "" : "s"}
              </Botao>
            </div>
          )}

          {cadencia !== null && cadencia.devidos > 0 && (
            <div className="border-b border-borda p-3">
              <Botao
                tamanho="sm"
                variante="secundario"
                disabled={ocupado}
                onClick={() => void rodarCadencia()}
                className="w-full"
              >
                enviar {cadencia.devidos} toque{cadencia.devidos === 1 ? "" : "s"} em atraso
              </Botao>
            </div>
          )}

          <ul className="max-h-[32rem] divide-y divide-borda overflow-y-auto">
            {conversas.map((c) => {
              const ativa = c.lead.id === selecionada;
              const nome = c.lead.razao_social ?? c.lead.nome_fantasia ?? "Empresa";
              return (
                <li key={c.lead.id}>
                  <button
                    onClick={() => setSelecionada(c.lead.id)}
                    className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors ${
                      ativa ? "bg-marca-fraca" : "hover:bg-superficie-2"
                    }`}
                  >
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-superficie-3 text-[10px] font-semibold text-texto-medio">
                      {iniciaisDe(nome)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-texto">{nome}</span>
                      <span className="block truncate text-xs text-texto-fraco">
                        {c.ultima?.corpo.split("\n")[0] ?? "sem mensagem"}
                      </span>
                      <span className="mt-1.5 inline-flex">
                        <Badge tom={TOM[c.estado]} ponto>
                          {ROTULO[c.estado]}
                        </Badge>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        {/* Thread */}
        <section className="realce-topo flex min-h-[28rem] flex-col overflow-hidden rounded-2xl border border-borda bg-superficie">
          {atual === null ? (
            <Vazio>Escolha uma conversa à esquerda.</Vazio>
          ) : (
            <>
              <header className="flex flex-wrap items-center gap-3 border-b border-borda px-5 py-3.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-marca-fraca text-xs font-semibold text-marca">
                  {iniciaisDe(atual.lead.razao_social ?? atual.lead.nome_fantasia ?? "")}
                </span>
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold text-texto">
                    {atual.lead.razao_social ?? atual.lead.nome_fantasia}
                  </h2>
                  <div className="flex items-center gap-2">
                    <Badge tom={TOM[atual.estado]} ponto>
                      {ROTULO[atual.estado]}
                    </Badge>
                    <span className="num text-xs text-texto-fraco">
                      score {Number(atual.lead.score).toFixed(0)}
                    </span>
                  </div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <Badge tom={nivel === "automatico" ? "marca" : "acento"}>
                    {nivel === "automatico" ? "piloto automático" : "assistido"}
                  </Badge>
                  <Botao variante="fantasma" tamanho="sm" onClick={() => setDetalhe(atual.lead)}>
                    por quê?
                  </Botao>
                </div>
              </header>

              <div className="flex-1 space-y-3 overflow-y-auto p-5">
                <AnimatePresence initial={false}>
                  {atual.mensagens.map((m) => (
                    <Balao key={m.id} mensagem={m} aoDecidir={decidir} ocupado={ocupado} />
                  ))}
                </AnimatePresence>
              </div>

              <footer className="border-t border-borda bg-superficie-2 px-5 py-3">
                {compondo ? (
                  <Compositor
                    lead={atual.lead}
                    ocupado={ocupado}
                    aoCancelar={() => setCompondo(false)}
                    aoEnviar={(texto) => void enviarManual(texto)}
                  />
                ) : (
                  <RodapeDaConversa
                    conversa={atual}
                    cadencia={cadencia}
                    estadoCadencia={
                      cadencia?.pendentes.find((p) => p.lead_id === atual.lead.id) ?? null
                    }
                    ocupado={ocupado}
                    aoSimular={() => setSimulando(atual.lead)}
                    aoRodarCadencia={() => void rodarCadencia()}
                    aoEscrever={() => setCompondo(true)}
                    aoDevolver={() => void devolverParaIA()}
                  />
                )}
              </footer>
            </>
          )}
        </section>
      </div>

      {detalhe && <ExplicacaoLead lead={detalhe} aoFechar={() => setDetalhe(null)} />}

      <AnimatePresence>
        {simulando && (
          <SimularResposta
            lead={simulando}
            aoFechar={() => setSimulando(null)}
            aoResponder={() => void carregar()}
          />
        )}
        {revisando && (
          <Revisao
            mensagens={mensagens}
            leads={leads}
            aoFechar={() => setRevisando(false)}
            aoDecidir={() => void carregar()}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * O rodape responde "e agora?" — e a resposta muda conforme a conversa.
 *
 * Sao quatro situacoes distintas, e trata-las como duas produzia texto errado:
 * depois que o lead respondia, o rodape continuava dizendo "aguardando o lead
 * responder".
 */
function RodapeDaConversa({
  conversa,
  cadencia,
  estadoCadencia,
  ocupado,
  aoSimular,
  aoRodarCadencia,
  aoEscrever,
  aoDevolver,
}: {
  conversa: Conversa;
  cadencia: Cadencia | null;
  estadoCadencia: EstadoCadencia | null;
  ocupado: boolean;
  aoSimular: () => void;
  aoRodarCadencia: () => void;
  aoEscrever: () => void;
  aoDevolver: () => void;
}) {
  const temResposta = conversa.mensagens.some((m) => m.direcao === "entrada");
  const pendente = conversa.mensagens.some((m) => m.status === "aguardando_aprovacao");
  const abordado = foiAbordado(conversa.mensagens);

  // Conversa assumida vem antes de tudo: enquanto ela valer, o agente esta
  // calado, e prometer que ele responde seria mentira.
  if (conversa.lead.assumido_em !== null) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-[16rem] flex-1 text-xs text-texto-fraco">
          <span className="font-medium text-texto-medio">Você assumiu esta conversa.</span>{" "}
          O agente não escreve mais aqui — nem toque de cadência, nem réplica.
        </p>
        <Botao tamanho="sm" disabled={ocupado} onClick={aoEscrever}>
          escrever
        </Botao>
        <Botao variante="fantasma" tamanho="sm" disabled={ocupado} onClick={aoDevolver}>
          devolver para a IA
        </Botao>
      </div>
    );
  }

  if (conversa.estado === "em_negociacao") {
    return <FaixaLeadQuente lead={conversa.lead} aoAssumir={aoEscrever} />;
  }

  if (temResposta && pendente) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-[16rem] flex-1 text-xs text-texto-fraco">
          <span className="font-medium text-texto-medio">O lead respondeu.</span> O agente já
          redigiu a réplica acima — ela sai quando você aprovar.
        </p>
        <Botao variante="secundario" tamanho="sm" onClick={aoEscrever}>
          escrever você mesmo
        </Botao>
      </div>
    );
  }

  if (!abordado) {
    return (
      <p className="text-xs text-texto-fraco">
        Aprove a primeira mensagem para ela sair. O lead só pode responder ao que de fato
        foi enviado.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <p className="min-w-[16rem] flex-1 text-xs text-texto-fraco">
        {textoDaCadencia(estadoCadencia, cadencia)}
      </p>
      {estadoCadencia !== null && !estadoCadencia.encerrada && (
        <Botao
          variante="secundario"
          tamanho="sm"
          disabled={ocupado}
          onClick={aoRodarCadencia}
        >
          enviar o toque {estadoCadencia.proximo_toque} agora
        </Botao>
      )}
      <Botao variante="secundario" tamanho="sm" onClick={aoEscrever}>
        escrever você mesmo
      </Botao>
      <Botao variante="fantasma" tamanho="sm" onClick={aoSimular}>
        simular resposta
      </Botao>
    </div>
  );
}

/**
 * O que dizer enquanto o lead nao responde.
 *
 * Antes do Motor 5 esta linha dizia so "aguardando o lead responder" — e
 * dava a entender que o sistema tinha desistido. Agora ela diz a verdade:
 * quantos toques ja sairam, quando sai o proximo, e quando a cadencia
 * terminou, por que terminou.
 */
function textoDaCadencia(
  estado: EstadoCadencia | null,
  cadencia: Cadencia | null,
): string {
  const total = cadencia?.max_toques ?? 3;
  if (estado === null) {
    return "Aguardando o lead responder. Quando responder, o agente classifica a intenção e decide — inclusive quando é melhor não responder.";
  }
  if (estado.encerrada) return `Cadência encerrada: ${estado.motivo}.`;
  if (estado.devido) {
    return `Toque ${estado.proximo_toque} de ${total} pronto para sair (${estado.angulo ?? ""}).`;
  }
  return `Toque ${estado.toques_enviados} de ${total} enviado. O próximo sai ${quando(estado.proximo_em)} — sem cobrar o silêncio, com outro ângulo.`;
}

function quando(iso: string | null): string {
  if (!iso) return "em breve";
  const dias = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (dias <= 0) return "hoje";
  if (dias === 1) return "amanhã";
  return `em ${dias} dias`;
}

function Balao({
  mensagem,
  aoDecidir,
  ocupado,
}: {
  mensagem: Mensagem;
  aoDecidir: (id: string, aprovar: boolean) => void;
  ocupado: boolean;
}) {
  const pendente = mensagem.status === "aguardando_aprovacao";
  const doLead = mensagem.direcao === "entrada";
  // Quem escreveu vem do registro da propria mensagem, e nao da presenca da
  // declaracao de IA no corpo: a declaracao virou opcional (DECLARAR_IA), e sem
  // ela tudo pareceria escrito a mao — inclusive para o cliente, que precisa
  // saber o que o agente mandou em nome dele.
  const daIA = mensagem.gerado_por_ia;

  // A mensagem do lead vem da ESQUERDA, a nossa da direita. Sem essa
  // separacao visual a thread de duas pontas volta a parecer um monologo.
  if (doLead) {
    return (
      <motion.article
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: EXPO }}
        className="mr-auto max-w-[85%]"
      >
        <div className="mb-1 text-[10px] font-medium uppercase tracking-rotulo text-texto-fraco">
          {mensagem.remetente ?? "o lead"}
        </div>
        <div className="rounded-2xl rounded-tl-sm border border-borda bg-superficie-2 px-4 py-3">
          <p className="whitespace-pre-line text-sm leading-relaxed text-texto">
            {mensagem.corpo}
          </p>
        </div>
      </motion.article>
    );
  }

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: EXPO }}
      className="ml-auto max-w-[85%]"
    >
      <div className="mb-1 flex items-center justify-end gap-2">
        <span
          className={`text-[10px] font-medium uppercase tracking-rotulo ${
            daIA ? "text-marca" : "text-texto-medio"
          }`}
        >
          {daIA ? "Prospector AI" : "você"}
        </span>
        <Badge tom={mensagem.status}>{mensagem.status}</Badge>
      </div>
      <div
        className={`rounded-2xl rounded-tr-sm border px-4 py-3 ${
          daIA
            ? "border-marca/20 bg-marca-fraca"
            : "border-borda-forte bg-superficie-3"
        }`}
      >
        {mensagem.assunto && (
          <p className="mb-1.5 text-xs font-medium text-texto">{mensagem.assunto}</p>
        )}
        <p className="whitespace-pre-line text-sm leading-relaxed text-texto-medio">
          {mensagem.corpo}
        </p>
      </div>
      <div className="mt-1 flex items-center justify-end gap-2 text-[11px] text-texto-fraco">
        <span>{mensagem.destinatario}</span>
        {pendente && (
          <>
            <Botao tamanho="sm" onClick={() => aoDecidir(mensagem.id, true)} disabled={ocupado}>
              aprovar e enviar
            </Botao>
            <Botao
              variante="perigo"
              tamanho="sm"
              onClick={() => aoDecidir(mensagem.id, false)}
              disabled={ocupado}
            >
              rejeitar
            </Botao>
          </>
        )}
      </div>
    </motion.article>
  );
}

/**
 * Faixa de lead quente.
 *
 * O protótipo trazia aqui um botão que assinava o plano E agendava a reunião
 * de uma vez. Separei as duas coisas: cobrar e marcar reunião são decisões
 * diferentes, e juntá-las num clique só usa a empolgação do momento para
 * vender. A pessoa fecha o negócio; o plano ela decide quando quiser.
 */
function FaixaLeadQuente({ lead, aoAssumir }: { lead: Lead; aoAssumir: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: EXPO }}
      className="flex flex-wrap items-center gap-3"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-positivo-fraco">
        <svg viewBox="0 0 24 24" className="h-4 w-4 text-positivo" fill="none" aria-hidden>
          <path
            d="M12 3c.6 3 2.4 4 3.6 5.4A6.9 6.9 0 0 1 17.5 13a5.5 5.5 0 1 1-11 0c0-1.6.7-3 1.7-4 .3 1 1 1.7 1.8 2 0-1.7.5-4.6 2-8z"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-texto">O lead está aquecido.</p>
        <p className="text-xs text-texto-fraco">
          {lead.razao_social ?? lead.nome_fantasia} respondeu demonstrando interesse — é
          hora de você entrar na conversa.
        </p>
      </div>
      <Botao onClick={aoAssumir} disabled={!lead.email}>
        assumir a conversa
      </Botao>
    </motion.div>
  );
}

/**
 * A caixa de escrever.
 *
 * O texto sai como foi digitado: nao passa por LLM. Reescrever o que a
 * pessoa escreveu seria colocar palavra na boca dela — e ela assinou.
 *
 * Por isso tambem a mensagem NAO leva a declaracao de IA: o Marco da IA
 * manda declarar quando e IA, nao manda mentir que e. O link de descadastro
 * continua, porque LGPD nao muda conforme quem digitou.
 */
function Compositor({
  lead,
  ocupado,
  aoEnviar,
  aoCancelar,
}: {
  lead: Lead;
  ocupado: boolean;
  aoEnviar: (texto: string) => void;
  aoCancelar: () => void;
}) {
  const [texto, setTexto] = useState("");
  const vazio = texto.trim().length === 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: EXPO }}
      className="space-y-2.5"
    >
      <textarea
        autoFocus
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder={`Escreva para ${lead.nome_fantasia ?? lead.razao_social ?? "o lead"}…`}
        className="min-h-[5.5rem] w-full resize-y rounded-lg border border-borda bg-superficie px-3 py-2 text-sm text-texto outline-none transition-all duration-200 ease-expo placeholder:text-texto-fraco focus:border-marca focus:ring-4 focus:ring-marca/12"
      />
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-[14rem] flex-1 text-xs text-texto-fraco">
          Sai como você escreveu, do seu remetente, com o link de descadastro. Ao
          enviar, você assume a conversa e o agente para de escrever neste lead.
        </p>
        <Botao variante="fantasma" tamanho="sm" onClick={aoCancelar} disabled={ocupado}>
          cancelar
        </Botao>
        <Botao
          tamanho="sm"
          carregando={ocupado}
          disabled={vazio || ocupado}
          onClick={() => aoEnviar(texto.trim())}
        >
          enviar
        </Botao>
      </div>
    </motion.div>
  );
}

/**
 * Deriva o estado da conversa do que REALMENTE aconteceu na thread.
 *
 * A ordem e por urgencia para quem esta olhando: o que exige acao vem antes do
 * que so descreve a relacao. Um lead em negociacao com mensagem parada
 * esperando aprovacao aparece como "aguardando sua aprovacao", porque e isso
 * que destrava a conversa.
 */
function estadoDa(lead: Lead, mensagens: Mensagem[]): EstadoConversa {
  if (lead.status === "convertido" || lead.status === "opt_out" || lead.status === "descartado") {
    return "encerrada";
  }
  if (mensagens.some((m) => m.status === "aguardando_aprovacao")) {
    return "aguardando_sua_aprovacao";
  }
  // Resposta do lead na thread — nao dependemos so do status do lead, que pode
  // nao ter avancado se a primeira mensagem nunca chegou a ser enviada.
  if (lead.status === "respondido" || mensagens.some((m) => m.direcao === "entrada")) {
    return "em_negociacao";
  }
  const enviadas = mensagens.filter((m) => m.status === "enviada" || m.status === "entregue");
  if (enviadas.length > 1) return "aguardando_resposta";
  if (enviadas.length === 1) return "primeiro_contato_enviado";
  return "encerrada";
}

/** O lead so pode responder ao que de fato saiu. */
function foiAbordado(mensagens: Mensagem[]): boolean {
  return mensagens.some(
    (m) => m.direcao === "saida" && (m.status === "enviada" || m.status === "entregue"),
  );
}

function iniciaisDe(nome: string): string {
  return (
    nome
      .split(/\s+/)
      .filter((p) => p.length > 2)
      .slice(0, 2)
      .map((p) => p[0])
      .join("")
      .toUpperCase() || "??"
  );
}
