// include/DetectorConstruction.hh
#ifndef DetectorConstruction_h
#define DetectorConstruction_h

#include "G4VUserDetectorConstruction.hh"
#include "G4String.hh"
#include "globals.hh"
#include "G4Material.hh"  // ← Add this
#include <vector>

class G4VPhysicalVolume;
class G4LogicalVolume;
class G4Material;

class DetectorConstruction : public G4VUserDetectorConstruction {
public:
    DetectorConstruction();
    virtual ~DetectorConstruction();  // ← Declare virtual destructor

    virtual G4VPhysicalVolume* Construct() override;

    // For command integration
    void AddLayer(const G4String& name, G4double ir, G4double orad, G4double len,
                  const G4String& matName, G4Material* mat);
    G4double GetFiberLength() const { return fiberLength; }

private:
    void DefineCommands();
    void BuildLayers();

    struct Layer {
        G4String name;
        G4double innerRadius, outerRadius;
        G4double length;
        G4String materialName;
        G4Material* material;

        Layer()
            : innerRadius(0), outerRadius(0), length(0), material(nullptr) {}

        Layer(const G4String& n, G4double ir, G4double orad, G4double len,
              const G4String& mn, G4Material* m = nullptr)
            : name(n), innerRadius(ir), outerRadius(orad), length(len),
              materialName(mn), material(m) {}
    };

    std::vector<Layer> layers;
    G4double fiberLength;
    class AddLayerCommand* addLayerCmd;  // Custom command
};

#endif