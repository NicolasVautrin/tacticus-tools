<#
.SYNOPSIS
    LA BANQUE DE CLIQUETS de tacticus-tools -- source UNIQUE, versionnee et EXECUTABLE.
    ⛔ N'EST PLUS UNE OBLIGATION AVANT PR depuis le 2026-08-05 (commit d82ec527). NE LA JOUE PAS
    par reflexe : elle reste lancable A LA DEMANDE (`-Only <id>`, `-List`), et c'est tout.

.DESCRIPTION
    Un CLIQUET est un garde-fou offline et deterministe : il n'atteste pas une tranche, il atteste
    que l'ARBRE n'a pas re-creuse un trou deja bouche.

    POURQUOI ELLE N'EST PLUS OBLIGATOIRE, mesure a l'appui (2026-08-05, sur les 67 runs de
    `logs/ratchets-bg`) : 2 437 lignes de cliquet, 5 non nulles -- 0,21 %. Deux de ces cinq sont des
    FAUX ROUGES documentes (#471 montage, #473 runner concurrent) et trois de plus ont ete
    rapportes le meme jour par des agents (`git add -A` a 120 s sous parallelisme 16, host
    injoignable), tous verts au rejeu seul. Les 32 cliquets de GISEMENT n'ont pas tire une seule
    fois ; seuls `probe_457` / `probe_462` tirent, et ce sont des lanceurs de suite de tests --
    `probe_457` pesant 67 % du cout, pour ~891 s par agent et par PR.
    Les prises citees plus bas restent VRAIES, mais ce sont des prises de FONDATION (trouvees en
    ECRIVANT le cliquet), pas de GARDE. Elles justifient de l'avoir ecrit, pas de le rejouer.

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
    Sous `pwsh -File`, un argument reste UNE chaine : `-Only a,b` arrivait donc comme l'id
    litteral `a,b`, qui ne matche rien -- l'exemple ci-dessous etait FAUX depuis #430. Les valeurs
    sont desormais RE-DECOUPEES sur la virgule, ce qui rend les deux formes equivalentes.

.PARAMETER Skip
    Exclut ces ids (meme regle de prefixe, virgule comprise). A n'utiliser QUE pour un
    diagnostic local.

.PARAMETER Since
    Transmet `--since <ref>` a `probe_457` : il ne rejoue que les fichiers de test IMPACTES par le
    diff `<ref>..HEAD`, deduits de son EMPREINTE MESUREE (fichiers reellement ouverts par chaque
    test) et du graphe d'imports. Tout doute -- ref inconnue, empreinte absente, import dynamique,
    changement dans une lecture non attribuable -- rejoue TOUT et le DIT.
    Les autres cliquets ne sont pas filtres : ce sont des balayeurs d'arbre.
    ⚠ C'est le SEUL mecanisme du depot qui RETIRE des tests. Il ne remplace pas un run complet :
    le jouer par PR, et garder un run SANS `-Since` avant tout dispatch d'agents.

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
    TROIS etats, jamais deux (#471). Sortie ASCII stricte (cp1252).

      * `0`   BANQUE VERTE  -- tout a ete mesure, rien ne rougit ;
      * `N`   BANQUE ROUGE  -- N cliquets ont MESURE et trouve un trou (contrat historique) ;
      * `99`  BANQUE INDISPONIBLE -- aucun rouge, mais au moins un cliquet n'a RIEN PU MESURER.

    Le tri-etat et son CRITERE (ce qui separe un echec de MONTAGE d'un verdict de MESURE) vivent
    dans `scripts/ratchets-verdict.ps1`, dot-source ci-dessous -- table UNIQUE, pas recopiee.
    En resume : un cliquet rend `99` (ou `64`) quand un depot PARFAIT aurait subi le meme echec
    sur cette machine a cet instant -- `git` en echec, CWD faux impose par l'appelant, `pytest`
    rc d'usage. `INDISPONIBLE` est BLOQUANT (le rc n'est jamais 0) : il change l'ACCUSE -- le
    harnais et non le code fusionne -- il ne fait rien taire.

    MESURE qui l'a impose (2026-08-04) : `BANQUE ROUGE -- 1/40 : probe_457:s3`, alors que cette
    tranche avait crashe en 4,5 s dans son propre montage (`git ls-files` -> 128) sans jouer un
    seul test. Un rouge de gisement pour une panne d'outil.

    ⚠ L'erreur d'USAGE de la banque ELLE-MEME (aucun cliquet selectionne, repertoire introuvable,
    `python` absent du PATH) rend **64**, jamais 1. Elle rendait 1, donc elle etait INDISTINGUABLE
    d'« un cliquet a rougi » -- un appelant lisait « 1 rouge » la ou RIEN n'avait ete joue. C'est
    la faute que `#457-r7` nomme sur `probe_457` (un `pytest rc=4` d'usage lu comme un rouge de
    gisement), et de la meme famille que « un echec RENDU se lit comme une mesure ».
    Un appelant DOIT traiter 64 comme « non mesure », jamais comme un verdict sur le depot.

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
    [string]   $Since,
    [int]      $ThrottleLimit = 0,
    [switch]   $Serial,
    [int]      $Lines = 14,
    [string]   $LogDir
)

# ==========================================================================================
#  LA BANQUE. Une entree = un cliquet. `Seul` dit ce que ce cliquet est SEUL a voir : c'est
#  le critere d'admission, avec le cout MARGINAL en parallele (jamais le cout absolu).
#
#  UN CLIQUET NEUF DECLARE AUSSI SON `DECLENCHEUR` (#486-r12) -- pas ici, dans SON PROPRE
#  fichier, au niveau module : << qu'est-ce qui doit changer pour qu'il puisse changer d'avis ? >>
#  Contrat et matcher : `scripts/python/declencheur_cliquet.py` (source UNIQUE, ne pas recopier).
#  Le defaut est `toujours: True` avec sa raison -- un declencheur trop LARGE est sain, trop
#  ETROIT est un faux vert. `probe_486r12_declencheurs.py` derive son perimetre de CETTE banque
#  et confronte chaque declaration a une MESURE (les fichiers reellement ouverts).
#  ⚠ La SELECTION n'est pas encore cablee ici : les declarations se posent d'abord.
#
#  `Rougit` est FACULTATIF et n'a qu'une valeur admise : 'compteur'. Il DECLARE qu'une entree
#  est structurellement incapable de rendre un code non nul -- elle est la pour le contexte,
#  pas pour garder. C'est une declaration MACHINE, lue par `probe_439`, qui garde les DEUX
#  directions : une entree sans declaration qui ne peut pas rougir est ROUGE (le vice de #430
#  et #435), et une entree DECLAREE compteur qui se met a pouvoir rougir l'est aussi -- sa
#  declaration est MORTE. Ne jamais poser ce champ pour faire taire un cliquet casse.
#
#  UN CLIQUET QUE CE FICHIER NOMME SANS EN FAIRE UNE ENTREE N'EST JOUE PAR RIEN (#409-r1).
#  C'est le gisement de `probe_319` : seul garde de la fidelite de `probe_273`, il a CRASHE des
#  mois sans que rien ne le signale -- invisible de `probe_439` (il n'etait pas une entree, et
#  on ne juge que ce qu'on visite) ET de `probe_486r2` (il etait NOMME et EXECUTABLE, donc ni
#  orphelin ni muet : simplement jamais joue). L'etape `etape_nommes_hors_banque` de `probe_439`
#  ferme cette porte : tout `probe_*.py` cite ICI -- prose comprise -- doit etre une entree, ou
#  porter une exemption MACHINE `# HORS-BANQUE: <script>.py -- <raison>`, gardee dans les deux
#  directions (une exemption qui designe une entree reelle, un fichier absent, ou un script que
#  ce fichier ne nomme plus, est MORTE). Mesure du 2026-08-08 : 38 nommes, 37 entrees, 1 ecart.
#
# HORS-BANQUE: probe_486r12_declencheurs.py -- Il rend rc=99 (BANQUE INDISPONIBLE) par
#  construction : son empreinte versionnee est keyee sur le SHA du source de chaque cliquet,
#  donc elle PERIME des qu'un cliquet change -- mesure du 2026-08-08, 23 entrees ABSENTES et 2
#  PERIMEES (probe_229, probe_313). La remesurer exige `--mesurer`, qui REJOUE toute la banque
#  sous audit hook. L'inscrire ici publierait donc un 99 permanent, c'est-a-dire la forme la
#  plus surement desarmee d'un garde-fou -- son propre en-tete le dit. Son entree est un
#  arbitrage de COUT qui appartient a l'orchestrateur ; ce qui change avec #409-r1, c'est que
#  l'arbitrage est desormais ECRIT et VISIBLE au lieu d'etre un oubli indistinguable.
# ==========================================================================================
$Ratchets = @(
    @{ Id = 'probe_181'; Argv = @('probe_181_targeting_gaps.py')
       Seul = 'une ability entree dans ABILITY_CLASSES SANS son masque TARGETING_OPTIONS (degradation PERMISSIVE, ni erreur ni crash)'
       Doc  = 'CLAUDE.md -- Entrer au registre SANS son masque de ciblage' }

    @{ Id = 'probe_437r1r1r1'; Argv = @('probe_437r1r1r1_effect_face_table.py')
       Seul = 'une classe d effet dont le port range la contribution de degat dans l ACCUMULATEUR (attackModifiers / defenseModifiers) que le natif ne lui donne pas -- la face est le SLOT VIRTUEL de sortie, jamais le porteur, et elle vaut +/-1 par borne des que les deux faces sont non neutres'
       Doc  = 'docs/rl/case-437-r1-r1-r1-face-native-des-effets.md' }

    @{ Id = 'probe_433r4r1r4r2'; Argv = @('probe_433r4r1r4r2_neigh_channel_wired.py')
       Seul = 'QUATRE facons de perdre le substrat de voisinage natif, et chacune est structurellement invisible a la precedente. (1) un call-site d adjacence branche A MOITIE : il passe la PORTE d elevation (elev_by_pos) mais pas l ENUMERATION (neigh_by_pos), alors que TileQuery$$IterateAdjacentTiles porte les DEUX etages -- la detection RESOUT l import, donc elle voit aussi le nom NU et l ALIAS, sans confondre les homonymes de services/ (mesure : 12 rouges par comparaison de noms, dont 9 faux positifs ; 3 vrais apres resolution). (2) de la GEOMETRIE NUE (hexgeo.distance == 1) dans une fonction qui DECLARE mirrorer un natif a liste stockee : celle-la ne passe NI l un NI l autre canal, donc elle est hors gisement de (1) PAR CONSTRUCTION -- c est exactement ainsi que newly_adjacent_ids et son jumeau ECS update_charging ont survecu au basculement (#433-r4-r1-r4-r2-r1). (3) la DERIVATION LAISSEE MORTE : (1) et (2) cotent la PRESENCE du canal, aucune sa CONSOMMATION -- un neigh = neigh_map(ctx) jamais relu, un predicat PUR du foyer dont la valeur est jetee, ou un parametre du canal jamais lu ont l allure d un mirror branche et le comportement d avant (#433-r4-r1-r4-r2-r1-r1 ; c est la seule mutation restee VERTE a la contre-epreuve de #611). (4) la GEOMETRIE qui decide MALGRE un canal disponible, par un critere de FLOT (etat << canal etabli indisponible >> fusionne en ET a la sortie d un if, branche qui termine exclue) -- c est ce qui distingue le repli LEGITIME (is_adjacent sous if neigh is None, are_tiles_adjacent apres un bloc canal a echappement complet) d une garde inerte ou d un canal consulte puis ignore. Meme signature de degradation que TARGETING_OPTIONS -- ni erreur ni crash, juste un predicat PLUS PERMISSIF que le natif (mesure sur 4 boards : is_charging 42 aretes fermees / 0 ouverte, newly_adjacent_ids 208 / 0), donc exploitable par un entrainement. probe_181 garde le REGISTRE des abilities, celui-ci garde les APPELS d une primitive, le CORPS de ses mirrors ET le flot qui relie le canal a la decision ; aucun autre ne lit l arite d un call-site de battle_query'
       Doc  = 'docs/rl/case-433r4r1r4r2r1-foyers-voisins-adjacence.md' }

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

    @{ Id = 'probe_464'; Argv = @('probe_464_sibling_script_cwd.py')
       Seul = 'un script FRERE invoque par chemin RELATIF dans un argv de subprocess, sans cwd= : `[sys.executable, "rl_duel.py", ...]` melange un chemin absolu et un chemin resolu depuis le CWD, donc hors de scripts/python le frere n est JAMAIS lance (rc 2 `can t open file`) -- et 8 des 15 appelants trouves ne lisaient meme pas ce rc. Aucun autre cliquet ne lit l argv d un subprocess : 273/0c garde la DESTINATION d une sortie data/, 440 le PERIMETRE d un balayage, 365 les IMPORTS. Gisement de COPIER-COLLER (22 sites, un seul litteral, 15 fichiers) donc alimente par notre propre cadence, comme TARGETING_OPTIONS'
       Doc  = 'docs/rl/case-464-cwd-des-scripts.md' }

    @{ Id = 'probe_391'; Argv = @('probe_391_conftest_dir_identity.py')
       Seul = 'un repertoire collecte DEUX fois par pytest dans une meme session : les fixtures de son conftest disparaissent pour le 3e argument, et le nodeid est IDENTIQUE (invisible a toute inspection par chaine)'
       Doc  = 'docs/rl/case-391-conftest-dir-identity.md' }

    @{ Id = 'probe_313'; Argv = @('probe_313_enum_mirror_bijection.py')
       Seul = 'un mirror IntEnum du moteur qui n est PLUS en bijection avec enums.tsv (manquant / mort / RENUMEROTE), toute IntEnum entree sous engine/ sans etre appariee ni justifiee HORS-MIRROR, et -- depuis #270-c -- le cran EN DESSOUS du mirror : une CLE des dicts que le moteur lit reellement (ABILITY_TRIGGERS, EFFECT_CLASSES, les six registres de triggers.dispatch = les cinq chemins de registration de collect_triggered_abilities) que le build ne nomme plus. Cette derniere degradation est muette au carre : .get(cle, ()) rend () et le passif n est JAMAIS inscrit, sans que le mirror ait bouge. Il distingue la cle INTROUVABLE (aucun enum) de la cle EGAREE (le nom vit dans un AUTRE enum -- c est l APPARIEMENT du registre qui est faux, pas la cle), seul verdict du depot qui NOMME sa cause plutot que de la constater'
       Doc  = 'docs/rl/case-313-enum-mirror-bijection.md ; case-318 ; case-270c-mirror-deja-bijectif-le-cran-du-dessous.md' }

    @{ Id = 'probe_449r2'; Argv = @('probe_449r2_spread_inventory.py')
       Seul = 'un port de la face COMBAT qui suppose l ABSENCE de variance d arme sur un montant sans l avoir LUE (le byte AttackDamageBehaviourOptions+6), le sens inverse (un zero JUSTE qu on retire), et surtout le REGIME DE DEFAUT de chaque porte de variance -- c est lui qui porte la decision, puisque deux des trois porteurs a variance nulle n ECRIVENT PAS le mot-cle. Depuis #449-r2-r4 il rougit AUSSI des qu un defaut entier NON NUL revient dans une signature : le pct de spread se lit dans BattleConfiguration.Damage.DamageSpreadPercentage, jamais dans une constante (mesure : a pct=60 le natif inflige 7774, un port a 20 en dur calcule 9388). Le gisement est invisible au grep (5 des 6 occurrences textuelles de spread_pct=0 sont des commentaires) et invisible a un inventaire par mot-cle (un call-site peut passer la variance POSITIONNELLEMENT). Il voit aussi un parametre de variance devenu MORT -- accepte et lu nulle part, donc plus jamais applique, sans qu un seul call-site change'
       Doc  = 'docs/rl/case-449-r2-r4-spread-lu-de-la-bc.md (#449-r2-r4) ; case-449-r2-spread-face-combat.md (#449-r2-r5)' }

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

    @{ Id = 'probe_440'; Argv = @('probe_440_repo_root_scan_guard.py')
       Seul = 'un balayage qui part de la RACINE du depot sans exclure .claude/worktrees -- il lit et RAPPORTE le code en cours des autres agents (rouge d agent attribue a l arbre principal) ; et la correction NAIVE de ce trou, le filtre par SEGMENT sur un chemin absolu, qui s auto-exclut depuis un worktree : 0 fichier, verdict vert'
       Doc  = 'docs/rl/case-434-perimetre-des-cliquets.md' }

    @{ Id = 'probe_274'; Argv = @('probe_274_step_ordinals_sweep.py')
       Seul = 'un ordinal StepType/GroupType fige en dur, y compris derriere un ALIAS (`step = ev.get("step")` puis `step == 13`) ou une CLE de dict, et la table de labels POSITIONNELLE du frontend -- GroupType (104 membres) n est couvert par aucune etape de probe_283'
       Doc  = 'docs/rl/case-254b-b-ordinaux-en-dur.md' }

    @{ Id = 'probe_443r1c'; Argv = @('probe_443r1c_ordinal_index_perime.py')
       Seul = 'un INDICE litteral (cle de dict/liste) qui vaut l ordinal ARCHIVE d un membre cite sur sa ligne, dans les DEUX angles morts de probe_283 : l acces par ACCESSEUR (.get/.pop/.setdefault -- son etape exec ne visite que Subscript) et le membre AMBIGU (son etape prose l ecarte quand la ligne ne nomme pas l enum, 4bis inconditionnellement). Mesure #443-r1c : le commentaire fautif s AUTO-ATTESTAIT A MOITIE -- sa moitie juste (10=TileEffects) entrait dans les ~1200 citations justes de l etape 4 pendant que sa moitie fausse (8=Elevation, ambigu dans 3 enums) restait invisible'
       Doc  = 'docs/rl/case-443-r1c-indices-perimes.md' }

    @{ Id = 'probe_443r2'; Argv = @('probe_443r2_only_active_callsites.py')
       Seul = 'un mirror de `EntityExtensions$$HasEffect` dont le SUBSTRAT contredit le litteral `onlyActive` qu il cite : `active_effects` (activite) sous un litteral 0/false/null, ou `has_effect` (presence) sous un 1/true. La divergence est SILENCIEUSE et ne se voit que sur un effet PRESENT-mais-INACTIF -- regime qu aucun montage naif n atteint (le canal decisionView par defaut DROPPE les inertes), donc invisible a tout test de conformite ordinaire. MESURE #443-r2 : 35 points d utilite de paire, sur le choix de CIBLE de l attaque normale'
       Doc  = 'docs/rl/case-443-r2-only-active.md' }

    @{ Id = 'probe_443r2b1'; Argv = @('probe_443r2b1_decision_inactive_readers.py')
       Seul = 'le CANAL de seed de la face DECISION, la ou probe_443r2 ne garde que le SUBSTRAT : un consommateur de PRODUCTION qui capte lui-meme son decisionView repart par DEFAUT sur le canal NU, qui DROPPE les effets inertes -- le port rend alors FAUX la ou le natif rend VRAI, sans erreur ni crash (mesure #443-r2-b1 : 35 points d utilite de paire, et une decision de CIBLE qui bascule sur une marche d agreement). Il voit aussi la faute SYMETRIQUE : la liste BRUTE qui laisse fuir l inerte vers des lecteurs qui n ont pas de flag a consulter'
       Doc  = 'docs/rl/case-443-r2-b1-canal-decision.md' }

    # Le garde qu'il tient (`green_skip_guard`, plugin pytest) est le seul de la banque qui
    # travaille A CHAQUE PASSE d'un agent, pour un cout nul -- ce cliquet garde qu'il mord ET
    # qu'il est BRANCHE. Sans son etape 2, un garde vert dans un tmpdir mais debranche du
    # conftest de production passerait pour un garde-fou.
    # Son etape 3 est d'une autre nature : elle balaie le GISEMENT, parce que le garde runtime ne
    # voit que les fichiers qu'une passe JOUE -- et 410 des 530 fichiers de test sont `_live.py`.
    @{ Id = 'probe_455'; Argv = @('probe_455_all_skipped_file.py')
       Seul = 'un FICHIER de test qui n a RIEN confronte, sous ses DEUX formes. (a) bilan passed == 0 and skipped > 0 -- la suite le compte comme un SUCCES, aucune assertion evaluee, rien ne le signale (mesure : test_summon_trait_effects_live.py, 8 skipped / 0 passed / rc 0 sur master, trouve en ECARTANT une PR). Le garde #77 du conftest ne le voit PAS : il lit la RAISON d un skip test par test, et un skip de MONTAGE ne porte aucun marqueur de harnais. (b) #455-r3, 0 TEST COLLECTE -- le fichier dont les tests ont DISPARU n emet AUCUN report, donc aucun bilan : il est structurellement invisible au critere (a), et invisible aussi a pytest des lors qu un test existe ailleurs dans la passe (mesure du 2026-08-03 : rc=0, aucun rapport ; SEUL il rendrait rc=5, mais personne ne joue un fichier seul). Le signal qui separe ce gisement d une selection legitime est la COLLECTE, pas la selection : -k / -m / --deselect filtrent APRES elle, un nodeid explicite n emet aucun report de collecte, et un import KO rend deja rc=2'
       Doc  = 'docs/rl/case-455-fichier-integralement-skippe.md' }

    # Le pendant LIVE de probe_457. Ce cliquet-ci est OFFLINE (il ne lit que git et le ledger) ;
    # ce qui coute est fait UNE FOIS par l'auteur, via `--run --since`, dont le perimetre est le
    # meme. Il ne pretend PAS garder l'etat du parc live -- 417 fichiers, ~1 h 50 a 4 workers,
    # hors de portee d'une banque a ~300 s de mur. Il garde le seul sous-ensemble dont le cout est
    # nul : ce que la PR TOUCHE (mediane 0 fichier, q3 1, sur 1706 commits mesures).
    @{ Id = 'probe_462'; Argv = @('probe_462_live_tests_status.py', '--gate', 'origin/master')
       Seul = 'un fichier *_live.py MODIFIE par la PR et livre ROUGE -- probe_457 exclut le live PAR CHOIX (la suite sature la session Frida partagee) et la boucle de merge ne rejoue que la tranche, donc RIEN ne regarde l etat des tests live sur master. Mesure #533 : test_env_fire_tile_dot_applies_resilient_cap_live introduit ROUGE par ad5692e7 dans un commit qui modifiait 398 lignes de SON PROPRE fichier, reste rouge 8 jours. Contre-epreuve : --gate 7b38fbe4~1 le NOMME. Il ne voit PAS le rot d un fichier que personne ne touche (trou B, mesure : test_nightshroud_combat_live.py, valide bit-exact le 2026-07-12, ROUGE le 2026-08-03) -- fermer celui-la couterait q3 64 fichiers et 19 pourcent des commits au-dela de 100, soit une demi-heure de live par PR'
       Doc  = 'docs/rl/case-462-tests-live-rouges-invisibles.md' }

    # Le pendant PYTHON de probe_365 (qui, lui, ne lit que le TypeScript de frida/), et surtout
    # le seul instrument du depot qui descend dans les corps de fonction. Sa contre-epreuve n'est
    # pas synthetique : joue sur `origin/master` au 2026-08-03 il rend rc=1 et NOMME les 5 sites.
    @{ Id = 'probe_462r5'; Argv = @('probe_462r5_dead_imports.py')
       Seul = 'un `from X import Y` de premiere partie ou X existe mais Y n y est PLUS, l import etant DANS UN CORPS DE FONCTION -- donc invisible a toute collecte : `pytest --collect-only` rend 417/417 rc 0 pendant que 10 tests meurent au setup, et un `import <module>` ne visite pas non plus les corps. probe_365 est aveugle deux fois (TypeScript seul, et son critere est la CIBLE absente/gitignoree, pas le NOM). Mesure #462-r4c : BUILD_HASH retire par #431 (4 probes) et GHOST_EFFECT renomme par #366-r1 (probe_230.case_ghost, que le grep de BUILD_HASH ne pouvait pas voir) -- 5 sites, 10 tests morts 2 jours'
       Doc  = 'docs/rl/case-462-r4c-imports-differes-morts.md ; case-462 residu #462-r5' }

    # Troisieme voie de consommation, apres la CIBLE (probe_365) et le NOM dans un corps de
    # fonction (probe_462r5) : l'ACCES ATTRIBUTAIRE a un module. Aucun des deux ne le voit --
    # il n'y a ici ni import absent ni `from X import Y`, seulement un `M.x` sur un nom lie a
    # un module. Contre-epreuve non synthetique : VERT sur `origin/master`, ROUGE (4 couples,
    # 15 acces) sur la branche du sweep #485-r1-r1 avant reparation.
    @{ Id = 'probe_485r1r1_acces'; Argv = @('probe_485r1r1_acces_attributaires.py')
       Seul = 'un `M.x` ou `M` est un nom lie a un MODULE `engine.*` et `x` un attribut que ce module n expose PAS -- un AttributeError en puissance, invisible de toute analyse d imports. Cause typique : vider un baril de re-export sans compter cette voie, car `from pkg import sous_module` lie un MODULE et non un symbole, donc la reclamation ne ressemble a aucun ImportFrom vers le baril vide. Mesure #485-r1-r1 : la vidange a retire NATIVE_PRIORITY, native_priority et _has_valid_targets de engine.playbook.noncomparable et DslContext de engine.dsl -- 4 couples dont DEUX lus par engine/** lui-meme (ai/action_generators.py, playbook/tile_targets.py), qu AUCUN des tests tombes ne montrait. Il resout chaque acces contre le module REELLEMENT importe, donc il voit la faute avant qu un test la joue ; et son etage informatif [3] nomme la reciproque -- une SUBSTITUTION posee sur un attribut absent, qui cree l attribut au lieu de le remplacer et ne mord donc sur rien (1 sur 521 ecritures, residu #485-r1-r1-r2)'
       Doc  = 'docs/rl/case-485-r1-r1-executer-le-sweep.md' }

    # QUATRIEME voie, et elle est en amont des trois autres : la FORME de ce qu'on hisse. Les trois
    # ci-dessus voient une consommation CASSEE (cible absente, nom disparu, attribut inexistant) ;
    # celle-ci voit une consommation qui MARCHE et qui a cesse d'etre SUBSTITUABLE. Rien ne casse,
    # rien ne leve : le patcheur est simplement ignore. C'est la cause des 28 fichiers rouges de
    # #484 et des 12 de #429-r1, et elle a recidive dans #485-r1-r1 meme.
    @{ Id = 'probe_485r5_forme_b'; Argv = @('probe_485r5_forme_b_mord.py')
       Seul = 'un import HISSE qui a glisse de la forme B (`import X` puis `X.foo()`) vers la forme A (`from X import foo` au niveau module) : le nom est alors resolu UNE fois a l import, donc tout `monkeypatch.setattr("X.foo", stub)` pose ensuite est ignore EN SILENCE -- aucune erreur, aucun test rouge, juste une contre-epreuve qui ne mord plus. Aucun cliquet d imports ne peut le voir : probe_365 lit la CIBLE, probe_462r5 le NOM absent, probe_485r1r1 l ATTRIBUT absent, et ici la cible existe, le nom existe et l attribut existe. probe_485_imports_differes, lui, classe le differe (porteur/gratuit) et ne dit rien de la forme de son remplacant. Il garde les quatre sites hisses par #485-r5 et exige de son propre TEMOIN qu il montre les deux formes DIVERGER (A ne mord pas, B mord) : sans ce cran il serait vert sur un mecanisme casse'
       Doc  = 'docs/rl/case-485-r5-quatre-differes-declares-cycle-et-mesures-gratuits.md' }

    @{ Id = 'probe_431'; Argv = @('probe_431_build_literals.py', '--cliquet')
       Seul = 'un hash de build ecrit en dur qui RESOUT un artefact du jeu (chemin de GameAssembly.dll, table de symboles, defaut de --build) HORS du foyer build_pin : le litteral court-circuite a la fois data/symbols/CURRENT et le binaire installe, donc symbols_sync peut etre VERT pendant que le script lit un autre build. Depuis #458 il voit AUSSI son propre perimetre : toute extension presente dans l arbre et hors des trois seaux le fait rougir. Ce second axe est ce qui le rendait creux -- ses globs passaient par Path.match, qui ne developpe pas ** : 967 fichiers versionnes tombaient dans AUCUN seau (tout scripts/python/engine, tout tests/, et par le HAUT frida/host/router.ts et frida/hooks/main.ts), lus puis jetes en silence sous un denominateur qui se lisait comme une couverture'
       Doc  = 'docs/rl/case-431-litteraux-de-build.md ; docs/rl/case-458-perimetre-derive-du-cliquet-431.md' }

    @{ Id = 'probe_330r4'; Argv = @('probe_330r4_estampilles_des_generes.py', '--cliquet')
       Seul = 'un artefact GENERE dont l en-tete DECLARE sortir d un build qui n est plus le courant. Aucune bijection ne peut le voir : probe_252, probe_275, probe_270 et probe_313 comparent une TABLE au build courant, ils ne lisent jamais ce que le fichier DECLARE -- les quatre etaient VERTS le 2026-08-15 pendant que DOUZE artefacts declaraient rnca9r7q6c ou kqkbjqfb6c. Et pour un scan d instructions (docs/rl/dsl-usage/*.tsv, xrefs du binaire) l estampille est le SEUL signal qui existe : aucune bijection membre a membre ne peut le rattraper, un deplacement de code le perime en silence. Le cliquet ecarte les lignes de DONNEES (un cache versionne porte une cle par build) et la prose historique (une case-doc datee est un fait exact), et il COMPTE ce qu il ecarte'
       Doc  = 'docs/rl/case-330-r3-r4-r5-forme-du-hash-et-estampilles.md ; docs/rl/case-10012-deux-rouges-targeting-rule-et-l-inventaire-des-estampilles.md' }

    # --- TROIS ENTREES RETIREES PAR #457-r6, et pourquoi ce n'est PAS un retrecissement.
    #
    # `pytest_signatures`, `pytest_attestations` et `pytest_adjacency` invoquaient `pytest` sur
    # cinq fichiers NOMMES A LA MAIN. C'etaient des ALLOWLISTS -- et c'est exactement ce que
    # `probe_457` a generalise : son perimetre se DERIVE (`git ls-files scripts/python/tests`,
    # tout ce qui n'est pas `_live.py`), donc il joue DEJA ces cinq fichiers, depuis #457-r5.
    # La banque faisait donc DEUX FOIS le meme travail. Mesure du 2026-08-03, durees ISOLEES
    # (`-Serial`, machine calme) : 29,0 + 7,5 + 3,9 = 40,4 s sur 739,6 s de somme isolee.
    #
    # Les gisements qu'elles nommaient ne sont PAS perdus -- ils vivent dans les fichiers de
    # test eux-memes, que `probe_457` joue :
    #   * `tests/test_additional_hits_variant_signatures_offline.py`  (#393, derive de signature
    #     d'une implementation de SUBSTITUTION -- le rouge tombe alors ailleurs que sur la cause) ;
    #   * `tests/test_337_dsl_triggers_attestation_offline.py`  (#337, une primitive `DSLTriggers`
    #     retombee en CITE_A_QUALIFIER, et une ligne de `dsl-port-attestations.tsv` devenue MORTE) ;
    #   * `tests/engine/runner/test_433_r1_identity_shortcircuit_offline.py`,
    #     `test_433_r3_isadjacent_node_offline.py`, `test_433_r3_r1_dsl_footprint_offline.py`
    #     (#433, les deux termes foldes de `MovementUtil$$AreTilesAdjacent`, le QUANTIFICATEUR du
    #     noeud DSL `IsAdjacent`, et le collapse MAIN TILE d'un noeud qui lit l'EMPREINTE).
    #
    # La redondance est PROUVEE MECANIQUEMENT, et sa non-reintroduction GARDEE, par
    # `tests/test_457_r6_banque_sans_doublon_offline.py` : il derive la banque (`probe_439`) et
    # le perimetre (`probe_457`), et rougit sur toute entree `pytest` qui les recoupe. Il a
    # mordu des sa premiere passe, avant que ces trois entrees ne soient retirees.

    # --- probe_283, en SIX entrees. `--step all` est l UNION STRICTE de ces six (lire `main`),
    #     et chaque etape est independante. Le decoupage ne change RIEN a la couverture ; il rend
    #     le cout MARGINAL en parallele quasi nul : joue d un bloc, probe_283 DOUBLE le mur du lot
    #     (145 s -> 299 s, mesure du 2026-08-01) ; eclate, sa plus longue etape (prose, ~47 s)
    #     passe TRES en dessous du mur, qui ne bouge pas.
    #     `diff` est un COMPTEUR (aucun `ko +=` : structurellement incapable de rougir). Il
    #     reste dans la banque quand meme -- 1 s de CPU pour que la banque reste l EQUIVALENT
    #     EXACT de `--step all`, et pour qu un futur `ko +=` sur lui soit vu.
    #     `on` en ETAIT un jusqu au 2026-08-07 : depuis #420-r5 il rougit sur une quote
    #     VERBATIM ANNOTEE `On(<Membre>)` dont le nombre vaut l ordinal ARCHIVE de ce membre.
    #     Sa declaration `Rougit = compteur` est donc RETIREE -- une declaration MORTE est
    #     elle-meme un rouge de `probe_439`, dans les DEUX directions.
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
       Seul = 'une QUOTE VERBATIM du helper de publication (`FUN_<addr>(0x4d|0x50|0x51|.., .., <n>)`) dont l ordinal est PERIME. Elle echappe a TOUTES les autres etapes -- ni ancre On(, ni membre au separateur court, et on ne peut pas ecrire le membre DEDANS sans falsifier la citation. Le gate ne mord que la ou l auteur a pose l annotation `On(<Membre>)` sur la ligne : le nombre cite vaut alors l ordinal ARCHIVE du membre nomme, ce qui n a aucune autre explication qu une recopie d un build perime. Compte AUSSI les litteraux On(<n>) NUS, stables vs decales (residu #283-r1, indecidables par construction)'
       Doc  = 'docs/rl/case-420-on-litteraux-perimes.md ; docs/rl/case-420-r2-r5-ancre-et-annotation.md' }

    # --- probe_457, en HUIT shards (etait TROIS). Le shard se derive d'un md5 du chemin -- stable,
    #     donc un fichier neuf ne redistribue pas les autres, et l'union des shards est STRICTE.
    #     Les entrees partagent la meme ligne `Seul` : meme gisement, decoupe pour le cout,
    #     exactement comme les six etapes de probe_283.
    #     Ce cliquet est le SEUL de la banque dont le perimetre se DERIVE au lieu d'etre nomme :
    #     les trois entrees `pytest_*` ci-dessus sont des allowlists, et c'est precisement ce qui
    #     a laisse `test_multihex_substrate.py` rouge pendant un jour sans que rien ne le dise.
    #
    #     POURQUOI HUIT (#457-r5). Le perimetre passe de 86 a 110 fichiers : le glob precedent
    #     (`tests/**/test_*.py`) excluait les fichiers poses DIRECTEMENT dans `tests/`, car `**/`
    #     exige un niveau intermediaire. Les 24 entrants sont les GARDES DE DEPOT (balayages
    #     d'arbre, tables de symboles) et pesent a eux seuls ~2150 s en serie, contre 116 s pour
    #     les 896 tests preexistants -- ~20x le cout par test. Le md5 regroupe les lourds
    #     (ecart-type 131-218 s), donc sharder davantage ne rachete plus son cout d'ordonnancement :
    #     la simulation donne 924 s a 3 shards, 629 s a 8, et seulement 443 s a SEIZE.
    #     MUR REEL, MESURE ISOLE le 2026-08-02 (-Only probe_439,probe_440,probe_457) : 297,8 s
    #     (shard le plus long 295,7 s, le plus court 48,3 s). La SIMULATION SURESTIME -- elle
    #     additionne des durees par fichier deja gonflees par la contention. Mesurer, pas simuler.
    #     Le vrai levier est d'alleger les balayages eux-memes -- residu #457-r6, et #524 vient de
    #     le demontrer sur probe_431 (perimetre x2,1 pour -14 % de temps).
    #     NE PAS << regler >> ce cout en retrecissant le perimetre : c'est la faute que #457-r5 repare.
    @{ Id = 'probe_457:s0'; Argv = @('probe_457_offline_tests_green.py', '--shard', '0/8')
       Seul = 'un fichier de test 100 % OFFLINE ROUGE EN PERMANENCE sur master -- invisible parce que la suite complete est proscrite (410 des 519 fichiers sont _live.py), qu un agent ne rejoue que SA tranche, et que les trois entrees pytest_* de cette banque nomment leurs fichiers A LA MAIN (allowlist : on n y entre que si quelqu un y pense). Mesure : test_multihex_substrate.py, 3 failed / 15 passed sur master. Il voit aussi la moitie plus couteuse du meme vice -- le VERT VACUEUX, un 4e test du meme fichier passant avec zero assertion utile parce que son anneau etait vide'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }
    @{ Id = 'probe_457:s1'; Argv = @('probe_457_offline_tests_green.py', '--shard', '1/8')
       Seul = 'idem probe_457:s0 -- shard 1/8 du MEME gisement (perimetre DERIVE, pas d allowlist)'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }
    @{ Id = 'probe_457:s2'; Argv = @('probe_457_offline_tests_green.py', '--shard', '2/8')
       Seul = 'idem probe_457:s0 -- shard 2/8 du MEME gisement (perimetre DERIVE, pas d allowlist)'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }
    @{ Id = 'probe_457:s3'; Argv = @('probe_457_offline_tests_green.py', '--shard', '3/8')
       Seul = 'idem probe_457:s0 -- shard 3/8 du MEME gisement (perimetre DERIVE, pas d allowlist)'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }
    @{ Id = 'probe_457:s4'; Argv = @('probe_457_offline_tests_green.py', '--shard', '4/8')
       Seul = 'idem probe_457:s0 -- shard 4/8 du MEME gisement (perimetre DERIVE, pas d allowlist)'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }
    @{ Id = 'probe_457:s5'; Argv = @('probe_457_offline_tests_green.py', '--shard', '5/8')
       Seul = 'idem probe_457:s0 -- shard 5/8 du MEME gisement (perimetre DERIVE, pas d allowlist)'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }
    @{ Id = 'probe_457:s6'; Argv = @('probe_457_offline_tests_green.py', '--shard', '6/8')
       Seul = 'idem probe_457:s0 -- shard 6/8 du MEME gisement (perimetre DERIVE, pas d allowlist)'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }
    @{ Id = 'probe_457:s7'; Argv = @('probe_457_offline_tests_green.py', '--shard', '7/8')
       Seul = 'idem probe_457:s0 -- shard 7/8 du MEME gisement (perimetre DERIVE, pas d allowlist)'
       Doc  = 'docs/rl/case-457-tests-offline-rouges-invisibles.md' }

    # Le PREMIER cliquet de la banque qui ne garde pas le CODE mais la BOUCLE. Il est aussi le
    # seul dont le sujet ne produit AUCUN rouge en se degradant : `loop_status` ne tombe pas en
    # panne, il se TAIT -- et un slot d'agent vide qu'on ne signale plus se lit exactement comme
    # un depot au repos. 100 % offline : la facade `Sources` est SUBSTITUEE (aucun git, aucun gh,
    # aucun host), sans quoi garder le tri-etat exigerait d'eteindre le host.
    @{ Id = 'probe_467'; Argv = @('probe_467_loop_status_fidelity.py')
       Seul = 'la degradation SILENCIEUSE de l etat de boucle, sur ses trois axes. (a) UN ZERO A LA PLACE D UN << PAS MESURE >> -- host eteint ou gh hors ligne, si liveRunners retombe a 0 au lieu de rester null, l orchestrateur lance 4 tests sur un budget partage inconnu (faute deja commise : 2 fichiers rendus en timed out) ; meme forme pour << 0 PR ouverte >> quand gh n a pas repondu. (b) LE RACCOURCI DE FLOTTE QUI DERIVE -- le decompte des agents en vol passe par le pre-filtre only_alive de fleet_board (54,8 s -> 0,2 s sur 870 transcripts, 1,23 Go) : s il cesse d etre EXACT, le compteur de slots ment, et c est le chiffre pour lequel l outil existe. (c) LE DECLENCHEUR QUI SE TAIT OU QUI HURLE -- un hook Stop muet est un garde-fou mort, un hook qui parle a chaque tour d un depot au repos se fait desarmer en une journee ; les deux directions sont gardees. Il voit aussi le verdict de banque ILLISIBLE rabattu sur un vert -- gisement MESURE le 2026-08-04 : les 3 verdicts presents dans logs/ratchets-bg n avaient AUCUNE ligne rc (precedence PowerShell dans ratchets-bg.ps1), et tout lecteur automatique rendait donc << rc inconnu >> sur un fichier d apparence normale. (d) DEPUIS #472, LE MEME VICE SUR L AXE DU TEMPS : un verdict rendu comme l etat COURANT alors qu il juge un ANCETRE -- mesure, le hook a repete << afb3e209 rc=1 ROUGE >> trois tours de suite pour une cause deja corrigee, HEAD valant entre-temps 4b62a914 puis c94efb11 ; re-mesure a froid, 48 commits d ecart entre le dernier verdict et la pointe. La ventilation JUGEE / EN COURS / NON JUGEE se tranche sur un FAIT (le handle du verrou de run, que l OS libere toujours a la mort du processus -- ni PID recyclable, ni age), et les DEUX glissements sont gardes : le perime qui realarme ET le perime qui devient silencieux. Contre-epreuve : 8 mutations injectees dans loop_status.py, 8 rouges, plus un end-to-end reel ratchets-bg -> loop_status (NON JUGEE -> EN COURS -> JUGEE)'
       Doc  = 'docs/rl/case-467-etat-de-boucle.md' }

    # Le PENDANT de probe_467, et il existe parce que probe_467 ne pouvait PAS voir ceci : les
    # DEUX probes #467 substituent la facade `Sources`, donc tous deux remplacent `http_json`.
    # Un champ disparu cote host (`.session` renomme, `liveRunners` retire) les laissait VERTS
    # tous les deux -- deux lecteurs partageant la meme entree morte s accordent parfaitement et
    # ont tort ensemble. Celui-ci confronte le contrat au CODE SOURCE du host (`frida/host/*.ts`),
    # avec la liste des champs DERIVEE de `loop_status.mesurer_harnais` et non recopiee. Il porte
    # son auto-epreuve : 3 mutations du host doivent le faire basculer, sinon il rougit lui-meme.
    # Le volet LIVE est opportuniste -- host eteint => NON MESURE dit, jamais un vert muet.
    @{ Id = 'probe_467r4'; Argv = @('probe_467r4_contrat_host.py')
       Seul = 'un champ du contrat host DISPARU (.session renomme, liveRunners retire de /api/admin/drain) -- les deux probes #467 substituent http_json et resteraient verts ; la degradation est muette (dr.get("liveRunners") rend None => tri-etat PAS MESURE a vie sur le seul chiffre que personne ne peut deviner)'
       Doc  = 'docs/rl/case-467-etat-de-boucle.md' }

    # Le SECOND cliquet de la banque sur la banque, et le symetrique EXACT de `probe_439` :
    # la-bas un cliquet qui ne POUVAIT PAS rougir, ici un cliquet qui rougit SANS AVOIR RIEN VU.
    # Il garde la CHAINE (table -> banque -> code de sortie), pas la conversion des 14 entrees
    # qui confondent encore -- son etape 4 les INVENTORIE sans rougir (residu #471-r1) : un
    # garde-fou qui rougirait sur une douzaine d'entrees a la fois se fait desactiver.
    @{ Id = 'probe_471'; Argv = @('probe_471_tri_etat_cliquets.py')
       Seul = 'un cliquet qui rougit SANS AVOIR RIEN MESURE -- une panne d OUTIL EXTERNE (git, pwsh, pytest en usage) sort en rc=1 comme Python le fait de toute exception, et la banque rabattait TOUT rc non nul sur ROUGE. MESURE 2026-08-04 : << BANQUE ROUGE -- 1/40 : probe_457:s3 >> alors que ce shard avait crashe en 4,5 s dans son propre montage (`git ls-files` -> 128, CalledProcessError) sans jouer un seul test, les 7 autres etant VERTS -- un rouge de gisement pour une panne d outil, sur un depot sain. C est le tri-etat de host_inputs (null != 0) et la lecon #467-r6 (une panne de capteur doit porter son NOM) a l etage du CLIQUET. Aucun autre cliquet ne regarde le code de SORTIE de la banque : 439 garde qu une entree PEUT rendre non nul, jamais ce que ce non-nul SIGNIFIE. Il porte sa contre-epreuve en montage REEL (depot jetable, probe_457 joue 3 fois : test vert -> 0, test rouge -> 1, git hors service -> 99) -- un chemin qui ne peut pas rendre les deux ne vaut rien, et sur une contre-epreuve le VERT est le resultat suspect, donc chaque scenario exige que sa mutation ait MORDU'
       Doc  = 'docs/rl/case-471-tri-etat-des-cliquets.md' }

    # Le cliquet des IDENTIFIANTS. Meme famille d'angle mort que probe_467 : la faute ne produit
    # aucun rouge, seulement un cout DIFFERE -- et ce cout est ASYMETRIQUE. Avant livraison, une
    # collision de numero est un choix de nom ; apres, c'est une REECRITURE D'HISTORIQUE (fichiers,
    # residus, references internes ET messages de commit, dont `git log --grep` depend).
    # Il porte sa contre-epreuve : 25 mutations du probe, 25 rouges du test (#468, -r4, -r10, -r11).
    # ATTENTION au sens de `--suggere` depuis #468-r10 : son corpus n'est plus << ce qui est
    # fusionne >>. Il lit AUSSI les refs hors HEAD et les NOMS ecrits dans les autres worktrees,
    # et depuis #468-r11 le CORPS DES PULL REQUESTS -- qui n'entre jamais dans l'arbre, le
    # squash-merge ne le recopiant pas dans le message de commit. Il IMPRIME sa portee : ce qu'il
    # ne peut structurellement pas voir (un numero pris et pas encore ecrit) est NOMME au lieu
    # d'etre tu. Ce chemin n'est pas joue par la banque : `Argv` ci-dessous n'a pas `--suggere`,
    # donc son cout (~3 s sans `gh`, ~6 s avec) ne touche pas le mur.
    @{ Id = 'probe_468'; Argv = @('probe_468_collision_numeros.py')
       Seul = 'un NUMERO de tache ou de residu ATTRIBUE DEUX FOIS -- rien dans ce depot ne les alloue : ils sont pris au vol par qui en a besoin, sans registre, et une collision ne se voit qu A L OEIL au merge. DEUX occurrences INDEPENDANTES le 2026-08-04 a quelques heures d ecart (#465, deux `#465-r1` a neuf lignes d ecart ; #448-r1-r1-r2, une ligne de backlog et un dispatch). Le critere porte sur la POSITION -- premiere cellule de tableau, tete de puce, prefixe de nom de case-doc -- et JAMAIS sur la presence : sur docs/rl, 6580 occurrences `#<n>` pour 836 definitions (12,7 %), donc un critere par presence rougirait sur la quasi-totalite des renvois croises du depot. Il a trouve des son premier passage une collision QUADRUPLE jamais vue a l oeil (#420-r1 portait quatre dossiers sans rapport, dont trois OUVERTS -- RESOLUE par #468-r5 : A livre garde le numero, B/C/D renumerotes). Le mode `--suggere` DONNE un numero libre au lieu de rattraper le geste fautif, sur le critere INVERSE (l UNION, mentions et messages de commit compris : un numero seulement cite est deja pris) -- et depuis #468-r10 il DIT ce qu il ne voit pas : deux agents dispatches ensemble avaient pris `#479` du meme `--suggere` (collision DOUBLE, racine ET residu) pendant que ce cliquet rendait PASS, correctement au regard de son corpus d alors. Aucun autre cliquet ne lit les identifiants : 439 lit la banque, 462 le ledger live, 457 les tests -- tous PAR nom, aucun ne verifie que le nom designe UN seul sujet'
       Doc  = 'docs/rl/case-468-attribution-des-numeros.md' }

    # Le cliquet du WORKTREE ORPHELIN. Meme famille que probe_467/probe_468 : la faute ne produit
    # AUCUN rouge -- elle produit un etat que plus personne ne regarde. `git worktree remove` qui
    # bute sur MAX_PATH a DEJA retire l'entree admin, donc `git worktree list` dit << supprime >>
    # pendant que le repertoire reste. Cout mesure : ~5 s (six depots synthetiques montes puis
    # detruits), et l'etape 0 est le SEUL controle du depot qui lise `core.longpaths` -- une config
    # que git ne peut pas lire depuis l'arbre, donc qu'aucun fichier versionne ne peut imposer.
    @{ Id = 'probe_480r11'; Argv = @('probe_480r11_worktree_orphelin.py')
       Seul = 'un `git worktree remove` qui ECHOUE en `Filename too long` APRES avoir retire l entree administrative -- il laisse un repertoire que git ne connait plus, avec un `.git/worktrees/<id>` disparu, donc un agent que `SendMessage` ne peut plus reprendre. MESURE 2026-08-07 : 13 repertoires accumules, 392 Mo, en silence, et `fleet_board` annoncait 14 agents << reprenables >> dont la plupart ne l etaient plus, parce qu il derivait cet etat de la SEULE PRESENCE du repertoire. La cause etait EXCLUSIVE et mesurable : sur 8 worktrees, 217 chemins depassaient 260 caracteres, TOUS dans le miroir de bytecode de probe_457 (qui vivait DANS le checkout et y reencodait le chemin absolu, ecrivant le chemin du worktree DEUX FOIS), AUCUN ailleurs. Windows a LongPathsEnabled=1 et PowerShell enumere les 5109 entrees sans une seule erreur : c est GIT qui refuse, faute de `core.longpaths` -- pose en LOCAL seulement, donc perdu sur tout autre clone et invisible de toute relecture. Il porte la PORTE SYMETRIQUE (entree admin sans repertoire, que `git worktree prune` ramasse et que RIEN ne joue dans ce depot) et ses 3 mutations. Aucun autre cliquet ne lit l etat des worktrees : 467 lit la boucle mais pas `git worktree list`, 479r4 lit les BRANCHES et leur livraison, jamais l enregistrement du repertoire'
       Doc  = 'docs/rl/case-480-r11-worktree-orphelin.md' }

    # Le pendant LIVE de probe_431 : la-bas le hash de build en dur (l'IDENTITE de l'artefact),
    # ici une ADRESSE DANS l'artefact -- qui ne contient aucun hash, donc qu'aucun critere de 431
    # ne regarde. Il porte son auto-epreuve (13 formes legitimes, 5 fautives) A CHAQUE RUN.
    @{ Id = 'probe_475'; Argv = @('probe_475_pinned_addresses.py')
       Seul = 'une ADRESSE DU BINAIRE ecrite en dur qui sert a ANCRER un hook dans frida/hooks/** hors du foyer build-pin, et un pin dont la transcription est FAUSSE dans le BON build. La degradation est MUETTE : Interceptor.attach REUSSIT sur du code arbitraire, donc une adresse perimee ne se voit ni a l erreur ni au crash -- seulement a un capteur qui ne fire jamais. MESURE 2026-08-04 : les SIX adresses en dur de bucket-audit et modifier-observe etaient 6/6 PERIMEES, la seule encore armee attachant Interceptor a FUN_180026780+0x40, au milieu d une autre fonction ; cout constate, #597 a du lire un predicat au decompile faute de capteur. Le second axe (R2) est le seul controle qui attrape une transcription fausse A L INTERIEUR du bon build -- faute deja commise ici (RVA_VALUE_MOD_MODIFY valait 0x1fadfc0 pour une VA dont la RVA est 0xfadfc0, latente parce que c etait un fallback derriere un findMethod qui reussissait). probe_431 garde le HASH, jamais l adresse ; probe_283 les ORDINAUX ; probe_365 les IMPORTS ; aucun ne lit d adresse. Le critere central est ce sur quoi il NE rougit PAS : masques de bits, base ghidra d affichage, codes d exception, POISON_OFFSET, arithmetique 64 bits, et les deux formes runtime (r.base.add(offset), lib.base.add(lib.size)) qui ont fait rejeter le critere .base.add au premier passage'
       Doc  = 'docs/rl/case-475-adresses-epinglees.md' }

    # Le cliquet de la BANQUE elle-meme. Il est dans la banque, donc soumis a son propre critere.
    @{ Id = 'probe_439'; Argv = @('probe_439_cliquet_peut_rougir.py')
       Seul = 'un cliquet de CETTE banque incapable de rendre un code non nul -- il occupe la place d un garde-fou et s imprime comme << rien a signaler >> (3 occurrences, TOUTES trouvees a l oeil : probe_181 #430, probe_326 #435, et l audit manuel de #430 qui a rate la seconde)'
       Doc  = 'docs/rl/case-439-cliquet-peut-rougir.md' }

    # Le cliquet du `.git/` PARTAGE. Il ne garde ni le moteur ni la banque : il garde le DEPOT
    # comme ressource commune a l'arbre principal, aux worktrees d'agents et a ratchets-bg.
    # Sa faute ne produit AUCUN rouge chez son auteur -- elle frappe le geste SUIVANT de
    # quelqu'un d'autre, minutes plus tard, sous la forme d'un `fatal: Unable to write index`.
    # Le cliquet de l'OUTILLAGE lui-meme : les ~830 probes de premier niveau. Il ne garde ni le
    # moteur ni la banque -- il garde le fait qu'on puisse encore DISTINGUER un instrument vivant
    # d'une scorie, ce que personne ne pouvait faire avant #486-r2.
    @{ Id = 'probe_486r2'; Argv = @('probe_486r2_usage_des_probes.py')
       Seul = 'un probe a la fois ORPHELIN (nomme NULLE PART -- ni docs, ni code, ni tests, ni messages de commit, ni corps de PR) et NON EXECUTABLE. Aucun autre cliquet ne regarde les probes EUX-MEMES : probe_462r5 lit les `from X import Y` de TOUT le depot mais ne repond pas << ce fichier peut-il encore demarrer >>, probe_455 garde les tests, probe_439 la banque. Le discriminant modelise les `sys.path.insert` que le probe pose LUI-MEME (evaluation symbolique de Path(__file__).resolve().parent, .parents[k], os.path.dirname/abspath/join, /) puis ferme TRANSITIVEMENT sur les modules du depot -- sans ce modele, une premiere tentative avait rendu 22 MORTS, TOUS FAUX (les probes inserent tests/engine/runner puis importent le helper par son nom nu). Il DISTINGUE aussi les deux causes d un module introuvable : artefact PRESENT dans l arbre mais hors sys.path -> le depot est accuse (MORT) ; artefact absent -> tierce partie non installee OU module supprime, INDISCERNABLE sans manifeste de dependances (le depot n en porte aucun) -> INDETERMINE, jamais MORT. Trois contre-epreuves a chaque passage : 17 formes synthetiques (6 MORTES, 9 VIVANTES, 2 INDETERMINEES), les 29 porteurs de helper qui doivent rester VIVANTS, et une MUTATION sur sources REELLES (inserts sys.path retires -> les 14 imports doivent etre SIGNALES, sinon le discriminant est laxiste et non fidele). Une accusation portee sans le corps des PR sort en NON MESURE (99), jamais en rouge : le squash-merge ne recopie pas le corps d une PR dans l arbre'
       Doc  = 'docs/rl/case-486r2-discriminant-usage-des-probes.md' }

    @{ Id = 'probe_474'; Argv = @('probe_474_optional_locks.py')
       Seul = 'un `git status` de LECTURE qui prend `.git/index.lock` de l ARBRE PRINCIPAL depuis un contexte TUABLE (script de fond, sous-process a budget). MESURE #474 : `git status` tient son lock a 0 OCTET pendant ~toute sa duree (5/5 ; 1,2 s sur cet arbre) et un git TerminateProcess-e dans cette fenetre ne nettoie rien -- 20/20 residus sur le binaire reel. Le residu est LIBRE et de 0 octet, donc indiscernable a l oeil d un lock vivant, et c est la commande SUIVANTE qui meurt dessus (3 fusions/commits interrompus en 80 min le 2026-08-04, plus 2 locks orphelins de 16 h encore presents a l instruction). Aucun autre cliquet ne regarde le `.git` partage : 434 garde le PERIMETRE de lecture, 455 les ECRITURES sous scripts/python -- aucun ne voit une ressource commune laissee verrouillee. Deux etages parce que le texte ne suffit pas : STATIQUE par AST (jamais par grep -- ce depot porte ~25 mentions de `git status` en COMMENTAIRE) et COMPORTEMENTAL sur `loop_status.Sources.git`, ou l option est posee a cote de `*args` et ou aucun littera ne nomme `status` -- l AST y est structurellement aveugle. Perimetre DERIVE de `git ls-files scripts`, sous-commandes bornees a ce qui est MESURE preneur de lock (status 3/3, describe --dirty 1/3 ; diff, ls-files, stash list, rev-parse, worktree list, for-each-ref, rev-list : 0/3) -- elargir au-dela du mesure serait la faute meme que 474 combat. Contre-epreuve : 29 epreuves, dont le retrait de l option du FOYER, que seul l etage comportemental voit'
       Doc  = 'docs/rl/case-474-index-lock-orphelin.md' }
)

