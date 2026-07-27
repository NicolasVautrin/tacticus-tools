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

# --- GARDE de synchronisation des symboles (residu #103 / O1) -----------------------------
#
# A CHAQUE demarrage de session, pas seulement apres un compactage : une mise a jour du jeu
# peut tomber entre deux sessions, et c'est precisement le moment ou l'on ne s'en doute pas.
#
# MUET quand tout est synchrone (--quiet). Il ne parle que pour dire qu'il y a un probleme
# -- ou que l'axe ghidra n'a PAS pu etre verifie (serveur eteint), ce qui n'est pas un succes.
# Attente bornee a 6 s : un ghidra-mcp a moitie mort ne doit pas retenir le demarrage.
#
# Cout mesure : ~1,3 s, dont ~1,1 s de demarrage Python + sha256 du GameAssembly.dll (60 Mo).
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$sync = & python (Join-Path $repo 'scripts\python\symbols_sync.py') --quiet --ghidra-timeout 6 2>&1
if ($LASTEXITCODE -ne 0 -or $sync) {
    Write-Output ($sync -join "`n")
}

if (-not $evt -or $evt.source -ne 'compact') { exit 0 }

Write-Output "Contexte compacte. Si tu conduis la campagne (dispatch d'agents, exploitation de"
Write-Output "la plateforme, migration de build), recharge le skill 'tacticus-orchestration'"
Write-Output "via l'outil Skill : il n'est pas dans le CLAUDE.md, il se charge a la demande."
