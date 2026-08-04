# `#419-r1-tr14-r5-r2-r1-r1` — le gate `ShouldExecute` de l'attaque normale

**Critère binaire** : le port refuse-t-il d'attaquer une cible que le natif refuse ? **Oui, depuis
cette tranche**, et des DEUX côtés — la forme générique (gate `Explosive` + `utility > 0`) et la
forme boss (`utility > 0` seul). Confronté live sur un carré 2×2 apparié, deux contre-épreuves
mordantes sur la seule case discriminante.

---

## 1. Le décompilé

### 1.1 Les deux corps, lus verbatim

`IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$ShouldExecute` :

```csharp
if (UnitExtensions.HasTriggeredAbility(target, 0x48)) return false;
return attackHealUtility > Fix64(0);
```

`IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$ShouldExecute` :

```csharp
return attackHealUtility > Fix64(0);
```

**Le rapport de #569 disait vrai sur les deux points, et les deux ont été re-dérivés** :

* `0x48` = 72 = **`Explosive`**, qualifié dans `IdunBattle.Entities.Enum.TriggeredAbilityType`
  (`data/symbols/rnca9r7q6c/frida/enums.tsv`) ;
* la lecture porte sur la **CIBLE**. La signature est
  `ShouldExecute(this, caster, casterTile, target, attackHealUtility)` — établie sur le corps
  NON générique (`Loki_NormalBossAttackPlaybook`, que Ghidra type entièrement). Dans le corps
  gshared, l'argument lu est `R9`, soit le **quatrième** : `target`. Le `attackHealUtility` est en
  `[rsp+0x28]`, cohérent avec un dernier argument caché `MethodInfo*`.

**Ce que le rapport ne disait PAS, et qui double la portée** : la clause `utility > 0` est la
SECONDE moitié du gate, et elle manquait au port tout autant. Les seize playbooks génériques
n'émettaient donc pas seulement sur une cible `Explosive` — ils émettaient aussi une action
d'utilité négative ou nulle, que le natif supprime.

`IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$ShouldExecute`
a le corps **identique** à la générique. Son `.ctor` passe `0x11` = `17 NormalAttack` à
`ComparablePlaybook<T>$$.ctor` — une identité qu'aucune branche de la cascade ne distribue
(résidu `-r1-r1`).

### 1.2 Où le gate s'insère, et avec quel argument

`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`,
dans l'ordre du flux :

```csharp
u = vtable[0x338](caster, casterPosition, target, ability, …);   // CalculateCustomUtility
if (u == BaseUtility.<+0x18> || u == BaseUtility.<+0x20>) return null;
if (u == BaseUtility.<+0x10>) return Nullable(BaseUtility.<+0x10>);
u += CalculateUtilityFromPredictions(caster, casterPosition, target, ability);
if (vtable[0x328](caster, casterPosition.MainTile, target, u)) {   // <-- ShouldExecute
    u += vtable[0x348](caster, casterPosition, ability);           // CalculateCasterPositionUtility
    u += utility(0x37).Evaluate(UtilityAttackCase.Base(caster, casterPosition, target, ability));
    u += CalculateUtilityFromTilePrediction(caster, casterPosition, target);
    return Nullable(u);
}
return Nullable_vide;                                              // AUCUNE action
```

Deux lectures qui déterminent le port :

* **l'argument est `custom + predictions`**, pas l'utilité finale — les trois termes positionnels
  sont sommés APRÈS. Pour l'attaque normale, `custom = Fix64.FromInt(1)`, donc le seuil effectif est
  `1 + Σ prédictions > 0` ;
* **`false` ⇒ `Nullable` VIDE**, c'est-à-dire rien poussé dans le `Bucket` — pas une utilité basse
  qui perdrait l'argmax.

### 1.3 Le défaut, dit exactement

