#include "RunAction.hh"
#include "G4Run.hh"
#include "G4UnitsTable.hh"
#include "G4SystemOfUnits.hh"
#include <fstream>

RunAction::RunAction() = default;

RunAction::~RunAction() = default;

void RunAction::BeginOfRunAction(const G4Run* run)
{
    G4cout << "🏁 Starting run #" << run->GetRunID() << G4endl;

    // Open dose output file
    std::ofstream clearFile("../dose_per_step.txt", std::ios::out | std::ios::trunc);
    clearFile << "# Volume\tX[um]\tY[um]\tZ[um]\tEdep[keV]\tLength[nm]" << G4endl;
    clearFile.close();
}

void RunAction::EndOfRunAction(const G4Run*)
{
    G4cout << "✅ Run finished." << G4endl;
}