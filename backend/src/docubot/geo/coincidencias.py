"""¿De qué lugar habla un texto? Candidatos con puntaje, nunca un nombre suelto.

1. Se buscan en el texto los nombres y alias del catálogo (la coincidencia más
   larga gana: «Benito Juárez» no cuenta también como «Juárez»).
2. Cada mención suma según dónde y cómo aparece:
   - en el título o en el campo de lugar que llenó la IA, vale más;
   - precedida de «municipio de», «ayuntamiento de»... favorece al municipio;
     precedida de «estado de», «gobierno del estado»... favorece al estado
     (así «Estado de Hidalgo» no se confunde con el municipio de Hidalgo);
   - los nombres de una sola palabra valen menos en el cuerpo del texto («Reforma»
     es un municipio, pero también una palabra común), y cada nombre cuenta a lo
     sumo 3 veces ahí.
3. Si el lugar que contiene a un candidato también aparece (su estado), el
   candidato sube: así se separan los municipios que se llaman igual.
4. Se elige el candidato más específico con puntaje suficiente, salvo que solo
   se mencione de pasada y el lugar que lo contiene sea claramente el
   protagonista («Congreso del Estado de Durango» no es del municipio que se
   nombra en una página). Si dos lugares con el mismo nombre quedan
   empatados, es ambiguo: no se adivina.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field

from docubot.filtros import tipos

PUNTUACION = re.compile(r"[^\w\s]")


def normalizar(texto: str) -> str:
    """Sin acentos, minúsculas y sin puntuación: «Juárez,» y «Juárez» son lo mismo."""
    return " ".join(PUNTUACION.sub(" ", tipos.normalizar(texto)).split())


UMBRAL = 2.0  # puntaje mínimo para asignar un lugar
UMBRAL_GENERAL = 1.5  # para un lugar sin hijos con puntaje (p. ej. solo el estado)
MAX_PALABRAS = 8
MAX_MENCIONES = 3  # en el cuerpo del texto, cada nombre cuenta hasta 3 veces

CONTEXTO_LOCAL = (
    "municipio",
    "municipal",
    "ayuntamiento",
    "alcaldia",
    "cabecera",
    "localidad",
    "ciudad de",
    "municipality",
    "county",
    "city of",
)
CONTEXTO_REGIONAL = ("estado", "gobierno del estado", "entidad", "provincia", "state of", "estatal")


@dataclass
class EntradaLugar:
    id: int
    clave: str
    nombre: str
    nivel: str
    padre_id: int | None
    profundidad: int = 0  # 0 = sin padre


@dataclass
class Candidato:
    lugar: EntradaLugar
    puntaje: float
    menciones: int


@dataclass
class Resultado:
    lugar: EntradaLugar | None = None
    confianza: float = 0.0
    estado: str = "sin_lugar"  # asignado | ambiguo | sin_lugar
    candidatos: list[Candidato] = field(default_factory=list)

    def puntaje_de(self, lugar_id: int) -> float:
        return next((c.puntaje for c in self.candidatos if c.lugar.id == lugar_id), 0.0)


class Indice:
    """Los nombres de un catálogo, listos para buscarlos en un texto."""

    def __init__(self, lugares: list[EntradaLugar], alias: dict[int, list[str]]) -> None:
        self.por_id = {l.id: l for l in lugares}
        for l in lugares:  # profundidad en la jerarquía (más profundo = más específico)
            p, n = l.padre_id, 0
            while p is not None and p in self.por_id and n < 10:
                n += 1
                p = self.por_id[p].padre_id
            l.profundidad = n
        self.nombres: dict[str, list[EntradaLugar]] = defaultdict(list)
        for l in lugares:
            for nombre in [l.nombre, *alias.get(l.id, [])]:
                n = normalizar(nombre)
                if len(n) >= 4 and l not in self.nombres[n]:
                    self.nombres[n].append(l)
        self.max_palabras = min(MAX_PALABRAS, max((len(n.split()) for n in self.nombres), default=1))
        self.hijos: dict[int, list[int]] = defaultdict(list)
        for l in lugares:
            if l.padre_id is not None:
                self.hijos[l.padre_id].append(l.id)

    def menciones(self, texto: str) -> list[tuple[str, list[str]]]:
        """[(nombre normalizado, palabras anteriores)] de cada mención en el texto."""
        palabras = normalizar(texto).split()
        salida = []
        i = 0
        while i < len(palabras):
            for largo in range(min(self.max_palabras, len(palabras) - i), 0, -1):
                clave = " ".join(palabras[i : i + largo])
                if clave in self.nombres:
                    salida.append((clave, palabras[max(0, i - 4) : i]))
                    i += largo
                    break
            else:
                i += 1
        return salida

    def descendientes(self, lugar_id: int) -> list[int]:
        salida, pendientes = [], [lugar_id]
        while pendientes:
            actual = pendientes.pop()
            salida.append(actual)
            pendientes.extend(self.hijos.get(actual, []))
        return salida


def _peso_contexto(lugar: EntradaLugar, anteriores: list[str], indice: Indice) -> float:
    previo = " ".join(anteriores[-3:])
    local = any(c in previo for c in CONTEXTO_LOCAL)
    regional = any(c in previo for c in CONTEXTO_REGIONAL) and not local
    tiene_hijos = bool(indice.hijos.get(lugar.id))
    if local:
        return 3.0 if not tiene_hijos else 0.4
    if regional:
        return 3.0 if tiene_hijos else 0.3
    return 1.0


def buscar(indice: Indice, texto: str, *, titulo: str = "", lugar_ia: str = "") -> Resultado:
    puntos: dict[int, float] = defaultdict(float)
    menciones: dict[int, int] = defaultdict(int)
    aportes: dict[int, set[str]] = defaultdict(set)  # qué nombres sumaron a cada lugar
    fuerte: set[int] = set()  # lugares con apoyo claro: título, campo de la IA o contexto explícito
    for fragmento, peso_base in ((lugar_ia, 4.0), (titulo, 3.0), (texto, 1.0)):
        if not fragmento:
            continue
        vistas: dict[str, int] = defaultdict(int)
        for nombre, anteriores in indice.menciones(fragmento):
            vistas[nombre] += 1
            en_cuerpo = peso_base == 1.0
            if en_cuerpo and vistas[nombre] > MAX_MENCIONES:
                continue  # una palabra repetida no gana por volumen
            una_palabra = len(nombre.split()) == 1
            unico = len(indice.nombres[nombre]) == 1
            for lugar in indice.nombres[nombre]:
                contexto = _peso_contexto(lugar, anteriores, indice)
                # una sola palabra dice poco («Reforma», «Hidalgo»): cuenta la mitad en el cuerpo
                # del texto, y también en el título si varios lugares la comparten, salvo que el
                # contexto diga de qué nivel se habla («municipio de Hidalgo»)
                if contexto >= 3 or not una_palabra or (not en_cuerpo and unico):
                    largo = 1.0
                else:
                    largo = 0.5
                puntos[lugar.id] += peso_base * largo * contexto
                menciones[lugar.id] += 1
                aportes[lugar.id].add(nombre)
                if not en_cuerpo or contexto >= 3:
                    fuerte.add(lugar.id)

    # si aparece, en otra mención, el lugar que lo contiene (p. ej. su estado), el candidato sube
    finales = dict(puntos)
    for lugar_id, p in puntos.items():
        padre = indice.por_id[lugar_id].padre_id
        if padre is not None and puntos.get(padre, 0) > 0 and aportes[padre] - aportes[lugar_id]:
            finales[lugar_id] = p + 2.0 + 0.5 * puntos[padre]

    candidatos = sorted(
        (Candidato(indice.por_id[i], round(p, 2), menciones[i]) for i, p in finales.items()),
        key=lambda c: (-c.puntaje, -c.lugar.profundidad),
    )
    r = Resultado(candidatos=candidatos[:8])
    if not candidatos:
        return r

    # el más específico que llega al umbral
    for profundidad in sorted({c.lugar.profundidad for c in candidatos}, reverse=True):
        nivel = [c for c in candidatos if c.lugar.profundidad == profundidad]
        umbral = UMBRAL if profundidad > 0 else UMBRAL_GENERAL
        mejor = nivel[0]
        if mejor.puntaje < umbral:
            continue
        padre = mejor.lugar.padre_id
        if padre is not None and mejor.lugar.id not in fuerte and puntos.get(padre, 0) >= 2 * puntos[mejor.lugar.id]:
            continue  # se menciona de pasada; el protagonista es el lugar que lo contiene
        empatados = [
            c
            for c in nivel[1:]
            if mejor.puntaje - c.puntaje < 1.0 and normalizar(c.lugar.nombre) == normalizar(mejor.lugar.nombre)
        ]
        if empatados:
            r.estado = "ambiguo"
            r.candidatos = [mejor, *empatados] + [c for c in candidatos if c is not mejor and c not in empatados][:3]
            return r
        r.lugar, r.estado = mejor.lugar, "asignado"
        r.confianza = round(min(0.95, 0.45 + mejor.puntaje / 12), 2)
        return r
    return r
