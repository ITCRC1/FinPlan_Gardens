"use client";
import { useCallback, useEffect, useState, CSSProperties } from "react";
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
  type Scenario, type Rent, type RentFila,
} from "@/lib/api";

/**
 * Rent — los locales que se alquilan dentro de la propiedad.
 *
 * Una fila por contrato. **No son líneas fijas del checkbook**: los inquilinos
 * entran y salen, así que se agregan desde acá y no desde el código.
 *
 * La renta venía cayendo en las cuentas de Sabor Ojochal (4500/4501/4502 del
 * 0155) porque los locales están adentro de Sabor. No es ingreso de Sabor: no
 * tiene costo de venta ni sigue la ocupación del hotel. Desde el 2026-11-01
 * tiene su propio renglón del P&L — `REV_RENT`, departamento 0157.
 *
 * **La suma de los contratos ACTIVOS es la que viaja al P&L.** Un contrato que
 * terminó se apaga con la casilla y conserva sus meses; borrarlo con la ✕ lo
 * saca de verdad al guardar.
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

const money = (v: number) => (v ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—");
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version))
    ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

/** Lo que se edita en pantalla: los montos van como texto para que borrar una
 *  casilla no la vuelva 0 mientras se tipea. */
type Borrador = {
  id?: string; name: string; ubicacion: string; cuenta: string; notes: string;
  active: boolean; meses: string[];
};
const vacia = (): Borrador => ({ name: "", ubicacion: "", cuenta: "", notes: "", active: true, meses: Array(12).fill("") });
const desdeApi = (f: RentFila): Borrador => ({
  id: f.id, name: f.name, ubicacion: f.ubicacion, cuenta: f.cuenta, notes: f.notes,
  active: f.active, meses: f.meses.map(v => (v ? String(v) : "")),
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
  const [filas, setFilas] = useState<Borrador[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

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
      setFilas(d.filas.map(desdeApi));
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); setDatos(null); }
  }, []);
  useEffect(() => { cargar(scenarioId); }, [scenarioId, cargar]);

  const num = (s: string) => { const n = parseFloat((s || "").replace(/[^0-9.-]/g, "")); return isNaN(n) ? 0 : n; };
  const totalFila = (f: Borrador) => f.meses.reduce((a, v) => a + num(v), 0);
  /** Lo que ve el P&L: los apagados no suman. */
  const totalMes = (m: number) => filas.reduce((a, f) => a + (f.active ? num(f.meses[m]) : 0), 0);
  const totalAnual = Array.from({ length: 12 }, (_, m) => totalMes(m)).reduce((a, b) => a + b, 0);

  const cambiar = (i: number, cambio: Partial<Borrador>) =>
    setFilas(prev => prev.map((f, k) => (k === i ? { ...f, ...cambio } : f)));

  /** Un monto se copia a los meses siguientes que estén vacíos: un alquiler casi
   *  nunca cambia mes a mes y tipearlo doce veces es trabajo tonto. */
  function ponerMes(i: number, m: number, v: string) {
    setFilas(prev => prev.map((f, k) => {
      if (k !== i) return f;
      const meses = [...f.meses];
      meses[m] = v.replace(/[^0-9.-]/g, "");
      for (let j = m + 1; j < 12; j++) { if (!meses[j]) meses[j] = meses[m]; else break; }
      return { ...f, meses };
    }));
  }

  /** Pegar desde Excel: una celda, una fila de meses o un bloque. Se empieza
   *  en la casilla donde se pegó y se sigue hacia la derecha; lo que pase de
   *  diciembre se descarta en vez de correrse al año siguiente. Una celda vacía
   *  queda vacía y no se vuelve 0, que es distinto. */
  function pegar(i: number, m: number, e: React.ClipboardEvent) {
    manejarPegado(e, (celdas) => {
      const plano = celdas.flat();
      setFilas(prev => prev.map((f, k) => {
        if (k !== i) return f;
        const meses = [...f.meses];
        plano.forEach((c, j) => {
          const destino = m + j;
          if (destino > 11) return;
          meses[destino] = String(c ?? "").trim() === "" ? "" : String(numeroDeExcel(c));
        });
        return { ...f, meses };
      }));
    });
  }

  async function guardar() {
    setBusy(true); setMsg(""); setError("");
    try {
      const d = await saveRent(scenarioId, filas.map((f, i) => ({
        id: f.id, name: f.name.trim(), ubicacion: f.ubicacion.trim(),
        cuenta: f.cuenta, notes: f.notes.trim(), sort: i, active: f.active,
        meses: f.meses.map(num),
      })));
      setDatos(d); setFilas(d.filas.map(desdeApi)); setMsg(t("saved"));
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setBusy(false); }
  }

  async function bajarExcel() {
    if (!datos) return;
    const meses = Array.from({ length: 12 }, (_, m) => m);
    const cuadro: FilaCuadro[] = [
      ...filas.map(f => ({
        // Con la cuenta adelante, el cuadro se coteja contra el mayor sin
        // tener que adivinar qué local es cuál.
        label: [f.cuenta, f.active ? f.name : `${f.name} (${t("off")})`]
          .filter(Boolean).join(" · "),
        valores: [...meses.map(m => num(f.meses[m])), totalFila(f)],
      })),
      { label: `${datos.linea.cuenta} · ${datos.linea.nombre}`, es_total: true,
        valores: [...meses.map(m => totalMes(m)), totalAnual] },
    ];
    try {
      await bajarCuadros("Rent", [{
        titulo: t("title"),
        subtitulo: scenarios.find(s => s.id === scenarioId)
          ? scnLabel(scenarios.find(s => s.id === scenarioId)!) : "",
        hoja: "Rent",
        columnas: [
          { label: t("tenant"), ancho: 34, formato: "texto" },
          ...MESES.map(m => ({ label: m, ancho: 12, formato: "usd" as const })),
          { label: t("yearTotal"), ancho: 15, formato: "usd" as const },
        ],
        filas: cuadro,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }

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
        {datos && <strong>{datos.linea.dept} · {datos.linea.cuenta} · {datos.linea.nombre}</strong>}
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
        <table style={{ borderCollapse: "collapse", minWidth: 1180 }}>
          <thead>
            <tr>
              <th style={{ ...th, minWidth: 210 }}>{t("tenant")}</th>
              <th style={{ ...th, minWidth: 130 }}>{t("where")}</th>
              <th style={{ ...th, minWidth: 150 }}>{t("account")}</th>
              <th style={{ ...th, width: 54, textAlign: "center" }}>{t("on")}</th>
              {MESES.map(m => <th key={m} style={thNum}>{m}</th>)}
              <th style={thNum}>{t("yearTotal")}</th>
              <th style={{ ...th, width: 34 }} />
            </tr>
          </thead>
          <tbody>
            {filas.map((f, i) => (
              <tr key={f.id ?? `nueva-${i}`} style={{ opacity: f.active ? 1 : 0.5 }}>
                <td style={td}>
                  <input value={f.name} placeholder={t("tenantPlaceholder")}
                    onChange={e => cambiar(i, { name: e.target.value })} style={inputTexto} />
                </td>
                <td style={td}>
                  <input value={f.ubicacion} placeholder={t("wherePlaceholder")}
                    onChange={e => cambiar(i, { ubicacion: e.target.value })} style={inputTexto} />
                </td>
                <td style={td}>
                  {/* La lista sale del catálogo, no del código. Una cuenta que
                      ya tomó otro contrato se muestra deshabilitada en vez de
                      esconderse: así se ve POR QUÉ no se puede elegir. */}
                  <select value={f.cuenta} title={t("accountHint")}
                    onChange={e => cambiar(i, { cuenta: e.target.value })}
                    style={{ ...inputTexto, width: 150 }}>
                    <option value="">{t("accountNone")}</option>
                    {(datos?.cuentas ?? []).map(c => {
                      const ocupada = !!c.tomada_por && c.cuenta !== f.cuenta;
                      return (
                        <option key={c.cuenta} value={c.cuenta} disabled={ocupada}>
                          {c.cuenta}{c.nombre ? ` · ${c.nombre}` : ""}
                          {ocupada ? ` — ${c.tomada_por}` : ""}
                        </option>
                      );
                    })}
                  </select>
                </td>
                <td style={{ ...td, textAlign: "center" }}>
                  <input type="checkbox" checked={f.active} title={t("onHint")}
                    onChange={e => cambiar(i, { active: e.target.checked })} />
                </td>
                {Array.from({ length: 12 }, (_, m) => (
                  <td key={m} style={tdNum}>
                    <input value={f.meses[m]} style={inputMes}
                      onPaste={e => pegar(i, m, e)}
                      onChange={e => ponerMes(i, m, e.target.value)} />
                  </td>
                ))}
                <td style={{ ...tdNum, fontWeight: 700 }}>{money(totalFila(f))}</td>
                <td style={{ ...td, textAlign: "center" }}>
                  <button onClick={() => setFilas(prev => prev.filter((_, k) => k !== i))}
                    title={t("removeHint")}
                    style={{ background: "none", border: "none", color: "var(--negative)",
                             cursor: "pointer", fontSize: 14 }}>✕</button>
                </td>
              </tr>
            ))}
            <tr>
              <td colSpan={4} style={{ ...td, fontWeight: 700 }}>
                {datos ? `${datos.linea.cuenta} · ${datos.linea.nombre}` : t("total")}
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

      <button onClick={() => setFilas(prev => [...prev, vacia()])}
        style={{ ...boton, marginTop: 12 }}>+ {t("addTenant")}</button>
    </div>
  );
}
