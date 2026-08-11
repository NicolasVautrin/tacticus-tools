# #915 — `PropheticSentinel` : `ToOwner` ne veut PAS dire « sur le porteur »

Passif de kit de `thousSekhetar` (« Sekhetar Robot »), `TriggeredAbilityType` 0x607 = 1543.
**DEUX** abilities natives sous le même id, **TROIS** prédicats de trait deux à deux différents.

## Ce que le natif fait

```
PropheticSentinel_AddBuffAbility
  CreateTrigger   = <DSLTriggers+0x30>  = On(0x21 AbilityInit) & <+0x70> & get_OwnerIsActor
  CreateBehaviour = AddStaticStatModifierEffectToOwner(0x616=1558 ExtraArmor,      FixedArmor,  ConfigVar(0x1b extraArmor),  turns=NULL)
                  & AddStaticStatModifierEffectToOwner(0x617=1559 ExtraBlockChance, BlockChance, ConfigVar(0x15 blockChance), turns=NULL)
                  & AddStaticStatModifierEffectToOwner(0x618=1560 ExtraBlockDamage, BlockDamage, ConfigVar(0x14 blockDmg),    turns=NULL)

PropheticSentinel_OverwatchAbility
  CreateTrigger   = On(0x17 TurnEnd) & <DSLTriggers+0x28 = IsTurnOf(Owner)>
                    & AmountIsEqualOrGreater(Count(UnitsWithTrait(AdjacentFriends(Caster@+0x48, CasterTile@+0x50, 1),
                                                                 0x3ea Psyker, 3)),
                                             <DSLFormulas+0x20> = Direct(1))
  CreateBehaviour = ActivateEffect(Owner@+0x30, 0x3f1 = Overwatch_AutoAttack)
```

## Le piège : `ToOwner` désigne où vit l'ENTITÉ-EFFET, pas qui reçoit la STAT

`AddStaticStatModifierEffect**ToOwner**` se lit comme un self-buff. Ce n'en est pas un.
L'entité-effet vit bien sur le porteur (elle est dans son `decisionView.effects`) mais la
modification de stat est **projetée** sur les unités du `CreateTargetSelector` de la **classe
d'effet** — un étage plus bas, invisible du `CreateBehaviour`. Même patron que `LionHelm` et
`UnbreakableDuty_DamageReduction`.

Le premier port de cette tranche déclarait `get_stat_modification_stat/amount` (self-buff) : trois
buffs donnés au porteur, zéro à ses voisins. **Aucune erreur, aucun crash** — c'est la mesure live
qui l'a retourné.

## L'appariement effectType → sélecteur n'est PAS lisible offline

Le build porte **deux** classes pour **trois** ids :
`Effects.Idun.PropheticSentinel_PsykerEffect` (`UnitsWithTrait(AdjacentFriends(Owner,1,3), 0x3ea
Psyker, 3)`) et `..._ChaosEffect` (même arbre, `0x7ea` **Chaos** ; corps ICF-dédupliqué avec
`ExplosiveMaladies_ExtraMeleeAttackEffect$$CreateTargetSelector`). `AStatModifierEffect$$.ctor` ne
porte pas l'effectType, donc rien n'apparie. **Tranché par la MESURE**, en régime discriminant —
quatre voisins **tous adjacents** couvrant les quatre combinaisons du couple (Psyker, Chaos),
`statModSources`, porteur ablvl 50 / multiplier 180 :

| voisin | traits | fixedArmor | blockChance | blockDamage |
|---|---|---|---|---|
| `thousAhriman` (2,1) | Psyker + Chaos | **898** | **25** | **898** |
| `deathBlightbringer` (1,2) | Chaos, non-Psyker | **898** | — | — |
| `astraPrimarisPsy` (3,2) | Psyker, Imperial | — | **25** | **898** |
| `adeptCanoness` (2,3) | ni l'un ni l'autre | — | — | — |
| `thousSekhetar` (2,2) | **le porteur** | — | — | — |

⇒ `1558 ExtraArmor` = sélecteur **Chaos** ; `1559`/`1560` = sélecteur **Psyker**. Le porteur ne
reçoit rien (`AdjacentFriends` retire sa propre tuile). Magnitudes bit-exactes contre le port :
`extraArmor`/`blockDmg` scalés par le multiplier (499 → 898), `blockChance` **non** (25, il est hors
`variablesAffectedByRarityBonus`).

