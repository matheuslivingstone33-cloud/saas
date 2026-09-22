import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { AO_EXPIRAR, api, sessao, type NivelAutonomia, type Perfil } from "./lib/api";
import { Aviso, Badge, Botao, Carregando } from "./components/ui";
import { EXPO, paginaVariantes, useVariantes } from "./components/movimento";
import Abertura, { useAbertura } from "./components/Abertura";
import { ProvedorTema, TrocaTema } from "./components/tema";
import Paleta, { usePaleta, type Comando } from "./components/Paleta";
import Entrada from "./pages/Entrada";
import Landing from "./pages/Landing";
import OnboardingChat from "./pages/OnboardingChat";
import Busca from "./pages/Busca";
import Descoberta from "./pages/Descoberta";
import Conversas from "./pages/Conversas";
import Painel from "./pages/Painel";
import Creditos from "./pages/Creditos";
import Conformidade from "./pages/Conformidade";

/**
 * Navegacao em tres passos, na ordem da jornada:
 *
 *   Busca  ->  Descoberta  ->  Conversas
 *   "quem  ->  "achei estas ->  "estou falando
 *   atendo?"    empresas"        com elas"
 *
 * Painel, Creditos e Conformidade sao importantes mas nao sao o caminho de
 * todo dia — vivem no menu da conta. Manter seis abas no topo diluiria o que
 * o produto faz.
 */

type Rota = "busca" | "descoberta" | "conversas" | "painel" | "creditos" | "conformidade";

