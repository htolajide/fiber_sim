#ifndef PrimaryGeneratorAction_h
#define PrimaryGeneratorAction_h

#include "G4VUserPrimaryGeneratorAction.hh"

class G4GeneralParticleSource;
class G4Event;

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
private:
    G4GeneralParticleSource* fGPS;
public:
    PrimaryGeneratorAction();
    virtual ~PrimaryGeneratorAction() override = default;
    virtual void GeneratePrimaries(G4Event*);
};

#endif