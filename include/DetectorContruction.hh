// include/DetectorConstruction.hh
#ifndef DetectorConstruction_h
#define DetectorConstruction_h

#include "G4VUserDetectorConstruction.hh"
#include "globals.hh"
#include <vector>
#include <sstream>

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
        Layer();
    };

    std::vector<Layer> layers;
    G4double fiberLength;
    G4GenericMessenger* fMessenger;
};

#endif