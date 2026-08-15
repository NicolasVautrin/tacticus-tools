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

**Les deux résidus que ce §3 avait ouverts sont FERMÉS (2026-08-07), et les deux énoncés étaient
faux — pas incomplets, faux.** Ils sont conservés ci-dessous rayés, parce que la façon dont chacun
s'est révélé faux est le vrai enseignement du cas.

~~**Ce qui n'est PAS porté** — le pré-gate `<slot 4>` … est **TRANSPARENT** pour le seul playbook
enregistré ; il faudra lire ce slot le jour où un playbook sans auto-gate entre au registre.~~
→ **#271-r2 FERMÉ.** Le slot a un NOM (`get_ShouldIncludingEnemiesWhenCalculate`, 5ᵉ méthode
d'`IdunBattle.AI.Playbook.ITriggeredAbilityNonOwnerPlaybook`, LUE dans le `global-metadata.dat`) et
il est porté **PAR CLASSE** depuis #477-r37 : **2 des 28** concrets le surchargent, l'entrée
`data/symbols/<build>/metadata/non_owner_slot4.tsv` est versionnée, et un cliquet confronte le port
au binaire. Ce qui restait ouvert n'était donc pas le port : c'était **cette citation-ci**, recopiée
dans la docstring du dispatcher, où elle affirmait « vaut `false` — aucune classe ne le surcharge »
DIX LIGNES au-dessus d'un code qui lisait `pb.SLOT_4` par classe.

~~**Second résidu** : le régime SPAWN … le `ctx` de ce foyer ne produit aucune clé d'unité ⇒ la
feuille rend 0. Identique aux autres feuilles gatées sur le sujet.~~
→ **#271-r3 LIVRÉ.** « Identique aux autres feuilles » était l'erreur : les autres feuilles sont
gatées sur le sujet **dans leur corps natif**, celle-ci ne l'est pas. `<EvaluateMovementInSteps>d__0`
ne rend `Fix64.Zero` que si `case.unit` **ET** `case.parent` sont nuls ; `<IterateAbilities>d__3`
prend alors le PARENT pour sujet et **désarme l'exclusion de self**. TROIS corps du registre y
yieldent — `PsychicFortress` (20), `BookOfFate` (5), branche SPAWN de `MawClawsOfThyrax` (5, sans le
gate `Summon`) — soit jusqu'à **30 points** perdus par tuile de spawn adjacente à un porteur ami. Et
le blocage annoncé (`seeding`) n'existait pas : le `State` du runner portait déjà tout, seul le
producteur de `ctx` refusait de publier.

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

