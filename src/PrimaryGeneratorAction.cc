#include "PrimaryGeneratorAction.hh"
#include "G4Event.hh"
#include "G4GeneralParticleSource.hh"  // ✅ Must include
#include "G4ios.hh"

PrimaryGeneratorAction::PrimaryGeneratorAction()
{
    fParticleGun = new G4GeneralParticleSource();  // ✅ Correct assignment
    G4cout << "✅ PrimaryGeneratorAction: GPS initialized" << G4endl;
}

PrimaryGeneratorAction::~PrimaryGeneratorAction()
{
    delete fParticleGun;  // ✅ Safe to delete
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event)
{
    fParticleGun->GeneratePrimaryVertex(event);  // ✅ Valid call
}