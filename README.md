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
- Modo de visualización:
  - Completo: todas las visualizaciones y análisis
  - Ejecutivo: vista resumida, enfocada en KPIs y decisión rápida
  - conserva preferencias entre sesiones locales (modo, paginación y filtros)
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
  - paginación de resultados filtrados
  - exportación de tareas filtradas a CSV y Excel (.xlsx) multi-hoja
    - Tareas_Filtradas
    - Resumen_Operativo
    - KPIs_Sesion
- Tabla de telemetría detallada paginada (en modo Completo)

## Ejecutar en local

1. Instala dependencias:

```bash
pip install -r requirements.txt
```

1. Ejecuta Streamlit:

```bash
streamlit run app.py
```

1. Abre en navegador:

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

## Publicar con URL de Vercel (Flask Gateway)

Si quieres compartir un enlace de Vercel, este repo ya incluye un gateway Flask:

- `api/index.py`: endpoint Flask para Vercel
- `vercel.json`: routing para ejecutar `api/index.py`

Funcionamiento:

1. Tu app principal se publica en Streamlit Community Cloud.
2. Vercel publica un endpoint Flask en tu dominio (`*.vercel.app`).
3. Ese endpoint redirige automáticamente a la URL pública de Streamlit.

### Pasos

1. Despliega primero la app en Streamlit Cloud y copia la URL pública (ejemplo: `https://xxxxx.streamlit.app`).
2. En Vercel, importa este mismo repositorio `rubences/DashBoard`.
3. En la configuración del proyecto en Vercel, añade la variable de entorno:
Key: `STREAMLIT_PUBLIC_URL`
Value: `https://tu-app.streamlit.app`
4. Haz deploy.
5. Al abrir tu URL de Vercel, redirigirá a Streamlit automáticamente.

### Endpoint de salud

- `GET /health` devuelve estado del gateway Flask.

Preferencias UI persistentes:
Se guardan automáticamente en `.streamlit/ui_prefs.json`.
Incluye perfil de vista, filtros, paginación, rol/sesión seleccionados y controles del circuito.
Puedes resetearlas desde el botón `Restablecer preferencias` en la barra lateral.

## Prompt recomendado para resumir la aplicación

Usa este prompt para generar un resumen ejecutivo y técnico de la app:

```text
Actúa como consultor senior de analítica y software para motorsport.

Quiero que resumas esta aplicación de Streamlit de forma profesional, clara y orientada a negocio y operación técnica.

Contexto de la app:
- Es un dashboard Moto3 para análisis de telemetría, setup, operación por roles y estandarización multi-circuito.
- Incluye pestañas de Goiânia (KPIs, alertas, comparador de sesiones, análisis avanzado, mapa de circuito, kanban y tareas), Aspar (spec comparativo por settings), Estándar Config Moto (matriz editable con validaciones y exportación), comparador Estándar vs Aspar, asistente RAG, diagramas avanzados (GG proxy y mapas técnicos) y una sección de avances tecnológicos 2016-2026.
- Permite exportaciones en CSV/Excel, persistencia de preferencias UI y control de calidad de datos.

Formato de salida requerido:
1) Resumen ejecutivo (5-8 líneas)
2) Problema que resuelve
3) Capacidades principales (bullet points)
4) Valor para perfiles clave (piloto, ingeniero, telemétrico, jefe de mecánicos)
5) Diferenciadores frente a un dashboard estándar
6) Riesgos o limitaciones actuales
7) Próximos pasos recomendados (priorizados)

Estilo:
- Español profesional
- Preciso, sin relleno
- Con enfoque en impacto operativo y toma de decisiones
```
