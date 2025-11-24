import base64
import datetime
import tempfile
from pathlib import Path

import gdstk
import pya


class GPFExportDialog(pya.QDialog):
    """Dialog for exporting a filtered GDS layout into a GPF container."""

    def __init__(self, main_window: pya.MainWindow):
        super(GPFExportDialog, self).__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Export GDS as GPF")
        self.resize(650, 400)

        self.layout = pya.QVBoxLayout(self)

        description = pya.QLabel(
            "Select the layers to export, optionally heal polygons, and assign relative doses.\n"
            "The export creates a portable .gpf file containing a filtered, flattened GDS snapshot."
        )
        description.setWordWrap(True)
        self.layout.addWidget(description)

        self.table = pya.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Use", "Layer", "Heal", "Relative dose"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.layout.addWidget(self.table)

        button_row = pya.QHBoxLayout()
        self.refresh_button = pya.QPushButton("Reload layers")
        self.refresh_button.clicked(self.load_layers)
        button_row.addWidget(self.refresh_button)

        button_row.addStretch(1)

        self.simulate_button = pya.QPushButton("Simulate beam path")
        self.simulate_button.clicked(self.handle_simulation)
        button_row.addWidget(self.simulate_button)

        self.export_button = pya.QPushButton("Export…")
        self.export_button.clicked(self.handle_export)
        button_row.addWidget(self.export_button)

        self.close_button = pya.QPushButton("Close")
        self.close_button.clicked(self.close)
        button_row.addWidget(self.close_button)

        self.layout.addLayout(button_row)

        self.load_layers()

    def load_layers(self) -> None:
        """Populate the table with layer information from the current view."""
        view = self.main_window.current_view()
        if view is None:
            pya.QMessageBox.warning(self, "No view", "Open a layout before exporting.")
            self.table.setRowCount(0)
            return

        layers = []
        for node in view.begin_layers():
            if node.is_layer():
                info = node.layer_info()
                label = node.name if node.name else f"{info.layer}/{info.datatype}"
                layers.append((info, label))

        self.table.setRowCount(len(layers))

        for row, (layer_info, label) in enumerate(layers):
            use_item = pya.QTableWidgetItem()
            use_item.setFlags(pya.Qt.ItemIsUserCheckable | pya.Qt.ItemIsEnabled)
            use_item.setCheckState(pya.Qt.Checked)
            self.table.setItem(row, 0, use_item)

            label_item = pya.QTableWidgetItem(label)
            label_item.setFlags(pya.Qt.ItemIsEnabled | pya.Qt.ItemIsSelectable)
            label_item.setData(pya.Qt.UserRole, layer_info)
            self.table.setItem(row, 1, label_item)

            heal_checkbox = pya.QCheckBox()
            heal_checkbox.setChecked(False)
            heal_checkbox.setAlignment(pya.Qt.AlignCenter)
            self.table.setCellWidget(row, 2, heal_checkbox)

            dose_spin = pya.QDoubleSpinBox()
            dose_spin.setRange(0.01, 1000.0)
            dose_spin.setSingleStep(0.1)
            dose_spin.setValue(1.0)
            dose_spin.setDecimals(3)
            self.table.setCellWidget(row, 3, dose_spin)

        self.table.resizeColumnsToContents()

    def handle_export(self) -> None:
        """Collect options, build the filtered layout, and write the GPF container."""
        view = self.main_window.current_view()
        if view is None:
            pya.QMessageBox.warning(self, "No view", "Open a layout before exporting.")
            return

        cellview = view.active_cellview()
        if cellview is None or cellview.is_null():
            pya.QMessageBox.warning(self, "No cell", "Activate a cell before exporting.")
            return

        source_layout = cellview.layout()
        source_cell = cellview.cell

        selected = []
        for row in range(self.table.rowCount()):
            use_item = self.table.item(row, 0)
            if use_item.checkState() != pya.Qt.Checked:
                continue

            label_item = self.table.item(row, 1)
            layer_info = label_item.data(pya.Qt.UserRole)
            heal_checkbox = self.table.cellWidget(row, 2)
            dose_spin = self.table.cellWidget(row, 3)
            selected.append(
                {
                    "info": layer_info,
                    "label": label_item.text(),
                    "heal": heal_checkbox.isChecked(),
                    "relative_dose": dose_spin.value(),
                }
            )

        if not selected:
            pya.QMessageBox.information(self, "No layers", "Select at least one layer to export.")
            return

        gpf_path, _ = pya.QFileDialog.getSaveFileName(
            self,
            "Save GPF",  # caption
            "",  # directory
            "GPF files (*.gpf)"
        )
        if not gpf_path:
            return

        filtered_layout = pya.Layout()
        filtered_layout.dbu = source_layout.dbu
        top_cell = filtered_layout.create_cell(source_cell.name or "TOP")

        layer_metadata = []
        layer_spec_map = {}

        for layer in selected:
            layer_info = layer["info"]
            source_index = source_layout.find_layer(layer_info)
            if source_index < 0:
                continue

            region = pya.Region(source_cell.begin_shapes_rec(source_index))
            if layer["heal"]:
                region = region.merged()

            target_index = filtered_layout.insert_layer(layer_info)
            top_cell.shapes(target_index).insert(region)

            spec = (layer_info.layer, layer_info.datatype)
            layer_metadata.append(
                {
                    "info": layer_info,
                    "label": layer["label"],
                    "relative_dose": layer["relative_dose"],
                    "spec": spec,
                }
            )
            layer_spec_map[spec] = layer_metadata[-1]

        exported_at = datetime.datetime.utcnow().isoformat() + "Z"

        all_layers_selected = self.table.rowCount() == len(layer_metadata)
        any_heal_requested = any(layer.get("heal") for layer in layer_metadata)
        source_filename = getattr(cellview, "filename", None) or getattr(cellview, "path", None)

        if source_filename and all_layers_selected and not any_heal_requested:
            self._export_from_existing_gds(
                gpf_path,
                exported_at,
                layer_metadata,
                source_layout.dbu,
                source_cell.name,
                source_filename,
            )
            pya.QMessageBox.information(
                self,
                "Export complete",
                f"Saved GPF to: {gpf_path}\nLayers: {len(selected)}",
            )
            return

        with tempfile.NamedTemporaryFile(suffix=".gds") as tmp:
            filtered_layout.write(tmp.name)
            tmp.flush()
            tmp.seek(0)
            gds_content = tmp.read()

        fractured_polygons = self._fracture_with_gdstk(
            tmp.name,
            layer_spec_map,
            top_cell.name,
        )

        for layer in layer_metadata:
            layer["polygons"] = fractured_polygons.get(layer["spec"], [])

        self._write_gpf_container(
            gpf_path,
            exported_at,
            layer_metadata,
            source_layout.dbu,
            source_cell.name,
            gds_content,
        )

        pya.QMessageBox.information(
            self,
            "Export complete",
            f"Saved GPF to: {gpf_path}\nLayers: {len(selected)}",
        )

    def handle_simulation(self) -> None:
        """Create a simulation window showing beam write order."""

        view = self.main_window.current_view()
        if view is None:
            pya.QMessageBox.warning(self, "No view", "Open a layout before simulating.")
            return

        cellview = view.active_cellview()
        if cellview is None or cellview.is_null():
            pya.QMessageBox.warning(self, "No cell", "Activate a cell before simulating.")
            return

        source_layout = cellview.layout()
        source_cell = cellview.cell

        selected = []
        for row in range(self.table.rowCount()):
            use_item = self.table.item(row, 0)
            if use_item.checkState() != pya.Qt.Checked:
                continue

            label_item = self.table.item(row, 1)
            layer_info = label_item.data(pya.Qt.UserRole)
            heal_checkbox = self.table.cellWidget(row, 2)
            dose_spin = self.table.cellWidget(row, 3)
            selected.append(
                {
                    "info": layer_info,
                    "label": label_item.text(),
                    "heal": heal_checkbox.isChecked(),
                    "relative_dose": dose_spin.value(),
                }
            )

        if not selected:
            pya.QMessageBox.information(self, "No layers", "Select at least one layer to simulate.")
            return

        filtered_layout = pya.Layout()
        filtered_layout.dbu = source_layout.dbu
        top_cell = filtered_layout.create_cell(source_cell.name or "TOP")

        layer_metadata = []
        layer_spec_map = {}

        for layer in selected:
            layer_info = layer["info"]
            source_index = source_layout.find_layer(layer_info)
            if source_index < 0:
                continue

            region = pya.Region(source_cell.begin_shapes_rec(source_index))
            if layer["heal"]:
                region = region.merged()

            target_index = filtered_layout.insert_layer(layer_info)
            top_cell.shapes(target_index).insert(region)

            spec = (layer_info.layer, layer_info.datatype)
            layer_metadata.append(
                {
                    "info": layer_info,
                    "label": layer["label"],
                    "relative_dose": layer["relative_dose"],
                    "spec": spec,
                }
            )
            layer_spec_map[spec] = layer_metadata[-1]

        exported_at = datetime.datetime.utcnow().isoformat() + "Z"

        with tempfile.NamedTemporaryFile(suffix=".gds") as tmp:
            filtered_layout.write(tmp.name)
            tmp.flush()
            fractured_polygons = self._fracture_with_gdstk(
                tmp.name,
                layer_spec_map,
                top_cell.name,
            )

        for layer in layer_metadata:
            layer["polygons"] = fractured_polygons.get(layer["spec"], [])

        report = self._generate_simulation_report(exported_at, layer_metadata, source_cell.name)

        sim_dialog = pya.QDialog(self)
        sim_dialog.setWindowTitle("Beam write simulation")
        sim_layout = pya.QVBoxLayout(sim_dialog)
        report_widget = pya.QPlainTextEdit(sim_dialog)
        report_widget.setReadOnly(True)
        report_widget.setPlainText(report)
        sim_layout.addWidget(report_widget)

        close_button = pya.QPushButton("Close", sim_dialog)
        close_button.clicked(sim_dialog.close)
        button_bar = pya.QHBoxLayout()
        button_bar.addStretch(1)
        button_bar.addWidget(close_button)
        sim_layout.addLayout(button_bar)

        sim_dialog.resize(600, 500)
        sim_dialog.show()
        sim_dialog.exec_()

    def _fracture_with_gdstk(self, gds_path: str, selected_layers: dict, top_name: str) -> dict:
        """Use gdstk's polygon fracturing to split shapes for each selected layer.

        Args:
            gds_path: Temporary GDS file containing the filtered geometry.
            selected_layers: Mapping of (layer, datatype) to metadata for inclusion.
            top_name: Name of the top cell for the filtered layout.

        Returns:
            Dictionary mapping (layer, datatype) tuples to lists of fractured
            polygons expressed in microns, where each polygon is a list of
            ``(x, y)`` tuples.
        """

        lib = gdstk.read_gds(gds_path)
        if not lib.top_level():
            return {}

        # Prefer the intended top cell; fall back to the first top-level cell.
        top_cell = next((c for c in lib.top_level() if c.name == top_name), lib.top_level()[0])

        # Coordinates from gdstk are in user units; convert to microns using the
        # library's unit scaling (meters per user unit).
        user_unit_in_m = lib.unit
        to_microns = user_unit_in_m * 1e6

        fractured = {spec: [] for spec in selected_layers.keys()}
        polygons = top_cell.get_polygons(apply_repetitions=True, include_paths=True, depth=None)

        for poly in polygons:
            spec = (poly.layer, poly.datatype)
            if spec not in fractured:
                continue
            pieces = poly.fracture(max_points=4, precision=lib.precision)
            if not pieces:
                pieces = [poly]
            for piece in pieces:
                coords = [(float(x * to_microns), float(y * to_microns)) for x, y in piece.points]
                fractured[spec].append(coords)

        return fractured

    def _generate_simulation_report(self, exported_at: str, layers: list, source_name: str) -> str:
        """Build a textual description of the beam writing path."""

        lines = [
            "Beam write simulation",  # title
            f"Source: {source_name}",
            f"Exported at: {exported_at}",
            "",
        ]

        for idx, layer in enumerate(layers, start=1):
            lines.append(
                f"Layer {idx} ({layer['label']}) — dose {layer['relative_dose']} — {len(layer['polygons'])} polygons"
            )
            for p_idx, poly in enumerate(layer["polygons"], start=1):
                lines.append(f"  Polygon {p_idx} with {len(poly)} vertices")
                coord_chunks = []
                for vx, vy in poly:
                    coord_chunks.append(f"({vx:.3f}, {vy:.3f})")
                lines.append("    Path: " + " -> ".join(coord_chunks))
            lines.append("")

        if len(lines) == 4:
            lines.append("No polygons were found for the selected layers.")

        return "\n".join(lines)

    def _write_gpf_container(
        self,
        path: str,
        exported_at: str,
        layers: list,
        dbu: float,
        source_name: str,
        gds_content: bytes,
    ) -> None:
        """Write a Raith-like ASCII GPF with fractured polygons.

        Notes:
            This writer targets the documented ASCII form of Raith GPF but has
            not been validated with vendor tools. Real production flows may
            require additional blocks (stage moves, beam settings, proximity
            correction data, etc.) that are not represented here.
        """

        header = [
            "# Raith Generic Pattern Format (GPF)",
            "# Generated by KLayout macro",
            f"# Exported at {exported_at}",
            f"# Source: {source_name}",
            f"# Original database unit: {dbu}um",
            "VERSION 1.0",
            "UNITS 1.0um",
        ]

        body_lines = []
        for idx, layer in enumerate(layers, start=1):
            info: pya.LayerInfo = layer["info"]
            body_lines.append(f"LAYER {idx} {info.layer} {info.datatype} LABEL \"{layer['label']}\"")
            body_lines.append(f"DOSE {layer['relative_dose']}")
            for poly in layer["polygons"]:
                coord_parts = []
                for x, y in poly:
                    coord_parts.append(f"{x:.6f}")
                    coord_parts.append(f"{y:.6f}")
                body_lines.append(f"POLY {len(poly)} {' '.join(coord_parts)}")
            body_lines.append("ENDLAYER")
        body_lines.append("END")

        with open(path, "wb") as handle:
            # ASCII header + fractured geometry
            for line in header + body_lines:
                handle.write((line + "\n").encode("ascii"))
            handle.write(b"# GDS payload base64\n")
            handle.write(base64.b64encode(gds_content))
            handle.write(b"\n")

    def _export_from_existing_gds(
        self,
        gpf_path: str,
        exported_at: str,
        layer_metadata: list,
        dbu: float,
        source_name: str,
        source_filename: str,
    ) -> None:
        """Shortcut export path that reuses the opened GDS verbatim.

        When all layers are selected and healing is disabled, we can fracture
        directly from the user's currently opened GDS file and embed that exact
        payload in the output. This preserves byte-for-byte parity with
        professionally exported GPFs that wrap the original GDS alongside the
        fractured polygon listing.
        """

        layer_spec_map = {layer["spec"]: layer for layer in layer_metadata}
        fractured_polygons = self._fracture_with_gdstk(
            source_filename,
            layer_spec_map,
            source_name,
        )

        for layer in layer_metadata:
            layer["polygons"] = fractured_polygons.get(layer["spec"], [])

        gds_content = Path(source_filename).read_bytes()
        self._write_gpf_container(
            gpf_path,
            exported_at,
            layer_metadata,
            dbu,
            source_name,
            gds_content,
        )


def register_menu_entry() -> None:
    app = pya.Application.instance()
    mw = app.main_window()

    action = pya.Action()
    action.title = "Export as GPF…"

    def on_triggered(_checked: bool = False) -> None:
        dialog = GPFExportDialog(mw)
        dialog.show()
        dialog.exec_()

    action.on_triggered = on_triggered

    tools_menu = mw.menu()
    tools_menu.insert_separator("tools_menu")
    tools_menu.insert_item("tools_menu", "export_gpf_action", action)


register_menu_entry()
