# Diseño: Sistema de señales — Weinstein + Wyckoff + CRT + ICT + PO3

**Fecha**: 2026-08-09
**Estado**: Diseño aprobado, pendiente de plan de implementación

## 1. Objetivo y alcance

Sistema que **genera señales/alertas** de entrada y salida sobre acciones, combinando análisis de régimen de tendencia (Weinstein), estructura de acumulación (Wyckoff), manipulación de rango (CRT) y precisión de entrada (ICT/PO3).

**No es un bot de ejecución automática.** No coloca órdenes ni gestiona una cuenta de bróker. El tamaño de posición se decide manualmente por el usuario en cada señal.

## 2. Universo

- **Todo NYSE + Nasdaq** (cubre de forma nativa S&P 500 y la práctica totalidad de Russell 2000; no se tratan como listas separadas para evitar redundancia).
- **Eurostoxx** (mercado europeo).
- Solo posiciones **largas**.

## 3. Arquitectura de dos etapas

El universo es demasiado amplio (miles de tickers) para correr la detección completa sobre cada uno cada semana. Se filtra en dos etapas:

### Etapa 1 — Filtro barato (todo el universo)

Herramienta: **TradingView (plan gratuito) + Pine Screener**, timeframe semanal.

Condiciones:
- **Distancia a MA30w**: `|precio − MA30w| / MA30w ≤ X%`, con X entre **5% y 10%** (parámetro a optimizar en backtest). Captura tanto valores aún en Fase B (por debajo, cerca del Spring) como los que acaban de romper al alza (Distribution reciente).
- **Pendiente de MA30w**: pendiente actual > pendiente de hace 3-5 semanas (la media se está aplanando o empezando a girar al alza).

**Nota de proceso (v1)**: no existe API gratuita para extraer resultados del screener de forma programática. El shortlist resultante se exporta **manualmente cada semana** como paso intermedio hacia la Etapa 2. Automatizar esto por completo requeriría un proveedor de datos de pago.

### Etapa 2 — Detección completa (solo sobre el shortlist de la Etapa 1)

Se aplica únicamente a los tickers que pasan la Etapa 1 (decenas/pocos cientos, no miles).

## 4. Capa de régimen: Weinstein + Wyckoff (semanal)

Un activo queda **habilitado** para buscar entradas solo si se cumplen todas las condiciones:

- Cierre semanal por encima de la MA30w.
- MA30w con pendiente ascendente (vs. 3-5 semanas atrás).
- Existe una estructura de Acumulación/Reacumulación válida (Wyckoff):
  - **Fase A**: Preliminary Support (PS) → Selling Climax (SC: rango > 2x el rango medio de 10 semanas, volumen > percentil 80 de 20 semanas) → Automatic Rally (AR) → Secondary Test (ST: retest del mínimo del SC en volumen menor, sin romperlo significativamente). Fase A termina en el ST.
  - **Fase B**: desde el ST hasta el Spring/Shakeout. Duración de Fase B ≥ **1.5x** la duración de Fase A.

**Invalidación**: si el cierre semanal cae por debajo de la MA30w, el activo queda deshabilitado — se cierra cualquier posición abierta (alerta de salida total) y no se buscan nuevas entradas hasta reconfirmar el régimen.

Todos los umbrales numéricos de esta sección (2x rango, percentil 80, ratio 1.5x) son **puntos de partida a validar empíricamente en backtest**, no hechos probados — ver sección 8.

## 5. Capa CRT (unificada con Wyckoff)

CRT y Wyckoff describen el mismo evento con distinto vocabulario; se unifican en una sola narrativa semanal:

- **Range** = rango de la Fase B de Wyckoff.
- **Manipulation** = el Spring/Shakeout (barrido del mínimo del rango, idealmente con mecha inferior larga y volumen ≥ media del rango).
- **Distribution** = ruptura de la resistencia del rango con volumen superior a la media (coincide con la Fase D de Wyckoff / confirmación de Stage 2 de Weinstein).

## 6. Entradas (ICT, 3 tramos, alertas)

