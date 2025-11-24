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
