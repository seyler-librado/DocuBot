import asyncio

from sqlalchemy import text, update

from docubot.db.modelos import Tarea
from docubot.pipeline import cola


async def test_dos_trabajadores_no_toman_la_misma_tarea(sesiones):
    async with sesiones() as s:
        for i in range(10):
            await cola.encolar(s, "eco", {"i": i})
        await s.commit()

    async def trabajador(nombre: str) -> list[int]:
        tomadas = []
        while True:
            async with sesiones() as s:
                tareas = await cola.tomar(s, "eco", nombre, limite=2)
                await s.commit()
            if not tareas:
                return tomadas
            tomadas += [t.id for t in tareas]
            await asyncio.sleep(0)

    a, b, c = await asyncio.gather(trabajador("a"), trabajador("b"), trabajador("c"))
    todas = a + b + c
    assert sorted(todas) == list(range(1, 11))
    assert len(set(todas)) == 10


async def test_respeta_prioridad_y_etapa(sesiones):
    async with sesiones() as s:
        await cola.encolar(s, "eco", {"n": "baja"})
        await cola.encolar(s, "eco", {"n": "alta"}, prioridad=5)
        await cola.encolar(s, "otra", {"n": "ajena"}, prioridad=9)
        await s.commit()
        [t] = await cola.tomar(s, "eco", "x")
        assert t.carga == {"n": "alta"}
        assert t.estado == "tomada" and t.intentos == 1


async def test_fallar_reintenta_con_espera_y_luego_marca_fallida(sesiones):
    async with sesiones() as s:
        tarea = await cola.encolar(s, "eco", max_intentos=2)
        await s.commit()

        [t] = await cola.tomar(s, "eco", "x")
        assert await cola.fallar(s, t.id, "boom") == "pendiente"
        await s.commit()
        # quedó en espera: todavía no se puede tomar
        assert await cola.tomar(s, "eco", "x") == []

        await s.execute(update(Tarea).values(disponible_en=text("now()")))
        [t] = await cola.tomar(s, "eco", "x")
        assert t.intentos == 2
        assert await cola.fallar(s, t.id, "boom otra vez") == "fallida"
        await s.commit()

        fila = await s.get(Tarea, tarea.id, populate_existing=True)
        assert fila.estado == "fallida" and fila.error == "boom otra vez"


async def test_recupera_tareas_huerfanas(sesiones):
    async with sesiones() as s:
        await cola.encolar(s, "eco")
        await s.commit()
        await cola.tomar(s, "eco", "muerto")
        await s.execute(update(Tarea).values(tomada_en=text("now() - interval '1 hour'")))
        await s.commit()

        assert await cola.recuperar_huerfanas(s, minutos=15) == 1
        await s.commit()
        assert await cola.resumen(s) == {"eco": {"pendiente": 1}}
