--[[
  RobloxAIDevTool.lua — Roblox Studio Plugin

  Installation:
    1. Open Roblox Studio → Plugins → Plugin Manager
    2. Click "Install from File" and select this .lua file
       (or paste contents into the Plugin Builder)
    3. Set your API key and model via the Settings panel

  Features:
    • AI Chat panel docked in Studio
    • Right-click any Script → "Review with AI"
    • Generate scripts via the toolbar button
    • Auto-insert generated code into the correct service

  Configuration:
    Edit CONFIG below or use the Settings widget.

  Note:
    This plugin calls an AI backend. Requires HttpService enabled
    in Studio and an API endpoint. Run `roblox-dev-tool --serve`
    from the CLI to start a local HTTP bridge, or configure a
    cloud-hosted endpoint.
--]]

-- ── Configuration ─────────────────────────────────────────────────────────────
local CONFIG = {
	-- Local bridge started by `roblox-dev-tool --serve`
	BackendURL   = "http://localhost:8765",
	ApiKey       = "",   -- paste your API key OR leave empty if backend handles auth
	Model        = "claude-opus-4-6",  -- or "openai:gpt-4o", "ollama:llama3", etc.
	Timeout      = 30,
}

-- ── Services ──────────────────────────────────────────────────────────────────
local HttpService       = game:GetService("HttpService")
local Selection         = game:GetService("Selection")
local StudioService     = game:GetService("StudioService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")

local plugin: Plugin = plugin  -- injected by Studio

-- ── Toolbar ───────────────────────────────────────────────────────────────────
local toolbar    = plugin:CreateToolbar("Roblox AI Dev Tool")
local chatBtn    = toolbar:CreateButton("AI Chat",    "Open AI chat panel",    "rbxassetid://0")
local generateBtn= toolbar:CreateButton("Generate",  "Generate a script",     "rbxassetid://0")
local reviewBtn  = toolbar:CreateButton("Review",    "Review selected script", "rbxassetid://0")

-- ── UI widget (DockWidget) ────────────────────────────────────────────────────
local widgetInfo = DockWidgetPluginGuiInfo.new(
	Enum.InitialDockState.Right, -- dock to the right
	true,   -- initially visible
	false,  -- don't override saved state
	400,    -- default width
	600,    -- default height
	300,    -- min width
	200     -- min height
)

local widget: DockWidgetPluginGui = plugin:CreateDockWidgetPluginGui(
	"RobloxAIDevTool", widgetInfo
)
widget.Title = "Roblox AI Dev Tool"
widget.ZIndexBehavior = Enum.ZIndexBehavior.Sibling

-- ── Build the UI ──────────────────────────────────────────────────────────────
local bg = Instance.new("Frame")
bg.Size         = UDim2.new(1, 0, 1, 0)
bg.BackgroundColor3 = Color3.fromRGB(30, 30, 30)
bg.BorderSizePixel = 0
bg.Parent       = widget

-- Header
local header = Instance.new("Frame")
header.Size   = UDim2.new(1, 0, 0, 40)
header.BackgroundColor3 = Color3.fromRGB(14, 99, 156)
header.BorderSizePixel = 0
header.Parent = bg

local headerLabel = Instance.new("TextLabel")
headerLabel.Size  = UDim2.new(1, -8, 1, 0)
headerLabel.Position = UDim2.new(0, 8, 0, 0)
headerLabel.BackgroundTransparency = 1
headerLabel.Text  = "🤖 Roblox AI Dev Tool  |  " .. CONFIG.Model
headerLabel.TextColor3 = Color3.new(1,1,1)
headerLabel.TextXAlignment = Enum.TextXAlignment.Left
headerLabel.Font  = Enum.Font.GothamBold
headerLabel.TextSize = 13
headerLabel.Parent = header

-- Chat history (ScrollingFrame)
local scroll = Instance.new("ScrollingFrame")
scroll.Size   = UDim2.new(1, 0, 1, -90)
scroll.Position = UDim2.new(0, 0, 0, 40)
scroll.BackgroundColor3 = Color3.fromRGB(30, 30, 30)
scroll.BorderSizePixel = 0
scroll.ScrollBarThickness = 6
scroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroll.CanvasSize = UDim2.new(0, 0, 0, 0)
scroll.Parent = bg

