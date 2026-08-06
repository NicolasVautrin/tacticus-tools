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

⚠ **Ces comptes sont ceux d'AVANT les réparations de cette tranche.** Les 11 fichiers réparés ici
posent désormais leur `NO_NOISE`, donc ils ont migré de (A) vers (B) : re-jouer le probe rend
aujourd'hui **44** en (B) et **28** en (A). C'est la trajectoire attendue, pas une divergence — et
c'est aussi pourquoi ces chiffres se re-dérivent au lieu de se citer.

**Ce que le balayage ne visite pas**, et il le dit lui-même plutôt que de rendre un zéro : les
probes (`probe_*.py`), ce qu'un test atteint via une fixture d'un autre paquet, et la face DÉCISION
hors tests (`engine_validate.py`, `predict_sweep.py`), qui monte pourtant des runners.

## 6. Ce qui a été JOUÉ — et pourquoi le témoin n'est pas optionnel

Les **38** fichiers du canal (A) ont été joués dans le régime NOUVEAU, puis les seuls **dégradés**
ont été rejoués en `TACTICUS_BIS_ITEMS=0`. Ce second passage n'est pas une formalité : le dépôt
porte un taux de rouge non nul sur les tests live (inventaire #462), donc **un rouge trouvé après
la bascule n'est pas ipso facto un rouge causé par elle**. Sans témoin, la tranche s'attribuerait
des défauts qu'elle n'a pas créés — et, pire, en réparerait qui ne sont pas les siens.

### 6.1 Les 38 du canal (A), régime NOUVEAU

**23 vert, 7 INERTE, 8 ROUGE.**

### 6.2 Les 15 dégradés, rejoués en `TACTICUS_BIS_ITEMS=0` — la causalité

| verdict | n | fichiers |
|---|---|---|
| **CAUSÉS** par la bascule (verts dans l'ancien régime) | **11** | 7 inertes + 4 rouges, listés ci-dessous |
| **PRÉEXISTANTS** (identiques dans les deux régimes) | **4** | `test_additional_hits_after_hit_maybe_live` (7 failed), `test_additional_hits_roll_order_live` (5), `test_additional_hits_rounding_live` (3), `test_psychic_stalk_extra_attack_damage_live` (2) |

Les 4 préexistants **ne sont pas touchés** : ce ne sont pas les défauts de cette tranche, et les
« réparer » à l'aveugle aurait masqué leur cause réelle. Ils sont signalés en résidu.

### 6.3 Les 11 réparations, arbitrées sur l'AXE de chaque fichier

| fichier | avant | arbitrage | après |
|---|---|---|---|
| `test_attack_nature_normal_like_live` | 0p/2s | neutraliser — l'axe est la NATURE du coup, le crit s'applique après le gate | 2p |
| `test_damage_crushingclaws_live` | 0p/1s | neutraliser — per-coup d'ability, l'axe crit a son fichier | 1p |
| `test_great_frost_axe_live` | 0p/1s | neutraliser — dégât bit-exact par coup | 1p |
| `test_heavy_weapon_moved_gate_live` | 0p/2s | neutraliser — le discriminant est le rapport entre deux bras | 2p |
| `test_mkxgravis_combat_live` | 0p/1s | neutraliser — le natif **exempte** le crit de la double-armure : un coup crité DÉSACTIVE le mécanisme mesuré | 1p |
| `test_psyker_splash_live` | 0p/1s | neutraliser — montant PLAT, sans variance | 1p |
| `test_sense_of_stone_live` | 0p/2s | neutraliser — 1169 doit rester le SEUL modificateur défenseur | 2p |
| `test_guardian_organism_combat_live` | 1p/1f | neutraliser — le discriminant est un FLAT constant | 2p |
| `test_overkill_amount_live` | 0p/4f | neutraliser — la borne se lit sur `sum(live_ph) == hp_before`, montants nus | 4p |
| `test_prioritised_efficiency_live` | 8p/2f | neutraliser — le discriminant est l'écart POST/PRE par coup | 10p |
| `test_visions_of_heresy_pierce_live` | 3p/1f | neutraliser les DEUX faces manquantes de `probe_366` | 4p |

**11 sur 11 réparés**, et chaque compte après réparation est **identique à celui du témoin** — le
critère n'est donc pas « c'est vert », c'est « le fichier mesure exactement ce qu'il mesurait
avant que le canal s'ouvre ».

⚠ **Deux montages posaient DÉJÀ `--crit` et `--block-target`, mais pas les deux autres faces** —
`probe_366_visions_of_heresy.build_args` et (côté préexistants) `_pierce_floor_regime`. Deux faces
sur quatre suffisaient **par accident** tant que le canal était muet ; c'est précisément la
signature du régime dégénéré, et elle survit à un montage qui *croit* neutraliser.

### 6.4 Le canal (C), que le canal (A) ne couvrait pas

Sur les **25** fichiers du canal (C), **23** ne sont pas déjà dans (A) — donc le canal (A) seul
aurait laissé ces 23 entièrement non mesurés. C'est la justification empirique du troisième canal :
sans lui, **3 fichiers cassés par la bascule seraient partis en production sans être vus**.

Joués en régime NOUVEAU : **17 vert, 6 ROUGE**. Témoin sur les 6 → **3 CAUSÉS, 3 PRÉEXISTANTS**.

| fichier | verdict | cause mesurée | réparation |
|---|---|---|---|
| `test_black_legion_1029_1020_live` | **causé** | un coup live à **5200** pour une borne haute du port de **2592** — un crit sort de la plage par construction | neutraliser (`_mk_runner`) |
| `test_exemplar_of_the_kauyon_hits_live` | **causé** | les 2 coups surnuméraires sont une cellule **dégénérée** (`min == max`, zéro tirage) ; le crit s'applique par-dessus et les déplace en bloc (`live [7611, 7611]` vs port `[4488, 4488]`, la valeur historiquement mesurée) | neutraliser — **après avoir supprimé la duplication du montage**, cf. ci-dessous |
| `test_my_will_be_done_overlord_live` | **causé** | le montage lit **qui rejoue** : le crit change l'issue des coups, donc la séquence, et le trigger natif cessait de fire (`aucune victime live`) | neutraliser (`probe_354`) |
| `test_429r1r3r1r2_unit_extensions_is_alive_live` | préexistant | 2 failed dans les deux régimes | non touché |
| `test_endturn_order_live` | préexistant | 1 failed dans les deux régimes | non touché |
| `test_harlequins_panoply_live` | préexistant | 2 failed dans les deux régimes | non touché |

⚠ Les trois causés du canal (C) **ne portent aucun marqueur `did_crit`** : ils ne skippent pas, ils
**rougissent**. Leur signature ne ressemble donc pas à celle du canal (A), et c'est exactement
pourquoi un balayage qui ne cherche que le mot « crit » les aurait manqués.

⚠ **Et une neutralisation posée au mauvais endroit ne mord PAS — c'est la mesure qui l'a dit, pas
la relecture.** Sur `exemplar_of_the_kauyon`, le montage était **dupliqué** : le probe
`probe_366r1_exemplar_kauyon_hits.build()` et la fixture du test construisaient chacun leur liste
d'arguments. La neutralisation posée côté probe a laissé le test **rigoureusement inchangé**
(`live [7611, 7611]` vs port `[4488, 4488]`, au chiffre près), et on aurait pu en conclure « le
crit n'est pas la cause, c'est un bug de port ». La réparation est donc d'abord un **foyer unique**
(`build_extra(enemy)`, consommé par les deux) ; ensuite seulement la neutralisation mord, et le
fichier revient à **6 passed**, le compte du témoin.

## 7. Résidus NOMMÉS

* **`#419-r6-r1` — les 315 fichiers live « indifférents aux deux marqueurs » ne sont pas joués**,
  ni la face DÉCISION hors tests (`engine_validate.py`, `predict_sweep.py`). Les canaux (A) et (C)
  ont été joués intégralement dans les deux régimes ; ces 315 ne l'ont pas été, et l'extrapolation
  n'est pas une mesure — le canal (C) vient précisément de montrer qu'un canal négligé cachait
  **3 casses réelles**. Y vivent aussi les **7 rouges PRÉEXISTANTS** mesurés ici et non traités
  (4 en (A), 3 en (C)).
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
