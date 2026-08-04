# case-589-r1-r1 — `EmpyricAmbush` : le seul seuil qui bascule, porté ET confronté

`#589-r1-r1`. `case-589-r1` avait établi que sur les six consommateurs de
`IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn`, un seul a un seuil au-dessus de la
borne saturante (`min(n_G, n_C) >= 2`) : `EmpyricAmbushEffect$$IsValidAttackForBuff`, `movement`
= **4**. Il n'était ni porté ni confronté. Les deux sont faits.

## 1. La question binaire, et sa réponse mesurée

> « À quelle valeur de `TilesMovedThisTurn` du **caster de l'attaque** le natif bascule-t-il
> `IsValidAttackForBuff`, et le port fait-il pareil ? »

**À 4, des deux côtés, exactement.** `--crit 100,700` (tous les coups critent des deux côtés, donc
ce qui bouge est `extraCritDmg` — écart DÉTERMINISTE, aucun tirage) :

| régime | `n` natif | LIVE | port | `NOCHANNEL` | buff |
|---|---|---|---|---|---|
| `Fly` (`blackHaarken`) | 2 | `[1802, 1940, 2066, 1694]` | == | inchangé | non |
| `Fly` | 3 | `[1802, 1940, 2066, 1694]` | == | inchangé | non |
| `Fly` | **4** | `[2367, 3355, 3247, 2841]` | == | `[1802, 1940, 2066, 1694]` | **OUI** |
| `Fly` | 5 | `[2367, 3355, 3247, 2841]` | == | `[1802, 1940, 2066, 1694]` | OUI |
| `TeleportStrike(+Fly)` (`bloodIntercessor`) | 3 | `[5621]` | == | inchangé | non |
| `TeleportStrike(+Fly)` | **4** | `[7886]` | == | `[5621]` | **OUI** |
| SUJET (porteur à 4, attaquant à 0) | 0 | `[1802, 1940, 2066, 1694]` | == | inchangé | non |

**7 mesures, 7 accords, 7 contre-épreuves conformes.** `n = 4` et `n = 5` rendent la MÊME valeur :
c'est un seuil, pas une pente — ce qui le sépare de `ModifiedExoarmour`, linéaire.

⚠ **L'accord n'est pas dégénéré, et c'est `NOCHANNEL` qui le dit** : retirer l'effet
d'`EFFECT_CLASSES` (il retombe sur `BaseEffect`, deux canaux à `None`) ramène, à `n >= 4`,
**exactement** les valeurs de `n < 4`. Sans ce témoin, « ça concorde » ne vaudrait rien.

## 2. L'arbre natif — SEPT nœuds, et le sujet n'est PAS le porteur

`IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$IsValidAttackForBuff` :

    AreEnemies( Caster@DSLSelectors+0x48, Target@+0x60, 0 = ByCurrentTeam )
  & (   HasFaction( Caster, 8 = Aeldari, 3 )
      | AmountIsEqualOrGreater( TilesMovedThisTurn(Caster),
                                Direct(GetNumberConstant(0x51 = movement)) ) )
  & (   AreFriends( Caster, EffectSource(<+0x38>), 0, anyEntity: false )
      & op_LogicalNot( AreEqual( Caster, EffectSource ) )
      & HasTrait( Caster, 0x10 = Hero ) )

Le sujet est `<+0x48>` = le **caster de l'attaque**, là où trois autres call-sites de
`TilesMovedThisTurn` ont pour sujet `<+0x30>` = Owner. **Confronté, pas seulement lu** (ligne
SUJET du tableau) : le porteur marqué parcourt 4 tuiles, l'attaquant 0, et le natif n'applique
RIEN. Si le sujet était l'Owner, le buff se serait appliqué.

Résolutions relues d'`enums.tsv` : `UnitFaction 8 = Aeldari`, `UnitTrait 0x10 = Hero`,
`AbilityConstantType 0x51 = movement`, `AbilityVariableType 0x41/0x42 = extraCritChance/extraCritDmg`,
`EffectType 0x62a = 1578`. La valeur du seuil est **relue du gameconfig**, jamais codée en dur.

