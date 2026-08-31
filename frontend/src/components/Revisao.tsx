import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { api, type Lead, type Mensagem } from "../lib/api";
import { EXPO } from "./movimento";
import { Badge, Botao } from "./ui";
import Portal from "./Portal";

/**
 * Revisao em foco.
 *
 * Aprovar mensagens era rolar uma lista de cartoes quase identicos e clicar um
 * a um. E a acao MAIS frequente do produto — quem roda campanha toda semana
 * passa mais tempo aqui do que em qualquer outra tela.
 *
 * Aqui e uma mensagem por vez, em tela cheia, com o motivo do score ao lado e
 * o teclado no comando: A aprova, R rejeita, E edita, setas navegam. Da para
 * revisar vinte mensagens sem tirar a mao do teclado.
 *
 * A pilha nao volta atras sozinha: decidir e definitivo, entao cada decisao
 * mostra o que aconteceu antes de avancar.
 */

type Props = {
  mensagens: Mensagem[];
  leads: Lead[];
  aoFechar: () => void;
  aoDecidir: () => void;
};

type Decisao = "aprovada" | "rejeitada";

export default function Revisao({ mensagens, leads, aoFechar, aoDecidir }: Props) {
  const [indice, setIndice] = useState(0);
  const [decisoes, setDecisoes] = useState<Record<string, Decisao>>({});
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);
  const [rascunho, setRascunho] = useState("");

  // A pilha exclui o que ja foi decidido NESTA sessao, sem esperar a lista do
  // servidor voltar. Sem isso, entre a decisao e o recarregamento a lista
  // encolhe por baixo do indice e uma mensagem e pulada sem ser vista.
  const pendentes = mensagens.filter(
    (m) => m.status === "aguardando_aprovacao" && !decisoes[m.id],
  );
  const atual = pendentes[indice];
  const lead = leads.find((l) => l.id === atual?.lead_id);
  const decididas = Object.keys(decisoes).length;

  /** Avanca para o proximo card (navegacao manual, sem decidir). */
  const avancar = useCallback(() => {
    setEditando(false);
    setIndice((i) => Math.min(i + 1, Math.max(0, pendentes.length - 1)));
  }, [pendentes.length]);

  const decidir = useCallback(
    async (decisao: Decisao) => {
      if (!atual || ocupado) return;
      setOcupado(true);
      setErro(null);
      try {
        if (decisao === "aprovada") await api.aprovar(atual.id);
        else await api.rejeitar(atual.id);
        // O item decidido SAI da pilha, entao o proximo assume este mesmo
        // indice. Avancar aqui pularia um.
        setDecisoes((d) => ({ ...d, [atual.id]: decisao }));
        setEditando(false);
        aoDecidir();
      } catch (e) {
        setErro(String(e));
      } finally {
        setOcupado(false);
      }
    },
    [atual, ocupado, aoDecidir, avancar],
  );

  // Teclado. Ignora quando o foco esta num campo de texto, senao digitar "a"
  // no editor aprovaria a mensagem.
  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      const alvo = e.target as HTMLElement;
      const digitando =
        alvo?.tagName === "INPUT" || alvo?.tagName === "TEXTAREA" || alvo?.isContentEditable;
      if (digitando) {
        if (e.key === "Escape") setEditando(false);
        return;
      }
      const tecla = e.key.toLowerCase();
      if (tecla === "a") {
        e.preventDefault();
        decidir("aprovada");
      } else if (tecla === "r") {
        e.preventDefault();
        decidir("rejeitada");
      } else if (tecla === "e") {
        e.preventDefault();
        setRascunho(atual?.corpo ?? "");
        setEditando(true);
      } else if (e.key === "ArrowRight" || tecla === "j") {
        avancar();
      } else if (e.key === "ArrowLeft" || tecla === "k") {
        setIndice((i) => Math.max(0, i - 1));
      } else if (e.key === "Escape") {
        aoFechar();
      }
    }
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [decidir, avancar, aoFechar, atual]);

  useEffect(() => {
    if (indice > 0 && indice >= pendentes.length) {
      setIndice(Math.max(0, pendentes.length - 1));
    }
  }, [indice, pendentes.length]);

  const acabou = pendentes.length === 0;

  return (
    <Portal>
    <motion.div
      className="fixed inset-0 z-40 flex items-center justify-center bg-fundo/80 p-4 backdrop-blur-md"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.section
        role="dialog"
        aria-label="Revisão de mensagens"
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: EXPO }}
        className="realce-topo flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-borda bg-superficie shadow-3"
      >
        <header className="flex items-center gap-3 border-b border-borda px-5 py-3.5">
          <h2 className="text-sm font-semibold text-texto">Revisão</h2>
          {!acabou && (
            <span className="num text-xs text-texto-fraco">
              {indice + 1} de {pendentes.length}
            </span>
          )}
          <div className="ml-auto flex items-center gap-3">
            {decididas > 0 && (
              <span className="num text-xs text-positivo">{decididas} decididas</span>
            )}
            <Botao variante="fantasma" tamanho="sm" onClick={aoFechar}>
              fechar
            </Botao>
          </div>
        </header>

        {/* Progresso da pilha */}
        <div className="h-0.5 bg-superficie-3">
          <motion.div
            className="h-full bg-marca"
            animate={{
              width: `${pendentes.length ? (decididas / (decididas + pendentes.length)) * 100 : 100}%`,
            }}
            transition={{ duration: 0.5, ease: EXPO }}
          />
        </div>

        {erro && (
          <div className="border-b border-perigo/30 bg-perigo-fraco px-5 py-2 text-xs text-perigo">
            {erro}
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            {acabou ? (
              <motion.div
                key="fim"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center gap-3 px-5 py-16 text-center"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-positivo-fraco">
                  <svg viewBox="0 0 24 24" className="h-6 w-6 text-positivo" fill="none">
                    <path
                      d="M5 13l4 4L19 7"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                <p className="text-sm font-medium text-texto">Fila vazia</p>
                <p className="max-w-sm text-sm text-texto-fraco">
                  {decididas > 0
                    ? `Você decidiu ${decididas} ${decididas === 1 ? "mensagem" : "mensagens"}. As aprovadas já foram para a caixa de saída.`
                    : "Nenhuma mensagem aguardando aprovação nesta campanha."}
                </p>
                <Botao onClick={aoFechar}>voltar</Botao>
              </motion.div>
            ) : (
              <motion.article
                key={atual.id}
                initial={{ opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -24 }}
                transition={{ duration: 0.28, ease: EXPO }}
                className="grid gap-5 px-5 py-5 md:grid-cols-[1fr_15rem]"
              >
                <div className="min-w-0 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-texto">{atual.destinatario}</span>
                    <Badge tom="atencao">aguardando</Badge>
                  </div>
                  <p className="text-sm font-medium text-texto-medio">{atual.assunto}</p>

                  {editando ? (
                    <textarea
                      autoFocus
                      value={rascunho}
                      onChange={(e) => setRascunho(e.target.value)}
                      className="min-h-[16rem] w-full resize-y rounded-lg border border-marca bg-superficie-2 p-3 text-sm text-texto outline-none ring-4 ring-marca/12"
                    />
                  ) : (
                    <div className="whitespace-pre-line rounded-lg border border-borda bg-superficie-2 p-4 text-sm leading-relaxed text-texto-medio">
                      {atual.corpo}
                    </div>
                  )}

                  {editando && (
                    <p className="text-xs text-texto-fraco">
                      A edição vale só para esta revisão — a Fase seguinte persiste o texto
                      alterado. <kbd className="rounded border border-borda px-1">Esc</kbd> cancela.
                    </p>
                  )}
                </div>

                <aside className="space-y-4 md:border-l md:border-borda md:pl-5">
                  {lead && (
                    <div>
                      <h3 className="text-[10px] font-semibold uppercase tracking-rotulo text-texto-fraco">
                        Por que esta empresa
                      </h3>
                      <p className="mt-1.5 text-sm font-medium text-texto">
                        {lead.razao_social ?? "Contato ainda nao revelado"}
                      </p>
                      <p className="num mt-0.5 text-xs text-texto-fraco">{lead.cnpj ?? "sem CNPJ"}</p>
                      <div className="mt-3 flex items-baseline gap-1.5">
                        <span className="num text-2xl font-semibold text-marca">
                          {Number(lead.score).toFixed(0)}
                        </span>
                        <span className="text-xs text-texto-fraco">de score</span>
                      </div>
                      <Fatores breakdown={lead.score_breakdown} />
                    </div>
                  )}

                  <div className="rounded-lg border border-borda bg-superficie-2 p-3">
                    <h3 className="text-[10px] font-semibold uppercase tracking-rotulo text-texto-fraco">
                      Conformidade
                    </h3>
                    <ul className="mt-1.5 space-y-1 text-xs text-texto-medio">
                      <li>✓ declara ser IA</li>
                      <li>✓ link de descadastro</li>
                      <li>✓ contato comercial (PJ)</li>
                    </ul>
                  </div>
                </aside>
              </motion.article>
            )}
          </AnimatePresence>
        </div>

        {!acabou && (
          <footer className="flex flex-wrap items-center gap-2 border-t border-borda px-5 py-3">
            <Botao onClick={() => decidir("aprovada")} disabled={ocupado}>
              aprovar e enviar
              <Tecla>A</Tecla>
            </Botao>
            <Botao variante="perigo" onClick={() => decidir("rejeitada")} disabled={ocupado}>
              rejeitar
              <Tecla>R</Tecla>
            </Botao>
            <Botao
              variante="secundario"
              onClick={() => {
                setRascunho(atual.corpo);
                setEditando((v) => !v);
              }}
            >
              editar
              <Tecla>E</Tecla>
            </Botao>
            <div className="ml-auto flex items-center gap-1 text-xs text-texto-fraco">
              <Tecla>←</Tecla>
              <Tecla>→</Tecla>
              navegar
            </div>
          </footer>
        )}
      </motion.section>
    </motion.div>
    </Portal>
  );
}

