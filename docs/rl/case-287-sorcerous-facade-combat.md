# Case #287 — SorcerousFacade (1100) : la face COMBAT

**Statut** : PORTE + VALIDE LIVE (3 bras, accord bit-exact). La face DECISION etait deja portee
(#27-4e, cf. `case-27-custom-utility.md` §`SorcerousFacade (1100)`) ; le moteur savait DECIDER de
lancer 1100 mais l'EXECUTION etait un no-op silencieux. Elle ne l'est plus.

Porteur : `thousTzaangor` « Yazaghor » (ThousandSons, HERO, dans le pool spawnable — aucun
`catalog_inject` requis). Allie Psyker de test : `thousSorcerer`.

## 1. L'artefact natif — QUATRE termes, quatre observables

`IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$ExecuteBehaviour`, MIRROR du
decompile (chaine `AbilityBehaviour.op_Addition`) :

```
sel = Cache( First( SortByDistance( ValidNormalAttackTargets(Caster@0x48, CasterTile@0x50,
                                                             range = null,
                                                             ignoreRule/additionalRule = VIDES),
                                    Caster@0x48 ),
                    1, 0 ),
             true )
[1] AddEffect( 0x4b4 = 1204 SorcerousFacade_AdditionalHits, AbilityStateReference,
               source = Caster@0x48, targets = op_Addition(Caster@0x48, Target@0x60),
               turns = TurnsFromRounds(1) )
[2] UseActiveAbility( Caster@0x48, sel, UnitNormalAttackType(Caster@0x48), <options> )
[3] KillDeadUnits( Caster@0x48, sel )
[4] TriggerAbilityDelayed( Owner@0x30, 0x49c = 1180 SorcerousFacade_Switch, unitSelectionType = 3 )
AActiveAbility.Execute( (((([1] + [2]) + [3]) + [4]) )
```

**DEUX RAILS, et les confondre est LE piege** : la cible du CAST (`Target@0x60`) est un **ALLIE
Psyker** (masque `TargetIsFriendly`) ; `sel` est l'**ENNEMI le plus proche** attaquable a l'attaque
normale — c'est LUI qui prend l'attaque. C'est deja ce que la face DECISION predit (#171).

`...SorcerousFacadeAbility$$GetTarget` construit EXACTEMENT le meme `sel` : un seul artefact natif,
partage entre les deux faces.

### La triggered 1180 (le terme [4])

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SorcerousFacade_SwitchAbility$$CreateBehaviour` :

```
IfAlive( Caster@0x48,
         KillDeadUnits( Killer(Target@0x60), Target@0x60, ForClearDeadUnits() )
         & If( IsAlive(Target) | (NOT IsAlive(Target) & IsCanAddUnit(Target)),
               SwitchPosition( Caster@0x48, Target@0x60 ) ) )
```

Deux identites RELUES qui evitent d'inventer des noeuds :
* `DSLBehaviors$$IfAlive(sel, then, else)` = LITTERALEMENT `If(DSLTriggers$$IsAlive(sel), then, else)` ;
* `DSLTriggers$$IsCanAddUnit(sel)` = `AmountIsGreater(DSLSelectors$$CanAddUnit(sel), Direct(0))`.

`DSLBehaviors$$SwitchPosition(u1, u2)` = `DisplaceUnitBehaviour(direction = 5, u1, u2, options,
targetSelectionType = 2)` -> case **5** du switch d'`IdunBattle.Operations.DisplaceUnitOperation$$
Execute` = `...$$SwitchPosition`, ou vit toute la logique :

```
deadCaster = HasFlag(caster, UnitFlag.Dead = 6) ; deadTarget = HasFlag(target, 6)
if (IsTemporary(tileCaster) || IsTemporary(tileTarget)) { gate slot 0x92 }   # NON PORTE
if (!deadTarget) MoveUnit(target -> tileCaster)
if (!deadCaster) MoveUnit(caster -> tileTarget)
if (!deadTarget) EventAndAbilitiesAndEffects(caster, target, ...)            # On(UnitDisplaced)
if (!deadCaster) EventAndAbilitiesAndEffects(caster, caster, ...)
```

Les deux moities sont **INDEPENDANTES** (une unite morte ne bouge pas, l'autre y va quand meme) et
l'ordre est **cible d'abord, caster ensuite** — ce n'est pas un swap atomique.

### L'effet 1204 (le terme [1])

`IdunBattle.Entities.Effects.Loki.SorcerousFacade_AdditionalHitsEffect$$CreateAdditionalHits` a un
corps **IDENTIQUE INSTRUCTION POUR INSTRUCTION** a `...SquigHound_AdditionalHitsEffect$$
CreateAdditionalHits` (memes appels, memes constantes `0x2f`/`0`/`1` ; seules les gardes de cctor
different). Le port en est donc le CLONE parametre par la config de 1100 :

```
EffectAdditionalHits.Create( trigger = get_OwnerIsCaster       (SEUL conjoint : ni melee ni ranged),
                             damage  = GetMinMaxDamage(this, 0) = RandomAmount(minDmg, maxDmg),
                             additionalHitsType = 1,
                             profile = GetDamageProfile(config).Value = Psychic,
                             hits    = Get(GetNumberConstant(0x2f = nrOfHits)) = 1,
                             predictionDamage = GetMinMaxDamage(this, 1) )
```

C'est le `+728-1455 Psychic` de l'i2 : le BUFF sur les attaques suivantes, **pas** le degat du cast
(#171). Canal #179 (`additional_hit_groups`).

## 2. La regle dynamique — portee, et ce n'etait PAS cosmetique

`...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` (mirror verbatim) :

```
if (HasTrait(target, 0x3ea = Psyker)) {
    if (battleQuery.<slot 0x40>(caster, casterTiles, GetNormalAttackType(caster))) return 0;
}
return 2;                                  # TargetingRule.TargetMatchesDynamicRule
```

Le slot 0x40 est `IdunBattle.Core.Services.BattleQuery$$HasValidTargets`
restreint a l'`ActiveAbilityType` de l'attaque normale du caster ; mirror = « l'ensemble
`valid_normal_attack_targets(state, caster)` est NON VIDE », c'est-a-dire EXACTEMENT la source que
`sel` consomme.

**Pourquoi elle est portee et pas laissee en residu permissif** : le bras `--far-foes` du probe la
mesure. Les deux ennemis hors de portee -> le natif rend `ok = True` et **NE MUTE RIEN** (refus
silencieux, signature #111), la ou le port sans la regle posait l'effet 1204 sur DEUX unites ET
echangeait les positions. Une degradation « permissive » qui MUTE l'etat n'est pas benigne.

## 3. Le masque de ciblage — MIGRATION de source

`...SorcerousFacadeAbility$$.ctor` prend la surcharge **FLAGS DIRECTS** (ni preset statique recopie,
ni surcharge PRESET+flags — aucun des deux pieges a masque ne s'applique) :

```
TargetingOptions..ctor(&opts, isSelfCasting = 0,
                       range = <TargetingRange statics+0x48 = UseWholeBoard>,
                       forceMeleeTarget = 1 (RangedBool.False), rules = 0x402, 0, 0)
AActiveAbility..ctor(this, &opts, 2)                       # AbilityAttackType.Others
```

`0x402` = `TargetIsFriendly | TargetMatchesDynamicRule`. Ce masque etait dans
`TARGETING_OPTIONS_UNPORTED` (pose par #217) ; il **MIGRE sur la classe** avec la face COMBAT, comme
l'exige le contrat de disjonction. `ABILITY_ATTACK_TYPE[1100] = Others` (litteral `2` du ctor) est
pose dans le MEME commit.

**La table `TARGETING_OPTIONS_UNPORTED` devient VIDE**, et c'est un ETAT, pas un oubli : elle
n'avait que cette entree. Le test de disjonction passerait desormais trivialement -> un test
NOUVEAU (`test_la_deuxieme_source_reste_CONSULTEE_meme_table_vide`) injecte une entree BIDON par
monkeypatch et verifie que `targeting_options_for` consulte toujours la 2e source. Le MECANISME
reste garde independamment du contenu.

## 4. Ce que le port a du construire

| piece | ou | note |
|---|---|---|
| `ValidNormalAttackTargets` (selecteur S) | `entities/selectors/units.py` | passe par `ctx.valid_normal_attack_targets` |
| `valid_normal_attack_targets` + `NORMAL_ATTACK_TARGETING_OPTIONS` | `runner/abilities/targeting.py` | REUTILISE la cascade `get_invalid_target_reason` avec le masque de l'attaque normale |
| `SwitchPosition` (feuille E) | `runner/abilities/behaviours/movement.py` | wrapper mince |
| `SwitchPositionOperation` | `runner/operations/displace.py` | case 5 de `DisplaceUnitOperation$$Execute` |
| `TriggerAbilityDelayed` (feuille E) + son registre | `runner/abilities/behaviours/lifecycle.py` | collapse INLINE, cf. §5 |
| `MoveUnitOperation(set_moved=...)` | `runner/operations/movement.py` | `MoveUnitOptions+0x11`, cf. §5 |
| `SorcerousFacadeAdditionalHitsEffect` (1204) | `entities/effects/loki/hits.py` | clone de SquigHound |
| `SorcerousFacadeAbility` + les deux arbres | `runner/abilities/loki/facade.py` | |

### Le masque de l'attaque NORMALE, relu

`IdunBattleLogic.Entities.Abilities.Active.Loki.Loki_NormalAttackAbility$$.ctor` recopie les 0x40
octets de `<TargetingOptions statics>+0x00`, ecrits par `...TargetingOptions$$.cctor` :
`isSelfCasting = 0`, `range = TargetingRange statics+0x00` (= `RANGE_ADJACENT_IF_MELEE_CASTER`),
`forceMeleeTarget = 2` (`RangedBool.IfRangedCaster`), **`rules = 0x4002`** =
`TargetIsEnemy | TargetMatchesDynamicRule`. C'est ce masque que
`ValidNormalAttackTargetsSelector$$Select` obtient du slot 0x3e d'`IBattleQuery` avant d'appeler
`TargetingQuery.GetValidTargets(unit, tiles, options)`.

## 5. Les deux quirks que la MESURE a tranches (pas la lecture)

**(a) Le differe s'execute DANS le cast.** Le natif PLANIFIE le [4] (service de triggers differes) ;
le port le COLLAPSE inline, en queue d'arbre — meme collapse que `MasterOfTheTutelaries_Summon`
(#202-C), et pour la meme raison (pas de scheduler offline). La mesure TRANCHE : les positions sont
deja echangees au retour d'`applyAction`. Si elles ne l'avaient pas ete, le collapse aurait ete FAUX.
⚠ Le collapse n'est fidele QUE parce que le differe est le DERNIER terme de l'arbre — ne pas le
generaliser en silence a un call-site ou il ne le serait pas.

**(b) Le switch ne pose PAS `UnitFlag.Moved`.** Le natif passe a `MoveUnit` un `MoveUnitOptions` NON
nul dont l'octet `+0x11` gate `SetMovedFlag`. MESURE (`combatSnapshot.units[].unitFlags` AVANT/APRES
le cast) : le caster teleporte gagne `[ArrivedAtFinalTile, ActiveAbilityUsed, TurnFinished,
NoActionAvailable]` et **PAS `Moved`**. Le port posait `Moved` (il passe par `MoveUnitOperation`,
qui appelle `set_moved_flag` inconditionnellement) -> d'ou le parametre `set_moved`, `False` au seul
call-site `SwitchPositionOperation`. Sans ce correctif, un cast ulterieur du meme tour aurait ete
refuse a tort par `CasterHasNotMoved` (0x10).

## 6. Validation

Montage : `scripts/python/probe_287_facade_combat.py` (build isole board `MC1_67`, drive des
positions des DEUX camps, snapshot pre-cast, cast LIVE, replay OFFLINE sur le MEME `state.rng`,
A/B causal registre ON/OFF). Garde : `tests/engine/runner/test_sorcerous_facade_combat_live.py`
(**9/9 PASS**).

| bras | geometrie | natif | port |
|---|---|---|---|
| `base` | `ultraTitus` colle (d=1), `ultraCalgar` loin | switch (1,0)<->(0,4) ; Titus 9537 -> **5223** ; 1204 sur caster+allie | **identique, bit-exact** |
| `swap` | `ultraCalgar` colle, `ultraTitus` loin | switch ; **Calgar** 9537 -> **6642** ; Titus INTACT | **identique, bit-exact** |
| `far` | les DEUX ennemis hors de portee | `ok=True`, **aucune mutation** (refus silencieux) | refus `invalid_target = 2` |

Points DISCRIMINANTS (ce qui interdit de conclure d'un accord trivial) :

* **le selecteur suit la DISTANCE, pas l'ordre d'enumeration** : `base` frappe l'id 77, `swap`
  frappe l'id 79. Un port qui prendrait « le premier enumere » (ordre d'id) frapperait 77 dans les
  DEUX bras ;
* **l'ordre [1] avant [2] est observable** : le degat total 4314 = 2325 (attaque normale) + **1989
  Psychic** (`additional_hits`) — l'effet pose par [1] alimente DEJA l'attaque de [2] ;
* **A/B causal** : le MEME etat rejoue avec 1100 retire d'`ABILITY_CLASSES` laisse positions ET PV
  INCHANGES ;
* **rail allie** : `abilityTargets` natif ne rend QUE l'allie (`[83]`) pour 1100 — non-regression du
  VETO #217 vue depuis la face COMBAT ;
* **bras `far`** : le seul ou l'observable attendu est « RIEN ne se passe » — donc le seul ou un
  port trop permissif se voit.

Non-regression re-jouee : `test_sorcerous_facade_decision_live.py` **8/8** (la face DECISION est
INCHANGEE : le masque a la meme valeur, seule sa SOURCE change), `test_targeting_options_sources.py`
+ `test_ability_registry_ratchet.py` **39/39** (avec `test_ability_target_gate_lot181_live.py`),
`test_the_quickening_live.py` + `test_thunderous_assault_push_live.py` **3/3** (les consommateurs de
`MoveUnitOperation`), `test_additional_hits_amount_bounds_live.py` **5/5** +
`test_attack_nature_gates_offline.py` (canal #179). Cliquets : `probe_181` (95 abilities, **0**
masque manquant), `probe_120` etape 0 (**0** litteral manquant), `probe_249`, `probe_273`.

## 7. Residus NOMMES (non couverts)

1. **`UnitFlag.NoActionAvailable` (4)** — le natif le pose en queue de cast
   (`IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation`, jamais portee). Residu
   **TRANSVERSE** au turn-flow, pas propre a cette ability ; le test le NOMME au lieu de le taire
   (l'assertion exige que l'ecart de flags soit EXACTEMENT `{4}`).
2. **La garde `IsTemporary` du switch** (+ son slot d'interface 0x92) : le port n'a pas de tuile
   TEMPORAIRE, `board` est statique.
3. **Les branches `dead_caster` / `dead_target` de `SwitchPositionOperation`** sont PORTEES mais NON
   CONFRONTEES : le gate de cible (`TargetIsFriendly` + la regle dynamique) et le `IsAlive(Caster)`
   de la triggered rendent l'etat difficile a atteindre par un cast normal. Le levier existe
   (`--dmg-target` pour tuer, puis cast) — a crafter si un jour un observable en depend.
4. **L'ordre d'enumeration de `ValidNormalAttackTargets`** : le natif enumere
   `GetPossibleTargetsForOptions` -> `GetUnitsInRange` ; le port enumere `state.entities`. Ne tranche
   qu'A DISTANCE EGALE sous le `SortByDistance` + `First(1)` (`OrderBy` LINQ est STABLE). Les deux
   bras mesures ont des distances distinctes.
5. **`unitSelectionType = 3`** du `TriggerAbilityDelayed` : conserve pour la tracabilite, jamais lu
   (le mode de resolution du selecteur natif n'est pas porte).
