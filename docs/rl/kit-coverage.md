# Couverture moteur par KIT (unites lineup)

> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur
> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`
> (par-ability). **Ne jamais fusionner un conflit sur ce fichier : le REGENERER.**
>
> Faces : `[CD]` = combat/decision portees, `[--]` = aucune ; `D` couvre les TROIS
> registres de scoring (non-comparables + overrides custom des comparables +
> sous-classes `AActiveAbility` par ability). La mention « NC classee, utilite NC non
> portee » marque une ability reconnue NonComparable dont l'utilite reste a porter :
> c'est un travail restant, pas une face couverte. Les MISSING passifs/traits sont des
> CANDIDATS (approximation registres, cf. docstring du script) : trancher au recon du kit.
>
> **Ce que le total compte** : les items du kit INTRINSEQUE (`activeAbilities`,
> `passiveAbilities`, traits de kit). **Ce qu'il ne compte pas** : les voies
> CONDITIONNELLES (mythique a debloquer, relique a equiper) — elles ont leur propre
> section, chiffree, en fin de document. ⚠ CONDITIONNEL vaut pour le JEU, pas pour le
> HARNAIS : les deux voies se MONTENT en runner (`--equip-relic` #237,
> `--equip-mythic` #999) et 2 des 11 mythiques sont confrontees en live (#1024).
> Les voies `trait`/`liveevent`/`summon`/`tile`
> ne sont derivables d'aucune source offline (`case-323-unit-map-attribution-voies.md`).
>
> Sections detaillees ordonnees par NOM de faction (ordre stable, pour qu'une
> regeneration ne produise un diff que la ou le contenu bouge) ; la priorisation par
> volume est la table de bilan ci-dessous.

## Bilan

- Unites lineup : **127** ; kits COMPLETS (aucun manque detecte) : **127** ; kits avec du travail : **0**
- Volume total : **0** items manquants (actives no-op + passifs/traits non registres)
- HORS total — voies conditionnelles : **4** abilities non portees (3 mythiques, 1 reliques equipables), dont **3 PARTIELLES**
- PARTIELS (#1041) — montage DECLARE, rien ne s'execute : **3** conditionnelle(s) (CabalOfSorcerers, GuardianConstruct, TheArdentBlade) ; **0** passif(s)
- HORS total — faces DECISION non portees : **3** actives sur 138, dont **3** dans des kits declares COMPLETS (3 kits concernes)
- DECOMPTES par un verdict ATTESTE : **10** (et **0** attestation(s) PERIMEE(S), dont l'item est REDEVENU manquant) — section dediee plus bas, jamais tue

### Priorite par faction (volume decroissant)

| faction | kits | items |
|---|---:|---:|

## Par faction (kits avec du travail)

## HORS total — faces DECISION non portees dans des kits COMPLETS (3)

> ⚠ **`missing` NE COMPTE QUE LA FACE COMBAT.** Une ability dont l'execution est
> portee mais dont l'UTILITE de decision ne l'est pas rend `missing = 0` : le kit
> sort << COMPLET >>, et son marqueur `[C-]` n'etait imprime nulle part, la section
> par faction ne rendant que les kits AVEC du travail. C'est le meme angle mort que
> #323 (un recensement qui rend zero sur ce qu'il ne visite pas), sur l'axe DECIDER.
>
> Consequence : l'IA CHOISIT ces abilities avec un scoring qui n'est pas celui du
> natif — divergence de POLITIQUE, invisible en replay puisque l'execution, elle,
> est fidele. Cf. doctrine « DECIDER != EXECUTER », face DECISION.
>
> Ces entrees restent **hors du total** : elles ne sont pas des items de kit
> manquants, ce sont des faces manquantes d'items presents. Les fondre dans
> `missing` changerait le sens du chiffre cite partout.

| unite | ability | id | categorie |
|---|---|---:|---|
| astraOrdnance | BasiliskBarrage | 1026 | DAMAGE(Blast) |
| spaceWolfPriest | RitesOfMorkai | 1211 | EFFECT/BUFF |
| ultraDreadnought | MacroPlasmaIncinerator | 1159 | DAMAGE(Plasma) |

## Verdicts ATTESTES — decomptes du total, et JAMAIS tus (10 valides, 0 perimees)

> Un item peut manquer aux registres pour une raison parfaitement legitime : **le
> natif n'a rien de propre a porter**, ou le mecanisme est porte par une voie SANS
> registre. Ecrit uniquement dans une case-doc, ce verdict ne survit a aucun outil —
> `1204 LeadingTheCharge` (prouvee SANS CONTENU PROPRE par #945) et `GalvanicField`
> (verdict MESURE par #952) etaient recomptes manquants a chaque regeneration, et un
> agent a failli etre redispatche dessus.
>
> Ce ne sont PAS des exceptions codees en dur. Chaque entree de
> `scripts/ratchets-951r2-couverture-attestee.json` porte sa RAISON, sa SOURCE, son
> BUILD et un ANCRAGE VERIFIABLE (le cliquet qui garde le verdict, et/ou le symbole
> qui porte le mecanisme). Foyer UNIQUE de validite :
> `scripts/python/coverage_attestations.py::validite`.
>
> ⚠ **L'asymetrie est INVERSE de celle du ledger #462/#465, et c'est structurel** :
> ici l'attestation EST le geste permissif (elle RETIRE du travail du compte). Une
> attestation PERIMEE — build change, cliquet disparu, porteur non resolvable —
> **REMET son item au compte des manquants**. Aucun chemin ne peut faire disparaitre
> du travail : la peremption ne sait que EN RAJOUTER. Un audit qui sous-compte fait
> RENONCER, ce qui est pire qu'un audit qui sur-compte et fait perdre du temps.

| item | verdict | ancrage | source | raison |
|---|---|---|---|---|
| active-decision:DevoutPush | RIEN_A_PORTER | `test_1021_face_decision_au_registre_offline.py` | docs/rl/case-996-r1-precisionshot-devoutpush.md#2 | IdunBattle.AI.Playbook.Loki.DevoutPushPlaybook ne declare AUCUNE methode propre : son corps ENTIER est `ALoki_NormalAttackPlaybook<T>..ctor(this, 0x41d = 1053)`. Il n'y a donc rien de PROPRE a porter. TROIS sources independantes, l'absence d'une methode dans les tables ne prouvant rien (dedup IL2CPP). (a) Ghidra : `search_symbols_by_name` sur `IdunBattle.AI.Playbook.Loki.DevoutPushPlaybook` rend UN SEUL symbole, son `.ctor`, et son decompile est ce seul appel. (b) `ghidra/functions.tsv` par la voie de `probe_909.methodes_par_classe` : la classe porte `('.ctor', 64 octets)` et RIEN d'autre, la ou `ALoki_NormalAttackPlaybook<T>` porte `CalculateCustomUtility`, `MakeDamagePredictions` et `ShouldExecute` -- et la ou ses voisines `PrecisionShot_AimPlaybook` / `PrecisionShot_AttackPlaybook` portent `EvaluateNonComparable` + `ShouldEvaluate`, ce qui montre que la mesure SAIT voir une surcharge quand il y en a une. (c) `frida/classes.tsv`, source DISTINCTE du dump : parent = `IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybook`1`, et l'instance inflatee `ALoki_NormalAttackPlaybook<IdunBattleLogic.Entities.Abilities.Active.Loki.DevoutPushAbility>` y figure -- meme famille que les 17 autres derivees, dont `MV71SniperDroneSquadAttackPlaybook`, deja attestee ici pour la MEME raison. PARTICULARITE MESUREE, ET ELLE N'EST PAS COUVERTE PAR CETTE ATTESTATION : sur les 18 derivees d'`ALoki_NormalAttackPlaybook`1`, 1053 est la SEULE dont le parametre de type n'est PAS une `*_NormalAttackAbility` -- c'est une ACTIVE DE KIT. Le corps de la BASE (`MakeDamagePredictions` = UN `ProbableDamageEvent` bati sur le slot 0x22 d'`IBattleQuery`, `CalculateCustomUtility` = Fix64(1), `ShouldExecute`) est donc load-bearing pour elle d'une facon qu'il n'est pour aucune autre. Ce corps est un fait de la BASE, commun aux 18, il ne se porte pas 18 fois -- residus #1021-r1 (deja ouvert) et #996-r1-r2 (la particularite 1053). |
| active-decision:EntropyCannons | RIEN_A_PORTER | `test_1021_face_decision_au_registre_offline.py` | docs/rl/case-970-r3-deux-faces-decision-squig-launchas-entropy-cannons.md#2 | `IdunBattle.AI.Playbook.EntropyCannonsPlaybook` porte DEUX corps -- `.ctor` et `MakeDamagePredictions` -- et son `MakeDamagePredictions` est la forme CANONIQUE, celle que le chemin generique du port emprunte deja (`prediction/abilities.py::make_damage_predictions`). Il n'y a donc rien de PROPRE a porter. Le corps, relu verbatim : `damage = ability.GetDamage(abilityState)` (corps dedup `...Loki.VigilanceEternalAbility$$GetDamage`, lui-meme relu = `AActiveAbility$$MinMaxDamage(this, state, isPrediction: 0)`, la forme (b)) ; `hits = AActiveAbility$$GetHits()` ; `profile = AActiveAbility$$GetDamageProfile()` ; `sel = this.dsl@+0x18 ->+0x90 ->+0x60` = `DSLSelectors.Target` ; puis UN SEUL appel a `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions(caster, casterPosition, target, sel, damage, hits, Nullable(profile), default, 0)`, poids Nullable VIDE. QUATRE sources independantes, l'absence d'un symbole dans les tables ne prouvant rien (dedup IL2CPP). (a) EMPREINTE STRUCTURELLE, `data/symbols/rnca9r7q6c/fingerprints/functions.tsv` : `EntropyCannonsPlaybook$$MakeDamagePredictions` partage `taille=381`, `n_ins=82`, `h_body=22f58035eafb`, `h_mnem=67e23d86827b` et `h_calls=100f3df5c794` avec EXACTEMENT deux autres fonctions du build -- `...Loki.LashOfTormentPlaybook$$MakeDamagePredictions`, DEJA attestee `RIEN_A_PORTER` ici meme, et `...Loki.MightFromBelowPlaybook$$MakeDamagePredictions`, dont la case-doc du port ecrit << la forme CANONIQUE, mot pour mot [...] Aucune entree n'est surchargee [...] Rien a poser de ce cote >>. Meme `h_calls` = le `GetDamage` appele est le meme corps dedup. TEMOIN QUE L'EMPREINTE DISCRIMINE, et il est necessaire : `...Loki.ArmoriumCherubPlaybook$$MakeDamagePredictions` a la MEME taille, le MEME `n_ins` et le MEME `h_mnem`, mais `h_body=5aa6395d0578` et `h_calls=9758bd6bbf0b`, tous deux DIFFERENTS -- un squelette identique ne suffit donc pas a faire passer un corps pour un autre, ce sont `h_body` et `h_calls` qui tranchent, et ils concordent pour 1168. (b) RECENSEMENT DE CLASSE, `ghidra/functions.tsv` par prefixe : `EntropyCannonsPlaybook` = 2 corps, la ou `...Loki.MightFromBelowPlaybook` en porte 3 (+ `CalculateCasterPositionUtility`, qui EST son seul delta et qui, elle, est portee au registre) et `...Loki.ArmoriumCherubPlaybook` 6 (`CalculateCustomUtility`, `CanKillTarget`, `GetNumEnemiesInNormalAttackRange`, `ShouldExecute`) -- la mesure SAIT voir une surcharge quand il y en a une. (c) `frida/classes.tsv`, source DISTINCTE du dump : parent = `IdunBattle.AI.Playbook.ComparablePlaybook`1`, taille 112, LE MEME que `LashOfTorment` et `MightFromBelow` -- aucune classe intermediaire ne s'interpose. (d) `mcp__ghidra__search_symbols_by_name` sur `EntropyCannonsPlaybook` rend 2 symboles, les memes deux. COHERENCE COTE PORT, VERIFIEE : `1168` figure DEJA dans `engine/entities/abilities/active_ability.py::_PREDICTION_MINMAX_RANDOM_READ` (la famille (b), qui coincide avec le defaut), et la classe n'a AUCUN `.cctor` ni `ShouldExecute` -- elle n'est donc PAS l'une des douze de `engine/playbook/static_threshold_gate.py`, dont le gate est precisement un `<X>Playbook$$ShouldExecute` lisant le premier static de sa classe. Son absence des deux tuples `DERIVED_CCTOR_IDS` / `NO_DERIVED_CCTOR_IDS` est donc CORRECTE. Appariement LU (mesure POSITIVE) dans `data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` : `active 1168 IdunBattle.AI.Playbook.EntropyCannonsPlaybook`. NE PAS CONFONDRE : la meme table porte `triggered 1168 ...Loki.ArchContaminatorPlaybook` -- un `TriggeredAbilityType` a ordinal egal, un AUTRE enum. |
| active-decision:ExcruciatingFrequencies | PORTE_HORS_REGISTRE | `test_979_recenseur_faces_decision_offline.py` | docs/rl/case-979-recenseur-faces-decision.md#4 | Sa face DECISION est portee par un GENERATEUR bespoke appele EN DUR dans ComparableAbilityGenerator.generate (ligne `cands += excruciating_frequencies_candidates(ctx)`), pas par un registre : le playbook natif cible une TUILE (ligne-AoE) et ses evals ont rankCount=0, donc aucun `plan` ne l'amene. Son gate ShouldExecute (seuil statique Fix64(10)) y vit sous MIN_UTILITY, ce que `static_threshold_gate.NOT_REGISTERED` dit deja de son cote. Aucun conteneur de niveau module ne peut donc l'exprimer -- c'est exactement le cas que ce ledger existe pour porter. |
| active-decision:LashOfTorment | RIEN_A_PORTER | `test_974_custodes_emperors_children_decision_offline.py` | docs/rl/case-979-recenseur-faces-decision.md#3 | IdunBattle.AI.Playbook.Loki.LashOfTormentPlaybook$$MakeDamagePredictions fait UN SEUL appel a ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions, avec sel = this@+0x18 (le dsl) ->+0x90 ->+0x60 = DSLSelectors.Target, base = VigilanceEternalAbility$$GetDamage (= MinMaxDamage(state, isPrediction:0), forme (b)), hits = AActiveAbility$$GetHits, prof = Nullable(AActiveAbility$$GetDamageProfile), poids = Nullable VIDE. C'est le chemin GENERIQUE du port, terme pour terme : l'inscrire a un registre d'override serait un port SPECULATIF. Verdict etabli par #974, RELU au decompile par #979. |
| active-decision:LeadingTheCharge | RIEN_A_PORTER | `test_945_loki_decision_faces_offline.py` | docs/rl/case-945-loki-faces-decision.md#7 | IdunBattle.AI.Playbook.Loki.LeadingTheChargePlaybook$$MakeDamagePredictions est STRUCTURELLEMENT identique au corps generique (que des appels DIRECTS aux corps de la classe de base : GetDamage -> AActiveAbility$$MinMaxDamage, GetHits, GetDamageProfile, GenerateMultiHitAttackPredictions). IL2CPP replique le corps de DefaultActiveAbilityPlaybook dans chaque specialisation : compter les symboles ne dit pas ce qui est surcharge. 1204 est deja dans _A_VIA_STAFF_OF_STARS_GET_DAMAGE (#344), qui EST le chemin generique du port. |
| active-decision:MV71SniperDroneSquadAttack | RIEN_A_PORTER | `test_1021_face_decision_au_registre_offline.py` | docs/rl/case-1021-cran-face-decision-au-registre.md#4 | 1076 est une ATTAQUE NORMALE concrete, pas une active de kit, et son playbook natif ne surcharge RIEN -- il n'y a donc aucun contenu PROPRE a porter. Trois sources independantes, l'absence d'une methode dans les tables ne prouvant rien (dedup IL2CPP). (a) Ghidra : `search_symbols_by_name` sur `IdunBattle.AI.Playbook.Loki.MV71SniperDroneSquadAttackPlaybook` rend UN SEUL symbole, son `.ctor`, qui appelle `IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor(this, 0x434 = 1076)`. (b) `frida/classes.tsv`, source DISTINCTE du dump : le parent de la classe d'ABILITY est `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility` -- celle que le CLAUDE.md nomme pour l'attaque normale -- et la chaine du playbook est `ALoki_NormalAttackPlaybook<T>` -> `ComparablePlaybook<T>` -> `Playbook<T>` -> `BasePlaybook`. (c) gameconfig : 1076 n'apparait dans AUCUNE cle de kit, ni par NOM ni par ORDINAL (balayage exhaustif), ce qui est exactement le regime d'une attaque normale, attribuee au runtime par `NormalAttackType@0x28`. TEMOIN DE FAMILLE : `ALoki_NormalAttackPlaybook<T>` compte 17 classes derivees, dont 15 coquilles sans methode propre, TOUTES les 17 NON PORTEE, et une seule au registre COMBAT -- celle-ci ; `Loki_NormalAttackPlaybook` (id 69, l'attaque normale generique) y est coquille et non portee. CE QUI RESTE, ET QUI N'EST PAS PROPRE A 1076 : la BASE porte `CalculateCustomUtility` = `Fix64(1)` et `ShouldExecute` = `if (IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility(unit, 0x48 = 72 Explosive)) return false; return utility > Fix64(0);`. Ce gate est un fait de la BASE, commun aux 17, il ne se porte pas 17 fois -- residu #1021-r1. |
| active-decision:PrecisionShot | RIEN_A_PORTER | `test_1021_face_decision_au_registre_offline.py` | docs/rl/case-996-r1-r3-precisionshot.md#6 | Le dict `+0x68` d'`IdunBattle.AI.PlaybookDatabase` (peuple par `IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`) apparie `1015 PrecisionShot` a `IdunBattle.AI.Playbook.Common.DefaultActiveAbilityPlaybook` -- le playbook GENERIQUE COMMUN. Il n'y a donc AUCUNE classe propre a 1015, et rien de PROPRE a porter : le natif la fait evaluer par le meme chemin generique que le port emprunte deja. C'est une mesure POSITIVE (la table DIT quelle classe est appariee), pas une absence -- distinction qui compte, l'absence d'un symbole dans les tables ne prouvant rien (dedup IL2CPP). TROIS sources independantes : (a) `data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` porte la ligne `active\t1015\tIdunBattle.AI.Playbook.Common.DefaultActiveAbilityPlaybook`, et 1015 est la SEULE des 233 actives du dict a retomber sur ce playbook generique -- les 232 autres ont une classe propre ; (b) `mcp__ghidra__search_symbols_by_name` sur `PrecisionShotPlaybook` rend **0** symbole, alors que les deux soeurs du triptyque rendent chacune 4 symboles (`PrecisionShot_AimPlaybook` / `PrecisionShot_AttackPlaybook` : `.ctor`, `.cctor`, `EvaluateNonComparable`, `ShouldEvaluate`) ; (c) `ghidra/functions.tsv` ne porte aucune fonction dont le prefixe de classe soit `...Playbook.Loki.PrecisionShotPlaybook`. Coherent avec la RE de la face COMBAT : 1015 est une FACADE dont l'`ExecuteBehaviour` n'est jamais atteint en regime naturel (cf. la case-doc), donc l'IA n'a rien de propre a evaluer pour elle. ⚠ NE VAUT PAS pour `1012 PrecisionShot_Aim`, dont le playbook propre porte un vrai `EvaluateNonComparable` + `ShouldEvaluate` -> inscrite en DETTE `SANS_VERDICT` (#996-r1-r3). |
| active-decision:StrikeFromTheShadows | RIEN_A_PORTER | `test_976_lot_astartes_astra_offline.py` | docs/rl/case-979-recenseur-faces-decision.md#3 | IdunBattle.AI.Playbook.Loki.StrikeFromTheShadowsPlaybook$$MakeDamagePredictions fait UN SEUL appel a GenerateMultiHitAttackPredictions ; son selecteur passe par StrikeFromTheShadowsAbility$$GetTarget, dont le corps entier est `return *(*(this+0x30)+0x90)+0x60` = DSLSelectors.Target -- donc PAS un selecteur propre. base/hits/prof = AActiveAbility generiques, poids Nullable VIDE. Verdict etabli par #976, RELU au decompile par #979 (le detour par GetTarget est ce qui pouvait le faire passer pour un override). |
| passif:GalvanicField | RIEN_A_PORTER | `test_952_hunters_beyond_death_offline.py` | docs/rl/case-952-hunters-beyond-death-et-galvanic-field.md#3 | GalvanicFieldAbility$$CreateBehaviour = AddFlag(0x18 CanRepairFullHealthUnits) & RemoveActiveAbility(0x1c Repair) & AddActiveAbility(0x45f Repair_GalvanicField). Les trois feuilles ont leur consommateur porte (unit_flags -> entity_can_be_repaired ; ABILITY_CLASSES[1119] ; le port ne derive jamais Repair d'un trait, donc rien a retirer), et les deux utilites de GalvanicFieldPlaybook rendent Fix64(0) -- porter le playbook ajouterait un terme nul. |
| trait:IndirectFire | PORTE_HORS_REGISTRE | `engine.services.targeting_query:INDIRECT_FIRE_TRAIT` | docs/rl/port-roadmap.md#5.1 | Le trait n'a ni trigger, ni ability derivee, ni owner-effect, ni classe d'effet homonyme : il est LU IMPERATIVEMENT par ses deux consommateurs, aux deux volets natifs. (1) elevation -- TargetingQuery$$GetTilesObscuringTerrain teste HasTrait(caster, 0x3ed) avant de poser le volet ObscuringType (services/targeting_query.py, INDIRECT_FIRE_TRAIT ; threade par ability_range._has_indirect_fire). (2) Trench -- le gate IsTrench(attackerTile)+IsNeighbourOf de la reduction (services/damage_modifiers.py, damage_model.py). |

