# Para quien tenga acceso a GitHub — cómo subir esto

**Fecha: 2026-09-03.** Escrito para alguien que llega en frío.

---

## Lo primero, en una línea

**Producción ya corre este código. GitHub no lo tiene.** Los commits viven sólo
en el disco de esta máquina. Falta un `git push` que la cuenta de acá no tiene
permiso para hacer.

```
remote: Permission to ITCRC1/FinPlan_Gardens.git denied to Bismark1973.
```

⚠️ **No borrar `C:\dev\FinPlan_Gardens`.** Es la única copia de esos commits.

---

## Cómo se destraba

En GitHub → `ITCRC1/FinPlan_Gardens` → **Settings** → **Collaborators** →
**Add people** → `Bismark1973` → permiso **Write**.

O lo empuja directo quien ya tenga acceso, con el repositorio de esta máquina.

---

## El comando

`main` ya está adelantado y **listo para empujar**. Es un avance lineal sobre
`origin/main`, sin commit de fusión ni conflictos que resolver:

```bash
cd C:\dev\FinPlan_Gardens && git push origin main
```

Si prefieren revisarlo antes por Pull Request, la misma historia está en una
rama aparte:

```bash
cd C:\dev\FinPlan_Gardens && git push origin port/cierre-amarena
```

**Nada más hay que hacer.** No hay que compilar, ni migrar, ni redesplegar: eso
ya está en producción.

---

## Qué se está subiendo

El cierre mensual que ya corre en Amarena y en Oxygen: P&L Statement con
Forecast, Auditoría por naturaleza —también sobre presupuestos—, detalle de
celda al tocar una línea, comentarios por mes, Word y Excel completos,
Checkbooks y Revenue Plan de consulta, y el aviso cuando la plata llega a un
renglón por descarte.

Cada commit explica **por qué**, no sólo qué.

---

## Cómo comprobar que está sano antes de empujar

```bash
cd C:\dev\FinPlan_Gardens\backend && .venv\Scripts\python.exe -m pytest -q
```

Al 2026-09-03: **4230 pasan, 36 saltadas, 0 fallan.**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://finplangardens-backend.up.railway.app/health
```

---

## ⚠️ Si el push falla por conflicto

Significa que alguien más subió algo a `main` desde el 2026-09-03. **No forzar.**

```bash
cd C:\dev\FinPlan_Gardens && git pull --rebase origin main
```

Después correr las pruebas otra vez **antes** de empujar. Un `--force` acá
borraría trabajo ajeno y dejaría producción corriendo algo que el repo no
describe — que es justamente el problema que este archivo existe para cerrar.

---

## Contexto que conviene tener

La migración `138` **ya está aplicada** en la base de producción, así que cuando
el push dispare un despliegue, `alembic upgrade head` no hace nada. No hay riesgo
de doble aplicación.

⚠️ **Esta propiedad se despliega desde la RAÍZ del repo, no desde `backend/`** —
al revés que Oxygen. El detalle, y por qué, está en
[`docs/DESPLIEGUE_GARDENS.md`](docs/DESPLIEGUE_GARDENS.md).
