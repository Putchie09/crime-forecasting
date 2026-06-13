# Criminalidad Alajuela — Sistema de Pronóstico

Sistema web para el análisis y pronóstico de criminalidad en la provincia de Alajuela, Costa Rica.
Desarrollado con Django 5, Tailwind CSS y Chart.js.

**Proyecto académico — IF-7200 Métodos Cuantitativos para la Toma de Decisiones**  
Universidad de Costa Rica, Sede de Occidente

---

## Requisitos del sistema

| Herramienta | Versión mínima |
|-------------|----------------|
| Python      | 3.12+          |
| pip         | 23+            |

---

## Ejecución

El proyecto se distribuye con la base de datos ya cargada (`db.sqlite3` incluida en el ZIP), por lo que en la mayoría de los casos no es necesario importar el dataset manualmente.

---

### Método 1 — Script automático `INICIAR.bat` (Windows, recomendado)

1. Descomprimir el ZIP en cualquier carpeta.
2. Hacer **doble clic** en `INICIAR.bat` (ubicado dentro de `crime_forecasting/`).

El script se encarga automáticamente de:

- Verificar que Python 3.12+ esté instalado.
- Crear el entorno virtual `venv/` si no existe.
- Instalar las dependencias de `requirements.txt` (solo la primera vez, ~5–8 min).
- Aplicar migraciones pendientes.
- Detectar el puerto disponible (usa 8000 o 8001 si el primero está ocupado).
- Abrir el navegador predeterminado en `http://127.0.0.1:<puerto>` automáticamente.

> **Requisito:** Python 3.12+ instalado con la opción **"Add Python to PATH"** marcada durante la instalación.  
> La ventana de consola debe permanecer abierta mientras se usa el sistema. Para detener el servidor, presione `Ctrl+C` o cierre la ventana.

---

### Método 2 — Manual (Linux/macOS o si el script no funciona)

```bash
# 1. Entrar al directorio del proyecto
cd crime_forecasting

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar el entorno virtual
#    Linux / macOS:
source venv/bin/activate
#    Windows (PowerShell / CMD):
venv\Scripts\activate

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Aplicar migraciones
python manage.py migrate

# 6. Iniciar el servidor
python manage.py runserver
```

Abra el navegador en: **http://127.0.0.1:8000**

---

### Cargar el dataset desde cero (opcional)

Solo es necesario si la base de datos está vacía o se desea reimportar los datos.

1. Copie el archivo `Estadisticas.xlsx` (datos del OIJ) a la carpeta `datasets/`:

   ```bash
   cp /ruta/al/Estadisticas.xlsx datasets/Estadisticas.xlsx
   ```

   > El archivo debe conservar el nombre `Estadisticas.xlsx`. Si tiene otro nombre, actualice `DATASET_PATH` en `config/settings.py`.

2. Ejecute el comando de carga:

   ```bash
   python manage.py load_dataset
   ```

   Este comando:
   - Lee `datasets/Estadisticas.xlsx`
   - Limpia y valida los datos
   - Filtra registros de la provincia de Alajuela
   - Construye las series de tiempo mensuales
   - Importa todo a la base de datos SQLite

---

## Estructura del proyecto

```
crime_forecasting/
│
├── config/                         # Configuración Django
│   ├── settings.py                 # Configuración principal
│   ├── urls.py                     # Rutas raíz
│   └── wsgi.py
│
├── forecasting/                    # Aplicación principal
│   ├── models.py                   # CrimeRecord + MonthlySeries
│   ├── views.py                    # HomeView, ForecastView, HistoricalView
│   ├── urls.py                     # Rutas de la app
│   ├── admin.py                    # Admin Django
│   │
│   ├── services/                   # Lógica de negocio (separada de vistas)
│   │   ├── data_service.py         # Carga, limpieza e importación del dataset
│   │   ├── forecast_service.py     # Orquestación de todos los modelos
│   │   └── report_service.py       # Generación de reportes PDF
│   │
│   ├── forecasting_methods/        # Implementación de modelos cuantitativos
│   │   ├── trend.py                # Tendencia lineal Y(t) = a + b·t
│   │   ├── exponential_smoothing.py# Suavizamiento exponencial (α óptimo)
│   │   ├── seasonal_index.py       # Índices estacionales mensuales
│   │   └── multiplicative_decomposition.py  # Y = T × S × I
│   │
│   ├── management/
│   │   └── commands/
│   │       └── load_dataset.py     # Comando: python manage.py load_dataset
│   │
│   └── migrations/                 # Migraciones de base de datos
│
├── templates/                      # Templates HTML
│   ├── base.html                   # Layout base con navegación
│   ├── forecasting/
│   │   ├── home.html               # Pantalla de inicio
│   │   ├── forecast.html           # Módulo de pronósticos
│   │   └── historical.html         # Explorador de datos
│   └── partials/
│       └── query_params.html       # Parámetros de filtro para paginación
│
├── static/                         # Archivos estáticos (CSS, JS, imágenes)
│   ├── css/
│   ├── js/
│   └── images/
│
├── datasets/                       # Dataset OIJ (aquí va Estadisticas.xlsx)
├── reports/                        # Reportes PDF generados
├── tests/                          # Pruebas unitarias
│
├── manage.py
└── requirements.txt
```

