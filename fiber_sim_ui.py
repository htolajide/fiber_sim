# fiber_sim_ui.py
# Multilayer Fiber FPI Radiation Simulator
# Supports dual-layer endface coatings: TiO2 + Gd2O3 (separate layers)

import sys
import os
import subprocess
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import time
from datetime import datetime  # ← Add this line
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog, QTextEdit,
    QTabWidget, QFormLayout, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QThread, pyqtSignal

# === Move simulation logic to a worker thread ===
class SimulationWorker(QThread):
        finished = pyqtSignal()
        error = pyqtSignal(str)
        log_message = pyqtSignal(str)  # New signal for logging
        simulation_finished = pyqtSignal(str)  # ✅ New: sends output file path

        def __init__(self, parent=None):
            super().__init__(parent)
            self.main_window = parent

        def run(self):
            try:
                out_dir = self.main_window.output_folder.text()
                os.makedirs(out_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                base_name = self.main_window.sensor_type.currentText().replace(" ", "_")
                dose_filename = f"dose_{base_name}_{timestamp}.txt"
                dose_path = os.path.join(out_dir, dose_filename)
                self.main_window.current_dose_file = dose_path

                # === Generate layers.cfg ===
                cfg_file = os.path.join(out_dir, "layers.cfg")
                with open(cfg_file, 'w') as f:
                    for i in range(self.main_window.layer_table.rowCount()):
                        w = lambda j: self.main_window.layer_table.cellWidget(i, j)
                        name = w(0).text().strip()
                        mat = w(1).currentText().strip()
                        ir = w(2).text().strip()
                        orad = w(3).text().strip()
                        L = w(4).text().strip()
                        if all([name, mat, ir, orad, L]):
                            f.write(f"{name} {mat} {ir} {orad} {L}\n")
                self.log_message.emit("✅ Generated layers.cfg")

                # === Generate input.mac ===
                src = self.main_window.source_type.currentText()
                n = int(self.main_window.num_particles.text())

                fiber_length = 5.0
                radius = 75.0
                try:
                    lengths = [float(self.main_window.layer_table.cellWidget(i, 4).text()) 
                            for i in range(self.main_window.layer_table.rowCount())]
                    fiber_length = max(lengths) if lengths else 5.0
                    # calculate radius from outermost layer
                    last_row = self.layer_table.rowCount() - 1
                    outer_rad = float(self.layer_table.cellWidget(last_row, 3).text())
                    radius = max(outer_rad * 1.1, 80)  # 10% larger, or 80 μm
                except:
                    pass

                macro_file = os.path.join(out_dir, "input.mac")
                with open(macro_file, 'w') as f:
                    f.write("# Radiation Source Configuration\n")
                    f.write("/run/initialize\n\n")
                    f.write("/gps/pos/type Plane\n")
                    f.write("/gps/pos/shape Circle\n")
                    f.write(f"/gps/pos/centre 0 0 {-fiber_length/2:.3f} mm\n")
                    f.write(f"/gps/pos/radius {radius} um\n")
                    f.write("/gps/ang/type iso\n\n")

                    if "Cs-137" in src:
                        f.write("/gps/particle gamma\n/gps/energy 662 keV\n")
                        f.write(f"/run/beamOn {n}\n")
                    elif "Co-60" in src:
                        n1 = n // 2
                        n2 = n - n1
                        f.write("/gps/particle gamma\n")
                        f.write(f"/gps/energy 1.17 MeV\n/run/beamOn {n1}\n")
                        f.write(f"/gps/energy 1.33 MeV\n/run/beamOn {n2}\n")
                    elif "Neutron" in src:
                        f.write("/gps/particle neutron\n/gps/energy 0.025 eV\n")
                        f.write(f"/run/beamOn {n}\n")

                self.log_message.emit("✅ Generated input.mac")

                # === Build ===
                self.log_message.emit("🔧 Cleaning and setting up build directory...")
                build_cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{os.getcwd()}:/home/geant4/work",
                    "my-geant4",
                    "/bin/bash", "-c",
                    "rm -rf /home/geant4/work/build && "
                    "mkdir -p /home/geant4/work/build && "
                    "cd /home/geant4/work/build && "
                    "cmake .. && "
                    "make -j8"
                ]
                result = subprocess.run(build_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    self.log_message.emit("❌ Build failed!")
                    self.log_message.emit(result.stderr[:500])
                    return
                else:
                    self.log_message.emit("✅ Build successful.")

                # === Run ===
                self.log_message.emit("☢️ Running Geant4 simulation...")
                run_cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{out_dir}:/home/geant4/work",
                    "-e", "LD_LIBRARY_PATH=/home/geant4/geant4-install/lib",
                    "my-geant4",
                    "/home/geant4/work/build/fiber_sim", "input.mac"
                ]
                run_result = subprocess.run(run_cmd, capture_output=True, text=True)
                if run_result.returncode == 0:
                    old_path = os.path.join(out_dir, "dose_per_step.txt")
                    time.sleep(1)
                    if os.path.exists(old_path):
                        os.rename(old_path, dose_path)
                        self.log_message.emit(f"📁 Dose data saved as: {dose_filename}")
                        self.simulation_finished.emit(dose_path)  # ✅ Emit file path
                    else:
                        self.log_message.emit("❌ No output file generated!")
                else:
                    self.log_message.emit("❌ Simulation failed!")
                    self.log_message.emit(run_result.stderr)

                self.finished.emit()
                
            except Exception as e:
                self.error.emit(str(e))
                self.finished.emit()

