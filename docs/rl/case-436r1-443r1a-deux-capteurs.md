# #436-r1 + #443-r1a — les deux capteurs qui manquaient, ECRITS

**Question binaire** : la prochaine fenêtre de reinject livrera-t-elle quelque chose ?

**Réponse** : oui, deux canaux — le lien BONDÉ d'un effet, et l'attribution du terme MOVE d'une
triggered ability. Les deux sont **écrits, compilés, embarqués dans le bundle et gardés offline**.
Les deux sont **NON CONFRONTÉS** : ils vivent dans `frida/hooks/*` et restent INERTES tant que la
fenêtre n'a pas eu lieu.

Le point de départ est une mesure : le 2026-08-02, une fenêtre a été ouverte sur un backlog qui
annonçait QUATRE items ; le grep du bundle réellement chargé en a montré **UN SEUL** de réel. Deux
capteurs étaient déjà embarqués, et le troisième — `BondComponent` — **n'existait ni dans le bundle
ni dans l'arbre** : personne ne l'avait écrit. Une fenêtre ne livre que ce qui est déjà CODE.

Build de référence : `rnca9r7q6c`.

---

## 1. `#436-r1` — le lien BONDÉ d'un effet

### 1.1 L'offset, lu CINQ fois — dont l'écrivain

Le résidu nommait « `BondComponent`, champ `bondedEntityId` à `+0x10` ». Vérifié, sans le croire :

| artefact natif | ce qu'il fait de `+0x10` |
|---|---|
| `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder` | **L'ÉCRIVAIN** — `*(int *)(comp + 0x10) = (int)bondedEntityId`, et c'est ce paramètre qui NOMME le champ |
| `IdunBattle.Entities.Components.BondComponent$$ToString` | `il2cpp_value_box(Int32, *(int *)(this + 0x10))` — champ UNIQUE |
| `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId` | `TryGetComponent<BondComponent>(effect)` puis `*(uint *)(comp + 0x10)` |
| `IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$Select` | même `TryGetComponent`, puis `state.GetEntity(*(int *)(comp + 0x10))` |
| `IdunBattle.Entities.EntityExtensions$$TryGetBondEffect` | `*(int *)(comp + 0x10)` comparé à `EntityId(bondedEntity)` |

Corroboré par la taille : `data/symbols/rnca9r7q6c/frida/classes.tsv` donne `BondComponent` = **24**
octets (header `0x10` + un int32), exactement comme `ChildComponent`.

⚠ **Même offset que `ChildComponent.ParentId` (#378), et ce n'est PAS le même champ.** Les deux sont
des `BEntityId` int32 à `+0x10` dans une classe de 24 octets ; ils ne se distinguent que par la
classe du composant et par l'entité qui le porte (une UNITÉ pour `ChildComponent`, l'entité-EFFET
ici). C'est exactement la forme de confusion qui avait déjà fait porter le mauvais bout du lien
en #372.

### 1.2 Ce que le canal débloque

