"""Línea de comandos: docubot api | worker | migrar | eco."""

import asyncio
import logging
from pathlib import Path

import typer

app = typer.Typer(
    help="DocuBot: descubre, descarga y cataloga documentos públicos.",
    no_args_is_help=True,
)


def _bitacora(nivel: str = "INFO") -> None:
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def api(host: str = "127.0.0.1", puerto: int = 8000, recargar: bool = False) -> None:
    """Levanta la API web."""
    import uvicorn

    _bitacora()
    uvicorn.run("docubot.main:app", host=host, port=puerto, reload=recargar, proxy_headers=True)


@app.command()
def worker() -> None:
    """Levanta los trabajadores del pipeline."""
    from docubot.pipeline.trabajador import correr

    _bitacora()
    asyncio.run(correr())


@app.command()
def migrar(revision: str = "head") -> None:
    """Aplica las migraciones de la base de datos."""
    from alembic import command
    from alembic.config import Config

    _bitacora()
    ini = Path("alembic.ini")
    cfg = Config(str(ini)) if ini.exists() else Config()
    cfg.set_main_option("script_location", "docubot:migraciones")
    command.upgrade(cfg, revision)
    typer.echo("Base de datos al día.")


@app.command()
def eco(mensaje: str = typer.Argument("hola"), veces: int = 1) -> None:
    """Encola tareas de prueba para comprobar que el worker responde."""
    from docubot.db.sesion import fabrica_sesiones, obtener_motor
    from docubot.pipeline import cola

    async def _encolar() -> None:
        async with fabrica_sesiones()() as s:
            for i in range(veces):
                await cola.encolar(s, "eco", {"mensaje": f"{mensaje} ({i + 1}/{veces})"})
            await s.commit()
        await obtener_motor().dispose()

    asyncio.run(_encolar())
    typer.echo(f"{veces} tarea(s) en la cola. Míralas con: docker compose logs -f worker")


# --- perfiles -----------------------------------------------------------------

perfiles_app = typer.Typer(help="Perfiles YAML: listar, validar, sincronizar.", no_args_is_help=True)
app.add_typer(perfiles_app, name="perfiles")


def _cargar(rutas: list[Path] | None):
    from docubot.ajustes import obtener_ajustes
    from docubot.perfiles import cargar, cargar_todos

    if rutas:
        return [cargar(r / "perfil.yaml" if r.is_dir() else r) for r in rutas]
    return cargar_todos(obtener_ajustes().carpeta_perfiles)


@perfiles_app.command("listar")
def perfiles_listar() -> None:
    """Muestra los perfiles encontrados y si son válidos."""
    cargados = _cargar(None)
    if not cargados:
        typer.echo("No hay perfiles. Copia config/perfiles/ejemplo.yaml para empezar.")
        return
    for c in cargados:
        marca = "ok " if c.valido else "ERR"
        resumen = ""
        if c.perfil:
            fuentes = ", ".join(f.tipo for f in c.perfil.descubrimiento.fuentes)
            resumen = f"  fuentes: {fuentes}"
        typer.echo(f"[{marca}] {c.nombre:<30} {c.archivo.name}{resumen}")


@perfiles_app.command("validar")
def perfiles_validar(
    rutas: list[Path] = typer.Argument(None, help="Archivos o carpetas; si no, todos los de config/perfiles"),
) -> None:
    """Valida perfiles y explica cada error. Sale con código 1 si alguno falla."""
    cargados = _cargar(rutas)
    malos = 0
    for c in cargados:
        if c.valido:
            typer.secho(f"✓ {c.nombre} ({c.archivo})", fg=typer.colors.GREEN)
        else:
            malos += 1
            typer.secho(f"✗ {c.nombre} ({c.archivo})", fg=typer.colors.RED)
            for e in c.errores:
                typer.echo(f"    - {e}")
    if not cargados:
        typer.echo("No se encontraron perfiles.")
    raise typer.Exit(1 if malos else 0)


