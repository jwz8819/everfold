# Everfold results across seeds

Mean over seeds with a 95% bootstrap interval (seed is the unit); n = seeds where the probe could be scored. n/a: the camera never moved, so the probe could not be tested.

| Condition | Seeds | Cross-view | Revisit | Propagation | Identity | Shrine | Static camera | $/run |
|---|---|---|---|---|---|---|---|---|
| abot-image | 8 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=8 | 81% [73%, 90%] n=8 | 0.27 |
| abot-image-drive | 20 | 0% [0%, 0%] n=19 | 0% [0%, 0%] n=19 | 0% [0%, 0%] n=20 | 7% [2%, 13%] n=20 | 0% [0%, 0%] n=20 | 1% [0%, 2%] n=20 | 0.39 |
| abot-preset | 1 | n/a | n/a | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | 0.18 |
| eden-image | 1 | n/a | n/a | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | 1.60 |
| eden-image-drive | 1 | 100% [100%, 100%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 17% [17%, 17%] n=1 | 2.61 |
| flux-oracle | 20 | 95% [85%, 100%] n=20 | 89% [76%, 98%] n=20 | 30% [12%, 50%] n=20 | 20% [10%, 33%] n=20 | 0% [0%, 0%] n=20 | 0% [0%, 0%] n=20 | 0.04 |
| lingbot-image | 8 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=8 | 85% [75%, 96%] n=8 | 0.30 |
| lingbot-image-drive | 12 | 8% [0%, 25%] n=12 | 7% [0%, 17%] n=12 | 0% [0%, 0%] n=12 | 8% [0%, 17%] n=12 | 0% [0%, 0%] n=12 | 0% [0%, 0%] n=12 | 0.69 |
| reference | 1 | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | n/a |

## Fact recall by kind (mean over seeds)

| Condition | atmosphere | feature | ground | landmark | person |
|---|---|---|---|---|---|
| abot-image | 100% | 16% | 74% | 28% | 28% |
| abot-image-drive | 100% | 26% | 70% | 24% | 19% |
| abot-preset | 100% | 0% | 0% | 0% | 0% |
| eden-image | 100% | 36% | 50% | 44% | 27% |
| eden-image-drive | 100% | 27% | 50% | 33% | 27% |
| flux-oracle | 100% | 63% | 76% | 58% | 34% |
| lingbot-image | 100% | 32% | 67% | 44% | 27% |
| lingbot-image-drive | 98% | 27% | 58% | 31% | 25% |
| reference | 71% | 0% | 86% | 22% | 0% |
