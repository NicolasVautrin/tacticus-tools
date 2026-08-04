# `#419-r1-tr14-r5-r2-r1-r1-r1-r2` — le gate `ShouldExecute` = `utility > <seuil statique>`

**Critère binaire** : le moteur pousse-t-il des actions que le natif écarte, parce que leur playbook
compare l'utilité d'action à un seuil que le port ignore ? **Non, pour 10 des 12 classes de la
famille**, depuis cette tranche — les 2 restantes ayant leur gate ailleurs, et l'une d'elles y voit
sa **borne** corrigée.

---

## 1. L'inventaire, RE-DÉRIVÉ — la famille compte DOUZE corps, pas cinq

La fiche de la tranche précédente (`case-419-r1-tr14-r5-r2-r1-r1-r1-kill-gate.md` §5.1) annonçait
« 5 corps » pour cette famille et rangeait le reste en « corps à logique propre, 13 non lus ». Le
recensement a été **refait**, et il est plus simple : on décompile **les 29 corps `ShouldExecute`
distincts** du build et on les classe par FORME, au lieu de partir d'une liste héritée.

```
mcp__ghidra__search_symbols_by_name(query = "Playbook\$\$ShouldExecute")   -> 29 corps nommés
mcp__ghidra__decompile_function(<les 29>)                                  -> classement par forme
```

| forme lue | corps |
|---|---|
| `return utility > <PREMIER champ statique de la classe>` | **12** |
| `return utility > Fix64(0)` **littéral** | 6 (`Common.Repair`, `Repair_GalvanicField`, `StranglethornCannon`, `TwistedScience_Heal`, `HealingBalms_Heal`, `Loki_NormalBossAttack`) |
| `utility > 0` **+ une clause** | 3 (`ReapingScythe`, `Common.Heal`, `MultiThreatEliminator`) |
| sans seuil (logique propre) | 8 (`SpiritLeech`, `FragBomb`, `SorcerousFacade`, `ArmoriumCherub`, `BloodChalice`, `HadesAutocannons`, `StormOfFlensingBlades`, `TacticalPrecision`) |

**Sept des douze étaient classées ailleurs par la fiche précédente** : `PlagueWind`, `PlasmaCannon`,
`ScytheOfDust`, `ScythingTalons`, `SeekerMissileFrequencyLock`, `StaffOfStars`, `Supercharge`. Elles
figuraient dans sa liste des « 13 non lus » ; les lire montre qu'elles ont la forme **identique**.

Deux autres corrections de la même veine, hors périmètre mais notées : `Repair_GalvanicField` et
`StranglethornCannon` sont dans les « non lus » alors qu'elles portent le seuil `Fix64(0)` littéral,
et `ReapingScythe` a la forme `utility > 0 && GetStat(caster, 12) > 2` — pas une « logique propre »
non identifiée. Le résidu §6 les reprend.

### Le corps, lu verbatim

```c
// <X>Playbook$$ShouldExecute
y = *(*(Il2CppClass*<X>Playbook + 0xb8));       // +0xb8 = Il2CppClass.static_fields
return Fix64.op_GreaterThan(attackHealUtility, y);
```

La double indirection lit le champ statique d'**offset 0** — le PREMIER static de la classe. Le
corps n'utilise ni le caster, ni la cible, ni la tuile de cast : c'est ce qui permet à une unique
classe Python de porter les douze identités.

Le `Il2CppClass*` lu est bien celui de la classe elle-même : le **même slot** est initialisé par son
`.ctor`, qui appelle `il2cpp_runtime_class_init` dessus puis
`ComparablePlaybook<T>..ctor(this, <id>, klass)`.

---

## 2. Le seuil — LU au `.cctor` de CHAQUE classe, et il n'est PAS uniforme

