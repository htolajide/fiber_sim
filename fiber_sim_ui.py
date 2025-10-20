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
from matplotlib.patches import Circle
import time
import re
from io import StringIO
from datetime import datetime  # ← Add this line
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog, QTextEdit,
    QSplitter, QFormLayout, QMessageBox, QTableWidget,
    QHeaderView, QGroupBox, QCheckBox, QTableWidgetItem
)
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QThread, pyqtSignal
import traceback

# === Move simulation logic to a worker thread ===
class SimulationWorker(QThread):
        finished = pyqtSignal()
        error = pyqtSignal(str)
        log_message = pyqtSignal(str)  # New signal for logging
        simulation_finished = pyqtSignal(str)  # ✅ New: sends output file path

        def __init__(self, parent=None):
            super().__init__(parent)
            self.main_window = parent
            self.is_stopped = False  # Flag to stop execution

        def stop(self):  # 👈 Add this method
            """Call this to request the worker to stop."""
            self.is_stopped = True

        def run(self):
            """Run Geant4 simulation using pre-generated config files"""
            try:
                if self.is_stopped:
                    return

                out_dir = self.main_window.output_folder.text().strip()
                if not os.path.exists(out_dir):
                    raise FileNotFoundError(f"Output directory does not exist: {out_dir}")

                # Paths to pre-generated files
                macro_file = os.path.join(out_dir, "input.mac")
                dose_temp = os.path.join(out_dir, "dose_per_step.txt")

                if not os.path.exists(macro_file):
                    raise FileNotFoundError("input.mac not found. Please run 'Run Simulation' to generate it.")

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                base_name = self.main_window.sensor_type.currentText().replace(" ", "_")
                dose_filename = f"dose_{base_name}_{timestamp}.txt"
                dose_path = os.path.join(out_dir, dose_filename)
                self.main_window.current_dose_file = dose_path  # Store for later use

                self.log_message.emit(f"📁 Output will be saved as: {dose_filename}")

                # === Build Geant4 Application (via Docker) ===
                self.log_message.emit("🔧 Cleaning and setting up build directory...")
                work_dir = os.getcwd()

                build_cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{work_dir}:/home/geant4/work",
                    "my-geant4",
                    "/bin/bash", "-c",
                    "cd /home/geant4/work && mkdir -p build && "
                    "cd build && "
                    "cmake .. && "           # Now .. refers to /home/geant4/work
                    "make -j$(nproc)"
                ]

                result = subprocess.run(build_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    self.error.emit("Build failed!")
                    self.log_message.emit(result.stderr[:1000])
                    return
                else:
                    self.log_message.emit("✅ Build successful.")

                # === Run Simulation ===
                self.log_message.emit("☢️ Running Geant4 simulation...")

                # Ensure output directory exists inside container
                prep_cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{out_dir}:/home/geant4/work/output",
                    "my-geant4",
                    "mkdir", "-p", "/home/geant4/work/output"
                ]
                subprocess.run(prep_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # === Run Simulation ===
                # Remove prep_cmd — no longer needed
                # Instead, ensure full project is mounted so fiber_sim can access layers.cfg and input.mac

                run_cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{work_dir}:/home/geant4/work",           # ✅ Mount full project (again)
                    "-e", "LD_LIBRARY_PATH=/home/geant4/geant4-install/lib",
                    "my-geant4",
                    "/home/geant4/work/build/fiber_sim",             # Executable
                    "/home/geant4/work/input.mac"                    # Macro file
                ]

                run_result = subprocess.run(run_cmd, capture_output=True, text=True)

                if run_result.returncode == 0:
                    time.sleep(0.5)
                    # Now dose_per_step.txt should be generated in out_dir
                    dose_temp = os.path.join(out_dir, "dose_per_step.txt")
                    if os.path.exists(dose_temp):
                        os.rename(dose_temp, dose_path)
                        self.log_message.emit(f"📁 Dose data saved as: {dose_filename}")
                        self.simulation_finished.emit(dose_path)
                    else:
                        self.error.emit("No output file generated by Geant4.")
                else:
                    self.error.emit("Simulation runtime error")
                    self.log_message.emit(run_result.stderr[:2000])

            except Exception as e:
                if not getattr(self, 'is_stopped', False):
                    self.error.emit(str(e))
            finally:
                if not getattr(self, 'is_stopped', False):
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
        self.setWindowTitle("Optical Fiber Interfermeter Radiation Dose Simulator")
        self.setGeometry(700, 150, 1000, 1200)
        self.dose_data = None
        self.material_db = MaterialDB()
        self.material_props = self.load_material_density()
        self.colorbar = None
        # ✅ Initialize cavity group as None
        self.cav_group = None

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
        self.setWindowTitle("Fiber FPI Radiation Simulation")
        self.setGeometry(300, 100, 1800, 1150)

        container = QWidget()
        container.setLayout(self.create_side_by_side_layout())
        self.setCentralWidget(container)  # Reuse existing widget
        # Now safe to access self.log
        self.setup_analysis()
       
    def create_side_by_side_layout(self):
        main_layout = QHBoxLayout()  # This will hold both panels

        # === Input Panel ===
        input_group = QGroupBox("Simulation Input")
        input_group.setFixedWidth(900)
        
        # Create a layout for the group box
        input_layout = QVBoxLayout()
        input_layout.addWidget(self.create_input_tab())  # Add the tab widget inside
        input_group.setLayout(input_layout)

        # === Output Panel ===
        output_group = QGroupBox("Results & Analysis")
        
        # Create a layout for the output panel
        output_layout = QVBoxLayout()
        output_layout.addWidget(self.create_output_tab())  # Add output tab
        output_group.setLayout(output_layout)

        # === Splitter (Optional: for resizable panels) ===
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(input_group)
        splitter.addWidget(output_group)
        splitter.setSizes([700, 700])

        # Add splitter to main layout
        main_layout.addWidget(splitter)

        return main_layout
    def setup_analysis(self):
        """Call this after UI is fully initialized"""
        self.material_props = self.load_material_density()
        if self.material_props is None:
            # Fallback defaults
            self.material_props = {
                'density': {},
                'specific_heat': {},
                'dn_dT_per_K': {}
            }
            
    def create_input_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        
        # --- Sensor Structure Selection ---
        # === 1. Sensor Type Selection ===
        hlay_type = QHBoxLayout()
        hlay_type.addWidget(QLabel("<b>Sensor Type:</b>"))
        self.sensor_type = QComboBox()
        self.sensor_type.addItems(["End-Face Coated FPI", "In-Fiber Microcavity"])
        self.sensor_type.currentTextChanged.connect(self.on_sensor_type_changed)
        hlay_type.addWidget(self.sensor_type)
        hlay_type.addStretch()
        layout.addLayout(hlay_type)
        

        # Tip info
        info = QLabel("💡 Layers stack radially outward. Add TiO₂ (e.g., 75.0 → 75.3 μm), then Gd₂O₃ on top.")
        info.setStyleSheet("QLabel { font-size: 10px; color: gray; }")
        layout.addWidget(info)


        # =======================
        # 3. Layer Table & Buttons
        # =======================
         # --- Layer Table ---
        self.layer_table = QTableWidget()
        self.layer_table.setColumnCount(6)
        self.layer_table.setHorizontalHeaderLabels([
            "Name", "Material", "Type",
            "Inner R (μm)", "Outer R (μm)", "Thickness / Length (mm)"
        ])
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        header_item = self.layer_table.horizontalHeaderItem(5)
        header_item.setToolTip("For End-Face Disk: axial thickness in mm\nFor others: length along fiber")
        layout.addWidget(self.layer_table)

        # Buttons
        hlay_btns = QHBoxLayout()
        btn_add = QPushButton("➕ Add Layer"); btn_add.clicked.connect(self.add_layer_row)
        btn_clear = QPushButton("🗑️ Clear All"); btn_clear.clicked.connect(self.clear_layers)
        btn_reset = QPushButton("↺ Reset Default"); btn_reset.clicked.connect(self.default_layers)
      

        hlay_btns.addWidget(btn_add)
        hlay_btns.addWidget(btn_clear)
        hlay_btns.addWidget(btn_reset)
        layout.addLayout(hlay_btns)
       
         # =======================
        # 4. Save / Load & Run
        # =======================
        hlay_save = QHBoxLayout()
        btn_save = QPushButton("💾 Save Geometry"); btn_save.clicked.connect(self.save_geometry)
        btn_load = QPushButton("📁 Load Geometry"); btn_load.clicked.connect(self.load_geometry)
        hlay_save.addWidget(btn_save); hlay_save.addWidget(btn_load)
        layout.addLayout(hlay_save)

         # === Move preview canvas BELOW table ===
        # ✅ Ensure preview_layout is only added ONCE
        if not hasattr(self, 'preview_layout'):
            self.preview_layout = QVBoxLayout()
            self.preview_layout.addWidget(QLabel("<b>Sensor Structure Preview:</b>"))
            
            # ✅ Increased height to 3.5 for better label visibility
            self.preview_canvas = MplCanvas(self, width=6, height=3.5, dpi=100)  # ← Was height=2
            self.preview_layout.addWidget(self.preview_canvas)
            layout.addLayout(self.preview_layout)
        else:
            # If already exists, don't re-add
            pass

        # =======================
        # 5. Radiation Source Settings
        # =======================
        layout.addWidget(QLabel("<b>Radiation Source:</b>"))

        # --- Radiation Source Configuration ---
        source_group = QGroupBox("Radiation Source")
        source_layout = QFormLayout()

        # Particle Type
        self.particle_combo = QComboBox()
        self.particle_combo.addItems(["gamma", "e-", "e+", "proton", "neutron"])
        source_layout.addRow("Particle:", self.particle_combo)

        self.num_particles = QLineEdit("50000")
        source_layout.addRow("Number of Particles:", self.num_particles)

        # Energy Mode
        self.energy_mode = QComboBox()
        self.energy_mode.addItems(["Monoenergetic", "Line Spectrum", "File Input"])
        self.energy_mode.currentTextChanged.connect(self.on_energy_mode_change)
        source_layout.addRow("Energy Mode:", self.energy_mode)

        # Energy Input
        self.energy_input = QLineEdit("0.662")  # Default in MeV
        self.energy_unit = QLabel("MeV")
        energy_hbox = QHBoxLayout()
        energy_hbox.addWidget(self.energy_input)
        energy_hbox.addWidget(self.energy_unit)
        source_layout.addRow("Energy:", energy_hbox)

        # Optional: Secondary line (for Co-60)
        self.second_line_layout = QHBoxLayout()
        self.second_line_check = QCheckBox("Add Second Line")
        self.second_line_check.stateChanged.connect(self.toggle_second_line)
        self.second_line_val = QLineEdit("1.332")
        self.second_line_val.setEnabled(False)
        self.second_line_layout.addWidget(self.second_line_check)
        self.second_line_layout.addWidget(QLabel("Energy (MeV):"))
        self.second_line_layout.addWidget(self.second_line_val)
        source_layout.addRow("", self.second_line_layout)

        # Or: Spectrum File
        self.spectrum_file = QLineEdit()
        self.spectrum_file.setPlaceholderText("Optionally load spectrum from CSV")
        self.spectrum_browse = QPushButton("Browse")
        self.spectrum_browse.clicked.connect(self.browse_spectrum_file)
        spec_layout = QHBoxLayout()
        spec_layout.addWidget(self.spectrum_file)
        spec_layout.addWidget(self.spectrum_browse)
        source_layout.addRow("Spectrum File:", spec_layout)
        self.spectrum_browse.setVisible(False)
        self.spectrum_file.setVisible(False)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)
        
        # Output folder
        self.output_folder = QLineEdit(os.getcwd())
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_folder)
        hlay_io = QHBoxLayout()
        hlay_io.addWidget(self.output_folder)
        hlay_io.addWidget(btn_browse)
        source_layout.addRow("Output Folder:", hlay_io)

        layout.addLayout(source_layout)

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

        # --- Experimental Calibration ---
        calib_group = QGroupBox("Experimental Calibration")
        calib_layout = QFormLayout()

        self.sensitivity_input = QLineEdit("-78.8")
        self.sensitivity_input.setPlaceholderText("e.g., -78.8")
        calib_layout.addRow("Sensitivity S_exp (nm/RIU):", self.sensitivity_input)

        calib_note = QLabel("💡 This comes from liquid refractometry (n = 1.33 → 1.40)")
        calib_note.setStyleSheet("QLabel { font-size: 11px; color: gray; }")
        calib_layout.addRow(calib_note)

        calib_group.setLayout(calib_layout)
        layout.addWidget(calib_group)


        # 🚀 Run Simulation Button (Big and visible!)
        btn_run = QPushButton("🚀 Run Simulation")
        btn_run.setStyleSheet("font-size: 14px; font-weight: bold; padding: 12px;")
        btn_run.clicked.connect(self.run_simulation)  # ← Connects to your method
        layout.addWidget(btn_run)

        # --- Stop Button ---
        self.btn_stop = QPushButton("⏹️ Stop Simulation")
        self.btn_stop.clicked.connect(self.stop_simulation)
        self.btn_stop.setEnabled(False)  # Initially disabled
        layout.addWidget(self.btn_stop)

        # =======================
        # 6. Log Console
        # =======================
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.append("✅ Ready to simulate!")
        layout.addWidget(self.log)
        self.default_layers()
        widget.setLayout(layout)

        self.default_layers()
        return widget
    
    ############### Layer Table Management ################
    def on_sensor_type_changed(self):
        """React when user changes sensor structure"""
        structure = self.sensor_type.currentText()
        self.log.append(f"🔧 Switched to: {structure}")
        
        # Clear current table
        self.layer_table.setRowCount(0)
        
        # Remove cavity group if exists
        if self.cav_group is not None:
            self.cav_group.setParent(None)
            self.cav_group = None

        # Load appropriate layers
        if structure == "End-Face Coated FPI":
            self.load_end_face_layers()
        elif structure == "In-Fiber Microcavity":
            self.load_microcavity_layers()

    def add_layer_row(self, name="", mat="", layer_type="Cylindrical", ir="", orad="", length="5.0"):
        try:
            row = self.layer_table.rowCount()
            self.layer_table.insertRow(row)

            # Name
            name_widget = QLineEdit(str(name))
            self.layer_table.setCellWidget(row, 0, name_widget)

            # Material
            if not hasattr(self, 'material_db'):
                raise AttributeError("material_db not initialized")

            mat_combo = QComboBox()
            mat_combo.addItems(self.material_db.list_materials())
            
            idx = mat_combo.findText(str(mat))
            if idx >= 0:
                mat_combo.setCurrentIndex(idx)
            self.layer_table.setCellWidget(row, 1, mat_combo)

            # Type
            type_combo = QComboBox()
            type_combo.addItems(["Solid Cylinder", "Hollow Cylinder", "End-Face Disk", "Microcavity Spacer", "Tapered Section"])
            t_idx = type_combo.findText(str(layer_type))
            if t_idx >= 0:
                type_combo.setCurrentIndex(t_idx)
            else:
                type_combo.setCurrentText("Hollow Cylinder")
            type_combo.currentTextChanged.connect(lambda: self.on_type_change(row))
            self.layer_table.setCellWidget(row, 2, type_combo)

            # Inner R
            ir_widget = QLineEdit(str(ir))
            self.layer_table.setCellWidget(row, 3, ir_widget)

            # Outer R
            orad_widget = QLineEdit(str(orad))
            self.layer_table.setCellWidget(row, 4, orad_widget)

            # Length
            len_widget = QLineEdit(str(length))
            self.layer_table.setCellWidget(row, 5, len_widget)

            self.update_preview()
            

        except Exception as e:
            import traceback
            print("❌ CRASH in add_layer_row():", str(e))
            print(traceback.format_exc())
            QMessageBox.critical(self, "Critical Error", f"Failed to add layer:\n{str(e)}")

    def on_type_change(self, row):
        w = lambda j: self.layer_table.cellWidget(row, j)
        layer_type = w(2).currentText()
        ir_widget = w(3)
        orad_widget = w(4)

        if layer_type == "Solid Cylinder":
            # Lock inner radius to 0
            ir_widget.setText("0.0")
            ir_widget.setEnabled(False)
            ir_widget.setPlaceholderText("Fixed: 0 μm")

            # Optional: Ensure outer radius is reasonable
            try:
                orad = float(orad_widget.text())
                if orad <= 0:
                    orad_widget.setText("4.1")  # Default core size
            except:
                orad_widget.setText("4.1")

        elif layer_type == "End-Face Disk":
            ir_widget.setEnabled(True)
            ir_widget.setPlaceholderText("Inner Radius (μm)")
            # Optionally suggest cladding outer radius
            if not ir_widget.text().strip():
                # Try to auto-fill based on previous layer?
                pass

        else:
            # Hollow Cylinder
            ir_widget.setEnabled(True)
            ir_widget.setPlaceholderText("Inner Radius (μm)")

        if layer_type == "End-Face Disk" and not ir_widget.text().strip():
            prev_row_irad = None
            if row > 0:
                prev_orad_widget = self.layer_table.cellWidget(row - 1, 4)
                if prev_orad_widget:
                    try:
                        prev_row_irad = float(prev_orad_widget.text())
                    except:
                        pass
            if prev_row_irad:
                ir_widget.setText(f"{prev_row_irad:.3f}")

        ir_widget.setToolTip(
            "For Solid Cylinder: fixed at 0\n"
            "For Hollow Cylinder / End-Face Disk: inner boundary radius (μm)"
)
        self.update_preview()

    def load_end_face_layers(self):
        """Load standard end-face coated FPI stack"""
        layers = [
            ("Core", "G4_SILICON_DIOXIDE", 0.0, 4.1),
            ("Cladding", "G4_SILICON_DIOXIDE", 4.1, 75.0),
            ("TiO2_Coating", "TiO2", 75.0, 75.3),
            ("Gd2O3_Coating", "Gd2O3", 75.3, 75.5)
        ]
        for name, mat, ir, orad in layers:
            row = self.layer_table.rowCount()
            self.layer_table.insertRow(row)

            self.layer_table.setItem(row, 0, QTableWidgetItem(name))

            mat_combo = QComboBox()
            mat_combo.addItems(["G4_SILICON_DIOXIDE", "TiO2", "Gd2O3"])
            mat_combo.setCurrentText(mat)
            self.layer_table.setCellWidget(row, 1, mat_combo)

            self.layer_table.setItem(row, 2, QTableWidgetItem(f"{ir:.1f}"))
            self.layer_table.setItem(row, 3, QTableWidgetItem(f"{orad:.1f}"))

            length = "5.0" if "Coating" not in name else "0.005"  # mm
            len_input = QLineEdit(length)
            self.layer_table.setCellWidget(row, 4, len_input)
            # Refresh preview
            self.update_preview()

    def load_microcavity_layers(self):
        """Load base layers for in-fiber microcavity"""
        layers = [
            ("Core", "G4_SILICON_DIOXIDE", 0.0, 4.1),
            ("Cladding", "G4_SILICON_DIOXIDE", 4.1, 75.0)
        ]
        for name, mat, ir, orad in layers:
            row = self.layer_table.rowCount()
            self.layer_table.insertRow(row)

            self.layer_table.setItem(row, 0, QTableWidgetItem(name))

            mat_combo = QComboBox()
            mat_combo.addItems(["G4_SILICON_DIOXIDE", "TiO2", "Gd2O3"])
            mat_combo.setCurrentText(mat)
            self.layer_table.setCellWidget(row, 1, mat_combo)

            self.layer_table.setItem(row, 2, QTableWidgetItem(f"{ir:.1f}"))
            self.layer_table.setItem(row, 3, QTableWidgetItem(f"{orad:.1f}"))

            len_input = QLineEdit("5.0")
            self.layer_table.setCellWidget(row, 4, len_input)

        # Add microcavity-specific inputs
        self.add_microcavity_parameters()
        # Refresh preview
        self.update_preview()

    def add_microcavity_parameters(self):
        """Add input fields for microcavity dimensions"""
        # Prevent duplicate creation
        if self.cav_group is not None:
            return
        
        self.cav_group = QGroupBox("Microcavity Parameters")
        cav_layout = QFormLayout()

        self.cav_radius = QLineEdit("5.0")   # μm
        self.cav_length = QLineEdit("150.0") # μm
        self.cav_zpos = QLineEdit("-2000.0") # μm
        self.cav_axis = QComboBox()
        self.cav_axis.addItems(["X", "Y"])

        cav_layout.addRow("Radius (μm):", self.cav_radius)
        cav_layout.addRow("Length (μm):", self.cav_length)
        cav_layout.addRow("Z Position (μm):", self.cav_zpos)
        cav_layout.addRow("Drill Axis:", self.cav_axis)

        self.cav_group.setLayout(cav_layout)

        # Add to layout (find main layout dynamically)
        main_layout = self.layout()  # Or store a reference
        if main_layout:
            main_layout.addWidget(self.cav_group)

    def preview_input_mac(self):
        mac_path = os.path.join(self.output_folder.text(), "input.mac")
        if not os.path.exists(mac_path):
            self.log.append("⚠️ input.mac not found. Run 'Run Simulation' first.")
            return
        with open(mac_path, 'r') as f:
            text = f.read()
        QMessageBox.information(self, "input.mac Content", text)

    def clear_layers(self):
        self.layer_table.setRowCount(0)
        self.update_preview()

    def default_layers(self):
        """Set up default layer stack based on selected sensor type"""
        self.clear_layers()
        
        sensor_type = self.sensor_type.currentText()

        if sensor_type == "In-Fiber Microcavity":
            # In-fiber microcavity: transverse hole for femtosecond-laser-drilled sensors
            self.add_layer_row("Core", "G4_SILICON_DIOXIDE", "Solid Cylinder", "0.0", "4.1", "5.0")
            self.add_layer_row("Cladding", "G4_SILICON_DIOXIDE", "Hollow Cylinder", "4.1", "75.0", "5.0")
            self.add_layer_row("Spacer", "G4_SILICON_DIOXIDE", "Hollow Cylinder", "75.0", "80.0", "0.01")   # 10 μm thick spacer
            self.add_layer_row("Cavity", "G4_AIR", "Hollow Cylinder", "80.0", "85.0", "0.005")              # 5 μm long cavity
        else:
            # Standard End-Face Coated FPI (most common case)
            self.add_layer_row("Core", "G4_SILICON_DIOXIDE", "Solid Cylinder", "0.0", "4.1", "5.0")
            self.add_layer_row("Cladding", "G4_SILICON_DIOXIDE", "Hollow Cylinder", "4.1", "75.0", "5.0")
            # ✅ 300 nm = 0.0003 mm, 200 nm = 0.0002 mm
            self.add_layer_row("TiO2_Coating", "TiO2", "End-Face Disk", "75.0", "75.3", "0.0003")
            self.add_layer_row("Gd2O3_Coating", "Gd2O3", "End-Face Disk", "75.3", "75.5", "0.0002")

        self.update_preview()

    def update_preview(self):
        if not hasattr(self, 'preview_canvas') or self.preview_canvas is None:
            return
            
        ax = self.preview_canvas.ax
        ax.clear()

        layers = []
        for i in range(self.layer_table.rowCount()):
            try:
                name_widget = self.layer_table.cellWidget(i, 0)
                mat_widget = self.layer_table.cellWidget(i, 1)
                type_widget = self.layer_table.cellWidget(i, 2)
                ir_widget = self.layer_table.cellWidget(i, 3)
                orad_widget = self.layer_table.cellWidget(i, 4)
                len_widget = self.layer_table.cellWidget(i, 5)

                if not all([name_widget, type_widget, ir_widget, orad_widget, len_widget]):
                    continue

                name = str(name_widget.text()).strip()
                layer_type = str(type_widget.currentText()).strip()
                ir = float(ir_widget.text())
                orad = float(orad_widget.text())
                L = float(len_widget.text())

                layers.append((name, layer_type, ir, orad, L))
            except Exception as e:
                continue

        if not layers:
            ax.set_xlim(-0.5, 0.5)
            ax.set_ylim(0, 80)
            ax.text(0, 40, "No layers defined", ha='center', va='center', fontsize=10, color='gray')
        else:
            # Color mapping
            colors = {
                'Core': 'blue',
                'Cladding': 'lightblue',
                'TiO2': 'red',
                'Gd2O3': 'darkred',
                'Spacer': 'orange',
                'Cavity': 'white',
                'Taper': 'purple'
            }

            z_pos = 0.0  # Axial position along fiber
            for i, (name, layer_type, ir, orad, L) in enumerate(layers):
                # Determine color
                color = 'gray'
                for key, col in colors.items():
                    if key in name or key in layer_type:
                        color = col
                        break

                # Draw geometry based on type
                if layer_type == "End-Face Disk":
                    # Thin axial disk at tip
                    ax.fill_betweenx([z_pos, z_pos + L], 0, orad,
                                color=color, edgecolor='black', linewidth=0.8, alpha=0.8)
                    # Label on the right
                    ax.text(orad + 2, z_pos + L/2, name,
                            fontsize=7, va='center', ha='left', color='black', weight='bold')
                    z_pos += L

                elif layer_type == "Solid Cylinder":
                    # Solid cylinder from center
                    ax.fill_betweenx([z_pos, z_pos + L], 0, orad,
                                color=color, edgecolor='black', linewidth=0.8, alpha=0.8)
                    ax.text(orad + 2, z_pos + L/2, name,
                            fontsize=7, va='center', ha='left', color='black', weight='bold')
                    z_pos += L

                elif layer_type == "TAPERED_SECTION":
                    # Tapered section: draw trapezoid
                    x_left = [z_pos, z_pos + L, z_pos + L, z_pos]
                    y_bottom = [ir, ir, orad, orad]  # Assuming outer radius changes
                    ax.fill(x_left, y_bottom, color=color, edgecolor='black', alpha=0.8)
                    ax.text(z_pos + L/2, (ir + orad)/2, name,
                            fontsize=7, va='center', ha='center', color='white', weight='bold')
                    z_pos += L

                else:
                    # Hollow Cylinder or MICROCAVITY_SPACER
                    ax.fill_betweenx([z_pos, z_pos + L], ir, orad,
                                color=color, edgecolor='black', linewidth=0.8, alpha=0.8)
                    ax.text(orad + 2, z_pos + L/2, name,
                            fontsize=7, va='center', ha='left', color='black', weight='bold')
                    z_pos += L

            ax.set_xlim(0, max(layer[3] for layer in layers) * 1.5)
            ax.set_ylim(-0.1, z_pos + 0.5)

        ax.set_xlabel("Radius (μm)")
        ax.set_ylabel("Z Position (mm)")
        ax.set_title("Fiber Sensor Structure Preview")
        ax.grid(True, alpha=0.3)
        self.preview_canvas.draw()

    def on_energy_mode_change(self):
        mode = self.energy_mode.currentText()
        self.energy_input.setVisible(mode != "File Input")
        self.energy_unit.setVisible(mode != "File Input")
        self.second_line_check.setVisible(mode == "Line Spectrum")
        self.spectrum_file.setVisible(mode == "File Input")
        self.spectrum_browse.setVisible(mode == "File Input")

    def toggle_second_line(self):
        checked = self.second_line_check.isChecked()
        self.second_line_val.setEnabled(checked)

    def generate_layers_cfg(self):
        """Generate layers.cfg with type tags matching C++ LayerType enum"""
        out_dir = self.output_folder.text().strip()
        #cfg_path = os.path.join(out_dir, "layers.cfg")
        if not out_dir:
            self.log.append("❌ Output folder not set")
            return
            
        try:
            os.makedirs(out_dir, exist_ok=True)
            cfg_path = os.path.join(out_dir, "layers.cfg")

            with open(cfg_path, 'w') as f:
                f.write("# Auto-generated by GUI\n")
                f.write(f"# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("# LayerType must match C++ enum: SOLID_CYLINDER, HOLLOW_CYLINDER, END_FACE_DISK, MICROCAVITY_SPACER, TAPERED_SECTION\n")

                for i in range(self.layer_table.rowCount()):
                    w = lambda j: self.layer_table.cellWidget(i, j)

                    # Safely extract widgets
                    name_widget = w(0)
                    mat_widget = w(1)
                    type_widget = w(2)      # "Type" combo box
                    ir_widget = w(3)        # Inner Radius
                    orad_widget = w(4)      # Outer Radius
                    len_widget = w(5)       # Length / Thickness

                    if not all([name_widget, mat_widget, type_widget, ir_widget, orad_widget, len_widget]):
                        self.log.append(f"⚠️ Row {i+1}: Missing widget, skipping.")
                        continue

                    try:
                        name = str(name_widget.text()).strip()
                        mat = str(mat_widget.currentText()).strip()
                        layer_type_str = str(type_widget.currentText()).strip()  # Use UI selection
                        ir = float(ir_widget.text())
                        orad = float(orad_widget.text())
                        length = float(len_widget.text())  # In mm

                        if not name or not mat:
                            self.log.append(f"⚠️ Row {i+1}: Empty name or material, skipping.")
                            continue

                    except Exception as e:
                        self.log.append(f"⚠️ Row {i+1}: Invalid numeric value, skipping.")
                        continue

                    # === Map UI Type to C++ Enum String ===
                    if layer_type_str == "Solid Cylinder":
                        c_type = "SOLID_CYLINDER"
                    elif layer_type_str == "Hollow Cylinder":
                        c_type = "HOLLOW_CYLINDER"
                    elif layer_type_str == "End-Face Disk":
                        c_type = "END_FACE_DISK"
                    elif "Taper" in name or "taper" in name:
                        c_type = "TAPERED_SECTION"
                    elif "Spacer" in name:
                        c_type = "MICROCAVITY_SPACER"
                    else:
                        c_type = "HOLLOW_CYLINDER"

                    # ✅ Write exactly 6 fields
                    f.write(f"{name} {mat} {ir:.6f} {orad:.6f} {length:.6f} {c_type}\n")

            self.log.append("✅ Generated layers.cfg with C++-compatible layer types")
            
        except Exception as e:
            self.log.append(f"❌ Failed to generate layers.cfg: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())

    def generate_input_mac(self):
        try:
            out_dir = self.output_folder.text()
            mac_path = os.path.join(out_dir, "input.mac")

            with open(mac_path, 'w') as f:
                f.write("# Geant4 Macro File - Auto-generated\n")
                f.write(f"# {self.sensor_type.currentText()} Source Configuration\n\n")

                # === Determine Sensor Type ===
                sensor_type = self.sensor_type.currentText()

                particle = "gamma"
                energy = "0.662 MeV"

                if hasattr(self, 'particle_combo'):
                    particle = self.particle_combo.currentText().lower()

                if hasattr(self, 'energy_input'):
                    try:
                        energy_val = float(self.energy_input.text())
                        energy = f"{energy_val:.6f} MeV"
                    except:
                        pass

                # === Source Setup Based on Sensor Type ===
                if sensor_type == "In-Fiber Microcavity":
                    f.write("# Source Setup: Transverse Illumination for Microcavity\n")
                    f.write("/gps/pos/type Plane\n")
                    f.write("/gps/pos/shape Circle\n")
                    f.write("/gps/pos/radius 100 um\n")           # Cover radial extent
                    f.write("/gps/pos/centre 0 0 0 mm\n")         # At cavity center
                    f.write("/gps/rot/z 90 deg\n")                # Emit in X-Y plane (transverse)
                    #f.write("/gps/direction 0 0 -1\n")  # ✅ Correct command                            # Point backward into fiber
                    f.write("/gps/ang/type iso\n")
                    f.write("/gps/ang/mintheta 0 deg\n")              # Min polar angle
                    f.write("/gps/ang/maxtheta 10 deg\n")     # Wide cone
                    f.write("/gps/ene/type Mono\n")
                    f.write(f"/gps/particle {particle}\n")
                    f.write(f"/gps/energy {energy}\n\n")

                else:
                    # Standard End-Face Coated FPI
                    f.write("# Source Setup: End-Face Illumination\n")
                    f.write("/gps/pos/type Plane\n")
                    f.write("/gps/pos/shape Circle\n")
                    f.write("/gps/pos/radius 83.05 um\n")         # Slightly larger than coating
                    f.write("/gps/pos/centre 0 0 -0.1 mm\n")      # Just in front of tip
                    f.write("/gps/direction 0 0 -1\n")  # ✅ Correct command                            # Point backward into fiber
                    f.write("/gps/ang/type iso\n")
                    f.write("/gps/ang/mintheta 0 deg\n")              # Min polar angle
                    f.write("/gps/ang/maxtheta 10 deg\n")       # Forward-peaked cone
                    f.write("/gps/ene/type Mono\n")
                    f.write(f"/gps/particle {particle}\n")
                    f.write(f"/gps/energy {energy}\n\n")

                # Run Settings
                n_events = 1000
                if hasattr(self, 'num_particles'):
                    try:
                        n_events = int(self.num_particles.text())
                    except:
                        pass
                f.write(f"/run/beamOn {n_events}\n")

            self.log.append(f"✅ Generated input.mac with {n_events} events")
            
        except Exception as e:
            self.log.append(f"❌ Failed to generate input.mac: {str(e)}")

    def generate_input_mac(self):
        try:
            out_dir = self.output_folder.text()
            mac_path = os.path.join(out_dir, "input.mac")

            with open(mac_path, 'w') as f:
                f.write("# Geant4 Macro File - Auto-generated\n")
                f.write("# End-Face Fiber Illumination Setup\n\n")

                # === General Particle Source (GPS) ===
                particle = "gamma"
                energy = "0.662 MeV"

                if hasattr(self, 'particle_combo'):
                    particle = self.particle_combo.currentText().lower()

                if hasattr(self, 'energy_input'):
                    try:
                        energy_val = float(self.energy_input.text())
                        energy = f"{energy_val:.6f} MeV"
                    except:
                        pass

                # Determine outer radius from layers (use cladding or coating)
                fiber_radius_um = 75.0  # Default
                try:
                    for i in range(self.layer_table.rowCount()):
                        w = lambda j: self.layer_table.cellWidget(i, j)
                        name = w(0).text().strip()
                        orad_str = w(4).text().strip() if w(4) else ""
                        if orad_str.replace('.', '').isdigit():
                            orad = float(orad_str)
                            # Use largest radius (e.g., Gd2O3 coating)
                            if "Coating" in name or "coating" in name:
                                fiber_radius_um = max(fiber_radius_um, orad)
                    # Add margin to ensure full coverage
                    beam_radius_um = fiber_radius_um * 1.1
                except Exception as e:
                    self.log.append(f"⚠️ Using default beam radius: {fiber_radius_um} μm")

                # GPS Configuration for end-face illumination
                f.write("# Source Setup: End-Face Illumination\n")
                f.write("/gps/pos/type Plane\n")
                f.write("/gps/pos/shape Circle\n")
                f.write(f"/gps/pos/radius {beam_radius_um} um\n")           # Slightly larger than coating
                f.write("/gps/pos/centre 0 0 -0.1 mm\n")                   # Just in front of fiber tip
                f.write("/gps/direction 0 0 -1\n")  # ✅ Correct command                            # Point backward into fiber
                f.write("/gps/ang/type iso\n")
                f.write("/gps/ang/mintheta 0 deg\n")              # Min polar angle
                f.write("/gps/ang/maxtheta 10 deg\n")                              # Forward-peaked cone
                f.write("/gps/ene/type Mono\n")
                f.write(f"/gps/particle {particle}\n")
                f.write(f"/gps/energy {energy}\n\n")

                # Run Settings
                n_events = 1000
                if hasattr(self, 'num_particles'):
                    try:
                        n_events = int(self.num_particles.text())
                    except:
                        pass
                f.write(f"/run/beamOn {n_events}\n")

            self.log.append(f"✅ Generated input.mac with {n_events} events for end-face illumination")
            
        except Exception as e:
            self.log.append(f"❌ Failed to generate input.mac: {str(e)}")
    
    def plot_end_face_fpi(self, ax):
        """Draw end-face coated FPI: axial stack of layers"""
        z_pos = 0.0  # Start at z = 0
        colors = {
            'Core': 'blue',
            'Cladding': 'lightblue',
            'TiO2_Coating': 'red',
            'Gd2O3_Coating': 'darkred'
        }

        for i in range(self.layer_table.rowCount()):
            w = lambda j: self.layer_table.cellWidget(i, j)
            name = w(0).text().strip()
            ir_um = float(w(2).text())
            orad_um = float(w(3).text())
            length_mm = float(w(4).text())

            color = 'gray'
            for key, col in colors.items():
                if key in name:
                    color = col
                    break

            # Draw as rectangle: (r_inner, r_outer) × (z_start, z_end)
            z_end = z_pos + length_mm
            ax.fill_betweenx(
                [z_pos, z_end],
                [ir_um, ir_um],
                [orad_um, orad_um],
                color=color,
                edgecolor='black',
                linewidth=0.5,
                alpha=0.8
            )
            ax.text(orad_um + 2, z_pos + length_mm/2, name, ha='left', va='center', fontsize=8)

            z_pos += length_mm

        ax.set_xlim(0, 90)
        ax.set_ylim(-0.1, z_pos + 0.5)

    def plot_microcavity(self, ax):
        """Draw in-fiber microcavity: transverse hole through core/cladding"""
        # Fiber body
        z_fiber = 5.0  # mm
        ax.fill_betweenx([0, z_fiber], 0, 75, color='lightblue', alpha=0.6, label="Cladding")
        ax.fill_betweenx([0, z_fiber], 0, 4.1, color='blue', alpha=0.8, label="Core")

        # Cavity parameters from UI
        try:
            cav_radius = float(self.cav_radius.text())     # μm
            cav_length = float(self.cav_length.text())     # μm → convert to mm
            cav_zpos = float(self.cav_zpos.text())         # μm → convert to mm
            axis = self.cav_axis_combo.currentText()       # X or Y
        except:
            cav_radius, cav_length, cav_zpos, axis = 5.0, 150.0, -2000.0, "X"

        cav_zpos_mm = cav_zpos * 1e-3  # μm → mm
        cav_length_mm = cav_length * 1e-3

        if axis == "X":
            # Drilled along X-axis → appears as circle in Y-Z plane
            center_y = 0
            ax.add_patch(Circle((center_y, cav_zpos_mm), cav_radius,
                                color='gray', alpha=0.7, label=f"Cavity ({axis})"))
            ax.text(center_y + cav_radius + 2, cav_zpos_mm, "Microcavity", 
                    ha='left', va='center', fontsize=9, color='black')
        else:
            # Drilled along Y-axis → same visual
            center_x = 0
            ax.add_patch(Circle((center_x, cav_zpos_mm), cav_radius,
                                color='gray', alpha=0.7, label=f"Cavity ({axis})"))
            ax.text(center_x + cav_radius + 2, cav_zpos_mm, "Microcavity", 
                    ha='left', va='center', fontsize=9, color='black')

        ax.set_xlim(-40, 90)
        ax.set_ylim(cav_zpos_mm - 1.0, cav_zpos_mm + 1.0)

    def browse_spectrum_file(self):
        """Open file dialog to select a custom energy spectrum file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Energy Spectrum File",
            "",
            "CSV Files (*.csv);;Text Files (*.txt);;All Files (*)"
        )
        if filename:
            self.spectrum_file.setText(filename)
            self.log.append(f"📁 Selected spectrum file: {os.path.basename(filename)}")

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
        """
        Refresh all material combo boxes in the layer table and source settings.
        Should be called after loading materials.json or modifying the database.
        """
        try:
            # Get current material lists from material_db
            materials_list = self.material_db.list_materials() if hasattr(self, 'material_db') else []

            if not materials_list:
                self.log.append("⚠️ No materials available in database.")
                return

            # Update every row's material combo
            for i in range(self.layer_table.rowCount()):
                widget = self.layer_table.cellWidget(i, 1)
                if isinstance(widget, QComboBox):
                    current_text = widget.currentText()
                    widget.clear()
                    widget.addItems(materials_list)
                    idx = widget.findText(current_text)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                    else:
                        fallback = "G4_SILICON_DIOXIDE"
                        idx_fb = widget.findText(fallback)
                        if idx_fb >= 0:
                            widget.setCurrentIndex(idx_fb)

            # Also refresh any other combos (e.g., add custom material dialog)
            if hasattr(self, 'source_type'):
                pass  # If source_type uses materials, update it too

            self.log.append("✅ Material dropdowns refreshed.")

        except Exception as e:
            self.log.append(f"❌ Failed to refresh material combos: {str(e)}")

    def save_geometry(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Geometry", "", "JSON Files (*.json)")
        if not filename: return

        data = []
        for i in range(self.layer_table.rowCount()):
            row = {}

            # Column 0: Name
            name_widget = self.layer_table.cellWidget(i, 0)
            row["name"] = name_widget.text().strip() if name_widget else ""

            # Column 1: Material
            mat_widget = self.layer_table.cellWidget(i, 1)
            row["material"] = mat_widget.currentText().strip() if mat_widget else ""

            # Column 2: Type
            type_widget = self.layer_table.cellWidget(i, 2)
            row["type"] = type_widget.currentText().strip() if type_widget else "Cylindrical"

            # Column 3: Inner Radius
            ir_widget = self.layer_table.cellWidget(i, 3)
            try:
                row["inner_rad_um"] = float(ir_widget.text())
            except:
                row["inner_rad_um"] = 0.0

            # Column 4: Outer Radius
            orad_widget = self.layer_table.cellWidget(i, 4)
            try:
                row["outer_rad_um"] = float(orad_widget.text())
            except:
                row["outer_rad_um"] = 0.0

            # Column 5: Length
            len_widget = self.layer_table.cellWidget(i, 5)
            try:
                row["length_mm"] = float(len_widget.text())
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
                    str(d.get("type", "Cylindrical")),           # ← New
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
        btn_export = QPushButton("💾 Export Results (excel)")
        btn_export.setStyleSheet("font-size: 14px; padding: 8px;")
        btn_export.clicked.connect(self.export_results)
        layout.addWidget(btn_export)

        # === Analysis Button ===
        btn_analyze = QPushButton("🔬 Analyze Dose")
        btn_analyze.setStyleSheet("font-size: 14px; padding: 8px;")
        btn_analyze.clicked.connect(self.analyze_dose)
        layout.addWidget(btn_analyze)

        # === Export Dose Summary Button ===
        btn_export_summary = QPushButton("📄 Export Dose Summary")
        btn_export_summary.setStyleSheet("font-size: 14px; padding: 8px;")
        btn_export_summary.clicked.connect(self.export_dose_summary)
        layout.addWidget(btn_export_summary)
        widget.setLayout(layout)
        return widget

    def kill_hanging_docker_processes(self):
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "--filter", "ancestor=my-geant4"],
                capture_output=True, text=True
            )
            container_ids = result.stdout.strip().splitlines()
            for cid in container_ids:
                if cid:
                    subprocess.run(["docker", "kill", cid])
                    self.log.append(f"🧹 Killed hanging Docker container: {cid}")
        except Exception as e:
            self.log.append(f"⚠️ Could not kill Docker processes: {str(e)}")

    def stop_simulation(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()  # Signal worker to stop
            self.log.append("🛑 Stopping simulation...")
            self.btn_stop.setEnabled(False)

    def run_simulation(self):
        """Start the simulation after generating config files"""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.log.append("⚠️ Waiting for previous simulation to stop...")
            self.worker.stop()
            self.worker.wait(3000)

        try:
            # --- Step 1: Generate config files in UI ---
            out_dir = self.output_folder.text().strip()
            os.makedirs(out_dir, exist_ok=True)

            self.generate_layers_cfg()   # Already defined in your UI
            self.generate_input_mac()    # Already defined in your UI

            self.log.append("✅ Configuration files generated.")

            # --- Step2: Start worker ---
            self.worker = SimulationWorker(self)
            self.worker.log_message.connect(self.log.append)
            self.worker.finished.connect(self.on_simulation_finished)
            self.worker.error.connect(lambda msg: self.log.append(f"💥 Error: {msg}"))
            self.worker.simulation_finished.connect(self.load_results)

            self.btn_stop.setEnabled(True)
            self.kill_hanging_docker_processes()

            self.worker.start()
            self.log.append("🔧 Started simulation in background...")

        except Exception as e:
            self.log.append(f"❌ Failed to prepare simulation: {str(e)}")

    def on_simulation_finished(self):
        self.log.append("🏁 Simulation finished.")
        # Optional: Enable buttons again
        self.btn_stop.setEnabled(False)  # Disable when done

    def export_dose_summary(self):
        if self.dose_summary_df is None:
            QMessageBox.warning(self, "No Data", "Run 'Analyze Dose' first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Dose Summary", "", "CSV Files (*.csv)")
        if not file_path:
            return

        # Add derived summary row
        summary_row = {
            'Layer': 'SUMMARY',
            'Material': 'System-Level',
            'Type': 'N/A',
            'Inner_Radius_um': '',
            'Outer_Radius_um': '',
            'Thickness_nm': '',
            'Length_mm': '',
            'Mass_kg': '',
            'Energy_J': self.dose_summary_df['Energy_J'].sum(),
            'Dose_Gy': '',  # Not directly additive
            'Delta_T_K': '',
            'Delta_n': '',
            'Specific_Heat_J_kgK': '',
            'dn_dT_per_K': '',
            'Step_Count': self.dose_summary_df['Step_Count'].sum()
        }

        # Append summary
        df_export = pd.concat([self.dose_summary_df, pd.DataFrame([summary_row])], ignore_index=True)

        # Save
        df_export.to_csv(file_path, index=False)
        self.log.append(f"📁 Saved dose summary to {file_path}")

        # Also save responsivity as separate line?
        with open(file_path, 'a') as f:
            f.write(f"\n# Responsivity (pm/Gy): {getattr(self, 'sensor_responsivity', 0):.3f}\n")
            f.write(f"# Sensitivity (nm/RIU): {getattr(self, 'sensitivity_input', None).text()}\n")

    def get_layers_from_ui(self):
        """Extract layer geometry from UI table using materials.json for properties"""
        if not hasattr(self, 'material_props') or self.material_props is None:
            # Fallback if materials.json not loaded
            self.material_props = {
                'density': {},
                'specific_heat': {}
            }

        layers = []
        for i in range(self.layer_table.rowCount()):
            w = lambda j: self.layer_table.cellWidget(i, j)
            name = w(0).text().strip()
            mat_name = w(1).currentText().strip()
            ir_um = float(w(2).text())
            orad_um = float(w(3).text())
            length_mm = float(w(4).text())
            vol_name_pv = name + "_PV"

            # Get from materials.json or default
            rho_gcm3 = self.material_props['density'].get(mat_name, 2.20)
            specific_heat = self.material_props['specific_heat'].get(mat_name, 700)

            layers.append({
                'name': name,
                'material': mat_name,
                'vol_name_pv': vol_name_pv,
                'ir_um': ir_um,
                'orad_um': orad_um,
                'length_mm': length_mm,
                'density_gcm3': rho_gcm3,
                'specific_heat_J_per_kg_K': specific_heat
            })
        return layers
    
    def get_layer_masses_from_ui(self):
        """Extract layer geometry and compute mass using UI table"""
        volumes_to_mass = {}

        for i in range(self.layer_table.rowCount()):
            w = lambda j: self.layer_table.cellWidget(i, j)
            name = w(0).text().strip()
            mat_name = w(1).currentText().strip()
            ir = float(w(2).text()) * 1e-6      # μm → m
            orad = float(w(3).text()) * 1e-6   # μm → m
            length = float(w(4).text()) * 1e-3  # mm → m

            vol_name_pv = name + "_PV"

            # Try NIST manager first
            nist = G4NistManager.Instance() if hasattr(G4NistManager, 'Instance') else None
            mat = None
            if nist:
                try:
                    mat = nist.FindOrBuildMaterial(mat_name)
                except:
                    pass

            if not mat:
                # Fallback densities (g/cm³ → kg/m³)
                density_map = {
                    "TiO2": 4.23,
                    "Gd2O3": 7.41,
                    "Al2O3": 3.97,
                    "ZrO2": 5.68,
                    "HfO2": 9.68,
                    "SiO2": 2.20,
                    "G4_SILICON_DIOXIDE": 2.20,
                    "G4_AIR": 0.001205
                }
                rho_gcm3 = density_map.get(mat_name, 2.20)  # default SiO₂
                density_kgm3 = rho_gcm3 * 1000  # g/cm³ → kg/m³
            else:
                # ❌ But keep original behavior for consistency
                # Geant4 stores density in mg/cm³ → divide by 1000 to get kg/m³
                density_kgm3 = mat.GetDensity() / 1000.0

            # Volume = π(R² - r²) × L
            volume_m3 = 3.14159 * ((orad**2) - (ir**2)) * length
            mass_kg = volume_m3 * density_kgm3

            volumes_to_mass[vol_name_pv] = max(mass_kg, 1e-20)

        return volumes_to_mass
    
    ############### Load & Plot Results ################
    def load_results(self, filename):
        if not os.path.exists(filename):
            self.log.append("❌ File not found!")
            return

        try:
            # --- Read raw content ---
            with open(filename, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]

            if len(lines) <= 1:
                self.log.append("⚠️ No data in file.")
                return

            # --- Remove comment lines but keep first valid header ---
            header = None
            data_lines = []
            for line in lines:
                if line.startswith("#"):
                    if "Volume" in line and "X" in line and "Edep" in line:
                        # Extract clean header
                        header = re.sub(r'^# *', '', line)
                    continue
                if line:
                    data_lines.append(line)

            if not header:
                self.log.append("❌ No valid header found.")
                return

            # --- Fix merged lines ---
            volume_names = [
                'Core_PV', 'Cladding_PV',
                'TiO2_Coating_PV', 'Gd2O3_Coating_PV',
                'World', 'Spacer_PV', 'Cavity_PV'
            ]
            pattern = r'(' + '|'.join(re.escape(name) for name in volume_names) + r')\t'

            fixed_content = '\n'.join(data_lines)
            fixed_content = re.sub(pattern, r'\n\1\t', fixed_content)
            fixed_content = fixed_content.strip()

            if not fixed_content:
                self.log.append("⚠️ No valid data after fixing.")
                return

            # --- Parse with pandas ---
            df = pd.read_csv(StringIO(header + '\n' + fixed_content), sep='\t')

            # Validate columns
            expected_cols = ['Volume', 'X', 'Y', 'Z', 'Edep_keV', 'StepLength_nm']
            if list(df.columns)[:6] != expected_cols[:len(df.columns)]:
                # Try without assuming names
                df = pd.read_csv(StringIO(fixed_content), sep='\t', header=None)
                df.columns = expected_cols[:df.shape[1]]

            # Add derived column
            if 'Edep_keV' in df.columns:
                df['Edep_J'] = df['Edep_keV'] * 1.602e-16
            else:
                self.log.append("❌ No Edep_keV column!")
                return

            # Store globally
            self.dose_data = df
            self.log.append(f"📊 Loaded {len(df)} energy deposits.")

            # Refresh plot
            self.plot_dose()

        except Exception as e:
            self.log.append(f"💥 Failed to load results: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())

    def save_energy_per_layer(self, filename):
        """
        After loading self.dose_data, compute total energy per volume
        and save to a clean text file for later use.
        """
        if self.dose_data is None:
            return

        try:
            # Group by Volume and sum Edep_J
            grouped = self.dose_data.groupby('Volume')['Edep_J'].sum()

            # Create output directory if needed
            out_dir = os.path.join(os.path.dirname(filename), "layer_energies")
            os.makedirs(out_dir, exist_ok=True)

            # Save each layer's energy
            for vol, total_energy_j in grouped.items():
                layer_name = vol.replace("_PV", "")
                energy_file = os.path.join(out_dir, f"energy_{layer_name}.txt")

                with open(energy_file, 'w') as f:
                    f.write(f"# Energy Summary for {layer_name}\n")
                    f.write(f"Volume: {vol}\n")
                    f.write(f"Total_Energy_J: {total_energy_j:.3e}\n")

                self.log.append(f"📁 Saved energy for {layer_name} → {energy_file}")

        except Exception as e:
            self.log.append(f"💥 Failed to save energy per layer: {str(e)}")

                     
    ############### Plotting & Analysis ################
    def plot_dose(self):
        if self.dose_data is None or self.canvas is None:
            return

        ax = self.canvas.ax
        ax.clear()

        df = self.dose_data.copy()
        r = np.sqrt(df['X']**2 + df['Y']**2)
        z = df['Z']
        E = df['Edep_keV']

        mask = df['Volume'] != 'World'
        sc = ax.scatter(r[mask], z[mask], c=E[mask], cmap='hot_r', s=5, alpha=0.9)

        ax.set_xlabel("Radial Position (μm)")
        ax.set_ylabel("Axial Position (μm)")
        ax.set_title("Energy Deposits in Fiber Sensor")
        ax.set_xlim(0, 80)
        ax.set_ylim(-2600, 2600)

        # ✅ Safely remove old colorbar
        if hasattr(self, 'colorbar') and self.colorbar is not None:
            try:
                # Temporarily disconnect from figure before removing
                cbar = self.colorbar
                self.colorbar = None  # Prevent reuse
                cbar.ax.clear()
                cbar.ax.figure.delaxes(cbar.ax)  # Force delete axes
            except Exception as e:
                print(f"Cleanup warning (safe to ignore): {e}")

        # ✅ Add new colorbar
        try:
            self.colorbar = self.canvas.figure.colorbar(sc, ax=ax, label="Energy (keV)")
        except Exception as e:
            print(f"Failed to create colorbar: {e}")
            self.colorbar = None

        # ✅ Redraw
        self.canvas.draw()
    
    def load_material_density(self):
        """Load material properties from materials.json"""
        materials_file = os.path.join(os.path.dirname(__file__), "materials.json")
        
        try:
            if not os.path.exists(materials_file):
                if hasattr(self, 'log'):
                    self.log.append("⚠️ materials.json not found.")
                return None

            with open(materials_file, 'r') as f:
                data = json.load(f)

            density_map = {}
            specific_heat_map = {}
            dn_dt_map = {}
            for name, props in data.items():
                if not isinstance(props, dict):
                    continue  # Skip strings or other invalid types
                density_map[name] = props.get('density_g_cm3', 2.20)
                specific_heat_map[name] = props.get('specific_heat_J_per_kg_K', 700)
                dn_dt_map[name] = props.get('dn_dT_per_K', 1.2e-5)

            if hasattr(self, 'log'):
                self.log.append(f"✅ Loaded {len(density_map)} material properties from materials.json")

            return {
                'density': density_map,
                'specific_heat': specific_heat_map,
                'dn_dT_per_K': dn_dt_map
            }

        except Exception as e:
            if hasattr(self, 'log'):
                self.log.append(f"💥 Failed to load materials.json: {str(e)}. Using defaults.")
            traceback.print_exc()
            return None
        
    ############### Dose Analysis ################
    def analyze_dose(self):
        if not hasattr(self, 'output_folder'):
            QMessageBox.warning(self, "No Output", "Run simulation first.")
            return
        energy_dir = os.path.join(self.output_folder.text(), "layer_energies")
        if not os.path.exists(energy_dir):
            QMessageBox.warning(self, "No Data", "Run simulation and load results first.")
            return

        try:
            # Load material properties from materials.json
            materials_file = os.path.join(os.path.dirname(__file__), "materials.json")
            with open(materials_file, 'r') as f:
                material_props = json.load(f)
            self.log.append(f"✅ Loaded {len(material_props)} material properties")

            results = []
            # CLADDING_RADIUS_UM = 75.0  # For disk area

            for i in range(self.layer_table.rowCount()):
                w = lambda j: self.layer_table.cellWidget(i, j)
                name = w(0).text().strip()
                mat_name = w(1).currentText().strip()
                ir_um = float(w(3).text())
                orad_um = float(w(4).text())
                length_mm = float(w(5).text())

                # ✅ Define layer_category based on type
                layer_type_str = w(2).currentText() if isinstance(w(2), QComboBox) else "Hollow Cylinder"

                if any(kw in name for kw in ['Coating', 'TI_OXIDE', 'GADOLINIA']):
                    layer_category = "End-Face Disk"
                elif abs(ir_um - 0.0) < 1e-6:
                    layer_category = "Solid Cylinder"
                else:
                    layer_category = "Hollow Cylinder"

                vol_name_pv = name + "_PV"

                # Get material properties
                props = material_props.get(mat_name, {})
                rho_gcm3 = props.get('density_g_cm3', 2.20)
                specific_heat = props.get('specific_heat_J_per_kg_K', 700)
                dn_dT = props.get('dn_dT_per_K', 1.2e-5)

                rho_kgm3 = rho_gcm3 * 1000
                thickness_nm = round((orad_um - ir_um) * 1000, 1)

                # === Compute Volume & Mass Based on Type ===
                R_m = orad_um * 1e-6  # outer radius in meters
                L_m = length_mm * 1e-3

                volume_m3 = 0.0

                if layer_category == "End-Face Disk":
                    # Annular shell volume
                    R_m = orad_um * 1e-6
                    r_m = ir_um * 1e-6
                    L_m = length_mm * 1e-3
                    volume_m3 = 3.14159 * ((R_m**2) - (r_m**2)) * L_m
                elif layer_category == "Solid Cylinder":
                    R_m = orad_um * 1e-6
                    L_m = length_mm * 1e-3
                    volume_m3 = 3.14159 * (R_m**2) * L_m
                else:
                    # Hollow cylinder
                    R_m = orad_um * 1e-6
                    r_m = ir_um * 1e-6
                    L_m = length_mm * 1e-3
                    volume_m3 = 3.14159 * ((R_m**2) - (r_m**2)) * L_m

                # Read saved energy
                energy_file = os.path.join(energy_dir, f"energy_{name}.txt")
                if os.path.exists(energy_file):
                    try:
                        with open(energy_file, 'r') as f:
                            for line in f:
                                if line.startswith("Total_Energy_J:"):
                                    total_energy_j = float(line.split(":")[1].strip())
                                    break
                    except Exception as e:
                        self.log.append(f"⚠️ Failed to read {energy_file}: {str(e)}")
                else:
                    self.log.append(f"⚠️ No energy file for {name}")

                mass_kg = volume_m3 * rho_kgm3
                dose_gy = total_energy_j / max(mass_kg, 1e-20)
                delta_T_K = dose_gy / specific_heat
                delta_n = dn_dT * delta_T_K

                results.append({
                    'Layer': name,
                    'Material': mat_name,
                    'Type': layer_category,
                    'Inner_Radius_um': ir_um,
                    'Outer_Radius_um': orad_um,
                    'Thickness_nm': thickness_nm,
                    'Length_mm': length_mm,
                    'Mass_kg': mass_kg,
                    'Energy_J': total_energy_j,
                    'Dose_Gy': dose_gy,
                    'Delta_T_K': delta_T_K,
                    'Delta_n': delta_n,
                    'Specific_Heat_J_kgK': specific_heat,
                    'dn_dT_per_K': dn_dT,
                    'Step_Count': 0
                })

            # Store and display
            self.dose_summary_df = pd.DataFrame(results)
            self.display_analysis_results()

            try:
                S_exp_nm_per_RIU = float(self.sensitivity_input.text())
            except ValueError:
                self.log.append("⚠️ Invalid sensitivity value. Using -78.8 nm/RIU.")
                S_exp_nm_per_RIU = -78.8

            # Compute effective parameters
            total_energy_j = self.dose_summary_df['Energy_J'].sum()
            total_mass_kg = self.dose_summary_df['Mass_kg'].sum()

            if total_mass_kg > 0:
                D_eff_Gy = total_energy_j / total_mass_kg
            else:
                D_eff_Gy = 0.0

            # Weighted average Δn by energy deposition
            weighted_delta_n = (
                (self.dose_summary_df['Delta_n'] * self.dose_summary_df['Energy_J']).sum() /
                max(total_energy_j, 1e-30)
            )

            # Predicted wavelength shift
            delta_lambda_nm = S_exp_nm_per_RIU * weighted_delta_n
            delta_lambda_pm = delta_lambda_nm * 1000  # Convert to pm

            # Radiation-Induced Spectral Responsivity
            if D_eff_Gy > 0:
                responsivity_pm_per_Gy = delta_lambda_pm / D_eff_Gy
            else:
                responsivity_pm_per_Gy = 0.0

            # Display in log
            self.log.append("\n🧩 System-Level Sensor Response:")
            self.log.append(f"  Effective Dose: {D_eff_Gy:.3e} Gy")
            self.log.append(f"  Effective Δn: {weighted_delta_n:.3e}")
            self.log.append(f"  → Predicted Δλ: {delta_lambda_nm:.3e} nm ({delta_lambda_pm:.3f} pm)")
            self.log.append(f"  📊 Radiation-Induced Spectral Responsivity: {responsivity_pm_per_Gy:.3f} pm/Gy")

            # Store for export
            self.sensor_responsivity = responsivity_pm_per_Gy
            self.predicted_wavelength_shift_nm = delta_lambda_nm

        except Exception as e:
            self.log.append(f"💥 Dose analysis failed: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())

    def display_analysis_results(self):
        """Display results in log"""
        self.log.append("\n🎯 Absorbed Dose & Temperature Rise Summary:")
        for _, row in self.dose_summary_df.iterrows():
            prefix = "🔷" if row['Type'] == 'End-Face Disk' else "🔶"
            self.log.append(
                f"{prefix} {row['Layer']} ({row['Material']}): "
                f"Dose={row['Dose_Gy']:.6f} Gy → ΔT={row['Delta_T_K']:.6f} K → Δn={row['Delta_n']:.3e}"
            )
                        
    ############### Exporting Results ################
    def export_results(self):
        if self.dose_data is None:
            QMessageBox.warning(self, "No Data", "Run simulation first.")
            return

        # Define core columns (exclude Edep_J for clean export)
        core_columns = ['Volume', 'X', 'Y', 'Z', 'Edep_keV', 'StepLength_nm']
        export_df = self.dose_data[core_columns].copy()

        # Add derived summary data (optional)
        summary_data = []
        for vol in export_df['Volume'].unique():
            subset = export_df[export_df['Volume'] == vol]
            total_edep = subset['Edep_keV'].sum() * 1.602e-16  # J
            count = len(subset)
            summary_data.append({'Volume': vol, 'Step Count': count, 'Total Energy (J)': total_edep})

        summary_df = pd.DataFrame(summary_data)

        # Open file dialog for .xlsx
        excel_file, _ = QFileDialog.getSaveFileName(self, "Save Results", "", "Excel Files (*.xlsx)")
        if not excel_file:
            return

        # Ensure file ends with .xlsx
        if not excel_file.lower().endswith('.xlsx'):
            excel_file += '.xlsx'

        try:
            # Write to Excel with multiple sheets
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                export_df.to_excel(writer, sheet_name='Energy_Deposits', index=False)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                # Optionally save geometry
                if hasattr(self, 'layer_table'):
                    geom_data = []
                    for i in range(self.layer_table.rowCount()):
                        w = lambda j: self.layer_table.cellWidget(i, j)
                        geom_data.append({
                            'Layer': w(0).text(),
                            'Material': w(1).currentText(),
                            'Layer type': w(2).currentText() if isinstance(w(2), QComboBox) else "Cylindrical",
                            'Inner Radius (μm)': w(3).text(),
                            'Outer Radius (μm)': w(4).text(),
                            'Length (mm)': w(5).text()
                        })
                    pd.DataFrame(geom_data).to_excel(writer, sheet_name='Geometry', index=False)

            self.log.append(f"📊 Saved results to {excel_file}")
            
            # Optional: Open folder
            # os.startfile(os.path.dirname(excel_file))

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not save file:\n{str(e)}")
def main():
    app = QApplication(sys.argv)
    window = FiberSimulationUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()