"""¿Lo que se bajó es de verdad el documento? Devuelve el motivo si no lo es."""

from docubot.documentos.almacen import ArchivoTemporal

ZIP = ("docx", "xlsx", "pptx", "odt", "ods", "odp", "zip", "kmz", "epub")


def revisar(archivo: ArchivoTemporal, extension: str) -> str | None:
    if archivo.bytes == 0:
        return "el archivo está vacío"
    inicio = archivo.inicio.lstrip()[:512].lower()
    if inicio.startswith((b"<!doctype html", b"<html", b"<head", b"<?xml")) or b"<html" in inicio:
        if extension != "xml":
            return "es una página HTML, no el documento"
    if extension == "pdf":
        if b"%PDF-" not in archivo.inicio[:1024]:
            return "no es un PDF (no empieza con %PDF)"
        if b"%%EOF" not in archivo.final:
            return "el PDF está incompleto (no termina en %%EOF)"
    elif extension in ZIP and not archivo.inicio.startswith(b"PK"):
        return f"no es un archivo .{extension} válido"
    return None
