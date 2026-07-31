# Decompte EXACT de la flotte d'agents : JOINTURE worktrees x transcripts.
#
# Pourquoi une jointure, et pas l'un des deux seuls (mesure du 2026-07-31) :
#   * worktrees SEULS  -> comptent les worktrees ABANDONNES (agents tombes, WIP garde en reserve).
#                         Mesure : 3 worktrees inactifs depuis 161 a 501 min comptes « en vol ».
#   * transcripts SEULS -> comptent les agents FINIS dont le worktree est deja nettoye, et
#                         remontent des CENTAINES d'agents historiques (500+ fichiers).
#   => EN VOL == worktree PRESENT **ET** transcript ecrit il y a moins de $FreshMin minutes.
#
# Usage : powershell -File scripts\fleet-count.ps1 [-FreshMin 15] [-Cap 5]

param([int]$FreshMin = 15, [int]$Cap = 5)

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# La session courante est celle dont le repertoire subagents/ a ete ecrit le plus recemment.
$projDir = Join-Path $HOME ".claude\projects\C--Users-nicolasv-tacticus-tools"
$subDir = Get-ChildItem $projDir -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "subagents" } |
    Where-Object { Test-Path $_ } |
    Sort-Object { (Get-Item $_).LastWriteTime } -Descending |
    Select-Object -First 1

if (-not $subDir) { Write-Output "AUCUN repertoire subagents/ trouve"; exit 2 }

# Cote WORKTREE : l'ensemble de reference. On ne regarde QUE ces ids -- c'est ce qui evite
# de balayer les centaines de transcripts historiques.
#
# L'ANCRE (le commit sur lequel le worktree est pose) est le TROISIEME indicateur, et il
# repond a ce que les deux autres taisent :
#   * `base` (merge-base avec master) = le commit de LANCEMENT -> quand l'agent est parti,
#     et sur quelle version du code il raisonne ;
#   * `retard` (commits de master absents de sa base) = son degre de PEREMPTION -- c'est ce
#     qu'il devra rebaser, et au-dela de quelques dizaines c'est un signal de re-brief ;
#   * `commits` (base..head) = a-t-il ECRIT ? Un worktree a 0 commit ne porte RIEN : sa
#     suppression ne detruit rien. Un worktree a N commits non mergees est une RESERVE.
$rows = @()
foreach ($line in (git worktree list)) {
    if ($line -notmatch "worktrees[\\/]agent-([0-9a-f]+)\s+([0-9a-f]+)") { continue }
    $id = $matches[1]; $head = $matches[2]
    $locked = $line -match "locked"
    $jPath = Join-Path $subDir "agent-$id.jsonl"
    $j = Get-Item $jPath -ErrorAction SilentlyContinue
    $age = if ($j) { [math]::Round(((Get-Date) - $j.LastWriteTime).TotalMinutes, 1) } else { $null }
    $enVol = ($age -ne $null -and $age -lt $FreshMin)

    # ORIGINE -- un agent peut en lancer un AUTRE (le CLAUDE.md l'autorise : « un agent lance
    # couramment un re-expert »). Un ENFANT n'est PAS un dispatch de l'orchestrateur : il fait
    # partie du travail de son parent et ne consomme pas un slot du plafond.
    # /!\ AUCUNE metadonnee ne distingue parent et enfant : `isSidechain`, `cwd` et `slug` sont
    #     IDENTIQUES pour les deux (mesure du 2026-07-31). Le seul discriminant durable est le
    #     PROMPT, et il ne tient que parce que l'orchestrateur ouvre TOUS ses briefs par
    #     `Tache #NNN --`. C'est une convention a preserver : sans elle, le decompte redevient
    #     dependant du contexte de la conversation (donc perdu au compact).
    $origine = "?"
    if ($j) {
        $l1 = Get-Content $jPath -TotalCount 1 -ErrorAction SilentlyContinue
        if ($l1) {
            $c = ($l1 | ConvertFrom-Json).message.content
            if ($c -is [array]) { $c = ($c | Where-Object { $_.type -eq 'text' } | Select-Object -First 1).text }
            $origine = if ($c -match '^\s*Tache #\d+') { "MOI" } else { "enfant" }
        }
    }

    $base = git merge-base $head master 2>$null
    $commits = if ($base) { [int](git rev-list --count "$base..$head" 2>$null) } else { 0 }
    $retard = if ($base) { [int](git rev-list --count "$head..master" 2>$null) } else { 0 }
    $lance = if ($base) { git log -1 --format="%cr" $base } else { "?" }

    # Verdict de CONSERVATION (independant de « en vol ») :
    #   0 commit          -> ne porte rien, suppression sans perte
    #   N commits         -> RESERVE : verifier avant de supprimer
    # /!\ `merge-base --is-ancestor` ne voit PAS un CHERRY-PICK (SHA different) : un worktree
    #     dont le CONTENU a ete recolte apparait quand meme « non merge ». C'est une borne
    #     BASSE -- ne jamais supprimer sur ce seul critere.
    $porte = if ($commits -eq 0) { "rien" } else { "$commits commit(s)" }

    $rows += [pscustomobject]@{
        id      = $id
        origine = $origine
        lock    = if ($locked) { "oui" } else { "non" }
        age     = if ($age -ne $null) { "$age min" } else { "aucun" }
        lance   = $lance
        retard  = $retard
        porte   = $porte
        etat    = if ($enVol) { "EN VOL" } else { "abandonne / reserve" }
        enVol   = $enVol
    }
}

$rows | Sort-Object enVol, origine -Descending |
    Format-Table id, origine, lock, age, lance, retard, porte, etat -AutoSize | Out-String | Write-Output

# Le plafond porte sur MES dispatches. Les enfants sont comptes a part : ils tournent, ils
# consomment de la concurrence, mais ils n'ouvrent ni ne ferment un slot.
$vol = @($rows | Where-Object { $_.enVol -and $_.origine -ne "enfant" }).Count
$enfants = @($rows | Where-Object { $_.enVol -and $_.origine -eq "enfant" }).Count
if ($enfants) { Write-Output "(+ $enfants agent(s) ENFANT en vol, lances par un agent -- hors plafond)" }
$libres = $Cap - $vol
Write-Output "EN VOL : $vol / $Cap"
if ($libres -gt 0) {
    Write-Output ">>> $libres SLOT(S) LIBRE(S) -- dispatcher AVANT de rendre la main."
} elseif ($libres -lt 0) {
    Write-Output ">>> AU-DESSUS DU PLAFOND ($([math]::Abs($libres)) de trop) -- ne rien lancer, ne RIEN tuer non plus."
} else {
    Write-Output ">>> plafond tenu."
}
