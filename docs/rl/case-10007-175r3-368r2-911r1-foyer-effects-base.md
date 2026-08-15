# Cinq résidus du foyer `effects/base.py` — ce que la re-mesure a confirmé, et ce qu'elle a réfuté

Build qui fait foi : **`t6dpr4k06g`**. Décompilé relu sur ce build ; live sur la session 95.
Items : `#10007` · `#175-r3` · `#368-r2` · `#433-r3-r2-r1` · `#911-r1`.

**Prémisses re-mesurées : 4 confirmées, 1 partiellement réfutée, 1 réfutée.** Le détail est
ci-dessous, item par item, avec ce qui a changé de statut.

---

## 1. `#10007` — le slot de perçage DÉFENSEUR (25) était MUET — **PRÉMISSE CONFIRMÉE**

### L'écart, relu

`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` invoque les
slots `0x1a` / `0x1b` / **`0x19` = 25 `PiercingMalusForDefense`** ; son homologue attaquant invoque
`0x16` / `0x17` / **`0x18` = 24 `PiercingBonusForAttack`**. Le port n'appelait **que le 24** dans sa
boucle défenseur : le slot 25 n'avait aucun mirror, donc il était structurellement muet.

### Ce que ce résidu ne disait pas, et qui change la forme du correctif

**Les DEUX boucles natives reçoivent LA MÊME collection d'effets.**
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` la construit **une fois** (un unique
appel virtuel, `local_948`) et la passe **inchangée** à l'appel du slot `0xd` (attaquant) **puis** à
celui du slot `0xe` (défenseur) — aucune réaffectation entre les deux. Chaque boucle écrit
`AbilityEntities+0x18 (Owner) <- le porteur de l'effet courant` avant d'évaluer le trigger : le tri
natif se fait donc par le **TRIGGER** (`OwnerIsTarget` / `OwnerIsCaster`), **jamais par la liste**.

C'est pourquoi le slot 24 **reste appelé** dans la boucle défenseur du port : le port, lui, découpe
par LISTE, et c'est sa seule voie vers les surchargeants `OwnerIsTarget` (`Supercharge`,
`BloodChalice`, `AllIsDust`). Ce n'est pas une erreur d'accumulateur — et ce serait sans effet
arithmétique de toute façon, `CalculateBaseDamageWithAllModifiers` sommant `attackModifiers@0x20` et
`defenseModifiers@0x20` dans le même `pierce_pct`.

### Le corps du slot, et le piège du signe

`BaseEffect$$PiercingMalusForDefense` et `BaseEffect$$PiercingBonusForAttack` ont des corps
**identiques à l'octet près**, à une seule différence : le champ de cache lu (`this+0x180..+0x1d0`
contre `this+0x128..+0x178`). Ce corps commun gère les **deux** fabriques :

| fabrique | champ de l'`EffectBonus` | ce que le slot rend |
|---|---|---|
| `EffectBonus.ForPiercing` | `+0x10` | la valeur telle quelle |
| `EffectBonus.ForSubtraction` | `+0x18` | la valeur **NIÉE** (`local_res8[0] = -local_res8[0]`) |

Une réduction de perçage se porte donc par un `for_piercing(..., -v)`.

### Le seul surchargeant natif du slot 25

`Loki.ModifiedExoarmour_PierceReductionEffect$$CreatePiercingMalusForDefense` =

```
EffectBonus.ForSubtraction(
    get_OwnerIsTarget & !DamageProfileIs(cfg.GetDamageProfile()) & !DamageProfileIs(cfg.GetDamageProfile2()),
    DSLFormulas.ConfigVar(0x3f = extraPierceRatio, GetAbilityState(this), cfg))
```

gameconfig `ModifiedExoarmour` : `damageProfile = Psychic`, `damageProfile_2 = DirectDamage`,
`extraPierceRatio` = 10 / 15 / **20** selon le palier. Porteur : `votanChampion` (Kimm), passif
`TriggeredAbilityType 1529`, et l'effet `1543` est **publié dès le déploiement** (déjà écrit dans
`effects/factory.py`). L'écart serait donc **mordant**, pas théorique.

