# Build and bake every flora asset listed in specs/models, in place.
# Usage: powershell -File tools/build_flora.ps1 [-Pattern "conifer|snag"]
# -Pattern is a regex alternation of family prefixes, not a glob.
param([string]$Pattern = "conifer|snag|broadleaf|shrub|stump|log|fern|grass|reed|mushroom|flower|berry|rock")

$ErrorActionPreference = "Continue"
$names = Get-ChildItem specs/models/*.json |
    Where-Object { $_.BaseName -match "^($Pattern)_\d+$" } |
    ForEach-Object { $_.BaseName } | Sort-Object

$failed = @()
foreach ($name in $names) {
    $out = python assetgen.py model $name 2>&1
    if ($LASTEXITCODE -ne 0) { $failed += $name; Write-Host "$name MODEL-FAIL"; continue }
    $out = python assetgen.py texture $name 2>&1
    if ($LASTEXITCODE -ne 0) { $failed += $name; Write-Host "$name TEX-FAIL"; continue }
    $dir = python tools/outdir.py $name
    $report = Get-Content "$dir/report.json" -Raw | ConvertFrom-Json
    $tex = Get-Content "$dir/report_texture.json" -Raw | ConvertFrom-Json
    Write-Host ("{0,-16} tris {1,5}/{2,-5} {3,-4} colors {4,-3} {5}" -f `
        $name, $report.tris, $report.tri_budget, $report.status, $tex.unique_colors, ($report.warnings -join "; "))
}
Write-Host ""
Write-Host "built $($names.Count - $failed.Count)/$($names.Count)"
if ($failed.Count) { Write-Host "FAILED: $($failed -join ', ')" }