const PRINCIPAIS: { chave: Rota; rotulo: string; icone: React.ReactNode }[] = [
  {
    chave: "busca",
    rotulo: "Busca",
    icone: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
        <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.9" />
        <path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    chave: "descoberta",
    rotulo: "Descoberta",
    icone: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.9" />
        <path d="M15.5 8.5l-2 5-5 2 2-5 5-2z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    chave: "conversas",
    rotulo: "Conversas",
    icone: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
        <path
          d="M20 15a2 2 0 0 1-2 2H8l-4 3V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
];

const CONTA: { chave: Rota; rotulo: string }[] = [
  { chave: "painel", rotulo: "Painel e métricas" },
  { chave: "creditos", rotulo: "Créditos e plano" },
  { chave: "conformidade", rotulo: "Conformidade" },
];

const TODAS: Rota[] = [...PRINCIPAIS.map((a) => a.chave), ...CONTA.map((a) => a.chave)];
const CHAVE_CAMPANHA = "prospector:campanha";
// Marca que o visitante ja passou da landing. Nao e autenticacao — e so
// memoria de navegacao, para nao mostrar a pagina de venda a cada carregamento.
const CHAVE_ENTROU = "prospector:entrou";

function rotaAtual(): Rota {
  const hash = window.location.hash.replace("#/", "") as Rota;
  return TODAS.includes(hash) ? hash : "busca";
}

export default function App() {
  return (
    <ProvedorTema>
      <Aplicacao />
    </ProvedorTema>
  );
}

function Aplicacao() {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [rota, setRota] = useState<Rota>(rotaAtual());
  const [erro, setErro] = useState<string | null>(null);
  const [forcarOnboarding, setForcarOnboarding] = useState(false);
  const [versao, setVersao] = useState(0);
  const [menuConta, setMenuConta] = useState(false);
  const [suporte, setSuporte] = useState(false);
  const [entrou, setEntrou] = useState<boolean>(() => {
    try {
      return localStorage.getItem(CHAVE_ENTROU) === "1";
    } catch {
      return false;
    }
  });
  // Desde a Etapa 8 passar da landing nao basta: e preciso ter sessao. Os dois
  // estados sao distintos de proposito — "ver a pagina inicial" no menu da
  // conta nao pode deslogar quem so quis reler a apresentacao.
  const [temSessao, setTemSessao] = useState<boolean>(() => sessao.ativa());
  // A campanha em foco sobrevive ao recarregamento: sem isso, atualizar a
  // pagina na Descoberta jogaria o usuario de volta para a Busca.
  const [campanha, setCampanha] = useState<string | null>(() => {
    try {
      return localStorage.getItem(CHAVE_CAMPANHA);
    } catch {
      return null;
    }
  });

  // useAbertura e um hook: precisa ser chamado no topo, nunca dentro de
  // useState(...) — la ele so rodaria na primeira renderizacao e bagunçaria a
  // ordem dos hooks nas seguintes.
  const deveAbrir = useAbertura();
  const [aberturaFechada, setAberturaFechada] = useState(false);
  const abrindo = deveAbrir && !aberturaFechada;
  const variantes = useVariantes(paginaVariantes);
  const paleta = usePaleta();

  const recarregar = useCallback(() => {
    if (!sessao.ativa()) return;
    api.perfil().then(setPerfil).catch((e) => setErro(String(e)));
  }, []);

  useEffect(recarregar, [recarregar, versao, temSessao]);

  useEffect(() => {
    const aoMudar = () => setRota(rotaAtual());
    window.addEventListener("hashchange", aoMudar);
    return () => window.removeEventListener("hashchange", aoMudar);
  }, []);

  // A sessao pode cair no meio do uso: o token de renovacao venceu, ou a conta
  // foi desativada. Sem isto a tela ficaria pedindo dados que o servidor recusa,
  // mostrando um erro atras do outro sem dizer o que fazer.
  useEffect(() => {
    const aoExpirar = () => {
      setTemSessao(false);
      setPerfil(null);
    };
    window.addEventListener(AO_EXPIRAR, aoExpirar);
    return () => window.removeEventListener(AO_EXPIRAR, aoExpirar);
  }, []);

  const irPara = useCallback((destino: Rota) => {
    window.location.hash = `#/${destino}`;
    setMenuConta(false);
  }, []);

  const entrar = useCallback(() => {
    setEntrou(true);
    try {
      localStorage.setItem(CHAVE_ENTROU, "1");
    } catch {
      /* sem localStorage: a landing reaparece no proximo carregamento */
    }
  }, []);

  const sair = useCallback(() => {
    sessao.limpar();
    setTemSessao(false);
    setPerfil(null);
    setMenuConta(false);
    setEntrou(false);
    try {
      localStorage.removeItem(CHAVE_ENTROU);
    } catch {
      /* nada a fazer */
    }
  }, []);

  const voltarParaLanding = useCallback(() => {
    setEntrou(false);
    setMenuConta(false);
    try {
      localStorage.removeItem(CHAVE_ENTROU);
    } catch {
      /* nada a fazer */
    }
  }, []);

  const escolherCampanha = useCallback((id: string) => {
    setCampanha(id);
    try {
      localStorage.setItem(CHAVE_CAMPANHA, id);
    } catch {
      /* localStorage indisponivel: a campanha vive so nesta sessao */
    }
  }, []);

  async function trocarAutonomia(nivel: NivelAutonomia) {
    try {
      await api.trocarAutonomia(nivel);
      setVersao((v) => v + 1);
    } catch (e) {
      setErro(String(e));
    }
  }

  const comandos: Comando[] = [
    ...PRINCIPAIS.map((a) => ({
      id: `ir-${a.chave}`,
      titulo: `Ir para ${a.rotulo}`,
      grupo: "Navegação",
      executar: () => irPara(a.chave),
    })),
    ...CONTA.map((a) => ({
      id: `ir-${a.chave}`,
      titulo: a.rotulo,
      grupo: "Conta",
      executar: () => irPara(a.chave),
    })),
    {
      id: "autonomia-assistido",
      titulo: "Autonomia: assistido (nada sai sem aprovar)",
      grupo: "Conta",
      executar: () => void trocarAutonomia("assistido"),
    },
    {
      id: "autonomia-automatico",
      titulo: "Autonomia: automático (o agente dispara sozinho)",
      grupo: "Conta",
      executar: () => void trocarAutonomia("automatico"),
    },
    {
      id: "refazer-onboarding",
      titulo: "Refazer onboarding",
      grupo: "Conta",
      executar: () => setForcarOnboarding(true),
    },
  ];

  if (abrindo) return <Abertura aoTerminar={() => setAberturaFechada(true)} />;
  if (!entrou) {
    return (
      <>
        <Landing aoComecar={entrar} aoSuporte={() => setSuporte(true)} />
        <AnimatePresence>
          {suporte && <PainelSuporte aoFechar={() => setSuporte(false)} />}
        </AnimatePresence>
      </>
    );
  }
  if (!temSessao) {
    return (
      <Entrada
        aoEntrar={() => {
          setTemSessao(true);
          setErro(null);
        }}
        aoVoltar={voltarParaLanding}
      />
    );
  }
  if (erro && !perfil)
    return (
      <div className="mx-auto max-w-2xl p-8">
        <Aviso tom="erro">{erro}</Aviso>
      </div>
    );
  if (!perfil)
    return (
      <div className="mx-auto max-w-6xl px-6 py-10">
        <Carregando />
      </div>
    );

  const precisaOnboarding = !perfil.onboarding_completo || forcarOnboarding;
  const nivel = perfil.assinatura.autonomy_level ?? "assistido";

  return (
    <div className="relative min-h-screen">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 overflow-hidden">
        <div className="aura left-1/2 h-64 w-[40rem] -translate-x-1/2 -translate-y-1/3" />
      </div>

      <header className="vidro sticky top-0 z-30 border-b border-borda">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-3">
          <motion.a
            href="#/busca"
            className="flex items-center gap-2.5"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            transition={{ duration: 0.15, ease: EXPO }}
          >
            <svg viewBox="0 0 64 64" className="h-8 w-8" aria-hidden>
              <circle cx="27" cy="27" r="15" fill="none" stroke="rgb(var(--cor-marca))" strokeWidth="5" />
              <line x1="38" y1="38" x2="53" y2="53" stroke="rgb(var(--cor-acento))" strokeWidth="5.5" strokeLinecap="round" />
              <circle cx="27" cy="27" r="4" fill="rgb(var(--cor-acento))" />
            </svg>
            <span className="font-marca text-lg tracking-tight text-texto">
              Prospector <span className="text-marca">AI</span>
            </span>
          </motion.a>

          {!precisaOnboarding && (
            <nav className="mx-auto flex gap-0.5 rounded-full border border-borda bg-superficie-2 p-1">
              {PRINCIPAIS.map((a) => {
                const ativa = rota === a.chave;
                return (
                  <a
                    key={a.chave}
                    href={`#/${a.chave}`}
                    className={`relative flex items-center gap-2 rounded-full px-4 py-1.5 text-sm transition-colors duration-200 ${
                      ativa ? "text-texto" : "text-texto-fraco hover:text-texto-medio"
                    }`}
                  >
                    {ativa && (
                      <motion.span
                        layoutId="aba-ativa"
                        className="absolute inset-0 rounded-full bg-superficie shadow-1 ring-1 ring-borda"
                        transition={{ duration: 0.3, ease: EXPO }}
                      />
                    )}
                    <span className="relative">{a.icone}</span>
                    <span className="relative">{a.rotulo}</span>
                  </a>
                );
              })}
            </nav>
          )}

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={paleta.abrir}
              title="Paleta de comandos"
              className="hidden items-center gap-2 rounded-full border border-borda bg-superficie-2 py-1 pl-2.5 pr-1.5 text-xs text-texto-fraco transition-colors hover:border-borda-forte hover:text-texto-medio sm:flex"
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" aria-hidden>
                <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
                <path d="M16.5 16.5L21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <kbd className="rounded border border-borda bg-superficie px-1.5 py-0.5 text-[10px]">Ctrl K</kbd>
            </button>

            <TrocaTema />

            <span className="hidden items-center gap-1.5 rounded-full border border-atencao/30 bg-atencao-fraco px-2.5 py-1 text-xs font-medium text-atencao sm:inline-flex">
              <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" aria-hidden>
                <path d="M5 17l2-9 5 4 5-4 2 9H5z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
              </svg>
              {perfil.assinatura.plano === "trial" ? "Plano Grátis" : perfil.assinatura.plano}
            </span>

            <MenuConta
              perfil={perfil}
              aberto={menuConta}
              alternar={() => setMenuConta((v) => !v)}
              irPara={irPara}
              nivel={nivel}
              trocarAutonomia={trocarAutonomia}
              refazerOnboarding={() => {
                setMenuConta(false);
                setForcarOnboarding(true);
              }}
              verLanding={voltarParaLanding}
              sair={sair}
            />
          </div>
        </div>
      </header>

      <main className="relative mx-auto max-w-6xl px-6 py-8">
        <AnimatePresence mode="wait">
          {erro && (
            <motion.div
              key="erro"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-6 overflow-hidden"
            >
              <Aviso tom="erro">{erro}</Aviso>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          <motion.div
            key={precisaOnboarding ? "onboarding" : rota}
            variants={variantes}
            initial="oculto"
            animate="visivel"
            exit="saida"
          >
            {precisaOnboarding ? (
              <OnboardingChat
                perfil={perfil}
                aoConcluir={() => {
                  setForcarOnboarding(false);
                  setVersao((v) => v + 1);
                  irPara("busca");
                }}
              />
            ) : rota === "busca" ? (
              <Busca
                perfil={perfil}
                aoDescobrir={(id) => {
                  escolherCampanha(id);
                  irPara("descoberta");
                }}
              />
            ) : rota === "descoberta" ? (
              <Descoberta
                campanhaId={campanha}
                aoAbordar={() => irPara("conversas")}
                aoNovaBusca={() => irPara("busca")}
              />
            ) : rota === "conversas" ? (
              <Conversas nivel={nivel} />
            ) : rota === "painel" ? (
              <Painel key={versao} />
            ) : rota === "creditos" ? (
              <Creditos aoMudar={() => setVersao((v) => v + 1)} />
            ) : (
              <Conformidade />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <Paleta aberta={paleta.aberta} fechar={paleta.fechar} comandos={comandos} />

      <footer className="mx-auto max-w-6xl px-6 pb-10 text-xs text-texto-fraco">
        Prospecção 100% B2B em conformidade com a LGPD · todos os provedores em modo mock
      </footer>
    </div>
  );
}

function MenuConta({
  perfil,
  aberto,
  alternar,
  irPara,
  nivel,
  trocarAutonomia,
  refazerOnboarding,
  verLanding,
  sair,
}: {
  perfil: Perfil;
  aberto: boolean;
  alternar: () => void;
  irPara: (r: Rota) => void;
  nivel: NivelAutonomia;
  trocarAutonomia: (n: NivelAutonomia) => void;
  refazerOnboarding: () => void;
  verLanding: () => void;
  sair: () => void;
}) {
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    function aoClicarFora(e: MouseEvent) {
      if (caixa.current && !caixa.current.contains(e.target as Node)) alternar();
    }
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") alternar();
    }
    document.addEventListener("mousedown", aoClicarFora);
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("mousedown", aoClicarFora);
      document.removeEventListener("keydown", aoTeclar);
    };
  }, [aberto, alternar]);

  const iniciais =
    (perfil.empresa ?? perfil.nome ?? "")
      .split(/\s+/)
      .filter((p) => p.length > 1)
      .slice(0, 2)
      .map((p) => p[0])
      .join("")
      .toUpperCase() || "??";

  return (
    <div className="relative" ref={caixa}>
      <button
        onClick={alternar}
        aria-haspopup="menu"
        aria-expanded={aberto}
        aria-label="Menu da conta"
        className="flex h-8 w-8 items-center justify-center rounded-full border border-borda bg-superficie-2 text-[11px] font-semibold text-texto-medio transition-colors hover:border-borda-forte hover:text-texto"
      >
        {iniciais}
      </button>

      <AnimatePresence>
        {aberto && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.99 }}
            transition={{ duration: 0.18, ease: EXPO }}
            className="realce-topo absolute right-0 top-10 z-40 w-64 overflow-hidden rounded-xl border border-borda bg-superficie shadow-3"
          >
            <div className="border-b border-borda px-4 py-3">
              <p className="truncate text-sm font-medium text-texto">
                {perfil.empresa ?? perfil.nome}
              </p>
              <p className="num text-xs text-texto-fraco">
                {perfil.saldo.creditos} créditos · {perfil.assinatura.plano}
              </p>
            </div>

            <div className="border-b border-borda p-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-rotulo text-texto-fraco">
                Autonomia
              </p>
              <div className="flex items-center gap-0.5 rounded-full border border-borda bg-superficie-2 p-0.5">
                {(["assistido", "automatico"] as NivelAutonomia[]).map((n) => {
                  const ativo = nivel === n;
                  return (
                    <button
                      key={n}
                      onClick={() => trocarAutonomia(n)}
                      title={
                        n === "assistido"
                          ? "Nada sai sem sua aprovação"
                          : "O agente dispara sozinho, dentro dos limites"
                      }
                      className={`relative flex-1 rounded-full px-2 py-1 text-xs transition-colors ${
                        ativo ? "text-white" : "text-texto-fraco hover:text-texto-medio"
                      }`}
                    >
                      {ativo && (
                        <motion.span
                          layoutId="autonomia-ativa"
                          className="absolute inset-0 rounded-full bg-marca"
                          transition={{ duration: 0.3, ease: EXPO }}
                        />
                      )}
                      <span className="relative">{n}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <nav className="p-1.5">
              {CONTA.map((item) => (
                <button
                  key={item.chave}
                  role="menuitem"
                  onClick={() => irPara(item.chave)}
                  className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm text-texto-medio transition-colors hover:bg-superficie-2 hover:text-texto"
                >
                  {item.rotulo}
                </button>
              ))}
              <button
                role="menuitem"
                onClick={refazerOnboarding}
                className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm text-texto-fraco transition-colors hover:bg-superficie-2 hover:text-texto"
              >
                Refazer onboarding
              </button>
              <button
                role="menuitem"
                onClick={verLanding}
                className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm text-texto-fraco transition-colors hover:bg-superficie-2 hover:text-texto"
              >
                Ver a página inicial
              </button>
              <button
                role="menuitem"
                onClick={sair}
                className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm text-texto-fraco transition-colors hover:bg-superficie-2 hover:text-texto"
              >
                Sair da conta
              </button>
            </nav>

            <div className="border-t border-borda px-4 py-2">
              <Badge tom="neutro" ponto>
                tudo mock
              </Badge>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}


/**
 * Suporte.
 *
 * O plano e suporte por WhatsApp com IA — mandando audio, soando natural, para
 * o cliente ver a qualidade da automacao na pratica. Isso ainda nao existe.
 *
 * Enquanto nao existe, a tela DIZ que nao existe. Um botao de suporte que abre
 * um vazio, ou que promete atendimento que ninguem vai responder, queima
 * confianca exatamente no momento em que a pessoa precisou de ajuda.
 */
function PainelSuporte({ aoFechar }: { aoFechar: () => void }) {
  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-fundo/70 p-4 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={aoFechar}
    >
      <motion.div
        role="dialog"
        aria-label="Suporte"
        onClick={(e) => e.stopPropagation()}
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8 }}
        transition={{ duration: 0.3, ease: EXPO }}
        className="realce-topo w-full max-w-md rounded-2xl border border-borda bg-superficie p-6 shadow-3"
      >
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-positivo-fraco">
            <svg viewBox="0 0 24 24" className="h-5 w-5 text-positivo" fill="currentColor" aria-hidden>
              <path d="M12 2a10 10 0 0 0-8.7 15l-1.2 4.4 4.5-1.2A10 10 0 1 0 12 2zm0 2a8 8 0 1 1-4.2 14.8l-.3-.2-2.3.6.6-2.2-.2-.4A8 8 0 0 1 12 4z" />
            </svg>
          </span>
          <div>
            <h2 className="text-base font-semibold text-texto">Suporte por WhatsApp</h2>
            <p className="text-xs text-texto-fraco">com um agente de IA</p>
          </div>
        </div>

        <p className="mt-4 text-sm leading-relaxed text-texto-medio">
          O suporte vai ser feito por IA no WhatsApp — respondendo por texto e por
          áudio, para você ver na prática a qualidade da automação que o produto usa.
        </p>

        <div className="mt-4 rounded-xl border border-atencao/30 bg-atencao-fraco p-3">
          <p className="text-sm text-atencao">
            <strong>Ainda não está no ar.</strong> O canal será ligado junto com os
            provedores reais. Não vamos abrir um número que ninguém atende.
          </p>
        </div>

        <p className="mt-4 text-xs leading-relaxed text-texto-fraco">
          Quando entrar, o agente vai se identificar como IA logo na primeira mensagem —
          exigência do Marco da IA, e o que separa "nossa automação é boa" de um
          problema jurídico.
        </p>

        <div className="mt-5 flex justify-end">
          <Botao onClick={aoFechar}>entendi</Botao>
        </div>
      </motion.div>
    </motion.div>
  );
}
