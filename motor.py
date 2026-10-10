"""
MOTOR DE CÁLCULO
Aquí vive toda la lógica. La interfaz (app.py) solo muestra lo que este archivo calcula.

Reglas acordadas:
- Solo se analiza la Zona 1 (Chasis – viga derecha, puntos VD-01 a VD-04).
- Datos dudosos: se marcan, se excluyen del análisis y generan aviso de verificar en campo.
- Tolerancia de medición: una grieta puede "bajar" hasta 20 mm sin reparación (error normal de medida).
- Cada reparación corta la tendencia y empieza un tramo nuevo. Se cuentan las reparaciones por punto.
- "Crece muy rápido": a su velocidad actual, la grieta pasaría su siguiente límite
  (Caution o Danger) antes de la próxima inspección.
"""
import os
import shutil
from datetime import datetime

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment

# ------------------------------------------------------------------
# PARÁMETROS (se pueden ajustar sin tocar el resto del código)
# ------------------------------------------------------------------
ZONA = "Chasis – viga derecha"
PREFIJO_ZONA = "VD"
TOLERANCIA_MM = 20          # bajada aceptada sin reparación
FACTOR_IMPOSIBLE = 2        # L mayor que 2 x Danger se considera imposible
FACTOR_ANOMALO = 4          # crecer 4 veces más rápido que lo habitual es sospechoso
SALTO_MINIMO_MM = 100       # ...pero solo si el salto es de al menos 100 mm
REPARACIONES_ALERTA = 2     # a partir de 2 reparaciones se avisa

HOJAS_GENERADAS = ["Analisis_Zona1", "Reparaciones", "Alertas", "Reporte"]

ESTADO_COLOR = {
    "Normal": "#1f9d55",
    "Alerta": "#e8a317",
    "Crítico": "#d03b3b",
    "Por verificar": "#7a5cc7",
    "N/I": "#9a9a95",
}


# ------------------------------------------------------------------
# 1. LECTURA
# ------------------------------------------------------------------
def cargar(ruta_excel):
    """Lee el Excel y devuelve (historial de la zona 1, tabla de puntos de la zona 1)."""
    hist = pd.read_excel(ruta_excel, sheet_name="Historial")
    puntos = pd.read_excel(ruta_excel, sheet_name="Puntos")

    hist = hist[hist["Código"].astype(str).str.startswith(PREFIJO_ZONA)].copy()
    puntos = puntos[puntos["Código"].astype(str).str.startswith(PREFIJO_ZONA)].copy()

    hist["Fecha"] = pd.to_datetime(hist["Fecha"])
    hist["Comentario"] = hist["Comentario"].fillna("").astype(str)
    hist = hist.sort_values(["Código", "Horas (h)"]).reset_index(drop=True)
    return hist, puntos.reset_index(drop=True)


def estado_por_longitud(L, caution, danger):
    if pd.isna(L):
        return "N/I"
    if L >= danger:
        return "Crítico"
    if L >= caution:
        return "Alerta"
    return "Normal"


def es_reparacion(comentario):
    return "repar" in str(comentario).lower()


