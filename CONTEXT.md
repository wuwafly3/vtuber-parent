# Desktop Pet (桌宠)

A desktop companion with AI chat, TTS voice, Live2D animation, and agent capabilities. The pet ("小灵") lives as a transparent always-on-top window and interacts through a separate console window.

## Language

**Tool**:
A capability the pet can invoke via LLM function calling to perceive or act on the outside world. Each tool has a name, description, JSON Schema parameters, and an async execute method. Examples: take_screenshot, (future) click, type.
_Avoid_: action, command, plugin, skill

**Agent Loop**:
The orchestration cycle in `handle_user_message` that detects LLM tool_call chunks, executes the tool via the registry, feeds the result back into the conversation, and repeats until the LLM produces a final text response. Runs in serial mode: only the last round streams to the frontend.
_Avoid_: agent cycle, tool loop, chain

**Tool Registry**:
The singleton that holds all registered tool instances, generates the OpenAI `tools` schema array, and dispatches tool calls by name to the correct tool's `execute()`.
_Avoid_: tool manager, tool router

**Screenshot**:
Capturing the full primary monitor via `mss` and encoding it as a base64 data URL. Returned to the LLM as a separate image user message appended after the tool result.
_Avoid_: screen capture, screen grab
