import base64
import os
import subprocess
import sys
import types
from pathlib import Path

import gdstk


sys.path.append(str(Path(__file__).resolve().parents[1]))


def _install_pya_stub():
    if "pya" in sys.modules:
        return sys.modules["pya"]

    pya_stub = types.ModuleType("pya")

    class Qt:
        ItemIsUserCheckable = 1
        ItemIsEnabled = 2
        ItemIsSelectable = 4
        Checked = 1
        AlignCenter = 0

    class LayerInfo:
        def __init__(self, layer, datatype):
            self.layer = layer
            self.datatype = datatype

    class Action:
        def __init__(self):
            self.title = ""
            self.on_triggered = None

    class Menu:
        def insert_separator(self, *args, **kwargs):
            pass

        def insert_item(self, *args, **kwargs):
            pass

    class MainWindow:
        def __init__(self):
            self._menu = Menu()

        def menu(self):
            return self._menu

    class Application:
        def __init__(self):
            self._main_window = MainWindow()

        @staticmethod
        def instance():
            return Application()

        def main_window(self):
            return self._main_window

    pya_stub.Qt = Qt
    pya_stub.LayerInfo = LayerInfo
    pya_stub.Application = Application
    pya_stub.Action = Action
    pya_stub.MainWindow = MainWindow

    class QDialog:
        def __init__(self, *args, **kwargs):
            pass

    # Minimal Qt widgets used only for type resolution in class definitions
    class _Widget:
        def __init__(self, *args, **kwargs):
            pass

        def addWidget(self, *args, **kwargs):
            pass

        def addLayout(self, *args, **kwargs):
            pass

        def addStretch(self, *args, **kwargs):
            pass

        def setWindowTitle(self, *args, **kwargs):
            pass

        def resize(self, *args, **kwargs):
            pass

        def show(self, *args, **kwargs):
            pass

        def exec_(self, *args, **kwargs):
            pass

        def clicked(self, *args, **kwargs):
            return lambda *a, **k: None

        def setPlainText(self, *args, **kwargs):
            pass

        def setReadOnly(self, *args, **kwargs):
            pass

    pya_stub.QDialog = QDialog
    pya_stub.QVBoxLayout = _Widget
    pya_stub.QLabel = _Widget
    pya_stub.QTableWidget = _Widget
    pya_stub.QTableWidgetItem = _Widget
    pya_stub.QHBoxLayout = _Widget
    pya_stub.QPushButton = _Widget
    pya_stub.QCheckBox = _Widget
    pya_stub.QDoubleSpinBox = _Widget
    pya_stub.QMessageBox = _Widget
    pya_stub.QFileDialog = _Widget
    pya_stub.Region = _Widget
    pya_stub.Layout = _Widget
    pya_stub.QPlainTextEdit = _Widget

    sys.modules["pya"] = pya_stub
    return pya_stub


def test_fracture_with_gdstk_produces_micron_coordinates(tmp_path):
    _install_pya_stub()
    import export_gpf

    library = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = library.new_cell("TOP")
    polygon = gdstk.Polygon(
        [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)], layer=1, datatype=0
    )
    cell.add(polygon)

    gds_path = tmp_path / "fracture.gds"
    library.write_gds(str(gds_path))

    dialog = object.__new__(export_gpf.GPFExportDialog)
    fractured = dialog._fracture_with_gdstk(str(gds_path), {(1, 0): {}}, "TOP")

    assert (1, 0) in fractured
    assert fractured[(1, 0)], "Expected fractured polygons for selected layer"

    for polygon_coords in fractured[(1, 0)]:
        for x, y in polygon_coords:
            assert 0 <= x <= 2
            assert 0 <= y <= 2


