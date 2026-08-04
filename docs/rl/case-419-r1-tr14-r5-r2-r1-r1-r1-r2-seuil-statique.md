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

## 2. Le seuil — le champ a DEUX écrivains, et le dernier vaut `Fix64(10)`

| classe (`IdunBattle.AI.Playbook[.Loki]`) | `ability_id` (lu au `.ctor`) | `.cctor` dérivé | seuil EFFECTIF |
|---|---|---|---|
| `BlightGrenadesPlaybook` | `0x498` = **1176** | oui (`Fix64(1)`) | `Fix64(10)` |
| `Loki.FlailSwingPlaybook` | `0x412` = **1042** | oui (`Fix64(1)`) | `Fix64(10)` |
| `Loki.MomentShacklePlaybook` | `0x4a0` = **1184** | oui (`Fix64(1)`) | `Fix64(10)` |
| `Loki.PlasmaCannonPlaybook` | `0x47e` = **1150** | oui (`Fix64(1)`) | `Fix64(10)` |
| `Loki.PlagueWindPlaybook` | `0x40b` = **1035** | non | `Fix64(10)` |
| `Loki.ScythingTalonsPlaybook` | `0x429` = **1065** | non | `Fix64(10)` |
| `Loki.SeekerMissileFrequencyLockPlaybook` | `0x42d` = **1069** | non | `Fix64(10)` |
| `Loki.StaffOfStarsPlaybook` | `0x431` = **1073** | non | `Fix64(10)` |
| `Loki.ScytheOfDustPlaybook` | `0x432` = **1074** | non | `Fix64(10)` |
| `Loki.SuperchargePlaybook` | `0x44f` = **1103** | non | `Fix64(10)` |
| `Loki.ExcruciatingFrequenciesPlaybook` | `0x4ad` = **1197** | non | `Fix64(10)` |
| `Loki.AncestralFortunePlaybook` | `0x4b7` = **1207** | non | `Fix64(10)` |

Les **quatre** `.cctor` dérivés ont été décompilés **un par un** — aucun n'a été déduit du premier.
Ils ont la même forme : `FixMath.NET.Fix64$$op_Implicit(1)` stocké à `**(klass + 0xb8)`.

