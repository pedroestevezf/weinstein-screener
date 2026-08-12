# Diseño: Plan 6 de 6 — Dashboard (Streamlit)

**Fecha**: 2026-08-12
**Estado**: Diseño aprobado vía mockup interactivo, pendiente de plan de implementación

**Mockup de referencia** (Artifact, iterado en vivo con el usuario durante el brainstorming): https://claude.ai/code/artifact/15bc0eb0-f82a-44ff-8f96-598600404b69

## 1. Objetivo y alcance

Interfaz de solo lectura/alertas sobre el pipeline ya implementado (Planes 1-5): permite explorar los candidatos de Etapa 1 y, bajo demanda, analizar la estructura Wyckoff/CRT/ICT de un ticker concreto. **No ejecuta operaciones ni gestiona una cuenta de bróker** — hereda esta restricción del diseño maestro del proyecto.

Dos pantallas:
1. **Screener Filtrado** — tabla de los candidatos de Etapa 1.
2. **Detalle de ticker** — análisis Etapa 2 completo de un ticker, calculado bajo demanda.

## 2. Decisión de arquitectura: Etapa 2 bajo demanda

La Etapa 2 (detección de estructura Wyckoff + señales ICT) **no se precalcula para los 943 candidatos**. Se ejecuta solo para el ticker que el usuario selecciona en ese momento, al entrar en su vista de detalle. Justificación (decidida explícitamente con el usuario, no asumida): la Etapa 2 no es instantánea por ticker, y precalcularla para los 943 candidatos en cada carga del dashboard sería costoso sin necesidad — el usuario normalmente solo profundiza en un puñado de tickers por sesión.

Consecuencia directa: la pantalla de Screener Filtrado solo puede mostrar columnas calculables baratamente (Etapa 1 + fundamentales vía `yfinance`, ver sección 3), nunca campos derivados de la estructura Wyckoff (esos solo existen tras abrir el detalle de un ticker concreto).

## 3. Pantalla 1 — Screener Filtrado

Tabla de los candidatos de Etapa 1 (`run_etapa1_screen`, Plan 5), ordenable por cualquier columna (clic en cabecera, segundo clic invierte el orden):

| Columna | Fuente | Coste |
|---|---|---|
| Ticker | `Etapa1Candidate.ticker` | ya calculado (Plan 5) |
| Sector | `yfinance Ticker.get_info()["sector"]` | ver más abajo |
| Distancia a MA30w | `Etapa1Candidate.distance_pct` | ya calculado (Plan 5) |
| Volumen relativo | nuevo, ver abajo | gratis (reutiliza velas ya descargadas) |
| Cap. mercado | `yfinance Ticker.get_info()["marketCap"]` | ver más abajo |
| PER | `yfinance Ticker.get_info()["trailingPE"]` | ver más abajo |
| EV / FCF | `yfinance Ticker.get_info()["enterpriseValue"] / ["freeCashflow"]` | ver más abajo |

**Nota sobre `ma_rising`**: todos los tickers de esta lista ya tienen `ma_rising=True` por construcción (`run_etapa1_screen` solo devuelve candidatos con `is_candidate=True`, que ya exige `ma_rising`) — no aporta como columna filtrable/ordenable, se puede omitir o mostrar como texto fijo.

### 3.1. Fundamentales (`sector`, `cap. mercado`, `PER`, `EV/FCF`)

Verificado con datos reales (`yf.Ticker(t).get_info()` para WM/AAPL/NGVC/BCML): estos 4 campos vienen de la **misma** llamada — no hay coste incremental por añadir `sector` una vez que ya se piden los otros tres.

**Restricción crítica de coste, verificada con datos reales**: `get_info()` es una llamada **por ticker, ~0.4-0.85s cada una, sin equivalente en lote** (a diferencia de `yfinance.download()`, que sí acepta lotes). Para el universo completo (~5395 tickers) supondría ~45-60 minutos. **Decisión explícita del usuario**: se calcula solo para los candidatos que ya pasaron el filtro técnico de Etapa 1 (943, no 5395) — unos 9-10 minutos, ejecutado como parte del mismo job semanal de `scripts/run_etapa1.py` (o un paso inmediatamente posterior), no en tiempo real al cargar el dashboard.

**Datos ausentes**: no todos los tickers tienen todos los campos (verificado: `BCML`, una small-cap, no tiene `freeCashflow`). Se muestran como "—" en la tabla y se ordenan siempre al final, en cualquier dirección de orden.

### 3.2. Volumen relativo (nuevo cálculo, sin coste adicional)

Motivación (explícita del usuario): no un promedio absoluto, sino una señal de actividad institucional reciente por encima de lo habitual.

**Definición**: media de volumen de las **últimas 3 semanas cerradas** ÷ media de las **20 semanas previas a esas 3**. Se calcula con las velas semanales que Etapa 1 ya descarga para el filtro técnico — no requiere ninguna llamada adicional. Parámetros (`recent_weeks=3`, `baseline_weeks=20`) son configurables, **a validar en backtest** como el resto de umbrales del proyecto.

Valores ≥1.5× se resaltan visualmente en la tabla (píldora "elevado") — umbral también a validar.

## 4. Pantalla 2 — Detalle de ticker

Al seleccionar un ticker de la tabla: estado de carga breve ("Analizando estructura Wyckoff/CRT/ICT de \<ticker\> (bajo demanda)…") mientras se ejecuta la Etapa 2 para ese ticker, luego:

### 4.1. Gráfico de precio anotado (semanal)

