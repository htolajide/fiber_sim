# tmm_engine.py
import numpy as np

def tmm_reflectance(lambda_nm, n_list, d_list):
    """
    Compute reflectance using Transfer Matrix Method for normal incidence.
    lambda_nm: Wavelength in nm
    n_list: List of refractive indices [n0, n1, ..., nN]
    d_list: List of layer thicknesses in micrometers (μm)
    """
    k0 = 2 * np.pi / lambda_nm
    r_total = 0.0

    for i in range(len(n_list) - 1):
        n1, n2 = n_list[i], n_list[i+1]
        d = d_list[i] if i < len(d_list) else 0
        r = (n1 - n2) / (n1 + n2)
        phase = k0 * n1 * d * 1000  # Convert μm → nm
        denominator = 1 + r * r_total * np.exp(-2j * phase)
        if abs(denominator) > 1e-15:
            r_total = (r + r_total * np.exp(-2j * phase)) / denominator
        if np.isinf(r_total) or np.isnan(r_total):
            r_total = 0.0
    return abs(r_total)**2


def compute_optical_spectrum(delta_n_dict, base_thickness_um=5.0):
    """
    Compute FPI transmission spectrum using TMM.
    Returns (wavelengths, reflectance)
    """
    # Base material indices
    n_core = 1.45
    n_clad = 1.44
    n_air = 1.0
    n_TiO2_base = 2.4
    n_Gd2O3_base = 1.9

    # Extract Δn from Geant4 results
    delta_n_tiO2 = delta_n_dict.get('TiO2_Coating_PV', {}).get('delta_n', 0.0)
    delta_n_gd2o3 = delta_n_dict.get('Gd2O3_Coating_PV', {}).get('delta_n', 0.0)

    n_TiO2 = n_TiO2_base + delta_n_tiO2
    n_Gd2O3 = n_Gd2O3_base + delta_n_gd2o3

    # Layer stack: Core | TiO2 | Gd2O3 | Air Gap | Cladding
    n_list = [n_core, n_TiO2, n_Gd2O3, n_air, n_clad]
    d_list = [np.inf, 0.2, 0.2, base_thickness_um, np.inf]  # in μm

    lambdas = np.linspace(1540, 1560, 800)
    R = [tmm_reflectance(l, n_list, d_list) for l in lambdas]

    return lambdas, R