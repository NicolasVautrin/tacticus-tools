# #1033 — `1107 Reveal` portée, et le faux no-op de `Maugetar`

Deux items d'un même lot (« les deux dernières actives en NO-OP SILENCIEUX »). Ils ont deux
verdicts opposés, et c'est le résultat : l'un se portait, l'autre **n'existait pas**.

| item | verdict |
|---|---|
| `1107 Reveal` | **PORTÉE** — ability + gate dynamique + effet 1219, aux trois registres |
| `Maugetar` | **N'EST PAS UNE ACTIVE** — l'audit la comptait à tort ; le correctif est le livrable |

---

## 1. `Maugetar` — la face active n'existe pas

Trois signaux se contredisaient : l'audit combat la listait en no-op **avec un id `?`**, l'audit kit
la listait parmi les voies conditionnelles **portées**, et le `CLAUDE.md` la documentait comme une
**inversion de voie**. La réconciliation tient en une mesure, prise sur le **build** et non sur le
mirror Python (`data/symbols/rnca9r7q6c/frida/enums.tsv`) :

| enum du build | membres | `Maugetar` |
|---|---|---|
| `IdunBattle.Entities.Enum.ActiveAbilityType` | 261 | **ABSENT** |
| `IdunBattle.Entities.Enum.TriggeredAbilityType` | 477 | **1498** |

