# case-271 — `KustomForceFieldReworked` (1547, `orksBigMek`) : les deux termes démasqués

**Question binaire du cas.** Avec les poids **vivants**, un A/B qui fait varier le nombre d'**alliés
adjacents** au porteur fait-il basculer le choix **natif** ?

**Réponse : OUI, sur les DEUX faces.** Le natif applique le terme, il applique son facteur ×2, et
l'état `master` (registre amputé) se trompe sur les configurations craftées.

---

## 1. Pourquoi cet item n'existait pas avant

Les deux clés valaient **0** dans la table `BC.Utilities` de la **capture** (`data/seed-bc.json`) et
valent **10** au gameconfig **vivant**. Tant que le natif et le moteur lisaient tous deux la capture,
ils étaient **d'accord — et faux tous les deux**. Le merge `dd129216`
(`catalog_inject.refresh_ai_utilities`) sert désormais les poids vivants aux deux côtés, ce qui a
démasqué le gap.

| clé | catégorie | capture | gameconfig vivant |
|---|---|---|---|
| `KustomForceFieldReworked_LikesAdjacentFriends` | `TriggeredAbilities` | 0 | **10** |
| `KustomForceFieldReworked_FriendsLikeToBeAdjacent` | `TriggeredAbilitiesNonOwner` | 0 | **10** |

Les deux littéraux sont **LUS** au décompilé (slot de metadata usage → `global-metadata.dat`,
`probe_212_bc_key_literals.py` sur les symboles des deux corps), pas devinés.

L'étape 0 du probe (`--offline-only`) imprime les deux valeurs côte à côte et **REFUSE de continuer**
si `engine.weights.load` retombe sur la capture : sans ce garde-fou, un A/B mesurerait le néant.

## 2. Les deux faces, au décompilé

### Face OWNER — `TriggeredAbilities(2)`

`IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedPlaybook$$GetAdjacentFriendUtility` :

```c
int v = ctx["KustomForceFieldReworked_LikesAdjacentFriends"];
if (UnitExtensions.HasFaction(unit, 5)) v *= 2;      // UnitFaction.Orks
return v;
```

Famille `AdjacentUnitPreferenceTriggeredAbilityPlaybook` : le `.ctor` appelle la MÊME base que
`GuardianOrganismPlaybook` / `SpiritualLeaderPlaybook`
(`IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`)
avec le littéral `0x60b` = 1547.

Le bloc `methodPointers` du PE donne `[.ctor, GetAdjacentFriendUtility, <ret 0>]` — **strictement le
même groupe que `GuardianOrganismPlaybook`**. Donc : **ni cap** `vtbl+0x228`, **ni filtre**
`vtbl+0x248` (les corps `<ret 1>` et `FilterAdjacentFriends` que porte `SpiritualLeaderPlaybook` sont
ABSENTS). Le `<ret 0>` est la face ENNEMIS non surchargée.

Terme = `10 × #amis non-Orks à R1` + `20 × #amis Orks à R1` de la tuile candidate.

### Face NON-OWNER — `TriggeredAbilitiesNonOwner(4)`

`IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` :

```c
if (case.unit == null) yield break;
if (!UnitExtensions.IsFriend(case.unit, owner, state)) yield break;
ITile ownerTile = EntityExtensions.GetMainTile(owner, state);
if (ownerTile == null) yield break;
if (!TileExtensions.IsAdjacentTo(case.MovementTile, ownerTile)) yield break;
Fix64 v = GetUtilityValue("KustomForceFieldReworked_FriendsLikeToBeAdjacent");
if (UnitExtensions.HasFaction(case.unit, 5)) v *= Fix64.FromInt(2);   // UnitFaction.Orks
yield return v;
```

Trois points que le décompilé **tranche** :

* le `HasFaction` porte sur **`case.unit`** (le MOVER), pas sur `owner` — le Big Mek est toujours Ork,
  ce serait un facteur constant sans intérêt ; c'est bien la faction de **celui qui bouge** qui double ;
* le ×2 est un `Fix64.op_Multiply` par `Fix64.FromInt(2)`, **pas un second poids BC** ;
* la clé vit dans la catégorie **séparée** `TriggeredAbilitiesNonOwner`.

Le `.ctor` appelle la même base que `ShieldOfFaithNonOwnerPlaybook` (littéral `0x5ad` = 1453) avec
`0x60b`. Le bloc `methodPointers` ne contient que `.ctor`, `CalculateMovementUtilityInSteps` et la
boilerplate d'itérateur : **aucun autre slot surchargé**.

### Reachability — PROUVÉE avant portage

