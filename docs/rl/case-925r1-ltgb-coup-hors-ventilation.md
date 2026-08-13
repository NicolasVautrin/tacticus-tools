# `#925-r1` — le `+1 coup` de `LetTheGalaxyBurn` n'était pas mal ATTRIBUÉ : il était joué DEUX FOIS

> Tranche « dégât appliqué & soin » — 4 résidus fermés (`#925-r1`, `#966-r1`, `#982-r5`, `#957-r3`
> partiellement), 2 non traités (`#966-r3`, `#942-r2`). Numéro neuf réservé et non consommé :
> **`#925-r3`**.

## 1. La question binaire, et pourquoi la réponse est « ni l'un ni l'autre »

L'énoncé hérité disait : *le port attribue le `+1 coup` de `LetTheGalaxyBurn` à la cible PRIMAIRE là
où le natif l'attribue à une cible du CLEAVE.* Il est **REPRODUIT à l'identique** (l'énoncé n'était
donc pas périmé, contrairement à la moitié des résidus de ce dépôt) mais son **diagnostic est faux** :
le port ne se trompait pas de cible, il jouait **un coup de trop**, et c'est le **tirage
surnuméraire** qui faisait ensuite rater au cleave le `Maybe` que le natif lui accorde.

## 2. La RE — le canal #179 est un VOLET du `Attack(...)`, pas un enfant de la feuille

`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
monte **UN SEUL** `IdunBattleLogic.Entities.DSLBehaviors$$Attack` autour de **trois volets FRÈRES** :

```
b1 = DSLBehaviors$$AttackDamage(...)                              # les coups d'ARME
b2 = <vslot 0x4e8>(abilityState)   = $$GetCustomNormalAttackBehaviour   # le FOLD, feuille NUE
b3 = DSLBehaviors$$ExecuteAdditionalHitsWithDamageProfileType(...)      # le canal #179
return DSLBehaviors$$Attack(caster, target, b1 & b2 & b3, source)
```

Le FOLD est un **frère** de `b3`, jamais son parent : il n'a aucun titre à le rejouer. C'est
exactement le même littéral natif (`isOutsideAttack`, 8ᵉ argument d'`$$AttackDamage`) qui pilote
déjà l'absence de `On(PreAttack = 5)` sur cette feuille (#925), et pour la même raison — **une
feuille nue n'ouvre pas d'attaque, donc elle ne porte aucun des volets que le `Attack(...)`
englobant porte déjà**.

## 3. Ce que le port faisait, et pourquoi ça se voyait si mal

Le gate de `damage_ops/ability.py` était `is_attack_damage_op` **SEUL**. Or le port joue le fold
**après** le `FinishAttack` / `On(Attack = 9)` de l'attaque primaire (`damage.py`, site du cleave) —
donc **après** que `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`
a effacé le flag persistant **et posé `DespoiledGround`** sur la tuile de la cible. Le descripteur d'
`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` se re-qualifiait
alors par **l'AUTRE branche** de son gate (`TargetHasTileEffect | IsPersistentData`).

La trace le montre sans ambiguïté (`probe_925r1_ltgb_attribution.py --verbose`) :

```
collect voie=normal   tgt astraBullgryn  n=1  pd=[(LetTheGalaxyBurn:1482,'LetTheGalaxyBurn')]
collect voie=ability  tgt astraBullgryn  n=1  pd=[]          <-- le FOLD, flag DEJA efface
exec    voie=normal   tgt astraBullgryn  per_hit=[542]       <-- le coup NATIF
exec    voie=ability  tgt astraBullgryn  per_hit=[626]       <-- le coup EN TROP
```

## 4. La mesure — décomposée par étage, jamais un scalaire fitté

Board `MC1_67`, seed `4463111`, `templAggressor` (`Boltstorm`) avec le trait `LetTheGalaxyBurn`
**greffé sur l'entité** (`--unit-stat Traits=[...]`, qui réécrit le seed BC : la greffe mord des
DEUX côtés).

| | cible primaire | `necroWarden` | `necroDestroyer` |
|---|---|---|---|
| **NATIF** | **3508** | **1185** | **1654** |
| port AVANT | 4134 | 1185 | 1129 |
| port APRÈS | **3508** | **1185** | **1654** |

Ventilation native par coup, **par cible** — c'est elle qui a tranché, pas le total :

```
astraBullgryn   [449, 436, 456, 542 | 619, 513, 493]   aat [1128 x4 | None x3]
necroDestroyer  [608, 493, 553]                        aat [None x3]      <-- 3 coups
necroWarden     [618, 567]                             aat [None x2]      <-- 2 coups
```

`necroDestroyer` a **un coup de plus** que `necroWarden` : c'est le `LetTheGalaxyBurn` natif. Après
correctif, le port le tire au même endroit et pour la même valeur (**553**).

**Généralisation, second porteur de fold** (`adeptMorvenn` / `RighteousRepugnance`, dont le gate est
l'INVERSE — `IsMeleePosition` au lieu d'`IsRangedPosition`) : primaire **4709 = 4709**,
`necroWarden` **1724 = 1724**. Le foyer corrigé est partagé, donc confronter un seul porteur ne
distinguerait pas « le fix est juste » de « le fix est juste sur CE porteur ».

## 5. Le correctif

`damage_ops/ability.py` — un point de mutation NOMMÉ, pendant exact de
`additional_targets.fold_emits_pre_attack` (#925) sur l'axe COUPS :

```python
def leaf_executes_additional_hits(is_outside_attack: bool) -> bool:
    return bool(is_outside_attack)
