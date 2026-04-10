# Dashboard Moto3 Goiânia

Dashboard técnico para análisis de telemetría, setup y operación por rol durante un fin de semana de Moto3 en Goiânia.

## Stack

- Streamlit
- Plotly
- Pandas

## Estructura

- `app.py`: aplicación principal
- `moto3_goiania_telemetry.csv`: datos de vueltas y telemetría
- `moto3_goiania_tasks.csv`: tareas operativas por rol/sesión
- `moto3_goiania_setup.csv`: parámetros de setup y referencias
- `requirements.txt`: dependencias de despliegue
- `.streamlit/config.toml`: configuración de tema y servidor

## Funcionalidades

- KPIs por sesión: mejor vuelta, velocidad punta, temperatura, anti-squat y presión trasera
- Gráficos de performance: tiempos por vuelta, sectores, gradiente térmico, presiones, mapas y compuestos
- Panel de alertas automáticas:
  - presión trasera por debajo de mínimo
  - exceso térmico en flanco derecho
  - anti-squat fuera de ventana objetivo
  - variabilidad de vuelta elevada
- Comparador de sesiones:
  - selección de sesión de referencia
  - deltas de KPIs clave
  - gráfico comparativo de métricas
- Mapa del circuito por localización:
  - trazado aproximado con puntos de curva
  - interacción para colorear vueltas por tiempo, run o sector dominante
  - selector para resaltar una vuelta
- Análisis avanzado:
  - scatter de temperatura derecha vs lap time
  - matriz de correlación de variables clave
  - distribución de tiempos de vuelta por run
- Kanban operativo por rol (Todo, In Progress, Done)
- Lista operativa de tareas:
  - progreso de completitud
  - filtros rápidos por estado y prioridad
  - búsqueda por texto
  - exportación de tareas filtradas a CSV y Excel (.xlsx) multi-hoja
    - Tareas_Filtradas
    - Resumen_Operativo
    - KPIs_Sesion

## Ejecutar en local

1. Instala dependencias:

```bash
pip install -r requirements.txt
```

2. Ejecuta Streamlit:

```bash
streamlit run app.py
```

3. Abre en navegador:

- `http://localhost:8501`

## Despliegue recomendado (gratis)

Plataforma recomendada: Streamlit Community Cloud.

1. Ve a `https://share.streamlit.io`
2. Inicia sesión con GitHub
3. Selecciona el repo `rubences/DashBoard`
4. Branch: `main`
5. Main file path: `app.py`
6. Deploy

Nota: Vercel no es una buena opción para apps Streamlit porque Streamlit requiere un proceso persistente con WebSockets.