* Les deux playbooks sont enregistrés par `IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`
  (lambdas `b__31_337` pour l'owner, `b__31_367` pour le non-owner) — même forme que
  `GuardianOrganismPlaybook` (`b__31_280`), playbook dont la vivacité est établie depuis case-36.
* Le `TriggeredAbilityComponent` LIVE du Big Mek du runner porte bien **1547** (RPC
  `unitAbilityStates` : `triggered: [1547, 1234]`).
* `orksBigMek` est dans `rl_duel build --list-pool` (rank 17, 97 unités) — porteur **HERO** direct,
  aucune injection de catalogue nécessaire. Les 4 autres porteurs (`orksBossBigMek`,
  `orksBossBigMekLEG`, `orksBossBigMekLHE`, `orksNpcBigMek`) sont **npc**.

## 3. La feuille `TriggeredAbilitiesNonOwner(4)`, portée par ce cas

Elle était `None` dans `TILE_LEAVES` depuis toujours. Chaîne native :

```
IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext
    Fix64 total = 0;
    if (case.unit == null && case.parent == null) { yield 0; return; }
    foreach ((playbook, owner) in IterateAbilities(case))
        total += playbook.CalculateMovementUtilityInSteps(case, owner);
    yield total;

IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CIterateAbilitiesu003Ed__3$$MoveNext
    subject = case.unit ?? case.parent;
    foreach (ta in <toutes les TriggeredAbility de la bataille>) {
        if (case.unit != null && case.unit == ta.Owner) continue;         // self exclu
        pb = PlaybookDatabase.LoadPlaybookNonOwner(ta.Type);              // null -> skip
        if (pb.<slot 4> || UnitExtensions.IsFriend(subject, ta.Owner))    // pre-gate
            yield (pb, ta.Owner);
    }
```

**Ce qui n'est PAS porté, et pourquoi** — le pré-gate `<slot 4>` (complément de
`IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$IsInvalidEntityForPlaybook`, qui vaut
`!slot4 && !IsFriend`) est un prédicat sans argument dont le corps est TRIVIAL, fondu par l'ICF, donc
sans symbole propre. Il est **TRANSPARENT** pour le seul playbook enregistré : celui-ci re-teste
`IsFriend` lui-même, donc un porteur non-ami rend 0 que le pré-gate l'ait écarté ou non. **Résidu
nommé** : le jour où un playbook NonOwner *sans auto-gate* entre au registre, il faudra lire ce slot
(bloc `methodPointers` du PE, `probe_8889_methodptr_vtable.py`) **avant** de le porter.

**Second résidu nommé** : le régime SPAWN (`case.unit == null`, `case.parent != null` — call-site
`SortTilesByUtilityForSummon`) où le natif itère avec le PARENT comme sujet et **sans** exclusion de
self. Le `ctx` de ce foyer ne produit aucune clé d'unité (`{"is_spawning": True}` seul) ⇒ la feuille
rend 0. Identique aux autres feuilles gatées sur le sujet.

## 4. LE PIÈGE DU CAS — l'adjacence du port n'était pas l'adjacence native

L'A/B crafté a d'abord rendu **« le natif ne suit pas »**. Ce verdict était **faux**, et ce n'est pas
le terme qui était en cause : c'est **l'instrument**.

Le contrôle qui l'a montré : rejouer **le même montage** avec `GuardianOrganism` (1181,
`tyranTyrantGuard`), terme dont la vivacité native est établie depuis case-36 (30 par ami adjacent,
30/90 EXACTS aux hooks). Le contrôle a échoué **aussi** — donc le défaut était en amont du terme.

Cause racine : `AdjacentUnitPreferenceTriggeredAbilityPlaybook.calculate_movement_utility_in_steps`
retenait les voisins par `hexgeo.distance(tile, pos) == 1` **nu**. Or
`IBattleQuery.GetAdjacent{Friends,Enemies}` passe par
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui applique un gate
**inconditionnel** `abs(elev(tuile) − elev(voisin)) < 2`. Deux tuiles côte à côte séparées de 2
niveaux **ne sont pas voisines** pour le natif.

**Mesure** (`probe_271_kustom_force_field_reworked.py --adjacency`), sur le voisinage NATIF que rend
`boardGraph` :

| board | paires | `hexgeo.distance == 1` FAUX | `battle_query.is_adjacent` FAUX |
|---|---:|---:|---:|
| `MC1_67` | 1 953 | 9 | **0** |
| `C4_09` | 2 415 | 22 | **0** |
| `C1_25` | 595 | 2 | **0** |
| **total** | **4 963** | **33** | **0** |

L'erreur est toujours **permissive** (le voisinage natif est un SOUS-ENSEMBLE de hexgeo) : le port
sur-comptait des voisins. Elle ne mord qu'au bord d'une marche d'élévation ≥ 2, ce qui explique
qu'elle ait survécu à #57i / #193c / #211 / #212 / #242 — et exactement pourquoi l'A/B de ce cas
posait son allié « adjacent » sur `(1,3)`, tuile d'élévation 4 voisine hexgeo de `(2,2)` (élévation 2)
mais **pas** voisine native.

