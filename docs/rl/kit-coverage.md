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
- HORS total — voies conditionnelles : **0** abilities non portees (0 mythiques, 0 reliques equipables), dont **0 PARTIELLES**
- PARTIELS (#1041) — montage DECLARE, rien ne s'execute : **0** conditionnelle(s) ; **0** passif(s)
- HORS total — faces DECISION non portees : **5** actives sur 138, dont **5** dans des kits declares COMPLETS (5 kits concernes)
- DECOMPTES par un verdict ATTESTE : **0** (et **10** attestation(s) PERIMEE(S), dont l'item est REDEVENU manquant) — section dediee plus bas, jamais tue

### Priorite par faction (volume decroissant)

| faction | kits | items |
|---|---:|---:|

## Par faction (kits avec du travail)

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
| astarCyrus | StrikeFromTheShadows | 1225 | DAMAGE(Bolter) |
| astraDreir | LeadingTheCharge | 1204 | DAMAGE(Power) |
| astraOrdnance | BasiliskBarrage | 1026 | DAMAGE(Blast) |
| deathCrawler | EntropyCannons | 1168 | DAMAGE(Energy) |
| emperLucius | LashOfTorment | 1196 | DAMAGE(Eviscerate) |

## Verdicts ATTESTES — decomptes du total, et JAMAIS tus (0 valides, 10 perimees)

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

**PERIMEES — ces items sont REDEVENUS des manquants** (10) :

* `active-decision:DevoutPush` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `active-decision:EntropyCannons` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `active-decision:ExcruciatingFrequencies` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `active-decision:LashOfTorment` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `active-decision:LeadingTheCharge` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `active-decision:MV71SniperDroneSquadAttack` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `active-decision:PrecisionShot` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `active-decision:StrikeFromTheShadows` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `passif:GalvanicField` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici
* `trait:IndirectFire` — lu sur le build 'rnca9r7q6c', le build courant est 't6dpr4k06g' -- un decompile relu ailleurs n'atteste rien ici

## Kits lineup COMPLETS (127)

> ⚠ **COMPLET = face COMBAT complete.** 5 de ces kits portent au moins une active
> sans face DECISION (section precedente) — ils sont marques `*` ci-dessous.

adeptCanoness, adeptCelestine, adeptExorcist, adeptHospitaller, adeptMorvenn, adeptRetributor, admecDestroyer, admecDominus, admecManipulus, admecMarshall, admecRuststalker, astarCyrus*, astarLysander, astraBullgryn, astraCreed, astraDreir*, astraOrdnance*, astraOrdnanceBattery, astraPrimarisPsy, astraYarrick, blackAbaddon, blackForgefiend, blackHaarken, blackObliterator, blackPossession, blackTerminator, bloodDante, bloodDeathCompany, bloodIntercessor, bloodMephiston, bloodSanguinary, bloodTerminator, custoAtlacoya, custoBladeChampion, custoKyrus, custoTrajann, custoVexilusPraetor, darkaAsmodai, darkaAzrael, darkaCompanion, darkaHellblaster, darkaSternguard, darkaStormSpeeder, darkaTerminator, deathBlightbringer, deathBlightlord, deathCrawler*, deathPutrifier, deathRotbone, deathTyphus, eldarAutarch, eldarFarseer, eldarJainZar, eldarLhykhis, eldarMauganRa, eldarRanger, emperExultant, emperFlawlessBlade, emperKakophonist, emperLucius*, emperNoiseMarine, genesBiophagus, genesKelermorph, genesMagus, genesPatriarch, genesPrimus, necroChronomancer, necroDestroyer, necroOverlord, necroPlasmancer, necroReanimator, necroSpyder, necroWarden, orksBigMek, orksKillaKan, orksNob, orksRukkatrukk, orksRuntherd, orksWarboss, spaceBlackmane, spaceHound, spaceRockfist, spaceStormcaller, spaceWolfPriest, spaceWulfen, tauAunShi, tauBroadside, tauCrisis, tauDarkstrider, tauFarsight, tauMarksman, tauShadowsun, templAggressor, templAncient, templChampion, templHelbrecht, templSwordBrother, thousAhriman, thousDaemonPrince, thousInfernalMaster, thousSekhetar, thousSorcerer, thousTerminator, thousTzaangor, tyranBiovore, tyranDeathleaper, tyranNeurothrope, tyranParasite, tyranTyrantGuard, tyranWingedPrime, ultraApothecary, ultraCalgar, ultraDreadnought, ultraEliminatorSgt, ultraInceptorSgt, ultraTigurius, ultraTitus, votanBeserk, votanChampion, votanIronmaster, votanMemnyr, votanUthar, worldEightbound, worldExecutions, worldJakhal, worldKharn, worldTerminator

## HORS total — voies conditionnelles (0 abilities non portees)

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

Portees (au moins une voie dont le gate passe) : **43** — AmuletOfTheVoidwyrm, BladeOfTheAncestors, BlightedLand, BookOfFate, CabalOfSorcerers, ChaliceOfBaal, ContemptuousDisregard, DaemonfleshPlate, DawnBlade, Dw02AdvancedBurstCannon, ElectrochaffBackups, GuardianConstruct, HeadwoppasKillchoppa, Helspear, HyperCorrosiveAcid, IntoxicatingElixir, KardiocoreGalvanus, Lakrimae, MastersOfManoeuvre, Maugetar, MawClawsOfThyrax, MonsterSlayerOfCaliban, MoreGitzOverEre, NetherRealmCasket, NornCrown, OnMyPosition, OrbsOfDecay, ParagonSpear, PhasalSubjugator, PhoenixGem, RelicBoltPistol, RelicOfLostCadia, RelicPowerFist, SabreOfSacrifice, ShieldOfFaith, SupaCyborkBody, TalismanOfRage, TalonOfHorus, TheArdentBlade, Vitarus, VolummsMasterArtifice, WisdomOfTheAncients, WyrdmakersHelm
