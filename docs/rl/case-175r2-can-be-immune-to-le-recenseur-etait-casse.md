# case-175-r2 — trois classes d'effet à `get_CanBeImmuneTo` vrai, et le recenseur qui disait l'inverse

Build `rnca9r7q6c`. Gardes : `tests/engine/runner/test_effect_immunity_live.py` (étages 5 et 6).
Re-dérivation : `python scripts/python/probe_175r2_can_be_immune_to.py [--runtime] [--regenerer]`.

## 1. Le résultat, et ses deux sources

`IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` (relu verbatim) =
`HasTrait(entity, 0x19)` puis appel **VIRTUEL** `klass+0x4e8` — le getter `get_CanBeImmuneTo`. La
valeur est donc **par classe**, et un override écrase ce que le `.ctor` a pu écrire.

Inventaire re-dérivé sur la **fermeture transitive** de `BaseEffect` (464 descendants) :
**13 classes** à `true`, dont **8 qui déclarent** le getter et **5 qui en héritent**.

| déclarent (corps `b0 01 c3`) | héritent de `BlockTileMovementEffect` |
|---|---|
| `DespoiledGroundEffect`, `BlockTileMovementEffect`, `BlockUnitMovementBondEffect`, `ContagionsOfNurgle_ArmorReduction_Effect`, `ContaminatedEffect`, `PinnedEffect`, **`StunnedEffect`**, **`TauntedEffect`** | `BlockEnteringUnitsTileEffect`, `FireEffect`, `IceEffect`, **`DarknessEffect`**, **`LandMineBlockTileMovementEffect`** |

Deux sources INDÉPENDANTES, **12 accords / 0 désaccord**, avec témoin non nul (`BaseEffect` =
`False` des deux côtés) :

* **binaire** — déclaration lue dans le `global-metadata.dat`, valeur lue par les OCTETS du corps
  dans le bloc `methodPointers`. Ancre LOCALE (contrôle d'alignement sur toutes les méthodes
  nommées de la classe) ; repli sur un **calage GLOBAL** calibré à **1193/1384** méthodes
  concordantes contre **22** pour le second candidat — c'est ce repli qui lit
  `DespoiledGroundEffect`, dont aucun corps n'a de symbole ;
* **runtime** — vtable (`resolveVtableSlot`), garde #218 appliquée, valeur tranchée par les OCTETS.

Les deux `Darkness`/`LandMine` sont des trouvailles de la fermeture : le §5 de `case-175-e` ne
les listait pas.

## 2. Le recenseur historique rendait un FAUX ZÉRO

`probe_224_can_be_immune_to.py` tranchait par **trois VA littérales** héritées d'un build
antérieur. Sur `rnca9r7q6c` il rendait :

* `CanBeImmuneTo == TRUE (0)` — **zéro** classe, sur les 442 du namespace ;
* `EntityIsImmuneToEffect SURCHARGE (10)` sur 10 classes sondées — alors que **9** pointaient sur
  `BaseEffect$$EntityIsImmuneToEffect` lui-même (`0x181006b00`), la VA à laquelle il comparait
  (`0x180f109b0`) étant celle d'un autre build.

Réparé : les corps s'identifient par leurs **octets** (`b0 01 c3` / `32 c0 c3`), la référence
`EntityIsImmuneToEffect` est **lue sur `BaseEffect`**, et le probe DIT « PAS MESURÉ » si le jeu
n'est pas installé. Après réparation : **10/10 true** et **1 seule** surcharge d'`EntityIsImmune-
ToEffect` (`ContaminatedEffect`) — ce que le décompilé dit.

⚠ C'est le vice « RVA hardcodée » du `CLAUDE.md`, transposé d'un **hook** à un **recenseur**.
Il ne crashe pas : il rend un inventaire faux, et l'inventaire finit recopié dans un commentaire.

## 3. Le port — quatre classes, pas trois