**Livré** : `BaseEffect.create_piercing_malus_for_defense` (défaut `None`) + son appel dans
`build_defender_modifiers_from_effects`, `native_face = "defender"`.
**Non livré** : la classe `1543` elle-même — son inscription passe par `effects/factory.py`, foyer
tenu par une autre tranche. Résidu **`#10007-r1`**.

---

## 2. `#175-r3` — `get_CanBeImmuneTo` sur CHAMP D'INSTANCE — **PRÉMISSE CONFIRMÉE, ÉNONCÉ RÉFUTÉ**

La prémisse tient : **49** classes ont un getter `movzx eax, byte ptr [rcx+0x480] ; ret`, dont
**3 seulement DÉCLARENT** (`AStatModifierEffect` et `MultiValueStatEntryEffect` lisent `+0x480`,
`NoneEffect` lit `+0x481`). L'énoncé « aucune de ces 49 n'est aujourd'hui à `true` », lui, est
**FAUX**.

### L'étage

```
AStatModifierEffect$$.ctor(this, sourceAbility, unitEffectType, canBeImmuneTo, keepOnRevive, isMultiply)
    this+0x480 = canBeImmuneTo    this+0x481 = keepOnRevive    this+0x482 = isMultiply
```

⚠ La fiche disait « **3e** argument » : c'est le **4e** (donc `r9` en x64 MS, pas `r8`).

### La mesure — `probe_175r3_can_be_immune_to_ctor.py`

| | |
|---|---|
| `canBeImmuneTo = 1` | **1** — `Loki.ChampionOfTheFeast_ReduceArmorEffect` (`mov r9b,0x1`) |
| `canBeImmuneTo = 0` | 32 |
| INDÉTERMINÉES | 16, **nommées** (`.ctor` fondu par l'ICF, ou FORWARDER dont la valeur vient de l'appelant) |

**Contre-épreuve de la méthode** : `AnvilShield_BlockChanceBelowHealthCapEffect` rend `0`, ce
qu'une lecture indépendante antérieure (fiche `#175-r2`) avait déjà établi. Et la classe trouvée à
`1` a été re-lue par décompilation ghidra, séparément du scan d'octets.

⚠ **LE PIÈGE, et il aurait donné trois valeurs fausses** : les `.ctor` INTERMÉDIAIRES n'ont pas la
même signature. `DynamicStatModifierEffect$$.ctor(this, abilityType, variableType, isNegative,
canBeImmuneTo)` met **`isNegative`** en `r9` — lire `r9` partout aurait rendu `isNegative` pour
`GrimEfficiency_ExtraArmor`, `GrimEfficiency_ExtraPierce` et `ProtectorImperative`. Les positions
sont donc **déclarées une par une** dans le probe, chacune lue au décompilé ; un `.ctor` d'ancêtre
hors table sort `INDÉTERMINÉ`, jamais `0`.

**Livré** : `ChampionOfTheFeastReduceArmorEffect.can_be_immune_to = True`. Conséquence observable :
`EntityIsImmuneToEffect(u) = HasTrait(u, Immune) && CanBeImmuneTo` — le gate de pose d'
`AddEffectOperation` mord désormais sur une cible `Immune`, là où le port rendait `False`
inconditionnellement.
**Reste** : les 16 indéterminées, et les volets 2/3 du résidu (`BlockUnitMovementBondEffect`, les
cinq feuilles de tuile) — résidu **`#175-r4`**.

---

## 3. `#368-r2` — l'`ActiveCondition` d'un effet de TUILE — **PRÉMISSE CONFIRMÉE**

### Deux lectures neuves