# ==========================================================================================
#  Moteur. Rien a editer ici pour ajouter un cliquet.
# ==========================================================================================
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$WorkDir = Join-Path $Root 'scripts\python'

# LE TRI-ETAT (#471). Table UNIQUE, dot-sourcee -- `Get-EtatCliquet` et `Get-CodeSortieBanque`.
# Elle vit dans son propre fichier pour etre CONFRONTABLE sans etre reimplementee : dot-sourcer
# `ratchets.ps1` lui-meme JOUERAIT la banque, donc aucun garde ne pourrait l'interroger.
. (Join-Path $PSScriptRoot 'ratchets-verdict.ps1')

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

# ==========================================================================================
#  GARDE DE RETRAIT (2026-08-05, d82ec527 + b0cb6b1e).
#
#  La banque n'est plus une obligation avant PR. L'en-tete le disait deja -- et un agent l'a
#  jouee quand meme le jour meme (46 cliquets, 713 s de mur, pour une tranche qui ne touchait
#  qu'un fichier). Une consigne en PROSE dans un fichier qu'on ouvre pour le LANCER ne suffit
#  pas : elle est lue APRES la decision. Donc on REFUSE, et on le dit.
#
#  Ce qu'on ne casse PAS : `-List` sort AVANT cette garde. C'est le contrat de derivation
#  (`probe_439` lit la composition par la), et lister n'execute rien.
#
#  Pourquoi 64 et pas 1 : `1` se lit « un cliquet est rouge », soit un verdict sur le depot.
#  Un refus n'en est pas un. 64 porte deja exactement ce sens dans ce fichier -- « RIEN n'a
#  ete joue ». Ne pas inventer un code neuf : `probe_471` et `loop_status` lisent cette table.
# ==========================================================================================
if (-not $env:TACTICUS_ALLOW_RATCHETS) {
    Write-Output ''
    Write-Output '  ==================================================================='
    Write-Output '   REFUS -- LA BANQUE DE CLIQUETS N EST PLUS UNE OBLIGATION AVANT PR'
    Write-Output '  ==================================================================='
    Write-Output ''
    Write-Output '  Retiree de la doctrine le 2026-08-05 (commit d82ec527). Si tu es un agent'
    Write-Output '  et que quelque chose t a dit de la jouer, cette source est PERIMEE :'
    Write-Output '  le CLAUDE.md et le skill d orchestration ne la prescrivent plus.'
    Write-Output ''
    Write-Output '  MESURE QUI A MOTIVE LE RETRAIT (67 runs de logs/ratchets-bg) :'
    Write-Output '    2 437 lignes de cliquet jouees, 5 non nulles -- 0,21 %.'
    Write-Output '    Les 32 cliquets de GISEMENT n ont pas tire UNE SEULE FOIS.'
    Write-Output '    probe_457 pesait 67 % du cout, pour ~891 s par agent et par PR.'
    Write-Output ''
    Write-Output '  CE QUE TU DOIS FAIRE A LA PLACE :'
    Write-Output '    - les tests CIBLES de ta tranche, et tu les montres dans ton rapport ;'
    Write-Output '    - la relecture du diff de tout test EXISTANT que tu modifies.'
    Write-Output ''
    Write-Output '  UN CLIQUET PRECIS TE SERT POUR TA MESURE ? Lance-le DIRECTEMENT, c est un'
    Write-Output '  script Python autonome -- pas besoin de cet enrobage :'
    Write-Output '      python scripts/python/<probe>.py'
    Write-Output '  La composition reste lisible : pwsh -File scripts/ratchets.ps1 -List'
    Write-Output ''
    Write-Output '  Echappatoire CONSCIENTE (orchestrateur, diagnostic) :'
    Write-Output '      $env:TACTICUS_ALLOW_RATCHETS = 1'
    Write-Output ''
    Write-Output "[ratchets] rc=$EX_USAGE -- RIEN n'a ete joue. Ce n'est PAS un verdict sur le depot."
    exit $EX_USAGE
}

