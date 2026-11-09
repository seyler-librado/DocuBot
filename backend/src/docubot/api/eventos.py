"""WebSocket de eventos en vivo: /api/eventos."""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from docubot.eventos import difusor

ruta = APIRouter(tags=["eventos"])
LATIDO = 25.0  # segundos sin eventos antes de mandar un ping (mantiene viva la conexión)


@ruta.websocket("/api/eventos")
async def eventos(ws: WebSocket) -> None:
    await ws.accept()
    difusor.iniciar()
    cola = difusor.suscribir()
    try:
        while True:
            try:
                carga = await asyncio.wait_for(cola.get(), LATIDO)
            except TimeoutError:
                carga = '{"tipo": "ping"}'
            await ws.send_text(carga)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        difusor.cancelar(cola)
        with contextlib.suppress(Exception):
            await ws.close()
