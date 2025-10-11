// include/DetectorConstruction.hh
#ifndef DetectorConstruction_h
#define DetectorConstruction_h

#include "G4VUserDetectorConstruction.hh"
#include "globals.hh"
#include "G4String.hh"
#include <vector>

class G4VPhysicalVolume;
class G4LogicalVolume;

struct Layer;  // Forward

class DetectorConstruction : public G4VUserDetectorConstruction {
public:
    DetectorConstruction();
    virtual ~DetectorConstruction() override = default;
    virtual G4VPhysicalVolume* Construct() override;

    void AddLayer(const G4String&, const G4String&, G4double, G4double, G4double);

private:
    std::vector<Layer> layers;
};

#endif