// include/AddLayerCommand.hh
#ifndef AddLayerCommand_h
#define AddLayerCommand_h

#include "G4UIcmdWithAString.hh"
#include "G4String.hh"

class DetectorConstruction;

class AddLayerCommand : public G4UIcmdWithAString {
public:
    AddLayerCommand(DetectorConstruction* det);
    virtual ~AddLayerCommand();

protected:
    void SetNewValue(G4UIcommand* command, G4String newValue);  // no 'override'

private:
    DetectorConstruction* fDetector;
};

#endif