import { motion } from "framer-motion";
import { useState } from "react";
import { api, type Lead, type ResultadoConversa } from "../lib/api";
import { EXPO } from "./movimento";
import { Aviso, Badge, Botao } from "./ui";
import Portal from "./Portal";

/**
 * Simulador de resposta do lead. SÓ EXISTE EM MODO MOCK.
 *
 * O produto inteiro foi construído para rodar sem chave de API — a conversa
 * não podia ser a exceção. Sem isto, o Motor 4 só seria testável depois de
 * ligar provedor pago, e ninguém consegue avaliar um motor que não pode rodar.
 *
 * Os exemplos não são decorativos: cada um exercita um caminho DIFERENTE do
 * motor, inclusive os três que fazem ele se calar. É a forma mais rápida de
 * alguém entender que "não responder" também é comportamento.
 */

const EXEMPLOS: { rotulo: string; texto: string; nota: string; tom: string }[] = [
  {
    rotulo: "Interesse",
    texto: "Tenho interesse sim, me manda mais detalhes. Qual o custo?",
    nota: "gera resposta e marca o lead como quente",
    tom: "positivo",
  },
  {
    rotulo: "Dúvida",
    texto: "Vocês atendem também manutenção de câmara fria?",
    nota: "gera resposta",
    tom: "acento",
  },
  {
    rotulo: "Objeção",
    texto: "Está caro para o nosso momento agora.",
    nota: "gera resposta sem inventar preço",
    tom: "atencao",
  },
  {
    rotulo: "Recusa",
    texto: "Não tenho interesse, obrigado.",
    nota: "encerra sem insistir",
    tom: "neutro",
  },
  {
    rotulo: "Quer uma pessoa",
    texto: "Quero falar com uma pessoa, por favor.",
    nota: "devolve para humano, mesmo no automático",
    tom: "marca",
  },
  {
    rotulo: "Pede descadastro",
    texto: "Por favor me tire da lista, não quero receber mais.",
    nota: "registra opt-out e para para sempre",
    tom: "perigo",
  },
];

export default function SimularResposta({
  lead,
  aoFechar,
  aoResponder,
}: {
  lead: Lead;
  aoFechar: () => void;
  aoResponder: () => void;
}) {
  const [texto, setTexto] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoConversa | null>(null);

  async function enviar(corpo: string) {
    const conteudo = corpo.trim();
    if (!conteudo || ocupado) return;
    setOcupado(true);
    setErro(null);
    try {
      const r = await api.simularResposta(lead.id, conteudo);
      setResultado(r);
      aoResponder();
    } catch (e) {
      setErro(String(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Portal>
      <motion.div
        className="fixed inset-0 z-40 flex items-center justify-center bg-fundo/75 p-4 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={aoFechar}
      >
        <motion.section
          role="dialog"
          aria-label="Simular resposta do lead"
          onClick={(e) => e.stopPropagation()}
          initial={{ opacity: 0, y: 18, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.32, ease: EXPO }}
          className="realce-topo w-full max-w-lg overflow-hidden rounded-2xl border border-borda bg-superficie shadow-3"
        >
          <header className="border-b border-borda px-5 py-3.5">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-texto">Simular resposta</h2>
              <Badge tom="neutro">só em modo mock</Badge>
            </div>
            <p className="mt-1 text-xs text-texto-fraco">
              Como se {lead.razao_social ?? lead.nome_fantasia} respondesse agora. Com
              provedor real, a resposta chega pelo webhook.
            </p>
          </header>

          <div className="max-h-[60vh] overflow-y-auto p-5">
            {resultado ? (
              <Resultado resultado={resultado} />
            ) : (
              <>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-rotulo text-texto-fraco">
                  Escolha um caminho
                </p>
                <div className="space-y-1.5">
                  {EXEMPLOS.map((ex) => (
                    <button
                      key={ex.rotulo}
                      onClick={() => void enviar(ex.texto)}
                      disabled={ocupado}
                      className="flex w-full items-start gap-3 rounded-lg border border-borda bg-superficie-2 p-3 text-left transition-colors hover:border-borda-forte disabled:opacity-50"
                    >
                      <span className="shrink-0">
                        <Badge tom={ex.tom}>{ex.rotulo}</Badge>
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm text-texto-medio">“{ex.texto}”</span>
                        <span className="mt-0.5 block text-xs text-texto-fraco">{ex.nota}</span>
                      </span>
                    </button>
                  ))}
                </div>

                <div className="mt-4 border-t border-borda pt-4">
                  <textarea
                    value={texto}
                    onChange={(e) => setTexto(e.target.value)}
                    placeholder="…ou escreva a resposta do lead com suas palavras"
                    className="min-h-[4.5rem] w-full resize-y rounded-lg border border-borda bg-superficie-2 p-3 text-sm text-texto outline-none transition-all focus:border-marca focus:bg-superficie focus:ring-4 focus:ring-marca/12"
                  />
                  <div className="mt-2 flex justify-end">
                    <Botao
                      onClick={() => void enviar(texto)}
                      disabled={!texto.trim()}
                      carregando={ocupado}
                    >
                      enviar como o lead
                    </Botao>
                  </div>
                </div>
              </>
            )}

            {erro && (
              <div className="mt-4">
                <Aviso tom="erro">{erro}</Aviso>
              </div>
            )}
          </div>

          <footer className="flex justify-end border-t border-borda px-5 py-3">
            <Botao variante={resultado ? "primario" : "secundario"} onClick={aoFechar}>
              {resultado ? "ver a conversa" : "cancelar"}
            </Botao>
          </footer>
        </motion.section>
      </motion.div>
    </Portal>
  );
}

function Resultado({ resultado }: { resultado: ResultadoConversa }) {
  const respondeu = resultado.respondeu || resultado.aguardando_aprovacao;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EXPO }}
      className="space-y-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-texto-fraco">o motor entendeu como</span>
        <Badge tom={resultado.lead_quente ? "positivo" : "neutro"}>{resultado.intencao}</Badge>
        {resultado.lead_quente && <Badge tom="positivo" ponto>lead quente</Badge>}
      </div>

      <div
        className={`rounded-xl border p-4 ${
          respondeu
            ? "border-marca/25 bg-marca-fraca"
            : "border-borda bg-superficie-2"
        }`}
      >
        <p className="text-sm font-medium text-texto">
          {respondeu ? "O agente respondeu" : "O agente NÃO respondeu — de propósito"}
        </p>
        <p className="mt-1 text-sm text-texto-medio">{resultado.motivo}</p>
      </div>

      {!respondeu && (
        <p className="text-xs leading-relaxed text-texto-fraco">
          Silêncio na hora certa é comportamento, não falha. Insistir depois de uma
          recusa, ou argumentar contra um pedido de descadastro, queima a reputação do
          seu remetente e expõe você juridicamente.
        </p>
      )}
    </motion.div>
  );
}