## Kits lineup COMPLETS (127)

> ⚠ **COMPLET = face COMBAT complete.** 3 de ces kits portent au moins une active
> sans face DECISION (section precedente) — ils sont marques `*` ci-dessous.

adeptCanoness, adeptCelestine, adeptExorcist, adeptHospitaller, adeptMorvenn, adeptRetributor, admecDestroyer, admecDominus, admecManipulus, admecMarshall, admecRuststalker, astarCyrus, astarLysander, astraBullgryn, astraCreed, astraDreir, astraOrdnance*, astraOrdnanceBattery, astraPrimarisPsy, astraYarrick, blackAbaddon, blackForgefiend, blackHaarken, blackObliterator, blackPossession, blackTerminator, bloodDante, bloodDeathCompany, bloodIntercessor, bloodMephiston, bloodSanguinary, bloodTerminator, custoAtlacoya, custoBladeChampion, custoKyrus, custoTrajann, custoVexilusPraetor, darkaAsmodai, darkaAzrael, darkaCompanion, darkaHellblaster, darkaSternguard, darkaStormSpeeder, darkaTerminator, deathBlightbringer, deathBlightlord, deathCrawler, deathPutrifier, deathRotbone, deathTyphus, eldarAutarch, eldarFarseer, eldarJainZar, eldarLhykhis, eldarMauganRa, eldarRanger, emperExultant, emperFlawlessBlade, emperKakophonist, emperLucius, emperNoiseMarine, genesBiophagus, genesKelermorph, genesMagus, genesPatriarch, genesPrimus, necroChronomancer, necroDestroyer, necroOverlord, necroPlasmancer, necroReanimator, necroSpyder, necroWarden, orksBigMek, orksKillaKan, orksNob, orksRukkatrukk, orksRuntherd, orksWarboss, spaceBlackmane, spaceHound, spaceRockfist, spaceStormcaller, spaceWolfPriest*, spaceWulfen, tauAunShi, tauBroadside, tauCrisis, tauDarkstrider, tauFarsight, tauMarksman, tauShadowsun, templAggressor, templAncient, templChampion, templHelbrecht, templSwordBrother, thousAhriman, thousDaemonPrince, thousInfernalMaster, thousSekhetar, thousSorcerer, thousTerminator, thousTzaangor, tyranBiovore, tyranDeathleaper, tyranNeurothrope, tyranParasite, tyranTyrantGuard, tyranWingedPrime, ultraApothecary, ultraCalgar, ultraDreadnought*, ultraEliminatorSgt, ultraInceptorSgt, ultraTigurius, ultraTitus, votanBeserk, votanChampion, votanIronmaster, votanMemnyr, votanUthar, worldEightbound, worldExecutions, worldJakhal, worldKharn, worldTerminator

