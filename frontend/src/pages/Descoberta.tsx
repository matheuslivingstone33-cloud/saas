import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { api, type Campanha, type Lead } from "../lib/api";
import { EXPO, itemVariantes, listaVariantes, NumeroAnimado } from "../components/movimento";
import { Aviso, Badge, Botao, Carregando, Vazio } from "../components/ui";
import ExecucaoAoVivo from "../components/ExecucaoAoVivo";
import ExplicacaoLead from "../components/ExplicacaoLead";

/**
 * Descoberta — o resultado da busca.
 *
 * A tela responde tres perguntas, nesta ordem de importancia:
 *   1. quantas empresas existem para mim? (o numero grande)
 *   2. quais sao as melhores? (os cartoes, ordenados por score)
 *   3. por que essas? (o insight e o "por que?" de cada uma)
 *
 * O plano gratuito mostra as 3 melhores e diz honestamente quantas ficaram de
 * fora. Esconder a existencia delas seria mais "limpo" e menos honesto.
 */

const GRATUITAS = 3;

/** Ramo escolhido pelo Cérebro, como vem em `campanha.expansao`. */
type RamoAlvo = { codigo: string; descricao: string; peso: number };

function ramosDa(campanha: Campanha | null): RamoAlvo[] {
  const bruto = (campanha?.expansao as { ramos?: unknown } | null)?.ramos;
  return Array.isArray(bruto) ? (bruto as RamoAlvo[]) : [];
}

