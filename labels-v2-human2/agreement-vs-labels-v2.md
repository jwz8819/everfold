# Agreement: human2 vs human1

50 frames, 319 claims. Agreement 0.91, Cohen's kappa 0.81 over present/absent/unclear, 0.82 on present vs not (the distinction the scores use).

Rough reading of kappa: above 0.8 strong, 0.6-0.8 substantial, 0.4-0.6 moderate, below 0.4 weak.

| Group | Claims | Agreement | Kappa | Present kappa |
|---|---|---|---|---|
| kind: atmosphere | 50 | 0.96 | 0.76 | 0.88 |
| kind: feature | 36 | 1.00 | 1.00 | 1.00 |
| kind: ground | 50 | 0.92 | 0.83 | 0.87 |
| kind: landmark | 51 | 0.86 | 0.73 | 0.73 |
| kind: person | 116 | 0.85 | 0.71 | 0.71 |
| kind: stale | 16 | 1.00 | 1.00 | 1.00 |
| run: abot-image-drive-seed1 | 14 | 0.86 | 0.71 | 0.71 |
| run: abot-image-drive-seed10 | 12 | 0.92 | 0.80 | 0.80 |
| run: abot-image-drive-seed11 | 12 | 0.75 | 0.52 | 0.40 |
| run: abot-image-drive-seed12 | 17 | 0.94 | 0.87 | 0.87 |
| run: abot-image-drive-seed13 | 12 | 1.00 | 1.00 | 1.00 |
| run: abot-image-drive-seed14 | 10 | 0.80 | 0.61 | 0.61 |
| run: abot-image-seed1 | 14 | 0.93 | 0.85 | 0.85 |
| run: abot-image-seed2 | 10 | 0.80 | 0.60 | 0.60 |
| run: abot-image-seed3 | 9 | 0.89 | 0.00 | 0.00 |
| run: abot-image-seed4 | 12 | 0.92 | 0.80 | 0.80 |
| run: abot-image-seed5 | 12 | 0.92 | 0.83 | 0.83 |
| run: flux-oracle-seed1 | 14 | 0.93 | 0.84 | 0.84 |
| run: flux-oracle-seed10 | 14 | 1.00 | 1.00 | 1.00 |
| run: flux-oracle-seed11 | 9 | 0.89 | 0.73 | 0.73 |
| run: flux-oracle-seed12 | 16 | 0.88 | 0.68 | 0.67 |
| run: flux-oracle-seed13 | 14 | 0.93 | 0.85 | 0.85 |
| run: lingbot-image-drive-seed1 | 11 | 0.91 | 0.81 | 0.81 |
| run: lingbot-image-drive-seed10 | 10 | 0.80 | 0.62 | 0.78 |
| run: lingbot-image-drive-seed11 | 11 | 1.00 | 1.00 | 1.00 |
| run: lingbot-image-drive-seed2 | 14 | 0.93 | 0.86 | 0.86 |
| run: lingbot-image-drive-seed3 | 11 | 1.00 | 1.00 | 1.00 |
| run: lingbot-image-seed1 | 11 | 0.73 | 0.52 | 0.65 |
| run: lingbot-image-seed2 | 17 | 0.94 | 0.88 | 0.88 |
| run: lingbot-image-seed3 | 15 | 1.00 | 1.00 | 1.00 |
| run: lingbot-image-seed4 | 18 | 0.89 | 0.78 | 0.78 |

## Confusion

- human2 absent / human1 absent: 129
- human2 absent / human1 present: 15
- human2 absent / human1 unclear: 2
- human2 present / human1 absent: 10
- human2 present / human1 present: 160
- human2 present / human1 unclear: 1
- human2 unclear / human1 present: 2