| classe Python | avant | après | pourquoi elle manquait |
|---|---|---|---|
| `StunnedEffect` | `False` | **`True`** | absente de l'inventaire de `probe_224` |
| `TauntedEffect` | `False` | **`True`** | idem |
| `ContagionsOfNurgleArmorReductionEffect` | `False` | **`True`** | **elle ÉTAIT dans l'inventaire écrit en commentaire dans `base.py`** — dix lignes au-dessus d'une classe qui la tenait à `False`. Le résidu ne comptait donc que trois classes ; il y en avait quatre |

`BlockUnitMovementBondEffect` reste NON portée : le port n'a aucune classe pour elle et son
`EffectType` **n'est pas établi** (son `.ctor` est fondu par l'ICF, aucun appelant nommé ; c'est
déjà ce qu'écrit `runner/operations/triggers/bond_removal.py` §3). Résidu **`#175-r3`**.

## 4. Le rayon de souffle — c'est le COMBAT

Le consommateur est le gate de POSE d'`IdunBattle.Operations.AddEffectOperation$$Execute`
(`entity_is_immune_to_effect`, `runner/operations/effects.py`). Mesuré sur l'état chargé d'un
runner (étage 6, deux bras, aucun cast) — le trait `Immune` est ajouté à `StatsComponent.ctx.traits`,
le substrat exact que lit `_unit_trait_names` :

| effet | cible **avec** `Immune` | cible **sans** |
|---|---|---|
| `Stunned` (1162), `Taunted_OnlySpecificTargets` (27), `ContagionsOfNurgle_ArmorReduction1` (1071), `Pinned` (1065) | **REFUSÉS** | posés |
| témoins `Stunned_CantUseAbility` (1165), `Stunned_DamageModifier` (1167) | **posés** | posés |

Refuser 1162 et 27 refuse AUSSI leurs sous-effets : ils ne sont spawnés que par l'`ApplyInternal`
du parent (et pour 27, l'écriture de `ForcedAttackTargetsComponent` avec).

⚠ **Le montage a un piège d'ORDRE, et il a mordu.** Poser les effets à la suite sur un même état
fait spawner 1165/1167 par `Stunned`, si bien que leur pose EXPLICITE suivante repartait sur le
gate « déjà présent » et rendait `False` — l'INVERSE de ce qui est testé. Un **état frais par
effet** le dissout.

## 5. Le contre-témoin versionné, RETOURNÉ

`test_effect_immunity_live.py` affirmait `stunned.can_be_immune_to is False` et
`stunned.entity_is_immune_to_effect([Immune]) is False`. Les deux sont retournées, avec la mesure
en docstring. La troisième affirmation du fichier — `AddEffectOperation` pose `Stunned` sur
`blackAbaddon` — reste VRAIE et n'est pas touchée : le gate est une **conjonction**, et c'est le
trait qui manque à cette cible, pas le drapeau.

## 6. Résidu — `#175-r3`

Trois choses que ce port ne peut pas porter, et pourquoi :

1. **49 classes** dont le getter EFFECTIF lit un **CHAMP D'INSTANCE** (`movzx eax, byte [rcx+X]`),
   pas une constante de classe : toute la descendance d'`AStatModifierEffect` /
   `MultiValueStatEntryEffect` / `NoneEffect`. Leur valeur dépend du `.ctor` — le port modélise
   `can_be_immune_to` comme un attribut de CLASSE, donc il ne peut pas l'exprimer. Aucune de ces
   49 n'est aujourd'hui à `true` **par déclaration**, mais rien ne le garantit par instance ;
2. `BlockUnitMovementBondEffect` — `true` au binaire, aucune classe Python, `EffectType` non établi ;
3. `DarknessEffect` / `LandMineBlockTileMovementEffect` / `FireEffect` / `IceEffect` /
   `BlockEnteringUnitsTileEffect` — `true` par héritage, aucune classe Python. Leur gate ne mord
   que sur une UNITÉ ; ce sont des effets de TUILE, donc l'écart est probablement inerte — mais
   « probablement » n'est pas une mesure.
