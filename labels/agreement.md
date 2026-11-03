# Judge vs human agreement

98 frames, 609 claims. Agreement 0.81, Cohen's kappa 0.66 over present/absent/unclear, 0.74 on present vs not (the distinction the scores use).

Rough reading of kappa: above 0.8 strong, 0.6-0.8 substantial, 0.4-0.6 moderate, below 0.4 weak.

| Group | Claims | Agreement | Kappa | Present kappa |
|---|---|---|---|---|
| kind: atmosphere | 98 | 0.95 | 0.27 | 0.27 |
| kind: feature | 77 | 0.82 | 0.56 | 0.72 |
| kind: ground | 98 | 0.68 | 0.41 | 0.47 |
| kind: landmark | 63 | 0.86 | 0.70 | 0.81 |
| kind: person | 231 | 0.77 | 0.55 | 0.62 |
| kind: stale | 42 | 0.98 | 0.92 | 1.00 |
| run: abot-image-drive-seed42 | 87 | 0.85 | 0.73 | 0.79 |
| run: abot-image-seed42 | 87 | 0.79 | 0.63 | 0.77 |
| run: abot-preset-seed42 | 87 | 0.95 | 0.85 | 0.96 |
| run: eden-image-drive-seed42 | 87 | 0.75 | 0.53 | 0.56 |
| run: eden-image-seed42 | 87 | 0.74 | 0.53 | 0.57 |
| run: lingbot-image-drive-seed42 | 87 | 0.82 | 0.67 | 0.81 |
| run: lingbot-image-seed42 | 87 | 0.79 | 0.63 | 0.70 |

## Confusion

- human absent / judge absent: 271
- human absent / judge present: 13
- human absent / judge unclear: 16
- human present / judge absent: 44
- human present / judge present: 220
- human present / judge unclear: 15
- human unclear / judge absent: 19
- human unclear / judge present: 7
- human unclear / judge unclear: 4
