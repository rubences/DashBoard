import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import math
import json
import os
import time
import csv
import sys
import re
import unicodedata
import importlib.util
from datetime import datetime
from io import BytesIO
from pathlib import Path

# ============================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================

st.set_page_config(
    page_title="Dashboard Moto3 Goiânia",
    page_icon="🏍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# CARGA DE DATOS
# ============================================================

TELEMETRY_CSV = "moto3_goiania_telemetry.csv"
TASKS_CSV = "moto3_goiania_tasks.csv"
SETUP_CSV = "moto3_goiania_setup.csv"
STANDARD_CONFIG_XLSX = "Mejora_Hoja_Config_Moto_mejorada.xlsx"
STANDARD_CONFIG_CSV = "Mejora_EXPORT_LONG.csv"
ASPAR_SPEC_CSV = "Spec_Domingo_completed.csv"
PREFS_FILE = Path(".streamlit/ui_prefs.json")

REQUIRED_TELEMETRY_COLUMNS = [
    "sesion", "vuelta", "run", "lap_time_s", "sector_1_s", "sector_2_s", "sector_3_s",
    "velocidad_punta_kmh", "temp_neumatico_right_c", "temp_neumatico_center_c", "temp_neumatico_left_c",
    "presion_front_hot_target_bar", "presion_rear_hot_target_bar", "anti_squat_pct",
    "traction_control_lvl", "engine_brake_lvl", "anti_wheelie_lvl",
    "neumatico_front", "neumatico_rear",
]
REQUIRED_TASKS_COLUMNS = ["sesion", "rol", "tarea", "estado", "prioridad"]
REQUIRED_SETUP_COLUMNS = ["parametro", "valor"]


def missing_columns(df, required_cols):
    return [col for col in required_cols if col not in df.columns]


def paginate_df(df, page, page_size):
    if df.empty:
        return df
    start = (page - 1) * page_size
    end = start + page_size
    return df.iloc[start:end]


def load_ui_prefs():
    if not PREFS_FILE.exists():
        return {}
    try:
        data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_ui_prefs(prefs):
    try:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # Si falla el guardado, la app mantiene el estado en sesión.
        pass


@st.cache_data
def load_data():
    df_telemetry = pd.read_csv(TELEMETRY_CSV)
    df_tasks = pd.read_csv(TASKS_CSV)
    df_setup = pd.read_csv(SETUP_CSV)

    numeric_cols = [
        "presion_front_cold_bar", "presion_rear_cold_bar",
        "presion_front_hot_target_bar", "presion_rear_hot_target_bar",
        "track_temp_c", "air_temp_c", "humidity_pct", "wind_kmh",
        "lap_time_s", "sector_1_s", "sector_2_s", "sector_3_s",
        "velocidad_punta_kmh", "temp_neumatico_right_c",
        "temp_neumatico_center_c", "temp_neumatico_left_c",
        "anti_squat_pct", "wheelbase_delta_mm", "rake_delta_deg",
        "swingarm_pivot_delta_mm", "traction_control_lvl",
        "engine_brake_lvl", "anti_wheelie_lvl"
    ]
    for col in numeric_cols:
        if col in df_telemetry.columns:
            df_telemetry[col] = pd.to_numeric(df_telemetry[col], errors="coerce")

    return df_telemetry, df_tasks, df_setup


@st.cache_data
def load_standard_config_template(path_xlsx=STANDARD_CONFIG_XLSX, path_csv=STANDARD_CONFIG_CSV):
    xlsx_path = Path(path_xlsx)
    csv_path = Path(path_csv)

    if csv_path.exists():
        try:
            df_long = pd.read_csv(csv_path)
        except Exception:
            df_long = pd.DataFrame()
    elif xlsx_path.exists():
        try:
            df_long = pd.read_excel(xlsx_path, sheet_name="EXPORT_LONG")
        except Exception:
            df_long = pd.DataFrame()
    else:
        return pd.DataFrame(), pd.DataFrame()

    if xlsx_path.exists():
        try:
            df_listas = pd.read_excel(xlsx_path, sheet_name="LISTAS")
        except Exception:
            df_listas = pd.DataFrame()
    else:
        df_listas = pd.DataFrame()

    expected_cols = [
        "setting_id", "setting_name", "circuito_fecha", "sesion", "tiempo_vuelta",
        "categoria", "parametro", "valor", "notas",
    ]
    if not df_long.empty:
        for col in expected_cols:
            if col not in df_long.columns:
                df_long[col] = ""
        df_long = df_long[expected_cols].copy()
        for col in ["setting_name", "categoria", "parametro", "valor", "circuito_fecha", "sesion", "notas"]:
            df_long[col] = df_long[col].fillna("").astype(str)

    return df_long, df_listas


@st.cache_data
def load_aspar_spec_long(path=ASPAR_SPEC_CSV):
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return pd.DataFrame()

    setting_cols = [c for c in df.columns if c.upper().startswith("SETTING")]
    if not setting_cols or "section" not in df.columns or "parameter" not in df.columns:
        return pd.DataFrame()

    long_df = df.melt(
        id_vars=["section", "parameter"],
        value_vars=setting_cols,
        var_name="setting_name",
        value_name="valor",
    )
    long_df = long_df.rename(columns={"section": "categoria", "parameter": "parametro"})
    for col in ["setting_name", "categoria", "parametro", "valor"]:
        long_df[col] = long_df[col].fillna("").astype(str)
    return long_df


def normalize_key(text):
    if text is None or pd.isna(text):
        return ""
    txt = str(text).strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return " ".join(txt.split())


def validate_standard_value(parametro, valor):
    """Valida formatos esperables para parámetros comunes del setup estándar."""
    p = normalize_key(parametro)
    v = str(valor).strip()
    if not v:
        return True, ""

    if "presion" in p:
        ok = bool(re.search(r"\d+(\.\d+)?\s*bar", v.lower()))
        return ok, "Esperado formato de presión, ej. 1.65 bar"
    if "sag" in p or "altura" in p or "length" in p or "longitud" in p:
        ok = bool(re.search(r"\d+(\.\d+)?\s*mm", v.lower())) or v.lower() in {"base", "std"}
        return ok, "Esperado formato en mm, ej. 35 mm"
    if "temp" in p:
        ok = bool(re.search(r"\d+(\.\d+)?\s*°?c", v.lower()))
        return ok, "Esperado formato de temperatura, ej. 45 °C"
    if "humedad" in p:
        ok = bool(re.search(r"\d+(\.\d+)?\s*%", v))
        return ok, "Esperado formato porcentaje, ej. 57%"
    if "wind" in p or "viento" in p:
        ok = bool(re.search(r"\d+(\.\d+)?\s*km/?h", v.lower()))
        return ok, "Esperado formato velocidad, ej. 6 km/h"
    if "maps" in p or "tc" in p or "eb" in p or "aw" in p:
        ok = bool(re.search(r"\d+", v)) or v.upper() in {"ON", "OFF", "STD"}
        return ok, "Esperado nivel numérico o estado ON/OFF"

    return True, ""


def build_validation_report(df_long):
    report_rows = []
    for _, row in df_long.iterrows():
        ok, hint = validate_standard_value(row.get("parametro", ""), row.get("valor", ""))
        if not ok:
            report_rows.append(
                {
                    "setting_name": row.get("setting_name", ""),
                    "categoria": row.get("categoria", ""),
                    "parametro": row.get("parametro", ""),
                    "valor": row.get("valor", ""),
                    "sugerencia": hint,
                }
            )
    return pd.DataFrame(report_rows)


df_telemetry, df_tasks, df_setup = load_data()

telemetry_missing = missing_columns(df_telemetry, REQUIRED_TELEMETRY_COLUMNS)
tasks_missing = missing_columns(df_tasks, REQUIRED_TASKS_COLUMNS)
setup_missing = missing_columns(df_setup, REQUIRED_SETUP_COLUMNS)
if telemetry_missing or tasks_missing or setup_missing:
    if telemetry_missing:
        st.error(f"Faltan columnas en telemetría: {', '.join(telemetry_missing)}")
    if tasks_missing:
        st.error(f"Faltan columnas en tareas: {', '.join(tasks_missing)}")
    if setup_missing:
        st.error(f"Faltan columnas en setup: {', '.join(setup_missing)}")
    st.stop()

# ============================================================
# UTILIDADES
# ============================================================

SESIONES_ORDEN = ["FP1", "Practice", "FP2", "Q2", "Race"]


def get_setup_value(param_name, default="N/D"):
    row = df_setup[df_setup["parametro"] == param_name]
    if row.empty:
        return default
    return row.iloc[0]["valor"]


def fmt_num(value, decimals=2, suffix=""):
    if pd.isna(value):
        return f"N/D{suffix}"
    return f"{value:.{decimals}f}{suffix}"


def fmt_delta(current, reference, decimals=3, suffix=""):
    if pd.isna(current) or pd.isna(reference):
        return "N/D"
    return f"{(current - reference):+.{decimals}f}{suffix}"


def session_summary(df_source):
    needed = [
        "sesion", "lap_time_s", "velocidad_punta_kmh", "temp_neumatico_right_c",
        "anti_squat_pct", "presion_rear_hot_target_bar",
    ]
    if any(col not in df_source.columns for col in needed):
        return pd.DataFrame(columns=["sesion", "best_lap", "avg_lap", "vmax", "temp_right", "anti_squat", "p_rear"])
    if df_source.empty:
        return pd.DataFrame(columns=["sesion", "best_lap", "avg_lap", "vmax", "temp_right", "anti_squat", "p_rear"])
    return (
        df_source.groupby("sesion", as_index=False)
        .agg(
            best_lap=("lap_time_s", "min"),
            avg_lap=("lap_time_s", "mean"),
            vmax=("velocidad_punta_kmh", "max"),
            temp_right=("temp_neumatico_right_c", "mean"),
            anti_squat=("anti_squat_pct", "mean"),
            p_rear=("presion_rear_hot_target_bar", "mean"),
        )
    )


INSIGHTS = {
    "Piloto": (
        "Concéntrate en la estabilidad en T1, conservar el flanco derecho del trasero "
        "y modular gas en las primeras vueltas para llegar con tracción al final."
    ),
    "Ingeniero de Pista": (
        "Cruza sectores, velocidad punta, presiones y anti-squat para decidir si el setup "
        "mantiene el equilibrio entre estabilidad en recta y agilidad en el mixto."
    ),
    "Telemétrico": (
        "Prioriza el cruce entre temperatura de pista, presiones dinámicas, temperatura L/C/R "
        "del neumático y mapas electrónicos para validar la correlación con el modelo base."
    ),
    "Jefe de Mecánicos": (
        "Tu foco es operativo: swap de neumáticos, chequeo de torque, estado de suspensiones "
        "y protocolo sin errores entre runs."
    ),
    "Técnico de Neumáticos": (
        "Vigila especialmente el SC1 trasero y el flanco derecho. La clave es mantener presión "
        "legal y evitar sobretemperatura o degradación prematura."
    ),
}

CIRCUIT_POINTS = [
    {"punto": "Meta", "lat": -16.6892, "lon": -49.2359},
    {"punto": "T1", "lat": -16.6881, "lon": -49.2322},
    {"punto": "T2", "lat": -16.6869, "lon": -49.2301},
    {"punto": "T3", "lat": -16.6848, "lon": -49.2295},
    {"punto": "T4", "lat": -16.6824, "lon": -49.2314},
    {"punto": "T5", "lat": -16.6813, "lon": -49.2342},
    {"punto": "T6", "lat": -16.6825, "lon": -49.2372},
    {"punto": "T7", "lat": -16.6849, "lon": -49.2391},
    {"punto": "T8", "lat": -16.6873, "lon": -49.2398},
    {"punto": "T9", "lat": -16.6894, "lon": -49.2383},
    {"punto": "T10", "lat": -16.6901, "lon": -49.2368},
]


def build_circuit_figure(dff_session, color_mode="Tiempo de vuelta", selected_lap=None):
    circuit_df = pd.DataFrame(CIRCUIT_POINTS)
    lat0 = circuit_df["lat"].mean()
    lon0 = circuit_df["lon"].mean()

    # Conversión aproximada lat/lon a metros para representar el trazado en un plano.
    circuit_df["x_m"] = (circuit_df["lon"] - lon0) * 111320 * math.cos(math.radians(lat0))
    circuit_df["y_m"] = (circuit_df["lat"] - lat0) * 110540

    # Cerrar el circuito uniendo último punto con meta.
    closed_df = pd.concat([circuit_df, circuit_df.iloc[[0]]], ignore_index=True)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=closed_df["x_m"],
            y=closed_df["y_m"],
            mode="lines",
            line={"width": 5, "color": "#111827"},
            name="Trazado",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=circuit_df["x_m"],
            y=circuit_df["y_m"],
            mode="markers+text",
            marker={"size": 9, "color": "#ef4444"},
            text=circuit_df["punto"],
            textposition="top center",
            name="Curvas",
            customdata=circuit_df[["lat", "lon"]],
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Lat: %{customdata[0]:.4f}<br>"
                "Lon: %{customdata[1]:.4f}<extra></extra>"
            ),
        )
    )

    if not dff_session.empty:
        laps = dff_session[
            ["vuelta", "lap_time_s", "run", "sector_1_s", "sector_2_s", "sector_3_s"]
        ].dropna(subset=["vuelta", "lap_time_s"]).sort_values("vuelta")
        if not laps.empty:
            idx_series = (
                (laps["vuelta"].rank(method="first") - 1)
                .astype(int)
                .mod(len(circuit_df))
            )
            lap_points = circuit_df.iloc[idx_series.values].copy()
            lap_points["vuelta"] = laps["vuelta"].values
            lap_points["lap_time_s"] = laps["lap_time_s"].values
            lap_points["run"] = laps["run"].astype(str).values
            lap_points["sector_dominante"] = (
                laps[["sector_1_s", "sector_2_s", "sector_3_s"]].idxmax(axis=1)
                .str.replace("_s", "", regex=False)
                .str.replace("_", " ", regex=False)
                .str.upper()
                .values
            )

            marker_cfg = {
                "size": 12,
                "line": {"width": 1, "color": "#ffffff"},
            }
            if color_mode == "Tiempo de vuelta":
                marker_cfg["color"] = lap_points["lap_time_s"]
                marker_cfg["colorscale"] = "Viridis"
                marker_cfg["showscale"] = True
                marker_cfg["colorbar"] = {"title": "Lap (s)"}
            elif color_mode == "Run":
                run_colors = {
                    "Run 1": "#2563eb",
                    "Run 2": "#16a34a",
                    "Run 3": "#ea580c",
                    "Run 4": "#9333ea",
                }
                marker_cfg["color"] = [run_colors.get(run_name, "#64748b") for run_name in lap_points["run"]]
            else:
                sector_colors = {
                    "SECTOR 1": "#ef4444",
                    "SECTOR 2": "#f59e0b",
                    "SECTOR 3": "#10b981",
                }
                marker_cfg["color"] = [
                    sector_colors.get(sector_name, "#64748b")
                    for sector_name in lap_points["sector_dominante"]
                ]

            fig.add_trace(
                go.Scatter(
                    x=lap_points["x_m"],
                    y=lap_points["y_m"],
                    mode="markers",
                    marker=marker_cfg,
                    name="Vueltas",
                    hovertemplate=(
                        "Vuelta %{customdata[0]}<br>"
                        "Tiempo: %{customdata[1]:.2f}s<br>"
                        "Run: %{customdata[2]}<br>"
                        "Sector dominante: %{customdata[3]}<extra></extra>"
                    ),
                    customdata=lap_points[["vuelta", "lap_time_s", "run", "sector_dominante"]],
                )
            )

            if selected_lap is not None:
                selected_df = lap_points[lap_points["vuelta"] == selected_lap]
                if not selected_df.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=selected_df["x_m"],
                            y=selected_df["y_m"],
                            mode="markers+text",
                            text=[f"V{int(selected_lap)}"],
                            textposition="bottom center",
                            marker={
                                "size": 22,
                                "color": "#111827",
                                "symbol": "star",
                                "line": {"width": 2, "color": "#facc15"},
                            },
                            name="Vuelta seleccionada",
                            hovertemplate="Vuelta seleccionada %{text}<extra></extra>",
                        )
                    )

    fig.update_layout(
        title="Circuito de Goiânia basado en localización",
        template="plotly_white",
        xaxis_title="Eje Este-Oeste (m)",
        yaxis_title="Eje Norte-Sur (m)",
        xaxis={"scaleanchor": "y", "scaleratio": 1},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return fig

# ============================================================
# SIDEBAR — FILTROS
# ============================================================

roles = sorted(df_tasks["rol"].dropna().unique().tolist())
sesiones_disponibles = [s for s in SESIONES_ORDEN if s in df_telemetry["sesion"].unique()]
if not sesiones_disponibles:
    sesiones_disponibles = sorted(df_telemetry["sesion"].dropna().unique().tolist())

if not roles:
    st.error("No hay roles disponibles en el CSV de tareas.")
    st.stop()
if not sesiones_disponibles:
    st.error("No hay sesiones disponibles en el CSV de telemetría.")
    st.stop()

if "_prefs_loaded" not in st.session_state:
    prefs = load_ui_prefs()
    st.session_state.view_mode = prefs.get("view_mode", "Completo") if prefs.get("view_mode") in ["Completo", "Ejecutivo"] else "Completo"
    st.session_state.task_page_size = int(prefs.get("task_page_size", 8)) if isinstance(prefs.get("task_page_size", 8), int) else 8
    st.session_state.telemetry_page_size = int(prefs.get("telemetry_page_size", 10)) if isinstance(prefs.get("telemetry_page_size", 10), int) else 10
    st.session_state.task_page_size = min(max(st.session_state.task_page_size, 5), 30)
    st.session_state.telemetry_page_size = min(max(st.session_state.telemetry_page_size, 5), 30)
    st.session_state.task_page = int(prefs.get("task_page", 1)) if isinstance(prefs.get("task_page", 1), int) else 1
    st.session_state.telemetry_page = int(prefs.get("telemetry_page", 1)) if isinstance(prefs.get("telemetry_page", 1), int) else 1
    st.session_state.task_search = str(prefs.get("task_search", ""))
    st.session_state.task_estados_sel = prefs.get("task_estados_sel", []) if isinstance(prefs.get("task_estados_sel", []), list) else []
    st.session_state.task_prioridades_sel = prefs.get("task_prioridades_sel", []) if isinstance(prefs.get("task_prioridades_sel", []), list) else []
    st.session_state.selected_role = str(prefs.get("selected_role", ""))
    st.session_state.selected_session = str(prefs.get("selected_session", ""))
    st.session_state.selected_compare_session = str(prefs.get("selected_compare_session", "Ninguna"))
    st.session_state.circuit_color_mode = str(prefs.get("circuit_color_mode", "Tiempo de vuelta"))
    st.session_state.selected_lap = prefs.get("selected_lap", None)
    st.session_state._prefs_loaded = True

with st.sidebar:
    st.title("🏍️ Moto3 Goiânia 2026")
    st.markdown("---")

    default_rol = "Ingeniero de Pista" if "Ingeniero de Pista" in roles else roles[0]
    saved_rol = st.session_state.get("selected_role", default_rol)
    if saved_rol not in roles:
        saved_rol = default_rol
    rol = st.selectbox("Rol", roles, index=roles.index(saved_rol))
    st.session_state.selected_role = rol

    default_sesion = "Practice" if "Practice" in sesiones_disponibles else sesiones_disponibles[0]
    saved_sesion = st.session_state.get("selected_session", default_sesion)
    if saved_sesion not in sesiones_disponibles:
        saved_sesion = default_sesion
    sesion = st.selectbox(
        "Sesión",
        sesiones_disponibles,
        index=sesiones_disponibles.index(saved_sesion)
    )
    st.session_state.selected_session = sesion

    compare_options = ["Ninguna"] + [s for s in sesiones_disponibles if s != sesion]
    saved_compare = st.session_state.get("selected_compare_session", "Ninguna")
    if saved_compare not in compare_options:
        saved_compare = "Ninguna"
    compare_session = st.selectbox("Comparar contra", compare_options, index=compare_options.index(saved_compare))
    st.session_state.selected_compare_session = compare_session

    st.markdown("### Modo de vista")
    view_mode = st.radio("Perfil", ["Completo", "Ejecutivo"], key="view_mode")
    task_page_size = st.slider("Filas por página (tareas)", min_value=5, max_value=30, step=1, key="task_page_size")
    telemetry_page_size = st.slider("Filas por página (telemetría)", min_value=5, max_value=30, step=1, key="telemetry_page_size")

    if st.button("Restablecer preferencias", width="stretch"):
        if PREFS_FILE.exists():
            PREFS_FILE.unlink(missing_ok=True)
        st.session_state.clear()
        st.rerun()

    st.markdown("### Interacción del circuito")
    color_options = ["Tiempo de vuelta", "Run", "Sector dominante"]
    saved_color_mode = st.session_state.get("circuit_color_mode", "Tiempo de vuelta")
    if saved_color_mode not in color_options:
        saved_color_mode = "Tiempo de vuelta"
    circuit_color_mode = st.selectbox(
        "Colorear vueltas por",
        color_options,
        index=color_options.index(saved_color_mode),
    )
    st.session_state.circuit_color_mode = circuit_color_mode

    dff_preview = df_telemetry[df_telemetry["sesion"] == sesion].copy()
    available_laps = sorted(dff_preview["vuelta"].dropna().astype(int).unique().tolist())
    selected_lap = None
    if available_laps:
        saved_lap = st.session_state.get("selected_lap", available_laps[0])
        if saved_lap not in available_laps:
            saved_lap = available_laps[0]
        selected_lap = st.select_slider(
            "Resaltar vuelta",
            options=available_laps,
            value=saved_lap,
        )
    st.session_state.selected_lap = selected_lap

    st.markdown("---")
    st.caption("Datos: telemetría, tareas y setup CSV")


# ============================================================
# PESTAÑAS
# ============================================================

tab_goiania, tab_compare, tab_aspar, tab_standard, tab_rag, tab_diagrams, tab_sector = st.tabs([
    "🏁 Goiânia 2026",
    "🚨 ESTÁNDAR vs ASPAR",
    "🏟️ Aspar — Spec Domingo",
    "📘 Estándar Config Moto",
    "🤖 Asistente RAG",
    "📊 Diagramas Pro",
    "📡 Avances 2016-2026",
])

with tab_goiania:
    # ============================================================
    # FILTRADO DE DATOS
    # ============================================================

    dff = df_telemetry[df_telemetry["sesion"] == sesion].copy()
    tff = df_tasks[(df_tasks["sesion"] == sesion) & (df_tasks["rol"] == rol)].copy()
    session_df = session_summary(df_telemetry)

    # KPIs base reutilizados por alertas, comparador y tarjetas.
    best_lap = dff["lap_time_s"].min() if not dff.empty else None
    vmax = dff["velocidad_punta_kmh"].max() if not dff.empty else None
    temp_right = dff["temp_neumatico_right_c"].mean() if not dff.empty else None
    anti_squat = dff["anti_squat_pct"].mean() if not dff.empty else None
    p_rear = dff["presion_rear_hot_target_bar"].mean() if not dff.empty else None

    # ============================================================
    # ENCABEZADO
    # ============================================================

    st.title("Dashboard Moto3 — Goiânia 2026")
    st.markdown(f"**Sesión:** {sesion} &nbsp;|&nbsp; **Rol:** {rol}")
    st.markdown("---")

    # ============================================================
    # ALERTAS AUTOMÁTICAS
    # ============================================================

    st.subheader("🚨 Alertas automáticas")
    alerts = []
    if p_rear is not None and not pd.isna(p_rear) and p_rear < 1.65:
        alerts.append({"tipo": "Crítica", "detalle": "Presión trasera media por debajo de 1.65 bar", "valor": round(p_rear, 3)})
    if temp_right is not None and not pd.isna(temp_right) and temp_right > 95:
        alerts.append({"tipo": "Alerta", "detalle": "Temperatura flanco derecho por encima de 95 °C", "valor": round(temp_right, 2)})
    if anti_squat is not None and not pd.isna(anti_squat) and not (108 <= anti_squat <= 112):
        alerts.append({"tipo": "Alerta", "detalle": "Anti-squat fuera de ventana 108-112%", "valor": round(anti_squat, 2)})

    if not dff.empty and dff["lap_time_s"].notna().sum() > 1:
        lap_std = float(dff["lap_time_s"].std())
        if lap_std > 0.6:
            alerts.append({"tipo": "Info", "detalle": "Variabilidad de vuelta alta (consistencia mejorable)", "valor": round(lap_std, 3)})

    if not alerts:
        st.success("Sin alertas críticas para la sesión seleccionada.")
    else:
        critical_count = len([a for a in alerts if a["tipo"] == "Crítica"])
        if critical_count > 0:
            st.error(f"Se detectaron {critical_count} alertas críticas.")
        st.dataframe(pd.DataFrame(alerts), width="stretch", hide_index=True)

    st.markdown("---")

    # ============================================================
    # COMPARADOR DE SESIONES
    # ============================================================

    st.subheader("📈 Comparador de sesiones")
    if compare_session == "Ninguna":
        st.caption("Selecciona una sesión de referencia en la barra lateral para activar la comparación.")
    else:
        current_row = session_df[session_df["sesion"] == sesion]
        compare_row = session_df[session_df["sesion"] == compare_session]

        if not current_row.empty and not compare_row.empty:
            current = current_row.iloc[0]
            reference = compare_row.iloc[0]

            cmp1, cmp2, cmp3, cmp4 = st.columns(4)
            cmp1.metric("Δ Mejor vuelta (s)", fmt_delta(current["best_lap"], reference["best_lap"], 3))
            cmp2.metric("Δ Velocidad punta (km/h)", fmt_delta(current["vmax"], reference["vmax"], 1))
            cmp3.metric("Δ Temp. der. (°C)", fmt_delta(current["temp_right"], reference["temp_right"], 2))
            cmp4.metric("Δ Presión trasera (bar)", fmt_delta(current["p_rear"], reference["p_rear"], 3))

            cmp_df = pd.DataFrame(
                [
                    {"metric": "Best lap (s)", sesion: current["best_lap"], compare_session: reference["best_lap"]},
                    {"metric": "Avg lap (s)", sesion: current["avg_lap"], compare_session: reference["avg_lap"]},
                    {"metric": "Vmax (km/h)", sesion: current["vmax"], compare_session: reference["vmax"]},
                    {"metric": "Temp right (°C)", sesion: current["temp_right"], compare_session: reference["temp_right"]},
                    {"metric": "Anti-squat (%)", sesion: current["anti_squat"], compare_session: reference["anti_squat"]},
                    {"metric": "Rear pressure (bar)", sesion: current["p_rear"], compare_session: reference["p_rear"]},
                ]
            )
            cmp_plot = cmp_df.melt(id_vars="metric", var_name="sesion", value_name="valor")
            fig_cmp = px.bar(cmp_plot, x="metric", y="valor", color="sesion", barmode="group", title=f"{sesion} vs {compare_session}")
            fig_cmp.update_layout(template="plotly_white", xaxis_title="Métrica", yaxis_title="Valor")
            st.plotly_chart(fig_cmp, width="stretch")
        else:
            st.info("No hay datos suficientes para comparar esas sesiones.")

    st.markdown("---")

    # ============================================================
    # KPI CARDS
    # ============================================================

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    kpi1.metric("⏱️ Mejor vuelta", fmt_num(best_lap, 2, " s"))
    kpi2.metric(
        "🚀 Velocidad punta",
        fmt_num(vmax, 0, " km/h"),
        help=f"Recta principal: {get_setup_value('main_straight_m', '994')} m"
    )
    kpi3.metric(
        "🌡️ Temp. flanco derecho",
        fmt_num(temp_right, 1, " °C"),
        delta="⚠️ Alta" if (temp_right is not None and temp_right > 95) else None,
        delta_color="inverse"
    )
    kpi4.metric(
        "⚙️ Anti-squat",
        fmt_num(anti_squat, 0, " %"),
        delta="En rango" if (anti_squat is not None and 108 <= anti_squat <= 112) else "Fuera de rango",
        delta_color="normal" if (anti_squat is not None and 108 <= anti_squat <= 112) else "inverse"
    )
    kpi5.metric(
        "💨 Presión trasera hot",
        fmt_num(p_rear, 2, " bar"),
        delta="⚠️ Bajo mínimo" if (p_rear is not None and p_rear < 1.65) else None,
        delta_color="inverse",
        help="Mínimo legal Race: 1.65 bar"
    )

    st.markdown("### 🎯 Cumplimiento de objetivos de sesión")
    q1, q2, q3 = st.columns(3)
    target_lap = q1.number_input("Objetivo mejor vuelta (s)", min_value=80.0, max_value=120.0, value=93.0, step=0.1)
    target_vmax = q2.number_input("Objetivo velocidad punta (km/h)", min_value=250.0, max_value=320.0, value=289.0, step=1.0)
    target_temp_max = q3.number_input("Temp. derecha máxima (°C)", min_value=80.0, max_value=120.0, value=95.0, step=1.0)

    c_ok_lap = best_lap is not None and not pd.isna(best_lap) and best_lap <= target_lap
    c_ok_vmax = vmax is not None and not pd.isna(vmax) and vmax >= target_vmax
    c_ok_temp = temp_right is not None and not pd.isna(temp_right) and temp_right <= target_temp_max
    c_ok_anti = anti_squat is not None and not pd.isna(anti_squat) and 108 <= anti_squat <= 112
    c_ok_press = p_rear is not None and not pd.isna(p_rear) and p_rear >= 1.65

    compliance_df = pd.DataFrame(
        [
            {"Control": "Lap time", "Objetivo": f"<= {target_lap:.2f}s", "Actual": fmt_num(best_lap, 2, " s"), "Estado": "✅" if c_ok_lap else "⚠️"},
            {"Control": "Velocidad punta", "Objetivo": f">= {target_vmax:.0f} km/h", "Actual": fmt_num(vmax, 0, " km/h"), "Estado": "✅" if c_ok_vmax else "⚠️"},
            {"Control": "Temp. derecha", "Objetivo": f"<= {target_temp_max:.0f} °C", "Actual": fmt_num(temp_right, 1, " °C"), "Estado": "✅" if c_ok_temp else "⚠️"},
            {"Control": "Anti-squat", "Objetivo": "108%-112%", "Actual": fmt_num(anti_squat, 1, " %"), "Estado": "✅" if c_ok_anti else "⚠️"},
            {"Control": "Presión trasera", "Objetivo": ">= 1.65 bar", "Actual": fmt_num(p_rear, 2, " bar"), "Estado": "✅" if c_ok_press else "⚠️"},
        ]
    )
    pass_rate = (compliance_df["Estado"] == "✅").mean() * 100
    csum1, csum2 = st.columns([1, 3])
    csum1.metric("QA sesión", f"{pass_rate:.0f}%")
    csum2.progress(pass_rate / 100, text=f"Controles en objetivo: {int((compliance_df['Estado'] == '✅').sum())}/{len(compliance_df)}")
    st.dataframe(compliance_df, width="stretch", hide_index=True)

    st.markdown("---")

    # ============================================================
    # GRÁFICOS — FILA 1: Tiempos + Sectores
    # ============================================================

    col_left, col_right = st.columns(2)

    with col_left:
        if not dff.empty:
            fig_lap = px.line(
                dff, x="vuelta", y="lap_time_s", markers=True, color="run",
                title=f"Evolución del tiempo por vuelta — {sesion}"
            )
            fig_lap.update_layout(template="plotly_white", yaxis_title="Tiempo (s)", xaxis_title="Vuelta")
        else:
            fig_lap = go.Figure()
            fig_lap.update_layout(title="Sin datos")
        st.plotly_chart(fig_lap, width='stretch')

    with col_right:
        if not dff.empty:
            sectors_df = dff.melt(
                id_vars=["vuelta", "run"],
                value_vars=["sector_1_s", "sector_2_s", "sector_3_s"],
                var_name="sector", value_name="tiempo"
            )
            fig_sector = px.bar(
                sectors_df, x="vuelta", y="tiempo", color="sector", barmode="group",
                title=f"Sectores por vuelta — {sesion}"
            )
            fig_sector.update_layout(template="plotly_white", yaxis_title="Tiempo (s)", xaxis_title="Vuelta")
        else:
            fig_sector = go.Figure()
            fig_sector.update_layout(title="Sin datos")
        st.plotly_chart(fig_sector, width='stretch')

    # ============================================================
    # GRÁFICOS — FILA 2: Térmico + Presiones
    # ============================================================

    col_left2, col_right2 = st.columns(2)

    with col_left2:
        fig_thermal = go.Figure()
        if not dff.empty:
            fig_thermal.add_trace(go.Scatter(
                x=dff["vuelta"], y=dff["temp_neumatico_right_c"], mode="lines+markers", name="Flanco derecho"
            ))
            fig_thermal.add_trace(go.Scatter(
                x=dff["vuelta"], y=dff["temp_neumatico_center_c"], mode="lines+markers", name="Centro"
            ))
            fig_thermal.add_trace(go.Scatter(
                x=dff["vuelta"], y=dff["temp_neumatico_left_c"], mode="lines+markers", name="Flanco izquierdo"
            ))
        fig_thermal.update_layout(
            title=f"Gradiente térmico del neumático — {sesion}",
            template="plotly_white", xaxis_title="Vuelta", yaxis_title="Temperatura (°C)"
        )
        st.plotly_chart(fig_thermal, width='stretch')

    with col_right2:
        fig_pressure = go.Figure()
        if not dff.empty:
            fig_pressure.add_trace(go.Bar(x=dff["vuelta"], y=dff["presion_front_hot_target_bar"], name="Delantera hot"))
            fig_pressure.add_trace(go.Bar(x=dff["vuelta"], y=dff["presion_rear_hot_target_bar"], name="Trasera hot"))
            fig_pressure.add_hline(y=1.65, line_dash="dash", annotation_text="Mínimo trasero")
        fig_pressure.update_layout(
            title=f"Presiones dinámicas objetivo — {sesion}",
            template="plotly_white", xaxis_title="Vuelta", yaxis_title="Presión (bar)", barmode="group"
        )
        st.plotly_chart(fig_pressure, width='stretch')

    # ============================================================
    # GRÁFICOS — FILA 3: Mapas electrónicos + Compuestos
    # ============================================================
    if view_mode == "Completo":
        col_left3, col_right3 = st.columns(2)

        with col_left3:
            fig_maps = go.Figure()
            if not dff.empty:
                fig_maps.add_trace(go.Scatter(x=dff["vuelta"], y=dff["traction_control_lvl"], mode="lines+markers", name="TC"))
                fig_maps.add_trace(go.Scatter(x=dff["vuelta"], y=dff["engine_brake_lvl"], mode="lines+markers", name="EBC"))
                fig_maps.add_trace(go.Scatter(x=dff["vuelta"], y=dff["anti_wheelie_lvl"], mode="lines+markers", name="AWC"))
            fig_maps.update_layout(
                title=f"Mapas electrónicos por vuelta — {sesion}",
                template="plotly_white", xaxis_title="Vuelta", yaxis_title="Nivel"
            )
            st.plotly_chart(fig_maps, width='stretch')

        with col_right3:
            if not dff.empty:
                compound_df = (
                    dff.groupby(["run", "neumatico_front", "neumatico_rear"], as_index=False)
                    .size()
                    .rename(columns={"size": "conteo"})
                )
                fig_compound = px.bar(
                    compound_df, x="run", y="conteo", color="neumatico_rear",
                    pattern_shape="neumatico_front",
                    title=f"Compuestos por run — {sesion}",
                    hover_data=["neumatico_front", "neumatico_rear"]
                )
                fig_compound.update_layout(template="plotly_white", xaxis_title="Run", yaxis_title="Registros")
            else:
                fig_compound = go.Figure()
                fig_compound.update_layout(title="Sin datos")
            st.plotly_chart(fig_compound, width='stretch')
    else:
        st.caption("Modo Ejecutivo activo: se ocultan gráficos secundarios (mapas y compuestos) para una lectura más rápida.")

    st.markdown("---")

    # ============================================================
    # ANÁLISIS AVANZADO
    # ============================================================
    if view_mode == "Completo":
        st.subheader("🔬 Análisis avanzado")
        adv1, adv2 = st.columns(2)

        with adv1:
            if not dff.empty:
                fig_scatter = px.scatter(
                    dff,
                    x="temp_neumatico_right_c",
                    y="lap_time_s",
                    color="run",
                    size="velocidad_punta_kmh",
                    hover_data=["vuelta", "sector_1_s", "sector_2_s", "sector_3_s"],
                    title="Relación temperatura derecha vs tiempo de vuelta",
                )
                fig_scatter.update_layout(template="plotly_white", xaxis_title="Temp flanco derecho (°C)", yaxis_title="Lap time (s)")
            else:
                fig_scatter = go.Figure()
                fig_scatter.update_layout(title="Sin datos")
            st.plotly_chart(fig_scatter, width="stretch")

        with adv2:
            corr_cols = [
                "lap_time_s",
                "velocidad_punta_kmh",
                "temp_neumatico_right_c",
                "presion_rear_hot_target_bar",
                "anti_squat_pct",
                "track_temp_c",
            ]
            available_corr_cols = [col for col in corr_cols if col in dff.columns]
            corr_df = dff[available_corr_cols].dropna() if not dff.empty and available_corr_cols else pd.DataFrame()
            if not corr_df.empty and len(corr_df) > 1:
                fig_corr = px.imshow(
                    corr_df.corr(numeric_only=True),
                    text_auto=True,
                    color_continuous_scale="RdBu",
                    origin="lower",
                    title="Matriz de correlación (sesión)",
                    zmin=-1,
                    zmax=1,
                )
                fig_corr.update_layout(template="plotly_white")
            else:
                fig_corr = go.Figure()
                fig_corr.update_layout(title="Sin datos suficientes para correlación")
            st.plotly_chart(fig_corr, width="stretch")

        hist_df = dff[["lap_time_s", "run"]].dropna() if not dff.empty else pd.DataFrame()
        if not hist_df.empty:
            fig_hist = px.histogram(
                hist_df,
                x="lap_time_s",
                color="run",
                barmode="overlay",
                nbins=12,
                title="Distribución de tiempos de vuelta por run",
                opacity=0.7,
            )
            fig_hist.update_layout(template="plotly_white", xaxis_title="Lap time (s)", yaxis_title="Frecuencia")
            st.plotly_chart(fig_hist, width="stretch")

    st.markdown("---")

    # ============================================================
    # CIRCUITO POR LOCALIZACIÓN
    # ============================================================

    st.subheader("🗺️ Mapa del circuito por localización")
    circuit_col, context_col = st.columns([2, 1])

    with circuit_col:
        fig_circuit = build_circuit_figure(dff, circuit_color_mode, selected_lap)
        st.plotly_chart(fig_circuit, width='stretch')

    with context_col:
        st.markdown("**Referencia geográfica**")
        st.write("• Trazado aproximado del Autódromo de Goiânia")
        st.write("• Curvas etiquetadas por punto")
        st.write(f"• Color activo: {circuit_color_mode}")
        if selected_lap is not None:
            st.write(f"• Vuelta resaltada: {selected_lap}")
        st.caption("Visual de apoyo para análisis táctico por sesión.")

    st.markdown("---")

    # ============================================================
    # KANBAN OPERATIVO
    # ============================================================

    st.subheader("📋 Kanban operativo por rol")

    todo_tasks = tff[tff["estado"] == "Todo"]["tarea"].tolist()
    progress_tasks = tff[tff["estado"] == "In Progress"]["tarea"].tolist()
    done_tasks = tff[tff["estado"] == "Done"]["tarea"].tolist()

    k1, k2, k3 = st.columns(3)


    def render_kanban_col(container, title, tasks, bg_color):
        items_html = "".join(
            f"<div style='background:white;padding:8px 10px;border-radius:8px;"
            f"margin-top:8px;font-size:13px;box-shadow:0 1px 4px rgba(0,0,0,0.07)'>{t}</div>"
            for t in tasks
        ) if tasks else "<p style='color:#6b7280;font-size:13px;margin-top:8px'>Sin tareas</p>"
        with container:
            st.markdown(
                f"<div style='background:{bg_color};padding:14px;border-radius:12px;min-height:200px'>"
                f"<strong style='font-size:15px'>{title}</strong>{items_html}</div>",
                unsafe_allow_html=True
            )


    render_kanban_col(k1, "🔵 Todo", todo_tasks, "#eef2ff")
    render_kanban_col(k2, "🟠 In Progress", progress_tasks, "#fff7ed")
    render_kanban_col(k3, "🟢 Done", done_tasks, "#ecfdf5")

    st.markdown("### ✅ Lista de tareas operativas")
    if tff.empty:
        st.info("No hay tareas para este rol en la sesión seleccionada.")
    else:
        order_map = {"Alta": 0, "Media": 1, "Baja": 2}
        tasks_table = tff[["tarea", "estado", "prioridad"]].copy()
        tasks_table["_orden"] = tasks_table["prioridad"].map(order_map).fillna(99)
        tasks_table = tasks_table.sort_values(["_orden", "estado", "tarea"]).drop(columns=["_orden"])

        done_count = (tasks_table["estado"] == "Done").sum()
        total_count = len(tasks_table)
        progress = done_count / total_count if total_count else 0

        p1, p2 = st.columns([1, 3])
        p1.metric("Completadas", f"{done_count}/{total_count}")
        p2.progress(progress, text=f"Progreso operativo: {progress * 100:.0f}%")

        st.markdown("**Filtros rápidos de tareas**")
        f1, f2, f3 = st.columns([1, 1, 2])
        estado_opts = sorted(tasks_table["estado"].dropna().unique().tolist())
        prioridad_opts = sorted(tasks_table["prioridad"].dropna().unique().tolist())

        if "task_estados_sel" not in st.session_state:
            st.session_state.task_estados_sel = estado_opts
        if "task_prioridades_sel" not in st.session_state:
            st.session_state.task_prioridades_sel = prioridad_opts

        st.session_state.task_estados_sel = [e for e in st.session_state.task_estados_sel if e in estado_opts]
        st.session_state.task_prioridades_sel = [p for p in st.session_state.task_prioridades_sel if p in prioridad_opts]
        if not st.session_state.task_estados_sel:
            st.session_state.task_estados_sel = estado_opts
        if not st.session_state.task_prioridades_sel:
            st.session_state.task_prioridades_sel = prioridad_opts

        estados_sel = f1.multiselect(
            "Estado",
            options=estado_opts,
            key="task_estados_sel",
        )
        prioridades_sel = f2.multiselect(
            "Prioridad",
            options=prioridad_opts,
            key="task_prioridades_sel",
        )
        search_text = f3.text_input("Buscar tarea", placeholder="Ej: presión, limitador, tracción", key="task_search")

        tasks_filtered = tasks_table[
            tasks_table["estado"].isin(estados_sel) & tasks_table["prioridad"].isin(prioridades_sel)
        ].copy()
        if search_text.strip():
            tasks_filtered = tasks_filtered[
                tasks_filtered["tarea"].str.contains(search_text.strip(), case=False, na=False)
            ]

        total_filtered = len(tasks_filtered)
        task_total_pages = max(1, math.ceil(total_filtered / task_page_size))
        st.session_state.task_page = min(max(int(st.session_state.task_page), 1), task_total_pages)
        pcol1, pcol2 = st.columns([1, 4])
        current_task_page = int(
            pcol1.number_input(
                "Página tareas",
                min_value=1,
                max_value=task_total_pages,
                step=1,
                key="task_page",
            )
        )
        tasks_visible = paginate_df(tasks_filtered, current_task_page, task_page_size)
        start_row = (current_task_page - 1) * task_page_size + (1 if total_filtered > 0 else 0)
        end_row = min(current_task_page * task_page_size, total_filtered)
        pcol2.caption(f"Mostrando {start_row}-{end_row} de {total_filtered} tareas filtradas")

        st.dataframe(tasks_visible, width="stretch", hide_index=True)

        csv_data = tasks_filtered.to_csv(index=False).encode("utf-8")

        resumen_operativo = pd.DataFrame(
            [
                {"campo": "sesion", "valor": sesion},
                {"campo": "rol", "valor": rol},
                {"campo": "total_tareas", "valor": int(total_count)},
                {"campo": "tareas_completadas", "valor": int(done_count)},
                {"campo": "progreso_pct", "valor": round(progress * 100, 2)},
                {"campo": "filtro_estado", "valor": ", ".join(estados_sel)},
                {"campo": "filtro_prioridad", "valor": ", ".join(prioridades_sel)},
                {"campo": "busqueda", "valor": search_text.strip() if search_text.strip() else "(sin filtro)"},
            ]
        )

        kpis_sesion = pd.DataFrame(
            [
                {"kpi": "mejor_vuelta_s", "valor": best_lap},
                {"kpi": "velocidad_punta_kmh", "valor": vmax},
                {"kpi": "temp_flanco_derecho_c", "valor": temp_right},
                {"kpi": "anti_squat_pct", "valor": anti_squat},
                {"kpi": "presion_trasera_hot_bar", "valor": p_rear},
            ]
        )

        xlsx_buffer = BytesIO()
        with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
            tasks_filtered.to_excel(writer, index=False, sheet_name="Tareas_Filtradas")
            resumen_operativo.to_excel(writer, index=False, sheet_name="Resumen_Operativo")
            kpis_sesion.to_excel(writer, index=False, sheet_name="KPIs_Sesion")
        xlsx_data = xlsx_buffer.getvalue()

        d1, d2 = st.columns(2)
        d1.download_button(
            label="Descargar tareas filtradas (CSV)",
            data=csv_data,
            file_name=f"tareas_{sesion}_{rol}.csv".replace(" ", "_"),
            mime="text/csv",
            width="content",
        )
        d2.download_button(
            label="Descargar tareas filtradas (Excel multi-hoja)",
            data=xlsx_data,
            file_name=f"tareas_{sesion}_{rol}.xlsx".replace(" ", "_"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="content",
        )

        st.markdown("**Checklist por estado (solo lectura):**")
        for _, row in tasks_visible.iterrows():
            st.checkbox(
                f"[{row['estado']}] ({row['prioridad']}) {row['tarea']}",
                value=row["estado"] == "Done",
                disabled=True,
            )

    if view_mode == "Completo":
        st.markdown("---")
        st.subheader("🧾 Telemetría detallada (paginada)")
        visible_cols = [
            "sesion", "run", "vuelta", "lap_time_s", "sector_1_s", "sector_2_s", "sector_3_s",
            "velocidad_punta_kmh", "temp_neumatico_right_c", "presion_rear_hot_target_bar", "anti_squat_pct",
        ]
        table_cols = [col for col in visible_cols if col in dff.columns]
        detailed_df = dff[table_cols].sort_values(["vuelta", "run"]) if table_cols else pd.DataFrame()
        if detailed_df.empty:
            st.caption("No hay datos de telemetría para mostrar en tabla.")
        else:
            telem_total = len(detailed_df)
            telem_pages = max(1, math.ceil(telem_total / telemetry_page_size))
            st.session_state.telemetry_page = min(max(int(st.session_state.telemetry_page), 1), telem_pages)
            t1, t2 = st.columns([1, 4])
            current_telem_page = int(
                t1.number_input(
                    "Página telemetría",
                    min_value=1,
                    max_value=telem_pages,
                    step=1,
                    key="telemetry_page",
                )
            )
            telem_visible = paginate_df(detailed_df, current_telem_page, telemetry_page_size)
            start_telem = (current_telem_page - 1) * telemetry_page_size + 1
            end_telem = min(current_telem_page * telemetry_page_size, telem_total)
            t2.caption(f"Mostrando {start_telem}-{end_telem} de {telem_total} registros")
            st.dataframe(telem_visible, width="stretch", hide_index=True)

    st.markdown("---")

    # ============================================================
    # RESUMEN DEL SETUP
    # ============================================================

    st.subheader("🔧 Resumen del setup")

    wheelbase = get_setup_value("wheelbase_delta_mm", dff["wheelbase_delta_mm"].iloc[0] if not dff.empty else "N/D")
    rake = get_setup_value("rake_delta_deg", dff["rake_delta_deg"].iloc[0] if not dff.empty else "N/D")
    anti_min = get_setup_value("anti_squat_target_min_pct", "108")
    anti_max = get_setup_value("anti_squat_target_max_pct", "112")
    swingarm = get_setup_value("swingarm_pivot_delta_mm", dff["swingarm_pivot_delta_mm"].iloc[0] if not dff.empty else "N/D")
    straight = get_setup_value("main_straight_m", "994")
    curves_right = get_setup_value("curves_right", "9")
    curves_left = get_setup_value("curves_left", "5")

    track_temp_mean = dff["track_temp_c"].mean() if not dff.empty else None
    air_temp_mean = dff["air_temp_c"].mean() if not dff.empty else None
    humidity_mean = dff["humidity_pct"].mean() if not dff.empty else None

    setup_s1, setup_s2, setup_s3 = st.columns(3)

    with setup_s1:
        st.markdown("**Geometría**")
        st.write(f"• Wheelbase: +{wheelbase} mm")
        st.write(f"• Rake: {rake}°")
        st.write(f"• Swingarm Pivot: +{swingarm} mm")

    with setup_s2:
        st.markdown("**Anti-squat & Trazado**")
        st.write(f"• Anti-squat objetivo: {anti_min}%–{anti_max}%")
        st.write(f"• Recta principal: {straight} m")
        st.write(f"• Asimetría: {curves_right} derechas / {curves_left} izquierdas")

    with setup_s3:
        st.markdown("**Condiciones medias de sesión**")
        st.write(f"• Track: {fmt_num(track_temp_mean, 1, ' °C')}")
        st.write(f"• Aire: {fmt_num(air_temp_mean, 1, ' °C')}")
        st.write(f"• Humedad: {fmt_num(humidity_mean, 1, '%')}")

    st.markdown("---")

    # ============================================================
    # LECTURA TÁCTICA POR ROL
    # ============================================================

    st.subheader("🎯 Lectura táctica por rol")
    st.info(INSIGHTS.get(rol, "Sin insight disponible para este rol."))

    # Guardado persistente de preferencias entre sesiones locales.
    prefs_to_save = {
        "view_mode": st.session_state.get("view_mode", "Completo"),
        "task_page_size": int(st.session_state.get("task_page_size", 8)),
        "telemetry_page_size": int(st.session_state.get("telemetry_page_size", 10)),
        "task_page": int(st.session_state.get("task_page", 1)),
        "telemetry_page": int(st.session_state.get("telemetry_page", 1)),
        "task_search": st.session_state.get("task_search", ""),
        "task_estados_sel": st.session_state.get("task_estados_sel", []),
        "task_prioridades_sel": st.session_state.get("task_prioridades_sel", []),
        "selected_role": st.session_state.get("selected_role", ""),
        "selected_session": st.session_state.get("selected_session", ""),
        "selected_compare_session": st.session_state.get("selected_compare_session", "Ninguna"),
        "circuit_color_mode": st.session_state.get("circuit_color_mode", "Tiempo de vuelta"),
        "selected_lap": st.session_state.get("selected_lap", None),
    }
    if st.session_state.get("_last_saved_prefs") != prefs_to_save:
        save_ui_prefs(prefs_to_save)
        st.session_state._last_saved_prefs = prefs_to_save

with tab_aspar:
    # ============================================================
    # ASPAR — SPEC DOMINGO
    # ============================================================

    ASPAR_CSV = "Spec_Domingo_completed.csv"

    SECTION_ICONS = {
        "BIKE": "🏍️", "TYRES": "🔴", "FORK": "🔩", "SHOCK": "🔧",
        "GEOMETRY": "📐", "ENGINE": "⚡", "EXT CONDITION": "🌡️",
    }

    SECTION_COLORS = {
        "BIKE": "#1e3a5f", "TYRES": "#7f1d1d", "FORK": "#1e3a5f",
        "SHOCK": "#1e3a5f", "GEOMETRY": "#14532d", "ENGINE": "#3b1278",
        "EXT CONDITION": "#78350f",
    }

    SETTING_NAMES = {
        "SETTING 1": "FP1 Base / Shakedown",
        "SETTING 2": "Practice Hot",
        "SETTING 3": "Q2 Time Attack",
        "SETTING 4": "Race Setup",
        "SETTING 5": "Stability (Long WB)",
        "SETTING 6": "Traction (High AS)",
    }

    @st.cache_data
    def load_aspar_csv():
        df = pd.read_csv(ASPAR_CSV)
        return df

    st.title("🏟️ Aspar — Spec Domingo")
    st.markdown(
        "Comparativo de los **6 settings** registrados durante la prueba en Aspar. "
        "Cada sección cubre una categoría técnica independiente."
    )
    st.markdown("---")

    try:
        aspar_df = load_aspar_csv()
    except FileNotFoundError:
        st.error(f"No se encontró el archivo '{ASPAR_CSV}'.")
        aspar_df = pd.DataFrame()

    if not aspar_df.empty:
        setting_cols = [c for c in aspar_df.columns if c.startswith("SETTING")]
        sections = aspar_df["section"].unique().tolist()

        # ── KPIs rápidos ──────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("⚙️ Settings", len(setting_cols))
        k2.metric("📦 Secciones", len(sections))
        k3.metric("📐 Parámetros", len(aspar_df))

        # Condición más repetida
        if "EXT CONDITION" in aspar_df["section"].values:
            cond_row = aspar_df[(aspar_df["section"] == "EXT CONDITION") & (aspar_df["parameter"] == "Condition")]
            cond_val = cond_row[setting_cols[0]].values[0] if not cond_row.empty else "N/D"
        else:
            cond_val = "N/D"
        k4.metric("🌤️ Condición", cond_val)

        st.markdown("---")

        # ── Temperaturas de pista por setting ─────────────────────
        st.subheader("🌡️ Condiciones externas por setting")
        ext_df = aspar_df[aspar_df["section"] == "EXT CONDITION"].copy()
        if not ext_df.empty:
            ext_pivot = ext_df.set_index("parameter")[setting_cols].T.reset_index()
            ext_pivot.rename(columns={"index": "Setting"}, inplace=True)
            ext_pivot["Setting_Nombre"] = ext_pivot["Setting"].map(SETTING_NAMES)

            ext_cols_display = st.columns(len(setting_cols))
            for col_widget, (_, row) in zip(ext_cols_display, ext_pivot.iterrows()):
                sname = SETTING_NAMES.get(row["Setting"], row["Setting"])
                with col_widget:
                    st.markdown(f"**{row['Setting']}**")
                    st.caption(sname)
                    for param in ["Air Temp", "Asph Temp", "Wind", "Humidity", "Condition"]:
                        if param in ext_df["parameter"].values:
                            val = ext_df[ext_df["parameter"] == param][row["Setting"]].values
                            val_str = val[0] if len(val) > 0 else "N/D"
                            st.write(f"• **{param}:** {val_str}")

        st.markdown("---")

        # ── Neumáticos por setting ─────────────────────────────────
        st.subheader("🔴 Neumáticos por setting")
        tyre_df = aspar_df[aspar_df["section"] == "TYRES"].copy()
        if not tyre_df.empty:
            tyre_pivot = tyre_df.set_index("parameter")[setting_cols].T.reset_index()
            tyre_pivot.rename(columns={"index": "Setting"}, inplace=True)
            tyre_pivot.insert(1, "Nombre", tyre_pivot["Setting"].map(SETTING_NAMES))

            st.dataframe(tyre_pivot, use_container_width=True, hide_index=True)

            # Gráfico de compuestos
            compound_rows = []
            for s_col in setting_cols:
                f_type_row = tyre_df[tyre_df["parameter"] == "F Type"]
                r_type_row = tyre_df[tyre_df["parameter"] == "R Type"]
                f_type = f_type_row[s_col].values[0] if not f_type_row.empty else "N/D"
                r_type = r_type_row[s_col].values[0] if not r_type_row.empty else "N/D"
                compound_rows.append({
                    "Setting": s_col,
                    "Nombre": SETTING_NAMES.get(s_col, s_col),
                    "Delantero": f_type,
                    "Trasero": r_type,
                })
            compound_df = pd.DataFrame(compound_rows)

            fig_compound = px.bar(
                compound_df.melt(id_vars=["Setting", "Nombre"], value_vars=["Delantero", "Trasero"],
                                  var_name="Eje", value_name="Compuesto"),
                x="Setting", y="Compuesto", color="Eje", barmode="group",
                text="Compuesto",
                title="Compuesto delantero vs trasero por setting",
                hover_data=["Nombre"],
                color_discrete_map={"Delantero": "#3b82f6", "Trasero": "#ef4444"},
            )
            fig_compound.update_traces(textposition="outside")
            fig_compound.update_layout(template="plotly_white", yaxis_title="", xaxis_title="Setting",
                                        yaxis_visible=False)
            st.plotly_chart(fig_compound, use_container_width=True)

        st.markdown("---")

        # ── Suspensión (FORK + SHOCK) ──────────────────────────────
        st.subheader("🔩 Suspensión: horquilla y amortiguador")
        susp_tab1, susp_tab2 = st.tabs(["🔩 Fork", "🔧 Shock"])

        with susp_tab1:
            fork_df = aspar_df[aspar_df["section"] == "FORK"].set_index("parameter")[setting_cols].T.reset_index()
            fork_df.rename(columns={"index": "Setting"}, inplace=True)
            fork_df.insert(1, "Nombre", fork_df["Setting"].map(SETTING_NAMES))
            st.dataframe(fork_df, use_container_width=True, hide_index=True)

            # Gráfico de compression y rebound del fork
            fork_raw = aspar_df[aspar_df["section"] == "FORK"].copy()
            numeric_params_fork = ["Compression", "Rebound", "Preload", "SAG", "Free SAG"]
            fork_numeric = fork_raw[fork_raw["parameter"].isin(numeric_params_fork)].copy()
            if not fork_numeric.empty:
                fork_melt = fork_numeric.melt(
                    id_vars=["parameter"], value_vars=setting_cols,
                    var_name="Setting", value_name="Valor_raw"
                )
                fork_melt["Valor"] = pd.to_numeric(
                    fork_melt["Valor_raw"].str.extract(r"([\d.]+)")[0], errors="coerce"
                )
                fork_melt["Nombre"] = fork_melt["Setting"].map(SETTING_NAMES)
                fig_fork = px.line(
                    fork_melt.dropna(subset=["Valor"]),
                    x="Setting", y="Valor", color="parameter", markers=True,
                    title="Parámetros numéricos de horquilla por setting",
                    hover_data=["Nombre", "Valor_raw"],
                )
                fig_fork.update_layout(template="plotly_white", xaxis_title="Setting", yaxis_title="Valor")
                st.plotly_chart(fig_fork, use_container_width=True)

        with susp_tab2:
            shock_df = aspar_df[aspar_df["section"] == "SHOCK"].set_index("parameter")[setting_cols].T.reset_index()
            shock_df.rename(columns={"index": "Setting"}, inplace=True)
            shock_df.insert(1, "Nombre", shock_df["Setting"].map(SETTING_NAMES))
            st.dataframe(shock_df, use_container_width=True, hide_index=True)

            shock_raw = aspar_df[aspar_df["section"] == "SHOCK"].copy()
            numeric_params_shock = ["Compression", "Rebound", "Preload", "SAG", "Free SAG", "Total Length"]
            shock_numeric = shock_raw[shock_raw["parameter"].isin(numeric_params_shock)].copy()
            if not shock_numeric.empty:
                shock_melt = shock_numeric.melt(
                    id_vars=["parameter"], value_vars=setting_cols,
                    var_name="Setting", value_name="Valor_raw"
                )
                shock_melt["Valor"] = pd.to_numeric(
                    shock_melt["Valor_raw"].str.extract(r"([\d.]+)")[0], errors="coerce"
                )
                shock_melt["Nombre"] = shock_melt["Setting"].map(SETTING_NAMES)
                fig_shock = px.line(
                    shock_melt.dropna(subset=["Valor"]),
                    x="Setting", y="Valor", color="parameter", markers=True,
                    title="Parámetros numéricos de amortiguador por setting",
                    hover_data=["Nombre", "Valor_raw"],
                )
                fig_shock.update_layout(template="plotly_white", xaxis_title="Setting", yaxis_title="Valor")
                st.plotly_chart(fig_shock, use_container_width=True)

        st.markdown("---")

        # ── Geometría ──────────────────────────────────────────────
        st.subheader("📐 Geometría")
        geo_df = aspar_df[aspar_df["section"] == "GEOMETRY"].set_index("parameter")[setting_cols].T.reset_index()
        geo_df.rename(columns={"index": "Setting"}, inplace=True)
        geo_df.insert(1, "Nombre", geo_df["Setting"].map(SETTING_NAMES))
        st.dataframe(geo_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Motor ──────────────────────────────────────────────────
        st.subheader("⚡ Motor")
        eng_df = aspar_df[aspar_df["section"] == "ENGINE"].set_index("parameter")[setting_cols].T.reset_index()
        eng_df.rename(columns={"index": "Setting"}, inplace=True)
        eng_df.insert(1, "Nombre", eng_df["Setting"].map(SETTING_NAMES))
        st.dataframe(eng_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Comparador lateral de dos settings ────────────────────
        st.subheader("🔍 Comparador de settings")
        st.caption("Selecciona dos settings para ver las diferencias parámetro a parámetro.")
        cmp_c1, cmp_c2 = st.columns(2)
        setting_a = cmp_c1.selectbox("Setting A", setting_cols, index=0,
                                      format_func=lambda s: f"{s} — {SETTING_NAMES.get(s, '')}")
        setting_b = cmp_c2.selectbox("Setting B", setting_cols, index=3,
                                      format_func=lambda s: f"{s} — {SETTING_NAMES.get(s, '')}")

        if setting_a != setting_b:
            diff_rows = []
            for _, row in aspar_df.iterrows():
                val_a = row[setting_a]
                val_b = row[setting_b]
                diff = "✅ Igual" if str(val_a).strip() == str(val_b).strip() else "⚠️ Diferente"
                diff_rows.append({
                    "Sección": row["section"],
                    "Parámetro": row["parameter"],
                    setting_a: val_a,
                    setting_b: val_b,
                    "Estado": diff,
                })
            diff_df = pd.DataFrame(diff_rows)
            n_diff = (diff_df["Estado"] == "⚠️ Diferente").sum()
            st.info(f"**{n_diff} parámetros difieren** entre {setting_a} y {setting_b}.")

            only_diff = st.checkbox("Mostrar solo diferencias", value=True)
            if only_diff:
                diff_df = diff_df[diff_df["Estado"] == "⚠️ Diferente"]

            def color_estado(val):
                if val == "⚠️ Diferente":
                    return "background-color: #fef9c3; color: #78350f; font-weight: bold"
                return "color: #15803d"

            st.dataframe(
                diff_df.style.map(color_estado, subset=["Estado"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("Selecciona dos settings distintos para comparar.")

        st.markdown("---")

        # ── Exportar ───────────────────────────────────────────────
        st.subheader("⬇️ Exportar spec completo")
        ec1, ec2 = st.columns(2)

        # CSV
        csv_bytes = aspar_df.to_csv(index=False).encode("utf-8")
        ec1.download_button(
            label="Descargar spec completo (CSV)",
            data=csv_bytes,
            file_name="aspar_spec_domingo.csv",
            mime="text/csv",
        )

        # Excel multi-hoja
        spec_buffer = BytesIO()
        with pd.ExcelWriter(spec_buffer, engine="openpyxl") as writer:
            for sec in sections:
                sec_data = aspar_df[aspar_df["section"] == sec].drop(columns=["section"])
                sec_data.to_excel(writer, index=False, sheet_name=sec[:31])
        ec2.download_button(
            label="Descargar spec completo (Excel multi-hoja)",
            data=spec_buffer.getvalue(),
            file_name="aspar_spec_domingo.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tab_compare:
    st.title("🚨 Comparador Global: Estándar vs Aspar")
    st.markdown(
        "Vista prioritaria para validar desviaciones entre el estándar de configuración y el spec de Aspar. "
        "Úsalo como control rápido antes de exportar setup a un circuito."
    )

    df_standard_long, _ = load_standard_config_template()
    df_aspar_long = load_aspar_spec_long()

    if df_standard_long.empty:
        st.error("No hay estándar cargado. Revisa Mejora_EXPORT_LONG.csv o Mejora_Hoja_Config_Moto_mejorada.xlsx.")
    elif df_aspar_long.empty:
        st.error("No hay spec Aspar cargado. Revisa Spec_Domingo_completed.csv.")
    else:
        standard_comp = df_standard_long[["setting_name", "categoria", "parametro", "valor"]].copy()
        aspar_comp = df_aspar_long[["setting_name", "categoria", "parametro", "valor"]].copy()

        for comp_df in [standard_comp, aspar_comp]:
            comp_df["k_setting"] = comp_df["setting_name"].apply(normalize_key)
            comp_df["k_categoria"] = comp_df["categoria"].apply(normalize_key)
            comp_df["k_parametro"] = comp_df["parametro"].apply(normalize_key)
            comp_df["join_key"] = (
                comp_df["k_setting"] + "|" + comp_df["k_categoria"] + "|" + comp_df["k_parametro"]
            )

        merged = standard_comp.merge(
            aspar_comp,
            on="join_key",
            how="outer",
            suffixes=("_std", "_aspar"),
        )

        merged["setting_name"] = merged["setting_name_std"].fillna(merged["setting_name_aspar"]).fillna("")
        merged["categoria"] = merged["categoria_std"].fillna(merged["categoria_aspar"]).fillna("")
        merged["parametro"] = merged["parametro_std"].fillna(merged["parametro_aspar"]).fillna("")
        merged["valor_std"] = merged["valor_std"].fillna("").astype(str)
        merged["valor_aspar"] = merged["valor_aspar"].fillna("").astype(str)

        def classify_row(row):
            std_val = row["valor_std"].strip()
            asp_val = row["valor_aspar"].strip()
            if std_val and asp_val:
                return "✅ Coincide" if normalize_key(std_val) == normalize_key(asp_val) else "⚠️ Diferente"
            if std_val and not asp_val:
                return "🟦 Solo estándar"
            if asp_val and not std_val:
                return "🟧 Solo Aspar"
            return "(vacío)"

        merged["estado"] = merged.apply(classify_row, axis=1)

        status_order = ["⚠️ Diferente", "🟦 Solo estándar", "🟧 Solo Aspar", "✅ Coincide"]
        c1, c2, c3 = st.columns([2, 2, 2])
        settings_cmp = sorted([s for s in merged["setting_name"].dropna().unique().tolist() if s])
        setting_sel = c1.selectbox("Setting", settings_cmp if settings_cmp else ["SETTING 1"])
        estado_sel = c2.multiselect("Estado", status_order, default=status_order)
        search_cmp = c3.text_input("Buscar parámetro", placeholder="Ej: preload, presión, sag")

        cmp_df = merged[merged["setting_name"] == setting_sel].copy() if settings_cmp else merged.copy()
        cmp_df = cmp_df[cmp_df["estado"].isin(estado_sel)]
        if search_cmp.strip():
            cmp_df = cmp_df[
                cmp_df["parametro"].str.contains(search_cmp.strip(), case=False, na=False)
                | cmp_df["categoria"].str.contains(search_cmp.strip(), case=False, na=False)
            ]

        total_cmp = len(cmp_df)
        diff_count = int((cmp_df["estado"] == "⚠️ Diferente").sum())
        match_count = int((cmp_df["estado"] == "✅ Coincide").sum())
        solo_std = int((cmp_df["estado"] == "🟦 Solo estándar").sum())
        solo_aspar = int((cmp_df["estado"] == "🟧 Solo Aspar").sum())

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🔍 Filas analizadas", total_cmp)
        k2.metric("⚠️ Diferencias", diff_count)
        k3.metric("✅ Coincidencias", match_count)
        k4.metric("🧩 Cobertura", f"{(match_count / total_cmp * 100):.1f}%" if total_cmp else "0.0%")

        pie_df = pd.DataFrame(
            [
                {"estado": "⚠️ Diferente", "count": diff_count},
                {"estado": "✅ Coincide", "count": match_count},
                {"estado": "🟦 Solo estándar", "count": solo_std},
                {"estado": "🟧 Solo Aspar", "count": solo_aspar},
            ]
        )
        pie_df = pie_df[pie_df["count"] > 0]
        if not pie_df.empty:
            fig_state = px.pie(
                pie_df,
                names="estado",
                values="count",
                title=f"Distribución de estados — {setting_sel}",
                color="estado",
                color_discrete_map={
                    "⚠️ Diferente": "#ef4444",
                    "✅ Coincide": "#16a34a",
                    "🟦 Solo estándar": "#2563eb",
                    "🟧 Solo Aspar": "#ea580c",
                },
            )
            st.plotly_chart(fig_state, width="stretch")

        out_cols = ["setting_name", "categoria", "parametro", "valor_std", "valor_aspar", "estado"]
        out_df = cmp_df[out_cols].sort_values(["estado", "categoria", "parametro"])

        cat_diff_df = (
            out_df[out_df["estado"] == "⚠️ Diferente"]
            .groupby("categoria", as_index=False)
            .size()
            .rename(columns={"size": "diferencias"})
            .sort_values("diferencias", ascending=False)
        )
        if not cat_diff_df.empty:
            st.markdown("**Top categorías con más diferencias**")
            fig_cat_diff = px.bar(
                cat_diff_df.head(8),
                x="categoria",
                y="diferencias",
                title=f"Ranking de desviaciones por categoría — {setting_sel}",
                color="diferencias",
                color_continuous_scale="Reds",
            )
            fig_cat_diff.update_layout(template="plotly_white", xaxis_title="Categoría", yaxis_title="Nº diferencias")
            st.plotly_chart(fig_cat_diff, width="stretch")

        st.dataframe(out_df, width="stretch", hide_index=True)

        st.download_button(
            label="Descargar comparación (CSV)",
            data=out_df.to_csv(index=False).encode("utf-8"),
            file_name=f"comparador_estandar_vs_aspar_{setting_sel}.csv".replace(" ", "_"),
            mime="text/csv",
            width="content",
        )

with tab_rag:
    # ============================================================
    # ASISTENTE RAG
    # ============================================================

    st.title("🤖 Asistente documental Moto3 (RAG)")
    st.markdown(
        "Haz preguntas sobre tus CSV/XLSX/DOCX/PDF. "
        "El asistente recupera contexto local de Chroma y responde con fuentes."
    )

    root_path = Path(__file__).resolve().parent
    rag_build_module = None

    def load_module_from_file(module_name, module_path):
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"No se pudo crear el spec para {module_name}.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # rag_chat es imprescindible para consultar. Si falla, detenemos esta pestaña.
    try:
        from rag_agent import rag_chat as rag_chat_module
    except Exception:
        try:
            if str(root_path) not in sys.path:
                sys.path.insert(0, str(root_path))
            rag_chat_path = root_path / "rag_agent" / "rag_chat.py"
            if not rag_chat_path.exists():
                raise FileNotFoundError("No se encontró rag_chat.py en la carpeta rag_agent.")
            rag_chat_module = load_module_from_file("rag_chat_module", rag_chat_path)
        except Exception as exc:
            st.error("No se pudo cargar el módulo de chat RAG. Revisa la carpeta rag_agent y dependencias básicas.")
            st.exception(exc)
            st.stop()

    # rag_build sólo se usa para reconstruir el índice. Si falta alguna dependencia
    # (p.ej. python-docx), dejamos el chat operativo e informamos en el botón.
    try:
        from rag_agent import rag_build as rag_build_module
    except Exception:
        try:
            rag_build_path = root_path / "rag_agent" / "rag_build.py"
            if rag_build_path.exists():
                rag_build_module = load_module_from_file("rag_build_module", rag_build_path)
        except Exception:
            rag_build_module = None

    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    model_options = [
        "Qwen/Qwen2.5-1.5B-Instruct",
        "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    ]
    selected_model = c1.selectbox("Modelo generador", model_options, index=0)
    top_k = int(c2.slider("Top-k recuperación", min_value=2, max_value=8, value=4, step=1))
    max_tokens = int(c3.slider("Máx. tokens", min_value=128, max_value=1024, value=500, step=64))
    fallback_enabled = st.checkbox(
        "Fallback automático al segundo modelo si falla el primero",
        value=True,
    )
    temperature = st.slider("Temperatura", min_value=0.0, max_value=1.0, value=0.2, step=0.05)

    if "rag_last_payload" not in st.session_state:
        st.session_state.rag_last_payload = None

    def append_rag_log(row):
        logs_dir = Path("rag_agent") / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "rag_interactions.csv"
        file_exists = log_file.exists()
        with log_file.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "question",
                    "collection",
                    "requested_model",
                    "used_model",
                    "fallback_used",
                    "top_k",
                    "max_tokens",
                    "temperature",
                    "latency_ms",
                    "answer_chars",
                    "sources_count",
                    "avg_distance",
                    "status",
                    "error",
                ],
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    default_token = st.session_state.get("rag_hf_token", "")
    if not default_token:
        try:
            default_token = st.secrets.get("HF_TOKEN", "")
        except Exception:
            default_token = ""
    if not default_token:
        default_token = os.getenv("HF_TOKEN", "")
    hf_token = st.text_input(
        "HF_TOKEN",
        value=default_token,
        key="rag_hf_token",
        type="password",
        help="Token de Hugging Face para usar InferenceClient",
    )

    st.caption("Tip: puedes definir HF_TOKEN en .streamlit/secrets.toml o variable de entorno para no escribirlo en cada sesión.")

    st.markdown("### Índice vectorial")
    i1, i2, i3 = st.columns(3)
    collection_name = i1.text_input("Colección Chroma", value="moto3_docs")
    chunk_size = int(i2.number_input("Chunk size", min_value=300, max_value=2000, value=900, step=50))
    overlap = int(i3.number_input("Overlap", min_value=50, max_value=400, value=150, step=10))

    rebuild_col, status_col = st.columns([1, 2])
    if rebuild_col.button("Reconstruir índice", width="stretch"):
        with st.spinner("Indexando documentos..."):
            if rag_build_module is None:
                st.session_state["rag_ready"] = False
                st.error(
                    "No se pudo cargar el indexador RAG. En Streamlit Cloud suele ser por dependencia faltante, "
                    "normalmente python-docx. Verifica requirements.txt y redeploy."
                )
            else:
                try:
                    rag_build_module.build_index(
                        collection_name=collection_name,
                        chunk_size=chunk_size,
                        overlap=overlap,
                        rebuild=True,
                    )
                    st.session_state["rag_ready"] = True
                    st.success("Índice reconstruido correctamente.")
                except Exception as exc:
                    st.session_state["rag_ready"] = False
                    st.error(f"Error al indexar: {exc}")

    try:
        exists, backend_name = rag_chat_module.collection_exists(collection_name)
        if exists:
            status_col.success(f"Colección disponible: {collection_name} (backend: {backend_name})")
            st.session_state["rag_ready"] = True
        else:
            status_col.warning("No hay colección creada aún. Pulsa 'Reconstruir índice'.")
    except Exception:
        status_col.warning("No se pudo leer el estado del índice vectorial.")

    st.markdown("---")
    st.markdown("### Chat técnico")

    if "rag_messages" not in st.session_state:
        st.session_state.rag_messages = []

    u1, u2 = st.columns([1, 1])
    if u1.button("🧹 Limpiar chat", width="stretch"):
        st.session_state.rag_messages = []
        st.session_state.rag_last_payload = None
        st.rerun()
    if u2.button("⬇️ Exportar chat (CSV)", width="stretch"):
        if st.session_state.rag_messages:
            chat_export_df = pd.DataFrame(st.session_state.rag_messages)
            st.download_button(
                label="Descargar historial RAG",
                data=chat_export_df.to_csv(index=False).encode("utf-8"),
                file_name="rag_chat_history.csv",
                mime="text/csv",
                width="stretch",
            )

    for msg in st.session_state.rag_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    demo_col1, demo_col2 = st.columns([1, 2])
    if demo_col1.button("Pregunta demo", width="stretch"):
        st.session_state["rag_demo_question"] = "¿Qué setting prioriza tracción y qué cambios aplica en geometría?"
    demo_col2.caption("Atajo de validación: lanza una pregunta de prueba con 1 clic.")

    user_question = st.chat_input("Escribe tu pregunta técnica")
    if not user_question and st.session_state.get("rag_demo_question"):
        user_question = st.session_state.pop("rag_demo_question")

    if user_question:
        st.session_state.rag_messages.append({"role": "user", "content": user_question})
        with st.chat_message("user"):
            st.markdown(user_question)

        with st.chat_message("assistant"):
            if not hf_token:
                msg = "Necesito HF_TOKEN para consultar el modelo remoto de Hugging Face."
                st.warning(msg)
                st.session_state.rag_messages.append({"role": "assistant", "content": msg})
            else:
                with st.spinner("Recuperando contexto y generando respuesta..."):
                    started = time.perf_counter()
                    try:
                        model_chain = [selected_model]
                        if fallback_enabled:
                            for candidate in model_options:
                                if candidate != selected_model:
                                    model_chain.append(candidate)

                        payload = None
                        used_model = selected_model
                        fallback_used = False
                        used_backend = "unknown"
                        last_error = None

                        for idx, model_id in enumerate(model_chain):
                            try:
                                assistant = rag_chat_module.RagAssistant(
                                    collection_name=collection_name,
                                    gen_model=model_id,
                                    hf_token=hf_token,
                                )
                                payload = assistant.answer_with_sources(
                                    question=user_question,
                                    k=top_k,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                )
                                used_model = model_id
                                fallback_used = idx > 0
                                used_backend = payload.get("backend", getattr(assistant, "backend", "unknown"))
                                break
                            except Exception as model_exc:
                                last_error = model_exc
                                continue

                        if payload is None:
                            raise RuntimeError(f"Fallaron todos los modelos configurados: {last_error}")

                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        answer_text = payload["answer"]
                        st.markdown(answer_text)
                        st.caption(f"Backend de recuperación activo: {used_backend}")
                        if fallback_used:
                            st.info(f"Respuesta generada con fallback: {used_model}")

                        sources = payload.get("sources", [])
                        if sources:
                            st.markdown("**Fuentes recuperadas**")
                            for source_item in sources:
                                src = source_item.get("source", "unknown")
                                ch = source_item.get("chunk", "?")
                                sh = source_item.get("sheet", "")
                                dist = source_item.get("distance", None)
                                sheet_txt = f" | hoja: {sh}" if sh else ""
                                dist_txt = f" | distancia: {dist:.4f}" if isinstance(dist, (int, float)) else ""
                                st.markdown(
                                    f"- [Fuente {source_item.get('index', '?')}] {src}{sheet_txt} | chunk {ch}{dist_txt}"
                                )

                        distances = [
                            float(s.get("distance")) for s in sources if isinstance(s.get("distance"), (int, float))
                        ]
                        avg_distance = round(sum(distances) / len(distances), 6) if distances else None

                        st.session_state.rag_last_payload = {
                            "question": user_question,
                            "answer": answer_text,
                            "sources": sources,
                            "requested_model": selected_model,
                            "used_model": used_model,
                            "used_backend": used_backend,
                            "fallback_used": fallback_used,
                            "latency_ms": elapsed_ms,
                            "avg_distance": avg_distance,
                        }

                        append_rag_log(
                            {
                                "timestamp": datetime.utcnow().isoformat(),
                                "question": user_question,
                                "collection": collection_name,
                                "requested_model": selected_model,
                                "used_model": used_model,
                                "used_backend": used_backend,
                                "fallback_used": fallback_used,
                                "top_k": top_k,
                                "max_tokens": max_tokens,
                                "temperature": temperature,
                                "latency_ms": elapsed_ms,
                                "answer_chars": len(answer_text),
                                "sources_count": len(sources),
                                "avg_distance": avg_distance,
                                "status": "ok",
                                "error": "",
                            }
                        )

                        save_text = answer_text
                        if payload.get("source_lines"):
                            save_text += "\n\nFuentes recuperadas:\n" + "\n".join(payload["source_lines"])
                        st.session_state.rag_messages.append({"role": "assistant", "content": save_text})
                    except Exception as exc:
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        err = f"No pude responder: {exc}"
                        st.error(err)
                        st.session_state.rag_messages.append({"role": "assistant", "content": err})
                        append_rag_log(
                            {
                                "timestamp": datetime.utcnow().isoformat(),
                                "question": user_question,
                                "collection": collection_name,
                                "requested_model": selected_model,
                                "used_model": "",
                                "used_backend": "",
                                "fallback_used": False,
                                "top_k": top_k,
                                "max_tokens": max_tokens,
                                "temperature": temperature,
                                "latency_ms": elapsed_ms,
                                "answer_chars": 0,
                                "sources_count": 0,
                                "avg_distance": "",
                                "status": "error",
                                "error": str(exc),
                            }
                        )

    st.markdown("---")
    st.markdown("### Evaluación RAG")

    last_payload = st.session_state.get("rag_last_payload")
    if not last_payload:
        st.caption("Aún no hay una consulta para evaluar. Haz una pregunta en el chat técnico.")
    else:
        sources = last_payload.get("sources", [])
        answer_text = last_payload.get("answer", "")
        citations_in_answer = answer_text.count("[Fuente")
        distances = [
            float(s.get("distance")) for s in sources if isinstance(s.get("distance"), (int, float))
        ]
        avg_distance = (sum(distances) / len(distances)) if distances else None
        max_distance = max(distances) if distances else None

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Fuentes recuperadas", len(sources))
        e2.metric("Citas en respuesta", citations_in_answer)
        e3.metric("Distancia media", f"{avg_distance:.4f}" if avg_distance is not None else "N/D")
        e4.metric("Latencia", f"{last_payload.get('latency_ms', 0)} ms")

        if len(sources) > 0 and citations_in_answer > 0:
            st.success("Respuesta con señales de grounding: hay recuperación y citación explícita.")
        elif len(sources) > 0:
            st.warning("Hay contexto recuperado, pero faltan citas explícitas en el texto de respuesta.")
        else:
            st.error("No hubo recuperación de contexto; la respuesta puede no estar fundamentada.")

        st.caption(
            f"Modelo solicitado: {last_payload.get('requested_model')} | "
            f"Modelo usado: {last_payload.get('used_model')} | "
            f"Backend: {last_payload.get('used_backend', 'unknown')} | "
            f"Fallback: {'sí' if last_payload.get('fallback_used') else 'no'}"
        )

        if sources:
            eval_df = pd.DataFrame(
                [
                    {
                        "fuente": s.get("source", "unknown"),
                        "hoja": s.get("sheet", ""),
                        "chunk": s.get("chunk", "?"),
                        "distancia": s.get("distance", ""),
                    }
                    for s in sources
                ]
            )
            st.dataframe(eval_df, width="stretch", hide_index=True)

        logs_path = Path("rag_agent") / "logs" / "rag_interactions.csv"
        if logs_path.exists():
            st.download_button(
                label="Descargar auditoría RAG (CSV)",
                data=logs_path.read_bytes(),
                file_name="rag_interactions.csv",
                mime="text/csv",
                width="content",
            )

with tab_standard:
    st.title("📘 Estándar de Configuración Moto")
    st.markdown(
        "Base estandarizada para reutilizar setup entre circuitos. "
        "Fuente principal: EXPORT_LONG de Mejora_Hoja_Config_Moto_mejorada.xlsx."
    )

    df_standard_long, df_standard_lists = load_standard_config_template()

    if df_standard_long.empty:
        st.error(
            "No pude cargar la plantilla estándar. Verifica que exista Mejora_Hoja_Config_Moto_mejorada.xlsx "
            "con la hoja EXPORT_LONG."
        )
    else:
        if "standard_working_df" not in st.session_state:
            st.session_state.standard_working_df = df_standard_long.copy()
        if "standard_original_df" not in st.session_state:
            st.session_state.standard_original_df = df_standard_long.copy()

        working_df = st.session_state.standard_working_df.copy()

        settings = sorted([s for s in working_df["setting_name"].unique().tolist() if s])
        categories = sorted([c for c in working_df["categoria"].unique().tolist() if c])
        total_rows = len(working_df)
        filled_rows = int(working_df["valor"].astype(str).str.strip().ne("").sum())
        fill_pct = (filled_rows / total_rows * 100) if total_rows else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("⚙️ Settings estándar", len(settings))
        k2.metric("📦 Categorías", len(categories))
        k3.metric("📐 Parámetros", total_rows)
        k4.metric("✅ Completitud", f"{fill_pct:.1f}%")

        st.markdown("---")

        f1, f2, f3 = st.columns([2, 2, 2])
        selected_categories = f1.multiselect("Filtrar categorías", categories, default=categories)
        selected_settings = f2.multiselect("Filtrar settings", settings, default=settings)
        search_param = f3.text_input("Buscar parámetro", placeholder="Ej: Rebound, Pressure, SAG")

        filtered_standard = working_df[
            working_df["categoria"].isin(selected_categories)
            & working_df["setting_name"].isin(selected_settings)
        ].copy()
        if search_param.strip():
            filtered_standard = filtered_standard[
                filtered_standard["parametro"].str.contains(search_param.strip(), case=False, na=False)
            ]

        pivot_df = pd.pivot_table(
            filtered_standard,
            index=["categoria", "parametro"],
            columns="setting_name",
            values="valor",
            aggfunc="first",
        ).reset_index() if not filtered_standard.empty else pd.DataFrame()

        st.subheader("📋 Matriz estándar por categoría y setting")
        if not pivot_df.empty:
            editable_cols = [c for c in pivot_df.columns if c not in ["categoria", "parametro"]]
            edited_pivot = st.data_editor(
                pivot_df,
                width="stretch",
                hide_index=True,
                disabled=["categoria", "parametro"],
                key="standard_matrix_editor",
            )

            edited_long = edited_pivot.melt(
                id_vars=["categoria", "parametro"],
                value_vars=editable_cols,
                var_name="setting_name",
                value_name="valor_new",
            )
            edited_long["valor_new"] = edited_long["valor_new"].fillna("").astype(str)

            merged_working = working_df.merge(
                edited_long,
                on=["setting_name", "categoria", "parametro"],
                how="left",
            )
            merged_working["valor"] = merged_working["valor_new"].where(
                merged_working["valor_new"].notna(),
                merged_working["valor"],
            )
            merged_working = merged_working.drop(columns=["valor_new"])
            st.session_state.standard_working_df = merged_working
            working_df = merged_working

            # Recalcula visuales con la matriz editada.
            filtered_standard = working_df[
                working_df["categoria"].isin(selected_categories)
                & working_df["setting_name"].isin(selected_settings)
            ].copy()
            if search_param.strip():
                filtered_standard = filtered_standard[
                    filtered_standard["parametro"].str.contains(search_param.strip(), case=False, na=False)
                ]
        else:
            st.dataframe(filtered_standard, width="stretch", hide_index=True)

        comp_by_setting = (
            filtered_standard.assign(filled=filtered_standard["valor"].astype(str).str.strip().ne(""))
            .groupby("setting_name", as_index=False)["filled"]
            .mean()
        ) if not filtered_standard.empty else pd.DataFrame(columns=["setting_name", "filled"])
        if not comp_by_setting.empty:
            comp_by_setting["completitud_pct"] = comp_by_setting["filled"] * 100
            fig_comp = px.bar(
                comp_by_setting,
                x="setting_name",
                y="completitud_pct",
                title="Completitud por setting (actualizada con edición en matriz)",
                color="completitud_pct",
                color_continuous_scale="Blues",
            )
            fig_comp.update_layout(template="plotly_white", xaxis_title="Setting", yaxis_title="% completitud")
            st.plotly_chart(fig_comp, width="stretch")

        validation_df = build_validation_report(filtered_standard)
        v1, v2 = st.columns(2)
        v1.metric("🧪 Validaciones con warning", int(len(validation_df)))
        v2.metric(
            "📊 Calidad de formato",
            f"{(1 - len(validation_df) / max(1, len(filtered_standard))) * 100:.1f}%"
            if len(filtered_standard) > 0 else "100.0%"
        )
        if not validation_df.empty:
            st.warning("Se detectaron formatos mejorables en la matriz (presiones, temperaturas, SAG, etc.).")
            st.dataframe(validation_df, width="stretch", hide_index=True)

        a1, a2 = st.columns(2)
        if a1.button("💾 Guardar cambios en Mejora_EXPORT_LONG.csv", width="stretch"):
            try:
                st.session_state.standard_working_df.to_csv(STANDARD_CONFIG_CSV, index=False)
                st.success("Cambios guardados en Mejora_EXPORT_LONG.csv")
            except Exception as exc:
                st.error(f"No se pudo guardar el CSV: {exc}")

        if a2.button("↺ Resetear matriz (recargar plantilla)", width="stretch"):
            st.session_state.standard_working_df = df_standard_long.copy()
            st.session_state.standard_original_df = df_standard_long.copy()
            st.rerun()

        orig_df = st.session_state.standard_original_df.copy()
        current_df = st.session_state.standard_working_df.copy()
        diff_base = orig_df.merge(
            current_df,
            on=["setting_name", "categoria", "parametro"],
            how="outer",
            suffixes=("_orig", "_curr"),
        )
        diff_base["valor_orig"] = diff_base["valor_orig"].fillna("").astype(str)
        diff_base["valor_curr"] = diff_base["valor_curr"].fillna("").astype(str)
        changes_df = diff_base[diff_base["valor_orig"] != diff_base["valor_curr"]][
            ["setting_name", "categoria", "parametro", "valor_orig", "valor_curr"]
        ].copy()
        st.metric("🧾 Cambios no guardados en sesión", len(changes_df))
        if not changes_df.empty:
            st.dataframe(changes_df, width="stretch", hide_index=True)
            st.download_button(
                label="Descargar diff de cambios (CSV)",
                data=changes_df.to_csv(index=False).encode("utf-8"),
                file_name="estandar_cambios_diff.csv",
                mime="text/csv",
                width="content",
            )

        st.markdown("---")
        st.subheader("🏁 Generador base por circuito")
        g1, g2, g3 = st.columns(3)
        circuito_input = g1.text_input("Circuito / Fecha", value="Circuito - Fecha")
        sesion_input = g2.text_input("Sesión", value="FP1")
        referencia_setting = g3.selectbox("Setting de referencia", settings if settings else ["SETTING 1"])

        export_base = filtered_standard[filtered_standard["setting_name"] == referencia_setting].copy()
        export_base["circuito_fecha"] = circuito_input
        export_base["sesion"] = sesion_input

        if st.button("Generar estándar base", width="content"):
            st.success(
                f"Base estándar creada para {circuito_input} ({sesion_input}) usando {referencia_setting}."
            )

        e1, e2 = st.columns(2)
        e1.download_button(
            label="Descargar estándar filtrado (CSV)",
            data=filtered_standard.to_csv(index=False).encode("utf-8"),
            file_name="estandar_config_moto_filtrado.csv",
            mime="text/csv",
            width="content",
        )
        e2.download_button(
            label="Descargar estándar base circuito (CSV)",
            data=export_base.to_csv(index=False).encode("utf-8"),
            file_name=f"estandar_{circuito_input}_{sesion_input}.csv".replace(" ", "_"),
            mime="text/csv",
            width="content",
        )

        with st.expander("Ver hoja LISTAS (catálogos)"):
            if df_standard_lists.empty:
                st.caption("La hoja LISTAS no está disponible o está vacía.")
            else:
                st.dataframe(df_standard_lists, width="stretch", hide_index=True)

with tab_sector:
    st.title("📡 Avances Tecnológicos y Proyección Sectorial (2016-2026)")
    st.markdown(
        "Las metodologías impulsadas por la investigación en control y simulación han acelerado la "
        "integración de software avanzado en vehículos comerciales y de competición, consolidando "
        "ecosistemas conectados, predictivos e inmersivos."
    )

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Periodo analizado", "2016-2026")
    t2.metric("Ejes tecnológicos", "4")
    t3.metric("Latencia objetivo", "<100 ms")
    t4.metric("Variables MAIDS", "~2000/caso")

    st.markdown("---")

    st.subheader("🤖 IA + Grey-box + RL-MPC")
    st.markdown(
        "Una de las barreras del MPC tradicional era la carga computacional para modelar en tiempo real "
        "la degradación térmica del neumático o la adherencia del asfalto. Entre 2024 y 2025, la evolución "
        "ha migrado hacia RL-MPC y arquitecturas de caja gris que combinan física y datos estocásticos."
    )
    st.markdown(
        "Se confirma que la elección de variables de control sigue siendo crítica incluso con IA avanzada. "
        "En NMPC, sustituir par de dirección por ángulo de dirección puede inducir oscilaciones y divergencias "
        "al perder dinámica inercial de la dirección."
    )
    st.markdown(
        "En alta competición y autonomía, se integran NMPC + MHE + Procesos Gaussianos para corregir en "
        "milisegundos la diferencia entre el modelo interno y la realidad física de la motocicleta."
    )

    st.markdown("---")

    st.subheader("⚡ Edge AI, RAG/CAG y Telemetría Local")
    st.markdown(
        "Para evitar dependencia de latencia cloud, las arquitecturas Edge AI procesan inferencia sobre la moto "
        "y la telemetría local. Las estrategias híbridas RAG/CAG habilitan detección visual de anomalías a alta "
        "velocidad y decisiones iterativas con tiempos compatibles con control en curva."
    )

    st.markdown("---")

    st.subheader("🛡️ ARAS, IoT y Conectividad V2V/V2X")
    st.markdown(
        "La teoría de control ya vive en ECUs comerciales: ABS en curva, IMUs de 6 ejes, radares milimétricos, "
        "tracción avanzada, anti-wheelie, anti-stoppie y suspensión semi-activa coordinada con Ride-by-Wire."
    )
    st.markdown(
        "El mantenimiento predictivo aporta alertas anticipadas sobre frenos, hidráulica y baterías. "
        "La información se distribuye por OTA en dashboards y cascos HUD/AR."
    )
    st.markdown(
        "La seguridad de V2V/V2X se refuerza con consenso consciente del contexto en VANETs (p. ej. CoCoChain), "
        "con gobernanza adaptativa tipo blockchain, eficiencia energética y latencias sub-100 ms."
    )

    st.markdown("---")

    st.subheader("🎮 Simulación HIL Inmersiva (6-DOF)")
    st.markdown(
        "Los simuladores HIL de 6 grados de libertad (Gough-Stewart), combinados con VR y chasis sensorizados, "
        "permiten capturar la biointeracción piloto-moto en tiempo real. Esto mejora la validez psicofisiológica "
        "frente a plataformas de movimiento reducido."
    )
    st.markdown(
        "Los modelos multicuerpo se acoplan en milisegundos con comandos del piloto para replicar cizalladura "
        "de neumático, viento lateral y transiciones de contramanillar/dirección directa."
    )

    st.markdown("---")

    st.subheader("📉 Seguridad Vial y Proyección")
    st.markdown(
        "La explotación de bases como MAIDS (más de 920 accidentes, ~2000 variables por caso) en simulación "
        "inmersiva permite ensayar estrategias de evasión y prevención con soporte V2V."
    )
    st.markdown(
        "La proyección sectorial apunta a algoritmos predictivos híbridos, más robustos, embebidos y auditables, "
        "con despliegue progresivo desde la competición hasta motocicletas comerciales conectadas."
    )

    with st.expander("Ver texto base completo de referencia", expanded=False):
        st.markdown(
            """
**Avances Tecnológicos y Proyección Sectorial (2016-2026)**

Las metodologías sentadas por investigadores como Moreno Giner abrieron un cauce analítico que ha propulsado la integración masiva del software de simulación en las infraestructuras de vehículos comerciales, redefiniendo las capacidades mecatrónicas entre los años 2017 y 2026. Al dejar atrás las limitaciones de los modelos clásicos, la industria ha convergido hacia ecosistemas conectados, predictivos y altamente inmersivos.

**Integración de Inteligencia Artificial y Modelos de Caja Gris (Grey-box Modeling)**

Una de las barreras del MPC tradicional radicaba en la dificultad computacional de parametrizar empíricamente la degradación térmica del compuesto del neumático o las variaciones de adherencia del asfalto en tiempo real. Hacia 2024 y 2025, el enfoque ha migrado hacia el Control Predictivo basado en Aprendizaje Automático (RL-MPC) y las arquitecturas de "Caja Gris" que combinan física y datos estocásticos.

Investigaciones de vanguardia han demostrado que la correcta selección de las entradas de control sigue siendo crítica en estos modelos avanzados. Por ejemplo, Hatakeyama y colaboradores (2024) demostraron que al reemplazar el par de dirección (steering torque) por el ángulo de dirección en algoritmos NMPC (Nonlinear Model Predictive Control), se producen oscilaciones excesivas e incluso divergencias en la respuesta debido a la supresión de la dinámica inercial de la dirección. Esto confirma que, incluso en la era de la IA, la física base de control por fuerza es indispensable.

En el ámbito de la alta competición y la conducción autónoma, investigadores como Kebbati (2025) han fusionado el estimador matemático multicuerpo con rutinas de Inteligencia Artificial mediante NMPC acoplado a Estimadores de Horizonte Móvil (MHE) y regresiones de Procesos Gaussianos. Estos algoritmos procesan las mediciones inerciales de la motocicleta en milisegundos, "aprendiendo" paramétricamente la diferencia geométrica entre el modelo interno y la realidad física.

Para soportar la inmensa carga computacional de estos algoritmos en tiempo real sin depender de la latencia de la nube, las investigaciones recientes de Juárez Cádiz proponen la aplicación de principios de optimización estructural para el despliegue de Edge AI (Inteligencia Artificial en el Extremo) directamente en la telemetría de las motocicletas. El uso de arquitecturas de inferencia híbridas de recuperación y caché (RAG/CAG) permite la detección visual de anomalías a alta velocidad y el procesamiento iterativo local, haciendo viable que el control computacional gestione el paso por curva de una moto deportiva con una precisión milimétrica.

**Evolución de los Sistemas Avanzados de Asistencia al Piloto (ARAS) y Conectividad**

La teoría de control en estado estacionario y transitorio, antaño empleada solo para validación en computadoras, reside ahora en las Unidades de Control del Motor (ECUs) de motocicletas comerciales. Los Sistemas Avanzados de Asistencia (ARAS) han evolucionado desde el ABS básico hacia el Control de Conducción Adaptativo (ARC), integrando sensores de ángulo de inclinación, ABS en curva, radares de onda milimétrica y Módulos de Medición Inercial (IMUs) de 6 ejes. Estos controladores embebidos regulan sistemas combinados de tracción y anti-hundimiento (anti-wheelie y anti-stoppie) interconectados al acelerador electrónico (Ride-by-Wire) y actuadores de válvulas de amortiguación semi-activa.

En paralelo, la digitalización ha desencadenado la revolución del "Mantenimiento Predictivo" e Internet de las Cosas (IoT). La Inteligencia Artificial analiza continuamente los datos de los sensores para identificar patrones que señalan fallas potenciales mucho antes de que ocurran, como la fatiga del fluido hidráulico, la salud de las baterías en motos eléctricas o el desgaste de los frenos. El sistema notifica al conductor de forma preventiva a través de infraestructuras Over-The-Air (OTA) proyectadas en displays modulares o cascos conectados con tecnología HUD y realidad aumentada.

La viabilidad y seguridad de estas infraestructuras conectadas, vitales para la comunicación Vehículo-a-Vehículo (V2V) y Vehículo-a-Todo (V2X), se sustentan en la gestión inteligente del contexto en redes VANETs. Protocolos recientes de consenso conscientes del contexto, como CoCoChain, propuestos por Juárez Cádiz, garantizan el intercambio seguro de datos de sensores y previenen vulnerabilidades criptográficas. Mediante una gobernanza adaptativa de Blockchain impulsada por entropía, estos sistemas logran alta eficiencia energética y latencias inferiores a 100 ms (sub-100 ms latency), requisitos indispensables para que las acciones de evasión automatizadas operen con garantías de seguridad.

**Simuladores Inmersivos de Interacción Dinámica (Hardware-in-the-Loop)**

Las limitantes históricas de carecer de una estimación fisiológica del comportamiento pasivo de un piloto vivo también se han abordado magistralmente con la llegada de simuladores hiperinmersivos HIL (Hardware-in-the-Loop). En los últimos años, arquitecturas como el manipulador paralelo Gough-Stewart de 6 grados de libertad (6-DOF) se han combinado con cascos de Realidad Virtual (VR) y chasis sensorizados.

Estas plataformas instrumentan sensores de tensión en múltiples puntos del chasis simulado para capturar la bioimpedancia exacta del peso del piloto y sus interacciones dinámicas en tiempo real. Estudios recientes han demostrado que las configuraciones dinámicas que permiten una transición progresiva entre el contramanillar y la dirección directa (simulando fielmente la inestabilidad de dos ruedas) ofrecen una validez psicofisiológica superior frente a los simuladores de movimiento reducido. Las ecuaciones analíticas del modelo multicuerpo interactúan en milisegundos con los comandos articulares del ser humano, replicando con alta fidelidad factores como la cizalladura de los neumáticos y el viento lateral cruzado.

El avance en estos simuladores resulta ser la piedra angular para desarrollar estrategias de prevención de accidentes. Bases de datos exhaustivas en Europa, como el proyecto MAIDS (Motorcycle Accidents In Depth Study), que documentó a fondo más de 920 accidentes utilizando cerca de 2000 variables por caso, han permitido identificar los escenarios críticos de siniestralidad. Al integrar esta analítica en los simuladores inmersivos, los investigadores pueden ensayar estrategias de evasión de colisión apoyadas en sistemas V2V, representando la última frontera tecnológica para reducir la tasa de siniestralidad de los motoristas frente a turismos y redefiniendo el diseño de los algoritmos de control predictivo del futuro.
            """
        )

with tab_diagrams:
    st.title("📊 Diagramas Pro de Dinámica y Rendimiento")
    st.markdown(
        "Panel visual de ingeniería para inspección rápida: GG diagram, mapa presión-temperatura, "
        "mapas electrónicos y riesgo térmico por sesión."
    )

    dg1, dg2, dg3 = st.columns(3)
    sesion_diagrama = dg1.selectbox("Sesión de análisis", sesiones_disponibles, index=sesiones_disponibles.index(sesion))
    color_by = dg2.selectbox("Color por", ["run", "tipo_vuelta", "neumatico_rear"], index=0)
    show_density = dg3.checkbox("Mostrar contorno GG", value=True)

    dgm = df_telemetry[df_telemetry["sesion"] == sesion_diagrama].copy()
    if dgm.empty:
        st.info("No hay datos para la sesión seleccionada.")
    else:
        # Proxy GG sin acelerómetros directos: combina cambio de ritmo y reparto sectorial.
        dgm = dgm.sort_values(["run", "vuelta"]).reset_index(drop=True)
        dgm["lap_delta_s"] = dgm.groupby("run")["lap_time_s"].diff().fillna(0)
        dgm["g_long_proxy"] = (-dgm["lap_delta_s"]).clip(-1.5, 1.5)
        sec_sum = (dgm["sector_1_s"] + dgm["sector_2_s"] + dgm["sector_3_s"]).replace(0, pd.NA)
        dgm["g_lat_proxy"] = ((dgm["sector_1_s"] - dgm["sector_3_s"]) / sec_sum * 8).fillna(0).clip(-1.8, 1.8)

        st.subheader("🌀 GG Diagram (proxy)")
        fig_gg = px.scatter(
            dgm,
            x="g_lat_proxy",
            y="g_long_proxy",
            color=color_by if color_by in dgm.columns else "run",
            hover_data=["vuelta", "run", "lap_time_s", "velocidad_punta_kmh"],
            title=f"GG proxy — {sesion_diagrama}",
            opacity=0.75,
        )
        if show_density:
            fig_gg.add_trace(
                go.Histogram2dContour(
                    x=dgm["g_lat_proxy"],
                    y=dgm["g_long_proxy"],
                    colorscale="Blues",
                    showscale=False,
                    contours={"showlabels": False},
                    opacity=0.35,
                    name="Densidad",
                )
            )
        fig_gg.add_hline(y=0, line_dash="dash", line_color="#64748b")
        fig_gg.add_vline(x=0, line_dash="dash", line_color="#64748b")
        fig_gg.update_layout(template="plotly_white", xaxis_title="g lateral (proxy)", yaxis_title="g longitudinal (proxy)")
        st.plotly_chart(fig_gg, width="stretch")

        st.markdown("---")
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("🌡️ Mapa presión-temperatura")
            fig_pt = px.scatter(
                dgm,
                x="presion_rear_hot_target_bar",
                y="temp_neumatico_right_c",
                color="run",
                size="velocidad_punta_kmh",
                hover_data=["vuelta", "lap_time_s", "neumatico_rear"],
                title="Rear pressure vs temperatura derecha",
            )
            fig_pt.add_hline(y=95, line_dash="dot", annotation_text="Umbral térmico")
            fig_pt.add_vline(x=1.65, line_dash="dot", annotation_text="Mínimo reglamentario")
            fig_pt.update_layout(template="plotly_white", xaxis_title="Presión trasera hot (bar)", yaxis_title="Temp derecha (°C)")
            st.plotly_chart(fig_pt, width="stretch")

        with c2:
            st.subheader("🎛️ Perfil electrónico por run")
            maps_df = (
                dgm.groupby("run", as_index=False)
                .agg(
                    tc=("traction_control_lvl", "mean"),
                    ebc=("engine_brake_lvl", "mean"),
                    awc=("anti_wheelie_lvl", "mean"),
                    lap=("lap_time_s", "mean"),
                )
            )
            fig_maps = px.line_polar(
                maps_df.melt(id_vars=["run", "lap"], value_vars=["tc", "ebc", "awc"], var_name="mapa", value_name="nivel"),
                r="nivel",
                theta="mapa",
                color="run",
                line_close=True,
                title="Radar de mapas electrónicos",
                hover_data=["lap"],
            )
            fig_maps.update_layout(template="plotly_white")
            st.plotly_chart(fig_maps, width="stretch")

        st.markdown("---")
        st.subheader("⚠️ Heatmap de riesgo por vuelta")
        risk_df = dgm[["vuelta", "run", "temp_neumatico_right_c", "presion_rear_hot_target_bar", "lap_time_s"]].copy()
        risk_df["risk_score"] = (
            (risk_df["temp_neumatico_right_c"] - 90).clip(lower=0) * 0.35
            + (1.65 - risk_df["presion_rear_hot_target_bar"]).clip(lower=0) * 100 * 0.45
            + (risk_df["lap_time_s"] - risk_df["lap_time_s"].median()).clip(lower=0) * 0.20
        )
        heat = risk_df.pivot_table(index="run", columns="vuelta", values="risk_score", aggfunc="mean")
        if not heat.empty:
            fig_heat = px.imshow(
                heat,
                color_continuous_scale="YlOrRd",
                aspect="auto",
                title="Matriz de riesgo operativo (0=mejor)",
            )
            fig_heat.update_layout(template="plotly_white", xaxis_title="Vuelta", yaxis_title="Run")
            st.plotly_chart(fig_heat, width="stretch")
