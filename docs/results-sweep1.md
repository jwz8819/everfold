# Everfold results across seeds

Mean over seeds with a 95% bootstrap interval (seed is the unit); n = seeds where the probe could be scored. n/a: the camera never moved, so the probe could not be tested.

| Condition | Seeds | Cross-view | Same tower | Revisit | Propagation | Identity | Shrine | Static camera | $/run |
|---|---|---|---|---|---|---|---|---|---|
| abot-image | 8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=8 | 81% [73%, 90%] n=8 | 0.27 |
| abot-image-2p | 20 | 75% [55%, 90%] n=20 | 5% [0%, 15%] n=20 | n/a | n/a | n/a | n/a | 0% [0%, 0%] n=20 | 0.06 |
| abot-image-drive | 20 | 0% [0%, 0%] n=19 | 0% [0%, 0%] n=19 | 15% [5%, 27%] n=19 | 2% [0%, 8%] n=20 | 13% [5%, 22%] n=20 | 0% [0%, 0%] n=20 | 1% [0%, 2%] n=20 | 0.39 |
| abot-preset | 1 | n/a | n/a | n/a | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | 0.18 |
| eden-image | 1 | n/a | n/a | n/a | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | 1.60 |
| eden-image-drive | 1 | 100% [100%, 100%] n=1 | 100% [100%, 100%] n=1 | 33% [33%, 33%] n=1 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=1 | 17% [17%, 17%] n=1 | 2.61 |
| flux-oracle | 20 | 95% [85%, 100%] n=20 | 10% [0%, 25%] n=20 | 89% [80%, 96%] n=20 | 82% [72%, 92%] n=20 | 37% [22%, 52%] n=20 | 30% [10%, 50%] n=20 | 0% [0%, 0%] n=20 | 0.04 |
| lingbot-image | 8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | n/a | 0% [0%, 0%] n=8 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=8 | 85% [75%, 96%] n=8 | 0.30 |
| lingbot-image-2p | 20 | 80% [60%, 95%] n=20 | 0% [0%, 0%] n=20 | n/a | n/a | n/a | n/a | 0% [0%, 0%] n=20 | 0.09 |
| lingbot-image-drive | 12 | 8% [0%, 25%] n=12 | 0% [0%, 0%] n=12 | 19% [7%, 32%] n=12 | 0% [0%, 0%] n=12 | 22% [8%, 36%] n=12 | 0% [0%, 0%] n=12 | 0% [0%, 0%] n=12 | 0.69 |
| reference | 1 | 0% [0%, 0%] n=1 | 100% [100%, 100%] n=1 | n/a | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | 0% [0%, 0%] n=1 | n/a |

## Fact recall by kind (mean over seeds)

| Condition | atmosphere | feature | ground | landmark | person |
|---|---|---|---|---|---|
| abot-image | 100% | 17% | 72% | 40% | 44% |
| abot-image-2p | 100% | n/a | 90% | 77% | 76% |
| abot-image-drive | 99% | 26% | 70% | 37% | 39% |
| abot-preset | 100% | 9% | 0% | 0% | 0% |
| eden-image | 100% | 46% | 57% | 67% | 39% |
| eden-image-drive | 100% | 27% | 50% | 22% | 55% |
| flux-oracle | 100% | 72% | 76% | 70% | 58% |
| lingbot-image | 100% | 34% | 64% | 57% | 46% |
| lingbot-image-2p | 100% | n/a | 85% | 79% | 78% |
| lingbot-image-drive | 98% | 27% | 57% | 38% | 45% |
| reference | 86% | 0% | 71% | 22% | 0% |

## Cost and latency (mean over seeds)

Player-hour: what one player's open session costs for an hour (fal list price per second x 3600). Ack: prompt sent to model confirms it. Response: prompt sent to the picture visibly changing (mean absolute pixel change of 12 or more). Responded: share of steps where the picture changed at all. Errors: moderation refusals and prompts never confirmed, per run.

| Condition | $/player-hour | $/run | Session s/run | Ack s | Response s | Frame s | Responded | Errors/run |
|---|---|---|---|---|---|---|---|---|
| abot-image | $4.50 | 0.27 | 204 | 1.9 | 4.7 | 6.2 | 43% | 2.5 |
| abot-image-2p | $4.50 | 0.06 | 42 | 2.3 | 2.4 | 4.8 | 65% | 0.0 |
| abot-image-drive | $4.50 | 0.39 | 304 | 1.8 | 1.8 | 4.1 | 74% | 2.7 |
| abot-preset | $4.50 | 0.18 | 146 | 0.7 | 4.7 | 5.7 | 7% | 0.0 |
| eden-image | $36.00 | 1.60 | 160 | 1.4 | 2.8 | 6.1 | 21% | 0.0 |
| eden-image-drive | $36.00 | 2.61 | 261 | 1.3 | 3.4 | 13.1 | 7% | 0.0 |
| flux-oracle | $0.003/image | 0.04 | n/a | n/a | n/a | 1.5 | n/a | 0.0 |
| lingbot-image | $4.50 | 0.30 | 232 | 3.9 | 3.0 | 7.9 | 54% | 2.0 |
| lingbot-image-2p | $4.50 | 0.09 | 66 | 9.2 | 10.1 | 15.1 | 8% | 0.1 |
| lingbot-image-drive | $4.50 | 0.69 | 538 | 3.9 | 1.6 | 6.3 | 62% | 1.8 |
| reference | n/a | n/a | n/a | n/a | n/a | 0.0 | n/a | n/a |
