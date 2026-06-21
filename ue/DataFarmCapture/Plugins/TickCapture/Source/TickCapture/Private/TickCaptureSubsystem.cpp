#include "TickCaptureSubsystem.h"

#include "TickCaptureManager.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"

bool UTickCaptureSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UTickCaptureSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	FString ConfigPath;
	if (!FParse::Value(FCommandLine::Get(), TEXT("CaptureConfig="), ConfigPath))
	{
		return;
	}
	FString Json;
	if (!FFileHelper::LoadFileToString(Json, *ConfigPath))
	{
		UE_LOG(LogTemp, Error, TEXT("TickCapture: cannot read config %s"), *ConfigPath);
		return;
	}
	TSharedPtr<FJsonObject> Obj;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
	if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
	{
		UE_LOG(LogTemp, Error, TEXT("TickCapture: bad JSON config %s"), *ConfigPath);
		return;
	}

	FCaptureConfig Cfg;
	Obj->TryGetStringField(TEXT("episode_id"), Cfg.EpisodeId);
	Obj->TryGetStringField(TEXT("out_dir"), Cfg.OutDir);
	Obj->TryGetStringField(TEXT("viewpoint"), Cfg.Viewpoint);
	int32 I;
	double D;
	if (Obj->TryGetNumberField(TEXT("width"), I)) Cfg.Width = I;
	if (Obj->TryGetNumberField(TEXT("height"), I)) Cfg.Height = I;
	if (Obj->TryGetNumberField(TEXT("num_frames"), I)) Cfg.NumFrames = I;
	if (Obj->TryGetNumberField(TEXT("warmup_frames"), I)) Cfg.WarmupFrames = I;
	if (Obj->TryGetNumberField(TEXT("seed"), I)) Cfg.Seed = I;
	if (Obj->TryGetNumberField(TEXT("fps"), D)) Cfg.Fps = static_cast<float>(D);
	Obj->TryGetBoolField(TEXT("orbit_test"), Cfg.bOrbitTest);

	if (Cfg.OutDir.IsEmpty())
	{
		UE_LOG(LogTemp, Error, TEXT("TickCapture: config missing out_dir"));
		return;
	}

	const FTransform T = FTransform::Identity;
	ATickCaptureManager* Mgr = InWorld.SpawnActorDeferred<ATickCaptureManager>(
		ATickCaptureManager::StaticClass(), T);
	if (!Mgr)
	{
		UE_LOG(LogTemp, Error, TEXT("TickCapture: failed to spawn manager"));
		return;
	}
	Mgr->Configure(Cfg);
	Mgr->FinishSpawning(T);
}
