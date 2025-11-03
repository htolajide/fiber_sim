#include "EventAction.hh"
#include "RunAction.hh"

EventAction::EventAction(RunAction* runAction)
    : G4UserEventAction(), fRunAction(runAction)
{}

EventAction::~EventAction() = default;

void EventAction::BeginOfEventAction(const G4Event*) {}

void EventAction::EndOfEventAction(const G4Event*) {}