# Ficha técnica · EAD · factor de exposición

*Sección 6.10 · generada el 2026-09-20 desde `models/ead_lgd_v1.json`.*

| Campo | Valor |
|---|---|
| Variable respuesta | ead_at_default / requested_amount |
| Población | 671 créditos en default (DEV 351) |
| Método | baseline global (factor sobre monto desembolsado) |
| Parámetro | 0.4154 |
| Error (MAE en VAL) | 0.159 |
| Confirmación OOT | 0.4301 |
| Limitación principal | La exposición del archivo no es coherente con el calendario de amortización (hallazgo V-01) |
| Uso | Pérdida esperada, pricing y stress (6.9 y 6.12) |