# `pwsh -File` ne decoupe PAS sur la virgule : `-Only a,b` arrive comme l'id litteral `a,b`.
# On re-decoupe, sinon la forme documentee ne selectionne rien -- et ne rien selectionner se
# lisait comme un rouge (cf. le code 64 ci-dessous).
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
$Skip = @($Skip | ForEach-Object { $_ -split ',' } | Where-Object { $_ })

# SELECTION PAR DIFF : transmise a `probe_457` (59 % du travail), qui restreint son perimetre aux
# fichiers de test IMPACTES -- empreinte MESUREE + graphe d'imports, tout doute rejouant TOUT.
# Les autres cliquets ne sont PAS filtres : ce sont des balayeurs d'arbre, leur perimetre est
# l'arbre entier par construction. Filtrer sur un diff n'y aurait aucun sens.
if ($Since) {
    $Ratchets = $Ratchets | ForEach-Object {
        $e = $_.Clone()
        if ($e.Argv[0] -like 'probe_457*') { $e.Argv = @($e.Argv) + @('--since', $Since) }
        $e
    }
}

$sel = $Ratchets
if ($Only) { $sel = $sel | Where-Object { $id = $_.Id; ($Only | Where-Object { $id -eq $_ -or $id.StartsWith($_ + ':') }).Count -gt 0 } }
if ($Skip) { $sel = $sel | Where-Object { $id = $_.Id; ($Skip | Where-Object { $id -eq $_ -or $id.StartsWith($_ + ':') }).Count -eq 0 } }
$sel = @($sel)

