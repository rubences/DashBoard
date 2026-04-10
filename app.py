import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

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

# ============================================================
# SIDEBAR — FILTROS
# ============================================================

roles = sorted(df_tasks["rol"].dropna().unique().tolist())
sesiones_disponibles = [s for s in SESIONES_ORDEN if s in df_telemetry["sesion"].unique()]
if not sesiones_disponibles:
    sesiones_disponibles = sorted(df_telemetry["sesion"].dropna().unique().tolist())

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

    st.markdown("---")
    st.caption("Datos: telemetría, tareas y setup CSV")

# ============================================================
# FILTRADO DE DATOS
# ============================================================

dff = df_telemetry[df_telemetry["sesion"] == sesion].copy()
tff = df_tasks[(df_tasks["sesion"] == sesion) & (df_tasks["rol"] == rol)].copy()

# ============================================================
# ENCABEZADO
# ============================================================

st.title("Dashboard Moto3 — Goiânia 2026")
st.markdown(f"**Sesión:** {sesion} &nbsp;|&nbsp; **Rol:** {rol}")
st.markdown("---")

# ============================================================
# KPI CARDS
# ============================================================

best_lap = dff["lap_time_s"].min() if not dff.empty else None
vmax = dff["velocidad_punta_kmh"].max() if not dff.empty else None
temp_right = dff["temp_neumatico_right_c"].mean() if not dff.empty else None
anti_squat = dff["anti_squat_pct"].mean() if not dff.empty else None
p_rear = dff["presion_rear_hot_target_bar"].mean() if not dff.empty else None

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
