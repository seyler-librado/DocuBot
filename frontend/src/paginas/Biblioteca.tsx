import { Library, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useDocumentos, usePerfil, usePerfiles } from "../api/consultas";
import { CuadriculaDocumentos } from "../componentes/documentos";
import { Cargando, Encabezado, Entrada, Paginacion, Selector, Vacio } from "../componentes/ui";
import { useDiferido } from "../util/diferido";
import { numero } from "../util/formato";

const LIMITE = 24;

export default function Biblioteca() {
  const [params, setParams] = useSearchParams();
  const perfil = params.get("perfil") ?? "";
  const tipo = params.get("tipo") ?? "";
  const ficha = params.get("ficha") ?? "";
  const desde = Number(params.get("desde") ?? 0);
  const [texto, setTexto] = useState(params.get("q") ?? "");
  const q = useDiferido(texto);

  const fijar = (cambios: Record<string, string>) => {
    const nuevos = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) v ? nuevos.set(k, v) : nuevos.delete(k);
    if (!("desde" in cambios)) nuevos.delete("desde");
    setParams(nuevos, { replace: true });
  };
  useEffect(() => {
    if ((params.get("q") ?? "") !== q) fijar({ q });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const { data: perfiles } = usePerfiles();
  const { data: detalle } = usePerfil(perfil || undefined);
  const tipos = detalle?.config ? Object.entries(detalle.config.documentos.tipos) : [];
  const { data, isLoading, isFetching } = useDocumentos({ perfil, tipo, ficha, q, limite: LIMITE, desde });

  return (
    <div>
      <Encabezado titulo="Biblioteca" subtitulo={data ? `${numero(data.total)} documento(s)` : "Los documentos descargados, con su ficha."} />
      <div className="mt-6 flex flex-wrap gap-2">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-2.5 top-2 size-4 text-stone-400" />
          <Entrada className="pl-8" placeholder="Buscar en título, ficha o URL…" value={texto} onChange={(e) => setTexto(e.target.value)} />
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
          <option value="ilegible">Ilegibles</option>
          <option value="error">Con error</option>
          <option value="sin">Sin ficha</option>
        </Selector>
        {isFetching && !isLoading && <span className="self-center text-xs text-stone-400">actualizando…</span>}
      </div>
      <div className="mt-6">
        {isLoading ? (
          <Cargando />
        ) : !data?.elementos.length ? (
          <Vacio icono={<Library className="size-8" />} titulo={q || perfil || tipo || ficha ? "Nada coincide con esos filtros" : "Todavía no hay documentos"}>
            {!(q || perfil || tipo || ficha) && "Corre un perfil: lo que se descargue aparecerá aquí."}
          </Vacio>
        ) : (
          <>
            <CuadriculaDocumentos documentos={data.elementos} />
            <Paginacion total={data.total} limite={LIMITE} desde={desde} alCambiar={(d) => fijar({ desde: String(d) })} />
          </>
        )}
      </div>
    </div>
  );
}
