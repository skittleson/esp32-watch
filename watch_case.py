"""
Watch Case — Waveshare ESP32-S3-Touch-LCD-1.28
===============================================
Parametric round watch case designed to fit the Waveshare ESP32-S3-Touch-LCD-1.28
development board (38 mm round PCB, Φ32.4 mm GC9A01A display).

Features:
  • Round case body with hollow interior for PCB
  • Φ33.2 mm dial opening on the top face
  • Annular case-back recess on the bottom (press-fit lid)
  • Two lug pairs (top and bottom) with 1.8 mm spring-bar through-holes (20 mm lug width)
  • USB-C port slot cut into the case side wall

Usage:
  pip install build123d
  python watch_case.py
  → watch_case.step  (for FreeCAD / Fusion 360)
  → watch_case.stl   (for 3D-printing slicer)

All dimensions are in millimetres.
"""

from build123d import (
    BuildPart,
    BuildSketch,
    BuildLine,
    Cylinder,
    Box,
    Circle,
    Face,
    Rectangle,
    RectangleRounded,
    Line,
    ThreePointArc,
    Wire,
    Sketch,
    make_face,
    Axis,
    Align,
    Mode,
    Plane,
    Pos,
    Locations,
    mirror,
    extrude,
    fillet,
    chamfer,
    add,
    export_step,
    export_stl,
)

# ─────────────────────────────────────────────────────────────────────────────
# PARAMETERS  (all in mm — edit here to tune the fit)
# ─────────────────────────────────────────────────────────────────────────────

# PCB & display
PCB_DIA = 38.0  # Waveshare ESP32-S3-Touch-LCD-1.28 PCB diameter
DISPLAY_DIA = 32.4  # GC9A01A visible display diameter
DIAL_OPENING_DIA = 33.2  # Top opening — slightly larger than display

# Case body
CASE_DIA = 44.0  # Case outer diameter
CASE_WALL = 3.0  # Radial wall thickness  (= (CASE_DIA - PCB_DIA) / 2)
CASE_HEIGHT = 11.5  # Total case height
CASE_FLOOR = 1.5  # Bottom floor thickness (sits below PCB)

# Case-back recess (annular ledge on the bottom for a press-fit lid)
CB_RECESS_DEPTH = 0.8  # Depth of the recess shelf
CB_RECESS_WIDTH = 1.5  # Radial width of the recess shelf

# Lugs
LUG_WIDTH = 20.0  # Between-lug gap (strap width) — standard 20 mm
LUG_BODY_WIDTH = 6.0  # Width of each lug tab (parallel to strap axis)
LUG_LENGTH = 8.5  # How far lugs extend from the case OD
LUG_HEIGHT = 4.0  # Lug thickness (Z)
LUG_BAR_DIA = 1.8  # Spring-bar through-hole diameter
LUG_FILLET_R = 1.0  # Fillet radius on lug edges

# USB-C port slot
USBC_WIDTH = 9.5  # Slot width  (USB-C receptacle is ~8.9 mm wide)
USBC_HEIGHT = 3.5  # Slot height (USB-C receptacle is ~3.3 mm tall)
USBC_CORNER_R = 1.2  # Rounded-rectangle corner radius
# The USB-C port centre sits near the bottom of the PCB stack.
# From the bottom of the case the port centre is roughly at CASE_FLOOR + 2.5 mm.
USBC_Z_CENTRE = CASE_FLOOR + 2.5  # Z-height of port centre from case bottom

# General finishing
FILLET_R = 1.5  # Global edge fillet radius on the main body
CHAMFER_TOP = 0.4  # Small chamfer on the top opening rim


# ─────────────────────────────────────────────────────────────────────────────
# DERIVED CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

import math

# Case radius
CASE_R = CASE_DIA / 2

# Inner cavity radius
CAVITY_R = PCB_DIA / 2

# Cavity height (from inside floor to top) — leaves room for PCB + components
CAVITY_H = CASE_HEIGHT - CASE_FLOOR

