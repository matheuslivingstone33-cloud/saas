import { motion } from "framer-motion";
import { EXPO } from "../components/movimento";
import { TrocaTema } from "../components/tema";

/**
 * Landing — a primeira coisa que o cliente ve.
 *
 * A promessa e concreta e verificavel, nao adjetivo: o produto encontra quem
 * CONSOME o seu servico. Por isso a pagina mostra o mecanismo (servico ->
 * ramos que compram -> abordagem) em vez de prometer "revolucionar suas
 * vendas". Quem vende ferramenta para prestador de servico compete com a
 * desconfianca de quem ja comprou lista de lead ruim.
 *
 * Numero nenhum aqui e inventado: os que aparecem sao do proprio produto
 * (dois baldes de custo, conformidade, dedup). Prova social falsa numa landing
 * de produto novo e o jeito mais rapido de perder o cliente na primeira tela.
 */

const COMO_FUNCIONA = [
  {
    titulo: "Você diz o que faz",
    texto: "Em uma frase, com as suas palavras. Sem formulário, sem categoria para escolher.",
  },
  {
    titulo: "A IA acha quem consome",
    texto:
      "O Cérebro cruza o seu serviço com os ramos que compram isso de forma recorrente — e descarta seus concorrentes.",
  },
  {
    titulo: "A abordagem sai pronta",
    texto:
      "Mensagem personalizada por empresa, com o motivo da escolha à vista. Você aprova ou deixa no automático.",
  },
];

const PROVAS = [
  {
    titulo: "Você vê por que cada empresa apareceu",
    texto:
      "Score aberto, fator por fator, com a origem de cada dado. Nada de caixa-preta: se a escolha não fizer sentido, dá para conferir a conta.",
  },
  {
    titulo: "Nunca aborda a mesma empresa duas vezes",
    texto:
      "Deduplicação por CNPJ, telefone e domínio. Sua reputação de remetente é ativo — o sistema trata como tal.",
  },
  {
    titulo: "Conformidade não é item opcional",
    texto:
      "Só dado público de empresa. Toda mensagem declara ser IA e leva descadastro de 1 clique. Opt-out é consultado antes de todo envio.",
  },
  {
    titulo: "Você enxerga o custo de cada lead",
    texto:
      "Dados e IA em contas separadas, com custo por lead na tela. Você sabe quanto custou o cliente antes de faturar.",
  },
];

