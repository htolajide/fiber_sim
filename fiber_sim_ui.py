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
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavToolbar
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QFileDialog, QTextEdit,
    QSplitter, QFormLayout, QMessageBox, QTableWidget, QTabWidget, 
    QHeaderView, QGroupBox, QCheckBox, QColorDialog, QDoubleSpinBox, QSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from tmm_engine import compute_optical_spectrum
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
            # === Start Timer ===
            start_time = time.time()
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
                # Use absolute path to project root (where CMakeLists.txt lives)
                work_dir = os.getcwd()  # Project root containing CMakeLists.txt, src/, build/
                
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
                run_cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{work_dir}:/home/geant4/work",           # ✅ Mount full project
                    "-e", "LD_LIBRARY_PATH=/home/geant4/geant4-install/lib",
                    "my-geant4",
                    "/home/geant4/work/build/fiber_sim",             # Executable
                    "/home/geant4/work/input.mac"                    # Macro file
                ]

                run_result = subprocess.run(
                    run_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=3600,  # 60-minute timeout
                    check=False
                )

                # Decode with error tolerance
                try:
                    stdout_text = run_result.stdout.decode('utf-8', errors='replace')
                except Exception:
                    stdout_text = run_result.stdout.decode('cp1252', errors='replace')

                try:
                    stderr_text = run_result.stderr.decode('utf-8', errors='replace')
                except Exception:
                    stderr_text = run_result.stderr.decode('cp1252', errors='replace')

                # === End Timer ===
                end_time = time.time()
                elapsed_seconds = end_time - start_time
                elapsed_minutes = elapsed_seconds / 60.0
                if run_result.returncode == 0:
                    time.sleep(0.5)
                    # Now dose_per_step.txt should be generated in out_dir
                    dose_temp = os.path.join(out_dir, "dose_per_step.txt")
                    if os.path.exists(dose_temp):
                        os.rename(dose_temp, dose_path)
                        self.log_message.emit(f"📁 Dose data saved as: {dose_filename}")
                        self.log_message.emit(f"⏱️ Simulation finished in {elapsed_minutes:.1f} minutes")
                        self.simulation_finished.emit(dose_path)
                    else:
                        self.error.emit("No output file generated by Geant4.")
                else:
                    self.error.emit("Simulation runtime error")
                    self.log_message.emit(f"⏱️ Failed after {elapsed_minutes:.1f} minutes")
                    self.log_message.emit(run_result.stderr[:2000])

            except subprocess.TimeoutExpired:
                end_time = time.time()
                elapsed_minutes = (end_time - start_time) / 60.0
                self.error.emit(f"❌ Simulation timed out after {elapsed_minutes:.1f} minutes.")
                return
            except Exception as e:
                self.error.emit(f"❌ Failed to run simulation: {str(e)}")
                return
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

    def add_material(self, symbol, name, density, formula=None, color=None):
        """
        Add or update a material in the database with optional color
        Example: add_material("Y2O3", "Yttrium Oxide", 5.01, "Y2O3", "#ff6b6b")
        """
        if not formula:
            formula = symbol  # fallback

        # Default color palette for auto-assignment
        default_colors = ['#e63946', '#c11a2b', '#457b9d', '#2a9d8f', 
                        '#8338ec', '#ffd60a', '#06d6a0', '#8d99ae']

        # Auto-assign color if not provided
        if color is None:
            used_colors = [mat.get('color') for mat in self.materials.values() if 'color' in mat]
            available = [c for c in default_colors if c not in used_colors]
            color = available[0] if available else default_colors[len(self.materials) % len(default_colors)]

        self.materials[symbol] = {
            "name": name,
            "density_g_cm3": float(density),
            "formula": formula,
            "color": color
        }

        # Save immediately
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.materials, f, indent=2)
            return True
        except Exception as e:
            print(f"Failed to save material: {e}")
            return False
        
    def update_material(self, old_symbol, new_symbol=None, name=None, density=None, formula=None, color=None):
        """Update material, optionally renaming its symbol"""
        if old_symbol not in self.materials:
            return False

        mat_data = self.materials.pop(old_symbol)  # Remove old entry

        # Apply updates
        if new_symbol:
            old_symbol = new_symbol  # Use new symbol as key
        if name:
            mat_data["name"] = name
        if density is not None:
            mat_data["density_g_cm3"] = float(density)
        if formula:
            mat_data["formula"] = formula
        if color:
            mat_data["color"] = color

        # Reinsert with (possibly new) symbol
        self.materials[new_symbol or old_symbol] = mat_data

        # Save to file
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.materials, f, indent=2)
            return True
        except Exception as e:
            print(f"Failed to save updated material: {e}")
            return False
        
    def list_materials(self):
        """
        Return only valid material symbols (exclude 'SOURCE', 'REFERENCES', etc.)
        """
        reserved_keys = {'SOURCE', 'REFERENCES', 'comments', 'version'}  # Add any meta keys used
        return sorted([
            key for key in self.materials.keys()
            if isinstance(self.materials[key], dict) and key not in reserved_keys
        ])

    def get(self, name):
        return self.materials.get(name)

def tmm_reflectance(lambda_nm, n_list, d_list):
        """
        Compute normal-incidence reflectance using Transfer Matrix Method (TMM).
        
        Parameters:
            lambda_nm: Wavelength in nanometers
            n_list: List of refractive indices [n0, n1, ..., nN]
            d_list: List of layer thicknesses in micrometers (inf = semi-infinite)
        
        Returns:
            Reflectance R = |r_total|^2
        """
        try:
            k0 = 2 * np.pi / lambda_nm  # Wave number in vacuum (nm⁻¹)

            # Start with identity matrix
            M_total = np.eye(2, dtype=complex)

            # Propagate through each layer
            for i in range(len(n_list)):
                n_i = n_list[i]
                d_i = d_list[i]

                if d_i == np.inf:
                    # Semi-infinite medium → no phase accumulation
                    continue

                # Phase accumulation in layer
                phi = k0 * n_i * (d_i * 1000)  # Convert μm → nm

                # Layer transfer matrix
                cos_phi = np.cos(phi)
                sin_phi = np.sin(phi)

                # Avoid division by zero in case of small n_i
                if abs(n_i) < 1e-6:
                    return 0.0

                m11 = cos_phi
                m12 = 1j * sin_phi / n_i
                m21 = 1j * n_i * sin_phi
                m22 = cos_phi

                M_i = np.array([[m11, m12], [m21, m22]], dtype=complex)

                # Multiply from left: M_total = M_i @ M_total
                M_total = np.dot(M_i, M_total)

            # Reflection coefficient
            if abs(M_total[0,0]) > 1e-15:
                r_total = M_total[1,0] / M_total[0,0]
            else:
                r_total = 0.0 + 0j

            # Return power reflectance
            return float(np.abs(r_total)**2)

        except Exception as e:
            print(f"❌ TMM error at λ={lambda_nm}: {str(e)}")
            return 0.0
        
class FiberSimulationUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setGeometry(700, 150, 1000, 1200)
        self.dose_data = None
        self.selected_color = "#8d99ae"  # Default gray
        self.material_db = MaterialDB()
        self.colorbar = None
        # ✅ Initialize cavity group as None
        self.cav_group = None

        # ✅ Initialize log early
        self.output_folder = None # Set default path will be set in create_source_tab
        self.source_type = None
        self.num_particles = None
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.material_props = self.load_material_properties()
        self.log.append("✅ Ready to simulate! Configure geometry and source.")
        self.init_ui()
        self.connect_symbol_selection()
        self._reference_setup = False
        

    def browse_folder(self):
        """Open a dialog to select output folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)

    def get_output_dir(self):
        """Safely get output directory"""
        if hasattr(self, 'output_folder') and self.output_folder is not None:
            path = self.output_folder.text().strip()
            if path and os.path.exists(path):
                return path
        return os.getcwd()  # fallback     
    
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
        self.default_layers()  # Now safe to call

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
        self.material_props = self.load_material_properties()
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

        # =======================
        # 5. Radiation Source Settings
        # =======================
        layout.addWidget(QLabel("<b>Settings:</b>"))

       # --- Radiation Source Group ---
        source_group = QGroupBox("Radiation Source")
        source_layout = QFormLayout()

        # === Option 1: Predefined Source ===
        self.source_type_combo = QComboBox()
        self.source_type_combo.addItems([
            "Custom",
            "Cs-137 (662 keV)",
            "Co-60 (1.17 & 1.33 MeV)",
            "Am-241 (59.5 keV)",
            "Na-22 (511 keV + 1.27 MeV)",
            "Thermal Neutron"
        ])
        self.source_type_combo.currentTextChanged.connect(self.on_source_type_changed)
        source_layout.addRow("Source:", self.source_type_combo)

        # === Option 2: Custom Particle & Energy (Hidden if using preset) ===
        self.custom_particle_label = QLabel("Particle:")
        self.particle_combo = QComboBox()
        self.particle_combo.addItems(["gamma", "e-", "e+", "proton", "neutron"])
        self.particle_combo.setCurrentText("gamma")
        source_layout.addRow(self.custom_particle_label, self.particle_combo)

        self.energy_input = QLineEdit("0.662")
        self.energy_unit = QLabel("MeV")
        energy_hbox = QHBoxLayout()
        energy_hbox.addWidget(self.energy_input)
        energy_hbox.addWidget(self.energy_unit)
        # Add label and layout manually
        self.energy_label = QLabel("Energy (MeV):")
        source_layout.addRow(self.energy_label, energy_hbox)

        # Optional: Second line for Co-60 / Na-22
        self.second_line_layout = QHBoxLayout()
        self.second_line_check = QCheckBox("Add Second Line")
        self.second_line_check.stateChanged.connect(self.toggle_second_line)
        self.second_line_val = QLineEdit("1.332")
        self.second_line_val.setEnabled(False)
        self.second_line_layout.addWidget(self.second_line_check)
        self.second_line_layout.addWidget(self.second_line_val)
        self.second_line_layout.addWidget(QLabel("MeV"))
        source_layout.addRow("", self.second_line_layout)

        # === Number of Particles ===
        self.num_particles = QLineEdit("50000")
        source_layout.addRow("Number of Particles:", self.num_particles)

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

       # - Add/Edit Custom Material Section -
        mat_group = QGroupBox("Add or Update Custom Material")
        mat_layout = QFormLayout()

        # Symbol Combo Box (Editable) — Now both selectable AND editable
        self.new_mat_symbol_combo = QComboBox()
        self.new_mat_symbol_combo.setEditable(True)
        self.new_mat_symbol_combo.setPlaceholderText("e.g., Y2O3")

        # Populate with current materials
        self.refresh_symbol_combobox()  # Defined below
        mat_layout.addRow("Chemical Symbol:", self.new_mat_symbol_combo)

        self.new_mat_name = QLineEdit()
        self.new_mat_name.setPlaceholderText("e.g., Yttrium Oxide")
        mat_layout.addRow("Material Name:", self.new_mat_name)

        self.new_mat_density = QLineEdit()
        self.new_mat_density.setPlaceholderText("Density (g/cm³)")
        mat_layout.addRow("Density:", self.new_mat_density)

        # Color Picker Row
        color_row = QHBoxLayout()
        self.new_mat_color_label = QLabel("🎨")
        self.new_mat_color_label.setFixedWidth(20)
        btn_pick_color = QPushButton("Choose Color")
        btn_pick_color.clicked.connect(self.pick_material_color)
        color_row.addWidget(self.new_mat_color_label)
        color_row.addWidget(btn_pick_color)
        mat_layout.addRow("Color:", color_row)

        # Buttons: Add & Update
        button_row = QHBoxLayout()
        btn_add_mat = QPushButton("➕ Add Material")
        btn_add_mat.clicked.connect(self.add_custom_material)
        btn_update_mat = QPushButton("🔄 Update Material")
        btn_update_mat.clicked.connect(self.update_custom_material)
        button_row.addWidget(btn_add_mat)
        button_row.addWidget(btn_update_mat)
        mat_layout.addRow(button_row)

        mat_group.setLayout(mat_layout)
        layout.addWidget(mat_group)
        # --- Optical Simulation Parameters ---
        optical_box = QGroupBox("Optical Wavelength Range")
        self.lambda_start = QDoubleSpinBox()
        self.lambda_start.setRange(1000, 2000)
        self.lambda_start.setValue(1500)
        self.lambda_start.setSuffix(" nm")

        self.lambda_end = QDoubleSpinBox()
        self.lambda_end.setRange(1000, 2000)
        self.lambda_end.setValue(1521)
        self.lambda_end.setSuffix(" nm")

        self.num_points = QSpinBox()
        self.num_points.setRange(100, 2000)
        self.num_points.setValue(800)

        optical_layout = QFormLayout()
        optical_layout.addRow("Sweep Start (nm):", self.lambda_start)
        optical_layout.addRow("Sweep End (nm):", self.lambda_end)
        optical_layout.addRow("Number of Points:", self.num_points)
        optical_box.setLayout(optical_layout)
        layout.addWidget(optical_box)

        # === Photoliquid Scintillator Option ===
        liquid_layout = QFormLayout()
        self.use_photoliquid = QCheckBox("🧪 Use Photoliquid Scintillator in Cavity")
        self.use_photoliquid.setChecked(False)  # Default: enabled
        self.use_photoliquid.stateChanged.connect(self.on_photoliquid_toggled)
        liquid_layout.addRow(self.use_photoliquid)

        # Tip
        tip = QLabel("💡 When checked, cavity medium becomes scintillator (e.g., Altima Gold LLT). Coatings act as mirrors.")
        tip.setStyleSheet("QLabel { font-size: 10px; color: gray; }")
        liquid_layout.addRow(tip)
        layout.addLayout(liquid_layout)

        # 🚀 Run Simulation Button (Big and visible!)
        btn_run = QPushButton("🚀 Run Simulation")
        btn_run.setStyleSheet("font-size: 14px; font-weight: bold; padding: 12px;")
        btn_run.clicked.connect(self.run_simulation)  # ← Connects to your method
        layout.addWidget(btn_run)

        # --- Stop Button ---
        self.btn_stop = QPushButton("⏹️ Stop Simulation")
        self.btn_stop.setStyleSheet("font-size: 14px; font-weight: bold; padding: 12px;")
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
        return widget
    
    ################ Output Tab Creation ################
    def create_output_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # === Top Section: Preview and Chart (Split 1:3) ===
        splitter = QSplitter(Qt.Vertical)

        # --- Structure Preview (Top 1/4) ---
        preview_group = QGroupBox("Sensor Structure Preview")
        if not hasattr(self, 'preview_layout'):
            preview_layout = QVBoxLayout()
            self.preview_canvas = MplCanvas(self, width=8, height=2.0, dpi=100)  # Smaller height
            preview_layout.addWidget(self.preview_canvas)
            preview_group.setLayout(preview_layout)

            # Wrap in widget for splitter
            preview_widget = QWidget()
            preview_widget.setLayout(QVBoxLayout())
            preview_widget.layout().addWidget(preview_group)
        else:
            # If already exists, don't re-add
            pass
        # --- Results Chart (Bottom 3/4) ---
        self.canvas = MplCanvas(self, width=8, height=6, dpi=100)
        chart_group = QGroupBox("Dose Distribution")
        self.chart_layout = QVBoxLayout()
        self.chart_layout.addWidget(self.canvas)
        chart_group.setLayout(self.chart_layout)

        self.chart_widget = QWidget()
        self.chart_widget.setLayout(QVBoxLayout())
        self.chart_widget.layout().addWidget(chart_group)

        # Create tab widget
        self.tabs = QTabWidget()
        self.energy_tab = QWidget()
        self.optics_tab = QWidget()

        # === Energy Tab ===
        self.energy_fig = Figure()
        self.energy_canvas = FigureCanvas(self.energy_fig)
        self.energy_ax = self.energy_fig.add_subplot(111)
        energy_layout = QVBoxLayout()
        energy_layout.addWidget(self.energy_canvas)
        self.energy_toolbar = NavToolbar(self.energy_canvas, self)
        energy_layout.addWidget(self.energy_toolbar)
        self.energy_tab.setLayout(energy_layout)

        # === Optics Tab ===
        self.optics_fig = Figure()
        self.optics_canvas = FigureCanvas(self.optics_fig)
        self.optics_ax = self.optics_fig.add_subplot(111)
        optics_layout = QVBoxLayout()
        optics_layout.addWidget(self.optics_canvas)
        self.optics_toolbar = NavToolbar(self.optics_canvas, self)
        optics_layout.addWidget(self.optics_toolbar)
        self.optics_tab.setLayout(optics_layout)

        # Add tabs
        self.tabs.addTab(self.energy_tab, "Energy Deposits")
        self.tabs.addTab(self.optics_tab, "Optical Spectrum")

        # Add to splitter
        splitter.addWidget(preview_widget)
        splitter.addWidget(self.tabs)
        splitter.setSizes([int(self.height() * 0.25), int(self.height() * 0.75)])  # 1:3 ratio

        layout.addWidget(splitter)

        # === Button Row (Single Line) ===
        btn_layout = QHBoxLayout()
        
        btn_export = QPushButton("💾 Export Results")
        btn_export.clicked.connect(self.export_results)

        btn_analyze = QPushButton("🔬 Analyze Dose")
        btn_analyze.clicked.connect(self.analyze_dose)

        # In create_analysis_tab() or similar
        self.analyze_optics_btn = QPushButton("🔍 Analyze Optical Response")
        self.analyze_optics_btn.clicked.connect(self.analyze_optical_response)
       
        btn_export_summary = QPushButton("📄 Export Dose Summary")
        btn_export_summary.clicked.connect(self.export_dose_summary)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_analyze)
        btn_layout.addWidget(self.analyze_optics_btn)
        btn_layout.addWidget(btn_export)
        btn_layout.addWidget(btn_export_summary)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)
        widget.setLayout(layout)
        return widget
    
    def pick_material_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()  # e.g., "#e63946"
            self.new_mat_color_label.setStyleSheet(f"background-color: {hex_color}; border: 1px solid black; border-radius: 10px;")
            self.new_mat_color_label.setToolTip(f"Selected color: {hex_color}")
            # Store in object
            self.selected_color = hex_color
        else:
            self.selected_color = None

    def on_source_type_changed(self, text):
        """Update visibility based on selected source"""
        if text == "Custom":
            # Show custom fields
            self.custom_particle_label.show()
            self.particle_combo.show()
            self.energy_label.show()
            self.energy_input.show()
            self.energy_unit.show()
            self.second_line_check.show()
        else:
            # Hide all custom fields
            self.custom_particle_label.hide()
            self.particle_combo.hide()
            self.energy_label.hide()
            self.energy_input.hide()
            self.energy_unit.hide()
            self.second_line_check.hide()
            self.second_line_val.hide() if hasattr(self, 'second_line_val') else None

    def toggle_second_line(self):
        state = self.second_line_check.isChecked()
        self.second_line_val.setEnabled(state)

    def refresh_symbol_combobox(self):
        """Reload symbol combo box with all current material symbols"""
        self.new_mat_symbol_combo.clear()
        symbols = sorted(self.material_db.list_materials())
        self.new_mat_symbol_combo.addItems(symbols)

    def clear_plot(self):
        """
        Completely clears both energy and optical plot areas,
        removes old canvases and colorbars, and creates fresh MplCanvases
        to prevent shrinking or overlapping on subsequent runs.
        """
        def safe_remove_colorbar(canvas, attr_name="colorbar"):
            """Safely remove colorbar associated with canvas"""
            if hasattr(canvas, attr_name) and getattr(canvas, attr_name) is not None:
                try:
                    cbar = getattr(canvas, attr_name)
                    setattr(canvas, attr_name, None)  # Prevent reuse
                    cbar.ax.clear()
                    cbar.ax.figure.delaxes(cbar.ax)
                except Exception as e:
                    print(f"Colorbar cleanup warning: {e}")

        try:
            # --- Clear Energy Canvas ---
            if hasattr(self, 'energy_canvas') and self.energy_canvas is not None:
                # Remove colorbar
                safe_remove_colorbar(self.energy_canvas, 'colorbar')

                # Clear axes
                if hasattr(self, 'energy_ax') and self.energy_ax is not None:
                    self.energy_ax.clear()

                # Remove from layout
                if self.energy_canvas in self.tabs.widget(0).layout().children():
                    self.tabs.widget(0).layout().removeWidget(self.energy_canvas)
                self.energy_canvas.deleteLater()
                self.energy_canvas = None
                self.energy_ax = None

            # --- Clear Optical Canvas ---
            if hasattr(self, 'optics_canvas') and self.optics_canvas is not None:
                # Remove colorbar
                safe_remove_colorbar(self.optics_canvas, 'colorbar')

                # Clear axes
                if hasattr(self, 'optics_ax') and self.optics_ax is not None:
                    self.optics_ax.clear()

                # Remove from layout
                if self.optics_canvas in self.tabs.widget(1).layout().children():
                    self.tabs.widget(1).layout().removeWidget(self.optics_canvas)
                self.optics_canvas.deleteLater()
                self.optics_canvas = None
                self.optics_ax = None

            # --- Recreate Canvases ---
            self.energy_fig = Figure()
            self.energy_canvas = FigureCanvas(self.energy_fig)
            self.energy_ax = self.energy_fig.add_subplot(111)

            self.optics_fig = Figure()
            self.optics_canvas = FigureCanvas(self.optics_fig)
            self.optics_ax = self.optics_fig.add_subplot(111)

            # Add to tabs
            self.tabs.widget(0).layout().addWidget(self.energy_canvas)
            self.tabs.widget(1).layout().addWidget(self.optics_canvas)

            # Reset data
            self.dose_data = None
            self.dose_summary_df = None

            self.log.append("✅ Plot area reset: energy and optical canvases cleared.")

        except Exception as e:
            self.log.append(f"⚠️ Failed to clear plot: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())

    ############### Layer Table Management ################
    def on_sensor_type_changed(self):
        self.clear_layers()
        sensor = self.sensor_type.currentText()
        if sensor == "In-Fiber Microcavity":
            self.load_microcavity_layers()
        else:
            self.load_end_face_layers()
        self.update_preview()

    def connect_symbol_selection(self):
        """Call this after creating new_mat_symbol_combo"""
        self.new_mat_symbol_combo.currentTextChanged.connect(self.load_material_for_editing)

    def load_material_for_editing(self, symbol):
        """Auto-fill fields when a symbol is selected"""
        if not symbol or symbol not in self.material_props:
            return

        mat = self.material_props[symbol]
        self.new_mat_name.setText(mat.get("name", ""))
        self.new_mat_density.setText(str(mat.get("density_g_cm3", "")))

        # Set color preview
        color_hex = mat.get("color", "#8d99ae")
        self.selected_color = color_hex
        self.new_mat_color_label.setStyleSheet(f"background-color: {color_hex}; border: 1px solid black; border-radius: 10px;")
        self.new_mat_color_label.setToolTip(f"Current color: {color_hex}")
        
    def add_layer_row(self, name="", mat="", layer_type="Cylindrical", ir="", orad="", length="5.0"):
        try:
            row = self.layer_table.rowCount()
            self.layer_table.insertRow(row)

            # === Column 0: Name (QLineEdit) ===
            name_str = str(name) if name is not None and str(name).strip() != "None" else ""
            name_widget = QLineEdit(name_str)
            name_widget.editingFinished.connect(self.update_preview)
            self.layer_table.setCellWidget(row, 0, name_widget)

            # === Column 1: Material (QComboBox) ===
            if not hasattr(self, 'material_db'):
                raise AttributeError("material_db not initialized")

            mat_combo = QComboBox()
            mat_combo.addItems(self.material_db.list_materials())
            
            idx = mat_combo.findText(str(mat))
            if idx >= 0:
                mat_combo.setCurrentIndex(idx)
            else:
                mat_combo.setCurrentIndex(0)  # Fallback to first material

            # ✅ Dynamic name sync: TiO2 → TiO2_Coating when coating
            def sync_name():
                current_name = name_widget.text().strip()
                selected_mat = mat_combo.currentText().strip()
                # Only auto-rename if it's a coating-type layer
                if "Coating" in current_name or any(kw in current_name.upper() for kw in ["TI_OXIDE", "GADOLINIA"]):
                    base = selected_mat.split("_")[0]  # e.g., "TiO2"
                    new_name = f"{base}_Coating"
                    name_widget.setText(new_name)
                self.update_preview()

            mat_combo.currentTextChanged.connect(sync_name)
            mat_combo.currentTextChanged.connect(lambda: self.on_type_change(row))
            self.layer_table.setCellWidget(row, 1, mat_combo)

            # === Column 2: Type (QComboBox) ===
            type_combo = QComboBox()
            type_combo.addItems([
                "Solid Cylinder", 
                "Hollow Cylinder", 
                "End-Face Disk", 
                "Microcavity Spacer", 
                "Tapered Section"
            ])
            t_idx = type_combo.findText(str(layer_type))
            if t_idx >= 0:
                type_combo.setCurrentIndex(t_idx)
            else:
                type_combo.setCurrentText("Hollow Cylinder")
            type_combo.currentTextChanged.connect(lambda: self.on_type_change(row))
            type_combo.currentTextChanged.connect(self.update_preview)
            self.layer_table.setCellWidget(row, 2, type_combo)

            # === Column 3: Inner Radius ===
            ir_str = str(ir) if ir not in [None, "None"] else "0.0"
            ir_widget = QLineEdit(ir_str)
            ir_widget.editingFinished.connect(self.update_preview)
            self.layer_table.setCellWidget(row, 3, ir_widget)

            # === Column 4: Outer Radius ===
            orad_str = str(orad) if orad not in [None, "None"] else "75.0"
            orad_widget = QLineEdit(orad_str)
            orad_widget.editingFinished.connect(self.update_preview)
            self.layer_table.setCellWidget(row, 4, orad_widget)

            # === Column 5: Length / Thickness ===
            len_str = str(length) if length not in [None, "None"] else "5.0"
            len_widget = QLineEdit(len_str)
            len_widget.editingFinished.connect(self.update_preview)
            self.layer_table.setCellWidget(row, 5, len_widget)

            # ✅ Force preview update after adding
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
            "For Hollow Cylinder / End-Face Disk: inner boundary radius (μm)")
        self.update_preview()

    def load_end_face_layers(self):
        """Load standard end-face coated FPI stack"""
        self.default_layers()
           
        # Refresh preview
        self.update_preview()

    def load_microcavity_layers(self):
        """Load base layers for in-fiber microcavity"""
        self.clear_layers()

        # Base fiber — full length (5 mm)
        self.add_layer_row("Core", "G4_SILICON_DIOXIDE", "Solid Cylinder", "0.0", "4.1", "5.0")
        self.add_layer_row("Cladding", "G4_SILICON_DIOXIDE", "Hollow Cylinder", "4.1", "75.0", "5.0")

        # Spacer layer (optional, can be used to separate cladding from cavity region)
        self.add_layer_row("Spacer", "G4_SILICON_DIOXIDE", "Hollow Cylinder", "75.0", "80.0", "5.0")  # Full length

        # Cavity: air-filled hollow cylinder placed at mid-length
        # This represents the void created by micromachining
        self.add_layer_row("Cavity", "G4_AIR", "HOLLOW_CYLINDER", "75.0", "85.0", "0.150")  # 150 μm long

        # Add user controls for cavity position/orientation
        self.add_microcavity_parameters()

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
    
    def refresh_symbol_combobox(self):
        """Reload symbol combo box with all current material symbols"""
        self.new_mat_symbol_combo.clear()
        symbols = sorted(self.material_db.list_materials())
        self.new_mat_symbol_combo.addItems(symbols)

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
                w = lambda j: self.layer_table.cellWidget(i, j)
                
                # Safely get text from QLineEdit or QComboBox
                name_widget = w(0)
                name = str(name_widget.text()).strip() if name_widget else ""

                mat_combo = w(1)
                mat_name = str(mat_combo.currentText()).strip() if mat_combo else "Unknown"

                type_combo = w(2)
                layer_type = str(type_combo.currentText()).strip() if type_combo else "Hollow Cylinder"

                ir_widget = w(3)
                ir = float(ir_widget.text()) if ir_widget and ir_widget.text().strip() else 0.0

                orad_widget = w(4)
                orad = float(orad_widget.text()) if orad_widget and orad_widget.text().strip() else 75.0

                len_widget = w(5)
                L = float(len_widget.text()) if len_widget and len_widget.text().strip() else 5.0

                layers.append((name, mat_name, layer_type, ir, orad, L))
            except Exception as e:
                continue  # Skip malformed rows

        if not layers:
            ax.text(0.5, 0.5, "No layers defined", ha='center', va='center', transform=ax.transAxes, fontsize=10, color='gray')
            ax.axis('off')
        else:
            sensor_type = self.sensor_type.currentText() if hasattr(self, 'sensor_type') else "End-Face Coated FPI"
            max_radius = max(layer[4] for layer in layers) * 1.2
            total_length = max(layer[5] for layer in layers)

            z_start = 0.0
            current_z = z_start

            # === Step 1: Draw Core & Cladding (Coaxial, Full Length) ===
            core_cladding_layers = [l for l in layers if "Coating" not in l[0] and "Cavity" not in l[0]]
            cavity_layer = next((l for l in layers if "Cavity" in l[0] or l[1] == "G4_AIR"), None)

            for name, mat_name, layer_type, ir, orad, L in core_cladding_layers:
                # Get color from material database
                mat_data = self.material_props.get(mat_name, {})
                color = mat_data.get('color', '#8d99ae')  # Default gray if missing

                rect = plt.Rectangle((current_z, -orad), total_length, 2*orad,
                                    facecolor=color, edgecolor='black', linewidth=0.8, alpha=0.8)
                ax.add_patch(rect)

                if layer_type == "Hollow Cylinder" and ir > 0:
                    hole = plt.Rectangle((current_z, -ir), total_length, 2*ir,
                                        facecolor='white', edgecolor='none')
                    ax.add_patch(hole)
                    label_y = (ir + orad) / 2
                    text_color = 'white'
                else:
                    label_y = orad + 2
                    text_color = 'black'

                ax.text(current_z + total_length/2, label_y, name,
                        fontsize=7, ha='center', va='bottom', color=text_color, weight='bold')

            # === Step 2: Draw Microcavity (Transverse Cut) ===
            cavity_end = total_length
            if sensor_type == "In-Fiber Microcavity" and cavity_layer is not None:
                name, mat_name, layer_type, cav_ir, cav_or, cav_len = cavity_layer
                try:
                    cav_zpos_mm = float(self.cav_zpos.text()) / 1000.0
                except:
                    cav_zpos_mm = -2.0  # Default

                mid_z = total_length / 2.0
                cavity_center_z = mid_z + cav_zpos_mm
                cavity_start = cavity_center_z - cav_len / 2.0
                cavity_end = cavity_center_z + cav_len / 2.0

                cut_depth_fraction = 0.5
                effective_outer_r = cav_ir + (cav_or - cav_ir) * cut_depth_fraction

                outer_rect = plt.Rectangle(
                    (cavity_start, -effective_outer_r), cav_len, 2*effective_outer_r,
                    facecolor='white', edgecolor='red', linewidth=1.5, hatch='///', alpha=0.6
                )
                inner_rect = plt.Rectangle(
                    (cavity_start, -cav_ir), cav_len, 2*cav_ir,
                    facecolor='white', edgecolor='none'
                )

                ax.add_patch(outer_rect)
                ax.add_patch(inner_rect)
                ax.text(cavity_center_z, effective_outer_r + 2, "Microcavity",
                        fontsize=7, ha='center', va='bottom', color='red', weight='bold', style='italic')

            # === Step 3: Draw Coatings at Tip (Visually Exaggerated) ===
            coating_base_z = total_length
            display_gap = 0.001  # Small gap between coatings
            label_offset_y = []  # Track vertical positions to avoid overlap

            for name, mat_name, layer_type, ir, orad, L in layers:
                if "Coating" not in name and "coating" not in name:
                    continue

                real_thickness = L
                display_thickness = max(real_thickness * 50, 0.05)  # Visually thickened
                mat_data = self.material_props.get(mat_name, {})
                color = mat_data.get('color', '#8d99ae')  # Default gray if missing
                disk_orad = max_radius * 1.05

                rect = plt.Rectangle((coating_base_z, -disk_orad), display_thickness, 2*disk_orad,
                                    facecolor=color, edgecolor='black', linewidth=0.8, alpha=0.8)
                ax.add_patch(rect)

                # Stagger labels vertically to prevent overlap
                candidate_y = disk_orad + 3
                while any(abs(candidate_y - y) < 15 for y in label_offset_y):
                    candidate_y += 8  # Move up until clear
                label_offset_y.append(candidate_y)

                # Add label with background box for readability
                ax.text(coating_base_z + display_thickness/2, candidate_y, name,
                        fontsize=7, ha='center', va='bottom', color='black', weight='bold',
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='white', edgecolor='gray', alpha=0.9))

                coating_base_z += display_thickness + display_gap

            # === Final Layout ===
            final_length = max(coating_base_z, cavity_end) * 1.1 if sensor_type == "In-Fiber Microcavity" else coating_base_z * 1.1
            ax.set_xlim(0, final_length)
            ax.set_ylim(-max_radius, max_radius)
            ax.set_xlabel("Axial Position Z (mm)")
            ax.set_ylabel("Radial Position Y (μm)")
            ax.set_title("Fiber Sensor Structure (YZ Side View)")
            ax.grid(True, alpha=0.3, axis='x')

        self.preview_canvas.draw()
        self.preview_canvas.figure.savefig("sensor_preview.pdf", dpi=150, bbox_inches='tight')

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

    def on_photoliquid_toggled(self):
        status = "enabled" if self.use_photoliquid.isChecked() else "disabled"
        self.log.append(f"🧪 Photoliquid mode {status}")

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

                f.write("/run/initialize\n")
                f.write("/control/macroPath /home/geant4/work \n")
                f.write("/control/execute vis.mac\n")

                # Determine source
                source = self.source_type_combo.currentText()

                if source == "Custom":
                    particle = self.particle_combo.currentText()
                    try:
                        energy = float(self.energy_input.text())
                        f.write(f"/gps/particle {particle}\n")
                        f.write(f"/gps/energy {energy} MeV\n")
                        
                        if self.second_line_check.isChecked():
                            try:
                                second_energy = float(self.second_line_val.text())
                                f.write(f"/gps/hist/point {second_energy} MeV\n")
                                f.write(f"/gps/hist/weight 1.0\n")  # Equal probability
                            except:
                                pass
                    except:
                        f.write("/gps/particle gamma\n/gps/energy 0.662 MeV\n")

                elif "Cs-137" in source:
                    f.write("/gps/particle gamma\n")
                    f.write("/gps/energy 0.662 MeV\n")

                elif "Co-60" in source:
                    f.write("/gps/particle gamma\n")
                    f.write("/gps/energy 1.17 MeV\n")
                    #f.write("/gps/hist/weight 1.0\n")

                elif "Am-241" in source:
                    f.write("/gps/particle gamma\n")
                    f.write("/gps/energy 0.0595 MeV\n")

                elif "Na-22" in source:
                    f.write("/gps/particle gamma\n")
                    f.write("/gps/energy 0.511 MeV\n")
                    #f.write("/gps/hist/weight 1.0\n")

                elif "Thermal Neutron" in source:
                    f.write("/gps/particle neutron\n")
                    f.write("/gps/energy 0.025 eV\n")  # Thermal energy
                            
                # === Source Setup Based on Sensor Type ===
                if sensor_type == "In-Fiber Microcavity":
                    f.write("# Source Setup: Transverse Illumination for Microcavity\n")
                    f.write("/gps/pos/type Plane\n")
                    f.write("/gps/pos/shape Circle\n")
                    f.write("/gps/pos/radius 75.05 um\n")           # Cover radial extent
                    f.write("/gps/pos/centre 0 0 -0.1 mm\n")      # Z = -0.1 mm (just before fiber)
                #   Emit backward along +Z axis (into fiber)
                    f.write("/gps/ang/type iso\n")
                #   f.write("/gps/ang/mintheta 170 deg\n")   # Nearly backward
                    f.write("/gps/ang/maxtheta 0 deg\n")   # Directly backward    # Focused cone      # Small forward cone
                    # Wide cone
                    f.write("/gps/ene/type Mono\n")

                else:
                    # Standard End-Face Coated FPI
                    f.write("# Source Setup: End-Face Illumination\n")
                    f.write("/gps/pos/type Plane\n")
                    f.write("/gps/pos/shape Circle\n")
                    f.write("/gps/pos/radius 80.05 um\n")         # Slightly larger than coating
                    f.write("/gps/pos/centre 0 0 -0.001 mm\n")      # Z = -0.1 mm (just before fiber)
                    # Emit backward along +Z axis (into fiber)
                    f.write("/gps/ang/type iso\n")
                    f.write("/gps/ang/mintheta 0 deg\n")   # Nearly backward
                    f.write("/gps/ang/maxtheta  5 deg\n")   # Directly backward
                    f.write("/gps/ene/type Mono\n")
                
                # Run Settings
                n_events = 1000
                if hasattr(self, 'num_particles'):
                    try:
                        n_events = int(self.num_particles.text())
                    except:
                        pass
                f.write(f"/run/beamOn {n_events}\n")
                # Confirm vis.mac exists before running simulation
                vis_mac_path = os.path.join(self.output_folder.text(), "vis.mac")
                if not os.path.exists(vis_mac_path):
                    # Create it if missing
                    with open(vis_mac_path, 'w') as f:
                        f.write("/vis/open OGL\n")
                        f.write("/vis/drawVolume\n")
                        f.write("/vis/viewer/set/style surface\n")
                        f.write("/vis/viewer/set/viewpointThetaPhi 90 0 deg\n")
                        f.write("/vis/scene/add/axes 1 mm\n")
                        f.write("/vis/scene/endOfEventAction accumulate\n")
                    self.log.append("✅ Created vis.mac for visualization")
                else:
                    self.log.append("✅ Found vis.mac")

            self.log.append(f"✅ Generated input.mac with {n_events} events")
            
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
        """Draw in-fiber microcavity: transverse rectangular trench cutting through core/cladding"""
        # Total fiber length based on layer table
        total_length_mm = sum(L for _, _, _, _, _, L in self.get_layers_from_table())
        mid_z = total_length_mm / 2.0  # Center of fiber

        try:
            cav_radius_um = float(self.cav_radius.text())       # Radial depth from cladding edge
            cav_axial_len_um = float(self.cav_length.text())    # Axial length of cavity
            cav_z_offset_um = float(self.cav_zpos.text())       # Offset from center
            drill_axis = self.cav_axis.currentText()            # 'X' or 'Y'
        except Exception as e:
            print(f"Error reading cavity params: {e}")
            cav_radius_um, cav_axial_len_um, cav_z_offset_um, drill_axis = 5.0, 150.0, -2000.0, "X"

        # Convert to mm
        cav_radius_mm = cav_radius_um * 1e-3
        cav_axial_len_mm = cav_axial_len_um * 1e-3
        cav_zpos_mm = mid_z + (cav_z_offset_um * 1e-3)

        # Define cavity bounds
        cavity_start_z = cav_zpos_mm - cav_axial_len_mm / 2
        cavity_end_z = cav_zpos_mm + cav_axial_len_mm / 2
        cavity_outer_r = 75.0 + cav_radius_um  # From cladding radius outward
        cavity_inner_r = 75.0                 # Start at cladding outer edge

        # Draw hollow rectangle representing removed material
        rect = plt.Rectangle(
            (cavity_start_z, -cavity_outer_r),
            cavity_end_z - cavity_start_z,
            2 * cavity_outer_r,
            facecolor='white',
            edgecolor='red',
            linewidth=1.5,
            hatch='///',
            alpha=0.6,
            label="Microcavity"
        )
        ax.add_patch(rect)

        # Optional: draw inner boundary to highlight transition
        inner_rect = plt.Rectangle(
            (cavity_start_z, -cavity_inner_r),
            cavity_end_z - cavity_start_z,
            2 * cavity_inner_r,
            facecolor='white',
            edgecolor='none'
        )
        ax.add_patch(inner_rect)

        # Label
        ax.text(
            (cavity_start_z + cavity_end_z) / 2,
            cavity_outer_r + 2,
            "Microcavity",
            fontsize=7,
            ha='center',
            va='bottom',
            color='red',
            weight='bold',
            style='italic'
        )

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
            if density <= 0: raise ValueError
        except:
            QMessageBox.warning(self, "Input Error", "Density must be a positive number.")
            return

        # Use selected color, fallback if not picked
        color = getattr(self, 'selected_color', '#8d99ae')

        # Add to DB
        success = self.material_db.add_material(symbol, name, density, color=color)
        if success:
            self.log.append(f"✅ Added material: {symbol} ({name}, {density} g/cm³)")
            self.refresh_material_combos()
            # Clear inputs
            self.new_mat_symbol.clear()
            self.new_mat_name.clear()
            self.new_mat_density.clear()
            self.new_mat_color_label.setStyleSheet("")
            self.new_mat_color_label.setToolTip("")
            self.selected_color = '#8d99ae'
        else:
            QMessageBox.critical(self, "Save Failed", "Could not save material to database.")
    
    def update_custom_material(self):
        old_symbol = self.new_mat_symbol_combo.currentText().strip()
        new_symbol = self.new_mat_symbol_combo.currentText().strip()  # Can be changed
        name = self.new_mat_name.text().strip()
        density_str = self.new_mat_density.text().strip()
        color = getattr(self, 'selected_color', None)

        if not old_symbol:
            QMessageBox.warning(self, "Input Error", "Select a material to update.")
            return
        if not all([new_symbol, name, density_str]):
            QMessageBox.warning(self, "Input Error", "Symbol, name, and density are required.")
            return

        try:
            density = float(density_str)
            if density <= 0: raise ValueError
        except:
            QMessageBox.warning(self, "Input Error", "Density must be a positive number.")
            return

        if old_symbol not in self.material_db.list_materials():
            QMessageBox.warning(self, "Not Found", f"No material found with symbol '{old_symbol}'.")
            return

        # Perform update (including symbol rename)
        success = self.material_db.update_material(
            old_symbol,
            new_symbol=new_symbol,
            name=name,
            density=density,
            color=color
        )

        if success:
            self.log.append(f"🔄 Updated material: {old_symbol} → {new_symbol}")
            self.refresh_symbol_combobox()
            self.refresh_material_combos()
            self.update_preview()
            # Clear fields?
            # self.new_mat_name.clear(); self.new_mat_density.clear()
        else:
            QMessageBox.critical(self, "Update Failed", "Could not save changes.")

    def load_material_properties(self):
        materials_file = os.path.join(os.path.dirname(__file__), "materials.json")
        try:
            with open(materials_file, 'r') as f:
                raw = json.load(f)
            reserved = {'SOURCE', 'REFERENCES'}
            return {k: v for k, v in raw.items() if isinstance(v, dict) and k not in reserved}
        except Exception as e:
            self.log.append(f"💥 Failed to load materials.json: {str(e)}")
            return {}
        
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
        # === Reset plot area ===
        self.clear_plot()  # ← Clean before every run
        # === Clear Log Box First ===
        self.log.clear()  # ← Clears all text
        self.log.append("✅ Ready to simulate!")  # First message
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

    def compute_optical_spectrum(self, use_radiation_effect=True):
        """
        Compute FPI transmission spectrum using TMM.
        - Uses Δn from analyze_dose() for functional layers.
        - Supports photoliquid (LLT) as cavity medium.
        - Requires 'Axial_Thickness_mm' in dose_summary_df.
        """
        if not hasattr(self, 'dose_summary_df') or self.dose_summary_df is None:
            self.log.append("❌ No dose data available. Run 'Analyze Dose' first.")
            return None, None

        try:
            import numpy as np

            # === Debug: Check required columns exist ===
            expected_columns = ['Layer', 'Material', 'Type', 'Axial_Thickness_mm', 'Delta_n']
            missing_cols = [col for col in expected_columns if col not in self.dose_summary_df.columns]
            if missing_cols:
                self.log.append(f"💥 Missing columns: {missing_cols}")
                self.log.append("💡 Did you run the updated analyze_dose()?")
                return None, None

            # Base refractive indices
            n_core = 1.45
            n_clad = 1.44

            mirror_layers = []   # Functional coatings like TiO2, Gd2O3
            liquid_layer = None # LLT_Coating

            # Parse layers from dose_summary_df
            for _, row in self.dose_summary_df.iterrows():
                mat_name = row['Material']
                layer_name = row['Layer']

                # Skip structural fibers
                if 'Core' in layer_name or 'Cladding' in layer_name:
                    continue

                # Get base index from material database
                props = getattr(self, 'material_db', None)
                base_index = float(props.materials.get(mat_name, {}).get('refractive_index', 1.5))
                thickness_um = float(row['Axial_Thickness_mm']) * 1000  # mm → μm

                # Apply radiation-induced change
                delta_n = float(row['Delta_n'])
                if not use_radiation_effect:
                    delta_n = 0.0
                n_eff = base_index + delta_n

                # Classify by name
                if 'LLT' in layer_name or 'Liquid' in layer_name:
                    liquid_layer = {'n': n_eff, 'thickness': thickness_um}
                else:
                    mirror_layers.append({'n': n_eff, 'thickness': thickness_um})

            # Build optical stack: Core | Mirrors | Cavity | Cladding
            n_list = [n_core]
            d_list = [np.inf]  # Core semi-infinite

            # Add mirror layers (TiO₂, Gd₂O₃)
            for m in mirror_layers:
                n_list.append(m['n'])
                d_list.append(m['thickness'])

            # === Determine Cavity Medium ===
            if self.use_photoliquid.isChecked() and liquid_layer:
                cavity_length_um = liquid_layer['thickness']
                n_cavity = liquid_layer['n']
                self.log.append(f"🧪 Using LLT as cavity: n = {n_cavity:.9f}, L = {cavity_length_um} μm")
            elif self.use_photoliquid.isChecked():
                cavity_length_um = 5.0
                n_cavity = 1.56
                self.log.append("⚠️ No LLT layer found. Using default liquid cavity.")
            else:
                cavity_length_um = 5.0
                n_cavity = 1.0
                self.log.append("🌫️ Air cavity (n=1.0)")

            # === DEBUG MODE: Artificially enhance shift for visibility ===
            DEBUG_MODE = True
            if DEBUG_MODE:
                if use_radiation_effect:
                    n_cavity += 1e-4  # Simulate ionization-induced Δn
                    self.log.append("🔍 DEBUG: Artificial Δn = +0.0001 applied to cavity")
                else:
                    self.log.append("🔍 DEBUG: Reference spectrum – no artificial Δn")

            # Close the stack: cavity + cladding
            n_list += [n_cavity, n_clad]
            d_list += [cavity_length_um, np.inf]

            # === Coarse sweep to find approximate resonance ===
            lambdas_coarse = np.linspace(1400, 1600, 800)
            R_coarse = [tmm_reflectance(l, n_list, d_list) for l in lambdas_coarse]
            coarse_min_idx = np.argmin(R_coarse)
            center_lambda = float(lambdas_coarse[coarse_min_idx])

            # === Fine sweep around resonance ===
            try:
                start = self.lambda_start.value()
                end = self.lambda_end.value()
                points = self.num_points.value()
            except Exception:
                start, end, points = center_lambda - 0.05, center_lambda + 0.05, 2000

            lambdas = np.linspace(start, end, points)
            R = [tmm_reflectance(l, n_list, d_list) for l in lambdas]

            # === Sub-pixel peak detection via parabolic fit ===
            def find_min_with_fit(wl, r):
                min_idx = np.argmin(r)
                if 0 < min_idx < len(r) - 1:
                    x = wl[min_idx-1:min_idx+2]
                    y = r[min_idx-1:min_idx+2]
                    A = np.vstack([x**2, x, np.ones(3)]).T
                    try:
                        a, b, c = np.linalg.solve(A, y)
                        return -b / (2*a)
                    except:
                        pass
                return wl[min_idx]

            lambda_min = float(find_min_with_fit(lambdas, R))

            df = pd.DataFrame({'Wavelength_nm': lambdas, 'Reflectance_a.u.': R})
            return df, lambda_min

        except Exception as e:
            self.log.append(f"❌ TMM simulation failed: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())
            return None, None

    def export_dose_summary(self):
        """Export dose analysis summary as CSV + metadata comments at end"""
        if self.dose_summary_df is None:
            QMessageBox.warning(self, "No Data", "Run 'Analyze Dose' first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Dose Summary", "", "CSV Files (*.csv)"
        )
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
            'Dose_Gy': '',
            'Delta_T_K': '',
            'Delta_n': '',
            'Specific_Heat_J_kgK': '',
            'dn_dT_per_K': '',
            'Step_Count': self.dose_summary_df['Step_Count'].sum()
        }

        # Append summary
        df_export = pd.concat([self.dose_summary_df, pd.DataFrame([summary_row])], ignore_index=True)
        
        try:
            # Save DataFrame first
            df_export.to_csv(file_path, index=False)
            
            # Now append metadata lines at the end
            with open(file_path, 'a') as f:
                f.write("\n")
                
                # Safely write responsivity
                responsivity_val = getattr(self, 'sensor_responsivity', None)
                if isinstance(responsivity_val, (int, float)):
                    f.write(f"# Responsivity (pm/Gy): {responsivity_val:.3f}\n")
                else:
                    f.write("# Responsivity (pm/Gy): unknown\n")

                # Safely write sensitivity input
                if hasattr(self, 'sensitivity_input') and self.sensitivity_input is not None:
                    try:
                        sens_text = self.sensitivity_input.text().strip()
                        f.write(f"# Sensitivity (nm/RIU): {sens_text or 'unknown'}\n")
                    except Exception:
                        f.write("# Sensitivity (nm/RIU): error_reading\n")
                else:
                    f.write("# Sensitivity (nm/RIU): not_available\n")

            self.log.append(f"📁 Saved dose summary to {file_path}")
            self.log.append("📌 Metadata (responsivity, sensitivity) appended at end.")

        except Exception as e:
            self.log.append(f"❌ Failed to export dose summary: {str(e)}")
        
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
    
    def analyze_optical_response(self):
        """Compute optical response using TMM with support for photoliquid mode"""
        if not hasattr(self, 'dose_summary_df') or self.dose_summary_df is None:
            self.log.append("❌ Run 'Analyze Dose' first.")
            return

        try:
            # === Step 1: Compute reference spectrum (no radiation effect) ===
            ref_spectrum, lambda_0 = self.compute_optical_spectrum(use_radiation_effect=False)
            if ref_spectrum is None or lambda_0 is None:
                self.log.append("❌ Failed to compute reference spectrum.")
                return

            # === Step2: Compute perturbed spectrum (with radiation-induced Δn) ===
            pert_spectrum, lambda_pert = self.compute_optical_spectrum(use_radiation_effect=True)
            if pert_spectrum is None or lambda_pert is None:
                self.log.append("❌ Failed to compute perturbed spectrum.")
                return

            # === Step3: Compute spectral shift ===
            delta_lambda_pm = (lambda_pert - lambda_0) * 1000  # nm → pm

            # === Step4: Log results clearly ===
            if self.use_photoliquid.isChecked():
                self.log.append(f"\n🧪 Photoliquid Scintillator Mode (e.g., Altima Gold LLT)")
                self.log.append(f"   Base n: {getattr(self, '_liquid_n_base', 1.56):.6f}")
                self.log.append(f"   dn/dDose: {getattr(self, '_dn_per_gy', 1e-4):.2e} /Gy")
            else:
                self.log.append(f"\n🌫️ Standard Air-Gap FPI Mode")

            self.log.append(f"🎯 Predicted spectral shift: Δλ = {delta_lambda_pm:+.3f} pm")

            # === Step5: Plot both spectra ===
            ax = self.optics_ax
            ax.clear()

            wavelengths = ref_spectrum['Wavelength_nm']

            ax.plot(wavelengths, ref_spectrum['Reflectance_a.u.'],
                    'k--', linewidth=2,
                    label=f"Reference\n$\\lambda_{{\\min}}$ = {lambda_0:.3f} nm")

            ax.plot(wavelengths, pert_spectrum['Reflectance_a.u.'],
                    'r-', linewidth=2,
                    label=f"Perturbed\n$\\lambda_{{\\min}}$ = {lambda_pert:.3f} nm")

            # Add arrow showing shift
            ymin, ymax = ax.get_ylim()
            ytext = ymin + 0.9*(ymax - ymin)
            ax.annotate("", xy=(lambda_pert, ytext), xytext=(lambda_0, ytext),
                        arrowprops=dict(arrowstyle="<->", color="C0", lw=2))
            ax.text((lambda_0 + lambda_pert)/2, ytext*1.02, f"$\\Delta\\lambda = {delta_lambda_pm:+.1f}~\\mathrm{{pm}}$",
                    ha='center', fontsize=10, color="C0")

            ax.set_xlabel("Wavelength (nm)")
            ax.set_ylabel("Reflectance (a.u.)")
            ax.set_title("FPI Spectral Shift: Radiation-Induced RI Change")
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.set_xlim(wavelengths.min(), wavelengths.max())

            # Redraw canvas
            self.optics_canvas.draw()

            # Save figure
            fig_path = os.path.join(self.output_folder.text(), "fig2_optical_response.pdf") \
                    if hasattr(self, 'output_folder') and self.output_folder.text() else "fig2_optical_response.pdf"
            self.optics_canvas.figure.savefig(fig_path, dpi=300, bbox_inches='tight')
            self.log.append(f"Raw Ref λ_min = {lambda_0:.6f} nm")
            self.log.append(f"Raw Perturbed λ_min = {lambda_pert:.6f} nm")
            self.log.append(f"Raw Δλ = {(lambda_pert - lambda_0)*1000:.6f} pm")
            self.log.append(f"✅ Optical spectrum plotted: Δλ = {delta_lambda_pm:+.2f} pm")
            self.log.append(f"📊 Saved as: {fig_path}")

            # Store for export
            self.predicted_wavelength_shift_nm = delta_lambda_pm / 1000
            self.sensor_responsivity = delta_lambda_pm / self.dose_summary_df['Dose_Gy'].sum() \
                                    if self.dose_summary_df['Dose_Gy'].sum() > 0 else 0.0

        except Exception as e:
            self.log.append(f"❌ Failed to analyze optical response: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())
                        
    ############### Plotting & Analysis ################
    def plot_dose(self):
        """
        Plot energy deposits in YZ view with automatic layer detection.
        - Handles any number of functional coatings (e.g., Al2O3, HfO2, etc.)
        - No hardcoded names like 'Gd2O3' or 'TiO2'
        - Clear non-overlapping labels using color spans
        - High-contrast 'seismic' colormap
        - Safe colorbar handling
        """
        if self.dose_data is None or self.energy_ax is None:
            return

        ax = self.energy_ax
        ax.clear()

        df = self.dose_data.copy()
        if len(df) == 0:
            self.log.append("⚠️ No dose data available.")
            return

        # === Step 1: Diagnose Data ===
        self.log.append("🔍 Analyzing energy deposit data...")
        self.log.append(f"   Total entries: {len(df)}")
        self.log.append(f"   Unique Volumes: {', '.join(df['Volume'].unique())}")

        # === Step 2: Compute radial position and filter valid fiber volumes ===
        try:
            r = np.sqrt(df['X']**2 + df['Y']**2)
            z = df['Z'] * 1000  # Convert mm → μm
            E = df['Edep_keV']

            # Exclude World/Air/Vacuum-like volumes
            world_like = df['Volume'].str.contains('World|Air|Vacuum|Gas', case=False, na=False)
            volume_names = df[~world_like]['Volume'].unique()

            # Extract unique materials by removing _PV, _Coating, _Layer, etc.
            import re
            def extract_material(vol_name):
                base = re.sub(r'_PV.*|_coating.*|_layer.*|_vol.*', '', vol_name, flags=re.IGNORECASE)
                return base.strip()

            material_labels = [extract_material(v) for v in volume_names]
            valid_mask = ~world_like
        except Exception as e:
            self.log.append(f"❌ Failed to process coordinates: {e}")
            return

        if valid_mask.sum() == 0:
            self.log.append("⚠️ No valid energy deposits found for plotting.")
            return

        # === Step 3: Scatter plot with high-visibility colormap ===
        sc = ax.scatter(r[valid_mask], z[valid_mask],
                        c=E[valid_mask], cmap='seismic', s=15, alpha=0.9,
                        edgecolors='none', vmin=None, vmax=np.percentile(E[valid_mask], 98))

        # === Step 4: Axis formatting ===
        ax.set_xlabel("Radial Position $r$ (μm)", fontsize=12)
        ax.set_ylabel("Axial Position $z$ (μm)", fontsize=12)
        ax.set_title("Energy Deposits in Coated FPI Sensor", fontsize=14)

        # Set limits
        ax.set_xlim(0, max(80, r[valid_mask].max() * 1.1))
        z_min, z_max = z[valid_mask].min(), z[valid_mask].max()
        margin = (z_max - z_min) * 0.1
        ax.set_ylim(z_min - margin, z_max + margin)

        # === Step 5: Detect Layer Boundaries Automatically ===
        layer_info = {}
        used_radii = []

        for vol_name in volume_names:
            # Try to extract radius info from layer name or infer from X/Y data
            mask_vol = df['Volume'] == vol_name
            if not mask_vol.any():
                continue

            r_local = r[mask_vol]
            if len(r_local) == 0:
                continue

            mean_r = r_local.mean()
            label = vol_name.replace('_PV', '').replace('_Coating', '').replace('_', ' ')

            # Avoid placing multiple labels at same radius
            if not used_radii or min(abs(mean_r - np.array(used_radii))) > 0.5:
                layer_info[label] = {'radius': mean_r, 'color': None}
                used_radii.append(mean_r)

        # Assign distinct colors dynamically
        colors = plt.cm.tab10(np.linspace(0, 1, len(layer_info)))
        for i, key in enumerate(layer_info.keys()):
            layer_info[key]['color'] = colors[i]

        # === Step 7: Colorbar (Safe Handling) ===
        if hasattr(self, 'colorbar') and self.colorbar is not None:
            try:
                self.colorbar.ax.clear()
                self.colorbar.ax.figure.delaxes(self.colorbar.ax)
                self.colorbar = None
            except Exception:
                pass

        try:
            self.colorbar = self.energy_fig.colorbar(sc, ax=ax, label="Energy Deposit (keV)")
            self.colorbar.ax.tick_params(labelsize=11)
            self.colorbar.set_label("Energy Deposit (keV)", size=12)
        except Exception as e:
            self.log.append(f"⚠️ Colorbar creation failed: {e}")

        # === Step 8: Finalize Canvas ===
        self.energy_canvas.draw()

        # === Optional: Save Figure ===
        fig_saved = False
        output_dir = getattr(self, 'output_folder', None)
        if output_dir and output_dir.text():
            fig_path = os.path.join(output_dir.text(), "fig1_energy_deposits.pdf")
            try:
                self.energy_fig.savefig(fig_path, dpi=300, bbox_inches='tight')
                self.log.append(f"✅ Energy deposit plot saved: {fig_path}")
                fig_saved = True
            except Exception as e:
                self.log.append(f"❌ Could not save figure: {e}")

        if not fig_saved:
            try:
                self.energy_fig.savefig("fig1_energy_deposits.pdf", dpi=300, bbox_inches='tight')
                self.log.append("✅ Energy deposit plot saved locally.")
            except Exception as e:
                self.log.append(f"❌ Failed to save local figure: {e}")

        self.log.append(f"📊 Plotted {valid_mask.sum()} energy deposits across {len(layer_info)} layers.")
        
    ############### Dose Analysis ################
    def analyze_dose(self):
        """
        Compute Δn for each layer using energy deposits from Geant4.
        - For core/cladding: use radial geometry to compute mass per segment
        - For functional coatings: assume uniform end-face deposition over full fiber area
        with volume determined by axial thickness only.
        """
        if not hasattr(self, 'output_folder') or not self.output_folder.text():
            self.log.append("❌ Output folder not set.")
            return None

        try:
            # Load material properties
            materials_file = os.path.join(os.path.dirname(__file__), "materials.json")
            with open(materials_file, 'r') as f:
                material_props = json.load(f)
            self.log.append(f"✅ Loaded {len(material_props)} material properties")

            results = []
            total_energy_j = 0.0

            # Fixed fiber radius (cladding outer radius) in meters
            FIBER_RADIUS_UM = 75.0
            FIBER_AREA_M2 = np.pi * (FIBER_RADIUS_UM * 1e-6)**2  # m²

            # Process all layers
            for i in range(self.layer_table.rowCount()):
                w = lambda j: self.layer_table.cellWidget(i, j)

                try:
                    name = str(w(0).text()).strip()
                    mat_name = str(w(1).currentText()).strip()

                    def clean_text(txt):
                        import re
                        match = re.search(r'[\d.]+', str(txt))
                        return float(match.group()) if match else 0.0

                    ir_um = clean_text(w(3).text())
                    orad_um = clean_text(w(4).text())
                    axial_thickness_mm = clean_text(w(5).text())  # Axial length in mm
                    axial_thickness_m = axial_thickness_mm * 1e-3  # mm → m

                except Exception as e:
                    self.log.append(f"⚠️ Invalid input in row {i}: {str(e)}")
                    continue

                vol_name_pv = name + "_PV"
                df_layer = self.dose_data[self.dose_data['Volume'] == vol_name_pv]
                absorbed_energy_j = (df_layer['Edep_keV'] * 1.602e-16).sum() if len(df_layer) > 0 else 0.0

                # Get material properties
                density_gcm3 = material_props.get(mat_name, {}).get('density_g_cm3', 2.20)
                density_kg_m3 = density_gcm3 * 1000  # g/cm³ → kg/m³
                heat_capacity_j_kgk = material_props.get(mat_name, {}).get('specific_heat_J_per_kg_K', 700)
                dn_dt = material_props.get(mat_name, {}).get('dn_dT_per_K', 1.2e-5)

                # === Determine Layer Type ===
                if i == 0:
                    layer_type = 'Core'
                elif i == 1:
                    layer_type = 'Cladding'
                else:
                    layer_type = 'Functional Coating'

                # === Compute Mass Based on Layer Type ===
                if layer_type in ['Core', 'Cladding']:
                    # Use actual radial dimensions
                    r_inner = ir_um * 1e-6  # μm → m
                    r_outer = orad_um * 1e-6
                    area_m2 = np.pi * (r_outer**2 - r_inner**2)
                    volume_m3 = area_m2 * axial_thickness_m
                    mass_kg = density_kg_m3 * volume_m3
                else:
                    # Functional coating: covers entire end-face uniformly
                    volume_m3 = FIBER_AREA_M2 * axial_thickness_m
                    mass_kg = density_kg_m3 * volume_m3

                # === Compute Dose, ΔT, Δn ===
                dose_gy = absorbed_energy_j / max(mass_kg, 1e-20)
                delta_t_k = dose_gy / heat_capacity_j_kgk if heat_capacity_j_kgk > 0 else 0.0
                delta_n = dn_dt * delta_t_k

                # Store result
                results.append({
                    'Layer': name,
                    'Material': mat_name,
                    'Type': layer_type,
                    'Inner_Radius_um': ir_um,
                    'Outer_Radius_um': orad_um,
                    'Axial_Thickness_mm': axial_thickness_mm,
                    'Mass_kg': mass_kg,
                    'Energy_J': absorbed_energy_j,
                    'Dose_Gy': dose_gy,
                    'Delta_T_K': delta_t_k,
                    'Delta_n': delta_n,
                    'Specific_Heat_J_kgK': heat_capacity_j_kgk,
                    'dn_dT_per_K': dn_dt,
                    'Step_Count': len(df_layer)
                })
                total_energy_j += absorbed_energy_j

            # Create DataFrame
            self.dose_summary_df = pd.DataFrame(results)

            # Display results in GUI
            self.display_analysis_results()

            # === System-Level Response from Functional Coatings Only ===
            func_df = self.dose_summary_df[self.dose_summary_df['Type'] == 'Functional Coating']
            if len(func_df) == 0:
                self.log.append("⚠️ No functional coating layers found.")
                self.effective_delta_n = 0.0
                self.total_functional_thickness_nm = 0.0
                return

            # Total axial thickness of stack (for ML export)
            self.total_functional_thickness_nm = int(func_df['Axial_Thickness_mm'].sum() * 1e6)  # mm → nm

            # Weighted average Δn by energy deposition
            total_energy_func = func_df['Energy_J'].sum()
            if total_energy_func > 1e-30:
                self.effective_delta_n = (
                    (func_df['Delta_n'] * func_df['Energy_J']).sum() / total_energy_func
                )
            else:
                self.effective_delta_n = 0.0

            # Compute effective dose in kGy
            total_mass_func = func_df['Mass_kg'].sum()
            self.effective_dose_gy = total_energy_func / max(total_mass_func, 1e-20)
            self.effective_dose_kgy = self.effective_dose_gy / 1000.0  # Gy → kGy

            # Log summary
            self.log.append("\n🧩 System-Level Sensor Response:")
            self.log.append(f"  Total Functional Stack Height: {self.total_functional_thickness_nm} nm")
            self.log.append(f"  Effective Dose: {self.effective_dose_gy:.3e} Gy ({self.effective_dose_kgy:.3e} kGy)")
            self.log.append(f"  Effective Δn: {self.effective_delta_n:.3e}")

            # Store for downstream use
            self.effective_delta_n = self.effective_delta_n
            self.effective_dose_gy = self.effective_dose_gy

            # === Export Data for ML Training ===
            try:
                # Safely get source inputs
                try:
                    gamma_energy_MeV = float(self.energy_input.value()) \
                                    if hasattr(self.energy_input, 'value') \
                                    else float(self.energy_input.text() or 0.662)
                except:
                    gamma_energy_MeV = 0.662

                try:
                    num_events = int(self.num_particles.text())
                except:
                    num_events = 500000

                source_text = self.source_type_combo.currentText().strip()

                data = {
                    'coating_thickness_nm': self.total_functional_thickness_nm,
                    'gamma_dose_kGy': self.effective_dose_kgy,
                    'photon_energy_MeV': gamma_energy_MeV,
                    'num_events': num_events,
                    'source_type_Cs137': 1 if 'Cs137' in source_text else 0,
                    'source_type_Co60': 1 if 'Co60' in source_text else 0,
                    'source_type_Xray': 1 if 'X-ray' in source_text else 0,
                    'effective_delta_n': self.effective_delta_n,
                    'timestamp': pd.Timestamp.now().strftime('%H:%M.%S')
                }

                output_dir = self.output_folder.text()
                output_file = os.path.join(output_dir, "ml_dataset.csv")

                df = pd.DataFrame([data])
                df.to_csv(output_file, mode='a', header=not os.path.exists(output_file), index=False)

                self.log.append(f"📊 ML training data exported: thickness={data['coating_thickness_nm']} nm")
                self.log.append(f"📁 Saved to: {output_file}")

            except PermissionError:
                self.log.append("❌ Cannot write to ml_dataset.csv: file is locked (open in Excel?) or permission denied.")

            except Exception as e:
                self.log.append(f"❌ Failed to export ML data: {str(e)}")

        except Exception as e:
            self.log.append(f"💥 Dose analysis failed: {str(e)}")
            import traceback
            self.log.append(traceback.format_exc())
            self.dose_summary_df = None

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
        """Export simulation results to Excel with multiple sheets"""
        if self.dose_data is None:
            QMessageBox.warning(self, "No Data", "Run simulation first.")
            return

        # Define core columns (exclude Edep_J for clean export)
        core_columns = ['Volume', 'X', 'Y', 'Z', 'Edep_keV', 'StepLength_nm']
        try:
            export_df = self.dose_data[core_columns].copy()
        except KeyError as e:
            QMessageBox.critical(self, "Data Error", f"Missing column: {str(e)}")
            return

        # Summary per volume
        summary_data = []
        for vol in export_df['Volume'].unique():
            subset = export_df[export_df['Volume'] == vol]
            total_edep_j = (subset['Edep_keV'] * 1.602e-16).sum()
            count = len(subset)
            summary_data.append({
                'Volume': vol,
                'Step Count': count,
                'Total Energy (J)': total_edep_j
            })
        summary_df = pd.DataFrame(summary_data)

        # Open file dialog
        excel_file, _ = QFileDialog.getSaveFileName(
            self, "Save Results", "", "Excel Files (*.xlsx)"
        )
        if not excel_file:
            return

        # Ensure .xlsx extension
        if not excel_file.lower().endswith('.xlsx'):
            excel_file += '.xlsx'

        try:
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                # === 1. Raw Energy Deposits ===
                export_df.to_excel(writer, sheet_name='Energy_Deposits', index=False)
                self.log.append("✅ Saved raw energy deposits.")

                # === 2. Summary per Volume ===
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                self.log.append("✅ Saved summary by volume.")

                # === 3. Dose Analysis Results (if available) ===
                if hasattr(self, 'dose_summary_df') and isinstance(self.dose_summary_df, pd.DataFrame):
                    self.dose_summary_df.to_excel(writer, sheet_name='Dose_Summary', index=False)
                    self.log.append("✅ Saved dose analysis results.")

                # === 4. Geometry ===
                if hasattr(self, 'layer_table'):
                    geom_data = []
                    for i in range(self.layer_table.rowCount()):
                        w = lambda j: self.layer_table.cellWidget(i, j)
                        try:
                            layer_name = str(w(0).text()).strip()
                            material = str(w(1).currentText()).strip()

                            def get_val(widget):
                                txt = widget.currentText() if hasattr(widget, 'currentText') else widget.text()
                                try:
                                    return float(txt.strip())
                                except:
                                    return 0.0

                            layer_type = str(w(2).currentText()) if hasattr(w(2), 'currentText') else "Cylindrical"
                            inner_rad = get_val(w(3))
                            outer_rad = get_val(w(4))
                            length_mm = get_val(w(5))

                            geom_data.append({
                                'Layer': layer_name,
                                'Material': material,
                                'Type': layer_type,
                                'Inner Radius (μm)': inner_rad,
                                'Outer Radius (μm)': outer_rad,
                                'Length (mm)': length_mm
                            })
                        except Exception as e:
                            self.log.append(f"⚠️ Failed to read row {i}: {str(e)}")
                            continue

                    if geom_data:
                        pd.DataFrame(geom_data).to_excel(writer, sheet_name='Geometry', index=False)
                        self.log.append("✅ Saved sensor geometry.")

                # === 5. Optical Spectrum ===
                # Call compute_optical_spectrum ONCE
                result = self.compute_optical_spectrum(use_radiation_effect=True)
                spectrum_df = result[0] if isinstance(result, tuple) else result

                if isinstance(spectrum_df, pd.DataFrame) and not spectrum_df.empty:
                    spectrum_df.to_excel(writer, sheet_name='Optical_Spectrum', index=False)
                    self.log.append("✅ Saved optical spectrum (perturbed).")

                    # Save reference too?
                    ref_result = self.compute_optical_spectrum(use_radiation_effect=False)
                    ref_df = ref_result[0] if isinstance(ref_result, tuple) else ref_result
                    if isinstance(ref_df, pd.DataFrame) and not ref_df.empty:
                        ref_df.to_excel(writer, sheet_name='Reference_Spectrum', index=False)
                        self.log.append("✅ Saved reference spectrum (unperturbed).")
                else:
                    self.log.append("⚠️ No optical spectrum data to save.")

            # Final success log
            self.log.append(f"📊 Full results exported to: {excel_file}")

        except PermissionError:
            QMessageBox.critical(self, "Export Failed", "Cannot save: file may be open in Excel.")
            self.log.append("❌ Export failed: Close Excel and try again.")

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not save file:\n{str(e)}")
            self.log.append(f"❌ Export error: {str(e)}")

def main():
    app = QApplication(sys.argv)
    window = FiberSimulationUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()