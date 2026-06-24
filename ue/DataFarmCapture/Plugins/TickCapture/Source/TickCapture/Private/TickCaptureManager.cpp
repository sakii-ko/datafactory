#include "TickCaptureManager.h"

#include "Components/SceneCaptureComponent2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "TextureResource.h"
#include "RHIGPUReadback.h"
#include "RenderingThread.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Modules/ModuleManager.h"
#include "Misc/App.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Async/Async.h"
#include "Engine/World.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"
#include "Math/RandomStream.h"
#include "ExplorerCharacter.h"
#include "DataFarmCharacter.h"
#include "DataFarmAIController.h"

ATickCaptureManager::ATickCaptureManager()
{
	PrimaryActorTick.bCanEverTick = true;
	SceneCapture = CreateDefaultSubobject<USceneCaptureComponent2D>(TEXT("SceneCapture"));
	RootComponent = SceneCapture;
}

void ATickCaptureManager::SetAction(const TArray<uint8>& Keys)
{
	for (int32 i = 0; i < 6 && i < Keys.Num(); ++i)
	{
		Action[i] = Keys[i] ? 1 : 0;
	}
}

void ATickCaptureManager::BeginPlay()
{
	Super::BeginPlay();
	if (!bConfigured)
	{
		UE_LOG(LogTemp, Warning, TEXT("TickCapture: BeginPlay with no config; idle."));
		return;
	}
	SaveCounter = MakeShared<FThreadSafeCounter, ESPMode::ThreadSafe>();
	RenderTarget = NewObject<UTextureRenderTarget2D>(this);
	RenderTarget->ClearColor = FLinearColor(0.45f, 0.65f, 0.95f);  // sky blue where no geometry
	RenderTarget->bAutoGenerateMips = false;
	RenderTarget->InitCustomFormat(Cfg.Width, Cfg.Height, PF_B8G8R8A8, false);
	RenderTarget->UpdateResourceImmediate(true);

	SceneCapture->TextureTarget = RenderTarget;
	SceneCapture->bCaptureEveryFrame = false;
	SceneCapture->bCaptureOnMovement = false;
	SceneCapture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
	// Lock exposure (disable eye-adaptation): min==max so the floor doesn't blow out
	// against the dark background and brightness is stable across frames.
	SceneCapture->PostProcessSettings.bOverride_AutoExposureMinBrightness = true;
	SceneCapture->PostProcessSettings.AutoExposureMinBrightness = 1.0f;
	SceneCapture->PostProcessSettings.bOverride_AutoExposureMaxBrightness = true;
	SceneCapture->PostProcessSettings.AutoExposureMaxBrightness = 1.0f;

	if (Cfg.bOrbitTest || Cfg.bAgentMode)
	{
		SpawnTestScene();
	}
	if (Cfg.bAgentMode)
	{
		if (UWorld* W = GetWorld())
		{
			FActorSpawnParameters SP;
			SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			if (Cfg.Character.IsSet())
			{
				// Own-content track: rigged, navmesh-driven character (collision-aware autopilot).
				ADataFarmCharacter* Ch = W->SpawnActor<ADataFarmCharacter>(FVector(0, 0, 150), FRotator::ZeroRotator, SP);
				if (Ch)
				{
					Ch->Configure(Cfg.Character.Mesh, Cfg.Character.AnimBp, Cfg.Character.Anim, Cfg.Character.Wardrobe);
					if (ADataFarmAIController* AI = Cast<ADataFarmAIController>(Ch->GetController()))
					{
						AI->InitExploration(Cfg.Seed);
					}
					Agent = Ch;
					TrackedActor = Ch;
				}
			}
			else
			{
				// Fallback: primitive open-floor wanderer (no skeletal mesh / no navmesh needed).
				AExplorerCharacter* Ch = W->SpawnActor<AExplorerCharacter>(FVector(0, 0, 150), FRotator::ZeroRotator, SP);
				if (Ch)
				{
					Ch->Init(Cfg.Seed, Cfg.AgentBounds);
					Agent = Ch;
					TrackedActor = Ch;
				}
			}
		}
	}
	if (!TrackedActor)
	{
		TrackedActor = this;
	}
	IFileManager::Get().MakeDirectory(*(Cfg.OutDir / TEXT("frames")), true);

	FApp::SetUseFixedTimeStep(true);
	FApp::SetFixedDeltaTime(1.0 / FMath::Max(1.f, Cfg.Fps));
	UE_LOG(LogTemp, Display, TEXT("TickCapture: capturing %d frames -> %s"), Cfg.NumFrames, *Cfg.OutDir);
}

void ATickCaptureManager::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bDone || !bConfigured)
	{
		return;
	}
	DrainReadbacks();

	if (TickCount >= Cfg.WarmupFrames + Cfg.NumFrames)
	{
		if (Pending.Num() == 0 && SaveCounter->GetValue() == 0)
		{
			Finish();
		}
		return;
	}

	if (Cfg.bAgentMode)
	{
		UpdateFollowCamera();
	}
	else if (Cfg.bOrbitTest)
	{
		const float Ang = TickCount * 0.05f;
		SetActorLocation(FVector(600.f * FMath::Cos(Ang), 600.f * FMath::Sin(Ang), 200.f));
		SetActorRotation(FRotator(-10.f, FMath::RadiansToDegrees(Ang) + 180.f, 0.f));
	}

	SceneCapture->CaptureScene();
	if (TickCount >= Cfg.WarmupFrames)
	{
		EnqueueFrame(TickCount - Cfg.WarmupFrames);
	}
	++TickCount;
}

