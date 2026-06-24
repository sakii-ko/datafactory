#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "DataFarmCharacter.generated.h"

class USkeletalMeshComponent;

// A rigged, navmesh-driven character for the own-content (TickCapture) track. Possessed by
// ADataFarmAIController, which autopilots it between reachable navmesh goals (collision-free).
// Configure() loads a SkeletalMesh + locomotion AnimBP onto the inherited Mesh component and
// attaches modular wardrobe parts driven by the body's pose (SetLeaderPoseComponent).
UCLASS()
class TICKCAPTURE_API ADataFarmCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ADataFarmCharacter();

	// Load body SkeletalMesh + locomotion AnimBP and attach wardrobe parts. Empty paths are
	// skipped (so a config with no mesh keeps the default capsule-only pawn). AnimBpPath may be
	// the asset path ('/Game/.../ABP.ABP') or the generated class ('/Game/.../ABP.ABP_C').
	void Configure(const FString& MeshPath, const FString& AnimBpPath, const TArray<FString>& Wardrobe);

	// World-space FPV eye viewpoint: head socket if present, else a forward+up offset from the
	// capsule top. OutRotation is the yaw-only look rotation (matches unrealzoo's eye cam).
	void GetEyeViewPoint(FVector& OutLocation, FRotator& OutRotation) const;

	// Eye socket on the skeleton (UE5 Manny/Quinn = "head"); falls back to a capsule offset.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "DataFarm")
	FName EyeSocketName = TEXT("head");

	// Eye offset in the actor's yaw frame: (forward, right, up) cm. Default ~ unrealzoo eye_offset.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "DataFarm")
	FVector EyeOffset = FVector(15.f, 0.f, 8.f);

private:
	UPROPERTY()
	TArray<USkeletalMeshComponent*> WardrobeParts;
};