Todas las entradas son generación de alerta, no ejecución.

**Entrada 1 — 30% (Spring)**
- Trigger: cambio de estructura (MSS) en diario tras el barrido semanal.
- Precio: retroceso al Order Block o Fair Value Gap (FVG) diario generado en el impulso de reacción.
- SL: bajo el mínimo del shakeout semanal (+ buffer ~0.25x ATR diario).

**Entrada 2 — 30% (Ruptura del rango)**
- Trigger: confirmación Weinstein/Distribution (cierre semanal sobre resistencia + MA30w ascendente + volumen sobre la media).
- Precio: cerca del breakout, sin esperar retest.
- SL: **1.5x ATR semanal** (no un % fijo — se adapta a la volatilidad de cada valor, dado lo heterogéneo del universo).

**Entrada 3 — 40% (Retest del rango)**
- Trigger: retroceso a la zona rota (antigua resistencia).
- Confirmación adicional obligatoria (al menos una): **volumen descendente** en las velas del retroceso, o **vela "no supply"** (rango estrecho, cierre bajo/plano, volumen bajo la media). Sin esto, la entrada no se activa aunque el precio toque la zona.
- Precio: Order Block/FVG diario formado en el retest.
- SL: estructural, bajo ese Order Block/FVG.

**Gestión de las entradas**:
- Al activarse la Entrada 2, se genera alerta para mover el SL de la Entrada 1 a breakeven.
- **Spring fallido** (Entrada 1 activada y luego detenida por su SL): no se genera una nueva Entrada 1 para ese mismo setup. Se recomienda, vía alerta, aumentar proporcionalmente las Entradas 2 y 3 manteniendo su ratio original (30:40 = 3:4) para sumar el 100%: Entrada 2 → ~43%, Entrada 3 → ~57%. Es una recomendación, no un tamaño forzado.

## 7. Salida (alertas)

- **Techo de referencia PO3**: al confirmarse la entrada, se calcula una vez el objetivo de Distribution del ciclo superior. Por defecto se usa el **timeframe mensual**; se pasa a **trimestral** solo si el rango de la Fase B (Wyckoff) es mayor que el rango mensual típico del valor.
- **Toma de parcial**: alerta para tomar ~25-30% de la posición abierta al alcanzar el techo de referencia.
- **Salida total (maestra)**: alerta de cierre completo si el cierre semanal cae por debajo de la MA30w — se cumpla o no se haya alcanzado el techo de referencia.

## 8. Parámetros a validar/optimizar en backtest

Ninguno de estos valores está confirmado por evidencia empírica — son puntos de partida razonables a probar contra datos históricos reales antes de confiar en ellos:

| Parámetro | Valor inicial |
|---|---|
| Distancia MA30w (Etapa 1) | 5-10% |
| Pendiente MA30w (lookback) | 3-5 semanas |
| Ratio duración Fase B / Fase A | 1.5x |
| Umbral rango Selling Climax | > 2x rango medio (10 semanas) |
| Umbral volumen Selling Climax | > percentil 80 (20 semanas) |
| Buffer SL Entrada 1 | 0.25x ATR diario |
| SL Entrada 2 | 1.5x ATR semanal |
| % parcial en techo PO3 | 25-30% |

## 9. Riesgos y puntos abiertos (no bloquean el diseño, a vigilar en implementación)

- **Calidad de datos de volumen en Europa**: varias reglas dependen del volumen (Selling Climax, no-supply bar, volumen descendente en retest). El volumen en mercados europeos está más fragmentado entre bolsas (MiFID) que el volumen consolidado de EE.UU. — vigilar al elegir la fuente de datos de la Etapa 2.
- Fuente de datos histórica (OHLCV diario/semanal, US+Europa) para la Etapa 2 aún no decidida — corresponde al plan de implementación.
- El paso manual de exportación del shortlist de la Etapa 1 es un cuello de botella operativo en v1.

## 10. Fuera de alcance (explícito)

- Ejecución automática de órdenes / integración con bróker.
- Gestión de tamaño de posición automatizada.
- Operativa en corto (short).
