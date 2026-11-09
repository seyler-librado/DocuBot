import { FileCog, Play } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { ResumenPerfil } from "../api/cliente";
import { usePerfiles } from "../api/consultas";
import DialogoCorrer from "../componentes/DialogoCorrer";
import { Boton, Cargando, Encabezado, Insignia, Tarjeta, Vacio } from "../componentes/ui";

const NOMBRES_FUENTE: Record<string, string> = {
  semillas: "semillas",
  lista_dominios: "lista de dominios",
  buscador: "buscador",
  commoncrawl: "Common Crawl",
  wayback: "Internet Archive",
};

function TarjetaPerfil({ p, alCorrer }: { p: ResumenPerfil; alCorrer: () => void }) {
  return (
    <Tarjeta className="flex flex-col p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/perfiles/${encodeURIComponent(p.nombre)}`} className="font-medium hover:text-marca-700 dark:hover:text-marca-100">
            {p.nombre}
          </Link>
          <p className="truncate font-mono text-xs text-stone-500">{p.archivo}</p>
        </div>
        {p.valido ? <Insignia tono="ok">válido</Insignia> : <Insignia tono="error">{p.errores.length} error(es)</Insignia>}
      </div>
      {p.descripcion && <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">{p.descripcion}</p>}
      {p.valido ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {p.fuentes?.map((f, i) => (
            <Insignia key={i}>{NOMBRES_FUENTE[f] ?? f}</Insignia>
          ))}
          {p.dominios?.map((d) => (
            <Insignia key={d}>{d}</Insignia>
          ))}
          <Insignia tono="marca">{p.modo === "todos" ? "todos los documentos" : `${Object.keys(p.tipos_documento ?? {}).length} tipo(s)`}</Insignia>
          {!!p.campos?.length && <Insignia tono="marca">{p.campos.length} campo(s) de ficha</Insignia>}
        </div>
      ) : (
        <ul className="mt-3 space-y-1 font-mono text-xs text-rose-700 dark:text-rose-300">
          {p.errores.slice(0, 4).map((e) => (
            <li key={e}>{e}</li>
          ))}
          {p.errores.length > 4 && <li>… y {p.errores.length - 4} más</li>}
        </ul>
      )}
      <div className="mt-4 flex gap-2 pt-1">
        {p.valido && (
          <Boton variante="principal" icono={<Play className="size-4" />} onClick={alCorrer}>
            Correr
          </Boton>
        )}
        <Link to={`/perfiles/${encodeURIComponent(p.nombre)}`}>
          <Boton variante="fantasma">Ver perfil</Boton>
        </Link>
      </div>
    </Tarjeta>
  );
}

export default function Perfiles() {
  const { data, isLoading } = usePerfiles();
  const [correr, setCorrer] = useState<string | null>(null);
  return (
    <div>
      <Encabezado
        titulo="Perfiles"
        subtitulo={
          <>
            Cada perfil dice qué buscar. Están en <code className="font-mono">config/perfiles/</code>; se vuelven a leer al
            abrir esta página.
          </>
        }
      />
      <div className="mt-6">
        {isLoading ? (
          <Cargando />
        ) : !data?.length ? (
          <Vacio icono={<FileCog className="size-8" />} titulo="No hay perfiles">
            Copia <code className="font-mono">config/perfiles/ejemplo.yaml</code> con otro nombre y ajústalo.
          </Vacio>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {data.map((p) => (
              <TarjetaPerfil key={p.archivo} p={p} alCorrer={() => setCorrer(p.nombre)} />
            ))}
          </div>
        )}
      </div>
      {correr && <DialogoCorrer perfil={correr} abierto alCerrar={() => setCorrer(null)} />}
    </div>
  );
}
