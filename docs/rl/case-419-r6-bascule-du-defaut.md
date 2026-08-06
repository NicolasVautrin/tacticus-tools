# `#419-r6` — basculer le défaut à « équiper », et ce que la bascule a rendu VISIBLE

## 1. Le geste, et pourquoi il n'est pas le travail

`_EQUIP_ITEMS_PAR_DEFAUT = True` (`scripts/python/rl_collect_batch.py`). Une ligne.

Le travail est ailleurs : #419-r5 avait laissé trois fichiers qui se dégradaient, et le premier
d'entre eux portait un **écart natif-port de 904 PV non diagnostiqué**. Le diagnostic est ce qui
suit, et sa conclusion renverse la lecture qu'on en avait : **la bascule n'a créé aucun de ces
défauts — elle les a rendus visibles.**

## 2. Les 904 PV : ni l'état de départ, ni le calcul du coup

Le critère était déjà posé par #419-r5 : `live_ph == off_ph == [5543]`, donc l'écart ne porte pas
sur le montant du coup. Restaient deux familles, aux conséquences disjointes — **(A)** l'état de
départ diverge, **(B)** le natif applique quelque chose de plus.

**(A) tombe par la mesure.** Les PV de la cible au départ valent **7629** sur les *quatre* canaux :
`observeBattle`, `combatSnapshot`, `decisionView`, et le port (`load_state` →
`HealthComponent.hp`). Aucune divergence de publication ni de lecture.

**(B) est vraie, et à deux étages.** Le bilan par soustraction les sépare :

```
hp avant                        7629
  - 5543   coup de l'ability    (Active_Ability_Type = 1043)
  - 1808   paquet SANS ability  (DamageProfileType 0, Attacker_Id = le caster)
  = 278    <- etat natif POST-CAST, publie dans les tags de ce dernier paquet
  + 904    turn-start adverse
  = 1182   <- ce que `applyAction` rend, et ce que le test lisait
port                            2086   (= 7629 - 5543, rien d'autre)
```

### 2.1 Le paquet de 1808 est le KNOCKBACK du push bloqué — et il est PORTÉ

`ThunderousAssault` pousse la cible d'un hex. Push **bloqué** ⇒
`IdunBattle.Operations.DisplaceUnitOperation$$ApplyKnockbackTo`, dont le montant est
`IdunBattle.Core.Services.DamageCalculations$$CalculateKnockbackDamage` =
`ceil(maxHealth × BC.Damage.KnockbackPercentage/100)`. Mesuré : `ceil(9037 × 20 %)` = **1808**,
au chiffre près. Le port porte ce mécanisme depuis #47 (`_apply_knockback_to`).

**Ce qui manquait était la GÉOMÉTRIE.** Le test appelait `load_state(dv, ob, snap)` **sans
`board=`** ; sans board, les feuilles géométriques de l'arbre DSL (`PushUnit`, la charge
`MoveUnit`) sont des **no-op silencieuses**, donc aucun push, donc aucun knockback. C'est le vice
de #63 (le bonus d'ÉLÉVATION perdu faute de `state.board`), et la parade est la même — celle que
`_combat_replay._do_replay` applique déjà.

Une fois le board passé, les deux côtés **s'accordent d'abord sur le déplacement** (ni le caster ni
la cible ne bougent : push bloqué des deux côtés), puis sur les PV : le port rend **278**, exactement
l'état natif post-cast.

### 2.2 Le +904 est un turn-start, donc un autre INSTANT

