import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCheck, ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, urlArchivo, type DefCampo, type Ficha } from "../api/cliente";
import { useDocumento, usePerfil, usePerfiles } from "../api/consultas";
import FormFicha from "../componentes/FormFicha";
import LugarDocumento from "../componentes/LugarDocumento";
import VisorPDF from "../componentes/VisorPDF";
import { Aviso, Boton, Cargando, Confianza, Estado, Insignia, Pestanas, Tarjeta } from "../componentes/ui";
import { bytes, dominio, fecha, numero } from "../util/formato";

function camposDe(ficha: Ficha | undefined, definidos: Record<string, DefCampo> | undefined): Record<string, DefCampo> {
  if (definidos && Object.keys(definidos).length) return definidos;
  // el perfil ya no está: se editan como texto los campos que tenga la ficha
  return Object.fromEntries(
    Object.keys(ficha?.campos ?? {}).map((k) => [k, { tipo: "texto", requerido: false, opciones: [], descripcion: "" } as DefCampo]),
  );
}

function PanelFicha({ documentoId, ficha, perfil }: { documentoId: number; ficha: Ficha | undefined; perfil: string }) {
  const { data: detallePerfil } = usePerfil(perfil);
  const qc = useQueryClient();
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ["documento", documentoId] });
    qc.invalidateQueries({ queryKey: ["fichas"] });
    qc.invalidateQueries({ queryKey: ["resumen"] });
    qc.invalidateQueries({ queryKey: ["documentos"] });
  };
  const guardar = useMutation({ mutationFn: (campos: Record<string, unknown>) => api.guardarFicha(documentoId, perfil, campos), onSuccess: refrescar });
  const aprobar = useMutation({ mutationFn: () => api.aprobarFicha(documentoId, perfil), onSuccess: refrescar });
  const rehacer = useMutation({ mutationFn: () => api.rehacerFicha(documentoId, perfil), onSuccess: refrescar });
  const campos = camposDe(ficha, detallePerfil?.config?.fichas.campos);
  const control = ficha?.control ?? {};

  return (
    <div className="space-y-4">
      {ficha ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Estado valor={ficha.estado} />
          <Confianza valor={ficha.confianza} />
          {typeof control.tipo_ia === "string" && <Insignia title="Tipo según la IA">IA: {control.tipo_ia === "OTRO" ? "otro tipo" : control.tipo_ia}</Insignia>}
        </div>
      ) : (
        <Aviso tono="info">Todavía no hay ficha para este perfil.</Aviso>
      )}
      {!!ficha?.motivos.length && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200">
          <p className="flex items-center gap-1.5 font-medium">
            <AlertTriangle className="size-4" /> Para revisar
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {ficha.motivos.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {Object.keys(campos).length > 0 && (
        <FormFicha campos={campos} valores={ficha?.campos ?? {}} guardando={guardar.isPending} alGuardar={(v) => guardar.mutate(v)} />
      )}
      {guardar.isSuccess && guardar.data.motivos.length > 0 && <Aviso tono="aviso">Guardada, pero: {guardar.data.motivos.join("; ")}</Aviso>}
      <div className="flex flex-wrap gap-2 border-t border-stone-200 pt-4 dark:border-stone-800">
        {ficha && ficha.estado !== "ok" && (
          <Boton icono={<CheckCheck className="size-4" />} cargando={aprobar.isPending} onClick={() => aprobar.mutate()}>
            Aprobar así
          </Boton>
        )}
        <Boton variante="fantasma" icono={<RefreshCw className="size-4" />} cargando={rehacer.isPending} onClick={() => rehacer.mutate()}>
          {ficha ? "Rehacer con IA" : "Hacer ficha con IA"}
        </Boton>
      </div>
      {rehacer.isSuccess && <p className="text-xs text-stone-500">En la cola; la ficha se actualiza sola cuando termine.</p>}
      {(rehacer.isError || aprobar.isError || guardar.isError) && (
        <Aviso>{((rehacer.error || aprobar.error || guardar.error) as Error).message}</Aviso>
      )}
      {ficha && (
        <p className="text-xs text-stone-400">
          {ficha.modelo && `${ficha.modelo} · `}
          {typeof control.metodo === "string" && `leída por ${control.metodo} · `}
          {typeof control.segundos === "number" && `${control.segundos} s · `}
          {fecha(ficha.actualizado)}
        </p>
      )}
    </div>
  );
}

