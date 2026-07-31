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

    # ORIGINE : resolue plus bas par LOOKUP DE PARENTE (voir $parentDe). Un agent peut en lancer
    # un AUTRE -- le CLAUDE.md l'autorise (« un agent lance couramment un re-expert ») -- et un
    # ENFANT n'est PAS un dispatch de l'orchestrateur : il fait partie du travail de son parent
    # et ne consomme aucun slot du plafond.
    $origine = "?"

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

# --- LOOKUP DE PARENTE -------------------------------------------------------------------
# Celui qui LANCE voit l'agentId du lance : le `tool_result` de son appel `Agent` le contient
# verbatim (« Async agent launched successfully ... agentId: <id> »). Donc :
#   * l'id apparait dans un AUTRE `subagents/agent-*.jsonl`  -> ENFANT, et ce fichier est son PARENT ;
#   * l'id n'apparait nulle part ailleurs                    -> lance par l'ORCHESTRATEUR (le
#     tool_result vit alors dans le transcript de la session principale, hors de subagents/).
# C'est une PREUVE, pas une heuristique -- et elle survit au compact, contrairement au decompte
# de tete ou a une convention de redaction des briefs.
# (Mesure du 2026-07-31 : `isSidechain`, `cwd` et `slug` sont IDENTIQUES chez parent et enfant --
#  aucun champ de metadonnee ne les separe. Il faut ce lookup.)
$ids = $rows.id
if ($ids) {
    $recents = Get-ChildItem $subDir -Filter "agent-*.jsonl" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-6) }
    foreach ($f in $recents) {
        $moi = $f.BaseName -replace '^agent-', ''
        $autres = @($ids | Where-Object { $_ -ne $moi })       # jamais se citer soi-meme
        if (-not $autres) { continue }
        # /!\ DEUX pieges, tous deux VECUS :
        #  1. `Select-String -SimpleMatch` ne peuple PAS `$_.Matches` -> la boucle recolte du vide
        #     et tout ressort « MOI ». On lit le fichier UNE fois et on teste par .Contains().
        #  2. Une simple MENTION de l'id n'est PAS une preuve de filiation : les agents lancent
        #     `git worktree list`, dont la sortie contient TOUS les ids. Chercher l'id nu produit
        #     un faux positif massif et meme des CYCLES (A enfant de B et B enfant de A).
        #     Le marqueur qui prouve le LANCEMENT est la chaine exacte du tool_result :
        #         agentId: <id> (internal ID - ...
        #     Le champ JSON du transcript de l'enfant lui-meme s'ecrit `"agentId":"<id>"` (sans
        #     espace, entre guillemets) : les deux formes ne se confondent pas.
        $txt = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $txt) { continue }
        foreach ($a in $autres) {
            if ($txt.Contains("agentId: $a")) {
                ($rows | Where-Object { $_.id -eq $a }) |
                    ForEach-Object { $_.origine = "enf. de $($moi.Substring(0,8))" }
            }
        }
    }
}
$rows | Where-Object { $_.origine -eq "?" } | ForEach-Object { $_.origine = "MOI" }

$rows | Sort-Object enVol, origine -Descending |
    Format-Table id, origine, lock, age, lance, retard, porte, etat -AutoSize | Out-String | Write-Output

# Le plafond porte sur MES dispatches. Les enfants sont comptes a part : ils tournent, ils
# consomment de la concurrence, mais ils n'ouvrent ni ne ferment un slot.
$vol = @($rows | Where-Object { $_.enVol -and $_.origine -eq "MOI" }).Count
$enfants = @($rows | Where-Object { $_.enVol -and $_.origine -ne "MOI" }).Count
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
