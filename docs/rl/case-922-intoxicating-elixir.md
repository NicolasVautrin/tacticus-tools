# #922 — `IntoxicatingElixir` : la relique dont le compteur inclut son propre porteur

**Verdict : PORTÉ (les DEUX faces) + CONFRONTÉ LIVE.** `EffectType.IntoxicatingElixir` (0x5b3 =
**1459**) était **déclaré dans l'enum et jamais posé** ; le playbook de mouvement 1463 n'était pas
au registre. Les deux le sont.

En chemin, un **écart de fidélité du foyer PARTAGÉ du crit** a été trouvé et corrigé : la crit
DAMAGE se relit **après** `On(PreAttackHit)`, coup 0 **compris**.

---

## 1. L'artefact, lu en entier (build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.Loki.IntoxicatingElixir_ExtraCritDmgEffect` (: `BaseEffect`).
SEPT méthodes, dont `CreateTargetSelector` seule dédupliquée (défaut `Owner`, cf. #913) :

```
$$.ctor                 = BaseEffect..ctor(this, AbilityOrEffect(0x5b7), hasAutomatic: 1)
$$GetLevelFormula(dsl, config, tileSelector) =
      Min( Count( EntitiesWithAnyEffect(
                      SurroundingUnits( origin = tileSelector,
                                        range  = GetNumberConstant(0x16 = range),
                                        unique = 1, includeCenter = 1, selectionType = 3 ),
                      EffectType[4] { Pinned, Stunned,
                                      Taunted_OnlySpecificTargets, ThrillSeekers } ) ),
           Get( GetNumberConstant(0x78 = nrOfUnits) ) )
$$GetCalculateLevel     = GetLevelFormula(dsl, config, Tiles(Owner@DSLSelectors+0x30))
$$CreateActiveCondition = AmountIsGreaterThanZero( <le MÊME GetLevelFormula> )
$$CreateCritDamageBonus = EffectBonus.ForAddition( get_OwnerIsCaster, GetCritAmount() )
$$GetCritAmount         = Multiply(
                              Multiply( ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet),
                                                  config@+0x60),
                                        EffectLevel(Effect@DSLSelectors+0x38) ),
                              ConditionalAmount(
                                  HealthPctIsBelowOrEqual(Owner@+0x30,
                                                          Get(GetNumberConstant(0x4f=healthPct))),
                                  formulaTrue  = <DSLFormulas+0x28> = Direct(2),
                                  formulaFalse = <DSLFormulas+0x20> = Direct(1) ) )
$$GetLocalizationDataInternal                                            — affichage seul
```

Surcharges tranchées par l'**adresse du `call`**, jamais par le nom ni l'arité :
`AmountIsGreaterThanZero(amount: IAmountFormula)` (tail-call, sa voisine prend un
`ITargetsSelector`), `ConditionalAmount(trigger, formulaTrue, formulaFalse)` à **3** arguments (les
deux autres surcharges sont `(trigger, formulaTrue)` et `(trigger, int, int)`),
`SurroundingUnits(origin, range: Int32, unique, includeCenter, unitSelectionType)`,
`EntitiesWithAnyEffect(entities, effectTypes: EffectType[])` — la variante **params-array**, sans
`effectTarget`.

Gameconfig : `range = 2`, `nrOfUnits = 6`, `healthPct = 50`,
`extraCritDmg = [295, 311, 327, 343, 359, 375, 391, 406, 422, 438]`.

### Le piège d'ordinal, et ce qui le tranche

```
EffectType            0x5b3 = 1459 = IntoxicatingElixir           <- CET effet
TriggeredAbilityType  0x5b7 = 1463 = IntoxicatingElixir           <- sa CONFIG
EffectType            0x5b7 = 1463 = OrbsOfDecay_AdditionalHits   <- une AUTRE ability
```

Le `.ctor`, relu **octet à octet** : `ba b7 05 00 00` (`mov edx, 0x5b7`) puis un `call` dont la
cible, résolue par son **RVA** (`next_ip + rel32`), appelle `AbilityOrEffect$$set_TriggeredAbility`
— les **quatre** surcharges d'`op_Implicit` sont homonymes dans les tables, seule l'adresse les
sépare. `…IntoxicatingElixirAbility$$GetEffectType` a pour corps ENTIER `return 0x5b3`.

## 2. Le bloc de quatre `EffectType` — AUCUN immédiat au décompilé, LU dans le metadata

Le tableau vient d'un `RuntimeHelpers.InitializeArray(new EffectType[4], <FieldInfo>)` : le `DAT_`
du site porte l'**index de metadata encodé** (`(kind << 29) | index`, ici `kind = 4 = FieldInfo`),
qui n'est résolu qu'au runtime. Rien à lire statiquement dans le PE.

Il a donc été lu dans `global-metadata.dat` (21,6 Mo) : l'**UNIQUE** fenêtre de 4 `int32` alignés
du fichier contenant à la fois `1065` et `1162` vaut

```
[1065, 1162, 27, 1434] = Pinned, Stunned, Taunted_OnlySpecificTargets, ThrillSeekers
```

et cet ordre est **exactement** celui de l'i2 (« Suppressed, Stunned, Taunted, or Thrilled »).
⚠ `Taunted` y est le **composite 27**, PAS ses trois sous-effets (`Taunted_BlockMovement` 25,
`Taunted_CantUseAbility` 26, `Taunted_RefreshUnitTurnFinished` 1237) que
`TauntedEffect$$ApplyInternal` spawne en même temps : les confondre compterait une cible tauntée
**quatre** fois.

## 3. Ce qui SÉPARE cet effet de ses quatre voisins de forme

`KardiocoreGalvanus_ExtraCritDmg` (#913), `AmuletOfTheVoidwyrm_CritDamageReduction`,
`SupaCyborkBody_CritDmgReduction` et `NetherRealmCasket_CritDamageReduction` partagent la forme
`ForXxx(<trigger>, Multiply(ConfigVar, <compteur>))`. **Recopier l'un d'eux serait faux ici** :

| | les voisins | `IntoxicatingElixir` |
|---|---|---|
| géométrie | `AdjacentFriends` — ring-1 **STOCKÉ** + porte d'élévation, porteur EXCLU | **`SurroundingUnits(Tiles(Owner), 2)` — disque CUBE, sans porte, `includeCenter = 1` : le PORTEUR SE COMPTE LUI-MÊME** |
| équipe | `Friends(reference = Owner)` | **AUCUN filtre — amis ET ennemis** |
| filtre | par TRAIT (`MechanicalUnits`) | **par EFFET (`EntitiesWithAnyEffect`)** |
| plafond | aucun | **`Min(…, nrOfUnits = 6)`** |
| magnitude | `ConfigVar × compteur` | **`× 2` de plus si `HealthPct(Owner) <= 50`** |
| activité | `YesTrigger` (Kardiocore) / géométrique (les 3 autres) | **géométrique** — absent du canal `decisionView` à compteur nul |

## 4. La confrontabilité — état 2, et le DEBUFF vient du jeu

Quatre porteurs `lineup` Emperor's Children (`emperExultant`, `emperFlawlessBlade`,
`emperKakophonist`, `emperNoiseMarine`), **aucun** ne l'équipe au seed. `emperKakophonist` et
`emperNoiseMarine` sont **au pool** ; la relique est montée par `--equip-relic` (#237).

Les deux debuffs exercés sont posés **par le jeu**, jamais inventés :

* `emperNoiseMarine` porte le trait **`SuppressiveFire`** (« An enemy hit by this unit's ranged
  attack becomes Suppressed ») → son tir **à distance** pose `Pinned` (1065). Un coup de **mêlée**
  n'en pose **aucun** — c'est ce qui donne le régime `n = 0` (cible BLESSÉE sans être DEBUFFÉE),
  et c'est mesuré, pas supposé ;
* les **cinq** Emperor's Children portent le trait `ThrillSeekers`, et
  `ThrillSeekersAbility$$CreateTrigger` = `On(6) & IsFirstHitInSeries & get_OwnerIsCaster &
  NOT IsWounded(target)` les rend `Thrilled` (1434) dès qu'ils frappent une cible à **pleine vie**.
  C'est ce qui rend confrontables les deux quirks que rien d'autre n'exerce : le porteur qui se
  compte lui-même, et l'ami qui compte comme un ennemi.

## 5. L'observable qui rend l'étage COMPTEUR confrontable SANS passer par le dégât

`decisionView.effects[].level` publie le niveau **STOCKÉ** (`EffectComponent+0x68`), que
`RefreshEffectsOperation$$UpdateLevel` tient égal à `$$GetCalculateLevel`.

⚠ **MESURE** : tant que l'effet est **INACTIF**, `UpdateLevel` ne le rafraîchit pas — le champ
reste à sa valeur d'initialisation (**1**, mesuré à compteur nul). Le `level` ne fait donc foi
**que** lorsque `active` est vrai ; à `active == False` c'est `active` qui porte l'information.
Un cliquet qui lirait `level` sans ce gate accuserait le port sur un régime où le natif ne dit
rien.

## 6. LE FIX DU FOYER PARTAGÉ — la crit DAMAGE se relit APRÈS `On(6)`, coup 0 COMPRIS

`AttackDamageOperation$$ExecuteHit`, relu dans l'ordre :

```
slot 0xad (profil) -> AttackHit..ctor -> slot 0xa RollCritical
   -> AbilityEntities..ctor -> EnqueueOperation(6) -> EnqueueOperation(7)
   -> slot 0xb CalculateCriticalDamage -> sub-op 0x42 -> EvaluateAfterHitTriggers
```

`On(6)` tombe **ENTRE** `RollCritical` et `CalculateCriticalDamage`. Donc ce qu'il pose :

* **ne mord pas** sur le TIRAGE de crit du coup 0 (c'est #522-r1, toujours vrai) ;
* **mord** sur sa **MAGNITUDE**, coup 0 compris.

Les trois vecteurs (`damage_ops/{normal,normal_like,ability}.py`) calculaient déjà `crit_apres` et
n'en consommaient que la **chance** — `crit_apres[1]` était calculé et **jamais lu**. Le trou était
**INERTE** jusqu'ici : aucun écouteur porté d'`On(6)` ne changeait la crit damage. Cette tranche en
crée un (le `Thrilled` que le porteur se pose à son propre coup 0 fait monter le compteur de la
relique), donc le trou devient **observable**.

**Mesure** (porteur `emperKakophonist`, relique niveau 3, cible à pleine vie) :

| | coup 0 | coup 1 | coup 2 |
|---|---|---|---|
| natif | 7289 | 6938 | 6979 |
| port AVANT le correctif | 5991 | 4889 | 5149 |
| port APRÈS | **7289** | **6938** | **6979** |

Les **trois** coups divergeaient, le 0 compris — c'est ce qui établit que la magnitude se relit
après l'event, et pas seulement pour les coups 1+.

Le correctif est un `crit_damage = crit_apres[1]` dans chacun des trois vecteurs : **strict no-op**
partout ailleurs (les deux mesures ne diffèrent que si un écouteur d'`On(6)` change la crit damage).
Contre-épreuve exécutable : le mutant `CRITDMG_AVANT` du probe fige la crit damage sur sa première
mesure et **doit** diverger.

## 7. Le port

* `engine/entities/effects/loki/intoxicating_elixir.py` — la classe + l'arbre du compteur ;
* `engine/entities/effects/factory.py` — `EFFECT_CLASSES["IntoxicatingElixir"]` ;
* `engine/runner/components.py` — `debuffed_units_in_range_count` + la clé de `unit_state`.
  ⚠ Son gate de présence est la **POSITION SEULE**, pas `position ET équipe` comme ses quatre
  voisins : ce sélecteur-là n'a aucun filtre d'équipe, donc exiger une équipe rendrait `None` là où
  le natif sait compter ;
* `engine/runner/operations/damage.py` — `debuffed_units_in_range_of` et `unit_health_of` dans
  `_crit_board` (le second est le substrat de `HealthPctIsBelowOrEqual`, tri-état `(None, None)`) ;
* `engine/playbook/intoxicating_elixir.py` + son entrée au registre `TRIGGERED_MOVE_PLAYBOOKS` ;
* `engine/utilities/tile.py` — la clé `self_effects` des **trois** constructeurs de `leaf_ctx`.

**PAS d'entrée `ABILITY_INIT_OWNER_EFFECTS`** : `_seed_ability_owner_effects` lit le **KIT**
gameconfig (`activeAbilities + passiveAbilities`), où la relique ne figure pas — elle arrive par
`BC.Units[].TertiaryAbility`. Même arbitrage explicite que `kardiocore_galvanus.py`.

## 8. La face DÉCISION

`IdunBattle.AI.Playbook.Loki.IntoxicatingElixirPlaybook` (`.ctor` → `0x5b7` = 1463) :

* `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` = `yield Fix64(0)` — corps PROPRE, pas une
  absence. Rien à enregistrer côté attack ;
* `<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext` appelle **littéralement la
  `$$GetLevelFormula` de l'effet de COMBAT**, seule l'ancre changeant (`DSLSelectors.Get(<tuile
  candidate>)` au lieu de `Tiles(Owner)`), puis `yield Fix64(w × n)` où
  `w = Utilities.Default.TriggeredAbilities["IntoxicatingElixir_LikesSuppressionStunTauntThrilled"]`
  = **5**. La clé est **LUE** : le `DAT_` du site est un slot de `StringLiteral`
  (`metadata/string_literals.tsv`), pas une devinette par préfixe.

Le port **partage donc son arbre** avec la classe d'effet et n'en re-dérive aucun étage. Le corps
n'écrit **aucun** `RemoveAll(u.Id == case.Unit.Id)` : le mover se compte lui-même dès que son
ORIGINE est à ≤ 2 hex de la tuile candidate — d'où la clé `self_effects`, ajoutée aux trois
constructeurs de `leaf_ctx` (c'est le pendant de `self_pos` sur l'axe des effets, et le régime est
COURANT : les quatre porteurs sont Emperor's Children).

## 9. Validation — 8 tests, 6 mutants du compteur, 4 contre-épreuves de canal

`probe_922_intoxicating_elixir_live.py` et `test_922_intoxicating_elixir_crit_live.py`.
LIVE == OFFLINE **bit-exact**, coup par coup, sur **tous** les bras de dégât.

| bras | compteur natif | port | résultat |
|---|---|---|---|
| `n = 0` (cible blessée en MÊLÉE, non pinnée) | effet **INACTIF** | inactif | bonus `None` — la condition est GÉOMÉTRIQUE |
| `n = 1` | 1 | 1 | **+327** |
| `n = 2` | 2 | 2 | **+654** — le PRODUIT discrimine |
| `--dist 3` (2 victimes, une hors portée) | **1** | 1 | le rayon `range = 2` mord, témoin NON NUL |
| `--low-hp` (49999/100000) | 1 | 1 | **+654** = `327 × 1 × 2` — le `ConditionalAmount` mord |
| `--compteur` | **1 → 2** | 2 | l'AMI `Thrilled` compte (aucun filtre d'équipe), puis le PORTEUR lui-même (`includeCenter`) |
| `--thrilled n = 1` | 1 au snapshot, **2** en cours de salve | idem | le correctif §6 exercé, `CRITDMG_AVANT` diverge |

**Mutants du compteur** — six lectures plausibles et fausses, chacune déclarant dans quel régime
elle doit mordre : `SANS_CENTRE`, `VOISIN_KARDIOCORE` (ring-1 + filtre d'équipe), `PORTEE_1`,
`SANS_PINNED`, `SANS_THRILLED`, `PLAFOND_1`. **6/6 conformes** dans les deux régimes.

**Contre-épreuves de canal** : `NOCHANNEL` (l'effet retiré d'`EFFECT_CLASSES`), `PASSIF` (le
callable `tertiary_ability_state_of` retiré → niveau des passifs, dernier palier), `SANSSANTE` (le
callable `unit_health_of` retiré → branche non doublée), `CRITDMG_AVANT` (l'état d'avant §6).

**Deux pièges de montage MESURÉS**, tous deux réparés dans le probe :

1. la clé de `abilityTargets.fromHere` est **`targetId`**, pas `unitId` — la lire au mauvais nom
   rendait un ensemble **VIDE en silence** et le montage se refusait (« aucun TIR possible ») sur
   une géométrie pourtant légale ;
2. les positions doivent être **RELUES** après chaque `place` — un dict capté avant les placements
   faisait chercher les tuiles de tir autour de l'ANCIENNE case, et a fait écrire une attente de
   mutant erronée avant d'être corrigée par la mesure.

## 10. Ce qui n'est PAS couvert

* **le PLAFOND `nrOfUnits = 6` n'est pas exercé LIVE** : il faudrait sept unités debuffées dans un
  disque de rayon 2, donc sept tireurs ou sept tours. Il est gardé par le mutant `PLAFOND_1`
  (rabattu à 1, il mord) et par la lecture du gameconfig — mais aucune mesure live ne le confirme ;
* **`Stunned` (1162) et `Taunted_OnlySpecificTargets` (27) ne sont pas exercés LIVE** : seuls
  `Pinned` et `ThrillSeekers` le sont. Les quatre entrent par le **même** `HasOneOfEffects`, donc
  rien ne les distingue dans le code — mais c'est dit plutôt que supposé ;
* ~~**le SEEDING d'un effet INACTIF au snapshot** — résidu `#922-r1`~~ — **FERMÉ (#10035,
  2026-08-18), et le « correctif d'UNE LIGNE » que cette section désignait n'était pas le bon.**
  Ce qu'elle affirmait — « le canal de capture du harnais, UNE ligne », dont le rayon (53 fichiers
  lecteurs de `ChargeRegimeHarness`) justifiait de ne pas la payer — visait un symptôme. La cause est
  **en amont du canal** et son rayon est **nul** pour ces 53 fichiers : `snapshot.load_state` joue
  `_load_stats_and_effects` — qui porte la boucle `_seed_ability_owner_effects` — **AVANT**
  `_load_tertiary_abilities`, seul écrivain de `ctx.tertiary_ability`. La quatrième source du seed
  (#1005) était donc structurellement muette sur le chemin de CAPTURE, alors qu'elle fonctionne sur
  le chemin OFFLINE où le ctx est complet avant l'appel. `--inactifs` donnait bien `1`, mais en
  **élargissant la capture** au lieu de réparer la pose.
  **MESURE, même montage (`--n 0 --thrilled`, SANS le drapeau)** : `instance_dans_by_unit`
  **0 → 1**, écart par coup **`[462, 1600, 988]` → `[0, 0, 0]`**, `accord=True`, les **deux** témoins
  (`NOCHANNEL`, `CRITDMG_AVANT`) restant ROUGES à `[6534, 4621, 5010]`.
  Le gisement était bien **PARTAGÉ** avec `AmuletOfTheVoidwyrm` et `NetherRealmCasket` — les trois
  sont fermés du même coup. Détail : `docs/rl/case-10035-pose-tertiaire-au-chargement.md`.
  ⚠ **Le volet (c) reste ouvert mais change de MOTIF** : basculer `includeInactive` par défaut dans
  `ChargeRegimeHarness` ne ferme plus rien ici (un owner-effet d'INIT est désormais rattrapé par le
  seed) ; ce qu'il couvrirait encore est un effet posé **en COMBAT** et devenu inactif, qu'aucun seed
  d'init ne peut rejouer ;
* la face **DÉCISION** est portée et son arbre est partagé avec la face COMBAT (donc confronté par
  ricochet). Résidu `#922-r2`, **re-mesuré le 2026-08-15 — son `BLOCAGE: capteur` est RÉFUTÉ.**
  Le walk L3 est bien le seul canal qui publierait l'utilité PAR-TUILE ; mais **l'ANCRE est
  observable sans aucun capteur** : ancrée sur `Tiles(Owner)` (l'ancre de la face COMBAT) elle
  serait CONSTANTE sur toutes les tuiles candidates d'une décision, ancrée sur
  `DSLSelectors.Get(<tuile candidate>)` elle VARIE — et cette variation change le CLASSEMENT.
  Livré : `tests/engine/test_922r2_intoxicating_elixir_ancre_offline.py` (6 assertions — l'ANCRE
  avec témoin non dégénéré, le classement INTERVERTI et sa contre-épreuve « mêmes unités NON
  debuffées ⇒ ex aequo à 0 », poids et PLAFOND lus au gameconfig, disque CUBE centre INCLUS sans
  porte d'élévation, SELF, absence de filtre d'équipe). L'autre moitié du résidu — « la clé
  `self_effects` des TROIS `leaf_ctx`, dont AUCUN test ne vérifie la forme » — est gardée par
  `tests/engine/test_175r1_movetowards_pathdist_offline.py` étage 4.
  Reste ouvert : l'**ARGMAX natif**, qui ne demande aucun capteur non plus (les quatre porteurs
  sont HERO `lineup`, montage de relique ÉCRIT depuis #237) ;
* `$$GetLocalizationDataInternal` : affichage seul, aucun observable de combat — non porté.

## 11. `#922-r1` volet (a) : le TROISIEME etage, LOCALISE -- le MOMENT de lecture, pas la formule

L'ecart `[462, 1600, 988]` survivait a la fermeture du SEED (#1005/#1081) et a la refutation de la
REACTIVATION. Il est desormais **localise, et sa cause est LUE**.

### Ce que la decomposition par etage dit (bras `--n 0 --thrilled --inactifs`)

| grandeur | natif | port |
|---|---|---|
| coups qui CRITENT | `Attack_DidCrit: 1` x3 | `crits: [true, true, true]` |
| degat par coup | `[6996, 6221, 5998]` | `[6534, 4621, 5010]` |
| compteur AU CALCUL | (bonus applique) | `compteur = 0`, `bonus_signe = None` |
| compteur APRES la salve | -- | `compteur_apres_rejeu = 1` |
| effets du porteur apres rejeu | -- | `[IntoxicatingElixir, ObsessiveAnnunciation_ExtraDmg, ThrillSeekers]` |

Les trois coups critent des DEUX cotes : ce n'est pas un ecart de crit-CHANCE. Le port POSE bien
`ThrillSeekers` en cours de salve et son compteur MONTE : l'hypothese « le port ne pose pas le
debuff » est refutee elle aussi. Mais **au moment du calcul** il lit `0` et ne verse rien.

### La contre-epreuve qui localise, sans payer le rayon

Bras `COMPTEUR_APRES` de `probe_922_intoxicating_elixir_live.py` : on ne touche NI la formule NI le
pipeline de degat, on **substitue l'ENTREE** -- le compteur d'APRES `On(PreAttackHit = 6)`. Le port
rend alors **`[6996, 6221, 5998]`**, soit le LIVE exact : ecart `[462, 1600, 988]` -> **`[0, 0, 0]`**.

⚠ **IL Y A DEUX PORTES, et n'en substituer qu'une NE MORD PAS** (mesure : le seul callable de
magnitude laisse la salve inchangee) :

1. **ACTIVITE** -- `UnitEffectStateView["debuffed_units_in_range"]` alimente la
   `CreateActiveCondition` ; a `0` l'instance est **exclue d'`active_effects`**, donc `_crit_params`
   ne la voit meme pas et la magnitude n'est jamais evaluee ;
2. **MAGNITUDE** -- le callable `debuffed_units_in_range_of` d'`att_ctx`.

### La cause, lue dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`

L'ordre du corps, slot par slot :

    slot 0xad (profil) -> AttackHit..ctor -> **slot 0xa RollCritical** -> AbilityEntities..ctor
      -> EnqueueOperation(6) -> EnqueueOperation(7) -> IsAttackMaxOutDamage
      -> **slot 0xb (crit-DEGAT)** -> slot 4 -> sub-op 0x42 -> EvaluateAfterHitTriggers

**La dissymetrie est la.** La crit-CHANCE est tiree **AVANT** l'event : le coup 0 n'a pas le bonus
pose par `On(6)`, et le port le porte deja correctement (`crit_chance` / `crit_chance_after`,
#522-r1). La crit-DEGAT est calculee **APRES** : elle voit le bonus **des le coup 0** -- ce qui
explique les 462 du premier coup, qu'une lecture « le stepping ne commence qu'au coup 1 » ne
pouvait pas expliquer.

### La borne ecrite dans le port est juste sur un axe, fausse sur l'autre

`damage_hits.py` justifie de ne pas retoucher `crit_damage` ainsi : « `GetCritDamageBonusFromEffects`
-- QUATRE arguments, **pas de `hitIndex`** ⇒ le canal crit-DEGAT n'est pas index-dependant ».
C'est **vrai sur l'axe INDEX** et **muet sur l'axe TEMPOREL** : l'absence de `hitIndex` ne dit rien
de la dependance a l'ETAT, qui change des qu'`On(6)` pose un effet. C'est cette phrase, exacte mais
partielle, qui a fait renoncer.

### Ce qui reste, et pourquoi ce n'est pas fait ici

Porter l'axe TEMPOREL sur la crit-DEGAT : un `crit_damage_after` pris par **TOUS** les coups, coup 0
compris (pas de decalage d'index, contrairement a la chance). Foyer = le pipeline de degat PARTAGE
(`operations/damage.py::_crit_params`, `operations/damage_hits.py::_run_hits`, et les TROIS vecteurs
`damage_ops/normal.py` / `ability.py` / `normal_like.py`) -- une tranche a soi seule. Residu
**#922-r5**, avec son montage discriminant deja ecrit et sa cible chiffree.

Portee : tout owner-effect a condition dependante de l'etat pose pendant la salve --
`AmuletOfTheVoidwyrm_CritDamageReduction` (1460) et `NetherRealmCasket_CritDamageReduction` (1455)
ont la meme forme, non mesuree chez eux.

## 12. `#922-r5` FERME (2026-08-17) -- l'axe temporel etait deja porte, et il ne servait a rien

Le paragraphe ci-dessus decrit un travail **deja livre** : #919 (2026-08-11) a pose
`crit_damage = crit_apres[1]` dans les TROIS vecteurs. La fiche #922-r5, ecrite le 2026-08-15,
prescrivait donc un correctif present dans l'arbre depuis quatre jours.

Et ce correctif etait un **NO-OP dans son propre regime de motivation**. Mesure : le bras
`CRITDMG_AVANT` du probe (qui fige `crit_damage` sur sa premiere lecture, c'est-a-dire l'etat
d'AVANT #919) rendait `[6534, 4621, 5010]` -- **exactement `OFFLINE`**. Un correctif dont le
contrefactuel est indistinguable ne corrige rien.

### La cause : une seule unite du board avait ses effets FIGES

`AttackDamageOperation._crit_carriers` relisait `state.effects.active_effects(...)` pour toutes les
unites du board **sauf l'attaquant**, a qui il repassait tel quel le parametre `attacker_effects`.
Or ce parametre est la liste que `damage_model.attacker_modifiers` calcule **en tete d'operation**,
donc AVANT `On(PreAttackHit = 6)`. Relire la facade CRIT apres l'event ne pouvait donc rien changer
pour un effet du PORTEUR : la liste, elle, datait d'avant.

C'est la porte que #922-r1 volet (a) appelait << l'ACTIVITE >>, et elle explique aussi pourquoi
substituer le seul callable de MAGNITUDE ne mordait pas : a compteur nul, l'instance est exclue
d'`active_effects`, donc `_crit_params` ne la voit meme pas et la magnitude n'est jamais evaluee.

### Ce qui l'etablit, et ce n'est pas une symetrie supposee

`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses` **ne prend AUCUN argument** --
ni unite, ni liste pre-calculee. Elle enumere la collection globale des entites-effet, appelle le
slot `0x29` du service sur chacune (rafraichissement) **avant** de tester `EffectComponent+0x5c`
(`IsActive`), et rend `(effet, cibles)`. Il n'existe donc, cote natif, aucune place ou la liste de
l'attaquant serait plus vieille que celle des autres.

### Mesure

Meme montage joue avant/apres (`probe_922_intoxicating_elixir_live.py --n 0 --thrilled
--inactifs`) : ecart natif/port par coup **`[462, 1600, 988]` -> `[0, 0, 0]`**, `accord=True`. Les
deux temoins du probe restent ROUGES, et c'est ce qui etablit que les DEUX pieces sont necessaires :
`NOCHANNEL` (port sans le canal) et `CRITDMG_AVANT` (port sans l'axe temporel) rendent tous deux
`[6534, 4621, 5010]`.

### Un temoin qui avait cesse de mordre, et le vert qu'il aurait pu donner

`test_922_intoxicating_elixir_crit_live.py::test_le_niveau_lu_est_celui_de_la_relique_pas_du_passif`
etait **rouge sur `origin/master`** -- avant comme apres ce correctif (contre-epreuve sur `HEAD~1` :
memes valeurs `passif == off == [5991, 4889, 5149]`). Le mutant `PASSIF` RETIRAIT le callable
`tertiary_ability_state_of`, en supposant que l'effet retomberait sur le niveau des PASSIFS. Depuis
la reparation du seeding tertiaire (#1005/#1081), l'INSTANCE porte elle-meme le couple TERTIAIRE :
le repli rendait deja le bon niveau, et le temoin ne discriminait plus. Il SUBSTITUE desormais la
branche de repli de `triggered_ability_state` au lieu de la retirer, et `etages()` imprime
`ability_level_instance` pour que la cause soit LUE. 9 passed.

⚠ **DEUX fichiers, un seul vice.** Le meme temoin, ecrit de la meme facon, etait inerte dans
`probe_589r1r1r2r1_amulet_crit_reduction_live.py` -- et son test rougissait pareil sur `master`
(`test_amulet_voidwyrm_crit_reduction_live.py::test_le_niveau_lu_est_celui_de_la_relique_pas_du_passif[1]`,
`passif == off == [2739, 2727, 3062, 2767]`, avant comme apres le correctif). Meme cause, meme
correctif, 9 passed. Ce n'est pas une coincidence : `AmuletOfTheVoidwyrm_CritDamageReduction` est
un owner-effect de relique de la MEME forme qu'`IntoxicatingElixir`, donc son instance a herite du
meme couple bake. Tout temoin qui refute une lecture en RETIRANT une entree, plutot qu'en
SUBSTITUANT la lecture fausse, est exposee a ce glissement.
