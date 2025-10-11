// include/SteppingAction.hh
#ifndef SteppingAction_h
#define SteppingAction_h

#include "G4UserSteppingAction.hh"
#include "globals.hh"
#include <fstream>

class G4Step;

class SteppingAction : public G4UserSteppingAction {
public:
    SteppingAction();
    virtual ~SteppingAction() override;

    virtual void UserSteppingAction(const G4Step*) override;

private:
    std::ofstream doseFile;
    static bool headerWritten;
};

#endif