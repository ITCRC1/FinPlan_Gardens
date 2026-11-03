"""Colaboración (Fase 3): asignación de secciones, estados y bloqueo por escenario."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.models.user import User
from app.models.scenario import Scenario
from app.models.section_assignment import (
    SectionAssignment, SECTIONS, SECTION_LABELS, STATUSES,
)
from app.models.annotation import Annotation, KINDS
from app.models.revenue_entry import RevenueEntry, REVENUE_LINES, REVENUE_LINE_LABELS
from app.models.sales_channel_config import SalesChannelConfig
from app.models.occupancy_budget import OccupancyBudget
from app.models.payroll_position import PayrollPosition
from app.models.opex_entry import OpexEntry
from app.models.room_type_config import RoomTypeConfig
from app.auth import get_current_user, get_current_admin

router = APIRouter(tags=["collab"])


async def _scenario_or_404(sid: str, db: AsyncSession) -> Scenario:
    s = await db.get(Scenario, sid)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


def _user_brief(u: User | None) -> dict | None:
    if not u:
        return None
    return {"id": u.id, "name": u.name or u.email, "email": u.email}


_STATUS_RANK = {"pending": 0, "in_progress": 1, "in_review": 2, "approved": 3}


#: Qué dimensión de provisionamiento gobierna cada sección del tablero. Las
#: que no están acá no se arman con departamentos: `master` es una sola fila y
#: `nonop` son rubros de abajo-GOP, que no tienen depto.
SECCION_DIM = {"revenue": "REVENUE", "costs": "COST",
               "payroll": "PAYROLL", "opex": "OPEX"}

#: Los rubros below-GOP del tablero. No salen del catálogo de departamentos
#: porque no son departamentos; su rótulo lo pone la pantalla.
NONOP_REFS = ["mgmt", "insurance", "capital", "financial", "depreciation"]


async def tablero_del_escenario(db: AsyncSession, scenario: Scenario) -> list[dict]:
    """Las filas del Tablero del Presupuesto, armadas desde el catálogo.

    **Por qué existe** (owner, 2026-11-03): *«revisá la naturaleza de cada
    sección y las que no apliquen que tengan la opción que se esconda»* ·
    *«planilla es extensa, opex es extensa»*.

    Antes la pantalla armaba esta lista sola, con una copia del catálogo de
    departamentos escrita en el navegador (`CWL_DEPTS`). Eso tenía dos
    consecuencias: mostraba los 37 departamentos en TODAS las secciones —Ingreso
    en Mantenimiento, costo de venta en Administración— y no se enteraba de lo
    que la propiedad había apagado en provisionamiento. El tablero pedía aprobar
    126 casillas de las cuales muchas no existen para este hotel.

    Ahora sale de donde ya vive la verdad, y por eso no hay que mantener una
    segunda lista:

    · `is_revenue_dept` dice quién factura. Ingreso sólo se ofrece ahí —es la
      misma regla que usa el provisionamiento (`_aplica`), no una copia.
    · `depts_habilitados` es el interruptor que el owner ya usa para apagar un
      departamento en una dimensión. El tablero lo respeta, así que esconder
      algo acá y esconderlo en el checkbook son **el mismo acto**, no dos.
    · `_conteos` dice cuántas líneas hay detrás de cada (depto, dimensión). Va
      en cada fila como `datos` para que apagar sea una decisión informada y no
      a ciegas.

    Cada fila trae además `madre`: el provisionamiento trabaja por paquete y
    rechaza un hijo suelto, así que la pantalla necesita saber a quién mandarle
    el apagado.
    """
    from app.api.provisioning_api import (DIMS_DEPT, _aplica, _conteos,
                                          depts_habilitados)
    from app.models.department_catalog import DepartmentCatalog

    catalogo = [d for d in (await db.execute(
        select(DepartmentCatalog).order_by(
            DepartmentCatalog.display_order, DepartmentCatalog.dept_code)
    )).scalars().all() if d.active]

    conteos = await _conteos(db, scenario.hotel_id)
    apagados = {dim: (await depts_habilitados(db, scenario.hotel_id, dim) or set())
                for dim in DIMS_DEPT}

    salida = [{"section": "master", "items": [{"ref": "", "label_key": "sec.general"}]}]
    for seccion, dim in SECCION_DIM.items():
        items = []
        for d in catalogo:
            codigo = (d.dept_code or "").strip()
            if not codigo or not _aplica(d, dim) or codigo in apagados[dim]:
                continue
            items.append({
                "ref": codigo,
                "label": d.dept_name or codigo,
                "datos": int(conteos.get(codigo, {}).get(dim, 0)),
                "madre": (d.parent_dept_code or "").strip() or codigo,
                "dimension": dim,
            })
        salida.append({"section": seccion, "items": items})
    salida.append({"section": "nonop",
                   "items": [{"ref": r, "label_key": f"nonop.{r}"} for r in NONOP_REFS]})
    return salida


class BulkAssigneeBody(BaseModel):
    assignee_id: str | None = None
    #: Vacío = todas las secciones del tablero.
    sections: list[str] = []


@router.post("/scenarios/{scenario_id}/assignments/bulk/")
async def asignar_en_bloque(
    scenario_id: str, body: BulkAssigneeBody,
    _u: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """Asigna de un golpe todas las filas del tablero a una persona.

    Owner, 2026-11-03: *«quiero que asignes todas las tareas a Bismark»*, sobre
    un tablero de 126 casillas. Una por una son 126 viajes al servidor y 126
    recargas de la pantalla; acá es uno.

    Las filas que no existían se crean, igual que cuando se asigna una sola:
    `SectionAssignment` nace al primer toque, no al crear el escenario.
    """
    scenario = await _scenario_or_404(scenario_id, db)
    if body.assignee_id:
        if await db.get(User, body.assignee_id) is None:
            raise ErrorApi(404, "usuario.no_encontrado")

    pedidas = set(body.sections or [])
    tocadas = 0
    for grupo in await tablero_del_escenario(db, scenario):
        if pedidas and grupo["section"] not in pedidas:
            continue
        for item in grupo["items"]:
            fila = await _get_or_create(scenario_id, grupo["section"], item["ref"], db)
            fila.assignee_id = body.assignee_id
            tocadas += 1
    await db.commit()
    return {"ok": True, "asignadas": tocadas, "assignee_id": body.assignee_id}


@router.get("/scenarios/{scenario_id}/assignments/")
async def get_assignments(
    scenario_id: str, idioma: str = Idioma,
    _u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Devuelve:
    - `assignments`: filas granulares por (section, ref=depto).
    - `sections`: rollup por sección (status = la menos avanzada de sus deptos), para
      el command center y compatibilidad."""
    await _scenario_or_404(scenario_id, db)
    rows = (await db.execute(
        select(SectionAssignment).where(SectionAssignment.scenario_id == scenario_id)
    )).scalars().all()
    users = {u.id: u for u in (await db.execute(select(User))).scalars().all()}

    assignments = [{
        "section": r.section, "ref": r.ref,
        "label": t(idioma, f"seccion.{r.section}"),
        "status": r.status, "locked": bool(r.locked),
        "assignee": _user_brief(users.get(r.assignee_id)) if r.assignee_id else None,
    } for r in rows]

    # rollup por sección
    sections = []
    for sec in SECTIONS:
        secRows = [r for r in rows if r.section == sec]
        if secRows:
            status = min(secRows, key=lambda r: _STATUS_RANK.get(r.status, 0)).status
            if all(r.status == "approved" for r in secRows):
                status = "approved"
            locked = any(r.locked for r in secRows)
        else:
            status, locked = "pending", False
        sections.append({"section": sec, "label": SECTION_LABELS[sec],
                         "status": status, "locked": locked, "assignee": None})
    return {"scenario_id": scenario_id, "sections": sections,
            "assignments": assignments,
            # La ESTRUCTURA del tablero: qué filas existen para esta propiedad.
            # Viaja acá y no en su propio endpoint para que la pantalla no pueda
            # pintar filas de un escenario con la estructura de otro.
            "tablero": await tablero_del_escenario(db, await _scenario_or_404(scenario_id, db))}


