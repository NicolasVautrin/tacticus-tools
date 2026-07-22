# Case-38 — `ReachedSummonCap` : fidélisation de la branche cap du gate DoctrinaImperatives (1118)

**Statut : PORT LIVRÉ (correct-par-RE, non-régressif) — branche cap PAS ENCORE exerçable live
(cf. §5, follow-up #38b).** Build `gqfc5mff6c`. Suite directe de `case-31` demi-partie B : le gate
3-branches de `DoctrinaImperativesPlaybook.EvaluateNonComparable @18112c8d0` était porté avec
`_reached_summon_cap` **hardcodé `False`** (champ offline manquant) → sous-tir du toggle quand le cap
de summons est réellement atteint (branche `count>0 & adj>0`).

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
aucun hook frais possible — reinject interdit pendant #39) : enfants ≈ squads `obs_units` de
`visualId == ability("ControlEdict").constants.unitId` (admecSmnVanguard) du **même camp** que le
caster, **morts inclus** (`obs_units` garde les dépouilles — même source que RitesOfRestoration,
cf. `project_decisionview_keeps_dead`). Le gate amont `HasTriggeredAbility(caster, ControlEdict)`
est structurel (l'unique porteur de DoctrinaImperatives porte ControlEdict) — non re-codé.

---

## §3 — Validation

1. **Sanity offline (contextes forgés) : 6/6 OK** — seuils 3/4/5 par niveau passif (1→3, 50→5),
   morts comptés (mirror all-ever), vid du camp adverse exclu, fallback sans `ability_config`
   (idx 0 → cap 3).
2. **RUN A — garde régression case-31-B (PASSÉE)** : seed 31337, roster
   `admecMarshall,admecManipulus,admecRuststalker` vs `necroWarden×2`, walk 9 steps (bataille finie) :
   **ability 5/5, move 8/8, prédiction 3/3, utilité 3/3 — zéro overfire 1118** (cap jamais atteint →
   changement inerte, attendu).
3. **RUN B — seed 38001, même roster, `--hp-target 250000 --hp-player 120000`, 60 steps** :
   **zéro overfire** (l'unique émission moteur 1118 = step 38, matchée). MAIS la branche cap n'a PAS
   été exercée : **aucun Skitarii n'a jamais spawné de tout le walk** (sonde `probe_38_children.py`,
   versionnée : `ever=0` sur 60 steps malgré ~10 attaques normales de Tan en stance Protector — cf.
   §5-b). Les 3 miss du walk (s32/s44/s50, `nc-pair` u81) sont **préexistants** (l'ancien port
   cap=False prenait les mêmes décisions) et relèvent d'un sous-mécanisme DIFFÉRENT du cap (§5-a).

## §5 — Découvertes annexes (sonde instrumentée + re-décompilé) → follow-up #38b

- **(a) Les émissions natives 1118 hors-cap contredisent notre reconstruction du gate.** Timeline
  sonde (dv effects) : Tan porte `ProtectorImperative` dès s01 ; le natif toggle CHAQUE TOUR dès t7
  (s32 P→C, s38 C→P, s44 P→C, s50 C→P) puis attaque. Sous-termes de NOTRE gate à ces steps :
  s38 `hv=False & conq=True` → émis (branche Conqueror) = MATCH ; s32/s44/s50 `hv=True, adj=2,
  cap=False (0 enfant)` → refus = MISS. Or le re-décompilé d'`EvaluateNonComparable @18112c8d0`
  (contrôle de flux relu ce jour) **CONFIRME** le modèle case-31 : `count==0 → ssi Conqueror ;
  count>0 → (adj>0 ? ReachedSummonCap : émettre)`. Avec 0 enfant, `ReachedSummonCap=False` ⇒ le
  natif n'a pu émettre à s32/s44/s50 que si SON `count==0` (≠ notre `hv=True`) ou SON `adj==0`
  (≠ notre `adj=2`). Suspects : la **sémantique du slot 0x51** (résolu « GetAdjacentUnits tout
  camp » en case-31 — même RE qui a produit le faux per-player #39 ; peut être friends-only, ou
  filtré unités-vraies via les params de `GetUnitsOnTiles`), ou `GetEligibleTargetsForNormalAttack`
  ≠ notre `_has_valid_targets`. **Plan discriminant** (micro-états craftés, doctrine positions
  pilotées) : Tan en P, 0 enfant, cible attaquable depuis sa tuile, UN ENNEMI adjacent et AUCUN ami
  → modèle tout-camp : pas d'émission ; modèle friends-only : émission. Variantes ami-seul /
  personne. À mener AVANT tout re-fit du port.
- **(b) ControlEdict ne summone JAMAIS dans les walks runner** malgré stance P + attaques normales.
  RE fait : `CreateTrigger @180e1d500` = `On(0x26, !(OwnerIsCaster & TriggeringAbilityIs(0x400=1024
  Burrowers_Appear))) & OwnerIsCaster` (la négation ne concerne PAS Tan) ; `CreateBehaviour
  @180e1d2c0` = `If(HasEffect(Self, 1247 ProtectorImperative)) → SummonMinion` +
  `If(HasEffect(Self, 1248 ConquerorImperative)) → Foreach(UnitsWithTrait(UnitsWithTrait(
  AdjacentFriends(Self,1,3), 2,3), 5,3), <attack>)`. Le gate stance est SATISFAIT (P présent dès
  s01) et le trigger devrait pomper sur ab=69 (On(38) natif pompe bien en runner — prouvé #35 Ice).
  Cause à élucider (#38b) — la validation LIVE de la branche cap en dépend.
- NB enum : `0x4b0=1200` est un **TriggeredAbilityType** (=ControlEdict) — l'`ActiveAbilityType`
  1200 est SquigLaunchas (les deux enums se recouvrent numériquement, toujours qualifier).

## §4 — Résidus

- **Summon `RemoveUnit`-ed** (retiré du board, pas seulement mort) : sort d'`observeBattle.units`
  (projection par UnitFoot avec tuile résolue) → sous-compte vs liste native. Aucun chemin connu
  qui remove un Skitarii ControlEdict en pratique.
- **2 Marshals dans le même camp** : l'approx identité par (vid, camp) poolerait leurs comptes ;
  le natif compte par-caster. Setup non standard, non couvert.
- **Branche `IsActive` de ReachedSummonCap** (abilities de summon ACTIVES) : non exercée par 1118
  (ControlEdict est triggered) — à mirrorer si un autre playbook consomme le slot 0xc9 avec une
  active (aucun caller connu à ce jour).
- Le lien parent→enfants EXACT nécessiterait un RPC (hooks frais) — à considérer si un miss
  d'agreement expose l'approximation identité.

## VAs

`ReachedSummonCap @181070f60` · `GetChildrenCount @180ecf290` · `GetChildrenUnits @180ecf520` ·
`GetChildren @180ecf700` · `GetParent @180ed1d70` · `ParentComponent..ctor @180fa6880` ·
`ChildComponent..ctor @180f97610` · `Blueprints.Unit @180eb3a3d` · `Blueprints.Machine @180eb2d46` ·
`RemoveUnitOperation.Execute @180e8add0` · `EvaluateNonComparable @18112c8d0` ·
`ControlEdictAbility.SummonMinion @180e1d5e0` · `GetVariableForLevel` (var 0x31=49 maxSummons).
