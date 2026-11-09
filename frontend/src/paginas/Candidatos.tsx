import { usePerfiles } from "../api/consultas";
import TablaCandidatos from "../componentes/TablaCandidatos";
import { Encabezado } from "../componentes/ui";

export default function Candidatos() {
  const { data: perfiles } = usePerfiles();
  return (
    <div>
      <Encabezado
        titulo="Candidatos"
        subtitulo="Todas las URLs de documentos que se han encontrado, con su puntaje. Acepta lo que el filtro dejó fuera o rechaza lo que no sirve."
      />
      <div className="mt-6">
        <TablaCandidatos perfiles={perfiles?.map((p) => p.nombre)} />
      </div>
    </div>
  );
}
