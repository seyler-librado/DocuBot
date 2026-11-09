// Cliente de la API de DocuBot: tipos y llamadas.

export class ErrorApi extends Error {
  estado: number;
  constructor(mensaje: string, estado: number) {
    super(mensaje);
    this.estado = estado;
  }
}

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const r = await fetch(ruta, init);
  if (!r.ok) {
    const d = await r.json().catch(() => null);
    const detalle = d?.detail;
    const mensaje =
      typeof detalle === "string"
        ? detalle
        : Array.isArray(detalle)
          ? detalle.map((x: { msg?: string }) => x.msg).join("; ")
          : `error ${r.status}`;
    throw new ErrorApi(mensaje, r.status);
  }
  const tipo = r.headers.get("content-type") ?? "";
  return (tipo.includes("json") ? r.json() : r.text()) as Promise<T>;
}

const enviar = <T>(metodo: string, ruta: string, cuerpo?: unknown) =>
  pedir<T>(ruta, {
    method: metodo,
    headers: cuerpo === undefined ? undefined : { "Content-Type": "application/json" },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });

export function consulta(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

// --- tipos ----------------------------------------------------------------------

export type Pagina<T> = { total: number; elementos: T[] };

export type Salud = {
  ok: boolean;
  version: string;
  base_datos: { ok: boolean; postgres?: string; postgis?: string | null; vector?: string | null; migracion?: string | null; error?: string };
};

export type Ajustes = {
  ia: {
    proveedor: string;
    modelo: string;
    url: string;
    con_llave: boolean;
    vision: boolean;
    paginas: number;
    paginas_imagen: number;
    max_caracteres: number;
    temperatura: number;
  };
  trabajadores: Record<string, number>;
  red: {
    user_agent: string;
    peticiones_por_segundo_por_dominio: number;
    simultaneas_por_dominio: number;
    respetar_robots: boolean;
    timeout: number;
    reintentos: number;
    verificar_tls: boolean;
    reintentar_sin_tls: boolean;
  };
  buscadores: { searxng_url: string; pais: string; idioma: string; con_llave: Record<string, boolean> };
  almacen: { carpeta: string; tamano_max_mb: number; respaldo_wayback: boolean };
  mapa: { teselas: string; atribucion: string };
};

export type ResumenGeneral = {
  perfiles: number;
  corridas_activas: number;
  documentos: number;
  bytes: number;
  fichas: Record<string, number>;
  por_bajar: number;
  candidatos: number;
  eventos_conectado: boolean;
};

export type SaludIA = {
  proveedor: string;
  ok: boolean | null;
  modelo?: string;
  modelos?: string[];
  vision?: boolean;
  detalle?: string;
  eco?: string;
  segundos?: number;
};

export type ResumenPerfil = {
  nombre: string;
  archivo: string;
  valido: boolean;
  errores: string[];
  descripcion?: string;
  fuentes?: string[];
  dominios?: string[];
  modo?: "palabras" | "todos";
  tipos_documento?: Record<string, string>;
  campos?: string[];
  geografia?: boolean;
  catalogo?: string | null;
};

export type DefCampo = {
  tipo: "texto" | "fecha" | "numero" | "opcion" | "lista" | "lugar";
  requerido: boolean;
  opciones: string[];
  descripcion: string;
};

export type FuenteConfig = {
  tipo: string;
  urls?: string[];
  archivo?: string;
  motor?: string;
  consultas?: string[];
  usar?: string;
  patron?: string;
};

export type ConfigPerfil = {
  nombre: string;
  descripcion: string;
  descubrimiento: {
    dominios: { permitir: string[]; bloquear: string[] };
    fuentes: FuenteConfig[];
    exploracion: { sitemap: boolean; profundidad: number; max_paginas: number; tiempo_max_s: number; secciones_prioritarias: string[] };
  };
  documentos: {
    extensiones: string[];
    modo: string;
    tipos: Record<string, { nombre: string; patrones: string[]; palabras: string[] }>;
    excluir: string[];
    puntaje_minimo: number;
  };
  fichas: { ia: boolean; campos: Record<string, DefCampo>; instrucciones: string };
  red: { peticiones_por_segundo_por_dominio: number | null; respetar_robots: boolean | null };
};

export type DetallePerfil = ResumenPerfil & { config: ConfigPerfil | null };

export type Corrida = {
  id: number;
  perfil: string;
  estado: "corriendo" | "terminada" | "detenida" | "error" | "pendiente";
  error: string | null;
  creada: string;
  iniciada: string | null;
  terminada: string | null;
  fuentes: number[];
  tareas: Record<string, Record<string, number>>;
  sitios: Record<string, number>;
  paginas: number;
  candidatos: Record<string, number>;
  candidatos_total: number;
  candidatos_estado: Record<string, number>;
  nuevos: number;
  documentos: number;
  bytes: number;
  descargar: boolean;
  fichas: Record<string, number>;
  cambios: Record<string, unknown>;
};

export type CambiosCorrida = {
  respetar_robots?: boolean;
  peticiones_por_segundo?: number;
  profundidad?: number;
  max_paginas?: number;
  puntaje_minimo?: number;
};

export type Sitio = {
  sitio_id: number;
  dominio: string;
  estado: string;
  origen: string;
  lugar: string | null;
  paginas: number;
  documentos: number;
  segundos: number | null;
  error: string | null;
};

export type Candidato = {
  id: number;
  perfil: string;
  corrida_id: number | null;
  url: string;
  fuente: string;
  tipo: string | null;
  puntaje: number | null;
  estado: string;
  motivo: string | null;
  ancla: string | null;
  pagina_origen: string | null;
  documento_id: number | null;
  nuevo: boolean | null;
  lugar: string | null;
};

export type Falla = { id: number; etapa: string; error: string | null; intentos: number; carga: Record<string, unknown>; terminada: string | null };

export type FichaCorta = { perfil: string; estado: string; confianza: string | null; titulo: string | null };

export type DocumentoResumen = {
  id: number;
  bytes: number;
  paginas: number | null;
  estado: string;
  mime: string;
  creado: string;
  url: string | null;
  tipo: string | null;
  ancla: string | null;
  nuevo: boolean | null;
  ficha: FichaCorta | null;
  titulo: string | null;
};

export type Ficha = {
  perfil: string;
  estado: string;
  confianza: string | null;
  motivos: string[];
  campos: Record<string, unknown>;
  titulo: string | null;
  modelo: string | null;
  control: Record<string, unknown>;
  actualizado: string;
};

export type DocumentoDetalle = {
  id: number;
  sha256: string;
  bytes: number;
  mime: string;
  paginas: number | null;
  estado: string;
  creado: string;
  texto: { metodo: string; caracteres: number; error: string | null; inicio: string } | null;
  perfiles: string[];
  fichas: Ficha[];
  lugares: LugarDocumento[];
  fuentes: {
    perfil: string;
    url: string;
    tipo: string | null;
    puntaje: number | null;
    ancla: string | null;
    pagina_origen: string | null;
    fuente: string;
    nuevo: boolean | null;
    respaldo: string | null;
    lugar: string | null;
  }[];
};

export type FichaRevision = {
  documento_id: number;
  perfil: string;
  estado: string;
  confianza: string | null;
  motivos: string[];
  titulo: string | null;
  paginas: number | null;
  url: string | null;
  tipo_ia: string | null;
  tipo_esperado: string | null;
  actualizado: string;
};

export type CandidatoLugar = { id: number; clave: string; nombre: string; nivel: string; padre: string | null; puntaje: number | null };

export type LugarDocumento = {
  lugar_id: number | null;
  nombre: string | null;
  clave: string | null;
  nivel: string | null;
  padre: string | null;
  catalogo: string | null;
  origen: string;
  confianza: number;
  estado: "asignado" | "ambiguo" | "revision" | "sin_lugar";
  candidatos: CandidatoLugar[];
};

export type LugarMapa = {
  id: number;
  clave: string;
  nombre: string;
  nivel: string;
  padre: string | null;
  lon: number | null;
  lat: number | null;
  documentos: number;
  revision: number;
};

export type Mapa = {
  catalogo: string;
  documentos: number;
  ubicados: number;
  por_estado: Record<string, number>;
  sin_procesar: number;
  extension: [number, number, number, number] | null;
  lugares: LugarMapa[];
};

export type Nivel = { nivel: string; lugares: number; con_poligono: boolean; tiene_padre: boolean };

export type LugarBuscado = { id: number; clave: string; nombre: string; nivel: string; padre: string | null };

export type LugarDudoso = {
  documento_id: number;
  estado: string;
  origen: string;
  catalogo: string;
  candidatos: CandidatoLugar[];
  titulo: string | null;
  url: string | null;
};

export type Coincidencia = { texto: string; pagina: number | null; tipo: "palabras" | "tema" };
export type ResultadoBusqueda = DocumentoResumen & { puntaje: number; coincidencias: Coincidencia[] };
export type Busqueda = { modo: "mixta" | "palabras" | "tema"; total: number; elementos: ResultadoBusqueda[] };
export type EstadoBusqueda = {
  palabras: { documentos: number };
  tema: { activa: boolean; proveedor: string; modelo?: string; fragmentos?: number; documentos?: number; faltan?: number };
};

// --- llamadas -------------------------------------------------------------------

export const api = {
  salud: () => pedir<Salud>("/api/salud"),
  ajustes: () => pedir<Ajustes>("/api/ajustes"),
  resumen: () => pedir<ResumenGeneral>("/api/resumen"),
  saludIA: () => pedir<SaludIA>("/api/ia/salud"),
  probarIA: () => enviar<SaludIA>("POST", "/api/ia/probar"),

  perfiles: () => pedir<ResumenPerfil[]>("/api/perfiles"),
  perfil: (nombre: string) => pedir<DetallePerfil>(`/api/perfiles/${encodeURIComponent(nombre)}`),
  perfilYaml: (nombre: string) => pedir<string>(`/api/perfiles/${encodeURIComponent(nombre)}/yaml`),

  corridas: (limite = 20) => pedir<Corrida[]>(`/api/corridas${consulta({ limite })}`),
  corrida: (id: number) => pedir<Corrida>(`/api/corridas/${id}`),
  correr: (datos: { perfil: string; fuentes?: number[]; descargar?: boolean; ajustes?: CambiosCorrida }) =>
    enviar<Corrida>("POST", "/api/corridas", datos),
  detener: (id: number) => enviar<unknown>("POST", `/api/corridas/${id}/detener`),
  reanudar: (id: number) => enviar<unknown>("POST", `/api/corridas/${id}/reanudar`),
  descargarCorrida: (id: number, fallidos = false) =>
    enviar<{ encoladas: number }>("POST", `/api/corridas/${id}/descargar${consulta({ fallidos })}`),
  fichasCorrida: (id: number, rehacer = false) =>
    enviar<{ extraer: number; fichar: number }>("POST", `/api/corridas/${id}/fichas${consulta({ rehacer })}`),
  sitios: (id: number, estado?: string) => pedir<Sitio[]>(`/api/corridas/${id}/sitios${consulta({ estado, limite: 500 })}`),
  fallas: (id: number) => pedir<Falla[]>(`/api/corridas/${id}/fallas`),

  candidatos: (f: Record<string, string | number | undefined>) => pedir<Pagina<Candidato>>(`/api/candidatos${consulta(f)}`),
  cambiarCandidato: (id: number, estado: "aceptado" | "rechazado") =>
    enviar<Candidato>("PATCH", `/api/candidatos/${id}`, { estado }),

  documentos: (f: Record<string, string | number | undefined>) => pedir<Pagina<DocumentoResumen>>(`/api/documentos${consulta(f)}`),
  documento: (id: number) => pedir<DocumentoDetalle>(`/api/documentos/${id}`),
  guardarFicha: (id: number, perfil: string, campos: Record<string, unknown>) =>
    enviar<{ estado: string; motivos: string[] }>("PUT", `/api/documentos/${id}/fichas/${encodeURIComponent(perfil)}`, { campos }),
  aprobarFicha: (id: number, perfil: string) =>
    enviar<unknown>("POST", `/api/documentos/${id}/fichas/${encodeURIComponent(perfil)}/aprobar`),
  rehacerFicha: (id: number, perfil: string) =>
    enviar<{ encolada: boolean }>("POST", `/api/documentos/${id}/fichas/${encodeURIComponent(perfil)}/rehacer`),

  fichas: (f: Record<string, string | number | undefined>) => pedir<Pagina<FichaRevision>>(`/api/fichas${consulta(f)}`),

  mapa: (perfil: string, corrida?: number) => pedir<Mapa>(`/api/mapa${consulta({ perfil, corrida })}`),
  niveles: (catalogo: string) => pedir<Nivel[]>(`/api/mapa/niveles${consulta({ catalogo })}`),
  buscarLugares: (catalogo: string, q: string) => pedir<LugarBuscado[]>(`/api/lugares/buscar${consulta({ catalogo, q })}`),
  asignarLugar: (documento: number, lugar_id: number) =>
    enviar<{ lugar_id: number; nombre: string }>("PUT", `/api/documentos/${documento}/lugar`, { lugar_id }),
  dudosos: (f: Record<string, string | number | undefined>) => pedir<Pagina<LugarDudoso>>(`/api/lugares/dudosos${consulta(f)}`),
  ubicarCorrida: (id: number) => enviar<{ encoladas: number }>("POST", `/api/corridas/${id}/lugares`),

  buscar: (f: Record<string, string | number | undefined>) => pedir<Busqueda>(`/api/buscar${consulta(f)}`),
  estadoBusqueda: () => pedir<EstadoBusqueda>("/api/busqueda/estado"),
  indexar: () => enviar<{ encolados: number }>("POST", "/api/busqueda/indexar"),
};

export const urlPoligonos = (catalogo: string, nivel: string) => `/api/mapa/poligonos${consulta({ catalogo, nivel })}`;

export const urlArchivo = (id: number) => `/api/documentos/${id}/archivo`;
export const urlPortada = (id: number) => `/api/documentos/${id}/portada`;
