import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Expansao, type NivelAutonomia, type Perfil } from "../lib/api";
import { EXPO } from "../components/movimento";
import { Aviso, Badge, Botao } from "../components/ui";

/**
 * Onboarding por conversa.
 *
 * Substitui o formulario. A diferenca nao e estetica: um formulario pede que o
 * usuario traduza o negocio dele para os campos QUE NOS escolhemos; a conversa
 * deixa ele descrever com as palavras dele e nos traduzimos.
 *
 * O momento que sustenta a tela e o passo "entendi": a IA mostra os ramos que
 * vai procurar ANTES de procurar. Isso vem do Cerebro de verdade
 * (`/v1/cerebro/expandir`), nao de texto ensaiado — se o entendimento estiver
 * errado, o usuario corrige na hora, antes de gastar consulta paga.
 */

type Autor = "ia" | "usuario";

type Fala = {
  id: number;
  autor: Autor;
  texto: string;
  /** Renderizado abaixo do balao — usado para mostrar os ramos entendidos. */
  extra?: React.ReactNode;
};

type Passo =
  | "tipo"
  | "nome_empresa"
  | "servico"
  | "regiao"
  | "analisando"
  | "confirmar"
  | "concluido";

const ATRASO_IA = 550;

export default function OnboardingChat({
  perfil,
  aoConcluir,
}: {
  perfil: Perfil;
  aoConcluir: () => void;
}) {
  const [falas, setFalas] = useState<Fala[]>([]);
  const [passo, setPasso] = useState<Passo>("tipo");
  const [digitando, setDigitando] = useState(false);
  const [entrada, setEntrada] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const [ehEmpresa, setEhEmpresa] = useState<boolean | null>(null);
  const [nomeEmpresa, setNomeEmpresa] = useState("");
  const [servico, setServico] = useState("");
  const [expansao, setExpansao] = useState<Expansao | null>(null);
  const [autonomia, setAutonomia] = useState<NivelAutonomia>("assistido");

  const contador = useRef(0);
  const fim = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLInputElement>(null);

  const dizer = useCallback((texto: string, extra?: React.ReactNode) => {
    setDigitando(true);
    // A pausa nao e enfeite: sem ela as falas aparecem todas de uma vez e a
    // tela deixa de parecer conversa. Com ela, da tempo de ler.
    setTimeout(() => {
      contador.current += 1;
      setFalas((f) => [...f, { id: contador.current, autor: "ia", texto, extra }]);
      setDigitando(false);
    }, ATRASO_IA);
  }, []);

  const responder = useCallback((texto: string) => {
    contador.current += 1;
    setFalas((f) => [...f, { id: contador.current, autor: "usuario", texto }]);
  }, []);

  // Abertura.
  useEffect(() => {
    dizer(
      "Oi! Sou o agente do Prospector. Vou configurar sua busca por clientes — " +
        "leva menos de um minuto. Primeiro: você é autônomo ou tem empresa?",
    );
  }, [dizer]);

  useEffect(() => {
    fim.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [falas.length, digitando]);

  useEffect(() => {
    if (["nome_empresa", "servico", "regiao"].includes(passo)) {
      setTimeout(() => campo.current?.focus(), ATRASO_IA + 80);
    }
  }, [passo]);

  function escolherTipo(empresa: boolean) {
    setEhEmpresa(empresa);
    responder(empresa ? "Tenho empresa" : "Sou autônomo");
    if (empresa) {
      dizer("Qual o nome da sua empresa?");
      setPasso("nome_empresa");
    } else {
      dizer("Me conta em uma ou duas linhas o que o seu negócio faz.");
      setPasso("servico");
    }
  }

  async function enviarTexto() {
    const texto = entrada.trim();
    if (!texto) return;
    setEntrada("");
    responder(texto);

    if (passo === "nome_empresa") {
      setNomeEmpresa(texto);
      dizer(`Me conta em uma ou duas linhas o que a ${texto} faz.`);
      setPasso("servico");
      return;
    }

    if (passo === "servico") {
      setServico(texto);
      dizer("Em que cidade e estado você atende? (ex.: Fortaleza, CE)");
      setPasso("regiao");
      return;
    }

    if (passo === "regiao") {
      setPasso("analisando");
      await analisar(servico, texto);
    }
  }

  /** O passo que da credibilidade: mostrar o que foi entendido, com os ramos. */
  async function analisar(servicoTexto: string, regiaoTexto: string) {
    setDigitando(true);
    setErro(null);
    try {
      const resultado = await api.expandir(servicoTexto, regiaoTexto);
      setExpansao(resultado);
      setDigitando(false);

      const ramos = resultado.ramos.slice(0, 6);
      dizer(
        `Entendi. Vou procurar empresas que CONSOMEM esse serviço em ${regiaoTexto} — ` +
          `não concorrentes suas.`,
        <div className="mt-3 space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {ramos.map((r) => (
              <span
                key={r.codigo}
                title={`CNAE ${r.codigo} · afinidade ${(r.peso * 100).toFixed(0)}`}
                className="inline-flex items-center gap-1.5 rounded-md border border-borda bg-superficie px-2 py-1 text-[11px] text-texto-medio"
              >
                <span className="max-w-[15rem] truncate">{r.descricao}</span>
                <span className="num text-marca">{(r.peso * 100).toFixed(0)}</span>
              </span>
            ))}
          </div>
          {resultado.excluidos_como_concorrente.length > 0 && (
            <p className="text-xs text-texto-fraco">
              Descartei {resultado.excluidos_como_concorrente.length} ramo
              {resultado.excluidos_como_concorrente.length === 1 ? "" : "s"} por serem
              concorrentes seus.
            </p>
          )}
        </div>,
      );

      setTimeout(() => {
        dizer(
          "Última coisa: quem aperta o botão de enviar? Eu posso preparar as mensagens " +
            "e deixar para você aprovar, ou disparar sozinho dentro dos limites.",
        );
        setPasso("confirmar");
      }, ATRASO_IA + 700);
    } catch (e) {
      setDigitando(false);
      setErro(String(e));
      dizer("Deu um problema ao analisar. Quer tentar de novo?");
      setPasso("regiao");
    }
  }

  async function concluir(nivel: NivelAutonomia) {
    setAutonomia(nivel);
    responder(nivel === "assistido" ? "Eu aprovo antes de enviar" : "Pode disparar sozinho");
    setDigitando(true);
    setErro(null);
    try {
      // `onboarding_completo` e DERIVADO no backend (empresa AND servico_padrao),
      // nao um campo gravavel. Enviar o booleano seria codigo morto dando a
      // impressao de funcionar; o que conclui o onboarding e preencher os dois
      // campos abaixo.
      await api.atualizarPerfil({
        empresa: ehEmpresa ? nomeEmpresa : perfil.nome,
        servico_padrao: servico,
      });
      await api.trocarAutonomia(nivel);
      setDigitando(false);
      dizer("Pronto! Configurado. Vamos encontrar seus clientes.");
      setPasso("concluido");
      setTimeout(aoConcluir, 1400);
    } catch (e) {
      setDigitando(false);
      setErro(String(e));
    }
  }

  const esperaTexto = ["nome_empresa", "servico", "regiao"].includes(passo);

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-texto sm:text-4xl">
          Me conte sobre sua empresa
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-texto-medio">
          Precisamos dessas informações para encontrar os melhores clientes para você.
        </p>
      </header>

      <section className="realce-topo flex min-h-[26rem] flex-col overflow-hidden rounded-2xl border border-borda bg-superficie shadow-2">
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <AnimatePresence initial={false}>
            {falas.map((f) => (
              <Balao key={f.id} fala={f} />
            ))}
          </AnimatePresence>

          {digitando && <Digitando />}

          {erro && <Aviso tom="erro">{erro}</Aviso>}

          <div ref={fim} />
        </div>

        <footer className="border-t border-borda p-4">
          {passo === "tipo" && !digitando && (
            <div className="flex flex-wrap gap-2">
              <Botao onClick={() => escolherTipo(false)} variante="secundario">
                Sou autônomo
              </Botao>
              <Botao onClick={() => escolherTipo(true)} variante="secundario">
                Tenho empresa
              </Botao>
            </div>
          )}

          {esperaTexto && (
            <div className="flex items-center gap-2">
              <input
                ref={campo}
                value={entrada}
                onChange={(e) => setEntrada(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void enviarTexto()}
                placeholder={
                  passo === "nome_empresa"
                    ? "Nome da empresa"
                    : passo === "servico"
                      ? "Ex.: instalo e faço manutenção de ar-condicionado"
                      : "Ex.: Fortaleza, CE"
                }
                className="flex-1 rounded-lg border border-borda bg-superficie-2 px-3 py-2.5 text-sm text-texto outline-none transition-all focus:border-marca focus:bg-superficie focus:ring-4 focus:ring-marca/12"
              />
              <Botao onClick={() => void enviarTexto()} disabled={!entrada.trim()}>
                enviar
              </Botao>
            </div>
          )}

          {passo === "analisando" && (
            <p className="text-center text-xs text-texto-fraco">analisando seu negócio…</p>
          )}

          {passo === "confirmar" && !digitando && (
            <div className="flex flex-wrap gap-2">
              <Botao onClick={() => void concluir("assistido")}>
                Eu aprovo antes de enviar
              </Botao>
              <Botao variante="secundario" onClick={() => void concluir("automatico")}>
                Pode disparar sozinho
              </Botao>
            </div>
          )}

          {passo === "concluido" && (
            <p className="text-center text-xs text-positivo">configuração salva</p>
          )}
        </footer>
      </section>

      {expansao && passo !== "concluido" && (
        <p className="mt-4 text-center text-xs text-texto-fraco">
          Errei o entendimento?{" "}
          <button
            className="underline underline-offset-2 hover:text-texto-medio"
            onClick={() => {
              setExpansao(null);
              dizer("Sem problema. Descreva o serviço de novo, com outras palavras.");
              setPasso("servico");
            }}
          >
            descrever de outro jeito
          </button>
        </p>
      )}

      <p className="mt-6 text-center text-xs text-texto-fraco">
        {autonomia === "assistido" ? (
          <Badge tom="acento">nada sai sem sua aprovação</Badge>
        ) : (
          <Badge tom="marca">o agente dispara dentro dos limites</Badge>
        )}
      </p>
    </div>
  );
}

function Balao({ fala }: { fala: Fala }) {
  const daIA = fala.autor === "ia";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EXPO }}
      className={daIA ? "flex gap-3" : "flex justify-end"}
    >
      {daIA && (
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-marca-fraca">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-marca" fill="none" aria-hidden>
            <path
              d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      )}
      <div className={daIA ? "max-w-[85%]" : "max-w-[80%]"}>
        <div
          className={
            daIA
              ? "rounded-2xl rounded-tl-sm border border-borda bg-superficie-2 px-4 py-2.5"
              : "rounded-2xl rounded-tr-sm bg-marca px-4 py-2.5"
          }
        >
          <p className={`text-sm leading-relaxed ${daIA ? "text-texto-medio" : "text-white"}`}>
            {fala.texto}
          </p>
          {fala.extra}
        </div>
      </div>
    </motion.div>
  );
}

function Digitando() {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-marca-fraca">
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-marca" fill="none" aria-hidden>
          <path
            d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-borda bg-superficie-2 px-4 py-3.5">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-texto-fraco"
            animate={{ opacity: [0.25, 1, 0.25], y: [0, -2, 0] }}
            transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.15 }}
          />
        ))}
      </div>
    </div>
  );
}
