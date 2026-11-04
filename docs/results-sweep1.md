# Everfold results across seeds

Mean over seeds with a 95% bootstrap interval (seed is the unit); n = seeds where the probe could be scored. n/a: the camera never moved, so the probe could not be tested.

| Condition | Seeds | Cross-view | Revisit | Propagation | Identity | Shrine | Static camera | $/run |
|---|---|---|---|---|---|---|---|---|
| abot-image | 8 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=8 | 81% [73%, 90%] n=8 | 0.27 |
| abot-image-drive | 20 | 0% [0%, 0%] n=19 | 15% [5%, 27%] n=19 | 2% [0%, 8%] n=20 | 13% [5%, 22%] n=20 | 0% [0%, 0%] n=20 | 1% [0%, 2%] n=20 | 0.39 |
| abot-preset | 1 | n/a | n/a | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | 0.18 |
| eden-image | 1 | n/a | n/a | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | 1.60 |
| eden-image-drive | 1 | 100% [100%, 100%] n=1 | 33% [33%, 33%] n=1 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 17% [17%, 17%] n=1 | 2.61 |
| flux-oracle | 20 | 95% [85%, 100%] n=20 | 89% [80%, 96%] n=20 | 82% [72%, 92%] n=20 | 37% [22%, 52%] n=20 | 30% [10%, 50%] n=20 | 0% [0%, 0%] n=20 | 0.04 |
| lingbot-image | 8 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=8 | 85% [75%, 96%] n=8 | 0.30 |
| lingbot-image-drive | 12 | 8% [0%, 25%] n=12 | 19% [7%, 32%] n=12 | 0% [0%, 0%] n=12 | 22% [8%, 36%] n=12 | 0% [0%, 0%] n=12 | 0% [0%, 0%] n=12 | 0.69 |
| reference | 1 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | n/a |

## Fact recall by kind (mean over seeds)

| Condition | atmosphere | feature | ground | landmark | person |
|---|---|---|---|---|---|
| abot-image | 100% | 17% | 72% | 40% | 44% |
| abot-image-drive | 99% | 26% | 70% | 37% | 39% |
| abot-preset | 100% | 9% | 0% | 0% | 0% |
| eden-image | 100% | 46% | 57% | 67% | 39% |
| eden-image-drive | 100% | 27% | 50% | 22% | 55% |
| flux-oracle | 100% | 72% | 76% | 70% | 58% |
| lingbot-image | 100% | 34% | 64% | 57% | 46% |
| lingbot-image-drive | 98% | 27% | 57% | 38% | 45% |
| reference | 86% | 0% | 71% | 22% | 0% |
