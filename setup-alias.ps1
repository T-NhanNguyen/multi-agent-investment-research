# ABOUTME: Utility script to set up a PowerShell alias for the investment research system.
# ABOUTME: Simplifies running the Docker-based orchestrator.

# $projectPath = "E:\ai-workspace\projects\multi-agent-investment-research"
$projectPath = $PSScriptRoot
$aliasCommand = "function invest-research { docker compose -f '$projectPath\docker-compose.yml' run --rm investment-research `$args }"

$profilePath = $PROFILE.CurrentUserAllHosts

if (!(Test-Path $profilePath)) {
    New-Item -Path $profilePath -ItemType File -Force | Out-Null
}

# Check if alias already exists
$existingContent = Get-Content $profilePath -ErrorAction SilentlyContinue
if ($existingContent -match "invest-research") {
    Write-Host "⚠ Alias 'invest-research' already exists in profile" -ForegroundColor Yellow
    $answer = Read-Host "Overwrite? (y/n)"
    if ($answer -ne "y") {
        Write-Host "✗ Installation cancelled" -ForegroundColor Red
        exit
    }
    # Remove old alias
    $newContent = $existingContent | Where-Object { $_ -notmatch "invest-research" }
    Set-Content -Path $profilePath -Value $newContent
}

Add-Content -Path $profilePath -Value "`n# Multi-Agent Investment Research Alias"
Add-Content -Path $profilePath -Value $aliasCommand

Write-Host "✓ Alias 'invest-research' added to PowerShell profile" -ForegroundColor Green
Write-Host "  Location: $profilePath" -ForegroundColor Cyan
Write-Host "`nTo activate, run:" -ForegroundColor Yellow
Write-Host "  . `$PROFILE" -ForegroundColor White
Write-Host "`nOr restart your terminal" -ForegroundColor Yellow