---

## Modelos cuantitativos implementados

### 1. Tendencia Lineal (`trend.py`)

Regresión lineal sobre el tiempo: **Y(t) = a + b·t**

- Estima intercepto `a` y pendiente `b` mediante mínimos cuadrados.
- Proyecta la trayectoria general de crecimiento o reducción.

### 2. Suavizamiento Exponencial (`exponential_smoothing.py`)

**S(t) = α·Y(t) + (1-α)·S(t-1)**

- El parámetro `α ∈ (0,1)` se optimiza automáticamente por minimización de SSE.
- Pesos decrecientes: observaciones recientes tienen mayor influencia.

### 3. Índices Estacionales (`seasonal_index.py`)

**Ŷ(t) = Tendencia(t) × ÍndiceEstacional(mes)**

1. Calcula el promedio mensual / promedio global para cada mes.
2. Ajusta la serie de tiempo con la tendencia lineal.
3. Re-estacionaliza para obtener el pronóstico final.

### 4. Descomposición Multiplicativa (`multiplicative_decomposition.py`)

**Y(t) = T(t) × S(t) × I(t)**

1. Media móvil centrada de 12 meses para estimar T(t).
2. Índices de irregular-estacional (SI) mediante ratios Y/CMA.
3. Índices estacionales mensuales normalizados (suma = 12).
4. Tendencia lineal sobre serie desestacionalizada.

---

## Métricas de evaluación

| Métrica | Descripción |
|---------|-------------|
| **DMA (MAE)** | Desviación Media Absoluta — menor es mejor |
| **MSE** | Error Cuadrático Medio |
| **RMSE** | Raíz del Error Cuadrático Medio |
| **Precisión** | 1 − MAE/media × 100% |

El sistema **selecciona automáticamente** el mejor modelo según el menor DMA.

---

## Módulos de la aplicación

### 1. Inicio (`/`)
- KPI cards: total de registros, cantones, tipos de delito, período
- Gráfico histórico general (toda la provincia)
- Tarjetas explicativas de cada metodología

### 2. Pronosticar (`/pronosticar/`)
- Formulario: Cantón, Tipo de delito, Fechas, Meses a pronosticar
- Todos los métodos se ejecutan automáticamente
- Gráfico histórico + pronóstico + fitted
- Comparación de métodos (Chart.js)
- Tabla de métricas (DMA, MSE, RMSE, Precisión)
- Tabla de pronóstico con valores mensuales
- Interpretación automática en español
- Exportación PDF

### 3. Datos históricos (`/datos-historicos/`)
- Filtros: búsqueda, cantón, delito, sexo, fechas
- Tabla paginada (50 registros/página)
- Exportación CSV con filtros aplicados

---

## Comandos útiles

```bash
# Cargar dataset
python manage.py load_dataset

# Dataset en ruta personalizada
python manage.py load_dataset --path /ruta/al/archivo.xlsx

# Crear superusuario para el admin
python manage.py createsuperuser

# Correr servidor de desarrollo
python manage.py runserver

# Panel de administración: http://127.0.0.1:8000/admin/
```

---

## Estilo visual

- **Tipografía:** Inter (Google Fonts)
- **Color principal:** `#1B263B` (azul marino oscuro)
- **Framework CSS:** Tailwind CSS (CDN)
- **Gráficos:** Chart.js 4.4
- **Inspiración:** Stripe, Linear, Vercel — diseño SaaS profesional

---

## Columnas requeridas en el dataset

El archivo Excel debe contener las siguientes columnas (el sistema normaliza mayúsculas/minúsculas):

```
Delito | SubDelito | Fecha | Hora | Victima | SubVictima | Edad | Sexo | Nacionalidad | Provincia | Canton | Distrito
```

El sistema filtra automáticamente los registros de la **provincia de Alajuela**.

---

## Notas importantes

1. **Datos mínimos para pronóstico:**
   - Tendencia lineal: mínimo 2 meses
   - Suavizamiento exponencial: mínimo 3 meses
   - Índices estacionales: mínimo **12 meses**
   - Descomposición multiplicativa: mínimo **12 meses**

2. Si el dataset de ejemplo (9 registros) solo tiene datos de 2021, los modelos estacionales mostrarán error. Use el dataset completo del OIJ.

3. El sistema es **stateless** entre sesiones — los resultados se calculan on-demand.

---

## 👥 Autores

- Yoel Putchie Campos — C36188
- Keleny Zamora Díaz — C38624
- Dayanara Campos Murillo — C31595

**Profesora:** Prof. Iyubanit Rodríguez  
**Curso:** IF-7200 — Métodos Cuantitativos para la Toma de Decisiones  
**I Ciclo 2026** — UCR Sede de Occidente, Recinto de Grecia