**(a) `IsSpawnTile` ne parle PAS de points de spawn.**
`IdunBattle.Entities.Selectors.SpawnTilesSelector$$Select` (corps **propre** — `frida/methods.tsv`
l'attribue bien à cette classe) est littéralement :

```
foreach (tile in <sélecteur interne>.Select(entities))
    if (TileExtensions.IsTemporary(tile)) result.Add(tile)
```

et `IdunBattle.Entities.TileExtensions$$IsTemporary` rend `TileComponent+0x2c`. Le prédicat est
« la tuile est **TEMPORAIRE** » (tuiles posées en combat : HulkDoor, plateformes), pas une
appartenance géométrique à un `SpawnPointGroup`. Lire le nom au lieu du corps aurait fait porter
une appartenance qui n'existe pas. Le canal existe déjà côté port : `boardGraph` publie
`isTemporary` par tuile (`frida/hooks/features/ai-step/rpc-board.ts`).

La condition complète est donc `IsWalkable(Self) | IsTemporary(Self)`, chacun des deux termes étant
un `AmountIsGreaterAbilityTrigger` sur son sélecteur.

**(b) LE MOMENT où le natif écrit le flag.** `IdunBattle.Operations.AddEffectOperation$$Execute`
appelle, **juste après `AddNewEffect`**, le slot **48** de `Core.Services.IOperationProcessor` —
`ImmediatelyRefreshEffects` — sur l'id de l'effet créé, puis `RefreshEffects(4)` et
`RefreshEffects(5)` en fin d'opération (slots lus dans `metadata/ioperationprocessor_slots.tsv` :
47 `RefreshEffects`, 48 `ImmediatelyRefreshEffects`). C'est ce refresh qui écrit
`EffectComponent.IsActive @+0x5c` — le champ naît à **zéro** (`EffectComponent$$.ctor` ne l'écrit
pas).

### Le domaine est de QUATRE types, pas cinq

`FireEffect`, `IceEffect`, `DespoiledGroundEffect`, `Loki.ContaminatedEffect`. **`58 Darkness` en
est EXCLU** : il est membre du set `StaticBattleRules.Effect$$IsTileStatusEffect` mais hérite le
corps par DÉFAUT (le trigger constant partagé par 114 classes). Indexer la table sur
`TILE_STATUS_EFFECT_TYPES` aurait été faux.

### La mesure comparait deux ÉTAGES DIFFÉRENTS

`E3` vient de `tileMeta` **sans** `includeInactive` : il ne rend que les effets **ACTIFS**.
`E4 burned_tiles` rend les tuiles où l'étage `[5]` a **POSÉ**. L'« écart port \ natif = `[(0,8)]` »
du bras D ne disait pas que le port se trompait de tuile — il disait que le natif y avait posé
**puis désactivé**. Le probe mesure désormais les deux étages.

| bras D (`MC1_67`, ancre `(0,7)`, trois tuiles à la MÊME élévation) | |
|---|---|
| natif (actifs) | `[(0,7), (1,8)]` |
| port — POSES | `[(0,7), (0,8), (1,8)]` — **identique au natif, qui pose aussi** |
| port — ACTIFS | `[(0,7), (1,8)]` → `gap_actifs = []`, **ACCORD** |
| CONTRE-ÉPREUVE (refresh neutralisé) | port ACTIFS `[(0,7), (0,8), (1,8)]`, `gap_actifs = [(0,8)]` → **MORD** |

### Le tri-état, et pourquoi il est load-bearing

`tile_status_effect_is_active(walkable, is_temporary)` rend `None` = **NON MESURÉ** quand le
substrat ne publie pas le canal, et le consommateur **laisse alors le flag INCHANGÉ** — exactement
ce que fait le natif quand il ne réévalue pas (`RefreshEffectsOperation$$ShouldBeActive` retourne
`+0x5c` inchangé dès que `ShouldRefreshForTrigger` est faux). Un `True` de confort ré-activerait ce
que le natif a désactivé ; un `False` désactiverait sur une non-mesure.

---

## 4. `#433-r3-r2-r1` — **NON RÉSOLU**, mais un des deux termes de l'objection tombe

Le foyer refusait d'inscrire `UnitFlag.Untargetable` pour `1044 Untargetable` faute de savoir si
l'inscription serait **observable** : « si rien n'inspecte l'état entre le `AddEffect` et le
`RemoveEffect` du même arbre, elle serait INERTE ».

**Mesuré** : côté port, il Y A un étage. `runner/abilities/behaviours/movement.py::FlyUnit` ne
déplace pas en silence — elle construit une `MoveUnitOperation` et l'exécute **avec le bus**
(`op.execute(state, ectx.bus)`), donc les vecteurs de mouvement du dispatcher partent **pendant** la
fenêtre d'intouchabilité. L'inscription ne serait donc pas structurellement inerte, contrairement au
cas `1230`/`1390` (aucun poseur).

