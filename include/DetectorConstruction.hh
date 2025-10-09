// include/DetectorConstruction.hh
#ifndef DetectorConstruction_h
#define DetectorConstruction_h

// Required Geant4 headers
#include "G4VUserDetectorConstruction.hh"
#include "G4GenericMessenger.hh"       // For G4GenericMessenger
#include "G4Material.hh"               // For G4Material
#include "G4String.hh"                 // For G4String
#include "globals.hh"                  // For G4double, etc.

#include <vector>

class G4VPhysicalVolume;
class G4LogicalVolume;

class DetectorConstruction : public G4VUserDetectorConstruction {
public:
    DetectorConstruction();
    virtual ~DetectorConstruction() override;

    virtual G4VPhysicalVolume* Construct() override;

private:
    void DefineCommands();
    void BuildLayers();

    struct Layer {
        G4String name;
        G4double innerRadius, outerRadius;
        G4double length;
        G4String materialName;
        G4Material* material;

        Layer();  // Default constructor
    };

    std::vector<Layer> layers;
    G4double fiberLength;
    G4GenericMessenger* fMessenger;
};

#endif