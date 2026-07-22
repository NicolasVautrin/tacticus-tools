# setup-agent-worktree.ps1 — rend un worktree agent RUNNABLE (tache #63).
#
# Les worktrees (.claude/worktrees/agent-*) sont des checkouts propres SANS les data/
# gitignores (dumps gameconfig/i2, seeds BC, boards, state-files, ai-traces) dont dependent
# gameconfig.py, rl_duel.py, engine_agreement_stages.py et les probes. Ce script cree une
# JUNCTION Windows <worktree>\data -> <arbre principal>\data (pas de droits admin requis,
# meme volume). data/ reste PHYSIQUEMENT PARTAGE : les disciplines runner restent obligatoires
# (state-file a NOM UNIQUE par agent, dispose ses propres runners, MAX_RUNNERS=10).
#
# Usage (depuis n'importe ou) :
#   powershell -File C:\Users\nicolasv\tacticus-tools\scripts\setup-agent-worktree.ps1 [-WorktreePath <chemin>]
#   (defaut : repertoire courant = le worktree de l'agent)
# Equivalent Git Bash :
#   cd <worktree> && cmd //c "mklink /J data C:\Users\nicolasv\tacticus-tools\data"

param([string]$WorktreePath = (Get-Location).Path)

$Main = "C:\Users\nicolasv\tacticus-tools"
$Target = Join-Path $Main "data"
$Link = Join-Path $WorktreePath "data"

if (-not (Test-Path (Join-Path $WorktreePath ".git"))) {
    Write-Error "Pas un worktree git : $WorktreePath"
    exit 1
}
if ((Resolve-Path $WorktreePath).Path -eq $Main) {
    Write-Output "SKIP: $WorktreePath est l'arbre principal (data/ reel deja present)"
    exit 0
}
if (Test-Path $Link) {
    $item = Get-Item $Link -Force
    if ($item.LinkType -eq "Junction") {
        Write-Output "OK (deja en place): $Link -> $($item.Target)"
        exit 0
    }
    Write-Error "data/ existe deja dans le worktree et n'est PAS une junction ($($item.LinkType)) - ne pas ecraser"
    exit 1
}
New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null
Write-Output "OK: junction creee $Link -> $Target"
