<#
.SYNOPSIS
    Joue la banque de cliquets SUR UN COMMIT FIGE, dans un worktree jetable, hors du chemin critique.

.DESCRIPTION
    La banque coute ~205 s de mur. Jouee en bloquant apres chaque merge, elle serialise la boucle de
    livraison ; jouee toutes les N PR, elle perd l'ATTRIBUTION -- et c'est l'attribution qui vaut,
    pas la frequence (mesure du 2026-08-03 : sur 6 rouges historiques, UN SEUL venait du changement
    en cours de validation ; les deux rouges REELS etaient des regressions de merges ANTERIEURS
    passes verts, trouvees en AJOUTANT un cliquet, pas en rejouant les existants).

    Ce script garde l'attribution a 1 PR et rend le mur invisible : il epingle un commit dans un
    worktree jetable et y joue la banque, pendant que l'arbre principal passe a la PR suivante.

    A lancer en arriere-plan (`run_in_background`, ou `Start-Process`). Le verdict atterrit dans
    `logs/ratchets-bg/<court>-<horodatage>.txt` de l'ARBRE PRINCIPAL, gitignore.

.PARAMETER Commit
    Le commit a juger. Defaut : HEAD. Accepte tout ce que `git rev-parse` comprend.

.PARAMETER KeepWorktree
    Conserve le worktree apres le run (diagnostic d'un rouge). Sinon il est retire.

.PARAMETER Only
    Transmis tel quel a `ratchets.ps1` (accepte le prefixe : `-Only probe_283` prend ses 6 etapes).
    Utile pour bisecter un cliquet fautif : `git bisect run pwsh -File scripts/ratchets-bg.ps1 -Only probe_313`.

.EXAMPLE
    pwsh -File scripts/ratchets-bg.ps1
    pwsh -File scripts/ratchets-bg.ps1 -Commit 50f0404a -Only probe_313

.NOTES
    JAMAIS de junction ni de lien symbolique vers l'arbre principal (sous Windows, une suppression
    recursive forcee SUIT le point de reparse et vide la CIBLE -- 67 modules deja detruits par cette
    voie le 2026-07-31). Le worktree vit dans le tmpdir SYSTEME, jamais sous le depot : un cliquet
    ni un test n'ecrit dans `scripts/python/`, que la banque enumere en parallele (#455).
#>
[CmdletBinding()]
param(
    [string]   $Commit = 'HEAD',
    [switch]   $KeepWorktree,
    [string[]] $Only
)

$ErrorActionPreference = 'Stop'

$repo = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if (-not $repo) { throw "pas un depot git : $PSScriptRoot" }

$sha = (git -C $repo rev-parse --verify "$Commit^{commit}" 2>$null)
if (-not $sha) { throw "commit introuvable : $Commit" }
$sha = $sha.Trim()
$court = $sha.Substring(0, 8)
$sujet = (git -C $repo log -1 --format='%s' $sha).Trim()

# Le verdict va dans l'ARBRE PRINCIPAL (le worktree, lui, disparait avec son `logs/`).
$dirVerdict = Join-Path $repo 'logs\ratchets-bg'
New-Item -ItemType Directory -Force -Path $dirVerdict | Out-Null
$stamp = (Get-Date -Format 'yyyyMMdd-HHmmss')
$verdict = Join-Path $dirVerdict "$court-$stamp.txt"

# Tmpdir SYSTEME -- surtout pas sous le depot.
$wt = Join-Path ([System.IO.Path]::GetTempPath()) ("ratchets-bg-" + $court + "-" + $stamp)

$lignes = [System.Collections.Generic.List[string]]::new()
function Note([string] $s) { $lignes.Add($s); Write-Host $s }

Note "[ratchets-bg] commit  $court  $sujet"
Note "[ratchets-bg] worktree $wt"

# Ce script juge un COMMIT, jamais le working tree -- c'est precisement ce qui garde
# l'attribution a 1 PR quand l'arbre principal est deja passe a la suivante. Corollaire qu'il
# faut DIRE, parce qu'on s'y fait prendre : un correctif non commite est INVISIBLE ici, et le
# verdict porte alors sur du code anterieur.
$sale = @(git -C $repo status --porcelain --untracked-files=no)
if ($sale.Count -gt 0) {
    Note "[ratchets-bg] ATTENTION : $($sale.Count) fichier(s) suivis MODIFIES et NON COMMITES dans"
    Note "[ratchets-bg] l'arbre principal. Ils ne sont PAS dans ce verdict -- il juge $court."
}

