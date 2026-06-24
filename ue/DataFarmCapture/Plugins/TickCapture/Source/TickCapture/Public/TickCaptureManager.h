#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TickCaptureManager.generated.h"

class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class FRHIGPUTextureReadback;

// Optional own-content character (render_config.json "character": {id, mesh, anim_bp, wardrobe}).
// When Mesh is set, the manager spawns a navmesh-driven ADataFarmCharacter instead of the
// primitive AExplorerCharacter.
struct FCharacterConfig
{
	FString Id;
	FString Mesh;
	FString AnimBp;
	TArray<FString> Wardrobe;
	bool IsSet() const { return !Mesh.IsEmpty(); }
};

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
	bool bAgentMode = false;
	float AgentBounds = 1500.f;
	FCharacterConfig Character;

	// TPV smooth-follow chase cam (defaults mirror UnrealZooConfig in unrealzoo.py).
	float TpvBack = 350.f;     // distance behind the agent (cm)
	float TpvHeight = 180.f;   // height above the agent (cm)
	float TpvPitch = -12.f;    // downward pitch (deg)
	float TpvSmooth = 0.25f;   // lerp factor toward the behind-agent target (0..1)
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
	void UpdateFollowCamera();
	bool IsFPV() const { return Cfg.Viewpoint == TEXT("fpv"); }
	FString BuildRow(int32 OutIndex) const;

	UPROPERTY()
	USceneCaptureComponent2D* SceneCapture = nullptr;
	UPROPERTY()
	UTextureRenderTarget2D* RenderTarget = nullptr;
	UPROPERTY()
	AActor* TrackedActor = nullptr;
	UPROPERTY()
	AActor* Agent = nullptr;

	FCaptureConfig Cfg;
	int32 TickCount = 0;
	bool bConfigured = false;
	bool bDone = false;
	uint8 Action[6] = {0, 0, 0, 0, 0, 0};

	// TPV smooth-follow chase-cam state (lerps position + yaw toward the behind-agent target).
	FVector CamLoc = FVector::ZeroVector;
	float CamYaw = 0.f;   // radians
	bool bCamInit = false;

	struct FPendingReadback
	{
		TSharedPtr<FRHIGPUTextureReadback> Readback;
		int32 OutIndex = 0;
		FString Row;
	};
	TArray<FPendingReadback> Pending;
	TArray<FString> Rows;
	TSharedPtr<FThreadSafeCounter, ESPMode::ThreadSafe> SaveCounter;
};
