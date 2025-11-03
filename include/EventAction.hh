// include/EventAction.hh
#ifndef EVENT_ACTION_HH
#define EVENT_ACTION_HH

#include "G4UserEventAction.hh"

class RunAction;
class G4Event;

class EventAction : public G4UserEventAction
{
public:
    EventAction(RunAction* runAction);  // ✅ Takes RunAction*
    virtual ~EventAction();

    virtual void BeginOfEventAction(const G4Event*);
    virtual void EndOfEventAction(const G4Event*);

private:
    RunAction* fRunAction;  // Store for later use (e.g., filling histograms)
};

#endif