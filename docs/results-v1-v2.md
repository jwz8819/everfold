# Everfold results: claim wording v1 vs v2

Mean over seeds, 95% bootstrap interval (seed is the unit). v2 = claim wording of 2026-11-03 (commit c3744f7); prompts and frames identical, every frame re-judged. n/a: camera never moved, so the probe cannot be tested.

| Condition | Wording | Seeds | Cross-view | Revisit | Propagation | Identity | Shrine | Static camera |
|---|---|---|---|---|---|---|---|---|
| flux-oracle | v1 | 20 | 95% [85%, 100%] | 89% [76%, 98%] | 30% [12%, 50%] | 20% [10%, 33%] | 0% [0%, 0%] | 0% [0%, 0%] |
|  | v2 | 20 | 95% [85%, 100%] | 89% [80%, 96%] | 82% [72%, 92%] | 37% [22%, 52%] | 30% [10%, 50%] | 0% [0%, 0%] |
| abot-image-drive | v1 | 20 | 0% [0%, 0%] | 0% [0%, 0%] | 0% [0%, 0%] | 7% [2%, 13%] | 0% [0%, 0%] | 1% [0%, 2%] |
|  | v2 | 20 | 0% [0%, 0%] | 15% [5%, 27%] | 2% [0%, 8%] | 13% [5%, 22%] | 0% [0%, 0%] | 1% [0%, 2%] |
| lingbot-image-drive | v1 | 12 | 8% [0%, 25%] | 7% [0%, 17%] | 0% [0%, 0%] | 8% [0%, 17%] | 0% [0%, 0%] | 0% [0%, 0%] |
|  | v2 | 12 | 8% [0%, 25%] | 19% [7%, 32%] | 0% [0%, 0%] | 22% [8%, 36%] | 0% [0%, 0%] | 0% [0%, 0%] |
| abot-image | v1 | 8 | 0% | n/a | 0% [0%, 0%] | 0% | 0% [0%, 0%] | 81% [73%, 90%] |
|  | v2 | 8 | 0% | n/a | 0% [0%, 0%] | 0% | 0% [0%, 0%] | 81% [73%, 90%] |
| lingbot-image | v1 | 8 | 0% | n/a | 0% [0%, 0%] | 0% | 0% [0%, 0%] | 85% [75%, 96%] |
|  | v2 | 8 | 0% | n/a | 0% [0%, 0%] | 0% | 0% [0%, 0%] | 85% [75%, 96%] |
| eden-image-drive | v1 | 1 | 100% | 0% | 0% | n/a | 0% | 17% |
|  | v2 | 1 | 100% | 33% | 0% | n/a | 0% | 17% |
| eden-image | v1 | 1 | n/a | n/a | 0% | n/a | 0% | 100% |
|  | v2 | 1 | n/a | n/a | 0% | n/a | 0% | 100% |
| abot-preset | v1 | 1 | n/a | n/a | 0% | n/a | 0% | 100% |
|  | v2 | 1 | n/a | n/a | 0% | n/a | 0% | 100% |
| reference | v1 | 1 | 0% | 100% | 0% | 0% | 0% | 0% |
|  | v2 | 1 | 0% | n/a | 0% | 0% | 0% | 0% |

## Fact recall by kind, v1 → v2

| Condition | landmark | person | feature | ground |
|---|---|---|---|---|
| flux-oracle | 58% → 70% | 34% → 58% | 63% → 72% | 76% → 76% |
| abot-image-drive | 24% → 37% | 19% → 39% | 26% → 26% | 70% → 70% |
| lingbot-image-drive | 31% → 38% | 25% → 45% | 27% → 27% | 58% → 57% |
| abot-image | 28% → 40% | 28% → 44% | 16% → 17% | 74% → 72% |
| lingbot-image | 44% → 57% | 27% → 46% | 32% → 34% | 67% → 64% |
| eden-image-drive | 33% → 22% | 27% → 55% | 27% → 27% | 50% → 50% |
| eden-image | 44% → 67% | 27% → 39% | 36% → 46% | 50% → 57% |
| abot-preset | 0% → 0% | 0% → 0% | 0% → 9% | 0% → 0% |
| reference | 22% → 22% | 0% → 0% | 0% → 0% | 86% → 71% |
