# export_gpf

Lightweight KLayout macro that adds an **Export as GPF…** screen to export the active
layout into a portable `.gpf` bundle. The dialog lets you pick which layers to
keep, optionally heal (merge) polygons before export, and assign relative dose
values that are preserved in the metadata.

## Installation
1. Install the Python **gdstk** package into the Python environment KLayout uses
   for macros (the dialog relies on gdstk for polygon fracturing and layer
   extraction).
2. Copy `export_gpf.py` into a folder KLayout can reach (e.g. *Macros > Manage
   Macros… > Add*).
3. Make sure the macro is set to **autorun on application start** so the menu
   entry is registered.
4. Restart KLayout if necessary.

## Usage
1. Open the GDS/OASIS layout you want to convert.
2. Choose **Tools > Export as GPF…** to open the export dialog.
3. In the table:
   - **Use** toggles whether the layer is included.
   - **Heal** merges shapes on that layer before export.
   - **Relative dose** stores a numeric multiplier in the exported metadata.
4. Click **Export…**, pick a destination `.gpf` file, and the macro writes an
   ASCII Raith **GPF** file containing fractured polygons and the selected
   settings.

## GPF format (produced by this macro)
The macro emits a Raith-compatible ASCII GPF file. Each layer is flattened and
fractured into trapezoids or polygons with four or fewer vertices, written as
`POLY` records under a `LAYER` block along with the relative dose value you
assign in the dialog. Geometry is fractured via **gdstk** with a four-vertex
limit, producing trapezoids/triangles compatible with Raith tools. The header
includes the export timestamp, database unit, and source cell name, and the
tail of the file embeds a base64-encoded GDS snapshot for reference.

## Compatibility notice
The generator here writes a **simplified** ASCII GPF that follows public Raith
examples but has **not** been validated on a real EBL tool. Production GPF
flows typically add stage parameters, patterning strategies, and beam settings
that are specific to a given system. Before relying on this macro to drive an
exposure, run the resulting file through the vendor’s official verification
tools or exporter to confirm the syntax and required fields for your machine.
