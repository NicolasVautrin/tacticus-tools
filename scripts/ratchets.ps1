<#
.SYNOPSIS
    LA BANQUE DE CLIQUETS de tacticus-tools -- source UNIQUE, versionnee et EXECUTABLE.

.DESCRIPTION
    Un CLIQUET est un garde-fou offline, deterministe, a rejouer AVANT d'ouvrir une PR. Il
    n'atteste pas une tranche : il atteste que l'ARBRE n'a pas re-creuse un trou deja bouche.

    POURQUOI CE FICHIER EXISTE (#430). La liste des cliquets n'existait nulle part comme objet :
    elle vivait en PROSE dans `CLAUDE.md`, dans un `runpar.ps1` NON VERSIONNE du scratchpad de
    l'orchestrateur, et dans des case-docs qui en citaient des compositions INCOMPATIBLES (l'une
    5 entrees, l'autre 8 dont 4 hors banque). Aucun fichier du depot ne les contenait ensemble.
    C'est la cause d'EXECUTION derriere trois derives mesurees le 2026-08-01 (#420, #421, #427).

    LE POINT QUE #427 A ETABLI, PAR MESURE. Prouver sa couverture est NECESSAIRE ET NON
    SUFFISANT : `probe_313` avait DEJA cette forme -- sa preuve de couverture EST un test offline
    -- et a laisse passer deux derives, parce que dans ce depot << etre un test >> et << etre
    joue >> sont INDEPENDANTS (la suite complete est proscrite par `CLAUDE.md`, et un agent ne
    cible que les tests de SA tranche). Un cliquet doit donc etre dans une LISTE QU'ON LANCE.

    Demonstration immediate : au premier passage de cette banque, `probe_313` etait ROUGE sur
    `origin/master` -- `PathfinderType` et `KillUnitStep`, deux mirrors natifs VERBATIM, etaient
    entres dans `engine/` sans entrer a son registre. Corrige dans le meme commit.

    NE PAS RECOPIER CETTE LISTE AILLEURS. `CLAUDE.md` et les case-docs POINTENT ce fichier.
    Un cliquet neuf s'ajoute ICI, avec sa ligne << ce qu'il est SEUL a voir >>.

.PARAMETER List
    Imprime la banque en TSV (id, commande, rougit, seul-a-voir, doc) et sort. Aucun lancement.
    C'est la voie par laquelle la banque se DERIVE : `probe_439` la lit ici plutot que de
    recopier sa composition. Changer ces colonnes, c'est changer un contrat -- rejouer #439.

.PARAMETER Only
    Ne joue que ces ids (accepte le prefixe : `-Only probe_283` prend ses 6 etapes).

.PARAMETER Skip
    Exclut ces ids (meme regle de prefixe). A n'utiliser QUE pour un diagnostic local.

.PARAMETER ThrottleLimit
    Degre de parallelisme. 0 (defaut) = min(nombre de cliquets, nombre de coeurs). Les cliquets
    sont 100 % OFFLINE (aucun runner, aucun RPC, aucune session Frida) : le plafond de 4 du
    `CLAUDE.md` ne les concerne PAS -- il borne ce qui MONTE UN RUNNER.

.PARAMETER Serial
    Force le jeu en serie (equivaut a -ThrottleLimit 1). Pour un diagnostic, pas pour une PR.

.PARAMETER Lines
    Nombre de lignes d'extrait affichees par cliquet ROUGE (defaut 14).

.PARAMETER LogDir
    Ou deposer les logs complets. Defaut `<racine>/logs/ratchets` (gitignore).

.OUTPUTS
    Code de sortie = NOMBRE de cliquets rouges (0 = banque verte). Sortie ASCII stricte (cp1252).

.EXAMPLE
    pwsh -File scripts/ratchets.ps1
    pwsh -File scripts/ratchets.ps1 -Only probe_313,probe_283 -Serial
    pwsh -File scripts/ratchets.ps1 -List
#>
[CmdletBinding()]
param(
    [switch]   $List,
    [string[]] $Only,
    [string[]] $Skip,
    [int]      $ThrottleLimit = 0,
    [switch]   $Serial,
    [int]      $Lines = 14,
    [string]   $LogDir
)

# ==========================================================================================
#  LA BANQUE. Une entree = un cliquet. `Seul` dit ce que ce cliquet est SEUL a voir : c'est
#  le critere d'admission, avec le cout MARGINAL en parallele (jamais le cout absolu).
#
#  `Rougit` est FACULTATIF et n'a qu'une valeur admise : 'compteur'. Il DECLARE qu'une entree
#  est structurellement incapable de rendre un code non nul -- elle est la pour le contexte,
#  pas pour garder. C'est une declaration MACHINE, lue par `probe_439`, qui garde les DEUX
#  directions : une entree sans declaration qui ne peut pas rougir est ROUGE (le vice de #430
#  et #435), et une entree DECLAREE compteur qui se met a pouvoir rougir l'est aussi -- sa
#  declaration est MORTE. Ne jamais poser ce champ pour faire taire un cliquet casse.
# ==========================================================================================
$Ratchets = @(
    @{ Id = 'probe_181'; Argv = @('probe_181_targeting_gaps.py')
       Seul = 'une ability entree dans ABILITY_CLASSES SANS son masque TARGETING_OPTIONS (degradation PERMISSIVE, ni erreur ni crash)'
       Doc  = 'CLAUDE.md -- Entrer au registre SANS son masque de ciblage' }

    @{ Id = 'probe_120'; Argv = @('probe_120_pre_unit_ability_fork.py')
       Seul = 'etape 0 : une ability au registre SANS son litteral ABILITY_ATTACK_TYPE ; puis le de-fork du vecteur On(PreUnitAbility) sur la voie CAST'
       Doc  = 'CLAUDE.md -- Meme regle pour ABILITY_ATTACK_TYPE' }

    @{ Id = 'probe_273'; Argv = @('probe_273_gitignored_inputs.py', '--only-scan')
       Seul = 'un lecteur qui rend 0 au lieu de dire qu il ne voit pas ; et un chemin data/<x> construit qui ne designe pas une entree VERSIONNEE'
       Doc  = 'docs/rl/case-273-entrees-gitignorees.md ; CLAUDE.md invariant 3' }

    @{ Id = 'probe_319'; Argv = @('probe_319_scan_fidelity.py')
       Seul = 'la DEGRADATION du cliquet 273 lui-meme : fidelite du balayage (un fragment de chemin pris pour une lecture) et reproductibilite worktree vs arbre principal -- les deux etaient FAUSSES'
       Doc  = 'docs/rl/case-319 ; propose par #409-r1' }

    @{ Id = 'probe_365'; Argv = @('probe_365_versioned_imports_gitignored.py')
       Seul = 'un fichier VERSIONNE qui importe statiquement une cible GITIGNOREE ou absente -- le depot cesse d etre auto-constructible, et c est ce qui pousse les agents a fabriquer des junctions destructrices'
       Doc  = 'CLAUDE.md invariant 3 (JAMAIS DE JUNCTION)' }

    @{ Id = 'probe_391'; Argv = @('probe_391_conftest_dir_identity.py')
       Seul = 'un repertoire collecte DEUX fois par pytest dans une meme session : les fixtures de son conftest disparaissent pour le 3e argument, et le nodeid est IDENTIQUE (invisible a toute inspection par chaine)'
       Doc  = 'docs/rl/case-391-conftest-dir-identity.md' }

    @{ Id = 'probe_313'; Argv = @('probe_313_enum_mirror_bijection.py')
       Seul = 'un mirror IntEnum du moteur qui n est PLUS en bijection avec enums.tsv (manquant / mort / RENUMEROTE), et toute IntEnum entree sous engine/ sans etre appariee ni justifiee HORS-MIRROR'
       Doc  = 'docs/rl/case-313-enum-mirror-bijection.md ; case-318' }

    @{ Id = 'probe_229'; Argv = @('probe_229_effect_triggers_active.py')
       Seul = 'un effet-trigger de EFFECT_TRIGGERS qui ne lit pas EffectComponent.IsActive alors que son RAIL natif l exige (ou l inverse)'
       Doc  = 'docs/rl/case-229-effect-triggers-active-inventory.md' }

    @{ Id = 'probe_421'; Argv = @('probe_421_rail_covers_registry.py')
       Seul = 'la COUVERTURE du RAIL de probe_229 : une classe entree au registre sans entrer au rail (19 mesurees le 2026-08-01) -- 229 seul est muet sur ce qu il ne connait pas'
       Doc  = 'docs/rl/case-229-effect-triggers-active-inventory.md' }

    @{ Id = 'probe_366camo'; Argv = @('probe_366_camo_seed_inventory.py')
       Seul = 'un effet condition-gated INERTE a la capture : le canal decisionView le DROPPE, donc le port n a rien a rallumer quand la simulation le fait entrer dans sa condition'
       Doc  = 'docs/rl/case-366-r1-camo-seed.md' }

    @{ Id = 'probe_366pos'; Argv = @('probe_366r1_position_readers_census.py')
       Seul = 'les CINQ portes du foyer POSITION pour l etat << unite vivante sans position >> -- n en balayer qu une laisse passer les deux tiers des lecteurs'
       Doc  = 'docs/rl/case-366-r1-tunneling-horror-pending-summon.md' }

    @{ Id = 'probe_366bcp'; Argv = @('probe_366_r1_bcpatch_port_blindspot.py')
       Seul = 'une fixture qui patche dans le seed BC une variable d ability que le port lit DEPUIS gameconfig : desynchronisation ARMEE, inerte tant que l effet n est pas porte, FAUSSE le lendemain'
       Doc  = 'docs/rl/case-366-r1-bcpatch-port-blindspot.md' }

    @{ Id = 'probe_431'; Argv = @('probe_431_build_literals.py', '--cliquet')
       Seul = 'un hash de build ecrit en dur qui RESOUT un artefact du jeu (chemin de GameAssembly.dll, table de symboles, defaut de --build) HORS du foyer build_pin : le litteral court-circuite a la fois data/symbols/CURRENT et le binaire installe, donc symbols_sync peut etre VERT pendant que le script lit un autre build'
       Doc  = 'docs/rl/case-431-litteraux-de-build.md' }

    @{ Id = 'pytest_signatures'
       Argv = @('-m', 'pytest', 'tests/test_additional_hits_variant_signatures_offline.py', '-q')
       Seul = 'une implementation de SUBSTITUTION dont la signature derive derriere le port -- le rouge tombe alors ailleurs que sur la cause'
       Doc  = 'docs/rl/case-393-substitution-signature-drift.md' }

    # `probe_326_dsl_port_matching.py` ne peut PAS tenir ce poste : son `main` finit par un
    # `return 0` INCONDITIONNEL -- il INVENTORIE les verdicts, il n'en rougit d'aucun. Le seul
    # artefact executable qui rougit sur ce gisement est ce test-la (#435).
    @{ Id = 'pytest_attestations'
       Argv = @('-m', 'pytest', 'tests/test_337_dsl_triggers_attestation_offline.py', '-q')
       Seul = 'une primitive `DSLTriggers` retombee en CITE_A_QUALIFIER -- l aveu que l outil ne sait pas attribuer, jamais un verdict -- et une ligne de `docs/rl/dsl-port-attestations.tsv` devenue MORTE (symbole disparu du build, porteur/ancre deplace, porteur devenu MUET sur sa primitive) : une attestation non verifiee ment avec l autorite d une mesure'
       Doc  = 'docs/rl/case-337-dsl-triggers-attestation.md' }

    # --- probe_283, en SIX entrees. `--step all` est l UNION STRICTE de ces six (lire `main`),
    #     et chaque etape est independante. Le decoupage ne change RIEN a la couverture ; il rend
    #     le cout MARGINAL en parallele quasi nul : joue d un bloc, probe_283 DOUBLE le mur du lot
    #     (145 s -> 299 s, mesure du 2026-08-01) ; eclate, sa plus longue etape (prose, ~47 s)
    #     passe TRES en dessous du mur, qui ne bouge pas.
    #     `diff` et `on` sont des COMPTEURS (aucun `ko +=` : structurellement incapables de
    #     rougir). Ils restent dans la banque quand meme -- 9 s de CPU pour que la banque reste
    #     l EQUIVALENT EXACT de `--step all`, et pour qu un futur `ko +=` sur eux soit vu.
    #     Aucune ecriture sans `--fix` : les six s executent en lecture seule, sans collision.
    @{ Id = 'probe_283:diff'; Argv = @('probe_283_enum_ordinal_sweep.py', '--step', 'diff')
       Rougit = 'compteur'
       Seul = 'COMPTEUR : le diff des enums entre builds archives -- le contexte du verdict des cinq autres etapes'
       Doc  = 'docs/rl/case-283-quatre-enums-renumerotes.md' }
    @{ Id = 'probe_283:mirror'; Argv = @('probe_283_enum_ordinal_sweep.py', '--step', 'mirror')
       Seul = 'les mirrors des QUATRE enums renumerotes par la MAJ gqfc5mff6c -> rnca9r7q6c'
       Doc  = 'docs/rl/case-283-quatre-enums-renumerotes.md' }
    @{ Id = 'probe_283:exec'; Argv = @('probe_283_enum_ordinal_sweep.py', '--step', 'exec')
       Seul = 'un ordinal FIGE EN DUR dans du code EXECUTABLE qui designe un AUTRE membre depuis la MAJ -- ni erreur ni trace (mesure #272 : CAPTURE_POINT = 24 devenu MoltenForm, feuille rendant 0.0 en silence)'
       Doc  = 'docs/rl/case-272-capture-point-ordinal-perime.md' }
    @{ Id = 'probe_283:tables'; Argv = @('probe_283_enum_ordinal_sweep.py', '--step', 'tables')
       Seul = 'les tables de correspondance ordinal -> nom devenues fausses par renumerotation'
       Doc  = 'docs/rl/case-283-quatre-enums-renumerotes.md' }
    @{ Id = 'probe_283:prose'; Argv = @('probe_283_enum_ordinal_sweep.py', '--step', 'prose')
       Seul = 'une citation de decompile en commentaire/docstring dont l ordinal vaut EXACTEMENT celui du build precedent -- 220 invalidees par une MAJ SANS QU UNE SEULE LIGNE CHANGE, donc structurellement invisible a tout declencheur sur diff'
       Doc  = 'docs/rl/case-420-on-litteraux-perimes.md' }
    @{ Id = 'probe_283:on'; Argv = @('probe_283_enum_ordinal_sweep.py', '--step', 'on')
       Rougit = 'compteur'
       Seul = 'COMPTEUR : les litteraux On(<n>) stables vs decales'
       Doc  = 'docs/rl/case-283-quatre-enums-renumerotes.md' }

    # Le cliquet de la BANQUE elle-meme. Il est dans la banque, donc soumis a son propre critere.
    @{ Id = 'probe_439'; Argv = @('probe_439_cliquet_peut_rougir.py')
       Seul = 'un cliquet de CETTE banque incapable de rendre un code non nul -- il occupe la place d un garde-fou et s imprime comme << rien a signaler >> (3 occurrences, TOUTES trouvees a l oeil : probe_181 #430, probe_326 #435, et l audit manuel de #430 qui a rate la seconde)'
       Doc  = 'docs/rl/case-439-cliquet-peut-rougir.md' }
)

# ==========================================================================================
#  Moteur. Rien a editer ici pour ajouter un cliquet.
# ==========================================================================================
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$WorkDir = Join-Path $Root 'scripts\python'

function Convert-ToAscii([string] $s) {
    if ($null -eq $s) { return '' }
    return ($s -replace '[^\x20-\x7E\t]', '.')
}

if ($List) {
    Write-Output ("id`tcommande`trougit`tseul-a-voir`tdoc")
    foreach ($r in $Ratchets) {
        Write-Output ("{0}`tpython {1}`t{2}`t{3}`t{4}" -f `
            $r.Id, ($r.Argv -join ' '), [string] $r.Rougit, $r.Seul, $r.Doc)
    }
    exit 0
}

$sel = $Ratchets
if ($Only) { $sel = $sel | Where-Object { $id = $_.Id; ($Only | Where-Object { $id -eq $_ -or $id.StartsWith($_ + ':') }).Count -gt 0 } }
if ($Skip) { $sel = $sel | Where-Object { $id = $_.Id; ($Skip | Where-Object { $id -eq $_ -or $id.StartsWith($_ + ':') }).Count -eq 0 } }
$sel = @($sel)

if ($sel.Count -eq 0) {
    Write-Output "[ratchets] AUCUN cliquet selectionne. `-List` pour voir la banque."
    exit 1
}
if (-not (Test-Path $WorkDir)) {
    Write-Output ("[ratchets] repertoire introuvable : {0}" -f $WorkDir)
    exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Output "[ratchets] `python` introuvable dans le PATH (ne PAS utiliser `py` : il skippe des dependances)."
    exit 1
}

if (-not $LogDir) { $LogDir = Join-Path $Root 'logs\ratchets' }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$throttle = if ($Serial) { 1 } elseif ($ThrottleLimit -gt 0) { $ThrottleLimit }
            else { [Math]::Min($sel.Count, [Environment]::ProcessorCount) }

Write-Output ("[ratchets] {0} cliquet(s), parallelisme {1}, logs -> {2}" -f $sel.Count, $throttle, $LogDir)
Write-Output ""

$wall = [Diagnostics.Stopwatch]::StartNew()
$results = $sel | ForEach-Object -Parallel {
    $item = $_
    $wd = $using:WorkDir
    $ld = $using:LogDir
    $ErrorActionPreference = 'Continue'
    Set-Location $wd
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $out = & python @($item.Argv) 2>&1 | ForEach-Object { $_.ToString() }
    $rc = $LASTEXITCODE
    $sw.Stop()
    $logPath = Join-Path $ld (($item.Id -replace '[^A-Za-z0-9_.-]', '_') + '.log')
    Set-Content -Path $logPath -Value $out -Encoding utf8
    [pscustomobject]@{
        Id  = $item.Id; Rc = $rc; Sec = [Math]::Round($sw.Elapsed.TotalSeconds, 1)
        Cmd = 'python ' + ($item.Argv -join ' '); Seul = $item.Seul; Doc = $item.Doc
        Log = $logPath; Out = $out
    }
} -ThrottleLimit $throttle
$wall.Stop()

$results = @($results | Sort-Object -Property @{ Expression = { $_.Rc -eq 0 } }, @{ Expression = 'Sec'; Descending = $true })
$rouges = @($results | Where-Object { $_.Rc -ne 0 })

foreach ($r in $results) {
    $etat = if ($r.Rc -eq 0) { 'OK   ' } else { 'ROUGE' }
    Write-Output ("  {0}  {1,-22} {2,7} s   rc={3}" -f $etat, $r.Id, $r.Sec, $r.Rc)
}
Write-Output ""

# Motif de la CAUSE. Chaque alternative est ANCREE en debut de ligne ou porte un separateur :
# un motif large noie la cause sous les lignes VERTES du meme probe -- mesure #430, `MANQUANT`
# non ancre matchait les `MANQUANTS=0` de probe_313 et repoussait la seule ligne utile hors cadre.
$rxFail = 'AssertionError|Traceback|\bBLOQUANT|VERDICT:\s*FAIL|\]\s*ROUGE|[A-Za-z]Error:' +
          '|^\s*(E\s|FAILED\b|ROUGE\b|FAIL\b|MANQUANT\b|MORT\b|MORTE\b|INTROUVABLE\b|ORPHELINE\b|RENUMEROTE\b)'
foreach ($r in $rouges) {
    Write-Output ("=" * 88)
    Write-Output ("ROUGE  {0}   (rc={1}, {2} s)" -f $r.Id, $r.Rc, $r.Sec)
    Write-Output ("  commande      : cd scripts/python ; {0}" -f $r.Cmd)
    Write-Output ("  seul a voir   : {0}" -f (Convert-ToAscii $r.Seul))
    Write-Output ("  doc           : {0}" -f $r.Doc)
    Write-Output ("  log complet   : {0}" -f $r.Log)
    $nonVides = @($r.Out | Where-Object { $_.Trim() -ne '' })
    $lignes = @($nonVides | Where-Object { $_ -match $rxFail })
    # Repli : aucun motif reconnu (un cliquet neuf, un crash inattendu) -> la QUEUE du log.
    $depuisLaQueue = $lignes.Count -eq 0
    if ($depuisLaQueue) { $lignes = $nonVides }
    # Les lignes de CAUSE se lisent depuis le HAUT (la premiere faute explique les suivantes) ;
    # un repli sans motif se lit depuis le BAS (c'est la qu'un crash depose sa trace).
    $extrait = if ($depuisLaQueue) { @($lignes | Select-Object -Last $Lines) }
               else { @($lignes | Select-Object -First $Lines) }
    Write-Output "  --- extrait ---"
    foreach ($l in $extrait) { Write-Output ("  | " + (Convert-ToAscii $l)) }
    if ($lignes.Count -gt $extrait.Count) {
        Write-Output ("  | ... {0} ligne(s) de plus dans le log" -f ($lignes.Count - $extrait.Count))
    }
    # La derniere ligne porte SOUVENT le verdict chiffre (`1 ecart(s) BLOQUANT(s)`,
    # `1 failed, 5 passed`) -- mais pas toujours : elle est annoncee pour ce qu'elle est.
    if ($nonVides.Count -gt 0) {
        Write-Output ("  derniere ligne: " + (Convert-ToAscii $nonVides[-1]))
    }
}
if ($rouges.Count -gt 0) { Write-Output ("=" * 88) }

$mur = [Math]::Round($wall.Elapsed.TotalSeconds, 1)
if ($rouges.Count -eq 0) {
    Write-Output ("[ratchets] BANQUE VERTE -- {0} cliquet(s), mur {1} s." -f $sel.Count, $mur)
} else {
    Write-Output ("[ratchets] BANQUE ROUGE -- {0}/{1} cliquet(s) : {2}. Mur {3} s." `
        -f $rouges.Count, $sel.Count, (($rouges | ForEach-Object { $_.Id }) -join ', '), $mur)
}
exit $rouges.Count
