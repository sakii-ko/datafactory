#include "ExplorerCharacter.h"

#include "GameFramework/CharacterMovementComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"

AExplorerCharacter::AExplorerCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;

	bUseControllerRotationYaw = false;
	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.f, 360.f, 0.f);
	Move->MaxWalkSpeed = 320.f;

	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	Body->SetupAttachment(RootComponent);
	Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Body->SetRelativeScale3D(FVector(0.7f, 0.7f, 1.8f));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (Cube.Succeeded())
	{
		Body->SetStaticMesh(Cube.Object);
	}
}

void AExplorerCharacter::Init(int32 Seed, float BoundsRadius)
{
	Rng.Initialize(Seed);
	Bounds = BoundsRadius;
}

void AExplorerCharacter::BeginPlay()
{
	Super::BeginPlay();
	PickTarget();
}

void AExplorerCharacter::PickTarget()
{
	const float A = Rng.FRandRange(-PI, PI);
	const float R = Rng.FRandRange(0.2f, 1.f) * Bounds;
	Target = FVector(R * FMath::Cos(A), R * FMath::Sin(A), GetActorLocation().Z);
	RetargetTimer = 0.f;
}

void AExplorerCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	RetargetTimer += DeltaSeconds;
	FVector To = Target - GetActorLocation();
	To.Z = 0.f;
	if (To.Size() < 120.f || RetargetTimer > 4.f)
	{
		PickTarget();
		To = Target - GetActorLocation();
		To.Z = 0.f;
	}
	AddMovementInput(To.GetSafeNormal(), 1.f);
}
