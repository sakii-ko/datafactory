#include "DataFarmAIController.h"

#include "NavigationSystem.h"
#include "NavigationData.h"
#include "Blueprint/AIBlueprintHelperLibrary.h"
#include "GameFramework/Pawn.h"

ADataFarmAIController::ADataFarmAIController()
{
	PrimaryActorTick.bCanEverTick = true;
	bStartAILogicOnPossess = true;
	Rng.Initialize(1);
}

void ADataFarmAIController::InitExploration(int32 Seed)
{
	Rng.Initialize(Seed != 0 ? Seed : 1);
	bHasGoal = false;
	Recent.Reset();
}

bool ADataFarmAIController::SampleReachable(const FVector& Origin, float Radius, FVector& OutPoint) const
{
	UNavigationSystemV1* Nav = UNavigationSystemV1::GetCurrent(GetWorld());
	if (!Nav)
	{
		return false;
	}
	FNavLocation Result;
	if (Nav->GetRandomReachablePointInRadius(Origin, Radius, Result))
	{
		OutPoint = Result.Location;
		return true;
	}
	return false;
}

bool ADataFarmAIController::PickExploreGoal(const FVector& From, FVector& OutGoal) const
{
	// Directed exploration: sample K reachable points, keep the one farthest (2D) from `From`.
	bool bFound = false;
	float BestD = -1.f;
	FVector Best = FVector::ZeroVector;
	const int32 K = FMath::Max(1, GoalCandidates);
	for (int32 i = 0; i < K; ++i)
	{
		FVector P;
		if (SampleReachable(From, NavRadius, P))
		{
			const float D = FVector::DistSquared2D(P, From);
			if (D > BestD)
			{
				BestD = D;
				Best = P;
				bFound = true;
			}
		}
	}
	if (bFound)
	{
		OutGoal = Best;
	}
	return bFound;
}

void ADataFarmAIController::GoTo(const FVector& InGoal)
{
	Goal = InGoal;
	bHasGoal = true;
	Recent.Reset();   // mirror python: clear the stuck window on re-target
	UAIBlueprintHelperLibrary::SimpleMoveToLocation(this, Goal);
}

void ADataFarmAIController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	APawn* P = GetPawn();
	if (!P)
	{
		return;
	}
	const FVector Loc = P->GetActorLocation();

	// Stuck detection: <StuckDist (2D) progress across the last StuckWindow frames.
	Recent.Add(Loc);
	if (Recent.Num() > StuckWindow)
	{
		Recent.RemoveAt(0);
	}
	const bool bStuck = Recent.Num() >= StuckWindow &&
		FVector::Dist2D(Recent.Last(), Recent[0]) < StuckDist;

	const bool bReached = bHasGoal && FVector::Dist2D(Loc, Goal) < GoalReach;

	// (re)target when we have no goal yet (also retries until the navmesh has finished building,
	// mirroring unrealzoo's _nav_goal(tries=12) retry loop), are stuck, or have reached the goal.
	if (!bHasGoal || bStuck || bReached)
	{
		FVector G;
		if (PickExploreGoal(Loc, G))
		{
			GoTo(G);
		}
	}
}