# Fake G4NistManager for density lookup (if you don't have PyG4Py)
class G4NistManager:
    @staticmethod
    def Instance():
        return G4NistManager()

    def FindOrBuildMaterial(self, name):
        # Simulate real NIST/material behavior
        density_map = {
            "G4_SILICON_DIOXIDE": 2.20,
            "G4_AIR": 0.001205,
            "TiO2": 4.23,
            "Gd2O3": 7.41,
            "Al2O3": 3.97,
            "ZrO2": 5.68,
            "HfO2": 9.68,
        }
        density = density_map.get(name)
        if density is None:
            return None
        # Mock material with GetDensity() in mg/cm³
        class MockMat:
            def GetDensity(self):
                return density * 1000  # mg/cm³
        return MockMat()
    
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=8, height=6, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.ax = self.figure.add_subplot(111)
        super().__init__(self.figure)
        self.setParent(parent)


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

    def add_material(self, symbol, name, density, formula=None):
        """
        Add or update a material in the database
        Example: add_material("Y2O3", "Yttrium Oxide", 5.01, "Y2O3")
        """
        if not formula:
            formula = symbol  # fallback

        self.materials[symbol] = {
            "name": name,
            "density_g_cm3": float(density),
            "formula": formula
        }

        # Save immediately
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.materials, f, indent=2)
            return True
        except Exception as e:
            print(f"Failed to save material: {e}")
            return False

    def list_materials(self):
        return sorted(self.materials.keys())

    def get(self, name):
        return self.materials.get(name)


class FiberSimulationUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dual-Layer Coated Fiber FPI Simulator")
        self.setGeometry(700, 150, 1000, 1200)
        self.dose_data = None
        self.material_db = MaterialDB()

        # ✅ Initialize log early
        self.output_folder = None  # will be set in create_source_tab
        self.source_type = None
        self.num_particles = None
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.append("✅ Ready to simulate! Configure geometry and source.")

        self.init_ui()

    def browse_folder(self):
        """Open a dialog to select output folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)
    def init_ui(self):
        container = QWidget()
        layout = QVBoxLayout()
        tabs = QTabWidget()
        tabs.addTab(self.create_input_tab(), "Sensor Configuration") 
        tabs.addTab(self.create_output_tab(), "Results & Visualization")  #
        layout.addWidget(tabs)
        self.setCentralWidget(container)
        container.setLayout(layout)

    def create_input_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # =======================
        # 1. Sensor Type & Info
        # =======================
        hlay_type = QHBoxLayout()
        hlay_type.addWidget(QLabel("<b>Sensor Type:</b>"))
        self.sensor_type = QComboBox()
        self.sensor_type.addItems(["Standard Fiber FPI", "Micro-Cavity FPI"])
        self.sensor_type.currentTextChanged.connect(self.on_sensor_type_changed)
        hlay_type.addWidget(self.sensor_type)
        hlay_type.addStretch()
        layout.addLayout(hlay_type)

        # Tip
        info = QLabel(
            "💡 Layers stack radially outward. Add TiO₂ (e.g., 75.0 → 75.1 μm), then Gd₂O₃ on top."
        )
        info.setStyleSheet("QLabel { font-size: 10px; color: gray; }")
        layout.addWidget(info)

        # =======================
        # 2. Layer Table
        # =======================
        self.layer_table = QTableWidget()
        self.layer_table.setColumnCount(5)
        self.layer_table.setHorizontalHeaderLabels([
            "Name", "Material", "Inner Rad (μm)", "Outer Rad (μm)", "Length (mm)"
        ])
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.layer_table)

        # Buttons
        hlay_btns = QHBoxLayout()
        btn_add = QPushButton("➕ Add Layer"); btn_add.clicked.connect(self.add_layer_row)
        btn_clear = QPushButton("🗑️ Clear All"); btn_clear.clicked.connect(self.clear_layers)
        btn_reset = QPushButton("↺ Reset Default"); btn_reset.clicked.connect(self.default_layers)
        btn_dual = QPushButton("⚡ Add TiO₂ + Gd₂O₃ Coating")
        btn_dual.clicked.connect(self.add_dual_coating)
        hlay_btns.addWidget(btn_add); hlay_btns.addWidget(btn_dual); hlay_btns.addWidget(btn_clear); hlay_btns.addWidget(btn_reset)
        layout.addLayout(hlay_btns)

         # =======================
        # 5. Save / Load & Run
        # =======================
        hlay_save = QHBoxLayout()
        btn_save = QPushButton("💾 Save Geometry"); btn_save.clicked.connect(self.save_geometry)
        btn_load = QPushButton("📁 Load Geometry"); btn_load.clicked.connect(self.load_geometry)
        hlay_save.addWidget(btn_save); hlay_save.addWidget(btn_load)
        layout.addLayout(hlay_save)

        # =======================
        # 3. Geometry Preview
        # =======================
        layout.addWidget(QLabel("<b>Structure Preview:</b>"))
        self.preview_canvas = MplCanvas(self, width=6, height=2, dpi=100)
        layout.addWidget(self.preview_canvas)

        # =======================
        # 4. Radiation Source Settings
        # =======================
        layout.addWidget(QLabel("<b>Radiation Source:</b>"))

        form = QFormLayout()
        
        self.source_type = QComboBox()
        self.source_type.addItems(["Cs-137 (662 keV)", "Co-60", "Thermal Neutron"])
        form.addRow("Source:", self.source_type)

        self.num_particles = QLineEdit("50000")
        form.addRow("Particles:", self.num_particles)

        # Output folder
        self.output_folder = QLineEdit(os.getcwd())
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_folder)
        hlay_io = QHBoxLayout()
        hlay_io.addWidget(self.output_folder)
        hlay_io.addWidget(btn_browse)
        form.addRow("Output Folder:", hlay_io)

        layout.addLayout(form)

        # --- Add Custom Material Section ---
        mat_group = QGroupBox("Add Custom Material")
        mat_layout = QFormLayout()

        self.new_mat_symbol = QLineEdit()
        self.new_mat_symbol.setPlaceholderText("e.g., Y2O3")
        mat_layout.addRow("Chemical Symbol:", self.new_mat_symbol)

        self.new_mat_name = QLineEdit()
        self.new_mat_name.setPlaceholderText("e.g., Yttrium Oxide")
        mat_layout.addRow("Material Name:", self.new_mat_name)

        self.new_mat_density = QLineEdit()
        self.new_mat_density.setPlaceholderText("Density (g/cm³)")
        mat_layout.addRow("Density:", self.new_mat_density)

        btn_add_mat = QPushButton("➕ Add Material")
        btn_add_mat.clicked.connect(self.add_custom_material)
        mat_layout.addWidget(btn_add_mat)

        mat_group.setLayout(mat_layout)
        layout.addWidget(mat_group)


        # 🚀 Run Simulation Button (Big and visible!)
        btn_run = QPushButton("🚀 Run Simulation")
        btn_run.setStyleSheet("font-size: 14px; font-weight: bold; padding: 12px; background-color: #4CAF50; color: white; border-radius: 6px;")
        btn_run.clicked.connect(self.run_simulation)  # ← Connects to your method
        layout.addWidget(btn_run)

        # =======================
        # 6. Log Console
        # =======================
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.append("✅ Ready to simulate!")
        layout.addWidget(self.log)
        self.default_layers()
        widget.setLayout(layout)
        return widget
    
    def create_output_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

         # === Matplotlib Canvas ===
        self.canvas = MplCanvas(self, width=8, height=6, dpi=100)
        layout.addWidget(self.canvas)

        # Export buttons
        hlay = QHBoxLayout()
        btn_export_csv = QPushButton("💾 Export Dose Data (CSV)")
        btn_export_csv.clicked.connect(self.export_results_csv)
        btn_export_plot = QPushButton("📊 Export Plot (PNG)")
        btn_export_plot.clicked.connect(self.export_plot)
        hlay.addWidget(btn_export_csv)
        hlay.addWidget(btn_export_plot)
        layout.addLayout(hlay)

        widget.setLayout(layout)
        return widget

    def add_layer_row(self, name="", mat="", ir="", orad="", length="5.0"):
        row = self.layer_table.rowCount()
        self.layer_table.insertRow(row)

        # 🔧 Ensure all values are strings
        name = str(name) if name is not None else ""
        mat = str(mat) if mat is not None else ""
        ir = str(ir) if ir is not None else ""
        orad = str(orad) if orad is not None else ""
        length = str(length) if length is not None else "5.0"

        # Name
        name_w = QLineEdit(name)
        self.layer_table.setCellWidget(row, 0, name_w)

        # Material (dropdown)
        mat_combo = QComboBox()
        mat_combo.addItems(self.material_db.list_materials())
        idx = mat_combo.findText(mat)
        if idx >= 0:
            mat_combo.setCurrentIndex(idx)
        self.layer_table.setCellWidget(row, 1, mat_combo)

        # Other fields
        for col, val in enumerate([ir, orad, length], start=2):
            item = QLineEdit(str(val))  # 🔒 Force to string
            self.layer_table.setCellWidget(row, col, item)

        # Update preview
        self.update_preview()

    def clear_layers(self):
        self.layer_table.setRowCount(0)
        self.update_preview()

    def default_layers(self):
        self.clear_layers()
        if self.sensor_type.currentText() == "Micro-Cavity FPI":
            self.add_layer_row("Core", "G4_SILICON_DIOXIDE", "0", "4.1", "5.0")
            self.add_layer_row("Cladding", "G4_SILICON_DIOXIDE", "4.1", "75.0", "5.0")
            self.add_layer_row("Spacer", "G4_SILICON_DIOXIDE", "75.0", "80.0", "0.01")   # ← string!
            self.add_layer_row("Cavity", "G4_AIR", "80.0", "85.0", "0.005")              # ← string!
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

        # ✅ Now safe to use self.log
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

    def add_custom_material(self):
        symbol = self.new_mat_symbol.text().strip()
        name = self.new_mat_name.text().strip()
        density_str = self.new_mat_density.text().strip()

        if not all([symbol, name, density_str]):
            QMessageBox.warning(self, "Input Error", "All fields are required.")
            return

        try:
            density = float(density_str)
            if density <= 0:
                raise ValueError
        except:
            QMessageBox.warning(self, "Input Error", "Density must be a positive number.")
            return

        # Add to DB
        success = self.material_db.add_material(symbol, name, density)
        if success:
            self.log.append(f"✅ Added material: {symbol} ({name}, {density} g/cm³)")
            # Refresh all combo boxes
            self.refresh_material_combos()
            self.new_mat_symbol.clear()
            self.new_mat_name.clear()
            self.new_mat_density.clear()
        else:
            QMessageBox.critical(self, "Save Failed", "Could not save material to database.")

    def refresh_material_combos(self):
        """Refresh all material dropdowns in the layer table"""
        for i in range(self.layer_table.rowCount()):
            widget = self.layer_table.cellWidget(i, 1)
            if isinstance(widget, QComboBox):
                current = widget.currentText()
                widget.clear()
                widget.addItems(self.material_db.list_materials())
                idx = widget.findText(current)
                if idx >= 0:
                    widget.setCurrentIndex(idx)

    def save_geometry(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Geometry", "", "JSON Files (*.json)")
        if not filename: return

        data = []
        for i in range(self.layer_table.rowCount()):
            row = {}

            # Column 0: Name (QLineEdit)
            name_widget = self.layer_table.cellWidget(i, 0)
            row["name"] = name_widget.text() if name_widget else ""

            # Column 1: Material (QComboBox)
            mat_widget = self.layer_table.cellWidget(i, 1)
            row["material"] = mat_widget.currentText() if mat_widget else ""

            # Columns 2–4: Numbers (QLineEdit)
            try:
                row["inner_rad_um"] = float(self.layer_table.cellWidget(i, 2).text())
            except:
                row["inner_rad_um"] = 0.0
            try:
                row["outer_rad_um"] = float(self.layer_table.cellWidget(i, 3).text())
            except:
                row["outer_rad_um"] = 0.0
            try:
                row["length_mm"] = float(self.layer_table.cellWidget(i, 4).text())
            except:
                row["length_mm"] = 5.0

            data.append(row)

        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        self.log.append(f"✅ Saved geometry to: {filename}")

    def load_geometry(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load Geometry", "", "JSON Files (*.json)")
        if not filename: return
        try:
            with open(filename) as f:
                data = json.load(f)
            self.clear_layers()
            for d in data:
                self.add_layer_row(
                    str(d.get("name", "")),
                    str(d.get("material", "")),
                    str(d.get("inner_rad_um", "0")),
                    str(d.get("outer_rad_um", "0")),
                    str(d.get("length_mm", "5.0"))
                )
            self.log.append(f"📂 Loaded geometry from: {filename}")
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
        self.canvas = MplCanvas(self, width=8, height=6, dpi=100)
        layout.addWidget(btn_export)
        layout.addWidget(self.canvas)
        widget.setLayout(layout)
        return widget
    
    def run_simulation(self):
        # Prevent multiple runs
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.log.append("⚠️ Simulation already running!")
            return

        # Create worker thread
        self.worker = SimulationWorker(self)

        # Connect signals
        # ✅ Connect log signal
        self.worker.log_message.connect(self.log.append)
        self.worker.finished.connect(self.on_simulation_finished)
        self.worker.error.connect(lambda msg: self.log.append(f"💥 Error: {msg}"))
        self.worker.simulation_finished.connect(self.load_results)  # ✅ Load results when done
        # Start the thread
        self.worker.start()
        self.log.append("🔧 Started simulation in background...")

    def on_simulation_finished(self):
        self.log.append("🏁 Simulation finished.")
        # Optional: Enable buttons again
        # self.btn_run.setEnabled(True)

    def load_results(self, filename):
        if not os.path.exists(filename):
            self.log.append("❌ File not found!")
            return

        try:
            df = pd.read_csv(filename, sep='\t', comment='#', header=None)
            if len(df) == 0:
                self.log.append("⚠️ Output file is empty.")
                return

            df.columns = ['Volume', 'X', 'Y', 'Z', 'Edep_keV', 'StepLength_nm']
            df['Edep_J'] = df['Edep_keV'] * 1.602e-16
            self.dose_data = df
            self.log.append(f"📊 Loaded {len(df)} energy deposits.")

            # === Step 1: Extract layer geometry from UI ===
            volumes_to_mass = {}

            for i in range(self.layer_table.rowCount()):
                w = lambda j: self.layer_table.cellWidget(i, j)
                name = w(0).text().strip()
                mat_name = w(1).currentText().strip()
                ir = float(w(2).text()) * 1e-6  # μm → m
                orad = float(w(3).text()) * 1e-6  # μm → m
                length = float(w(4).text()) * 1e-3  # mm → m

                vol_name_pv = name + "_PV"

                # Get material from NIST or custom DB
                nist = G4NistManager.Instance() if hasattr(G4NistManager, 'Instance') else None
                mat = None
                if nist:
                    mat = nist.FindOrBuildMaterial(mat_name)
                if not mat:
                    # Fallback densities (g/cm³ → kg/m³)
                    density_map = {
                        "TiO2": 4.23,
                        "Gd2O3": 7.41,
                        "Al2O3": 3.97,
                        "ZrO2": 5.68,
                        "HfO2": 9.68,
                        "SiO2": 2.20,
                    }
                    density_gcm3 = density_map.get(mat_name, 2.20)  # default SiO2
                    density_kgm3 = density_gcm3 * 1000  # g/cm³ → kg/m³
                else:
                    density_kgm3 = mat.GetDensity() / 1000.0  # Geant4 stores in mg/cm³ → kg/m³

                # Volume = π(R² - r²) × L
                volume_m3 = 3.14159 * ((orad**2) - (ir**2)) * length
                mass_kg = volume_m3 * density_kgm3

                volumes_to_mass[vol_name_pv] = max(mass_kg, 1e-20)  # avoid zero

            # === Step 2: Group and compute dose ===
            self.log.append("🔍 Dose by volume:")
            grouped = df.groupby('Volume')['Edep_J'].sum()

            for vol, total_energy in grouped.items():
                if vol in volumes_to_mass:
                    mass = volumes_to_mass[vol]
                    dose_gy = total_energy / mass
                    self.log.append(f"  {vol}: {dose_gy:.6f} Gy")
                else:
                    self.log.append(f"  {vol}: ❓ Unknown volume (no geometry info)")

            self.plot_dose()

        except Exception as e:
            self.log.append(f"💥 Failed to load: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())

    def plot_dose(self):
        if self.dose_data is None:
            self.log.append("No dose data to plot.")
            return
        if self.canvas is None:
            self.log.append("Canvas not initialized.")
            return

        ax = self.canvas.ax
        ax.clear()

        df = self.dose_data.copy()

        # Compute radial position
        r = np.sqrt(df['X']**2 + df['Y']**2)

        # Filter out World hits for clarity (optional)
        mask = df['Volume'] != 'World'
        r = r[mask]
        z = df['Z'][mask]
        E = df['Edep_keV'][mask]

        if len(r) == 0:
            ax.text(0.5, 0.5, 'No valid data to plot', transform=ax.transAxes, ha='center')
        else:
            sc = ax.scatter(r, z, c=E, cmap='hot_r', s=5, alpha=0.9)
            ax.set_xlabel("Radial Position (μm)")
            ax.set_ylabel("Axial Position (μm)")
            ax.set_title("Energy Deposits in Fiber Sensor")
            ax.set_xlim(0, 80)
            ax.set_ylim(-2600, 2600)
            self.canvas.figure.colorbar(sc, ax=ax, label="Energy (keV)")

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
            self.canvas.figure.savefig(png_file, dpi=300, bbox_inches='tight')
            self.log.append(f"📊 Saved plot to {png_file}")


def main():
    app = QApplication(sys.argv)
    window = FiberSimulationUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()