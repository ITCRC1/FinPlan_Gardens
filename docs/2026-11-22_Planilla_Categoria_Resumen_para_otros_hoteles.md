# Planilla: Categoria, filtros, pestaña Resumen y deptos apagados

**Origen:** FinPlan CWL, 2026-11-22 (todo en producción y verificado).
**Destino:** FinPlan Amarena (AMA), FinPlan Oxygen (OXY) y FinPlan Gardens / Ojochal.
**Qué se porta:** el código, nada de datos. Lo que en CWL fue de datos no se repite:
el roster de Isaac, el borrado de las posiciones del Club y del Área Recreativa y las
excepciones de Categoria de RRHH.

---

## 1. Los commits, en orden

Se cherry-pickean del repo de CWL (`git fetch cwl main`, con el remote apuntando a
`C:\Users\User\Documents\FinPlan_CWL`) **en este orden**:

| # | Commit | Qué hace |
|---|---|---|
| 1 | `efcbc02` | En la plantilla de planilla, el **nombre del colaborador** (col E) se puede editar y el import lo lee |
| 2 | `d0f8a87` | **Categoria** (Operaciones / Administrativo / Gerencial) y **SubCategoria** (On Property / Outside) en cada posición. Migración nueva, columnas V y W del Excel con lista y autofiltro |
| 3 | `ab97a37` | Bajar el Excel **filtrado por Categoria**. Al subirlo se reemplazan **solo** las posiciones de ese filtro |
| 4 | `1c1722a` | Los deptos **apagados** en el provisionamiento (dimensión PAYROLL) no salen en el Excel, y si se sube un Excel viejo sus filas se ignoran (`ignored_depts`) |
| 5 | `52f3deb` | El botón **Recalcular** de la planilla vuelve a leer el depto al terminar. Antes, después de subir, «Totales dept» quedaba en blanco |
| 6 | `d5b2f06` | Pestaña **Resumen** en el Excel |
| 7 | `980c9a0` | Opción «Operaciones + Gerencial». El #8 la quita, pero se aplica igual para que el #8 entre limpio |
| 8 | `6c12009` | Filtro por **SubCategoria**: On Property / Outside |

## 2. Lo que hay que adaptar en cada hotel

1. **Migración `165_categoria_de_la_posicion.py`.** En CWL es la revisión `165` con
   `down_revision = "164"`. En cada hotel hay que renombrarla al número siguiente de
   **su** cabeza:

   | Hotel | Cabeza al 22-nov | Nueva revisión |
   |---|---|---|
   | AMA | 155 | 156 |
   | OXY | 152 | 153 |
   | Gardens | 154 | 155 |

   Antes de renombrar, confirmar la cabeza con `ls backend/alembic/versions`: puede
   haber cambiado desde el 22-nov. La migración solo agrega `categoria` y
   `subcategoria` (`String(20)`, nullable) a `payroll_positions`.
2. **`DEFECTO_POR_DEPTO`** (`backend/app/models/payroll_position.py`). Sale del archivo de
   RRHH de CWL y se deja igual en los tres hoteles, porque el catálogo de
   departamentos es el mismo en todo el grupo:

   | Depto | Categoria / SubCategoria |
   |---|---|
   | 0181 | Gerencial / Outside |
   | 0112, 0182, 0183, 0184, 0190, 0191, 0230 | Administrativo / Outside |
   | Todo lo demás | Operaciones / On Property |

   Es solo el valor por defecto. Cada posición se corrige en las columnas V y W del Excel.
3. **Conflictos esperables.**
   - `payroll_api.py` y `frontend/lib/api.ts` difieren bastante entre hoteles.
     Resolver a mano conservando lo del hotel y agregando lo nuevo.
   - `textos.py` y `messages/*.json`: claves nuevas, sin pisar las del hotel.
   - `payroll_excel.py` es casi idéntico al de CWL (2 líneas de diferencia).
4. **Tests.** `backend/tests/test_planilla_categoria.py` tiene que quedar en verde. Es
   independiente del hotel; si falla algo, es una adaptación pendiente, no la prueba.
   Correr también `pytest -k "payroll or planilla or excel"` y comparar contra `main`
   **antes** del port: una falla que ya estaba antes no es de este cambio.
5. **Frontend.** Correr `npx tsc --noEmit -p .` en `frontend/`.

## 3. Cómo queda para el usuario

**La lista al lado de «⬇ Excel»** (pantalla Planilla → Checkbook):
- Todas las categorías
- **On Property**: operativos y gerenciales en sitio
- **Outside**: administrativos y gerenciales fuera
- Solo Operaciones · Solo Administrativo · Solo Gerencial

**El Excel:**
- **Pestaña Planilla:** columnas A..U como antes. Agrega **V = Categoria** y
  **W = SubCategoria**, editables con lista, y autofiltro en el encabezado (funciona con
  la hoja protegida). Si se bajó con filtro, la **fila 2** lo dice («Solo Categoria: …»
  o «Solo SubCategoria: …») y el import lo lee de ahí.
- **Pestaña Resumen:** un renglón por depto con Headcount, Salario mensual ₡,
  Salario mensual US$, SW anual US$ y HC por mes (la suma de FTE, con el cero en
  blanco). Al final va el **TOTAL**. Son **fórmulas** sobre la pestaña Planilla: si se
  edita un FTE, el Resumen se mueve solo. Headcount y salario cuentan solo las
  posiciones con FTE en al menos un mes.
- **El import lee solo la primera pestaña.** Un Excel viejo, sin V/W, sigue subiendo.

**Subir un Excel filtrado reemplaza solo lo que trae el filtro.** Ejemplo: Recepción baja
«Solo Operaciones» y lo sube, y los Gerencial de Recepción no se tocan. Cuidados:
- Si se copian las filas a otro Excel donde la fila 2 dice otra cosa, el import lo toma
  como completo y reemplaza el depto entero.
- Toda subida recrea las posiciones y se lleva sus conceptos manuales (horas extra,
  cafetería, vivienda). Esto ya pasaba antes.
- Después de subir hay que **recalcular**.

## 4. Verificación del deploy

- **Backend:** `/health` del hotel → `git_sha` igual al commit y `migraciones_al_dia: true`.
- **Frontend:** bajar los chunks de `/payroll/checkbook` y buscar el literal
  `sub:On Property`. El nombre o hash del chunk no sirve para comprobarlo.
- **Prueba real:** bajar el Excel del Working del hotel y abrir la pestaña Resumen. El
  TOTAL de headcount tiene que coincidir con el número de posiciones con FTE > 0.

---

## 5. Port a Gardens (OJO), 2026-11-22

- Los 8 commits entraron en orden. Conflictos solo en el #3: `payroll_api.py` (import de
  `conceptos_por_depto_excel`, propio de Gardens) y `page.tsx` (botón «↓ Conceptos x depto»,
  propio de Gardens). Se conservaron los dos y se agregó lo nuevo.
- Migración renombrada a **`155_categoria_de_la_posicion.py`** (`revision = "155"`,
  `down_revision = "154"`).
- `DEFECTO_POR_DEPTO` quedó igual que en CWL.
- Tests: `test_planilla_categoria.py` 20/20 (hace falta `aiosqlite` instalado; sin él 12 se
  saltan). `pytest -k "payroll or planilla or excel"`: 357 → 379 passed, 0 fallas, igual que
  `origin/main` antes del port. Suite completa: 4936 → 4960 passed, 0 fallas en las dos. `npx tsc --noEmit -p .` limpio.
