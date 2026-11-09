import maplibregl, { type GeoJSONSource, type Map as MapaGL } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapPinned, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { urlPoligonos, type LugarMapa } from "../api/cliente";
import { useAjustes, useDocumentos, useMapa, useNiveles, usePerfiles } from "../api/consultas";
import { Portada } from "../componentes/documentos";
import { Cargando, Estado, Insignia, Selector, Tarjeta, Vacio, cx } from "../componentes/ui";
import { numero } from "../util/formato";

const MARCA = "#0f766e";
const oscuro = () => document.documentElement.classList.contains("dark");
// MapLibre pide los datos desde un worker: necesita direcciones absolutas
const absoluta = (ruta: string) => new URL(ruta, location.origin).href;

function PanelLugar({ lugar, perfil, alCerrar }: { lugar: LugarMapa; perfil: string; alCerrar: () => void }) {
  const { data, isLoading } = useDocumentos({ perfil, lugar: lugar.id, limite: 50 });
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-2 border-b border-stone-200 p-4 dark:border-stone-800">
        <div className="min-w-0">
          <h2 className="font-semibold leading-snug">{lugar.nombre}</h2>
          <p className="text-xs text-stone-500">
            {lugar.nivel}
            {lugar.padre && ` · ${lugar.padre}`} · {numero(data?.total ?? lugar.documentos)} documento(s)
          </p>
        </div>
        <button onClick={alCerrar} className="rounded-md p-1 text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800" aria-label="Cerrar">
          <X className="size-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <Cargando />
        ) : !data?.elementos.length ? (
          <p className="p-4 text-sm text-stone-500">Sin documentos aquí.</p>
        ) : (
          <ul className="space-y-1">
            {data.elementos.map((d) => (
              <li key={d.id}>
                <Link to={`/documentos/${d.id}`} className="flex gap-3 rounded-lg p-2 hover:bg-stone-100 dark:hover:bg-stone-800">
                  <Portada id={d.id} className="h-16 w-12 shrink-0 rounded border border-stone-200 dark:border-stone-700" />
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-sm font-medium">{d.titulo || "Sin título"}</span>
                    <span className="mt-1 flex flex-wrap gap-1">
                      {d.tipo && <Insignia tono="marca">{d.tipo}</Insignia>}
                      {d.ficha && <Estado valor={d.ficha.estado} />}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function Mapa() {
  const [params, setParams] = useSearchParams();
  const { data: perfiles } = usePerfiles();
  const conGeo = useMemo(() => (perfiles ?? []).filter((p) => p.valido && p.geografia), [perfiles]);
  const perfil = params.get("perfil") || conGeo[0]?.nombre;
  const catalogo = conGeo.find((p) => p.nombre === perfil)?.catalogo ?? undefined;
  const { data: mapa, isLoading } = useMapa(perfil);
  const { data: niveles } = useNiveles(catalogo);
  const { data: ajustes } = useAjustes();
  const [elegido, setElegido] = useState<LugarMapa | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);
  const mapaGL = useRef<MapaGL | null>(null);
  const [listo, setListo] = useState(false);

  const general = niveles?.find((n) => !n.tiene_padre && n.con_poligono)?.nivel;
  const detallado = [...(niveles ?? [])].reverse().find((n) => n.tiene_padre && n.con_poligono)?.nivel;
  const porId = useMemo(() => new Map((mapa?.lugares ?? []).map((l) => [l.id, l])), [mapa]);

  // crear el mapa una vez
  useEffect(() => {
    if (!contenedor.current || !ajustes || mapaGL.current) return;
    const m = new maplibregl.Map({
      container: contenedor.current,
      style: {
        version: 8,
        sources: {
          base: { type: "raster", tiles: [ajustes.mapa.teselas], tileSize: 256, attribution: ajustes.mapa.atribucion, maxzoom: 19 },
        },
        layers: [
          { id: "fondo", type: "background", paint: { "background-color": oscuro() ? "#1c1917" : "#f5f5f4" } },
          { id: "base", type: "raster", source: "base", paint: { "raster-opacity": oscuro() ? 0.35 : 0.75, "raster-saturation": -0.6 } },
        ],
      },
      center: [-102, 23.6],
      zoom: 4.2,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    m.on("load", () => setListo(true));
    m.on("error", (e) => console.error("mapa:", e.error?.message ?? e));
    (contenedor.current as HTMLDivElement & { __mapa?: MapaGL }).__mapa = m; // para pruebas automáticas de la interfaz
    mapaGL.current = m;
    return () => {
      m.remove();
      mapaGL.current = null;
      setListo(false);
    };
  }, [ajustes]);

  // polígonos del catálogo
  useEffect(() => {
    const m = mapaGL.current;
    if (!m || !listo || !catalogo) return;
    for (const capa of ["general-relleno", "detalle-relleno", "detalle-borde", "general-borde", "puntos"]) if (m.getLayer(capa)) m.removeLayer(capa);
    for (const fuente of ["detalle", "general", "puntos"]) if (m.getSource(fuente)) m.removeSource(fuente);
    const linea = oscuro() ? "#57534e" : "#a8a29e";
    if (general) {
      // los documentos de nivel general (p. ej. estatales) sombrean todo su lugar, más tenue
      m.addSource("general", { type: "geojson", data: absoluta(urlPoligonos(catalogo, general)) });
      m.addLayer({
        id: "general-relleno",
        type: "fill",
        source: "general",
        paint: {
          "fill-color": "#2dd4bf",
          "fill-opacity": ["case", ["boolean", ["feature-state", "elegido"], false], 0.4, [">", ["coalesce", ["feature-state", "docs"], 0], 0], 0.18, 0],
        },
      });
    }
    if (detallado) {
      m.addSource("detalle", { type: "geojson", data: absoluta(urlPoligonos(catalogo, detallado)) });
      m.addLayer({
        id: "detalle-relleno",
        type: "fill",
        source: "detalle",
        paint: {
          "fill-color": [
            "interpolate", ["linear"], ["coalesce", ["feature-state", "docs"], 0],
            0, "rgba(0,0,0,0)", 1, "#99f6e4", 5, "#2dd4bf", 20, "#0d9488", 60, "#134e4a",
          ],
          "fill-opacity": ["case", ["boolean", ["feature-state", "elegido"], false], 0.85, 0.6],
        },
      });
      m.addLayer({
        id: "detalle-borde",
        type: "line",
        source: "detalle",
        paint: {
          "line-color": ["case", ["boolean", ["feature-state", "elegido"], false], MARCA, linea],
          "line-width": ["case", ["boolean", ["feature-state", "elegido"], false], 2.5, 0.3],
        },
      });
    }
    if (general) {
      m.addLayer({ id: "general-borde", type: "line", source: "general", paint: { "line-color": oscuro() ? "#a8a29e" : "#57534e", "line-width": 1 } });
    }
    m.addSource("puntos", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    m.addLayer({
      id: "puntos",
      type: "circle",
      source: "puntos",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "documentos"], 1, 4, 10, 9, 50, 15],
        "circle-color": ["case", [">", ["get", "revision"], 0], "#f59e0b", MARCA],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.5,
        "circle-opacity": 0.9,
      },
    });
    const elegir = (id: number) => {
      const lugar = porIdRef.current.get(id);
      if (lugar) setElegido(lugar);
    };
    m.on("click", "puntos", (e) => {
      const id = e.features?.[0]?.properties?.id;
      if (id != null) elegir(Number(id));
    });
    m.on("click", "general-relleno", (e) => {
      const id = e.features?.[0]?.id;
      if (id != null && porIdRef.current.has(Number(id))) elegir(Number(id));
    });
    m.on("click", "detalle-relleno", (e) => {
      const id = e.features?.[0]?.id;
      if (id != null && porIdRef.current.has(Number(id))) elegir(Number(id));
    });
    for (const capa of ["puntos", "detalle-relleno"]) {
      m.on("mouseenter", capa, () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", capa, () => (m.getCanvas().style.cursor = ""));
    }
  }, [listo, catalogo, general, detallado]);

  const porIdRef = useRef(porId);
  porIdRef.current = porId;

  // conteos: color de cada polígono y puntos
  useEffect(() => {
    const m = mapaGL.current;
    if (!m || !listo || !mapa) return;
    const aplicar = () => {
      for (const fuente of ["detalle", "general"]) {
        if (!m.getSource(fuente)) continue;
        m.removeFeatureState({ source: fuente });
        for (const l of mapa.lugares) m.setFeatureState({ source: fuente, id: l.id }, { docs: l.documentos });
      }
      (m.getSource("puntos") as GeoJSONSource | undefined)?.setData({
        type: "FeatureCollection",
        features: mapa.lugares
          .filter((l) => l.lon != null && l.lat != null)
          .map((l) => ({ type: "Feature", properties: { id: l.id, documentos: l.documentos, revision: l.revision }, geometry: { type: "Point", coordinates: [l.lon!, l.lat!] } })),
      });
    };
    if ((m.getSource("detalle") && !m.isSourceLoaded("detalle")) || (m.getSource("general") && !m.isSourceLoaded("general"))) m.once("idle", aplicar);
    else aplicar();
  }, [listo, mapa, detallado, general]);

  // encuadrar el catálogo la primera vez
  const encuadrado = useRef<string | null>(null);
  useEffect(() => {
    const m = mapaGL.current;
    if (!m || !listo || !mapa?.extension || encuadrado.current === mapa.catalogo) return;
    const [x1, y1, x2, y2] = mapa.extension;
    m.fitBounds([[x1, y1], [x2, y2]], { padding: 40, duration: 0 });
    encuadrado.current = mapa.catalogo;
  }, [listo, mapa]);

  // resaltar el lugar elegido
  useEffect(() => {
    const m = mapaGL.current;
    if (!m || !listo) return;
    for (const fuente of ["detalle", "general"]) {
      if (!m.getSource(fuente)) continue;
      for (const l of mapa?.lugares ?? []) m.setFeatureState({ source: fuente, id: l.id }, { elegido: l.id === elegido?.id });
    }
    if (elegido?.lon != null && elegido.lat != null) m.easeTo({ center: [elegido.lon, elegido.lat], zoom: Math.max(m.getZoom(), 6.5) });
  }, [elegido, listo, mapa]);

  if (perfiles && !conGeo.length) {
    return (
      <Vacio icono={<MapPinned className="size-8" />} titulo="Ningún perfil tiene geografía">
        Agrega <code className="font-mono">geografia.catalogo</code> a un perfil (hay un catálogo de México en{" "}
        <code className="font-mono">config/catalogos/mexico</code>) para ver sus documentos en el mapa.
      </Vacio>
    );
  }

  const e = mapa?.por_estado ?? {};
  const dudosos = (e.ambiguo ?? 0) + (e.revision ?? 0);
  return (
    <div className="-mx-4 -my-6 flex h-[calc(100dvh-57px)] flex-col sm:-mx-6 lg:-my-8 lg:h-dvh">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-stone-200 bg-white px-4 py-3 sm:px-6 dark:border-stone-800 dark:bg-stone-900">
        <h1 className="text-lg font-semibold">Mapa</h1>
        {conGeo.length > 1 && (
          <Selector className="w-auto" value={perfil} onChange={(ev) => setParams({ perfil: ev.target.value })} aria-label="Perfil">
            {conGeo.map((p) => (
              <option key={p.nombre}>{p.nombre}</option>
            ))}
          </Selector>
        )}
        {mapa && (
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-stone-600 dark:text-stone-400">
            <span>
              <strong className="tabular-nums text-stone-900 dark:text-stone-100">{numero(mapa.documentos)}</strong> documentos
            </span>
            <span>
              <strong className="tabular-nums text-stone-900 dark:text-stone-100">{numero(e.asignado ?? 0)}</strong> ubicados en{" "}
              {numero(mapa.lugares.length)} lugares
            </span>
            {(e.sin_lugar ?? 0) + mapa.sin_procesar > 0 && <span>{numero((e.sin_lugar ?? 0) + mapa.sin_procesar)} sin lugar</span>}
            {dudosos > 0 && (
              <Link to="/revision?vista=lugares" className="text-amber-700 hover:underline dark:text-amber-400">
                {numero(dudosos)} por decidir
              </Link>
            )}
          </div>
        )}
      </div>
      <div className="relative flex-1">
        {/* MapLibre le pone position: relative a su contenedor: el que ocupa el espacio es el de afuera */}
        <div className="absolute inset-0">
          <div ref={contenedor} className="h-full w-full" />
        </div>
        {(isLoading || !listo) && (
          <div className="absolute left-4 top-4">
            <Tarjeta className="px-3">
              <Cargando texto="Cargando mapa…" />
            </Tarjeta>
          </div>
        )}
        <div className="pointer-events-none absolute bottom-6 left-4 hidden sm:block">
          <Tarjeta className="pointer-events-auto space-y-1.5 px-3 py-2 text-xs text-stone-600 dark:text-stone-300">
            <div className="font-medium">Documentos por lugar</div>
            <div className="flex items-center gap-1">
              {["#99f6e4", "#2dd4bf", "#0d9488", "#134e4a"].map((c) => (
                <span key={c} className="h-2.5 w-6 rounded-sm" style={{ background: c }} />
              ))}
              <span className="ml-1">1 → 60+</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-full bg-amber-500" /> con lugar por revisar
            </div>
          </Tarjeta>
        </div>
        {elegido && perfil && (
          <div className={cx("absolute inset-x-0 bottom-0 max-h-[55%] sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-96")}>
            <div className="h-full overflow-hidden rounded-t-2xl border border-stone-200 bg-white shadow-xl sm:rounded-none sm:border-y-0 sm:border-r-0 dark:border-stone-800 dark:bg-stone-900">
              <PanelLugar lugar={elegido} perfil={perfil} alCerrar={() => setElegido(null)} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
