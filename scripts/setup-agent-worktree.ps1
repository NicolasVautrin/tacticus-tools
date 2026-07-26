# setup-agent-worktree.ps1 — rend un worktree agent RUNNABLE (tache #63).
#
# Les worktrees (.claude/worktrees/agent-*) sont des checkouts propres SANS les data/
# gitignores (dumps gameconfig/i2, seeds BC, boards, state-files, ai-traces) dont dependent
# gameconfig.py, rl_duel.py, engine_agreement_stages.py et les probes. Ce script cree une
# JUNCTION Windows <worktree>\data -> <arbre principal>\data (pas de droits admin requis,
# meme volume). data/ reste PHYSIQUEMENT PARTAGE : les disciplines runner restent obligatoires
# (state-file a NOM UNIQUE par agent, dispose ses propres runners, MAX_RUNNERS).
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
    if ($item.LinkType) {
        Write-Error "data/ du worktree est un reparse point inattendu ($($item.LinkType)) - ne pas ecraser"
        exit 1
    }
    # Repertoire REEL. C'est le cas NORMAL d'un worktree frais depuis que data/symbols/ est
    # VERSIONNE (seule exception de data/) : git materialise data\symbols\ au checkout, AVANT
    # qu'on ait pu poser la junction. On ne peut donc plus refuser en bloc - mais on ne supprime
    # que si le contenu se reduit EXACTEMENT a du suivi-par-git deja present dans l'arbre
    # principal. Tout le reste (seeds BC, boards, state-files, ai-traces...) est gitignore, donc
    # SEUL du travail non reproductible : sa presence ici signale autre chose qu'un checkout
    # frais -> on s'arrete.
    $unexpected = @(Get-ChildItem -Force $Link | Where-Object { $_.Name -ne 'symbols' })
    if ($unexpected.Count -gt 0) {
        Write-Error ("data/ du worktree contient autre chose que symbols/ : " +
            ($unexpected.Name -join ', ') + " - contenu non versionne, refus de supprimer")
        exit 1
    }
    if (-not (Test-Path (Join-Path $Target "symbols"))) {
        Write-Error "data\symbols absent de l'arbre principal ($Target) - refus (la junction priverait le worktree de sa table de symboles)"
        exit 1
    }
    Remove-Item -Recurse -Force $Link
    Write-Output "data\symbols (checkout git) supprime du worktree -> remplace par la junction vers l'arbre principal"
}
New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null
Write-Output "OK: junction creee $Link -> $Target"