# Lug layout: lugs extend along ±X (12/6 o'clock), strap channel runs in Y.
# Each lug pair has two tabs flanking the strap gap.
# Tab centre offset from origin in Y = LUG_WIDTH/2 + LUG_BODY_WIDTH/2.
LUG_Y_OFFSET = LUG_WIDTH / 2 + LUG_BODY_WIDTH / 2  # tab centre Y = 13.0

# The tab's inner Y edge (closest to strap channel centre) = LUG_WIDTH / 2 = 10.0.
# For the lug box to intersect the case cylinder, the case must reach that Y at
# the embed X region.  At the tab inner edge (Y = LUG_WIDTH/2), the case cylinder
# extends in X to: sqrt(CASE_R^2 - (LUG_WIDTH/2)^2).
# The lug inner face must be at X <= that value, so:
#   CASE_R - LUG_EMBED <= sqrt(CASE_R^2 - (LUG_WIDTH/2)^2)
#   LUG_EMBED >= CASE_R - sqrt(CASE_R^2 - (LUG_WIDTH/2)^2)
# Add 2 mm margin to ensure a solid volumetric union.
_min_embed = CASE_R - math.sqrt(CASE_R**2 - (LUG_WIDTH / 2) ** 2)
LUG_EMBED = _min_embed + 2.0  # guaranteed overlap + 2 mm safety margin

# Lug box total length (embed inside case + exposed length outside)
LUG_TOTAL_LEN = LUG_LENGTH + LUG_EMBED

# Lug box centre X: starts at (CASE_R - LUG_EMBED), extends to (CASE_R + LUG_LENGTH)
LUG_X_CENTRE = (CASE_R - LUG_EMBED + CASE_R + LUG_LENGTH) / 2

# Lug Z: flush with the bottom face (Z=0), extending upward by LUG_HEIGHT
LUG_Z_BOTTOM = 0
LUG_Z_CENTRE = LUG_HEIGHT / 2

# ── Gusset geometry (all derived — no extra params needed) ────────────────────
# The gusset fills the concave void between the curved case OD and the flat
# inner face of each lug tab.  One gusset per tab, on the inner-Y side (the
# side facing the strap channel — where strap tension pulls hardest).
#
# Profile key points in the XY plane (first quadrant, +X lug pair):
#
#   A ──arc──► B ──line──► C ──line──► D ──line──► A  (closed)
#
#   A  case OD at lug outer-Y edge
#   M  case OD arc midpoint (at LUG_Y_OFFSET — used for ThreePointArc)
#   B  case OD at lug inner-Y edge
#   C  lug flat face at inner-Y edge
#   D  lug flat face at outer-Y edge
#
# The gusset is then extruded for LUG_HEIGHT and added to the part.
# It is mirrored to all four quadrants (±X, ±Y) to cover all four tabs.

GUSSET_Y_INNER = LUG_WIDTH / 2  # 10.0 — inner tab edge
GUSSET_Y_OUTER = LUG_Y_OFFSET + LUG_BODY_WIDTH / 2  # 16.0 — outer tab edge
GUSSET_Y_MID = LUG_Y_OFFSET  # 13.0 — arc midpoint Y

GUSSET_X_A = math.sqrt(max(0, CASE_R**2 - GUSSET_Y_OUTER**2))  # 15.100
GUSSET_X_M = math.sqrt(CASE_R**2 - GUSSET_Y_MID**2)  # 17.748  (arc mid)
GUSSET_X_B = math.sqrt(CASE_R**2 - GUSSET_Y_INNER**2)  # 19.596
GUSSET_X_C = CASE_R - LUG_EMBED  # 17.596 (lug face)
GUSSET_X_D = GUSSET_X_C  # same X as C


