// DetectorConstruction.cc
// Implementation of DetectorConstruction class for multilayer fiber FPI

#include "DetectorConstruction.hh"

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

// Helper: Create non-NIST materials
G4Material* CreateCustomMaterial(const G4String& name) {
    G4NistManager* nist = G4NistManager::Instance();

    if (name == "TiO2") {
        G4double density = 4.23 * g/cm3;
        G4Material* mat = new G4Material("TiO2", density, 2);
        mat->AddElement(nist->FindOrBuildElement("Ti"), 1);
        mat->AddElement(nist->FindOrBuildElement("O"), 2);
        return mat;
    }

    if (name == "Gd2O3") {
        G4double density = 7.41 * g/cm3;
        G4Material* mat = new G4Material("Gd2O3", density, 2);
        mat->AddElement(nist->FindOrBuildElement("Gd"), 2);
        mat->AddElement(nist->FindOrBuildElement("O"), 3);
        return mat;
    }

    if (name == "Al2O3") {
        G4double density = 3.97 * g/cm3;
        G4Material* mat = new G4Material("Al2O3", density, 2);
        mat->AddElement(nist->FindOrBuildElement("Al"), 2);
        mat->AddElement(nist->FindOrBuildElement("O"), 3);
        return mat;
    }

    if (name == "ZrO2") {
        G4double density = 5.68 * g/cm3;
        G4Material* mat = new G4Material("ZrO2", density, 2);
        mat->AddElement(nist->FindOrBuildElement("Zr"), 1);
        mat->AddElement(nist->FindOrBuildElement("O"), 2);
        return mat;
    }

    if (name == "HfO2") {
        G4double density = 9.68 * g/cm3;
        G4Material* mat = new G4Material("HfO2", density, 2);
        mat->AddElement(nist->FindOrBuildElement("Hf"), 1);
        mat->AddElement(nist->FindOrBuildElement("O"), 2);
        return mat;
    }

    return nullptr;
}

// Default constructor
DetectorConstruction::DetectorConstruction()
    : fiberLength(5.*mm), fMessenger(nullptr)
{
    Layer core = {"Core", 0, 4.1*um, fiberLength, "G4_SILICON_DIOXIDE", nullptr};
    Layer clad = {"Cladding", 4.1*um, 75*um, fiberLength, "G4_SILICON_DIOXIDE", nullptr};

    layers.push_back(core);
    layers.push_back(clad);

    DefineCommands();
}

void DetectorConstruction::DefineCommands() {
    fMessenger = new G4GenericMessenger(this, "/detector/config/", "Detector Configuration");

    auto& addLayerCmd = *fMessenger->DeclareMethod("addLayer",
        [this](G4String params) {
            std::istringstream is(params);
            G4String name, matName;
            G4double inRad, outRad, len = fiberLength/mm;
            is >> name >> matName >> inRad >> outRad >> len;
            inRad *= um; outRad *= um; len *= mm;

            Layer lyr;
            lyr.name = name;
            lyr.materialName = matName;
            lyr.innerRadius = inRad;
            lyr.outerRadius = outRad;
            lyr.length = len;

            G4NistManager* nist = G4NistManager::Instance();
            lyr.material = nist->FindOrBuildMaterial(matName);
            if (!lyr.material) {
                lyr.material = CreateCustomMaterial(matName);
            }
            if (!lyr.material) {
                G4ExceptionDescription msg;
                msg << "Unknown material: " << matName;
                G4Exception("DetectorConstruction::addLayer", "MatNotFound", JustWarning, msg);
                return;
            }

            layers.push_back(lyr);
            G4cout << "Added layer: " << name << " [" << matName << "] "
                   << inRad/um << " → " << outRad/um << " μm" << G4endl;
        });

    addLayerCmd.SetParameterName("params", false);
    addLayerCmd.SetDescription(
        "Add a cylindrical layer: name mat inRad(um) outRad(um) len(mm)"
    );

    fMessenger->DeclareProperty("fiberLength", fiberLength, "Fiber length in mm");
    fiberLength /= mm; fiberLength *= mm;
}

void DetectorConstruction::BuildLayers() {
    G4NistManager* nist = G4NistManager::Instance();

    for (auto& layer : layers) {
        if (layer.material) continue;
        layer.material = nist->FindOrBuildMaterial(layer.materialName);
        if (!layer.material) {
            layer.material = CreateCustomMaterial(layer.materialName);
        }
        if (!layer.material) {
            G4cerr << "⚠️ Material not found: " << layer.materialName << G4endl;
            layer.material = nist->FindOrBuildMaterial("G4_AIR");
        }
    }
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

        G4cout << "Built: " << lyr.name 
               << " (" << lyr.materialName << ") "
               << lyr.innerRadius/um << " → " << lyr.outerRadius/um << " μm" << G4endl;
    }

    return physWorld;
}