async def _get_or_create(sid: str, section: str, ref: str, db: AsyncSession) -> SectionAssignment:
    if section not in SECTIONS:
        raise ErrorApi(422, "collab.seccion_invalida", secciones=SECTIONS)
    r = (await db.execute(
        select(SectionAssignment).where(
            SectionAssignment.scenario_id == sid,
            SectionAssignment.section == section,
            SectionAssignment.ref == ref,
        )
    )).scalar_one_or_none()
    if r is None:
        r = SectionAssignment(scenario_id=sid, section=section, ref=ref)
        db.add(r)
    return r


class AssigneeBody(BaseModel):
    assignee_id: str | None = None


@router.put("/scenarios/{scenario_id}/assignments/{section}/assignee/")
async def set_assignee(
    scenario_id: str, section: str, body: AssigneeBody, ref: str = "",
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    await _scenario_or_404(scenario_id, db)
    r = await _get_or_create(scenario_id, section, ref, db)
    if body.assignee_id:
        u = await db.get(User, body.assignee_id)
        if not u:
            raise ErrorApi(404, "usuario.no_encontrado")
    r.assignee_id = body.assignee_id
    await db.commit()
    return {"saved": True, "section": section, "ref": ref, "assignee_id": r.assignee_id}


class StatusBody(BaseModel):
    status: str


@router.patch("/scenarios/{scenario_id}/assignments/{section}/status/")
async def set_status(
    scenario_id: str, section: str, body: StatusBody, ref: str = "",
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if body.status not in STATUSES:
        raise ErrorApi(422, "collab.estado_invalido", estados=STATUSES)
    await _scenario_or_404(scenario_id, db)
    r = await _get_or_create(scenario_id, section, ref, db)
    if r.locked and user.role != "admin":
        raise ErrorApi(409, "collab.seccion_bloqueada")
    if user.role != "admin" and r.assignee_id != user.id:
        raise ErrorApi(403, "collab.no_sos_responsable")
    if body.status == "approved" and user.role != "admin":
        raise ErrorApi(403, "collab.solo_admin_aprueba")
    r.status = body.status
    await db.commit()
    return {"saved": True, "section": section, "ref": ref, "status": r.status}


class LockBody(BaseModel):
    locked: bool


@router.patch("/scenarios/{scenario_id}/assignments/{section}/lock/")
async def set_lock(
    scenario_id: str, section: str, body: LockBody, ref: str = "",
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    await _scenario_or_404(scenario_id, db)
    r = await _get_or_create(scenario_id, section, ref, db)
    r.locked = body.locked
    await db.commit()
    return {"saved": True, "section": section, "ref": ref, "locked": r.locked}


# ─── Anotaciones: comentarios (narrativa) + Q&A ───────────────────────────────

def _annot_dict(a: Annotation, users: dict) -> dict:
    u = users.get(a.author_id)
    return {
        "id": a.id, "section": a.section, "label": SECTION_LABELS.get(a.section, a.section),
        "ref": a.ref, "month": a.month, "kind": a.kind, "body": a.body,
        "resolved": bool(a.resolved),
        "author": (u.name or u.email) if u else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/scenarios/{scenario_id}/annotations/")
async def list_annotations(
    scenario_id: str, kind: str | None = None, section: str | None = None,
    _u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _scenario_or_404(scenario_id, db)
    q = select(Annotation).where(Annotation.scenario_id == scenario_id)
    if kind:
        q = q.where(Annotation.kind == kind)
    if section:
        q = q.where(Annotation.section == section)
    q = q.order_by(Annotation.created_at)
    rows = (await db.execute(q)).scalars().all()
    users = {u.id: u for u in (await db.execute(select(User))).scalars().all()}
    return {"scenario_id": scenario_id, "annotations": [_annot_dict(a, users) for a in rows]}


class AnnotationBody(BaseModel):
    section: str
    ref: str = ""
    month: int = 0
    kind: str = "comment"
    body: str


@router.post("/scenarios/{scenario_id}/annotations/")
async def add_annotation(
    scenario_id: str, body: AnnotationBody,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await _scenario_or_404(scenario_id, db)
    if body.section not in SECTIONS:
        raise ErrorApi(422, "collab.seccion_invalida", secciones=SECTIONS)
    if body.kind not in KINDS:
        raise ErrorApi(422, "collab.kind_invalido", kinds=KINDS)
    if not body.body.strip():
        raise ErrorApi(422, "collab.texto_vacio")
    a = Annotation(
        scenario_id=scenario_id, section=body.section, ref=body.ref.strip(),
        month=body.month if 0 <= body.month <= 12 else 0,
        kind=body.kind, body=body.body.strip(), author_id=user.id,
    )
    db.add(a)
    await db.commit()
    users = {user.id: user}
    return _annot_dict(a, users)


class ResolveBody(BaseModel):
    resolved: bool


@router.patch("/annotations/{annotation_id}/resolve/")
async def resolve_annotation(
    annotation_id: str, body: ResolveBody,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    a = await db.get(Annotation, annotation_id)
    if not a:
        raise ErrorApi(404, "anotacion.no_encontrada")
    if user.role != "admin" and a.author_id != user.id:
        raise ErrorApi(403, "auth.solo_autor_o_admin")
    a.resolved = body.resolved
    await db.commit()
    return {"saved": True, "id": a.id, "resolved": a.resolved}


@router.delete("/annotations/{annotation_id}/")
async def delete_annotation(
    annotation_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    a = await db.get(Annotation, annotation_id)
    if not a:
        raise ErrorApi(404, "anotacion.no_encontrada")
    if user.role != "admin" and a.author_id != user.id:
        raise ErrorApi(403, "auth.solo_autor_o_admin")
    await db.delete(a)
    await db.commit()
    return {"deleted": True}


# ─── Validaciones automáticas (en lenguaje humano) ────────────────────────────
_MONTHS_ATTR = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


@router.get("/scenarios/{scenario_id}/validations/")
async def get_validations(
    scenario_id: str, _u: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """Chequeos automáticos por sección. level: ok | warn | error.

    El `level` es un ESTADO —lo lee el semáforo de la pantalla— y sigue en
    inglés; el `message` es lo que se lee, y sale en el idioma de quien pide.
    """
    scenario = await _scenario_or_404(scenario_id, db)
    out: list[dict] = []

    def add(section, level, clave, **params):
        out.append({"section": section, "level": level,
                    "message": t(idioma, clave, **params)})

    # ── master: inventario + pax ──
    rts = (await db.execute(
        select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == scenario.hotel_id))).scalars().all()
    total_units = sum(rt.units for rt in rts)
    if total_units <= 0:
        add("master", "error", "colaboracion.sin_inventario")
    else:
        add("master", "ok", "colaboracion.inventario_ok", n=total_units)

    # ── revenue: líneas + canales + ocupación ──
    rev = (await db.execute(
        select(RevenueEntry).where(RevenueEntry.scenario_id == scenario_id))).scalars().all()
    by_line = {e.line.upper(): e for e in rev}
    filled = 0; missing = []
    for line in REVENUE_LINES:
        e = by_line.get(line)
        tot = sum(float(getattr(e, m) or 0) for m in _MONTHS_ATTR) if e else 0.0
        if tot:
            filled += 1
        else:
            missing.append(REVENUE_LINE_LABELS.get(line, line))
    if filled == 0:
        add("revenue", "warn", "colaboracion.revenue_vacio")
    elif missing:
        add("revenue", "warn", "colaboracion.revenue_faltan_lineas", n=len(missing),
            lineas=", ".join(missing[:4]) + ("…" if len(missing) > 4 else ""))
    else:
        # ⚠️ El número sale del CONTEO, no escrito a mano. Decía «11 líneas»
        # cuando `REVENUE_LINES` tiene 14: quedó viejo al agregar tres líneas y
        # nadie lo notó, porque un mensaje de «todo bien» no se lee con lupa.
        add("revenue", "ok", "colaboracion.revenue_completo", n=filled)

    chans = (await db.execute(
        select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id))).scalars().all()
    if not chans:
        add("revenue", "warn", "colaboracion.canales_sin_configurar")
    else:
        mix_by_month: dict[int, float] = {}
        for c in chans:
            mix_by_month[c.month] = mix_by_month.get(c.month, 0.0) + float(c.mix_pct or 0)
        bad = [m for m, s in mix_by_month.items() if s > 0 and abs(s - 1.0) > 0.01]
        if bad:
            add("revenue", "warn", "colaboracion.mix_no_cierra", n=len(bad))

    occ = (await db.execute(
        select(OccupancyBudget).where(OccupancyBudget.scenario_id == scenario_id))).scalars().all()
    over = sum(1 for o in occ if float(o.occupancy_pct or 0) > 1.0)
    if over:
        add("revenue", "warn", "colaboracion.ocupacion_sobre_cien", n=over)

    # ── payroll ──
    pos = (await db.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id))).scalars().all()
    if not pos:
        add("payroll", "warn", "colaboracion.sin_posiciones")
    else:
        nosal = sum(1 for p in pos if float(p.salary_amount or 0) == 0)
        if nosal:
            add("payroll", "warn", "colaboracion.posiciones_sin_salario", n=nosal)
        else:
            add("payroll", "ok", "colaboracion.posiciones_con_salario", n=len(pos))

    # ── opex ──
    opex_n = (await db.execute(
        select(OpexEntry).where(OpexEntry.scenario_id == scenario_id))).scalars().all()
    if not opex_n:
        add("opex", "warn", "colaboracion.opex_sin_datos")

    n_err = sum(1 for v in out if v["level"] == "error")
    n_warn = sum(1 for v in out if v["level"] == "warn")
    return {"scenario_id": scenario_id, "validations": out, "errors": n_err, "warnings": n_warn}
