using UnrealBuildTool;

public class TickCapture : ModuleRules
{
	public TickCapture(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"RHI", "RenderCore", "ImageWrapper", "Json", "Projects",
			"NavigationSystem", "AIModule"
		});
	}
}