export default function Landing({
  aoComecar,
  aoSuporte,
}: {
  aoComecar: () => void;
  aoSuporte: () => void;
}) {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[36rem]">
        <div className="aura left-1/2 h-[30rem] w-[52rem] -translate-x-1/2 -translate-y-1/4" />
      </div>

      <header className="relative mx-auto flex max-w-6xl items-center gap-4 px-6 py-5">
        <span className="flex items-center gap-2.5">
          <svg viewBox="0 0 64 64" className="h-8 w-8" aria-hidden>
            <circle cx="27" cy="27" r="15" fill="none" stroke="rgb(var(--cor-marca))" strokeWidth="5" />
            <line x1="38" y1="38" x2="53" y2="53" stroke="rgb(var(--cor-acento))" strokeWidth="5.5" strokeLinecap="round" />
            <circle cx="27" cy="27" r="4" fill="rgb(var(--cor-acento))" />
          </svg>
          <span className="font-marca text-lg tracking-tight text-texto">
            Prospector <span className="text-marca">AI</span>
          </span>
        </span>

        <div className="ml-auto flex items-center gap-2.5">
          <TrocaTema />
          <button
            onClick={aoSuporte}
            className="inline-flex items-center gap-2 rounded-full border border-borda bg-superficie-2 px-3.5 py-1.5 text-sm text-texto-medio transition-colors hover:border-borda-forte hover:text-texto"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4 text-positivo" fill="currentColor" aria-hidden>
              <path d="M12 2a10 10 0 0 0-8.7 15l-1.2 4.4 4.5-1.2A10 10 0 1 0 12 2zm0 2a8 8 0 1 1-4.2 14.8l-.3-.2-2.3.6.6-2.2-.2-.4A8 8 0 0 1 12 4z" />
            </svg>
            Suporte
          </button>
        </div>
      </header>

      <main className="relative mx-auto max-w-6xl px-6">
        {/* Herói */}
        <section className="py-16 text-center sm:py-24">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EXPO }}
          >
            <span className="inline-flex items-center gap-2 rounded-full border border-borda bg-superficie-2 px-3 py-1 text-xs text-texto-medio">
              <span className="h-1.5 w-1.5 rounded-full bg-positivo" />
              Prospecção B2B em conformidade com a LGPD
            </span>

            <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight text-texto sm:text-6xl">
              Seus próximos clientes já existem.
              <span className="block text-marca">Falta alguém encontrar.</span>
            </h1>

            <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-texto-medio">
              Diga o serviço que você faz. A IA descobre as empresas que consomem isso
              na sua região, explica por que cada uma foi escolhida e escreve a primeira
              conversa.
            </p>

            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <motion.button
                onClick={aoComecar}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.98 }}
                transition={{ duration: 0.15, ease: EXPO }}
                className="inline-flex items-center gap-2 rounded-xl bg-marca px-6 py-3 text-sm font-medium text-white shadow-2 transition-colors hover:bg-marca-forte"
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
                  <path
                    d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinejoin="round"
                  />
                </svg>
                Usar de forma gratuita
              </motion.button>

              <button
                onClick={aoSuporte}
                className="inline-flex items-center gap-2 rounded-xl border border-borda px-5 py-3 text-sm text-texto-medio transition-colors hover:border-borda-forte hover:text-texto"
              >
                Falar com o suporte
              </button>
            </div>

            <p className="mt-4 text-xs text-texto-fraco">
              10 leads por mês no plano grátis, sendo 3 com automação. Sem cartão.
            </p>
          </motion.div>
        </section>

        {/* Como funciona */}
        <section className="border-t border-borda py-16">
          <h2 className="text-center text-2xl font-semibold tracking-tight text-texto">
            Como funciona
          </h2>
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {COMO_FUNCIONA.map((passo, i) => (
              <motion.div
                key={passo.titulo}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ duration: 0.5, ease: EXPO, delay: i * 0.08 }}
                className="realce-topo rounded-2xl border border-borda bg-superficie p-6"
              >
                <span className="num flex h-8 w-8 items-center justify-center rounded-lg bg-marca-fraca text-sm font-semibold text-marca">
                  {i + 1}
                </span>
                <h3 className="mt-4 text-base font-semibold text-texto">{passo.titulo}</h3>
                <p className="mt-2 text-sm leading-relaxed text-texto-medio">{passo.texto}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* O que separa de uma lista de leads */}
        <section className="border-t border-borda py-16">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-texto">
              Não é uma lista de contatos
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-texto-medio">
              Lista de lead qualquer um vende. O que muda o resultado é saber por que
              aquela empresa precisa de você — e conseguir provar.
            </p>
          </div>

          <div className="mt-10 grid gap-5 md:grid-cols-2">
            {PROVAS.map((prova, i) => (
              <motion.div
                key={prova.titulo}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={{ duration: 0.5, ease: EXPO, delay: i * 0.06 }}
                className="flex gap-4 rounded-2xl border border-borda bg-superficie p-5"
              >
                <svg viewBox="0 0 24 24" className="mt-0.5 h-5 w-5 shrink-0 text-positivo" fill="none" aria-hidden>
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
                  <path d="M8.5 12.2l2.3 2.3 4.7-4.9" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div>
                  <h3 className="text-sm font-semibold text-texto">{prova.titulo}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-texto-medio">{prova.texto}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Chamada final */}
        <section className="border-t border-borda py-16 text-center">
          <h2 className="mx-auto max-w-xl text-3xl font-semibold leading-tight tracking-tight text-texto">
            Comece pela pergunta que importa:
            <span className="block text-marca">quem você quer atender hoje?</span>
          </h2>
          <motion.button
            onClick={aoComecar}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.98 }}
            transition={{ duration: 0.15, ease: EXPO }}
            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-marca px-6 py-3 text-sm font-medium text-white shadow-2 transition-colors hover:bg-marca-forte"
          >
            Usar de forma gratuita
          </motion.button>
        </section>
      </main>

      <footer className="relative mx-auto max-w-6xl border-t border-borda px-6 py-8 text-xs text-texto-fraco">
        <p>
          Prospector AI · descoberta a partir de dados públicos de empresas, em
          conformidade com a LGPD. Todos os provedores rodando em modo mock nesta
          instalação.
        </p>
      </footer>
    </div>
  );
}
