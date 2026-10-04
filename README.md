# mcp-jev-recreated — VFX Knowledge Base + Jev selector

Working (non-mock) pipeline that lets an LLM describe a desired visual effect
in plain text and get back the best **real, existing** Minecraft VFX resources
for it — ranked by Jev (TypeSafe AI) against a catalog built from actual mod
and vanilla resources.

## What it does

```
"translucent rings rippling out of the mouth in a cone"
        │
        ▼
VFX Knowledge Base (4,430 passports, real resources)
        │  particles · world events · photon fx/models/shaders/textures
        │  quasar emitters/particle defs/vfx params · composites
        ▼
passports: identity + factual + measured + visual semantics
        │  (measured = real in-game capture; visual = two independent
        │   annotation passes merged with disagreement flags)
        ▼
Jev stage 1 — Noul independent relevance per candidate (batched)
Jev stage 2 — single Choice over the top pool
        │
        ▼
top-10: {rank, id, source, kind, noul_relevance, choice_probability, summary}
```

Measured end-to-end: **~3.1 s per query**, ~330k input tokens/query on the
4.4k-resource catalog (candidate-filtered to ~200 answerable entries,
all with full measured+visual enrichment).

## Layout

| path | contents |
|---|---|
| `src/jevlab/providers/` | one provider per resource family |
| `src/jevlab/passports/` | passport schema + SemanticValue + content hash |
| `src/jevlab/catalog/` | catalog build/merge/stats |
| `src/jevlab/enrichment/` | measured + visual layer merging |
| `src/jevlab/jev/` | TypeSafe client (real API), question builders |
| `src/jevlab/ranking/` | two-stage selector |
| `src/jevlab/find_effects.py` | end-to-end query → top-K with query cache |
| `src/jevlab/evals/` | Codex ability eval harness |
| `probe/` | Fabric probe mod — registry dump + capture harness (ldlib2 uitest) |
| `data/` | committed artifacts: dumps, measurements, contact sheets, catalog, evals |
| `docs/` | architecture, evaluation, research inventories |

## Usage

```bash
pip install -e .            # python >=3.10, deps: httpx, pytest
export TYPESAFE_API_KEY=…   # live TypeSafe/Jev key

# rebuild the catalog from committed dumps + all visual passes
python -m jevlab.build_catalog --data-dir data \
    --exceptions data/capture/exceptions.json \
    $(for f in data/visual/batches/batch_*.json data/visual/batches_b/group_*.json; do \
      printf -- "--visual-pass %s " "$f"; done)

# ask for an effect — real Jev calls, top-10 JSON
python -m jevlab.find_effects "a cold blue beam that holds for a second" \
    --top-k 10 --batch-size 12 --stage2-pool 12 --no-query-cache

# run the Codex ability eval (12 real ability descriptions)
python -m jevlab.evals.run_eval --out data/evals/results_full_enrichment.json \
    --batch-size 12 --stage2-pool 12 --no-query-cache
```

## Tests

```bash
pytest tests/unit          # 33 tests, offline, seconds
pytest tests/ -m typesafe  # 2 live API tests, needs TYPESAFE_API_KEY
```

## Current numbers (all real, see docs/evaluation.md)

- catalog **4,430** resources: 142 particle types, 82 world events, 5 photon
  .fx, 6 meshes, 130 photon shaders/postfx, 3,910 textures, 15 quasar emitters,
  132 quasar particle defs, 8 composites — **0 build diagnostics**
- measured layer: **197 captured shots** (3 angles × 3 ticks, real
  Minecraft; every shot spawned server-side particles)
- visual layer: **197/197 shots annotated** — pass A on all, independent
  pass B on the 78 ambiguous/low-confidence shots; 73 disagreement flags
- visual coverage of answerable candidates: **205/205** (197 annotated +
  8 documented unrenderable composite exceptions)
- Codex eval at full enrichment (2 identical live runs): **recall@10 =
  0.50**, hit@1 = 0.42, hit@3 = 0.83, hit@10 = 0.92, MRR = 0.618,
  ~3.1 s/query, ~330k input tokens/query. Full visual enrichment
  *regressed* recall vs the 0.56–0.58 baseline — measured layer alone
  scored 0.68 under identical config; attribution matrix in
  docs/evaluation.md.
- 37 tests green (35 offline + 2 live)

See `docs/architecture.md` for design, `docs/evaluation.md` for full eval
results and known limits.