1. ~~**Pré-gate `<slot 4>` de `IterateAbilities`**~~ — **FERMÉ (#271-r2, 2026-08-07)**, cf. §3 et
   §7.1 ci-dessous.
2. ~~**Régime SPAWN de la feuille 4**~~ — **LIVRÉ (#271-r3, 2026-08-07)**, cf. §3 et §7.2. Reste la
   confrontation LIVE du choix de tuile de spawn : **`#271-r5`**.
3. **Face NON-OWNER : pas de confrontation à écart STRICTEMENT POSITIF.** Les deux bascules mesurées
   partent d'un ex aequo. Deux voies pour fermer : (a) un couple (board, seed, pas) où la meilleure
   et la deuxième tuile d'un allié diffèrent de 1..25 **et** où la proposition native est un move pur
   — le balayage `--nonowner --gap-min 1` sur `MC1_67`/`C4_09` × 777/31337 × pas 0..12 n'en a pas
   trouvé ; (b) rendre le miroir strict montable en pré-positionnant le Big Mek DEVANT ses alliés.
4. **`X_nat` par tuile non re-mesurable** sur `rnca9r7q6c` : les hooks `scorer-damage-trace` portent
   des RVA `gqfc5mff6c` (`probe_257_scorer_rva_migration.py` les migrerait, mais ça exige un
   reinject). Toute la confrontation de ce cas passe donc par l'ARGMAX, pas par la valeur du terme.
5. ~~**Les 24 autres playbooks `*NonOwnerPlaybook`** du binaire restent non portés.~~
   **ÉNONCÉ RÉFUTÉ ET RÉÉCRIT (#271-r4, 2026-08-07).** Les deux chiffres étaient faux : le binaire
   déclare **28** concrets (compte par PARENT — trois ne portent pas le suffixe `NonOwnerPlaybook`
   et échappaient au grep par nom), et le registre en porte **19**. Ventilation par FACE, lue dans
   `data/symbols/<build>/metadata/non_owner_slot4.tsv` : **24 MOVE / 3 ATTACK / 1 REPAIR**.
   * face **MOVE** : 19 au registre, 1 portée volontairement hors registre
     (`RedemptionOfTheRisen`, 0 porteur), **4 non portées** — toutes déjà nommées ailleurs
     (`#477-r43` pour les trois gates `HasRarity`, `#477-r45` pour `SabreOfSacrifice`) ;
   * faces **ATTACK** (3 classes) et **REPAIR** (1) : **NON portées, et ce n'est pas du dead code.**

   **La reachability est MESURÉE, pas supposée** (`probe_271r4_composition_map.py`). Le dispatcher a
   trois entrées (`$$EvaluateMovementInSteps` / `$$EvaluateAttackInSteps` / `$$EvaluateRepairInSteps`,
   plus DEUX `IterateAbilities`, `d__3` et `d__4`), et une face n'est atteignable que si la feuille 4
   est membre du composite qui la porte. `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities`
   remplit sa carte de composition (`db+0x58`) par `RuntimeHelpers.InitializeArray` depuis des blobs
   de `<PrivateImplementationDetails>` qui vivent dans le **`global-metadata.dat`** et **pas dans le
   PE** (mesuré : 0 occurrence dans `GameAssembly.dll`). Le probe s'ancre sur le blob `Tile(7)` — la
   seule chose identifiable sans rien supposer, ses 29 éléments étant déjà portés et confrontés, et
   sa suite d'octets UNIQUE dans le fichier — puis segmente les blobs voisins, délimités par un `0` :

   | composite | n | membres |
   |---|--:|---|
   | `Tile(7)` | 29 | … `TriggeredAbilities(2)`, **`TriggeredAbilitiesNonOwner(4)`** … |
   | `Damage(35)` | 13 | `OnlyImperviousUnitIfCanBeDamaged`, `DamageDealt`, `KillUnit`, `DislikeObjects`, `DislikeBoss`, `DislikeEnvironmentUnits`, `OverkillUnit`, `EnemyOnTerritoryTile`, `TriggeredAbilities`, **`TriggeredAbilitiesNonOwner`**, `UnitSpecificBehaviours`, `OptimizedGait_AdjacentFriends`, `AttackTargetWithEffect` |
   | `Repair(47)` | 3 | `RepairedAmount`, `TriggeredAbilities`, **`TriggeredAbilitiesNonOwner`** |

   ⚠ **ANTI-CIRCULARITÉ** : on ne cherche pas « un blob qui contient la feuille 4 ». Chaque blob est
   identifié par sa TAILLE (lue au décompilé) **et** par un témoin INDÉPENDANT déjà porté dans le
   dépôt (`Damage` : les trois dominants de `utilities/damage.py` ; `Repair` : `RepairedAmount` de
   `utilities/repair.py`) ; témoin absent ⇒ le probe LÈVE. Corroboration : le blob `Damage` porte
   aussi la feuille 2, que le port câble déjà comme « feuille 2 du composite Damage(35) ».
   ⚠ `NoHidingFromTheWatchersNonOwnerPlaybook` (ATTACK) porte `<slot 4> = true` : l'inscrire sans
   cette valeur rendrait sa branche ENNEMI structurellement inatteignable — le bug de #477-r35,
   transposé d'une face. Garde posée en attendant : le registre MOVE ne peut contenir que des
   classes de face MOVE (`test_477r37_slot4_et_faces_restantes_live.py`).

### 7.5 — la RE des DEUX faces restantes est FAITE (2026-08-07) ; le port ne l'est pas

> **LA FACE ATTACK EST LIVRÉE ET CONFRONTÉE (2026-08-08).** Foyer :
> `engine/playbook/non_owner_attack.py` (neuf) + `TriggeredAbilitiesNonOwnerUtility.
> evaluate_attack_in_steps` + le câblage dans les DEUX foyers qui somment `Damage(35)`
> (`playbook/base.py`, `playbook/excruciating_frequencies.py`). Les deux corps non bloqués sont
> portés ; `ShieldOfFaith` reste `capteur` et la face REPAIR ouvre **`#271-r7`**.
> Ce qui a été RELU (et non hérité de ce §7.5) : les deux `MoveNext` de dispatch,
> `<IterateAbilities>d__4`, les deux corps concrets et leurs `.ctor`. Tout concorde.
> **Clés BC LUES** (`probe_212_bc_key_literals.py` sur le symbole du `MoveNext`, jamais devinées) :
> `NoHidingFromTheWatchers_AttackIfAdjacentToFriendAndMele` = **10** (le `Mele` tronqué est celui
> du binaire) et `WayOfTheShortBlade_TauAdjacentToEnemy` = **5**.
>
> **CONFRONTATION LIVE — `probe_271r4_face_attack_live.py`**, deux bras, board `MC1_67`/777.
> Les porteurs natifs de 1523 sont un SUMMON et un npc, et le summon n'a **aucun invocateur
> dérivable** (`darkaSmnWatcher` n'apparaît dans AUCUNE constante d'ability — 1 occurrence dans
> tout le gameconfig, sa propre entrée d'unité) ⇒ recours 3 de `case-92` §5bis, la **GREFFE**,
> licite ici parce que le corps ne lit du porteur QUE sa position et son identité (vérifié au
> décompilé, aucune stat, aucun trait) :
>
> | bras | porteur greffé | ami du caster ? | terme ON | terme OFF |
> |---|---|---|---:|---:|
> | `nohiding` | `worldKharn` (camp adverse) | non | **10.0** | 0.0 |
> | `nohiding-gate` | `ultraApothecary` (même camp) | oui | **0.0** | 0.0 |
>
> Le bras nominal prouve les DEUX choses à la fois : le pré-gate `<slot 4> = true` yielde bien un
> porteur **ENNEMI** (sans lui, la branche serait structurellement inatteignable — le bug de
> #477-r35), et le corps rend la clé BC. Le contrôle prouve que le gate `IsFriend` du corps coupe.
>
> **NON COUVERT — `#271-r8`** : la confrontation d'**ARGMAX natif**. Faire basculer le choix du
> jeu exige un état où 10 dépasse l'écart entre les deux meilleures paires, et le composite
> `Damage(35)` est dominé par `DamageDealt` ~[0,100] et `KillUnit` ~[0,100]. Ce qui est mesuré est
> « le terme MORD et DÉPLACE l'utilité de 10 », pas « le natif suit ».

> **LA FACE REPAIR EST LIVRÉE (2026-08-15, `#271-r7`) — et son `BLOCAGE: etage` n'existait pas.**
> Il disait « le `<slot 6>` d'`IUtility` n'est pas dans
> `data/symbols/<build>/metadata/interface_slots.tsv` (l'interface n'y figure pas), le canal n'est
> pas établi ». C'est le **TSV** qui manquait, pas le slot : un slot d'interface se LIT dans le
> `global-metadata.dat`, comme les huit autres interfaces de cette table.
> MESURE (`probe_271r7_iutility_slots.py`, même machinerie `il2cpp_metadata.locate_types` que
> `probe_477r25`, donc table désignée par le TYPE et sans ambiguïté d'interface) :
> `IUtility` slot 6 = **`EvaluateRepair(UtilityAttackCase) -> Fix64`** ; les slots 0..8 concordent
> avec la déclaration Il2CppDumper, le 9 (`CalculateMovementModifier`) est un AJOUT de ce build.
>
> Livré : `engine/playbook/non_owner_repair.py` (3ᵉ registre),
> `TriggeredAbilitiesNonOwnerUtility.evaluate_repair_in_steps` (jumeau EXACT de la face ATTACK —
> même `<IterateAbilities>d__4`, même pré-gate, seul le slot appelé change), et le câblage dans
> `ActionGenerator._repair_candidates`.
> ⚠ **Le terme est un DOUBLEMENT, pas un poids** : le corps ne fait AUCUN `getUtilityVal`, il
> RE-ÉMET `RepairedAmount(48)`, déjà membre du composite `Repair(47)`. Et ça se lit avec l'autre
> face du même passif — `VoltagheistField_RepairReductionEffect$$CreateEffectRepairBonus` divise la
> magnitude prédite par 2 : le doublement de l'UTILITÉ compense exactement le halving de la
> MAGNITUDE. Porter l'un sans l'autre biaise le choix de cible.
> **NON COUVERT** : la confrontation LIVE (montage = GREFFE de `VoltagheistField` sur une unité
> MECHANICAL du pool — les 3 porteurs sont 1 summon + 2 npc, et le corps ne lit du porteur que son
> IDENTITÉ) ; et la **feuille 2** du composite `Repair(47)` reste non portée (3 membres, 2 sommés).

Ce §7.5 fixe ce qui a été LU, pour qu'une reprise n'ait plus à le refaire.

**Les deux dispatchers sont JUMEAUX, et diffèrent de la face MOVE sur deux points.**

```c
// IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.<EvaluateAttackInSteps>d__1$$MoveNext
// IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.<EvaluateRepairInSteps>d__2$$MoveNext
Fix64 total = 0;
foreach ((playbook, owner) in IterateAbilities(case.Caster))          // surcharge (caseEntity)
    total += playbook.<slot 1 | slot 2>(case, owner);                 // Attack | Repair
yield total;
```

* **AUCUN gate de nullité du sujet** — ni `case.unit == null`, ni le couple `unit`/`parent` de la
  face MOVE. Les deux faces appellent directement la surcharge `IterateAbilities(IEntity)`
  (`$$IterateAbilities(caseEntity)` @ `<d__4>`), pas `$$IterateAbilities(movementCase)` (`<d__3>`).
* **Le SUJET est le CASTER** : `case+0x10`, et `UtilityAttackCase$$.ctor` écrit `caster` à `+0x10`,
  `casterPosition` à `+0x18`, `target` à `+0x20` — lu, pas supposé. Les DEUX faces prennent un
  `UtilityAttackCase` (le paramètre de la face REPAIR s'appelle `repairCase` mais son type déclaré
  est le même, `frida/methods.tsv`).

**`<IterateAbilities>d__4`** diffère de `d__3` sur un seul point, et il est load-bearing :

```c
foreach (ta in <utility+0x50 = abilityAndEffectCache>.<slot 5>()) {
    if (ta.Owner == subject) continue;                      // INCONDITIONNEL (d__3 le garde par `case.unit != null`)
    pb = PlaybookDatabase.LoadPlaybookNonOwner(ta.Type);     // null -> skip
    if (pb.<slot 4> || UnitExtensions.IsFriend(subject, ta.Owner, State))
        yield (pb, ta.Owner);
}
```

**Les QUATRE corps concrets, et leur blocage RÉEL — un par classe, jamais un par face :**

| classe | face | corps natif (lu) | blocage |
|---|---|---|---|
| `NoHidingFromTheWatchersNonOwnerPlaybook` | ATTACK | `if (case.Target != owner \|\| case.CasterPosition.MainTile == null \|\| GetMainTile(owner) == null) yield break; if (IsFriend(case.Caster, owner, State)) yield break; if (Query.<slot 132 = GetAdjacentFriends(pos, owner)>(GetUnitPosition(owner, State), owner).Count != 0) yield <clé BC>;` | `aucun` — et c'est elle qui porte `<slot 4> = true`, donc sa branche ENNEMI n'existe QUE si le pré-gate est porté |
| `WayOfTheShortBladeNonOwnerPlaybook` | ATTACK | `if (!HasTrait(case.Caster, 0x10 = Hero)) yield break; if (!(HasFaction(case.Caster, 9 = Tau) && HasRangedWeapon(case.Caster, null) && Query.<slot 0x61 = AreEntitiesAdjacent>(case.CasterPosition, case.Target))) yield break; range = GetNumberConstant(config, 0x16 = AbilityConstantType.range); if (Query.<slot 0x6d = GetDistance>(owner, case.CasterPosition) <= range) yield <clé BC>;` | `aucun` |
| `ShieldOfFaithNonOwnerPlaybook` | ATTACK | `if (case.Caster.BaseUnitComponent != null && BaseUnitComponent.<+0x74> != 5) yield break;` (= `HasRarity(Mythic)`) `; if (!AnyTileHasEffectOfUnit(case.Target, EffectType 5)) yield break; yield <clé BC>;` — et `$$AnyTileHasEffectOfUnit` = `GetTiles(target, State).Any(t => HasEffect(t, State, effectType, false))` | **`capteur`** — c'est le MÊME verrou `rarity` que `#477-r43` (aucun canal `rarity` côté port ; il faudrait `combatSnapshot.units[].rarity` ← `BaseUnitComponent.Rarity`) |
| `VoltagheistFieldPlaybook` | REPAIR | `if (case.Target != owner) yield break; yield <utilitiesDatabase @+0xe0>.GetUtility(0x30, 0).<slot 6>(case);` — `IUtilitiesDatabase` slot 0 = `GetUtility` (2 args), `0x30 = 48 = UtilityType.RepairedAmount` | `etage` — la feuille `RepairedAmount(48)` EST portée (`utilities/repair.py`), mais le port n'a aucun dispatcher REPAIR pour la feuille 4 ni de canal `IUtility.<slot 6>` |

**Ce qui reste à faire, dans l'ordre** : (a) `FACE` par classe au registre (la table
`data/symbols/<build>/metadata/non_owner_slot4.tsv` la porte déjà, et
`test_477r37_…::test_le_registre_MOVE_ne_contient_QUE_des_faces_MOVE` doit rester vrai) ;
(b) le mirror d'`<IterateAbilities>d__4` (exclusion de self INCONDITIONNELLE) ; (c) les deux corps
non bloqués ; (d) le câblage dans `Damage(35)` et `Repair(47)` ; (e) la confrontation live, dont le
porteur est à établir pour chacune des trois abilities.

## 8. Re-dérivation

```bash
cd scripts/python
# #271-r4 : les TROIS faces de la feuille 4, leur reachability, et la ventilation des 28 concrets
python probe_271r4_composition_map.py [--blobs]
# #271-r2 : le `<slot 4>` des 28, re-derive du binaire et confronte au port
python probe_477r37_slot4_et_faces_restantes.py --offline-only
# #271-r3 : le regime SPAWN (offline pur, ~2 s)
python -m pytest tests/engine/test_271r3_spawn_non_owner_offline.py -q

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

### 7.6 -- `#271-r5` : le regime SPAWN est CONFRONTE LIVE, et le natif suit le port

**2026-08-08, `MC1_67` / seed 777.** Le port des trois termes de spawn (#271-r3) etait
mirror-1:1 et garde par 8 tests offline + 5 mutations. L'OBSERVABLE -- **quelle tuile le natif
choisit pour faire apparaitre un summon** -- n'avait jamais ete mesure. Un port mirror-1:1 avec
des tests offline reste une HYPOTHESE tant que le natif ne l'a pas confirme.

#### Le montage

`probe_130_placement_sort_rng.py --case controledict` pilote deja un spawn qui passe par
`IdunBattleLogic.Entities.DSLFactory$$SortTilesByUtilityForSummon` : `admecMarshall` attaque, son
passif `ControlEdict` fait apparaitre un `admecSmnVanguard` sur l'anneau-1 du CASTER. Il ne
discriminait pas ce terme -- son montage est un 1v1, aucun des trois porteurs n'y est. On ajoute
**`ultraTigurius`** (`PsychicFortress` 1000, HERO **du pool** : ni relique, ni injection
catalogue) et on le place ADJACENT au Marshall.

#### La geometrie est CHERCHEE avant d'etre montee

`ElevationUtility` vaut `10 x elev` : deux crans d'elevation annulent exactement le `+20`. On
calcule donc, sur le `boardGraph` du runner (et non sur le dump versionne, qui n'en a ni la forme
ni la metadata), toutes les configurations `(C, P, ennemi)` ou le terme RENVERSE l'argmax :

| critere | compte |
|---|--:|
| geometries ou le `+20` renverse l'argmax | **92** |
| ... a **DOUBLE ecart strictement positif** | **51** |

⚠ **Le double ecart est ce qui separe cette confrontation de celle qui laisse `#271-r1` ouvert.**
`strict` = de combien X bat Y **sans** le terme ; `marge` = de combien Y bat X **avec**. Un
`strict == 0` laisserait un tie-break natif FIXE produire le meme renversement -- rien ne serait
tranche. Un `marge == 0` ferait trancher l'argmax stable APRES, le terme n'ayant fait qu'egaliser.
Le premier tri essaye ne retenait que `strict`, et rendait des candidats a `marge = 0` ; le tri
final maximise `min(strict, marge)`.

#### Les trois bras

Geometrie retenue : `C = t13` (Marshall), `P = t14` (Tigurius), ennemi `t12` ; `strict = +10`,
`marge = +10`.

| bras | tuile de spawn |
|---|---|
| port **SANS** le terme (`PsychicFortressNonOwnerPlaybook` neutralise) | **t22** |
| port **AVEC** | **t23** |
| **NATIF** | **t23** |

Le bras SANS neutralise la **seule methode**
`PsychicFortressNonOwnerPlaybook.calculate_movement_utility_in_steps`, pas l'entree de registre :
la question posee est << ce terme-la porte-t-il le resultat ? >>, pas << le cablage tient-il ? >>.
Sans ce bras, un accord natif/port ne distinguerait pas les deux.

Livre : `probe_271r5_spawn_non_owner_live.py` (etape 1 offline `--geometrie-seule`, etape 2 live
a N essais) et `tests/engine/runner/test_271r5_spawn_non_owner_live.py` (4 tests, dont le temoin
NON NUL -- un accord entre deux listes vides passerait pour un vert).

#### Le rouge de `master` que cette fiche annoncait est REPARE

`test_placement_sort_rng_live.py::test_utility_sort_scenario_really_discriminates` rougissait en
`CONTRE-CONTROLE INERTE` (`tuiles M0 [26] == live [26]`). La cause n'etait pas la geometrie mais
le **modele M0 lui-meme** : ce n'est pas l'identite, c'est `sorted(tiles)` **puis un TIRAGE** des
que le pool depasse 1. `_discriminating_caster_tile` rendait la PREMIERE tuile qui << desaccorde >>,
laquelle laissait un pool de **deux** candidats -- donc une chance sur deux que M0 tombe sur la
meme tuile que le tri. Il l'a fait. Le rouge n'accusait ni le port ni le harnais : il accusait le
tirage.

Correctif : la selection maximise desormais le nombre de candidats **strictement moins bons que
le maximum**, c'est-a-dire le nombre de tuiles que M0 peut tirer et qui le feraient diverger. La
probabilite de coincidence passe de `1/2` a `1/len(pool)`. Elle ne devient pas nulle, et **ne
peut pas l'etre** : M0 tire, donc aucune geometrie ne lui interdit de tomber juste. C'est le prix
d'un contre-controle bati sur un modele STOCHASTIQUE, et il est desormais ecrit au site.
Mesure apres correctif : **22 passed** sur le fichier entier.

### 7.7 -- `#271-r8` : l'ARGMAX de la face ATTACK reste NON CONFRONTE, et l'obstacle est PIRE que ce que la fiche disait

**Non traite le 2026-08-08 ; ce qui suit est ce qui a ete ETABLI, pas une hypothese.**

La fiche pose la condition de bascule ainsi : << faire basculer le choix du jeu exige un etat ou
le terme **(10)** depasse l'ecart entre les deux meilleures paires >>. Relu au site du port,
`engine/playbook/base.py::calculate_utility_from_predictions` :

```python
trig += triggered_abilities_non_owner_attack_utility(ctx, ctx.uid, ev.target, caster_tile)
if trig:
    ua += (-1.0 if ev.friendly else 1.0) * ev.probability * trig
```

Le terme est donc **multiplie par `ev.probability`** avant d'entrer dans l'utilite d'action --
mirror du natif, qui somme `CalculateUtilityFromDamageEvent` = `prob1 x prob2 x composite`.
L'ecart franchissable n'est pas `10` mais **`prob x 10`**, et il est donc **strictement plus
petit des que la prediction n'est pas certaine**. La condition de separabilite est plus dure que
la fiche ne l'ecrit ; toute reprise doit partir de la, sous peine de chercher une fenetre de
10 qui n'existe pas.

⚠ **La seconde voie de la fiche est PERIMEE et ne doit pas etre suivie** : elle propose << le
canal des hooks par-tuile >>, dont les RVA sont celles du build `gqfc5mff6c` (desinstalle), et
elle exigerait de toute facon une fenetre de reinject -- ce qu'un agent ne fait pas.

Reste donc la voie 1 : chercher un etat ou les deux meilleures paires (cible, tuile) sont
separees de moins de `prob x 10`. Elle n'a PAS ete essayee dans cette tranche : elle demande de
scorer, cote port, TOUTES les paires candidates du composite `Damage(35)` pour en lire l'ecart --
c'est-a-dire un balayage d'utilite d'action que le probe actuel (`probe_271r4_face_attack_live.py`,
qui n'evalue QUE la feuille) ne sait pas faire. `WayOfTheShortBlade` (1500) est dans le meme etat,
avec en plus une injection catalogue a monter (`tauFarsight` hors pool).

**Etat : NON CONFRONTE.** Ce n'est pas << non separable >> -- aucun montage n'a ete essaye, donc
rien n'autorise a le conclure.

### 7.8 -- `#271-r1` : la voie (b) est OUTILLEE et le blocage annonce est LEVE -- mais les deux regimes s'EXCLUENT

**Non ferme le 2026-08-08. Ce qui suit est mesure, et il DEPLACE la cause.**

#### La voie (a), elargie, reste sterile -- et la cause n'etait pas la geometrie

Balayage `--nonowner necroWarden,orksNob --gap-min 1` sur **4 boards** (`MC1_67`, `C4_09`,
`MC1_31`, `C1_09`) x **2 seeds** x pas **0,2,4,6,8** = **80 montages** : **0 concluant**.
Ventilation des refus, qui n'avait jamais ete faite :

| cause | compte |
|---|--:|
| **action deja consommee** (mek et/ou mover) | **38** |
| aucune tuile ou poser le Big Mek voisin de T2 seule | 14 |
| autres | 28 |

La cause DOMINANTE n'est donc pas geometrique : c'est que `step2_nonowner` laisse l'IA jouer
`pre_steps` chunks pour etaler les unites, et que l'IA CONSOMME au passage l'action du Big Mek ou
du mover. Les deux moities du montage se contredisent -- a `pre_steps = 0` le Big Mek, ne au fond
du spawn, n'ATTEINT aucune tuile utile ; des qu'on avance, il n'a plus d'action.

#### La voie (b) est livree : `--preplace`

`step2_nonowner_preplace` pose le mover et le Big Mek par `--place` **AU BUILD** -- donc sans
consommer d'action et sans dependre de la portee de deplacement. C'est litteralement le
<< pre-positionner le Big Mek DEVANT ses allies >> de la fiche. Elle **fonctionne** : le blocage
<< action deja consommee >> tombe a **0**, et la paire a **ecart STRICT** que la voie (a)
n'atteignait jamais apparait des le premier montage utile --

    mover@(4,4) mek@(4,5) | T1=(6,5) (-171.00) T2=(5,6) (-195.00) ecart = 24.00

#### Mais le blocage RESIDUEL est ailleurs, et les deux regimes s'excluent

| regime | paire a ecart STRICT | proposition native |
|---|---|---|
| **pres des ennemis** (30 positions x 2 movers) | **oui** (24 mesure) | **ATTAQUE** -> tuile issue du sweep `ActiveAbilityActionGenerator`, hors du `UnitMovement(6) = Tile(7) + MinDist(16)` que le probe modelise |
| **loin des ennemis** (`--loin 6`, 14 positions x 2 movers) | **non**, 14/14 | move PUR |

Et meme dans le premier regime, l'ecart trouve (**24**) **depasse le terme** (10 pour un ami
non-Ork, 20 pour un Ork) : `OFF == ON`, aucune bascule.

**Le montage cherche doit donc satisfaire TROIS conditions a la fois** -- ecart T1-T2 dans
`1..terme`, Big Mek voisin natif de T2 **seule**, et mover hors de portee d'attaque -- et les
deux dernieres tirent en sens INVERSE : eloigner le mover des ennemis pour obtenir un move pur
l'eloigne aussi des zones ou le relief cree des ecarts de composite exploitables.

**Etat : NON CONFRONTE, cause DEPLACEE.** Ce n'est plus << le montage n'a pas ete trouve >> mais
<< les deux regimes s'excluent sur les boards essayes >>. Piste pour une reprise, la seule qui
reste ouverte sans nouveau capteur : balayer `--preplace --loin <n>` sur beaucoup de boards en
faisant VARIER `--loin` (l'optimum est entre les deux regimes), plutot que d'ajouter des pas.
L'outil est en place et ventile desormais ses refus, ce qui rend ce balayage lisible.

### 7.9 -- `#271-r1` : ma propre reprise etait FAUSSE ; la decomposition par etage donne la cause

**2026-08-08, second passage.** Le §7.8 designait la suite : << varier `--loin`, l'optimum est
ENTRE les deux regimes >>. **Cette piste est REFUTEE par la mesure.**

`--loin 2,3,4,5` sur `MC1_67`/777, 10 positions par distance : la cause est **UNIFORME**, 10/10
aux quatre distances, et c'est toujours << pas de paire >> -- **jamais** << proposition NON
PURE >>. Il n'y a pas de compromis de distance a trouver.

#### Ce qui a debloque le diagnostic : separer les deux causes que << pas de paire >> confondait

  * **(a)** l'ECART T1-T2 est-il a portee du terme ?
  * **(b)** parmi les tuiles a portee, le Big Mek peut-il etre voisin NATIF de T2 **SEULE** ?

| board (loin=4) | mover | ecart T1-T2 (min / median / max) | (a) hors de portee | (b) voisinage intenable |
|---|---|---|--:|--:|
| `MC1_67` | `necroWarden` | 24.0 / 24.0 / 85.0 | 4 | 6 |
| `MC1_67` | `orksNob` | 24.0 / 24.0 / 24.0 | 0 | **10/10** |
| `MC1_31` | `orksNob` | 115.0 / 115.0 / 115.0 | **6/6** | 0 |
| `C1_09` | `orksNob` | 115.0 / 115.0 / 115.0 | **6/6** | 0 |
| `C4_09` | `orksNob` | 10.0 / 100.0 / 100.0 | 5 | 1 |

#### La cause est STRUCTURELLE, et elle est la MEME que celle de `#271-r8`

L'ecart entre les deux meilleures tuiles vaut **24 en minimum comme en mediane** sur `MC1_67`, et
**100-115** ailleurs -- quand le terme vaut **au mieux 20** (ami Ork ; 10 pour un non-Ork). Le
composite `UnitMovement(6) = Tile(7) + MinDist(16)` est **domine par `MinDist`**, dont le PAS
entre tuiles voisines depasse le terme.

C'est exactement le diagnostic de `#271-r8` sur la face ATTACK (dominee par `DamageDealt` et
`KillUnit`, ~[0,100]). **Les deux faces butent sur la meme cause** : un terme de 10-20 dans un
composite dont les paliers valent 24 a 115. Ce n'est pas un defaut de montage, et aucun nombre de
positions supplementaires n'y changera rien.

⚠ **Defaut du filtre, trouve au passage** : `MAX_GAP = 25` est plus PERMISSIF que le terme reel.
Le probe annoncait donc << franchissable >> des paires que le terme ne peut pas renverser -- les
ecarts de 24 d'`orksNob` passaient le filtre et etaient comptes en << voisinage intenable >>,
ce qui deplacait l'accusation. La sortie imprime desormais l'ecart **et** le terme cote a cote.

#### La reprise, re-designee sur la mesure

Ce n'est plus une question de distance ni de nombre de positions : il faut un board dont le PAS
de `MinDist(16)` soit **inferieur a 20**. Le probe mesure cette distribution a **cout nul** a
chaque position (min / median / max), donc un balayage large de boards rend un **critere de
selection** au lieu d'un chapelet de << NON CONCLUANT >>. Sur les quatre boards essayes, aucun
ne descend sous 24 -- mais quatre boards sur 675 ne sont pas une conclusion.
