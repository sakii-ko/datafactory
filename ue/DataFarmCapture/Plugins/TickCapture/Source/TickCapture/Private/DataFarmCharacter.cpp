#include "DataFarmCharacter.h"

#include "DataFarmAIController.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/AnimInstance.h"
#include "Misc/Paths.h"

ADataFarmCharacter::ADataFarmCharacter()
{
	PrimaryActorTick.bCanEverTick = false;

	// Possessed by our navmesh AIController whether placed in the level or spawned at runtime.
	AIControllerClass = ADataFarmAIController::StaticClass();
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;

	// Orient-to-movement locomotion (the AIController only feeds nav targets; movement faces travel).
	bUseControllerRotationYaw = false;
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->bOrientRotationToMovement = true;
		Move->bUseControllerDesiredRotation = false;
		Move->RotationRate = FRotator(0.f, 360.f, 0.f);
		Move->MaxWalkSpeed = 200.f;   // ~ unrealzoo nav_speed (110) .. speed cap (200) cm/s
	}

	// Standard UE mannequin alignment: mesh dropped to capsule base, rotated to face +X.
	if (USkeletalMeshComponent* Body = GetMesh())
	{
		Body->SetRelativeLocation(FVector(0.f, 0.f, -90.f));
		Body->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
	}
}

void ADataFarmCharacter::Configure(const FString& MeshPath, const FString& AnimBpPath, const TArray<FString>& Wardrobe)
{
	USkeletalMeshComponent* Body = GetMesh();
	if (!Body)
	{
		return;
	}

	if (!MeshPath.IsEmpty())
	{
		if (USkeletalMesh* SK = LoadObject<USkeletalMesh>(nullptr, *MeshPath))
		{
			Body->SetSkeletalMeshAsset(SK);   // UE5.5: SetSkeletalMesh is deprecated
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("DataFarmCharacter: could not load mesh %s"), *MeshPath);
		}
	}

	if (!AnimBpPath.IsEmpty())
	{
		// Normalise an asset path to its generated UClass ('..._C'); StaticLoadClass needs the class.
		FString ClassPath = AnimBpPath;
		if (!ClassPath.EndsWith(TEXT("_C")))
		{
			FString Pkg, Obj;
			if (ClassPath.Split(TEXT("."), &Pkg, &Obj))
			{
				ClassPath = Pkg + TEXT(".") + Obj + TEXT("_C");
			}
			else
			{
				ClassPath = ClassPath + TEXT(".") + FPaths::GetCleanFilename(ClassPath) + TEXT("_C");
			}
		}
		if (UClass* AnimClass = StaticLoadClass(UAnimInstance::StaticClass(), nullptr, *ClassPath))
		{
			Body->SetAnimationMode(EAnimationMode::AnimationBlueprint);
			Body->SetAnimInstanceClass(AnimClass);
		}
		else
		{
			UE_LOG(LogTemp, Warning, TEXT("DataFarmCharacter: could not load AnimBP class %s"), *ClassPath);
		}
	}

	// Modular wardrobe: each part is a skeletal mesh driven by the body's pose (no own anim).
	for (const FString& PartPath : Wardrobe)
	{
		if (PartPath.IsEmpty())
		{
			continue;
		}
		USkeletalMesh* PartSK = LoadObject<USkeletalMesh>(nullptr, *PartPath);
		if (!PartSK)
		{
			UE_LOG(LogTemp, Warning, TEXT("DataFarmCharacter: could not load wardrobe %s"), *PartPath);
			continue;
		}
		USkeletalMeshComponent* Part = NewObject<USkeletalMeshComponent>(this);
		Part->SetupAttachment(Body);
		Part->RegisterComponent();
		Part->AttachToComponent(Body, FAttachmentTransformRules::SnapToTargetIncludingScale);
		Part->SetSkeletalMeshAsset(PartSK);
		Part->SetLeaderPoseComponent(Body);   // share the body's evaluated pose every frame
		WardrobeParts.Add(Part);
	}
}

void ADataFarmCharacter::GetEyeViewPoint(FVector& OutLocation, FRotator& OutRotation) const
{
	const FRotator YawRot(0.f, GetActorRotation().Yaw, 0.f);
	const USkeletalMeshComponent* Body = GetMesh();
	if (Body && EyeSocketName != NAME_None && Body->DoesSocketExist(EyeSocketName))
	{
		const FTransform S = Body->GetSocketTransform(EyeSocketName);
		OutLocation = S.GetLocation() + YawRot.RotateVector(EyeOffset);
	}
	else
	{
		const float HalfH = GetCapsuleComponent() ? GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
		OutLocation = GetActorLocation() + FVector(0.f, 0.f, HalfH * 0.85f) + YawRot.RotateVector(EyeOffset);
	}
	OutRotation = YawRot;
}
