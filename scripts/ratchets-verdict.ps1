<#
.SYNOPSIS
    LE TRI-ETAT d'un cliquet -- l'unique table qui traduit un code de sortie en ETAT, et le seul
    endroit ou se calcule le code de sortie de la banque. Dot-source, jamais recopie.

.DESCRIPTION
    LE DEFAUT QUE CE FICHIER FERME (#471)
    -------------------------------------
    `ratchets.ps1` rabattait TOUT rc non nul sur `ROUGE` et le comptait dans `$rouges.Count`.
    Un cliquet qui n'avait RIEN PU MESURER etait donc indistinguable d'un cliquet qui avait
    mesure et trouve un trou.

    MESURE qui l'a revele (2026-08-04, banque sur `d2ede23d`) : `BANQUE ROUGE -- 1/40 cliquet(s) :
    probe_457:s3`. Cette tranche-la n'a joue AUCUN test -- elle a crashe en 4,5 s dans son propre
    montage, sur `git ls-files scripts/python/tests` rendant 128 (`CalledProcessError`,
    `probe_457_offline_tests_green.py:239`). Les 7 autres tranches etaient VERTES (s5 : 412,7 s,
    rc=0) et la commande rejouee a la main dans le meme worktree rendait rc=0 immediatement.

    C'est le meme vice, un etage plus haut, que le tri-etat de `scripts/python/host_inputs.py`
    (`null` = PAS mesure, JAMAIS rabattu sur un zero) et que la lecon `#467-r6` (une panne de
    capteur doit porter son NOM -- `gh` rendait `rc=127` pour trois pannes distinctes, ce qui a
    fait corriger la mauvaise cause). Le symetrique est `#439` : la-bas un cliquet qui ne POUVAIT
    PAS rougir, ici un cliquet qui rougit SANS AVOIR RIEN VU.

    LE CRITERE -- CE QUI SEPARE << MONTAGE >> DE << MESURE >>
    ---------------------------------------------------------
    Un cliquet repond a DEUX questions, dans cet ordre :

      1. MONTAGE -- << ai-je pu CONSTITUER l'objet de ma mesure, et l'observer ? >>
      2. MESURE  -- << l'observation viole-t-elle mon invariant ? >>

    La ligne de partage est celle-ci : le MONTAGE est tout ce dont le cliquet depend et qui
    N'EST PAS LE DEPOT -- le CWD que l'appelant lui donne, les outils externes qu'il invoque
    (`git`, `pwsh`, `pytest` en tant que programme), le systeme de fichiers, les ressources
    d'execution. La MESURE est ce qui vient du CONTENU du depot.

    TEST OPERATIONNEL, en une question :
        << un depot PARFAIT, a cet instant, sur cette machine, aurait-il produit ce meme echec ? >>
        OUI  -> INDISPONIBLE (le depot n'est pas accuse)
        NON  -> ROUGE

    Ce que ce critere tranche, et qu'il faut ecrire pour qu'il ne glisse pas :

      * `git ls-files` qui rend 128            -> INDISPONIBLE (un depot parfait le subit aussi) ;
      * `pytest` rc 2 / 3 / 4 (interrompu, erreur interne, usage)  -> INDISPONIBLE ;
      * un CWD faux impose par l'appelant      -> INDISPONIBLE ;
      * un test qui ECHOUE (`pytest rc=1`)     -> ROUGE ;
      * `git ls-files` qui rend rc=0 et une liste VIDE -> **ROUGE**. C'est une reponse VALIDE de
        l'outil, donc un fait sur le depot : le perimetre s'est effondre. C'est LA frontiere a ne
        pas laisser glisser -- sans elle, << je n'ai rien trouve >> deviendrait << je n'ai pas pu
        regarder >>, et tout finirait INDISPONIBLE.

    POURQUOI CE N'EST PAS UNE ECHAPPATOIRE
    --------------------------------------
    `INDISPONIBLE` est **BLOQUANT** : le code de sortie de la banque n'est JAMAIS 0 quand une
    entree est indisponible, et l'etat s'imprime en clair avec son extrait de cause. Reclasser un
    rouge en indisponible ne fait donc RIEN taire -- ca change l'ACCUSE (le harnais au lieu du
    code fusionne), pas le blocage. C'est ce qui distingue ce tri-etat d'un `|| true`.

    LA CONVENTION DE CODE DE SORTIE, ET D'OU ELLE VIENT
    ---------------------------------------------------
    Elle n'est PAS inventee ici -- elle etait deja tenue par trois endroits du depot, qui ne se
    parlaient simplement pas :
      * `scripts/ratchets-bg.ps1`  : `99` = << MONTAGE EN ECHEC -- aucun verdict sur le depot >> ;
      * `probe_457_offline_tests_green.py` : `EX_NON_MESURE = 99`, deja rendu par son garde de CWD
        et par son refus d'ecrire (#464) -- mais ECRASE en `ROUGE` par la banque ;
      * `ratchets.ps1` : `64` = erreur d'USAGE, deja documentee << a traiter comme non mesure >>.

    Ce fichier ne fait que les REUNIR en une table unique et testable.

