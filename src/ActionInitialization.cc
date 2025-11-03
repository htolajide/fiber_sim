#include "ActionInitialization.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "EventAction.hh"
#include "SteppingAction.hh"

ActionInitialization::ActionInitialization() = default;

ActionInitialization::~ActionInitialization() = default;

void ActionInitialization::BuildForMaster() const {
    SetUserAction(new RunAction);
}

void ActionInitialization::Build() const {
    // Create RunAction
    auto* runAction = new RunAction;
    SetUserAction(runAction);

    // Pass RunAction to EventAction
    SetUserAction(new PrimaryGeneratorAction);
    SetUserAction(new SteppingAction);
    SetUserAction(new EventAction(runAction));  // ✅ Pass the runAction instance
}