Le `MethodInfo` du niveau `ComparablePlaybook`1` porte un `methodPointer` **NUL** : la définition
générique n'a pas de corps compilé. Ce sont les classes CONCRÈTES qui déclarent chacune leur propre
`MethodInfo`, et celles qui ne spécialisent rien pointent toutes sur le **même** corps de trois
octets `b0 01 c3` (`mov al,1 ; ret`) — mesuré sur six classes indépendantes (`Drachnyen`,
`Chronometron`, `DoomSiren`, `ForwardObservers`, `PlasmaGrenade`, `MartialInspiration`). Son unique
propriétaire NOMMÉ dans les tables est `UnityEngine.U2D.IK.Solver2D$$DoValidate` (dédup IL2CPP).

Le comportement par défaut EFFECTIF est donc « accepter », et c'est ce que la base du port porte.
⚠ Dire « la base rend `true` » est un raccourci : la base n'a pas de corps, ce sont les feuilles qui
en portent un trivial. La conclusion pratique est la même, la méthode de lecture non.

---

## 2. Le PÉRIMÈTRE — balayage EXHAUSTIF, pas un échantillon

La consigne était de ne pas s'arrêter aux deux playbooks du rapport. Les **363** classes
`IdunBattle.AI.Playbook.*Playbook` nommées du build ont été balayées **niveau par niveau**
(`class_get_methods` de la chaîne de parents, RPC `resolveMethodPtr` — la technique SANS prérequis,
celle qui reste valide quand la vtable n'est pas matérialisée) :

| catégorie | compte | ce que ça veut dire |
|---|---|---|
| héritent d'`ALoki_NormalAttackPlaybook`1` @`0x181461ac0` | **16** | le gate `Explosive`, sans le redéclarer |
| déclarent le corps trivial `return true` | 35 | override sans effet |
| déclarent un corps PROPRE | **43** (29 corps distincts) | logique de gate réelle |
| ne déclarent rien à aucun niveau | 269 | NonComparable et bases (pas ce slot) |

**Les 16 sont EXACTEMENT les 16 identités de la cascade** (14 par la voie passive, `1126
RogalDorn_NormalAttack` par l'active, `69 Loki_NormalAttack` en repli) — le balayage le confirme de
façon indépendante du raisonnement par les `.ctor`. `1030 Loki_NormalBossAttack` est dans la colonne
« corps propre », seule de sa famille. Aucun `<X>_NormalAttack*Playbook` ne redéclare le gate.

⚠ **Et la table des symboles nommés ne suffisait PAS à le conclure.** Elle contient 31
`$$ShouldExecute` (29 côté Frida) pour **43** corps propres réels, parce que les corps sont
DÉDUPLIQUÉS : le corps `0x181221f30`, que la table attribue à
`IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute`, est **le slot de 14 classes**
(`BringerOfDespair`, `CrushingClaws`, `DakkaDakkaDakka`, `FragstormGrenadeLauncher`, `Fragstorm`,
`GreatFrostAxe`, `HarbingerOfDestruction`, `HellfireShells`, `IncendiaryShells`, `MortisRound`,
`PsychicMaelstrom`, `SanctorumMissile`, `SkyStrike`, `SpiritLeech`) ; `0x18121e9e0` en couvre 2.

⚠ **La technique des POINTEURS DE SLOT n'aurait pas suffi non plus, seule.** Elle exige une vtable
matérialisée ; ici elle l'était (vérifié : le slot `+0x328` de `Loki_NormalAttackPlaybook` rend bien
`ShouldExecute` @`0x181461ac0`, encadré par `get_IgnoreTileUtility` à `+0x318` et
`CalculateCustomUtility` à `+0x338`), mais elle ne distingue pas « hérité » de « redéclaré sur le
même corps ». Les deux techniques ont été jouées ; c'est l'énumération par niveau qui tranche.

---

## 3. Le port

### 3.1 Le gate, à son rang

`engine/playbook/base.py` :

* `ComparablePlaybook.should_execute(ctx, caster_tile, target, ability_id, utility)` — slot `+0x328`,
  défaut `True` ;
* `calculate_action_utility` l'appelle APRÈS `calculate_custom_utility + Σ prédictions` et AVANT les
  termes positionnels. `False` ⇒ `None`, le `Nullable` vide.

Le custom est **relu** pour l'argument du gate (il n'est sommé à `u_full` nulle part : c'est
`ComparableAbilityGenerator._action_utility` qui en fait `u_action`). Sans effet de bord — tous les
`calculate_custom_utility` du port sont purs — et c'est le seul moyen de donner au gate l'argument
que le natif lui donne.

L'override de `NonAttackComparablePlaybook` (route Comparable sans prédiction, #27-4b) est
**supprimé** : il était identique, et deux corps auraient été un fork. Les deux routes consultent
désormais le même.

### 3.2 Les deux formes, et le dispatch

`engine/playbook/common.py` :

* `NormalAttackPlaybook.should_execute` — refus si la CIBLE porte `Explosive`, puis `utility > 0` ;
* `NormalBossAttackPlaybook(NormalAttackPlaybook)` (`ability_id = 1030`) — `utility > 0` seul ;
* `normal_attack_playbook(ability_id)` — le foyer de dispatch, câblé dans
  `engine/ai/action_generators.py` (`pb = normal_attack_playbook(ab) if ab in ctx.normal_ids …`).

