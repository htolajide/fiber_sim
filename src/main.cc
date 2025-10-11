// main.cc
#include "G4RunManager.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4UIExecutive.hh"

#include "QGSP_BERT_HP.hh"
#include "G4EmStandardPhysics_option4.hh"
#include "G4DecayPhysics.hh"
#include "G4RadioactiveDecayPhysics.hh"

#include "DetectorConstruction.hh"
#include "PrimaryGeneratorAction.hh"
#include "SteppingAction.hh"

int main(int argc, char** argv) {
    G4RunManager* runManager = new G4RunManager;

    DetectorConstruction* det = new DetectorConstruction;
    runManager->SetUserInitialization(det);

    QGSP_BERT_HP* physics = new QGSP_BERT_HP;
    physics->RegisterPhysics(new G4DecayPhysics());
    physics->RegisterPhysics(new G4RadioactiveDecayPhysics());
    runManager->SetUserInitialization(physics);

    runManager->SetUserAction(new PrimaryGeneratorAction);
    runManager->SetUserAction(new SteppingAction);

    runManager->Initialize();

    G4VisExecutive* vis = new G4VisExecutive;
    vis->Initialize();

    G4UImanager* UI = G4UImanager::GetUIpointer();

    if (argc == 1) {
        G4UIExecutive ui(argc, argv);
        UI->ApplyCommand("/control/execute init_vis.mac");
        ui.SessionStart();
    } else {
        G4String fileName = argv[1];
        UI->ApplyCommand("/control/execute " + fileName);
    }

    delete vis;
    delete runManager;

    return 0;
}