function Tecla({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-current/25 px-1 text-[10px] leading-4 opacity-70">
      {children}
    </kbd>
  );
}

function Fatores({ breakdown }: { breakdown: Record<string, unknown> | null | undefined }) {
  // `contribuicoes` ja vem em PONTOS do score (nao em 0-1): e o que o usuario
  // precisa ver — quanto cada fator somou nos 100 pontos, nao o valor bruto.
  const contribuicoes = (breakdown?.contribuicoes ?? {}) as Record<string, number>;
  const linhas = Object.entries(contribuicoes)
    .filter(([, pts]) => Number(pts) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 5);
  if (linhas.length === 0) return null;
  const maior = Math.max(...linhas.map(([, p]) => Number(p)), 1);

  return (
    <ul className="mt-3 space-y-1.5">
      {linhas.map(([nome, pontos]) => (
        <li key={nome} className="text-xs">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-texto-fraco">{nome.replace(/_/g, " ")}</span>
            <span className="num text-texto-medio">+{Number(pontos).toFixed(0)}</span>
          </div>
          <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-superficie-3">
            <motion.div
              className="h-full rounded-full bg-marca/70"
              initial={{ width: 0 }}
              animate={{ width: `${(Number(pontos) / maior) * 100}%` }}
              transition={{ duration: 0.6, ease: EXPO }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