**Correction** : les deux branches du corps commun utilisent désormais
`battle_query.is_adjacent(tile, pos, ctx["elev_by_pos"])`. Ça touche **les 12 playbooks** de la
famille, pas seulement le nouveau. `elev_by_pos` absent ⇒ dégradation en hexgeo pur, exactement
comme partout ailleurs.

## 5. Confrontation live — protocole et résultats

Les hooks par-tuile de `scorer-damage-trace` portent des RVA du build `gqfc5mff6c` et ne sont pas
ré-armables sur `rnca9r7q6c` sans réinjection (interdite). Le canal utilisé est donc l'**ARGMAX**,
celui des gardes #193c / #211 / #212, avec deux durcissements :

* la décision comparée est celle du **tactic complet** (`DefaultAiUnitTactic.calculate_next_action`),
  pas `_best_attack` : le Big Mek est une unité de SOUTIEN, ses pas sont des **mouvements purs**
  tranchés par `MovementActionGenerator` — sur ces pas `_best_attack` rend `None` et ne mesure rien ;
* le montage **REFUSE** les états où la proposition native contient un `ActiveAbilityMessage` : la
  tuile viendrait du sweep d'ATTAQUE, hors du modèle `UnitMovement(6) = Tile(7) + MinDist(16)`.

### Pourquoi il faut CRAFTER

Sur la trajectoire naturelle (seed 777 / `MC1_67`, 29 pas), le terme **varie** sur 13 pas mais ne
**bascule** l'argmax qu'une fois : `MinDistanceToClosestEnemy.PerTileDistance` vaut **−100 par tuile**
de distance-chemin ; un écart d'une seule tuile (100) écrase le terme (10..40). Le terme ne tranche
qu'entre tuiles à **distance-chemin égale** — configuration qu'il faut fabriquer.

### Face OWNER (`--driven`) — `MC1_67` / 777, sujet `orksBigMek`

`T1 = (3,2)` (LightCover DryBush, +9) bat `T2 = (2,2)` de 9 sans le terme.

| variante | terme(T2) | port OFF | port ON | **NATIF** |
|---|---:|---|---|---|
| témoin (aucun allié posé) | +0 | (3,2) | (3,2) | **(3,2)** |
| allié **Ork** voisin natif de T2 | **+20** | (3,2) | (2,2) | **(2,2)** |
| allié **non-Ork** voisin natif de T2 | **+10** | (3,2) | (2,2) | **(2,2)** |

Le natif suit le port **avec** le terme dans les trois configurations ; l'état `master` (OFF) se
trompe dans deux sur trois.

Contrôle d'instrument sur le même montage avec `GuardianOrganism` (1181) : terme +30, `OFF=(3,2)`,
`ON=(2,2)`, **NATIF=(2,2)** — l'instrument mesure bien ce qu'il prétend.

### Le facteur ×2 (`--swap`) — échange de factions à géométrie identique

Aucun couple (board, seed) testé n'offre un écart T1−T2 dans `]10, 20[` (les `Tile(7)` sont quantifiés
par paliers : Elevation 10/niveau, LightCover 9 ; MinDist saute de 100). On isole donc le facteur 2
autrement : **un ami de chaque faction, un de chaque côté**, la géométrie étant identique dans les
deux variantes — seule change la **faction de l'occupant de chaque tuile**.

| variante | terme(T1) | terme(T2) | port ON | **NATIF** |
|---|---:|---:|---|---|
| ORK voisin de T2, non-ORK voisin de T1 | +10 | +20 | (2,2) | **(2,2)** |
| l'inverse (pur échange de places) | +20 | +10 | (3,2) | **(3,2)** |

Si le poids était **plat** (quelle que soit sa valeur), les deux termes s'annuleraient et T1 gagnerait
dans **les deux** variantes. La bascule de la première variante est donc la signature **exclusive** du
`HasFaction(unit, 5) -> v *= 2`.

### Face NON-OWNER (`--nonowner`) — le Big Mek comme AIMANT

Montage retourné : le sujet est un **allié** du Big Mek, et l'unité qu'on déplace est le **Big Mek**,
posé sur une tuile voisine **native** de T2 et pas de T1.

| board/seed | mover | terme(T2) | écart | port OFF | port ON | **NATIF** |
|---|---|---:|---:|---|---|---|
| `MC1_67`/777, pas 0 | `necroWarden` (non-Ork) | **+10** | 0 | (0,4) | (3,3) | **(3,3)** |
| `MC1_67`/777, pas 10 | `orksNob` (Ork) | **+20** | 0 | (2,5) | (3,5) | **(3,5)** |

