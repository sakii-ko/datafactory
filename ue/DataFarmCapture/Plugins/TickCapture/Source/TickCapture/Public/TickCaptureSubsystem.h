#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "TickCaptureSubsystem.generated.h"

// Auto-spawns + drives an ATickCaptureManager when launched with -CaptureConfig=<json>.
UCLASS()
class TICKCAPTURE_API UTickCaptureSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
};
