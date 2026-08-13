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
> section, chiffree, en fin de document. Les voies `trait`/`liveevent`/`summon`/`tile`
> ne sont derivables d'aucune source offline (`case-323-unit-map-attribution-voies.md`).
>
> Sections detaillees ordonnees par NOM de faction (ordre stable, pour qu'une
> regeneration ne produise un diff que la ou le contenu bouge) ; la priorisation par
> volume est la table de bilan ci-dessous.

## Bilan

- Unites lineup : **127** ; kits COMPLETS (aucun manque detecte) : **124** ; kits avec du travail : **3**
- Volume total : **3** items manquants (actives no-op + passifs/traits non registres)
- HORS total — voies conditionnelles : **30** abilities non portees (11 mythiques, 19 reliques equipables)
- HORS total — faces DECISION non portees : **5** actives sur 138, dont **5** dans des kits declares COMPLETS (5 kits concernes)
- DECOMPTES par un verdict ATTESTE : **6** (et **0** attestation(s) PERIMEE(S), dont l'item est REDEVENU manquant) — section dediee plus bas, jamais tue

### Priorite par faction (volume decroissant)

| faction | kits | items |
|---|---:|---:|
| AdeptusMechanicus | 1 | 1 |
| Tau | 1 | 1 |
| ThousandSons | 1 | 1 |

## Par faction (kits avec du travail)

### AdeptusMechanicus — 1 kits, 1 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| admecDestroyer | 1 | SentinelDirectives(1139) [CD] OK | - | Vehicle(x8) |

### Tau — 1 kits, 1 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| tauFarsight | 1 | ExemplarOfTheMontka(1210) [CD] OK | WayOfTheShortBlade | - |

### ThousandSons — 1 kits, 1 items

| unite | manque | actives | passifs manquants | traits de kit manquants |
|---|---|---|---|---|
| thousDaemonPrince | 1 | AetherStride(1208) [-D] NO-OP SUMMON<br>InfernalCannon(1209) [CD] OK | - | - |

## HORS total — faces DECISION non portees dans des kits COMPLETS (5)

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
| deathCrawler | EntropyCannons | 1168 | DAMAGE(Energy) |
| orksRukkatrukk | SquigLaunchas | 1200 | DAMAGE(Physical) |
| spaceWolfPriest | RitesOfMorkai | 1211 | EFFECT/BUFF |
| ultraDreadnought | MacroPlasmaIncinerator | 1159 | DAMAGE(Plasma) |

## Verdicts ATTESTES — decomptes du total, et JAMAIS tus (6 valides, 0 perimees)

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
| active-decision:ExcruciatingFrequencies | PORTE_HORS_REGISTRE | `test_979_recenseur_faces_decision_offline.py` | docs/rl/case-979-recenseur-faces-decision.md#4 | Sa face DECISION est portee par un GENERATEUR bespoke appele EN DUR dans ComparableAbilityGenerator.generate (ligne `cands += excruciating_frequencies_candidates(ctx)`), pas par un registre : le playbook natif cible une TUILE (ligne-AoE) et ses evals ont rankCount=0, donc aucun `plan` ne l'amene. Son gate ShouldExecute (seuil statique Fix64(10)) y vit sous MIN_UTILITY, ce que `static_threshold_gate.NOT_REGISTERED` dit deja de son cote. Aucun conteneur de niveau module ne peut donc l'exprimer -- c'est exactement le cas que ce ledger existe pour porter. |
| active-decision:LashOfTorment | RIEN_A_PORTER | `test_974_custodes_emperors_children_decision_offline.py` | docs/rl/case-979-recenseur-faces-decision.md#3 | IdunBattle.AI.Playbook.Loki.LashOfTormentPlaybook$$MakeDamagePredictions fait UN SEUL appel a ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions, avec sel = this@+0x18 (le dsl) ->+0x90 ->+0x60 = DSLSelectors.Target, base = VigilanceEternalAbility$$GetDamage (= MinMaxDamage(state, isPrediction:0), forme (b)), hits = AActiveAbility$$GetHits, prof = Nullable(AActiveAbility$$GetDamageProfile), poids = Nullable VIDE. C'est le chemin GENERIQUE du port, terme pour terme : l'inscrire a un registre d'override serait un port SPECULATIF. Verdict etabli par #974, RELU au decompile par #979. |
| active-decision:LeadingTheCharge | RIEN_A_PORTER | `test_945_loki_decision_faces_offline.py` | docs/rl/case-945-loki-faces-decision.md#7 | IdunBattle.AI.Playbook.Loki.LeadingTheChargePlaybook$$MakeDamagePredictions est STRUCTURELLEMENT identique au corps generique (que des appels DIRECTS aux corps de la classe de base : GetDamage -> AActiveAbility$$MinMaxDamage, GetHits, GetDamageProfile, GenerateMultiHitAttackPredictions). IL2CPP replique le corps de DefaultActiveAbilityPlaybook dans chaque specialisation : compter les symboles ne dit pas ce qui est surcharge. 1204 est deja dans _A_VIA_STAFF_OF_STARS_GET_DAMAGE (#344), qui EST le chemin generique du port. |
| active-decision:StrikeFromTheShadows | RIEN_A_PORTER | `test_976_lot_astartes_astra_offline.py` | docs/rl/case-979-recenseur-faces-decision.md#3 | IdunBattle.AI.Playbook.Loki.StrikeFromTheShadowsPlaybook$$MakeDamagePredictions fait UN SEUL appel a GenerateMultiHitAttackPredictions ; son selecteur passe par StrikeFromTheShadowsAbility$$GetTarget, dont le corps entier est `return *(*(this+0x30)+0x90)+0x60` = DSLSelectors.Target -- donc PAS un selecteur propre. base/hits/prof = AActiveAbility generiques, poids Nullable VIDE. Verdict etabli par #976, RELU au decompile par #979 (le detour par GetTarget est ce qui pouvait le faire passer pour un override). |
| passif:GalvanicField | RIEN_A_PORTER | `test_952_hunters_beyond_death_offline.py` | docs/rl/case-952-hunters-beyond-death-et-galvanic-field.md#3 | GalvanicFieldAbility$$CreateBehaviour = AddFlag(0x18 CanRepairFullHealthUnits) & RemoveActiveAbility(0x1c Repair) & AddActiveAbility(0x45f Repair_GalvanicField). Les trois feuilles ont leur consommateur porte (unit_flags -> entity_can_be_repaired ; ABILITY_CLASSES[1119] ; le port ne derive jamais Repair d'un trait, donc rien a retirer), et les deux utilites de GalvanicFieldPlaybook rendent Fix64(0) -- porter le playbook ajouterait un terme nul. |
| trait:IndirectFire | PORTE_HORS_REGISTRE | `engine.services.targeting_query:INDIRECT_FIRE_TRAIT` | docs/rl/port-roadmap.md#5.1 | Le trait n'a ni trigger, ni ability derivee, ni owner-effect, ni classe d'effet homonyme : il est LU IMPERATIVEMENT par ses deux consommateurs, aux deux volets natifs. (1) elevation -- TargetingQuery$$GetTilesObscuringTerrain teste HasTrait(caster, 0x3ed) avant de poser le volet ObscuringType (services/targeting_query.py, INDIRECT_FIRE_TRAIT ; threade par ability_range._has_indirect_fire). (2) Trench -- le gate IsTrench(attackerTile)+IsNeighbourOf de la reduction (services/damage_modifiers.py, damage_model.py). |

## Kits lineup COMPLETS (124)

> ⚠ **COMPLET = face COMBAT complete.** 5 de ces kits portent au moins une active
> sans face DECISION (section precedente) — ils sont marques `*` ci-dessous.

adeptCanoness, adeptCelestine, adeptExorcist, adeptHospitaller, adeptMorvenn, adeptRetributor, admecDominus, admecManipulus, admecMarshall, admecRuststalker, astarCyrus, astarLysander, astraBullgryn, astraCreed, astraDreir, astraOrdnance*, astraOrdnanceBattery, astraPrimarisPsy, astraYarrick, blackAbaddon, blackForgefiend, blackHaarken, blackObliterator, blackPossession, blackTerminator, bloodDante, bloodDeathCompany, bloodIntercessor, bloodMephiston, bloodSanguinary, bloodTerminator, custoAtlacoya, custoBladeChampion, custoKyrus, custoTrajann, custoVexilusPraetor, darkaAsmodai, darkaAzrael, darkaCompanion, darkaHellblaster, darkaSternguard, darkaStormSpeeder, darkaTerminator, deathBlightbringer, deathBlightlord, deathCrawler*, deathPutrifier, deathRotbone, deathTyphus, eldarAutarch, eldarFarseer, eldarJainZar, eldarLhykhis, eldarMauganRa, eldarRanger, emperExultant, emperFlawlessBlade, emperKakophonist, emperLucius, emperNoiseMarine, genesBiophagus, genesKelermorph, genesMagus, genesPatriarch, genesPrimus, necroChronomancer, necroDestroyer, necroOverlord, necroPlasmancer, necroReanimator, necroSpyder, necroWarden, orksBigMek, orksKillaKan, orksNob, orksRukkatrukk*, orksRuntherd, orksWarboss, spaceBlackmane, spaceHound, spaceRockfist, spaceStormcaller, spaceWolfPriest*, spaceWulfen, tauAunShi, tauBroadside, tauCrisis, tauDarkstrider, tauMarksman, tauShadowsun, templAggressor, templAncient, templChampion, templHelbrecht, templSwordBrother, thousAhriman, thousInfernalMaster, thousSekhetar, thousSorcerer, thousTerminator, thousTzaangor, tyranBiovore, tyranDeathleaper, tyranNeurothrope, tyranParasite, tyranTyrantGuard, tyranWingedPrime, ultraApothecary, ultraCalgar, ultraDreadnought*, ultraEliminatorSgt, ultraInceptorSgt, ultraTigurius, ultraTitus, votanBeserk, votanChampion, votanIronmaster, votanMemnyr, votanUthar, worldEightbound, worldExecutions, worldJakhal, worldKharn, worldTerminator

## HORS total — voies conditionnelles (30 abilities non portees)

> Une unite `lineup` porte aussi des abilities par deux voies que le kit n'expose
> pas : `mythic` (`units.<kind>.<id>.mythicAbilities`, a DEBLOQUER) et `item`
> (`items[*].abilityId` + `allowedUnits`, la relique a EQUIPER). Elles sont hors du
> total parce que leur nature differe — mais les taire reproduirait la cecite de #323,
> qui a fait rendre un faux « 0 unite, DEAD ». Une relique se ventile en TROIS etats
> (equipee au seed / porteur au pool relique non equipee / porteur hors pool) :
> `case-323-unit-map-attribution-voies.md` §5. La voie `relicAbilities` ne touche
> AUCUNE unite `lineup` (0 mesure) — elle n'apparait donc pas ici.

| ability | voie | porteurs lineup | ex. |
|---|---|---:|---|
| BladeOfTheAncestors | item | 1 | votanUthar |
| BookOfFate | item | 3 | blackPossession, thousInfernalMaster, thousSorcerer |
| ChaliceOfBaal | item | 1 | bloodSanguinary |
| Dw02AdvancedBurstCannon | item | 1 | tauCrisis |
| HeadwoppasKillchoppa | item | 1 | orksWarboss |
| Helspear | item | 1 | blackHaarken |
| Maugetar | item | 1 | eldarMauganRa |
| MonsterSlayerOfCaliban | item | 1 | darkaCompanion |
| NornCrown | item | 1 | tyranNeurothrope |
| ParagonSpear | item | 1 | custoKyrus |
| PhasalSubjugator | item | 1 | necroOverlord |
| PhoenixGem | item | 1 | eldarAutarch |
| RelicOfLostCadia | item | 3 | astraBullgryn, astraOrdnance, astraPrimarisPsy |
| RelicPowerFist | item | 3 | bloodIntercessor, darkaTerminator, templAggressor |
| SabreOfSacrifice | item | 1 | astraDreir |
| TheArdentBlade | item | 1 | adeptCelestine |
| Vitarus | item | 1 | bloodMephiston |
| VolummsMasterArtifice | item | 1 | votanIronmaster |
| WyrdmakersHelm | item | 1 | spaceWolfPriest |
| BlightedLand | mythic | 1 | deathCrawler |
| CabalOfSorcerers | mythic | 1 | thousDaemonPrince |
| ContemptuousDisregard | mythic | 1 | blackForgefiend |
| ElectrochaffBackups | mythic | 1 | tauBroadside |
| GuardianConstruct | mythic | 1 | necroReanimator |
| HyperCorrosiveAcid | mythic | 1 | tyranBiovore |
| MastersOfManoeuvre | mythic | 1 | darkaStormSpeeder |
| MoreGitzOverEre | mythic | 1 | orksRukkatrukk |
| OnMyPosition | mythic | 1 | astraOrdnanceBattery |
| ShieldOfFaith | mythic | 1 | adeptExorcist |
| WisdomOfTheAncients | mythic | 1 | ultraDreadnought |

Portees (au moins un registre) : **13** — AmuletOfTheVoidwyrm, DaemonfleshPlate, DawnBlade, IntoxicatingElixir, KardiocoreGalvanus, Lakrimae, MawClawsOfThyrax, NetherRealmCasket, OrbsOfDecay, RelicBoltPistol, SupaCyborkBody, TalismanOfRage, TalonOfHorus
