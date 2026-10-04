You are an independent visual-effects analyst (visual observation pass).

For each Minecraft VFX capture sheet listed at the bottom:

1. Download the contact sheet PNG with the `download_attachment` tool
   (each URL is a Devin attachment).
2. Look at EVERY cell: rows are camera angles (front / threequarter / top),
   columns are capture ticks (t3, t8, t20). Base your semantics ONLY on
   pixels you actually see — never infer appearance from the shot id or name.
3. Produce one observation per shot in exactly this shape:

```json
{
  "observations": {
    "<shot_key>": {
      "visibility": "clear | faint | none | ambiguous",
      "description": "literal description of what is visible across angles and ticks",
      "properties": {
        "dominant_colors": ["..."],
        "shape": ["..."],
        "motion": ["..."],
        "brightness": ["..."],
        "density": ["..."],
        "scale_impression": ["..."],
        "persistence": ["..."],
        "texture_quality": ["..."],
        "blend_appearance": ["..."]
      },
      "possible_roles": ["gameplay roles this effect could serve"],
      "confidence": 0.0,
      "notes": "optional — ambiguity, anomalies, partial visibility"
    }
  }
}
```

Rules:
- `visibility=none` ONLY when every frame equals the empty baseline
  (flat grass + sky horizon, nothing else). A few faint specks = `faint`.
- If the effect is visible only from certain angles/ticks, say so in
  `description` (e.g. "top view only").
- The scene contains a persistent brown dirt-debris pile near the anchor,
  visible in many top views across shots — treat it as background unless it
  clearly changes together with the effect.
- All property values must be short lowercase strings; give every
  observation at least 6 property keys.
- `possible_roles` = concrete gameplay usages (e.g. "explosion aftermath",
  "magic buff aura", "projectile trail", "hit impact", "ambient fire").
- `confidence` = your calibrated certainty in the reported semantics —
  lower it when pixels are scarce, blocked, or ambiguous.
- Do NOT run Minecraft, gradle, or any in-game verification. Your only job
  is analyzing the provided PNG sheets.

Output:
- Write the complete JSON (all shots of the batch) to `pass.json`,
  validate it parses, then upload it with `upload_attachment`.
- End your final message with a line `PASS_URL: <url>` and a short list of
  shots you found ambiguous or invisible.

Batch (shot_key → sheet attachment URL):
