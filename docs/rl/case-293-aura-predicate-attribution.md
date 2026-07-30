# case-293 — L'écart d'une unité du prédicat d'aura par UNITÉ : **c'est le comparateur**, et la lecture « STRICT » venait d'un ctor dédupliqué

## Verdict

`IdunBattleLogic.Entities.DSLTriggers$$IsInUnitContagionsOfNurgleAura` construit un
**`IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger`** (`minAmount <= amount`),
**pas** l'`AmountIsGreaterAbilityTrigger` (`minAmount < amount`) que suggère le nom du `.ctor` appelé.
Le prédicat vaut donc `dist <= range` — **INCLUSIF**, exactement comme la version d'ÉQUIPE
`IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount`.

**Le port était déjà juste** (`engine/entities/triggers.py::IsInUnitAura` compare `<=` depuis la
PR #299) : ce cas ne change **aucun comportement**. Il transforme un `<=` *choisi par localisation*,
posé sur une mesure live sans que l'étage fautif soit désigné, en `<=` **lu au décompilé**. Les deux
modèles concurrents sont réfutés, chacun sur son propre étage.

| modèle candidat | statut | par quoi |
|---|---|---|
| comparateur INCLUSIF | **CONFIRMÉ** | pointeur de classe + encodage `setge` du `ShouldTrigger` |
| `MinDistance` natif = `hexdist − 1` | **RÉFUTÉ** | chemin de distance lu de bout en bout, sans offset |
| `GetCurrentRange` natif = table + 1 | **RÉFUTÉ** | arbre `GetRangeOnOwnerTurn` lu en entier, sur l'effet 1071 lui-même |

---

## 1. Le piège : un `.ctor` trivial DÉDUPLIQUÉ, dont la table ne nomme qu'un propriétaire

`IsInUnitContagionsOfNurgleAura(target, unit)` se termine par :

```csharp
range = DSLFormulas.ContagionsOfNurgleRange(unit, unitSelectionType: 0, isNextTurn: false);
dist  = DSLFormulas.MinDistance(target, unit);
obj   = il2cpp_object_new(<pointeur de classe>);      // <-- LA seule ancre
<ctor>(obj, amount: range, minAmount: dist);          // corps trivial, PARTAGÉ
```

Le `<ctor>` a pour corps `base..ctor` + `[this+0x18] = amount` + `[this+0x20] = minAmount`. Ce corps
est **identique** pour toutes les conditions de même layout, donc **IL2CPP le déduplique** : une seule
adresse, un seul nom dans `data/symbols/<build>/ghidra/functions.tsv`. Sur ce build, ce nom est
`AmountIsGreaterAbilityTrigger$$.ctor` — et le `ShouldTrigger` de *cette* classe finit bien par
`return minAmount < amount`, STRICT. **La lecture était cohérente, et fausse.**

L'ancre correcte est le **pointeur de classe** chargé juste avant `il2cpp_object_new`. Sur ce build,
deux globals seulement portent cette famille :

| global (rôle) | chargé par | `ShouldTrigger` |
|---|---|---|
| famille INCLUSIVE | `IdunBattleLogic.Entities.DSLTriggers$$AmountIsEqualOrGreater` | `return minAmount <= amount` (`setge`) |
| famille STRICTE | `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreater`, `$$AmountIsGreaterThanZero` | `return minAmount < amount` (`setg`) |

`IsInUnitContagionsOfNurgleAura` charge **le premier**. Fin de l'ambiguïté.

### Ce piège a récidivé trois fois, et il change de sens d'un build à l'autre

| cas | nom du `.ctor` au décompilé | classe réelle | sens de l'erreur |
|---|---|---|---|
| #48 `UnitsDirectlyBehind` | `AmountIsEqualOrGreater...` | `AmountIsGreater...` | évité (le solveur a lu le singleton) |
| #108 `MurderousSwing` | `AmountIsEqualOrGreater...` | `AmountIsGreater...` | évité (documenté dans le port) |
| **#224 → #299 → #293** `IsInUnitContagionsOfNurgleAura` | `AmountIsGreater...` | `AmountIsEqualOrGreater...` | **subi** — sens INVERSE des deux précédents |

⇒ **le propriétaire que la table donne à un corps partagé n'a aucune stabilité** : ni entre sites, ni
entre builds. Ne jamais dériver un comparateur du nom d'un `.ctor`.

---

## 2. Les deux autres étages, lus (et non fittés)

**Distance** — `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` accumule
`Math.Min(min, PositionComponent.Distance(b, a))` sur le produit des deux sélecteurs (`int.MaxValue`
si une énumération est vide). `IdunBattle.Entities.Components.PositionComponent$$Distance` =
`IdunBattle.Utils.Hex.CubeCoordinate$$Distance(this.ToCube(), other.ToCube())`, lui-même
`Max(Max(|dx|, |dy|), |dz|)`. **Aucun offset** : c'est la distance hex nue, et `hexgeo.distance`
(forme `somme/2`) lui est égale sur les 20 736 paires vérifiées.

**Portée** — `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect$$GetCurrentRange`
= `GetRangeOnOwnerTurn( StatAmount(Owner, 0xc = TurnsStarted) )`, et `GetRangeOnOwnerTurn(numRounds)`
est l'arbre :

```csharp
ConditionalAmount( Not(AmountIsGreater(numRounds, Direct(2))), Direct(1),
  ConditionalAmount( Not(AmountIsGreater(numRounds, Direct(4))), Direct(2), Direct(3) ))
// n <= 2 -> 1 ; n <= 4 -> 2 ; sinon 3
```

soit exactement `engine/entities/effects/aura.aura_range_on_owner_turn`. Ce modèle était déjà réfuté
par le probe d'ÉQUIPE — mais celui-ci mesurait `EntropyCannons`, donc une **autre** définition
d'effet ; il l'est maintenant sur **1071 lui-même**, par lecture.

---

## 3. Garde re-dérivable — `probe_293_aura_predicate_comparator.py`

Offline, **sans runner ni session Frida**. Il lit le pointeur de classe directement dans les octets de
`GameAssembly.dll` (opérandes RIP-relatives résolues), en ne partant que de **symboles** — aucune VA
n'est écrite dans le probe.

```bash
cd scripts/python
python probe_293_aura_predicate_comparator.py --inventory
```

| étape | ce qu'elle mesure |
|---|---|
| 1 | le sujet charge un global propre à la famille INCLUSIVE, et **aucun** propre à la famille STRICTE |
| 2 | corroboration indépendante : `setg` (strict) vs `setge` (inclusif) dans les deux `ShouldTrigger` |
| 3 | les deux modèles concurrents, réfutés côté port (table de portée ; `hexgeo.distance` == `CubeCoordinate.Distance`) |
| 3b | `IsInUnitAura.should_trigger` est bien resté `<=` |
| 4 | **inventaire** : les 22 sites d'instanciation, ventilés STRICT / INCLUSIF |

Sans `GameAssembly.dll` du build courant il rend **`NON MESURÉ`** et sort en erreur — jamais un
« 0 écart » qui se lirait comme un accord.

L'étape 4 est le vrai garde-fou : c'est la seule colonne qui dise à quelle famille appartient un site,
et elle se re-dérive en une commande au prochain changement de build.

---

## 4. Confrontation live

Le décompilé suffit désormais, mais la mesure a été rejouée — et le montage le plus discriminant,
resté **non exercé** jusqu'ici (résidu (a) de `case-224-cursed-plague-bell-attack.md` §4), a été
**craqué** en amincissant l'équipe adverse pour libérer l'anneau 1 autour du porteur.

| montage (board `C1_02`, seed `4242`) | `TurnsStarted` | `range` | mesure |
|---|---|---|---|
| `--advance 4 --dists 1 --tanks custoKyrus` | 2 | **1** | d=1 → **riposte** (natif 1795 = port 1795) |
| `--advance 6 --dists 1,2,3` | 3 | 2 | d=2 → riposte (1620 = 1620) ; d=3 → rien |
| `--advance 10 --dists 2,3,4` | 5 | 3 | d=2 → riposte (1795) ; d=3 → riposte (4860) ; d=4 → rien |

La première ligne est celle qui compte : **au palier `range = 1`, un comparateur strict donnerait un
rayon de 0** — la cloche ne pourrait jamais partir, à aucune distance. Elle part au contact.

**Contre-épreuve** (`--mutate strict`, qui remet le comparateur de l'autre classe) — elle rougit
**exactement** les cas `d == range`, et rien d'autre :

| montage | cas rouges |
|---|---|
| `--advance 4 --dists 1` (range 1) | **1/1** — d=1 : natif 1795, port muté 0 (`port_dist=1`, `port_range=1`) |
| `--advance 6 --dists 1,2,3` (range 2) | **1/2** — d=2 rouge (natif 1620, port muté 0) ; d=3 reste vert |

---

## 5. Ce que ce cas n'établit PAS

* **Aucun changement de comportement n'est livré** : le `<=` était déjà en place. Ce cas remplace une
  justification (« forme la plus locale ») par une lecture, et supprime la mention « trois modèles
  indiscernables » de six fichiers.
* **Le balayage d'opérandes de l'étape 1 est un décodage linéaire**, qui peut sur-générer sur du
  désalignement. Le critère est donc une **différence ensembliste** entre familles, jamais une égalité
  exacte de jeux d'adresses. Contrôle de cohérence passé : l'inventaire inverse de l'étape 4 reproduit
  **exactement** les 22 fonctions que `list_xrefs` donne sur les deux globals.
* **Les 9 prédicats `DSLTriggers$$Is*` / `$$Has*` de la famille inclusive ne sont pas portés** comme
  nœuds (le port porte le *sélecteur* ou la *primitive* `TileExtensions`/`UnitExtensions`) : il n'y a
  donc rien à confronter dessus aujourd'hui, mais rien non plus qui les couvre si un arbre DSL vient
  à les instancier.
* **Un résidu voisin a été trouvé et NON corrigé** (hors périmètre) :
  `IsActiveAbilityCountedAsUsed` — cf. `backlog.md`. Le seuil natif y est
  `isPreAbilityTrigger ? Direct(0) : Direct(1)` (cache de `IdunBattleLogic.Entities.DSLFormulas$$.ctor`)
  avec la classe **STRICTE**, soit `used > 1` sur la branche que le port mirroir ; le port écrit
  `used >= 1`. **Inerte aujourd'hui** (`state.total_active_ability_used` n'existe pas), mais à
  corriger avant de câbler ce compteur.