⚠ La hiérarchie native est INVERSE de celle du port : `Loki_NormalBossAttackPlaybook$$.ctor` appelle
`ComparablePlaybook<T>..ctor(this, 0x406, …)` **directement**, elle ne dérive PAS
d'`ALoki_NormalAttackPlaybook<T>`. Hériter côté port est ce qui fait porter `is_normal_attack`, le
custom `+1` et la prédiction d'attaque normale — tous trois **identiques par mesure**
(`Loki_NormalBossAttackPlaybook$$CalculateCustomUtility` = `Fix64.FromInt(1)`, `MakeDamagePredictions`
de même forme) ; ce que l'héritage natif ne donne pas — le gate `Explosive` — est précisément ce que
la sous-classe reprend.

### 3.3 Le substrat, et le trou qu'il a fallu fermer d'abord

`HasTriggeredAbility` fait `TriggeredAbilityComponent$$TryGetAbility` : l'**ENTITÉ**, pas le kit
gameconfig. Le foyer port est `entities.triggered_ability_type.entity_triggered_ability_ids`
(tri-état). Mais ce champ n'était seedé que par la face COMBAT (`snapshot._load_triggered_abilities`,
#456-r1) : sur le chemin LIVE de la décision (`build_predictor`) il restait `None`, et le foyer
retombait **silencieusement** sur le kit.

Cette tranche ajoute donc `engine/playbook/scene.py::_seed_measured_triggered`, pendant exact de
`_seed_measured_passives` / `_seed_measured_actives` — **même payload `unitAbilityStates`, coût RPC
nul**, avec le parsing extrait en foyer partagé `snapshot.triggered_ability_ids_by_unit`.

**Le rayon de souffle est MESURÉ, pas supposé** (volet `canal`, 8/8) : sur les deux unités du
montage, le kit gameconfig diverge du composant monté **dans les deux sens**, comme #456-r1 l'avait
trouvé côté combat.

| unité | kit gameconfig | composant MONTÉ (mesuré) |
|---|---|---|
| `orksNob` | `[1246]` | `[1234, 1518]` (+`72` dans les bras `expl`) |
| `necroWarden` | `[1004]` | `[1004, 1010]` |

Le kit annonce donc un id que la bataille **ne monte pas** (`1246`) et en rate deux qu'elle monte.
Ce seed change ce que la feuille `TriggeredAbilities(2)` de `scene_tile_leaf_ctx` itère côté
décision — c'est pourquoi les tests de terme de paire ont été rejoués (§5).

---

## 4. La mesure — carré 2×2 sur la MÊME unité

Board `MC1_67`, seed `9292901`, **même attaquant, même cible, même géométrie, même seed** dans les
quatre bras. Deux axes, tous deux ÉCRITS dans `BC.Units[]` :

* **CIBLE** : `orksNob.PassiveAbilities` = `[Explosive]` (greffe) ou `[]` ;
* **CASTER** : `necroWarden.Traits` += `Boss` (⇒ attaque normale `1030`) ou non (⇒ `69`).

`Explosive` (72) n'a qu'un porteur au gameconfig (`LootObj_ExplOilDrum`, npc) et **zéro** au seed
BC ; sa config est absente des 194 entrées de `BC.Abilities.PassiveAbilities`.
`catalog_inject.graft_passive_ability` écrit les DEUX côtés. ⚠ `replace=True` **VIDE**
`PassiveAbilities` — c'est fait dans les deux bras (`[]` côté `ctrl`), sans quoi ils différeraient
par plus que la seule variable étudiée.

`probe_419r1tr14r5r2r1r1_normal_attack_should_execute.py --volet gate`, **4/4 conformes** :

| bras | cible `Explosive` | caster `Boss` | attaque normale | natif (`aiDryRunAllUnits`) | port |
|---|---|---|---|---|---|
| `ctrl_gen` | non | non | `69` | `ActiveAbilityMessage(69 → 77)` | attaque |
| **`expl_gen`** | **oui** | non | `69` | **`FinishUnitTurnMessage`** | **n'attaque pas** |
| `ctrl_boss` | non | oui | `1030` | `ActiveAbilityMessage(1030 → 77)` | attaque |
| **`expl_boss`** | **oui** | oui | `1030` | `ActiveAbilityMessage(1030 → 77)` | attaque |

**Le discriminant était énoncé avant la mesure** : une seule case bascule, `expl_gen`. Un port qui ne
gate rien attaque dans les quatre ; un port qui gate tout, ou qui applique le gate au boss, échoue
sur `expl_boss` et sur les témoins. Les deux `ctrl_*` **attestent aussi le montage** — sans eux, un
caster hors de portée rendrait « aucune attaque » partout et se lirait comme un gate qui mord.