`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` appelle `ABondEffect$$BondedEntityId` et
écrit `[cette valeur]` dans le `ForcedAttackTargetsComponent@+0x50` de la cible. C'est l'ENTRÉE de
`TargetIsAllowedForCaster` (bit 23, #436) — que le natif **n'arme que sous `Count > 0`**.

Sans le canal, un état reconstruit depuis un snapshot natif repartait `GetOnlyTargets == []` : la
restriction disparaissait **sans erreur ni crash**. Dégradation PERMISSIVE, invisible en self-play.
Le port ne voyait le taunt que quand c'était LUI qui l'avait posé.

### 1.3 Le TRI-ÉTAT, et pourquoi la branche « absent » n'a pas le même sens qu'en #378

| situation | `bondMeasured` | `bondedEntityId` |
|---|---|---|
| classe `BondComponent` irrésolue / lecture en erreur | `false` | `null` |
| composant absent (l'effet n'est pas un bond effect) | `true` | `null` |
| champ `== 0` (jamais écrit) | `true` | `null` |
| lien réel | `true` | l'id |

⚠ **La branche « composant absent » est ici le régime DOMINANT**, là où elle ne se déclenchait
jamais en #378 (l'ECS crée un `ChildComponent` sur chaque unité). `Blueprints$$BondEffect` n'attache
un `BondComponent` qu'aux effets construits par cette voie ; le `Blueprints$$Effect` ordinaire n'en
met pas. D'où un écart NOMMÉ avec le natif : `ABondEffect$$BondedEntityId` **logue une erreur et rend
`0`** quand le composant manque — le capteur, lui, balaie TOUS les effets et rapporte l'absence
comme une mesure, sans quoi le canal serait noyé de fausses erreurs.

Le `0 -> null` est celui de #378, et il n'est pas inventé : `MatchComponent$$NextId` est un
PRÉ-incrément sur un champ zéroé, donc le premier id émis est `1` et `0` n'est jamais un id
d'entité. `BondComponent$$.ctor` n'écrit pas le champ (son corps n'appelle que le ctor parent).

### 1.4 Le port

`EffectFactory.create` lit le couple sous le gate `bondMeasured is True` et pose `eff.bonded`
(attribut d'instance — `BaseEffect.bonded` est un attribut de CLASSE simple, exactement comme le
fait déjà la voie de pose `AddEffectOperation.execute`). Puis `snapshot._load_forced_attack_targets`
rejoue le `TauntedEffect$$ApplyInternal` pour les effets arrivés par HYDRATATION, sous le gate de
classe `writes_forced_attack_targets()` — **la même part DATA que la voie de pose**, donc aucune
seconde règle recopiée.

**Ce qui n'est PAS fait, et c'est délibéré** : hydrater par `eff.source`. Chez les quatre
producteurs lus, `bondedEntityId == source`, ce qui rend le repli tentant — et faux : ce serait une
DÉDUCTION, pas une lecture, et une liste fausse ici fait REFUSER un cast que le natif accepte
(dégradation RESTRICTIVE, l'inverse de la convention permissive de tout ce module).

---

## 2. `#443-r1a` — l'attribution du terme MOVE

### 2.1 Le dispatcher, remis en C#

`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` :

```csharp
Fix64 x = 0;
if (case.Unit == null) { yield return x; yield break; }
foreach (var ta in case.Unit.GetComponent<TriggeredAbilitiesComponent>().<Abilities@+0x18>) {
    var pb = this.<>4__this.<playbookDatabase@+0x48>.LoadPlaybook(ta.<AbilityType>);
    if (pb == null) continue;
    var it = pb.<slot 2 = CalculateMovementUtilityInSteps>(case, this.<>4__this.<weights@+0x58>);
    while (it.MoveNext()) yield return (Fix64)0;      // les « steps » : budget de calcul
    x += it.Current;                                   // la contribution de CETTE ability
}
yield return x;                                        // le TOTAL
```

Le décompilé de `d__2` est **ambigu sur le sens du `break`** (ghidra place la boucle externe DANS
l'interne). Il est levé par une SECONDE SOURCE, lue exprès :
`…TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext` a le **même
layout de state machine à 72 octets** et un décompilé explicite. Les deux concordent.

| SM `d__2` / `d__0` | +0x10 | +0x18 | +0x20 | +0x28 | +0x30 | +0x38 | +0x40 |
|---|---|---|---|---|---|---|---|
| | `<>1__state` | `<>2__current` | `case` | `<>4__this` | accumulateur `x` | énum. EXTERNE | énum. INTERNE |

`IdunBattle.AI.Utilities.UtilityMovementCase` (64 o), lu sur ses PROPRES accesseurs — jamais par
transposition :

| offset | champ | artefact qui l'établit |
|---|---|---|
| `+0x10` | `Unit` | `$$get_UnitOrParent`, `$$StaysOnTile`, `$$get_IsSpawning` |
| `+0x18` | `MovementPosition` (`UnitPosition` **INLINE**) | `$$get_MovementTile` = `IdunBattle.Core.UnitPosition$$get_MainTile(this + 0x18)`, qui rend `list[0]` de la liste au champ `+0x00` de la struct |
| `+0x30` | `Parent` (le spawner) | `$$get_UnitOrParent`, `$$get_IsSpawning` |

### 2.2 L'ATTRIBUTION — ce qui compte plus que le code

`scorerTileTermTrace` capte le composite `Tile(7)` complet **sans aucun `unitId`**. Mesure de
#443-r1 sur `MC1_67`/777 : les 4 events captés portaient TOUS sur des tuiles occupées par un TIERS,
et une version antérieure du probe, sans filtre, avait rendu un **accord parfait sur le `Tile(7)`
d'une AUTRE unité**. Un canal sans attribution ne rend pas « moins de mesure » : il fabrique du faux
positif, à l'échelle.

Le capteur publie donc, par évaluation terminée :

* `unitId` + `unitMeasured` (tri-état) — l'unité ÉVALUÉE ;
* `parentId` + `isSpawning` — **publiés à part**. `get_UnitOrParent` les confond parce que ses
  appelants n'ont besoin que d'« un sujet » ; un canal d'attribution qui ferait pareil rendrait
  indiscernables « le drone a été évalué » et « le drone SPAWNE depuis X » ;
* `tile` — `null` quand elle n'a pas été lue, **jamais `(-1,-1)`**, qui se lirait comme une
  coordonnée ;
* `contribs` — la DÉCOMPOSITION par playbook, ce qu'aucun canal existant ne donne.

La décomposition est obtenue en lisant le DELTA de l'accumulateur entre deux `MoveNext`, étiqueté du
nom de classe de l'énumérateur INTERNE capturé à l'entrée (`MoveNext` le remet à `null` juste après
avoir accumulé sa `Current` — c'est le seul instant où l'on sait quelle ability vient de
contribuer). Elle porte sa propre auto-vérification : `sum(contribs) == total` confronte deux champs
lus par deux chemins distincts, donc un offset d'accumulateur faux la casse.

### 2.3 Pourquoi pas `ai-trace` L3

`installL3` hooke la même surface — et 51 autres. Mais `--l3` est INTERDIT par le `CLAUDE.md`
(52 trampolines session-globaux sur le hot path, crash si un autre agent walke l'IA) ; ses events
partent dans le flux ai-trace **sans attribution par runner** ; et il émet le score TOTAL de la
state machine, **sans décomposition** — donc insuffisant dès que le mover porte plus d'une triggered
ability. Ici : 2 hooks, armés à la demande, `OriginBuffers` par runner, rien au `register`.

### 2.4 Résolution 100 % runtime

Aucune adresse en dur — contrairement aux hooks d'itérateur de `scorer-damage-trace`, qui en
portent et l'assument. La chaîne : `findClassAnywhere` → `il2cpp_class_get_nested_types` (préfixe
`<EvaluateMovementInSteps>d__`) → `findMethod(sm, "MoveNext")` → `getFieldOffset` par nom pour
chaque champ. Les offsets lus ne servent que de **repli NOMMÉ**, et `triggeredMoveTraceStatus`
publie champ par champ ce qui y est retombé — un capteur dont un offset est en repli n'est pas faux,
mais il n'est plus auto-vérifiant, et il faut le SAVOIR avant d'exploiter une mesure.

⚠ `class_get_declaring_type` a été ajouté à `helpers.ts` pour ça. Le nom court d'une state machine
**collisionne massivement** : mesuré sur `rnca9r7q6c`, **39 classes** portent un
`<EvaluateMovementInSteps>d__N`, dont plusieurs le même `d__2`. Chercher par `findClassAnywhere`
rendrait la PREMIÈRE trouvée — potentiellement la mauvaise, sans la moindre erreur.

---

## 3. Fichiers

| pièce | fichier |
|---|---|
| capteur BOND (tri-état, source des 2 vues d'effet) | `frida/hooks/game/effects.ts::readBondLink` |
| lecture du canal côté port | `engine/entities/effects/factory.py::EffectFactory.create` |
| seed du taunt HYDRATÉ | `engine/runner/snapshot.py::_load_forced_attack_targets` |
| capteur MOVE (2 hooks, on-demand, OriginBuffers) | `frida/hooks/features/triggered-move-trace.ts` |
| helper de désambiguïsation des nested | `frida/hooks/il2cpp/helpers.ts::class_get_declaring_type` |
| probe BOND (cast LIVE) | `scripts/python/probe_436r1_bond_channel.py` |
| probe MOVE (attribution) | `scripts/python/probe_443r1a_triggered_move_anchor.py` |
| gardes offline | `tests/engine/test_436r1_bond_channel_offline.py` (15), `tests/engine/test_443r1a_triggered_move_anchor_offline.py` (17) |

## 4. Validation

**32 gardes offline VERTES.** Quatre mutations adversariales, chacune vérifiée mordante, avec
restauration contrôlée après chacune :

| mutant | ce qu'on retire | rouges |
|---|---|---|
| (a) | le gate `bondMeasured` de `EffectFactory.create` | **2** |
| (c) | le gate `writes_forced_attack_targets()` du seed | **1** |
| (d) | l'appel `_load_forced_attack_targets` de `load_state` | **1** |
| (e) | le contrôle « tuile atteignable par l'unité attribuée » du probe MOVE | **1** — et c'est `test_LE_FAUX_POSITIF_DE_443r1_EST_REFUSE` |

La mutation (b) — remplacer `eff.bonded` par `eff.source` en repli — est couverte par
`test_seed_ne_DEDUIT_pas_le_bonded_depuis_la_source`, qui pose exprès `source == bonded` : c'est ce
qui rend le repli tentant chez les quatre producteurs lus.

`frida-compile` **rc 0** ; `tsc --noEmit -p tsconfig.hooks.json` : **0 erreur** sur les fichiers
touchés (les 146 restantes sont préexistantes et toutes dans `hooks/scratch/`,
`normalize-bc/debug-rpcs.ts` et `rl/tensorizer.ts`). Grep du bundle produit : les deux capteurs y
sont — `triggeredMoveTrace{On,Dump,Status}`, `readBondLink`, `bondMeasured`, `BondComponent`,
`UtilityMovementCase`, `il2cpp_class_get_declaring_type`.

### 4bis. Ce qui n'est PAS couvert — la face LIVE, et c'est TOUTE la face live

**NON CONFRONTÉ — capteurs livrés, fenêtre de reinject requise.** Aucun test de cette tranche ne
prouve qu'un de ces deux canaux fire. Les deux probes le DISENT plutôt que de le taire : ils rendent
**rc 7** avec un verdict `not_reinjected` nommé, et refusent de conclure quoi que ce soit du natif —
ni « pas de taunt », ni « le terme MOVE ne fire pas ».

Les MONTAGES, eux, sont prêts et discriminants :

* `probe_436r1_bond_channel.py` — `tyranTyrantGuard` amené au contact, `CrushingClaws` (1105) casté
  **EN LIVE**. C'est ce qui le distingue du probe #436, qui posait le taunt offline et ne pouvait
  donc rien dire du canal de capture.
* `probe_443r1a_triggered_move_anchor.py` — montage greffe de #443-r1 (1120 sur `tauCrisis`), avec
  un étage E1 qui essaie PLUSIEURS déclencheurs et **rapporte lequel fait firer le hook**. C'est
  l'information dont la fenêtre aura besoin en premier : #443-r1 avait mesuré qu'`aiStepDryRun` ne
  faisait firer AUCUN hook, et qu'un état déjà scoré n'est pas RE-scoré.

Autres non-couverts, nommés :

* le **régime `bondMeasured=false`** n'a pas été observé (il exigerait que `findClassAnywhere`
  échoue sur `BondComponent`) — il est exercé offline, pas live ;
* les **noms de champ de la state machine** (`<>7__wrap1/2`, le local Fix64 de l'accumulateur) sont
  essayés par candidats et **non vérifiés** : seule la fenêtre dira lesquels résolvent. Le capteur
  ne ment pas dessus — `triggeredMoveTraceStatus` liste les replis, et `check_channel` les remonte ;
* la valeur du terme `SaviorProtocols` n'est **pas confrontée** : cette tranche ouvre la
  confrontation (étage E4 du probe), elle ne la fait pas ;
* le **`TriggeredAbilitiesNonOwnerUtility`** est hooké mais son rôle exact dans le sweep n'est pas
  mesuré — on le couvre pour qu'un « zéro event » ne se lise pas à tort comme « le terme ne fire
  pas » ;
* la voie 3 de `ForcedAttackTargets` (`AddForcedAttackTargetBehaviour`, 23 porteurs summons
  Tyranides) reste non portée — écart déjà nommé par #436, inchangé ici.

## 5. Re-dériver

```
python scripts/python/probe_436r1_bond_channel.py
python scripts/python/probe_443r1a_triggered_move_anchor.py --state-file <ABSOLU>
python -m pytest tests/engine/test_436r1_bond_channel_offline.py \
                 tests/engine/test_443r1a_triggered_move_anchor_offline.py -q
```