@perfiles_app.command("sincronizar")
def perfiles_sincronizar() -> None:
    """Copia los perfiles válidos a la base de datos."""
    from dataclasses import asdict

    from docubot.db.sesion import fabrica_sesiones, obtener_motor
    from docubot.perfiles.sincronizar import sincronizar

    async def _correr():
        async with fabrica_sesiones()() as s:
            r = await sincronizar(s, _cargar(None))
            await s.commit()
        await obtener_motor().dispose()
        return r

    for clave, valor in asdict(asyncio.run(_correr())).items():
        if valor:
            typer.echo(f"{clave}: {valor if not isinstance(valor, dict) else list(valor)}")


# --- corridas -----------------------------------------------------------------


def _linea(r: dict) -> str:
    t = r["tareas"]
    activas = sum(v.get("pendiente", 0) + v.get("tomada", 0) for v in t.values())
    fallidas = sum(v.get("fallida", 0) for v in t.values())
    sitios = sum(r["sitios"].values())
    explorados = sitios - r["sitios"].get("pendiente", 0)
    estados = r.get("candidatos_estado", {})
    return (
        f"corrida {r['id']} [{r['estado']}]  sitios {explorados}/{sitios}  páginas {r['paginas']}  "
        f"candidatos {r['candidatos_total']} (aceptados {estados.get('aceptado', 0) + estados.get('descargado', 0)})  "
        f"descargados {r.get('documentos', 0)} ({r.get('bytes', 0) // 1048576} MB)  tareas activas {activas}"
        + (f"  fallidas {fallidas}" if fallidas else "")
        + (
            f"  fichas {sum(r['fichas'].values())} (revisar {r['fichas'].get('revision', 0)})"
            if r.get("fichas")
            else ""
        )
    )


async def _con_sesion(funcion):
    from docubot.db.sesion import fabrica_sesiones, obtener_motor

    try:
        async with fabrica_sesiones()() as s:
            return await funcion(s)
    finally:
        await obtener_motor().dispose()


@app.command()
def correr(
    perfil: str = typer.Argument(..., help="Nombre del perfil"),
    fuente: list[int] = typer.Option(None, "--fuente", "-f", help="Solo estas fuentes (índices, desde 0)"),
    esperar: bool = typer.Option(True, help="Mostrar el avance hasta que termine"),
    descargar: bool = typer.Option(
        True, "--descargar/--sin-descargar", help="Bajar los candidatos aceptados conforme aparecen"
    ),
) -> None:
    """Lanza una corrida para un perfil: descubre, califica y descarga (la hace el worker)."""
    import time

    from docubot.db.modelos import Corrida
    from docubot.pipeline import corridas

    cargados = [c for c in _cargar(None) if c.nombre == perfil]
    if not cargados:
        typer.secho(f"No hay un perfil llamado '{perfil}'. Míralos con: docubot perfiles listar", fg=typer.colors.RED)
        raise typer.Exit(1)

    async def _crear(s):
        c = await corridas.crear(s, cargados[0], fuente or None, descargar=descargar)
        await s.commit()
        return c.id

    try:
        corrida_id = asyncio.run(_con_sesion(_crear))
    except corridas.ErrorCorrida as error:
        typer.secho(str(error), fg=typer.colors.RED)
        raise typer.Exit(1) from None
    typer.echo(f"Corrida {corrida_id} creada. El worker ya la está procesando.")
    if not esperar:
        return

    async def _resumen(s):
        return await corridas.resumen(s, await s.get(Corrida, corrida_id))

    try:
        while True:
            r = asyncio.run(_con_sesion(_resumen))
            typer.echo(_linea(r))
            if r["estado"] != "corriendo":
                break
            time.sleep(5)
    except KeyboardInterrupt:
        typer.echo(
            f"\nDejo de mostrar el avance; la corrida sigue. Para detenerla: docubot corridas detener {corrida_id}"
        )


corridas_app = typer.Typer(help="Corridas: ver, detener, reanudar.", no_args_is_help=True)
app.add_typer(corridas_app, name="corridas")


