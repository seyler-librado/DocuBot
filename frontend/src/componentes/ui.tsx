// Componentes base de la interfaz.

import { Loader2, X } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

export const cx = (...clases: (string | false | null | undefined)[]) => clases.filter(Boolean).join(" ");

// --- botón ------------------------------------------------------------------------

type Variante = "principal" | "secundario" | "fantasma" | "peligro";
const VARIANTES: Record<Variante, string> = {
  principal: "bg-marca-700 text-white hover:bg-marca-600 shadow-sm",
  secundario:
    "border border-stone-300 bg-white text-stone-800 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:hover:bg-stone-800",
  fantasma: "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100",
  peligro: "border border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-300 dark:hover:bg-rose-950",
};

export function Boton({
  variante = "secundario",
  cargando,
  icono,
  tamano = "md",
  className,
  children,
  disabled,
  ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: Variante;
  cargando?: boolean;
  icono?: ReactNode;
  tamano?: "sm" | "md";
}) {
  return (
    <button
      {...resto}
      disabled={disabled || cargando}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        tamano === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
        VARIANTES[variante],
        className,
      )}
    >
      {cargando ? <Loader2 className="size-4 animate-spin" /> : icono}
      {children}
    </button>
  );
}

// --- insignia -----------------------------------------------------------------------

type Tono = "neutro" | "marca" | "ok" | "aviso" | "error" | "info";
const TONOS: Record<Tono, string> = {
  neutro: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
  marca: "bg-marca-50 text-marca-900 dark:bg-marca-900/40 dark:text-marca-100",
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  aviso: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  error: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
  info: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
};

export function Insignia({ tono = "neutro", children, className, title }: { tono?: Tono; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONOS[tono], className)}>
      {children}
    </span>
  );
}

const ESTADOS: Record<string, [string, Tono]> = {
  // fichas
  ok: ["lista", "ok"],
  revision: ["por revisar", "aviso"],
  ilegible: ["ilegible", "neutro"],
  error: ["con error", "error"],
  // corridas
  corriendo: ["en curso", "info"],
  terminada: ["terminada", "ok"],
  detenida: ["detenida", "aviso"],
  // candidatos
  nuevo: ["sin calificar", "neutro"],
  aceptado: ["aceptado", "marca"],
  rechazado: ["rechazado", "neutro"],
  descargado: ["descargado", "ok"],
  fallido: ["falló", "error"],
  // sitios
  explorado: ["explorado", "ok"],
  pendiente: ["pendiente", "neutro"],
  sin_respuesta: ["sin respuesta", "error"],
  redes_sociales: ["red social", "neutro"],
  estacionado: ["estacionado", "neutro"],
  bloqueado: ["bloqueado", "aviso"],
};

export function Estado({ valor }: { valor: string | null | undefined }) {
  if (!valor) return null;
  const [texto, tono] = ESTADOS[valor] ?? [valor, "neutro" as Tono];
  return <Insignia tono={tono}>{texto}</Insignia>;
}

export function Confianza({ valor }: { valor: string | null | undefined }) {
  if (!valor) return null;
  const tono: Tono = valor === "alta" ? "ok" : valor === "media" ? "aviso" : valor === "manual" ? "marca" : "error";
  return <Insignia tono={tono}>{valor === "manual" ? "revisada a mano" : `confianza ${valor}`}</Insignia>;
}

// --- contenedores -----------------------------------------------------------------

export function Tarjeta({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900", className)}>{children}</div>;
}

export function Seccion({ titulo, accion, children, className }: { titulo: string; accion?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("mt-8", className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-stone-500 dark:text-stone-400">{titulo}</h2>
        {accion}
      </div>
      {children}
    </section>
  );
}

export function Encabezado({ titulo, subtitulo, acciones }: { titulo: ReactNode; subtitulo?: ReactNode; acciones?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{titulo}</h1>
        {subtitulo && <div className="mt-1 text-sm text-stone-500 dark:text-stone-400">{subtitulo}</div>}
      </div>
      {acciones && <div className="flex flex-wrap items-center gap-2">{acciones}</div>}
    </header>
  );
}

export function Cifra({ valor, nombre, detalle }: { valor: ReactNode; nombre: string; detalle?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-2xl font-semibold tabular-nums tracking-tight">{valor}</div>
      <div className="text-xs text-stone-500 dark:text-stone-400">{nombre}</div>
      {detalle && <div className="mt-0.5 text-xs text-stone-400 dark:text-stone-500">{detalle}</div>}
    </div>
  );
}

export function Vacio({ icono, titulo, children }: { icono?: ReactNode; titulo: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-stone-300 px-6 py-12 text-center dark:border-stone-700">
      {icono && <div className="mb-3 text-stone-400">{icono}</div>}
      <p className="font-medium">{titulo}</p>
      {children && <div className="mt-1 max-w-md text-sm text-stone-500 dark:text-stone-400">{children}</div>}
    </div>
  );
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-stone-500">
      <Loader2 className="size-4 animate-spin" /> {texto}
    </div>
  );
}

export function Aviso({ tono = "error", children }: { tono?: "error" | "aviso" | "info"; children: ReactNode }) {
  const estilos = {
    error: "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200",
    aviso: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200",
    info: "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-200",
  };
  return <div className={cx("rounded-lg border px-4 py-3 text-sm", estilos[tono])}>{children}</div>;
}

// --- formularios ------------------------------------------------------------------

const BASE_ENTRADA =
  "rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm placeholder:text-stone-400 focus:border-marca-500 focus:outline-none focus:ring-2 focus:ring-marca-500/20 dark:border-stone-700 dark:bg-stone-950";

// ancho completo salvo que se pida otro (w-auto, w-40...): si no, w-full le gana a w-auto
const ancho = (className?: string) => (/(^|\s)w-/.test(className ?? "") ? "" : "w-full");

export function Entrada({ className, ...resto }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...resto} className={cx(BASE_ENTRADA, ancho(className), className)} />;
}

