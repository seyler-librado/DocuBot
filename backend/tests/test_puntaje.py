from docubot.documentos.almacen import Almacen
from docubot.documentos.validacion import revisar
from docubot.filtros.puntaje import Calificador
from docubot.perfiles.esquema import Documentos

DOCS = Documentos(
    tipos={
        "PMD": {"nombre": "Plan municipal", "patrones": [r"plan\s*municipal"]},
        "ATLAS": {"nombre": "Atlas", "palabras": ["atlas"]},
    },
    excluir=["formato", "solicitud"],
    puntaje_minimo=60,
)


def test_puntaje_segun_donde_aparece_el_tipo():
    c = Calificador(DOCS)
    n = c.calificar("https://m.gob.mx/docs/Plan_Municipal_2024-2027.pdf")
    assert (n.puntaje, n.tipo, n.estado) == (95, "PMD", "aceptado")
    assert "nombre del archivo" in n.motivo and "año" in n.motivo

    n = c.calificar("https://m.gob.mx/docs/archivo_17.pdf", "Atlas de riesgos")
    assert (n.puntaje, n.tipo) == (80, "ATLAS")

    n = c.calificar("https://m.gob.mx/plan-municipal/x.pdf")
    assert (n.puntaje, n.estado) == (35, "rechazado")  # 50 por la ruta, -15 por el nombre "x"

    n = c.calificar("https://m.gob.mx/boletin.pdf", "Boletín de prensa")
    assert (n.puntaje, n.tipo, n.estado) == (0, None, "rechazado")


def test_palabras_excluidas_ganan():
    n = Calificador(DOCS).calificar("https://m.gob.mx/Formato_plan_municipal.pdf")
    assert (n.puntaje, n.estado) == (0, "rechazado")
    assert n.motivo == "excluido por «formato»"


def test_modo_todos():
    c = Calificador(Documentos(modo="todos", excluir=["formato"]))
    assert c.calificar("https://m.gob.mx/cualquier-cosa.pdf").puntaje == 70
    assert c.calificar("https://m.gob.mx/informe-2023.pdf").puntaje == 80
    assert not c.calificar("https://m.gob.mx/formato.pdf").aceptado


def test_validacion_de_archivos(tmp_path):
    almacen = Almacen(tmp_path)

    def archivo(contenido: bytes):
        t = almacen.temporal()
        t.escribir(contenido)
        t.cerrar()
        return t

    assert revisar(archivo(b"%PDF-1.7\n...\n%%EOF\n"), "pdf") is None
    assert revisar(archivo(b""), "pdf") == "el archivo está vacío"
    assert revisar(archivo(b"  <!DOCTYPE html><html>"), "pdf") == "es una página HTML, no el documento"
    assert revisar(archivo(b"%PDF-1.4 cortado"), "pdf") == "el PDF está incompleto (no termina en %%EOF)"
    assert revisar(archivo(b"hola"), "pdf") == "no es un PDF (no empieza con %PDF)"
    assert revisar(archivo(b"PK\x03\x04..."), "docx") is None
    assert revisar(archivo(b"nada"), "docx") == "no es un archivo .docx válido"


def test_almacen_por_huella(tmp_path):
    almacen = Almacen(tmp_path)
    rutas = []
    for _ in range(2):
        t = almacen.temporal()
        t.escribir(b"%PDF-1.4 mismo contenido %%EOF")
        rutas.append(almacen.guardar(t, "pdf"))
    assert rutas[0] == rutas[1]
    sha = rutas[0].split("/")[-1].split(".")[0]
    assert rutas[0] == f"{sha[:2]}/{sha[2:4]}/{sha}.pdf"
    assert (tmp_path / rutas[0]).read_bytes() == b"%PDF-1.4 mismo contenido %%EOF"
    assert list((tmp_path / ".tmp").iterdir()) == []
