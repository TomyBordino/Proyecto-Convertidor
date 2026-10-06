# TPO Teoría de Carteras — Perfil 3 (Gestión algorítmica)

**Perfil:** desarrollador freelancer de 25 años, sin cargas de familia, ingresos en moneda dura,
horizonte > 10 años → **perfil agresivo**. El foco de la materia es: activos de alta Beta,
renta variable y CEDEARs, y frontera eficiente (Unidades 2 y 3).

**Modalidad:** gestión algorítmica. El equipo define las reglas (`config.py`) antes del
06/10/2026. Desde ahí, **todas** las decisiones (armado, rebalanceos, ventas por alerta) las
toma `tpo.py`. Las personas solo cargan las órdenes en BymaLab y confirman la ejecución.

## Instalación

```bash
cd tpo-perfil3
pip install -r requirements.txt
python tpo.py armar --demo     # prueba con datos sintéticos (no usa internet)
```

Antes de empezar, poner en `config.py` el capital inicial real de BymaLab
(`CAPITAL_INICIAL_ARS`) y borrar `estado/` y `salidas/` si se hicieron pruebas.

## Uso durante las 4 semanas

| Cuándo | Comando | Qué hace |
|---|---|---|
| Día 1 (06/10) | `python tpo.py armar` | Selecciona activos y arma la cartera tangente |
| Cada lunes | `python tpo.py rebalancear` | Re-optimiza y genera órdenes (siempre hay al menos una, por reglamento) |
| Todos los días al cierre | `python tpo.py alertas` | Stops, quiebre de tendencia, desvíos de peso, drawdown |
| Después de operar | `python tpo.py confirmar` | Registra lo ejecutado en `estado/cartera.json` |
| Cuando quieran | `python tpo.py estado` | Valuación, pesos, Beta y resultado |

Flujo de cada operación:

1. Correr el comando → se genera `salidas/ultimas_ordenes.csv` (ticker, compra/venta, cantidad).
2. Cargar esas órdenes en BymaLab.
3. Si la cantidad o el precio real difieren, anotarlos en las columnas `cantidad_ejecutada`
   y `precio_ejecutado` del CSV.
4. `python tpo.py confirmar` y hacer commit de `estado/` y `salidas/`.

Si BymaLab muestra precios distintos a los de Yahoo, se puede crear `precios_manuales.csv`
(columnas `ticker,precio_ars`) para que las cantidades se calculen con esos precios.

### Alertas automáticas

El workflow `.github/workflows/tpo-alertas.yml` corre `alertas` de lunes a viernes a las
17:15 (hora argentina) en GitHub Actions. Si salta una alerta, abre un **Issue** en el repo con
las órdenes, y GitHub les avisa por mail / app. Para que funcione, `estado/cartera.json` tiene
que estar commiteado y pusheado después de cada `confirmar`.

## Metodología (para el informe)

1. **Datos.** Cierres diarios ajustados de 2 años de los subyacentes en USD (Yahoo Finance) y
   precio en pesos de BYMA (`.BA`) para dimensionar las órdenes. Trabajar en USD evita que la
   devaluación del peso distorsione retornos y covarianzas; es coherente con un inversor que
   cobra en moneda dura. Tasa libre de riesgo: T-Bill a 13 semanas (`^IRX`).
2. **Universo.** ~36 CEDEARs tecnológicos/growth, ETFs (QQQ, ARKK) y acciones argentinas vía
   sus ADR.
3. **Filtro de Beta.** Beta vs SPY (1 año) ≥ 1,0.
4. **Ranking.** Score = 45% momentum 12-1 + 30% Beta + 25% Sharpe (z-scores, recortados al
   5–95%). Se eligen los 10 mejores; un activo que ya está en cartera se mantiene mientras
   rankee entre los 13 primeros (histéresis, para evitar rotación y costos).
5. **Retorno esperado.** 50% CAPM (rf + β·prima de mercado 5,5%) + 50% media histórica
   (acotada entre −50% y +100%). La mezcla reduce el error de estimación de Markowitz.
6. **Riesgo.** Matriz de covarianzas anualizada, contraída 30% hacia su diagonal.
7. **Optimización.** Cartera tangente (máximo Sharpe) con pesos entre 4% y 20%, 2% de liquidez
   y Beta de cartera ≥ 1,2. Se exporta la frontera eficiente (CSV y PNG) en cada corrida.
8. **Rebalanceo semanal.** Se opera un activo si su peso difiere > 2 p.p. del objetivo o si
   entra/sale de la selección. Si nada supera la banda, se ajusta el mayor desvío (rebalanceo
   táctico obligatorio por reglamento).
9. **Alertas diarias.**
   - Stop trailing: −15% en USD desde el máximo posterior a la compra → venta total.
   - Quiebre de tendencia: −10% en 20 ruedas y precio bajo la media de 50 → vender la mitad.
   - Desvío de peso > 5 p.p. → volver al objetivo (toma de ganancia si sobrepondera).
   - Drawdown de cartera > 12% → no vende (horizonte largo), pero adelanta el rebalanceo.

   Lo vendido por alertas queda en efectivo hasta el próximo rebalanceo.

`salidas/bitacora.md` registra cada decisión del algoritmo con su justificación (ranking,
pesos, métricas y órdenes). Sirve como evidencia ante el comité de que las decisiones
fueron algorítmicas.
