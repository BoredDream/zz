param(
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$VenvPath = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$BundledPython = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$BundledNode = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$BundledModules = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"

if ($Install) {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        if (Test-Path -LiteralPath $BundledPython) {
            & $BundledPython -m venv $VenvPath
        } else {
            python -m venv $VenvPath
        }
    }
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "缺少Python环境。请先执行 .\scripts\run_q2.ps1 -Install"
}

$NodeModules = Join-Path $RepoRoot "node_modules"
if (-not (Test-Path -LiteralPath $NodeModules)) {
    if (-not (Test-Path -LiteralPath $BundledModules)) {
        throw "缺少@oai/artifact-tool运行环境。请在Codex桌面环境中运行。"
    }
    New-Item -ItemType Junction -Path $NodeModules -Target $BundledModules | Out-Null
}

& $VenvPython -X utf8 (Join-Path $RepoRoot "src\q2_solver.py") `
    --data-dir (Join-Path $RepoRoot "problem\data") `
    --output-dir (Join-Path $RepoRoot "outputs\q2") `
    --report (Join-Path $RepoRoot "reports\q2_report.md")

if (Test-Path -LiteralPath $BundledNode) {
    & $BundledNode (Join-Path $RepoRoot "scripts\build_result2.mjs")
} else {
    node (Join-Path $RepoRoot "scripts\build_result2.mjs")
}

& $VenvPython -X utf8 (Join-Path $RepoRoot "scripts\validate_q2.py")

Write-Output "第二问全部结果已生成。"
