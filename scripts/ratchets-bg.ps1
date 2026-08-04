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

.PARAMETER Since
    Transmis a `ratchets.ps1` : `probe_457` ne rejoue que les fichiers de test IMPACTES par le diff
    `<ref>..HEAD` (empreinte MESUREE + graphe d'imports, tout doute rejouant TOUT). C'est la forme
    normale de la boucle de merge -- passer la BASE de la PR fusionnee.
    ⚠ Ne remplace pas un run complet : garder un run SANS `-Since` une fois par session.

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
    [string[]] $Only,
    [string]   $Since
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

# --- VERROU DE RUN (#472) ---------------------------------------------------------------------
# Ce qui permet a un lecteur (`loop_status`) de distinguer « la pointe n'est PAS ENCORE jugee » de
# « la banque la juge EN CE MOMENT ». Sans ce fait, les deux se ressemblent : aucun verdict.
#
# LE FAIT EST LE HANDLE, pas le fichier. Ouvert en partage LECTURE SEULE et garde pendant tout le
# run, il ne peut etre ouvert en ECRITURE par personne d'autre tant que ce processus vit ; et l'OS
# le libere TOUJOURS a sa mort, donc un run tue (kill, reboot, fenetre fermee) laisse un fichier
# OUVRABLE -- un RESIDU, jamais un « EN COURS » perpetuel. Ni un PID (recyclable) ni un age (une
# banque lente est un run lent, pas un run mort) ne donneraient cette propriete.
#
# Il vit a cote des VERDICTS, pas dans le tmpdir systeme ou vit le worktree : Python et .NET ne
# resolvent pas `TEMP`/`TMP` dans le meme ordre, et un desaccord y serait SILENCIEUX.
$dirRuns = Join-Path $dirVerdict 'runs'
New-Item -ItemType Directory -Force -Path $dirRuns | Out-Null

# Nettoyage OPPORTUNISTE des residus -- meme fait, meme test : ouvrable en ecriture == plus
# personne ne le tient. Sans lui, chaque run tue laisserait un fichier a vie.
foreach ($vieux in @(Get-ChildItem -LiteralPath $dirRuns -Filter '*.lock' -ErrorAction SilentlyContinue)) {
    try {
        $f = [System.IO.File]::Open($vieux.FullName, 'Open', 'Write', 'None')
        $f.Close(); $f.Dispose()
        Remove-Item -LiteralPath $vieux.FullName -Force -ErrorAction SilentlyContinue
    } catch { }        # tenu par un run VIVANT : on n'y touche pas
}

$verrouRun = Join-Path $dirRuns "$court-$stamp.lock"
$fluxRun = $null
try {
    $fluxRun = [System.IO.File]::Open($verrouRun, 'Create', 'Write', 'Read')
    $octetsRun = [System.Text.Encoding]::UTF8.GetBytes(
        "commit : $sha`npid    : $PID`ndebut  : $stamp`nrepo   : $repo`n")
    $fluxRun.Write($octetsRun, 0, $octetsRun.Length)
    $fluxRun.Flush()
} catch {
    # Degradation SUE et DITE : le lecteur lira « NON JUGEE » au lieu de « EN COURS ». C'est le
    # bon sens de la degradation -- « la pointe n'est pas jugee » reste VRAI dans les deux cas.
    $fluxRun = $null
    Write-Host "[ratchets-bg] verrou de run NON POSE ($($_.Exception.Message)) -- un lecteur dira NON JUGEE"
}

# Tmpdir SYSTEME -- surtout pas sous le depot, ni sous `.claude/worktrees` (un cliquet joue depuis
# l'arbre principal y lirait le code des autres agents, #434).
#
# WORKTREE PERSISTANT, et c'est ce qui rend les 88 s de froid. Un worktree NEUF presente au filtre
# systeme 1608 fichiers .py inconnus : mesure du 2026-08-03, banque complete a 293,1 s sur arbre
# neuf contre 205,2 s sur arbre chaud. En REUTILISANT le meme repertoire on ne presente au filtre
# que les fichiers REELLEMENT changes par le commit -- c'est-a-dire le diff de la PR, une poignee.
# Repli sur un worktree jetable horodate si le persistant est deja pris (deux runs simultanes) :
# correct, seulement plus lent.
$racineTmp = [System.IO.Path]::GetTempPath()
$wtPersistant = Join-Path $racineTmp 'ratchets-bg-wt'
$verrou = Join-Path $racineTmp 'ratchets-bg-wt.lock'

$fluxVerrou = $null
try {
    $fluxVerrou = [System.IO.File]::Open($verrou, 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
    $fluxVerrou = $null
}

if ($fluxVerrou) {
    $wt = $wtPersistant
    $jetable = $false
} else {
    $wt = Join-Path $racineTmp ("ratchets-bg-" + $court + "-" + $stamp)
    $jetable = $true
}

$lignes = [System.Collections.Generic.List[string]]::new()
function Note([string] $s) { $lignes.Add($s); Write-Host $s }

Note "[ratchets-bg] commit  $court  $sujet"
Note ("[ratchets-bg] worktree {0}  ({1})" -f $wt, $(if ($jetable) { 'JETABLE -- le persistant est pris' } else { 'persistant' }))

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
    $sommet = if (Test-Path $wt) { (git -C $wt rev-parse --show-toplevel 2>$null) } else { $null }
    if ($sommet) { $sommet = $sommet.Trim().Replace('/', '\') }
    $reutilisable = $sommet -and ($sommet.TrimEnd('\') -ieq $wt.TrimEnd('\'))

    # Garde-fou : on ne fait JAMAIS un checkout forcé ailleurs que dans notre propre worktree.
    if ($sommet -and -not $reutilisable) {
        throw "$wt appartient a un autre arbre ($sommet) -- refus d'y toucher"
    }

    if ($reutilisable) {
        git -C $wt checkout --detach --force --quiet $sha
        if ($LASTEXITCODE -ne 0) { throw "checkout dans le worktree persistant a echoue (rc $LASTEXITCODE)" }
        Note "[ratchets-bg] worktree REUTILISE -- seuls les fichiers du diff sont neufs pour le filtre"
    } else {
        if (Test-Path $wt) { Remove-Item -Recurse -Force $wt }
        git -C $repo worktree prune
        git -C $repo worktree add --detach --quiet $wt $sha
        if ($LASTEXITCODE -ne 0) { throw "git worktree add a echoue (rc $LASTEXITCODE)" }
        Note "[ratchets-bg] worktree CREE -- premier run : l'arbre entier est froid pour le filtre"
    }

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
    if ($Only)  { $argv += @('-Only', ($Only -join ',')) }
    if ($Since) { $argv += @('-Since', $Since) }

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
    if (-not $jetable -and -not $KeepWorktree) {
        # Le persistant est GARDE volontairement : c'est lui qui evite de re-presenter 1608
        # fichiers inconnus au filtre systeme a chaque run. `-KeepWorktree` reste sans effet ici.
        Note "[ratchets-bg] worktree persistant conserve (c'est ce qui rend les ~88 s de froid)"
    }
    elseif ($KeepWorktree) {
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
    if ($fluxVerrou) { $fluxVerrou.Close(); $fluxVerrou.Dispose(); $fluxVerrou = $null }
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

# ⚠ LES PARENTHESES AUTOUR DU `-f` SONT LOAD-BEARING. La virgule lie PLUS FORT que l'operateur de
# format : sans elles, PowerShell parse `@("commit..","sujet..","quand..","mur {0:N1} s") -f ($mur,
# "rc      : $rc  ($etat)", '')`, joint le tableau de gauche par des espaces et l'applique comme UN
# SEUL format -- l'en-tete devenait une ligne unique et **la ligne `rc` disparaissait purement et
# simplement**. Mesure du 2026-08-04 : les 3 verdicts presents sur disque n'en portaient AUCUNE, et
# tout lecteur automatique du verdict rendait donc « rc inconnu » sur un fichier d'apparence normale.
$entete = @(
    "commit  : $sha",
    "sujet   : $sujet",
    "quand   : $stamp",
    ("mur     : {0:N1} s" -f $mur),
    "rc      : $rc  ($etat)",
    ''
)
Set-Content -LiteralPath $verdict -Value ($entete + $lignes) -Encoding utf8
Write-Host "[ratchets-bg] verdict -> $verdict"

# Le verrou tombe APRES l'ecriture du verdict, et c'est l'ordre qui compte : entre les deux, un
# lecteur doit voir « EN COURS », jamais « NON JUGEE » alors que le verdict arrive.
if ($fluxRun) { $fluxRun.Close(); $fluxRun.Dispose(); $fluxRun = $null }
Remove-Item -LiteralPath $verrouRun -Force -ErrorAction SilentlyContinue

exit $rc
