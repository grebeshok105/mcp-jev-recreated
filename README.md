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

Measured end-to-end: **~1.0 s per query**, ~78k input tokens/query on the
4.4k-resource catalog (candidate-filtered to ~200 answerable entries).

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

# rebuild the catalog from committed dumps
python -m jevlab.build_catalog --data-dir data \
    --visual-pass data/visual/pass_a.json \
    --visual-pass data/visual/pass_b.json

# ask for an effect — real Jev calls, top-10 JSON
python -m jevlab.find_effects "a cold blue beam that holds for a second" \
    --top-k 10 --no-query-cache

# run the Codex ability eval (12 real ability descriptions)
python -m jevlab.evals.run_eval --out data/evals/results.json
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
- measured layer: 9 captured shots (multi-angle × multi-tick, real Minecraft)
- visual layer: 9 shots × 2 independent passes; 31/91 disagreement flags
  (token-normalized incl. singularization + domain stopwords)
- Codex eval: **recall@10 = 0.56–0.58** across two live runs (28–29/50
  expected ids), 12/12 cases with ≥1 hit, ~1.0 s/query, ~938k input tokens
- 37 tests green (35 offline + 2 live)

See `docs/architecture.md` for design, `docs/evaluation.md` for full eval
results and known limits.
