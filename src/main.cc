// src/main.cc
#include "G4RunManager.hh"
#include "G4UImanager.hh"

// User actions and detector construction
#include "DetectorConstruction.hh"
#include "ActionInitialization.hh"

// Physics list and models
#include "FTFP_BERT.hh" // For FTFP_BERT
#include "QGSP_BERT_HP.hh"                            
#include "G4EmStandardPhysics_option4.hh"             // High-precision EM
#include "G4DecayPhysics.hh"                          // Decay processes
#include "G4RadioactiveDecayPhysics.hh"               // Radioactive decay

// Visualization (optional)
#include "G4VisExecutive.hh"
#include "G4UIExecutive.hh"

int main(int argc, char** argv) {
    // Run manager
    G4RunManager* runManager = new G4RunManager;

    // Set up detector
    DetectorConstruction* detector = new DetectorConstruction();
    runManager->SetUserInitialization(detector);

    // Set up physics
    G4VModularPhysicsList* physicsList = new FTFP_BERT;                     // Base physics
    physicsList->ReplacePhysics(new G4EmStandardPhysics_option4());         // Better low-energy EM
    physicsList->RegisterPhysics(new G4DecayPhysics());
    physicsList->RegisterPhysics(new G4RadioactiveDecayPhysics());
    runManager->SetUserInitialization(physicsList);

    // Set up action initialization
    ActionInitialization* actions = new ActionInitialization();
    runManager->SetUserInitialization(actions);

    // Initialize
    runManager->Initialize();

    // Visualization manager
    G4VisManager* visManager = new G4VisExecutive;
    visManager->Initialize();

    // Get UI manager
    G4UImanager* UImanager = G4UImanager::GetUIpointer();

    if (argc == 1) {
        // Interactive mode
        G4UIExecutive ui(argc, argv);
        UImanager->ApplyCommand("/control/execute vis.mac");
        ui.SessionStart();
    } else {
        // Batch mode
        G4String command = "/control/execute ";
        G4String fileName = argv[1];
        UImanager->ApplyCommand(command + fileName);
    }

    // Cleanup
    delete visManager;
    delete runManager;

    return 0;
}