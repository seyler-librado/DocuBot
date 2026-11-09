import { Search, Sparkles } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { Coincidencia, ResultadoBusqueda } from "../api/cliente";
import { useBuscar, useEstadoBusqueda, usePerfil, usePerfiles } from "../api/consultas";
import { Portada } from "../componentes/documentos";
import { Aviso, Cargando, Estado, Insignia, Paginacion, Selector, Tarjeta, Vacio, cx } from "../componentes/ui";
import { useDiferido } from "../util/diferido";
import { dominio, numero } from "../util/formato";

const LIMITE = 20;
type Modo = "mixta" | "palabras" | "tema";

/** Pinta el pasaje con sus coincidencias resaltadas (el texto se escapa: solo ⟦…⟧ se vuelve <mark>). */
function Resaltado({ texto }: { texto: string }) {
  const partes = texto.split(/(⟦[^⟧]*⟧)/g);
  return (
    <>
      {partes.map((p, i) =>
        p.startsWith("⟦") ? (
          <mark key={i} className="rounded bg-amber-200/70 px-0.5 text-inherit dark:bg-amber-500/30">
            {p.slice(1, -1)}
          </mark>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

function Pasaje({ c, documento }: { c: Coincidencia; documento: number }) {
  return (
    <div className="flex gap-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
      <span className="mt-0.5 shrink-0">
        {c.tipo === "tema" ? <Sparkles className="size-3.5 text-marca-600" aria-label="coincide por tema" /> : <span className="block w-3.5" />}
      </span>
      <p className="min-w-0">
        <Resaltado texto={c.texto} />
        {c.pagina && (
          <Link to={`/documentos/${documento}?pagina=${c.pagina}`} className="ml-1.5 whitespace-nowrap text-xs font-medium text-marca-700 hover:underline dark:text-marca-100">
            pág. {c.pagina}
          </Link>
        )}
      </p>
    </div>
  );
}

function Resultado({ r }: { r: ResultadoBusqueda }) {
  const pagina = r.coincidencias.find((c) => c.pagina)?.pagina;
  const enlace = `/documentos/${r.id}${pagina ? `?pagina=${pagina}` : ""}`;
  return (
    <Tarjeta className="flex gap-4 p-4">
      <Link to={enlace} className="hidden shrink-0 sm:block">
        <Portada id={r.id} className="h-32 w-24 rounded-md border border-stone-200 dark:border-stone-700" />
      </Link>
      <div className="min-w-0 flex-1">
        <Link to={enlace} className="line-clamp-2 font-medium leading-snug hover:text-marca-700 dark:hover:text-marca-100">
          {r.titulo || "Sin título"}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-stone-500">
          <span>{dominio(r.url)}</span>
          {r.tipo && <Insignia tono="marca">{r.tipo}</Insignia>}
          {r.ficha && <Estado valor={r.ficha.estado} />}
          {r.paginas && <span>{r.paginas} pág.</span>}
        </div>
        {r.coincidencias.length > 0 && (
          <div className="mt-3 space-y-2">
            {r.coincidencias.map((c, i) => (
              <Pasaje key={i} c={c} documento={r.id} />
            ))}
          </div>
        )}
      </div>
    </Tarjeta>
  );
}

const MODOS: { valor: Modo; texto: string; ayuda: string }[] = [
  { valor: "mixta", texto: "Mixta", ayuda: "palabras y tema, combinados" },
  { valor: "palabras", texto: "Palabras", ayuda: "las palabras exactas (sin importar acentos ni plurales)" },
  { valor: "tema", texto: "Por tema", ayuda: "documentos que hablan de lo mismo, aunque usen otras palabras" },
];

export default function Buscar() {
  const [params, setParams] = useSearchParams();
  const [texto, setTexto] = useState(params.get("q") ?? "");
  const q = useDiferido(texto, 400);
  const modo = (params.get("modo") as Modo) || "mixta";
  const perfil = params.get("perfil") ?? "";
  const tipo = params.get("tipo") ?? "";
  const ficha = params.get("ficha") ?? "";
  const desde = Number(params.get("desde") ?? 0);
  const { data: estado } = useEstadoBusqueda();
  const { data: perfiles } = usePerfiles();
  const { data: detalle } = usePerfil(perfil || undefined);
  const tipos = detalle?.config ? Object.entries(detalle.config.documentos.tipos) : [];
  const temaActivo = estado?.tema.activa ?? false;

  const fijar = (cambios: Record<string, string>) => {
    const nuevos = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) v ? nuevos.set(k, v) : nuevos.delete(k);
    if (!("desde" in cambios)) nuevos.delete("desde");
    setParams(nuevos, { replace: true });
  };
  useEffect(() => {
    if ((params.get("q") ?? "") !== q.trim()) fijar({ q: q.trim() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const consulta = params.get("q") ?? "";
  const { data, isFetching, error } = useBuscar({ q: consulta, modo, perfil, tipo, ficha, limite: LIMITE, desde });

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-semibold tracking-tight">Buscar</h1>
      <form className="relative mt-4" onSubmit={(e) => e.preventDefault()}>
        <Search className="pointer-events-none absolute left-3.5 top-3.5 size-5 text-stone-400" />
        <input
          id="buscador"
          autoFocus
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder='Un tema, una frase entre comillas, palabras a excluir con -…'
          className="w-full rounded-xl border border-stone-300 bg-white py-3 pl-11 pr-4 text-base shadow-sm placeholder:text-stone-400 focus:border-marca-500 focus:outline-none focus:ring-2 focus:ring-marca-500/20 dark:border-stone-700 dark:bg-stone-900"
        />
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border border-stone-300 p-0.5 dark:border-stone-700" role="radiogroup" aria-label="Tipo de búsqueda">
          {MODOS.map((m) => {
            const deshabilitado = m.valor !== "palabras" && !temaActivo;
            return (
              <button
                key={m.valor}
                role="radio"
                aria-checked={modo === m.valor}
                disabled={deshabilitado}
                title={deshabilitado ? "La búsqueda por tema está apagada (ver Ajustes)" : m.ayuda}
                onClick={() => fijar({ modo: m.valor === "mixta" ? "" : m.valor })}
                className={cx(
                  "rounded-md px-3 py-1 text-sm font-medium transition-colors disabled:opacity-40",
                  modo === m.valor ? "bg-marca-700 text-white" : "text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800",
                )}
              >
                {m.texto}
              </button>
            );
          })}
        </div>
        <Selector className="w-auto" value={perfil} onChange={(e) => fijar({ perfil: e.target.value, tipo: "" })} aria-label="Perfil">
          <option value="">Todos los perfiles</option>
          {perfiles?.map((p) => (
            <option key={p.nombre}>{p.nombre}</option>
          ))}
        </Selector>
        {tipos.length > 0 && (
          <Selector className="w-auto" value={tipo} onChange={(e) => fijar({ tipo: e.target.value })} aria-label="Tipo de documento">
            <option value="">Todos los tipos</option>
            {tipos.map(([clave, t]) => (
              <option key={clave} value={clave}>
                {t.nombre}
              </option>
            ))}
          </Selector>
        )}
        <Selector className="w-auto" value={ficha} onChange={(e) => fijar({ ficha: e.target.value })} aria-label="Estado de la ficha">
          <option value="">Cualquier ficha</option>
          <option value="ok">Fichas listas</option>
          <option value="revision">Por revisar</option>
        </Selector>
      </div>

      <div className="mt-6">
        {error ? (
          <Aviso>{(error as Error).message}</Aviso>
        ) : consulta.length < 2 ? (
          <Vacio icono={<Search className="size-8" />} titulo="¿Qué buscas?">
            <ul className="mt-2 space-y-1 text-left">
              <li>
                <span className="font-medium">Palabras:</span> «planeacion» encuentra «Planeación»; «reglamentos» encuentra «reglamento».
              </li>
              <li>
                <span className="font-medium">Frases y exclusiones:</span> <code>"agua potable" -drenaje</code>
              </li>
              {temaActivo && (
                <li>
                  <span className="font-medium">Por tema:</span> «reglas para manejar» encuentra reglamentos de tránsito.
                </li>
              )}
            </ul>
          </Vacio>
        ) : !data ? (
          <Cargando texto="Buscando…" />
        ) : !data.elementos.length ? (
          <Vacio titulo={`Nada encontrado para «${consulta}»`}>
            {modo === "palabras" && temaActivo && "Prueba la búsqueda por tema: encuentra documentos que usan otras palabras."}
          </Vacio>
        ) : (
          <>
            <p className={cx("mb-3 text-sm text-stone-500", isFetching && "opacity-60")}>
              {numero(data.total)} documento(s)
              {data.modo !== modo && " · búsqueda por palabras (la de tema está apagada)"}
            </p>
            <div className={cx("space-y-3", isFetching && "opacity-60")}>
              {data.elementos.map((r) => (
                <Resultado key={r.id} r={r} />
              ))}
            </div>
            <Paginacion total={data.total} limite={LIMITE} desde={desde} alCambiar={(d) => fijar({ desde: String(d) })} />
          </>
        )}
      </div>
    </div>
  );
}
