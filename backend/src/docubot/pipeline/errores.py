"""Errores que el worker trata de forma especial."""


class ErrorPermanente(Exception):
    """Reintentar no sirve (falta una llave, configuración inválida...): la tarea se marca fallida de inmediato."""
