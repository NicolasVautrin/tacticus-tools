# case-1011-r1 — `PhasalSubjugator` (relique 1557, `necroOverlord`) : PORTÉ + CONFRONTÉ LIVE

RE : décompilé ghidra, build `rnca9r7q6c`. Transcription complète des deux arbres :
en-tête de `engine/runner/operations/triggers/loki/phasal_subjugator.py`.

## 1. Une clé, DEUX classes — et l'étage qui bloquait, levé SANS capteur

`AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_433` construit **une
`List` + DEUX `Add`** (contrôle : `b__28_432`, la clé voisine `0x614`, n'en construit qu'UN).

`PhasalSubjugator_TriggerPassiveAbility$$CreateTrigger` est **absent des deux tables** (corps
dédupliqué par l'ICF). Identifié par la **structure** de `frida/methods.tsv`, qui est écrite dans
l'ordre `methodPointers` **par classe visitée** :

```
[51013] 12a7cb0  ...PhasalSubjugator_TriggerPassiveAbility.HasFriendlyWarrior
[51014] efad70   ...Abilities.Active.Loki.CallInReinforcementsAbility.CreateTrigger   <-- INTRUS
[51015] 12a7d80  ...PhasalSubjugator_TriggerPassiveAbility.CreateBehaviour
```

Contrôle décisif : dans le groupe NATUREL de `CallInReinforcementsAbility` (lignes 52429-52430)
son `CreateTrigger` **manque**. Et le corps `efad70`, décompilé, est **générique** —
`On(0x29, ownerNeedsToBeAlive: 1) & get_OwnerIsActor`, aucun littéral propre. ⇒ partage légitime,
**`EventTriggerType` 0x29 = 41 = `UnitFinishedTurnNormally`**.

## 2. Les deux arbres

| classe | trigger | behaviour |
|---|---|---|
| `_SummonAbility` | `On(0x1c = ArrivedAtFinalTile, alive) & get_OwnerIsActor & NOT AmountIsGreaterThanZero(Friends(Owner, UnitsWithVisualId(VisualUnitIdFromUnitId(GetStringConstant(0)), 1), 1))` | `Spawn(Owner, First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(Owner)), 7, Owner), 1), unitId, WithStatsFromConfig(config, abilityState))` |
| `_TriggerPassiveAbility` | `On(0x29, alive) & get_OwnerIsActor` (corps partagé) | `If(NOT HasFriendlyWarrior(), <le même Spawn>) & IfAlive(Owner, TriggerAbility(Owner, 0x614, sel = 3, ignoreUnitHavingAbility = false))` |

Les DEUX `1` du gate sont des `UnitSelectionType.OnlyAlive` — **type DÉCLARÉ** lu dans
`frida/methods.tsv` (`UnitsWithVisualId(unitId, selectionType)` / `Friends(of, entities,
selectionType)`), jamais l'ordinal. Un Guerrier **mort** ne bloque donc pas le re-summon.

⚠ **Le gate `HasFriendlyWarrior` change de place entre les deux classes** : conjoint du TRIGGER
pour la première, `If` du BEHAVIOUR pour la seconde. Le re-déclenchement de `1556` a donc lieu
MÊME quand un Guerrier vit. Recopier la forme de la classe 1 supprimerait la moitié de la relique.

## 3. Le re-déclenchement de 1556, et la PRÉMISSE RÉFUTÉE

`TRIGGERED_ABILITY_BEHAVIOURS[MyWillBeDoneOverlord]` (posé dans `my_will_be_done_overlord.py`,
patron `AdaptiveStrategy` → `RelentlessMarch`) : `TriggerTriggeredAbilityOperation$$TriggerAbility`
appelle `ExecuteBy(..., 0x20 = Custom)`, donc la branche `else` du `CreateBehaviour` de 1556.

`my_will_be_done_overlord.py` §5 annonçait : « le jour où la branche `Custom` a un appelant, le
terme `!TriggeringAbilityIs(1557) | IsUnitWithVisualId(...)` doit être posé ». **Il ne doit pas.**
`BaseTriggeredAbility$$Execute`, lu en entier, écrit `+0x60 CurrentAbility` **avant** le behaviour
et `+0x98 TriggeringAbility` **après** ; `TriggerAbilityBehaviour$$Execute` reconstruit son
`AbilityEntities` par `AbilityEntities$$.ctor(<copie de l'entrant>, null)` et n'écrase que
`actor`/`caster`/`target`/`unitFeetTiles` ; `TriggerTriggeredAbilityOperation` et `ExecuteBy` ne
font que **recopier** les 0x148 octets. Or le porteur est `On(0x29)`, dont le canal est nul.
`TriggeringAbilityIs(1557)` est donc FAUX **aussi** sous `Custom` — poser le terme aurait
restreint le pool aux seuls `necroSmnWarrior` là où le natif ne restreint rien.

## 4. Ce qui a été MESURÉ LIVE (build `rnca9r7q6c`, board `MC1_67`, seed 777)

Montage : `--equip-relic "necroOverlord:PhasalSubjugator:1"`, `--place necroOverlord:3,2`,
`--place necroWarden:3,3`. `act finish --unit <overlord>` :

```
[Ability_Power e=83 «PhasalSubjugator»]          <- classe 1, On(0x1c)
  AddUnit e=116  Unit_IsSummoned=1 Unit_Parent_Id=83
  ChangeStats e=116  MaxHealth=5875  FixedArmor=1470  Attack=1960
[/]
[Ability_Power e=83 «PhasalSubjugator»]          <- classe 2, On(0x29) : VIDE
[/]
```

**Deux fires distincts de 1557 sur la même clôture d'activation**, et le second **sans spawn** —
c'est exactement le `If(NOT HasFriendlyWarrior(), Spawn)` du behaviour, le Guerrier venant d'être
posé par le premier.

**Le triple de stats fige la lecture TERTIAIRE** : `summonHp[0] / summonArmor[0] / summonDmg[0]` =
**5875 / 1470 / 1960**, contre **8729 / 2184 / 2912** au dernier palier — ce que le port lirait s'il
prenait le niveau des PASSIFS (50 dans tout runner normalisé). Témoin non dégénéré.

⚠ Le `visualId` de l'unité posée est **`necroNpc1Warrior`**, pas `necroSmnWarrior` : c'est
précisément pour ça que `VisualUnitIdFromUnitId` rend les **deux** formes.

## 5. Ce qui n'est PAS couvert

* **Le `TriggerAbility(1556)` produisant une action OBSERVABLE** : dans les deux montages joués,
  `MyWillBeDoneOverlordAbility$$GetTargetFriend` n'a élu personne (aucun allié mécanique adjacent
  n'avait de cible d'attaque normale **depuis sa propre tuile**). Le chemin est confirmé
  structurellement (le second groupe existe) et par le cliquet offline (étage 3, qui exerce
  `TRIGGERED_ABILITY_BEHAVIOURS[1556]` et exige une action émise), pas par un delta live.
* `selectionType = 3` / `ignoreUnitHavingAbility = false` du `TriggerAbility` : la feuille portée
  n'expose ni l'un ni l'autre (résidu PARTAGÉ, déjà nommé par `geminae_superia.py`).
* Le seed BC est **périmé sur ce porteur** (`[seed-bc] bloc Units NON rattrapé (#254-bc) :
  necroOverlord{PassiveAbilities,Traits}`) — sans effet sur ce qui précède (la relique arrive par
  `--equip-relic`, pas par le bloc `Units`), mais à savoir avant toute mesure de kit sur lui.

Cliquet : `tests/engine/runner/test_1011r1_phasal_subjugator_offline.py` (15 tests, 6 étages ;
5 mutations adversariales vues ROUGES).
