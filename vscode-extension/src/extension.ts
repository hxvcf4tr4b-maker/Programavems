/**
 * extension.ts — Roblox AI Dev Tool VS Code Extension
 *
 * Features:
 *  • Sidebar chat panel (webview)
 *  • Right-click "Review File" on .lua/.luau files
 *  • Command palette: Generate Script, Insert Template, Show Deps
 *  • Communicates with the Python backend via child_process (stdio JSON-RPC)
 */

import * as vscode from "vscode";
import * as cp from "child_process";
import * as path from "path";
import * as fs from "fs";

// ── JSON-RPC request ID counter ───────────────────────────────────────────────
let _reqId = 0;
function nextId(): number { return ++_reqId; }

// ── Backend process (singleton per workspace) ─────────────────────────────────
let _proc: cp.ChildProcess | null = null;
const _pending = new Map<number, { resolve: (v: any) => void; reject: (e: any) => void }>();

function getBackend(context: vscode.ExtensionContext): cp.ChildProcess {
  if (_proc && !_proc.killed) return _proc;

  const cfg = vscode.workspace.getConfiguration("robloxAI");
  const pythonPath: string = cfg.get("pythonPath") ?? "python";
  const scriptPath = path.join(context.extensionPath, "..", "server_mode.py");

  const env: NodeJS.ProcessEnv = { ...process.env };
  const anthropicKey: string = cfg.get("anthropicApiKey") ?? "";
  const openaiKey: string = cfg.get("openaiApiKey") ?? "";
  if (anthropicKey) env["ANTHROPIC_API_KEY"] = anthropicKey;
  if (openaiKey) env["OPENAI_API_KEY"] = openaiKey;

  _proc = cp.spawn(pythonPath, [scriptPath], { env, stdio: ["pipe", "pipe", "pipe"] });

  // Parse newline-delimited JSON responses
  let buf = "";
  _proc.stdout?.on("data", (chunk: Buffer) => {
    buf += chunk.toString();
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg = JSON.parse(line);
        const pending = _pending.get(msg.id);
        if (pending) {
          _pending.delete(msg.id);
          if (msg.error) pending.reject(new Error(msg.error));
          else pending.resolve(msg.result);
        }
      } catch {}
    }
  });

  _proc.on("exit", () => { _proc = null; });
  return _proc;
}

function callBackend(context: vscode.ExtensionContext, method: string, params: object): Promise<any> {
  return new Promise((resolve, reject) => {
    const id = nextId();
    const req = JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n";
    const proc = getBackend(context);
    _pending.set(id, { resolve, reject });
    proc.stdin?.write(req);
    setTimeout(() => {
      if (_pending.has(id)) {
        _pending.delete(id);
        reject(new Error("Backend timeout"));
      }
    }, 60_000);
  });
}

