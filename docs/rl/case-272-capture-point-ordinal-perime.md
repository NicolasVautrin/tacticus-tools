# case-272 — la feuille `CapturePoint` rendait 0.0 : le test n'atteignait pas la feuille qu'il nomme

**Question posée.** La feuille `CapturePointTileUtility` est-elle censée rendre
`heroes_on_capture_points` (300) dans le montage de
`test_trait_gates_dynamic_live.py::test_in_battle_granted_trait_flips_the_capture_point_gate` ?

**Réponse mesurée : OUI — et le port l'implémentait déjà fidèlement.** Le rouge ne venait ni du
gate de trait, ni de la table de poids, ni de la feuille : le test indexait le registre des feuilles
par un **ordinal d'enum figé en dur**, périmé depuis la MAJ de build. Il mesurait
`MoltenForm_TilesUtility` en croyant mesurer `CapturePointTileUtility`.

Rejouer : `python scripts/python/probe_272_capture_point_gate.py` (offline, 4 contrôles) ;
`--live --board <id> --seed <s>` ajoute la mesure du co-gate `is_territory` en bataille.

---

## 1. Ce que la feuille native exige en entrée (le décompilé)

```
IdunBattle.AI.Utilities.CapturePointTileUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext
    x = Fix64(0)
    if (case.position.MainTile == null) yield break            // rien d'émis
    flag = (case.unit == null) ? (case.parent != null)          // `get_IsSpawning` INLINÉ (case-205)
                              : HasTrait(case.unit, 0x2) || HasTrait(case.unit, 0xd)
    if (IdunBattle.Entities.TileExtensions$$IsTerritoryTile(case.position.MainTile))
        x += GetUtilityValue(flag ? <summons_dislike_capture_points>
                                  : <heroes_on_capture_points>)
```

Trois entrées, donc, et **trois seulement** : la tuile principale du `case`, son octet territoire
(`TileComponent+0x2e`), et le couple de traits du sujet. Le montage du test les fournit toutes
(`meta={"is_territory": True}`, sujet sans trait 2/0xd, `is_spawning=False`) ⇒ **300 attendu**.

`engine/utilities/tile.py::CapturePointTileUtility.evaluate` est ce mirror, à l'ordre des deux
gates près (sans effet observable : aucun des deux n'a d'effet de bord). Table de vérité confrontée
aux poids BC réels par `probe_272` étape 2, **6/6 conformes**.

## 2. La cause réelle — un ordinal d'enum figé, périmé par la MAJ de build

`test_trait_gates_dynamic_live.py` naissait (`883668e6`, 2026-07-29) avec :

```python
CAPTURE_POINT = 24                       # UtilityType.CapturePoint
...
leaf = TILE_LEAVES[CAPTURE_POINT][1]
```

Exact à l'écriture. Périmé par `fe5b9245` (#252) : la MAJ de build **insère `AttackTile` en 8** et
décale de +1 les 59 membres suivants — `CapturePoint` **24 → 25**, et **24 devient `MoltenForm`**.
`TILE_LEAVES` étant keyé par MEMBRES depuis #254, l'index `24` rend donc `MoltenForm_TilesUtility`,
qui gate sur `unit_triggered_abilities` (1221) : elle rend **0.0 sur n'importe quel `meta`**, sans
erreur ni `KeyError`.

Mesure (probe_272 étape 1, re-dérivée) :

| index | feuille rendue | `evaluate(meta.is_territory=True)` |
|---|---|---|
| `24` (l'ancien ordinal) | `MoltenForm` / `MoltenForm_TilesUtility` | **0.0** — le rouge, à l'identique |
| `UtilityType.CapturePoint` (=25) | `CapturePoint` / `CapturePointTileUtility` | **300** |

Le cliquet de #254 protège le **registre** (chaque clé doit valoir `UtilityType.<name>`) mais ne
regardait pas les **consommateurs**. C'est par là que le défaut est rentré.

## 3. Correction

* le test prend le **MEMBRE** (`CAPTURE_POINT = UtilityType.CapturePoint`) ;
* il porte une **garde d'identité** : la feuille confrontée doit être `CapturePointTileUtility` et
  son `UTILITY_TYPE` doit valoir `UtilityType.CapturePoint`. Un ordinal périmé ne peut donc plus
  rendre une autre feuille en silence — il échoue en nommant la feuille reçue ;
* `probe_272` ferme les deux formes du patron sur tout `scripts/python` : index littéral de
  `TILE_LEAVES`, et constante-ordinal annotée `= <int>  # UtilityType.<Name>`. **0 site restant** ;
* `probe_175_tile_leaf_unit_traits.py` dérive désormais ses ordinaux des membres — sa table
  affichait `CapturePoint(24)`, `PowerUp(26)`, `DespoiledGround(28)`… c'est-à-dire l'étiquette de
  la feuille **voisine**. Cosmétique (son indexation passe par `TILE_LEAF_IDS`, des membres), mais
  c'est le même mensonge qui a coûté ici.

**Aucune ligne de moteur n'a changé** : ni `engine/utilities/tile.py`, ni le substrat de traits
(#225), ni les poids.

## 4. Validation

* `test_trait_gates_dynamic_live.py` : **4 passed**. La mesure discriminante est retrouvée telle que
  §6 de `case-225` l'annonçait — `u77 eldarMauganRa`, kit `HeavyWeapon/Hero/Overwatch/Terrifying`,
  `unit_traits (16,34,1001,1003,1006) -> (2,16,34,1001,1003,1006)`, **CapturePoint 300 → −300**
  (changement de SIGNE). Avant correction : `0.0` sur la branche de contrôle.
* Non-régression : `test_tile_leaf_unit_traits_live.py` (famille Tile(7)/traits) — **8 passed** au
  total sur les deux fichiers.
* `probe_272` offline : enum du port ↔ table VERSIONNÉE du build **0 divergence** sur 68 membres,
  table de vérité 6/6, 0 ordinal figé restant.

## 5. Portée réelle de la feuille — et ce qui n'est PAS couvert

Le test force `meta={"is_territory": True}` : c'est un **jeton**, et `probe_272 --live` mesure
pourquoi il n'y a pas d'alternative. Sur **MC1_67/777 (63 tuiles)** et **C4_09/31337 (70 tuiles)** :
**`tileMeta.isTerritory` = 0 partout**. Le co-gate ne mord donc jamais en bataille sur les seeds
arène (`RuleSet: null`), et la feuille y reste **inerte** — ce que `tile.py` annonçait déjà
(« ACTIF #175, mais 0 tuile territoire hors ruleset Territories »), désormais mesuré.

Non couvert, nommé :

1. **Aucune exécution de bout en bout de la feuille en bataille** — il faudrait une BC en ruleset
   Territories. Tant qu'elle n'existe pas dans le harnais, la table de vérité de `probe_272` est la
   borne de ce qu'on peut affirmer.
2. **`runner_tile_leaf_ctx` ne produit pas `is_territory_by_pos`** (résidu déjà nommé dans
   `tile.py`) : sur le chemin RUNNER, `apply_tile_attributes` ne peut poser `meta.is_territory` que
   si l'appelant fournit la carte lui-même — c'est ce que fait l'étape 4 du probe. Le chemin
   DÉCISION, lui, la construit (`engine/ai/context.py::_tile_attribute_maps`).
3. **Les ordinaux `UtilityType` cités dans les docs antérieures à `fe5b9245`** (backlog, case-175,
   case-205…) sont décalés de +1 au-dessus de 7. Rien d'exécutable n'en dépend ; les lire comme des
   étiquettes historiques, et se fier au nom, jamais au nombre.
