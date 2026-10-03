"""
Standalone demo: connect to the Framelink Figma MCP server and fetch a design.

This is intentionally separate from main.py so it doesn't interfere with the
existing DocumentMCP chat demo. It reuses the project's own MCPClient (stdio),
which just spawns a subprocess and speaks MCP over its stdin/stdout.

The Figma server (https://github.com/GLips/Figma-Context-MCP) is an npm package
run via `npx`; it talks to Figma's REST API using a personal access token.

Usage:
    # 1. Put your token in .env:  FIGMA_API_KEY=figd_xxx
    # 2a. Just verify the connection and list the server's tools:
    uv run figma_demo.py
    # 2b. Fetch a specific design (paste a Figma file or frame URL):
    uv run figma_demo.py "https://www.figma.com/design/<fileKey>/Title?node-id=1-2"

    (Without uv:  python figma_demo.py ... )

Get a token at: Figma -> Settings -> Security -> Personal access tokens
(scope: "File content" read is enough).
"""

import os
import re
import sys
import json
import asyncio

from dotenv import load_dotenv

from mcp_client import MCPClient
from mcp import types

load_dotenv()

FIGMA_API_KEY = os.getenv("FIGMA_API_KEY", "").strip()


def parse_figma_url(url: str) -> dict[str, str]:
    """Pull the fileKey (and node id, if present) out of a Figma URL.

    Accepts /design/, /file/ and /proto/ links. A bare file key also works.
    The node-id in a URL looks like `1-2`; that is the form the Figma MCP
    server expects, so we pass it through unchanged.
    """
    # A bare key was passed (no slashes / not a URL) -> treat as the file key.
    if "/" not in url and "figma.com" not in url:
        return {"fileKey": url}

    file_match = re.search(r"figma\.com/(?:design|file|proto)/([A-Za-z0-9]+)", url)
    if not file_match:
        raise ValueError(
            f"Could not find a file key in: {url}\n"
            "Expected something like https://www.figma.com/design/<fileKey>/..."
        )
    result = {"fileKey": file_match.group(1)}

    node_match = re.search(r"[?&]node-id=([0-9]+-[0-9]+)", url)
    if node_match:
        result["nodeId"] = node_match.group(1)
    return result


def _summarize_result(result: types.CallToolResult) -> str:
    """Render a tool result compactly so a big design dump stays readable."""
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            text = block.text
            # The Figma data comes back as JSON text; pretty-print a summary
            # rather than flooding the terminal with the whole tree.
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                parts.append(text[:2000])
                continue

            preview = json.dumps(data, indent=2)
            if len(preview) > 2500:
                preview = preview[:2500] + "\n... (truncated)"
            parts.append(preview)
        else:
            parts.append(f"[{block.type} content]")
    return "\n".join(parts) if parts else "(no content returned)"


# get_figma_data returns a compact YAML-ish text. Node lines look like:
#     [IMAGE-SVG] "Battery" #0:8476 layout=...
#     [FRAME] "Time Style" #0:8493 ...
_NODE_LINE_RE = re.compile(r'^\s*\[([A-Z0-9-]+)\]\s+(?:"([^"]*)"\s+)?#(\S+)',
                           re.MULTILINE)
