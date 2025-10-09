# fiber_sim_ui.py
# Multilayer Fiber FPI Radiation Simulator
# Supports dual-layer endface coatings: TiO2 + Gd2O3 (separate layers)

import sys
import os
import subprocess
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog, QTextEdit,
    QTabWidget, QFormLayout, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PyQt5.QtCore import Qt


class MplCanvas(FigureCanvasQTAgg):
    """Matplotlib canvas embedded in PyQt5"""
    def __init__(self, parent=None, width=6, height=3, dpi=100):
        self.fig, self.ax = plt.subplots(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)


class MaterialDB:
    """Material database with pure oxides and coating materials"""
    def __init__(self, db_file="materials.json"):
        self.db_file = db_file
        self.materials = {}
        self.load_db()

    def load_db(self):
        if not os.path.exists(self.db_file):
            self.create_default_db()
        try:
            with open(self.db_file, 'r') as f:
                raw = json.load(f)
            self.materials = raw
        except Exception as e:
            print(f"Error loading materials: {e}")

    def create_default_db(self):
        default = {
            "G4_SILICON_DIOXIDE": {
                "name": "Fused Silica",
                "density_g_cm3": 2.20,
                "formula": "SiO2"
            },
            "G4_AIR": {
                "name": "Air",
                "density_g_cm3": 0.001205,
                "formula": "N2/O2"
            },
            "TiO2": {
                "name": "Titanium Dioxide",
                "density_g_cm3": 4.23,
                "formula": "TiO2"
            },
            "Gd2O3": {
                "name": "Gadolinium Oxide",
                "density_g_cm3": 7.41,
                "formula": "Gd2O3"
            },
            "Al2O3": {
                "name": "Aluminum Oxide",
                "density_g_cm3": 3.97,
                "formula": "Al2O3"
            },
            "ZrO2": {
                "name": "Zirconium Dioxide",
                "density_g_cm3": 5.68,
                "formula": "ZrO2"
            },
            "HfO2": {
                "name": "Hafnium Dioxide",
                "density_g_cm3": 9.68,
                "formula": "HfO2"
            }
        }
        with open(self.db_file, 'w') as f:
            json.dump(default, f, indent=2)

    def list_materials(self):
        return sorted(self.materials.keys())

    def get(self, name):
        return self.materials.get(name)


class FiberSimulationUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dual-Layer Coated Fiber FPI Simulator")
        self.setGeometry(100, 100, 1100, 800)
        self.dose_data = None
        self.material_db = MaterialDB()
        self.init_ui()

    def init_ui(self):
        container = QWidget()
        layout = QVBoxLayout()
        tabs = QTabWidget()
        tabs.addTab(self.create_input_tab(), "Sensor Configuration")
        tabs.addTab(self.create_output_tab(), "Results & Visualization")
        layout.addWidget(tabs)
        self.setCentralWidget(container)
        container.setLayout(layout)

    def create_input_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # --- Sensor Type ---
        hlay_type = QHBoxLayout()
        hlay_type.addWidget(QLabel("<b>Sensor Type:</b>"))
        self.sensor_type = QComboBox()
        self.sensor_type.addItems(["Standard Fiber FPI", "Micro-Cavity FPI"])
        self.sensor_type.currentTextChanged.connect(self.on_sensor_type_changed)
        hlay_type.addWidget(self.sensor_type)
        hlay_type.addStretch()
        layout.addLayout(hlay_type)

        # --- Layer Table ---
        self.layer_table = QTableWidget()
        self.layer_table.setColumnCount(5)
        headers = ["Name", "Material", "Inner Rad (μm)", "Outer Rad (μm)", "Length (mm)"]
        self.layer_table.setHorizontalHeaderLabels(headers)
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.layer_table)

        # Tooltips
        mat_tip = "Select material from database. For dual-layer coating:\n1. Add TiO₂ layer\n2. Add Gd₂O₃ on top"
        self.layer_table.horizontalHeaderItem(1).setToolTip(mat_tip)

        # --- Control Buttons ---
        hlay_btns = QHBoxLayout()
        btn_add = QPushButton("➕ Add Layer"); btn_add.clicked.connect(self.add_layer_row)
        btn_clear = QPushButton("🗑️ Clear All"); btn_clear.clicked.connect(self.clear_layers)
        btn_dual = QPushButton("⚡ Add TiO₂ + Gd₂O₃ Coating"); btn_dual.clicked.connect(self.add_dual_coating)
        btn_reset = QPushButton("↺ Reset Default"); btn_reset.clicked.connect(self.default_layers)

        hlay_btns.addWidget(btn_add)
        hlay_btns.addWidget(btn_clear)
        hlay_btns.addWidget(btn_dual)
        hlay_btns.addWidget(btn_reset)
        layout.addLayout(hlay_btns)

        # Info label
        info = QLabel(
            "💡 Layers are stacked radially outward. "
            "For dual-layer coating: TiO₂ (e.g., 100 nm) → Gd₂O₃ (e.g., 200 nm)"
        )
        info.setStyleSheet("QLabel { font-size: 10px; color: gray; }")
        layout.addWidget(info)

        # --- Geometry Preview ---
        layout.addWidget(QLabel("<b>Structure Preview (r-z):</b>"))
        self.preview_canvas = MplCanvas(self)
        layout.addWidget(self.preview_canvas)

        # --- Save/Load ---
        hlay_io = QHBoxLayout()
        btn_save = QPushButton("💾 Save Geometry"); btn_save.clicked.connect(self.save_geometry)
        btn_load = QPushButton("📁 Load Geometry"); btn_load.clicked.connect(self.load_geometry)
        hlay_io.addWidget(btn_save); hlay_io.addWidget(btn_load)
        layout.addLayout(hlay_io)

        # Initialize
        self.default_layers()
        widget.setLayout(layout)
        return widget

    def add_layer_row(self, name="", mat="", ir="", orad="", length="5.0"):
        row = self.layer_table.rowCount()
        self.layer_table.insertRow(row)
        name_w = QLineEdit(name)
        self.layer_table.setCellWidget(row, 0, name_w)
        mat_combo = QComboBox()
        mat_combo.addItems(self.material_db.list_materials())
        idx = mat_combo.findText(mat)
        if idx >= 0: mat_combo.setCurrentIndex(idx)
        self.layer_table.setCellWidget(row, 1, mat_combo)
        for col, val in enumerate([ir, orad, length], start=2):
            item = QLineEdit(val)
            self.layer_table.setCellWidget(row, col, item)
        self.update_preview()

    def clear_layers(self):
        self.layer_table.setRowCount(0)
        self.update_preview()

    def default_layers(self):
        self.clear_layers()
        if self.sensor_type.currentText() == "Micro-Cavity FPI":
            self.add_layer_row("Core", "G4_SILICON_DIOXIDE", "0", "4.1", "5.0")
            self.add_layer_row("Cladding", "G4_SILICON_DIOXIDE", "4.1", "75.0", "5.0")
            self.add_layer_row("Spacer", "G4_SILICON_DIOXIDE", "75.0", "80.0", "0.01")
            self.add_layer_row("Cavity", "G4_AIR", "80.0", "85.0", "0.005")
        else:
            self.add_layer_row("Core", "G4_SILICON_DIOXIDE", "0", "4.1", "5.0")
            self.add_layer_row("Cladding", "G4_SILICON_DIOXIDE", "4.1", "75.0", "5.0")

    def on_sensor_type_changed(self):
        reply = QMessageBox.question(
            self, 'Change Sensor Type',
            'This will reset current layers. Continue?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.default_layers()

    def add_dual_coating(self):
        if self.layer_table.rowCount() == 0:
            base_radius = 75.0  # Start after cladding
        else:
            try:
                base_radius = float(self.layer_table.cellWidget(self.layer_table.rowCount()-1, 3).text())
            except:
                base_radius = 75.0

        ti_thickness = 0.1   # 100 nm = 0.1 μm
        gd_thickness = 0.2   # 200 nm = 0.2 μm

        ti_outer = base_radius + ti_thickness
        gd_outer = ti_outer + gd_thickness

        self.add_layer_row("TiO2_Coating", "TiO2", f"{base_radius:.3f}", f"{ti_outer:.3f}", "5.0")
        self.add_layer_row("Gd2O3_Coating", "Gd2O3", f"{ti_outer:.3f}", f"{gd_outer:.3f}", "5.0")

        self.log.append("✅ Added TiO₂ (100 nm) + Gd₂O₃ (200 nm) dual-layer coating.")
        self.update_preview()

    def update_preview(self):
        ax = self.preview_canvas.ax
        ax.clear()
        layers = []
        for i in range(self.layer_table.rowCount()):
            try:
                name = self.layer_table.cellWidget(i, 0).text()
                ir = float(self.layer_table.cellWidget(i, 2).text())
                orad = float(self.layer_table.cellWidget(i, 3).text())
                L = float(self.layer_table.cellWidget(i, 4).text())
                layers.append((name, ir, orad, L))
            except:
                continue
        if not layers: return
        colors = ['#a8dadc', '#8d99ae', '#ef233c', '#8338ec', '#06d6a0', '#ffd60a']
        for i, (name, ir, orad, L) in enumerate(layers):
            rect = plt.Rectangle((-L/2, ir), L, orad - ir, facecolor=colors[i % len(colors)], edgecolor='black', linewidth=0.8)
            ax.add_patch(rect)
            ax.text(-L/2 + 0.05*L, (ir + orad)/2, name, fontsize=7, va='center', ha='left', color='white', weight='bold')
        max_r = max(l[2] for l in layers) * 1.1
        max_L = max(l[3] for l in layers)
        ax.set_xlim(-max_L/2*1.1, max_L/2*1.1)
        ax.set_ylim(0, max_r)
        ax.set_xlabel("Axial Position (mm)")
        ax.set_ylabel("Radial Position (μm)")
        ax.set_title("Fiber Sensor Structure")
        ax.grid(True, alpha=0.3)
        self.preview_canvas.draw()

    def save_geometry(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Geometry", "", "JSON Files (*.json)")
        if not filename: return
        data = []
        for i in range(self.layer_table.rowCount()):
            w = lambda j: self.layer_table.cellWidget(i, j).text()
            data.append({
                "name": w(0),
                "material": w(1),
                "inner_rad_um": w(2),
                "outer_rad_um": w(3),
                "length_mm": w(4)
            })
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        self.log.append(f"💾 Saved geometry to {filename}")
        self.update_preview()

    def load_geometry(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load Geometry", "", "JSON Files (*.json)")
        if not filename: return
        try:
            with open(filename) as f:
                data = json.load(f)
            self.clear_layers()
            for d in data:
                self.add_layer_row(
                    d["name"], d["material"],
                    d["inner_rad_um"], d["outer_rad_um"],
                    d["length_mm"]
                )
            self.log.append(f"📂 Loaded geometry from {filename}")
            self.update_preview()
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load geometry:\n{str(e)}")

    def create_output_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        self.canvas = MplCanvas(self, width=8, height=6, dpi=100)
        layout.addWidget(self.canvas)
        btn_export = QPushButton("💾 Export Results (CSV + Plot)")
        btn_export.clicked.connect(self.export_results)
        layout.addWidget(btn_export)
        widget.setLayout(layout)
        return widget

    def run_simulation(self):
        try:
            out_dir = self.output_folder.text()
            os.makedirs(out_dir, exist_ok=True)

            # Generate geometry.mac
            geo_file = os.path.join(out_dir, "geometry.mac")
            with open(geo_file, 'w') as f:
                for i in range(self.layer_table.rowCount()):
                    w = lambda j: self.layer_table.cellWidget(i, j).text()
                    name, mat, ir, orad, L = w(0), w(1), w(2), w(3), w(4)
                    f.write(f"/detector/config/addLayer {name} {mat} {ir} {orad} {L}\n")
            self.log.append("✅ Generated geometry.mac")

            # Generate radiation macro
            src = self.source_type.currentText()
            n = int(self.num_particles.text())
            macro_file = os.path.join(out_dir, "input.mac")
            with open(macro_file, 'w') as f:
                f.write("/run/initialize\ncuts/setLowEdge 10 eV\n")
                f.write("/gps/type Plane\n/gps/shape Circle\n/gps/radius 1 mm\n")
                f.write("/gps/ang/type iso\n/gps/position 0 0 -5 mm\n")
                if "Cs-137" in src:
                    f.write("/gps/particle gamma\n/gps/energy 662 keV\n/run/beamOn " + str(n) + "\n")
                elif "Co-60" in src:
                    f.write("/gps/particle gamma\n")
                    f.write(f"/gps/energy 1.17 MeV\n/run/beamOn {n//2}\n")
                    f.write(f"/gps/energy 1.33 MeV\n/run/beamOn {n//2}\n")
                elif "Neutron" in src:
                    f.write("/gps/particle neutron\n/gps/energy 0.025 eV\n")
                    f.write("/process/had/Verbosity 0\n/run/beamOn " + str(n) + "\n")
            self.log.append("✅ Generated input.mac")

            # Build simulation binary
            self.log.append("🔧 Building simulation...")
            build_cmd = [
                "docker", "run", "--rm",
                "-v", f"{os.getcwd()}:/home/geant4/work",
                "my-geant4",
                "/bin/bash", "-c",
                "cd /home/geant4/work/build || mkdir -p build && "
                "cd build && "
                "if [ ! -f CMakeCache.txt ]; then cmake ..; fi && "
                "make -j8"
            ]
            result = subprocess.run(build_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log.append("❌ Build failed!")
                self.log.append(result.stderr)
                QMessageBox.critical(self, "Build Failed", "Check logs.")
                return
            else:
                self.log.append("✅ Build successful.")

            # Run simulation
            self.log.append("☢️ Running Geant4 simulation...")
            run_cmd = [
                "docker", "run", "--rm",
                "-v", f"{out_dir}:/home/geant4/work",
                "my-geant4",
                "/home/geant4/work/build/fiber_sim"
            ]
            run_result = subprocess.run(run_cmd, capture_output=True, text=True)
            if run_result.returncode == 0:
                self.log.append("✅ Simulation completed!")
                self.load_results(os.path.join(out_dir, "dose_per_step.txt"))
            else:
                self.log.append(f"❌ Simulation failed: {run_result.stderr}")
                QMessageBox.critical(self, "Simulation Failed", "See log for details.")

        except Exception as e:
            self.log.append(f"💥 Error: {str(e)}")
            QMessageBox.critical(self, "Error", str(e))

    def create_source_tab(self):
        widget = QWidget()
        layout = QFormLayout()
        self.source_type = QComboBox()
        self.source_type.addItems(["Cs-137 (662 keV)", "Co-60", "Thermal Neutron"])
        layout.addRow("Radiation Source", self.source_type)
        self.num_particles = QLineEdit("50000")
        layout.addRow("Number of Particles", self.num_particles)
        self.output_folder = QLineEdit(os.getcwd())
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_folder)
        hlay = QHBoxLayout(); hlay.addWidget(self.output_folder); hlay.addWidget(btn_browse)
        layout.addRow("Output Folder", hlay)
        widget.setLayout(layout)
        return widget

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)

    def load_results(self, filename):
        if not os.path.exists(filename):
            self.log.append("❌ No output file found!")
            return
        df = pd.read_csv(filename, sep='\t', comment='#', header=None)
        df.columns = ['Volume', 'X', 'Y', 'Z', 'Edep_keV', 'StepLength_nm']
        df['Edep_J'] = df['Edep_keV'] * 1.602e-16
        self.dose_data = df
        self.log.append(f"📊 Loaded {len(df)} steps.")
        self.plot_dose()

    def plot_dose(self):
        if self.dose_data is None: return
        ax = self.canvas.ax
        ax.clear()
        r = (self.dose_data['X']**2 + self.dose_data['Y']**2)**0.5
        sc = ax.scatter(r, self.dose_data['Z'], c=self.dose_data['Edep_keV'], cmap='hot_r', s=3, alpha=0.8)
        ax.set_xlabel("Radial Position (μm)")
        ax.set_ylabel("Axial Position (μm)")
        ax.set_title("Energy Deposit Distribution")
        self.canvas.fig.colorbar(sc, ax=ax, label="Energy (keV)")
        self.canvas.draw()

    def export_results(self):
        if self.dose_data is None:
            QMessageBox.warning(self, "No Data", "Run simulation first.")
            return
        csv_file, _ = QFileDialog.getSaveFileName(self, "Save Dose Data", "", "CSV Files (*.csv)")
        if csv_file:
            self.dose_data.to_csv(csv_file, index=False)
            self.log.append(f"💾 Saved dose data to {csv_file}")
        png_file, _ = QFileDialog.getSaveFileName(self, "Save Plot", "", "PNG Files (*.png)")
        if png_file:
            self.canvas.fig.savefig(png_file, dpi=300, bbox_inches='tight')
            self.log.append(f"📊 Saved plot to {png_file}")


def main():
    app = QApplication(sys.argv)
    window = FiberSimulationUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()