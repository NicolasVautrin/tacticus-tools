# #1005 — reliques BLOOD ANGELS : `ChaliceOfBaal` (1550) et `Vitarus` (1470)

Couple de reliques de la voie `item`, deux porteurs du MÊME roster (`bloodSanguinary`,
`bloodMephiston`, tous deux HERO du pool rank 17) : **un seul montage**
(`rl_duel build --equip-relic`). Les deux ids sont des `TriggeredAbilityType` — aucune n'entre
dans `ABILITY_CLASSES`, aucune ne pose de `TARGETING_OPTIONS` ni d'`ABILITY_ATTACK_TYPE`.

Build de lecture : `rnca9r7q6c`.

## 1. Les artefacts natifs, et le canal de chacun

`AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_426` construit
`ChaliceOfBaalAbility` **puis** `ChaliceOfBaal_ResetAbility` dans LA MÊME liste — deux classes pour
une clé, patron `LetTheGalaxyBurn` / `DaemonfleshPlate`. Idem côté `Vitarus`, mais les deux classes
relèvent de canaux DIFFÉRENTS :

| classe native | canal de port |
|---|---|
| `Triggered.Loki.ChaliceOfBaalAbility` | `RELIC_ABILITY_TRIGGERS["ChaliceOfBaal"]` |
| `Triggered.Loki.ChaliceOfBaal_ResetAbility` | idem (2ᵉ entrée) |
| `Effects.Loki.ChaliceOfBaalEffect` (1569) | `EFFECT_CLASSES["ChaliceOfBaal_ExtraDmg"]` |
| `Triggered.Loki.VitarusAbility` | `RELIC_ABILITY_TRIGGERS["Vitarus"]` |
| `Triggered.Loki.Vitarus_InitAbility` | **`ABILITY_INIT_OWNER_EFFECTS["Vitarus"]`** |
| `Effects.Loki.VitarusEffect` (1466) | `EFFECT_CLASSES["Vitarus"]` |

`Vitarus_InitAbility` a pour parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`
(`frida/classes.tsv`) et n'override QUE `$$GetEffectType`, dont le corps ENTIER est `return 0x5ba`
(= 1466) : l'appariement ability → effet est LU, pas deviné. Le reste vient de la base
(`OnOwnerSpecificAbilityInit` + `AddEffect(GetEffectType(), AbilityState(Owner), source = Owner,
targets = Owner, turns = <zeroe>)`) — patron `ToughToKill` / `Skullsmasher`.

`ChaliceOfBaal_ResetAbility$$CreateBehaviour` **n'a pas de symbole propre** : son corps est FONDU
par l'ICF avec `NoHidingFromTheWatchers_EndPhaseAbility$$CreateBehaviour`, placé dans le bloc
d'adresses de `ChaliceOfBaal_Reset` (entre `ChaliceOfBaalAbility$$.ctor` et
`ChaliceOfBaal_ResetAbility$$CreateTrigger`, dans une zone ordonnée alphabétiquement par classe).
L'attribution est établie par ÉLIMINATION : les SEULES cinq fonctions du binaire qui touchent le
`Il2CppClass*` d'`AChaliceOfBaalAbility` sont son `.cctor`, son `HasTriggeredThisTurn`, les deux
`.ctor` dérivés et `ChaliceOfBaalAbility$$CreateBehaviour` — il n'y a pas de sixième. Le corps
partagé, lui, ne lit AUCUN static de classe (il dérive son `AbilityOrEffect` de `this`), ce qui est
exactement ce qui le rend ICF-fusionnable entre classes.

## 2. `Vitarus` — le va-et-vient du feu

    VitarusAbility$$CreateTrigger =
        On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive = true)
      & get_OwnerIsCaster & IsMeleeAttack
      & ( IsNormalAttack(CurrentAbility@<DSLSelectors+0x88>)
        | AreEqual(CurrentAbility@<+0x88>, AbilityOrEffect(TriggeredAbilityType.FuryOfTheAncients)) )

    VitarusAbility$$CreateBehaviour =
        If( Any(Tiles(Target@<+0x60>), HasEffect(<élément@+0x68>, EffectType.Fire = 5,
                                                 onlyActive: false, EffectTargetType.Both = 6)),
            Inform(TagKey.Is_Modified = 0xe9, 1) + RemoveEffect(tiles, Nullable(Fire), null),
            AddEffect(Fire, AbilityStateReference, tiles, Nullable<int>(null)) )

Le `0x4df` est LU AUX OCTETS (`mov edx, 0x4df`, `call` dont le rel32 résout sur
`AbilityOrEffect$$op_Implicit(triggeredAbility:TriggeredAbilityType)` — PAS sur les surcharges
`ActiveAbilityType` / `EffectType`, que l'ordinal seul n'aurait pas discriminées). Idem `0x60e`
(ctor de `ChaliceOfBaalEffect`) et `0x5be` (ctor de `VitarusEffect`).

**MESURE LIVE (runner 614)** — une seule attaque de mêlée de Mephiston produit **TROIS** blocs
`[Ability_Power e=77 «Vitarus»]` dans la cascade, un par ATTAQUE (l'attaque normale + chaque maillon
du `ChainAttackDamage` de `FuryOfTheAncients`) :

1. après les 3 coups de l'attaque normale → **POSE** `Fire` sur la tuile de la cible
   (`Effect_SourceId = <la tuile elle-même>`, `Effect_RemainingTurns = 4` = la durée par défaut) ;
2. après le maillon de Fury sur la MÊME cible → `Info Is_Modified=1` + **RETRAIT** du `Fire` ;
3. après le maillon de Fury sur la 2ᵉ cible → **POSE** `Fire` sur SA tuile.

Les trois branches du `If` sont donc observées, dans l'ordre, avec leur témoin natif
(`Is_Modified`). L'ORDRE bonus/mutation est structurel et le port le reproduit par construction :
le bonus est calculé PENDANT le coup (`damage_model.attacker_modifiers`), le feu est muté APRÈS
l'attaque (`On(9)`).

Résidu `#1005-r3` : le 2ᵉ disjoint est inatteignable côté port (Fury ne thread pas son kind).