...
if is_attack_damage_op and leaf_executes_additional_hits(is_outside_attack):
```

L'appel se résout dans les **globals du module**, donc un `setattr` de module mord — c'est ce qui
rend la contre-épreuve gratuite (rejeu du même bundle d'état, même Mersenne Twister).

## 6. Gardes, et la garde vue ROUGE

`tests/engine/test_925r1_ltgb_attribution_live.py` — **7 crans × 2 porteurs**, dont un cran de
non-trivialité et une contre-épreuve intégrée.

⚠ **Le cran de non-trivialité a d'abord été écrit FAUX, et il a rougi sur un montage pourtant
juste** : il comparait le **COMPTE** de coups tirés du canal #179 par la voie `ability`, or le
CLEAVE emprunte la même voie — les deux régimes en tirent 1 chacun (le corrigé sur `necroDestroyer`,
légitime ; le mutant sur la primaire, en trop). Le discriminant est la **CIBLE**, pas le nombre. Un
cran de non-trivialité mal ciblé fait accuser le montage à la place du code.

**Mutation adversariale** (`leaf_executes_additional_hits` forcée à `True` dans le fichier) —
6 failed / 8 passed, message verbatim :

```
etage 3 : PV par cible -- port corrige {'astraBullgryn': 4134, 'necroWarden': 1185,
'necroDestroyer': 1129} != natif {'astraBullgryn': 3508, 'necroWarden': 1185,
'necroDestroyer': 1654}
```

et sur le second porteur : `{'astraBullgryn': 5315, 'necroWarden': 3981} != {'astraBullgryn': 4709,
'necroWarden': 1724}`.

## 7. Rayon de souffle — mesuré, pas supposé

`is_outside_attack = False` a **trois** producteurs : le FOLD primaire, les feuilles nues de
transfert d'`haze_of_corruption.py`, et `SortedAttackSeries` (`combat.py`, qui le pose sur ses
enfants). Le risque nommé était `1088 HellfyreMissileRack` (deux feuilles NUES sur la même cible).

| joué | résultat |
|---|---|
| `test_487_hellfyre_missile_rack_live.py` (le risque nommé) | **4 passed** |
| `test_478_cleave_live.py` + `test_black_legion_1029_1020_live.py` | **23 passed** |
| `test_ability_hits_channel_live.py` + `test_let_the_galaxy_burn_live.py` | **8 passed** |
| `test_925_fold_pre_attack_live.py` | **13 passed** |
| `test_925_boltstorm_faces_offline` + `test_944_combat_behaviours_offline` + `test_949_ledger_complet_offline` | **27 passed** |
| `test_925r1_ltgb_attribution_live.py` (neuf) | **14 passed** |
| `probe_925_fold_pre_attack.py --regime boltstorm` et `--regime rr` | **OK** |

## 8. Une prémisse PÉRIMÉE, corrigée en chemin

`test_925_fold_pre_attack_live.py` faisait porter son verdict sur la **ventilation par coup** et
**pas** sur le total de PV, parce qu'à l'écriture de #925 la divergence de ce résidu subsistait. Elle
est fermée : le probe #925 passe donc du **rapport** au **verdict** sur le PV (`etage 2ter`), et la
docstring du test dit ce qui a changé plutôt que de le taire.

---

# Les trois autres résidus de la tranche

## `#966-r1` — FERMÉ : `isNegative` est **LU**, et l'énoncé se trompait de CAUSE

