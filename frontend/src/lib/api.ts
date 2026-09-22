/**
 * Cliente da API do Prospector AI.
 *
 * Fase 6: a interface consome SOMENTE mocks — o backend inteiro roda com
 * PROVIDER_MODE=mock, sem nenhuma chave. Nada aqui muda na Fase 7.
 *
 * Etapa 8: toda requisicao leva `Authorization: Bearer`. O token de acesso dura
 * 30 minutos e e renovado automaticamente pelo token de renovacao — o usuario
 * so ve a tela de login quando os DOIS vencem.
 */
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const CHAVE_ACESSO = "prospector:acesso";
const CHAVE_RENOVACAO = "prospector:renovacao";

export type Sessao = {
  acesso: string;
  renovacao: string;
  tipo: string;
  expira_em_segundos: number;
  usuario: { id: string; email: string; nome: string };
};

export const sessao = {
  acesso: () => localStorage.getItem(CHAVE_ACESSO),
  renovacao: () => localStorage.getItem(CHAVE_RENOVACAO),
  ativa: () => Boolean(localStorage.getItem(CHAVE_ACESSO)),
  guardar(s: Sessao) {
    localStorage.setItem(CHAVE_ACESSO, s.acesso);
    localStorage.setItem(CHAVE_RENOVACAO, s.renovacao);
  },
  limpar() {
    localStorage.removeItem(CHAVE_ACESSO);
    localStorage.removeItem(CHAVE_RENOVACAO);
  },
};

/** Avisa a aplicacao que a sessao caiu de vez, para ela mandar ao login. */
export const AO_EXPIRAR = "prospector:sessao-expirada";

// Uma renovacao por vez: sem isto, cinco requisicoes que esbarram no 401 juntas
// disparam cinco renovacoes, e as quatro ultimas usam um token de renovacao que
// a primeira ja trocou.
let renovando: Promise<boolean> | null = null;

