#include "G4UserSteppingAction.hh"
#include "G4Step.hh"
#include "G4SDManager.hh"
#include <fstream>

class SteppingAction : public G4UserSteppingAction {
public:
    SteppingAction();
    virtual void UserSteppingAction(const G4Step*) override;
};

std::ofstream doseFile("dose_per_step.txt", std::ios::app);

SteppingAction::SteppingAction() {
    doseFile << "# Volume\tX[um]\tY[um]\tZ[um]\tEdep[keV]\tLength[nm]\n";
}

void SteppingAction::UserSteppingAction(const G4Step* step) {
    G4double edep = step->GetTotalEnergyDeposit();
    if (edep <= 0.) return;

    G4String volName = step->GetPreStepPoint()->GetPhysicalVolume()->GetName();
    G4ThreeVector pos = step->GetPreStepPoint()->GetPosition();

    doseFile
        << volName << "\t"
        << pos.x()/um << "\t" << pos.y()/um << "\t" << pos.z()/um << "\t"
        << edep/keV << "\t"
        << step->GetStepLength()/nm
        << "\n";
}