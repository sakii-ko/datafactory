-- overrides.lua — Black Myth: Wukong adapter for the generic datafarm_agent.
-- Game-specific class names + HUD lever + terrain line-trace. Everything here is [VALIDATE]:
-- it must be confirmed against the running game's object graph (FindFirstOf/FindAllOf dumps).
--
-- Episode-specific params (log_path, num_frames, fps, seed, resolution) are written by the launcher
-- into gi_runtime.lua; we merge them over the static [roam] defaults below.

local rt = (pcall(require, "gi_runtime")) and require("gi_runtime") or {}

local M = {
  game              = "blackmyth",
  player_controller = "PlayerController",            -- [VALIDATE] BMW may subclass
  tick_function     = "/Script/Engine.Actor:ReceiveTick",
  hud_command       = "showhud",
  config = {
    log_path    = rt.log_path   or "agent.jsonl",
    num_frames  = rt.num_frames or 900,
    fps         = rt.fps        or 30.0,
    seed        = rt.seed       or 1,
    speed       = 1.0,
    turn_jitter = 0.15,
    turn_step   = 0.6,
    probe_dist  = 250.0,
    boot_delay_ms = 8000,
  },
}

-- HUD off: showhud kills canvas AHUD; BMW UI is largely UMG, so also hide the root widget. [VALIDATE]
function M.hud_off(pc)
  -- TODO[VALIDATE]: dump UMG (FindAllOf("UserWidget")) on the live game, set the HUD widget's
  -- visibility to Hidden (ESlateVisibility::Hidden = 1). Placeholder until we can inspect it.
  local widgets = FindAllOf("UserWidget")
  if widgets then
    for _, w in ipairs(widgets) do
      if w:IsValid() then pcall(function() w:SetVisibility(1) end) end
    end
  end
end

-- Terrain probe: trace forward from loc along (fx,fy); return (blocked, edge).
-- blocked = wall ahead within probe_dist; edge = no ground ahead (drop-off). [VALIDATE]
function M.line_trace(loc, fx, fy, dist)
  local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
  if not (ksl and ksl:IsValid()) then return false, false end
  local ahead = { X = loc.X + fx * dist, Y = loc.Y + fy * dist, Z = loc.Z }
  -- wall check: horizontal trace loc -> ahead
  local blocked = false
  pcall(function()
    local hit = {}
    blocked = ksl:LineTraceSingle(nil, loc, ahead, 0, false, {}, 0, hit, true, {}, {}, 1.0)
  end)
  -- edge check: trace down from `ahead`; if nothing within a step height, it's a drop-off
  local edge = false
  pcall(function()
    local down = { X = ahead.X, Y = ahead.Y, Z = ahead.Z - 300.0 }
    local hit = {}
    local ground = ksl:LineTraceSingle(nil, ahead, down, 0, false, {}, 0, hit, true, {}, {}, 1.0)
    edge = not ground
  end)
  return blocked, edge
end

return M
