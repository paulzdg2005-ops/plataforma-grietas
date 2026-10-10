"""
INTERFAZ DE LA APP
Muestra lo que calcula motor.py. Cuatro pantallas: Resumen, Historial por punto,
Registrar inspección y Alertas y reportes.
"""
import os
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import motor

CARPETA = os.path.dirname(os.path.abspath(__file__))
EXCEL = os.path.join(CARPETA, "datos", "EH4000_historial_grietas.xlsx")
CARPETA_ESQUEMAS = os.path.join(CARPETA, "imagenes", "esquemas")
CARPETA_FOTOS = os.path.join(CARPETA, "imagenes", "fotos")
os.makedirs(CARPETA_ESQUEMAS, exist_ok=True)
os.makedirs(CARPETA_FOTOS, exist_ok=True)

st.set_page_config(page_title="Integridad estructural EH4000", page_icon="🛠️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
.tarjeta {border-radius: 12px; padding: 14px 18px; margin-bottom: 10px; border: 1px solid #e3e3e0; background: #ffffff;}
.etiqueta {display:inline-block; padding: 3px 10px; border-radius: 8px; font-size: 13px; font-weight: 600; color: white;}
.kpi {border-radius: 12px; padding: 14px 18px; background: #f4f6fa;}
.kpi p {margin: 0;} .kpi .n {font-size: 30px; font-weight: 700;} .kpi .t {font-size: 14px; color: #555;}
</style>
""", unsafe_allow_html=True)


def etiqueta(estado):
    color = motor.ESTADO_COLOR.get(estado, "#888")
    return f'<span class="etiqueta" style="background:{color}">{estado}</span>'


def kpi(titulo, valor, color):
    st.markdown(f'<div class="kpi"><p class="t">{titulo}</p><p class="n" style="color:{color}">{valor}</p></div>',
                unsafe_allow_html=True)


@st.cache_data
def calcular(ruta, modificado, hasta):
    return motor.calcular_todo(ruta, hasta)


if not os.path.exists(EXCEL):
    st.error(f"No encuentro el Excel. Debe estar en: {EXCEL}")
    st.stop()

# ------------------------------------------------------------------
# BARRA LATERAL
# ------------------------------------------------------------------
completo = calcular(EXCEL, os.path.getmtime(EXCEL), None)
fechas = sorted(completo["historial"]["Fecha"].dt.date.unique(), reverse=True)

with st.sidebar:
    st.markdown("## 🛠️ Integridad estructural")
    st.caption("Camión de acarreo EH4000 · Equipo EH4-01\nZona 1: Chasis – viga derecha")
    pantalla = st.radio("Pantalla", ["Resumen de la zona", "Historial por punto",
                                     "Registrar inspección", "Alertas y reportes"])
    st.divider()
    ver_fecha = st.selectbox(
        "Ver el estado a la fecha", fechas, index=0,
        format_func=lambda d: d.strftime("%d-%b-%Y") + ("  (última)" if d == fechas[0] else ""),
        help="Sirve para 'viajar en el tiempo' y ver qué habría mostrado la plataforma en una inspección pasada.")
    st.caption(f"Intervalo típico entre inspecciones: {completo['intervalo']:.0f} h")

hasta = None if ver_fecha == fechas[0] else ver_fecha
R = calcular(EXCEL, os.path.getmtime(EXCEL), hasta)
res, an, al = R["resumen"], R["analisis"], R["alertas"]


# ------------------------------------------------------------------
# MODELO 3D SIMPLIFICADO DE LA VIGA DERECHA
# ------------------------------------------------------------------
POSICION_3D = {  # (x, y, z) aproximados sobre la viga
    "VD-01": (5.0, 0.0, 0.5),   # láminas, cara interna
    "VD-02": (1.0, 0.5, 0.0),   # unión con soporte clevis
    "VD-03": (7.0, 0.5, 1.0),   # unión con la columna
    "VD-04": (9.0, 0.5, -0.6),  # soporte suspensión delantera (parte inferior)
}


def modelo_3d(res):
    fig = go.Figure()

    def caja(x0, x1, y0, y1, z0, z1, color="#8a8f98"):
        v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        aristas = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
        xs, ys, zs = [], [], []
        for a, b in aristas:
            xs += [v[a][0], v[b][0], None]
            ys += [v[a][1], v[b][1], None]
            zs += [v[a][2], v[b][2], None]
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode="lines", line=dict(color=color, width=5),
                                   hoverinfo="skip", showlegend=False))

    caja(0, 10, 0, 1, 0, 1)            # viga derecha
    caja(6.6, 7.4, 0, 1, 1, 3.5)       # columna
    caja(0.5, 1.5, 0, 1, -0.8, 0)      # soporte clevis
    caja(8.5, 9.5, 0, 1, -1.2, 0)      # soporte suspensión delantera

    for _, r in res.iterrows():
        x, y, z = POSICION_3D.get(r["Código"], (0, 0, 0))
        color = motor.ESTADO_COLOR.get(r["Estado"], "#888")
        texto = (f"<b>{r['Código']}</b><br>{r['Descripción']}<br>Estado: {r['Estado']}<br>"
                 f"L: {r['L válida (mm)']:.0f} mm · Caution {r['Caution (mm)']:.0f} · Danger {r['Danger (mm)']:.0f}"
                 f"<br>Reparaciones: {r['Reparaciones']}")
        fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[z], mode="markers+text", text=[r["Código"]],
                                   textposition="top center", hovertext=[texto], hoverinfo="text",
                                   marker=dict(size=14, color=color, line=dict(color="white", width=2)),
                                   showlegend=False))
    fig.update_layout(height=430, margin=dict(l=0, r=0, t=0, b=0),
                      scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
                                 aspectmode="data", camera=dict(eye=dict(x=0.9, y=-1.6, z=0.9))))
    return fig


# ------------------------------------------------------------------
# PANTALLA 1: RESUMEN
# ------------------------------------------------------------------
if pantalla == "Resumen de la zona":
    st.title("Zona 1 · Chasis – viga derecha")
    st.caption(f"Estado a la inspección del {ver_fecha:%d-%b-%Y}")

    c = res["Estado"].value_counts()
    cols = st.columns(5)
    with cols[0]: kpi("Críticos", c.get("Crítico", 0), motor.ESTADO_COLOR["Crítico"])
    with cols[1]: kpi("En alerta", c.get("Alerta", 0), motor.ESTADO_COLOR["Alerta"])
    with cols[2]: kpi("Normales", c.get("Normal", 0), motor.ESTADO_COLOR["Normal"])
    with cols[3]: kpi("Por verificar", c.get("Por verificar", 0), motor.ESTADO_COLOR["Por verificar"])
    with cols[4]: kpi("Avisos activos", len(al), "#1f3864")

    izq, der = st.columns([3, 2])
    with izq:
        st.subheader("Modelo de la viga")
        st.plotly_chart(modelo_3d(res), width="stretch")
        st.caption("Arrastra para girar. Pasa el mouse sobre un punto para ver su detalle.")
    with der:
        st.subheader("Puntos de inspección")
        for _, r in res.iterrows():
            rapido = " · ⚡ crece muy rápido" if r["Crece muy rápido"] == "Sí" else ""
            proy = (f"Llega a {r['Siguiente límite']} en ~{r['Horas hasta el límite']:.0f} h"
                    if not pd.isna(r["Horas hasta el límite"]) else
                    ("Ya pasó Danger" if r["Siguiente límite"] == "Ya pasó Danger" else "Sin crecimiento"))
            st.markdown(
                f'<div class="tarjeta"><b>{r["Código"]}</b> {etiqueta(r["Estado"])}<br>'
                f'<span style="color:#555">{r["Descripción"]}</span><br>'
                f'L = <b>{r["L válida (mm)"]:.0f} mm</b> (Caution {r["Caution (mm)"]:.0f} / Danger {r["Danger (mm)"]:.0f})'
                f' · {proy}{rapido}<br>🔧 Reparaciones: {r["Reparaciones"]}</div>',
                unsafe_allow_html=True)

    esquema = os.path.join(CARPETA_ESQUEMAS, str(R["puntos"]["Esquema"].iloc[0]))
    if os.path.exists(esquema):
        st.subheader("Esquema de la zona")
        st.image(esquema, width="stretch")


# ------------------------------------------------------------------
# PANTALLA 2: HISTORIAL POR PUNTO
# ------------------------------------------------------------------
elif pantalla == "Historial por punto":
    codigos = list(res["Código"])
    cod = st.selectbox("Punto", codigos, format_func=lambda c: f"{c} · " +
                       res.set_index("Código").loc[c, "Descripción"])
    r = res.set_index("Código").loc[cod]
    d = an[an["Código"] == cod].sort_values("Horas (h)")

    st.markdown(f"### {cod} {etiqueta(r['Estado'])}", unsafe_allow_html=True)
    cols = st.columns(5)
    with cols[0]: kpi("L actual válida", f"{r['L válida (mm)']:.0f} mm", "#1f3864")
    with cols[1]: kpi("Caution / Danger", f"{r['Caution (mm)']:.0f} / {r['Danger (mm)']:.0f}", "#1f3864")
    with cols[2]: kpi("Velocidad actual", "—" if pd.isna(r["Velocidad (mm/h)"]) else f"{r['Velocidad (mm/h)']:.3f} mm/h", "#1f3864")
    with cols[3]: kpi("Horas hasta el límite", "—" if pd.isna(r["Horas hasta el límite"]) else f"{r['Horas hasta el límite']:.0f} h", "#1f3864")
    with cols[4]: kpi("Reparaciones", r["Reparaciones"], "#1f3864")

    eje = st.radio("Ver contra", ["Horas de operación", "Fecha"], horizontal=True)
    xcol = "Horas (h)" if eje == "Horas de operación" else "Fecha"

    fig = go.Figure()
    xmin, xmax = d[xcol].min(), d[xcol].max()
    ymax = max(r["Danger (mm)"] * 1.25, d.loc[d["Calidad"] != "Dudoso", "L actual (mm)"].max() * 1.15)

    # Franjas de estado
    fig.add_hrect(y0=0, y1=r["Caution (mm)"], fillcolor=motor.ESTADO_COLOR["Normal"], opacity=0.07, line_width=0)
    fig.add_hrect(y0=r["Caution (mm)"], y1=r["Danger (mm)"], fillcolor=motor.ESTADO_COLOR["Alerta"], opacity=0.10, line_width=0)
    fig.add_hrect(y0=r["Danger (mm)"], y1=ymax, fillcolor=motor.ESTADO_COLOR["Crítico"], opacity=0.08, line_width=0)
    fig.add_hline(y=r["Caution (mm)"], line_dash="dash", line_color=motor.ESTADO_COLOR["Alerta"],
                  annotation_text=f"Caution {r['Caution (mm)']:.0f} mm", annotation_position="top left")
    fig.add_hline(y=r["Danger (mm)"], line_dash="dash", line_color=motor.ESTADO_COLOR["Crítico"],
                  annotation_text=f"Danger {r['Danger (mm)']:.0f} mm", annotation_position="top left")

    # Reparaciones
    for _, rp in d[d["Motivo"].str.startswith("Reparación")].iterrows():
        if rp["Reparaciones acumuladas"] > 0:
            fig.add_vline(x=rp[xcol], line_color="#555", line_width=1.5, line_dash="dot")
            fig.add_annotation(x=rp[xcol], y=ymax * 0.97, text=f"🔧 Rep. {rp['Reparaciones acumuladas']}",
                               showarrow=False, font=dict(size=11))

    # Tramos válidos
    validas = d[d["Calidad"].isin(["OK", "Variación menor", "Confirmado"])]
    for t, g in validas.groupby("Tramo"):
        fig.add_trace(go.Scatter(
            x=g[xcol], y=g["L actual (mm)"], mode="lines+markers", name=f"Tramo {t}",
            line=dict(color="#2a78d6", width=2.5), marker=dict(size=8),
            customdata=np.stack([g["Fecha"].dt.strftime("%d-%b-%Y"), g["Horas (h)"], g["Inspector"], g["Calidad"]], axis=-1),
            hovertemplate="%{y:.0f} mm<br>%{customdata[0]} · %{customdata[1]:,.1f} h<br>%{customdata[2]} · %{customdata[3]}<extra></extra>",
            showlegend=False))

    dud = d[d["Calidad"] == "Dudoso"]
    if not dud.empty:
        fig.add_trace(go.Scatter(
            x=dud[xcol], y=dud["L actual (mm)"].clip(upper=ymax * 0.98), mode="markers", name="Dudoso (excluido)",
            marker=dict(symbol="x", size=13, color="#7a5cc7", line=dict(width=1)),
            text=dud["Motivo"], customdata=dud["L actual (mm)"],
            hovertemplate="Dudoso: %{customdata:.0f} mm<br>%{text}<extra></extra>"))

    # Proyección hasta el siguiente límite (solo en la vista por horas)
    if xcol == "Horas (h)" and not pd.isna(r["Horas hasta el límite"]) and not validas.empty:
        ult = validas.iloc[-1]
        lim = r["Caution (mm)"] if r["Siguiente límite"] == "Caution" else r["Danger (mm)"]
        fig.add_trace(go.Scatter(x=[ult["Horas (h)"], ult["Horas (h)"] + r["Horas hasta el límite"]],
                                 y=[ult["L actual (mm)"], lim], mode="lines", name="Proyección",
                                 line=dict(color="#2a78d6", dash="dot", width=2),
                                 hovertemplate="Proyección: %{y:.0f} mm a %{x:,.0f} h<extra></extra>"))

    fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="Longitud de grieta (mm)",
                      xaxis_title=eje, yaxis_range=[0, ymax], hovermode="closest",
                      legend=dict(orientation="h", y=-0.2), plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")
    st.caption("Línea azul: mediciones válidas (cada reparación inicia un tramo nuevo). "
               "X morada: dato dudoso, se muestra pero no entra en los cálculos. Punteado: proyección.")

    with st.expander("Ver todas las mediciones de este punto"):
        tabla = d[["Fecha", "Horas (h)", "Inspector", "L actual (mm)", "Estado", "Calidad", "Motivo",
                   "Tramo", "Reparaciones acumuladas", "Velocidad (mm/h)"]].copy()
        tabla["Fecha"] = tabla["Fecha"].dt.strftime("%d-%b-%Y")
        st.dataframe(tabla, hide_index=True, width="stretch")

    st.subheader("Imágenes")
    c1, c2 = st.columns(2)
    esquema = os.path.join(CARPETA_ESQUEMAS, str(d["Imagen"].iloc[0]))
    with c1:
        if os.path.exists(esquema):
            st.image(esquema, caption="Esquema de la zona", width="stretch")
        else:
            st.info(f"Pon el esquema de la zona en imagenes/esquemas/ con el nombre {d['Imagen'].iloc[0]}")
    with c2:
        fotos = sorted([f for f in os.listdir(CARPETA_FOTOS) if f.startswith(cod)], reverse=True)
        if fotos:
            elegida = st.selectbox("Fotos del punto", fotos)
            st.image(os.path.join(CARPETA_FOTOS, elegida), width="stretch")
        else:
            st.info("Este punto aún no tiene fotos. Se agregan al registrar una inspección.")


# ------------------------------------------------------------------
# PANTALLA 3: REGISTRAR INSPECCIÓN
# ------------------------------------------------------------------
elif pantalla == "Registrar inspección":
    st.title("Registrar inspección · Zona 1")
    hist = completo["historial"]
    ult_h = hist["Horas (h)"].max()
    ult_f = hist["Fecha"].max().date()
    st.caption(f"Última inspección registrada: {ult_f:%d-%b-%Y} con {ult_h:,.1f} h")

    c1, c2, c3 = st.columns(3)
    fecha = c1.date_input("Fecha", value=date.today(), min_value=ult_f)
    horas = c2.number_input("Horas del equipo (horómetro)", min_value=0.0, value=float(ult_h), step=10.0, format="%.1f")
    inspector = c3.selectbox("Inspector", sorted(hist["Inspector"].unique()) + ["Otro"])
    if inspector == "Otro":
        inspector = c3.text_input("Código del inspector", placeholder="INSP-04")

    puntos = completo["puntos"]
    ultimos = completo["resumen"].set_index("Código")
    mediciones, fotos_subidas = [], {}
    for _, p in puntos.iterrows():
        cod = p["Código"]
        with st.container(border=True):
            a, b, c, e = st.columns([2.2, 1.4, 1.2, 2.2])
            a.markdown(f"**{cod}** · {p['Descripción']}  \nCaution {p['Caution (mm)']} · Danger {p['Danger (mm)']} · "
                       f"anterior válida: {ultimos.loc[cod, 'L válida (mm)']:.0f} mm")
            no_insp = c.checkbox("No inspeccionado", key=f"ni_{cod}")
            reparado = c.checkbox("Reparado", key=f"rep_{cod}")
            L = b.number_input("L actual (mm)", min_value=0.0, step=5.0, key=f"L_{cod}", disabled=no_insp)
            if not no_insp:
                b.markdown(etiqueta(motor.estado_por_longitud(L, p["Caution (mm)"], p["Danger (mm)"])),
                           unsafe_allow_html=True)
            comentario = e.text_input("Comentario", key=f"c_{cod}")
            foto = e.file_uploader("Foto", type=["jpg", "jpeg", "png"], key=f"f_{cod}", label_visibility="collapsed")
            if foto is not None:
                fotos_subidas[cod] = foto
            mediciones.append({"codigo": cod, "L": None if no_insp else float(L),
                               "reparado": reparado, "comentario": comentario})

    if st.button("💾 Guardar inspección", type="primary"):
        errores = []
        if horas <= ult_h:
            errores.append(f"Las horas deben ser mayores que las de la última inspección ({ult_h:,.1f} h).")
        if not inspector:
            errores.append("Escribe el código del inspector.")
        if errores:
            for e in errores:
                st.error(e)
        else:
            try:
                motor.registrar_inspeccion(EXCEL, fecha, horas, inspector, mediciones)
                for cod, foto in fotos_subidas.items():
                    ext = os.path.splitext(foto.name)[1].lower()
                    with open(os.path.join(CARPETA_FOTOS, f"{cod}_{fecha:%Y-%m-%d}{ext}"), "wb") as f:
                        f.write(foto.getbuffer())
                st.cache_data.clear()
                st.success("Inspección guardada en el Excel y reportes actualizados.")
                st.balloons()
            except PermissionError:
                st.error("No pude guardar: el Excel está abierto. Ciérralo y vuelve a intentar.")


# ------------------------------------------------------------------
# PANTALLA 4: ALERTAS Y REPORTES
# ------------------------------------------------------------------
else:
    st.title("Alertas y reportes")
    st.caption(f"Avisos a la inspección del {ver_fecha:%d-%b-%Y}")

    colores = {"Crítico": "#d03b3b", "Crece muy rápido": "#d03b3b", "Alerta": "#e8a317",
               "Verificar en campo": "#7a5cc7", "Reparación repetida": "#1f3864"}
    if al.empty:
        st.success("No hay avisos activos.")
    for _, a in al.iterrows():
        color = colores.get(a["Tipo"], "#888")
        st.markdown(
            f'<div class="tarjeta" style="border-left: 6px solid {color}">'
            f'<span class="etiqueta" style="background:{color}">{a["Tipo"]}</span> '
            f'<b>{a["Código"]}</b> · prioridad {a["Prioridad"].lower()}<br>{a["Detalle"]}</div>',
            unsafe_allow_html=True)

    st.subheader("Reparaciones registradas")
    rep = R["reparaciones"].copy()
    rep["Fecha"] = rep["Fecha"].dt.strftime("%d-%b-%Y")
    st.dataframe(rep, hide_index=True, width="stretch")

    st.subheader("Reporte por punto")
    st.dataframe(res.drop(columns=["Última fecha"]), hide_index=True, width="stretch")

    st.divider()
    st.markdown("Escribe en el Excel las hojas **Analisis_Zona1**, **Reparaciones**, **Alertas** y **Reporte** "
                "con el estado más reciente. Antes de guardar se crea una copia en la carpeta *datos/respaldos*.")
    if st.button("📊 Actualizar reportes en el Excel", type="primary"):
        try:
            motor.actualizar_reportes(EXCEL)
            st.cache_data.clear()
            st.success(f"Reportes actualizados en {EXCEL}")
        except PermissionError:
            st.error("No pude guardar: el Excel está abierto. Ciérralo y vuelve a intentar.")