Ghidra concorde : aucun symbole `...Abilities.Active.*Maugetar*` n'existe — seulement
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Maugetar_AddEffectAbility`,
`...Maugetar_ResetMovementAbility` et `IdunBattle.Entities.Effects.Loki.Maugetar_HasNotMovedEffect`.
Le gameconfig, lui, range bien le nom dans les `activeAbilities` d'`eldarBossMauganRaUltra` : c'est
l'une des deux inversions de voie mesurées (#270-c).

**Conséquence, et c'est ce qui tranche le cas** : `ABILITY_CLASSES` est indexé par `ActiveAbilityType`.
Aucun entier ne code `Maugetar` en active, donc aucun `ActiveAbilityMessage` ne peut le désigner, et
il n'existe **aucune clé à inscrire**. Le porter était *impossible*, pas difficile. La face qui
existe — la triggered 1498 — est portée depuis #1006 (`RELIC_ABILITY_TRIGGERS`, c'est la relique
`R_Crit_Maugetar`).

### Le défaut de l'audit, et sa correction

`audit_combat_ability_coverage.collect()` faisait `aid = name2id.get(nm)` sur le **seul**
`ACTIVE_ABILITY_TYPE`. Un nom absent rendait `None`, donc `None in ABILITY_CLASSES` = `False`, donc
« NO-OP silencieux ». L'id `?` affiché était la seule trace du problème.

Le correctif ventile en **trois** états (`PORTED` / `NO-OP` / `HORS-ACTIVE`), sort les inversions du
compte des no-op, et dit l'enum réel **plus le registre qui porte cette face-là**. L'état `INCONNU`
(nom d'aucun enum) reste un signal : le correctif ne fabrique pas de silence.

Ampleur mesurée : sur **175** noms distincts en `activeAbilities`, **1 seul** était dans ce cas.
Bilan de l'audit : no-op **8 → 6**, `DAMAGE` 5 → 4, `EFFECT/BUFF` 2 → 1.

> ⚠ **Une faute commise ici, gardée comme témoin.** `_triggered_portee` a d'abord été écrit avec le
> seul `ABILITY_TRIGGERS` et rendait « NON PORTEE » pour `Maugetar`, dont les deux triggered vivent
> dans `RELIC_ABILITY_TRIGGERS`. Une liste blanche ne peut pas montrer le registre qu'elle a oublié :
> le prédicat **dérive** désormais tout dict majuscule du module. Le mutant `M12` le garde.

---

## 2. `1107 Reveal` — la RE, et l'i2 qui s'y apparie terme à terme

L'i2 `Abilities/Reveal_CurrentLevelDescription` et le décompilé se recouvrent **un pour un**, ce qui
est le meilleur contrôle croisé disponible :

| i2 | étage natif |
|---|---|
| « An enemy within {range} hexes » | `TargetIsEnemy` + preset `RANGE_FROM_CONFIG` (`constants.range` = 2) |
| « that is not Revealed » | `EntityExtensions$$HasEffect(target, 0x4c3)` → `return 2` |
| « has defeated a friendly Aeldari unit this battle » | `GetDeadUnitsKilledBy(target)` filtré par `HasFaction(Aeldari) & IsFriend(caster)` |
| « becomes Revealed for {nrOfRounds} rounds » | `AddEffect(0x4c3, …, TurnsFromRounds(GetNumberConstant(0x45)))` |
| « deal +{extraDmgPct}% damage » | `RevealedEffect$$CreateEffectDamageMalusForDefense` |
| « ignore any hit reductions » | `RevealedEffect$$CreateEffectHitsBonusForAttack` = `ForReset` — **non porté**, §3 |

**Le cast ne frappe pas.** La config le confirme indépendamment : `variables` est VIDE, et les seules
`constants` sont `extraDmgPct` / `nrOfRounds` / `range` — ni `minDmg`, ni `nrOfHits`, ni
`damageProfile`.

### Le masque : la surcharge PRESET + FLAGS

`...RevealAbility$$.ctor` recopie le preset statique `<TargetingOptions statics>+0x180`
(`+0x28` = `0x4002`, `+0x08` ← `TargetingRange statics+0x18` = `RANGE_FROM_CONFIG`, `+0x20` = 1 =
`RangedBool.False`) puis appelle `TargetingOptions$$.ctor(&opts, &preset, 0x6000002)` — la surcharge
à **trois** arguments, dont le corps lu fait `Rules@+0x28 = additionalRules | template.Rules@+0x28`.

    masque EFFECTIF = 0x4002 | 0x6000002 = 0x6004002
      0x2         TargetMatchesDynamicRule        -> consulte le gate dynamique
      0x4000      TargetIsEnemy                   <- vient du PRESET
      0x2000000   AllowObscuredTargetByElevation  <- vient des FLAGS
      0x4000000   AllowObscuredTargetByWalls      <- vient des FLAGS
    décomposition exhaustive, 0 bit résiduel

Prendre le littéral visible pour le masque effectif aurait **perdu `TargetIsEnemy`** : l'ability
aurait accepté de marquer un allié. `AbilityAttackType` = `2` (`Others`), 3ᵉ argument
d'`AActiveAbility$$.ctor`.

### L'étage `GetDeadUnitsKilledBy`, lu et non supposé

`IdunBattle.Core.Services.BattleQuery$$GetDeadUnitsKilledBy` balaie toutes les unités, retient les
mortes dont `UnitComponent+0x108` (`Nullable<DamageSource>`) porte `KillerId == killer.Id`. Son
substrat est donc **`death_source`**, pas la file `MatchState.Deaths` — les confondre aurait changé
la population balayée.

### La face native de l'effet

`RevealedEffect` dérive de `BaseEffect` (`frida/classes.tsv`) et implémente
`CreateEffectDamageMalusForDefense` (slot 0x1a) **directement** → `defenseModifiers`. Son voisin de
forme `MarkerlightEffect` (même trigger `OwnerIsTarget`, même `ForPercentIncrease`, même gate de
faction) dérive, lui, de `DamageModifierAbilityEffect` et sort par le forwarder **attaquant**.
Recopier la face du voisin aurait changé le nombre de `Fix64.Round` (#437-r1-r1-r1).

---

## 3. Ce qui n'est PAS porté, et pourquoi — résidu `#1033-r1`

Le canal COUPS (`ForReset`, « ignore any hit reductions ») : `engine/services/effect_bonus.py`
**nomme** les sept fabriques natives mais n'en construit que six. Le port ne fabrique pas
d'équivalence avec `BaseEffect$$BlockHitsReduction`, qui est un **autre slot natif** que
`RevealedEffect` ne surcharge pas. État actuel, restrictif et assumé : le marquage donne bien
`+extraDmgPct %` et n'annule aucune réduction de coups.

---

## 4. La confrontation live — et le témoin qui a réfuté mon propre vert · résidu `#1033-r4`

Porteur unique `eldarNpc2Warlock` (npc, hors pool) → **greffe** sur `eldarAutarch` (`case-92` §5bis).
La greffe **fonctionne** : `abilities montees = [69, 1107]`. Géométrie **pilotée** (`--place` /
`--a-place`), victime rendue mortelle en un coup.