Canal natif : `aiDryRunAllUnits` (= `CalculateNextActionForUnit`, sans commit). L'attaquant est
amené à portée par trois déplacements REJOUÉS À L'IDENTIQUE dans les quatre bras, l'adversaire ne
jouant jamais (`--no-ai`) : la géométrie est donc pilotée, pas subie.

### 4.1 Les deux contre-épreuves mordent, et seulement là

| contre-épreuve | `ctrl_gen` | `expl_gen` | `ctrl_boss` | `expl_boss` |
|---|---|---|---|---|
| gate coupé (= le port d'avant) | inerte | **MORD** | inerte | inerte |
| canal `TriggeredAbilityComponent` coupé côté décision | inerte | **MORD** | inerte | inerte |

La seconde est ce qui prouve que le gate lit le **composant monté** et non le kit : `Explosive` n'a
aucun porteur au seed BC ni au kit du greffon, donc un port resté sur le kit ne PEUT pas mordre.
L'inertie des trois autres lignes est la réciproque : un port qui déborderait les ferait bouger.

---

## 5. La NON-RÉGRESSION, mesurée sur des trajectoires entières

Le carré 2×2 prouve que le port gate LÀ OÙ le natif refuse. Le bras réciproque — « il ne gate nulle
part ailleurs » — n'est pas assuré par trois témoins : il se mesure sur des décisions en volume.

`engine_validate.run_agreement` marche la trajectoire de l'IA NATIVE (`aiStepDryRun` → `applyAction`)
et compare la décision du moteur à chaque chunk. Joué **deux fois par couple (seed, board)**, sur
deux runners IDENTIQUES, le second avec `should_execute` des deux playbooks remis au défaut de la
base (= le port d'avant cette tranche) :

| seed / board | position | ability | stay | livré ≡ gate-coupé |
|---|---|---|---|---|
| `777` / `MC1_67` | 19/20 | 20/20 | 4/4 | **oui** |
| `31337` / `MC1_67` | 22/22 | 17/17 | 1/1 | **oui** |
| `2468` / `C1_74` | 15/16 | 21/22 | 8/8 | **oui** |

**56/58 position, 58/59 ability, 13/13 stay — et les six colonnes sont IDENTIQUES entre les deux
runs.** Le gate ne retire donc AUCUNE décision que le natif prend, sur 130 chunks de trois batailles
et deux boards. C'est le sens exact de ce chiffre : ni « le gate est bon » (aucune de ces batailles
ne porte `Explosive`), ni « il est inerte en général » — seulement « il ne DÉBORDE pas ».

⚠ Cette même mesure est ce qui borne la clause `utility > 0` : elle n'a mordu sur aucun des 59
chunks d'ability, donc son régime discriminant reste NON CONFRONTÉ (cf. §8).

---

## 6. Tests rejoués

| fichier | verdict |
|---|---|
| `test_419r1tr14r5r2r1r1_normal_attack_should_execute_live.py` (neuf) | **7 passed** |
| `test_419r1tr14r5r2r1_trait_normal_attack_live.py` | 6 passed |
| `test_419r1tr14r5_normal_attack_dispatch_live.py` | 6 passed |
| `test_419r1tr14r5_r1r4_normal_attack_table_live.py` | 9 passed |
| `test_419r1tr14r5r2_active_normal_attack_live.py` | 6 passed |
| `test_normal_attack_bonus_decision_live.py` | 8 passed |
| `test_419r1tr9_r4_r1_r2_normal_attack_gate_live.py` | 6 passed |
| `test_419r1tr14_heavy_bolt_pistol_live.py` | 6 passed |
| `test_443_savior_protocols_pair_term_live.py` | 5 passed |
| `test_443r1_savior_protocols_move_term_live.py` | 5 passed |
| `test_443r2_only_active_overwatch_live.py` | 7 passed |
| `test_tile_term_triggered_playbooks_live.py` | 12 passed |

**12 fichiers, 83 verts, 0 rouge.** Les sept derniers ne sont pas de la tranche : ce sont les
consommateurs du terme de PAIRE et de la feuille `TriggeredAbilities(2)`, c'est-à-dire exactement ce
que le seed de `triggered_abilities` côté décision (§3.3) pouvait déplacer.

Banque de cliquets (`-Since origin/master`) : **38/40 verts**. `probe_462` a rougi sur l'attestation
manquante du fichier live neuf — régénérée et commitée. `probe_467r4` a rougi sur
« la valeur propagée est celle du host (8 vs 9) » : il lit `liveRunners` à deux instants pendant que
les runners de cette tranche montaient et descendaient — **VERT au re-jeu seul**, et le diff ne
touche ni `loop_status.py` ni `frida/host/*`.

---

## 7. Résidus NOMMÉS

* **`#419-r1-tr14-r5-r2-r1-r1-r1` — les 43 autres `ShouldExecute` ne sont pas portés.** Le balayage
  du §2 les compte : **43** classes déclarent un corps propre (29 corps distincts), et cette tranche
  n'en porte qu'un (`Loki_NormalBossAttackPlaybook`). Deux sont déjà modélisés autrement
  (`HealPlaybook` / `HealingBalms_HealPlaybook`, par le `pred > 0` de leur `score()`). Le reste est
  une dégradation **permissive** de même nature que celle fermée ici, sur les abilities SPÉCIALES.
  Le gisement est identifié classe par classe ; le trancher demande de lire 29 corps.
* **`#419-r1-tr14-r5-r2-r1-r1-r2` — `17 NormalAttack` n'est distribué par aucune branche portée.**
  `Idun.NormalAttackPlaybook<T>` a le MÊME gate que la générique et son `.ctor` passe `0x11`. Aucune
  classe concrète n'en dérive dans le build, et `17` n'est la valeur d'aucune entrée de la cascade —
  la fabrique pose `this@+0x20` en repli, mesuré à `69` sur toutes les unités confrontées. NON
  CONFRONTÉ (aucun porteur trouvé), pas « mort » : la borne est le repli générique, non lu.
* **`#419-r1-tr14-r5-r2-r1-r1-r3` — le terme lifesteal de `SpiritLeech` est sommé APRÈS le gate.**
  `ComparableAbilityGenerator._action_utility` ajoute `ls` au retour de `calculate_action_utility`,
  alors que le natif somme tout DANS `CalculateActionUtility`, avant `ShouldExecute`. Inerte
  aujourd'hui (`SpiritLeechPlaybook` a son propre `ShouldExecute`, non porté — cf. `-r1`), mais
  c'est un rang faux qui mordra dès que ce gate-là sera porté.
* **`#419-r1-tr14-r5-r2-r1-r2` (les deux presets `TargetingOptions`) et `#419-r1-tr14-r5-r2-r2` (la
  garde `FilterNewList`) restent ouverts** — hors périmètre de cette tranche, inchangés par elle.
* **La garde de PORT `if not events: return None` reste une divergence assumée** (case-27) : le
  natif somme `0` et laisse `ShouldExecute` trancher. Elle n'est pas touchée ici ; avec le gate
  `utility > 0` désormais porté, les deux coïncident sur toute attaque normale sans prédiction
  (`custom = 1 > 0` ⇒ le natif accepterait — c'est donc bien une divergence, et elle est nommée là).

---

## 8. Ce qui n'est PAS couvert

* **Le carré 2×2 tient sur un seul board (`MC1_67`) et un seul seed.** Ni le gate ni le dispatch ne
  lisent le terrain ou le RNG. La généralisation est portée par l'autre mesure (§5, trois couples et
  deux boards), mais elle y est de NON-RÉGRESSION : aucune de ces trois batailles ne porte de cible
  `Explosive`, donc le bras « le gate mord » reste sur un seul board.
* **La clause `utility > 0` n'a pas de bras dédié.** Elle est portée et lue au décompilé, mais aucun
  montage ne la rend discriminante : sur les quatre bras, `1 + Σ prédictions` est largement positif,
  et le §5 confirme qu'elle n'a mordu sur aucun des 59 chunks d'ability. Un bras qui la testerait
  demanderait une attaque normale d'utilité négative (cible AMIE, ou prédiction nulle) — non
  construit.
* **Le custom est RELU pour l'argument du gate**, donc `calculate_custom_utility` est évalué deux
  fois par candidat sur la route d'attaque (une fois dans `_action_utility`, une fois dans
  `calculate_action_utility`). Sans effet observable (fonctions pures) ; le coût n'a pas été mesuré
  sur les playbooks dont le custom fait lui-même une prédiction (`HealingBalms`, `Drachnyen`).
* **Le `TriggeredAbilityComponent` mesuré est celui du pas 0.** `Explosive` accordé EN BATAILLE
  (par un `AddTrait` dérivé, ou une greffe dynamique) n'a pas été cherché ; le seed est re-joué pour
  les ARRIVANTS mais pas par pas, exactement comme les passifs et les actives (les trois sont figés
  au spawn côté fabrique).
* **Les 14 classes qui partagent le corps `0x181221f30` n'ont pas été lues.** Elles sont comptées,
  pas décodées — c'est le résidu `-r1`.