async function renovarSessao(): Promise<boolean> {
  const token = sessao.renovacao();
  if (!token) return false;
  if (renovando) return renovando;

  renovando = (async () => {
    try {
      const resp = await fetch(`${BASE}/v1/auth/renovar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ renovacao: token }),
      });
      if (!resp.ok) return false;
      sessao.guardar((await resp.json()) as Sessao);
      return true;
    } catch {
      return false;
    } finally {
      renovando = null;
    }
  })();
  return renovando;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detalhe: string,
    readonly tipo?: string,
  ) {
    super(detalhe);
  }
}

function enviar(caminho: string, init?: RequestInit): Promise<Response> {
  const token = sessao.acesso();
  return fetch(`${BASE}${caminho}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
}

async function req<T>(caminho: string, init?: RequestInit): Promise<T> {
  let resp = await enviar(caminho, init);

  // 401 numa rota comum quer dizer acesso vencido. Renova UMA vez e repete;
  // se a renovacao tambem falhou, a sessao acabou de verdade.
  if (resp.status === 401 && !caminho.startsWith("/v1/auth/")) {
    if (await renovarSessao()) {
      resp = await enviar(caminho, init);
    } else {
      sessao.limpar();
      window.dispatchEvent(new CustomEvent(AO_EXPIRAR));
    }
  }

  if (!resp.ok) {
    let detalhe = `${resp.status} ${resp.statusText}`;
    let tipo: string | undefined;
    try {
      const corpo = await resp.json();
      detalhe = typeof corpo.detail === "string" ? corpo.detail : detalhe;
      tipo = corpo.tipo;
    } catch {
      /* resposta sem corpo JSON */
    }
    throw new ApiError(resp.status, detalhe, tipo);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/**
 * Abre um fluxo SSE autenticado.
 *
 * O `EventSource` do navegador nao aceita cabecalho, e pendurar o token na
 * query string o deixaria em log de servidor e historico. Com `fetch` o Bearer
 * viaja no lugar certo — e, de quebra, some a reconexao automatica do
 * EventSource, que ja custou 256 execucoes de campanha por um clique so.
 *
 * Devolve a resposta CRUA: quem chama le o corpo em pedacos. Um 401 renova a
 * sessao uma vez e repete, igual ao `req`.
 */
export async function abrirFluxo(caminho: string, signal?: AbortSignal): Promise<Response> {
  const abrir = () =>
    fetch(`${BASE}${caminho}`, {
      signal,
      headers: {
        Accept: "text/event-stream",
        ...(sessao.acesso() ? { Authorization: `Bearer ${sessao.acesso()}` } : {}),
      },
    });

  let resp = await abrir();
  if (resp.status === 401) {
    if (await renovarSessao()) {
      resp = await abrir();
    } else {
      sessao.limpar();
      window.dispatchEvent(new CustomEvent(AO_EXPIRAR));
    }
  }
  return resp;
}

const get = <T>(caminho: string) => req<T>(caminho);
const post = <T>(caminho: string, body?: unknown) =>
  req<T>(caminho, { method: "POST", body: body ? JSON.stringify(body) : undefined });
const patch = <T>(caminho: string, body: unknown) =>
  req<T>(caminho, { method: "PATCH", body: JSON.stringify(body) });

// ---------------------------------------------------------------- tipos
export type Pagina<T> = {
  itens: T[];
  total: number;
  pagina: number;
  por_pagina: number;
  paginas: number;
};

export type NivelAutonomia = "assistido" | "automatico";

export type Perfil = {
  id: string;
  email: string;
  nome: string;
  empresa: string | null;
  cnpj: string | null;
  servico_padrao: string | null;
  regiao_padrao: string | null;
  tom_de_voz: string | null;
  diferenciais: string | null;
  provas: string | null;
  evitar: string | null;
  onboarding_completo: boolean;
  assinatura: {
    plano: string | null;
    status: string | null;
    autonomy_level: NivelAutonomia | null;
    teto_leads_mes: number;
    leads_consumidos_mes: number;
    overage_habilitado: boolean;
    plano_catalogo: PlanoCatalogo | null;
  };
  saldo: Saldo;
};

export type Saldo = {
  creditos: number;
  plano: string;
  teto_leads_mes: number;
  leads_consumidos_mes: number;
  restante_no_teto: number;
  overage_habilitado: boolean;
  bloqueado: boolean;
  motivo_bloqueio: string;
  alertas: string[];
};

export type PlanoCatalogo = {
  codigo: string;
  nome: string;
  preco_centavos: number;
  preco_reais: number;
  creditos_mes: number;
  teto_leads_mes: number;
  overage_centavos_por_credito: number;
  destaques: string[];
  equivalencia?: Equivalencia;
};

export type Equivalencia = {
  plano: string;
  creditos_mes: number;
  tokens_por_lead: number;
  tokens_mes: number;
  leads_estimados: number;
  base: "medido" | "estimado";
  amostra_leads: number;
  custo_medio_lead_micros: number;
  aviso: string;
};

export type Campanha = {
  id: string;
  nome: string;
  servico: string;
  regiao: string;
  status: string;
  canal_padrao: string;
  autonomy_override: NivelAutonomia | null;
  meta_leads: number;
  filtros: Record<string, unknown>;
  expansao: Record<string, unknown> | null;
  created_at: string;
};

export type Lead = {
  id: string;
  campaign_id: string;
  cnpj: string | null;
  razao_social: string | null;
  nome_fantasia: string | null;
  cnae_principal: string | null;
  porte: string;
  municipio: string | null;
  bairro: string | null;
  uf: string | null;
  telefone: string | null;
  email: string | null;
  website: string | null;
  score: number;
  score_breakdown: {
    score?: number;
    componentes?: Record<string, number>;
    pesos?: Record<string, number>;
    contribuicoes?: Record<string, number>;
    explicacao?: string;
  } | null;
  status: string;
  provenance: Record<string, unknown>;
  /** Quando uma PESSOA assumiu a conversa. Preenchido = o agente calou:
   *  nao ha mais toque de cadencia nem replica do Motor 4 neste lead. */
  assumido_em: string | null;
  /** Contato liberado? Enquanto for false, razao social, CNPJ, e-mail,
   *  telefone e site vem NULOS da API — o corte e do servidor. */
  revelado: boolean;
  revelado_em: string | null;
  created_at: string;
};

export type Mensagem = {
  id: string;
  campaign_id: string | null;
  lead_id: string | null;
  canal: string;
  direcao: "saida" | "entrada";
  /** Posicao dentro da conversa daquele lead. Relogio nao serve: pergunta e
   *  replica do mesmo turno nascem com carimbo identico. */
  ordem: number;
  status: string;
  destinatario: string | null;
  remetente: string | null;
  assunto: string | null;
  corpo: string;
  declaracao_ia: string | null;
  gerado_por_ia: boolean;
  corpo_original: string | null;
  link_descadastro: string | null;
  tokens_entrada: number;
  tokens_saida: number;
  enviado_em: string | null;
  created_at: string;
};

export type Dashboard = {
  campanhas: number;
  funil: Record<string, number>;
  leads_por_status: Record<string, number>;
  mensagens: Record<string, number>;
  taxas: { qualificacao: number; resposta: number; conversao: number };
  custo: {
    balde_1_dados: { eventos: number; micros: number; usd: number };
    balde_2_ia: { eventos: number; micros: number; usd: number };
    total_usd: number;
  };
  consumo: {
    tokens_por_lead: number;
    base: string;
    amostra_leads: number;
    custo_medio_lead_micros: number;
  };
  saldo: Saldo;
};

export type Provedores = Record<
  string,
  { modo: string; chave_presente: boolean; rede_habilitada: boolean }
>;

export type Expansao = {
  servico: string;
  regiao: string;
  termos: string[];
  cnaes_alvo: string[];
  ramos: { codigo: string; descricao: string; peso: number; distancia: number }[];
  excluidos_como_concorrente: string[];
  justificativa: string;
};

export type Intencao =
  | "interesse"
  | "duvida"
  | "objecao"
  | "recusa"
  | "pedido_opt_out"
  | "pedido_humano"
  | "ausencia"
  | "indefinida";

/** Um ramo que este cliente ja aprendeu a mirar melhor (ou pior). */
export type RamoAprendido = {
  cnae: string;
  descricao: string;
  fator: number;
  amostras: number;
  media_sinal: number;
  versao: number;
  intencoes: Partial<Record<Intencao, number>>;
  faltam_amostras: number;
};

export type EstadoAprendizado = {
  versao: number;
  amostras: number;
  pesos: Record<string, number>;
  origem: string;
  mira: RamoAprendido[];
};

export type ResultadoConversa = {
  lead_id: string;
  intencao: Intencao;
  respondeu: boolean;
  encerrou: boolean;
  motivo: string;
  resposta_id: string | null;
  aguardando_aprovacao: boolean;
  lead_quente: boolean;
};

/** Motor 5 — onde o lead esta na cadencia de toques. */
export type EstadoCadencia = {
  lead_id: string;
  empresa: string | null;
  toques_enviados: number;
  proximo_toque: number | null;
  proximo_em: string | null;
  devido: boolean;
  encerrada: boolean;
  motivo: string;
  angulo: string | null;
};

export type Cadencia = {
  ativa: boolean;
  max_toques: number;
  dias: { toque2: number; toque3: number };
  devidos: number;
  pendentes: EstadoCadencia[];
};

export type ResultadoCadencia = {
  avaliados: number;
  gerados: number;
  enviados: number;
  aguardando_aprovacao: number;
  bloqueados: number;
  motivos: Record<string, number>;
  toques: {
    lead_id: string;
    empresa: string | null;
    toque: number;
    angulo: string;
    assunto: string;
    enviada: boolean;
    aguardando_aprovacao: boolean;
  }[];
};

/** Quanto ainda da para revelar, e por qual regra. */
export type Cota = {
  plano: string;
  teto_mes: number;
  usadas_mes: number;
  restantes_no_mes: number;
  por_campanha: number | null;
  usadas_na_campanha: number;
  restantes_na_campanha: number | null;
  creditos: number;
  bloqueio: string | null;
};

export type ResultadoExecucao = {
  campaign_id: string;
  nivel_autonomia: string;
  termos_usados: string[];
  ramos_alvo: string[];
  descobertos: number;
  duplicados: number;
  qualificados: number;
  mensagens_geradas: number;
  mensagens_enviadas: number;
  mensagens_aguardando_aprovacao: number;
  bloqueadas: number;
  sem_contato: number;
  motivos_bloqueio: Record<string, number>;
  interrompido_por_saldo: boolean;
  custo: Dashboard["custo"];
};

export type Limites = {
  limite_usuario: number;
  enviadas_usuario_24h: number;
  restante_usuario: number;
  limite_campanha: number;
  enviadas_campanha_24h: number;
  restante_campanha: number;
};

// ---------------------------------------------------------------- api
export const api = {
  // conta
  perfil: () => get<Perfil>("/v1/me"),
  atualizarPerfil: (dados: Partial<Perfil>) => patch<Perfil>("/v1/me", dados),
  trocarAutonomia: (autonomy_level: NivelAutonomia) =>
    post<{ de: string; para: string; alterado: boolean }>("/v1/me/autonomia", {
      autonomy_level,
    }),
  dashboard: () => get<Dashboard>("/v1/dashboard"),
  provedores: () => get<{ provedores: Provedores }>("/v1/providers"),

  // campanhas
  campanhas: () => get<Pagina<Campanha>>("/v1/campaigns?por_pagina=50"),
  campanha: (id: string) => get<Campanha>(`/v1/campaigns/${id}`),
  criarCampanha: (dados: {
    nome: string;
    servico: string;
    regiao: string;
    meta_leads?: number;
    autonomy_override?: NivelAutonomia | null;
  }) => post<Campanha>("/v1/campaigns", dados),
  executar: (id: string, limite_leads = 5) =>
    post<ResultadoExecucao>(`/v1/campaigns/${id}/run`, {
      limite_leads,
      assincrono: false,
    }),
  reabrir: (id: string) => post<Campanha>(`/v1/campaigns/${id}/reset`),
  limites: (id: string) => get<Limites>(`/v1/campaigns/${id}/limites`),
  disparar: (id: string) => post<Record<string, unknown>>(`/v1/campaigns/${id}/disparar`),

  // auth (Etapa 8)
  registrar: (dados: { email: string; nome: string; senha: string; empresa?: string }) =>
    post<Sessao>("/v1/auth/registrar", dados),
  entrar: (email: string, senha: string) =>
    post<Sessao>("/v1/auth/entrar", { email, senha }),
  eu: () => get<{ id: string; email: string; nome: string }>("/v1/auth/eu"),

  // cerebro
  expandir: (servico: string, regiao: string) =>
    post<Expansao>("/v1/cerebro/expandir", { servico, regiao, max_ramos: 6, max_termos: 6 }),
  pesos: () => get<EstadoAprendizado>("/v1/cerebro/pesos"),

  // leads e mensagens
  leads: (campaignId?: string) =>
    get<Pagina<Lead>>(
      `/v1/leads?por_pagina=100${campaignId ? `&campaign_id=${campaignId}` : ""}`,
    ),
  mensagens: (campaignId?: string, status?: string) =>
    get<Pagina<Mensagem>>(
      `/v1/messages?por_pagina=100${campaignId ? `&campaign_id=${campaignId}` : ""}` +
        `${status ? `&status=${status}` : ""}`,
    ),
  editarMensagem: (id: string, corpo: string) =>
    patch<Mensagem>(`/v1/messages/${id}`, { corpo }),
  aprovar: (id: string) => post<Mensagem>(`/v1/messages/${id}/aprovar`),

  // motor 4 — conversa
  simularResposta: (leadId: string, corpo: string) =>
    post<ResultadoConversa>(`/v1/leads/${leadId}/simular-resposta`, { corpo }),
  rejeitar: (id: string) => post<Mensagem>(`/v1/messages/${id}/rejeitar`),

  // etapa 6 — revelacao de contato
  revelar: (leadId: string) => post<Lead>(`/v1/leads/${leadId}/revelar`),
  cotaDeRevelacao: (leadId: string) => get<Cota>(`/v1/leads/${leadId}/cota`),

  // motor 5 — cadencia
  cadencia: () => get<Cadencia>("/v1/cadencia"),
  // `forcar` pula a ESPERA e so ela: os guardrails continuam valendo. So
  // existe em modo mock — sem isso a cadencia so seria visivel daqui a 3 dias.
  rodarCadencia: (forcar = false) =>
    post<ResultadoCadencia>("/v1/cadencia/executar", { forcar, limite: 50 }),
  // etapa 5 — a resposta manual acontece DENTRO do produto: enviar por fora
  // (um mailto:) tiraria a resposta do lead do alcance do Motor 4.
  responder: (leadId: string, corpo: string) =>
    post<{ enviada: boolean; assumida: boolean; motivo: string }>(
      `/v1/leads/${leadId}/responder`,
      { corpo },
    ),
  devolverParaIA: (leadId: string) =>
    post<{ devolvida: boolean; assumida: boolean }>(
      `/v1/leads/${leadId}/devolver-para-ia`,
    ),
  simularRetorno: (leadId: string, tipo: "permanente" | "transitorio" | "reclamacao") =>
    post<{ suprimido: boolean; motivo: string; campanha_pausada: boolean }>(
      `/v1/leads/${leadId}/simular-retorno`,
      { tipo },
    ),

  // creditos
  saldo: () => get<Saldo>("/v1/billing/saldo"),
  vitrine: () =>
    get<{
      planos: PlanoCatalogo[];
      pacotes_avulsos: {
        codigo: string;
        nome: string;
        creditos: number;
        preco_reais: number;
        centavos_por_credito: number;
      }[];
      custo_em_creditos: Record<string, number>;
      observacao: string;
    }>("/v1/billing/vitrine"),
  extrato: () =>
    get<
      Pagina<{
        id: string;
        tipo: string;
        quantidade: number;
        saldo_apos: number;
        descricao: string | null;
        created_at: string;
      }>
    >("/v1/billing/extrato?por_pagina=30"),
  comprar: (pacote: string) =>
    post<{ checkout: { id: string; url: string }; pacote: { creditos: number } }>(
      "/v1/billing/comprar",
      { pacote },
    ),
  confirmarCompra: (checkout_id: string, pacote: string) =>
    post<{ creditado: number; saldo: number }>("/v1/billing/confirmar", {
      checkout_id,
      pacote,
    }),
  trocarPlano: (plano: string) =>
    post<{ de: string; para: string; saldo: number }>("/v1/billing/plano", { plano }),

  margem: () =>
    get<{
      creditos_consumidos: number;
      receita_brl: number;
      custo: {
        balde_1_dados_usd: number;
        balde_2_ia_usd: number;
        total_usd: number;
        total_brl: number;
      };
      margem_brl: number;
      margem_pct: number;
      por_lead: { leads: number; custo_brl: number; receita_brl: number; margem_brl: number };
      taxa_usd_brl: number;
    }>("/v1/margem"),

  // compliance
  lia: () => get<Record<string, unknown>>("/v1/compliance/lia"),
  optOuts: () =>
    get<{ total: number; itens: { contato: string; origem: string; registrado_em: string }[] }>(
      "/v1/compliance/opt-outs",
    ),
  integridade: () =>
    get<{ integra: boolean; registros: number; primeiro_erro_seq: number | null }>(
      "/v1/audit/integridade",
    ),
};