local layout = Instance.new("UIListLayout")
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Padding   = UDim.new(0, 4)
layout.Parent    = scroll

local padding = Instance.new("UIPadding")
padding.PaddingAll = UDim.new(0, 6)
padding.Parent = scroll

-- Input area
local inputFrame = Instance.new("Frame")
inputFrame.Size  = UDim2.new(1, 0, 0, 50)
inputFrame.Position = UDim2.new(0, 0, 1, -50)
inputFrame.BackgroundColor3 = Color3.fromRGB(37, 37, 38)
inputFrame.BorderSizePixel = 0
inputFrame.Parent = bg

local inputBox = Instance.new("TextBox")
inputBox.Size      = UDim2.new(1, -72, 1, -8)
inputBox.Position  = UDim2.new(0, 4, 0, 4)
inputBox.BackgroundColor3 = Color3.fromRGB(60, 60, 60)
inputBox.TextColor3 = Color3.new(1,1,1)
inputBox.PlaceholderText = "Ask anything about Roblox scripting…"
inputBox.PlaceholderColor3 = Color3.fromRGB(130,130,130)
inputBox.Text       = ""
inputBox.Font       = Enum.Font.Gotham
inputBox.TextSize   = 12
inputBox.TextXAlignment = Enum.TextXAlignment.Left
inputBox.ClearTextOnFocus = false
inputBox.MultiLine  = false
inputBox.BorderSizePixel = 0
inputBox.Parent    = inputFrame

local sendButton = Instance.new("TextButton")
sendButton.Size    = UDim2.new(0, 62, 1, -8)
sendButton.Position = UDim2.new(1, -66, 0, 4)
sendButton.BackgroundColor3 = Color3.fromRGB(14, 99, 156)
sendButton.TextColor3 = Color3.new(1,1,1)
sendButton.Text    = "Send"
sendButton.Font    = Enum.Font.GothamBold
sendButton.TextSize = 13
sendButton.BorderSizePixel = 0
sendButton.Parent  = inputFrame

-- ── Message helpers ───────────────────────────────────────────────────────────
local msgCount = 0

local function addMessage(role: string, text: string)
	msgCount += 1
	local isUser = (role == "user")

	local frame = Instance.new("Frame")
	frame.Size  = UDim2.new(1, 0, 0, 0)
	frame.AutomaticSize = Enum.AutomaticSize.Y
	frame.BackgroundColor3 = isUser
		and Color3.fromRGB(38, 79, 120)
		or  Color3.fromRGB(45, 45, 45)
	frame.BorderSizePixel = 0
	frame.LayoutOrder = msgCount
	frame.Parent = scroll

	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, 4)
	corner.Parent = frame

	local pad = Instance.new("UIPadding")
	pad.PaddingAll = UDim.new(0, 6)
	pad.Parent = frame

	local label = Instance.new("TextLabel")
	label.Size  = UDim2.new(1, 0, 0, 0)
	label.AutomaticSize = Enum.AutomaticSize.Y
	label.BackgroundTransparency = 1
	label.TextColor3 = Color3.new(1,1,1)
	label.Text  = text
	label.Font  = Enum.Font.Gotham
	label.TextSize = 12
	label.TextXAlignment = Enum.TextXAlignment.Left
	label.TextWrapped = true
	label.RichText = false
	label.Parent = frame

	-- Auto-scroll to bottom
	task.defer(function()
		scroll.CanvasPosition = Vector2.new(0, scroll.AbsoluteCanvasSize.Y)
	end)
end

-- ── HTTP backend call ─────────────────────────────────────────────────────────
local function callBackend(method: string, params: { [string]: any }): (boolean, any)
	local payload = HttpService:JSONEncode({
		jsonrpc = "2.0",
		id = 1,
		method = method,
		params = params,
	})

	local success, response = pcall(function()
		return HttpService:PostAsync(
			CONFIG.BackendURL .. "/rpc",
			payload,
			Enum.HttpContentType.ApplicationJson,
			false,
			{ ["X-API-Key"] = CONFIG.ApiKey }
		)
	end)

	if not success then
		return false, "HTTP error: " .. tostring(response)
	end

	local ok, data = pcall(HttpService.JSONDecode, HttpService, response)
	if not ok then
		return false, "JSON parse error: " .. tostring(data)
	end

	if data.error then
		return false, data.error
	end
	return true, data.result
