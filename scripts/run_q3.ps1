param([switch]$Install)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$BundledPython = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$BundledNode = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$BundledModules = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"

if ($Install -and -not (Test-Path -LiteralPath $VenvPython)) {
    & $BundledPython -m venv (Join-Path $RepoRoot ".venv")
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
}
if (-not (Test-Path -LiteralPath $VenvPython)) { throw "缺少Python环境，请先使用-Install" }
$NodeModules = Join-Path $RepoRoot "node_modules"
if (-not (Test-Path -LiteralPath $NodeModules)) { New-Item -ItemType Junction -Path $NodeModules -Target $BundledModules | Out-Null }
$env:PYTHONPATH = Join-Path $RepoRoot "src"
& $VenvPython -u -X utf8 (Join-Path $RepoRoot "src\q3_solver.py") --data-dir (Join-Path $RepoRoot "problem\data") --output-dir (Join-Path $RepoRoot "outputs\q3") --report (Join-Path $RepoRoot "reports\q3_report.md")
& $BundledNode (Join-Path $RepoRoot "scripts\build_result3.mjs")
& $VenvPython -X utf8 (Join-Path $RepoRoot "scripts\validate_q3.py")
Write-Output "第三问全部结果已生成并通过校验。"
