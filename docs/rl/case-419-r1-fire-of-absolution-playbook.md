# case-419-r1 (tranche 7) — `FireOfAbsolution` (TriggeredAbilityType **1017**), face ATTACK

Sixième résidu ATTACK de `#419-r1` fermé. Corps natif :
`IdunBattle.AI.Playbook.Loki.FireOfAbsolutionPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext`.

Port : `scripts/python/engine/playbook/fire_of_absolution.py` (RE intégrale dans son en-tête —
cette fiche ne la répète pas, elle enregistre les **arbitrages** et les **mesures**).

---

## 1. Verdict

**QUIRK PORTÉ**, confronté live, accord **exact** (résidu nul).

    u = FIREOFABSOLUTION_AdjacentFriend x |GetAdjacentFriends(case.Target, playerId)|
      + FIREOFABSOLUTION_AdjacentEnemy  x |GetAdjacentEnemies(case.Target, playerId, false)|
      = -20 x nAmis + 20 x nEnnemis                            (poids du gameconfig courant)

Premier playbook attack du registre qui **somme deux produits poids × cardinal**, premier dont un
poids est **négatif** — il rend donc une utilité `< 0`, ce qu'aucun autre ne fait (mesuré :
`-19.950003` au `pairUtility` natif dans le régime caster-adjacent).

## 2. Le piège du nom — `1017` vaut trois choses

Le brief signalait que `1017` était déjà cité au dépôt. Vérification faite dans les **trois** enums
(`data/symbols/<build>/frida/enums.tsv`) avant toute conclusion :

| enum | 1017 | où il est cité |
|---|---|---|
| `TriggeredAbilityType` | **`FireOfAbsolution`** | **cette tranche** |
| `ActiveAbilityType` | `FragBomb` | `case-249-tile-has-enemy-unit.md`, `case-astramilitarum-fragbomb-basilisk.md` (masque `0x80040`) |
| `EffectType` | `ActOfFaith_Effect` | — |

Le `1017` de #249 (`TargetTileHasEnemyUnit`) est donc l'ability **ACTIVE** `FragBomb`, avec son
`TARGETING_OPTIONS`. **Rien de ce qui est livré ici n'était « déjà porté ».** Et symétriquement :
`FireOfAbsolutionAbility` est DÉCLENCHÉE (`CreateTrigger` = `On(0x4a, true) & OwnerIsActor &
IsRangedAttack`), jamais castée — elle n'entre donc **ni** dans `ABILITY_CLASSES`, **ni** dans
`TARGETING_OPTIONS`, **ni** dans `ABILITY_ATTACK_TYPE`, conformément à la règle de registre.

## 3. Gate de confrontabilité — ventilation des 4 porteurs

| porteur | catégorie | chemin vers la bataille |
|---|---|---|
| `adeptRetributor` | **HERO** | présent dans `rl_duel build --list-pool` — **spawné directement**, aucune injection |
| `adeptBossRetributor` | npc | hors-jeu |
| `adeptBossRetributorLHE` | npc | hors-jeu |
| `adeptNpcRetributor` | npc | hors-jeu |

Voie d'attribution : `passive` (les 4). La confrontation n'a eu besoin **ni** de l'injection
catalogue, **ni** de la greffe `case-92` §5bis. `adeptRetributor` porte `1017` comme **SEUL**
triggered (`kit_triggered_ability_ids` = `[1017]`), et le montage **atteste** en plus qu'aucun autre
playbook du registre ATTACK n'est dans son `AbilitiesComponent` live : aucun terme étranger ne peut
se mêler à la mesure.

## 4. Ce que la RE a dû lire, et qui ne se devinait pas

**La disposition de la SM se lit dans le WRAPPER, jamais par analogie.** Celle de `d__4` est
`+0x20 = case`, `+0x28 = this`, `+0x30 = getUtilityVal` — c'est l'**inverse** de `Boltstorm`
(`d__3` : `+0x20 = this`, `+0x28 = case`). Prendre le voisin pour modèle aurait interverti le
playbook et le case.

**Les deux slots d'interface, identifiés par le proxy NOMMÉ** — jamais par l'ordre supposé de
`IBattleQuery`. Chaque lambda `RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClassNNN_0$$u003C<M>u003Eb__0`
a pour corps entier l'appel d'interface :

    DisplayClass152 -> slot 0x7d GetAdjacentEnemies (ref, int, bool)   <- utilisé ici
    DisplayClass156 -> slot 0x81 GetAdjacentFriends (ref, int)         <- utilisé ici

