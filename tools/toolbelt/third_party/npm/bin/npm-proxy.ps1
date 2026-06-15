param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$NpmArgs
)

$ErrorActionPreference = "Stop"

function Write-ProxyError {
  param([string]$Message)
  [Console]::Error.WriteLine($Message)
}

function Test-PackageRoot {
  param([string]$Path)
  return ($Path -and (Test-Path (Join-Path $Path "package.json")))
}

function Resolve-NpmCommand {
  $candidates = @()
  if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles "nodejs\npm.cmd" }
  $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  if ($programFilesX86) { $candidates += Join-Path $programFilesX86 "nodejs\npm.cmd" }
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) { return (Resolve-Path $candidate).Path }
  }
  $cmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd = Get-Command npm -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

function Resolve-DevSuiteRootFromScript {
  $cursor = Split-Path -Parent $PSCommandPath
  while ($cursor) {
    if ((Test-Path (Join-Path $cursor "tools\suite")) -and (Test-Path (Join-Path $cursor "tools\toolbelt"))) {
      return (Resolve-Path $cursor).Path
    }
    $parent = Split-Path -Parent $cursor
    if (-not $parent -or $parent -eq $cursor) { break }
    $cursor = $parent
  }
  return $null
}

function Command-RequiresWorkspace {
  param([string[]]$Args)
  if (-not $Args -or $Args.Count -eq 0) { return $false }
  if ($Args[0] -in @("--version", "-version", "-v", "--help", "help", "config")) { return $false }
  if ($Args[0] -in @("run", "install", "ci", "audit", "outdated", "update", "exec", "test", "start", "publish", "pack", "rebuild")) { return $true }
  return $false
}

function Add-UniquePath {
  param([System.Collections.ArrayList]$List, [hashtable]$Seen, [string]$Path)
  if (-not $Path) { return }
  try { $resolved = (Resolve-Path $Path -ErrorAction Stop).Path } catch { return }
  $key = $resolved.ToLowerInvariant()
  if (-not $Seen.ContainsKey($key)) { $Seen[$key] = $true; [void]$List.Add($resolved) }
}

function Get-WorkspaceCandidates {
  $devSuiteRoot = Resolve-DevSuiteRootFromScript
  $current = (Get-Location).Path
  $seen = @{}
  $result = New-Object System.Collections.ArrayList

  foreach ($name in @("TAKESOME_WORKSPACE_ROOT", "NORTHSTAR_WORKSPACE_ROOT", "NEWENGINE_PROJECT_ROOT", "WORKSPACE_ROOT", "PROJECT_ROOT", "VITE_WORKSPACE_ROOT")) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($value) { Add-UniquePath -List $result -Seen $seen -Path $value }
  }

  if (Test-PackageRoot $current) { Add-UniquePath -List $result -Seen $seen -Path $current }

  if ($devSuiteRoot) {
    $parent = Split-Path -Parent $devSuiteRoot
    foreach ($siblingName in @("TakeSomeWebsite", "TakeSomeWebSite", "TakeSomeFrontend", "TakeSomeSPA", "TakeSomeLanding", "TakeSomeApp")) {
      $candidate = Join-Path $parent $siblingName
      if (Test-PackageRoot $candidate) { Add-UniquePath -List $result -Seen $seen -Path $candidate }
    }
    Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -ne $devSuiteRoot } |
      Where-Object { Test-PackageRoot $_.FullName } |
      Sort-Object Name |
      ForEach-Object { Add-UniquePath -List $result -Seen $seen -Path $_.FullName }
  }

  Add-UniquePath -List $result -Seen $seen -Path $current
  return $result
}

function Resolve-WorkingDirectory {
  param([string[]]$Args)
  $current = (Get-Location).Path
  if (-not (Command-RequiresWorkspace -Args $Args)) { return $current }
  foreach ($candidate in (Get-WorkspaceCandidates)) { if (Test-PackageRoot $candidate) { return $candidate } }
  return $current
}

function Needs-GuardForBuildLikeCommand {
  param([string[]]$Args)
  if (-not $Args -or $Args.Count -eq 0) { return $false }
  $joined = ($Args -join " ").ToLowerInvariant()
  return ($joined -match '(^| )run (build|typecheck|lint|test|check)( |$)' -or $joined -match '(^| )(build|typecheck|lint|test|check)( |$)')
}

if ($NpmArgs.Count -gt 0 -and $NpmArgs[0] -eq "--") {
  if ($NpmArgs.Count -gt 1) { $NpmArgs = $NpmArgs[1..($NpmArgs.Count - 1)] } else { $NpmArgs = @() }
}

if ($NpmArgs.Count -gt 0 -and $NpmArgs[0] -eq "--devsuite-resolve-workspace") {
  foreach ($candidate in (Get-WorkspaceCandidates)) {
    $marker = if (Test-PackageRoot $candidate) { "package" } else { "no-package" }
    Write-Output "$marker`t$candidate"
  }
  exit 0
}

$npm = Resolve-NpmCommand
if (-not $npm) { Write-ProxyError "npm was not found. Install Node.js or expose npm.cmd on PATH."; exit 9009 }

$workingDirectory = Resolve-WorkingDirectory -Args $NpmArgs
if ((Command-RequiresWorkspace -Args $NpmArgs) -and -not (Test-PackageRoot $workingDirectory)) {
  Write-ProxyError "npm workspace was not found. No package.json in configured workspace candidates."
  Write-ProxyError "Current directory: $((Get-Location).Path)"
  Write-ProxyError "Set TAKESOME_WORKSPACE_ROOT or NORTHSTAR_WORKSPACE_ROOT to a directory containing package.json."
  foreach ($candidate in (Get-WorkspaceCandidates)) { Write-ProxyError "candidate: $candidate" }
  exit 2
}

$output = @()
$exitCode = 0
try {
  Push-Location $workingDirectory
  $output = & $npm @NpmArgs 2>&1
  $exitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
} catch {
  $output += $_.Exception.Message
  $exitCode = 1
} finally {
  Pop-Location
}

foreach ($line in $output) { Write-Output $line }
$text = ($output | ForEach-Object { [string]$_ }) -join "`n"
$guardFailed = $false
if ($text -match '(?im)^\s*npm\s+(ERR!|error)\b' -or $text -match '(?im)\bENOENT\b' -or $text -match '(?im)Could not read package\.json' -or $text -match '(?im)Missing script:') { $guardFailed = $true }
if (Needs-GuardForBuildLikeCommand -Args $NpmArgs) {
  if ($text -match '(?im)\berror\s+TS\d+\b' -or $text -match '(?im)Failed to compile' -or $text -match '(?im)\bSyntaxError\b' -or $text -match '(?im)\bTypeError\b' -or $text -match '(?im)\bCannot find module\b' -or $text -match '(?im)\bRollupError\b' -or $text -match '(?im)\bVite\b.*\berror\b') { $guardFailed = $true }
}
if ($guardFailed -and $exitCode -eq 0) { $exitCode = 1 }
exit $exitCode