| régime | témoin (autre ability) | natif | port | lecture |
|---|---|---|---|---|
| A — aucun mort | **(0, 0)** | `[]` | `[]` | **NON CONCLUANT** : aucun cast n'était possible |
| B — un Aeldari ami défait | **(1, 1)** | `[]` | `[]` | **NON ATTEINT** : le natif refuse, raison non établie |

> **Le régime A était un FAUX VERT, et c'est le contrôle-témoin qui l'a montré.** `natif=[] port=[]`
> se lisait comme un accord ; le témoin `(0, 0)` dit que l'état n'autorisait **aucun** cast, donc que
> les deux zéros ne prouvaient rien. Le probe rend désormais ce régime `NON CONCLUANT`.

En régime B le témoin est non nul — le cast **est** possible — et le natif refuse quand même, avec
`targetCount: 0` **et** `fromHereCount: 0` : ce n'est donc pas une question de portée. Les deux côtés
rendent `[]`, mais pour des raisons possiblement différentes (le port par manque de seeding, §5 ; le
natif pour une raison non établie). **Ce n'est pas un accord.** `1107` est portée et **NON
CONFRONTÉE sur un régime acceptant**.

Prochain étage à lire, nommé : `IdunBattle.Entities.UnitExtensions$$IsFriend(unit, caster, entities)`
quand `unit` est **morte** — son `GetCurrentPlayer(...)` peut rendre `null`, ce qui fermerait le
lambda `b__0` et rendrait le gate inatteignable par cette voie.

---

## 5. Le seeding manquant — résidu `#1033-r3`

`decisionView.units[].killerId` **publie** le tueur (mesuré : `81`), et `load_state` laisse pourtant
`UnitComponent.death_source` à `None`. Tout gate qui lit `death_source` est donc structurellement
aveugle aux morts survenues hors du runner Python — dont celui de `1107`. Le lecteur du canal existe
déjà (`effects_state.melee_defeats_by_killer`) ; il s'agit de le brancher au chargement.

---

## 6. La face DÉCISION — résidu `#1033-r2`

`IdunBattle.AI.Playbook.Loki.RevealPlaybook` **existe**. La RE est faite (§ ligne de dette de
`probe_1021`) : utilité **constante** `Fix64(1)`, filtre `WillNormalAttackKill` (on écarte les cibles
qu'une attaque normale tuerait). Inscrite en `SANS_VERDICT` au registre de dette — la porter fera
descendre la dette.

> ⚠ **Témoin gardé dans le code** : le docstring de `loki/reveal.py` a d'abord affirmé « aucun
> `RevealPlaybook` n'existe, c'est une ABSENCE mesurée » **sans avoir interrogé le binaire**.
> `search_symbols_by_name` a rendu trois symboles. Une déduction non lue est une hypothèse.

---

## 7. Validation

- **34 tests offline** (`tests/engine/runner/test_1033_reveal_offline.py`), 7 étages, montage en
  fixture nommée `MontageReveal`, contre-épreuves par conjoint.
- **12 mutants adversariaux** (`probe_1033_mutants_reveal.py`), **12/12 vus ROUGES** — masque,
  sélecteurs, durée, chaque conjoint du gate, tri-état de l'effet, face native, et les deux mutants
  qui restaurent le défaut de l'audit.
- Cliquets de registre rejoués **verts** : `test_1021_face_decision_au_registre_offline` (40),
  `test_ability_registry_ratchet`, `test_targeting_options_sources`,
  `test_996_no_op_silencieuses_offline`, `test_437_r1_face_lists_cells_offline`,
  `test_519_comptes_derives_offline`, `test_909_decision_actives_offline` (33),
  `probe_181_targeting_gaps` (175/175, 0 manquante), `probe_120` étape 0 (aucun littéral manquant).
- **Non couvert** : le régime live où le natif ACCEPTE une cible (§4), le canal COUPS (§3), la face
  décision (§6).

> `probe_437r1r1r1_effect_face_table.py` rend `FAIL (rc=3)` — **déjà à `bcd6215c`**, avec les mêmes
> trois noms non résolus (`HeadClaimer_ExtraDmg`, `IconOfObstinacy_ExtraDmg`,
> `WayOfTheShortBlade_DamageBuff`). Vérifié en arbre témoin : ce n'est pas le fait de cette tranche.
> `RevealedEffect` s'y apparie proprement (96 → 97 classes, 0 divergence).