export default function Documento() {
  const id = Number(useParams().id);
  const navegar = useNavigate();
  const [params] = useSearchParams();
  const paginaInicial = Number(params.get("pagina")) || undefined;
  const { data: d, isLoading, error } = useDocumento(id);
  const { data: perfiles } = usePerfiles();
  const [perfil, setPerfil] = useState<string>("");
  useEffect(() => {
    if (d && !d.perfiles.includes(perfil)) setPerfil(d.fichas[0]?.perfil ?? d.perfiles[0] ?? "");
  }, [d, perfil]);

  if (isLoading) return <Cargando />;
  if (error || !d) return <Aviso>No existe el documento #{id}.</Aviso>;
  const ficha = d.fichas.find((f) => f.perfil === perfil);
  const principal = d.fuentes[0];
  const titulo = ficha?.titulo || principal?.ancla || `Documento #${d.id}`;
  const esPdf = d.mime === "application/pdf";

  return (
    <div className="mx-auto max-w-[1600px]">
      <button onClick={() => navegar(-1)} className="mb-3 inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-800 dark:hover:text-stone-200">
        <ArrowLeft className="size-4" /> Volver
      </button>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0 lg:sticky lg:top-6 lg:h-[calc(100dvh-5rem)]">
          {esPdf ? (
            <VisorPDF url={urlArchivo(d.id)} nombre={`${d.sha256.slice(0, 12)}.pdf`} paginaInicial={paginaInicial} />
          ) : (
            <Tarjeta className="p-6 text-sm">
              Este archivo ({d.mime}) no se puede mostrar aquí.{" "}
              <a href={urlArchivo(d.id)} className="text-marca-700 underline">
                Descárgalo
              </a>
              .
            </Tarjeta>
          )}
        </div>

        <div className="min-w-0 space-y-6">
          <div>
            <h1 className="text-xl font-semibold leading-snug text-balance">{titulo}</h1>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {principal?.tipo && <Insignia tono="marca">{principal.tipo}</Insignia>}
              {principal?.nuevo === true && <Insignia tono="info">nuevo</Insignia>}
              {principal?.nuevo === false && <Insignia>ya se tenía</Insignia>}
              {d.fuentes.some((f) => f.respaldo) && <Insignia tono="aviso">del Internet Archive</Insignia>}
              {d.texto && <Insignia>{d.texto.metodo === "escaneado" ? "escaneado" : d.texto.metodo === "ilegible" ? "ilegible" : "con texto"}</Insignia>}
            </div>
          </div>

          <Tarjeta className="p-4">
            {d.perfiles.length > 1 && (
              <div className="mb-4">
                <Pestanas valor={perfil} alCambiar={setPerfil} opciones={d.perfiles.map((p) => ({ valor: p, texto: p }))} />
              </div>
            )}
            {perfil ? <PanelFicha documentoId={d.id} ficha={ficha} perfil={perfil} /> : <p className="text-sm text-stone-500">Sin perfil.</p>}
          </Tarjeta>

          {(d.lugares.length > 0 || perfiles?.some((p) => p.nombre === perfil && p.catalogo)) && (
            <LugarDocumento
              documentoId={d.id}
              lugares={d.lugares}
              catalogo={perfiles?.find((p) => p.nombre === perfil)?.catalogo ?? null}
            />
          )}

          <section>
            <h2 className="mb-2 text-sm font-semibold text-stone-500">De dónde salió</h2>
            <Tarjeta className="divide-y divide-stone-100 dark:divide-stone-800">
              {d.fuentes.map((f, i) => (
                <div key={i} className="px-4 py-3 text-sm">
                  <a href={f.url} target="_blank" rel="noreferrer" className="flex items-start gap-1 break-all font-medium hover:text-marca-700">
                    {f.url} <ExternalLink className="mt-0.5 size-3.5 shrink-0" />
                  </a>
                  <p className="mt-1 text-xs text-stone-500">
                    {f.fuente}
                    {f.puntaje != null && ` · ${f.puntaje} puntos`}
                    {f.ancla && ` · enlace: «${f.ancla}»`}
                    {f.lugar && ` · lugar ${f.lugar}`}
                  </p>
                  {f.pagina_origen && (
                    <a href={f.pagina_origen} target="_blank" rel="noreferrer" className="mt-0.5 block truncate text-xs text-stone-400 hover:text-marca-700">
                      encontrado en {dominio(f.pagina_origen)}
                      {new URL(f.pagina_origen).pathname}
                    </a>
                  )}
                </div>
              ))}
            </Tarjeta>
          </section>

          {d.texto && (
            <details className="rounded-xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900">
              <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
                Texto extraído <span className="font-normal text-stone-500">· {numero(d.texto.caracteres)} caracteres</span>
              </summary>
              <div className="border-t border-stone-200 px-4 py-3 dark:border-stone-800">
                {d.texto.error ? (
                  <p className="text-sm text-stone-500">{d.texto.error}</p>
                ) : d.texto.metodo === "escaneado" ? (
                  <p className="text-sm text-stone-500">El documento está escaneado: no tiene capa de texto. La IA lo lee por imagen.</p>
                ) : (
                  <pre className="max-h-96 overflow-auto whitespace-pre-wrap font-sans text-xs leading-relaxed text-stone-600 dark:text-stone-300">{d.texto.inicio}</pre>
                )}
              </div>
            </details>
          )}

          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs text-stone-500">
            <dt>Tamaño</dt>
            <dd className="text-right text-stone-700 dark:text-stone-300">{bytes(d.bytes)}</dd>
            <dt>Páginas</dt>
            <dd className="text-right text-stone-700 dark:text-stone-300">{d.paginas ?? "—"}</dd>
            <dt>Descargado</dt>
            <dd className="text-right text-stone-700 dark:text-stone-300">{fecha(d.creado)}</dd>
            <dt>Huella</dt>
            <dd className="truncate text-right font-mono text-stone-700 dark:text-stone-300" title={d.sha256}>
              {d.sha256.slice(0, 16)}…
            </dd>
          </dl>
          <Link to="/biblioteca" className="text-sm text-marca-700 hover:underline dark:text-marca-100">
            ← Biblioteca
          </Link>
        </div>
      </div>
    </div>
  );
}
