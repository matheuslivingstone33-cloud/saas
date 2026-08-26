import { useCallback, useEffect, useState } from "react";
import { api, type NivelAutonomia, type Perfil } from "./lib/api";
import { Aviso, Badge, Carregando } from "./components/ui";
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
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [rota, setRota] = useState<Rota>(rotaAtual());
  const [erro, setErro] = useState<string | null>(null);
  const [forcarOnboarding, setForcarOnboarding] = useState(false);
  const [versao, setVersao] = useState(0);

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

  if (erro && !perfil) return <div className="p-8"><Aviso tom="erro">{erro}</Aviso></div>;
  if (!perfil) return <Carregando />;

  const precisaOnboarding = !perfil.onboarding_completo || forcarOnboarding;
  const nivel = perfil.assinatura.autonomy_level ?? "assistido";

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <img src="/assets/logo.svg" alt="" className="h-9 w-9" />
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Prospector AI</h1>
            <p className="text-xs text-slate-500">
              {perfil.empresa ?? perfil.nome} · {perfil.saldo.creditos} créditos
            </p>
          </div>

          {!precisaOnboarding && (
            <nav className="ml-6 flex gap-1">
              {ABAS.map((a) => (
                <a
                  key={a.chave}
                  href={`#/${a.chave}`}
                  className={`rounded-md px-3 py-1.5 text-sm transition ${
                    rota === a.chave
                      ? "bg-slate-100 font-medium text-slate-900"
                      : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {a.rotulo}
                </a>
              ))}
            </nav>
          )}

          <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5">
              {(["assistido", "automatico"] as NivelAutonomia[]).map((n) => (
                <button
                  key={n}
                  onClick={() => trocarAutonomia(n)}
                  title={
                    n === "assistido"
                      ? "Nada sai sem sua aprovação"
                      : "O agente dispara sozinho, dentro dos limites"
                  }
                  className={`rounded px-2.5 py-1 text-xs transition ${
                    nivel === n
                      ? "bg-marca-500 text-white"
                      : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
            <Badge tom="mock">tudo mock</Badge>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {erro && (
          <div className="mb-6">
            <Aviso tom="erro">{erro}</Aviso>
          </div>
        )}

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
      </main>

      <footer className="mx-auto max-w-6xl px-6 pb-10 text-xs text-slate-400">
        Fases 0–6 rodam sem nenhuma chave de API.{" "}
        <button className="underline" onClick={() => setForcarOnboarding(true)}>
          refazer onboarding
        </button>
      </footer>
    </div>
  );
}
