"""Perfiles: qué buscar y cómo catalogarlo, definidos en YAML."""

from docubot.perfiles.cargador import PerfilCargado, archivos_de_perfiles, cargar, cargar_todos
from docubot.perfiles.esquema import Perfil

__all__ = ["Perfil", "PerfilCargado", "archivos_de_perfiles", "cargar", "cargar_todos"]
