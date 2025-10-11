// DetectorConstruction.cc
#include "DetectorConstruction.hh"

#include "G4RunManager.hh"
#include "G4NistManager.hh"
#include "G4Box.hh"
#include "G4Tubs.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4Material.hh"
#include "G4Element.hh"
#include "G4Exception.hh"
#include <fstream>
#include <sstream>

// Forward declaration
class G4VPhysicalVolume;
class G4LogicalVolume;

// Structure to hold layer definition
struct Layer {
    G4String name;
    G4String materialName;
    G4double innerRadius, outerRadius, length;
    G4Material* material;
};

// Helper: Create custom materials
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
    return nullptr;
}

DetectorConstruction::DetectorConstruction() {
    // Default layers
    // AddLayer("Core", "G4_SILICON_DIOXIDE", 0.0*um, 4.1*um, 5.0*mm);
    // AddLayer("Cladding", "G4_SILICON_DIOXIDE", 4.1*um, 75.0*um, 5.0*mm);

    // Read additional layers from file
    std::ifstream f("layers.cfg");
    if (!f) {
        G4cout << "No layers.cfg found — using defaults." << G4endl;
        return;
    }

    G4String name, matName;
    G4double ir, orad, len;
    while (f >> name >> matName >> ir >> orad >> len) {
        AddLayer(name, matName, ir*um, orad*um, len*mm);
    }
}

void DetectorConstruction::AddLayer(const G4String& name,
                                   const G4String& matName,
                                   G4double innerR, G4double outerR, G4double length) {
    G4NistManager* nist = G4NistManager::Instance();
    G4Material* mat = nist->FindOrBuildMaterial(matName);
    if (!mat) mat = CreateCustomMaterial(matName);
    if (!mat) {
        G4Exception("DetectorConstruction::AddLayer", "MatNotFound", JustWarning,
                    ("Unknown material: " + matName).c_str());
        return;
    }

    Layer lyr;
    lyr.name = name;
    lyr.materialName = matName;
    lyr.innerRadius = innerR;
    lyr.outerRadius = outerR;
    lyr.length = length;
    lyr.material = mat;

    layers.push_back(lyr);

    G4cout << "📌 Queued: " << name << " [" << matName << "] "
           << innerR/um << " → " << outerR/um << " μm" << G4endl;
}

G4VPhysicalVolume* DetectorConstruction::Construct() {
    G4NistManager* nist = G4NistManager::Instance();

    // === 1. World Volume ===
    G4Box* solidWorld = new G4Box("World", 1.*cm, 1.*cm, 1.*cm);
    G4LogicalVolume* logicWorld = new G4LogicalVolume(solidWorld, nist->FindOrBuildMaterial("G4_AIR"), "World");
    G4VPhysicalVolume* physWorld = new G4PVPlacement(0, G4ThreeVector(), logicWorld, "World", 0, false, 0);

    // === 2. Build All Layers ===
    for (const auto& lyr : layers) {
        if (lyr.outerRadius <= lyr.innerRadius) {
            G4Exception("DetectorConstruction::Construct", "InvalidGeom", JustWarning,
                        ("Invalid radii: " + lyr.name).c_str());
            continue;
        }

        G4Tubs* solid = new G4Tubs(lyr.name,
                                   lyr.innerRadius, lyr.outerRadius,
                                   lyr.length/2., 0, 360*deg);

        G4LogicalVolume* log = new G4LogicalVolume(solid, lyr.material, lyr.name);
        new G4PVPlacement(0, G4ThreeVector(), log, lyr.name + "_PV", logicWorld, false, 0);

        G4cout << "✅ Built: " << lyr.name << " [" << lyr.materialName << "] "
               << lyr.innerRadius/um << " → " << lyr.outerRadius/um << " μm" << G4endl;
    }

    return physWorld;
}