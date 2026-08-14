# #1035 — `BlightedLand` et `HyperCorrosiveAcid` : deux mythiques de MoW, deux formes opposées

**Verdict** : `HyperCorrosiveAcid` (1455, `tyranBiovore`) est **PORTÉE ET CONFRONTÉE LIVE** sur sa
face TRIGGER + BEHAVIOUR. `BlightedLand` (1447, `deathCrawler`) est **CÂBLÉE** — sa face ability
est un owner-effect permanent qui tient en une entrée de registre. Les **DEUX EFFETS** qu'elles
posent (1448, 1442) restent **HORS `EFFECT_CLASSES`** : leurs canaux de dégât ouvrent sur la
RARETÉ, canal absent du port. Dégradation RESTRICTIVE et nommée (`#1035-r1`, `#1035-r2`).

Les deux porteurs sont **au pool** (`rl_duel build --list-pool` → 8 MoW spawnables, `deathCrawler`
et `tyranBiovore` compris) : rien à injecter, le montage est `--equip-mythic`.

---

## 1. Ce que le décompilé dit — les deux classes n'ont pas la même forme

| | `BlightedLandAbility` | `HyperCorrosiveAcidAbility` |
|---|---|---|
| parent (`frida/classes.tsv`) | `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` |
| override (`sources_win`) | **`$$GetEffectType` SEUL** (slot 34) | `$$CreateTrigger` (24) **et** `$$CreateBehaviour` (26) |
| `TriggeredAbilityType` | 0x5a7 = 1447 | 0x5af = 1455 |
| `EffectType` posé | 0x5a2 = 1442 `BlightedLand_ExtraDamagePct` | 0x5a8 = 1448 `HyperCorrosiveAcid_ExtraDamagePct` |
| forme | owner-effect PERMANENT posé à l'init | refresh-or-add sur `DamageTaken` |

`case-999` §7 rangeait `BlightedLand` parmi les « trois `GetEffectType`-only dont il faut d'abord
identifier la base ». La base est **lue**, pas devinée : `frida/classes.tsv` la nomme, et
`sources_win` confirme que la classe ne déclare **que** `$$GetEffectType` + `.ctor`.

### `BlightedLandAbility` — tout vient de la base

```
AOwnerEffectTriggeredAbility$$CreateTrigger   = OnOwnerSpecificAbilityInit(this.AbilityType@<this+0x10>)
AOwnerEffectTriggeredAbility$$CreateBehaviour = If( CreateCondition(abilityState),
                                                   AddEffect(GetEffectType(),
                                                             AbilityState(Owner@<DSLSelectors+0x30>,
                                                                          AbilityType(this)),
                                                             source = Owner, targets = Owner,
                                                             options = <Nullable ZERO-initialise>) )
AOwnerEffectTriggeredAbility$$CreateCondition = <DSLTriggers+0x70>                     # YesTrigger
BlightedLandAbility$$GetEffectType            = return 0x5a2
```

C'est exactement le patron `Vitarus` / `NornCrown` / `MoreGitzOverEre` — donc une entrée de
`ABILITY_INIT_OWNER_EFFECTS`, rien de plus.

### `HyperCorrosiveAcidAbility` — un trigger à quatre conjoints

```
CreateTrigger   : On(0x0f = DamageTaken, ownerNeedsToBeAlive: 1)
                  & AreEnemies(Owner@<sel+0x30>, Target@<sel+0x60>, ByCurrentTeam)
                  & IsAlive(Target@<sel+0x60>)
                  & AreFriends(Owner@<sel+0x30>, Actor@<sel+0x40>, ByCurrentTeam, anyEntity: false)
                  & IsUnitWithVisualId(Actor@<sel+0x40>,
                        VisualUnitIdFromUnitId(GetStringConstant(0x0 = unitId)))
CreateBehaviour : If( HasEffect(Target@<sel+0x60>, 0x5a8, onlyActive: 0, effectTarget: 6),
                      ChangeEffectTurns(Target@<sel+0x60>, 0x5a8, turns, ChangeType.Set = 1),
                      AddEffect(0x5a8, get_AbilityStateReference(this),
                                source = Owner@<sel+0x30>, targets = Target@<sel+0x60>, turns) )
   avec turns = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds))
```