## HORS total — voies conditionnelles (4 abilities non portees)

> Une unite `lineup` porte aussi des abilities par deux voies que le kit n'expose
> pas : `mythic` (`units.<kind>.<id>.mythicAbilities`, a DEBLOQUER) et `item`
> (`items[*].abilityId` + `allowedUnits`, la relique a EQUIPER). Elles sont hors du
> total parce que leur nature differe — mais les taire reproduirait la cecite de #323,
> qui a fait rendre un faux « 0 unite, DEAD ». Une relique se ventile en TROIS etats
> (equipee au seed / porteur au pool relique non equipee / porteur hors pool) :
> `case-323-unit-map-attribution-voies.md` §5. La voie `relicAbilities` ne touche
> AUCUNE unite `lineup` (0 mesure) — elle n'apparait donc pas ici.
>
> ⚠ **LA COLONNE `etat` EST UN TRI-ETAT DEPUIS #1041, PLUS UN BOOLEEN**, parce que
> le booleen etait faux DES DEUX COTES et que ne corriger qu'un sens DEGRADAIT le
> chiffre. `ABSENT` = aucune voie ne la designe. **`PARTIEL` = une voie la designe
> et son GATE tombe** : typiquement une pose d'owner-effect dont la cible n'a
> AUCUNE classe dans `EFFECT_CLASSES` — le montage est ECRIT et il ne s'execute
> RIEN. Les deux comptent comme du travail, mais ils n'appellent pas le meme :
> `ABSENT` demande un port entier, `PARTIEL` demande la face qui manque.
> Foyer : `scripts/python/kit_item_voies.py`.

