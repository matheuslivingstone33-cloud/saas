import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { EXPO, NumeroAnimado } from "./movimento";
import { Badge, Botao } from "./ui";
import Portal from "./Portal";

/**
 * Execucao ao vivo.
 *
 * "Rodar campanha" era uma caixa-preta: clique, espera, leads aparecem. O que
 * o produto tem de mais valioso — o raciocinio — ficava invisivel.
 *
 * Aqui o backend transmite cada etapa por SSE e a interface narra: que ramos o
 * Cerebro escolheu e quais descartou como concorrente, que termo buscou, que
 * empresa casou com a Receita, quanto deu o score e por que.
 *
 * Isso nao e enfeite: e o que transforma "confie no algoritmo" em "veja o que
 * ele fez". Com provedores reais a execucao leva dezenas de segundos — sem
 * isto, seriam dezenas de segundos de tela parada.
 */

type Evento = { id: number; etapa: string; dados: Record<string, unknown> };

type Props = {
  campanhaId: string;
  limiteLeads?: number;
  aoTerminar: () => void;
  aoFechar: () => void;
};

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Como cada etapa se apresenta: icone, cor e frase. */
const APARENCIA: Record<
  string,
  { rotulo: string; tom: "neutro" | "marca" | "acento" | "positivo" | "atencao" | "perigo" }
> = {
  aberto: { rotulo: "conectado", tom: "neutro" },
  inicio: { rotulo: "iniciando", tom: "neutro" },
  cerebro: { rotulo: "cérebro", tom: "marca" },
  busca: { rotulo: "buscando", tom: "acento" },
  encontrado: { rotulo: "empresa", tom: "positivo" },
  duplicado: { rotulo: "duplicada", tom: "neutro" },
  recusado: { rotulo: "recusada", tom: "neutro" },
  descoberta: { rotulo: "descoberta", tom: "acento" },
  qualificado: { rotulo: "score", tom: "marca" },
  redigida: { rotulo: "redigida", tom: "marca" },
  enviada: { rotulo: "enviada", tom: "positivo" },
  bloqueado: { rotulo: "bloqueada", tom: "perigo" },
  falhou: { rotulo: "falhou", tom: "perigo" },
  abordagem: { rotulo: "abordagem", tom: "acento" },
  erro: { rotulo: "erro", tom: "perigo" },
  fim: { rotulo: "concluída", tom: "positivo" },
};

