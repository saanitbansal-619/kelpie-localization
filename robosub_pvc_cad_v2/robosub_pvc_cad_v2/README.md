# RoboSub four-hydrophone PVC prototype — CAD V2

**Status: engineering prototype / NOT fit-tested or underwater validated.** Units: mm. Generated with CadQuery using `generate_cad.py`. Files are STEP (editable CAD geometry) and STL (mesh for slicing). Assembly STEP/STL includes *solid placeholder PVC rods and simple 12-mm-diameter sensor gauges*, not manufacturer-accurate sensors.

## Geometry
- Upper hydrophone acoustic-tip targets: (144.338,0,0), (-72.169,125,0), (-72.169,-125,0).
- Lower hydrophone acoustic-tip target: (0,0,-400). Lower sensor oriented **horizontally** to avoid collision with vertical mast; upper three are oriented vertically.
- 250 mm triangle side; lower tip 400 mm below centroid. Acoustic tip position must be measured against actual S1f hydrophone drawing and corrected if needed.
- PVC nominal 1/2-inch Schedule 40, OD 21.34 mm. Printed bore = 21.99 mm (0.65 mm diameter clearance), **printer-dependent**.

## Printed parts
| Part | Qty | File prefix | Purpose |
|---|---:|---|---|
| Central hub | 1 | `central_hub` | Three 120-degree radial sockets and one downward socket |
| Upper sensor mounts | 3 | `upper_hydrophone_mount` | Radial pipe socket and *open guide*, not a hard clamp |
| Lower sensor mount | 1 | `lower_hydrophone_mount` | Downward mast socket and offset horizontal sensor guide |
| Cable clips | 4-8 optional | `cable_clip` | Trial clip for cable tie routing; fit test required |
| Socket test coupon | 1 | `pvc_socket_fit_coupon` | **Print this first** |
| 12-mm gauge | 1 optional | `sensor_12mm_fit_gauge` | Test guide fit without using fragile hydrophone |

## Initial PVC cuts (do not cut until socket fit is confirmed)
- 3 x 120 mm radial arms.
- 1 x 380 mm vertical mast.
- Total 740 mm of PVC, excluding kerf, trial cuts and spares. One 10-ft stick is sufficient.
- The radial arms seat approximately 25 mm in each socket; the vertical mast seats ~25 mm into the bottom fitting and ~25 mm into the hub. Dry-fit, mark insertion depth, and verify tip-to-tip coordinates before final assembly.

## Important limitations / safety
1. The upper/lower sensor guides are **open, oversized retainers**, not finalized secure hydrophone clamps. Add compliant silicone padding and independent cable strain relief. Never tighten hard plastic against the sensing bulb. The lower guide's retention scheme requires bench verification before water use.
2. The actual S1f sensing/acoustic-center offset, cable bend radius, and full body shape must be checked against the specific sensor before assembly. 12-mm gauge is not a full sensor replica.
3. Printed PVC sockets may be loose or too tight. Print `pvc_socket_fit_coupon.stl` in intended PETG and adjust `FIT` in `generate_cad.py` after measuring. Do not solvent-cement until geometry verified.
4. Central hub has no structural bracing or ballast/suspension provisions yet. Evaluate stiffness and add external braces or suspension as needed. Avoid relying on friction alone underwater; add mechanical retention after fit testing.
5. **The 400-mm drop is a target geometry, not a guaranteed measurement from raw pipe cuts.** Check with calipers/tape using sensor acoustic centers and adjust mast length.
6. STEP solids may overlap at interfaces in the assembled preview. It is a visualization, not a collision-cleared manufacturing assembly.

## How to use
- View `full_frame_assembly.step` in FreeCAD or other STEP viewer.
- View individual `.stl` files in a slicer or 3dviewer.net.
- To modify dimensions: edit `generate_cad.py`, install `cadquery`, rerun script.
- Start with socket coupon and 12-mm dummy. Do not print all parts before a successful dry fit.