void ATickCaptureManager::EnqueueFrame(int32 OutIndex)
{
	const FString Row = BuildRow(OutIndex);
	TSharedPtr<FRHIGPUTextureReadback> RB = MakeShared<FRHIGPUTextureReadback>(TEXT("DataFarmReadback"));
	FRHIGPUTextureReadback* RBptr = RB.Get();
	FTextureRenderTargetResource* RTRes = RenderTarget->GameThread_GetRenderTargetResource();

	ENQUEUE_RENDER_COMMAND(DataFarmEnqueueCopy)(
		[RBptr, RTRes](FRHICommandListImmediate& RHICmdList)
		{
			FRHITexture* Tex = RTRes->GetRenderTargetTexture();
			RHICmdList.Transition(FRHITransitionInfo(Tex, ERHIAccess::Unknown, ERHIAccess::CopySrc));
			RBptr->EnqueueCopy(RHICmdList, Tex);
		});

	Pending.Add({RB, OutIndex, Row});
}

void ATickCaptureManager::DrainReadbacks()
{
	const int32 W = Cfg.Width;
	const int32 H = Cfg.Height;
	while (Pending.Num() > 0 && Pending[0].Readback->IsReady())
	{
		FPendingReadback P = Pending[0];
		Pending.RemoveAt(0);

		int32 RowPitchInPixels = 0;
		const uint8* Src = static_cast<const uint8*>(P.Readback->Lock(RowPitchInPixels));
		TArray<FColor> Pixels;
		Pixels.SetNumUninitialized(W * H);
		for (int32 y = 0; y < H; ++y)
		{
			const FColor* SrcRow = reinterpret_cast<const FColor*>(Src + static_cast<int64>(y) * RowPitchInPixels * 4);
			for (int32 x = 0; x < W; ++x)
			{
				Pixels[y * W + x] = SrcRow[x];
			}
		}
		P.Readback->Unlock();

		const FString Path = Cfg.OutDir / FString::Printf(TEXT("frames/%06d.png"), P.OutIndex);
		SaveCounter->Increment();
		TSharedPtr<FThreadSafeCounter, ESPMode::ThreadSafe> SC = SaveCounter;
		Async(EAsyncExecution::ThreadPool, [Pixels = MoveTemp(Pixels), W, H, Path, SC]()
		{
			IImageWrapperModule& Mod = FModuleManager::LoadModuleChecked<IImageWrapperModule>("ImageWrapper");
			TSharedPtr<IImageWrapper> Img = Mod.CreateImageWrapper(EImageFormat::PNG);
			Img->SetRaw(Pixels.GetData(), static_cast<int64>(Pixels.Num()) * sizeof(FColor), W, H, ERGBFormat::BGRA, 8);
			FFileHelper::SaveArrayToFile(Img->GetCompressed(100), *Path);
			SC->Decrement();
		});
		Rows.Add(P.Row);
	}
}

FString ATickCaptureManager::BuildRow(int32 OutIndex) const
{
	const FTransform PT = TrackedActor ? TrackedActor->GetActorTransform() : GetActorTransform();
	const FTransform CT = SceneCapture->GetComponentTransform();
	const FVector PP = PT.GetLocation();
	const FQuat PQ = PT.GetRotation();
	const FVector CP = CT.GetLocation();
	const FQuat CQ = CT.GetRotation();
	return FString::Printf(
		TEXT("%d,%f,frames/%06d.png,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%d,%d,%d,%d,%d,%d"),
		OutIndex, OutIndex / Cfg.Fps, OutIndex,
		PP.X, PP.Y, PP.Z, PQ.W, PQ.X, PQ.Y, PQ.Z,
		CP.X, CP.Y, CP.Z, CQ.W, CQ.X, CQ.Y, CQ.Z,
		Action[0], Action[1], Action[2], Action[3], Action[4], Action[5]);
}

