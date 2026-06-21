using UnrealBuildTool;

public class DataFarmCapture : ModuleRules
{
	public DataFarmCapture(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "RenderCore", "RHI"
		});
	}
}