**VERDICT : POSITIF LU** pour `1503 HealingBalms_ExtraCritDamage` et `1504 …_ExtraCritChance`. Les
deux fabriques `IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_498`
(1503) et `…b__14_497` (1504) posent `xor r9d, r9d` — le 3ᵉ argument `isNegative` d'
`IdunBattle.Entities.Effects.DynamicStatModifierEffect$$.ctor` — à **false**.

⚠ **Pourquoi chercher `1503`/`0x5df` ne pouvait RIEN rendre** : `_effectsBuilder` est un
`Dictionary<EffectType, Func<IEffect>>` — la **clé vit chez l'appelant**, la lambda ne porte
**jamais** l'EffectType. C'est `0x5de` (l'ABILITY) qu'il fallait chercher. Et
`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` fait **20 205 instructions**, hors de
portée du pseudo-C — d'où le faux constat « l'inscription passe par une table de données ». Le
résidu concluait juste (positif) **par accident**.

**Témoin négatif** : sur les **14** fabriques `DynamicStatModifierEffect` du build, **13** posent
`false` et **une seule** `mov r9b, 1` — `…b__14_533` → `1541 AugmentedAssault_ReduceArmor`. Les deux
enregistrements sont structurellement identiques ; seul `r9` change. Un accord sans ce témoin ne
prouverait rien.

**Aucun code exécutable ne change** : la valeur rendue était déjà positive. Le livrable est une
**citation qui remplace une inférence** — et trois données lues en prime (`abilityType` =
`TriggeredAbilityType`, `isMultiply = false`, `keepOnRevive = true`).

⚠ Le maillon **dérivé** et non lu directement : la formule d'index `N = (offset - 8) / 8` du cache
de délégué. Corroborée par la sémantique (497 lit `extraCritChance` et tombe sur l'EffectType
`…ExtraCritChance`) et par la monotonie des offsets, pas confrontée live.

## `#982-r5` — FERMÉ : l'énoncé est FAUX sur son point central, et le vrai manque était un CLIQUET

L'énoncé annonçait « le port n'est pas écrit ». **Il l'est** : le prédicat
(`runner/abilities/attack_query.entity_can_be_healed`, mirror 1:1), le substrat
(`UnitFlagsComponent`), le seed (`runner/snapshot._load_unit_flags` ← `combatSnapshot.units[].unitFlags`)
et le gate d'exécution (`operations/heal.py`) sont tous en place **et mordent**.

Mesure (`probe_982r5_swap_decisionview.py`, `MC1_67` / seed 777, `spaceWolfPriest` injecté au
catalogue) :

```
unitFlags spaceWolfPriest = [23] | autres = {necroWarden: [], tauCrisis: [], ultraCalgar: []}
decisionView.abilities    = [69, 1211, 1212]
PORT  flags=[23]  actives=['HealingBalms_Heal', 'Loki_NormalAttack', 'RitesOfMorkai']
```

⇒ **La prémisse la plus faible du dossier est TRANCHÉE** : `decisionView` publie bien `1212` et
**pas** le `18` générique. Le §SWAP de `runner/abilities/loki/healing_balms.py` est **fondé**.

**Ce qui manquait vraiment** : rien ne rougissait si le 3ᵉ disjoint disparaissait →
`tests/engine/test_982r5_can_heal_full_health_offline.py` (6 crans, offline pur). **Vu ROUGE** par
mutation de `attack_query.py:217` :

```
le 3e disjoint d'`EntityCanBeHealed` ne mord PAS : caster AVEC le flag
`CanHealFullHealthUnits` -> False (attendu True), caster SANS -> False (attendu False),
sur une cible a PLEINS PV dans les deux cas
```

S'y ajoutent **trois proses** qui affirmaient une inertie révolue (« aucun chemin du port ne les
pose », « aucun consommateur porté ne le lit ») — elles ont produit **deux verdicts de résidu
erronés d'affilée** (#966-r2 puis #982-r5). Corrigées dans `attack_query.py`,
`runner/abilities/loki/healing_balms.py` (×2) et `operations/heal.py`.

