#ifndef DETECTOR_CONSTRUCTION_HH
#define DETECTOR_CONSTRUCTION_HH

#include "G4VUserDetectorConstruction.hh"
#include "G4String.hh"
#include "G4Material.hh"
#include <vector>

// Define layer types
enum LayerType {
    SOLID_CYLINDER,
    HOLLOW_CYLINDER,
    END_FACE_DISK,
    MICROCAVITY_SPACER,
    TAPERED_SECTION
};

struct Layer {
    G4String name;
    G4String materialName;
    G4double innerRadius, outerRadius, length;
    LayerType type;        // ✅ Now defined
    G4Material* material;
};

class DetectorConstruction : public G4VUserDetectorConstruction
{
public:
    DetectorConstruction();
    virtual ~DetectorConstruction();

    virtual G4VPhysicalVolume* Construct();

    // AddLayer now includes typeStr
    void AddLayer(const G4String&, const G4String&, G4double, G4double, G4double, const G4String&);

private:
    std::vector<Layer> layers;
};

#endif