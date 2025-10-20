// src/SteppingAction.cc
#include "SteppingAction.hh"
#include "G4Step.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"
#include "G4ios.hh"

// Define static member
bool SteppingAction::headerWritten = false;

SteppingAction::SteppingAction()
{
    // --- Write to current directory ---
    std::ofstream clearFile("dose_per_step.txt", std::ios::out | std::ios::trunc);
    clearFile.close();

    doseFile.open("dose_per_step.txt", std::ios::app);

    if (!headerWritten) {
        doseFile << "# Volume\tX[um]\tY[um]\tZ[um]\tEdep[keV]\tLength[nm]" << G4endl;
        headerWritten = true;
    }

    if (!doseFile.is_open()) {
        G4Exception("SteppingAction::SteppingAction", "FileOpenError", FatalException,
                    "Could not open dose_per_step.txt");
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
    // Debug first few hits
    static int count = 0;
    if (++count <= 5) {
        G4cout << "🎯 Hit in " << volName 
               << " at Z=" << pos.z()/mm << " mm"
               << " | Edep=" << edep/keV << " keV" << G4endl;
    }
    // Write with tab separation
    doseFile
        << volName << "\t"
        << pos.x()/um << "\t" 
        << pos.y()/um << "\t" 
        << pos.z()/um << "\t"
        << edep/keV << "\t"
        << step->GetStepLength()/nm
        << G4endl;  // Flushes buffer — important!

    // Debug: log first hit
    static int count2 = 0;
    if (++count2 == 1) {
        G4cout << "🎯 First energy deposit: " << G4BestUnit(edep, "Energy") 
               << " in " << volName << G4endl;
    }
}