Ce sont **les deux mêmes slots** que la face MOVE de `adjacent_unit_preference.py` — mais **ancrés
sur la CIBLE** (`case.Target`) et non sur la tuile candidate. Le foyer géométrique
(`battle_query.is_adjacent`) est donc partagé, sans aucun fork.

**Le filtre exact**, lu jusqu'à la feuille (`BattleQuery$$CountOrGetUnitsOnTiles`) : occupant unique
par tuile (`GetUnit(tile)` — un mort a quitté la sienne), `ignoreSteppables: false` donc **les
Steppables comptent**, ring-1 avec la porte `|Δelev| < 2` d'`IterateAdjacentTiles`.

## 5. Le quirk : **le caster se compte lui-même parmi les amis**

Le natif n'oppose **aucun** retrait au résultat du slot 0x81 — ni `op_Subtraction`, ni `Remove`, ni
test `!= case.Caster`. Ce n'est pas un oubli de lecture, et c'est démontré par deux voisins :

* la famille **MOVE** (`AdjacentUnitPreference...d__1`) a, elle, un retrait **explicite**
  (« MINUS self ») — le natif sait donc l'écrire quand il le veut ;
* la face **COMBAT de la MÊME ability** exclut nommément le caster de son splash
  (`FireOfAbsolutionAbility$$CreateBehaviour` : `AdjacentUnits(Target) - Caster@0x48 - Target@0x60`).

Le playbook et le behaviour **divergent donc**, au sein de la même ability. Conséquence mesurable :
un `adeptRetributor` qui tire sur une cible adjacente s'inflige **-20**.

Pourquoi le poids ami est négatif se lit dans le behaviour : le splash frappe **toutes** les unités
adjacentes à la cible, **alliées comprises** (le sélecteur ne filtre pas par camp). Le playbook
chiffre exactement ça : `+20` par ennemi qui sera touché, `-20` par ami.

## 6. Confrontation live — le montage et ses chiffres

`probe_419_r1_fire_of_absolution_pair_term.py`, board `MC1_67`, seed `41504`, caster
`adeptRetributor`. Les unités sont **déplacées** (jamais « bloqué par la géométrie de spawn ») et
toutes les adjacences sont **re-mesurées** sur les positions live avec l'adjacence **native**.

**Étape A — balayage isolant** (caster sur une tuile de tir FIXE, un seul déplacement par cran) :

| cran | amis | ennemis | natif | port | port muté | manque = nat − muté | attendu |
|---|---|---|---|---|---|---|---|
| `n0` | 0 | 0 | 6.274686 | 6.274686 | 6.274686 | −0.000000 | 0 |
| `e1` | 0 | 1 | 26.274686 | 26.274686 | 6.274686 | **+20.000000** | +20 |
| `e2` | 0 | 2 | 46.274686 | 46.274686 | 6.274686 | **+40.000000** | +40 |
| `f1` | 1 | 2 | 26.274686 | 26.274686 | 6.274686 | **+20.000000** | +20 |
| `f2` | 2 | 2 | 6.274686 | 6.274686 | 6.274686 | −0.000000 | 0 |
| `zz` | 1 | 1 | 6.274686 | 6.274686 | 6.274686 | −0.000000 | 0 |

Écart NIVEAU max `|manque − attendu|` = **1e-9**. Contrairement à #446, cette paire porte un résidu
**NUL** : `natif == port` exactement. La garde asserte les deux séparément (invariance de l'écart
**et** niveau), pour que l'apparition future d'un résidu étranger fasse céder la bonne assertion.

**Étape B — le quirk du caster, par DOUBLE DELTA.** Le confronter en niveau est impossible (changer
la tuile de tir change tout le score) ; on annule le résidu ET la variation de tuile :

    (nat_adj − muté_adj) − (nat_far − muté_far)  =  −20.000000   ==  wFriend   (attendu)

avec `nat_adj = -19.950003` et `muté_adj = 0.049998` — le natif rend bien une utilité **négative**.

**Étape C — les 5 contre-épreuves, jouées à CHAQUE cran** :

| mutant | déplacement max du port | verdict |
|---|---|---|
| `swap_keys` (clés échangées) | +80 (crans `e1`/`e2`/`f1`) | MORD |
| `friends_only` | +40 | MORD |
| `enemies_only` | +40 | MORD |
| `no_elev_gate` (`hexgeo` nu) | +20 (**cran `zz` seul**) | MORD |
| `exclude_caster` | +20 (**régime `adj` seul**) | MORD |

### 6bis. Deux contre-épreuves d'abord VERTES — et pourquoi

La **première** version du montage jouait les mutants sur le **seul dernier cran**, `f2` = `(2, 2)`.
Deux d'entre elles y étaient inertes, sans que rien ne cloche :