export function AreaTexto({ className, ...resto }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...resto} className={cx(BASE_ENTRADA, ancho(className), "min-h-20", className)} />;
}

export function Selector({ className, children, ...resto }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...resto} className={cx(BASE_ENTRADA, ancho(className), "pr-8", className)}>
      {children}
    </select>
  );
}

export function Etiqueta({ texto, ayuda, children }: { texto: string; ayuda?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-stone-600 dark:text-stone-400">{texto}</span>
      {children}
      {ayuda && <span className="mt-1 block text-xs text-stone-400">{ayuda}</span>}
    </label>
  );
}

export function Interruptor({ activo, alCambiar, texto, ayuda }: { activo: boolean; alCambiar: (v: boolean) => void; texto: string; ayuda?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={activo}
        onClick={() => alCambiar(!activo)}
        className={cx(
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full transition-colors",
          activo ? "bg-marca-600" : "bg-stone-300 dark:bg-stone-700",
        )}
      >
        <span className={cx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform", activo ? "translate-x-4.5" : "translate-x-0.5")} />
      </button>
      <span className="text-sm">
        {texto}
        {ayuda && <span className="block text-xs text-stone-500">{ayuda}</span>}
      </span>
    </label>
  );
}

// --- navegación -------------------------------------------------------------------

export function Pestanas<T extends string>({ opciones, valor, alCambiar }: { opciones: { valor: T; texto: ReactNode }[]; valor: T; alCambiar: (v: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-stone-200 dark:border-stone-800">
      {opciones.map((o) => (
        <button
          key={o.valor}
          onClick={() => alCambiar(o.valor)}
          className={cx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            valor === o.valor
              ? "border-marca-600 text-marca-700 dark:text-marca-100"
              : "border-transparent text-stone-500 hover:text-stone-800 dark:hover:text-stone-200",
          )}
        >
          {o.texto}
        </button>
      ))}
    </div>
  );
}

export function Paginacion({ total, limite, desde, alCambiar }: { total: number; limite: number; desde: number; alCambiar: (desde: number) => void }) {
  if (total <= limite) return null;
  const pagina = Math.floor(desde / limite) + 1;
  const paginas = Math.ceil(total / limite);
  return (
    <div className="mt-4 flex items-center justify-between gap-2 text-sm text-stone-500">
      <span>
        {desde + 1}–{Math.min(desde + limite, total)} de {total.toLocaleString("es-MX")}
      </span>
      <div className="flex items-center gap-2">
        <Boton tamano="sm" disabled={pagina <= 1} onClick={() => alCambiar(Math.max(0, desde - limite))}>
          Anterior
        </Boton>
        <span className="tabular-nums">
          {pagina} / {paginas}
        </span>
        <Boton tamano="sm" disabled={pagina >= paginas} onClick={() => alCambiar(desde + limite)}>
          Siguiente
        </Boton>
      </div>
    </div>
  );
}

// --- diálogo ----------------------------------------------------------------------

export function Dialogo({ abierto, alCerrar, titulo, children, pie }: { abierto: boolean; alCerrar: () => void; titulo: string; children: ReactNode; pie?: ReactNode }) {
  useEffect(() => {
    if (!abierto) return;
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && alCerrar();
    addEventListener("keydown", tecla);
    return () => removeEventListener("keydown", tecla);
  }, [abierto, alCerrar]);
  if (!abierto) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-stone-950/40 p-0 backdrop-blur-sm sm:items-center sm:p-4" onClick={alCerrar}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[92vh] w-full max-w-lg flex-col rounded-t-2xl bg-white shadow-xl sm:rounded-2xl dark:bg-stone-900"
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3 dark:border-stone-800">
          <h2 className="font-semibold">{titulo}</h2>
          <button onClick={alCerrar} className="rounded-md p-1 text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" aria-label="Cerrar">
            <X className="size-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {pie && <div className="flex justify-end gap-2 border-t border-stone-200 px-5 py-3 dark:border-stone-800">{pie}</div>}
      </div>
    </div>
  );
}
