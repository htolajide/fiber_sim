// DetectorConstruction.cc
#include "DetectorConstruction.hh"
#include "AddLayerCommand.hh"   // ← After main header

#include "G4RunManager.hh"
#include "G4NistManager.hh"
#include "G4Box.hh"
#include "G4Tubs.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4GenericMessenger.hh"
#include "G4Material.hh"
#include "G4Element.hh"
#include "G4UnitsTable.hh"
#include "G4Exception.hh"

DetectorConstruction::DetectorConstruction()
    : fiberLength(5.*mm), addLayerCmd(nullptr)
{
    layers.emplace_back("Core", 0, 4.1*um, fiberLength, "G4_SILICON_DIOXIDE");
    layers.emplace_back("Cladding", 4.1*um, 75*um, fiberLength, "G4_SILICON_DIOXIDE");

    DefineCommands();
}

void DetectorConstruction::DefineCommands() {
    addLayerCmd = new AddLayerCommand(this);
}

void DetectorConstruction::BuildLayers() {
    G4NistManager* nist = G4NistManager::Instance();

    for (auto& layer : layers) {
        if (layer.material) continue;
        layer.material = nist->FindOrBuildMaterial(layer.materialName);
        if (!layer.material) {
            if (layer.materialName == "TiO2") {
                G4double density = 4.23 * g/cm3;
                layer.material = new G4Material("TiO2", density, 2);
                layer.material->AddElement(nist->FindOrBuildElement("Ti"), 1);
                layer.material->AddElement(nist->FindOrBuildElement("O"), 2);
            } else if (layer.materialName == "Gd2O3") {
                G4double density = 7.41 * g/cm3;
                layer.material = new G4Material("Gd2O3", density, 2);
                layer.material->AddElement(nist->FindOrBuildElement("Gd"), 2);
                layer.material->AddElement(nist->FindOrBuildElement("O"), 3);
            }
        }
        if (!layer.material) {
            G4cerr << "⚠️ Material not found: " << layer.materialName << ", using air." << G4endl;
            layer.material = nist->FindOrBuildMaterial("G4_AIR");
        }
    }
}

void DetectorConstruction::AddLayer(const G4String& name, G4double ir, G4double orad, G4double len,
                                    const G4String& matName, G4Material* mat) {
    layers.emplace_back(name, ir, orad, len, matName, mat);
}

G4VPhysicalVolume* DetectorConstruction::Construct() {
    G4NistManager* nist = G4NistManager::Instance();

    G4double world_size = 1.*cm;
    G4Box* solidWorld = new G4Box("World", world_size, world_size, world_size);
    G4LogicalVolume* logicWorld = new G4LogicalVolume(solidWorld, nist->FindOrBuildMaterial("G4_AIR"), "World");
    G4VPhysicalVolume* physWorld = new G4PVPlacement(0, G4ThreeVector(), logicWorld, "World", 0, false, 0);

    BuildLayers();

    for (size_t i = 0; i < layers.size(); ++i) {
        const Layer& lyr = layers[i];
        if (lyr.outerRadius <= lyr.innerRadius) continue;

        G4Tubs* tub = new G4Tubs(lyr.name, lyr.innerRadius, lyr.outerRadius, lyr.length/2., 0, 360*deg);
        G4LogicalVolume* logVol = new G4LogicalVolume(tub, lyr.material, lyr.name);
        new G4PVPlacement(0, G4ThreeVector(), logVol, lyr.name + "_PV", logicWorld, false, 0);
    }

    return physWorld;
}

// Add this at the end of the file
DetectorConstruction::~DetectorConstruction() = default;