$rc = 99
$t0 = Get-Date
try {
    git -C $repo worktree add --detach --quiet $wt $sha
    if ($LASTEXITCODE -ne 0) { throw "git worktree add a echoue (rc $LASTEXITCODE)" }

    # Les poids d'ordonnancement (LPT + shardage par cout) vivent dans `logs/`, GITIGNORE : un
    # checkout frais retomberait sur le repli md5 -- mur sous-optimal, verdict INCHANGE. On les
    # recopie pour que le run de fond ait le meme profil que celui de l'arbre principal.
    $poidsSrc = Join-Path $repo 'logs\ratchets'
    if (Test-Path $poidsSrc) {
        $poidsDst = Join-Path $wt 'logs\ratchets'
        New-Item -ItemType Directory -Force -Path $poidsDst | Out-Null
        Copy-Item (Join-Path $poidsSrc '*.json') $poidsDst -ErrorAction SilentlyContinue
        Note "[ratchets-bg] poids d'ordonnancement recopies"
    } else {
        Note "[ratchets-bg] AUCUN poids a recopier -- repli md5, mur sous-optimal, verdict inchange"
    }

    $argv = @('-File', (Join-Path $wt 'scripts\ratchets.ps1'))
    if ($Only) { $argv += @('-Only', ($Only -join ',')) }

    Push-Location $wt
    try { $sortie = & pwsh @argv 2>&1; $rc = $LASTEXITCODE }
    finally { Pop-Location }

    foreach ($l in $sortie) { $lignes.Add([string] $l) }
    Write-Host ($sortie -join [Environment]::NewLine)
}
catch {
    $rc = 99
    Note "[ratchets-bg] ECHEC DU MONTAGE : $($_.Exception.Message)"
    Note "[ratchets-bg] rc=99 signale un echec de MONTAGE, PAS un gisement rouge -- ne pas le lire"
    Note "[ratchets-bg] comme un verdict sur le commit (cf. 'un echec RENDU se lit comme une mesure')."
}
finally {
    if ($KeepWorktree) {
        Note "[ratchets-bg] worktree CONSERVE : $wt"
    } elseif (Test-Path $wt) {
        # Garde-fou : une suppression recursive forcee SUIT les points de reparse. On n'en cree
        # jamais, donc en trouver un signifie que quelque chose d'anormal est arrive -> on
        # s'abstient plutot que de vider une cible partagee.
        $reparse = Get-ChildItem -LiteralPath $wt -Recurse -Force -ErrorAction SilentlyContinue |
                   Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } |
                   Select-Object -First 1
        if ($reparse) {
            Note "[ratchets-bg] POINT DE REPARSE trouve ($($reparse.FullName)) -- worktree CONSERVE."
            Note "[ratchets-bg] Le retirer de force suivrait le lien et viderait sa CIBLE. A traiter a la main."
        } else {
            git -C $repo worktree remove --force $wt 2>&1 | Out-Null
            if (Test-Path $wt) { Note "[ratchets-bg] worktree NON retire : $wt" }
        }
    }
}

$mur = ((Get-Date) - $t0).TotalSeconds

# Trois issues DISTINCTES, et les confondre est le vice que `#457-r7` nomme : un rc d'USAGE ou un
# echec de MONTAGE ne dit RIEN sur le depot, alors qu'un rouge, si. Les rabattre sur « rouge »
# ferait passer « rien n'a tourne » pour un verdict.
$etat = switch ($rc) {
    0       { 'VERTE' }
    64      { 'USAGE -- RIEN JOUE, aucun verdict sur le depot' }
    99      { 'MONTAGE EN ECHEC -- aucun verdict sur le depot' }
    default { "ROUGE ($rc)" }
}
Note ("[ratchets-bg] {0} -- commit {1}, {2:N1} s" -f $etat, $court, $mur)

$entete = @(
    "commit  : $sha",
    "sujet   : $sujet",
    "quand   : $stamp",
    "mur     : {0:N1} s" -f $mur,
    "rc      : $rc  ($etat)",
    ''
)
Set-Content -LiteralPath $verdict -Value ($entete + $lignes) -Encoding utf8
Write-Host "[ratchets-bg] verdict -> $verdict"

exit $rc
