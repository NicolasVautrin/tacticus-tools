# #943-r7 (clôture) — le `BLOCAGE: seeding` désignait un foyer partagé ; il n'y avait qu'une clé

Onze sites `LISTE_STOCKEE` restaient nus, sous une raison écrite noir sur blanc : « les câbler exige
de PUBLIER `elevations_by_pos`/`adjacent_neigh_by_pos` en amont, dans `damage_model.
attacker_modifiers` **ET** dans la face PRÉDICTION — un foyer partagé bien au-delà de l'adjacence ».

**Re-mesuré site par site : la phrase est vraie pour zéro d'entre eux.** Le gisement passe de
**9 → 0** (`etape6`, ventilation `GEOMETRIQUE=5, LISTE_STOCKEE=0`), et la tolérance de l'étape 2
passe de **3 → 0**.

## 1. Le rouge de `master` : `chalice_of_baal.py:288` — CÂBLÉ, pas toléré

`c3c04e73` (#1010) a introduit un `_adjacent` en `hexgeo.distance == 1` sous une docstring qui
déclarait `BattleQuery$$AreEntitiesAdjacent`. Sa prose revendiquait le résidu **#271** (la porte
d'élévation) ; **ce n'était pas la même cause** — le décompilé donne les DEUX étages :

```
BattleQuery$$AreEntitiesAdjacent(e1, e2) = MovementUtil$$AreTilesAdjacent(GetTiles(e1), GetTiles(e2))
MovementUtil$$AreTilesAdjacent(t1, t2)   = (|elev(t1) - elev(t2)| < 2)
                                         & (t1 == t2 || ConnectivityComponent$$IsNeighbour(t1, t2))
```

soit l'appartenance à la liste **STOCKÉE** *et* la porte, en termes séparés (`iVar7 < 2 & bVar3`).
Le canal était atteignable : `_adjacent(state, …)` reçoit l'ECS, donc `State.board`. Câblé sur
`engine.battle_query.are_entities_adjacent` (court-circuit d'identité compris, #433-r1).

**Pourquoi `adjacent_neigh_by_pos` est le substrat EXACT de cette conjonction** : le champ
`neighbours` du `boardGraph` est `connectivity ∩ {|dElev| < 2}` ; l'intersecter une seconde fois par
la même porte est idempotent, donc `is_adjacent(canal capté)` ≡ `(|dElev| < 2) & IsNeighbour`.

## 2. Les onze — ce que la re-mesure a trouvé

| ce qui était écrit | ce qui est mesuré |
|---|---|
| `imperative.py` ×2 (dégât), `icon_of_obstinacy.py` (aura) — `BLOCAGE: seeding` | leur agrégateur `aura_attack_damage_bonus_from_allies` publiait **DÉJÀ** `ctx["board"]` sur ses **deux** faces. **ZÉRO seeding** |
| `hits.py` ×4, `traits/combat.py` — `BLOCAGE: seeding` | **UNE clé** (`board`) ajoutée au board de coups et aux ctx d'`additional_hits`, sur les deux faces ; les constructeurs tenaient déjà `state.board` / `scene.board`. Clé **additive** dans un dict, pas un canal à construire |
| `triggers/loki/icon_of_obstinacy.py` — « COUPLE NON FERMABLE » | le couple se ferme dès que sa jumelle est câblable : les **deux** expressions du même `AIconOfObstinacyAbility$$GetAffectedUnits` le sont dans le **même commit** |
| `momentum.py` — `BLOCAGE: capteur` | **SUBSTRAT AUTRE**, et c'est le seul dont l'analyse tenait. Mais l'étiquette est fausse : le capteur EXISTE (`rpc-board.ts` publie `connectivity` depuis #448-r1-r1-r1-r1-r2) |

S'y ajoutent les **trois** sites de `GEOMETRIE_NUE_TOLEREE`, dont la justification (« réparer ICI
seulement serait un fork ») tombait avec la famille : `aura_selectors.py::adjacent_friends_including_owner`
(aucun blocage propre — il reçoit l'ECS, face unique), `loki/icon_of_obstinacy.py` (la jumelle
ci-dessus), `loki/terrors_lament.py::_adjacent_enemy_melee` (« ce ctx d'aura ne publie aucun
board » : sur ses **quatre** call-sites, deux passent le board de coups et deux le ctx défenseur).

## 3. `momentum` — le seul substrat DIFFÉRENT, lu au décompilé

`TileExtensions$$IsNeighbourOf(targetTile, GetMainTile(caster))` (l'ordre est LU dans
`UnstoppableMomentumReworkedAbility$$ExecuteBehaviourStep`) énumère `ConnectivityComponent+0x10` de
la tuile **CIBLE** et compare l'id de la tuile du caster — **sans aucune porte d'élévation**. Ni
`is_adjacent` ni `neighbours_native` ne conviennent : les deux ajouteraient la porte. Câblé sur
`Board.neighbours_connectivity`, **tri-état** — canal absent ⇒ repli géométrique nommé.

⚠ Ce champ n'existe **qu'en live** (`InitializeConnectivityOperation$$Execute` le construit en
bataille ; `data/boards/*.json` sont des ASSETS). L'inclusion mesurée est
`neighbours ⊆ connectivity ⊆ géométrie`, donc le câblage est **strictement restrictif**.

## 4. La DIRECTION, lue et non devinée

`IsAdjacentAbilityTrigger$$.ctor` range `selector1 → +0x20`, `selector2 → +0x28`, et
`ShouldTrigger` appelle `AreEntitiesAdjacent(<+0x20>, <+0x28>)` ; `AreTilesAdjacent(t1, t2)` lit
`connectivity(t1)`. Le champ `neighbours` étant **brut** (ni trié ni symétrisé), l'axe est
observable — et `hexgeo.distance`, symétrique, ne pouvait pas l'exprimer. D'où, site par site :
`AdjacentFriends(Owner)` ⇒ `is_adjacent(owner, bénéficiaire)` ; `AdjacentUnits(Target)` de
`GetStuckIn` ⇒ `is_adjacent(cible, unité)` (le 2ᵉ argument du call-site est `DSLSelectors+0x60`,
la CIBLE) ; `AdjacentEnemies(<alliés filtrés>)` de `LegendaryCommander` ⇒ `is_adjacent(allié, cible)` ;
`IsAdjacent(Caster, Owner)` de `TerrorsLament` ⇒ `are_entities_adjacent(att, owner)`.

## 5. Effet sur le cliquet

```
etape 1 : call-sites gates par l'elevation   153 -> 166   (0 sans voisinage, inchange)
etape 2 : mirrors declares a geometrie nue     6 ->   2   (0 sans acces au canal ; TOLERANCE 3 -> 0)
etape 3 : fonctions qui touchent le canal    194 -> 205   (0 derivation morte, inchange)
etape 6 : geometries nues sans canal          18 ->   5
          ventilation   GEOMETRIQUE=5, LISTE_STOCKEE=9 -> GEOMETRIQUE=5, LISTE_STOCKEE=0
VERDICT : FAIL (1) -> PASS
```

L'**étape 5** est passée au rouge d'elle-même après le câblage des trois derniers foyers
d'`AdjacentFriends` : sa suspension était devenue le vice. `AdjacentFriends` est **ARMÉ**, et
`NATIFS_LISTE_STOCKEE_SUSPENDUS` est désormais **vide** — 4ᵉ sortie par la porte du haut.

**Trois gardes ont rougi, tous pour la bonne raison, et ont été RÉÉCRITS, pas retirés** :
`test_la_JUSTIFICATION_de_la_tolerance_se_re_mesure` (ses trois témoins venaient d'être câblés — il
prescrivait lui-même « retire-la » : c'est fait, et il porte désormais une **conditionnelle**, pas
un seuil) ; `test_la_tolerance_MORD_quand_on_la_vide` (lisait le registre RÉEL, dont le cardinal est
tombé à 0 — devenu **synthétique**, donc indépendant de l'occupation) ;
`test_les_natifs_SUSPENDUS_le_sont_pour_une_raison_qui_se_MESURE` (son `assert registre non vide`
exigeait **qu'il reste un vice** ; remplacé par le cran qui empêche « vide » de vouloir dire
« oublié » : les 4 natifs sortis doivent être ARMÉS).

## 6. Validation

**Offline** — `tests/engine/test_943r7_faces_jumelles_adjacence_offline.py`, **55 tests, 0 skip**
(§4 neuve : les onze derniers). Régime discriminant : deux tuiles à distance hex **1** non voisines
dans la liste stockée. **Contre-épreuve, arbre témoin détaché sur `401b0ae9`** : **15 des 55
échouent** — exactement les discriminants ; les 40 verts sont les cas « arête portée » (verdict
inchangé), les replis sans canal (comportement d'avant) et les huit sites de #943-r7 déjà câblés.

Un garde **dérivé** couvre le mode de défaillance propre à cette tranche — un ctx qui ne publie pas
la clé a l'**allure** d'un câblage complet et le **comportement** d'avant : il part des méthodes
d'effet réellement câblées (contenu, pas nom), remonte à leur agrégateur dans
`entities/effects/__init__.py`, puis à tous ses call-sites, et distingue **PUBLIEUR** de **RELAIS**
(une fonction qui répand un de ses propres paramètres transmet un ctx monté ailleurs). Contre-épreuve
jouée : retirer `"board"` d'une seule face le fait rougir en nommant la face.

**Cliquets** : `probe_433r4r1r4r2_neigh_channel_wired` (PASS), `test_433r4r1r4r2r1r1_derivation_morte_offline`
(51 tests), `probe_433_r1_identity_shortcircuit` (rc 0 — l'arête `entities.traits.combat →
engine.battle_query` ne referme aucun cycle : `battle_query` n'importe que `hexgeo` + `.hex_corner`
et s'interdit `engine.entities`).

### Ce qui n'est PAS couvert

* **NON CONFRONTÉ — jeu non lancé.** Aucune mesure live n'a pu être prise (process du jeu absent,
  drain armé). Restent dus : (a) le champ `connectivity` du `boardGraph` d'un runner réel, que le
  board témoin **fabrique** — on exerce le PRÉDICAT, pas la capture ; (b) le comportement observable
  des onze abilities en bataille. Résidu **#943-r7-r1**.
* **Deux mesures DISJOINTES** (héritées) : offline, 8,9 % des arêtes des 779 boards versionnés
  tombent par la seule porte `|dElev| ≥ 2` ; live, les 22 arêtes de `MC2_60` tombent par
  l'ÉNUMÉRATION. Ce fichier exerce l'énumération ; la porte a ses gardes dans
  `test_943r4_adjacence_cablee_offline.py`.

## 7. Résidu ouvert

* **#943-r7-r1** — la confrontation LIVE du substrat `connectivity` de `momentum` et du
  comportement des onze sites câblés.
