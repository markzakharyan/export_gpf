import base64
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


def test_write_gpf_container_writes_header_and_base64(tmp_path):
    pya = _install_pya_stub()
    import export_gpf

    dialog = object.__new__(export_gpf.GPFExportDialog)
    output_path = tmp_path / "output.gpf"

    layers = [
        {
            "info": pya.LayerInfo(1, 0),
            "label": "L1",
            "relative_dose": 2.5,
            "polygons": [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]],
        }
    ]
    gds_content = b"example_gds"

    dialog._write_gpf_container(
        str(output_path),
        "2024-01-01T00:00:00Z",
        layers,
        0.001,
        "TOP",
        gds_content,
    )

    data = output_path.read_text().splitlines()

    assert any(line.startswith("# Raith Generic Pattern Format") for line in data)
    assert "VERSION 1.0" in data
    assert "UNITS 1.0um" in data
    assert 'LAYER 1 1 0 LABEL "L1"' in data
    assert "DOSE 2.5" in data
    assert "POLY 3 0.000000 0.000000 1.000000 0.000000 1.000000 1.000000" in data
    assert data[-1] == base64.b64encode(gds_content).decode("ascii")


def _normalize_gpf(lines):
    """Strip timestamp noise so reference comparisons remain stable."""

    return [line for line in lines if not line.startswith("# Exported at ")]


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


def test_conversion_matches_professional_reference(tmp_path):
    pya = _install_pya_stub()
    import export_gpf

    dialog = object.__new__(export_gpf.GPFExportDialog)
    dialog.table = type("_Table", (), {"rowCount": lambda self: 2})()

    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    reference_gpf = fixtures / "pro_reference.gpf"

    # Decode the embedded GDS payload from the reference GPF to avoid storing
    # a binary fixture in the repo.
    payload_lines = []
    seen_payload = False
    for line in reference_gpf.read_text().splitlines():
        if seen_payload:
            payload_lines.append(line.strip())
        if line.strip() == "# GDS payload base64":
            seen_payload = True

    reference_gds = tmp_path / "pro_reference.gds"
    reference_gds.write_bytes(base64.b64decode("".join(payload_lines)))

    layers = [
        {
            "info": pya.LayerInfo(1, 0),
            "label": "RECT",
            "relative_dose": 1.0,
            "spec": (1, 0),
        },
        {
            "info": pya.LayerInfo(2, 0),
            "label": "POLY",
            "relative_dose": 1.2,
            "spec": (2, 0),
        },
    ]

    output_path = tmp_path / "output.gpf"
    dialog._export_from_existing_gds(
        str(output_path),
        "2024-01-01T00:00:00Z",
        layers,
        0.001,
        "TOP",
        str(reference_gds),
    )

    expected = _normalize_gpf(reference_gpf.read_text().splitlines())
    actual = _normalize_gpf(output_path.read_text().splitlines())

    assert actual == expected