⚠ **Le gate porte sur l'ACTEUR, jamais sur le porteur.** Aucun `get_OwnerIsActor` : le Biovore n'a
pas à frapper, et ne frappera jamais sur ce vecteur. C'est sa **Spore Mine** (`unitId` =
`"tyranSmnSporeMine"` au gameconfig) qui déclenche, et l'effet se pose sur SA victime.

Le behaviour est celui d'`ElectrochaffBackups` (#1025) au type d'effet près, `ChangeType.Set`
compris — un re-déclenchement REMET la durée, il ne l'accumule pas.

---

## 2. L'étage réparé : `IsUnitWithVisualId` comparait une chaîne à une LISTE

Le natif compare **une** chaîne. `IdunBattle.Entities.Selectors.IsUnitWithVisualIdTrigger$$ShouldTrigger`,
corps entier :

```
unit  = <selecteur @+0x10>.SelectUnit(entities);   if (unit == null)  return false;
value = <formule   @+0x18>.Calculate(entities);    if (!HasValue)     return false;
return System.String.op_Equality( UnitExtensions$$GetVisualUnitId(unit), value.Value );
```

Mais le nœud PORTÉ qui l'alimente au call-site natif, `entities/formulas.py::VisualUnitIdFromUnitId`,
rend délibérément les **DEUX** formes (`[unitId, gameconfig.unit(unitId).visualId]`) — c'est la
RÉDUCTION OFFLINE déjà écrite dans son propre docstring, parce que le champ `visualId` du port
porte l'id de CONFIG pour une unité spawnée offline et l'id VISUEL pour une unité seedée du live.

⇒ composer les deux nœuds **comme le natif les compose** comparait une `str` à une `list` :
**FAUX systématiquement, sans erreur**. `IsUnitWithVisualId` accepte désormais les deux formes de
valeur (scalaire ⇒ égalité native au bit près ; collection ⇒ appartenance, la réduction que le port
assume déjà pour `UnitsWithIds`/`UnitsWithVisualId`).

**Rayon de souffle MESURÉ au moment du changement** : `IsUnitWithVisualId` n'avait **0 consommateur
EXÉCUTABLE** dans `engine/**` — les six autres occurrences du dépôt sont des citations de décompilé
en docstring. `engine/runner/operations/triggers/loki/hyper_corrosive_acid.py` est le **premier**.

---

## 3. La confrontation LIVE — et pourquoi son montage est étroit

