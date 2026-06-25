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
	Obj->TryGetBoolField(TEXT("agent_mode"), Cfg.bAgentMode);
	if (Obj->TryGetNumberField(TEXT("agent_bounds"), D)) Cfg.AgentBounds = static_cast<float>(D);
	// optional TPV chase-cam overrides (else the defaults: back 350 / height 180 / pitch -12)
	if (Obj->TryGetNumberField(TEXT("tpv_back"), D)) Cfg.TpvBack = static_cast<float>(D);
	if (Obj->TryGetNumberField(TEXT("tpv_height"), D)) Cfg.TpvHeight = static_cast<float>(D);
	if (Obj->TryGetNumberField(TEXT("tpv_pitch"), D)) Cfg.TpvPitch = static_cast<float>(D);
	if (Obj->TryGetNumberField(TEXT("tpv_smooth"), D)) Cfg.TpvSmooth = static_cast<float>(D);

	// optional own-content character: {id, mesh, anim_bp, wardrobe: {slot: path, ...}}
	const TSharedPtr<FJsonObject>* CharObj = nullptr;
	if (Obj->TryGetObjectField(TEXT("character"), CharObj) && CharObj && CharObj->IsValid())
	{
		(*CharObj)->TryGetStringField(TEXT("id"), Cfg.Character.Id);
		(*CharObj)->TryGetStringField(TEXT("mesh"), Cfg.Character.Mesh);
		(*CharObj)->TryGetStringField(TEXT("anim_bp"), Cfg.Character.AnimBp);
		(*CharObj)->TryGetStringField(TEXT("anim"), Cfg.Character.Anim);   // single-sequence fallback
		const TSharedPtr<FJsonObject>* Ward = nullptr;
		if ((*CharObj)->TryGetObjectField(TEXT("wardrobe"), Ward) && Ward && Ward->IsValid())
		{
			for (const auto& Pair : (*Ward)->Values)   // slot -> mesh path
			{
				FString PartPath;
				if (Pair.Value.IsValid() && Pair.Value->TryGetString(PartPath) && !PartPath.IsEmpty())
				{
					Cfg.Character.Wardrobe.Add(PartPath);
				}
			}
		}
		Cfg.bAgentMode = true;   // a character implies the walking-agent path
	}

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
