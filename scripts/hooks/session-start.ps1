# Hook SessionStart -- rappelle de recharger le skill orchestrateur apres un compactage.
#
# POURQUOI ICI ET PAS SUR PostCompact : seuls UserPromptSubmit, UserPromptExpansion et
# SessionStart voient leur stdout REINJECTE dans le contexte. PostCompact est classe
# "no decision control -- side effects" : il peut jouer un son, pas remettre du contexte.
#
# MUET hors compactage (`source != "compact"`) : au demarrage normal le CLAUDE.md suffit.
#
# ASCII STRICT : PowerShell 5.1 lit ce fichier en ANSI ; un tiret long ou un accent y casse
# la chaine et fait echouer le hook.

$ErrorActionPreference = 'SilentlyContinue'
$evt = try { [Console]::In.ReadToEnd() | ConvertFrom-Json } catch { $null }
if (-not $evt -or $evt.source -ne 'compact') { exit 0 }

Write-Output "Contexte compacte. Si tu conduis la campagne (dispatch d'agents, exploitation de"
Write-Output "la plateforme, migration de build), recharge le skill 'tacticus-orchestration'"
Write-Output "via l'outil Skill : il n'est pas dans le CLAUDE.md, il se charge a la demande."
