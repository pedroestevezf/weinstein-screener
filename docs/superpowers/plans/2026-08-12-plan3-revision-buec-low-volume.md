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
- `find_entry_3_signal(...)`: nuevo parámetro `low_volume_fraction: float = 0.5`, propagado a `find_buec`. **Decisión**: `high_confidence` pasa de `buec.no_supply` a `buec.no_supply or buec.low_volume` — un BUEC confirmado por ausencia real de vendedores (por cualquiera de las dos rutas de "poco volumen") es la señal de mayor calidad de las tres, igual que ya trataba `no_supply` en solitario.

### Compatibilidad

`low_volume_fraction` con valor por defecto no cambia el comportamiento de ningún test existente que no lo pase explícitamente — solo añade casos nuevos que antes devolvían `None`. Los tests existentes de `test_ict.py` deben seguir pasando sin modificación salvo que alguno dependa implícitamente de que `find_buec` devuelva `None` en un caso donde ahora `low_volume` se cumple (a revisar por el implementador).

### Task 1 — Tercer criterio de confirmación BUEC en `ict.py`

Implementar los cambios de diseño anteriores en `weinstein_screener/ict.py`, con tests que cubran:
- Vela con volumen muy bajo (≤50% de la mediana de las 10 previas) que toca la banda, sin ser rango estrecho ni bajista → antes `None`, ahora `BuecResult(low_volume=True, ...)`.
- Vela con volumen normal (>50% de la mediana) que toca la banda y no cumple ningún otro criterio → sigue `None`.
- Caso con un pico de volumen dentro de la ventana de 10 semanas previas → la mediana (no la media) determina el resultado (test de regresión directo sobre `_is_low_volume_candle`, con el mismo escenario numérico verificado arriba).
- `find_entry_3_signal`: `high_confidence=True` cuando el BUEC se confirma solo por `low_volume` (sin `no_supply`).
- Los tests existentes de `test_ict.py` siguen pasando sin modificación.