# 64 = erreur d'USAGE, jamais un verdict. Rendre 1 ici la rendait indistinguable d'un cliquet
# rouge : l'appelant lisait « 1 rouge » alors que RIEN n'avait tourne. Contrat documente en .OUTPUTS.
# La CONSTANTE vient de `ratchets-verdict.ps1` (dot-source plus haut) : la redefinir ici ferait
# exister deux sources pour un meme contrat -- c'est ce que #430 combat sur la banque elle-meme.

if ($sel.Count -eq 0) {
    Write-Output "[ratchets] USAGE : aucun cliquet selectionne. `-List` pour voir la banque."
    Write-Output "[ratchets] rc=$EX_USAGE -- RIEN n'a ete joue. Ce n'est PAS un verdict sur le depot."
    exit $EX_USAGE
}
if (-not (Test-Path $WorkDir)) {
    Write-Output ("[ratchets] USAGE : repertoire introuvable : {0}" -f $WorkDir)
    Write-Output "[ratchets] rc=$EX_USAGE -- RIEN n'a ete joue. Ce n'est PAS un verdict sur le depot."
    exit $EX_USAGE
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Output "[ratchets] USAGE : `python` introuvable dans le PATH (ne PAS utiliser `py` : il skippe des dependances)."
    Write-Output "[ratchets] rc=$EX_USAGE -- RIEN n'a ete joue. Ce n'est PAS un verdict sur le depot."
    exit $EX_USAGE
}

