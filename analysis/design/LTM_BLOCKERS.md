# LTM implementation blockers

Recorded under the blocker protocol in [LTM_IMPLEMENTATION_HANDOFF.md](LTM_IMPLEMENTATION_HANDOFF.md) §2. Each entry is a place where
the frozen spec cannot be built exactly as written, the minimal deviation applied, and its impact. The frozen documents are
unchanged.

---

## B1. The high-entropy secret detector classifies the system's own ULID ids as secrets

| | |
|---|---|
| **Step** | 6 (first surfaced when a memory-state snapshot containing real row ids went through the leak guard) |
| **Spec requirements in conflict** | (1) Deep dive §0.1: `memories.id` is `'mem_' + ULID` (and §24 / design §17 use the same form for events and traces). (2) Deep dive §3: `high_entropy_tokens` flags any `[A-Za-z0-9_\-+/=]{20,}` token with ≥ 3 character classes and ≥ 3.5 bits/char as `SECRET`; §8.9 makes `HIGH_ENTROPY` an ingress (prohibited) class. (3) Deep dive §24.1 leak guard: `ingress_scrub(json.dumps(trace))` must equal its input, and handoff §6.2 gates every file on `contract.leak_free` |
| **Observed** | `mem_01K…` (4 + 26 chars: lower `mem`, upper + digits from Crockford base32, `_`) has 4 character classes and ≈ 4.5 bits/char. `test_consolidate.TestConflict.test_supersede_emits_edge` → `LeakError: prohibited pattern in trace: HIGH_ENTROPY` from `trace.memory_state_snapshot`. Every trace containing a memory, event or trace id would fail `contract.leak_free` |
| **Minimal deviation applied** | `detectors.high_entropy_tokens` skips a token only when the **whole token** matches the system id grammar `^(?:mem\|evt\|trc\|run)_[0-9A-HJKMNP-TV-Z]{20,26}$` (prefix + uppercase Crockford base32). This mirrors the spec's own `looks_like_url_path` exclusion in the same function. No constant, threshold, pattern or id format changed |
| **Why nothing smaller works** | Changing the id format (e.g. the 12-char ids in design §6.3's example) breaks the §0.1 ULID requirement and raises collision risk. Exempting fields in the leak guard alone would leave the same ids flagged by ingress/events, and would let a real secret hide in an id-named field. Raising the entropy threshold or class count is forbidden (handoff §1: constants verbatim) and would weaken secret detection |
| **Also applies to** | The harness `meta.run_id`. Design §25's example format `run_2026-10-07T18-00-00Z` itself trips the verbatim entropy rule (4 character classes, 24 chars), so the harness uses `run_` + ULID, which the same id grammar covers. `meta.git_commit` is the bare sha with a separate `git_dirty` boolean, because `sha+dirty` also trips the rule |
| **Gates affected** | `contract.leak_free` (all 8 files), `privacy.trace_file_leak_free`, the step-3 leak guard. With the deviation all can pass |
| **Impact on demo claims** | None on the four proofs. Residual risk: a user-typed string that is exactly `mem_`/`evt_`/`trc_`/`run_` + 20–26 uppercase Crockford characters is not treated as a high-entropy secret. Provider-format keys (`sk-…`, `ghp_…`, `AKIA…`, JWT, PEM), credentials and OTPs are detected by their own rules and are unaffected |

---

## B2. The credential rule matches the spec's own typed labels (`SECRET:API_KEY`)

| | |
|---|---|
| **Step** | 10 (first full harness run: `contract.leak_free` failed on `privacy.{baseline,ltm}.json`, which contain no secret) |
| **Spec requirements in conflict** | (1) Handoff §7: `canary_scan.canaries` are labels such as `SECRET:API_KEY`; design §25 / §24 visual beats label the classification `SECRET → REJECT` (the `privacy.classify` detector label is `SECRET:API_KEY`, alongside `CONTACT:EMAIL`). (2) Deep dive §3 verbatim `CREDENTIAL` rule `(?i)\b(password\|…\|secret\|token\|api[ _-]?key)\b\s*(?:is\|:\|=)\s*(\S+)` reads `SECRET:API_KEY` as "secret: <value>". (3) Deep dive §24.1 leak guard / handoff §6.2 `contract.leak_free`, and the event backstop (no prohibited pattern in an event) |
| **Observed** | `privacy.ltm.json` / `privacy.baseline.json`: CREDENTIAL hits only on the canary labels (the literal key has 0 occurrences). The same collision would make the event backstop redact the `privacy.classify` detail of the API-key candidate, so the UI would lose its `SECRET:API_KEY` detector label |
| **Minimal deviation applied** | `detectors._placeholder_spans` also protects exact typed labels `SECRET:(API_KEY\|JWT\|PRIVATE_KEY\|CREDENTIAL\|SECRET_URL\|OTP\|HIGH_ENTROPY)`, the same protection bracketed placeholders (`[SECRET:API_KEY]`) already had. Only this module's own detector kind names qualify. No pattern, threshold or label format changed |
| **Why nothing smaller works** | Renaming the labels (e.g. `SECRET/API_KEY`) contradicts handoff §7's explicit examples. Masking labels only in the harness leak check would still redact the classify event at the source. Loosening the CREDENTIAL rule changes a verbatim constant |
| **Gates affected** | `contract.leak_free` (privacy files), `privacy.trace_file_leak_free`, and the completeness of the `privacy.classify` pipeline entry |
| **Impact on demo claims** | None. Residual risk: a user secret whose value is exactly one of those seven upper-case kind names, written as `secret:API_KEY`, is not redacted. Such a value is a label, not a credential |
