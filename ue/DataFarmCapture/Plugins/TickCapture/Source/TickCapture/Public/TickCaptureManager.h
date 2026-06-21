#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TickCaptureManager.generated.h"

class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class FRHIGPUTextureReadback;

struct FCaptureConfig
{
	FString EpisodeId = TEXT("ep");
	FString OutDir;
	int32 Width = 1280;
	int32 Height = 720;
	int32 NumFrames = 256;
	int32 WarmupFrames = 8;
	float Fps = 16.f;
	int32 Seed = 0;
	FString Viewpoint = TEXT("tpv");
	bool bOrbitTest = false;
};

// Tick-synchronized headless capture: each tick samples (RGB, player 6-DoF, camera 6-DoF,
// 6-dim action) and pushes a non-blocking GPU readback, writing frames/NNNNNN.png + steps.csv
// + meta.json in the datafarm schema. Zero temporal alignment error (Matrix-Game-3.0 §4.1).
UCLASS()
class TICKCAPTURE_API ATickCaptureManager : public AActor
{
	GENERATED_BODY()

public:
	ATickCaptureManager();

	void Configure(const FCaptureConfig& InCfg) { Cfg = InCfg; bConfigured = true; }
	void SetTrackedActor(AActor* InActor) { TrackedActor = InActor; }
	void SetAction(const TArray<uint8>& Keys);

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;

private:
	void EnqueueFrame(int32 OutIndex);
	void DrainReadbacks();
	void Finish();
	void SpawnTestScene();
	FString BuildRow(int32 OutIndex) const;

	UPROPERTY()
	USceneCaptureComponent2D* SceneCapture = nullptr;
	UPROPERTY()
	UTextureRenderTarget2D* RenderTarget = nullptr;
	UPROPERTY()
	AActor* TrackedActor = nullptr;

	FCaptureConfig Cfg;
	int32 TickCount = 0;
	bool bConfigured = false;
	bool bDone = false;
	uint8 Action[6] = {0, 0, 0, 0, 0, 0};

	struct FPendingReadback
	{
		TSharedPtr<FRHIGPUTextureReadback> Readback;
		int32 OutIndex = 0;
		FString Row;
	};
	TArray<FPendingReadback> Pending;
	TArray<FString> Rows;
};
