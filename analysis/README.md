# OpenPoke memory & privacy analysis (current state)

| Deliverable | File |
|---|---|
| 1. Architecture diagram | [ARCHITECTURE.md §1](ARCHITECTURE.md#1-component-architecture) |
| 2. Data-flow diagram + context reconstruction + summarisation mechanics | [ARCHITECTURE.md §2](ARCHITECTURE.md#2-data-flow--one-user-turn-and-its-derived-copies) |
| 3. Persistence locations table | [ARCHITECTURE.md §3](ARCHITECTURE.md#3-persistence-locations) |
| 4. External-model boundaries table | [ARCHITECTURE.md §4](ARCHITECTURE.md#4-external-model-boundaries) |
| 5. Test results + reproducible commands | [TEST_RESULTS.md](TEST_RESULTS.md) |
| 6. Weaknesses ranked by severity | [FINDINGS.md](FINDINGS.md#weaknesses-ranked-by-severity) |
| 7. Concise current-state findings | [FINDINGS.md](FINDINGS.md) |

Harness: `lab/` (mock OpenRouter with request capture, fake Composio, launcher that patches seams in-memory, runner).
Raw evidence: `lab/results/*.json` and `lab/results/*.llm_captures.jsonl` (every LLM request body, synthetic data only).
No file under `server/` or `web/` was modified.
