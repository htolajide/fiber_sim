// src/SteppingAction.cc
#include "SteppingAction.hh"
#include "G4Step.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"

// Define static member
bool SteppingAction::headerWritten = false;

SteppingAction::SteppingAction()
{
    // Open file in append mode
    doseFile.open("/home/geant4/work/dose_per_step.txt", std::ios::app);

    // Write header only once
    if (!headerWritten) {
        doseFile << "# Volume\tX[um]\tY[um]\tZ[um]\tEdep[keV]\tLength[nm]\n";
        headerWritten = true;
    }
}

SteppingAction::~SteppingAction() {
    if (doseFile.is_open()) {
        doseFile.close();
    }
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

    // Debug: log first hit
    static int count = 0;
    if (++count == 1) {
        G4cout << "🎯 First energy deposit: " << edep/keV 
               << " keV in " << volName << G4endl;
    }
}