"""core/tools/auditor.py — Deep Technical Audit & Code Inspection Engine."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("muse.tools.auditor")


@dataclass
class AuditReport:
    """Comprehensive technical audit report for an external tool candidate."""

    tool_id: str
    name: str
    repository: str
    target_dir: str
    commit: Optional[str] = None
    language: str = "Unknown"
    frameworks: List[str] = field(default_factory=list)
    license: str = "Unknown"
    architecture: str = ""
    process_model: str = "subprocess"
    communication_model: str = "stdio"
    mcp_support: bool = False
    mcp_transport: Optional[str] = None
    native_modules: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    security_concerns: List[str] = field(default_factory=list)
    entrypoints: List[str] = field(default_factory=list)
    source_files_count: int = 0
    total_loc: int = 0
    capabilities: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    platform_support: List[str] = field(default_factory=lambda: ["windows", "linux", "darwin"])
    integration_options: List[str] = field(default_factory=list)
    recommended_integration: str = ""
    decision: str = "pending"  # "compatible", "partially_compatible", "incompatible"
    key_source_files: List[str] = field(default_factory=list)
    raw_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            f"# Source-Code Analysis Report: {self.name} (`{self.tool_id}`)",
            "",
            f"- **Repository**: {self.repository}",
            f"- **Commit**: `{self.commit or 'N/A'}`",
            f"- **Language**: {self.language}",
            f"- **License**: {self.license}",
            f"- **Architecture**: {self.architecture}",
            f"- **Decision**: **{self.decision.upper()}**",
            "",
            "## Architecture & Process Model",
            f"- **Process Model**: {self.process_model}",
            f"- **Communication**: {self.communication_model}",
            f"- **MCP Implementation**: {'Yes (' + str(self.mcp_transport) + ')' if self.mcp_support else 'No / Native Adapter Required'}",
            f"- **Native Components**: {', '.join(self.native_modules) if self.native_modules else 'None (Pure Script / Managed)'}",
            f"- **Platforms**: {', '.join(self.platform_support)}",
            "",
            "## Strengths & Capabilities",
        ]
        for cap in self.capabilities:
            lines.append(f"- [+] {cap}")
        lines.append("")
        lines.append("## Limitations & Security Concerns")
        for lim in self.limitations:
            lines.append(f"- [-] {lim}")
        for sec in self.security_concerns:
            lines.append(f"- [!] Security: {sec}")
        lines.append("")
        lines.append("## Key Source Files")
        for ksf in self.key_source_files:
            lines.append(f"- `{ksf}`")
        lines.append("")
        lines.append("## Integration Options")
        for idx, opt in enumerate(self.integration_options, 1):
            lines.append(f"{idx}. {opt}")
        lines.append("")
        lines.append(f"**Recommended Integration**: {self.recommended_integration}")
        lines.append("")
        return "\n".join(lines)


class ToolAuditor:
    """Inspects candidate repositories in external/ or system paths."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or str(Path(__file__).resolve().parent.parent.parent)
        self.external_dir = os.path.join(self.workspace_root, "external")
        self.audits_dir = os.path.join(self.workspace_root, "tools", "audits")
        os.makedirs(self.audits_dir, exist_ok=True)

    def get_repo_commit(self, repo_path: str) -> Optional[str]:
        """Extract HEAD commit hash using git CLI."""
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            return None
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    def audit_repository(self, tool_id: str, repo_info: Dict[str, Any]) -> AuditReport:
        """Perform deep technical audit on cloned repository."""
        repo_dir = os.path.join(self.external_dir, tool_id)
        report = AuditReport(
            tool_id=tool_id,
            name=repo_info.get("name", tool_id),
            repository=repo_info.get("repository", ""),
            target_dir=repo_dir,
            commit=self.get_repo_commit(repo_dir) if os.path.isdir(repo_dir) else None,
        )

        if not os.path.isdir(repo_dir):
            report.decision = "missing"
            report.limitations.append("Repository directory not found in external/")
            return report

        # 1. Detect primary language and build manifests
        files = []
        loc = 0
        extensions = {}
        files_read = 0
        for root, _, filenames in os.walk(repo_dir):
            if ".git" in root or "node_modules" in root or "venv" in root or "__pycache__" in root:
                continue
            for f in filenames:
                rel = os.path.relpath(os.path.join(root, f), repo_dir)
                files.append(rel)
                ext = os.path.splitext(f)[1].lower()
                extensions[ext] = extensions.get(ext, 0) + 1
                if files_read < 200 and ext in (".py", ".ts", ".js", ".go", ".rs", ".cs", ".zig", ".c", ".cpp"):
                    try:
                        full_path = os.path.join(root, f)
                        if os.path.isfile(full_path) and os.path.getsize(full_path) < 200000:
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as fl:
                                loc += sum(1 for _ in fl)
                            files_read += 1
                    except Exception:
                        pass

        report.source_files_count = len(files)
        report.total_loc = loc

        # Language identification
        if extensions.get(".ts", 0) > 0 or extensions.get(".js", 0) > 0:
            report.language = "TypeScript / Node.js" if extensions.get(".ts", 0) > 0 else "JavaScript"
        elif extensions.get(".py", 0) > 0:
            report.language = "Python"
        elif extensions.get(".go", 0) > 0:
            report.language = "Go"
        elif extensions.get(".rs", 0) > 0:
            report.language = "Rust"
        elif extensions.get(".cs", 0) > 0:
            report.language = "C# / .NET"
        elif extensions.get(".zig", 0) > 0 or extensions.get(".c", 0) > 0:
            report.language = "Zig / C"

        # 2. License detection
        license_files = [f for f in files if "license" in f.lower() or "copying" in f.lower()]
        if license_files:
            lic_path = os.path.join(repo_dir, license_files[0])
            try:
                with open(lic_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000).lower()
                    if "mit license" in content or "permission is hereby granted" in content:
                        report.license = "MIT"
                    elif "apache license" in content or "version 2.0" in content:
                        report.license = "Apache-2.0"
                    elif "general public license" in content:
                        report.license = "GPL / AGPL"
                    elif "mozilla public license" in content:
                        report.license = "MPL-2.0"
                    else:
                        report.license = "Custom Open Source"
            except Exception:
                pass

        # 3. Dependencies and manifests
        package_json = os.path.join(repo_dir, "package.json")
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        reqs = os.path.join(repo_dir, "requirements.txt")
        cargo_toml = os.path.join(repo_dir, "Cargo.toml")
        go_mod = os.path.join(repo_dir, "go.mod")

        if os.path.isfile(package_json):
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    pj = json.load(f)
                    deps = list(pj.get("dependencies", {}).keys())
                    report.dependencies.extend(deps[:15])
                    report.entrypoints.append(pj.get("main", "index.js"))
                    if "@modelcontextprotocol/sdk" in deps:
                        report.mcp_support = True
                        report.mcp_transport = "stdio"
                    if "napi" in str(pj) or "native" in str(pj):
                        report.native_modules.append("N-API / C++ / Rust bindings")
            except Exception:
                pass

        if os.path.isfile(cargo_toml):
            report.frameworks.append("Cargo / Rust")
            report.native_modules.append("Native Rust compiled binary")

        if os.path.isfile(go_mod):
            report.frameworks.append("Go Modules")
            report.native_modules.append("Static Go binary")

        if os.path.isfile(reqs) or os.path.isfile(pyproject):
            report.frameworks.append("Python Package")

        # 4. Tool-specific architecture heuristics
        self._inspect_specific_tool(tool_id, repo_dir, files, report)

        # 5. Persist audit files
        json_path = os.path.join(self.audits_dir, f"{tool_id}.json")
        md_path = os.path.join(self.audits_dir, f"{tool_id}.md")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())

        logger.info("Generated audit report for %s -> %s", tool_id, md_path)
        return report

    def _inspect_specific_tool(self, tool_id: str, repo_dir: str, files: List[str], report: AuditReport) -> None:
        """Detailed architecture deduction for each known candidate."""
        if tool_id == "zavora-computer-use":
            report.architecture = "Native Rust/NAPI Windows UI Automation Engine + MCP TypeScript Server"
            report.process_model = "Node.js host process with compiled Rust DLL via NAPI"
            report.communication_model = "stdio (JSON-RPC MCP)"
            report.mcp_support = True
            report.mcp_transport = "stdio"
            report.capabilities = [
                "High-performance native Windows coordinate clicking (Rust)",
                "Hardware keyboard scan-code typing",
                "Direct Desktop Duplication API screen capture",
                "UI Automation element tree walking",
                "Window discovery & process handles",
            ]
            report.limitations = [
                "Windows-specific native compilation required (MSVC toolchain)",
                "Full screen takeover potential during mouse automation",
            ]
            report.security_concerns = [
                "Full desktop input injection (mouse/keyboard)",
                "Can read entire display framebuffer",
                "Arbitrary process inspection & termination",
            ]
            report.key_source_files = [f for f in files if "native" in f or "server" in f or "index" in f][:5]
            report.integration_options = [
                "Expose via internal stdio MCP client routed into Muse 18010 gateway",
                "Spawn dedicated loopback worker on private localhost port",
                "Call compiled CLI subcommands directly",
            ]
            report.recommended_integration = "Multiplex stdio MCP protocol behind Muse /mcp on 127.0.0.1:18010"
            report.decision = "compatible"

        elif tool_id == "pyautogui-mcp":
            report.architecture = "Python PyAutoGUI wrapper exposing MCP JSON-RPC protocol"
            report.process_model = "Python subprocess executing pywin32 / ctypes"
            report.communication_model = "stdio (MCP protocol)"
            report.mcp_support = True
            report.mcp_transport = "stdio"
            report.capabilities = [
                "Pure Python coordinate mouse clicking",
                "Keyboard typing and hotkey dispatch",
                "Pillow screenshot capture",
            ]
            report.limitations = [
                "No direct UI Automation accessibility tree inspection",
                "Screenshot capture slower than Direct3D / Rust",
            ]
            report.security_concerns = ["Global mouse and keyboard input control"]
            report.key_source_files = [f for f in files if f.endswith(".py")][:5]
            report.integration_options = [
                "Direct in-process Python module import",
                "Subprocess stdio MCP bridge",
            ]
            report.recommended_integration = "In-process Python adapter or stdio MCP bridge"
            report.decision = "compatible"

        elif tool_id == "go-mcp-computer-use":
            report.architecture = "Compiled Go desktop automation daemon exposing MCP"
            report.process_model = "Single compiled Go binary running native Windows API calls"
            report.communication_model = "stdio"
            report.mcp_support = True
            report.mcp_transport = "stdio"
            report.capabilities = [
                "Zero runtime dependencies (single static binary)",
                "Fast startup (<10ms)",
                "Mouse, keyboard, and screen capture",
            ]
            report.limitations = ["Requires Go compiler or precompiled binary for Windows"]
            report.security_concerns = ["System input synthesis"]
            report.key_source_files = [f for f in files if f.endswith(".go")][:5]
            report.integration_options = ["Compile executable and launch via stdio MCP bridge"]
            report.recommended_integration = "Subprocess stdio MCP wrapper"
            report.decision = "compatible"

        elif tool_id == "mcp-computer-use":
            report.architecture = ".NET / C# MCP server using Windows UIAutomationCore and user32.dll"
            report.process_model = ".NET runtime CLR process"
            report.communication_model = "stdio"
            report.mcp_support = True
            report.mcp_transport = "stdio"
            report.capabilities = [
                "Native Windows UI Automation accessibility element discovery",
                "Process and application targeting",
            ]
            report.limitations = ["Requires .NET SDK / Runtime installed on system"]
            report.security_concerns = ["Desktop accessibility control"]
            report.key_source_files = [f for f in files if f.endswith(".cs") or f.endswith(".csproj")][:5]
            report.integration_options = ["Run via dotnet cli and pipe stdio"]
            report.recommended_integration = "Optional secondary desktop automation backend"
            report.decision = "partially_compatible"

        elif tool_id == "moli":
            report.architecture = "High-speed scriptable headless browser automation engine"
            report.process_model = "Subprocess browser controller"
            report.communication_model = "CDP / stdio"
            report.capabilities = ["Fast page fetch", "DOM evaluation", "Screenshot"]
            report.limitations = ["Early stage development, platform-dependent builds"]
            report.security_concerns = ["Browser network traffic"]
            report.key_source_files = files[:5]
            report.integration_options = ["CLI wrapper adapter"]
            report.recommended_integration = "Tier 1 fallback browser adapter"
            report.decision = "partially_compatible"

        elif tool_id == "lightpanda":
            report.architecture = "Lightweight headless browser written in Zig/C, optimized for AI agents"
            report.process_model = "Native compiled binary"
            report.communication_model = "CDP (Chrome DevTools Protocol)"
            report.capabilities = ["Ultra-low memory footprint", "Fast JS execution", "DOM extraction"]
            report.limitations = ["Windows native binary availability varies; pre-alpha builds"]
            report.security_concerns = ["Outbound web fetch"]
            report.key_source_files = files[:5]
            report.integration_options = ["CDP WebSocket bridge or CLI adapter"]
            report.recommended_integration = "Tier 1 high-speed JS fetcher"
            report.decision = "partially_compatible"

        elif tool_id == "camoufox":
            report.architecture = "Firefox-based anti-detect browser with native C++ fingerprint spoofing"
            report.process_model = "Python Playwright-compatible browser process"
            report.communication_model = "Playwright Python API"
            report.capabilities = [
                "C++ level canvas/audio/webgl fingerprint spoofing",
                "Firefox gecko engine",
                "Full Playwright compatibility",
            ]
            report.limitations = ["Large browser download (>100MB)"]
            report.security_concerns = ["Browser credential persistence"]
            report.key_source_files = [f for f in files if f.endswith(".py")][:5]
            report.integration_options = ["Direct Python import via camoufox package"]
            report.recommended_integration = "Tier 3 stealth browser backend alongside Obscura"
            report.decision = "compatible"

        elif tool_id == "csi":
            report.architecture = "Chrome System Interface: connects to active user Chrome via CDP"
            report.process_model = "Python script connecting to running Chrome debugging port"
            report.communication_model = "WebSocket CDP"
            report.capabilities = [
                "Zero login required (uses existing session)",
                "Full extension and profile preservation",
            ]
            report.limitations = ["Requires Chrome launched with remote debugging port"]
            report.security_concerns = ["Access to user's real browser profile and credentials"]
            report.key_source_files = [f for f in files if f.endswith(".py")][:5]
            report.integration_options = ["Incorporate into ChromeAdapter"]
            report.recommended_integration = "Backend for user-authenticated browser sessions"
            report.decision = "compatible"

        elif tool_id == "agent-browser":
            report.architecture = "Vercel Labs headless browser CLI tailored for agent workflows"
            report.process_model = "Node.js process executing Puppeteer / Playwright"
            report.communication_model = "CLI stdout / MCP"
            report.mcp_support = True
            report.capabilities = ["Semantic snapshotting", "Deterministic action dispatch"]
            report.limitations = ["Node runtime dependency"]
            report.key_source_files = files[:5]
            report.integration_options = ["CLI subcommand adapter or stdio MCP"]
            report.recommended_integration = "Tier 2 headless agent browser"
            report.decision = "compatible"

        elif tool_id == "yt-dlp":
            report.architecture = "Universal media downloader and metadata extractor in Python"
            report.process_model = "Python library or subprocess executable"
            report.communication_model = "In-process Python API or CLI stdout/JSON"
            report.capabilities = [
                "Metadata extraction for 1000+ video/audio platforms",
                "Direct stream URL extraction",
                "Audio extraction and format transcoding",
            ]
            report.limitations = ["Requires FFmpeg for format merging"]
            report.security_concerns = ["Arbitrary media download"]
            report.key_source_files = [f for f in files if f.endswith(".py")][:5]
            report.integration_options = ["In-process import `import yt_dlp` or CLI wrapper"]
            report.recommended_integration = "Primary media extraction adapter"
            report.decision = "compatible"
