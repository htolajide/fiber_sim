// DetectorConstruction.cc
#include "DetectorConstruction.hh"

#include "G4SDManager.hh"
#include "G4MultiSensitiveDetector.hh"
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
#include "G4ThreeVector.hh"
#include "G4UserLimits.hh"
#include <fstream>
#include <sstream>
#include <set>

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

    if (name == "SiO2") {
        G4double density = 2.65 * g/cm3;
        G4Material* mat = new G4Material("SiO2", density, 2);
        mat->AddElement(nist->FindOrBuildElement("Si"), 1);
        mat->AddElement(nist->FindOrBuildElement("O"), 2);
        return mat;
    }

    if (name == "Si") {
        G4double density = 2.33 * g/cm3;
        G4Material* mat = new G4Material("Si", density, 1);
        mat->AddElement(nist->FindOrBuildElement("Si"), 1);
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

    if (name == "ZnO") {
        G4double density = 5.61 * g/cm3;
        G4Material* mat = new G4Material("ZnO", density, 2);
        mat->AddElement(nist->FindOrBuildElement("Zn"), 1);
        mat->AddElement(nist->FindOrBuildElement("O"), 1);
        return mat;
    }

    if (name == "ITO") {
        G4double density = 7.14 * g/cm3;
        G4Material* mat = new G4Material("ITO", density, 3);
        mat->AddElement(nist->FindOrBuildElement("In"), 2);
        mat->AddElement(nist->FindOrBuildElement("Sn"), 1);
        mat->AddElement(nist->FindOrBuildElement("O"), 3);
        return mat;
    }

    // === Handle Altima Gold LLT ===
    if (name == "Altima Gold LLT" || name == "Altima_Gold_LLT") {
        return nist->FindOrBuildMaterial("G4_POLYSTYRENE");
    }

    return nullptr;
}

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

            AddLayer(name, matName, ir*um, orad*um, len*mm, typeStr);  // ✅ Now valid: 6 args
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
    if (typeStr == "SOLID_CYLINDER") {
        lyr.type = SOLID_CYLINDER;
    } else if (typeStr == "HOLLOW_CYLINDER") {
        lyr.type = HOLLOW_CYLINDER;
    } else if (typeStr == "END_FACE_DISK") {
        lyr.type = END_FACE_DISK;
    } else if (typeStr == "MICROCAVITY_SPACER") {
        lyr.type = MICROCAVITY_SPACER;
    } else if (typeStr == "TAPERED_SECTION") {
        lyr.type = TAPERED_SECTION;
    } else {
        G4cerr << "⚠️ Unknown layer type: " << typeStr << ". Defaulting to HOLLOW_CYLINDER." << G4endl;
        lyr.type = HOLLOW_CYLINDER;
    }

    layers.push_back(lyr);

    G4cout << "📌 Queued: " << name << " [" << matName << "] "
           << innerR/um << " → " << outerR/um << " μm | Type: " << typeStr << G4endl;
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
    G4NistManager* nist = G4NistManager::Instance();

    // === 1. World Volume ===
    G4Box* solidWorld = new G4Box("World", 1.*cm, 1.*cm, 1.*m);
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
    G4double z_position = 0.0;

    // --- Step 1: Construct all layers ---
    std::vector<G4LogicalVolume*> coatingLogics;

    for (const auto& lyr : layers) {
        G4LogicalVolume* logVol = nullptr;
        G4VPhysicalVolume* physVol = nullptr;

        if (lyr.type == END_FACE_DISK) {
            G4Tubs* solid = new G4Tubs(lyr.name,
                                    0, lyr.outerRadius,
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

        // --- Step2: Mark coating layers as sensitive ---
        G4String matName = lyr.material->GetName();
        std::set<G4String> coatingMaterials = {"TiO2", "Gd2O3", "ZrO2", "Al2O3", "HfO2", "Si", "SiO2", "ZnO", "ITO", "C12H26"};

        if (coatingMaterials.find(matName) != coatingMaterials.end()) {
            coatingLogics.push_back(logVol);
            G4cout << "🎯 Sensitivity enabled for: " << lyr.name << " (" << matName << ")" << G4endl;
        }
    }

    // --- Step3: Create and assign Multi-Sensitive Detector ---
    if (!coatingLogics.empty()) {
        G4SDManager* sdManager = G4SDManager::GetSDMpointer();
        G4MultiSensitiveDetector* multiSD = new G4MultiSensitiveDetector("CoatingSD");
        sdManager->AddNewDetector(multiSD);

        for (auto* logic : coatingLogics) {
            logic->SetSensitiveDetector(multiSD);
            G4cout << "📌 Assigned sensitive detector to: " << logic->GetName() << "_PV" << G4endl;
        }
    }

    // --- Step4: Set step limits in thin coating layers ---
    G4double maxStep = 50 * nm;
    G4UserLimits* stepLimit = new G4UserLimits(maxStep);

    for (const auto& lyr : layers) {
        G4String matName = lyr.material->GetName();
        std::set<G4String> thinLayers = {"TiO2", "Gd2O3", "ZrO2", "Al2O3", "HfO2", "ZnO", "Si", "SiO2", "ITO", "C12H26"};

        if (thinLayers.find(matName) != thinLayers.end()) {
            for (auto* logic : coatingLogics) {
                if (logic->GetName() == lyr.name) {
                    logic->SetUserLimits(stepLimit);
                    G4cout << "📏 Step limit set to 50 nm in: " << lyr.name << G4endl;
                    break;
                }
            }
        }
    }

    return physWorld;
}