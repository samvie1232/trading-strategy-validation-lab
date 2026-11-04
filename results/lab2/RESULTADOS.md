# Resultados del Lab v2 (4 de noviembre de 2026)
Hipótesis y criterios: [`PREREGISTRO.md`](PREREGISTRO.md). Datos de XM (cuenta demo). **Ninguna de las 6 familias aprueba.**

| Familia | Fuera de muestra | Ops | Sharpe preregistrado | Sharpe swap corregido | Sharpe sin swap | Sharpe sin costos | Deflated Sharpe |
|---|---|---:|---:|---:|---:|---:|---:|
| H1 RSI2 diario, índices | 2017-2026 | 253 | 0,19 | 0,31 | 0,42 | 0,45 | 0,10 |
| H2 RSI2 M30, oro y US500 | 2023-2026 | 1.234 | -0,65 | -0,63 | -0,58 | 0,53 | 0,01 |
| H3 Ruptura H1, oro | 2023-2026 | 1.084 | -1,61 | -1,52 | -1,37 | -0,74 | 0,00 |
| H4 Salidas cortas | 2023-2026 | 2.572 | -2,07 | -2,01 | -1,87 | 0,42 | 0,00 |
| H5 Salidas + filtro de costo | 2023-2026 | 1.248 | -0,82 | -0,79 | -0,67 | 0,16 | 0,00 |
| H6 Oro/plata | 2017-2026 | 85 | -1,66 | -1,07 | -0,72 | -0,51 | 0,00 |

Operaciones y Deflated Sharpe corresponden a la corrida preregistrada. El Sharpe mínimo exigido es 0,5.

## Comparación con el azar (criterio 8)
- H4: -0,054R por operación; p95 de azar -0,052R; percentil 93.
- H5: -0,018R por operación; p95 de azar -0,013R; percentil 92.

## Controles
Registro en [`controls.log`](controls.log).
- Causalidad y costos: sin fallas.
- Negativo: 0 de 18 corridas barajadas aprueba.
- Positivo: las 6 familias detectan el efecto plantado.
- Una operación de H4 recalculada a mano coincidió con el motor (0,4416R).

## Sensibilidad al swap
No existe swap histórico. La corrida preregistrada usa `legacy_fixed`: fija el swap actual en puntos o moneda y lo divide por el precio de cada fecha. Eso sobreestima el costo cuando el precio era menor (oro 2017: -22,8 % anual frente a -6,4 % en 2026). Desde esta versión, el valor por defecto es `constant_pct`. Ambos modelos usan tasas de hoy, así que tampoco reflejan los años de tasas bajas; por eso también se reporta sin swap. Ningún veredicto cambia.

## Limitaciones
- Preregistro interno: no hay un tercero que certifique la fecha.
- Dos enmiendas previas a los resultados reales están descritas en el preregistro.
- Spread de cuenta demo; deslizamiento supuesto, no medido en vivo.
- En velas de M30 se desconoce el orden de precios dentro de la vela; se asume el stop primero.
- H4 y H5 comparten reglas, así que sus operaciones no son independientes.
- La ruptura usa velas H1 agregadas desde M30. GoldGuardian no se probó en este motor por falta de M15.