| classe (`IdunBattle.AI.Playbook[.Loki]`) | `ability_id` (lu au `.ctor`) | `.cctor` | seuil |
|---|---|---|---|
| `BlightGrenadesPlaybook` | `0x498` = **1176** | oui | `Fix64(1)` |
| `Loki.FlailSwingPlaybook` | `0x412` = **1042** | oui | `Fix64(1)` |
| `Loki.MomentShacklePlaybook` | `0x4a0` = **1184** | oui | `Fix64(1)` |
| `Loki.PlasmaCannonPlaybook` | `0x47e` = **1150** | oui | `Fix64(1)` |
| `Loki.PlagueWindPlaybook` | `0x40b` = **1035** | non | `Fix64(0)` |
| `Loki.ScythingTalonsPlaybook` | `0x429` = **1065** | non | `Fix64(0)` |
| `Loki.SeekerMissileFrequencyLockPlaybook` | `0x42d` = **1069** | non | `Fix64(0)` |
| `Loki.StaffOfStarsPlaybook` | `0x431` = **1073** | non | `Fix64(0)` |
| `Loki.ScytheOfDustPlaybook` | `0x432` = **1074** | non | `Fix64(0)` |
| `Loki.SuperchargePlaybook` | `0x44f` = **1103** | non | `Fix64(0)` |
| `Loki.ExcruciatingFrequenciesPlaybook` | `0x4ad` = **1197** | non | `Fix64(0)` |
| `Loki.AncestralFortunePlaybook` | `0x4b7` = **1207** | non | `Fix64(0)` |

Les **quatre** `.cctor` ont été décompilés **un par un** — aucun n'a été déduit du premier. Ils ont
la même forme : `FixMath.NET.Fix64$$op_Implicit(1)` stocké à `**(klass + 0xb8)`, donc à l'offset 0
des statics, exactement là où `ShouldExecute` lit.

### L'absence de `.cctor` est une MESURE, pas un grep négatif

C'est le point qui décide de huit lignes sur douze, et c'est exactement le gisement où
« pas dans la table » ne prouve rien (dédup IL2CPP des corps triviaux, bases génériques absentes du
dump Frida). Deux énumérations `class_get_methods` **indépendantes** :

1. `data/symbols/rnca9r7q6c/frida/methods.tsv` — produit par l'énumération IL2CPP, pas par Ghidra ;
2. le RPC **`resolveMethodPtr`**, qui REJOUE l'énumération dans le processus, chaîne de parents
   comprise.

Le **témoin** de la seconde est `ShouldExecute` : il doit apparaître à `depth 0` pour les douze,
sinon « aucun `.cctor` » ne mesurerait que la panne du RPC. Mesuré : **12/12** à `depth 0`.
Les deux sources s'accordent sur les douze lignes.

⚠ **Un bug de parsing a d'abord fait DIVERGER les deux sources sur les quatre `.cctor`** : le nom
qualifié d'un constructeur statique est `<Classe>..cctor` (DEUX points), et un `rsplit(".", 1)`
en tire `cctor`. Le désaccord accusait la table ; la faute était dans le lecteur.

Un `.cctor` absent ⇒ le champ n'est **jamais écrit** ⇒ il vaut ce que `Class::Init` y a laissé,
c.-à-d. **zéro** (`static_fields` est alloué zéro-initialisé). Confirmation indépendante : le port
de `1197` faisait déjà `if u <= 0: return None  # ShouldExecute : util > 0` dans son générateur
bespoke, écrit bien avant cette tranche.

---

## 3. Le port

`engine/playbook/static_threshold_gate.py` — **une** classe,
`StaticUtilityThresholdPlaybook(DefaultActiveAbilityPlaybook)`, paramétrée par `(ability_id,
utility_threshold)`. Les dix ids enregistrés retombaient jusqu'ici sur `DefaultActiveAbilityPlaybook`
(aucune entrée au registre) : ils en HÉRITENT, donc `make_damage_predictions`,
`calculate_custom_utility` et `make_effect_predictions` restent EXACTEMENT ce qu'ils étaient. Le
seul delta est `should_execute`.

Le gate vit au slot de vtable `+0x328`, appelé par
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
avec `attackHealUtility = CalculateCustomUtility + CalculateUtilityFromPredictions`, donc AVANT les
trois termes positionnels. `false` ⇒ `Nullable` VIDE = aucune action dans le `Bucket`.

### 3.1 DEUX des douze ne sont PAS enregistrées, et c'est mesuré