Une Spore Mine n'inflige du dégât que par deux voies, **toutes deux hors de portée d'un
`applyAction` direct** (un summon s'OBSERVE, il ne se COMMANDE pas) : son attaque normale
`FloatingDeath_NormalAttack` (1146) jouée par `PlayAutomaticUnits` au turn-start, et l'explosion

```
FloatingDeath_AttackAbility$$CreateTrigger   = On(0x2 = PreUnitDeath_2, alive: 0)
                                               & get_OwnerIsTarget & NOT TargetIsOverkilled
FloatingDeath_AttackAbility$$CreateBehaviour = AttackWithAbilityDamage(
                                                   Owner@<sel+0x30>,
                                                   AdjacentEnemies(Owner, unique: 1, 3),
                                                   MinMaxDamage, DamageProfileFromConfig,
                                                   Direct(GetNumberConstant(0x2f)), ..., 2)
```

**`NOT TargetIsOverkilled` est ce qui rend le régime étroit** : une mine a 1664 PV et un ork la
SURKILL, donc l'explosion n'a pas lieu et rien n'est mesurable. **Trois montages successifs n'ont
rien produit pour cette seule raison** (`--dmg-target 1` ne mord pas sur ce chemin). Ce qui ouvre le
régime est `--unit-stat "orksNob:Damage=1"` : l'ennemi survit, frappe sans surkiller, les mines
ripostent — et le vecteur `On(0x0f = DamageTaken)` existe enfin, `actor` = une mine.

Montage retenu (fixture nommée `monter_biovore_et_declencher`, board `MC1_67`, seed 777) :
MoW `tyranBiovore` + `--equip-mythic` ; `BioMinefield` (1144) casté sur l'ennemi → **3** mines
adjacentes (`nrOfSummons = 3`) ; fin de tour + tour IA.

| bras | dégâts échangés | effets sur l'ennemi |
|---|---|---|
| `--equip-mythic` | `u100->u77 1467`, `u103->u77 3377` | `BeastSlayer_ExtraDmg`, **`HyperCorrosiveAcid_ExtraDamagePct(r2)`**, `Contaminated_Unit(r2)`, `BeastSlayer_ExtraBlock` |
| **CONTRE-BRAS** (sans) | `u100->u77 1467`, `u103->u77 3377` — **identiques** | `BeastSlayer_ExtraDmg`, `Contaminated_Unit(r2)`, `BeastSlayer_ExtraBlock` |

La séparation est **nette et non dégénérée** : mêmes coups au point près, seule l'option change.
`(r2)` = `ConvertRoundsToTurns(nrOfRounds = 1)` à 2 joueurs, la valeur que le port calcule.

Le **montage** lui-même est confirmé indépendamment par `probe_999_mythic_monte.py --unit
tyranBiovore --level 1` : `entite 81 TERTIAIRE id=1455 level=1 mult=100`, hiérarchies
`{0: 6, 2: 4, 3: 1}` — l'inscription de **hiérarchie 3** est bien là.

Troisième étage live, et il n'a pas d'équivalent offline : **le `visualId` que la mine porte en
bataille est `tyranSmnSporeMine`**, exactement la constante que le gate compare. Le gameconfig
porte `visualId = null` pour cette entrée, donc `VisualUnitIdFromUnitId` ne rend QUE l'id de
config : si le natif la nommait autrement en bataille, le gate serait VRAI offline et FAUX en live,
silencieusement.

---

## 4. Le mur : la RARETÉ — déjà mesuré, ne pas le re-mesurer

Les deux effets restent HORS `EFFECT_CLASSES` :

```
HyperCorrosiveAcid_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack =
    EffectBonus$$ForPercentIncrease(
        get_OwnerIsTarget
        & ( AreFriends(Caster@<sel+0x48>, EffectSource(Effect@<sel+0x38>), 0, false)
            & HasRarity(Caster@<sel+0x48>, 5 = Mythic)
            & HasTrait(Caster@<sel+0x48>, 0x10 = UnitTrait.Hero) ),
        ConfigVar(0xa = AbilityVariableType.extraDmgPct, GetAbilityState(effet), effet@+0x60) )

BlightedLandEffect$$CreateTargetSelector =
    UnitsOnTilesWithEffect(
        UnitsWithRarity( Friends(Owner@<sel+0x30>, AllUnits@<sel+0x20>, 3), 5 = Mythic, 3),
        0x4dc = EffectType.Contaminated )
BlightedLandEffect$$CreateEffectDamageBonusForAttack =
    EffectBonus$$ForPercentIncrease(get_OwnerIsCaster,
                                    ConfigVar(0xa = extraDmgPct, ...))
```

i2 concordant : « Enemies that are damaged by a friendly **Spore Mine** take +{extraDmgPct}% Damage
from attacks by **Mythic characters** for {nrOfRounds} round » ; « Friendly **Mythic** characters
deal +{extraDmgPct}% Damage while on a **Contaminated** hex ».

**Tout ce verrou est déjà mesuré par `case-1024-shield-of-faith-on-my-position.md` §4** — l'enum
existe, `BC.Units[].Rarity` atteint bien `BaseUnitComponent.Rarity` (contre-épreuve live
`--unit-stat "<vis>:Rarity=4"`), et **`rl_duel build` pose `targetRarity = 5`, donc dans un runner
standard toute unité est Mythic et `HasRarity(·, Mythic)` est uniformément VRAI**. C'est le régime
DÉGÉNÉRÉ : un port qui oublierait le gate serait d'accord avec le natif dans tous les bras par
défaut. Inscrire ces effets « au jugé » est donc précisément la faute que ce verrou empêche.

**Apport de cette tranche sur ce seul point — la VOIE que `readUnitConfig` peut prendre.**
`case-1024` prescrit de résoudre `BaseUnitComponent.Rarity` par `getFieldOffset` (le piège `0x74`,
qui vaut `AbilityVariablesMultiplierPercentage` dans `UnitConfiguration` et la RARETÉ dans
`BaseUnitComponent`). Or `readUnitConfig` tient **déjà** le pointeur `UnitConfiguration` :

```
IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent :
    BaseUnitComponent+0x70 = Math.Max(UnitConfiguration+0x7c /* Level */, 1)
    BaseUnitComponent+0x74 =          UnitConfiguration+0x80 /* Rarity */
```

et `UnitConfiguration+0x80` **EST** `Rarity` (`sources_win`, ancré par ses deux voisins DÉJÀ portés :
`+0x74 AbilityVariablesMultiplierPercentage` et `+0x78 TertiaryAbilityVariablesMultiplierPercentage`,
que `UnitContext` cite aux mêmes offsets). Le capteur se réduit donc à **un champ de plus** dans le
dict que `readUnitConfig` rend déjà, résolu comme ses cinq voisins par
`getFieldOffset(unitConfigurationClass, "Rarity")` — jamais par recopie de `0x80`.

**Cela exige une FENÊTRE DE REINJECT**, qu'un agent n'a pas le droit d'ouvrir. Résidus `#1035-r1`
(effet 1448) et `#1035-r2` (effet 1442), tous deux `BLOCAGE: capteur`.

---

## 5. Ce qui N'EST PAS couvert

- **Les deux canaux de dégât** (1448, 1442) : non portés, verrou capteur ci-dessus. Aucune mesure de
  l'amplitude du `+extraDmgPct` n'est donc faite ni offline ni live.
- **`BlightedLand` n'a PAS de confrontation live de sa POSE.** L'entrée `ABILITY_INIT_OWNER_EFFECTS`
  est un FILET offline (sur un runner, l'effet 1442 arrive par la CAPTURE, sa `CreateActiveCondition`
  héritée étant le corps dédupliqué `return <DSLTriggers+0x70>` = `YesTrigger`, refcount 182).
  Le cliquet offline `test_le_seed_offline_pose_l_owner_effect_de_blighted_land` couvre la voie
  tertiaire ; le pendant live reste à jouer.
- **L'attaque normale de la mine** (`FloatingDeath_NormalAttack`, 1146) n'a pas été le vecteur
  mesuré : c'est la RIPOSTE / l'explosion qui a fourni le dégât. Le trigger porté ne distingue pas
  les deux (il ne lit ni `ability_type` ni le profil), donc l'écart est sans observable — mais il
  n'est pas mesuré.
- **`FloatingDeath` reste non porté côté runner** (le commentaire d'`handler.py` le dit déjà :
  « mine inerte offline »), donc le vecteur `DamageTaken` avec `actor` = une mine **n'existe pas en
  simulation pure**. Le port de `HyperCorrosiveAcid` est correct et gardé par 17 cliquets offline,
  mais il ne sera exercé de bout en bout offline que le jour où la mine agira. C'est un étage
  AMONT, pas un défaut de cette tranche.

---

## 6. Résidus ouverts

- **#1035-r1** — porter `HyperCorrosiveAcid_ExtraDamagePctEffect` (1448) : `ForPercentIncrease`
  gaté `get_OwnerIsTarget & AreFriends(Caster, EffectSource) & HasRarity(Caster, Mythic) &
  HasTrait(Caster, Hero)`. BLOCAGE `capteur` (cf. §4).
- **#1035-r2** — porter `BlightedLandEffect` (1442) : aura dont le sélecteur est
  `UnitsOnTilesWithEffect(UnitsWithRarity(Friends(Owner), Mythic), Contaminated)`. BLOCAGE
  `capteur` (même canal), plus l'étage `UnitsOnTilesWithEffect` à vérifier côté port.

---

## 7. Ce que cette tranche a trouvé en passant

**La PR #1026 « ShieldOfFaith et OnMyPosition — deux mythiques de MoW » n'a livré AUCUN PORT, et
l'audit a raison de les compter non portées.** Le message de son commit (`9024bea6`) le dit
explicitement : « RE complète, confrontation live à 4 séparations, **aucun port** (mur = canal
rarity) ». Le titre de la PR annonce deux abilities, le livrable est une RE + un verdict de
blocage. Il n'y a donc **pas de contradiction** entre `kit-coverage.md` et cette PR — seulement un
titre qui se lit comme un port. Mesure : `git grep ShieldOfFaith -- scripts/python/engine` ne rend
que le mirror d'enum et des citations en docstring ; aucune entrée de registre.