Les deux basculent et le natif suit le port **avec** le terme. ⚠ **Limite honnête** : ces deux
montages ont un écart **nul** (T1 et T2 ex aequo sans le terme) — un tie-break natif fixe pourrait
produire le même résultat. Le miroir strict (même paire, aimant de l'autre côté) n'a pas été montable
sur les couples testés (le Big Mek, placé derrière ses alliés au spawn, n'atteint aucune tuile
voisine de T1 seule), et aucun couple (board, seed, pas) balayé n'a offert un écart **strictement
positif** ≤ 25 sur un état où la proposition native est un mouvement PUR. Voir §7.

## 6. Ce que le port fait maintenant

* `engine/playbook/adjacent_unit_preference.py` — `KustomForceFieldReworkedPlaybook` (face owner,
  gate `HasFaction` DANS l'accesseur, ni cap ni filtre) + entrée 1547 au registre. Et la correction
  d'adjacence du corps commun (§4).
* `engine/playbook/non_owner.py` (**neuf**) — famille `TriggeredAbilityNonOwnerPlaybook`,
  `KustomForceFieldReworkedNonOwnerPlaybook`, registre `NON_OWNER_MOVE_PLAYBOOKS` +
  `load_playbook_non_owner` (mirror de `PlaybookDatabase.LoadPlaybookNonOwner`).
* `engine/utilities/tile.py` — feuille `TriggeredAbilitiesNonOwnerUtility` (UtilityType 4), entrée
  dans `TILE_LEAVES` : le composite `Tile(7)` passe de 26 à 27 feuilles portées.

## 7. Résidus NOMMÉS

1. **Pré-gate `<slot 4>` de `IterateAbilities`** — non porté, transparent pour le seul playbook au
   registre (§3). À lire avant d'enregistrer un playbook NonOwner sans auto-gate `IsFriend`.
2. **Régime SPAWN de la feuille 4** (`case.unit == null`, parent non nul) — rend 0 faute d'un `ctx`
   de spawn peuplé ; même résidu que les autres feuilles gatées sur le sujet (case-205).
3. **Face NON-OWNER : pas de confrontation à écart STRICTEMENT POSITIF.** Les deux bascules mesurées
   partent d'un ex aequo. Deux voies pour fermer : (a) un couple (board, seed, pas) où la meilleure
   et la deuxième tuile d'un allié diffèrent de 1..25 **et** où la proposition native est un move pur
   — le balayage `--nonowner --gap-min 1` sur `MC1_67`/`C4_09` × 777/31337 × pas 0..12 n'en a pas
   trouvé ; (b) rendre le miroir strict montable en pré-positionnant le Big Mek DEVANT ses alliés.
4. **`X_nat` par tuile non re-mesurable** sur `rnca9r7q6c` : les hooks `scorer-damage-trace` portent
   des RVA `gqfc5mff6c` (`probe_257_scorer_rva_migration.py` les migrerait, mais ça exige un
   reinject). Toute la confrontation de ce cas passe donc par l'ARGMAX, pas par la valeur du terme.
5. **Les 24 autres playbooks `*NonOwnerPlaybook`** du binaire restent non portés (absence du registre
   == `LoadPlaybookNonOwner` rend null == même dégradation que le natif, pas un trou silencieux).

## 8. Re-dérivation

```bash
cd scripts/python
python probe_271_kustom_force_field_reworked.py --offline-only          # etape 0 : poids vivants
python probe_271_kustom_force_field_reworked.py --adjacency --boards "MC1_67,C4_09,C1_25"
python probe_271_kustom_force_field_reworked.py --driven --seed 777 --board MC1_67 \
    --p-units "orksBigMek,orksNob,astraBullgryn,necroWarden,orksWarboss" \
    --a-units "worldKharn,templChampion,tauMarksman"
python probe_271_kustom_force_field_reworked.py --driven --carrier tyranTyrantGuard --ability 1181 \
    --p-units "tyranTyrantGuard,orksNob,astraBullgryn,necroWarden,orksWarboss" \
    --a-units "worldKharn,templChampion,tauMarksman"         # CONTROLE DE L'INSTRUMENT
python probe_271_kustom_force_field_reworked.py --swap --seed 777 --board MC1_67 \
    --p-units "orksBigMek,orksNob,orksWarboss,astraBullgryn,necroWarden" \
    --a-units "worldKharn,templChampion,tauMarksman"          # isole le facteur 2
python probe_271_kustom_force_field_reworked.py --nonowner "orksNob,necroWarden" \
    --pre-steps "0,10" --seed 777 --board MC1_67 \
    --p-units "orksBigMek,orksNob,astraBullgryn,necroWarden,orksWarboss" \
    --a-units "worldKharn,templChampion,tauMarksman"
```

Gardes : `tests/engine/test_kustom_force_field_reworked_live.py`.
