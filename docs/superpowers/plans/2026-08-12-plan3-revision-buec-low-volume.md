# Revisión — Plan 3: tercer criterio de confirmación BUEC (volumen muy bajo)

**Fecha**: 2026-08-12
**Estado**: Verificado, pendiente de ejecución

## Contexto y motivo

Al revisar el mockup del dashboard (Plan 6), surgió un caso real en el ticker WM: el BUEC se detecta (el precio toca la zona rota de `ar_high`) pero ninguno de los dos criterios de confirmación existentes en `find_buec` (`ict.py`) se cumple:

- **`volume_declining`**: volumen descendente a lo largo del retroceso (≥80% de las velas comparadas en descenso).
- **`no_supply`**: vela con rango estrecho + cierre en la mitad superior + volumen bajo la media de las 2 velas previas, **y además** bajista.

El usuario propuso un tercer criterio, más suelto que `no_supply`: una vela con volumen muy bajo respecto a las semanas previas que toca la parte alta del rango — sin exigir rango estrecho ni cierre bajista/plano. Es un caso real y distinto, no una variante de los dos existentes.

## Diseño

### Nuevo criterio: `low_volume`

`_is_low_volume_candle(df, index, lookback=10, fraction=0.5) -> bool`: volumen de la vela `index` ≤ `fraction` × **mediana** (no media) del volumen de las `lookback` velas previas.

**Por qué mediana y no media**: verificado con un caso sintético (mediana=502500, media=681500 con un pico de 2.3M mezclado en la ventana de 10 semanas — representando un SC/AR/Spring real que puede caer dentro de esa ventana). Con la media, la comparación de esa misma vela BUEC pasa de un ratio 0.46 (mediana, refleja bien "está a la mitad de lo habitual") a 0.34 (media, inflada por el pico) — la media hace que el criterio se dispare con más facilidad de la que aparenta cuando hay un pico reciente dentro de la ventana. La mediana es robusta a ese sesgo.

**Fracción por defecto**: `0.5` (la vela debe tener como mucho la mitad del volumen mediano reciente). Es deliberadamente más estricto que `volume_decline_fraction=0.8` (usado para "volumen descendente", que solo exige un descenso del 20%) porque busca algo cualitativamente distinto y más raro — una sequía real de vendedores, no solo un descenso moderado. **Parámetro a validar en backtest**, como el resto de umbrales del proyecto (sección 8 del diseño original).

### Cambios en `ict.py`

- `BuecResult`: añadir campo `low_volume: bool`.
- `_is_low_volume_candle(df, index, lookback=10, fraction=0.5) -> bool`: nueva función pura, mismo estilo que `_is_no_supply_candle` (usa `.iloc`, sin mirar hacia adelante).
- `find_buec(...)`: nuevo parámetro `low_volume_fraction: float = 0.5`. Reutiliza la misma ventana `no_supply_lookback` para `_is_low_volume_candle` (no se añade un lookback separado — mismo espíritu de reutilización que ya aplica `no_supply_lookback` a `_is_no_supply_candle`). El disparo pasa de `volume_declining or no_supply` a `volume_declining or no_supply or low_volume`.
- `find_entry_3_signal(...)`: nuevo parámetro `low_volume_fraction: float = 0.5`, propagado a `find_buec`. **Decisión inicial, superada — ver Addendum**: `high_confidence` iba a pasar de `buec.no_supply` a `buec.no_supply or buec.low_volume`. La revisión final encontró que esto admitía velas de distribución reales; la decisión final usa un criterio dedicado (`_is_high_confidence_buec_candle`), no `buec.low_volume` directamente.

### Compatibilidad

