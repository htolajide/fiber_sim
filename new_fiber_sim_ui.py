# main_window.py
import os
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QLineEdit, QLabel, QFileDialog, QTextEdit,
    QHeaderView, QSplitter
)
from PyQt5.QtCore import Qt


class FiberSimMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fiber FPI Radiation Sensor Simulator")
        self.setGeometry(100, 100, 1400, 900)  # Wide window for side-by-side layout

        # Data storage
        self.dose_data = None
        self.dose_summary_df = None
        self.output_folder = QLineEdit(os.path.join(os.path.expanduser("~"), "Documents", "Geant4SimResult"))

        self.init_ui()

    def init_ui(self):
        # === Main Widget and Layout ===
        container = QWidget()
        main_layout = QVBoxLayout(container)

        # === Splitter: Left Input Panel | Right Output Panel ===
        splitter = QSplitter(Qt.Horizontal)

        # Left: Input Group
        input_group = QGroupBox("Geometry & Simulation Setup")
        input_layout = QVBoxLayout(input_group)

        # --- Output Folder ---
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output Folder:"))
        output_layout.addWidget(self.output_folder)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_folder)
        output_layout.addWidget(btn_browse)
        input_layout.addLayout(output_layout)

        # --- Sensor Structure Selection ---
        struct_layout = QHBoxLayout()
        struct_layout.addWidget(QLabel("Sensor Structure:"))
        self.structure_combo = QComboBox()
        self.structure_combo.addItems([
            "End-Face Coated FPI",
            "In-Fiber Microcavity"
        ])
        self.structure_combo.setCurrentText("End-Face Coated FPI")
        self.structure_combo.currentTextChanged.connect(self.on_structure_changed)
        struct_layout.addWidget(self.structure_combo)
        input_layout.addLayout(struct_layout)

        # --- Layer Table ---
        self.layer_table = QTableWidget()
        self.layer_table.setColumnCount(5)
        self.layer_table.setHorizontalHeaderLabels([
            "Name", "Material", "Inner R (μm)", "Outer R (μm)", "Length (mm)"
        ])
        self.layer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        input_layout.addWidget(self.layer_table)

        # Add Row Button
        btn_add_layer = QPushButton("➕ Add Layer")
        btn_add_layer.clicked.connect(self.add_layer_row)
        input_layout.addWidget(btn_add_layer)

        # Insert microcavity parameters here (will be added dynamically)
        self.cav_group = None  # Placeholder

        # --- Buttons ---
        btn_run = QPushButton("▶️ Run Simulation")
        btn_run.clicked.connect(self.run_simulation)
        input_layout.addWidget(btn_run)

        btn_load = QPushButton("📂 Load Results")
        btn_load.clicked.connect(self.load_results)
        input_layout.addWidget(btn_load)

        btn_analyze = QPushButton("📊 Analyze Dose")
        btn_analyze.clicked.connect(self.analyze_dose)
        input_layout.addWidget(btn_analyze)

        btn_export = QPushButton("📤 Export Dose Summary")
        btn_export.clicked.connect(self.export_dose_summary)
        input_layout.addWidget(btn_export)

        # Add input group to splitter
        splitter.addWidget(input_group)

        # === Right: Output Group ===
        output_group = QGroupBox("Output & Log")
        output_layout = QVBoxLayout(output_group)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.append("✅ Fiber sensor simulator ready.")
        output_layout.addWidget(self.log)

        # Optional: Visualization placeholder
        btn_viz = QPushButton("🖼️ Update Visualization")
        btn_viz.clicked.connect(self.update_visualization)
        output_layout.addWidget(btn_viz)

        # Add output group to splitter
        splitter.addWidget(output_group)

        # Set sizes: left 60%, right 40%
        splitter.setSizes([800, 600])

        # Add splitter to main layout
        main_layout.addWidget(splitter)
        self.setCentralWidget(container)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)

    def on_structure_changed(self):
        """React when user changes sensor structure"""
        structure = self.structure_combo.currentText()
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

    def add_layer_row(self):
        row = self.layer_table.rowCount()
        self.layer_table.insertRow(row)

        # Name
        name_input = QLineEdit(f"Layer_{row+1}")
        self.layer_table.setCellWidget(row, 0, name_input)

        # Material
        mat_combo = QComboBox()
        mat_combo.addItems(["G4_SILICON_DIOXIDE", "TiO2", "Gd2O3", "Air", "Polymer"])
        self.layer_table.setCellWidget(row, 1, mat_combo)

        # Inner Radius
        ir_input = QLineEdit("0.0")
        self.layer_table.setCellWidget(row, 2, ir_input)

        # Outer Radius
        orad_input = QLineEdit("0.0")
        self.layer_table.setCellWidget(row, 3, orad_input)

        # Length
        len_input = QLineEdit("5.0")
        self.layer_table.setCellWidget(row, 4, len_input)

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

    def add_microcavity_parameters(self):
        """Add cavity geometry inputs below layer table"""
        self.cav_group = QGroupBox("Microcavity Parameters")
        cav_layout = QHBoxLayout()

        cav_form = QFormLayout()
        self.cav_radius = QLineEdit("5.0")   # μm
        self.cav_length = QLineEdit("150.0") # μm
        self.cav_zpos = QLineEdit("-2000.0") # μm
        self.cav_axis = QComboBox()
        self.cav_axis.addItems(["X", "Y"])

        cav_form.addRow("Radius (μm):", self.cav_radius)
        cav_form.addRow("Length (μm):", self.cav_length)
        cav_form.addRow("Z Position (μm):", self.cav_zpos)
        cav_form.addRow("Drill Axis:", self.cav_axis)
        cav_layout.addLayout(cav_form)

        self.cav_group.setLayout(cav_layout)
        self.findChild(QVBoxLayout).addWidget(self.cav_group)

    def run_simulation(self):
        self.log.append("🔧 Running simulation... (Not implemented yet)")
        # Placeholder — will connect to Geant4 later

    def load_results(self):
        self.log.append("📂 Loading dose results... (Placeholder)")

    def analyze_dose(self):
        self.log.append("📊 Analyzing dose distribution... (Placeholder)")

    def export_dose_summary(self):
        self.log.append("📁 Exporting dose summary... (Placeholder)")

    def update_visualization(self):
        self.log.append("🖼️ Updating 3D visualization... (Placeholder)")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FiberSimMainWindow()
    window.show()
    sys.exit(app.exec_())