# test_dose_and_delta_n.py
import os
import re
import io
import pandas as pd
import numpy as np

def load_geant4_data(file_path):
    with open(file_path, 'r') as f:
        content = ''.join([line for line in f if not line.startswith('#')])
    volume_names = ['Core_PV', 'Cladding_PV', 'TiO2_Coating_PV', 'Gd2O3_Coating_PV']
    pattern = r'(' + '|'.join(volume_names) + r')(\t|-)'
    fixed_content = re.sub(pattern, lambda m: m.group(1) + '\t', content)
    df = pd.read_csv(io.StringIO(fixed_content), sep='\t',
                     names=['Volume','X','Y','Z','Edep_keV','StepLength_nm'])
    df['Edep_J'] = df['Edep_keV'] * 1.602e-16
    return df

# Auto-detect latest file
files = [f for f in os.listdir() if f.startswith("dose_") and f.endswith(".txt")]
latest_file = max(files, key=os.path.getctime)
df = load_geant4_data(latest_file)

material_props = {
    'TiO2': {'density_g_cm3': 4.23, 'specific_heat_J_per_kg_K': 680, 'dn_dT_per_K': 1.0e-4},
    'Gd2O3': {'density_g_cm3': 7.41, 'specific_heat_J_per_kg_K': 230, 'dn_dT_per_K': 2.0e-5}
}

layers = {
    'TiO2_Coating_PV': {'ir': 75.0, 'orad': 75.3, 'length': 0.03},  # μm → mm
    'Gd2O3_Coating_PV': {'ir': 75.3, 'orad': 75.5, 'length': 0.02}
}

def compute_volume(ir_um, orad_um, length_mm):
    r_inner = ir_um * 1e-6
    r_outer = orad_um * 1e-6
    L = length_mm * 1e-3
    return np.pi * (r_outer**2 - r_inner**2) * L

delta_n_dict = {}
for vol_name_template, dims in layers.items():
    matches = [v for v in df['Volume'].unique() if vol_name_template.split('_PV')[0] in v]
    if not matches:
        continue
    vol_name = matches[0]
    mask = df['Volume'] == vol_name
    total_energy_J = df[mask]['Edep_J'].sum()

    volume_m3 = compute_volume(dims['ir'], dims['orad'], dims['length'])
    mat_key = vol_name.split('_')[0]
    props = material_props.get(mat_key, {'density_g_cm3': 2.2, 'specific_heat_J_per_kg_K': 700, 'dn_dT_per_K': 1.2e-5})
    
    mass_kg = props['density_g_cm3'] * 1000 * volume_m3
    dose_Gy = total_energy_J / max(mass_kg, 1e-20)
    delta_T = dose_Gy / props['specific_heat_J_per_kg_K']
    delta_n = props['dn_dT_per_K'] * delta_T

    delta_n_dict[vol_name] = {'dose_Gy': dose_Gy, 'delta_n': delta_n}

# === TMM Test ===
def tmm_reflectance(lambda_nm, n_list, d_list):
    k0 = 2 * np.pi / lambda_nm
    r_total = 0.0
    for i in range(len(n_list)-1):
        n1, n2 = n_list[i], n_list[i+1]
        d = d_list[i]
        r = (n1 - n2)/(n1 + n2)
        phase = k0 * n1 * d * 1000
        denominator = 1 + r * r_total * np.exp(-2j*phase)
        if abs(denominator) > 1e-15:
            r_total = (r + r_total*np.exp(-2j*phase)) / denominator
    return abs(r_total)**2

# Build structure
n_core = 1.45; n_clad = 1.44; n_air = 1.0
n_TiO2 = 2.4 + delta_n_dict.get('TiO2_Coating_PV', {}).get('delta_n', 0)
n_Gd2O3 = 1.9 + delta_n_dict.get('Gd2O3_Coating_PV', {}).get('delta_n', 0)

n_list = [n_core, n_TiO2, n_Gd2O3, n_air, n_clad]
d_list = [np.inf, 0.03, 0.02, 5.0, np.inf]  # in mm → convert internally

lambdas = np.linspace(1200, 1650, 800)
R = [tmm_reflectance(l, n_list, d_list) for l in lambdas]

import matplotlib.pyplot as plt
plt.plot(lambdas, R)
plt.xlabel("Wavelength (nm)")
plt.ylabel("Reflectance")
plt.title("FPI Spectrum – Should Show Resonance Dip")
plt.grid(True)
plt.savefig("test_tmm_spectrum.pdf")
plt.show()

print("\n📊 Final Δn Results:")
for k, v in delta_n_dict.items():
    print(f"{k}: {v['dose_Gy']:.3f} Gy → Δn = {v['delta_n']:.2e}")