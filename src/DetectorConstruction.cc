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
#include "G4ThreeVector.hh"  // ✅ Added: needed for G4ThreeVector
#include <fstream>
#include <sstream>

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

// We'll assume `layers` is a member of DetectorConstruction class.
// So we need to use `this->layers` or just `layers` inside methods.
DetectorConstruction::~DetectorConstruction() = default;

DetectorConstruction::DetectorConstruction() {
    std::ifstream f("layers.cfg");
    if (!f) {
        G4cout << "❌ FAILED TO OPEN layers.cfg" << G4endl;
        return;
    }

    G4cout << "✅ Successfully opened layers.cfg" << G4endl;

    std::string line;
    while (std::getline(f, line)) {
        // Skip empty lines and comments
        if (line.empty() || line[0] == '#' || line.find_first_not_of(" \t") == std::string::npos) {
            continue;
        }

        std::istringstream iss(line);
        G4String name, matName, typeStr;
        G4double ir, orad, len;

        if (iss >> name >> matName >> ir >> orad >> len >> typeStr) {
            G4cout << "📄 Read: " << name 
                   << " | Mat=" << matName 
                   << " | R=" << ir << "-" << orad << " μm"
                   << " | L=" << len << " mm"
                   << " | Type=" << typeStr << G4endl;

            AddLayer(name, matName, ir*um, orad*um, len*mm, typeStr);
        } else {
            G4cout << "❌ Failed to parse line: " << line << G4endl;
        }
    }
}

void DetectorConstruction::AddLayer(const G4String& name,
                                   const G4String& matName,
                                   G4double innerR,
                                   G4double outerR,
                                   G4double length,
                                   const G4String& typeStr)
{
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

    // Convert string to enum
    if (typeStr == "END_FACE_DISK") {
        lyr.type = END_FACE_DISK;
    } else if (typeStr == "SOLID_CYLINDER") {
        lyr.type = SOLID_CYLINDER;
    } else if (typeStr == "HOLLOW_CYLINDER") {
        lyr.type = HOLLOW_CYLINDER;
    } else if (typeStr == "MICROCAVITY_SPACER") {
        lyr.type = MICROCAVITY_SPACER;
    } else {
        lyr.type = TAPERED_SECTION;
    }

    // Add to member vector
    layers.push_back(lyr);

    G4cout << "📌 Queued: " << name << " [" << matName << "] "
           << innerR/um << " → " << outerR/um << " μm | Type: " << typeStr << G4endl;
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
    G4NistManager* nist = G4NistManager::Instance();

    // === 1. World Volume ===
    G4Box* solidWorld = new G4Box("World", 1.*cm, 1.*cm, 1.*m);  // 1 meter long!
    G4LogicalVolume* logicWorld = new G4LogicalVolume(solidWorld,
                                                      nist->FindOrBuildMaterial("G4_AIR"),
                                                      "World");
    G4VPhysicalVolume* physWorld = new G4PVPlacement(0,
                                                     G4ThreeVector(),
                                                     logicWorld,
                                                     "World",
                                                     0,
                                                     false,
                                                     0);

    // Build along Z-axis starting near source
    G4double z_position = -5.0*mm;

    for (const auto& lyr : layers) {
        G4LogicalVolume* logVol = nullptr;
        G4VPhysicalVolume* physVol = nullptr;

        if (lyr.type == END_FACE_DISK) {
            // ✅ End-face disk: full radial coverage, very short axial thickness
            G4Tubs* solid = new G4Tubs(lyr.name,
                                       0, lyr.outerRadius,     // Starts at center
                                       lyr.length / 2., 0, 360*deg);
            logVol = new G4LogicalVolume(solid, lyr.material, lyr.name);
            physVol = new G4PVPlacement(0,
                                        G4ThreeVector(0, 0, z_position + lyr.length / 2.),
                                        logVol, lyr.name + "_PV",
                                        logicWorld, false, 0);
            z_position += lyr.length;

            G4cout << "🔷 Built Disk: " << lyr.name << " at Z=" << z_position/mm << " mm" << G4endl;
        }
        else if (lyr.type == SOLID_CYLINDER) {
            // ✅ Solid cylinder from center
            G4Tubs* solid = new G4Tubs(lyr.name,
                                       0, lyr.outerRadius,
                                       lyr.length / 2., 0, 360*deg);
            logVol = new G4LogicalVolume(solid, lyr.material, lyr.name);
            physVol = new G4PVPlacement(0,
                                        G4ThreeVector(0, 0, z_position + lyr.length / 2.),
                                        logVol, lyr.name + "_PV",
                                        logicWorld, false, 0);
            z_position += lyr.length;

            G4cout << "✅ Built Solid: " << lyr.name << " at Z=" << z_position/mm << " mm" << G4endl;
        }
        else {
            // ✅ Hollow Cylinder (Cladding, Spacer, etc.)
            G4Tubs* solid = new G4Tubs(lyr.name,
                                       lyr.innerRadius, lyr.outerRadius,
                                       lyr.length / 2., 0, 360*deg);
            logVol = new G4LogicalVolume(solid, lyr.material, lyr.name);
            physVol = new G4PVPlacement(0,
                                        G4ThreeVector(0, 0, z_position + lyr.length / 2.),
                                        logVol, lyr.name + "_PV",
                                        logicWorld, false, 0);
            z_position += lyr.length;

            G4cout << "🔶 Built Shell: " << lyr.name << " at Z=" << z_position/mm << " mm" << G4endl;
        }
    }

    return physWorld;
}