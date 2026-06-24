#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "Math/RandomStream.h"
#include "DataFarmAIController.generated.h"

// Navmesh autopilot ported from datafarm/backends/unrealzoo.py (the proven exploration policy):
//   - directed exploration: sample K reachable nav points, walk to the FARTHEST from current pos
//     (covers new ground instead of random-walk looping);
//   - stuck recovery: no >StuckDist progress over StuckWindow frames -> re-target;
//   - goal-reach re-target: once within GoalReach of the goal, pick a new one.
// Uses UNavigationSystemV1::GetRandomReachablePointInRadius + UAIBlueprintHelperLibrary::SimpleMoveToLocation.
UCLASS()
class TICKCAPTURE_API ADataFarmAIController : public AAIController
{
	GENERATED_BODY()

public:
	ADataFarmAIController();

	// Seed the exploration RNG (per-episode determinism). Call after possession.
	void InitExploration(int32 Seed);

	virtual void Tick(float DeltaSeconds) override;

	// --- proven constants (defaults mirror UnrealZooConfig in unrealzoo.py) ---
	UPROPERTY(EditAnywhere, Category = "DataFarm") float NavRadius = 8000.f;  // nav_radius: goal sampling radius (cm)
	UPROPERTY(EditAnywhere, Category = "DataFarm") int32 GoalCandidates = 4;  // goal_candidates: sample K, take farthest
	UPROPERTY(EditAnywhere, Category = "DataFarm") float GoalReach = 300.f;   // goal_reach: re-target within this (cm)
	UPROPERTY(EditAnywhere, Category = "DataFarm") int32 StuckWindow = 8;     // frames in the progress window
	UPROPERTY(EditAnywhere, Category = "DataFarm") float StuckDist = 40.f;    // <this cm over the window => stuck

private:
	bool SampleReachable(const FVector& Origin, float Radius, FVector& OutPoint) const;
	bool PickExploreGoal(const FVector& From, FVector& OutGoal) const;   // farthest-of-K
	void GoTo(const FVector& InGoal);

	FRandomStream Rng;
	FVector Goal = FVector::ZeroVector;
	bool bHasGoal = false;
	TArray<FVector> Recent;   // recent positions (ring) for stuck detection
};