## 3. `ChaliceOfBaal` — PORTÉE, NON CONFRONTÉE

    CreateTrigger = On(UnitDeath = 0, alive) & NOT HasTrait(Target@<+0x60>, UnitTrait.Steppable)
                  & IsAdjacent(Owner@<+0x30>, Target@<+0x60>, UnitSelectionType.Any)
                  & NOT HasTriggeredThisTurn()
    HasTriggeredThisTurn = AmountIsGreaterThanZero(GetPersistentData(AbilityOrEffect(1550),
                              Owner, Get("ChaliceOfBaalTriggered")))
    CreateBehaviour = Heal(Owner, UnitsAffectedByHealType(Owner + AdjacentFriends(Owner, unique,
                              OnlyAliveAndTargetable), NonMechanical), Get(hp[niveau]), ForHeal)
                    & AddEffect(1569, AbilityStateReference, source = Owner, targets, Direct(1))
                    & SetPersistentData(1550, Owner, "ChaliceOfBaalTriggered", <vrai>)
    Reset : On(TurnEnd = 0x17, alive) & HasTriggeredThisTurn() -> ClearAllPersistentData(1550, Owner)

⚠ **AUCUN `get_OwnerIsActor`** — le porteur n'a pas à être le TUEUR (contraste `DawnBlade`, qui le
porte). N'importe quelle unité non `Steppable` qui meurt à son contact déclenche la relique, alliée
comme ennemie. La clé persistante est le littéral `"ChaliceOfBaalTriggered"` :
`AChaliceOfBaalAbility$$.cctor` a pour corps entier `statics[0] = <literal cache 0x33af708>`, et
`metadata/string_literals.tsv` donne ce slot pour cette chaîne.

Résidu `#1005-r2` : les trois observables (soin, effet 1569 sur les alliés, drapeau une-fois-par-tour)
n'ont pas été relevés live.

## 4. Le NIVEAU d'une relique n'est PAS celui des passifs — et ça se voyait nulle part

**MESURE** (RPC `unitAbilityStates`, runner 614, `bloodMephiston` avec `Vitarus` équipée) :

    triggered: [ {raw: [1247, .., level 50, mult 180, .., hiérarchie 2, ..]},   # FuryOfTheAncients
                 {raw: [1470, .., level  1, mult 100, .., hiérarchie 3, ..]} ]  # Vitarus (RELIQUE)

Le natif résout le `ConfigVar` d'un effet de relique contre l'`AbilityState` que l'`AddEffect` lui
a passé — `AbilityState(Owner, <l'ability courante>)`, donc l'état **TERTIAIRE**. Côté port,
`EffectFactory.create` reçoit le couple PASSIF de l'unité porteuse (canal de seed
`decisionView.effects` comme voie offline) : `Vitarus.extraDmg` aurait été lu à l'indice clampé
(`extraDmg[10] = 728`) au lieu d'`extraDmg[1] = 490` — **+238 par coup, en silence**.

Le correctif est un CANAL, pas une rustine locale : `attacker_modifiers` publie
`att_tertiary_{ability,level,mult}` et le foyer `effects/base.py::relic_ability_state` les lit ;
`_seed_ability_owner_effects` matérialise l'owner-effet TERTIAIRE avec SON couple. Clés absentes →
repli sur les champs de l'effet, **et le repli est testé** (contre-épreuve : 728).

Résidu `#1005-r1` : l'écart mesuré (~+539/coup) ne se réconcilie pas avec 490 sans isoler le
placement pré/post-perçage du canal additif.

## 5. Deux fautes silencieuses trouvées en portant

* **`RemoveEffect` était aveugle au domaine TUILE.** La feuille ne résolvait que
  `isinstance(tu, dict)` (les unités), alors que le natif itère des `IEntity` indifférenciées —
  exactement comme `AddEffectBehaviour`, dont le port routait DÉJÀ les deux domaines. Le disjoint
  « on ÉTEINT » de `VitarusAbility$$CreateBehaviour` (`RemoveEffect(Fire, Tiles(Target))`) aurait
  été un **no-op silencieux**. Corrigé en passant par le MÊME résolveur qu'`AddEffect`
  (`_add_effect_targets` / `_add_effect_target_id`), pour que la clé de POSE et la clé de RETRAIT
  ne puissent pas diverger.
* **`Tiles(Target())` rend des POSITIONS, pas des ids.** `HasEffect` n'a que deux branches
  (unité-dict, tuile-ID) : un `(col,row)` n'est routé NULLE PART et le gate serait FAUX en silence.
  D'où `Tiles(Target(), as_ids=True)` dans l'arbre `Vitarus`.

## 6. Ce qui garde

`tests/engine/test_1005_reliques_blood_angels_offline.py` (14 tests, aucun runner) : les deux
registres, le canal INIT de `Vitarus_InitAbility`, les trois vecteurs natifs, le foyer
`relic_ability_state` (+ contre-épreuve 728), les gates lus des deux effets, l'unicité du foyer
`target_is_on_fire_tile`, la forme des deux arbres, le domaine tuile de `RemoveEffect`, la voie
tertiaire du seed, et la présence des trois clés dans `attacker_modifiers`.