end

-- ── Send a chat message ────────────────────────────────────────────────────────
local function sendMessage()
	local text = inputBox.Text:match("^%s*(.-)%s*$")
	if text == "" then return end
	inputBox.Text = ""

	addMessage("user", text)
	addMessage("assistant", "⏳ Thinking…")

	task.spawn(function()
		local ok, result = callBackend("chat", { message = text, model = CONFIG.Model })
		-- Replace the last assistant message
		local children = scroll:GetChildren()
		for i = #children, 1, -1 do
			local child = children[i]
			if child:IsA("Frame") and child.LayoutOrder == msgCount then
				local lbl = child:FindFirstChildOfClass("TextLabel")
				if lbl then
					lbl.Text = ok and (result.response or "No response") or ("⚠ " .. tostring(result))
				end
				break
			end
		end
	end)
end

-- ── Insert generated code into Studio ─────────────────────────────────────────
local function insertScript(scriptType: string, code: string, placement: string)
	ChangeHistoryService:SetWaypoint("Before AI Insert")

	local serviceMap = {
		Script            = game:GetService("ServerScriptService"),
		LocalScript       = game:GetService("StarterPlayer").StarterPlayerScripts,
		ModuleScript      = game:GetService("ReplicatedStorage"),
	}

	local parent = serviceMap[scriptType] or game:GetService("ReplicatedStorage")

	local inst
	if scriptType == "Script" then
		inst = Instance.new("Script")
	elseif scriptType == "LocalScript" then
		inst = Instance.new("LocalScript")
	else
		inst = Instance.new("ModuleScript")
	end

	inst.Source = code
	inst.Name   = "AIGenerated"
	inst.Parent = parent

	ChangeHistoryService:SetWaypoint("After AI Insert")
	Selection:Set({ inst })
	addMessage("assistant", "✔ Inserted " .. scriptType .. " into " .. parent.Name)
end

-- ── Review selected script ─────────────────────────────────────────────────────
local function reviewSelected()
	local selected = Selection:Get()
	if #selected == 0 then
		addMessage("assistant", "⚠ Select a Script, LocalScript, or ModuleScript first.")
		return
	end
	local inst = selected[1]
	if not inst:IsA("LuaSourceContainer") then
		addMessage("assistant", "⚠ Selected instance is not a script.")
		return
	end

	local code = inst.Source
	addMessage("user", "Review: " .. inst.Name)
	addMessage("assistant", "⏳ Reviewing " .. inst.Name .. "…")

	task.spawn(function()
		local ok, result = callBackend("review", { code = code, fileName = inst.Name .. ".luau" })
		local children = scroll:GetChildren()
		for i = #children, 1, -1 do
			local child = children[i]
			if child:IsA("Frame") and child.LayoutOrder == msgCount then
				local lbl = child:FindFirstChildOfClass("TextLabel")
				if lbl then
					lbl.Text = ok and (result.review or "Looks good!") or ("⚠ " .. tostring(result))
				end
				break
			end
		end
	end)
end

-- ── Wire up events ─────────────────────────────────────────────────────────────
sendButton.MouseButton1Click:Connect(sendMessage)
inputBox.FocusLost:Connect(function(enterPressed)
	if enterPressed then sendMessage() end
end)

chatBtn.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

reviewBtn.Click:Connect(reviewSelected)

generateBtn.Click:Connect(function()
	-- Ask via a simple prompt message
	addMessage("assistant", "What should I generate? Type your request in the chat box.")
	widget.Enabled = true
end)

-- ── Startup message ────────────────────────────────────────────────────────────
addMessage("assistant",
	"👋 Roblox AI Dev Tool ready!\n\n" ..
	"Model: " .. CONFIG.Model .. "\n" ..
	"Backend: " .. CONFIG.BackendURL .. "\n\n" ..
	"Commands:\n" ..
	"• Ask anything about Roblox scripting\n" ..
	"• Select a Script + click Review in toolbar\n" ..
	"• Click Generate to scaffold a new script\n\n" ..
	"⚠ Requires: roblox-dev-tool --serve running locally"
)

print("[RobloxAIDevTool] Plugin loaded successfully")
