# MCP Chat

MCP Chat is a command-line interface application that enables interactive chat capabilities with AI models through the Anthropic API. The application supports document retrieval, command-based prompts, and extensible tool integrations via the MCP (Model Control Protocol) architecture.

## Prerequisites

- Python 3.9+
- Anthropic API Key

## Setup

### Step 1: Configure the environment variables

1. Create or edit the `.env` file in the project root and verify that the following variables are set correctly:

```
ANTHROPIC_API_KEY=""  # Enter your Anthropic API secret key
```

### Step 2: Install dependencies

#### Option 1: Setup with uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver.

1. Install uv, if not already installed:

```bash
pip install uv
```

2. Create and activate a virtual environment:

```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
uv pip install -e .
```

4. Run the project

```bash
uv run main.py
```

#### Option 2: Setup without uv

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install anthropic python-dotenv prompt-toolkit "mcp[cli]==1.8.0"
```

3. Run the project

```bash
python main.py
```

## Usage

### Using the MCP Inspector on Windows

Run the server:
uv run mcp dev .\mcp_server.py

Run: mcp dev .\mcp_server.py
Browser opens at: http://localhost:6274/


Sometimes uv might not work correctly on windows, if so, try the more direct, deterministic option — point straight at the venv's Python, skipping uv entirely:

Command: C:\dev\ai-dev\2026-07-AI4Devs-Course\Session2\proj-mcp-cli\.venv\Scripts\python.exe
Arguments: mcp_server.py





### Basic Interaction

Simply type your message and press Enter to chat with the model.

### Document Retrieval

Use the @ symbol followed by a document ID to include document content in your query:

```
> Tell me about @deposition.md
```

### Commands

Use the / prefix to execute commands defined in the MCP server:

```
> /summarize deposition.md
```

Commands will auto-complete when you press Tab.



## Figma
uv run figma_demo.py "https://www.figma.com/design/tHm72cbGTItMqApwFQ7pkZ/WhatsAppUI?node-id=0-8474&m=dev"

### download images
uv run figma_demo.py "https://www.figma.com/design/tHm72cbGTItMqApwFQ7pkZ/WhatsAppUI?node-id=0-8474&m=dev" --images

## from claude
generate some CSS for this design from Figma.
  @https://www.figma.com/design/tHm72cbGTItMqApwFQ7pkZ/WhatsAppUI?node-id=0-8474&m=dev

## GitHub MCP

Let Claude Code create GitHub issues/PRs through the official remote GitHub MCP server.

### 1. Create a Personal Access Token (PAT)

GitHub → **Settings** → **Developer settings** → **Personal access tokens**.

- **Fine-grained (recommended):** repository access = this repo, permission **Issues: Read and write**.
- **Classic:** `repo` scope (`public_repo` if the repo is public).

Copy the token — it's shown only once.

### 2. Expose the token as `GITHUB_PAT`

`.mcp.json` references it as `${GITHUB_PAT}`, so it stays out of source control. Set it in your environment (Claude Code does **not** auto-load `.env`):

```powershell
# Windows (persistent, new processes only)
setx GITHUB_PAT "github_pat_your_token_here"
```

```bash
# macOS / Linux
export GITHUB_PAT="github_pat_your_token_here"
```

### 3. Server config

Already committed in [.mcp.json](.mcp.json):

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ${GITHUB_PAT}" }
    }
  }
}
```

### 4. Restart Claude Code

The token is read when the editor launches, so **fully restart** — "Reload Window" is not enough. In VS Code, close all windows and reopen the folder. Approve the `github` server when prompted (project MCP servers require approval).

### 5. Verify and use

```
/mcp        # should list `github` as connected
```

Then ask Claude, e.g.:

```
create a demo issue titled "Issue created by MCP for demo" in vyaron/proj-mcp-cli
```

Claude calls the `issue_write` MCP tool — no `gh` CLI. Troubleshooting: if `/mcp` shows `github` failed, the token likely isn't visible to the editor (redo step 4), lacks **Issues: Read and write**, or has expired.