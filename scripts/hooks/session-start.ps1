# Hook SessionStart -- SEUL evenement (avec UserPromptSubmit/Expansion) dont le stdout est
# REINJECTE dans le contexte de Claude. C'est donc lui, et pas PostCompact, qui peut restaurer
# quoi que ce soit apres un compactage (PostCompact = effets de bord uniquement).
#
# On ne parle QUE si `source == "compact"` : au demarrage normal le CLAUDE.md suffit, et polluer
# chaque session couterait du contexte pour rien.
#
# ASCII STRICT : PowerShell 5.1 lit ce fichier en ANSI. Un tiret long ou un accent y casse la
# chaine et fait echouer le hook (vecu le 2026-07-25). Aucun caractere non-ASCII ici.
#
# Sortie volontairement COURTE : elle est payee en tokens a chaque compactage.

$ErrorActionPreference = 'SilentlyContinue'
$raw = [Console]::In.ReadToEnd()
$evt = try { $raw | ConvertFrom-Json } catch { $null }
if (-not $evt -or $evt.source -ne 'compact') { exit 0 }

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$snap = Join-Path $repo '.claude\last-compact-state.md'

Write-Output "Le contexte vient d'etre compacte. Le resume est une RECONSTITUTION : ne reprends"
Write-Output "aucun diagnostic comme acquis, re-derive-le depuis le code."
Write-Output ""

if (Test-Path $snap) {
    Write-Output "Etat MESURE juste avant le compactage (des faits, pas un resume) :"
    Write-Output ""
    Get-Content $snap | Select-Object -Skip 4
    Write-Output ""
}

Write-Output "Si tu conduis la campagne (dispatch d'agents, exploitation de la plateforme,"
Write-Output "migration de build), recharge le skill 'tacticus-orchestration' via l'outil Skill."
Write-Output "Il n'est PAS dans le CLAUDE.md : il est charge a la demande, expres."
