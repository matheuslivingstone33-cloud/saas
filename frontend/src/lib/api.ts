/**
 * Cliente da API do Prospector AI.
 *
 * Fase 6: a interface consome SOMENTE mocks — o backend inteiro roda com
 * PROVIDER_MODE=mock, sem nenhuma chave. Nada aqui muda na Fase 7.
 */
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const USUARIO_DEV = "demo@prospector.local";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detalhe: string,
    readonly tipo?: string,
  ) {
    super(detalhe);
  }
}

async function req<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${caminho}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      // Autenticacao real (JWT) entra antes de qualquer exposicao publica.
      "X-User-Email": USUARIO_DEV,
      ...(init?.headers ?? {}),
    },
  });
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

  // cerebro
  expandir: (servico: string, regiao: string) =>
    post<Expansao>("/v1/cerebro/expandir", { servico, regiao, max_ramos: 6, max_termos: 6 }),
  pesos: () => get<{ versao: number; amostras: number; pesos: Record<string, number> }>(
    "/v1/cerebro/pesos",
  ),

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
  aprovar: (id: string) => post<Mensagem>(`/v1/messages/${id}/aprovar`),

  // motor 4 — conversa
  simularResposta: (leadId: string, corpo: string) =>
    post<ResultadoConversa>(`/v1/leads/${leadId}/simular-resposta`, { corpo }),
  rejeitar: (id: string) => post<Mensagem>(`/v1/messages/${id}/rejeitar`),

  // motor 5 — cadencia
  cadencia: () => get<Cadencia>("/v1/cadencia"),
  // `forcar` pula a ESPERA e so ela: os guardrails continuam valendo. So
  // existe em modo mock — sem isso a cadencia so seria visivel daqui a 3 dias.
  rodarCadencia: (forcar = false) =>
    post<ResultadoCadencia>("/v1/cadencia/executar", { forcar, limite: 50 }),
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
