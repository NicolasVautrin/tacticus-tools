# case-366-r1-blockhits-purgeresponse — `PurgeResponse` (1538) : le canal sans porteur

> Second et dernier implémenteur natif de `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction`,
> après `1117 InescapableAccuracy_overrideHits` (PR #422, `case-366-r1-inescapable-accuracy-override-hits.md`).
> Cette tranche ne fait pas qu'ajouter une classe : elle **élargit le balayage** de l'agrégateur à
> tout le board, parce que le trigger de `PurgeResponse` ne lit **rien** de son porteur.

## 1. Le trigger — un nœud, et rien d'autre

`IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger`, lu **à
l'assembleur** (un seul `call` vers `IdunBattleLogic.Entities.DSLTriggers`, aucun
`IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`) :

```
TriggeringAbilityIs( AbilityOrEffect( EffectType 0x3f1 = 1009 Overwatch_AutoAttack ) )
```

à comparer à l'autre implémenteur, `…InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReduction
Trigger` = `get_OwnerIsCaster & IsRangedAttack`. **Aucun nœud en commun.**

Trois points de la RE valent d'être écrits, chacun ayant un piège en face :

* **la surcharge d'`op_Implicit` est celle de l'`EffectType`** — `IdunBattle.Core.AbilityOrEffect$$
  op_Implicit` a trois surcharges d'enum, distinguées par le `set_*` qu'elles appellent ; celle
  appelée ici écrit le slot **`Effect`** (`AbilityOrEffect$$set_Effect`). `1009` est donc
  `EffectType.Overwatch_AutoAttack`, **pas** `ActiveAbilityType.ResurrectionOrb`, ni
  `TriggeredAbilityType.WhipcoilBody`, ni `UnitTrait.Resilient` — quatre enums, même entier ;
* **le nœud lit `AbilityEntities+0x98`** (`triggerAbilityOrEffect`), via
  `IdunBattleLogic.Entities.AbilityTypeSelector.TriggeringAbilitySelector$$Select` (copie plate
  `+0x98/+0xa0/+0xa8/+0xb0`). L'offset est établi par le `$$.ctor` d'`AbilityEntities`, dont les
  paramètres sont nommés : `currentAbilityOrEffect@+0x60`, `parentAbilityOrEffect@+0x7c`,
  `triggerAbilityOrEffect@+0x98`. `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` le
  remplit depuis `context+0x2c` ;
* **le `.ctor`** = `BaseEffect(AbilityOrEffect(TriggeredAbilityType 0x5f6 = 1526 PurgeResponse),
  hasAutomaticActivation = 1)` — ici la surcharge appelée est `set_TriggeredAbility`. Le même entier
  ne circule pas : `1526` est la source, `1009` est le déclencheur comparé.

L'autre moitié du passif — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
PurgeResponse_ActiveOverwatchAbility` (`CreateTrigger` = `On(0x17) & <DSLTriggers+0x28> &
AmountIsGreaterThanZero(Count(HeroUnits(UnitsFromFaction(AdjacentFriends(Owner, incl. self, 3),
0x14))))`, `CreateBehaviour` = `ActivateEffect(Owner, 0x3f1)`) — **arme l'overwatch du Steeljack**
et ne touche pas au canal des coups. Hors périmètre, non portée.

### 1.1 Le décompilé est PLUS LARGE que la description

i2 (`Abilities/PurgeResponse_CurrentLevelDescription`) : « While Overwatching, **the Ironkin
Steeljack's** attacks ignore hit reductions ». Le trigger, lui, ne compare que l'AbilityOrEffect
déclenchante de l'attaque : tant qu'**une** instance active de `1538` existe **n'importe où** sur le
board — y compris dans le camp adverse de l'attaquant — **toute** attaque d'overwatch ignore les
réductions de coups. Le décompilé fait foi ; la description ne l'implémente pas.

C'est cette forme qui est **mesurée** ici, pas déduite : dans le bras `ON`, le porteur est mon
summon et l'attaquant est l'overwatcher **ennemi** (§4).

