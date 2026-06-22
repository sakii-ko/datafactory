#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Math/RandomStream.h"
#include "ExplorerCharacter.generated.h"

class UStaticMeshComponent;

// A self-wandering character: picks random targets within a radius and steers toward
// them (orient-to-movement), producing diverse trajectories. No NavMesh dependency —
// open-floor steering with arrival/timeout retargeting. Deterministic given a seed.
UCLASS()
class TICKCAPTURE_API AExplorerCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AExplorerCharacter();
	void Init(int32 Seed, float BoundsRadius);
	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;

private:
	void PickTarget();

	UPROPERTY()
	UStaticMeshComponent* Body = nullptr;

	FRandomStream Rng;
	FVector Target = FVector::ZeroVector;
	float Bounds = 1500.f;
	float RetargetTimer = 0.f;
};
