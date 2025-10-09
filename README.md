# Multilayer Fiber FPI Radiation Simulator

A GUI-based simulation tool for modeling radiation response in coated optical fiber Fabry-Pérot sensors.

## Features
- Dynamic multilayer geometry (core, cladding, coating, cavity)
- Support for micro-cavity FPI designs
- Material database with custom composites
- Real-time 2D structure preview
- Geant4 backend via Docker
- Dose visualization and export

## Requirements
- Python 3.8+ with PyQt5, pandas, matplotlib
- Docker Desktop
- Geant4 v11.3.2 source (`geant4-v11.3.2.tar.gz`)

## Usage
1. Install dependencies: `pip install pyqt5 pandas matplotlib`
2. Build Docker image: `docker build -t my-geant4 .`
3. Run: `python fiber_sim_ui.py`