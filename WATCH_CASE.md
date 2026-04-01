# Watch Case — Build Guide

Parametric round watch case for the **Waveshare ESP32-S3-Touch-LCD-1.28**
(38 mm round PCB, Φ32.4 mm GC9A01A display, capacitive touch, IMU, LiPo).

---

## Requirements

- Python 3.10–3.14
- [build123d](https://github.com/gumyr/build123d) — Python BREP CAD library built on OpenCascade

```bash
# Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install build123d
```

---

## Generate the Part

```bash
python watch_case.py
```

Outputs two files in the current directory:

| File | Use |
|---|---|
| `watch_case.step` | FreeCAD, Fusion 360, SolidWorks, or any STEP-capable CAD tool |
| `watch_case.stl` | 3D printing slicer (PrusaSlicer, Cura, Bambu Studio, etc.) |

---

## Part Overview

```
         ┌─────────────────────────────────────┐
         │          dial opening               │  ← Φ33.2 mm top opening
         │  ╔═══════════════════════════════╗  │
         │  ║                               ║  │
         │  ║        PCB cavity             ║  │  ← Φ38 mm interior
         │  ║     (holds Waveshare PCB)     ║  │
[lug]────┤  ╚═══════════════════════════════╝  ├────[lug]
[lug]────┤  └─── case-back recess ────────┘    ├────[lug]
         └─────────────────────────────────────┘
                       USB-C slot →  ▯
```

| Feature | Description |
|---|---|
| **Case body** | Φ44 mm OD, 3 mm walls, 11.5 mm tall |
| **PCB cavity** | Φ38 mm inner bore, open at the top |
| **Dial opening** | Φ33.2 mm through-hole on top (display sits here) |
| **Case floor** | 1.5 mm solid floor at the bottom |
| **Case-back recess** | 0.8 mm deep × 1.5 mm wide annular ledge at the bottom for a press-fit disc lid |
| **Lugs** | 4 tabs (2 pairs at ±X), flush with the bottom face, for a 20 mm strap |
| **Spring-bar holes** | Φ1.8 mm through-holes running Y-axis through each lug pair |
| **USB-C slot** | 9.5 × 3.5 mm rounded-rectangle cutout on the +X side wall |

---

## Coordinate System

```
        +Z (top / dial face)
         │
         │
─────────┼───────── +X  (USB-C slot side, also 12/6-o'clock lugs)
         │
        (origin at bottom-centre of case)
```

- **Z = 0** — bottom of case (case-back face, lug bottom)
- **Z = 11.5** — top of case (dial opening face)
- Lugs sit at **Z 0 → 4 mm** (bottom of the case), so a strap runs under the case

---

## Parameters

All tunable constants live at the top of `watch_case.py`.
Edit and re-run to regenerate.

### PCB / Display

| Constant | Default | Description |
|---|---|---|
| `PCB_DIA` | `38.0` | PCB outer diameter (mm) |
| `DISPLAY_DIA` | `32.4` | GC9A01A visible display diameter |
| `DIAL_OPENING_DIA` | `33.2` | Top opening diameter (slightly > display) |

### Case Body

| Constant | Default | Description |
|---|---|---|
| `CASE_DIA` | `44.0` | Case outer diameter |
| `CASE_WALL` | `3.0` | Radial wall thickness |
| `CASE_HEIGHT` | `11.5` | Total case height |
| `CASE_FLOOR` | `1.5` | Bottom floor thickness |

### Case-Back Recess

| Constant | Default | Description |
|---|---|---|
| `CB_RECESS_DEPTH` | `0.8` | Recess shelf depth |
| `CB_RECESS_WIDTH` | `1.5` | Recess shelf radial width |

### Lugs

| Constant | Default | Description |
|---|---|---|
| `LUG_WIDTH` | `20.0` | Strap width / gap between lug tabs |
| `LUG_BODY_WIDTH` | `6.0` | Width of each individual lug tab |
| `LUG_LENGTH` | `8.5` | How far lugs extend beyond the case OD |
| `LUG_HEIGHT` | `4.0` | Lug thickness (Z height) |
| `LUG_BAR_DIA` | `1.8` | Spring-bar hole diameter |
| `LUG_FILLET_R` | `1.0` | Fillet radius on lug corners |

### USB-C Slot

| Constant | Default | Description |
|---|---|---|
| `USBC_WIDTH` | `9.5` | Slot width |
| `USBC_HEIGHT` | `3.5` | Slot height |
| `USBC_CORNER_R` | `1.2` | Slot corner radius |
| `USBC_Z_CENTRE` | `CASE_FLOOR + 2.5` | Z-height of slot centre from case bottom |

### Finishing

| Constant | Default | Description |
|---|---|---|
| `FILLET_R` | `1.5` | Outer top-rim fillet radius |
| `CHAMFER_TOP` | `0.4` | Inner dial-opening chamfer |

---

## Build Steps (how the script works)

The script uses **build123d Builder Mode** — each operation is performed inside a
`with BuildPart()` context and applied to the accumulating solid.

```
1. Cylinder  ──────────────────────────────────  case outer body (Φ44 mm, 11.5 mm tall)
2. Cylinder subtracted from top  ─────────────  hollow interior (Φ38 mm bore)
3. Circle subtracted through floor  ──────────  dial opening (Φ33.2 mm)
4. Annular ring subtracted from bottom  ───────  case-back press-fit recess
5. 4× Box added at bottom corners  ────────────  lug tabs (embedded into case wall)
6. 2× Cylinder subtracted through lugs  ───────  spring-bar through-holes
7. RectangleRounded subtracted from +X wall  ──  USB-C slot
8. Fillet lug vertical edges  ─────────────────  smooth lug corners
9. Chamfer inner top rim  ──────────────────────  guide edge for display/crystal
10. Fillet outer top rim  ─────────────────────  smooth case top edge
```

### Key geometry note — lug attachment

Lug boxes are embedded `CASE_WALL` (3 mm) **inside** the case cylinder.
If the lug inner face only touches the case surface tangentially (no overlap),
the boolean union leaves them as separate bodies. The embed guarantees a
volumetric intersection so the union produces a single solid.

```
         case OD
            │
   ┌────────┼─────────────┐
   │  embed │  lug extends│
   │◄──3mm─►│◄───8.5mm───►│
   └────────┴─────────────┘
   ^
   CASE_R - LUG_EMBED  (lug inner face, inside the wall)
```

---

## 3D Printing Tips

- **Orientation:** print with the dial face (top) face-down on the bed — the flat
  top provides a perfect first layer and the interior cavity needs no supports.
- **Layer height:** 0.15–0.2 mm for good thread/surface detail.
- **Material:** PETG or ABS for better dimensional accuracy than PLA on tight fits.
- **Walls:** at least 3 perimeters / 1.2 mm wall width.
- **Case-back lid:** print a separate Φ44 mm disc, 1.2–1.5 mm thick, to snap into
  the recess. Add a small notch for a coin to open it.
- **Spring bars:** standard 20 mm × 1.5 mm watch spring bars will fit the
  Φ1.8 mm holes with slight press-fit.

---

## Viewing the Output

Open `watch_case.step` in any of:

- **FreeCAD** (free) — File → Open
- **Fusion 360** — Upload to a project
- **CAD Assistant** (free, by OpenCascade) — drag and drop
- **ocp_vscode** — add `show(case_part)` to the script and run inside VS Code
  with the [OCP CAD Viewer extension](https://github.com/bernhard-42/vscode-ocp-cad-viewer)

---

## File Reference

```
watch_case.py    ← parametric CAD script (edit this)
watch_case.step  ← generated STEP file (CAD tools)
watch_case.stl   ← generated STL file  (3D printing)
WATCH_CASE.md    ← this document
```