* `swap_keys` — **les deux poids sont opposés** : sur des cardinaux **égaux**, les échanger rend
  exactement la même valeur. L'appariement clé ↔ slot n'était donc prouvé par **rien**, alors que
  c'est précisément le point que le décompilé ne tranche pas (les littéraux de chaîne sont des
  caches `DAT_` initialisés au runtime). Correction : **les mutants sont joués à chaque cran**, et
  le montage exige désormais un cran où `nAmis != nEnnemis`.
* `no_elev_gate` — aucun voisin de la cible n'était séparé de ≥ 2 niveaux. Correction : `find_layout`
  **cherche** une tuile `Z` voisine-hex de la cible que le natif n'y considère PAS adjacente, et
  **préfère** les layouts qui en offrent une ; le cran `zz` l'exerce. Si le board n'en a pas, le
  probe le **dit** et la garde **refuse** plutôt que de rendre un vert qui ne prouve rien.

C'est l'application directe du critère : *une contre-épreuve verte se nomme en résidu ou se corrige
— jamais elle ne se lit comme une confirmation.*

## 7. Contre-épreuve de la GARDE elle-même

`tests/engine/test_419_r1_fire_of_absolution_pair_term_live.py` — **7 passed**. Chaque mutation du
port a été appliquée **au fichier source**, l'application **vérifiée** (une substitution qui ne
matche pas rendrait un vert sans valeur), la garde rejouée, la source restaurée :

| mutation du port | verdict de la garde |
|---|---|
| clés échangées | **ROUGIT** (5 failed) |
| caster exclu des amis | **ROUGIT** (2 failed) |
| adjacence `hexgeo` nue (porte d'élévation retirée) | **ROUGIT** (3 failed) |
| terme ennemi retiré | **ROUGIT** (3 failed) |
| playbook **décâblé** du registre | **ROUGIT** (7 errors) |
| *restauration* | *7 passed* |

## 8. « Porté + inerte » — le câblage, vérifié

Le patron que #419 recense est un playbook qui entre au registre sans que rien ne l'alimente. Trois
vérifications ont été faites **avant** la mesure, et deux sont **assertées par le montage** :

1. `1017` est bien dans le kit dérivé (`kit_triggered_ability_ids` = `[1017]` pour les 4 porteurs) ;
2. le montage **refuse** si `1017` n'est pas dans l'`AbilitiesComponent` **live** du caster ;
3. la garde vise le **foyer** `engine.utilities.tile.triggered_abilities_attack_utility` (pas
   seulement la classe), donc elle garde le **câblage** autant que le calcul.

Substrats consommés : `scene.units` / `.pos` / `.team` / `.alive` / `.elev_by_pos` — tous déjà
alimentés et exercés par les tranches précédentes. Aucun capteur neuf, **aucune réinjection**.

## 9. Face MOVE — pas un résidu

`FireOfAbsolutionPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__3$$MoveNext` est
**lu** : un seul état, `Fix64.op_Implicit(0)`, aucun champ de la SM consulté. Son absence de
`TRIGGERED_MOVE_PLAYBOOKS` **est** le comportement natif.

⚠ Le classement `SM` de `probe_419_triggered_playbook_inventory.py` dit qu'un corps **existe**, pas
qu'il **calcule** — l'en-tête du module avait d'abord annoncé un « corps propre » sur cette seule
foi, ce qui était **faux**. Corrigé après lecture.

## 10. Ce qui n'est PAS couvert

* **Les 3 porteurs npc** (`adeptBossRetributor`, `adeptBossRetributorLHE`, `adeptNpcRetributor`) :
  **NON CONFRONTÉS** — hors-jeu. Le corps ne lit ni stat ni trait du caster, donc rien ne les
  distingue du hero pour ce terme ; la greffe `case-92` §5bis n'a pas été jugée nécessaire.
* **`ignoreSteppables: false`** est lu au décompilé mais **NON CONFRONTÉ** : le montage n'amène
  aucune unité `Steppable` au contact de la cible. Un port qui filtrerait les Steppables passerait
  cette garde. Résidu nommé **`#419-r1/1017-steppable`**.
* **`IsFriend`/`IsEnemy` vs `scene.team`** : le natif compare l'**entité joueur**
  (`CurrentPlayerEntityId` du caster) ; le port compare la **team**. Les deux coïncident sur les
  duels que le harnais monte (un joueur = une team) — non discriminé, et non discriminable par ce
  harnais.
* **Un second couple board/seed** : le balayage n'a été joué que sur `MC1_67`/`41504`.
* La face **NON-OWNER** : `1017` n'a pas de playbook non-owner (l'inventaire n'en liste aucun).
