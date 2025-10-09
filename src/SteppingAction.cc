// SteppingAction.cc - Record energy deposit per step
#include "G4UserSteppingAction.hh"
#include "G4Step.hh"
#include "G4SDManager.hh"
#include <fstream>

// 🔧 Required for units like um, keV, nm
#include "G4SystemOfUnits.hh"      // Defines mm, um, keV, MeV, etc.
#include "G4PhysicalConstants.hh"  // For c_light, pi, etc.

class SteppingAction : public G4UserSteppingAction {
public:
    SteppingAction();
    virtual void UserSteppingAction(const G4Step*) override;
};

// Output file
std::ofstream doseFile("dose_per_step.txt", std::ios::app);

SteppingAction::SteppingAction() {
    // Write header
    doseFile << "# Volume\tX[um]\tY[um]\tZ[um]\tEdep[keV]\tLength[nm]\n";
}

void SteppingAction::UserSteppingAction(const G4Step* step) {
    G4double edep = step->GetTotalEnergyDeposit();
    if (edep <= 0.) return;

    const G4ThreeVector& pos = step->GetPreStepPoint()->GetPosition();
    G4String volName = step->GetPreStepPoint()->GetPhysicalVolume()->GetName();
    G4double stepLength = step->GetStepLength();

    // 🔧 Use CLHEP units: um, keV, nm
    doseFile
        << volName << "\t"
        << pos.x() / um << "\t"   // Position in micrometers
        << pos.y() / um << "\t"
        << pos.z() / um << "\t"
        << edep / keV << "\t"     // Energy in keV
        << stepLength / nm        // Step length in nanometers
        << "\n";
}