## TROIS prédicats, jamais interchangeables

| face | artefact natif | prédicat |
|---|---|---|
| COMBAT — armure | `PropheticSentinel_ChaosEffect$$CreateTargetSelector` | amis adjacents **Chaos** |
| COMBAT — block ×2 | `PropheticSentinel_PsykerEffect$$CreateTargetSelector` | amis adjacents **Psyker** |
| COMBAT — overwatch | `..._OverwatchAbility$$CreateTrigger` | ≥ 1 ami adjacent **Psyker** |
| DÉCISION owner | `PropheticSentinelPlaybook.<…>MoveNext` | +20 / ami adjacent **Psyker** |
| DÉCISION non-owner | `PropheticSentinelNonOwnerPlaybook$$GetAdjacencyUtility` | **Psyker (20) + Chaos (20), CUMULÉS** |

Recopier l'un sur l'autre est l'erreur naturelle du kit ; la face non-owner (déjà portée avant cette
tranche) est la seule qui cumule.

## Le `CreateTrigger` du volet BUFF n'est pas celui du volet OVERWATCH

`PropheticSentinel_AddBuffAbility$$CreateTrigger` est **absent** de `frida/methods.tsv` : son corps
est ICF-dédupliqué avec `SummaryExecutionAddBaseEffectAbility$$CreateTrigger` (`return <+0x30>`).
De même, `..._OverwatchAbility$$CreateBehaviour` est dédupliqué avec
`PurgeResponse_ActiveOverwatchAbility$$CreateBehaviour`. L'hypothèse naturelle — « les deux classes
partagent le trigger d'adjacence » — est **RÉFUTÉE** : le départ se lit dans la **table des
pointeurs de méthodes** (le metadata déclare `CreateTrigger` slot 26 **et** `CreateBehaviour` slot
28 pour les deux classes ; les entrées consécutives donnent les corps). L'absence dans la table ne
prouve rien, dans les deux sens.

## Port

* `engine/entities/effects/loki/prophetic_sentinel.py` — les 3 classes d'aura (interface
  `aura_stat_modification_{stat,amount,targets}` consommée par `runner/operations/aura_stat_mods.py`).
* `engine/entities/effects/factory.py` — `EFFECT_CLASSES` ×3 + `ABILITY_INIT_OWNER_EFFECTS`.
* `engine/runner/operations/triggers/loki/prophetic_sentinel.py` + `dispatch/registry.py` — le
  ré-armement d'overwatch.
* `engine/playbook/prophetic_sentinel.py` + `adjacent_unit_preference.py` — la face DÉCISION owner
  (elle n'existait pas ; son absence valait 0 là où le natif rend `20 × n`).

## Validation

`probe_915_prophetic_sentinel.py` — 4 régimes discriminants (VERT, bit-exact), étage GÉOMÉTRIE (le
voisin Psyker+Chaos éloigné : les 3 contributions tombent à 0 des deux côtés, les autres ne bougent
pas), **4 mutants sur 4 ROUGES** (trait de chaque sélecteur, stat, variable `0x15`/`0x14`).
`tests/engine/test_915_prophetic_sentinel_offline.py` — 11 gardes offline, dont l'**absence** de
l'interface self-buff (le cran qui garde le bug d'origine).

## Résidus

* **#915-r1** — le mapping `EffectType → classe d'effet` n'est pas dérivable offline (le ctor ne
  porte pas l'id ; la convention de nom échoue sur 101 classes / 443). Ici tranché par la mesure ;
  un outil le rendrait dérivable pour les prochains kits à auras multiples.
* **#915-r2** — face DÉCISION owner : le natif prend le slot `0x84` de `GetAdjacentFriends`, dont le
  1er argument est `case.Position` (une **liste** de tuiles) ; le port part de la tuile candidate.
  Écart inerte pour un mover mono-tuile ; il mordrait sur une Machine of War.
* **#915-r3** — le ré-armement d'overwatch n'est **pas confronté live**. Offline, le trigger fire au
  bon régime et `ActivateEffect` repose le flag. Montage manquant : consommer l'overwatch du
  Sekhetar (le faire tirer en réaction), puis clore son tour **avec** puis **sans** ami Psyker
  adjacent, et lire le flag `active` de `1009` via `decisionView includeInactive`.
