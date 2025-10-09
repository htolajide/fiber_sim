#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4GeneralParticleSource.hh"
#include "G4Event.hh"
#include "G4SystemOfUnits.hh" 

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
private:
    G4GeneralParticleSource* fGPS;
public:
    PrimaryGeneratorAction();
    virtual void GeneratePrimaries(G4Event*);
};

PrimaryGeneratorAction::PrimaryGeneratorAction() {
    fGPS = new G4GeneralParticleSource();
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event) {
    fGPS->GeneratePrimaryVertex(event);
}