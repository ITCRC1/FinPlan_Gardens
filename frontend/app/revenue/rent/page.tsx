"use client";
import { Fragment, useCallback, useEffect, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { manejarPegado, numeroDeExcel } from "@/lib/pegarGrilla";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getRent, saveRent,
  type Scenario, type Rent, type RentContrato,
} from "@/lib/api";

/**
 * Rent — los locales que se alquilan dentro de la propiedad.
 *
 * Un inquilino por bloque, y dentro **un set de conceptos**: alquiler,
 * mantenimiento, servicios… cada uno con su cuenta contable y sus doce meses
 * (owner, 2026-11-01: «no quiero solo una cuenta, quiero un set de cuentas»).
 * Los inquilinos entran y salen, así que se agregan desde acá y no desde el
 * código; las cuentas salen del catálogo, no de una lista escrita acá.
 *
 * La renta venía cayendo en las cuentas de Sabor Ojochal (4500/4501/4502 del
 * 0155) porque los locales están adentro de Sabor. No es ingreso de Sabor: no
 * tiene costo de venta ni sigue la ocupación del hotel. Desde el 2026-11-01
 * tiene su propio renglón del P&L — `REV_RENT`, departamento 0157.
 *
 * **La suma de los conceptos de los contratos ACTIVOS es la que viaja al P&L.**
 * El interruptor es del inquilino: si se fue, no cobra ninguno de sus
 * conceptos. Apagado conserva sus meses; la ✕ sí lo borra al guardar.
 */
const HOTEL = HOTEL_ID;
const MESES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                        "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 11, textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.05em", background: "var(--bg-elevated)" };
const thNum: CSSProperties = { ...th, textAlign: "right", textTransform: "none", letterSpacing: 0 };
const tdNum: CSSProperties = { padding: "4px 6px", textAlign: "right", fontSize: 12.5, fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--border-subtle)" };
const td: CSSProperties = { padding: "4px 8px", fontSize: 12.5, borderBottom: "1px solid var(--border-subtle)" };
const inputMes: CSSProperties = { width: 74, textAlign: "right", padding: "3px 6px", fontSize: 12.5, fontVariantNumeric: "tabular-nums", borderRadius: 4, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" };
const inputTexto: CSSProperties = { ...inputMes, width: "100%", textAlign: "left" };
const boton: CSSProperties = { padding: "5px 14px", fontSize: 12.5, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "transparent", color: "var(--text-primary)", border: "1px solid var(--border-medium)" };
const botonChico: CSSProperties = { ...boton, padding: "2px 9px", fontSize: 11.5, fontWeight: 600 };
/** La fila del inquilino: la que manda sobre sus conceptos. */
const tdCabeza: CSSProperties = { ...td, background: "var(--bg-elevated)", borderTop: "2px solid var(--border-medium)" };

const money = (v: number) => (v ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—");
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version))
    ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

/** Lo que se edita en pantalla: los montos van como texto para que borrar una
 *  casilla no la vuelva 0 mientras se tipea. */
type ItemBorrador = { id?: string; concepto: string; cuenta: string; meses: string[] };
type Borrador = {
  name: string; ubicacion: string; notes: string; active: boolean;
  items: ItemBorrador[];
};
const itemVacio = (concepto: string): ItemBorrador =>
  ({ concepto, cuenta: "", meses: Array(12).fill("") });
const vacio = (concepto: string): Borrador =>
  ({ name: "", ubicacion: "", notes: "", active: true, items: [itemVacio(concepto)] });
const desdeApi = (c: RentContrato): Borrador => ({
  name: c.name, ubicacion: c.ubicacion, notes: c.notes, active: c.active,
  items: c.items.map(i => ({
    id: i.id, concepto: i.concepto, cuenta: i.cuenta,
    meses: i.meses.map(v => (v ? String(v) : "")),
  })),
});

