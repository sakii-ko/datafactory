using UnrealBuildTool;

public class DataFarmCaptureTarget : TargetRules
{
	public DataFarmCaptureTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("DataFarmCapture");
	}
}
