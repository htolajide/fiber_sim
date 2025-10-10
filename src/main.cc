// src/main.cc
#include "G4RunManager.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4UIExecutive.hh"

// Physics lists
#include "G4EmStandardPhysics_option4.hh"
#include "G4HadronPhysicsQGSP_BERT_HP.hh"
#include "G4RadioactiveDecayPhysics.hh"
#include "G4VModularPhysicsList.hh"  // ← Required!

// User actions
#include "DetectorConstruction.hh"               // ← Added!
#include "PrimaryGeneratorAction.hh"             // ← Added!
#include "SteppingAction.hh"                     // ← Added!

int main(int argc, char** argv) {
    G4RunManager* runManager = new G4RunManager;

    // Detector construction
    runManager->SetUserInitialization(new DetectorConstruction);  // ✅ Now known

    // Physics list
    G4VModularPhysicsList* physicsList = new G4VModularPhysicsList();  // ✅ Now valid
    physicsList->RegisterPhysics(new G4EmStandardPhysics_option4());
    physicsList->RegisterPhysics(new G4HadronPhysicsQGSP_BERT_HP());
    physicsList->RegisterPhysics(new G4RadioactiveDecayPhysics());
    runManager->SetUserInitialization(physicsList);

    // Generator action
    runManager->SetUserAction(new PrimaryGeneratorAction);  // ✅ Now known

    // Stepping action
    runManager->SetUserAction(new SteppingAction);  // ✅ Now known

    // Initialize
    runManager->Initialize();

    // Visualization
    G4VisManager* visManager = new G4VisExecutive;
    visManager->Initialize();

    G4UIExecutive* ui = new G4UIExecutive(argc, argv);
    G4UImanager* UImanager = G4UImanager::GetUIpointer();

    if (argc == 1) {
        UImanager->ApplyCommand("/control/execute macros/init_vis.mac");
        ui->SessionStart();
    } else {
        G4String command = "/control/execute ";
        G4String fileName = argv[1];
        UImanager->ApplyCommand(command + fileName);
    }

    delete ui;
    delete visManager;
    delete runManager;

    return 0;
}