**Ce qui reste ouvert, et qui suffit à ne pas inscrire** : aucun **LECTEUR** du flag `0x11` n'a été
recensé — le scan exhaustif de `#433-r3-r2-r1-r1` porte sur `UnitFlagsComponent$$Add`/`$$Remove`,
pas sur les tests. Sans lecteur identifié, l'inscription serait une divergence non confrontée. Le
montage live (overwatch sur le caster pendant le `FlyUnit`, natif contre port) reste dû.

**Indépendance vérifiée** : cette tranche ne touche ni `runner/operations/resurrect.py`, ni
`spawn.py`, ni `entities/unit_selection_type.py` — les trois foyers de `#433-r3-r2-r1-r1` — et le
domaine `UNTARGETABLE_EFFECT_TYPES` est **inchangé** (3 membres).

---

## 5. `#911-r1` — face SUCCESS de `DaemonicPatrons_Finale` — **RÉSOLU, confronté LIVE**

Ce que le résidu déclarait restant après la levée de l'étage `#1088`
(`get_RemoveOnDeathStep = AfterDeathTrigger` sur `TauntedEffect`) : la confrontation live de la face
SUCCESS. Jouée, deux bras, **port == natif des deux côtés**.

| bras | natif | port (rejeu offline, même flux PRNG) | contre-épreuve `NOPORT` |
|---|---|---|---|
| TAUNTÉ | `usable: True` | `usable: True` | `usable: False` → **MORD** |
| NON TAUNTÉ | `usable: False` | `usable: False` | identique → ne mord pas (attendu) |

Le témoin n'est pas dégénéré : les deux bras diffèrent par **un seul conjoint**
(`HasEffect(Target@<DSLSelectors+0x60>, 0x1b = 27, onlyActive 0, 6)`) et le natif y rend deux
verdicts opposés.

**Livré** : `mesurer()` extraite de `run()` dans le probe (le probe MESURE, le test ASSERTE, aucun
montage dupliqué) + `tests/engine/runner/test_911r1_daemonic_patrons_finale_live.py` (8 tests).
**Reste** : la face **FAIL** (`On(EffectRemoved)` → perte de `hpPct` % des PV courants à
l'expiration de `1465`), non confrontée — elle exige d'attendre trois tours du porteur sans kill
taunté. Résidu **`#911-r2`**.

---

## Ce qui n'est PAS couvert

* **`#10007`** — la classe `1543 ModifiedExoarmour_PierceReduction` n'est pas portée (`#10007-r1`) :
  le canal est posé, mais aucun effet ne l'emprunte encore, donc le slot 25 reste **exercé
  uniquement par les gardes**, pas par une confrontation live.
* **`#175-r3`** — 16 indéterminées, et les volets 2/3 (`BlockUnitMovementBondEffect`, les cinq
  feuilles de tuile qui héritent `true` sans classe Python) : `#175-r4`. Aucune confrontation live
  du nouveau `true` de `ChampionOfTheFeast_ReduceArmor` (le gate ne mord que sur une cible
  `Immune`, régime non monté ici).
* **`#368-r2`** — le port n'évalue la condition qu'**à la pose**. Un effet de tuile dont la
  marchabilité changerait EN COURS de vie (tuile détruite, plateforme retirée) ne serait pas
  réévalué : le natif, lui, rejoue `RefreshEffects` à chaque trigger de refresh. Non mesuré, non
  porté. La face DÉCISION n'est pas touchée (elle lit le flag NATIF via `tileMeta`).
* **`#433-r3-r2-r1`** — non résolu, cf. §4.
* **`#911-r1`** — face FAIL non confrontée (`#911-r2`).

## Reproduire

```
python probe_175r3_can_be_immune_to_ctor.py --vrais
python probe_368_daemonic_ordnance_pose.py --pose --only D
python probe_911r1_daemonic_patrons_finale_live.py
python probe_911r1_daemonic_patrons_finale_live.py --non-taunte
python -m pytest tests/engine/test_175r3_can_be_immune_to_ctor_offline.py \
                 tests/engine/test_368_daemonic_ordnance_pose_live.py \
                 tests/engine/runner/test_911r1_daemonic_patrons_finale_live.py -q
```
