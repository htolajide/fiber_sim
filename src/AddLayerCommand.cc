// src/AddLayerCommand.cc
#include "AddLayerCommand.hh"
#include "DetectorConstruction.hh"
#include "G4UImanager.hh"
#include "G4NistManager.hh"
#include "G4UnitsTable.hh"
#include "G4SystemOfUnits.hh"
#include "G4Exception.hh"
#include <sstream>

AddLayerCommand::AddLayerCommand(DetectorConstruction* det)
    : G4UIcmdWithAString("/detector/config/addLayer", nullptr), fDetector(det)
{
    SetGuidance("Add a cylindrical layer: name mat inRad(um) outRad(um) len(mm)");
    SetParameterName("params", false);
}

AddLayerCommand::~AddLayerCommand()
{
}

// ✅ Match exact signature: G4String newValue (pass by value)
void AddLayerCommand::SetNewValue(G4UIcommand* command, G4String newValue) {
    std::istringstream is(newValue);
    G4String name, matName;
    G4double inRad, outRad, len = fDetector->GetFiberLength() / mm;
    is >> name >> matName >> inRad >> outRad >> len;
    if (!is) {
        G4Exception("AddLayerCommand::SetNewValue", "InvalidInput", JustWarning,
                    "Invalid input format. Expected: name mat ir orad [len]");
        return;
    }
    inRad *= um; outRad *= um; len *= mm;

    G4NistManager* nist = G4NistManager::Instance();
    G4Material* mat = nist->FindOrBuildMaterial(matName);
    if (!mat) {
        // Try custom materials
        if (matName == "TiO2") {
            G4double density = 4.23 * g/cm3;
            mat = new G4Material("TiO2", density, 2);
            mat->AddElement(nist->FindOrBuildElement("Ti"), 1);
            mat->AddElement(nist->FindOrBuildElement("O"), 2);
        } else if (matName == "Gd2O3") {
            G4double density = 7.41 * g/cm3;
            mat = new G4Material("Gd2O3", density, 2);
            mat->AddElement(nist->FindOrBuildElement("Gd"), 2);
            mat->AddElement(nist->FindOrBuildElement("O"), 3);
        }
    }
    if (!mat) {
        G4ExceptionDescription msg;
        msg << "Unknown material: " << matName;
        G4Exception("AddLayerCommand::SetNewValue", "MatNotFound", JustWarning, msg);
        return;
    }

    fDetector->AddLayer(name, inRad, outRad, len, matName, mat);

    G4cout << "Added layer: " << name 
           << " [" << matName << "] "
           << inRad/um << " → " << outRad/um << " μm" << G4endl;
}