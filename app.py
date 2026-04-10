import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import math
from io import BytesIO

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

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "Completo"
if "task_page_size" not in st.session_state:
    st.session_state.task_page_size = 8
if "telemetry_page_size" not in st.session_state:
    st.session_state.telemetry_page_size = 10
if "task_page" not in st.session_state:
    st.session_state.task_page = 1
if "telemetry_page" not in st.session_state:
    st.session_state.telemetry_page = 1
if "task_search" not in st.session_state:
    st.session_state.task_search = ""

with st.sidebar:
    st.title("🏍️ Moto3 Goiânia 2026")
    st.markdown("---")

    default_rol = "Ingeniero de Pista" if "Ingeniero de Pista" in roles else roles[0]
    rol = st.selectbox("Rol", roles, index=roles.index(default_rol))

    default_sesion = "Practice" if "Practice" in sesiones_disponibles else sesiones_disponibles[0]
    sesion = st.selectbox(
        "Sesión",
        sesiones_disponibles,
        index=sesiones_disponibles.index(default_sesion)
    )

    compare_options = ["Ninguna"] + [s for s in sesiones_disponibles if s != sesion]
    compare_session = st.selectbox("Comparar contra", compare_options, index=0)

    st.markdown("### Modo de vista")
    view_mode = st.radio("Perfil", ["Completo", "Ejecutivo"], key="view_mode")
    task_page_size = st.slider("Filas por página (tareas)", min_value=5, max_value=30, step=1, key="task_page_size")
    telemetry_page_size = st.slider("Filas por página (telemetría)", min_value=5, max_value=30, step=1, key="telemetry_page_size")

    st.markdown("### Interacción del circuito")
    circuit_color_mode = st.selectbox(
        "Colorear vueltas por",
        ["Tiempo de vuelta", "Run", "Sector dominante"],
        index=0,
    )

    dff_preview = df_telemetry[df_telemetry["sesion"] == sesion].copy()
    available_laps = sorted(dff_preview["vuelta"].dropna().astype(int).unique().tolist())
    selected_lap = None
    if available_laps:
        selected_lap = st.select_slider(
            "Resaltar vuelta",
            options=available_laps,
            value=available_laps[0],
        )

    st.markdown("---")
    st.caption("Datos: telemetría, tareas y setup CSV")

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
