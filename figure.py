
import matplotlib.pyplot as plt
import numpy as np

# Parameters
responsivity_pm_per_Gy = -0.116  # pm/Gy
dose_Gy = np.linspace(0, 10, 100)  # 0 to 10 Gy
delta_lambda_nm = (responsivity_pm_per_Gy * dose_Gy) / 1000  # convert pm → nm

plt.figure(figsize=(8, 5))
plt.plot(dose_Gy, delta_lambda_nm, 'b-', linewidth=2)
plt.xlabel("Absorbed Dose (Gy)")
plt.ylabel("Wavelength Shift $\\Delta\\lambda$ (nm)")
plt.title("Predicted Spectral Shift vs. Absorbed Dose in TiO₂ Coating")
plt.grid(True, alpha=0.3)
plt.axhline(0, color='k', linewidth=0.5)
plt.axvline(0, color='k', linewidth=0.5)
plt.text(2, -0.0008, f'Slope = {responsivity_pm_per_Gy:.3f} pm/Gy', fontsize=12, bbox=dict(boxstyle="round", facecolor="wheat"))
plt.tight_layout()
plt.savefig("delta_lambda_vs_dose.png", dpi=300)
plt.show()