// ── Chat Webview Panel ─────────────────────────────────────────────────────────
class RobloxChatPanel {
  static current: RobloxChatPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];

  static createOrShow(context: vscode.ExtensionContext): void {
    const column = vscode.window.activeTextEditor
      ? vscode.ViewColumn.Beside
      : vscode.ViewColumn.One;

    if (RobloxChatPanel.current) {
      RobloxChatPanel.current._panel.reveal(column);
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "robloxAIChat",
      "Roblox AI Dev Tool",
      column,
      { enableScripts: true, retainContextWhenHidden: true }
    );
    RobloxChatPanel.current = new RobloxChatPanel(panel, context);
  }

  private constructor(panel: vscode.WebviewPanel, private context: vscode.ExtensionContext) {
    this._panel = panel;
    this._panel.webview.html = this._getHtml();

    this._panel.webview.onDidReceiveMessage(
      async (msg) => {
        if (msg.type === "userMessage") {
          await this._handleUserMessage(msg.text);
        }
      },
      null,
      this._disposables
    );

    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
  }

  private async _handleUserMessage(text: string): Promise<void> {
    this._panel.webview.postMessage({ type: "assistantChunk", text: "…thinking…" });
    try {
      const result = await callBackend(this.context, "chat", { message: text });
      this._panel.webview.postMessage({ type: "assistantDone", text: result.response ?? "" });
    } catch (e: any) {
      this._panel.webview.postMessage({ type: "error", text: e.message });
    }
  }

  public postCode(code: string, label: string): void {
    this._panel.webview.postMessage({ type: "injectCode", code, label });
  }

  public dispose(): void {
    RobloxChatPanel.current = undefined;
    this._panel.dispose();
    for (const d of this._disposables) d.dispose();
    this._disposables = [];
  }

  private _getHtml(): string {
    return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #1e1e1e; color: #d4d4d4; font-family: var(--vscode-font-family); font-size: 13px; display: flex; flex-direction: column; height: 100vh; }
  #messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
  .msg { padding: 8px 12px; border-radius: 6px; max-width: 90%; white-space: pre-wrap; word-break: break-word; }
  .user { background: #264f78; align-self: flex-end; }
  .assistant { background: #2d2d2d; border-left: 3px solid #ce9178; }
  .error-msg { background: #5a1d1d; border-left: 3px solid #f44747; }
  code { background: #0d0d0d; padding: 2px 6px; border-radius: 3px; font-family: var(--vscode-editor-font-family); }
  pre { background: #0d0d0d; padding: 8px; border-radius: 4px; overflow-x: auto; margin: 4px 0; }
  #inputRow { display: flex; padding: 8px; gap: 6px; background: #252526; border-top: 1px solid #3c3c3c; }
  #input { flex: 1; background: #3c3c3c; border: none; color: #d4d4d4; padding: 8px; border-radius: 4px; resize: none; font-family: inherit; font-size: 13px; }
  #input:focus { outline: 1px solid #007acc; }
  button { background: #0e639c; color: white; border: none; padding: 8px 14px; border-radius: 4px; cursor: pointer; font-size: 13px; }
  button:hover { background: #1177bb; }
  #model-badge { font-size: 11px; color: #858585; padding: 4px 12px; background: #252526; }
</style>
</head>
<body>
<div id="model-badge">Roblox AI Dev Tool</div>
<div id="messages"></div>
<div id="inputRow">
  <textarea id="input" rows="3" placeholder="Ask anything about Roblox scripting… (Shift+Enter for newline)"></textarea>
  <button id="send">Send</button>
</div>
<script>
  const vscode = acquireVsCodeApi();
  const messages = document.getElementById('messages');
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('send');

  function addMsg(role, text) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    // Simple markdown: code blocks
    div.innerHTML = text
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/\`\`\`[\\w]*(\\n[\\s\\S]*?)\`\`\`/g, '<pre>$1</pre>')
      .replace(/\`([^\`]+)\`/g, '<code>$1</code>');
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  let pendingDiv = null;
  sendBtn.onclick = function() { send(); };
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  function send() {
    const text = input.value.trim();
    if (!text) return;
    addMsg('user', text);
    input.value = '';
    pendingDiv = addMsg('assistant', '⏳ thinking…');
    vscode.postMessage({ type: 'userMessage', text });
  }

  window.addEventListener('message', function(e) {
    const msg = e.data;
    if (msg.type === 'assistantDone') {
      if (pendingDiv) { pendingDiv.remove(); pendingDiv = null; }
      addMsg('assistant', msg.text);
    } else if (msg.type === 'assistantChunk') {
      if (pendingDiv) pendingDiv.textContent = msg.text;
    } else if (msg.type === 'error') {
      if (pendingDiv) { pendingDiv.remove(); pendingDiv = null; }
      addMsg('error-msg', '⚠ ' + msg.text);
    } else if (msg.type === 'injectCode') {
      addMsg('assistant', '📋 ' + msg.label + ':\\n' + msg.code);
    }
  });
</script>
</body>
</html>`;
  }
}

// ── Extension activate ────────────────────────────────────────────────────────
export function activate(context: vscode.ExtensionContext): void {
  // Open chat panel
  context.subscriptions.push(
    vscode.commands.registerCommand("robloxAI.openChat", () => {
      RobloxChatPanel.createOrShow(context);
    })
  );

  // Review current file
  context.subscriptions.push(
    vscode.commands.registerCommand("robloxAI.reviewFile", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) { vscode.window.showWarningMessage("No active Luau file."); return; }
      const code = editor.document.getText();
      const fileName = path.basename(editor.document.fileName);
      RobloxChatPanel.createOrShow(context);
      const panel = RobloxChatPanel.current;
      if (panel) {
        panel.postCode(code, `Reviewing: ${fileName}`);
        // Also fire backend review
        vscode.window.withProgress(
          { location: vscode.ProgressLocation.Notification, title: `Reviewing ${fileName}…` },
          async () => {
            try {
              const result = await callBackend(context, "review", { code, fileName });
              panel.postCode(result.review ?? "No issues found.", `Review result for ${fileName}`);
            } catch (e: any) {
              vscode.window.showErrorMessage(`Review failed: ${e.message}`);
            }
          }
        );
      }
    })
  );

  // Generate script via quick input
  context.subscriptions.push(
    vscode.commands.registerCommand("robloxAI.generateScript", async () => {
      const feature = await vscode.window.showInputBox({ prompt: "What should the script do?", placeHolder: "e.g. round system with lobby and intermission" });
      if (!feature) return;
      const typeChoice = await vscode.window.showQuickPick(["Script", "LocalScript", "ModuleScript"], { placeHolder: "Script type" });
      if (!typeChoice) return;
      RobloxChatPanel.createOrShow(context);
      const panel = RobloxChatPanel.current;
      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "Generating script…" },
        async () => {
          try {
            const result = await callBackend(context, "generate", { feature, scriptType: typeChoice });
            if (panel) panel.postCode(result.code ?? "", `Generated: ${feature}`);
          } catch (e: any) {
            vscode.window.showErrorMessage(`Generation failed: ${e.message}`);
          }
        }
      );
    })
  );

  // Insert template
  context.subscriptions.push(
    vscode.commands.registerCommand("robloxAI.insertTemplate", async () => {
      const templates = ["singleton", "signal", "statemachine", "class", "roundsystem", "datastore", "netbridge", "promise"];
      const choice = await vscode.window.showQuickPick(templates, { placeHolder: "Choose a template" });
      if (!choice) return;
      try {
        const result = await callBackend(context, "template", { name: choice });
        const editor = vscode.window.activeTextEditor;
        if (editor) {
          editor.edit(eb => eb.insert(editor.selection.active, result.code ?? ""));
        } else {
          const doc = await vscode.workspace.openTextDocument({ language: "lua", content: result.code ?? "" });
          vscode.window.showTextDocument(doc);
        }
      } catch (e: any) {
        vscode.window.showErrorMessage(`Template error: ${e.message}`);
      }
    })
  );

  // Show dependency graph
  context.subscriptions.push(
    vscode.commands.registerCommand("robloxAI.showDeps", async () => {
      try {
        const result = await callBackend(context, "deps", {});
        const panel = vscode.window.createWebviewPanel("robloxDeps", "Dependency Graph", vscode.ViewColumn.Beside, {});
        panel.webview.html = `<html><body style="background:#1e1e1e;color:#d4d4d4;font-family:monospace;padding:16px;white-space:pre">${result.graph ?? "No graph available"}</body></html>`;
      } catch (e: any) {
        vscode.window.showErrorMessage(`Deps error: ${e.message}`);
      }
    })
  );

  vscode.window.showInformationMessage("Roblox AI Dev Tool activated! Open the chat from the activity bar.");
}

export function deactivate(): void {
  if (_proc) _proc.kill();
}