Le roster est 1v1 : le cast termine le tour du joueur, et `applyAction` rend un état qui a **déjà
traversé le turn-start adverse**. Le trait `LivingMetal` de `necroOverlord` (i2 : « Regenerates
{hpPct}% of its max Health at the start of the players' turn », `livingMetalHp = 10`) y régénère
`10 % × 9037` = **904**.

Comparer cet état à un port qui n'a simulé aucun tour, c'est comparer deux instants. L'oracle des PV
se lit donc désormais dans les **tags du dernier paquet de dégât** (`UnitStats_RemainingHealth`),
qui datent d'avant la bascule de tour — pas dans `res.units[].hp`.

## 3. Pourquoi c'était invisible AVANT la bascule — et c'est le point

Sans items, la `FixedArmor` de la cible vaut **1110** au lieu de 1764. Le coup principal fait donc
**6700** au lieu de 5543, le knockback **achève** la cible, `live_after == 0`, et la garde
`if live_after is not None and live_after > 0` **saute l'assertion PV**.

Le trou était là depuis toujours. Ce n'est pas la bascule qui l'a créé : c'est elle qui a fait
**survivre la cible**, donc exécuter l'assertion. Un test dont la garde « cible morte » sert de
silencieux ne valide ses PV que par accident.

## 4. Les trois réparations, arbitrées par fichier

| fichier | arbitrage | pourquoi | avant → après |
|---|---|---|---|
| `test_damage_ability_live` | **board + oracle post-cast + `NO_NOISE`** | son assertion PV mesure TOUT ce que le cast retire, donc elle doit voir le knockback (board) et rien de plus (instant) | 1 failed → **1 passed** |
| `test_damage_normal_armored_live` | **neutraliser** | l'axe est l'ORDRE reduce-then-roll, que seul le per-coup discrimine ; un crit multiplie APRÈS ce point — il masquerait le discriminant, et le fichier ne sait qu'en skipper | 3 skipped → **3 passed** |
| `test_damage_catalog_live` | **neutraliser** | l'en-tête du fichier dit déjà que « les axes crit/block ont leurs tests dédiés » : un crit y est hors axe par construction | 1 passed + 4 skipped → **5 passed** |

`NO_NOISE` porte sur les **quatre** faces (`--crit`/`--block-player` n'épinglent que les p-units,
`--crit-target`/`--block-target` que les a-units) — c'est le remède-type établi par #419-r5.

⚠ **Neutraliser n'est pas « faire taire »**, et la différence est ce qui sépare cette tranche du
régime qu'elle supprime : le régime dégénéré était **global, silencieux et non déclaré** ; ici le
choix est **local, écrit au build, et motivé par l'axe du fichier**. Aucun des trois n'a été
neutralisé avant que la cause de sa dégradation soit nommée.

## 5. Le périmètre, DÉRIVÉ et non hérité

Les 8 fichiers de #419-r5 sont tous des fichiers de dégât. La bascule change l'état de **tout runner
construit**. `probe_419r6_perimetre_bascule.py` dérive le périmètre de l'arbre de tests, par
**trois canaux d'exposition distincts** — le troisième étant celui qu'un balayage « cherche le mot
crit » raterait :

* **(A) coup propre exigé** — le fichier filtre/skippe sur `did_crit`/`DidCrit`/`mightCrit`. Risque :
  il devient **inerte** (`passed == 0 and skipped > 0`, garde #455).
* **(B) déjà neutralisé au build** — immunisé par construction.
* **(C) valeur en dur** — `assert x == <entier > 100>`. Équiper change `FixedArmor` sur **49** unités
  sur 106 et `Health` sur **4** (mesure #419-r5 étape 3) : ce canal n'a rien à voir avec le crit.

Comptes re-dérivés (`python scripts/python/probe_419r6_perimetre_bascule.py`) — **à re-dériver, pas
à citer** :

```
fichiers de test visites : 700   | offline 313 | LIVE 387
  (B) deja neutralises   :  34
  (A) coup propre, nus   :  38
      indifferents       : 315
  (C) valeur en dur      :  25
```

**Ce que le balayage ne visite pas**, et il le dit lui-même plutôt que de rendre un zéro : les
probes (`probe_*.py`), ce qu'un test atteint via une fixture d'un autre paquet, et la face DÉCISION
hors tests (`engine_validate.py`, `predict_sweep.py`), qui monte pourtant des runners.

## 6. Ce qui a été JOUÉ

<!-- MESURE-38 -->

## 7. Résidus NOMMÉS

* **`#419-r6-r1` — le périmètre au-delà des 38 n'est pas joué.** Les **315** fichiers live
  « indifférents aux deux marqueurs » et les **25** porteurs d'une valeur en dur n'ont pas été
  mesurés dans les deux régimes ; la face DÉCISION (`engine_validate.py`, `predict_sweep.py`) non
  plus. L'extrapolation n'est pas une mesure, et le canal (C) est précisément celui dont la
  signature (un scalaire figé qui rougit) ne ressemble pas à celle du canal (A).
* **`#419-r6-r2` — `ChampionOfTheFeast` (`TriggeredAbilityType` 1086) n'est porté par aucun des
  quatre registres de trigger** (`ABILITY_TRIGGERS` 38, `ACTIVE_ABILITY_TRIGGERS` 2,
  `EFFECT_TRIGGERS` 32, `TRAIT_TRIGGERS` 11). i2 : « After moving, deals {nrOfHits}x
  {minDmg}-{maxDmg} Power Damage to an adjacent enemy and reduces this enemy's Armour ». Il frappe
  à chaque déplacement du caster : sur le montage de `test_damage_ability_live` il a retiré **1408**
  PV à la cible et réduit son armure de **2761 → 1764** *pendant l'approche*. Sans effet sur ce
  test (l'état est capturé après l'approche, et les deux côtés lisent le même snapshot), mais c'est
  une divergence d'état réelle en self-play. L'audit `combat-ability-coverage.md` ne le voit pas :
  il ne couvre que les `activeAbilities`.
* **La face DÉCISION reste en régime dégénéré non re-mesuré.** `MightCrit@+0xB1` =
  `CouldCrit(attaquant)` valait `False` sur *toutes* les prédictions ; la bascule l'ouvre, et
  `engine_agreement_stages` / les tests d'overkill n'ont pas été rejoués ici. C'est le point le plus
  gros de `#419-r6-r1`.

## 8. Ce qui n'est PAS couvert

* **Un seul rank (17) et un seul board (`MC1_67`)** pour tout le diagnostic des 904 PV.
* **Le knockback n'est confronté que dans son régime BLOQUÉ.** Le push réussi (la cible bouge, aucun
  knockback) n'est pas exercé par ce montage — les deux côtés s'accordent ici sur « bloqué », ce qui
  est un accord, pas une couverture des deux branches.
* **Le choix BiS n'est toujours pas confronté au choix du jeu** (résidu ouvert par #419-r5, inchangé).
* **Le block n'a toujours pas d'étage live dédié** (idem).
