"""
templates.py — Built-in Luau script templates for common Roblox patterns.

Each template is a dict with:
  name        short identifier used in /templates <name>
  title       display name
  type        Script | LocalScript | ModuleScript
  placement   recommended Roblox Explorer location
  tags        searchable keywords
  description one-line description
  code        ready-to-use Luau code
"""

from __future__ import annotations

# ─── Template definitions ─────────────────────────────────────────────────────

TEMPLATES: list[dict] = [
    # ── 1. Singleton service ──────────────────────────────────────────────────
    {
        "name": "singleton",
        "title": "Singleton Service",
        "type": "ModuleScript",
        "placement": "ReplicatedStorage/Modules",
        "tags": ["module", "singleton", "service", "pattern"],
        "description": "A ModuleScript that exposes a single instance — prevents duplicate setup.",
        "code": """\
-- SingletonService.luau
-- Usage: local Svc = require(path.to.SingletonService)
--        Svc:Init()   Svc:DoThing()

local SingletonService = {}
SingletonService.__index = SingletonService

local instance: typeof(SingletonService) | nil = nil

function SingletonService.getInstance()
\tif not instance then
\t\tinstance = setmetatable({}, SingletonService)
\t\tinstance:_init()
\tend
\treturn instance
end

function SingletonService:_init()
\t-- one-time setup here
\tself._initialized = true
\tprint("[SingletonService] Initialized")
end

function SingletonService:doSomething(value: string): string
\tassert(self._initialized, "Call getInstance() first")
\treturn "processed: " .. value
end

return SingletonService
""",
    },
    # ── 2. Signal / Observable ────────────────────────────────────────────────
    {
        "name": "signal",
        "title": "Custom Signal (Observable)",
        "type": "ModuleScript",
        "placement": "ReplicatedStorage/Modules",
        "tags": ["signal", "event", "observable", "bindable"],
        "description": "Lightweight signal implementation — no BindableEvents needed.",
        "code": """\
-- Signal.luau
-- local Signal = require(path.to.Signal)
-- local fired = Signal.new()
-- local conn = fired:Connect(function(x) print(x) end)
-- fired:Fire("hello")
-- conn:Disconnect()

export type Connection = {
\tDisconnect: (self: Connection) -> (),
\tConnected: boolean,
}

export type Signal<T...> = {
\tConnect: (self: Signal<T...>, fn: (T...) -> ()) -> Connection,
\tOnce:    (self: Signal<T...>, fn: (T...) -> ()) -> Connection,
\tFire:    (self: Signal<T...>, T...) -> (),
\tWait:    (self: Signal<T...>) -> T...,
\tDestroy: (self: Signal<T...>) -> (),
}

local Signal = {}
Signal.__index = Signal

function Signal.new<T...>(): Signal<T...>
\treturn setmetatable({ _listeners = {} }, Signal) :: any
end

function Signal:Connect(fn)
\tlocal conn = { Connected = true, _fn = fn }
\tconn.Disconnect = function(self)
\t\tself.Connected = false
\t\tself._fn = nil
\tend
\ttable.insert(self._listeners, conn)
\treturn conn
end

function Signal:Once(fn)
\tlocal conn
\tconn = self:Connect(function(...)
\t\tconn:Disconnect()
\t\tfn(...)
\tend)
\treturn conn
end

function Signal:Fire(...)
\tfor i = #self._listeners, 1, -1 do
\t\tlocal conn = self._listeners[i]
\t\tif conn.Connected then
\t\t\ttask.spawn(conn._fn, ...)
\t\telse
\t\t\ttable.remove(self._listeners, i)
\t\tend
\tend
end

function Signal:Wait()
\tlocal thread = coroutine.running()
\tself:Once(function(...)
\t\ttask.spawn(thread, ...)
\tend)
\treturn coroutine.yield()
end

function Signal:Destroy()
\ttable.clear(self._listeners)
end

return Signal
""",
    },
    # ── 3. State machine ──────────────────────────────────────────────────────
    {
        "name": "statemachine",
        "title": "Finite State Machine",
        "type": "ModuleScript",
        "placement": "ReplicatedStorage/Modules",
        "tags": ["state", "machine", "fsm", "round", "game loop"],
        "description": "Generic FSM with enter/exit/update callbacks and transition guards.",
        "code": """\
-- StateMachine.luau
-- local sm = require(StateMachine).new({
--   Lobby   = { onEnter = function() end, transitions = { "Game" } },
--   Game    = { onEnter = function() end, onExit = function() end },
--   Results = { onEnter = function() end, transitions = { "Lobby" } },
-- }, "Lobby")
-- sm:TransitionTo("Game")
-- sm:Update(dt)   -- call from RunService.Heartbeat

export type StateConfig = {
\tonEnter:      ((sm: StateMachine) -> ())?;
\tonExit:       ((sm: StateMachine) -> ())?;
\tonUpdate:     ((sm: StateMachine, dt: number) -> ())?;
\ttransitions:  { string }?;
}

export type StateMachine = {
\tTransitionTo: (self: StateMachine, state: string) -> boolean;
\tUpdate:       (self: StateMachine, dt: number) -> ();
\tCurrentState: string;
}

local StateMachine = {}
StateMachine.__index = StateMachine

function StateMachine.new(states: { [string]: StateConfig }, initial: string): StateMachine
\tassert(states[initial], "Initial state '" .. initial .. "' not found")
\tlocal self = setmetatable({
\t\t_states = states,
\t\tCurrentState = initial,
\t}, StateMachine)
\tlocal cfg = states[initial]
\tif cfg.onEnter then cfg.onEnter(self :: any) end
\treturn self :: any
end

function StateMachine:TransitionTo(target: string): boolean
\tlocal cfg = self._states[self.CurrentState]
\tif cfg.transitions then
\t\tlocal allowed = false
\t\tfor _, s in cfg.transitions do
\t\t\tif s == target then allowed = true break end
\t\tend
\t\tif not allowed then
\t\t\twarn("Transition " .. self.CurrentState .. " → " .. target .. " not allowed")
\t\t\treturn false
\t\tend
\tend
\tif cfg.onExit then cfg.onExit(self) end
\tself.CurrentState = target
\tlocal newCfg = self._states[target]
\tif newCfg and newCfg.onEnter then newCfg.onEnter(self) end
\treturn true
end

function StateMachine:Update(dt: number)
\tlocal cfg = self._states[self.CurrentState]
\tif cfg and cfg.onUpdate then cfg.onUpdate(self, dt) end
end

return StateMachine
""",
    },
    # ── 4. OOP class template ─────────────────────────────────────────────────
    {
        "name": "class",
        "title": "OOP Class Template",
        "type": "ModuleScript",
        "placement": "ReplicatedStorage/Modules",
        "tags": ["class", "oop", "object", "template"],
        "description": "Idiomatic Luau OOP pattern with constructor, methods, and cleanup.",
        "code": """\
-- MyClass.luau
-- Replace "MyClass" with your class name throughout.

export type MyClass = {
\t-- Public properties
\tName: string;
\t-- Public methods
\tDoThing: (self: MyClass, value: number) -> string;
\tDestroy:  (self: MyClass) -> ();
}

type MyClassPrivate = MyClass & {
\t_connections: { RBXScriptConnection };
\t_value: number;
}

local MyClass = {}
MyClass.__index = MyClass

-- Constructor
function MyClass.new(name: string): MyClass
\tlocal self: MyClassPrivate = setmetatable({
\t\tName = name,
\t\t_connections = {},
\t\t_value = 0,
\t}, MyClass) :: any
\treturn self :: any
end

-- Methods
function MyClass:DoThing(value: number): string
\tself._value += value
\treturn ("%s processed %d (total: %d)"):format(self.Name, value, self._value)
end

-- Cleanup — always implement Destroy to prevent memory leaks
function MyClass:Destroy()
\tfor _, conn in self._connections do
\t\tconn:Disconnect()
\tend
\ttable.clear(self._connections)
end

return MyClass
""",
    },
    # ── 5. Round system ───────────────────────────────────────────────────────
    {
        "name": "roundsystem",
        "title": "Round System",
        "type": "Script",
        "placement": "ServerScriptService",
        "tags": ["round", "game", "lobby", "intermission", "loop"],
        "description": "Complete server-side round loop: Lobby → Game → Intermission.",
        "code": """\
-- RoundSystem.server.luau
-- Place in ServerScriptService
-- Fires RemoteEvents in ReplicatedStorage.Events for UI updates.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

-- Configuration
local Config = {
\tLobbyTime = 30,
\tGameTime  = 180,
\tEndTime   = 15,
\tMinPlayers = 2,
}

-- Remote events (create these in ReplicatedStorage.Events)
local Events = ReplicatedStorage:WaitForChild("Events", 10)
local UpdateStatus = Events and Events:FindFirstChild("UpdateStatus")
local RoundStarted = Events and Events:FindFirstChild("RoundStarted")
local RoundEnded   = Events and Events:FindFirstChild("RoundEnded")

local State = "Lobby"
local activePlayers: { Player } = {}

local function broadcast(msg: string)
\tif UpdateStatus then
\t\tUpdateStatus:FireAllClients(msg)
\tend
end

local function countdown(seconds: number, label: string)
\tfor i = seconds, 1, -1 do
\t\tbroadcast(label .. ": " .. i .. "s")
\t\ttask.wait(1)
\tend
end

local function startRound()
\tState = "Game"
\tactivePlayers = Players:GetPlayers()
\tif RoundStarted then RoundStarted:FireAllClients() end
\tbroadcast("Game in progress!")
\t-- TODO: teleport players, enable mechanics, etc.
end

local function endRound()
\tState = "Intermission"
\t-- TODO: determine winner, show leaderboard
\tif RoundEnded then RoundEnded:FireAllClients() end
end

local function gameLoop()
\twhile true do
\t\t-- Lobby phase
\t\tState = "Lobby"
\t\tbroadcast("Waiting for players…")
\t\trepeat
\t\t\ttask.wait(1)
\t\tuntil #Players:GetPlayers() >= Config.MinPlayers

\t\tcountdown(Config.LobbyTime, "Game starts in")

\t\tif #Players:GetPlayers() < Config.MinPlayers then
\t\t\tbroadcast("Not enough players!")
\t\t\ttask.wait(5)
\t\t\tcontinue
\t\tend

\t\t-- Game phase
\t\tstartRound()
\t\tcountdown(Config.GameTime, "Time remaining")
\t\tendRound()

\t\t-- Intermission
\t\tcountdown(Config.EndTime, "Next round in")
\tend
end

-- Handle players leaving mid-round
Players.PlayerRemoving:Connect(function(player)
\tlocal idx = table.find(activePlayers, player)
\tif idx then table.remove(activePlayers, idx) end
\tif State == "Game" and #activePlayers < 1 then
\t\tbroadcast("All players left — ending round")
\t\tendRound()
\tend
end)

task.spawn(gameLoop)
""",
    },
    # ── 6. DataStore Manager ──────────────────────────────────────────────────
    {
        "name": "datastore",
        "title": "DataStore Manager",
        "type": "ModuleScript",
        "placement": "ServerScriptService",
        "tags": ["datastore", "data", "save", "load", "player"],
        "description": "Typed player data manager with auto-save and session locking.",
        "code": """\
-- DataManager.luau
-- Place in ServerScriptService and require from a server Script.

local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

-- ── Config ────────────────────────────────────────────────────────────────
local STORE_NAME = "PlayerData_v1"
local AUTO_SAVE_INTERVAL = 60  -- seconds
local MAX_RETRIES = 3

export type PlayerData = {
\tCoins: number;
\tLevel: number;
\tXP: number;
\tInventory: { string };
}

local DEFAULT_DATA: PlayerData = {
\tCoins = 0,
\tLevel = 1,
\tXP = 0,
\tInventory = {},
}

-- ── Module ────────────────────────────────────────────────────────────────
local DataManager = {}
local store = DataStoreService:GetDataStore(STORE_NAME)
local cache: { [number]: PlayerData } = {}  -- userId → data
local sessionLocks: { [number]: boolean } = {}

local function deepCopy<T>(t: T): T
\tif type(t) ~= "table" then return t end
\tlocal copy = {}
\tfor k, v in t :: any do
\t\tcopy[k] = deepCopy(v)
\tend
\treturn copy :: any
end

local function loadData(userId: number): PlayerData
\tfor attempt = 1, MAX_RETRIES do
\t\tlocal ok, result = pcall(function()
\t\t\treturn store:GetAsync(tostring(userId))
\t\tend)
\t\tif ok then
\t\t\tif result then
\t\t\t\t-- Merge with defaults to handle new fields after updates
\t\t\t\tfor k, v in DEFAULT_DATA do
\t\t\t\t\tif result[k] == nil then result[k] = v end
\t\t\t\tend
\t\t\t\treturn result
\t\t\tend
\t\t\treturn deepCopy(DEFAULT_DATA)
\t\tend
\t\twarn("[DataManager] Load attempt", attempt, "failed:", result)
\t\ttask.wait(2 ^ attempt)
\tend
\treturn deepCopy(DEFAULT_DATA)
end

local function saveData(userId: number, data: PlayerData)
\tfor attempt = 1, MAX_RETRIES do
\t\tlocal ok, err = pcall(function()
\t\t\tstore:SetAsync(tostring(userId), data)
\t\tend)
\t\tif ok then return end
\t\twarn("[DataManager] Save attempt", attempt, "failed:", err)
\t\ttask.wait(2 ^ attempt)
\tend
end

-- ── Public API ────────────────────────────────────────────────────────────
function DataManager.get(player: Player): PlayerData
\treturn cache[player.UserId]
end

function DataManager.save(player: Player)
\tlocal data = cache[player.UserId]
\tif data then saveData(player.UserId, data) end
end

-- ── Lifecycle hooks ───────────────────────────────────────────────────────
Players.PlayerAdded:Connect(function(player)
\tsessionLocks[player.UserId] = true
\tlocal data = loadData(player.UserId)
\tcache[player.UserId] = data
\tprint("[DataManager]", player.Name, "data loaded")
end)

Players.PlayerRemoving:Connect(function(player)
\tDataManager.save(player)
\tcache[player.UserId] = nil
\tsessionLocks[player.UserId] = nil
\tprint("[DataManager]", player.Name, "data saved")
end)

-- Auto-save loop
task.spawn(function()
\twhile true do
\t\ttask.wait(AUTO_SAVE_INTERVAL)
\t\tfor _, player in Players:GetPlayers() do
\t\t\tDataManager.save(player)
\t\tend
\tend
end)

-- Save on server close
game:BindToClose(function()
\tfor _, player in Players:GetPlayers() do
\t\tDataManager.save(player)
\tend
end)

return DataManager
""",
    },
    # ── 7. Network Bridge (RemoteEvent wrapper) ───────────────────────────────
    {
        "name": "netbridge",
        "title": "Network Bridge",
        "type": "ModuleScript",
        "placement": "ReplicatedStorage/Modules",
        "tags": ["remote", "event", "network", "client", "server"],
        "description": "Typed wrapper around RemoteEvents with rate limiting and validation.",
        "code": """\
-- NetworkBridge.luau
-- Place in ReplicatedStorage/Modules — works on both server and client.
-- Server: Bridge.onServer("BuyItem", handler)
-- Client: Bridge.fireServer("BuyItem", itemId)

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local IS_SERVER = RunService:IsServer()

-- Folder to store RemoteEvents
local function getEventsFolder(): Folder
\tif IS_SERVER then
\t\tlocal folder = ReplicatedStorage:FindFirstChild("BridgeEvents")
\t\tif not folder then
\t\t\tfolder = Instance.new("Folder")
\t\t\tfolder.Name = "BridgeEvents"
\t\t\tfolder.Parent = ReplicatedStorage
\t\tend
\t\treturn folder :: Folder
\tend
\treturn ReplicatedStorage:WaitForChild("BridgeEvents", 10) :: Folder
end

local function getOrCreateRemote(name: string): RemoteEvent
\tlocal folder = getEventsFolder()
\tif IS_SERVER then
\t\tlocal existing = folder:FindFirstChild(name)
\t\tif existing then return existing :: RemoteEvent end
\t\tlocal re = Instance.new("RemoteEvent")
\t\tre.Name = name
\t\tre.Parent = folder
\t\treturn re
\tend
\treturn folder:WaitForChild(name, 10) :: RemoteEvent
end

-- Rate limiting (server-side)
local rateLimits: { [Player]: { [string]: number } } = {}
local RATE_LIMIT = 10  -- max fires per second per event per player

local function checkRateLimit(player: Player, eventName: string): boolean
\tif not IS_SERVER then return true end
\trateLimits[player] = rateLimits[player] or {}
\tlocal now = tick()
\tlocal last = rateLimits[player][eventName] or 0
\tif now - last < (1 / RATE_LIMIT) then
\t\twarn("[NetworkBridge] Rate limit hit:", player.Name, eventName)
\t\treturn false
\tend
\trateLimits[player][eventName] = now
\treturn true
end

-- Cleanup rate limit data when player leaves
if IS_SERVER then
\tgame:GetService("Players").PlayerRemoving:Connect(function(player)
\t\trateLimits[player] = nil
\tend)
end

-- ── Public API ────────────────────────────────────────────────────────────
local Bridge = {}

-- SERVER: listen for client → server events
function Bridge.onServer(eventName: string, handler: (player: Player, ...any) -> ())
\tassert(IS_SERVER, "onServer must be called on the server")
\tgetOrCreateRemote(eventName).OnServerEvent:Connect(function(player, ...)
\t\tif checkRateLimit(player, eventName) then
\t\t\thandler(player, ...)
\t\tend
\tend)
end

-- SERVER: fire to one client
function Bridge.fireClient(eventName: string, player: Player, ...: any)
\tassert(IS_SERVER, "fireClient must be called on the server")
\tgetOrCreateRemote(eventName):FireClient(player, ...)
end

-- SERVER: fire to all clients
function Bridge.fireAll(eventName: string, ...: any)
\tassert(IS_SERVER, "fireAll must be called on the server")
\tgetOrCreateRemote(eventName):FireAllClients(...)
end

-- CLIENT: fire to server
function Bridge.fireServer(eventName: string, ...: any)
\tassert(not IS_SERVER, "fireServer must be called on the client")
\tgetOrCreateRemote(eventName):FireServer(...)
end

-- CLIENT: listen for server → client events
function Bridge.onClient(eventName: string, handler: (...any) -> ())
\tassert(not IS_SERVER, "onClient must be called on the client")
\tgetOrCreateRemote(eventName).OnClientEvent:Connect(handler)
end

return Bridge
""",
    },
    # ── 8. Promise ────────────────────────────────────────────────────────────
    {
        "name": "promise",
        "title": "Promise (Async Utility)",
        "type": "ModuleScript",
        "placement": "ReplicatedStorage/Modules",
        "tags": ["promise", "async", "await", "coroutine"],
        "description": "Minimal Promise implementation for chaining async Roblox operations.",
        "code": """\
-- Promise.luau
-- Usage:
--   local Promise = require(path.to.Promise)
--   Promise.new(function(resolve, reject)
--     task.wait(2)
--     resolve("done")
--   end):andThen(function(val) print(val) end)
--     :catch(function(err) warn(err) end)

type PromiseState = "pending" | "resolved" | "rejected"

export type Promise<T> = {
\tandThen:  (self: Promise<T>, fn: (T) -> any) -> Promise<any>;
\tcatch:    (self: Promise<T>, fn: (any) -> any) -> Promise<T>;
\tfinally:  (self: Promise<T>, fn: () -> ()) -> Promise<T>;
\tawait:    (self: Promise<T>) -> (boolean, T | any);
}

local Promise = {}
Promise.__index = Promise

function Promise.new<T>(executor: (resolve: (T) -> (), reject: (any) -> ()) -> ()): Promise<T>
\tlocal self = setmetatable({
\t\t_state = "pending" :: PromiseState,
\t\t_value = nil,
\t\t_callbacks = {},
\t}, Promise)

\tlocal function resolve(value)
\t\tif self._state ~= "pending" then return end
\t\tself._state = "resolved"
\t\tself._value = value
\t\tfor _, cb in self._callbacks do
\t\t\tif cb.type == "then" then task.spawn(cb.fn, value) end
\t\tend
\tend

\tlocal function reject(reason)
\t\tif self._state ~= "pending" then return end
\t\tself._state = "rejected"
\t\tself._value = reason
\t\tlocal handled = false
\t\tfor _, cb in self._callbacks do
\t\t\tif cb.type == "catch" then
\t\t\t\thandled = true
\t\t\t\ttask.spawn(cb.fn, reason)
\t\t\tend
\t\tend
\t\tif not handled then
\t\t\twarn("[Promise] Unhandled rejection:", reason)
\t\tend
\tend

\ttask.spawn(executor, resolve, reject)
\treturn self :: any
end

function Promise:andThen(fn)
\treturn Promise.new(function(resolve, reject)
\t\tlocal function handle()
\t\t\tif self._state == "resolved" then
\t\t\t\tlocal ok, result = pcall(fn, self._value)
\t\t\t\tif ok then resolve(result) else reject(result) end
\t\t\telseif self._state == "rejected" then
\t\t\t\treject(self._value)
\t\t\tend
\t\tend
\t\tif self._state ~= "pending" then
\t\t\ttask.spawn(handle)
\t\telse
\t\t\ttable.insert(self._callbacks, { type = "then", fn = handle })
\t\tend
\tend)
end

function Promise:catch(fn)
\treturn Promise.new(function(resolve, reject)
\t\ttable.insert(self._callbacks, {
\t\t\ttype = "catch",
\t\t\tfn = function(reason)
\t\t\t\tlocal ok, result = pcall(fn, reason)
\t\t\t\tif ok then resolve(result) else reject(result) end
\t\t\tend,
\t\t})
\t\tif self._state == "rejected" then
\t\t\tfor _, cb in self._callbacks do
\t\t\t\tif cb.type == "catch" then task.spawn(cb.fn, self._value) end
\t\t\tend
\t\tend
\tend)
end

function Promise:finally(fn)
\treturn self:andThen(function(v)
\t\tfn()
\t\treturn v
\tend):catch(function(e)
\t\tfn()
\t\terror(e)
\tend)
end

function Promise:await()
\tlocal thread = coroutine.running()
\tself:andThen(function(v) task.spawn(thread, true, v) end)
\t    :catch(function(e) task.spawn(thread, false, e) end)
\treturn coroutine.yield()
end

-- Utility constructors
function Promise.resolve<T>(value: T): Promise<T>
\treturn Promise.new(function(resolve) resolve(value) end)
end

function Promise.reject(reason: any): Promise<never>
\treturn Promise.new(function(_, reject) reject(reason) end)
end

function Promise.all(promises: { Promise<any> }): Promise<{ any }>
\treturn Promise.new(function(resolve, reject)
\t\tlocal results = table.create(#promises)
\t\tlocal done = 0
\t\tfor i, p in promises do
\t\t\tp:andThen(function(v)
\t\t\t\tresults[i] = v
\t\t\t\tdone += 1
\t\t\t\tif done == #promises then resolve(results) end
\t\t\tend):catch(reject)
\t\tend
\tend)
end

return Promise
""",
    },
]

# ─── Public helpers ───────────────────────────────────────────────────────────


def get_template(name: str) -> dict | None:
    """Look up a template by name (case-insensitive)."""
    name = name.strip().lower()
    for t in TEMPLATES:
        if t["name"] == name:
            return t
    return None


def search_templates(query: str) -> list[dict]:
    """Return templates whose name, title, tags, or description match query."""
    q = query.strip().lower()
    results: list[dict] = []
    for t in TEMPLATES:
        searchable = " ".join(
            [t["name"], t["title"], t["description"], " ".join(t["tags"])]
        ).lower()
        if q in searchable:
            results.append(t)
    return results


def list_templates() -> list[dict]:
    return TEMPLATES