- Velas semanales + **línea de MA30 semanal**.
- **Requisito de datos, no solo de dibujo** (aprendido durante el mockup, donde una serie sintética de 32 velas sin suficiente historial previo producía una MA30 mal definida al principio del gráfico): al pedir los datos para pintar el gráfico, solicitar **`semanas_visibles + 30` semanas de histórico como mínimo**, y solo dibujar el rango de las semanas visibles. El pipeline ya descarga de sobra (10 años por defecto en `fetch_ohlcv`) para que esto no sea un problema en producción — es un requisito para la capa de renderizado del gráfico, no para la capa de datos.
- **Rango completo de acumulación** (mínimo del SC ↔ máximo del AR) sombreado, con líneas de referencia punteadas para ambos niveles — no solo el sub-rango de la Fase B. Abarca desde la vela del SC hasta la vela del JAC.
- Marcadores de SC (en su mínimo), AR (en su máximo), ST (en su mínimo), Spring (en su mínimo, **por debajo** del mínimo del SC), JAC (en su cierre), BUEC (en su mínimo) — cada uno en el punto de la vela que corresponde a lo que representa, no genéricamente en el máximo/mínimo de la vela.
- Línea de objetivo proyectado (`project_range_target`: precio de entrada del JAC + amplitud del rango SC↔AR).
- Eje de precios a la derecha, con marcas de rejilla tenues, separadas visualmente de las etiquetas de color de SC-low/AR-high/objetivo.
- Barras de volumen debajo del precio, coloreadas igual que la vela correspondiente.
- **Nota importante de alcance**: la Entrada 3 (BUEC) se evalúa sobre velas **diarias**, no sobre las velas semanales de este gráfico — el marcador de BUEC en el gráfico semanal es una referencia visual aproximada de dónde ocurre el retroceso, no la vela exacta que evalúa `find_buec`. El dashboard debe dejar esto claro en la interfaz (ver mockup) para no sugerir una correspondencia 1:1 que no existe.

### 4.2. Aviso de recorrido ya avanzado

Reutiliza `project_range_target` (ya implementado, Plan 4). Progreso hacia el objetivo:

```
progreso = (precio_actual - precio_entrada_JAC) / (objetivo_proyectado - precio_entrada_JAC)
```

Si `progreso >= 0.5` (parámetro, **a validar en backtest**): banner de aviso visible en el detalle — "Ha cubierto el X% de la distancia entre la entrada del JAC y el objetivo proyectado — el ratio riesgo/beneficio de una entrada nueva aquí es pobre."

**Decisión explícita del usuario sobre dónde vive este filtro**: solo como aviso en el detalle bajo demanda, no como filtro/exclusión en la tabla de Etapa 1 — calcularlo para los 943 candidatos de la lista requeriría la Etapa 2 completa (estructura Wyckoff + JAC + rango), que es precisamente lo que la arquitectura bajo-demanda (sección 2) evita hacer en lote.

### 4.3. Tres tarjetas de entrada (Entrada 1 / 2 / 3)

Estado (`Activa` / `Sin señal`), precio, stop loss, y contexto específico de cada una:

- **Entrada 1 (Spring)**: composición ya implementada (`find_entry_1_signal`, Plan 3).
- **Entrada 2 (JAC)**: composición ya implementada (`find_entry_2_signal`, Plan 4 revisión).
- **Entrada 3 (BUEC)**: composición ya implementada (`find_entry_3_signal`, Plan 3 + revisión 2026-08-12). El dashboard debe reflejar el estado real, binario, de `find_buec` — no existe un estado intermedio "BUEC detectado pero sin confirmar" en el código (esto fue un error introducido en una iteración temprana del mockup, corregido: `find_buec` devuelve una vela que cumple al menos uno de los tres criterios, o `None`, sin paso intermedio).

### 4.4. Panel de alertas de gestión y panel de objetivo/salida

Ya implementados (`management.py`, Plan 4): breakeven de Entrada 1, reasignación por Spring fallido, salida maestra por cierre bajo MA30w, objetivo proyectado y distancia al mismo.

## 5. Cambios en el pipeline detectados y resueltos durante este brainstorming

Durante la revisión del mockup se identificó una carencia real en `ict.py` (Plan 3): `find_buec` solo confirmaba por volumen descendente o vela "no supply" (rango estrecho + cierre bajo + volumen bajo la media de 2 velas), dejando sin cubrir el caso de una vela con volumen muy bajo respecto a las semanas previas que toca la parte alta del rango sin cumplir esas otras condiciones. Se implementó como revisión de Plan 3 (rama `plan3-revision-buec-low-volume`, ya fusionada a `main`, ver `docs/superpowers/plans/2026-08-12-plan3-revision-buec-low-volume.md`):

- `find_buec` gana un tercer criterio de **detección**: `low_volume` (volumen ≤50% de la **mediana** de las 10 semanas previas — mediana, no media, para no dejarse engañar por un pico real de SC/AR/Spring dentro de esa ventana).
- `find_entry_3_signal`'s `high_confidence` usa un criterio **distinto y más estricto**, no `low_volume` directamente: vela bajista, de rango estrecho, con cierre en el 75% superior de su rango, y volumen muy bajo respecto a la **mediana de las 4 velas previas** (ventana más corta que la de detección, más sensible a un secado de volumen reciente). Esto evita que una vela de distribución real (rango ancho, cierre bajo) se etiquete como la señal de mayor confianza.

El dashboard (sección 4.3) debe consumir estos campos tal cual quedaron, no la versión anterior a la revisión.

## 6. Fuera de alcance de este diseño

- Cobertura de Eurostoxx en la tabla (Etapa 1 sigue limitada a NYSE+Nasdaq, Plan 5).
- Comparar varios tickers a la vez, o histórico de alertas pasadas — no solicitado.
- Cualquier ejecución de órdenes o gestión de posición automatizada — fuera de alcance de todo el proyecto.