export default function ExecucaoAoVivo({ campanhaId, limiteLeads = 5, aoTerminar, aoFechar }: Props) {
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [rodando, setRodando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const fim = useRef<HTMLDivElement>(null);

  const empurrar = useCallback((etapa: string, dados: Record<string, unknown>) => {
    // O id sai de DENTRO do atualizador, a partir da lista corrente.
    //
    // Ler um contador externo aqui gera chave duplicada: no modo estrito o
    // React invoca o atualizador duas vezes, e as duas leriam o mesmo valor.
    // Atualizador puro e a regra — o proprio estado e a fonte do id.
    setEventos((atual) => [...atual, { id: atual.length + 1, etapa, dados }]);
  }, []);

  // O callback vive numa ref, NAO no array de dependencias.
  //
  // Se `aoTerminar` entrasse nas dependencias, qualquer chamador que passasse
  // uma funcao inline (identidade nova a cada renderizacao) faria o efeito
  // reexecutar: fecha o fluxo, abre outro — e abrir executa a campanha de
  // novo. Foi exatamente esse laco que gerou centenas de execucoes.
  const aoTerminarRef = useRef(aoTerminar);
  aoTerminarRef.current = aoTerminar;

  useEffect(() => {
    // ATENCAO: o EventSource RECONECTA SOZINHO quando o servidor fecha o fluxo.
    // Como abrir esta rota EXECUTA a campanha, cada reconexao era uma execucao
    // nova — um clique gerou 256 execucoes e 1020 consultas ao Places antes de
    // isto ser corrigido. Defesas, nesta ordem:
    //   1. o servidor recusa execucao concorrente da mesma campanha (409);
    //   2. o servidor manda `retry: 24h`, entao o navegador nao reabre sozinho;
    //   3. aqui: `encerrado` fecha, e a flag garante que nada reabra depois.
    const url = `${BASE}/v1/campaigns/${campanhaId}/run/stream?limite_leads=${limiteLeads}`;
    const fonte = new EventSource(url);
    let encerrado = false;

    const encerrar = () => {
      if (encerrado) return;
      encerrado = true;
      fonte.close();
      setRodando(false);
    };

    const etapas = Object.keys(APARENCIA).concat("encerrado");
    for (const etapa of etapas) {
      fonte.addEventListener(etapa, (e) => {
        if (encerrado) return;
        const dados = JSON.parse((e as MessageEvent).data || "{}");
        if (etapa === "encerrado") {
          encerrar();
          aoTerminarRef.current();
          return;
        }
        if (etapa === "erro") setErro(String(dados.detalhe ?? "falha na execução"));
        // "aberto" e handshake de protocolo — nao diz nada ao usuario.
        if (etapa !== "aberto") empurrar(etapa, dados);
      });
    }

    fonte.onerror = () => {
      // Chega aqui quando o servidor fecha OU a conexao cai. Em ambos os casos
      // fechamos: reabrir custaria outra execucao paga.
      //
      // O EventSource NAO expoe o codigo HTTP ao JavaScript. Entao, quando o
      // servidor recusa com 409 (campanha ja rodando, ou o intervalo minimo
      // entre execucoes), tudo o que chega aqui e "erro" — sem nenhum evento
      // antes. Silencio nessa hora parece defeito; o usuario merece o motivo.
      if (!encerrado) {
        setEventos((atual) => {
          if (atual.length === 0) {
            setErro(
              "Não foi possível iniciar agora. A campanha pode já estar rodando " +
                "ou ter rodado há poucos segundos — aguarde um momento e tente de novo.",
            );
          }
          return atual;
        });
        encerrar();
        aoTerminarRef.current();
      }
    };

    return encerrar;
    // Dependencias PROPOSITALMENTE reduzidas: o efeito precisa rodar uma unica
    // vez por campanha. Abrir o fluxo tem efeito colateral pago.
  }, [campanhaId, limiteLeads, empurrar]);

  useEffect(() => {
    fim.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [eventos.length]);

  const achados = eventos.filter((e) => e.etapa === "encontrado").length;
  const pontuados = eventos.filter((e) => e.etapa === "qualificado");
  const redigidas = eventos.filter((e) => e.etapa === "redigida").length;
  const consultas = eventos.filter((e) => e.etapa === "busca").length;

  return (
    <Portal>
    <motion.div
      className="fixed inset-0 z-40 flex items-end justify-center bg-fundo/70 p-4 backdrop-blur-sm sm:items-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={rodando ? undefined : aoFechar}
    >
      <motion.section
        role="dialog"
        aria-label="Execução da campanha"
        onClick={(e) => e.stopPropagation()}
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, ease: EXPO }}
        className="realce-topo flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-borda bg-superficie shadow-3"
      >
        <header className="flex items-center gap-3 border-b border-borda px-5 py-3.5">
          <span className="relative flex h-2.5 w-2.5">
            {rodando && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-marca opacity-60" />
            )}
            <span
              className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                erro ? "bg-perigo" : rodando ? "bg-marca" : "bg-positivo"
              }`}
            />
          </span>
          <h2 className="text-sm font-semibold text-texto">
            {erro ? "Execução interrompida" : rodando ? "Executando" : "Execução concluída"}
          </h2>
          <div className="ml-auto flex items-center gap-4 text-xs text-texto-fraco">
            <Metrica rotulo="consultas" valor={consultas} />
            <Metrica rotulo="empresas" valor={achados} />
            <Metrica rotulo="mensagens" valor={redigidas} />
          </div>
        </header>

        {erro && (
          <div className="border-b border-perigo/30 bg-perigo-fraco px-5 py-3 text-sm text-perigo">
            {erro}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <ol className="relative space-y-2.5 border-l border-borda pl-5">
            <AnimatePresence initial={false}>
              {eventos.map((ev) => (
                <LinhaEvento key={ev.id} evento={ev} />
              ))}
            </AnimatePresence>
            {rodando && (
              <li className="flex items-center gap-2 text-xs text-texto-fraco">
                <span className="-ml-[1.6rem] h-2 w-2 rounded-full bg-borda-forte" />
                <span className="inline-flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <motion.span
                      key={i}
                      className="h-1 w-1 rounded-full bg-texto-fraco"
                      animate={{ opacity: [0.2, 1, 0.2] }}
                      transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.15 }}
                    />
                  ))}
                </span>
              </li>
            )}
            <div ref={fim} />
          </ol>
        </div>

        <footer className="flex items-center gap-3 border-t border-borda px-5 py-3">
          {pontuados.length > 0 && (
            <p className="text-xs text-texto-fraco">
              score médio{" "}
              <span className="num font-medium text-texto">
                {(
                  pontuados.reduce((s, e) => s + Number(e.dados.score ?? 0), 0) / pontuados.length
                ).toFixed(0)}
              </span>
            </p>
          )}
          <div className="ml-auto">
            <Botao variante={rodando ? "secundario" : "primario"} onClick={aoFechar}>
              {rodando ? "acompanhar em segundo plano" : "ver resultado"}
            </Botao>
          </div>
        </footer>
      </motion.section>
    </motion.div>
    </Portal>
  );
}

function Metrica({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <span className="flex items-baseline gap-1">
      <NumeroAnimado valor={valor} className="text-sm font-semibold text-texto" duracao={0.4} />
      <span>{rotulo}</span>
    </span>
  );
}

function LinhaEvento({ evento }: { evento: Evento }) {
  const { etapa, dados } = evento;
  const aparencia = APARENCIA[etapa] ?? { rotulo: etapa, tom: "neutro" as const };

  return (
    <motion.li
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.28, ease: EXPO }}
      className="relative"
    >
      <span
        className={`absolute -left-[1.6rem] top-1.5 h-2 w-2 rounded-full ring-4 ring-superficie ${
          aparencia.tom === "positivo"
            ? "bg-positivo"
            : aparencia.tom === "perigo"
              ? "bg-perigo"
              : aparencia.tom === "marca"
                ? "bg-marca"
                : aparencia.tom === "acento"
                  ? "bg-acento"
                  : "bg-borda-forte"
        }`}
      />
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <Badge tom={aparencia.tom}>{aparencia.rotulo}</Badge>
        <Corpo etapa={etapa} dados={dados} />
      </div>
    </motion.li>
  );
}

function Corpo({ etapa, dados }: { etapa: string; dados: Record<string, unknown> }) {
  const t = (c: unknown) => String(c ?? "");

  switch (etapa) {
    case "inicio":
      return (
        <span className="text-sm text-texto-medio">
          <span className="text-texto">{t(dados.campanha)}</span> · {t(dados.regiao)} · modo{" "}
          {t(dados.autonomia)}
        </span>
      );

    case "cerebro": {
      const ramos = (dados.ramos ?? []) as { codigo: string; descricao: string; peso: number }[];
      const excluidos = (dados.excluidos ?? []) as string[];
      return (
        <div className="w-full space-y-2">
          <p className="text-sm text-texto-medio">
            casou o serviço com <span className="text-texto">{ramos.length} ramos</span> que o
            consomem
            {excluidos.length > 0 && (
              <>
                {" "}
                e descartou <span className="text-texto">{excluidos.length}</span> como concorrente
              </>
            )}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {ramos.slice(0, 6).map((r) => (
              <span
                key={r.codigo}
                title={`${r.codigo} — peso ${r.peso}`}
                className="inline-flex items-center gap-1.5 rounded-md border border-borda bg-superficie-2 px-2 py-1 text-[11px] text-texto-medio"
              >
                <span className="num text-texto-fraco">{r.codigo}</span>
                <span className="max-w-[13rem] truncate">{r.descricao}</span>
                <span className="num text-marca">{(r.peso * 100).toFixed(0)}</span>
              </span>
            ))}
          </div>
        </div>
      );
    }

    case "busca":
      return (
        <span className="text-sm text-texto-medio">
          “{t(dados.termo)}” em {t(dados.regiao)} ·{" "}
          <span className="num text-texto">{t(dados.candidatos)}</span> candidatas
        </span>
      );

    case "encontrado":
      return (
        <span className="text-sm text-texto-medio">
          <span className="font-medium text-texto">{t(dados.empresa)}</span>
          {dados.cnpj ? <span className="num text-texto-fraco"> · {t(dados.cnpj)}</span> : null}
          {dados.enriquecido ? (
            <span className="text-positivo"> · casou com a Receita</span>
          ) : (
            <span className="text-texto-fraco"> · sem CNPJ na base</span>
          )}
        </span>
      );

    case "duplicado":
      return <span className="text-sm text-texto-fraco">{t(dados.nome)} — já estava na base</span>;

    case "recusado":
      return (
        <span className="text-sm text-texto-fraco">
          {t(dados.nome)} — {t(dados.motivo)}
        </span>
      );

    case "qualificado":
      return (
        <span className="text-sm text-texto-medio">
          <span className="font-medium text-texto">{t(dados.empresa)}</span> ·{" "}
          <span className="num font-semibold text-marca">{Number(dados.score ?? 0).toFixed(0)}</span>
          <span className="block text-xs text-texto-fraco">{t(dados.explicacao)}</span>
        </span>
      );

    case "redigida":
      return (
        <span className="text-sm text-texto-medio">
          para <span className="text-texto">{t(dados.destinatario)}</span> ·{" "}
          <span className="num">{t(dados.tokens)}</span> tokens
          {dados.automatica ? "" : " · aguarda sua aprovação"}
        </span>
      );

    case "enviada":
      return <span className="text-sm text-texto-medio">{t(dados.destinatario)}</span>;

    case "bloqueado":
      return (
        <span className="text-sm text-texto-medio">
          {t(dados.empresa)} — {t(dados.motivo)}
        </span>
      );

    case "descoberta":
      return (
        <span className="text-sm text-texto-medio">
          <span className="num text-texto">{t(dados.consultas)}</span> consultas ·{" "}
          <span className="num text-texto">{t(dados.criados)}</span> novas ·{" "}
          <span className="num">{t(dados.duplicados)}</span> repetidas
        </span>
      );

    case "abordagem":
      return (
        <span className="text-sm text-texto-medio">
          <span className="num text-texto">{t(dados.geradas)}</span> mensagens ·{" "}
          <span className="num">{t(dados.enviadas)}</span> enviadas ·{" "}
          <span className="num">{t(dados.aguardando)}</span> aguardando
        </span>
      );

    case "erro":
      return <span className="text-sm text-perigo">{t(dados.detalhe)}</span>;

    case "fim":
      return <span className="text-sm text-texto-medio">campanha encerrada</span>;

    default: {
      // Etapa que a interface ainda nao conhece: mostra os campos de forma
      // legivel em vez de despejar JSON na cara do usuario.
      const resumo = Object.entries(dados)
        .filter(([, v]) => v !== null && typeof v !== "object")
        .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
        .join(" · ");
      return <span className="text-sm text-texto-fraco">{resumo || etapa}</span>;
    }
  }
}
