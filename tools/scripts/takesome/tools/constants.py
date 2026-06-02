from __future__ import annotations

TOOL_SCHEMA = "takesome.tool.v1"
CACHE_SCHEMA = "takesome.toolRegistryCache.v1"

LEGACY_TOOL_PATHS = [
    "tools/netexturetool",
    "tools/NePak",
    "tools/nepak",
    "tools/nematerialtool",
    "tools/nelistfile",
    "tools/nelisyfile",
    "tools/DDSCubemap",
    "tools/DDSHeaderViewer",
    "tools/NoiseGenerator",
    "tools/AssetAnalysisTool",
    "tools/common",
    "tools/dataTool",
    "tools/neassetchain",
    "tools/reference/DDSCubemap",
    "tools/reference/DDSHeaderViewer",
    "tools/reference/NoiseGenerator",
    "tools/reference/AssetAnalysisTool",
    "tools/reference/dataTool",
    "tools/reference/neassetchain",
    "tools/quarantine/DDSCubemap",
    "tools/quarantine/DDSHeaderViewer",
    "tools/quarantine/NoiseGenerator",
    "tools/quarantine/AssetAnalysisTool",
    "tools/quarantine/dataTool",
    "tools/quarantine/neassetchain",
]

LEGACY_TOOL_IDENTITIES = [
    "netexturetool",
    "nepak",
    "nematerialtool",
    "nelistfile",
    "nelisyfile",
    "ddscubemap",
    "ddsheaderviewer",
    "noisegenerator",
    "assetanalysistool",
    "datatool",
    "neassetchain",
]

SOURCE_SKIP_DIRS = {
    ".git",
    ".takesome",
    ".northstar",
    "target",
    "node_modules",
    "logs",
    "cache",
    "dist",
    "out",
    "bin",
    "obj",
    "artifacts",
    "__pycache__",
}

TEXT_EXTS = {
    ".rs", ".py", ".toml", ".json", ".md", ".txt", ".bat", ".cmd", ".ps1", ".yml", ".yaml",
}
