# Third-party notices

Ascent Copilot's own code, documentation and seeded demo data were written by the team. The third-party
data, libraries and models below are used under their licences. Versions are those tested on 2026-10-19.

## Data included in this repository

| Data | Where | Licence and attribution |
|---|---|---|
| World Food Programme, "Bangladesh - Food Prices" (monthly market prices, 2022-01 to 2026-08) | `sme_copilot/market/snapshot/wfp_bgd_prices.csv.gz` (filtered) and runtime downloads | [CC BY-IGO](https://creativecommons.org/licenses/by/3.0/igo/). Source: WFP via the Humanitarian Data Exchange, <https://data.humdata.org/dataset/wfp-food-prices-for-bangladesh>. Shown in the price drawer as "Source: World Food Programme market prices (HDX, CC BY-IGO)". |

Financing products in `config/` are illustrative placeholders written by the team, not lender data.

## Python libraries (installed from PyPI, not redistributed)

| Package | Version | Licence |
|---|---|---|
| fastapi | 0.143.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| SQLAlchemy | 2.1.4 | MIT |
| pydantic / pydantic-settings | 2.14.1 / 2.15.0 | MIT |
| pandas | 3.0.6 | BSD-3-Clause |
| numpy | 2.5.4 | BSD-3-Clause (and bundled permissive licences) |
| openpyxl | 3.1.5 | MIT |
| defusedxml | 0.7.1 | PSF-2.0 |
| PyYAML | 6.0.3 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| reportlab | 5.0.1 | BSD |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| bcrypt | 5.0.0 | Apache-2.0 |
| python-multipart | 0.0.32 | Apache-2.0 |
| matplotlib | 3.11.2 | Matplotlib (PSF-based) licence |
| rapidfuzz | 3.14.6 | MIT |
| pytest (tests only) | 9.1.1 | MIT |

Optional price forecasting (`requirements-forecast.txt`):

| Package | Version | Licence |
|---|---|---|
| chronos-forecasting | 2.3.2 | Apache-2.0 |
| torch | 2.14.1 | BSD-3-Clause (and bundled permissive licences) |
| transformers | 5.20.1 | Apache-2.0 |

The frontend uses no third-party JavaScript, fonts or images: icons, charts and styles are the team's own code.

## Models (downloaded by the operator, not redistributed)

| Model | Used for | Licence |
|---|---|---|
| amazon/chronos-bolt-small | Next-month price range in the Home price drawer | Apache-2.0 |
| Gemma 4 (via Ollama / llama.cpp) | Default shared AI Assistant language model | Gemma Terms of Use |
| Qwen, Llama and cloud models listed in `config/providers.yaml` | Optional AI Assistant language models | Each provider's licence or terms of service |

The app works without any language model (the offline rules engine) and without the forecasting model
(a statistical estimate).
