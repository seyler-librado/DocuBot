import { ArrowRight, ClipboardCheck, FileCog, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCorridas, useDocumentos, useResumen, useSalud, useSaludIA } from "../api/consultas";
import { useEventos } from "../api/eventos";
import { Actividad, TarjetaCorrida } from "../componentes/corridas";
import { CuadriculaDocumentos } from "../componentes/documentos";
import { Aviso, Cifra, Encabezado, Seccion, Tarjeta, Vacio, cx } from "../componentes/ui";
import { bytes, numero } from "../util/formato";

function Indicador({ ok, texto }: { ok: boolean | null | undefined; texto: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-stone-500">
      <span className={cx("size-2 rounded-full", ok == null ? "bg-stone-300 dark:bg-stone-600" : ok ? "bg-emerald-500" : "bg-rose-500")} />
      {texto}
    </span>
  );
}

export default function Panel() {
  const { data: resumen } = useResumen();
  const { data: salud, isError: sinApi } = useSalud();
  const { data: ia } = useSaludIA();
  const { data: corridas } = useCorridas(4);
  const { data: documentos } = useDocumentos({ limite: 5 });
  const { eventos } = useEventos();
  const porRevisar = resumen?.fichas.revision ?? 0;
  const fichasListas = resumen?.fichas.ok ?? 0;
  const [consulta, setConsulta] = useState("");
  const navegar = useNavigate();

  return (
    <div>
      <Encabezado
        titulo="Panel"
        subtitulo="Descubre, descarga y cataloga documentos públicos según tus perfiles."
        acciones={
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <Indicador ok={salud?.base_datos.ok} texto="Base de datos" />
            <Indicador ok={ia?.ok} texto={ia ? (ia.proveedor === "ninguno" ? "Sin IA" : `IA: ${ia.proveedor}`) : "IA"} />
          </div>
        }
      />
      {sinApi && (
        <div className="mt-6">
          <Aviso>No se pudo hablar con la API. ¿Están arriba los contenedores? (docker compose up -d)</Aviso>
        </div>
      )}

      {!!resumen?.documentos && (
        <form
          className="relative mt-6"
          onSubmit={(e) => {
            e.preventDefault();
            if (consulta.trim().length >= 2) navegar(`/buscar?q=${encodeURIComponent(consulta.trim())}`);
          }}
        >
          <Search className="pointer-events-none absolute left-3.5 top-3 size-5 text-stone-400" />
          <input
            value={consulta}
            onChange={(e) => setConsulta(e.target.value)}
            placeholder={`Busca en ${numero(resumen.documentos)} documentos: un tema, una frase, un lugar…`}
            className="w-full rounded-xl border border-stone-300 bg-white py-2.5 pl-11 pr-4 text-base shadow-sm placeholder:text-stone-400 focus:border-marca-500 focus:outline-none focus:ring-2 focus:ring-marca-500/20 dark:border-stone-700 dark:bg-stone-900"
          />
        </form>
      )}

      <Tarjeta className="mt-6 grid grid-cols-2 gap-6 p-5 sm:grid-cols-4">
        <Cifra valor={numero(resumen?.documentos)} nombre="documentos" detalle={bytes(resumen?.bytes)} />
        <Cifra valor={numero(fichasListas)} nombre="fichas listas" />
        <Cifra valor={numero(resumen?.por_bajar)} nombre="aceptados por bajar" />
        <Cifra valor={numero(resumen?.corridas_activas)} nombre="corridas en curso" />
      </Tarjeta>

      {porRevisar > 0 && (
        <Link
          to="/revision"
          className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 hover:bg-amber-100 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200"
        >
          <span className="flex items-center gap-2">
            <ClipboardCheck className="size-4" /> {porRevisar} ficha(s) esperan revisión
          </span>
          <ArrowRight className="size-4" />
        </Link>
      )}

      <div className="grid gap-x-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <Seccion titulo="Corridas recientes" accion={<Link to="/corridas" className="text-sm text-marca-700 hover:underline dark:text-marca-100">Ver todas</Link>}>
            {corridas?.length ? (
              <div className="space-y-3">
                {corridas.map((c) => (
                  <TarjetaCorrida key={c.id} c={c} />
                ))}
              </div>
            ) : (
              <Vacio icono={<FileCog className="size-8" />} titulo="Todavía no hay corridas">
                Ve a <Link to="/perfiles" className="text-marca-700 underline">Perfiles</Link> y corre uno.
              </Vacio>
            )}
          </Seccion>
          {!!documentos?.elementos.length && (
            <Seccion titulo="Últimos documentos" accion={<Link to="/biblioteca" className="text-sm text-marca-700 hover:underline dark:text-marca-100">Biblioteca</Link>}>
              <CuadriculaDocumentos documentos={documentos.elementos} />
            </Seccion>
          )}
        </div>
        <Seccion titulo="Actividad en vivo">
          <Tarjeta className="px-4 py-1">
            <Actividad eventos={eventos} limite={14} />
          </Tarjeta>
        </Seccion>
      </div>
    </div>
  );
}