`low_volume_fraction` con valor por defecto no cambia el comportamiento de ningún test existente que no lo pase explícitamente para los casos donde antes no se detectaba ningún BUEC. **Corrección (ver Addendum)**: esto no cubre todos los casos — `find_buec` devuelve el primer candidato (recorriendo velas en orden) que cumple *cualquiera* de los criterios, así que un nuevo match por `low_volume` en una vela más temprana que un `no_supply`/`volume_declining` preexistente **desplaza** cuál vela se detecta como BUEC, cambiando `entry_price`/`stop_loss` de una señal que ya existía antes de esta revisión, no solo añadiendo detecciones donde antes había `None`. Este comportamiento de precedencia (primer candidato que cumple cualquier criterio) es el mismo que ya regía entre `volume_declining` y `no_supply` antes de esta revisión — no es nuevo en su mecánica, pero `low_volume` amplía las oportunidades de que se dispare en una vela distinta a la que se habría detectado antes. Cubierto con un test explícito de precedencia.

## Addendum (2026-08-12) — fixes de la revisión final antes de fusionar

La revisión final de rama (modelo más capaz) encontró 2 hallazgos Important, ambos corregidos aquí antes de fusionar a `main`:

1. **`high_confidence` admitía velas de distribución reales.** `high_confidence = buec.no_supply or buec.low_volume` dejaba pasar como señal de máxima confianza cualquier vela con volumen bajo, sin exigir nada sobre su forma — incluida una vela bajista de rango ancho cerrando cerca de su mínimo (el perfil clásico de una vela de distribución, justo lo contrario de "ausencia de vendedores"). **Resuelto**: se sustituye `buec.low_volume` en el cálculo de `high_confidence` por un criterio dedicado y más estricto que el de detección — nueva función `_is_high_confidence_buec_candle`: vela **bajista, de rango estrecho, con cierre en el 75% superior de su rango** (más exigente que el 50% de `_is_no_supply_candle`), y con volumen muy bajo respecto a la **mediana de las 4 velas previas** (ventana más corta y sensible que las 10 usadas para la detección base — a petición explícita del usuario, ya que un dry-up de volumen reciente es más significativo comparado contra un puñado de velas inmediatas que diluido en una ventana de 10). El campo `low_volume` de `BuecResult` y su uso en el disparo de `find_buec` (`volume_declining or no_supply or low_volume`) **no cambian** — siguen sirviendo para la detección (activar la Entrada 3), solo se retira su uso directo en `high_confidence`.

2. **La afirmación de compatibilidad era incorrecta.** El documento decía "solo añade casos nuevos que antes devolvían `None`" — falso: `find_buec` devuelve el **primer** candidato que cumple cualquier criterio, así que un nuevo match por `low_volume` en una vela más temprana puede desplazar un BUEC que antes se detectaba en una vela posterior por `no_supply`, cambiando `entry_price`/`stop_loss` de señales que ya existían antes de esta revisión. **Resuelto**: se corrige esta afirmación (ver más abajo) y se añade un test que fija explícitamente esta precedencia (primer candidato que cumple cualquier criterio, sin importar cuál).

### Task 1 — Tercer criterio de confirmación BUEC en `ict.py`

Implementar los cambios de diseño anteriores en `weinstein_screener/ict.py`, con tests que cubran:
- Vela con volumen muy bajo (≤50% de la mediana de las 10 previas) que toca la banda, sin ser rango estrecho ni bajista → antes `None`, ahora `BuecResult(low_volume=True, ...)`.
- Vela con volumen normal (>50% de la mediana) que toca la banda y no cumple ningún otro criterio → sigue `None`.
- Caso con un pico de volumen dentro de la ventana de 10 semanas previas → la mediana (no la media) determina el resultado (test de regresión directo sobre `_is_low_volume_candle`, con el mismo escenario numérico verificado arriba).
- `find_entry_3_signal`: `high_confidence=True` cuando el BUEC se confirma solo por `low_volume` (sin `no_supply`). **Superado por el Addendum**: `high_confidence` ya no depende directamente de `buec.low_volume` — el test real cubre `_is_high_confidence_buec_candle` en su lugar.
- Los tests existentes de `test_ict.py` siguen pasando sin modificación.
