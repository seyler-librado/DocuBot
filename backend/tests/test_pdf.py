import base64

from simulado import pdf_con_texto

from docubot.documentos import pdf

TEXTO = (
    "PLAN MUNICIPAL DE DESARROLLO 2024-2027\nMunicipio de Tula de Allende, Hidalgo\n"
    + "Objetivos y estrategias del municipio. " * 8
)


def test_extrae_texto_por_pagina(tmp_path):
    ruta = tmp_path / "plan.pdf"
    ruta.write_bytes(pdf_con_texto([TEXTO, "Segunda pagina con el decreto de aprobacion"]))
    e = pdf.extraer(ruta)
    assert e.estado == "texto" and e.paginas == 2
    assert "PLAN MUNICIPAL DE DESARROLLO" in e.textos[0]
    assert e.contenido.startswith("[página 1]\nPLAN MUNICIPAL")
    assert "[página 2]\nSegunda pagina" in e.contenido

    # lo guardado en la base se puede volver a partir por páginas
    otra = pdf.Extraccion.desde_contenido(e.contenido)
    assert otra.textos == e.textos
    assert otra.para_ia(paginas=1, max_caracteres=50) == e.contenido[:50]


def test_para_ia_agrega_las_ultimas_paginas_si_las_primeras_estan_vacias():
    e = pdf.Extraccion("texto", paginas=6, textos=["", "", "", "", "", "Decreto final firmado"])
    assert "Decreto final" in e.para_ia(paginas=2, max_caracteres=1000)


def test_escaneado_e_imagenes(tmp_path):
    ruta = tmp_path / "escaneado.pdf"
    ruta.write_bytes(pdf_con_texto(["", "", ""]))
    e = pdf.extraer(ruta)
    assert e.estado == "escaneado" and e.paginas == 3
    imagenes = pdf.imagenes(ruta, paginas=2, lado=300)
    assert len(imagenes) == 2
    assert base64.b64decode(imagenes[0])[:3] == b"\xff\xd8\xff"  # JPEG


def test_ilegible(tmp_path):
    vacio = tmp_path / "vacio.pdf"
    vacio.write_bytes(b"")
    assert pdf.extraer(vacio).estado == "ilegible"
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"%PDF-1.4\nesto no es un pdf de verdad\n%%EOF")
    e = pdf.extraer(roto)
    assert e.estado in ("ilegible", "escaneado")
    assert pdf.extraer(tmp_path / "no-existe.pdf").estado == "ilegible"
