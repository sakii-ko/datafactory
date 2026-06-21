using UnrealBuildTool;

public class DataFarmCaptureEditorTarget : TargetRules
{
	public DataFarmCaptureEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("DataFarmCapture");
	}
}