def test_generate_simulation_report_summarizes_polygons():
    _install_pya_stub()
    import export_gpf

    dialog = object.__new__(export_gpf.GPFExportDialog)
    layers = [
        {
            "label": "RECT",
            "relative_dose": 1.0,
            "polygons": [
                [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
                [(2.0, 2.0), (3.0, 2.0), (3.0, 3.0), (2.0, 3.0)],
            ],
        }
    ]

    report = dialog._generate_simulation_report(
        "2024-01-01T00:00:00Z", layers, "TOP"
    )

    assert "Beam write simulation" in report
    assert "Layer 1 (RECT)" in report
    assert "2 polygons" in report
    assert "Polygon 2 with 4 vertices" in report
    assert "(2.000, 2.000)" in report


def test_export_with_freebeam_cli_uses_binary(tmp_path):
    pya = _install_pya_stub()
    import export_gpf

    dialog = object.__new__(export_gpf.GPFExportDialog)

    library = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = library.new_cell("TOP")
    cell.add(gdstk.rectangle((0, 0), (1, 1), layer=1, datatype=0))
    gds_path = tmp_path / "input.gds"
    library.write_gds(str(gds_path))

    stub_gpfout = tmp_path / "gpfout"
    stub_gpfout.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "open(sys.argv[2], 'w').write('freebeam-stub')\n"
    )
    os.chmod(stub_gpfout, 0o755)

    output_gpf = tmp_path / "output.gpf"
    dialog._export_with_freebeam_cli(
        str(stub_gpfout),
        str(output_gpf),
        "2024-01-01T00:00:00Z",
        [
            {
                "info": pya.LayerInfo(1, 0),
                "label": "RECT",
                "relative_dose": 1.0,
                "spec": (1, 0),
            }
        ],
        0.001,
        "TOP",
        str(gds_path),
    )

    assert output_gpf.read_text() == "freebeam-stub"


def test_export_with_freebeam_cli_can_emit_reference_fixture(tmp_path):
    pya = _install_pya_stub()
    import export_gpf

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    reference_gpf = fixtures / "pro_reference.gpf"

    # Decode embedded payload to reconstruct the GDS input
    payload_lines = []
    seen_payload = False
    for line in reference_gpf.read_text().splitlines():
        if seen_payload:
            payload_lines.append(line.strip())
        if line.strip() == "# GDS payload base64":
            seen_payload = True
    reference_gds = tmp_path / "pro_reference.gds"
    reference_gds.write_bytes(base64.b64decode("".join(payload_lines)))

    stub_gpfout = tmp_path / "gpfout"
    stub_gpfout.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys, pathlib\n"
        "out = pathlib.Path(sys.argv[2])\n"
        "ref = pathlib.Path(os.environ['REFERENCE_GPF'])\n"
        "out.write_text(ref.read_text())\n"
        "pathlib.Path(os.environ['ARG_LOG']).write_text(' '.join(sys.argv))\n"
    )
    os.chmod(stub_gpfout, 0o755)

    arg_log = tmp_path / "args.txt"
    env = os.environ.copy()
    env["REFERENCE_GPF"] = str(reference_gpf)
    env["ARG_LOG"] = str(arg_log)
    os.environ.update(env)

    dialog = object.__new__(export_gpf.GPFExportDialog)
    output_gpf = tmp_path / "output.gpf"

    # Directly exercise the Freebeam CLI helper
    subprocess_result = subprocess.run(
        [
            str(stub_gpfout),
            str(reference_gds),
            str(output_gpf),
            "0",
            "0",
            "10",
            "10",
            "10",
            "10",
            "0",
            "0",
            "5",
            "1",
            "100",
            str(tmp_path / "dose.txt"),
            "nopath",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert subprocess_result.returncode == 0

    dialog._export_with_freebeam_cli(
        str(stub_gpfout),
        str(output_gpf),
        "2024-01-01T00:00:00Z",
        [
            {
                "info": pya.LayerInfo(1, 0),
                "label": "RECT",
                "relative_dose": 1.0,
                "spec": (1, 0),
            }
        ],
        0.001,
        "TOP",
        str(reference_gds),
    )

    assert output_gpf.read_text() == reference_gpf.read_text()
    arg_line = arg_log.read_text()
    assert str(reference_gds) in arg_line
    assert str(output_gpf) in arg_line