# ------------------------------------------------------------------
# 2. ANÁLISIS POR PUNTO (calidad, tramos, reparaciones, velocidad)
# ------------------------------------------------------------------
def analizar(hist, puntos):
    """
    Recorre cada punto en orden de horas y le pone a cada medición:
    Calidad (OK / Variación menor / Confirmado / Dudoso / N/I), Motivo, Tramo,
    N° de reparaciones acumuladas, Velocidad (mm/h), Estado y si el aviso sigue Vigente.

    Regla de confirmación: si un salto exagerado se repite en una de las dos inspecciones
    siguientes (valor parecido, +/- CONFIRMA_MM), la grieta es real. Entonces el salto se
    acepta y la medición baja que quedó en medio se marca como dudosa.
    """
    CONFIRMA_MM = 100
    filas = []
    for _, p in puntos.iterrows():
        cod, cau, dan = p["Código"], p["Caution (mm)"], p["Danger (mm)"]
        datos = hist[hist["Código"] == cod].sort_values("Horas (h)")

        tramo, n_rep = 1, 0
        ultimo = None            # última medición válida (L, horas)
        inicio_tramo = None      # primera medición válida del tramo
        vel_tramo_anterior = None
        pendiente = None         # salto exagerado esperando confirmación: (indice_en_filas, L, h, lecturas_desde)
        propias = []             # índices en `filas` de este punto

        for _, r in datos.iterrows():
            L, h = r["L actual (mm)"], r["Horas (h)"]
            calidad, motivo, vel = "OK", "", np.nan

            if pd.isna(L):
                calidad, motivo = "N/I", "No inspeccionado"

            elif es_reparacion(r["Comentario"]):
                if ultimo is not None and inicio_tramo is not None and ultimo[1] > inicio_tramo[1]:
                    vel_tramo_anterior = (ultimo[0] - inicio_tramo[0]) / (ultimo[1] - inicio_tramo[1])
                if ultimo is not None and ultimo[0] > 0:
                    n_rep += 1
                tramo += 1
                motivo = "Reparación: " + r["Comentario"]
                ultimo, inicio_tramo, pendiente = (L, h), (L, h), None

            elif L > FACTOR_IMPOSIBLE * dan or L < 0:
                calidad = "Dudoso"
                motivo = f"Valor imposible ({L:.0f} mm; Danger es {dan:.0f} mm)"

            elif pendiente is not None and abs(L - pendiente[1]) <= CONFIRMA_MM and L > (ultimo[0] if ultimo else 0) + TOLERANCIA_MM:
                # La medición actual confirma el salto que estaba en duda
                i0 = pendiente[0]
                filas[i0].update({"Calidad": "Confirmado", "Vigente": "",
                                  "Motivo": f"Salto confirmado por la inspección del {r['Fecha']:%d-%b-%Y}",
                                  "Estado": estado_por_longitud(pendiente[1], cau, dan)})
                prev = pendiente[4]
                if prev is not None and pendiente[2] > prev[1]:
                    filas[i0]["Velocidad (mm/h)"] = (pendiente[1] - prev[0]) / (pendiente[2] - prev[1])
                for j in propias:
                    if filas[j]["Horas (h)"] > pendiente[2] and filas[j]["Calidad"] in ("OK", "Variación menor"):
                        filas[j].update({"Calidad": "Dudoso", "Estado": "Por verificar", "Velocidad (mm/h)": np.nan,
                                         "Motivo": "Contradice las mediciones de antes y después (posible error de anotación)"})
                calidad = "Confirmado"
                motivo = f"Confirma la medición del {filas[i0]['Fecha']:%d-%b-%Y} ({pendiente[1]:.0f} mm)"
                if h > pendiente[2]:
                    vel = max((L - pendiente[1]) / (h - pendiente[2]), 0.0)
                ultimo, pendiente = (L, h), None

            elif ultimo is not None and L < ultimo[0] - TOLERANCIA_MM:
                calidad = "Dudoso"
                motivo = f"Bajó de {ultimo[0]:.0f} a {L:.0f} mm sin reparación registrada"

            else:
                if ultimo is not None and h > ultimo[1]:
                    vel = (L - ultimo[0]) / (h - ultimo[1])
                ref = None
                if inicio_tramo is not None and ultimo is not None and ultimo[1] > inicio_tramo[1] \
                        and ultimo[0] > inicio_tramo[0]:
                    ref = (ultimo[0] - inicio_tramo[0]) / (ultimo[1] - inicio_tramo[1])
                elif vel_tramo_anterior and vel_tramo_anterior > 0:
                    ref = vel_tramo_anterior

                salto = L - ultimo[0] if ultimo is not None else 0
                if ref and not pd.isna(vel) and vel > FACTOR_ANOMALO * ref and salto >= SALTO_MINIMO_MM:
                    calidad = "Dudoso"
                    motivo = (f"Creció {salto:.0f} mm a {vel:.2f} mm/h, "
                              f"{vel / ref:.0f} veces más rápido de lo habitual ({ref:.3f} mm/h)")
                    vel = np.nan
                    pendiente = (len(filas), L, h, 0, ultimo)
                elif ultimo is not None and L < ultimo[0]:
                    calidad = "Variación menor"
                    motivo = f"Bajó {ultimo[0] - L:.0f} mm (dentro de la tolerancia de {TOLERANCIA_MM} mm)"

                if calidad != "Dudoso":
                    if inicio_tramo is None:
                        inicio_tramo = (L, h)
                    ultimo = (L, h)

            # El salto en duda solo espera confirmación durante 2 inspecciones
            if pendiente is not None and pendiente[0] != len(filas) and not pd.isna(L):
                pendiente = pendiente[:3] + (pendiente[3] + 1, pendiente[4])
                if pendiente[3] > 2:
                    pendiente = None

            estado = "Por verificar" if calidad == "Dudoso" else estado_por_longitud(L, cau, dan)
            propias.append(len(filas))
            filas.append({
                "Fecha": r["Fecha"], "Horas (h)": h, "Inspector": r["Inspector"],
                "Código": cod, "Descripción": r["Descripción"], "L actual (mm)": L,
                "Caution (mm)": cau, "Danger (mm)": dan, "Estado": estado,
                "Calidad": calidad, "Motivo": motivo, "Tramo": tramo,
                "Reparaciones acumuladas": n_rep, "Velocidad (mm/h)": vel,
                "Comentario": r["Comentario"], "Imagen": r.get("Imagen", ""),
            })

        # ¿El aviso de un dato dudoso sigue vigente? Solo si no hubo reparación después.
        ultima_rep = max([filas[j]["Horas (h)"] for j in propias if filas[j]["Motivo"].startswith("Reparación")],
                         default=-1)
        for j in propias:
            if filas[j]["Calidad"] == "Dudoso":
                filas[j]["Vigente"] = "Sí" if filas[j]["Horas (h)"] > ultima_rep else "No (punto reparado después)"
            else:
                filas[j]["Vigente"] = ""
    return pd.DataFrame(filas)


