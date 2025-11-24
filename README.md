# export_gpf

Lightweight KLayout macro that adds an **Export as GPF…** screen to export the active
layout into a portable `.gpf` bundle. The dialog lets you pick which layers to
keep, optionally heal (merge) polygons before export, and assign relative dose
values that are preserved in the metadata.

## Installation
1. Run `./install.sh` to install Python dependencies, download Yale Freebeam
   (via the `FREEBEAM_URL` mirror), and copy the macro into your KLayout macros
   directory. The script installs a `gpfout` binary under `~/.local/freebeam`
   and symlinks it into `~/.local/bin` so the macro can find it automatically.
2. Ensure the macro is set to **autorun on application start** so the menu entry
   is registered.
3. Restart KLayout if necessary.

## Usage
1. Open the GDS/OASIS layout you want to convert.
2. Choose **Tools > Export as GPF…** to open the export dialog.
3. In the table:
   - **Use** toggles whether the layer is included.
   - **Heal** merges shapes on that layer before export.
   - **Relative dose** stores a numeric multiplier in the exported metadata.
4. Click **Export…**, pick a destination `.gpf` file, and the macro passes the
   filtered layout to Yale **Freebeam** `gpfout` for GPF generation. Exports are
   blocked if `gpfout` is not installed.
5. Use **Simulate beam path** to open a companion window that lists the fractured
   polygons (in microns) in the order they would be written, along with the
   per-layer dose annotations you configured.

## GPF format (produced by this macro)
Exports always invoke the Yale **Freebeam** toolchain, passing layer extents,
block sizing, and a temporary relative-dose file to the `gpfout` binary. Each
layer is flattened and fractured into trapezoids or polygons with four or fewer
vertices, written as `POLY` records under a `LAYER` block along with the
relative dose value you assign in the dialog. Geometry is fractured via
**gdstk** with a four-vertex limit, producing trapezoids/triangles compatible
with Raith tools.

## Compatibility notice
The generator here writes a **simplified** ASCII GPF that follows public Raith
examples but has **not** been validated on a real EBL tool. Production GPF
flows typically add stage parameters, patterning strategies, and beam settings
that are specific to a given system. Before relying on this macro to drive an
exposure, run the resulting file through the vendor’s official verification
tools or exporter to confirm the syntax and required fields for your machine.

## Tests and reference fixtures
- Run the automated checks with `pytest`.
- The suite ships with `fixtures/pro_reference.gpf`, a professionally converted
  reference export. Tests decode the embedded base64 payload from that file to
  reconstruct the original GDS on the fly and stub a `gpfout` binary so the
  Freebeam export path can be exercised without the real tool.
