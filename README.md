# `krita-base-colouring`

A standalone, reusable Antigravity skill for **vision-first, non-destructive base colouring in Krita** using native Fill Tool workflows (`select_content` + `set_selection(grow)`), hidden gap-repair reference layers, clean semantic `Base_Colours` organisation, and deterministic leak/cutout auditing.

This skill complements lineart-reconstruction workflows and stops strictly after verified flat base colours so the artist retains full control over all shading, lighting, and rendering decisions.

---

## Directory Structure

```text
krita-base-colouring/
├── SKILL.md                                     # Core agent workflow (Stages A–F)
├── README.md                                    # Installation, discovery, and usage guide
├── LICENSE                                      # MIT License
├── configs/
│   ├── default_fill_config.json                 # Generic fill, gap-repair & MCP defaults
│   └── layer_naming_conventions.json            # Canonical layer stack & naming conventions
├── references/
│   ├── visual_decomposition_and_boundaries.md   # Stage A & B methodology
│   ├── workflow_krita_mcp.md                    # Krita 6.0.4 / krita-mcp v1.7.0 notes
│   └── verification_and_recovery.md             # Stage C failure recovery & Stage E audit
├── scripts/
│   ├── png_io.py                                # Pure-stdlib PNG RGBA decoder/writer/cropper
│   ├── lineart_fill_diagnostics.py              # Seed validator, component scan, leak bottlenecks
│   ├── base_colour_audit.py                     # Cutout audit, unfilled-island scan, overlap check
│   └── krita_batch_builder.py                   # Schema-safe Krita MCP edit_batch builders
├── tests/
│   ├── fixtures/                                # Synthetic fixtures + generator script
│   ├── test_lineart_fill_diagnostics.py
│   ├── test_base_colour_audit.py
│   └── test_krita_batch_builder.py
├── examples/
│   ├── sample_lineart_fixture.png
│   ├── sample_base_coloured_preview.png
│   ├── sample_jewel_zoom_2x.png
│   └── synthetic_character_prop_walkthrough.md
└── reports/
    └── validation_report.md                     # Offline unit + live Krita smoke + regression audit
```

---

## Requirements & Installation

- **Python**: `3.10+` (**standard library only**—zero `pip install` or third-party packages required for any helper script or test).
- **Krita** (for live execution): Krita `6.0.4` (tested) with `krita-mcp v1.7.0` active.

### Antigravity Skill Discovery

Antigravity discovers workspace skills under `.agents/skills/` (or `.agents/skills.json`) at a project root, or globally under `~/.gemini/config/skills/`.

1. **Clone into a workspace skills folder and symlink into `.agents/skills/`** (recommended without duplicating files):

```bash
git clone https://github.com/ashdawgthegoat/krita-base-colouring.git skills/krita-base-colouring
mkdir -p .agents/skills
ln -sfn ../../skills/krita-base-colouring .agents/skills/krita-base-colouring
```

2. **Or reference via `.agents/skills.json`**:

```json
{
  "entries": [
    { "path": "skills" }
  ]
}
```

3. **Or install directly into global config**:

```bash
git clone https://github.com/ashdawgthegoat/krita-base-colouring.git ~/.gemini/config/skills/krita-base-colouring
```

See [reports/validation_report.md](./reports/validation_report.md) for verified discovery behavior.

---

## Usage Overview

This skill is designed to be executed interactively by an agent with visual inspection and Krita MCP access:

1. **Stage A (Visual Decomposition)**: Inspect full and zoomed views, separate intentional negative spaces from fillable compartments, and draft a semantic Region Map with palette colours.
2. **Stage B (Boundary Preparation)**: Lock original lineart, build `Fill_Assist_Hidden/Lineart_Fill_Reference`, export it via `export_layers(trim=false)`, run `scripts/lineart_fill_diagnostics.py`, inspect bottlenecks visually, and seal only true contour gaps on the hidden helper layer.
3. **Stage C (Base Colouring)**: Use `select_content(mode="contiguous")` + `set_selection(grow=1)` + tight `draw(fill_rect)` (optionally built with `scripts/krita_batch_builder.py`) across semantic layers inside `Base_Colours`. Undo and repair on any leak; fall back to `select_polygon`/masks only for tiny soft-anti-aliased or un-inked regions.
4. **Stage D (Layer Organisation)**: Keep original lineart locked on top, `Base_Colours` disjoint below it, `Fill_Assist_Hidden` hidden (`visible: false`), and `Background` independent at bottom.
5. **Stage E (Verification)**: Export full composite and background-hidden cutout, run `scripts/base_colour_audit.py` + `audit_layer_disjointness`, and inspect full + zoomed crops.
6. **Stage F (Handoff)**: Save a separate layered `*_base_coloured.kra` and export `*_base_coloured_preview.png`, leaving source `.kra` files untouched and stopping before shading/rendering.

---

## Running Offline Tests & Optional Diagnostics

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

For quick CLI inspection of an exported `Lineart_Fill_Reference.png` or Stage E cutout:

```bash
python3 scripts/lineart_fill_diagnostics.py path/to/Lineart_Fill_Reference.png --bg 0,0
python3 scripts/lineart_fill_diagnostics.py path/to/Lineart_Fill_Reference.png --leak-from 150,220 --leak-to 0,0
python3 scripts/base_colour_audit.py --transparent path/to/cutout.png --composite path/to/composite.png --empty-pt 0,0
```