_NAME_RE = re.compile(r'^NAME:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)

# Figma node types that export cleanly as vector SVG; everything else we render
# to PNG via its node id.
_VECTOR_TYPES = {"IMAGE-SVG", "VECTOR", "LINE", "ELLIPSE", "STAR",
                 "REGULAR_POLYGON", "BOOLEAN_OPERATION"}


def _result_text(result: types.CallToolResult) -> str:
    """Concatenate the text blocks of a tool result."""
    return "\n".join(
        b.text for b in result.content if isinstance(b, types.TextContent)
    )


def _sanitize_filename(name: str, fallback: str) -> str:
    """Reduce a Figma layer name to something the tool's filename rule allows
    (^[A-Za-z0-9_.-]+$). Emoji, spaces and slashes become underscores."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("._")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned or fallback


def _extract_image_nodes(text: str, max_svgs: int = 25) -> list[dict]:
    """Scan get_figma_data output and pick vector nodes worth exporting as SVG.

    Filenames are made unique and rule-compliant. Returns the `nodes` payload
    for download_figma_images (minus the root frame, which we add separately).
    """
    nodes: list[dict] = []
    seen: set[str] = set()
    for node_type, name, node_id in _NODE_LINE_RE.findall(text):
        if node_type not in _VECTOR_TYPES:
            continue
        base = _sanitize_filename(name or "", node_id.replace(":", "_"))
        fname = f"{base}.svg"
        n = 2
        while fname in seen:
            fname = f"{base}_{n}.svg"
            n += 1
        seen.add(fname)
        nodes.append({"nodeId": node_id, "fileName": fname})
        if len(nodes) >= max_svgs:
            break
    return nodes


async def _download_images(client, fileKey, root_node_id, design_name,
                           fetched_text, png_scale):
    """Export the selected frame as PNG plus its vector nodes as SVGs."""
    nodes: list[dict] = []
    if root_node_id:
        frame_name = _sanitize_filename(design_name or "frame", "frame")
        nodes.append({
            "nodeId": root_node_id.replace("-", ":"),
            "fileName": f"{frame_name}.png",
        })
    nodes.extend(_extract_image_nodes(fetched_text))

    if not nodes:
        print("\nNo exportable image/vector nodes were found in this frame.")
        return

    args = {
        "fileKey": fileKey,
        "localPath": ".",  # relative to the server's IMAGE_DIR (figma-img)
        "pngScale": png_scale,
        "nodes": nodes,
    }
    print(f"\nDownloading {len(nodes)} image(s) "
          f"(1 PNG frame + {len(nodes) - 1} SVG nodes) ...")
    result = await client.call_tool("download_figma_images", args)
    if result is None:
        print("No result returned from download_figma_images.")
        return
    if result.isError:
        print("download_figma_images returned an error:")
    print(_result_text(result) or "(done)")


async def run(url: str | None, download_images: bool = False,
              png_scale: float = 2):
    if not FIGMA_API_KEY:
        print(
            "FIGMA_API_KEY is empty. Add your token to .env:\n"
            "    FIGMA_API_KEY=figd_your_token_here\n"
            "(Figma -> Settings -> Security -> Personal access tokens)"
        )
        return

    # Spawn the Framelink Figma MCP server over stdio. `-y` auto-installs it on
    # first run. The SDK resolves `npx` -> `npx.cmd` on Windows for us, and it
    # merges this env with a safe default (so PATH is preserved).
    client = MCPClient(
        command="npx",
        args=["-y", "figma-developer-mcp", "--stdio"],
        env={"FIGMA_API_KEY": FIGMA_API_KEY},
    )

    print("Starting Figma MCP server via npx (first run may download it)...")
    async with client:
        tools = await client.list_tools()
        print(f"\nConnected. The server exposes {len(tools)} tool(s):")
        for tool in tools:
            desc = (tool.description or "").strip().splitlines()
            first_line = desc[0] if desc else ""
            print(f"  - {tool.name}: {first_line}")

        if url is None:
            print(
                "\nNo Figma URL given, so this was just a connection check.\n"
                "Fetch a design with:\n"
                '    uv run figma_demo.py "https://www.figma.com/design/<fileKey>/..."'
            )
            return

        args = parse_figma_url(url)
        print(f"\nFetching design data with get_figma_data({args}) ...\n")
        result = await client.call_tool("get_figma_data", args)

        if result is None:
            print("No result returned.")
            return
        if result.isError:
            print("The server returned an error:")
        text = _result_text(result)
        print(_summarize_result(result))

        if download_images:
            name_match = _NAME_RE.search(text)
            design_name = name_match.group(1) if name_match else None
            await _download_images(
                client,
                fileKey=args["fileKey"],
                root_node_id=args.get("nodeId"),
                design_name=design_name,
                fetched_text=text,
                png_scale=png_scale,
            )

    # Windows: let the ProactorEventLoop finish closing the subprocess pipes
    # before asyncio.run() tears the loop down (mirrors main.py / mcp_client.py).
    await asyncio.sleep(0.1)


def _silence_proactor_teardown():
    """Swallow the harmless Windows shutdown noise from subprocess pipes.

    On Windows, a ProactorEventLoop subprocess pipe transport can raise
    ValueError("I/O operation on closed pipe") from __del__ at interpreter
    shutdown -- after our event loop is already gone, so no amount of waiting
    prevents it. Python routes that through sys.unraisablehook; we filter out
    just this one case and defer everything else to the default handler.
    """
    default_hook = sys.unraisablehook

    def hook(unraisable):
        exc = unraisable.exc_value
        if isinstance(exc, ValueError) and "closed pipe" in str(exc):
            return
        default_hook(unraisable)

    sys.unraisablehook = hook


if __name__ == "__main__":
    # Tiny arg parse: first non-flag arg is the URL; --images enables export;
    # --scale N sets the PNG export scale (default 2).
    argv = sys.argv[1:]
    want_images = "--images" in argv
    scale = 2.0
    if "--scale" in argv:
        i = argv.index("--scale")
        if i + 1 < len(argv):
            scale = float(argv[i + 1])
            del argv[i:i + 2]
    positionals = [a for a in argv if not a.startswith("--")]
    target = positionals[0] if positionals else None

    # Figma layer names contain emoji; a legacy Windows console (cp1252) would
    # crash on print(). Force UTF-8 output and replace anything unmappable.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        _silence_proactor_teardown()
    try:
        asyncio.run(run(target, download_images=want_images, png_scale=scale))
    except KeyboardInterrupt:
        pass