export default function Descoberta({
  campanhaId,
  aoAbordar,
  aoNovaBusca,
}: {
  campanhaId: string | null;
  aoAbordar: (leadId: string) => void;
  aoNovaBusca: () => void;
}) {
  const [campanha, setCampanha] = useState<Campanha | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<Lead | null>(null);
  const [aoVivo, setAoVivo] = useState(false);
  const [jaRodou, setJaRodou] = useState(false);
  // Guarda o resumo da ultima execucao. Sem isso nao da para distinguir
  // "nao encontrei nada" de "encontrei, mas voce ja tem todas" — dois
  // resultados opostos que apareciam com a mesma tela vazia.
  const [ultimaExecucao, setUltimaExecucao] = useState<{
    duplicados: number;
    candidatos: number;
  } | null>(null);

  const carregar = useCallback(async () => {
    if (!campanhaId) {
      setCarregando(false);
      return;
    }
    try {
      const [c, l] = await Promise.all([
        api.campanha(campanhaId),
        api.leads(campanhaId),
      ]);
      setCampanha(c);
      setLeads(l.itens);
      // Campanha em rascunho e sem lead nenhum: nunca rodou. Abre a execucao
      // ao vivo automaticamente — o usuario acabou de pedir a busca, esperar
      // um segundo clique seria burocracia.
      if (!jaRodou && l.itens.length === 0 && c.status === "rascunho") {
        setJaRodou(true);
        setAoVivo(true);
      }
    } catch (e) {
      setErro(String(e));
    } finally {
      setCarregando(false);
    }
  }, [campanhaId, jaRodou]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (!campanhaId) {
    return (
      <Vazio>
        Nenhuma busca ainda. Comece pela aba <strong>Busca</strong> dizendo o serviço
        que você faz e onde atua.
      </Vazio>
    );
  }

  if (carregando) return <Carregando />;

  const ramos = ramosDa(campanha);
  const ordenados = [...leads].sort((a, b) => Number(b.score) - Number(a.score));
  const melhores = ordenados.slice(0, GRATUITAS);
  const restantes = Math.max(0, ordenados.length - GRATUITAS);

  return (
    <div>
      <button
        onClick={aoNovaBusca}
        className="mb-5 inline-flex items-center gap-2 text-sm text-texto-fraco transition-colors hover:text-texto"
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
          <path d="M19 12H5M11 18l-6-6 6-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Nova busca
      </button>

      {erro && (
        <div className="mb-5">
          <Aviso tom="erro">{erro}</Aviso>
        </div>
      )}

      {Boolean(campanha?.expansao?.justificativa) && (
        <Badge tom="positivo" ponto>
          análise concluída
        </Badge>
      )}

      <h1 className="mt-3 max-w-3xl text-3xl font-semibold leading-tight tracking-tight text-texto sm:text-4xl">
        {ordenados.length > 0 ? (
          <>
            Encontramos{" "}
            <span className="text-marca">
              <NumeroAnimado valor={ordenados.length} /> empresa
              {ordenados.length === 1 ? "" : "s"}
            </span>{" "}
            precisando de <span className="text-marca">{campanha?.servico}</span> na sua
            região.
          </>
        ) : (
          <>Procurando empresas que precisam de {campanha?.servico}…</>
        )}
      </h1>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-texto-fraco">
        <span className="inline-flex items-center gap-1.5">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
            <path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
            <circle cx="12" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.7" />
          </svg>
          {campanha?.regiao}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-positivo" fill="none" aria-hidden>
            <path d="M12 3l7 3v6c0 4.4-3 8.2-7 9-4-.8-7-4.6-7-9V6l7-3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
            <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          Dados públicos de empresas · LGPD
        </span>
        <button
          onClick={() => setAoVivo(true)}
          className="inline-flex items-center gap-1.5 text-marca transition-opacity hover:opacity-80"
        >
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
            <path d="M7 4l12 8-12 8V4z" fill="currentColor" />
          </svg>
          rodar de novo ao vivo
        </button>
      </div>

      {ordenados.length > 0 && (
        <div className="mt-8 flex items-baseline justify-between gap-4">
          <h2 className="text-sm font-medium text-texto">
            {melhores.length === ordenados.length
              ? "Oportunidades encontradas"
              : `As ${melhores.length} melhores oportunidades para você`}
          </h2>
          {restantes > 0 && (
            <p className="text-xs text-texto-fraco">
              {restantes} {restantes === 1 ? "empresa restante disponível" : "empresas restantes disponíveis"} no plano PRO
            </p>
          )}
        </div>
      )}

      <motion.div
        variants={listaVariantes}
        initial="oculto"
        animate="visivel"
        className="mt-4 grid gap-4 md:grid-cols-3"
      >
        {melhores.map((lead) => (
          <CartaoLead
            key={lead.id}
            lead={lead}
            ramos={ramos}
            aoExplicar={() => setDetalhe(lead)}
            aoAbordar={() => aoAbordar(lead.id)}
          />
        ))}
      </motion.div>

      {ordenados.length === 0 && !aoVivo && <SemResultado ultima={ultimaExecucao} />}

      {detalhe && <ExplicacaoLead lead={detalhe} aoFechar={() => setDetalhe(null)} />}

      <AnimatePresence>
        {aoVivo && (
          <ExecucaoAoVivo
            campanhaId={campanhaId}
            limiteLeads={10}
            aoTerminar={(resumo) => {
              setUltimaExecucao(resumo);
              void carregar();
            }}
            aoFechar={() => setAoVivo(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * O vazio tem duas causas OPOSTAS e elas nao podem parecer a mesma coisa:
 *
 *   - nao encontrei candidatas  -> o termo ou a regiao precisam mudar
 *   - encontrei, mas todas ja   -> o sistema funcionou; as empresas estao
 *     estavam na sua base          em Conversas, nao aqui
 *
 * Mostrar "nenhuma empresa ainda" no segundo caso faz o produto parecer
 * quebrado justamente quando ele acertou.
 */
function SemResultado({
  ultima,
}: {
  ultima: { duplicados: number; candidatos: number } | null;
}) {
  if (ultima && ultima.duplicados > 0) {
    return (
      <div className="mt-6">
        <Aviso tom="info">
          <p className="font-medium">
            Encontramos {ultima.duplicados}{" "}
            {ultima.duplicados === 1 ? "empresa" : "empresas"}, mas{" "}
            {ultima.duplicados === 1 ? "ela já estava" : "todas já estavam"} na sua base.
          </p>
          <p className="mt-1 text-texto-medio">
            O sistema não aborda a mesma empresa duas vezes — isso protege sua reputação
            de remetente. Elas estão na aba <strong>Conversas</strong>. Para achar novas,
            tente outra região ou amplie o serviço.
          </p>
        </Aviso>
      </div>
    );
  }

  return (
    <Vazio>
      {ultima
        ? "Nenhuma empresa encontrada para esse serviço nessa região. Tente descrever o serviço de outro jeito ou ampliar a região."
        : "Nenhuma empresa ainda. Rode a descoberta para o Cérebro procurar quem consome esse serviço."}
    </Vazio>
  );
}

function CartaoLead({
  lead,
  ramos,
  aoExplicar,
  aoAbordar,
}: {
  lead: Lead;
  ramos: RamoAlvo[];
  aoExplicar: () => void;
  aoAbordar: () => void;
}) {
  const score = Number(lead.score);
  const nome = lead.razao_social ?? lead.nome_fantasia ?? "Empresa";
  const iniciais = nome
    .split(/\s+/)
    .filter((p) => p.length > 2)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();

  return (
    <motion.article
      variants={itemVariantes}
      whileHover={{ y: -3 }}
      transition={{ duration: 0.2, ease: EXPO }}
      className="realce-topo flex flex-col rounded-2xl border border-borda bg-superficie p-5 shadow-1 transition-shadow hover:shadow-2"
    >
      <header className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-marca-fraca text-xs font-semibold text-marca">
          {iniciais || "??"}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-texto" title={nome}>
            {nome}
          </h3>
          <p className="truncate text-xs text-texto-fraco">
            {lead.municipio ?? "—"}
            {lead.uf ? `/${lead.uf}` : ""}
          </p>
        </div>
        <span className="num shrink-0 rounded-md bg-superficie-2 px-2 py-1 text-xs font-semibold text-marca">
          {score.toFixed(0)}%
        </span>
      </header>

      <div className="mt-4 rounded-xl border border-positivo/20 bg-positivo-fraco/60 p-3">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-rotulo text-positivo">
          <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" aria-hidden>
            <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          </svg>
          Insight da IA
        </div>
        <p className="mt-1 text-xs leading-relaxed text-texto-medio">{insightDe(lead, ramos)}</p>
      </div>

      <dl className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-texto-fraco">
        <div className="flex items-center gap-1.5">
          <dt className="sr-only">Porte</dt>
          <dd>{rotuloPorte(lead.porte)}</dd>
        </div>
        {lead.cnpj && (
          <div className="flex items-center gap-1.5">
            <dt className="sr-only">CNPJ</dt>
            <dd className="num">{lead.cnpj}</dd>
          </div>
        )}
      </dl>

      <div className="mt-4 flex items-center gap-2">
        <Botao onClick={aoAbordar} tamanho="sm" className="flex-1">
          Iniciar abordagem com IA
        </Botao>
        <Botao variante="fantasma" tamanho="sm" onClick={aoExplicar}>
          por quê?
        </Botao>
      </div>
    </motion.article>
  );
}

/**
 * Frase curta e concreta sobre por que este lead interessa.
 *
 * NAO usa o fator de maior pontuacao. "Tem contato comercial" pesa 20 pontos e
 * seria o topo em quase todo lead — mas todo lead que chegou aqui tem contato,
 * entao dizer isso e repetir o obvio em todos os cartoes. Contato e
 * pre-requisito, nao insight.
 *
 * A ordem abaixo e por PODER DE DISTINCAO: o que diferencia esta empresa das
 * outras. O ramo vem primeiro porque e a promessa central do produto — achamos
 * quem CONSOME o seu servico, e o ramo e a prova disso.
 */
function insightDe(lead: Lead, ramos: RamoAlvo[]): string {
  const b = lead.score_breakdown ?? {};
  const c = (b.componentes ?? {}) as Record<string, number>;

  const ramo = lead.cnae_principal
    ? ramos.find((r) => r.codigo === lead.cnae_principal)
    : undefined;

  if (ramo && Number(c.aderencia_cnae ?? 0) > 0) {
    return `${ramo.descricao} — ramo que consome esse serviço de forma recorrente.`;
  }
  if (Number(c.intencao ?? 0) > 0) {
    return "Há sinal recente de intenção: a empresa demonstrou movimento nessa direção.";
  }
  if (Number(c.aderencia_texto ?? 0) > 0.3) {
    return "A descrição do negócio casa diretamente com o serviço que você oferece.";
  }
  if (Number(c.porte ?? 0) >= 0.9) {
    return `${rotuloPorte(lead.porte)}: estrutura para contratar de forma recorrente.`;
  }
  if (Number(c.reputacao ?? 0) >= 0.9) {
    return `Negócio ativo e bem avaliado em ${lead.municipio ?? "sua região"}.`;
  }
  if (Number(c.contato ?? 0) > 0) {
    return "Tem canal comercial público — dá para abordar hoje, sem intermediário.";
  }
  return `Empresa em ${lead.municipio ?? "sua região"} com perfil compatível.`;
}

function rotuloPorte(porte: string | null | undefined): string {
  const mapa: Record<string, string> = {
    mei: "MEI",
    me: "Microempresa",
    epp: "Pequeno porte",
    demais: "Médio ou grande",
    desconhecido: "Porte não informado",
  };
  return mapa[porte ?? "desconhecido"] ?? "Porte não informado";
}