# ─────────────────────────────────────────────────────────────────────────────
# PRE-BUILD: Gusset solid (built outside BuildPart to avoid context capture)
# ─────────────────────────────────────────────────────────────────────────────
# Arc gusset profile — first quadrant (+X, +Y):
#   A → arc(M) → B → C → D → A
# A/M/B lie on the case OD; C/D lie on the lug flat inner face.
_pt_A = (GUSSET_X_A, GUSSET_Y_OUTER)
_pt_M = (GUSSET_X_M, GUSSET_Y_MID)
_pt_B = (GUSSET_X_B, GUSSET_Y_INNER)
_pt_C = (GUSSET_X_C, GUSSET_Y_INNER)
_pt_D = (GUSSET_X_D, GUSSET_Y_OUTER)

_gusset_wire = Wire.combine(
    [
        ThreePointArc(_pt_A, _pt_M, _pt_B),
        Line(_pt_B, _pt_C),
        Line(_pt_C, _pt_D),
        Line(_pt_D, _pt_A),
    ]
)[0]
# extrude() outside BuildPart goes in -Z from Z=0 → Z: -LUG_HEIGHT to 0
# Translate up by LUG_HEIGHT so gusset sits at Z: 0 → LUG_HEIGHT (lug base to top)
_gusset_raw = extrude(Sketch() + Face(_gusset_wire), LUG_HEIGHT)
GUSSET_Q1 = Pos(0, 0, LUG_HEIGHT) * _gusset_raw  # +X, +Y quadrant

