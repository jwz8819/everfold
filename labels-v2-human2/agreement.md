# Agreement: human2 vs judge

50 frames, 319 claims. Agreement 0.78, Cohen's kappa 0.59 over present/absent/unclear, 0.65 on present vs not (the distinction the scores use).

Rough reading of kappa: above 0.8 strong, 0.6-0.8 substantial, 0.4-0.6 moderate, below 0.4 weak.

| Group | Claims | Agreement | Kappa | Present kappa |
|---|---|---|---|---|
| kind: atmosphere | 50 | 0.92 | 0.00 | 0.00 |
| kind: feature | 36 | 0.86 | 0.73 | 0.78 |
| kind: ground | 50 | 0.66 | 0.32 | 0.32 |
| kind: landmark | 51 | 0.80 | 0.64 | 0.68 |
| kind: person | 116 | 0.72 | 0.49 | 0.58 |
| kind: stale | 16 | 1.00 | 1.00 | 1.00 |
| run: abot-image-drive-seed1 | 14 | 0.57 | 0.16 | 0.07 |
| run: abot-image-drive-seed10 | 12 | 0.92 | 0.80 | 0.80 |
| run: abot-image-drive-seed11 | 12 | 0.83 | 0.70 | 0.80 |
| run: abot-image-drive-seed12 | 17 | 0.71 | 0.40 | 0.68 |
| run: abot-image-drive-seed13 | 12 | 0.75 | 0.47 | 0.47 |
| run: abot-image-drive-seed14 | 10 | 0.90 | 0.80 | 0.80 |
| run: abot-image-seed1 | 14 | 0.79 | 0.58 | 0.55 |
| run: abot-image-seed2 | 10 | 0.80 | 0.60 | 0.60 |
| run: abot-image-seed3 | 9 | 0.78 | -0.06 | -0.12 |
| run: abot-image-seed4 | 12 | 0.83 | 0.65 | 0.64 |
| run: abot-image-seed5 | 12 | 0.83 | 0.67 | 0.67 |
| run: flux-oracle-seed1 | 14 | 0.79 | 0.58 | 0.70 |
| run: flux-oracle-seed10 | 14 | 0.86 | 0.44 | 0.44 |
| run: flux-oracle-seed11 | 9 | 0.89 | 0.70 | 1.00 |
| run: flux-oracle-seed12 | 16 | 0.56 | 0.07 | 0.14 |
| run: flux-oracle-seed13 | 14 | 0.86 | 0.70 | 0.70 |
| run: lingbot-image-drive-seed1 | 11 | 0.82 | 0.62 | 0.62 |
| run: lingbot-image-drive-seed10 | 10 | 0.70 | 0.47 | 0.60 |
| run: lingbot-image-drive-seed11 | 11 | 0.64 | 0.00 | 0.00 |
| run: lingbot-image-drive-seed2 | 14 | 0.86 | 0.72 | 0.72 |
| run: lingbot-image-drive-seed3 | 11 | 0.82 | 0.64 | 0.79 |
| run: lingbot-image-seed1 | 11 | 0.73 | 0.48 | 0.48 |
| run: lingbot-image-seed2 | 17 | 0.82 | 0.64 | 0.64 |
| run: lingbot-image-seed3 | 15 | 1.00 | 1.00 | 1.00 |
| run: lingbot-image-seed4 | 18 | 0.67 | 0.46 | 0.67 |

## Confusion

- human2 absent / judge absent: 103
- human2 absent / judge present: 30
- human2 absent / judge unclear: 13
- human2 present / judge absent: 18
- human2 present / judge present: 146
- human2 present / judge unclear: 7
- human2 unclear / judge present: 1
- human2 unclear / judge unclear: 1
