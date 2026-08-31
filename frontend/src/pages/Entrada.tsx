import { useState } from "react";
import { motion } from "framer-motion";
import { ApiError, api, sessao, type Sessao } from "../lib/api";
import { Aviso } from "../components/ui";

/**
 * Entrar ou criar conta (Etapa 8).
 *
 * Antes desta etapa nao havia login: a interface mandava `X-User-Email` fixo e
 * o backend confiava. Esta tela e a porta que faltava.
 *
 * Uma decisao de produto: o modo padrao e **criar conta**, nao entrar. Quem
 * chega pela landing esta vendo o produto pela primeira vez; abrir num
 * formulario de login pergunta uma senha que a pessoa ainda nao tem.
 */
export default function Entrada({
  aoEntrar,
  aoVoltar,
}: {
  aoEntrar: (s: Sessao) => void;
  aoVoltar: () => void;
}) {
  const [modo, setModo] = useState<"criar" | "entrar">("criar");
  const [nome, setNome] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const criando = modo === "criar";

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      const s = criando
        ? await api.registrar({ email, nome, senha, empresa: empresa || undefined })
        : await api.entrar(email, senha);
      sessao.guardar(s);
      aoEntrar(s);
    } catch (erroApi) {
      // 409 no cadastro nao e falha do usuario: e alguem que ja tem conta.
      // Levar direto para o login poupa a pessoa de reler a mensagem.
      if (erroApi instanceof ApiError && erroApi.status === 409) {
        setModo("entrar");
        setErro("Você já tem uma conta com este e-mail. Entre com sua senha.");
      } else {
        setErro(erroApi instanceof ApiError ? erroApi.detalhe : String(erroApi));
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-fundo px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="w-full max-w-md"
      >
        <button
          onClick={aoVoltar}
          className="mb-6 text-sm text-texto-fraco transition-colors hover:text-texto"
        >
          ← Voltar
        </button>

        <div className="realce-topo rounded-2xl border border-borda bg-superficie p-6 shadow-1 sm:p-8">
          <h1 className="text-xl font-semibold text-texto">
            {criando ? "Criar sua conta" : "Entrar"}
          </h1>
          <p className="mt-1.5 text-sm text-texto-medio">
            {criando
              ? "Leva menos de um minuto. Você começa com créditos para rodar uma busca inteira."
              : "Use o e-mail e a senha que você cadastrou."}
          </p>

          <form onSubmit={enviar} className="mt-6 space-y-4">
            {criando && (
              <>
                <Campo
                  rotulo="Seu nome"
                  valor={nome}
                  aoMudar={setNome}
                  obrigatorio
                  autoComplete="name"
                />
                <Campo
                  rotulo="Empresa"
                  nota="opcional — autônomo pode deixar em branco"
                  valor={empresa}
                  aoMudar={setEmpresa}
                  autoComplete="organization"
                />
              </>
            )}
            <Campo
              rotulo="E-mail"
              tipo="email"
              valor={email}
              aoMudar={setEmail}
              obrigatorio
              autoComplete="email"
            />
            <Campo
              rotulo="Senha"
              tipo="password"
              valor={senha}
              aoMudar={setSenha}
              obrigatorio
              nota={criando ? "ao menos 8 caracteres" : undefined}
              autoComplete={criando ? "new-password" : "current-password"}
            />

            {erro && <Aviso tom="erro">{erro}</Aviso>}

            <button
              type="submit"
              disabled={enviando}
              className="w-full rounded-xl bg-marca px-4 py-2.5 text-sm font-medium text-white shadow-1 transition-all duration-200 hover:brightness-110 disabled:opacity-60"
            >
              {enviando ? "Um instante…" : criando ? "Criar conta" : "Entrar"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-texto-fraco">
            {criando ? "Já tem conta?" : "Ainda não tem conta?"}{" "}
            <button
              onClick={() => {
                setModo(criando ? "entrar" : "criar");
                setErro(null);
              }}
              className="font-medium text-marca hover:underline"
            >
              {criando ? "Entrar" : "Criar conta"}
            </button>
          </p>
        </div>
      </motion.div>
    </div>
  );
}

function Campo({
  rotulo,
  valor,
  aoMudar,
  tipo = "text",
  nota,
  obrigatorio,
  autoComplete,
}: {
  rotulo: string;
  valor: string;
  aoMudar: (v: string) => void;
  tipo?: string;
  nota?: string;
  obrigatorio?: boolean;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-texto">{rotulo}</span>
      {nota && <span className="ml-1.5 text-xs text-texto-fraco">{nota}</span>}
      <input
        type={tipo}
        value={valor}
        required={obrigatorio}
        autoComplete={autoComplete}
        onChange={(e) => aoMudar(e.target.value)}
        className="mt-1.5 w-full rounded-xl border border-borda bg-superficie-2 px-3 py-2 text-sm text-texto outline-none transition-colors focus:border-marca"
      />
    </label>
  );
}
