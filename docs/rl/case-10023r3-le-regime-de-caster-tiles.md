# #10023-r3 — `ReturnsOnlyUnits` : le discriminant est le NŒUD, et il retourne #10023

**Verdict : le mirror portait le MAUVAIS régime, et les deux faces portaient la MÊME erreur.**
Build `t6dpr4k06g`.

---

## 1. Ce que le résidu demandait, et ce qui est mesuré

`IdunBattle.DSL.TargetsSelector$$SelectAllUnits`, relu verbatim :

```
lVar8 = <slot 0x17 = Select>(this, entities);
cVar5 = (**(code **)(*(longlong *)this + 0x278))(this, ...);   // slot 20 = get_ReturnsOnlyUnits
if (cVar5 == '\0') { foreach (e in lVar8) if ((u = SelectUnit(this,e,sel)) != null) out.Add(u); }
return <lVar8 TEL QUEL si la porte est VRAIE, sinon la liste resolue>;
```

Les slots viennent de **deux sources indépendantes** qui concordent :
`data/symbols/<build>/metadata/interface_slots.tsv` donne `TargetsSelector 19 get_ReturnsOnlyTiles`,
`20 get_ReturnsOnlyUnits`, `23 Select` ; et la vtable IL2CPP commence à `klass+0x138` par entrées de
`0x10`, donc `0x138 + 20*0x10 = 0x278` — exactement l'offset du binaire.

**La propriété n'est pas résoluble par la table des symboles** : `frida/methods.tsv` est indexée par
ADRESSE et IL2CPP déduplique les corps triviaux — elle porte **2** `get_ReturnsOnlyTiles` pour tout
le binaire et **aucun** `get_ReturnsOnlyUnits`.

