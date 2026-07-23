# Case-38 — `ReachedSummonCap` : fidélisation de la branche cap du gate DoctrinaImperatives (1118)

**Statut : RÉSOLU + VALIDÉ (#38b, 2026-07-23).** Build `gqfc5mff6c`. Suite directe de `case-31`
demi-partie B : le gate 3-branches de `DoctrinaImperativesPlaybook.EvaluateNonComparable @18112c8d0`.
Le port émettait 1118 correctement SAUF sur la branche `count>0 & free>0 → ReachedSummonCap`, qui
sous-tirait **parce que `_reached_summon_cap` comptait les summons par le MAUVAIS visualId** (cle de
config `admecSmnVanguard` au lieu du `visualId` LIVE `admecNpc1Vanguard`) → 0 enfant vu → cap toujours
`False` → misses s32/44/50 du walk 38001. **De plus, la sémantique du slot 0x51 héritée de case-31
(« GetAdjacentUnits TOUT CAMP ») était FAUSSE** : le slot 0x51 = `GetFreeAdjacentTiles` (tuiles LIBRES
adjacentes), corrigé #38b. Les DEUX mystères de #38b (sémantique du gate + « summon inerte en runner »)
sont le MÊME artefact d'observation : le mauvais visualId. Voir §5.

---

## §1 — Artefact natif (décompilé = vérité)

### `BattleQuery.ReachedSummonCap @181070f60` (slot BattleQuery 0xc9)

Signature : `bool ReachedSummonCap(this, unit, Nullable<AbilityType> at)`. Appelé par le gate 1118
avec `at = ControlEdict 0x4b0=1200` (le PASSIF de Tan Gi'da — ability **TRIGGERED**).

```
si at.IsTriggered() et HasTriggeredAbility(unit, at):        # branche empruntée (ControlEdict)
    state  = GetAbilityState(unit, at)                        # -> .level
    config = <configs triggered du service this+0x48>[at] |> FirstOrDefault
    cap    = AbilityConfiguration.GetVariableForLevel(config, 0x31, state.level)
    return cap <= GetChildrenCount(unit, this+0x38 /*entities*/, predicat=null)
sinon si at.IsActive() et HasActiveAbility(unit, at):         # branche symétrique (actives)
    ... même formule (config via at direct)
sinon: return false
```

- **`0x31` = 49 = `maxSummons`** (enum `IdunBattle.Configuration.AbilityVariableType`, dump
  `il2cpp_enums.tsv` : `...48=armorReduction,49=maxSummons,50=landmineDmg,51=extraSummons...`).
- `ControlEdict.variables.maxSummons` (gameconfig) = tableau per-niveau :
  **3** (L1-26), **4** (L27-35), **5** (L36+).
- `level` = celui de l'**ability state** de ControlEdict = **niveau PASSIF** du caster.

### `UnitExtensions.GetChildrenCount @180ecf290` — compte BRUT, dépouilles incluses

`GetChildrenCount(unit, entities, predicat)` : `TryGetComponent(unit, ParentComponent)` → itère la
liste d'ids enfants à `component+0x10` ; pour chaque id, fetch l'entité ; **si `predicat == null`
(cas ReachedSummonCap) : incrémente inconditionnellement**. Aucun filtre vivant, aucun filtre type.

La liste `ParentComponent.children` est **append-only** :
- créée VIDE pour toute unité par `Blueprints.Unit @180eb3a3d` / `Blueprints.Machine @180eb2d46`
  (seuls xrefs du ctor `ParentComponent$$.ctor @180fa6880`) ;
- alimentée au spawn (`AddUnitOperation`, qui porte aussi `InherentAbilitiesLevelFromParent`) ;
- **JAMAIS purgée** : `RemoveUnitOperation.Execute @180e8add0` ne touche que les listes
  `units`/`removed` du **PlayerComponent** (+0x30/+0x38) — le composant relu est celui du JOUEUR
  (son id nourrit ensuite `GetAmountOfTurnsStartedByPlayer`), PAS `ParentComponent` ; aucune API
  `RemoveChild` n'existe sur `ParentComponent` (ctor/Copy/GetComponentId/ToString seulement).

⇒ **`GetChildrenCount(caster)` = nombre TOTAL d'enfants jamais spawnés par le caster, morts
inclus.** Sémantique volontairement DIFFÉRENTE du cap runner-face (`ControlEdictAbility.SummonMinion
@180e1d5e0` : Skitarii **vivants** — un mort libère le re-summon) : côté playbook, un cap « plein de
morts » suffit à déclencher le toggle Conqueror.

Côté enfant : `ChildComponent` (+0x10 = id parent, lu par `UnitExtensions.GetParent @180ed1d70`),
créé lui aussi au blueprint.

---

## §2 — Port

Fichiers :
- `engine/playbook/noncomparable/doctrina_imperatives.py` — `_reached_summon_cap` : mirror
  `cap = ability_var("ControlEdict", "maxSummons", level_passif)` ≤ compte enfants.
- `engine/playbook/noncomparable/_base.py` — `NCContext.ability_config` : callable
  `uid -> {"active","passive","multiplier"}` (combatSnapshot, expose DÉJÀ `passiveAbilityLevel`).
- `engine/ai/action_generators.py` — branchement `ability_config=ctx.heal_config` (le cache
  `_ACTIVE_LEVEL_CACHE` du contexte porte déjà les 3 champs).

**Approximation d'identité offline** (aucun lien parent→enfants dans decisionView/observeBattle,
aucun hook frais possible) : enfants ≈ squads `obs_units` du summon ControlEdict du **même camp** que
le caster, **morts inclus** (`obs_units` garde les dépouilles — même source que RitesOfRestoration,
cf. `project_decisionview_keeps_dead`). **Le nom à matcher est le `visualId` LIVE
`admecNpc1Vanguard` = `gameconfig.unit(constants.unitId).visualId`, PAS la clé de config
`admecSmnVanguard`** (cause racine #38b, cf. §5). Le gate amont `HasTriggeredAbility(caster,
ControlEdict)` est structurel (l'unique porteur de DoctrinaImperatives porte ControlEdict) — non re-codé.

---

## §3 — Validation

1. **Sanity offline (contextes forgés) : 6/6 OK** — seuils 3/4/5 par niveau passif (1→3, 50→5),
   morts comptés (mirror all-ever), vid du camp adverse exclu, fallback sans `ability_config`
   (idx 0 → cap 3).
2. **RUN A — garde régression case-31-B (PASSÉE)** : seed 31337, roster
   `admecMarshall,admecManipulus,admecRuststalker` vs `necroWarden×2`, walk 9 steps (bataille finie) :
   **ability 5/5, move 8/8, prédiction 3/3, utilité 3/3 — zéro overfire 1118** (cap jamais atteint →
   changement inerte, attendu).
3. **RUN B (post-fix #38b) — seed 38001, même roster, `--hp-target 250000 --hp-player 120000`,
   55 steps** : les 3 miss `nc-pair` u81 s32/s44/s50 (1118 cap-branch) deviennent des **HITS**
   (`1118→81` == natif), **zéro nouvel overfire**. Généralisation seeds **54321** (s32/38/44 hit) et
   **2468** (s37/43/49 hit) : mêmes verdicts, 0 overfire 1118, sur des trajectoires de summon
   distinctes. Guard **31337** : ability 5/5, move 8/8, pred 3/3, util 3/3 (cap jamais atteint →
   1118 inerte, comme case-31-B). Miss résiduels (s7/s33 : cible de l'attaque 69 ; 1119/1123 sur
   u83/u85) **préexistants et hors périmètre** (aucun ne touche 1118).

## §5 — RÉSOLU (#38b, 2026-07-23) : les deux mystères = UN artefact d'observation (mauvais visualId)

**Cause racine UNIQUE** : le summon ControlEdict est le config `admecSmnVanguard` (= `constants.unitId`),
mais son champ `visualId` (ce que `observeBattle`/`decisionView` exposent LIVE) vaut
**`admecNpc1Vanguard`**. `probe_38_children.py` ET `_reached_summon_cap` comptaient les enfants par
`visualId == admecSmnVanguard` → **jamais aucun match** → cap toujours `False` ET « aucun summon
observé ». Les deux « mystères » de #38b étaient la MÊME cécité.

### (b) ControlEdict summone bien — RÉSOLU (artefact d'observation)
`probe_38b_summons.py` (walk 38001, comptage par TOUS les visualId) : **7 `admecNpc1Vanguard`
distincts** apparaissent (croissance 3→4→5→6→7 le long du walk), pas 0. Le trigger On(38) pompe, le
summon spawne — `probe_38` regardait le mauvais nom. (Le test `test_control_edict_live` documentait
déjà `SUMMON_VIS=admecSmnVanguard` cle vs `SUMMON_LIVE_VIS=admecNpc1Vanguard` visualId.)

### (a) La branche cap — RÉSOLU (mirror corrigé + slot 0x51 refait)
Modèle 3-branches **CONFIRMÉ au désassemblage** (`EvaluateNonComparable @18112c8d0`, capstone) :
`count==0 → ssi Conqueror ; count>0 & GetFreeAdjacentTiles(caster)==0 → émettre ; count>0 & free>0 →
ssi ReachedSummonCap`. Deux corrections :

1. **Slot 0x51 = `GetFreeAdjacentTiles` @181061650, PAS `GetAdjacentUnits`.** Le verdict case-31
   (« GetAdjacentUnits TOUT CAMP », même lot de RE que le faux per-player #39) était FAUX :
   `GetAdjacentUnits` prend 3 params (from/friendsOf/enemiesOf) et ne matche pas le dispatch à
   **1 argument** du call-site (`FUN_180003bd0(0x51, itf, service, caster)`). Résolu LIVE via
   `resolveVtableSlot` sur `BattleQuery` (ancre slot `0xc9`=ReachedSummonCap @181070f60 → slot `0x51`=
   `GetFreeAdjacentTiles`) ; corroboré par `aggressive_onslaught.py` (déjà porté slot 0x51 = free
   tiles). @181061650 = `GetAdjacentTiles(caster,1,1,1)` puis `FilterInPlace(CanAddUnit(tile,world,
   1,0,0))` = tuiles WALKABLE+VIDES+|dElev|<2 adjacentes. Mirror = `battle_query.adjacent_addable_count`.
2. **`_reached_summon_cap` : compter par `visualId` LIVE.** Résoudre `constants.unitId → gameconfig
   .visualId` (`admecSmnVanguard → admecNpc1Vanguard`) avant de compter `obs_units` (morts inclus =
   all-ever, mirror de `GetChildrenCount` append-only).

**Preuve de CAUSATION (pas corrélation)** — `probe_38b_capAB.py`, A/B natif, MÊME tuile (4,7),
count fixe (fh=2), free>0 dans les deux bras :
| instant | summons (cap) | free_adj | `ncEvaluate` leaf natif |
|---------|---------------|----------|-------------------------|
| A       | 0 (False)     | 6        | **PAS d'émission**      |
| B       | 5 (True)      | 2        | **émission (util 100)** |

Seul le cap change → l'émission flippe : la branche cap EST le déterminant (et à free=6>0, A n'émet
PAS → réfute tout « adj==0 → émettre » ; valide aussi que le mirror free-adj est fidèle : le natif
voit AUSSI free>0). Oracle par step (`probe_38b_gate.py`) : port `_should_emit` == leaf natif sur
**14/14 steps Tan** (s32/44/50 : miss→hit ; s27 cap=True mais count==0/conq=False → pas d'overfire ;
s33/45/51 gate ouvert mais once-per-turn `_usable`=False → port joue 69 comme le natif).

- NB enum : `0x4b0=1200` est un **TriggeredAbilityType** (=ControlEdict) — l'`ActiveAbilityType`
  1200 est SquigLaunchas (les deux enums se recouvrent numériquement, toujours qualifier).

## §4 — Résidus / non couverts

- **Branche `free==0` (Tan encerclé → émettre inconditionnel)** : confirmée au DÉSASSEMBLAGE (`jle
  cb1d` saute vers le MÊME bloc `GenerateAction(Fix64(100))` que la branche cap-true, elle-même
  validée live par l'A/B), mais **PAS craftée live** — surround complet impraticable (tuile 5-6
  voisins vs 3 unités mobilisables ; corner degré 2 `(6,8)` atteignable en théorie mais drive
  cross-board AI-gated non fiable en <30 tours). Risque résiduel = mon mirror `adjacent_addable_count`
  SUR-compterait (free>0 quand natif free==0) → je prendrais la branche cap au lieu d'émettre → un
  MISS (jamais un overfire) dans l'état rare « Tan totalement encerclé ». Non observé.
- **Summon `RemoveUnit`-ed** (retiré du board, pas seulement mort) : sort d'`observeBattle.units`
  → sous-compte vs `GetChildrenCount` (append-only). Aucun chemin connu qui remove un Skitarii
  ControlEdict en pratique.
- **2 Marshals dans le même camp** : l'approx identité par (visualId, camp) poolerait leurs comptes ;
  le natif compte par-caster (ParentComponent). Setup non standard, non couvert.
- **Branche `IsActive` de ReachedSummonCap** (abilities de summon ACTIVES) : non exercée par 1118
  (ControlEdict est triggered) — à mirrorer si un autre playbook consomme le slot 0xc9 avec une
  active (aucun caller connu à ce jour).

## VAs

`ReachedSummonCap @181070f60` (slot itf 0xc9) · `GetChildrenCount @180ecf290` ·
`GetFreeAdjacentTiles @181061650` (slot itf **0x51**, `<>b__96_0 @1810721f0` = `CanAddUnit(tile,
world,1,0,0)`) · `GetAdjacentTiles @18105b660` · `CanAddUnit @180ec4c60` ·
`GetEligibleTargetsForNormalAttack @18111ed00` (dispatch slot itf **0x41** `GetValidTargets`) ·
`GetChildren @180ecf700` · `GetParent @180ed1d70` · `ParentComponent..ctor @180fa6880` ·
`Blueprints.Unit @180eb3a3d` · `RemoveUnitOperation.Execute @180e8add0` ·
`EvaluateNonComparable @18112c8d0` · `ControlEdictAbility.SummonMinion @180e1d5e0` ·
`GetVariableForLevel` (var 0x31=49 maxSummons). Slots IBattleQuery résolus LIVE `resolveVtableSlot`
(ancre 0xc9=ReachedSummonCap) : 0x3f=HasValidTargets, 0x41=GetValidTargets, 0x44=GetAllValidTargets
FromAllPossibleMovementTiles, **0x51=GetFreeAdjacentTiles**, 0x7f=GetAdjacentEnemies, 0xc9=Reached
SummonCap.