# ------------------------------------------------------------------
# 3. RESUMEN POR PUNTO (estado actual, velocidad, proyección)
# ------------------------------------------------------------------
def intervalo_inspeccion(hist):
    """Horas típicas entre inspecciones (mediana)."""
    h = np.sort(hist["Horas (h)"].unique())
    return float(np.median(np.diff(h))) if len(h) > 1 else 500.0


def resumen(analisis, puntos, intervalo):
    filas = []
    for _, p in puntos.iterrows():
        cod, cau, dan = p["Código"], p["Caution (mm)"], p["Danger (mm)"]
        d = analisis[analisis["Código"] == cod].sort_values("Horas (h)")
        if d.empty:
            continue
        validas = d[d["Calidad"].isin(["OK", "Variación menor", "Confirmado"])]
        ultima = d.iloc[-1]

        if validas.empty:
            continue
        uv = validas.iloc[-1]
        tramo_actual = validas[validas["Tramo"] == uv["Tramo"]]

        # Velocidad: pendiente de una recta ajustada a las mediciones válidas del tramo actual
        vel = np.nan
        if len(tramo_actual) >= 2 and tramo_actual["Horas (h)"].nunique() >= 2:
            vel = float(np.polyfit(tramo_actual["Horas (h)"], tramo_actual["L actual (mm)"], 1)[0])
            vel = max(vel, 0.0)

        L = uv["L actual (mm)"]
        estado = estado_por_longitud(L, cau, dan)
        if ultima["Calidad"] == "Dudoso":
            estado = "Por verificar"

        siguiente = cau if L < cau else (dan if L < dan else None)
        horas_limite = np.nan
        if siguiente is not None and vel and vel > 0:
            horas_limite = (siguiente - L) / vel
        rapido = bool(not np.isnan(horas_limite) and horas_limite < intervalo)

        filas.append({
            "Código": cod, "Descripción": p["Descripción"],
            "Caution (mm)": cau, "Danger (mm)": dan,
            "Última fecha": ultima["Fecha"], "Últimas horas": ultima["Horas (h)"],
            "Último valor medido (mm)": ultima["L actual (mm)"],
            "L válida (mm)": L, "Estado": estado,
            "Velocidad (mm/h)": round(vel, 4) if not np.isnan(vel) else np.nan,
            "Siguiente límite": ("Caution" if siguiente == cau else "Danger") if siguiente else "Ya pasó Danger",
            "Horas hasta el límite": round(horas_limite) if not np.isnan(horas_limite) else np.nan,
            "Crece muy rápido": "Sí" if rapido else "No",
            "Reparaciones": int(d["Reparaciones acumuladas"].max()),
        })
    return pd.DataFrame(filas)