.NOTES
    Dot-source (`. $PSScriptRoot\ratchets-verdict.ps1`), jamais recopie : c'est ce qui permet a
    `probe_471_tri_etat_cliquets.py` de CONFRONTER la table sans la reimplementer -- un garde-fou
    dont le verdict derive ne vaut rien (lecon de `probe_319`).
#>

#: Erreur d'USAGE de la banque elle-meme : aucun cliquet selectionne, repertoire introuvable,
#: `python` absent du PATH. Documentee dans `.OUTPUTS` de `ratchets.ps1` depuis #457-r7.
$EX_USAGE = 64

#: << RIEN N'A ETE MESURE >>. Un appelant DOIT le traiter comme non mesure, jamais comme un rouge
#: de gisement -- ni comme un vert.
$EX_INDISPONIBLE = 99

function Get-EtatCliquet {
    <#
    .SYNOPSIS
        Traduit le code de sortie d'UN cliquet en `OK` | `INDISPO` | `ROUGE`.
    .DESCRIPTION
        `64` est traite comme `99`, et ce n'est pas une commodite : `.OUTPUTS` de `ratchets.ps1`
        dit deja qu'un appelant DOIT lire 64 comme << non mesure >>. La banque est un appelant.
        Toute autre valeur non nulle est un ROUGE -- c'est le defaut SUR : un cliquet qui invente
        un code de sortie doit accuser le depot, pas s'exempter en silence.
    #>
    param([Parameter(Mandatory)][int] $Rc)
    if ($Rc -eq 0) { return 'OK' }
    if ($Rc -eq 99 -or $Rc -eq 64) { return 'INDISPO' }
    return 'ROUGE'
}

function Get-CodeSortieBanque {
    <#
    .SYNOPSIS
        Code de sortie de la BANQUE, a partir des deux comptes.
    .DESCRIPTION
        Le ROUGE PRIME : il accuse le code fusionne, information plus actionnable qu'un capteur
        muet, et le contrat historique (`rc = nombre de cliquets rouges`) reste vrai des qu'il y
        a un rouge. Sinon, un indisponible rend `99` -- jamais 0, sinon la PR passerait sur un
        cliquet qui n'a rien vu, c'est-a-dire exactement le silence que #471 ferme.

        RESERVE ASSUMEE : si la banque comptait un jour 64 ou 99 cliquets ROUGES, son code de
        sortie serait ambigu avec les deux sentinelles. Elle en a 40 ; l'ambiguite est notee, pas
        contournee -- la contourner demanderait un canal hors code de sortie.
    #>
    param([Parameter(Mandatory)][int] $Rouges, [Parameter(Mandatory)][int] $Indispos)
    if ($Rouges -gt 0) { return $Rouges }
    if ($Indispos -gt 0) { return 99 }
    return 0
}
