# Conjuntos dorados

Para medir qué tan bien llena la IA las fichas, crea aquí una carpeta por
conjunto, con algunos PDFs y un `dorado.csv` con la ficha correcta de cada uno.
Esta carpeta no se versiona (salvo este README).

```bash
docker compose exec api docubot ia evaluar /app/config/evaluacion/mi-conjunto --perfil mi-perfil
```

Formato y detalles: [docs/ia.md](../../docs/ia.md#qué-tan-bien-lo-hace-el-conjunto-dorado).
