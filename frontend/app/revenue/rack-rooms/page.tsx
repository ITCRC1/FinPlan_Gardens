"use client";
/**
 * Planning → Rack Rooms Calculation.
 *
 * Owner, 2026-10-16: *«me interesa clonar el tab KPIs RACK y el tab Origen
 * Tarifa Rac y la base de datos viene desde el tab llamado Resumen Mensual.
 * Favor crea un modelo donde yo pueda modificar las variables inputs y que
 * derive todo lo demás»*.
 *
 * ## Los seis sub-tabs, en el orden del cálculo
 *
 *     1 · Villas y RAC    se digita: unidades y tarifa por temporada
 *     2 · Temporadas      se digita: los rangos de fecha del año
 *     3 · Noches          se digita: noches por segmento y mes
 *     4 · Origen tarifa   sale: días por temporada → RAC del mes → tarifa neta
 *     5 · KPIs Rack       sale: ingreso, ADR, ocupación, RevPAR mes a mes
 *     6 · Conexión        el interruptor hacia el P&L
 *
 * Son sub-tabs y no pantallas sueltas porque el número final no se entiende sin
 * el camino: el ADR del 5 sale del RAC del 4, que sale de lo que se digitó en
 * el 1 y el 2.
 *
 * ## ⚠️ Nada llega al P&L hasta el paso 6
 *
 * Mientras `rooms_source` siga en `tarifas`, esto se llena y se compara sin
 * mover un número del reporte. Conectarlo es un acto aparte y explícito.
 *
 * ## ⚠️ Los CONTROLES se muestran, no se esconden
 *
 * El libro del owner tiene filas de control que tienen que dar cero: días sin
 * temporada, unidades que no coinciden, segmentos sin comisión. Cuando fallan,
 * el total **sigue cuadrando consigo mismo** — por eso van arriba y en rojo, no
 * enterrados en una celda que nadie mira.
 */
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import IrA from "@/components/IrA";
import {
  getScenarios, getRackRooms, saveRackVillas, saveRackTemporadas,
  saveRackComisiones, saveRackNoches, conectarRackRooms,
  type Scenario, type RackRoomsResponse, type RackVillaFila,
  type RackTemporadaFila, type RackComisionFila,
} from "@/lib/api";
import { elegir } from "@/lib/escenarioPreferido";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { fmtUsd, fmtPct, fmtInt } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { manejarPegado, numeroDeExcel, repartirPegado } from "@/lib/pegarGrilla";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { recalcularYContar } from "@/lib/recalcular";

const MONTHS_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const PASOS = ["villas", "temporadas", "noches", "origen", "kpis", "conexion"] as const;
type Paso = typeof PASOS[number];
const TEMPORADAS = ["PICO", "ALTA", "VERDE"] as const;

/** Texto → número tolerante: acepta lo que sale de Excel (`$1,234.50`, `20%`). */
const n = (v: string | number | undefined | null) => {
  const x = parseFloat(String(v ?? "").replace(/[, %$]/g, ""));
  return isNaN(x) ? 0 : x;
};

const btn = (on: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: on ? "pointer" : "not-allowed", border: "none",
  background: on ? "var(--brand)" : "var(--bg-surface)",
  color: on ? "#fff" : "var(--text-disabled)",
});
const excelBtn: React.CSSProperties = {
  padding: "7px 16px", fontSize: 13, fontWeight: 700, borderRadius: 5,
  cursor: "pointer", background: "transparent", color: "var(--positive)",
  border: "1px solid var(--positive)",
};
const inpNum: React.CSSProperties = {
  width: 78, textAlign: "right", padding: "3px 5px", fontSize: 12.5,
  borderRadius: 4, border: "1px solid var(--border-medium)",
  background: "var(--bg-base)", color: "var(--text-primary)",
  fontVariantNumeric: "tabular-nums",
};
const TD: React.CSSProperties = { padding: "4px 7px", textAlign: "right",
                                  fontVariantNumeric: "tabular-nums" };
