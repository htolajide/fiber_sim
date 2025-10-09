#include "G4RunManager.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "G4UIExecutive.hh"
#include "G4SystemOfUnits.hh" 

#include "G4EmStandardPhysics_option4.hh"
#include "G4HadronPhysicsQGSP_BERT_HP.hh"
#include "G4RadioactiveDecayPhysics.hh"

int main(int argc, char** argv) {
    G4RunManager* runManager = new G4RunManager;

    // Detector
    runManager->SetUserInitialization(new DetectorConstruction);

    // Physics
    G4VModularPhysicsList* physicsList = new G4VModularPhysicsList();
    physicsList->RegisterPhysics(new G4EmStandardPhysics_option4());
    physicsList->RegisterPhysics(new G4HadronPhysicsQGSP_BERT_HP());
    physicsList->RegisterPhysics(new G4RadioactiveDecayPhysics());
    runManager->SetUserInitialization(physicsList);

    // Generator
    runManager->SetUserAction(new PrimaryGeneratorAction);

    // Stepping
    runManager->SetUserAction(new SteppingAction);

    // Initialize
    runManager->Initialize();

    // Visualization and UI
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

    if (doseFile.is_open()) doseFile.close();
    return 0;
}