| slot | valeur mesurée | comment |
|---|---|---|
| `<DSLSelectors+0x60>` = `Target` | **VRAI** | 19 casts de `1201 SquigMine` (#10023-r1) |
| `<DSLSelectors+0x58>` = `CasterTiles` | **VRAI** | ce résidu, ci-dessous |

## 2. La mesure — `1094 TheLantern` sur `deathBossMortarion`

`probe_10023r3_caster_tiles_regime_live.py`. Board `GB_Mortarion_05`, seed `777`, cible **`(1,7)`**
(l'une des **2** tuiles que `abilityTargets.fromHere` déclare légales).

**Le caster SEPT-HEX n'arrive PAS par `--p-units`** : `SetupGameOperation$$AddBossUnit` est la seule
voie qui pose un porteur sur une LISTE de tuiles, `AddPredefinedUnits` n'en pose qu'UNE (#10018-r1).
Monter Mortarion par le roster donnerait un caster mono-hex, sur lequel les deux régimes coïncident
— le régime dégénéré exact qui a empêché #10023 de trancher. Le montage écrit donc `BC.BossUnit`
dans une COPIE du seed BC. Mesuré : `feet = [(4,8),(3,9),(4,9),(5,9),(5,8),(4,7),(3,8)]`.

⚠ **La main tile est `feet[0]`, pas `pos`** : `decisionView.units[].pos` vaut `(3,8)` — le DERNIER
pied projeté (`runner/snapshot.py::_load_feet`).

| | aire | verdict |
|---|---|---|
| NATIF (tuiles `1195 TheLantern_PendingTarget`) | **9** | — |
| régime « retranche l'empreinte » | 9 | `B\natif = natif\B = []` |
| régime « retranche la main tile seule » | 10 | `A\natif = [(3,8)]` |

⇒ **`CasterTiles.ReturnsOnlyUnits == VRAI`.** L'aire entière concorde, pas une tuile isolée.

### L'explication concurrente, écartée des DEUX côtés

Un pied absent s'expliquerait aussi par un filtre d'**OCCUPATION** — les pieds sont les seules
tuiles occupées à distance 2 de la cible.

- **Décompilé** : `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` n'appelle
  `TileExtensions$$IsEmptyOrSteppable` que sous le flag `onlyMovable`, que `TheLanternAbility` passe
  à `0` ; `TileUtil$$IsTileValidForList` ne lit que le mur (`tileComponent+0x41`), `IsWalkable` et —
  sous `checkElevation`, ici à `0` — l'écart d'élévation. **Aucun test d'occupant.**
- **Mesure** : bras de contrôle — une unité alliée posée sur `(2,8)`, tuile VIDE de l'aire au même
  étage (`ring2 & cring1`), y **reste marquée** après le même cast.

## 3. Le port

`engine/dsl/base.py` :

- `TargetsSelector.RETURNS_ONLY_UNITS = True` — le défaut est la **mesure**, pas une commodité ;
- `_main_tile_of(entity, …)` mirrore les **trois** branches de `EntityExtensions$$GetMainTileId`
  (unité → `feet[0]`, entité à pieds → `set[0]` récursif, tuile → **elle-même**) ;
- `_main_tiles(origin, board, units, only_units)` boucle par ENTITÉ ; le régime `False` (jamais
  déclaré par aucun nœud) résout d'abord l'occupant, donc une tuile VIDE y disparaît ;
- `returns_only_units(node)` lit la propriété du NŒUD. Call-sites : `accessors.SurroundingTiles`
  (`self.center`) et `_within(center_node=…)` (4 nœuds `Surrounding*`).

**L'effet correctif** : le foyer retranchait `_origin_tiles(origin, board)[:1]`, donc UNE tuile sur
une empreinte de sept. Invisible sur toute origine à un élément — **34 des 35** instanciations
recensées.

**La face DÉCISION aussi** : `playbook/noncomparable/the_lantern.py::_ring` excluait `feet[:1]`.
#10023 avait aligné la face COMBAT sur elle ; il fallait l'inverse.

## 3bis. Le probe est un CLIQUET, et il a fallu le rendre tel

Écrit comme un simple relevé du NATIF, `probe_10023r3_caster_tiles_regime_live.py` rendait **ROUGE
quel que soit l'état du port** — y compris après l'avoir corrigé. Un cliquet qui reste rouge sur du
code juste se fait désarmer. Il confronte donc d'abord l'aire du **MIRROR**
(`the_lantern_area_selector` évalué sur l'état live rejoué offline) à celle du natif ; la
ventilation A/B reste comme **diagnostic** du régime.

- **VERT mesuré** : mirror = natif = les mêmes **9** tuiles.
- **CONTRE-ÉPREUVE REJOUABLE** (`--muter-port`, qui remet `_origin_tiles(…)[:1]`) : le mirror rend
  **10** tuiles, `port\natif = [(3,8)]` → **rc 1**. Le cliquet mord exactement sur la faute qu'il
  garde. La mutation patche les **DEUX** liaisons (`accessors.py` importe `_main_tiles` en forme A,
  donc patcher le seul foyer laisserait le call-site intact et la contre-épreuve serait vacante).

## 3ter. `#459` disait l'INVERSE — et la résolution n'est ni « lui » ni « moi »

`test_459_tile_accessors_offline.py::test_surrounding_excludes_only_the_main_tile` assertait
`SurroundingUnits(TargetTile(), 1)` == `[tgt]` sur une origine multi-hex, docstring à l'appui :
« retrancher toute l'empreinte ici serait une seconde erreur, pas une correction ». Il est tombé
sur ce correctif. **Les deux ne pouvaient pas être vrais.**

### Ce qui tranche : la metadata, pas un arbitrage

`global-metadata.dat` est indexée **par TYPE**, donc la déduplication de CODE qui aveugle
`frida/methods.tsv` ne l'atteint pas. Lecture (`il2cpp_metadata.type_methods`) :

| type | méthodes DÉCLARÉES | override `get_ReturnsOnly*` |
|---|---|---|
| `IdunBattle.DSL.TargetsSelector` | 27 | déclare les **quatre** |
| `CasterTileSelector` | `.ctor`, `Select` | **aucun** |
| `TargetTilesSelector` | `.ctor`, `Select` | **aucun** |
| `UnitsMainTilesSelector` | `.ctor`, `Select` | **aucun** |
| `AdjacentTilesSelector` | 4 | `ReturnsOnlyTiles`, `ReturnsOnlyUnique` |

`CasterTileSelector` et `TargetTilesSelector` dérivent toutes deux de `TargetsSelector`, même taille
(24), et **n'overrident rien** : elles héritent de la MÊME valeur. La mesure live faite sur l'une
vaut donc pour l'autre — et c'est **lu**, plus supposé.

### La faute de `#459` est dans son MONTAGE, pas dans son intention

Son raisonnement — « `Tiles(origin)` = `GetMainTile` par ENTITÉ → UNE SEULE tuile » — n'est vrai que
si l'origine n'énumère **qu'une** entité. Or `#459` établit lui-même, deux tests plus haut
(`test_target_tile_returns_the_whole_footprint`), que `TargetTile()` en rend **TROIS**. Le fichier se
contredisait.

**La réciproque qu'il gardait est VRAIE — elle vit sur l'origine en domaine UNITÉ** :

| origine | `AdjacentUnits` | `SurroundingUnits` | |
|---|---|---|---|
| `TargetTile()` — N entités-**tuile** | `[]` | `[]` | coïncident |
| `Target()` — 1 entité-**unité** | `[]` | `[tgt]` | **divergent** |

Côté `Adjacent`, `SelectTiles(Target)` déplie l'entité en son empreinte ⇒ tout retranché ; côté
`Surrounding`, `Tiles(Target)` applique `GetMainTile` à l'unique entité ⇒ **une** tuile. Le
call-site `SurroundingUnits(Target())` existe pour de vrai (`abilities/bloodangels.py`) : ce n'est
pas un cas d'école.

### Ce que ça corrige dans MA propre conclusion

« Le discriminant est le NŒUD, pas le domaine de la valeur » était **trop large**. Deux choses
commandent, et il faut les tenir séparées :

1. la **propriété du nœud** (`ReturnsOnlyUnits`) décide s'il y a **résolution** tuile → occupant ;
2. ce que le nœud **ÉNUMÈRE** décide du **nombre** de main tiles — `GetMainTile` s'applique PAR
   ENTITÉ.

Le port faisait déjà exactement cela (`_main_tiles` boucle sur `_origin_entities`) ; c'est la prose
qui était fausse, des deux côtés.

### Le retournement, et ce qui le garde

Patron `case-589-r2` : (a) la **mesure** — les deux ci-dessus ; (b) un **garde qui remplace** —
`test_the_two_exclusions_DIVERGE_on_a_UNIT_domain_origin` porte la réciproque sur l'origine qui
l'exerce, et le fichier garde désormais **les deux** faits (coïncidence en domaine tuile, divergence
en domaine unité) au lieu d'un seul ; (c) un **cran anti-vidage** —
`test_the_unit_domain_montage_is_not_vacuous` asserte que `Target()` rend bien UNE entité là où
`TargetTile()` en rend TROIS, sans quoi les deux assertions passeraient sur un montage dégénéré.

**Contre-épreuve JOUÉE** — les deux mutations mordent sur le test retourné, et sur lui seul :

| mutation de `_main_tiles` | résultat |
|---|---|
| port d'avant (`[:1]` partout) | 1 failed / 21 passed → `..._on_a_TILE_domain_origin` |
| résolution d'occupant | 1 failed / 21 passed → le même |
| revert | **22 passed** |

**Et un cran de plus, en amont** : `probe_10023r1` **étage 7** vérifie qu'aucun des trois sélecteurs
n'override `get_ReturnsOnlyUnits`. C'est *ce fait* qui autorise à transporter la mesure ; s'il
changeait, le transport deviendrait faux **en silence**. Il rend `NON MESURÉ` (jamais un rouge
fabriqué) quand le jeu n'est pas installé, et il assertionne son propre non-vide (la base doit
déclarer la propriété, sinon l'étage ne garde rien).

## 4. Ce qu'aucun cliquet ne pouvait voir

`probe_10023r1` étage 4 assertionnait « UNE SEULE tuile retranchée » et il était **VERT** — l'oracle
et le port portaient la **même** erreur. Le test qui le joue rangeait même cet étage parmi ceux qui
« survivent à la mutation `résolution d'occupant' », et c'était vrai : sous cette mutation les sept
pieds résolvent vers la même unité, donc une seule tuile aussi. Seule une mesure **extérieure**
pouvait rouvrir le dossier.

Depuis : l'étage est renommé `etage4_empreinte_retranchee_en_entier`, il porte un cran de non-vide
sur son propre écart, et **deux** mutations mordent désormais dessus (`résolution d'occupant`,
`port d'avant`). `test_1030_the_lantern_offline` a vu sa contre-épreuve **inversée** (la zone mutée
est désormais plus GRANDE).

## 5. Ce que la tranche NE couvre PAS

- **Le régime `ReturnsOnlyUnits == False` est porté, jamais exercé** : aucun nœud du dépôt ne le
  déclare. Il est écrit parce que c'est le natif.
- **Deux slots MESURÉS ; trois sélecteurs COUVERTS par héritage LU.** `Target` et `CasterTiles`
  concordent en live ; `TargetTilesSelector` et `UnitsMainTilesSelector` sont couverts parce que la
  metadata établit qu'ils n'overrident pas (étage 7). Les **autres** classes de sélecteur prennent
  le défaut **sans être vérifiées** : l'étage 7 ne balaie que ces trois-là. Un nœud qui rendrait
  `False` doit l'ÉCRIRE avec la mesure qui l'établit — et l'ajouter à `HERITIERS_SANS_OVERRIDE`
  s'il doit être couvert.
- **Le régime « N unités distinctes »** reste inerte : 35 instanciations, aucune origine multi-unité.
- Le montage n'a qu'**une** cible discriminante par run (`abilityTargets.fromHere` n'en déclare que
  2, le gate dynamique `|A ∩ B| == 1` de #1030-r1 étant très restrictif).
