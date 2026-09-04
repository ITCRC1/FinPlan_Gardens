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
| Áreas que opera | **Rooms, Spa y Tours** (owner, 2026-09-03) |
| Categorías | **7** activas, 16 unidades |
| Ingreso 2026 | 397.039,20 — Rooms 374.791,20 · Spa 11.448 · Tours 10.800 |
| Actuales | ninguno (`actual_entries` = 0) |
| `FORECAST Working 2026` | corte 0, sin filas de gasto |
| Reparto de lavandería y cafetería | **sin configurar en los 12 escenarios** |
| Presupuesto 2026 | arranca en junio |

## ⚠️ El presupuesto llegó con datos de Amarena

El clon trajo el presupuesto de Amarena **entero**: Club Madresal con 145.000 de
ingreso, 96.644 de gasto y 19 puestos de planilla, más Spa, Tours y A&B.

El owner confirmó el 2026-09-03 que **Ojochal opera Rooms, Spa y Tours**, y que
el Club es de Amarena. Se sacó el Club —427 filas— y el ingreso pasó de
547.079,20 a **397.039,20**, exactamente los 150.040 de menos.

**Lo que NO se borró, a propósito: el catálogo.** Las 54 reglas de
`account_mapping` del departamento 260 y su fila en `department_catalog` se
quedan. Sin ellas, un movimiento del Club que entre mañana cae por DESCARTE en
`OPEX_ROOMS`, sin dar error y con el GOP cuadrando — el modo de falla que se
corrigió en Oxygen ese mismo día. `account_mapping` tiene que seguir en **1.098**
reglas, igual que en las otras dos propiedades.

⚠️ **La cifra de Rooms también viene del clon.** Nadie confirmó que los
374.791,20 sean de Ojochal; sólo se confirmó qué áreas opera.

⚠️ **El reparto no se copió de otra propiedad a propósito.**
`laundry_allocation_config` guarda `kilos_historicos` —kilos medidos por
departamento—. Traer los de Amarena dejaría a Ojochal repartiendo su lavandería
con el consumo de otro hotel, y el P&L cuadraría igual sin que nada avise.
Hoy quedan **9.838,52** sin repartir, parados en `OH_LAUNDRY`.

## ⚠️ Un `rollback` no alcanza como resguardo

`recalculate_scenario` hace su propio `commit`. Un guion «en seco» que borra,
recalcula y después revierte **ya escribió**: el commit de adentro cierra la
transacción y el rollback posterior no revierte nada.

Pasó el 2026-09-03 sacando el Club: la corrida de prueba borró de verdad, y se
llevó las 54 reglas de catálogo que la versión siguiente del guion ya excluía.
Se restauraron desde Oxygen —son las mismas del grupo—, pero la lección queda:
**medir el antes y el después, no confiar en el seco.**
