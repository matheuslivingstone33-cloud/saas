import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Lead, type Mensagem, type NivelAutonomia } from "../lib/api";
import { EXPO } from "../components/movimento";
import { Aviso, Badge, Botao, Carregando, Vazio } from "../components/ui";
import Revisao from "../components/Revisao";
import ExplicacaoLead from "../components/ExplicacaoLead";

/**
 * Conversas — onde a abordagem vira negocio.
 *
 * ESTADO ATUAL (importante): o sistema hoje e de MAO UNICA. Ele gera a
 * mensagem, envia e registra o status. Nao existe recebimento de resposta,
 * nem IA respondendo. Os estados `respondido` e `convertido` existem na
 * maquina de estados do lead e nunca acontecem — nada os preenche.
 *
 * Esta tela mostra o que ha de verdade e diz, sem rodeio, o que falta. Fingir
 * uma conversa de duas pontas que nao existe seria mentir para o usuario no
 * lugar onde ele mais precisa confiar.
 *
 * O Motor 4 (receber, encadear, responder, negociar) e a proxima etapa.
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

  const carregar = useCallback(async () => {
    try {
      const [l, m] = await Promise.all([api.leads(), api.mensagens()]);
      setLeads(l.itens);
      setMensagens(m.itens);
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
        const ordenadas = [...msgs].sort(
          (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
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

              {/* Enquanto o Motor 4 nao existe, dizemos a verdade. */}
              <footer className="border-t border-borda bg-superficie-2 px-5 py-3">
                <p className="text-xs text-texto-fraco">
                  <span className="font-medium text-texto-medio">Só de ida, por enquanto.</span>{" "}
                  As respostas dos leads ainda não chegam aqui — receber, encadear e deixar
                  a IA negociar é a próxima etapa do produto.
                </p>
              </footer>
            </>
          )}
        </section>
      </div>

      {detalhe && <ExplicacaoLead lead={detalhe} aoFechar={() => setDetalhe(null)} />}

      <AnimatePresence>
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

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: EXPO }}
      className="ml-auto max-w-[85%]"
    >
      <div className="mb-1 flex items-center justify-end gap-2">
        <span className="text-[10px] font-medium uppercase tracking-rotulo text-marca">
          Prospector AI
        </span>
        <Badge tom={mensagem.status}>{mensagem.status}</Badge>
      </div>
      <div className="rounded-2xl rounded-tr-sm border border-marca/20 bg-marca-fraca px-4 py-3">
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
 * Deriva o estado da conversa do que EXISTE hoje.
 *
 * `em_negociacao` depende de o lead ter respondido — o que so vai acontecer
 * quando o Motor 4 existir. Deixamos o caso mapeado para a tela ja funcionar
 * no dia em que a primeira resposta chegar.
 */
function estadoDa(lead: Lead, mensagens: Mensagem[]): EstadoConversa {
  if (lead.status === "convertido" || lead.status === "opt_out" || lead.status === "descartado") {
    return "encerrada";
  }
  if (lead.status === "respondido") return "em_negociacao";
  if (mensagens.some((m) => m.status === "aguardando_aprovacao")) {
    return "aguardando_sua_aprovacao";
  }
  const enviadas = mensagens.filter((m) => m.status === "enviada" || m.status === "entregue");
  if (enviadas.length > 1) return "aguardando_resposta";
  if (enviadas.length === 1) return "primeiro_contato_enviado";
  return "encerrada";
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
