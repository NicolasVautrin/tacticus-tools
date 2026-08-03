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
    Code de sortie = NOMBRE de cliquets rouges (0 = banque verte). Sortie ASCII stricte (cp1252).

    ⚠ EXCEPTION, et c'est un CONTRAT : une erreur d'USAGE (aucun cliquet selectionne, repertoire
    introuvable, `python` absent du PATH) rend **64**, jamais 1. Elle rendait 1, donc elle etait
    INDISTINGUABLE d'« un cliquet a rougi » -- un appelant lisait « 1 rouge » la ou RIEN n'avait
    ete joue. C'est la faute que `#457-r7` nomme sur `probe_457` (un `pytest rc=4` d'usage lu comme
    un rouge de gisement), et de la meme famille que « un echec RENDU se lit comme une mesure ».
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

    @{ Id = 'probe_449r2'; Argv = @('probe_449r2_spread_inventory.py')
       Seul = 'un port de la face COMBAT qui suppose l ABSENCE de variance d arme sur un montant sans l avoir LUE (le byte AttackDamageBehaviourOptions+6), le sens inverse (un zero JUSTE qu on retire), et surtout la VALEUR PAR DEFAUT de chaque porte de variance -- c est elle qui porte la decision, puisque deux des trois porteurs a variance nulle n ECRIVENT PAS le mot-cle. Le gisement est invisible au grep (5 des 6 occurrences textuelles de spread_pct=0 sont des commentaires) et invisible a un inventaire par mot-cle (un call-site peut passer la variance POSITIONNELLEMENT). Il voit aussi un parametre de variance devenu MORT -- accepte et lu nulle part, donc plus jamais applique, sans qu un seul call-site change'
       Doc  = 'docs/rl/case-449-r2-spread-face-combat.md (#449-r2-r5)' }

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

    @{ Id = 'probe_431'; Argv = @('probe_431_build_literals.py', '--cliquet')
       Seul = 'un hash de build ecrit en dur qui RESOUT un artefact du jeu (chemin de GameAssembly.dll, table de symboles, defaut de --build) HORS du foyer build_pin : le litteral court-circuite a la fois data/symbols/CURRENT et le binaire installe, donc symbols_sync peut etre VERT pendant que le script lit un autre build. Depuis #458 il voit AUSSI son propre perimetre : toute extension presente dans l arbre et hors des trois seaux le fait rougir. Ce second axe est ce qui le rendait creux -- ses globs passaient par Path.match, qui ne developpe pas ** : 967 fichiers versionnes tombaient dans AUCUN seau (tout scripts/python/engine, tout tests/, et par le HAUT frida/host/router.ts et frida/hooks/main.ts), lus puis jetes en silence sous un denominateur qui se lisait comme une couverture'
       Doc  = 'docs/rl/case-431-litteraux-de-build.md ; docs/rl/case-458-perimetre-derive-du-cliquet-431.md' }

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
$EX_USAGE = 64

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