# ------------------------------------------------------------------
# 4. ALERTAS
# ------------------------------------------------------------------
def alertas(analisis, res, intervalo):
    a = []
    # Estado actual de cada punto
    for _, r in res.iterrows():
        if r["Estado"] == "Crítico":
            a.append(("Alta", "Crítico", r["Código"],
                      f"Mide {r['L válida (mm)']:.0f} mm y su Danger es {r['Danger (mm)']:.0f} mm. "
                      f"Reparar antes de seguir operando."))
        elif r["Estado"] == "Alerta":
            a.append(("Media", "Alerta", r["Código"],
                      f"Mide {r['L válida (mm)']:.0f} mm (Caution {r['Caution (mm)']:.0f}). "
                      f"Aumentar frecuencia de inspección y programar reparación."))
        if r["Crece muy rápido"] == "Sí":
            a.append(("Alta", "Crece muy rápido", r["Código"],
                      f"A {r['Velocidad (mm/h)']:.3f} mm/h llegaría a {r['Siguiente límite']} en unas "
                      f"{r['Horas hasta el límite']:.0f} h, antes de la próxima inspección (~{intervalo:.0f} h)."))
        if r["Reparaciones"] >= REPARACIONES_ALERTA:
            a.append(("Media", "Reparación repetida", r["Código"],
                      f"Lleva {r['Reparaciones']} reparaciones. El material soldado varias veces se debilita: "
                      f"considerar evaluación de ingeniería o refuerzo."))

    # Datos dudosos -> verificar en campo
    for _, d in analisis[(analisis["Calidad"] == "Dudoso") & (analisis["Vigente"] == "Sí")].iterrows():
        prioridad = "Alta" if d["L actual (mm)"] >= d["Danger (mm)"] else "Media"
        extra = " Si el valor es real, el punto estaría en Crítico." if prioridad == "Alta" else ""
        a.append((prioridad, "Verificar en campo", d["Código"],
                  f"{d['Fecha']:%d-%b-%Y}: {d['Motivo']}. Excluido del análisis.{extra}"))

    df = pd.DataFrame(a, columns=["Prioridad", "Tipo", "Código", "Detalle"])
    if not df.empty:
        df["orden"] = df["Prioridad"].map({"Alta": 0, "Media": 1})
        df = df.sort_values(["orden", "Código"]).drop(columns="orden").reset_index(drop=True)
    return df


def reparaciones(analisis):
    r = analisis[analisis["Motivo"].str.startswith("Reparación")].copy()
    r = r[r["Reparaciones acumuladas"] > 0]
    r = r.drop_duplicates(["Código", "Reparaciones acumuladas"])
    return r[["Código", "Fecha", "Horas (h)", "Reparaciones acumuladas", "Comentario"]].rename(
        columns={"Reparaciones acumuladas": "N° de reparación"})


# ------------------------------------------------------------------
# 5. TODO JUNTO (con opción de ver el estado "a una fecha")
# ------------------------------------------------------------------
def calcular_todo(ruta_excel, hasta=None):
    hist, puntos = cargar(ruta_excel)
    if hasta is not None:
        hist = hist[hist["Fecha"] <= pd.Timestamp(hasta)]
    intervalo = intervalo_inspeccion(hist)
    an = analizar(hist, puntos)
    res = resumen(an, puntos, intervalo)
    al = alertas(an, res, intervalo)
    rep = reparaciones(an)
    return {"historial": hist, "puntos": puntos, "analisis": an, "resumen": res,
            "alertas": al, "reparaciones": rep, "intervalo": intervalo}


