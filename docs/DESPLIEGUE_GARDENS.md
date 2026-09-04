# Desplegar Ojochal Gardens — cómo se hace hoy

> **Última revisión: 2026-09-03.**
>
> ⚠️ `DESPLIEGUE_OJOCHAL_GARDENS.md` describe el arranque de la propiedad.
> Este archivo es cómo se **despliega**, que no es lo mismo.

## ⚠️ Se sube desde la RAÍZ del repo, no desde `backend/`

Esta es la diferencia con Oxygen y cuesta media hora si no se sabe:

```bash
cd C:\dev\FinPlan_Gardens && railway up --service "FinPlan_Gardens_Backend" --ci
```

```bash
cd C:\dev\FinPlan_Gardens && railway up --service "FinPlan_Gardens_Frontend" --ci
```

**Por qué.** El servicio de Gardens tiene `backend` configurado como directorio
raíz. Subiendo desde `backend/`, el constructor busca esa carpeta dentro de lo
que se subió, no la encuentra, y falla con un mensaje que no lo dice:

```
railpack prepare exited with an error
```

En Oxygen es al revés —se sube desde `backend/`— porque su servicio no tiene esa
opción puesta. Mismo código, distinta configuración de servicio.

## El vínculo, una vez

```bash
railway link --project af16af82-9033-4b79-a1d5-da0f27dfcaa3 --environment production --service "FinPlan_Gardens_Backend"
```

Los nombres llevan **guión bajo**: `FinPlan_Gardens_Backend` y
`FinPlan_Gardens_Frontend`.

## Antes de subir una migración

El arranque es `alembic upgrade head && python -m app.seed && uvicorn`. **Si la
migración falla, el servicio no levanta** — reintenta tres veces y se queda
abajo. El despliegue anterior sigue sirviendo mientras tanto, así que un fallo
no tira la app, pero tampoco entra el cambio.

Comparar la revisión de producción contra la cadena local:

```sql
select version_num from alembic_version;
```

El 2026-09-03 se aplicó la **138** sobre la **137** de seguridad, sin renumerar.

## Verificar después

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://finplangardens-backend.up.railway.app/health
```

Contra la base, la receta de `railway ssh` está en la memoria del proyecto. **Dos
trampas:** el intérprete está en `/app/.venv/bin/python` y no en `/proc/1/exe`, y
`recalculate_scenario` hace su propio `commit` — un guion «en seco» que recalcula
**ya escribió**.

## Estado de los datos (2026-09-03)

| | |
|---|---|
| `HOTEL_ID` | `OJO` — Ojochal Gardens |
| Categorías | **7** activas, 16 unidades |
| Actuales | ninguno (`actual_entries` = 0) |
| `FORECAST Working 2026` | corte 0, sin filas de gasto |
| Reparto de lavandería y cafetería | **sin configurar en los 12 escenarios** |
| Presupuesto 2026 | arranca en junio |

⚠️ **El reparto no se copió de otra propiedad a propósito.**
`laundry_allocation_config` guarda `kilos_historicos` —kilos medidos por
departamento—. Traer los de Amarena dejaría a Gardens repartiendo su lavandería
con el consumo de otro hotel, y el P&L cuadraría igual sin que nada avise.
Hoy quedan **9.838,52** sin repartir, parados en `OH_LAUNDRY`.