⚠ **Ce n'est PAS le seuil.** Le même slot est écrit une seconde fois par
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.cctor`
(`op_Implicit(0xa)` = `Fix64(10)`), et cette écriture-là arrive en DERNIER. **Mesuré** sur deux
identités aux `.cctor` OPPOSÉS : `1150` (qui déclare `Fix64(1)`) bascule dans
`(9,9997062 ; 10,0002938]`, `1069` (qui n'en déclare aucun, donc `Fix64(0)`) dans
`(9,9998703 ; 10,0001297]`. Détail, mécanisme et contre-épreuves :
**`case-419-r1-tr14-r5-r2-r1-r1-r1-r2-r4-seuil-effectif.md`**.

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

### 4.1 L'axe, énoncé AVANT

Sur une cible à PV pleins et sans bouclier, l'utilité de dégât vaut, au décompilé porté
(`engine/utilities/damage.py::DamageUtility.evaluate`, `W_DAMAGE = 80`, `W_REMAINING = 20`) :

```
u = 80 * dmg/(maxHP+2) + 20 * (1 - (maxHP+2-dmg)/(maxHP+2)) = 100 * dmg / (maxHP + 2)
```

Donc **`u × (maxHP + 2)` est INVARIANT** à dégât constant : `u` est pilotable par les PV de la cible.
Trois bras sur le MÊME caster, un seul axe, les deux derniers **calibrés depuis le `u` mesuré au
premier** (aucune valeur de dégât n'est supposée).

### 4.2 Le montage — `Movement = 0`, et pourquoi il ferme DEUX concurrents à la fois

`aiDryRunAllUnits` rend l'action **gagnante**. Dans un régime où l'utilité d'attaque est faible,
deux autres générateurs la raflent **que le gate morde ou non** :

1. **l'ATTAQUE NORMALE**, qui garde son `CalculateCustomUtility = Fix64(1)` ;
2. **le MOUVEMENT** — et c'est le piège le moins évident : **un déplacement CONSOMME l'activation**
   (mesuré : après un `MoveUnitMessage` appliqué, `aiDryRunAllUnits` rend `FinishUnitTurnMessage`),
   donc « bouger » et « caster » s'EXCLUENT. À `u ≈ 0.07`, le natif se rapproche, toujours.

`--unit-stat <X>:Movement=0` ferme les deux : le générateur de mouvement n'a plus aucune tuile, et
le sweep de tuiles du générateur d'action se réduit à l'origine — l'attaque normale n'a donc de plan
que si la cible est **déjà** à portée d'arme, condition purement géométrique. Il suffit alors de :

```
portée de l'arme la plus longue  <  distance(caster, cible)  <=  range de l'ability
```

⚠ **Et le placement libre du premier tour vient du trait `Teleport`, PAS d'une phase de
déploiement.** Mesuré, même spawn `(1,0)` et même `Movement=0` : `darkaTerminator` (Terminator, donc
Teleport) rend **58** tuiles atteignables (distances 2 à 11), `tauMarksman` en rend **0**. C'est ce
qui **réduit le montage à UN caster** — un porteur sans Teleport reste à son spawn, hors de portée
de son ability, et avec un `Movement` suffisant pour approcher il choisirait de bouger. Le témoin
est donc un témoin de **RÉGIME** (le même caster à trois utilités), pas d'ability.

| caster | ability | seuil | armes | range | distance |
|---|---|---|---|---|---|
| `darkaTerminator` | 1150 PlasmaCannon | 1 | melee (1) | 3 | **3** |

Deux autres pièges, mesurés puis fermés, gardés ligne à ligne :

* **`endturn` testé AVANT d'être joué.** Le patron repris de #581 attend que le tour REVIENNE
  (`currentPlayer == 3`) ; utilisé pour TERMINER le tour il sort immédiatement — c'est déjà notre
  tour — et le tour n'est jamais soldé. Symptôme trompeur : « AUCUNE tuile movable » au deuxième pas.
* **La mutation doit avoir MORDU.** `frozen` mesure, APRÈS placement, qu'il ne reste aucune tuile.
  Un montage dont la mutation ne prend pas donne un vert qui ne prouve rien.

### 4.3 Les trois bras — mesure

| bras | PV cible | `u` (port) | montage | natif | port | contre-épreuve |
|---|---|---|---|---|---|---|
| `lo` | 4 000 000 | **0,0851** | frozen, dist 3, pas de plan normal, castable | refuse | **refuse** | **MORD** |
| `mid` | 68 078 | **5,0** | idem | refuse | **refuse** | **MORD** |
| `hi` | 17 018 | **20,0** | idem | **`ActiveAbilityMessage(1150)`** | accepte | inerte |

* **A (accord PLEIN)** : natif et port s'accordent DANS LES DEUX SENS, 3/3. C'est ce que la
  correction de seuil (`-r4`) a acheté : avec le seuil `Fix64(1)` initialement porté, le bras `mid`
  était PERMISSIF (le port acceptait, le natif refusait) et seul le sens « le port ne refuse jamais
  ce que le natif choisit » était exigible.
* **B** : le gate mord partout SOUS le seuil (`lo`, `mid`) et nulle part au-dessus.
* **C (le témoin)** : à `u = 20` le natif émet bel et bien `ActiveAbilityMessage(1150)`. Sans lui, le
  refus des bras `lo`/`mid` se lirait aussi bien comme « cette ability n'est de toute façon jamais
  proposée ».
* **D (contre-épreuve)** : `should_execute` remis au défaut de la base — STRICTEMENT le port d'avant
  cette tranche — MORD sur `lo` et `mid`, et reste INERTE sur `hi`. L'inertie est la réciproque : un
  port qui déborderait ferait bouger le bras `hi`.

### 4.4 Le point de bascule NATIF — tranché par `-r4`

Le natif ne bascule qu'entre `u = 5` et `u = 20`, très au-dessus du `Fix64(1)` lu au `.cctor`
dérivé. Trois lectures étaient possibles, et cette tranche-ci ne les séparait pas :

1. le port SURESTIME `u` (divergence de PRÉDICTION, hors gate) — **RÉFUTÉE** : `pairUtility` (le
   `CalculateUtilityFromPredictions` NATIF) rend `0,08509995` / `5,000000005` / `19,999999995` et
   `aiPlaybookPredict` rend la MÊME liste d'events que le port ;
2. un filtre vit AU-DESSUS du playbook — **RÉFUTÉE** : le prédicat de `Bucket$$AddAction` /
   `$$ChooseAction` est `Bucket$$IsValidAction`, et les DEUX buckets du chemin
   `ActiveAbilityActionGenerator` ont un seuil inerte ;
3. le seuil effectif n'est pas celui du `.cctor` dérivé — **CONFIRMÉE**. Le slot a un SECOND
   écrivain, `ComparablePlaybook<T>$$.cctor`, qui y met `Fix64(10)` en DERNIER.

Le seuil effectif est donc **10**, encadré à 3·10⁻⁵ sur deux identités aux `.cctor` opposés.
Détail : **`case-419-r1-tr14-r5-r2-r1-r1-r1-r2-r4-seuil-effectif.md`**.

---

### 4.5 Le voisinage rejoué

| fichier | verdict |
|---|---|
| `test_419r1tr14r5r2r1r1r1r2_static_threshold_gate_live.py` (neuf) | **15 passed** |
| `test_419r1tr14r5r2r1r1r1_normal_attack_kill_gate_live.py` (#581, même foyer) | 10 passed |
| `test_plague_wind_prediction_live.py` (1035, l'un des dix ids) | 22 passed |
| `test_tile_term_unit_gated_playbooks_live.py` (bespoke MomentShackle) | 30 passed |
| `test_prediction_trait_gates_live.py` (bespoke) | 6 passed |

---

## 5. Ce qui n'est PAS couvert

* **Deux des douze identités sont confrontées live** (`1150 PlasmaCannon` ici, `1069
  SeekerMissileFrequencyLock` greffée dans `-r4`). Les dix autres partagent le MÊME corps natif et
  le MÊME objet Python : ce qui est confronté est le **corps**, pas chaque identité. Leur seule
  spécificité est l'`ability_id`, lu au décompilé et gardé par un cran offline.
* **La comparaison STRICTE (`utility == seuil` refusé) n'est pas confrontée live** : à l'égalité
  exacte, le natif (Fix64 Q32.32) et le port (flottant) ne calculent pas le même `u` à 10⁻⁹ près —
  régime mesuré et nommé dans la fiche `-r4` §5.1. Cran de source uniquement.
* **Un seul board, un seul seed, une seule cible.** Ni le gate ni le seuil ne lisent le terrain ou
  le RNG, mais le point de bascule NATIF (§4.4) n'a été localisé que dans cette configuration.
* **`1073 StaffOfStars` et `1074 ScytheOfDust` : aucun porteur recensé** — cf. résidu `-r2-r3`.

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
* **`-r2-r4` — FERMÉ.** Le point de bascule natif est celui de `ShouldExecute` : son seuil vaut
  `Fix64(10)`, pas `Fix64(1)`. Les deux causes concurrentes sont réfutées (§4.4). Les résidus
  qu'ouvre cette résolution — `BloodChalice`/`CultDemagogue`, le chemin NON-comparable du prédicat
  de bucket — sont nommés dans `case-419-r1-tr14-r5-r2-r1-r1-r1-r2-r4-seuil-effectif.md` §8.

---

## 7. La technique, réutilisable

**Piloter l'utilité d'action par les PV de la cible.** `u = 100 × dmg/(maxHP + 2)` sur une cible à
PV pleins sans bouclier ⇒ `u × (maxHP + 2)` est INVARIANT à dégât constant. Un premier bras à PV
énormes donne la constante ; tous les autres régimes s'en **calibrent** sans jamais supposer le
dégât. C'est ce qui permet de traverser un seuil d'utilité à volonté, dans les deux sens.

**Isoler une ability de ses concurrents par `Movement = 0`.** Un seul `--unit-stat` ferme le
générateur de MOUVEMENT (plus aucune tuile) *et* l'ATTAQUE NORMALE (sweep réduit à l'origine, donc
hors portée d'arme dès que la géométrie le veut). Sans lui, aucun régime de faible utilité n'est
observable : le natif bouge, et bouger CONSOMME l'activation.

**Se méfier du placement du premier tour.** Il vient du trait `Teleport`, pas d'une phase de
déploiement — donc il n'est disponible que pour certaines unités, et c'est ce qui décide quels
porteurs sont montables à `Movement = 0`.