# ------------------------------------------------------------------
# 6. ESCRITURA EN EL EXCEL (backend)
# ------------------------------------------------------------------
def respaldar(ruta_excel):
    carpeta = os.path.join(os.path.dirname(os.path.abspath(ruta_excel)), "respaldos")
    os.makedirs(carpeta, exist_ok=True)
    nombre = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + os.path.basename(ruta_excel)
    shutil.copy2(ruta_excel, os.path.join(carpeta, nombre))


def _escribir_hoja(wb, nombre, df):
    if nombre in wb.sheetnames:
        del wb[nombre]
    ws = wb.create_sheet(nombre)
    ws.append(list(df.columns))
    for fila in df.itertuples(index=False):
        valores = []
        for v in fila:
            if isinstance(v, pd.Timestamp):
                v = v.to_pydatetime()
            elif isinstance(v, float) and np.isnan(v):
                v = None
            elif isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = float(v)
            valores.append(v)
        ws.append(valores)
    cab = PatternFill("solid", fgColor="1F3864")
    for c in ws[1]:
        c.font = Font(name="Arial", bold=True, color="FFFFFF")
        c.fill = cab
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for fila in ws.iter_rows(min_row=2):
        for c in fila:
            c.font = Font(name="Arial")
            if isinstance(c.value, datetime):
                c.number_format = "dd-mmm-yyyy"
    for col in ws.columns:
        ancho = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, ancho + 2), 70)
    ws.freeze_panes = "A2"


def actualizar_reportes(ruta_excel, hacer_respaldo=True):
    """Recalcula todo y escribe las hojas de reporte en el mismo Excel."""
    r = calcular_todo(ruta_excel)
    if hacer_respaldo:
        respaldar(ruta_excel)
    wb = load_workbook(ruta_excel)
    _escribir_hoja(wb, "Analisis_Zona1", r["analisis"])
    _escribir_hoja(wb, "Reparaciones", r["reparaciones"])
    _escribir_hoja(wb, "Alertas", r["alertas"])
    rep = r["resumen"].copy()
    rep.insert(0, "Generado", datetime.now().replace(microsecond=0))
    _escribir_hoja(wb, "Reporte", rep)
    wb.save(ruta_excel)
    return r


def registrar_inspeccion(ruta_excel, fecha, horas, inspector, mediciones):
    """
    mediciones: lista de dicts {codigo, L (None si no se inspeccionó), reparado (bool), comentario}
    Agrega las filas al final de la hoja Historial y luego actualiza los reportes.
    """
    _, puntos = cargar(ruta_excel)
    respaldar(ruta_excel)
    wb = load_workbook(ruta_excel)
    ws = wb["Historial"]
    encabezados = [c.value for c in ws[1]]
    equipo = ws.cell(row=2, column=encabezados.index("Equipo") + 1).value or "EH4-01"
    for m in mediciones:
        p = puntos[puntos["Código"] == m["codigo"]].iloc[0]
        comentario = m.get("comentario", "") or ""
        if m.get("reparado"):
            comentario = ("Zona reparada por soldadura. " + comentario).strip()
        fila = {
            "Fecha": datetime.combine(fecha, datetime.min.time()), "Equipo": equipo,
            "Horas (h)": float(horas), "Inspector": inspector, "Zona": p["Zona"],
            "Código": m["codigo"], "Descripción": p["Descripción"],
            "L actual (mm)": m["L"], "Comentario": comentario or None, "Imagen": p.get("Esquema", None),
        }
        ws.append([fila.get(h) for h in encabezados])
        ws.cell(row=ws.max_row, column=1).number_format = "yyyy-mm-dd"
    wb.save(ruta_excel)
    return actualizar_reportes(ruta_excel, hacer_respaldo=False)
