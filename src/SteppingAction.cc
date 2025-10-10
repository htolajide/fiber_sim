// SteppingAction.cc
#include "G4UserSteppingAction.hh"
#include "G4Step.hh"
#include "G4SDManager.hh"
#include <fstream>

// Units
#include "G4SystemOfUnits.hh"

// Forward declare file stream
extern std::ofstream doseFile;  // Declare external

class SteppingAction : public G4UserSteppingAction {
public:
    SteppingAction();
    virtual ~SteppingAction() {
        if (doseFile.is_open()) {
            doseFile.close();
        }
    }
    virtual void UserSteppingAction(const G4Step*) override;
};

// Define globally
std::ofstream doseFile("dose_per_step.txt", std::ios::app);

SteppingAction::SteppingAction() {
    if (doseFile.is_open()) {
        doseFile << "# Volume\tX[um]\tY[um]\tZ[um]\tEdep[keV]\tLength[nm]\n";
    }
}

void SteppingAction::UserSteppingAction(const G4Step* step) {
    G4double edep = step->GetTotalEnergyDeposit();
    if (edep <= 0.) return;

    const G4ThreeVector& pos = step->GetPreStepPoint()->GetPosition();
    G4String volName = step->GetPreStepPoint()->GetPhysicalVolume()->GetName();
    G4double stepLength = step->GetStepLength();

    doseFile
        << volName << "\t"
        << pos.x()/um << "\t" << pos.y()/um << "\t" << pos.z()/um << "\t"
        << edep/keV << "\t"
        << stepLength/nm
        << "\n";
}