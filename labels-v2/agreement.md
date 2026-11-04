# Agreement: human1 vs judge

50 frames, 319 claims. Agreement 0.79, Cohen's kappa 0.60 over present/absent/unclear, 0.66 on present vs not (the distinction the scores use).

Rough reading of kappa: above 0.8 strong, 0.6-0.8 substantial, 0.4-0.6 moderate, below 0.4 weak.

| Group | Claims | Agreement | Kappa | Present kappa |
|---|---|---|---|---|
| kind: atmosphere | 50 | 0.90 | 0.00 | 0.00 |
| kind: feature | 36 | 0.86 | 0.73 | 0.78 |
| kind: ground | 50 | 0.72 | 0.44 | 0.44 |
| kind: landmark | 51 | 0.86 | 0.75 | 0.80 |
| kind: person | 116 | 0.69 | 0.44 | 0.53 |
| kind: stale | 16 | 1.00 | 1.00 | 1.00 |
| run: abot-image-drive-seed1 | 14 | 0.64 | 0.38 | 0.43 |
| run: abot-image-drive-seed10 | 12 | 1.00 | 1.00 | 1.00 |
| run: abot-image-drive-seed11 | 12 | 0.75 | 0.53 | 0.56 |
| run: abot-image-drive-seed12 | 17 | 0.71 | 0.43 | 0.56 |
| run: abot-image-drive-seed13 | 12 | 0.75 | 0.47 | 0.47 |
| run: abot-image-drive-seed14 | 10 | 0.90 | 0.80 | 0.80 |
| run: abot-image-seed1 | 14 | 0.86 | 0.70 | 0.69 |
| run: abot-image-seed2 | 10 | 0.80 | 0.60 | 0.60 |
| run: abot-image-seed3 | 9 | 0.89 | 0.00 | 0.00 |
| run: abot-image-seed4 | 12 | 0.92 | 0.83 | 0.82 |
| run: abot-image-seed5 | 12 | 0.75 | 0.53 | 0.53 |
| run: flux-oracle-seed1 | 14 | 0.71 | 0.46 | 0.55 |
| run: flux-oracle-seed10 | 14 | 0.86 | 0.44 | 0.44 |
| run: flux-oracle-seed11 | 9 | 0.78 | 0.50 | 0.73 |
| run: flux-oracle-seed12 | 16 | 0.56 | 0.03 | 0.14 |
| run: flux-oracle-seed13 | 14 | 0.93 | 0.84 | 0.84 |
| run: lingbot-image-drive-seed1 | 11 | 0.91 | 0.79 | 0.79 |
| run: lingbot-image-drive-seed10 | 10 | 0.60 | 0.32 | 0.40 |
| run: lingbot-image-drive-seed11 | 11 | 0.64 | 0.00 | 0.00 |
| run: lingbot-image-drive-seed2 | 14 | 0.79 | 0.57 | 0.57 |
| run: lingbot-image-drive-seed3 | 11 | 0.82 | 0.64 | 0.79 |
| run: lingbot-image-seed1 | 11 | 0.73 | 0.41 | 0.38 |
| run: lingbot-image-seed2 | 17 | 0.88 | 0.76 | 0.76 |
| run: lingbot-image-seed3 | 15 | 1.00 | 1.00 | 1.00 |
| run: lingbot-image-seed4 | 18 | 0.67 | 0.47 | 0.66 |

## Confusion

- human1 absent / judge absent: 102
- human1 absent / judge present: 24
- human1 absent / judge unclear: 13
- human1 present / judge absent: 19
- human1 present / judge present: 150
- human1 present / judge unclear: 8
- human1 unclear / judge present: 3