@corridas_app.command("listar")
def corridas_listar(limite: int = 10) -> None:
    """Las corridas más recientes."""
    from sqlalchemy import select

    from docubot.db.modelos import Corrida
    from docubot.pipeline import corridas

    async def _listar(s):
        filas = (await s.scalars(select(Corrida).order_by(Corrida.id.desc()).limit(limite))).all()
        return [await corridas.resumen(s, c) for c in filas]

    for r in asyncio.run(_con_sesion(_listar)):
        typer.echo(f"{r['perfil']:<25} {_linea(r)}")


@corridas_app.command("detener")
def corridas_detener(corrida_id: int) -> None:
    """Cancela lo pendiente de una corrida (lo que está en curso termina)."""
    from docubot.pipeline import corridas

    async def _detener(s):
        n = await corridas.detener(s, corrida_id)
        await s.commit()
        return n

    typer.echo(f"{asyncio.run(_con_sesion(_detener))} tarea(s) canceladas.")


@corridas_app.command("reanudar")
def corridas_reanudar(
    corrida_id: int, fallidas: bool = typer.Option(False, help="Reintentar también las fallidas")
) -> None:
    """Retoma una corrida detenida."""
    from docubot.pipeline import corridas

    async def _reanudar(s):
        n = await corridas.reanudar(s, corrida_id, fallidas)
        await s.commit()
        return n

    typer.echo(f"{asyncio.run(_con_sesion(_reanudar))} tarea(s) de vuelta en la cola.")


@app.command("descargar")
def descargar_cmd(
    corrida_id: int,
    limite: int = typer.Option(None, help="Solo los N de mayor puntaje"),
    fallidos: bool = typer.Option(False, help="Reintentar también los que fallaron"),
) -> None:
    """Encola la descarga de los candidatos aceptados de una corrida que falten."""
    from docubot.pipeline import descargas

    async def _encolar(s):
        n = await descargas.descargar_corrida(s, corrida_id, limite=limite, incluir_fallidos=fallidos)
        await s.commit()
        return n

    typer.echo(f"{asyncio.run(_con_sesion(_encolar))} descarga(s) en la cola.")


@app.command("fichas")
def fichas_cmd(
    corrida_id: int,
    rehacer: bool = typer.Option(False, help="Rehacer también las fichas que ya existen"),
) -> None:
    """Encola extracción de texto y fichas con IA para los documentos de una corrida."""
    from docubot.db.modelos import Corrida
    from docubot.pipeline import corridas, procesar

    async def _encolar(s):
        corrida = await s.get(Corrida, corrida_id)
        if corrida is None:
            return None
        cuenta = await procesar.completar_corrida(
            s, corrida_id, await corridas.perfil_actual(s, corrida), rehacer=rehacer
        )
        if sum(cuenta.values()):
            await corridas.reabrir(s, corrida_id)
        await s.commit()
        return cuenta

    cuenta = asyncio.run(_con_sesion(_encolar))
    if cuenta is None:
        typer.secho(f"No existe la corrida {corrida_id}.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo(
        f"En la cola: {cuenta['extraer']} extracción(es) de texto, {cuenta['fichar']} ficha(s), {cuenta['ubicar']} ubicación(es)."
    )


ia_app = typer.Typer(help="IA: estado y prueba del proveedor.", no_args_is_help=True)
app.add_typer(ia_app, name="ia")


@ia_app.command("probar")
def ia_probar() -> None:
    """Muestra el proveedor configurado y le hace una pregunta de ida y vuelta."""
    from docubot import ia
    from docubot.api.ia import probar

    async def _correr():
        try:
            return await probar()
        finally:
            await ia.cerrar()

    d = asyncio.run(_correr())
    typer.echo(
        f"proveedor: {d.get('proveedor')}  modelo: {d.get('modelo') or '(el del servidor)'}  visión: {d.get('vision')}"
    )
    if d.get("modelos"):
        typer.echo(f"modelos en el servidor: {', '.join(map(str, d['modelos'][:10]))}")
    if d.get("eco") is not None:
        typer.echo(f"respuesta: {d['eco']!r} en {d.get('segundos')} s")
    if d.get("detalle"):
        typer.echo(f"detalle: {d['detalle']}")
    ok = d.get("ok")
    typer.secho(
        "OK" if ok else ("sin IA configurada" if ok is None else "NO RESPONDE"),
        fg=typer.colors.GREEN if ok else typer.colors.RED,
    )
    raise typer.Exit(0 if ok or ok is None else 1)


