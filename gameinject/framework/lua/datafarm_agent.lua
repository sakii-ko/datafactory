-- datafarm_agent.lua — GENERIC UE4SS Lua agent for the gameinject track.
-- Reused across every UE4/UE5 game; game-specific names live in games/<game>/lua/overrides.lua.
--
-- Responsibilities (per the gameinject design):
--   1. resolve PlayerController / Pawn / PlayerCameraManager from the live UObject graph
--   2. turn the HUD off
--   3. each frame: generate a 6-dim action (free-roam, terrain-aware via line traces),
--      apply it (AddMovementInput), and LOG (frame_id, t, action6, cam 6-DoF, pawn pose) as JSONL
--      -> the capture layer matches its RGB/depth frames to this log by frame_id.
--
-- The action is KNOWN-FOR-FREE because WE author it (Matrix-Game / GameNGen "drive-then-log").
-- !! Parts marked [VALIDATE] use UE4SS reflection that must be confirmed against a running game;
--    they are best-effort skeletons until we have a game to test on. Keep this file generic.

local OV = require("overrides")   -- games/<game>/lua/overrides.lua (class names, HUD lever, tick hook)
local cfg = OV.config or {}
local out = io.open(cfg.log_path or "datafarm_agent.jsonl", "w")

local frame = 0
local heading = 0.0                       -- current yaw heading (radians), evolves for free-roam
local rng = { s = cfg.seed or 1 }
local function rand() rng.s = (rng.s * 1103515245 + 12345) % 2147483648; return rng.s / 2147483648 end

-- ---- resolve actors -------------------------------------------------------
local PC, Pawn, Cam
local function resolve()
  PC   = FindFirstOf(OV.player_controller or "PlayerController")
  if PC and PC:IsValid() then
    Pawn = PC.Pawn
    Cam  = PC.PlayerCameraManager
  end
  return PC and Pawn and Cam and Pawn:IsValid() and Cam:IsValid()
end

-- ---- HUD off --------------------------------------------------------------
local function hud_off()
  if PC and PC:IsValid() then
    PC:ConsoleCommand(OV.hud_command or "showhud", false)   -- kills canvas AHUD
  end
  if OV.hud_off then OV.hud_off(PC) end                      -- per-game UMG widget hide [VALIDATE]
end

-- ---- terrain-aware free-roam action --------------------------------------
-- Returns a unit world-direction + a 6-dim action [fwd,back,left,right, turnL,turnR].
-- Uses a forward line-trace (overrides.line_trace) to detect walls/edges and steer.
local function roam_action(loc)
  -- evolve heading: mild random walk + bias to keep moving forward
  heading = heading + (rand() - 0.5) * (cfg.turn_jitter or 0.15)
  local fx, fy = math.cos(heading), math.sin(heading)
  local act = { 1, 0, 0, 0, 0, 0 }   -- default: walk forward
  -- terrain probe: is there ground ahead and no wall? [VALIDATE — needs a real LineTrace]
  if OV.line_trace then
    local blocked, edge = OV.line_trace(loc, fx, fy, cfg.probe_dist or 250.0)
    if blocked or edge then           -- wall ahead or drop-off -> turn instead of walking into it
      local dir = (rand() < 0.5) and 1 or -1
      heading = heading + dir * (cfg.turn_step or 0.6)
      act = { 0, 0, 0, 0, dir > 0 and 1 or 0, dir < 0 and 1 or 0 }
      fx, fy = math.cos(heading), math.sin(heading)
    end
  end
  return fx, fy, act
end

-- ---- per-frame tick -------------------------------------------------------
local function on_tick()
  if not (Pawn and Pawn:IsValid()) then if not resolve() then return end end
  local ploc = Pawn:K2_GetActorLocation()
  local fx, fy, act = roam_action(ploc)
  -- apply movement (Mode B: synthetic input; nav-free, terrain-aware)
  Pawn:AddMovementInput({ X = fx, Y = fy, Z = 0.0 }, cfg.speed or 1.0, false)   -- [VALIDATE]
  -- read camera 6-DoF + pawn pose
  local cloc = Cam:GetCameraLocation()
  local crot = Cam:GetCameraRotation()
  local prot = Pawn:K2_GetActorRotation()
  -- log one JSONL row; capture layer aligns RGB/depth by frame_id
  out:write(string.format(
    '{"frame":%d,"t":%.4f,"action":[%d,%d,%d,%d,%d,%d],' ..
    '"cam_loc":[%.2f,%.2f,%.2f],"cam_rot":[%.3f,%.3f,%.3f],' ..
    '"player_loc":[%.2f,%.2f,%.2f],"player_rot":[%.3f,%.3f,%.3f]}\n',
    frame, frame / (cfg.fps or 30.0),
    act[1], act[2], act[3], act[4], act[5], act[6],
    cloc.X, cloc.Y, cloc.Z, crot.Pitch, crot.Yaw, crot.Roll,
    ploc.X, ploc.Y, ploc.Z, prot.Pitch, prot.Yaw, prot.Roll))
  out:flush()
  frame = frame + 1
  if cfg.num_frames and frame >= cfg.num_frames then out:close() end
end

-- ---- boot -----------------------------------------------------------------
-- Hook the per-frame function the game actually ticks (set in overrides, e.g. a movement-component
-- or pawn ReceiveTick). RegisterHook fires our logger+driver every frame, tick-aligned. [VALIDATE]
ExecuteWithDelay(cfg.boot_delay_ms or 8000, function()   -- let the level/pawn load
  if resolve() then hud_off() end
  RegisterHook(OV.tick_function or "/Script/Engine.Actor:ReceiveTick", function() on_tick() end)
  print("[datafarm_agent] armed: " .. (OV.game or "unknown"))
end)
