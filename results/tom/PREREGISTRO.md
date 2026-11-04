# Preregistro H8: cambio de mes en índices
Fecha: 2026-11-04. Escrito antes de correr esta prueba con datos reales.

**Conocimiento previo:** conozco el efecto por la literatura y mencioné que puede haberse reducido. Ya usé estos mismos índices en H1, así que los datos no son nuevos para mí; H8 no reutiliza reglas de H1.

## Fundamento
Flujos previsibles alrededor de fin de mes (salarios, pensiones, rebalanceos) podrían elevar los retornos de los índices en esos días.

## Datos
XM D1: US500Cash, US100Cash, US30Cash y GER40Cash, desde 2015. Fuera de muestra desde 2017. Cuenta demo.

## Reglas
- Solo compras. Entrada a la apertura del día hábil indicado antes del fin de mes, por calendario de días hábiles.
- Salida al cierre de la vela N del mes nuevo. Sin stop.
- Tamaño: 10 % de volatilidad objetivo con volatilidad de 60 días rezagada, máximo 3x.
- Costos: spread de la vela + 25 % de deslizamiento; swap como % constante del nocional. Estrés: costos x2.

## Parámetros (4)
Entrada {último día hábil, penúltimo} x salida {vela 2, vela 3 del mes nuevo}.

## Validación y criterios (todos obligatorios)
Walk-forward de 2 años / 6 meses, seleccionando por Sharpe de entrenamiento.
1. Operaciones OOS >= 100
2. Sharpe OOS >= 0,5
3. Eficiencia walk-forward >= 0,5
4. Ventanas OOS positivas >= 55 %
5. Caída p95 Monte Carlo <= 25 %
6. Sharpe con doble costo >= 0,2
7. Deflated Sharpe >= 0,95, con N = 53 (49 + 4)
8. Resultado medio por operación por encima del percentil 95 de ventanas al azar de igual duración, una por mes, con el mismo tamaño y costos. Separa el efecto de fin de mes de la simple subida del mercado.

## Controles
- Negativo: velas barajadas, 5 semillas. Ninguna debe aprobar.
- Positivo: retorno plantado en esos días. Debe aprobar.
- Causalidad y monotonía de costos.

## Contexto (no decide)
Comprar y mantener con swap, resultado por índice, últimos 24 meses y sensibilidad sin swap.