if (-not $LogDir) { $LogDir = Join-Path $Root 'logs\ratchets' }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# ------------------------------------------------------------------ ORDONNANCEMENT (#457-r6)
# `ForEach-Object -Parallel` consomme la liste DANS L'ORDRE de la liste. Un cliquet de 90 s
# lance en DERNIER se colle en fin de mur ; lance en PREMIER, il est recouvert par tous les
# autres. Mesure du 2026-08-02 : somme ISOLEE 675 s, mais mur 244 s pour un plus-long-cliquet
# de 89,7 s -- l'ecart etait de l'ORDRE et de la CONTENTION, pas du travail.
#
# LPT (longest processing time first) : on trie par duree DECROISSANTE. Les durees viennent du
# run PRECEDENT (`durations.json`, sous `logs/`, gitignore) -- elles se MESURENT, elles ne se
# declarent pas, donc aucune liste de poids a maintenir. Un cliquet INCONNU passe en TETE :
# on ignore son cout, on le suppose donc maximal (le choix sur).
#
# L'ordre n'affecte NI le verdict NI le code de sortie -- des poids perimes coutent du mur,
# jamais un faux vert. C'est precisement pourquoi ce fichier peut vivre hors du depot.
$durPath = Join-Path $LogDir 'durations.json'
$dur = @{}
if (Test-Path $durPath) {
    try {
        (Get-Content $durPath -Raw | ConvertFrom-Json).PSObject.Properties |
            ForEach-Object { $dur[$_.Name] = [double] $_.Value }
    } catch { $dur = @{} }
}
if ($dur.Count -gt 0) {
    $sel = @($sel | Sort-Object -Property `
        @{ Expression = { if ($dur.ContainsKey($_.Id)) { $dur[$_.Id] } else { [double]::MaxValue } }
           Descending = $true })
}

# Parallelisme. Le defaut vise les coeurs PHYSIQUES, pas les logiques : ces cliquets sont des
# process Python liants en CPU, et deux d'entre eux sur les deux fils d'un meme coeur se
# ralentissent mutuellement. Mesure du 2026-08-02 sur un Ultra 9 185H (16 physiques / 22
# logiques) : a 22, `probe_391` passe de 5,4 s isole a 98,5 s -- x18, entierement de la
# contention. On plafonne donc au nombre de coeurs physiques quand on sait le lire.
$physical = $null
try { $physical = (Get-CimInstance Win32_Processor -ErrorAction Stop | Measure-Object -Property NumberOfCores -Sum).Sum } catch { }
if (-not $physical -or $physical -lt 1) { $physical = [Environment]::ProcessorCount }
$throttle = if ($Serial) { 1 } elseif ($ThrottleLimit -gt 0) { $ThrottleLimit }
            else { [Math]::Min($sel.Count, $physical) }

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

# Les durees MESUREES de ce run alimentent l'ordonnancement du suivant. FUSION avec l'existant :
# sous `-Only`/`-Skip` on ne mesure qu'une partie de la banque, et ecraser le fichier perdrait
# le poids des cliquets non joues (donc les renverrait en tete au run d'apres, pour rien).
foreach ($r in $results) { $dur[$r.Id] = $r.Sec }
try { $dur | ConvertTo-Json -Compress | Set-Content -Path $durPath -Encoding utf8 } catch { }

# TRI-ETAT (#471) : trois seaux, pas deux. `Get-EtatCliquet` est la table UNIQUE.
$results = @($results | Sort-Object -Property @{ Expression = { $_.Rc -eq 0 } }, @{ Expression = 'Sec'; Descending = $true })
$rouges   = @($results | Where-Object { (Get-EtatCliquet $_.Rc) -eq 'ROUGE' })
$indispos = @($results | Where-Object { (Get-EtatCliquet $_.Rc) -eq 'INDISPO' })

foreach ($r in $results) {
    $etat = switch (Get-EtatCliquet $r.Rc) {
        'OK'      { 'OK    ' }
        'INDISPO' { 'INDISP' }
        default   { 'ROUGE ' }
    }
    Write-Output ("  {0} {1,-22} {2,7} s   rc={3}" -f $etat, $r.Id, $r.Sec, $r.Rc)
}
Write-Output ""

# Motif de la CAUSE. Chaque alternative est ANCREE en debut de ligne ou porte un separateur :
# un motif large noie la cause sous les lignes VERTES du meme probe -- mesure #430, `MANQUANT`
# non ancre matchait les `MANQUANTS=0` de probe_313 et repoussait la seule ligne utile hors cadre.
$rxFail = 'AssertionError|Traceback|\bBLOQUANT|VERDICT:\s*FAIL|\]\s*ROUGE|[A-Za-z]Error:' +
          '|^\s*(E\s|FAILED\b|ROUGE\b|FAIL\b|MANQUANT\b|MORT\b|MORTE\b|INTROUVABLE\b|ORPHELINE\b|RENUMEROTE\b)'
# Motif de la cause d'une INDISPONIBILITE (#471). Distinct : un cliquet qui n'a rien mesure DIT
# pourquoi (`REFUS`, `rc=99`, `aucun verdict`), et ces lignes-la ne matchent aucun motif de faute.
# Sans motif propre, l'extrait retomberait sur la queue du log et noierait la cause reelle.
$rxIndispo = 'REFUS|NON MESURE|non mesure|aucun verdict|MONTAGE|rc=99|rc=64|USAGE|' +
             'CalledProcessError|Traceback|[A-Za-z]Error:'

function Show-Detail {
    param($R, [string] $Bandeau, [string] $Regex, [string] $Note)
    Write-Output ("=" * 88)
    Write-Output ("{0}  {1}   (rc={2}, {3} s)" -f $Bandeau, $R.Id, $R.Rc, $R.Sec)
    if ($Note) { Write-Output ("  {0}" -f $Note) }
    Write-Output ("  commande      : cd scripts/python ; {0}" -f $R.Cmd)
    Write-Output ("  seul a voir   : {0}" -f (Convert-ToAscii $R.Seul))
    Write-Output ("  doc           : {0}" -f $R.Doc)
    Write-Output ("  log complet   : {0}" -f $R.Log)
    $nonVides = @($R.Out | Where-Object { $_.Trim() -ne '' })
    $lignes = @($nonVides | Where-Object { $_ -match $Regex })
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

foreach ($r in $rouges) { Show-Detail $r 'ROUGE' $rxFail '' }
# Les INDISPONIBLES sont affiches avec le MEME niveau de detail : ils ne se taisent pas. Ce qui
# change, c'est l'ACCUSE -- le harnais, pas le code fusionne -- donc la conduite a tenir.
foreach ($r in $indispos) {
    Show-Detail $r 'INDISPONIBLE' $rxIndispo `
        'RIEN N A ETE MESURE ici : ce cliquet accuse le HARNAIS, pas le code. Rejouer CETTE entree seule ; si elle passe, la cause etait transitoire -- le DIRE dans la PR, ne pas la taire.'
}
if ($rouges.Count -gt 0 -or $indispos.Count -gt 0) { Write-Output ("=" * 88) }

$mur = [Math]::Round($wall.Elapsed.TotalSeconds, 1)
$ids = { param($x) ($x | ForEach-Object { $_.Id }) -join ', ' }
if ($rouges.Count -eq 0 -and $indispos.Count -eq 0) {
    Write-Output ("[ratchets] BANQUE VERTE -- {0} cliquet(s), mur {1} s." -f $sel.Count, $mur)
} elseif ($rouges.Count -eq 0) {
    Write-Output ("[ratchets] BANQUE INDISPONIBLE -- {0}/{1} cliquet(s) n'ont RIEN MESURE : {2}. Mur {3} s." `
        -f $indispos.Count, $sel.Count, (& $ids $indispos), $mur)
    Write-Output "[ratchets] Aucun rouge par ailleurs. Ce n'est PAS un verdict favorable sur le depot :"
    Write-Output "[ratchets] c'est l'absence de verdict sur ces entrees-la."
} else {
    Write-Output ("[ratchets] BANQUE ROUGE -- {0}/{1} cliquet(s) : {2}. Mur {3} s." `
        -f $rouges.Count, $sel.Count, (& $ids $rouges), $mur)
    if ($indispos.Count -gt 0) {
        # Le rouge prime dans le CODE de sortie ; l'indisponible doit rester LISIBLE quand meme,
        # sinon corriger le rouge rendrait la banque verte sur une entree jamais mesuree.
        Write-Output ("[ratchets] + {0} cliquet(s) INDISPONIBLE(S) (rien mesure) : {1}." `
            -f $indispos.Count, (& $ids $indispos))
    }
}
exit (Get-CodeSortieBanque -Rouges $rouges.Count -Indispos $indispos.Count)
