# Label → Region static benchmark viewer

This directory is a self-contained, browser-only visualization of the first
Label → Region benchmark slice. It contains ten T1–T5-style samples and twenty
single-operation cases. The viewer renders the section geometry, labels every
edge with its stable curve name, overlays the silver Region annotation and the
rules resolver output, and shows the decision/evidence/entity comparison for
the selected case.

Open `index.html` directly, or serve this directory with:

```powershell
python -m http.server 7898
```

The precomputed data is intentionally static: no Python package, CAD kernel,
image model, or network API is required to inspect the cases. The prompt field
selects among the exported cases; it is not a live resolver endpoint.

## Contents

- `viewer_data.js` — section geometry, stable edge names, silver gold regions,
  and precomputed rules results.
- `index.html`, `app.js`, `style.css` — the interactive viewer.
- `dfc_snapshots/*.json` — section-only DFC JSON v3 artifacts that can be read
  by the `dfc-data` JSON codec.

The fixtures are silver annotations rather than engineer-confirmed entity-level
gold labels. A `needs_confirmation` result and its candidate overlay are
evidence for evaluation only; they never authorize a DFC modification.