with BuildPart() as case_part:
    # ── 1. CASE OUTER BODY ───────────────────────────────────────────────────
    Cylinder(
        radius=CASE_R,
        height=CASE_HEIGHT,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )

    # ── 2. HOLLOW INTERIOR (PCB cavity) ─────────────────────────────────────
    # Subtract a cylinder from the top face downward, leaving CASE_FLOOR.
    with BuildSketch(Plane.XY.offset(CASE_HEIGHT)):
        Circle(CAVITY_R)
    extrude(amount=-CAVITY_H, mode=Mode.SUBTRACT)

    # ── 3. DIAL OPENING ──────────────────────────────────────────────────────
    # Cut through the remaining floor so the display is fully exposed.
    with BuildSketch(Plane.XY.offset(CASE_HEIGHT)):
        Circle(DIAL_OPENING_DIA / 2)
    extrude(amount=-(CASE_FLOOR + 0.1), mode=Mode.SUBTRACT)

    # ── 4. CASE-BACK RECESS ──────────────────────────────────────────────────
    # Annular ledge at the very bottom; a thin disc lid drops into this step.
    with BuildSketch(Plane.XY):  # bottom face (Z=0)
        Circle(CASE_R)
        Circle(CASE_R - CB_RECESS_WIDTH, mode=Mode.SUBTRACT)
    extrude(amount=CB_RECESS_DEPTH, mode=Mode.SUBTRACT)

    # ── 5. LUGS ──────────────────────────────────────────────────────────────
    # Four lug tabs total — two pairs at ±X, each pair flanking the strap channel.
    # Each tab is a Box centred at (±LUG_X_CENTRE, ±LUG_Y_OFFSET, LUG_Z_CENTRE).
    # LUG_TOTAL_LEN includes LUG_EMBED overlap inside the case wall so the
    # boolean union produces a single connected solid.
    lug_positions = [
        (LUG_X_CENTRE, LUG_Y_OFFSET, LUG_Z_CENTRE),
        (LUG_X_CENTRE, -LUG_Y_OFFSET, LUG_Z_CENTRE),
        (-LUG_X_CENTRE, LUG_Y_OFFSET, LUG_Z_CENTRE),
        (-LUG_X_CENTRE, -LUG_Y_OFFSET, LUG_Z_CENTRE),
    ]
    with Locations(*lug_positions):
        Box(LUG_TOTAL_LEN, LUG_BODY_WIDTH, LUG_HEIGHT)

    # ── 5b. SPRING-BAR THROUGH-HOLES ─────────────────────────────────────────
    # One Y-axis hole per lug pair, centred at (±LUG_X_CENTRE, 0, LUG_Z_CENTRE).
    # The cylinder runs the full Y extent of both tabs in the pair.
    bar_y_half = LUG_Y_OFFSET + LUG_BODY_WIDTH / 2 + 0.5  # slight overshoot

    for x_sign in (+1, -1):
        bar_x = x_sign * LUG_X_CENTRE
        # Draw hole cross-section on XZ plane at +Y face of the lug pair
        with BuildSketch(Plane.XZ.offset(bar_y_half)):
            with Locations((bar_x, LUG_Z_CENTRE)):
                Circle(LUG_BAR_DIA / 2)
        extrude(amount=-(2 * bar_y_half), mode=Mode.SUBTRACT)

    # ── 5c. ARC GUSSETS ──────────────────────────────────────────────────────
    # GUSSET_Q1 was built outside this context (above) to avoid builder-mode
    # context capture.  Mirror it to all four quadrants and add to part.
    add(GUSSET_Q1)  # +X, +Y
    add(mirror(GUSSET_Q1, Plane.XZ))  # +X, −Y
    add(mirror(GUSSET_Q1, Plane.YZ))  # −X, +Y
    add(mirror(mirror(GUSSET_Q1, Plane.XZ), Plane.YZ))  # −X, −Y

    # ── 6. USB-C PORT SLOT ───────────────────────────────────────────────────
    # Slot cut through the +X side wall.  The USB-C port on the Waveshare board
    # is at the board edge, so we place the slot at +X at the appropriate height.
    with BuildSketch(Plane.YZ.offset(CASE_R + 0.1)):  # just outside the +X wall
        with Locations((0, USBC_Z_CENTRE)):
            RectangleRounded(USBC_WIDTH, USBC_HEIGHT, USBC_CORNER_R)
    extrude(amount=-(CASE_WALL + 0.2), mode=Mode.SUBTRACT)

    # ── 7. FILLETS & CHAMFERS ────────────────────────────────────────────────
    # The arc gussets already provide the smooth stress-relief where it matters
    # most (lug-to-case transition).  Skip filleting the lug tab corners — the
    # gusset geometry makes the OCC fillet kernel fail on those edges.

    # Chamfer the top inner rim (dial opening edge) — guides the crystal/display.
    # Fillet the outer top rim — smooth case edge.
    # Both are cosmetic; wrap in try/except so a topology quirk doesn't abort export.
    top_face_edges = (
        case_part.edges()
        .filter_by(Axis.Z, reverse=True)  # horizontal (circular) edges
        .group_by(Axis.Z)[-1]  # topmost Z group
    )
    top_face_edges_sorted = top_face_edges.sort_by(lambda e: e.length)
    inner_rim = top_face_edges_sorted[0]  # shortest = inner (dial opening)
    outer_rim = top_face_edges_sorted[-1]  # longest  = outer case rim

    try:
        chamfer(inner_rim, length=CHAMFER_TOP)
    except ValueError:
        print("Note: top inner chamfer skipped (topology)")
    try:
        fillet(outer_rim, radius=FILLET_R)
    except ValueError:
        print("Note: top outer fillet skipped (topology)")


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────────────────────────────────────

part = case_part.part

export_step(part, "watch_case.step")
print("Exported: watch_case.step")

export_stl(part, "watch_case.stl")
print("Exported: watch_case.stl")

print(
    f"\nWatch case summary:\n"
    f"  Outer diameter : {CASE_DIA:.1f} mm\n"
    f"  Height         : {CASE_HEIGHT:.1f} mm\n"
    f"  Dial opening   : {DIAL_OPENING_DIA:.1f} mm\n"
    f"  Lug width      : {LUG_WIDTH:.1f} mm (20 mm strap)\n"
    f"  USB-C slot     : {USBC_WIDTH:.1f} × {USBC_HEIGHT:.1f} mm\n"
    f"  Fits PCB       : Waveshare ESP32-S3-Touch-LCD-1.28 ({PCB_DIA:.0f} mm round)\n"
)