const TDL: React.CSSProperties = { padding: "4px 7px", textAlign: "left" };
const AVISO: React.CSSProperties = {
  padding: "8px 12px", borderRadius: 5, fontSize: 12.5, marginBottom: 10,
  background: "var(--bg-surface)", borderLeft: "3px solid var(--negative)",
  color: "var(--text-primary)",
};

export default function RackRoomsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("rackRooms");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [data, setData] = useState<RackRoomsResponse | null>(null);
  const [paso, setPaso] = useState<Paso>("villas");

  // Los inputs se editan como TEXTO y se convierten al guardar: un `number`
  // controlado no deja escribir «0.», ni borrar el campo para teclear otra cosa.
  const [villas, setVillas] = useState<RackVillaFila[]>([]);
  const [temps, setTemps] = useState<RackTemporadaFila[]>([]);
  const [coms, setComs] = useState<RackComisionFila[]>([]);
  const [noches, setNoches] = useState<Record<string, Record<number, string>>>({});
  const [tarifasPropias, setTarifasPropias] = useState<Record<string, Record<number, string>>>({});

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const aplicar = useCallback((d: RackRoomsResponse) => {
    setData(d);
    setVillas(d.villas.map(v => ({ ...v })));
    setTemps(d.temporadas.map(x => ({ ...x })));
    // Un segmento sin fila de comisión se muestra en 0% — que es como lo lee el
    // motor: sin fila se vende A RACK, no gratis. Ver `tarifa_del_segmento`.
    const porCode = new Map(d.comisiones.map(c => [c.segmento_code, c]));
    setComs(d.segmentos.map(s => porCode.get(s.code)
      ?? { segmento_code: s.code, comision_pct: "0", tarifa_propia: false }));
    const nn: Record<string, Record<number, string>> = {};
    const tp: Record<string, Record<number, string>> = {};
    for (const s of d.segmentos) { nn[s.code] = {}; tp[s.code] = {}; }
    for (const e of d.entradas) {
      (nn[e.segmento_code] ??= {})[e.month] = String(n(e.noches));
      (tp[e.segmento_code] ??= {})[e.month] = String(n(e.tarifa));
    }
    setNoches(nn);
    setTarifasPropias(tp);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        const budget = elegir(all, "budget") ?? all[0];
        if (!budget) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(budget.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setError(null);
    try { aplicar(await getRackRooms(sid)); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, [aplicar]);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const locked = !!data?.locked;
  const segs = data?.segmentos ?? [];
  const propias = useMemo(
    () => new Set(coms.filter(c => c.tarifa_propia).map(c => c.segmento_code)),
    [coms]);

  // ── Pegar desde Excel ──────────────────────────────────────────────────────
  //
  // El owner arma esto en un libro y lo trae pegado. Sin esto los doce meses
  // entran DENTRO de la primera celda: no falla, no avisa, y hay que teclearlos
  // de nuevo. Owner, 2026-10-04: *«rate y todo queda en la primera celda»*.

  /** La grilla de noches: filas = segmentos (en pantalla), columnas = meses. */
  const pegarNoches = useCallback((fi: number, mi: number, bloque: string[][]) => {
    setNoches(v => {
      const out = { ...v };
      repartirPegado(bloque, fi, mi, segs.length, 12, (f, c, valor) => {
        const code = segs[f].code;
        out[code] = { ...(out[code] ?? {}), [c + 1]: String(numeroDeExcel(valor)) };
      });
      return out;
    });
  }, [segs]);

  /** Las tarifas propias: sólo las filas que tienen tarifa propia. */
  const conTarifaPropia = useMemo(
    () => segs.filter(s => propias.has(s.code)), [segs, propias]);
  const pegarTarifas = useCallback((fi: number, mi: number, bloque: string[][]) => {
    setTarifasPropias(v => {
      const out = { ...v };
      repartirPegado(bloque, fi, mi, conTarifaPropia.length, 12, (f, c, valor) => {
        const code = conTarifaPropia[f].code;
        out[code] = { ...(out[code] ?? {}), [c + 1]: String(numeroDeExcel(valor)) };
      });
      return out;
    });
  }, [conTarifaPropia]);

  /** El cuadro de villas: columnas = unidades, RAC pico, alta, verde. */
  const COLS_VILLA = ["unidades", "rac_pico", "rac_alta", "rac_verde"] as const;
  const pegarVillas = useCallback((fi: number, ci: number, bloque: string[][]) => {
    setVillas(xs => {
      const out = xs.map(x => ({ ...x }));
      repartirPegado(bloque, fi, ci, out.length, COLS_VILLA.length, (f, c, valor) => {
        const k = COLS_VILLA[c];
        const num = numeroDeExcel(valor);
        // Unidades es un entero: un «2.5» pegado por error se trunca acá y no
        // en el backend, donde el redondeo no se vería.
        (out[f] as Record<string, unknown>)[k] =
          k === "unidades" ? Math.max(0, Math.round(num)) : String(num);
      });
      return out;
    });
  }, []);

  /** Guarda y recarga. El backend devuelve el cuadro recalculado entero. */
  async function guardar(fn: () => Promise<RackRoomsResponse>) {
    if (!scenarioId || locked) return;
    setSaving(true); setError(null); setMsg(null);
    try { aplicar(await fn()); setMsg(t("saved")); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setSaving(false); }
  }

  async function recalcular() {
    if (!scenarioId) return;
    setRecalc(true); setError(null);
    try {
      await recalcularYContar(scenarioId);
      await load(scenarioId);
      setMsg(t("recalculated"));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setRecalc(false); }
  }

  // ── Los controles del libro ────────────────────────────────────────────────
  const avisos: string[] = [];
  if (data && !data.hay_tarifario) avisos.push(t("warnNoTariff"));
  if (data && !data.controles.unidades.coinciden) {
    avisos.push(t("warnUnits", { hotel: data.controles.unidades.hotel,
                                 tarifario: data.controles.unidades.tarifario }));
  }
  if (data?.controles.meses_sin_temporada.length) {
    avisos.push(t("warnSeasonGap", {
      meses: data.controles.meses_sin_temporada.map(m => MONTHS[m - 1]).join(", ") }));
  }
  if (data?.controles.segmentos_sin_comision.length) {
    avisos.push(t("warnNoCommission", {
      codes: data.controles.segmentos_sin_comision.join(", ") }));
  }

  // ── Excel: el cuadro de KPIs, que es el que se manda afuera ────────────────
  async function bajarExcel() {
    if (!data) return;
    const sel = scenarios.find(s => s.id === scenarioId);
    const esc = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const d = data;
    const fila = (label: string, pick: (m: typeof d.meses[0]) => number,
                  formato: FilaCuadro["formato"], total: number,
                  nivel = 1): FilaCuadro =>
      ({ label, nivel, formato, valores: [...d.meses.map(pick), total] });
    const T = d.total;
    const filas: FilaCuadro[] = [
      { label: t("blockRack"), es_total: true, valores: Array(13).fill(null) },
      fila(t("racWeighted"), m => n(m.rac_ponderado), "usd2", 0),
      { label: t("blockVolume"), es_total: true, valores: Array(13).fill(null) },
      fila(t("available"), m => n(m.disponibles), "num", n(T.disponibles)),
      fila(t("nightsRevenue"), m => n(m.noches_ingreso), "num", n(T.noches_ingreso)),
      fila(t("nightsTotal"), m => n(m.noches_totales), "num", n(T.noches_totales)),
      { label: t("blockKpis"), es_total: true, valores: Array(13).fill(null) },
      fila(t("revenue"), m => n(m.ingreso), "usd2", n(T.ingreso)),
      fila(t("adr"), m => n(m.adr), "usd2", n(T.adr)),
      fila(t("occupancy"), m => n(m.ocupacion), "pct", n(T.ocupacion)),
      fila(t("occupancyTotal"), m => n(m.ocupacion_total), "pct", n(T.ocupacion_total)),
      fila(t("revpar"), m => n(m.revpar), "usd2", n(T.revpar)),
      { label: t("blockSegments"), es_total: true, valores: Array(13).fill(null) },
    ];
    for (const s of segs) {
      filas.push({
        label: s.nombre, nivel: 1, formato: "usd2",
        valores: [...d.meses.map(m => n(m.segmentos[s.code]?.ingreso)),
                  n(T.segmentos[s.code]?.ingreso)],
      });
    }
    try {
      await bajarCuadros("Rack_Rooms", [{
        titulo: "Rack Rooms Calculation",
        subtitulo: `${esc} · ${t("xlsSubtitle")}`,
        hoja: "Rack Rooms",
        columnas: [
          { label: t("concept"), ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 12, formato: "usd2" as const })),
          { label: tc("total"), ancho: 14, formato: "usd2" as const },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          Rack Rooms Calculation
        </h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
                className="fin-input" style={{ minWidth: 220 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>
              {s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}
            </option>))}
        </select>
        <button onClick={bajarExcel} style={excelBtn}>⬇ Excel</button>
        {data?.conectado && (
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--positive)" }}>
            ● {t("connected")}
          </span>)}
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t("intro")}
      </p>

      {/* Los sub-tabs, en el orden del cálculo */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {PASOS.map((p, i) => (
          <button key={p} onClick={() => setPaso(p)} style={{
            ...btn(true),
            background: paso === p ? "var(--brand)" : "var(--bg-surface)",
            color: paso === p ? "#fff" : "var(--text-secondary)",
          }}>{i + 1} · {t(`step_${p}`)}</button>))}
      </div>

      {avisos.map((a, i) => <div key={i} style={AVISO}>⚠️ {a}</div>)}
      {error && <div style={{ ...AVISO, borderLeftColor: "var(--negative)" }}>{error}</div>}
      {msg && <div style={{ ...AVISO, borderLeftColor: "var(--positive)" }}>{msg}</div>}
      {locked && <div style={AVISO}>🔒 {t("lockedHint")}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : !data ? null : (
        <>
          {/* ── 1 · Villas y RAC ───────────────────────────────────────────── */}
          {paso === "villas" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10 }}>
                {t("villasHint")}
              </p>
              <table className="fin-table" style={{ minWidth: 720 }}>
                <thead><tr>
                  <th style={{ textAlign: "left", minWidth: 200 }}>{t("villa")}</th>
                  <th style={{ textAlign: "right" }}>{t("units")}</th>
                  <th style={{ textAlign: "right" }}>RAC {t("seasonPICO")}</th>
                  <th style={{ textAlign: "right" }}>RAC {t("seasonALTA")}</th>
                  <th style={{ textAlign: "right" }}>RAC {t("seasonVERDE")}</th>
                  <th />
                </tr></thead>
                <tbody>
                  {villas.map((v, i) => (
                    <tr key={i}>
                      <td style={TDL}>
                        <input value={v.villa} disabled={locked} className="fin-input"
                               style={{ width: 200, fontSize: 12.5 }}
                               onChange={e => setVillas(xs => xs.map((x, j) =>
                                 j === i ? { ...x, villa: e.target.value } : x))} />
                      </td>
                      {COLS_VILLA.map((k, ki) => (
                        <td key={k} style={TD}>
                          <input value={String(v[k] ?? "")} disabled={locked} style={inpNum}
                                 onPaste={e => manejarPegado(e, b => pegarVillas(i, ki, b))}
                                 onChange={e => setVillas(xs => xs.map((x, j) =>
                                   j === i ? { ...x, [k]: k === "unidades"
                                     ? Math.max(0, Math.round(n(e.target.value)))
                                     : e.target.value } : x))} />
                        </td>))}
                      <td style={TD}>
                        <button disabled={locked} style={{ ...btn(!locked), padding: "3px 9px" }}
                                onClick={() => setVillas(xs => xs.filter((_, j) => j !== i))}>
                          ✕
                        </button>
                      </td>
                    </tr>))}
                  <tr>
                    <td style={{ ...TDL, fontWeight: 700 }}>{tc("total")}</td>
                    <td style={{ ...TD, fontWeight: 700 }}>
                      {fmtInt(villas.reduce((a, v) => a + (v.unidades || 0), 0))}
                    </td>
                    <td colSpan={4} />
                  </tr>
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button disabled={locked} style={btn(!locked)}
                        onClick={() => setVillas(xs => [...xs, {
                          villa: "", unidades: 0, rac_pico: "0", rac_alta: "0",
                          rac_verde: "0", orden: xs.length }])}>
                  + {t("addVilla")}
                </button>
                <button disabled={locked || saving} style={btn(!locked && !saving)}
                        onClick={() => guardar(() => saveRackVillas(scenarioId,
                          villas.map((v, i) => ({ ...v, orden: i }))))}>
                  {saving ? tc("saving") : tc("save")}
                </button>
              </div>
            </div>)}

          {/* ── 2 · Temporadas ─────────────────────────────────────────────── */}
          {paso === "temporadas" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10 }}>
                {t("seasonsHint")}
              </p>
              <table className="fin-table" style={{ minWidth: 560 }}>
                <thead><tr>
                  <th style={{ textAlign: "left" }}>{t("season")}</th>
                  <th style={{ textAlign: "left" }}>{t("from")}</th>
                  <th style={{ textAlign: "left" }}>{t("to")}</th>
                  <th style={{ textAlign: "right" }}>{t("days")}</th>
                  <th />
                </tr></thead>
                <tbody>
                  {temps.map((x, i) => {
                    const dias = Math.round(
                      (new Date(x.hasta).getTime() - new Date(x.desde).getTime())
                      / 86400000) + 1;
                    return (
                      <tr key={i}>
                        <td style={TDL}>
                          <select value={x.temporada} disabled={locked} className="fin-input"
                                  style={{ fontSize: 12.5 }}
                                  onChange={e => setTemps(xs => xs.map((y, j) =>
                                    j === i ? { ...y, temporada: e.target.value } : y))}>
                            {TEMPORADAS.map(s =>
                              <option key={s} value={s}>{t(`season${s}`)}</option>)}
                          </select>
                        </td>
                        {(["desde", "hasta"] as const).map(k => (
                          <td key={k} style={TDL}>
                            <input type="date" value={x[k]} disabled={locked}
                                   className="fin-input" style={{ fontSize: 12.5 }}
                                   onChange={e => setTemps(xs => xs.map((y, j) =>
                                     j === i ? { ...y, [k]: e.target.value } : y))} />
                          </td>))}
                        <td style={TD}>{isNaN(dias) ? "—" : fmtInt(dias)}</td>
                        <td style={TD}>
                          <button disabled={locked} style={{ ...btn(!locked), padding: "3px 9px" }}
                                  onClick={() => setTemps(xs => xs.filter((_, j) => j !== i))}>
                            ✕
                          </button>
                        </td>
                      </tr>);
                  })}
                  <tr>
                    <td colSpan={3} style={{ ...TDL, fontWeight: 700 }}>
                      {t("daysCovered")}
                    </td>
                    <td style={{ ...TD, fontWeight: 700 }}>
                      {fmtInt(data.meses.reduce(
                        (a, m) => a + m.dias - m.dias_sin_temporada, 0))} / {
                        fmtInt(data.meses.reduce((a, m) => a + m.dias, 0))}
                    </td>
                    <td />
                  </tr>
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button disabled={locked} style={btn(!locked)}
                        onClick={() => setTemps(xs => [...xs, {
                          temporada: "VERDE",
                          desde: `${data.year}-01-01`, hasta: `${data.year}-01-31` }])}>
                  + {t("addSeason")}
                </button>
                <button disabled={locked || saving} style={btn(!locked && !saving)}
                        onClick={() => guardar(() => saveRackTemporadas(scenarioId, temps))}>
                  {saving ? tc("saving") : tc("save")}
                </button>
              </div>
            </div>)}

          {/* ── 3 · Noches por segmento ────────────────────────────────────── */}
          {paso === "noches" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10 }}>
                {t("nightsHint")}
              </p>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 1180 }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", minWidth: 210 }}>{t("segment")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 76 }}>{m}</th>)}
                    <th style={{ textAlign: "right", minWidth: 86 }}>{tc("total")}</th>
                  </tr></thead>
                  <tbody>
                    {segs.map((s, fi) => (
                      <tr key={s.code}>
                        <td style={TDL}>
                          {s.nombre}
                          {!s.genera_ingreso && (
                            <span title={t("noRevenueHint")}
                                  style={{ marginLeft: 6, fontSize: 11,
                                           color: "var(--text-secondary)" }}>
                              ({t("noRevenue")})
                            </span>)}
                        </td>
                        {MONTHS.map((_, mi) => (
                          <td key={mi} style={TD}>
                            <input value={noches[s.code]?.[mi + 1] ?? ""} disabled={locked}
                                   style={{ ...inpNum, width: 62 }}
                                   onPaste={e => manejarPegado(e, b => pegarNoches(fi, mi, b))}
                                   onChange={e => setNoches(v => ({ ...v,
                                     [s.code]: { ...(v[s.code] ?? {}),
                                                 [mi + 1]: e.target.value } }))} />
                          </td>))}
                        <td style={{ ...TD, fontWeight: 600 }}>
                          {fmtInt(MONTHS.reduce(
                            (a, _, mi) => a + n(noches[s.code]?.[mi + 1]), 0))}
                        </td>
                      </tr>))}
                  </tbody>
                </table>
              </div>

              {/* La tarifa propia: sólo para los segmentos sin RAC */}
              {propias.size > 0 && (
                <>
                  <h3 style={{ fontSize: 14, fontWeight: 700, marginTop: 18,
                               color: "var(--text-primary)" }}>
                    {t("ownRateTitle")}
                  </h3>
                  <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 8 }}>
                    {t("ownRateHint")}
                  </p>
                  <div className="fin-sticky" style={{ overflowX: "auto" }}>
                    <table className="fin-table" style={{ minWidth: 1180 }}>
                      <thead><tr>
                        <th style={{ textAlign: "left", minWidth: 210 }}>{t("segment")}</th>
                        {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 76 }}>{m}</th>)}
                      </tr></thead>
                      <tbody>
                        {conTarifaPropia.map((s, fi) => (
                          <tr key={s.code}>
                            <td style={TDL}>{s.nombre}</td>
                            {MONTHS.map((_, mi) => (
                              <td key={mi} style={TD}>
                                <input value={tarifasPropias[s.code]?.[mi + 1] ?? ""}
                                       disabled={locked} style={{ ...inpNum, width: 70 }}
                                       onPaste={e => manejarPegado(e, b => pegarTarifas(fi, mi, b))}
                                       onChange={e => setTarifasPropias(v => ({ ...v,
                                         [s.code]: { ...(v[s.code] ?? {}),
                                                     [mi + 1]: e.target.value } }))} />
                              </td>))}
                          </tr>))}
                      </tbody>
                    </table>
                  </div>
                </>)}

              <button disabled={locked || saving} style={{ ...btn(!locked && !saving), marginTop: 10 }}
                      onClick={() => guardar(() => saveRackNoches(scenarioId,
                        segs.flatMap(s => MONTHS.map((_, mi) => ({
                          segmento_code: s.code, month: mi + 1,
                          noches: n(noches[s.code]?.[mi + 1]),
                          ...(propias.has(s.code)
                            ? { tarifa: n(tarifasPropias[s.code]?.[mi + 1]) }
                            : {}),
                        })))))}>
                {saving ? tc("saving") : tc("save")}
              </button>
            </div>)}

          {/* ── 4 · Origen de la tarifa ────────────────────────────────────── */}
          {paso === "origen" && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10 }}>
                {t("originHint")}
              </p>

              {/* Las comisiones: el único input de esta pantalla */}
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
                {t("commissionsTitle")}
              </h3>
              <table className="fin-table" style={{ minWidth: 560, marginBottom: 18 }}>
                <thead><tr>
                  <th style={{ textAlign: "left", minWidth: 210 }}>{t("segment")}</th>
                  <th style={{ textAlign: "right" }}>{t("commission")}</th>
                  <th style={{ textAlign: "left" }}>{t("ownRate")}</th>
                </tr></thead>
                <tbody>
                  {coms.map((c, i) => {
                    const s = segs.find(x => x.code === c.segmento_code);
                    return (
                      <tr key={c.segmento_code}>
                        <td style={TDL}>{s?.nombre ?? c.segmento_code}</td>
                        <td style={TD}>
                          <input value={c.comision_pct} disabled={locked} style={inpNum}
                                 onChange={e => setComs(xs => xs.map((y, j) =>
                                   j === i ? { ...y, comision_pct: e.target.value } : y))} />
                          <span style={{ marginLeft: 6, fontSize: 11,
                                         color: "var(--text-secondary)" }}>
                            = {fmtPct(n(c.comision_pct))}
                          </span>
                        </td>
                        <td style={TDL}>
                          <input type="checkbox" checked={c.tarifa_propia} disabled={locked}
                                 onChange={e => setComs(xs => xs.map((y, j) =>
                                   j === i ? { ...y, tarifa_propia: e.target.checked } : y))} />
                        </td>
                      </tr>);
                  })}
                </tbody>
              </table>
              <button disabled={locked || saving} style={{ ...btn(!locked && !saving), marginBottom: 20 }}
                      onClick={() => guardar(() => saveRackComisiones(scenarioId, coms))}>
                {saving ? tc("saving") : tc("save")}
              </button>

              {/* El camino, mes a mes: días → RAC por villa → RAC ponderado */}
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
                {t("pathTitle")}
              </h3>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 1180 }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", minWidth: 210 }}>{t("concept")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>)}
                  </tr></thead>
                  <tbody>
                    {TEMPORADAS.map(s => (
                      <tr key={s}>
                        <td style={TDL}>{t("daysIn")} {t(`season${s}`)}</td>
                        {data.meses.map(m => (
                          <td key={m.month} style={TD}>
                            {fmtInt(m.dias_por_temporada[s] ?? 0)}
                          </td>))}
                      </tr>))}
                    <tr>
                      <td style={{ ...TDL, color: "var(--negative)" }}>
                        {t("daysNoSeason")}
                      </td>
                      {data.meses.map(m => (
                        <td key={m.month} style={{ ...TD,
                          color: m.dias_sin_temporada ? "var(--negative)" : undefined,
                          fontWeight: m.dias_sin_temporada ? 700 : undefined }}>
                          {fmtInt(m.dias_sin_temporada)}
                        </td>))}
                    </tr>
                    {villas.map(v => (
                      <tr key={v.villa}>
                        <td style={TDL}>RAC · {v.villa}</td>
                        {data.meses.map(m => (
                          <td key={m.month} style={TD}>
                            {fmtUsd(n(m.rac_por_villa[v.villa]))}
                          </td>))}
                      </tr>))}
                    <tr>
                      <td style={{ ...TDL, fontWeight: 700 }}>{t("racWeighted")}</td>
                      {data.meses.map(m => (
                        <td key={m.month} style={{ ...TD, fontWeight: 700 }}>
                          {fmtUsd(n(m.rac_ponderado))}
                        </td>))}
                    </tr>
                    {segs.filter(s => s.genera_ingreso).map(s => (
                      <tr key={s.code}>
                        <td style={TDL}>{t("netRateOf")} {s.nombre}</td>
                        {data.meses.map(m => (
                          <td key={m.month} style={TD}>
                            {fmtUsd(n(m.segmentos[s.code]?.tarifa))}
                          </td>))}
                      </tr>))}
                  </tbody>
                </table>
              </div>
            </div>)}

          {/* ── 5 · KPIs Rack ──────────────────────────────────────────────── */}
          {paso === "kpis" && (
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              <table className="fin-table" style={{ minWidth: 1260 }}>
                <thead><tr>
                  <th style={{ textAlign: "left", minWidth: 220 }}>{t("concept")}</th>
                  {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 82 }}>{m}</th>)}
                  <th style={{ textAlign: "right", minWidth: 96 }}>{tc("total")}</th>
                </tr></thead>
                <tbody>
                  <tr><td style={{ ...TDL, fontWeight: 700 }} colSpan={14}>{t("blockVolume")}</td></tr>
                  <tr>
                    <td style={TDL}>{t("available")}</td>
                    {data.meses.map(m => <td key={m.month} style={TD}>{fmtInt(n(m.disponibles))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtInt(n(data.total.disponibles))}</td>
                  </tr>
                  <tr>
                    <td style={TDL}>{t("nightsRevenue")}</td>
                    {data.meses.map(m => <td key={m.month} style={TD}>{fmtInt(n(m.noches_ingreso))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtInt(n(data.total.noches_ingreso))}</td>
                  </tr>
                  <tr>
                    <td style={TDL}>{t("nightsTotal")}</td>
                    {data.meses.map(m => <td key={m.month} style={TD}>{fmtInt(n(m.noches_totales))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtInt(n(data.total.noches_totales))}</td>
                  </tr>
                  <tr><td style={{ ...TDL, fontWeight: 700 }} colSpan={14}>{t("blockKpis")}</td></tr>
                  <tr>
                    <td style={{ ...TDL, fontWeight: 700 }}>{t("revenue")}</td>
                    {data.meses.map(m => <td key={m.month} style={{ ...TD, fontWeight: 700 }}>{fmtUsd(n(m.ingreso))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtUsd(n(data.total.ingreso))}</td>
                  </tr>
                  <tr>
                    <td style={TDL}>{t("adr")}</td>
                    {data.meses.map(m => <td key={m.month} style={TD}>{fmtUsd(n(m.adr))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtUsd(n(data.total.adr))}</td>
                  </tr>
                  <tr>
                    <td style={TDL}>{t("occupancy")}</td>
                    {data.meses.map(m => <td key={m.month} style={TD}>{fmtPct(n(m.ocupacion))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtPct(n(data.total.ocupacion))}</td>
                  </tr>
                  <tr>
                    <td style={TDL} title={t("occupancyTotalHint")}>{t("occupancyTotal")}</td>
                    {data.meses.map(m => <td key={m.month} style={TD}>{fmtPct(n(m.ocupacion_total))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtPct(n(data.total.ocupacion_total))}</td>
                  </tr>
                  <tr>
                    <td style={TDL}>{t("revpar")}</td>
                    {data.meses.map(m => <td key={m.month} style={TD}>{fmtUsd(n(m.revpar))}</td>)}
                    <td style={{ ...TD, fontWeight: 700 }}>{fmtUsd(n(data.total.revpar))}</td>
                  </tr>
                  <tr><td style={{ ...TDL, fontWeight: 700 }} colSpan={14}>{t("blockSegments")}</td></tr>
                  {segs.map(s => (
                    <tr key={s.code}>
                      <td style={TDL}>{s.nombre}</td>
                      {data.meses.map(m => (
                        <td key={m.month} style={TD}>
                          {fmtUsd(n(m.segmentos[s.code]?.ingreso))}
                        </td>))}
                      <td style={{ ...TD, fontWeight: 700 }}>
                        {fmtUsd(n(data.total.segmentos[s.code]?.ingreso))}
                      </td>
                    </tr>))}
                </tbody>
              </table>
            </div>)}

          {/* ── 6 · Conexión ───────────────────────────────────────────────── */}
          {paso === "conexion" && (
            <div style={{ maxWidth: 760 }}>
              <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 14 }}>
                {t("connectHint")}
              </p>
              <div style={{ padding: 16, borderRadius: 6, background: "var(--bg-surface)",
                            border: "1px solid var(--border-medium)" }}>
                <div style={{ fontSize: 13, marginBottom: 12 }}>
                  {t("currentModel")}: <b>{data.conectado ? t("modelChannels") : t("modelRates")}</b>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button disabled={locked || saving || data.conectado}
                          style={btn(!locked && !saving && !data.conectado)}
                          onClick={() => guardar(async () => {
                            await conectarRackRooms(scenarioId, "canales");
                            return getRackRooms(scenarioId);
                          })}>
                    {t("connect")}
                  </button>
                  <button disabled={locked || saving || !data.conectado}
                          style={btn(!locked && !saving && data.conectado)}
                          onClick={() => guardar(async () => {
                            await conectarRackRooms(scenarioId, "tarifas");
                            return getRackRooms(scenarioId);
                          })}>
                    {t("disconnect")}
                  </button>
                  <button disabled={recalc} style={btn(!recalc)} onClick={recalcular}>
                    {recalc ? t("recalculating") : t("recalculate")}
                  </button>
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginTop: 12 }}>
                  {t("connectWarning")}
                </p>
              </div>
            </div>)}
        </>
      )}
    </div>
  );
}
