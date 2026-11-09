import { ChevronLeft, ChevronRight, Download, ExternalLink, Maximize2, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { Cargando } from "./ui";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

function BotonBarra({ titulo, onClick, disabled, children }: { titulo: string; onClick?: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      title={titulo}
      aria-label={titulo}
      onClick={onClick}
      disabled={disabled}
      className="rounded-md p-1.5 text-stone-300 hover:bg-white/10 hover:text-white disabled:opacity-30"
    >
      {children}
    </button>
  );
}

/** Visor de PDF: una página a la vez (rápido aun con documentos de cientos de páginas). */
export default function VisorPDF({ url, nombre, paginaInicial }: { url: string; nombre?: string; paginaInicial?: number }) {
  const contenedor = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(600);
  const [paginas, setPaginas] = useState(0);
  const [pagina, setPagina] = useState(paginaInicial ?? 1);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const el = contenedor.current;
    if (!el) return;
    const observador = new ResizeObserver(([e]) => setAncho(Math.max(240, e.contentRect.width - 32)));
    observador.observe(el);
    return () => observador.disconnect();
  }, []);

  useEffect(() => {
    setPagina(paginaInicial ?? 1);
    setError(null);
  }, [url, paginaInicial]);

  const ir = useCallback((n: number) => setPagina((p) => Math.min(Math.max(1, n), paginas || p)), [paginas]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select")) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") ir(pagina + 1);
      if (e.key === "ArrowLeft" || e.key === "PageUp") ir(pagina - 1);
    };
    addEventListener("keydown", tecla);
    return () => removeEventListener("keydown", tecla);
  }, [ir, pagina]);

  const iz = ZOOMS.indexOf(zoom);

  return (
    <div className="flex h-full min-h-[60vh] flex-col overflow-hidden rounded-xl bg-stone-800 ring-1 ring-stone-900/5 dark:bg-stone-900 dark:ring-white/10">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-2 py-1.5 text-sm text-stone-200">
        <div className="flex items-center gap-1">
          <BotonBarra titulo="Página anterior" onClick={() => ir(pagina - 1)} disabled={pagina <= 1}>
            <ChevronLeft className="size-4" />
          </BotonBarra>
          <input
            aria-label="Página"
            value={pagina}
            onChange={(e) => ir(Number(e.target.value) || 1)}
            className="w-12 rounded bg-white/10 px-1.5 py-0.5 text-center tabular-nums focus:outline-none focus:ring-1 focus:ring-white/40"
          />
          <span className="tabular-nums text-stone-400">/ {paginas || "…"}</span>
          <BotonBarra titulo="Página siguiente" onClick={() => ir(pagina + 1)} disabled={!paginas || pagina >= paginas}>
            <ChevronRight className="size-4" />
          </BotonBarra>
        </div>
        <div className="flex items-center gap-1">
          <BotonBarra titulo="Alejar" onClick={() => setZoom(ZOOMS[Math.max(0, iz - 1)])} disabled={iz <= 0}>
            <Minus className="size-4" />
          </BotonBarra>
          <span className="w-12 text-center tabular-nums text-stone-400">{Math.round(zoom * 100)}%</span>
          <BotonBarra titulo="Acercar" onClick={() => setZoom(ZOOMS[Math.min(ZOOMS.length - 1, iz + 1)])} disabled={iz >= ZOOMS.length - 1}>
            <Plus className="size-4" />
          </BotonBarra>
          <BotonBarra titulo="Ajustar al ancho" onClick={() => setZoom(1)}>
            <Maximize2 className="size-4" />
          </BotonBarra>
          <span className="mx-1 h-4 w-px bg-white/10" />
          <a href={url} target="_blank" rel="noreferrer" title="Abrir en otra pestaña" className="rounded-md p-1.5 text-stone-300 hover:bg-white/10 hover:text-white">
            <ExternalLink className="size-4" />
          </a>
          <a href={url} download={nombre} title="Descargar" className="rounded-md p-1.5 text-stone-300 hover:bg-white/10 hover:text-white">
            <Download className="size-4" />
          </a>
        </div>
      </div>
      <div ref={contenedor} className="flex-1 overflow-auto p-4">
        {error ? (
          <div className="rounded-lg bg-white/5 p-6 text-center text-sm text-stone-300">
            No se pudo mostrar el documento aquí ({error}).{" "}
            <a href={url} target="_blank" rel="noreferrer" className="underline">
              Ábrelo en otra pestaña
            </a>
            .
          </div>
        ) : (
          <Document
            file={url}
            onLoadSuccess={({ numPages }) => setPaginas(numPages)}
            onLoadError={(e) => setError(e.message)}
            loading={<div className="text-stone-300"><Cargando texto="Abriendo documento…" /></div>}
            className="flex justify-center"
          >
            <Page
              pageNumber={pagina}
              width={ancho * zoom}
              className="shadow-2xl"
              loading={<div style={{ width: ancho * zoom, height: ancho * zoom * 1.3 }} className="bg-white/5" />}
            />
          </Document>
        )}
      </div>
    </div>
  );
}