void ATickCaptureManager::SpawnTestScene()
{
	UWorld* W = GetWorld();
	if (!W) return;
	FActorSpawnParameters SP;

	auto SpawnSun = [&](const FRotator& Rot, float Intensity)
	{
		if (ADirectionalLight* L = W->SpawnActor<ADirectionalLight>(FVector(0, 0, 1000), Rot, SP))
		{
			if (auto* C = Cast<UDirectionalLightComponent>(L->GetLightComponent()))
			{
				C->SetMobility(EComponentMobility::Movable);
				C->SetIntensity(Intensity);
			}
		}
	};
	SpawnSun(FRotator(-50, 40, 0), 4.f);   // key
	SpawnSun(FRotator(-20, -150, 0), 1.5f);  // fill (no pure-black shadows; no SkyAtmosphere)

	UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UStaticMesh* Cyl = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	auto SpawnMesh = [&](UStaticMesh* M, const FVector& Loc, const FVector& Scale)
	{
		if (!M) return;
		AStaticMeshActor* A = W->SpawnActor<AStaticMeshActor>(Loc, FRotator::ZeroRotator, SP);
		if (!A) return;
		A->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
		A->GetStaticMeshComponent()->SetStaticMesh(M);
		A->SetActorScale3D(Scale);
	};
	SpawnMesh(Plane, FVector(0, 0, 0), FVector(80, 80, 1));

	// scatter varied primitives for visual reference + parallax
	FRandomStream Rng(Cfg.Seed * 977 + 13);
	for (int32 i = 0; i < 18; ++i)
	{
		const float a = Rng.FRandRange(-PI, PI), r = Rng.FRandRange(250.f, Cfg.AgentBounds);
		const float h = Rng.FRandRange(1.f, 4.f);
		SpawnMesh(Rng.FRand() < 0.5f ? Cube : Cyl,
			FVector(r * FMath::Cos(a), r * FMath::Sin(a), h * 50.f),
			FVector(Rng.FRandRange(1.f, 2.5f), Rng.FRandRange(1.f, 2.5f), h));
	}
	UE_LOG(LogTemp, Display, TEXT("TickCapture: spawned runtime test scene."));
}

void ATickCaptureManager::UpdateFollowCamera()
{
	if (!TrackedActor) return;
	const FVector Loc = TrackedActor->GetActorLocation();
	const float YawDeg = TrackedActor->GetActorRotation().Yaw;

	if (IsFPV())
	{
		// FPV: eye cam at the head socket / forward-up offset on the mesh (no smoothing).
		FVector EyeLoc;
		FRotator EyeRot;
		if (ADataFarmCharacter* DFC = Cast<ADataFarmCharacter>(TrackedActor))
		{
			DFC->GetEyeViewPoint(EyeLoc, EyeRot);
		}
		else
		{
			const FRotator YawRot(0.f, YawDeg, 0.f);
			EyeLoc = Loc + FVector(0, 0, 70) + YawRot.Vector() * 15.f;
			EyeRot = YawRot;
		}
		SceneCapture->SetWorldLocationAndRotation(EyeLoc, EyeRot);
		return;
	}

	// TPV: smooth-follow chase cam (ported from unrealzoo _chase_cam + the lerp loop).
	// Target sits TpvBack behind + TpvHeight above the agent along its yaw-forward.
	const float YawRad = FMath::DegreesToRadians(YawDeg);
	const FVector Fwd(FMath::Cos(YawRad), FMath::Sin(YawRad), 0.f);
	const FVector Tgt = Loc - Cfg.TpvBack * Fwd + FVector(0.f, 0.f, Cfg.TpvHeight);
	if (!bCamInit)
	{
		CamLoc = Tgt;        // first frame: snap (no lerp)
		CamYaw = YawRad;
		bCamInit = true;
	}
	else
	{
		CamLoc += Cfg.TpvSmooth * (Tgt - CamLoc);
		CamYaw += Cfg.TpvSmooth * FMath::UnwindRadians(YawRad - CamYaw);   // shortest-arc yaw lerp
	}
	const FRotator Rot(Cfg.TpvPitch, FMath::RadiansToDegrees(CamYaw), 0.f);
	SceneCapture->SetWorldLocationAndRotation(CamLoc, Rot);
}

void ATickCaptureManager::Finish()
{
	bDone = true;
	const FString Header = TEXT("index,t,rgb,player_x,player_y,player_z,player_qw,player_qx,player_qy,player_qz,")
		TEXT("cam_x,cam_y,cam_z,cam_qw,cam_qx,cam_qy,cam_qz,forward,back,left,right,jump,attack");
	FFileHelper::SaveStringToFile(Header + TEXT("\n") + FString::Join(Rows, TEXT("\n")) + TEXT("\n"),
		*(Cfg.OutDir / TEXT("steps.csv")));

	const FString Meta = FString::Printf(
		TEXT("{\n  \"episode_id\": \"%s\",\n  \"source\": \"ue\",\n  \"viewpoint\": \"%s\",\n")
		TEXT("  \"label_kind\": \"precise_action\",\n  \"fps\": %f,\n  \"resolution\": [%d, %d],\n")
		TEXT("  \"seed\": %d,\n  \"coord_frame\": \"ue_left_cm\",\n  \"schema_version\": 1,\n  \"num_steps\": %d\n}\n"),
		*Cfg.EpisodeId, *Cfg.Viewpoint, Cfg.Fps, Cfg.Width, Cfg.Height, Cfg.Seed, Rows.Num());
	FFileHelper::SaveStringToFile(Meta, *(Cfg.OutDir / TEXT("meta.json")));

	UE_LOG(LogTemp, Display, TEXT("TickCapture: wrote %d frames -> %s"), Rows.Num(), *Cfg.OutDir);
	FPlatformMisc::RequestExit(true);  // force: -game with a possessed pawn won't exit on a soft request
}
