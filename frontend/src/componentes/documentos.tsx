import { FileText } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { urlPortada, type DocumentoResumen } from "../api/cliente";
import { bytes, dominio } from "../util/formato";
import { Estado, Insignia, cx } from "./ui";

export function Portada({ id, className }: { id: number; className?: string }) {
  const [fallo, setFallo] = useState(false);
  return (
    <div className={cx("relative overflow-hidden bg-stone-100 dark:bg-stone-800", className)}>
      {fallo ? (
        <div className="flex h-full items-center justify-center text-stone-400">
          <FileText className="size-10" />
        </div>
      ) : (
        <img src={urlPortada(id)} alt="" loading="lazy" onError={() => setFallo(true)} className="h-full w-full object-cover object-top" />
      )}
    </div>
  );
}

export function TarjetaDocumento({ d }: { d: DocumentoResumen }) {
  return (
    <Link
      to={`/documentos/${d.id}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-stone-200 bg-white transition-shadow hover:shadow-md dark:border-stone-800 dark:bg-stone-900"
    >
      <Portada id={d.id} className="aspect-[4/5] border-b border-stone-200 dark:border-stone-800" />
      <div className="flex flex-1 flex-col gap-2 p-3">
        <p className="line-clamp-3 text-sm font-medium leading-snug group-hover:text-marca-700 dark:group-hover:text-marca-100">
          {d.titulo || "Sin título"}
        </p>
        <p className="truncate text-xs text-stone-500">{dominio(d.url)}</p>
        <div className="mt-auto flex flex-wrap gap-1">
          {d.tipo && <Insignia tono="marca">{d.tipo}</Insignia>}
          {d.ficha ? <Estado valor={d.ficha.estado} /> : <Insignia>sin ficha</Insignia>}
          {d.nuevo && <Insignia tono="info">nuevo</Insignia>}
        </div>
        <p className="text-xs text-stone-400">
          {d.paginas ? `${d.paginas} pág. · ` : ""}
          {bytes(d.bytes)}
        </p>
      </div>
    </Link>
  );
}

export function CuadriculaDocumentos({ documentos }: { documentos: DocumentoResumen[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {documentos.map((d) => (
        <TarjetaDocumento key={d.id} d={d} />
      ))}
    </div>
  );
}