| ability | voie | etat | porteurs lineup | ex. | detail |
|---|---|---|---:|---|---|
| TheArdentBlade | item | PARTIEL | 1 | adeptCelestine | ABILITY_INIT_OWNER_EFFECTS(effet-a-une-classe) |
| CabalOfSorcerers | mythic | PARTIEL | 1 | thousDaemonPrince | ABILITY_INIT_OWNER_EFFECTS(effet-a-une-classe) |
| GuardianConstruct | mythic | PARTIEL | 1 | necroReanimator | ABILITY_INIT_OWNER_EFFECTS(effet-a-une-classe) |
| ShieldOfFaith | mythic | ABSENT | 1 | adeptExorcist | - |

Portees (au moins une voie dont le gate passe) : **39** — AmuletOfTheVoidwyrm, BladeOfTheAncestors, BlightedLand, BookOfFate, ChaliceOfBaal, ContemptuousDisregard, DaemonfleshPlate, DawnBlade, Dw02AdvancedBurstCannon, ElectrochaffBackups, HeadwoppasKillchoppa, Helspear, HyperCorrosiveAcid, IntoxicatingElixir, KardiocoreGalvanus, Lakrimae, MastersOfManoeuvre, Maugetar, MawClawsOfThyrax, MonsterSlayerOfCaliban, MoreGitzOverEre, NetherRealmCasket, NornCrown, OnMyPosition, OrbsOfDecay, ParagonSpear, PhasalSubjugator, PhoenixGem, RelicBoltPistol, RelicOfLostCadia, RelicPowerFist, SabreOfSacrifice, SupaCyborkBody, TalismanOfRage, TalonOfHorus, Vitarus, VolummsMasterArtifice, WisdomOfTheAncients, WyrdmakersHelm
