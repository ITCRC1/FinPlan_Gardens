"use client";
/**
 * El modelo que MANDA, cuando el escenario saca Rooms del tarifario RAC.
 *
 * Owner, 2026-10-28: *«yo necesito tener claro cuál fue el modelo que usé…
 * manejo 4 hoteles y todos tienen modelos diferentes. Yo prefiero hacer que las
 * vistas muestren el dato correcto, por si tengo que validar, se vea dónde salió
 * el número. Si me das RAC y la vista del descuento editable con la nota de que
 * se agregó manual, yo sabré… y veo el neto ahí mismo y el monto que se va al
 * cálculo de ingresos»*.
 *
 * ## Por qué un bloque aparte y no un aviso
 *
 * La primera idea fue ponerle un cartel a la pantalla: «ojo, este total no es
 * el del P&L». El owner lo rechazó, y con razón: un aviso le dice que el número
 * que está mirando no sirve, pero no le dice cuál sirve ni de dónde sale. Con
 * cuatro propiedades en modelos distintos, lo que necesita no es una
 * advertencia sino **la trazabilidad**: RAC → descuento → neto → lo que viaja.
 *
 * ## ⚠️ Acá no se edita
 *
 * El descuento se edita en Planning → Rack Rooms → Origen de la tarifa, y de
 * acá sale un enlace. Dos pantallas que escriben el mismo campo es como
 * empiezan las dos verdades — y este sistema ya pagó por eso tres veces.
 */
import type { RackRoomsResponse } from "@/lib/api";

const MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const n = (v: string | number | undefined | null) => {
  const x = parseFloat(String(v ?? ""));
  return isNaN(x) ? 0 : x;
};
const usd = (v: number) =>
  "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2,
                                    maximumFractionDigits: 2 });
const usd0 = (v: number) =>
  "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 });
const pct = (v: number) => (v * 100).toFixed(1) + "%";
const ent = (v: number) => Math.round(v).toLocaleString("en-US");

const TD: React.CSSProperties = { padding: "5px 8px", textAlign: "right",
                                  fontVariantNumeric: "tabular-nums" };
const TDL: React.CSSProperties = { padding: "5px 8px", textAlign: "left" };

export default function BloqueModeloRac({ d, esc }: {
  d: RackRoomsResponse; esc: string;
}) {
  const T = d.total;
  const R = T.rack;
  // El RAC del año es el ponderado SIN tarifa propia: Long term no sale del
  // tarifario, y mezclarlo haría ver un RAC más bajo del que se cobra.
  const racAnio = n(R.adr_rack_sin_propias);

  const fila = (
    label: string,
    v: (m: RackRoomsResponse["meses"][0]) => number,
    total: number,
    f: (x: number) => string,
    opts: { bold?: boolean; nota?: string; color?: string } = {},
  ) => (
    <tr>
      <td style={{ ...TDL, fontWeight: opts.bold ? 700 : undefined }}>
        {label}
        {opts.nota && (
          <span style={{ marginLeft: 6, fontSize: 10.5, fontWeight: 400,
                         color: "var(--warning, #F59E0B)" }}>
            {opts.nota}
          </span>)}
      </td>
      {d.meses.map(m => (
        <td key={m.month} style={{ ...TD, fontWeight: opts.bold ? 700 : undefined,
                                   color: opts.color }}>
          {f(v(m))}
        </td>))}
      <td style={{ ...TD, fontWeight: 700, color: opts.color }}>{f(total)}</td>
    </tr>
  );

  return (
    <div style={{ marginBottom: 26, padding: "14px 16px", borderRadius: 8,
                  background: "var(--bg-surface)",
                  border: "2px solid var(--brand)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10,
                    flexWrap: "wrap", marginBottom: 4 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0,
                     color: "var(--text-primary)" }}>
          Modelo en uso: Rack Rooms — por segmento de venta
        </h2>
        <span style={{ fontSize: 11.5, fontWeight: 700, padding: "2px 8px",
                       borderRadius: 4, background: "var(--brand)",
                       color: "#fff" }}>
          este es el que mueve el P&amp;L
        </span>
      </div>
      <p style={{ fontSize: 12, color: "var(--text-secondary)",
                  margin: "0 0 12px" }}>
        Ingreso = noches por segmento × RAC ponderado × (1 − descuento).
        Las tablas de abajo son el <b>modelo de tarifas</b> (rack por tipo ×
        net factor de canales): sirven para ver los supuestos, pero en este
        escenario <b>no alimentan el reporte</b>.
      </p>

      <div className="fin-sticky" style={{ overflowX: "auto" }}>
        <table className="fin-table" style={{ minWidth: 1180, fontSize: 12.5 }}>
          <thead><tr>
            <th style={{ textAlign: "left", minWidth: 230 }}>Concepto</th>
            {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 74 }}>{m}</th>)}
            <th style={{ textAlign: "right", minWidth: 96 }}>Año</th>
          </tr></thead>
          <tbody>
            {fila("RAC ponderado ($/noche)", m => n(m.rac_ponderado), racAnio, usd)}
            {fila("Noches ocupadas", m => n(m.rack.noches_facturadas),
                  n(R.noches_facturadas), ent)}
            {fila("Noches disponibles", m => n(m.disponibles),
                  n(T.disponibles), ent)}
            {fila("Ingreso a tarifa RACK", m => n(m.rack.ingreso_rack),
                  n(R.ingreso_rack), usd0, { bold: true })}
            {fila("% descuento vs rack", m => n(m.rack.comision_pct),
                  n(R.comision_pct), pct,
                  { nota: "cargado a mano, por mes" })}
            {fila("Descuento $", m => n(m.rack.comision_usd),
                  n(R.comision_usd), usd0)}
            {fila("INGRESO NETO", m => n(m.rack.ingreso_neto),
                  n(R.ingreso_neto), usd0,
                  { bold: true, color: "var(--brand)" })}
            {fila("ADR neto", m => n(m.rack.adr_neto), n(T.adr), usd)}
            {fila("RevPAR neto", m => n(m.rack.revpar_neto), n(T.revpar), usd)}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: 18, flexWrap: "wrap",
                    alignItems: "center", marginTop: 12 }}>
        <span style={{ fontSize: 13 }}>
          Lo que va al cálculo de ingresos:{" "}
          <b style={{ color: "var(--brand)", fontSize: 15 }}>
            {usd(n(T.ingreso))}
          </b>
        </span>
        <a href={`/revenue/rack-rooms?esc=${encodeURIComponent(esc)}`}
           style={{ fontSize: 12.5, color: "var(--brand)", fontWeight: 600 }}>
          Editar el descuento en Origen de la tarifa →
        </a>
      </div>
    </div>
  );
}