export default function RentPage() {
  const hotel = useHotel();
  const t = useTranslations("rent");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [datos, setDatos] = useState<Rent | null>(null);
  const [contratos, setContratos] = useState<Borrador[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const CONCEPTO = datos?.concepto_por_defecto ?? "Alquiler";

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL);
        if (!all.length) { setError(tc("noScenarios", { hotel: hotel.id })); return; }
        setScenarios(all);
        const bud = elegir(all, "budget") ?? all[0];
        setScenarioId(sharedScenarioOr(bud.id));
      } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    })();
  }, [setScenarioId, tc, hotel.id]);

  const cargar = useCallback(async (id: string) => {
    if (!id) return;
    setError(""); setMsg("");
    try {
      const d = await getRent(id);
      setDatos(d);
      setContratos(d.contratos.map(desdeApi));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); setDatos(null); }
  }, []);
  useEffect(() => { cargar(scenarioId); }, [scenarioId, cargar]);

  const num = (s: string) => { const n = parseFloat((s || "").replace(/[^0-9.-]/g, "")); return isNaN(n) ? 0 : n; };
  const totalItem = (it: ItemBorrador) => it.meses.reduce((a, v) => a + num(v), 0);
  const mesContrato = (c: Borrador, m: number) => c.items.reduce((a, it) => a + num(it.meses[m]), 0);
  const totalContrato = (c: Borrador) => c.items.reduce((a, it) => a + totalItem(it), 0);
  /** Lo que ve el P&L: los contratos apagados no suman, con todo y conceptos. */
  const totalMes = (m: number) =>
    contratos.reduce((a, c) => a + (c.active ? mesContrato(c, m) : 0), 0);
  const totalAnual = Array.from({ length: 12 }, (_, m) => totalMes(m)).reduce((a, b) => a + b, 0);

  const cambiarContrato = (ci: number, cambio: Partial<Borrador>) =>
    setContratos(prev => prev.map((c, k) => (k === ci ? { ...c, ...cambio } : c)));
  const cambiarItem = (ci: number, ii: number, cambio: Partial<ItemBorrador>) =>
    setContratos(prev => prev.map((c, k) => k !== ci ? c : {
      ...c, items: c.items.map((it, j) => (j === ii ? { ...it, ...cambio } : it)),
    }));

  /** Un monto se copia a los meses siguientes que estén vacíos: un alquiler casi
   *  nunca cambia mes a mes y tipearlo doce veces es trabajo tonto. */
  function ponerMes(ci: number, ii: number, m: number, v: string) {
    setContratos(prev => prev.map((c, k) => k !== ci ? c : {
      ...c, items: c.items.map((it, j) => {
        if (j !== ii) return it;
        const meses = [...it.meses];
        meses[m] = v.replace(/[^0-9.-]/g, "");
        for (let x = m + 1; x < 12; x++) { if (!meses[x]) meses[x] = meses[m]; else break; }
        return { ...it, meses };
      }),
    }));
  }

  /** Pegar desde Excel: una celda, una fila de meses o un bloque. Se empieza en
   *  la casilla donde se pegó y se sigue hacia la derecha; lo que pase de
   *  diciembre se descarta en vez de correrse. Una celda vacía queda vacía y no
   *  se vuelve 0, que es distinto. */
  function pegar(ci: number, ii: number, m: number, e: React.ClipboardEvent) {
    manejarPegado(e, (celdas) => {
      const plano = celdas.flat();
      setContratos(prev => prev.map((c, k) => k !== ci ? c : {
        ...c, items: c.items.map((it, j) => {
          if (j !== ii) return it;
          const meses = [...it.meses];
          plano.forEach((cel, x) => {
            const destino = m + x;
            if (destino > 11) return;
            meses[destino] = String(cel ?? "").trim() === "" ? "" : String(numeroDeExcel(cel));
          });
          return { ...it, meses };
        }),
      }));
    });
  }

  async function guardar() {
    setBusy(true); setMsg(""); setError("");
    try {
      const d = await saveRent(scenarioId, contratos.map(c => ({
        name: c.name.trim(), ubicacion: c.ubicacion.trim(),
        notes: c.notes.trim(), active: c.active,
        items: c.items.map(it => ({
          id: it.id, concepto: it.concepto.trim() || CONCEPTO,
          cuenta: it.cuenta, meses: it.meses.map(num),
        })),
      })));
      setDatos(d); setContratos(d.contratos.map(desdeApi)); setMsg(t("saved"));
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setBusy(false); }
  }

  async function bajarExcel() {
    if (!datos) return;
    const meses = Array.from({ length: 12 }, (_, m) => m);
    const cuadro: FilaCuadro[] = [];
    contratos.forEach(c => {
      cuadro.push({
        label: c.active ? c.name : `${c.name} (${t("off")})`, nivel: 0,
        valores: [...meses.map(m => mesContrato(c, m)), totalContrato(c)],
      });
      // Con la cuenta adelante, el cuadro se coteja contra el mayor sin tener
      // que adivinar qué concepto es cuál.
      c.items.forEach(it => cuadro.push({
        label: [it.cuenta, it.concepto].filter(Boolean).join(" · "), nivel: 1,
        valores: [...meses.map(m => num(it.meses[m])), totalItem(it)],
      }));
    });
    cuadro.push({ label: `${datos.linea.dept} · ${datos.linea.nombre}`, es_total: true,
                  valores: [...meses.map(m => totalMes(m)), totalAnual] });
    try {
      await bajarCuadros("Rent", [{
        titulo: t("title"),
        subtitulo: scenarios.find(s => s.id === scenarioId)
          ? scnLabel(scenarios.find(s => s.id === scenarioId)!) : "",
        hoja: "Rent",
        columnas: [
          { label: t("tenant"), ancho: 36, formato: "texto" },
          ...MESES.map(m => ({ label: m, ancho: 12, formato: "usd" as const })),
          { label: t("yearTotal"), ancho: 15, formato: "usd" as const },
        ],
        filas: cuadro,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

  /** El desplegable de cuentas. La lista sale del catálogo; la que ya tomó otro
   *  concepto se ve deshabilitada CON el nombre de quien la tiene, en vez de
   *  esconderse: así se ve por qué no se puede elegir. */
  const selectorCuenta = (ci: number, ii: number, it: ItemBorrador) => (
    <select value={it.cuenta} title={t("accountHint")}
      onChange={e => cambiarItem(ci, ii, { cuenta: e.target.value })}
      style={{ ...inputTexto, width: 160 }}>
      <option value="">{t("accountNone")}</option>
      {(datos?.cuentas ?? []).map(c => {
        const ocupada = !!c.tomada_por && c.cuenta !== it.cuenta;
        return (
          <option key={c.cuenta} value={c.cuenta} disabled={ocupada}>
            {c.cuenta}{c.nombre ? ` · ${c.nombre}` : ""}
            {ocupada ? ` — ${c.tomada_por}` : ""}
          </option>
        );
      })}
    </select>
  );

  return (
    <div className="pag pag-ancha" style={{ padding: "24px 20px 60px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} disabled={!datos} style={boton}>⬇ Excel</button>
        <button onClick={guardar} disabled={busy || !datos}
          style={{ ...boton, background: "var(--brand)", color: "#fff", border: "none",
                   cursor: busy || !datos ? "not-allowed" : "pointer" }}>
          {busy ? tc("saving") : tc("save")}
        </button>
      </div>

      <p style={{ color: "var(--text-secondary)", fontSize: 12.5, maxWidth: 980, marginTop: 10 }}>
        {t("intro")}{" "}
        {datos && <strong>{datos.linea.dept} · {datos.linea.nombre}</strong>}
      </p>
      {datos?.nota && (
        <p style={{ color: "var(--text-secondary)", fontSize: 12, maxWidth: 980, marginTop: -4 }}>
          {datos.nota}
        </p>
      )}
      {error && <p style={{ color: "var(--negative)", fontSize: 13 }}>{error}</p>}
      {msg && <p style={{ color: "var(--positive)", fontSize: 13 }}>{msg}</p>}

      {/* `fin-scroll-x`: sin ella el encabezado sticky resuelve contra esta caja
          y `top: var(--nav-h)` lo baja 44px, tapando la primera fila. */}
      <div className="fin-scroll-x" style={{ overflowX: "auto", marginTop: 14 }}>
        <table style={{ borderCollapse: "collapse", minWidth: 1240 }}>
          <thead>
            <tr>
              <th style={{ ...th, minWidth: 210 }}>{t("tenant")}</th>
              <th style={{ ...th, minWidth: 140 }}>{t("whereOrAccount")}</th>
              <th style={{ ...th, width: 54, textAlign: "center" }}>{t("on")}</th>
              {MESES.map(m => <th key={m} style={thNum}>{m}</th>)}
              <th style={thNum}>{t("yearTotal")}</th>
              <th style={{ ...th, width: 34 }} />
            </tr>
          </thead>
          <tbody>
            {contratos.map((c, ci) => (
              <Fragment key={`c-${ci}`}>
                {/* El inquilino: su nombre, dónde está y si cobra. Los montos
                    de esta fila son la SUMA de sus conceptos, no se digitan. */}
                <tr key={`c-${ci}`} style={{ opacity: c.active ? 1 : 0.5 }}>
                  <td style={tdCabeza}>
                    <input value={c.name} placeholder={t("tenantPlaceholder")}
                      onChange={e => cambiarContrato(ci, { name: e.target.value })}
                      style={{ ...inputTexto, fontWeight: 700 }} />
                  </td>
                  <td style={tdCabeza}>
                    <input value={c.ubicacion} placeholder={t("wherePlaceholder")}
                      onChange={e => cambiarContrato(ci, { ubicacion: e.target.value })}
                      style={inputTexto} />
                  </td>
                  <td style={{ ...tdCabeza, textAlign: "center" }}>
                    <input type="checkbox" checked={c.active} title={t("onHint")}
                      onChange={e => cambiarContrato(ci, { active: e.target.checked })} />
                  </td>
                  {Array.from({ length: 12 }, (_, m) => (
                    <td key={m} style={{ ...tdCabeza, textAlign: "right", fontWeight: 700,
                                         fontVariantNumeric: "tabular-nums" }}>
                      {money(mesContrato(c, m))}
                    </td>
                  ))}
                  <td style={{ ...tdCabeza, textAlign: "right", fontWeight: 800,
                               fontVariantNumeric: "tabular-nums" }}>
                    {money(totalContrato(c))}
                  </td>
                  <td style={{ ...tdCabeza, textAlign: "center" }}>
                    <button onClick={() => setContratos(p => p.filter((_, k) => k !== ci))}
                      title={t("removeHint")}
                      style={{ background: "none", border: "none", color: "var(--negative)",
                               cursor: "pointer", fontSize: 14 }}>✕</button>
                  </td>
                </tr>

                {c.items.map((it, ii) => (
                  <tr key={`c-${ci}-i-${it.id ?? ii}`} style={{ opacity: c.active ? 1 : 0.5 }}>
                    <td style={{ ...td, paddingLeft: 26 }}>
                      <input value={it.concepto} placeholder={CONCEPTO}
                        onChange={e => cambiarItem(ci, ii, { concepto: e.target.value })}
                        style={inputTexto} />
                    </td>
                    <td style={td}>{selectorCuenta(ci, ii, it)}</td>
                    <td style={td} />
                    {Array.from({ length: 12 }, (_, m) => (
                      <td key={m} style={tdNum}>
                        <input value={it.meses[m]} style={inputMes}
                          onPaste={e => pegar(ci, ii, m, e)}
                          onChange={e => ponerMes(ci, ii, m, e.target.value)} />
                      </td>
                    ))}
                    <td style={{ ...tdNum, fontWeight: 600 }}>{money(totalItem(it))}</td>
                    <td style={{ ...td, textAlign: "center" }}>
                      {c.items.length > 1 && (
                        <button title={t("removeItemHint")}
                          onClick={() => cambiarContrato(ci, {
                            items: c.items.filter((_, j) => j !== ii) })}
                          style={{ background: "none", border: "none",
                                   color: "var(--text-secondary)", cursor: "pointer",
                                   fontSize: 13 }}>✕</button>
                      )}
                    </td>
                  </tr>
                ))}

                <tr key={`c-${ci}-add`}>
                  <td colSpan={16} style={{ ...td, paddingLeft: 26 }}>
                    <button style={botonChico}
                      onClick={() => cambiarContrato(ci, {
                        items: [...c.items, itemVacio("")] })}>
                      + {t("addConcept")}
                    </button>
                  </td>
                </tr>
              </Fragment>
            ))}

            <tr>
              <td colSpan={3} style={{ ...td, fontWeight: 700 }}>
                {datos ? `${datos.linea.dept} · ${datos.linea.nombre}` : t("total")}
              </td>
              {Array.from({ length: 12 }, (_, m) => (
                <td key={m} style={{ ...tdNum, fontWeight: 700, background: "var(--bg-elevated)" }}>
                  {money(totalMes(m))}
                </td>
              ))}
              <td style={{ ...tdNum, fontWeight: 800, background: "var(--bg-elevated)" }}>
                {money(totalAnual)}
              </td>
              <td style={td} />
            </tr>
          </tbody>
        </table>
      </div>

      <button onClick={() => setContratos(prev => [...prev, vacio(CONCEPTO)])}
        style={{ ...boton, marginTop: 12 }}>+ {t("addTenant")}</button>
    </div>
  );
}