**Le seul écart RÉEL restant**, nommé et borné : la **porte de résultat vide** de queue d'
`IdunBattle.Operations.HealUnitOperation$$Execute`
(`… && !HasFlag(caster, 0x17)) return this;`). Le port sort sur `healed <= 0` sans consulter le
flag — écart borné aux **sorties non modélisées** (event, statistiques, triggers, `RefreshEffects`),
**jamais aux PV**.

⚠ **Leçon de méthode** : `EntityCanBeHealed` est atteint par le **slot virtuel `0x11`**
d'`IAttackQuery` — recenser ses consommateurs **par xref est structurellement impossible** (ses
seuls xrefs non-DATA sont le décorateur de cache). Même classe de faux négatif que l'absence dans
une table indexée par adresse.

## `#957-r3` — l'override est POSÉ, la confrontation live RESTE

L'énoncé est **confirmé** : `IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions`
passe `AActiveAbility$$GetHits()` = `GetNumberConstant(0x2f = nrOfHits)` **BRUT**, là où le chemin
générique du port (`get_special_hits` = `GetDefaultAttackHits(nrOfHits, ExtraHits)`) **ajoute** la
stat `ExtraHits` du caster. `1197` entre au registre `_MAKE_DMG_INPUT_OVERRIDES` avec son
`hits_override` littéral, et `tests/engine/test_957r3_excruciating_hits_offline.py` (3 crans) garde
la forme **et** le régime qui la rend discriminante (`ExtraHits = 2` ⇒ générique ≠ override ;
`ExtraHits = 0` ⇒ égalité — ce qui explique que l'écart soit resté invisible).

**NON CONFRONTÉ LIVE** faute de budget : l'accord avec le natif sur `emperNoiseMarine` porteur d'un
`+ExtraHits`. La ligne de backlog est réécrite à cet état.

## Ce qui n'est PAS couvert

* `#966-r3` et `#942-r2` — **NON TRAITÉS** (budget). Pour `#966-r3`, la prémisse `decisionView`
  publie `1212` est désormais **acquise** (ci-dessus) ; restent les trois effets posés, la magnitude
  du soin, le ré-armement et le soin retardé.
* **Un seul board (`MC1_67`) et deux seeds** (`4463111`, `777`) — la géométrie des montages est
  dérivée, mais l'amplitude ne s'estime pas depuis un board.
* **La lecture verbatim de `IdunBattle.Operations.AttackDamageOperation$$Execute`** : ghidra-mcp est
  resté injoignable (port 13337) pendant toute la tranche. Le correctif s'appuie sur la structure
  de `$$GetAttackDamageBehaviour`, **déjà lue et versionnée par #925** sur ce build, plus la mesure
  live bit-exacte sur deux porteurs. Ce qui reste à confirmer d'un grep : que
  `$$ExecuteAdditionalHitsWithoutDamageProfileType` (appelé depuis `AttackDamageOperation$$Execute`)
  ne traite **pas** les descripteurs #179 hétérogènes — deux transcriptions du dépôt se
  contredisent sur ce point (`case-202-abraxas-kit.md` dit « le coup bonus BASE », le commentaire
  d'`ability.py` dit « les coups additionnels HÉTÉROGÈNES »). Aucune des deux ne change le verdict
  mesuré, mais la trancher fermerait la dernière hypothèse de ce dossier.
* **Les autres feuilles NUES** (`haze_of_corruption`, `SortedAttackSeries`) perdent elles aussi le
  canal #179 : conforme à la RE, mais **non confronté** — aucun de leurs porteurs n'a de descripteur
  #179 actif dans les tests joués.
