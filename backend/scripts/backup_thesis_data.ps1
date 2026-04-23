# Backup Thesis Data to Archive
# Usage: .\backup_thesis_data.ps1

$ErrorActionPreference = "Stop"

$root = "E:/dailyfile/myfiles/project_all/learnpath322"
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$dst = "$root/document/thesis_assets/archive/1.0.0_baseline_$ts"

Write-Host "Creating archive directory: $dst"
New-Item -ItemType Directory -Force "$dst" | Out-Null

# Backup backend artifacts
if (Test-Path "$root/backend/artifacts/thesis_validation") {
    Write-Host "Backing up backend/artifacts/thesis_validation..."
    Copy-Item -Recurse -Force "$root/backend/artifacts/thesis_validation" "$dst/backend_thesis_validation"
}

if (Test-Path "$root/backend/artifacts/final_reports") {
    Write-Host "Backing up backend/artifacts/final_reports..."
    Copy-Item -Recurse -Force "$root/backend/artifacts/final_reports" "$dst/backend_final_reports"
}

if (Test-Path "$root/backend/artifacts/final_ablation") {
    Write-Host "Backing up backend/artifacts/final_ablation..."
    Copy-Item -Recurse -Force "$root/backend/artifacts/final_ablation" "$dst/backend_final_ablation"
}

# Backup document thesis_assets
if (Test-Path "$root/document/thesis_assets/final_reports") {
    Write-Host "Backing up document/thesis_assets/final_reports..."
    Copy-Item -Recurse -Force "$root/document/thesis_assets/final_reports" "$dst/document_final_reports"
}

if (Test-Path "$root/document/thesis_assets/final_ablation") {
    Write-Host "Backing up document/thesis_assets/final_ablation..."
    Copy-Item -Recurse -Force "$root/document/thesis_assets/final_ablation" "$dst/document_final_ablation"
}

# Backup thesis markdown
if (Test-Path "$root/document/毕业论文_v2.md") {
    Write-Host "Backing up document/毕业论文_v2.md..."
    Copy-Item -Force "$root/document/毕业论文_v2.md" "$dst/毕业论文_v2.md"
}

# Backup thesis docx
if (Test-Path "$root/document/毕业论文_v2.docx") {
    Write-Host "Backing up document/毕业论文_v2.docx..."
    Copy-Item -Force "$root/document/毕业论文_v2.docx" "$dst/毕业论文_v2.docx"
}

Write-Host "Backup complete: $dst"