* **`1184 MomentShackle`** — sa route est le générateur BESPOKE (`playbook/bespoke.py` : self-heal +
  `CalculateCasterPositionUtility`, position-swept), pas `_best_attack`. Son gate y vivait déjà sous
  le nom `MIN_UTILITY = 1.0`, **avec la mauvaise borne** : `if util < self.MIN_UTILITY: continue`
  accepte `util == 1.0`, là où `Fix64$$op_GreaterThan` le REFUSE. Corrigé en `if not util >
  self.MIN_UTILITY`. Le seuil, lui, était juste.
* **`1197 ExcruciatingFrequencies`** — route bespoke elle aussi (ligne-AoE à cible TUILE,
  `playbook/excruciating_frequencies.py`), gate déjà posé et **conforme** au seuil lu.

Les inscrire au registre serait un port MORT — leur `calculate_action_utility` n'est jamais appelé —
et masquerait où vit réellement leur gate. `NOT_REGISTERED` porte ce fait, et un cran le garde.

---

## 4. La mesure

Board `MC1_67`, seed `4242`, `--no-ai` (l'adversaire ne joue jamais : la géométrie est **pilotée**).
Canal natif `aiDryRunAllUnits` (= `CalculateNextActionForUnit`, sans commit) ; canal port
`calculate_action_utility` depuis la tuile COURANTE (`None` = le `Nullable` vide natif), et
`u` = l'argument EXACT du gate, lu AVANT lui.

### 4.1 L'axe, énoncé AVANT — et il SÉPARE les deux seuils

Sur une cible à PV pleins et sans bouclier, l'utilité de dégât vaut, au décompilé porté
(`engine/utilities/damage.py::DamageUtility.evaluate`, `W_DAMAGE = 80`, `W_REMAINING = 20`) :

```
u = 80 * dmg/(maxHP+2) + 20 * (1 - (maxHP+2-dmg)/(maxHP+2)) = 100 * dmg / (maxHP + 2)
```

Donc **`u × (maxHP + 2)` est INVARIANT** à dégât constant : `u` est pilotable par les PV de la cible.
Deux bras, un seul axe :

* **bras `lo`** — PV énormes ⇒ `0 < u < 1`. Le seuil `1` doit REFUSER, le seuil `0` ACCEPTER.
* **bras `hi`** — PV **calibrés** depuis le `u` mesuré en `lo` pour viser `u ≈ 2`. Les deux acceptent.

Ce n'est donc pas un régime dégénéré : les deux modèles candidats (`> 0` et `> 1`) rendent des
verdicts **opposés** dans le bras `lo`, et le même dans `hi`. Le seuil s'en trouve **encadré**,
pas seulement « grand ».

### 4.2 Les quatre critères

* **A (nécessité, symétrique)** : le port ne refuse JAMAIS une ability que le natif CHOISIT. Les
  deux canaux ne mesurent pas la même chose (`aiDryRunAllUnits` rend l'action GAGNANTE, le port rend
  « une action EXISTE ») : c'est le seul accord exigible ligne à ligne, et le sens de divergence le
  plus grave.
* **B (le discriminant)** : en bras `lo`, le seuil `1` est refusé par le natif, le seuil `0` accepté.
  Même bras, même cible, mêmes PV — la seule chose qui sépare les deux lignes est la VALEUR lue.
* **C (témoin temporel)** : en bras `hi`, les deux sont acceptées. Exclut « cette ability n'est de
  toute façon jamais proposée » et borne le seuil PAR LE HAUT.
* **D (contre-épreuve)** : `should_execute` remis au défaut de la base — STRICTEMENT le port d'avant
  cette tranche — doit MORDRE là où le gate refuse et rester INERTE partout ailleurs.

### 4.3 Le montage, et les TROIS pièges qu'il a fallu fermer

L'attaque normale porte `CalculateCustomUtility = Fix64(1)`. En bras `lo`, où toutes les utilités
tendent vers 0, elle raflerait l'argmax **que le gate morde ou non** : le bras aurait deux causes
indistinguables. Le montage la prive donc de tout plan par la GÉOMÉTRIE —
`distance > Movement + portée de l'arme la plus longue` — avec `Movement` ramené à 1 par
`--unit-stat` et une approche qui vise une DISTANCE, pas « à portée ».

| caster | ability | seuil | armes | range | distance |
|---|---|---|---|---|---|
| `darkaTerminator` | 1150 PlasmaCannon | 1 | melee (1) | 3 | 3 |
| `tauMarksman` | 1069 SeekerMissileFrequencyLock | 0 | melee / R3 | 5 | 5 |

Trois pièges, tous **mesurés** puis fermés, et tous gardés ligne à ligne :

1. **`endturn` testé AVANT d'être joué.** Le patron repris de #581 attend que le tour REVIENNE
   (`currentPlayer == 3`) ; utilisé pour TERMINER le tour, il sort immédiatement — c'est déjà notre
   tour — et le tour n'est jamais soldé. Symptôme trompeur au deuxième pas d'approche :
   « AUCUNE tuile movable ».
2. **Le premier tour est le DÉPLOIEMENT.** `decisionView` y publie des positions de pré-placement :
   mesuré, une distance de **11** pour une unité qui se retrouve à **3** après UN hex. On solde un
   tour à vide avant toute lecture de distance.
3. **Un déplacement ne consomme PAS l'action d'attaque.** `CalculateNextActionForUnit` rend UNE
   action à la fois : un caster qui préfère une autre tuile émet d'abord un `MoveUnitMessage`
   (mesuré : `darkaTerminator` à `u = 2.0`, ability `rankCount = 4` dont sa propre tuile, rendait
   `MoveUnitMessage vers (4,7)`). On le laisse se poser — mais **dans le même tour**. La première
   version soldait le tour entre deux pas, rendant un mouvement neuf à chaque fois : les deux
   casters finissaient à portée de leur attaque normale (`normalPlan` faux → vrai), détruisant la
   neutralisation même que le montage cherche.

Et un garde qui n'est pas un piège mais une discipline : **`--unit-stat <X>:Movement=1` doit avoir
MORDU**. `reach` est mesuré sur les tuiles réellement rendues. Un montage dont la mutation ne prend
pas donne un vert qui ne prouve rien — c'est le vert le plus dangereux.

---

## 6. Résidus NOMMÉS

* **`-r2-r1` — la ventilation des 29 corps corrige la fiche #581 au-delà de cette famille.**
  `Repair_GalvanicField` et `StranglethornCannon` y sont « non lus » alors qu'elles portent le seuil
  `Fix64(0)` **littéral** (même famille au littéral près, port trivial) ; `ReapingScythe` est
  `utility > Fix64(0) && GetStat(caster, 12) > 2` et `Common.Heal` est
  `utility > Fix64(0) && (!IsBoss(caster) || caster != target)` — la seconde moitié de chacune n'est
  pas portée. Le compte des corps restants après cette tranche est donc à re-dériver, pas à
  décrémenter.
* **`-r2-r2` — la borne `>=` du bespoke n'est pas confrontée live.** La correction de
  `MomentShacklePlaybook` est un mirror de source (`inspect.getsource` la garde), pas une mesure :
  elle ne mord que sur `util == 1.0` EXACTEMENT, et `util = self_heal_u + adj_enemies × 25` avec
  `self_heal_u = eff/(maxHP+1)×100` ne l'atteint qu'à une égalité flottante exacte. Le même vice de
  borne existe peut-être sur `BloodChalicePlaybook.MIN_UTILITY` et `CultDemagoguePlaybook.MIN_UTILITY`
  (même écriture `util < MIN_UTILITY`), mais leur seuil vient d'`EvaluateInternal`, pas de
  `ShouldExecute` — hors périmètre, à lire avant de toucher.
* **`-r2-r3` — deux des douze n'ont AUCUN porteur recensé.** `1073 StaffOfStars` et
  `1074 ScytheOfDust` rendent **0 unité** sur les cinq voies dérivables du gameconfig. Le zéro ne
  prouve pas la mort (quatre voies non couvertes : trait, live-event, summon, tuile) et le port du
  gate est le MÊME objet que pour les dix autres — mais ces deux identités sont **NON CONFRONTÉES**.