lugares_app = typer.Typer(help="Lugares: importar catálogos y ubicar documentos.", no_args_is_help=True)
app.add_typer(lugares_app, name="lugares")


@lugares_app.command("importar")
def lugares_importar(
    perfil: str, forzar: bool = typer.Option(False, help="Reimportar aunque no haya cambiado")
) -> None:
    """Importa a la base el catálogo de lugares de un perfil."""
    from docubot.geo.catalogo import importar

    cargados = [c for c in _cargar(None) if c.nombre == perfil and c.valido]
    if not cargados or cargados[0].perfil.geografia is None:
        typer.secho(f"No hay un perfil válido '{perfil}' con geografia.catalogo.", fg=typer.colors.RED)
        raise typer.Exit(1)

    async def _correr(s):
        r = await importar(s, cargados[0].perfil.geografia, cargados[0].carpeta, forzar=forzar)
        await s.commit()
        return r

    r = asyncio.run(_con_sesion(_correr))
    typer.echo(
        f"{r.catalogo}: " + ("sin cambios" if r.sin_cambios else f"{r.lugares} lugares, {r.poligonos} polígonos")
    )


@lugares_app.command("ubicar")
def lugares_ubicar(corrida_id: int) -> None:
    """Vuelve a ubicar los documentos de una corrida (respeta lo elegido a mano)."""
    from docubot.db.modelos import Corrida
    from docubot.pipeline import corridas, procesar

    async def _correr(s):
        corrida = await s.get(Corrida, corrida_id)
        if corrida is None:
            return None
        n = await procesar.ubicar_corrida(s, corrida_id, await corridas.perfil_actual(s, corrida))
        if n:
            await corridas.reabrir(s, corrida_id)
        await s.commit()
        return n

    n = asyncio.run(_con_sesion(_correr))
    if n is None:
        typer.secho(f"No existe la corrida {corrida_id}.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo(f"{n} documento(s) por ubicar en la cola.")


busqueda_app = typer.Typer(help="Búsqueda: indexar documentos y buscar desde la terminal.", no_args_is_help=True)
app.add_typer(busqueda_app, name="busqueda")


@busqueda_app.command("indexar")
def busqueda_indexar(rehacer: bool = typer.Option(False, help="Reindexar también lo ya indexado")) -> None:
    """Encola los vectores (búsqueda por tema) de los documentos con texto que no los tengan."""
    from docubot.api.busqueda import encolar_faltantes

    async def _correr(s):
        n = await encolar_faltantes(s, rehacer)
        await s.commit()
        return n

    typer.echo(f"{asyncio.run(_con_sesion(_correr))} documento(s) por indexar en la cola.")


@busqueda_app.command("buscar")
def busqueda_buscar(
    consulta: str, modo: str = typer.Option("mixta", help="mixta | palabras | tema"), limite: int = 10
) -> None:
    """Busca en los documentos y muestra los mejores resultados."""
    from docubot.busqueda.buscar import MARCA_FIN, MARCA_INICIO, buscar

    async def _correr(s):
        return await buscar(s, consulta, modo, None, limite, 0)

    modo_usado, total, resultados = asyncio.run(_con_sesion(_correr))
    typer.echo(f"{total} resultado(s) · búsqueda {modo_usado}")
    for r in resultados:
        typer.secho(f"\n#{r.documento_id}  ({r.puntaje})", bold=True)
        for c in r.coincidencias:
            texto = c.texto.replace(MARCA_INICIO, "«").replace(MARCA_FIN, "»")
            typer.echo(f"  p.{c.pagina or '?'} [{c.tipo}] {texto}")


@ia_app.command("evaluar")
def ia_evaluar(
    carpeta: Path = typer.Argument(..., help="Carpeta con los PDFs y dorado.csv"),
    perfil: str = typer.Option(..., help="Perfil cuyos campos se evalúan"),
    salida: Path = typer.Option(None, help="Guardar el detalle en este JSON"),
) -> None:
    """Mide qué tan bien llena la IA las fichas contra un conjunto dorado (ver docs/ia.md)."""
    import json

    from docubot import ia
    from docubot.ajustes import obtener_ajustes
    from docubot.ia.evaluar import evaluar

    cargados = [c for c in _cargar(None) if c.nombre == perfil and c.valido]
    if not cargados:
        typer.secho(f"No hay un perfil válido llamado '{perfil}'.", fg=typer.colors.RED)
        raise typer.Exit(1)

    async def _correr():
        try:
            return await evaluar(cargados[0].perfil, carpeta, ia.obtener(), obtener_ajustes().ia)
        finally:
            await ia.cerrar()

    informe = asyncio.run(_correr())
    typer.echo(f"{len(informe.documentos)} documento(s) · aciertos: {informe.global_} %\n")
    for campo, c in informe.por_campo().items():
        barra = "█" * round(c["porcentaje"] / 5)
        typer.echo(f"  {campo:<22} {c['porcentaje']:>5} %  {barra}  ({c['aciertos']}/{c['total']})")
    for d in informe.documentos:
        if d.error:
            typer.secho(f"  ✗ {d.archivo}: {d.error}", fg=typer.colors.RED)
    if salida:
        salida.write_text(json.dumps(informe.a_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        typer.echo(f"\nDetalle en {salida}")


candidatos_app = typer.Typer(help="Candidatos: recalcular puntajes.", no_args_is_help=True)
app.add_typer(candidatos_app, name="candidatos")


@candidatos_app.command("recalificar")
def candidatos_recalificar(perfil: str) -> None:
    """Recalcula el puntaje de los candidatos de un perfil con su YAML actual."""
    from sqlalchemy import select

    from docubot.db.modelos import Perfil as PerfilBD
    from docubot.perfiles.sincronizar import sincronizar
    from docubot.pipeline.recalificar import recalificar

    cargados = [c for c in _cargar(None) if c.nombre == perfil]
    if not cargados or not cargados[0].valido:
        typer.secho(f"No hay un perfil válido llamado '{perfil}'.", fg=typer.colors.RED)
        raise typer.Exit(1)

    async def _correr(s):
        await sincronizar(s, cargados)
        perfil_id = await s.scalar(select(PerfilBD.id).where(PerfilBD.nombre == perfil))
        cuenta = await recalificar(s, perfil_id, cargados[0].perfil)
        await s.commit()
        return cuenta

    cuenta = asyncio.run(_con_sesion(_correr))
    typer.echo(f"aceptados {cuenta['aceptado']}  rechazados {cuenta['rechazado']}  cambiaron {cuenta['cambiados']}")
    typer.echo("Para bajar los aceptados de una corrida: docubot descargar <corrida>")


# --- red ----------------------------------------------------------------------

red_app = typer.Typer(help="Herramientas de red.", no_args_is_help=True)
app.add_typer(red_app, name="red")


@red_app.command("probar")
def red_probar(url: str) -> None:
    """Pide una URL como lo haría DocuBot (robots.txt, ritmo, reintentos) y muestra el resultado."""
    from docubot.red.cliente import Cliente, ErrorRed

    async def _correr() -> None:
        async with Cliente() as cliente:
            permitido = await cliente.permitido(url)
            typer.echo(f"robots.txt: {'permite' if permitido else 'NO permite'}")
            try:
                r = await cliente.obtener(url)
            except ErrorRed as error:
                typer.secho(f"error: {error}", fg=typer.colors.RED)
                raise typer.Exit(1) from None
            typer.echo(f"estado: {r.status_code}  url final: {r.url}")
            typer.echo(f"tipo: {r.headers.get('content-type', '?')}  bytes: {len(r.content)}")
            if cliente.hosts_sin_tls:
                typer.secho(f"certificado inválido en: {', '.join(cliente.hosts_sin_tls)}", fg=typer.colors.YELLOW)

    _bitacora("WARNING")
    asyncio.run(_correr())


if __name__ == "__main__":
    app()