## 2. Ce qui a été élargi, et jusqu'où

`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses` **ne prend aucun argument de
portée** : elle énumère la liste globale des entités-effet, filtre sur `EffectComponent+0x5c`
(`IsActive`) et sur `targets.Count > 0`, puis rend `(effet, cibles)`. La boucle BLOCK de
`GetAttackHits` itère `effets × cibles` en écrivant `AbilityEntities+0x18 (Owner) <- la cible de
l'effet` avant chaque appel.

Le port balayait, lui, les seuls effets de l'**ATTAQUANT** — ce qui *rendait* le `get_OwnerIsCaster`
de `1117`. L'alignement tient en deux gestes solidaires :

| | avant | après |
|---|---|---|
| univers du balayage | effets de l'attaquant | **tout le board** (`entities.effects.board_effect_carriers` : attaquant + cible + `aura_sources`) |
| `get_OwnerIsCaster` de `1117` | rendu par le canal | **dans sa classe** (`owner_id` vs `att_id`, idiome `GravitonRifle_ExtraPierceEffect`) |

Le second geste n'est pas cosmétique : sans lui, l'élargissement rendrait `1117` **permissif** (un
Maugan Ra spectateur bloquerait les réductions d'un tiers). Verrouillé par
`test_widened_sweep_offline` (branche (b)) et par le nouvel assert de
`test_gates_are_tristate_offline`.

**Choix de portée : le board entier, pas un sur-ensemble plus étroit.** Le trigger de
`PurgeResponse` n'a aucun nœud positionnel ni d'identité — un univers plus étroit serait faux pour
un porteur posté à l'autre bout de la carte. Les trois collections que la formule tient déjà
**recouvrent** cet univers (les `aura_sources` sont toutes les unités vivantes ≠ cible), donc
l'alignement ne coûte aucune collecte supplémentaire.

⚠ **Non couvert** : les effets portés par une **tuile**. `GetActiveEffectsWithBonuses` énumère des
entités-effet dont les cibles peuvent être des tuiles ; le port n'a d'`aura_sources` que pour les
unités. Aucun des deux implémenteurs n'est tile-borne — le trou est documenté, pas comblé.

## 3. Le port

| natif | port |
|---|---|
| `PurgeResponseEffect$$CreateBlockHitReductionTrigger` | `PurgeResponseEffect.block_hits_reduction` (`entities/effects/loki/votann.py`) |
| la boucle `effets × cibles` de `GetAttackHits` | `entities.effects.block_hits_reduction_from_effects(carriers, att_ctx)` |
| `EffectsQuery$$GetActiveEffectsWithBonuses` | `entities.effects.board_effect_carriers` |
| `AbilityEntities+0x18` (`Owner`) | la clé `owner_id`, posée **par porteur** par l'agrégateur |
| `AbilityEntities+0x98` (`triggerAbilityOrEffect`) | la clé `trigger_ability_type` du board de coups (`runner/damage_model.py::build_hits_board`) |

Le producteur unique de `trigger_ability_type` sur l'axe COUPS est le vecteur **OVERWATCH** :
`triggers/effect_triggers.py` passe déjà `triggering_ability=OVERWATCH_AUTO_ATTACK` à
`AttackDamageOperation.execute`, qui le thread désormais jusqu'à `build_hits_board`. La re-entrée
`#120bis` (cible remplacée) le conserve — sans quoi un tir d'overwatch re-ciblé perdrait **en
silence** et sa `DamageSource` et ce nœud.

⚠ Le port **collapse** les trois `Nullable` de l'`AbilityOrEffect` en un entier — comme le fait
déjà le canal DÉGÂT (`attacker_modifiers`, `trigger_ability_type`, #47). Exact tant que le seul
producteur est l'overwatch (EffectType 1009) ; un futur producteur qui y poserait un
`ActiveAbilityType 1009` exigerait de matérialiser le slot. Épinglé par
`test_purge_response_gates_offline`.

**Face PRÉDICTION** : la clé est absente (une prédiction d'attaque normale n'a pas de déclencheur),
donc le nœud est FAUX — ce qui est le mirror exact du `Nullable` vide du natif. Aucun gap de canal.

## 4. La voie SUMMON, et le carré mesuré

Aucune unité `LeaguesOfVotann` n'est dans le pool, et le porteur est un **summon** : on injecte
l'**invocateur** (`votanMemnyr`, `catalog_inject`) et on lui fait caster `IronkinSteeljack` (1219)
sur un hex libre **adjacent** (case-92 §5 — un hex non adjacent rend `ok:true / mutated:false /
spawned:0`). Le summon se projette sous le `visualId` **`votanNpc2Steeljack`** (piège #427), et
arrive avec `PurgeResponse` (1538) **actif** — vérifié live.

Montage : le porteur est **mon** summon, l'attaquant est l'**ennemi** overwatcher, la cible est
**mon** mover. Le porteur n'est donc ni l'attaquant ni la cible, et il est dans l'autre camp que
l'attaquant — un flag gaté `get_OwnerIsCaster` ne pourrait pas s'armer. **Le compte de la salve est
à lui seul la mesure de l'absence de ce nœud.**

Choix des trois rôles, chacun payé par une mesure fausse évitée (gardé par
`test_montage_units_are_the_right_ones`) :

* **overwatcher** — trait `Overwatch` + arme à distance multi-coups. `eldarMauganRa` est **écarté**
  alors qu'il coche les mêmes cases : il porte `1117`, dont le canal est le même — il bloquerait
  tout seul ;
* **mover** — trait `Camouflage` (→ `Camouflage_HitReduction`, `OwnerIsTarget & IsRangedAttack`).
  `tyranDeathleaper`, `astarCyrus` et `thousSekhetar` sont **écartés** : ils portent `Infiltrate`,
  qui est précisément l'immunité du mover à l'overwatch
  (`Overwatch_AutoAttackEffect$$AdditionalTriggers` = `NOT HasEffect(mover, 0x418 = 1048)`) → aucune
  salve. Reste `tauMarksman` ;
* **parking** — l'invocateur (`PredictiveGuidance` : +1 coup aux amis Votann contre un ennemi marqué
  à 2 hexes) et le summon lui-même (`BigTarget_AdjacentEffect` : −1 coup ranged sur ses alliés
  ring-1) sont **garés à 6 hexes**. Le summon porte le trait `Summon`, donc le natif le fait **jouer
  tout seul** au début de chaque tour de son équipe (`PlayAutomaticUnits`, case-291) : il faut le
  **re-garer après** le cycle de tour — mesuré C1_25/31337, sans ce re-parking le bras `ON` est
  refusé (`d=1`).

### 4.1 Le carré

`probe_366_r1_blockhits_purgeresponse.py`. Criterion = le **nombre de coups** de la salve
d'overwatch (le trigger est nu : `PurgeResponse` n'a aucune magnitude).

| couple | bras | réduction | LIVE | OFFLINE | mutations → rejeu |
|---|---|---|---|---|---|
| MC1_67/777 · `necroDestroyer` (6 coups, d=2) | **ON** | Camouflage −1 | n=**6** `[1766, 1763, 1785, 1633, 1721, 1880]` | n=**6** | `NOCHANNEL` / `NOWIDEN` / `NOTRIGGER` → n=**5** |
| MC1_67/777 · `necroDestroyer` | **OFF** | Camouflage −1 | n=**5** | n=**5** | — (contrôle live) |
| C1_25/31337 · `admecDestroyer` (4 coups, d=3) | **ON** | Camouflage −2 | n=**4** `[2860, 2552, 2676, 2711]` | n=**4**, **bit-exact** | `NOCHANNEL` / `NOWIDEN` / `NOTRIGGER` → n=**2** |
| C1_25/31337 · `admecDestroyer` | **OFF** | Camouflage −2 | n=**2** `[2860, 2552]` | n=**2**, **bit-exact** | — (contrôle live) |

Les deux couples changent **quatre** choses à la fois (board, seed, overwatcher, branche de
`Camouflage`) — le second exerce la branche `AverageDistance > 2` (−2), donc un delta de 2.

Les trois mutations :

* **`NOCHANNEL`** — inscription retirée d'`EFFECT_CLASSES` : c'est la **vue rouge d'avant le fix** ;
* **`NOWIDEN`** — `board_effect_carriers` remplacée par l'univers d'avant cette tranche (les seuls
  effets de l'attaquant). **C'est la garde de l'élargissement** : elle rougit si le balayage se
  re-rétrécit ;
* **`NOTRIGGER`** — `trigger_ability_type` forcée à `None`. Ce gate est **binaire** (pas tri-état) :
  forcer et retirer coïncident, et le désarmement va bien dans le sens qui efface le blocage. Le
  probe le **vérifie** plutôt que de le supposer (#422 : sur une contre-épreuve, VERT est le
  résultat suspect).

Cliquet : `tests/engine/runner/test_purge_response_blockhits_live.py` — **10 passed**
(4 structurels offline + 6 live).

## 5. Ce qui n'est PAS couvert

* **Les VALEURS du couple `necroDestroyer` divergent (≈ ×2)** — résidu **préexistant et nommé** :
  `InescapableDeath` (« Imospekh's ranged attacks each deal +655 Damage per hit **when triggered by
  Overwatch** »), effet `1018 InescapableDeath_Effect`, **non inscrit** au registre. Il ne touche
  que la valeur, jamais le compte ; le couple `admecDestroyer` (sans bonus non porté) est
  **bit-exact jusqu'à la valeur** des deux côtés, ce qui borne le résidu. La seconde moitié
  d'`InescapableDeath` (« retaining 1 fewer hits ») est un canal de COUPS, mais elle est
  conditionnée à un **kill** par l'overwatch — inerte ici (PV gonflés, aucun mort).
* **Le vecteur ABILITY ne thread pas `trigger_ability_type`** dans le board de coups (seul le
  vecteur NORMAL le fait). Nativement le champ est renseigné pour un cast ; côté port, le porter
  serait sans effet sur ce canal (le littéral de `PurgeResponse` est un `EffectType`, qu'aucune
  ability ne peut valoir) et rouvrirait le risque de collision d'enum. Écart volontaire, borné.
* **`PurgeResponse_ActiveOverwatchAbility` n'est pas portée** : l'overwatch du Steeljack lui-même
  n'est donc jamais armé côté port. Sans conséquence sur ce canal (le trigger ne lit pas le
  porteur), mais le Steeljack **n'overwatche pas** en simulation.
* **La face PRÉDICTION n'est pas confrontée live** — elle est correcte par construction (clé
  absente → nœud faux), mais aucun bras ne lit une prédiction.
* **Les effets de TUILE** restent hors de l'univers du balayage (§2).
* **Le porteur npc `votanNpc2Steeljack`** n'est pas confronté en tant que tel : c'est le `visualId`
  sous lequel le summon se projette, donc le même code est exercé, mais aucun montage ne le fait
  entrer comme unité npc autonome.

## 6. Résidus

* **`#366-r1-blockhits-purgeresponse` est CLOS** — les deux implémenteurs natifs de
  `BlockHitsReduction` sont désormais portés et confrontés live. Le canal n'a plus d'implémenteur
  inconnu : `search_symbols_by_name("CreateBlockHitReductionTrigger")` en rend **exactement deux**.
* **`InescapableDeath` (1018)** — résidu nommé ci-dessus, hors périmètre : deux canaux (+dégât par
  coup sous overwatch, −1 coup à la salve suivante après un kill sous overwatch), aucun porté.
* **`PurgeResponse_ActiveOverwatchAbility`** — `CreateTrigger` / `CreateBehaviour` lus (§1), non
  portés : l'auto-activation de l'overwatch du Steeljack quand un héros Votann est à 3 hexes.
