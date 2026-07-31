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
$rows = @()
foreach ($line in (git worktree list)) {
    if ($line -notmatch "worktrees[\\/]agent-([0-9a-f]+)") { continue }
    $id = $matches[1]
    $locked = $line -match "locked"
    $j = Get-Item (Join-Path $subDir "agent-$id.jsonl") -ErrorAction SilentlyContinue
    $age = if ($j) { [math]::Round(((Get-Date) - $j.LastWriteTime).TotalMinutes, 1) } else { $null }
    $enVol = ($age -ne $null -and $age -lt $FreshMin)
    $rows += [pscustomobject]@{
        id     = $id
        lock   = if ($locked) { "oui" } else { "non" }
        age    = if ($age -ne $null) { "$age min" } else { "aucun" }
        etat   = if ($enVol) { "EN VOL" } else { "abandonne / reserve" }
        enVol  = $enVol
    }
}

$rows | Sort-Object enVol -Descending | Format-Table id, lock, age, etat -AutoSize | Out-String | Write-Output

$vol = @($rows | Where-Object { $_.enVol }).Count
$libres = $Cap - $vol
Write-Output "EN VOL : $vol / $Cap"
if ($libres -gt 0) {
    Write-Output ">>> $libres SLOT(S) LIBRE(S) -- dispatcher AVANT de rendre la main."
} elseif ($libres -lt 0) {
    Write-Output ">>> AU-DESSUS DU PLAFOND ($([math]::Abs($libres)) de trop) -- ne rien lancer, ne RIEN tuer non plus."
} else {
    Write-Output ">>> plafond tenu."
}
