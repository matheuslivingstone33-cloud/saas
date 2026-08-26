import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { api, type NivelAutonomia, type Perfil } from "./lib/api";
import { Aviso, Badge, Carregando } from "./components/ui";
import { EXPO, paginaVariantes, useVariantes } from "./components/movimento";
import Abertura, { useAbertura } from "./components/Abertura";
import { ProvedorTema, TrocaTema } from "./components/tema";
import Onboarding from "./pages/Onboarding";
import Painel from "./pages/Painel";
import Campanhas from "./pages/Campanhas";
import Creditos from "./pages/Creditos";
import Conformidade from "./pages/Conformidade";

type Rota = "painel" | "campanhas" | "creditos" | "conformidade";

const ABAS: { chave: Rota; rotulo: string }[] = [
  { chave: "painel", rotulo: "Painel" },
  { chave: "campanhas", rotulo: "Campanhas" },
  { chave: "creditos", rotulo: "Créditos" },
  { chave: "conformidade", rotulo: "Conformidade" },
];

function rotaAtual(): Rota {
  const hash = window.location.hash.replace("#/", "") as Rota;
  return ABAS.some((a) => a.chave === hash) ? hash : "painel";
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
  // useAbertura e um hook: precisa ser chamado no topo, nunca dentro de
  // useState(...) — la ele so rodaria na primeira renderizacao e bagunçaria a
  // ordem dos hooks nas seguintes.
  const deveAbrir = useAbertura();
  const [aberturaFechada, setAberturaFechada] = useState(false);
  const abrindo = deveAbrir && !aberturaFechada;
  const variantes = useVariantes(paginaVariantes);

  const recarregar = useCallback(() => {
    api.perfil().then(setPerfil).catch((e) => setErro(String(e)));
  }, []);

  useEffect(recarregar, [recarregar, versao]);

  useEffect(() => {
    const aoMudar = () => setRota(rotaAtual());
    window.addEventListener("hashchange", aoMudar);
    return () => window.removeEventListener("hashchange", aoMudar);
  }, []);

  async function trocarAutonomia(nivel: NivelAutonomia) {
    try {
      await api.trocarAutonomia(nivel);
      setVersao((v) => v + 1);
    } catch (e) {
      setErro(String(e));
    }
  }

  if (abrindo) return <Abertura aoTerminar={() => setAberturaFechada(true)} />;
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
      {/* Luz de fundo do topo — some no tema claro por causa da opacidade baixa */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 overflow-hidden">
        <div className="aura left-1/2 h-64 w-[40rem] -translate-x-1/2 -translate-y-1/3" />
      </div>

      <header className="vidro sticky top-0 z-30 border-b border-borda">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-3.5">
          <motion.a
            href="#/painel"
            className="flex items-center gap-2.5"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            transition={{ duration: 0.15, ease: EXPO }}
          >
            <svg viewBox="0 0 64 64" className="h-8 w-8" aria-hidden>
              <circle cx="27" cy="27" r="15" fill="none" stroke="rgb(var(--cor-marca))" strokeWidth="5" />
              <line
                x1="38"
                y1="38"
                x2="53"
                y2="53"
                stroke="rgb(var(--cor-acento))"
                strokeWidth="5.5"
                strokeLinecap="round"
              />
              <circle cx="27" cy="27" r="4" fill="rgb(var(--cor-acento))" />
            </svg>
            <div className="leading-tight">
              <div className="font-marca text-lg tracking-tight text-texto">Prospector</div>
              <div className="num text-[11px] text-texto-fraco">
                {perfil.empresa ?? perfil.nome} · {perfil.saldo.creditos} créditos
              </div>
            </div>
          </motion.a>

          {!precisaOnboarding && (
            <nav className="ml-4 flex gap-0.5">
              {ABAS.map((a) => {
                const ativa = rota === a.chave;
                return (
                  <a
                    key={a.chave}
                    href={`#/${a.chave}`}
                    className={`relative rounded-lg px-3 py-1.5 text-sm transition-colors duration-200 ${
                      ativa ? "text-texto" : "text-texto-fraco hover:text-texto-medio"
                    }`}
                  >
                    {ativa && (
                      <motion.span
                        layoutId="aba-ativa"
                        className="absolute inset-0 rounded-lg bg-superficie-2 ring-1 ring-borda"
                        transition={{ duration: 0.3, ease: EXPO }}
                      />
                    )}
                    <span className="relative">{a.rotulo}</span>
                  </a>
                );
              })}
            </nav>
          )}

          <div className="ml-auto flex items-center gap-2.5">
            <div
              role="radiogroup"
              aria-label="Nível de autonomia"
              className="flex items-center gap-0.5 rounded-full border border-borda bg-superficie-2 p-0.5"
            >
              {(["assistido", "automatico"] as NivelAutonomia[]).map((n) => {
                const ativo = nivel === n;
                return (
                  <button
                    key={n}
                    role="radio"
                    aria-checked={ativo}
                    onClick={() => trocarAutonomia(n)}
                    title={
                      n === "assistido"
                        ? "Nada sai sem sua aprovação"
                        : "O agente dispara sozinho, dentro dos limites"
                    }
                    className={`relative rounded-full px-2.5 py-1 text-xs transition-colors duration-200 ${
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
            <TrocaTema />
            <Badge tom="neutro" ponto>
              tudo mock
            </Badge>
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
              <Onboarding
                perfil={perfil}
                aoConcluir={() => {
                  setForcarOnboarding(false);
                  setVersao((v) => v + 1);
                  window.location.hash = "#/campanhas";
                }}
              />
            ) : rota === "painel" ? (
              <Painel key={versao} />
            ) : rota === "campanhas" ? (
              <Campanhas nivel={nivel} />
            ) : rota === "creditos" ? (
              <Creditos aoMudar={() => setVersao((v) => v + 1)} />
            ) : (
              <Conformidade />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="mx-auto max-w-6xl px-6 pb-10 text-xs text-texto-fraco">
        Fases 0–6 rodam sem nenhuma chave de API.{" "}
        <button
          className="underline underline-offset-2 transition-colors hover:text-texto-medio"
          onClick={() => setForcarOnboarding(true)}
        >
          refazer onboarding
        </button>
      </footer>
    </div>
  );
}
