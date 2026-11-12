# Measured Experiment Comparison

Scores are uncalibrated; all reconstructions remain partial. Equivalent uncached tokens include reused API responses, avoiding warm-cache cost bias. API seconds exclude deterministic processing and retries.

| Run | Status | Quality | Selected | Actual calls | Actual tokens | Equivalent uncached tokens | API seconds equivalent | Wall seconds observed | Cache hits |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| [smoke-bauhaus-direct](../runs/smoke-bauhaus-direct/index.html) | partial | 0.595 | 0 | 4 | 26,369 | 26,369 | 208.2 | 224.7 | 0 |
| [smoke-bauhaus-spec](../runs/smoke-bauhaus-spec/index.html) | failed | — | None | 1 | 6,503 | 6,503 | 54.9 | 55.5 | 0 |
| [smoke-bauhaus-spec-v2](../runs/smoke-bauhaus-spec-v2/index.html) | partial | 0.750 | 1 | 4 | 35,371 | 41,874 | 302.6 | 271.8 | 1 |
| [smoke-fallingwater-direct](../runs/smoke-fallingwater-direct/index.html) | partial | 0.460 | 0 | 4 | 25,968 | 25,968 | 206.5 | 230.9 | 0 |
| [smoke-fallingwater-spec](../runs/smoke-fallingwater-spec/index.html) | partial | 0.450 | 1 | 4 | 26,051 | 26,051 | 175.5 | 188.6 | 0 |
| [smoke-rietveld-camera](../runs/smoke-rietveld-camera/index.html) | partial | 0.702 | 1 | 2 | 10,372 | 32,901 | 204.9 | 62.0 | 3 |
| [smoke-rietveld-direct](../runs/smoke-rietveld-direct/index.html) | partial | 0.517 | 0 | 4 | 23,439 | 23,439 | 173.3 | 186.5 | 0 |
| [smoke-rietveld-spec](../runs/smoke-rietveld-spec/index.html) | failed | — | None | 1 | 6,814 | 6,814 | 59.4 | 60.1 | 0 |
| [smoke-rietveld-spec-v2](../runs/smoke-rietveld-spec-v2/index.html) | failed | — | None | 2 | 16,697 | 23,511 | 171.7 | 121.6 | 1 |
| [smoke-rietveld-spec-v3](../runs/smoke-rietveld-spec-v3/index.html) | partial | 0.648 | 0 | 3 | 20,990 | 37,510 | 237.2 | 111.1 | 2 |

Actual total including failed trials and independent review: **30 calls, 202,891 tokens**. USD cost unknown (no verified prices configured).
