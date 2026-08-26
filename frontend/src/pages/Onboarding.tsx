import { useState } from "react";
import { api, type NivelAutonomia, type Perfil } from "../lib/api";
import { Aviso, Botao, Campo, Card } from "../components/ui";

/**
 * Onboarding em 3 passos. O passo 2 e o coracao do produto: mostrar, ANTES de
 * gastar qualquer credito, quais ramos o Cerebro entendeu que compram o
 * servico — e quais ele descartou por serem concorrentes.
 */
export default function Onboarding({
  perfil,
  aoConcluir,
}: {
  perfil: Perfil;
  aoConcluir: () => void;
}) {
  const [passo, setPasso] = useState(1);
  const [empresa, setEmpresa] = useState(perfil.empresa ?? "");
  const [servico, setServico] = useState(perfil.servico_padrao ?? "");
  const [regiao, setRegiao] = useState("Fortaleza, CE");
  const [nivel, setNivel] = useState<NivelAutonomia>(
    perfil.assinatura.autonomy_level ?? "assistido",
  );
  const [previa, setPrevia] = useState<Awaited<ReturnType<typeof api.expandir>> | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function verPrevia() {
    setOcupado(true);
    setErro(null);
    try {
      await api.atualizarPerfil({ empresa, servico_padrao: servico } as never);
      setPrevia(await api.expandir(servico, regiao));
      setPasso(2);
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  async function concluir() {
    setOcupado(true);
    setErro(null);
    try {
      await api.trocarAutonomia(nivel);
      await api.criarCampanha({
        nome: `${servico.slice(0, 40)} — ${regiao}`,
        servico,
        regiao,
        meta_leads: 25,
      });
      aoConcluir();
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {["Seu serviço", "O que o Cérebro entendeu", "Nível de autonomia"].map((t, i) => (
          <span
            key={t}
            className={`rounded-full px-3 py-1 ${
              passo === i + 1
                ? "bg-marca-500 text-white"
                : passo > i + 1
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {i + 1}. {t}
          </span>
        ))}
      </div>

      {erro && <Aviso tom="erro">{erro}</Aviso>}

      {passo === 1 && (
        <Card titulo="Passo 1 — o que você faz">
          <div className="space-y-4">
            <Campo rotulo="Nome da sua empresa" valor={empresa} onChange={setEmpresa} placeholder="Refrigeração Ceará Serviços" />
            <Campo
              rotulo="Descreva o serviço que você presta"
              valor={servico}
              onChange={setServico}
              multiline
              placeholder="instalação e manutenção preventiva de ar condicionado para empresas"
              ajuda="Escreva como você explicaria para um cliente. O Cérebro cuida do resto."
            />
            <Campo rotulo="Região de atuação" valor={regiao} onChange={setRegiao} placeholder="Fortaleza, CE" />
            <div className="flex justify-end">
              <Botao onClick={verPrevia} disabled={ocupado || servico.length < 10 || !empresa}>
                {ocupado ? "analisando..." : "ver o que o Cérebro entendeu"}
              </Botao>
            </div>
          </div>
        </Card>
      )}

      {passo === 2 && previa && (
        <Card titulo="Passo 2 — quem compra o seu serviço">
          <p className="mb-4 text-sm text-slate-600">{previa.justificativa}</p>

          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Ramos que vamos procurar
          </h3>
          <ul className="mb-5 space-y-1.5">
            {previa.ramos.map((r) => (
              <li key={r.codigo} className="flex items-center gap-3 text-sm">
                <span className="w-16 shrink-0 font-mono text-xs text-slate-400">{r.codigo}</span>
                <span className="flex-1 text-slate-700">{r.descricao}</span>
                <span className="tabular-nums text-xs text-slate-400">
                  aderência {(r.peso * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>

          {previa.excluidos_como_concorrente.length > 0 && (
            <Aviso tom="info">
              Descartamos {previa.excluidos_como_concorrente.length} ramo(s) por serem{" "}
              <strong>concorrentes</strong> (fazem o mesmo que você):{" "}
              {previa.excluidos_como_concorrente.join(", ")}.
            </Aviso>
          )}

          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Termos de busca
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {previa.termos.map((t) => (
                <span key={t} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                  {t}
                </span>
              ))}
            </div>
          </div>

          <div className="mt-6 flex justify-between">
            <Botao variante="secundario" onClick={() => setPasso(1)}>
              voltar
            </Botao>
            <Botao onClick={() => setPasso(3)}>faz sentido, continuar</Botao>
          </div>
        </Card>
      )}

      {passo === 3 && (
        <Card titulo="Passo 3 — quanto de autonomia você dá ao agente">
          <div className="grid gap-4 md:grid-cols-2">
            {(
              [
                {
                  valor: "assistido" as NivelAutonomia,
                  titulo: "Assistido",
                  descricao:
                    "O agente descobre, qualifica e escreve. Nada sai sem você aprovar, uma mensagem por vez.",
                  para: "Recomendado para começar.",
                },
                {
                  valor: "automatico" as NivelAutonomia,
                  titulo: "Automático",
                  descricao:
                    "O agente dispara sozinho, respeitando teto diário, opt-out e todos os guardrails.",
                  para: "Quando você já confiar no que ele escreve.",
                },
              ] as const
            ).map((opcao) => (
              <button
                key={opcao.valor}
                onClick={() => setNivel(opcao.valor)}
                className={`rounded-lg border p-4 text-left transition ${
                  nivel === opcao.valor
                    ? "border-marca-500 bg-marca-50 ring-1 ring-marca-500"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="font-medium text-slate-900">{opcao.titulo}</div>
                <p className="mt-1 text-sm text-slate-600">{opcao.descricao}</p>
                <p className="mt-2 text-xs text-slate-400">{opcao.para}</p>
              </button>
            ))}
          </div>

          <Aviso tom="atencao">
            Você pode trocar de nível a qualquer momento. A troca é registrada na trilha de
            auditoria — é uma decisão com consequência legal.
          </Aviso>

          <div className="mt-6 flex justify-between">
            <Botao variante="secundario" onClick={() => setPasso(2)}>
              voltar
            </Botao>
            <Botao onClick={concluir} disabled={ocupado}>
              {ocupado ? "criando..." : "criar minha primeira campanha"}
            </Botao>
          </div>
        </Card>
      )}
    </div>
  );
}
