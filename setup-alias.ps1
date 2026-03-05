# ABOUTME: Utility script to set up a PowerShell alias for the investment research system.
# ABOUTME: Simplifies running the Docker-based orchestrator.

# $projectPath = "E:\ai-workspace\projects\multi-agent-investment-research"
$projectPath = $PSScriptRoot
$researchAlias = "function invest-research { docker compose -f '$projectPath\docker-compose.yml' run --rm investment-research `$args }"
$logsAlias = "function invest-logs { fly logs -a investment-orchestrator }"

$profilePath = $PROFILE.CurrentUserAllHosts

if (!(Test-Path $profilePath)) {
    New-Item -Path $profilePath -ItemType File -Force | Out-Null
}

# Check if aliases already exist
$existingContent = Get-Content $profilePath -ErrorAction SilentlyContinue
if ($existingContent -match "invest-research" -or $existingContent -match "invest-logs") {
    Write-Host "⚠ Research aliases already exist in profile" -ForegroundColor Yellow
    $answer = Read-Host "Overwrite? (y/n)"
    if ($answer -ne "y") {
        Write-Host "✗ Installation cancelled" -ForegroundColor Red
        exit
    }
    # Remove old aliases
    $newContent = $existingContent | Where-Object { $_ -notmatch "invest-research" -and $_ -notmatch "invest-logs" }
    Set-Content -Path $profilePath -Value $newContent
}

Add-Content -Path $profilePath -Value "`n# Multi-Agent Investment Research Aliases"
Add-Content -Path $profilePath -Value $researchAlias
Add-Content -Path $profilePath -Value $logsAlias

Write-Host "✓ Aliases 'invest-research' and 'invest-logs' added to PowerShell profile" -ForegroundColor Green
Write-Host "  Location: $profilePath" -ForegroundColor Cyan
Write-Host "`nTo activate, run:" -ForegroundColor Yellow
Write-Host "  . `$PROFILE" -ForegroundColor White
Write-Host "`nOr restart your terminal" -ForegroundColor Yellow