**Config lue = l'ability ACTIVE 1232**, relue byte à byte : `mov edx, 0x4d0` + la surcharge
d'`AbilityOrEffect$$op_Implicit` qui appelle `set_ActiveAbility` (les surcharges sont homonymes,
elles se tranchent par adresse). L'effet est posé sur la **cible**, source = Lhykhis, `turns =
<DSLFormulas+0x20>` = `Direct(1)` — **un tour**.

## 3. Ce que ce port a dû ouvrir : le balayage des canaux CRIT

Les deux canaux (`DamagePrediction$$GetCritChanceBonusFromEffects` / `$$GetCritDamageBonusFromEffects`)
construisent leur `AbilityEntities` en `(attacker, attacker, defender)` **puis écrasent
`AbilityEntities+0x18` (`Owner`) par le porteur de l'effet à chaque itération** — la même boucle
`effets × cibles` que `GetAttackHits` (relue par `case-366-r1-blockhits-purgeresponse`). Le porteur
n'est donc pas forcément l'attaquant, et `EmpyricAmbush` est le **premier implémenteur porté qui
vit sur la CIBLE** (`get_OwnerIsTarget`).

Deux gestes solidaires, exactement comme #422 sur l'axe COUPS :

| | avant | après |
|---|---|---|
| univers du balayage | effets de l'ATTAQUANT | **tout le board** (`board_effect_carriers`) |
| `get_OwnerIsCaster` de 1115 / 1116 / 1222 / `SagaOfTheWarriorBorn_Owner` | rendu par le canal | **dans leurs classes** (foyer `effects.base.owner_is_caster`) |

Le second n'est pas cosmétique : sans lui, l'élargissement rendrait ces quatre effets
**PERMISSIFS** (un porteur spectateur bufferait un tiers). Les deux résidus de portée que les
docstrings de ces canaux nommaient depuis #366-r1 sont donc fermés.

## 4. Ce que la non-régression a trouvé

Les quatre tests des canaux crit ont rougi, et **aucun n'accusait le port** :

* trois fichiers × un test OFFLINE — leur `att_ctx` ne portait pas d'identité, puisque le nœud
  était rendu par le canal. Mis à jour à sa nouvelle place native ;
* `test_ischarging_saga_crit_live.py` — son mutant `always` fabriquait un contexte MINIMAL
  (`{"is_charging": True}`), que le nouveau nœud referme : **la mutation a cessé de mordre, et le
  test l'a signalé**. C'est le garde-fou « sur une contre-épreuve, VERT est le résultat suspect »
  qui a fonctionné. Le mutant préserve désormais le contexte (`{**att_ctx, "is_charging": True}`).

Contre-épreuve jouée avant de toucher quoi que ce soit : `engine/` ramené à `origin/master`, les
quatre tests LIVE de Saga **passent** — c'était donc bien cette tranche, pas un rot préexistant.

## 5. Les gardes

* `tests/engine/runner/test_empyric_ambush_threshold_live.py` — **5 passed** : les deux régimes,
  le bras SUJET, et la garde de registre. Le montage est **importé** du probe, pas retranscrit.
* `tests/engine/entities/pathfinding/test_589r1_tiles_moved_consumers_offline.py` — **8 passed**.
  `EmpyricAmbush` **sort** de `test_aucun_trigger_a_SEUIL_n_est_porte` (son seuil est désormais
  exercé ET confronté — c'est ce que ce cran réclamait) et gagne
  `test_le_seuil_porte_d_EmpyricAmbush_bascule_a_movement`, qui relit le seuil du gameconfig.
* `probe_589r1r1_empyric_ambush_live.py` — la mesure, avec ses gardes de régime : un attaquant
  **Aeldari** ou **sans `Hero`** est REFUSÉ d'entrée (le premier sature le `op_BitwiseOr`, le
  second ferme tout : les deux rendraient un vert qui ne mesure rien).

## 6. Reproduction

    python probe_589r1r1_empyric_ambush_live.py --dist 2,3,4,5
    python probe_589r1r1_empyric_ambush_live.py --attacker bloodIntercessor --dist 3,4
    python probe_589r1r1_empyric_ambush_live.py --dist 4 --sujet
    python -m pytest tests/engine/runner/test_empyric_ambush_threshold_live.py
    python -m pytest tests/engine/entities/pathfinding/test_589r1_tiles_moved_consumers_offline.py

## 7. Ce qui n'est PAS couvert

* **`eldarLhykhis` n'est PAS au pool** — la fiche #589-r1-r1 l'affirmait, `rl_duel build
  --list-pool` la dément et `catalog_inject --missing` la liste parmi les 21 unités `lineup` hors
  catalogue. Elle s'**injecte** (`write_augmented_seed_bc`), donc elle reste confrontable : c'est
  une correction de la fiche, pas une limite.
* **`EmpyricAmbushAbility` (1232) n'est pas portée.** Ce sont l'EFFET et son gate qui le sont. La
  POSE côté port n'existe donc pas : en confrontation, l'effet arrive dans l'état du port par la
  capture live (`EffectsState.seed` → `EffectFactory`). Un replay-diff qui ferait caster Lhykhis
  **par le port** divergerait — l'ability est toujours un no-op combat.
* **`EmpyricAmbush_AnyMove` (1580) et `EmpyricAmbush_Reset` (1555) ne sont pas portés.** Lus :
  `AnyMoveAbility` = `On(PreUnitMove) & OwnerIsActor` → `AddEffect(1580, targets = Owner, turns
  = 0)`, retiré par `On(UnitAfterMove) & OwnerIsActor` ; `ResetAbility` = `On(UnitDefeated) &
  OwnerIsActor & AreEnemies(Owner, Target) & IsNormalAttack & IsMeleeAttack`. Aucun des deux ne
  lit `TilesMovedThisTurn` — hors périmètre de cette tranche, mais non portés.
* **Le régime `Walk` n'est pas joué**, et c'est délibéré : mesuré INERTE pour #589 (0 basculement
  sur 3906 couples × 2 boards), il ne discrimine rien sur l'axe qui nous occupe.
* **Un seul board (`MC1_67`) et un seul seed (777)** pour la confrontation du seuil. Le seuil ne
  dépend pas de la géométrie — c'est le COMPTEUR qui en dépend, et lui a été généralisé sur deux
  boards par `case-589-r1`. Mais aucune mesure de CE cas n'a été rejouée sur un board à `Bridge`,
  donc le couple « compteur rebranché × seuil franchi » n'est pas confronté **de bout en bout**.
* **`AmuletOfTheVoidwyrm_CritDamageReduction`** (`ForSubtraction(get_OwnerIsTarget, …)`, sur la
  CIBLE) reste NON PORTÉ. L'élargissement du balayage le rend désormais **atteignable** ; il ne le
  porte pas. C'est l'axe RÉDUCTION du canal crit-dégât, gisement séparé.
* **Les effets de TUILE** restent hors de l'univers du balayage, comme sur l'axe COUPS.
* **La face PRÉDICTION** n'est pas touchée : `services/damage_prediction.py` n'appelle pas
  `crit_chance_bonus_from_effects` (gap préexistant du canal, `case-366-r1` §6.4), donc le
  +extraCritChance de 1578 n'entre pas dans la prédiction de dégât.
