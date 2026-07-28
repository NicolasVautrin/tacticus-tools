# Case #222 — Lot « l'effet est porté, la POSE manque » : 4 maillons câblés (+ 1 prémisse réfutée)

**Status : 4 items LIVRÉS et CONFRONTÉS LIVE, RE décompilé-citée (build `gqfc5mff6c`). Zéro-régression
prouvée (garde agreement 31337 : prediction 21/23, utilité 23/23, ability 27/27 — identique au baseline
case-204).**

Patron commun du lot : l'**effet** était déjà porté et consommé, mais **rien ne le posait** → code
enregistré-mais-mort, no-op silencieux. Le travail est le **maillon de pose** (trigger / rotation /
accumulation / dispatch), pas l'effet.

| # | Porteur (HERO, tous dans `--list-pool` rank 17) | Ce qui manquait | VAs |
|---|---|---|---|
| 1 | `admecDominus` « Vitruvius » — MasterAnnihilator | pose du marqueur 1249 + **remove-by-source** | `CreateTrigger @18110ba90`, `CreateBehaviour @18110b940` |
| 2 | `blackObliterator` « Volk » — FleshmetalGuns | **rotation** turn-start `Modulo(UnitTurnsStarted,3)` des effets 1067/1212/1221 | `CreateTrigger @180e17450`, `CreateBehaviour @18121f6e0` |
| 3 | `emperNoiseMarine` « Shiron » — TerrifyingCrescendo | **accumulation** du stack de 1424 (+1, cap 6) | `CreateTrigger @1811a3910`, `CreateBehaviour @1811a3840` |
| 4 | `spaceRockfist` « Arjac » — AnvilShield | **dispatch `On(UnitBlocked=0x3d)`** → Ice sur la tuile de l'attaquant | émetteur `@180e25fc0` ; `ApplyIce @180e16500`/`@180e16480` |

---

## 1. MasterAnnihilator (admecDominus) — pose + remove-by-source

`MasterAnnihilatorAbility.CreateTrigger @18110ba90`
```
On(0x26 = NormalAttack) & get_OwnerIsCaster & AreEnemies(target@0x178, caster@0x160)
```
`MasterAnnihilatorAbility.CreateBehaviour @18110b940` (`AbilityBehaviour.op_Addition`)
```
RemoveEffect( OwnerOfEffect( EffectsFromUnitSource(self@0x148, 0x4e1) ), Nullable(0x4e1) )
+ AddEffect( 0x4e1 = 1249, AbilityStateReference, source = caster@0x160, cible = target@0x178,
             options = struct ZERO )
```
Le **remove-by-source** est un couple de sélecteurs : `EffectsFromUnitSource(Self, 1249)`
(`DSLFactory.EffectsFromUnitSource @180deec70` → `EffectWithTypeSelector`, keyé sur
`EffectComponent.SourceUnit @+0x10`) puis `OwnerOfEffect` (`@180df8350`) qui remonte aux **porteurs**.
Conséquence sémantique — le discriminant de validation : **le marqueur d'un AUTRE poseur n'est PAS
touché**.

**Port** : `runner/operations/triggers/loki/master_annihilator.py` (`MasterAnnihilatorMarkAbility`,
arbre `master_annihilator_tree()`) + `ABILITY_TRIGGERS["MasterAnnihilator"]` ; nouveaux sélecteurs
`EffectsFromUnitSource` / `OwnerOfEffect` (`entities/selectors.py`) + accesseur `ctx.effects_from_source`
(`entities_from_state`) ; `RemoveEffect` rendue MULTI-cible (le natif itère son sélecteur — les
call-sites mono-cible historiques `Caster()` restent bit-identiques).

**Résidu** : `MasterAnnihilator_AdditionalHitEffect.CreateRemoveEffectTrigger @180f58f40` =
`On(0=UnitDeath) & AreEqual(target@0x178, EffectSource(thisEffect))` (le marqueur se retire quand SA
source meurt) — **non porté** : il faudrait un registre d'effet-triggers « remove-self ». Le cap
`maxDmg` du coup bonus reste TODO (pré-existant, `hits.py:611`).

## 2. FleshmetalGuns (blackObliterator) — rotation turn-start

`CreateTrigger` de `FleshMetalGunsAbility` n'a **pas de symbole propre** (corps dédupliqué). Identifié
par la **table de pointeurs de méthodes** : xrefs DATA de `CreateBehaviour @18121f6e0` → `0x1830f97c8` ;
slot précédent `0x1830f97c0` = `0x180e17450` ; motif par classe `[.ctor, stub, CreateTrigger,
CreateBehaviour]` confirmé par le couple voisin `FleshMetalGuns_TileEffectAbility` (`0x1830f97d8` =
`@18121fbc0`, `0x1830f97e0` = `@18121fb40`). Corps :
```
On(0x16 = TurnStart_Actions) & df@0xa0
```
`df@0xa0`, construit par `DSLFactory.InitializeShared @180df2670` = `new <DAT_18320cc68>(df@0x148,
df@0x10)` — MÊME classe et MÊMES arguments que `DSLFactory.IsTurnOf @180df5780` appliqué à `Self@0x148`
⇒ **`IsTurnOf(Self)`** (la rotation fire au début du tour du PROPRIÉTAIRE).

`CreateBehaviour @18121f6e0`
```
Nothing() + RemoveEffect(Self,0x42b) + RemoveEffect(Self,0x4bc) + RemoveEffect(Self,0x4c5)
+ If(Modulo(UnitTurnsStarted(Self), Get(3), Get(1)), AddEffect(0x42b=1067 FocusedMalice, Self))
+ If(Modulo(UnitTurnsStarted(Self), Get(3), Get(2)), AddEffect(0x4bc=1212 RuinousSalvo,  Self))
+ If(Modulo(UnitTurnsStarted(Self), Get(3), Get(0)), AddEffect(0x4c5=1221 WarpHail,      Self))
```
`Modulo(a,b,c)` (`@180df69a0` → `ModuloAbilityTrigger.ShouldTrigger @180eeda30`) est un **PRÉDICAT**
(`a mod b == c`). `UnitTurnsStarted` (`@180dff280` → `@180f2d6c0`) = `GetStat(unit, 0xc)`, incrémenté
par `StartTurnOperation` **AVANT** l'émission de `On(0x16)` ⇒ au 1er tour de Volk le compteur vaut déjà 1.
**Cycle : `%3==1` Melta, `%3==2` Flame, `%3==0` HeavyRound.**

**Port** : `triggers/loki/fleshmetal_guns.py` (`FleshmetalGunsRotationAbility`, arbre
`fleshmetal_guns_tree()`) + `ABILITY_TRIGGERS["FleshmetalGuns"]` ; `UnitTurnsStarted` lit désormais le
VRAI compteur (`ctx.get_stat(unit, 0xc)`) quand le dict n'a pas le marqueur `_turns_started` posé par
`SpawnUnit` (le couple GetEmRuntz reste inchangé).

~~**Résidu** : le volet **DespoiledGround**~~ — **PORTÉ ET VALIDÉ LIVE (#85)**, cf.
`docs/rl/case-85-despoiled-ground.md`. `FleshMetalGuns_TileEffectAbility` (`On(0x10=DamageDealt) &
OwnerIsCaster & HasEffect(Self,0x4c5)` → `AddEffect(0x5c4=1476, Tiles(Target))`) est câblé, le
vecteur `On(0x10)` existe (émetteur RECTIFIÉ : c'est `IdunBattle.Operations.ApplyDamageOperation$$
Execute`, **pas** `ADamageOperation$$EvaluateAfterHitTriggers` qui n'émet que `0x3d` et `8`), et les
classes d'effet 1476/1478 + le DoT d'environnement sont portés.

## 3. TerrifyingCrescendo (emperNoiseMarine) — accumulation

`CreateTrigger @1811a3910` (disjonction `op_BitwiseOr`)
```
branche1 = On(0 = UnitDeath)          & get_OwnerIsActor & TargetIsOverkilled
branche2 = On(0x3e = PreEffectAdded)  & get_OwnerIsActor & TriggeringEffectIs(0x429 = 1065 Pinned)
```
`CreateBehaviour @1811a3840`
```
AddEffectOrIncreaseLevel(0x590=1424, AbilityStateReference, self@0x148, selector=self@0x148,
                         amount = df@0xc0 = Const(1),
                         max    = Direct(GetNumberConstant(0x62) = buffMaxLevel = 6))
```
`df@0xc0` est le nœud constant **1** alloué par `DSLFactory..ctor @180e020b0` (comparatif :
`HeadClaimerAbility @181220e30` passe le MÊME `df@0xc0` avec un `max` NULL).

**Deux VECTEURS D'ÉVÉNEMENT manquaient**, tous deux ajoutés à leur place EXACTE :
- `On(UnitDeath=0)` — `KillUnitOperation.Execute @180e76470` émet la séquence
  `1 (PreUnitDeath) → 2 → **0 (UnitDeath)** → 0x37 (UnitDefeated) → 0x36 (PostUnitKill)` ; le port
  n'émettait que `1` et `0x37` → `unit_death_triggers` inséré ENTRE les deux.
- `On(PreEffectAdded=0x3e)` — `AddEffectOperation.Execute @180e48940` l'émet **TOUT EN HAUT**
  (`FUN_180026490(0x50,…,0x3e)` **AVANT** le gate cible-nulle, **AVANT** le gate « déjà présent » et
  **AVANT** le gate d'immunité). C'est ce qui donne la sémantique i2 « **would have** Suppressed » :
  le compteur monte même quand le Pinned n'est pas réellement appliqué. **CONFIRMÉ LIVE** (§Validation B).
  L'`AbilityEntities` de cet événement est `ctor(source, source, target)` ⇒ **actor = la SOURCE**.

`AddEffectOrIncreaseLevel @180de6860` est une **FACTORY** : elle alloue
`ForeachBehaviour(selector, Func)` dont le lambda `b__0 @180e25540` construit, par élément,
`If(HasEffect(elem,type), IncreaseEffectLevel(elem,type,amount,max), AddEffect(type,…,{level=amount}))`.
Portée comme un **arbre** (`add_effect_or_increase_level`), pas comme un helper fusionné (doctrine #149).
Le clamp est le mirror EXACT d'`IncreaseEffectLevelOperation.Execute @180e73cb0` :
`if (!max || max < cur || cur+amount <= max) level += amount; else level = max` (quirk `max < cur`
conservé).

**Port** : `triggers/loki/terrifying_crescendo.py` (2 classes = 2 branches, comme ActOfFaith
accumulate/reset) + `ABILITY_TRIGGERS["TerrifyingCrescendo"]` ; feuille `IncreaseEffectLevel` +
factory `add_effect_or_increase_level` (`abilities/behaviours/effects.py`) ; `If` du DSL enrichi de sa
**branche `else`** (4ᵉ argument natif de `DSLFactory.If @180df1960`) ; `Foreach` NORMALISE un sélecteur
mono-entité (un dict compte pour UN élément — sinon Python itérait les clés).

Ceci **CLÔT le résidu #204** « Accumulation : NON re-simulée offline ».

## 4. AnvilShield (spaceRockfist) — dispatch `On(UnitBlocked)` (+ prémisse partiellement réfutée)

### Prémisse RÉFUTÉE pour l'effet 1202
`AnvilShieldAbility_ApplyAdditionalBlockAndBlockChance.CreateBehaviour @180e16340` pose
`AddStaticStatModifierEffect(Self, 0x4b2=1202, stat 8 BLOCK_DAMAGE, blockDmg)` +
`(Self, 0x4b0=1200, stat 7 BLOCK_CHANCE, blockChance)`. Son `CreateTrigger` est le corps dédupliqué
`@180e15880` (`return df@0xa8`) et `df@0xa8` est construit par `InitializeShared @180df2670` =
`On(0x21 = AbilityInit) & OwnerIsActor` — **ce n'est PAS un trigger on-block** : ce sont des
**owner-effects posés à l'INIT de l'ability**. GROUND TRUTH live : Arjac porte
`AnvilShield_AdditionalBlock` dès le premier `decisionView` d'un runner frais. ⇒ **rien à câbler** ;
la note « posé par le vecteur ON-BLOCK » de `hits.py` était une mis-attribution, corrigée.

### Ce qui manquait vraiment : le DISPATCH
`ADamageOperation.EvaluateAfterHitTriggers @180e25fc0` :
```
AbilityEntities.ctor(caster = param_3 (ATTAQUANT), owner = actor = target = param_4 (DÉFENSEUR),
                     casterTiles = GetTiles(attaquant), targetTiles = GetTiles(défenseur))
if (param_6 != 0)  emit On(0x3d = UnitBlocked)      # le flag BLOCK
                   emit On(8  = AttackHit)          # TOUJOURS
```
Le port RÉSOLVAIT `did_block` (`damage_hits.py:99/134`) mais **n'émettait jamais l'événement** → tout
le cluster on-block d'AnvilShield était inatteignable. Vecteur ajouté (`unit_blocked_triggers`, dispatché
AVANT `On(8)` comme le natif), `did_block` threadé depuis `damage.py` / `damage_ops.py` / `summon_ai.py` /
`mv71.py` / `summon.py`.

`AnvilShieldAbility_ApplyIce` — `CreateTrigger @180e16500` = `On(0x3d) & get_OwnerIsTarget &
IsUnit(caster@0x160)` ; `CreateBehaviour @180e16480` = `AddEffect(0x11=Ice, stateRef, source=Self@0x148,
cible = df@0x168 = CasterTile)` ⇒ **la tuile de l'attaquant gèle**. L'effet de tuile Ice était déjà porté
(même effet que LordOfTempests AddIce).

**Port** : `triggers/loki/anvil_shield.py` (`AnvilShieldApplyIceAbility`) + `ABILITY_TRIGGERS["AnvilShield"]`.
⚠ GRANULARITÉ : le natif émet `On(0x3d)` PAR COUP bloqué, le port UNE fois par ATTAQUE (même agrégation
que `is_crit`, déjà en place) — observationnellement équivalent pour ce consommateur (la pose d'Ice est
idempotente).

**Résidus** (non portés, dead-code offline si portés tels quels) :
- ~~`ApplyStun` / `FrozenAttackerAdvantage`~~ — **PORTÉS ET VALIDÉS LIVE (#100)**, cf.
  `docs/rl/case-100-anvil-shield-residus.md`. Les trois prérequis manquants ont été construits (classes
  d'effet 1200/1201, vecteur `On(0x2b = PreUnitAbility)` + son pendant `On(0xe = UnitPostAbility)`, canal
  stat 7 avec son driver d'`ActiveCondition`). ⚠ **Une lecture de #222 est RECTIFIÉE** : le 4ᵉ argument de
  `DSLFactory$$HasEffect` n'est PAS un `minLevel` mais un flag **ACTIVE-ONLY** (`EffectComponent+0x5c`,
  lu par `EntityExtensions$$IsOwnerOfEffect`, remis à 0 par `RefreshEffectsOperation$$DeactivateEffect`)
  — c'est ce qui rend le gate cohérent : 1200 est posé en permanence sur Arjac et n'ouvre le gate qu'en
  dessous de 35 % PV (`CreateActiveCondition` = `healthPct >= StatAmount(Self, HEALTH, CURRENT_PCT)`).

---

## Correctif transverse de la POSE (trouvé par confrontation live)

`AddEffectOperation.execute` retombait sur **`duration = 1`** quand ni override ni
`DefaultAmountOfRounds(type)` n'existaient, et ne posait **jamais de niveau**. GROUND TRUTH live
(runner 1181, `decisionView.effects`) : `MasterAnnihilator_extraHit` posé par l'attaque NATIVE de
Vitruvius = **`level 1, remaining 0`** — idem `RelentlessMarch_DangerZone`, `FleshmetalGuns*`,
`AnvilShield_AdditionalBlock`, `HeavyWeapon_ExtraDmg`, `LetTheGalaxyBurn`, `Daemon_ExtraBlock`.

Relecture du décompilé (`@180e48940`) : le `1` (`local_588[0] = 1`) n'est PAS la durée mais le
**NIVEAU** (`EffectComponent.Level @+0x68` — prouvé par `IncreaseEffectLevelOperation.Execute
@180e73cb0` qui lit/écrit CE champ comme niveau) ; la durée vient de `lVar14` =
`ConvertRoundsToTurns(DefaultAmountOfRounds(type))`, **null ⇒ 0 = permanent**. Corrigé :
`duration = override ?? default ?? 0 (permanent)` et `level = param ?? 1`. Table
`DefaultAmountOfRounds @181559ff0` re-vérifiée : transcription `_DEFAULT_ROUNDS` EXACTE
(`0x4f→3` ; `0x429,0x48a→1` ; `5,0x11,0x12,0x3a,0x4dc,0x5c4→2`), 0x4e1/0x590/0x42b/0x4bc/0x4c5 absents.

**Blast radius** : seuls les effets posés SANS override ET hors table changent — les 4 items de ce lot +
`ProtectorImperative`/`ConquerorImperative` (1247/1248) qui EXPIRAIENT au 1ᵉʳ tick et deviennent
persistants (une stance Doctrina persiste jusqu'au switch : c'est un **fix**, `test_doctrina_imperatives_
live.py` reste vert).

**Écart FLAGGÉ, non corrigé (pré-existant, hors périmètre)** : live `Pinned remaining = 2` vs port `1`
(= `DefaultAmountOfRounds(0x429)=1` **rounds**, que le natif convertit en TURNS via
`BattleQuery.ConvertRoundsToTurns` = `count(joueurs non-Environment) × rounds` = 2 ici). Le port ne
convertit pas les défauts de la table (`turns_per_round` n'est appliqué que par le nœud
`TurnsFromRounds`). Candidat tâche dédiée.

---

## Validation

### A. OFFLINE — `scripts/python/probe_lot_pose.py` (état observé, avec contrôles négatifs)

| item | observé | contrôle négatif |
|---|---|---|
| 1 MasterAnnihilator | attaque #1 → `MasterAnnihilator_extraHit(lvl=1, rem=None, src=Vitruvius)` sur e1 ; attaque #2 → marqueur **retiré** d'e1 et posé sur e2 | marqueur d'une **AUTRE source** sur e3 : **INTACT** (0 retrait) ; magnitude : Physical → `+1 coup`, **Psychic → None** |
| 2 FleshmetalGuns | 5 tours consécutifs : `turns 19→FocusedMalice, 20→RuinousSalvo, 21→WarpHail, 22→FocusedMalice, 23→RuinousSalvo` | magnitude de l'effet POSÉ non inerte : `{count 2, amount 997.0, Flame}` (ablvl=50, mult=180) — même forme que la référence SEED-like `{count 2, 1246.5, Melta}` |
| 3 TerrifyingCrescendo | 9 poses de Pinned par Shiron → level **1,2,3,4,5,6,6,6,6** (cap `buffMaxLevel=6`) | Pinned posé par une **autre unité** : level **inchangé** ; magnitude : `extraDmg[50]×mult 160 = 266`/stack → additif RANGED **1596** à level 6, **MELEE → None** (gate `IsRangedAttack`) |
| 4 AnvilShield | attaque **avec** block → `Ice(rem=2, src=Arjac)` sur la tuile de l'attaquant | attaque **sans** block → **0 Ice** |

Le `1596` de l'item 3 est **exactement** la valeur live-validée de case-204 (`266/coup × 6`).

### B. LIVE — `probe_lot_pose_live.py` / `probe_lot_pose_live2.py` (les DEUX camps pilotés, zéro RNG)

`applyAction` ne vérifie pas la propriété du `unitId` → positions des deux camps **drivées** à la main
(pas d'IA native, pas de tirage de placement).

- **FleshmetalGuns (rotation NATIVE)** : 3 tours consécutifs de Volk →
  `FocusedMalice → RuinousSalvo → WarpHail`. **Séquence identique au port.** (Et le seed d'un runner
  frais à `turnsStarted=1` porte bien FocusedMalice = `1 mod 3`.)
- **MasterAnnihilator (NATIF)** : attaques successives sur u77 → u79 → u77 ⇒ marques
  `{77:[…]}` puis `{79:[…]}` puis `{77:[…]}` — le marqueur **se déplace**, jamais en double,
  `level 1, remaining 0, source 83`. **Comportement identique au port.**
- **TerrifyingCrescendo (NATIF)** : 8 tirs RANGED de Shiron sur une cible déjà Pinned →
  stack **1,2,3,4,5,6,6,6**. Le port offline donne **1,2,3,4,5,6,6,6,6** : **identique**. Le fait que la
  cible porte DÉJÀ `Pinned(1, rem 2)` à chaque tir et que le compteur monte quand même **prouve** que
  `On(PreEffectAdded)` précède le gate « déjà présent » (le choix de RE porté).
- **AnvilShield (NATIF)** : runner dédié (`--block-target 100,500`, Arjac côté a-units) ; l'attaque
  bloquée produit la cascade `… ('group','AnvilShield') → ('group','Ice') …`. **La chaîne on-block →
  Ice fire bien côté natif.** (La tuile ciblée n'est pas lisible par RPC — elle est déterminée par le
  décompilé `AddEffect(Ice, cible = CasterTile@0x168)`.)

### C. Zéro-régression

- Garde agreement `engine_agreement_stages.py --build --seeds 31337 --steps 40` :
  **PREDICTION 21/23 (91 %, mêmes 2 `mismatch-logic` `healthDmgMin/Max` pré-existants), UTILITÉ 23/23,
  ability 27/27** — identique au baseline enregistré en case-204.
- Tests ciblés (tous verts) : `test_doctrina_imperatives_live` (durée 1247/1248), `test_suppressive_fire_live`,
  `test_effect_stun_live`, `test_act_of_faith_reset_live`, `test_act_of_faith_crit_resets_both_paths`
  (RemoveEffect multi-cible), `test_control_edict_live` (after-hit + summon), `test_damage_block_live`
  (`did_block` threadé), `test_turnflow_live` (StartTurn), `test_summon_trigger_live`,
  `test_lord_of_tempests_ice_live`, `test_rad_saturation_live`, `test_thebetrayer_rage_duration_live`,
  `test_damage_roll_live`, `test_runner_attack_live`, `test_tainted_narthecium_revive_live`,
  `test_dead_attacker_noop_live`.

### D. NON couvert (honnête)

- **Branche OVERKILL de TerrifyingCrescendo** (`On(UnitDeath) & TargetIsOverkilled`) : le vecteur est
  câblé et le behaviour partagé avec la branche suppress (validée), mais **aucun scénario d'overkill
  n'a été exercé** (cibles à 400 000 PV pour isoler l'accumulation). Double-incrément
  overkill+suppress dans un même tir : non isolé (résidu déjà noté en #204).
- ~~**Tuile Ice d'AnvilShield côté LIVE**~~ — **COUVERT (#99)** : le RPC **`tileMeta`** expose bien les
  effets de tuile (`effects[].{name,effectType,source,remaining}`). `test_lot_pose_live.py::
  test_anvil_shield_ices_blocked_attacker_tile_live` relit la tuile de l'attaquant LIVE (source =
  Arjac, `remaining = 4`) et la confronte au rejeu offline.
- **`On(UnitBlocked)` per-coup** : agrégé per-attaque côté port (cf. §4).
- ~~**Conversion rounds→turns des durées par défaut**~~ — **RÉSOLU (#98)**, cf.
  `docs/rl/case-98-duration-rounds-to-turns.md` : `ConvertRoundsToTurns @181058af0` porté runtime
  (facteur = joueurs non-Environment du `TurnOrder`), les deux voies (`TurnsFromRounds(n)` et
  `DefaultAmountOfRounds`) converties, canal `duration_turns` séparé pour les `Direct(n)`/`Nullable(n)`.

### E. Tests de garde (#99)

Le lot n'avait livré que des **probes** (aucune garde automatique — pour une classe de bug qui est
justement le no-op SILENCIEUX). `tests/engine/runner/test_lot_pose_live.py` couvre désormais les
**4 maillons**, chacun confronté au LIVE puis rejoué OFFLINE depuis la même capture :

| Test | Oracle natif observé | Ce qu'il garderait |
|---|---|---|
| `test_master_annihilator_mark_migrates_live` | marque 1249 : `u77 → u79`, jamais en double | vecteur `On(0x26)` débranché (aucune marque), `RemoveEffect` rendue mono-cible (accumulation) ou non filtrée par source (efface les marques d'autres poseurs — contrôle négatif offline) |
| `test_fleshmetal_guns_rotation_live` | `FocusedMalice → RuinousSalvo → WarpHail → FocusedMalice` | rotation figée (`UnitTurnsStarted` non lu) ou vecteur turn-start muet |
| `test_terrifying_crescendo_stacks_and_caps_live` | stack `1,2,3,4,5,6,6,6,6`, cap = `buffMaxLevel` lu de la config | vecteur recâblé sur `On(EffectAdded)` (le stack cesserait de monter dès le 2e tir sur cible déjà Pinned = LE bug d'origine), clamp perdu, pose muette |
| `test_anvil_shield_ices_blocked_attacker_tile_live` | Ice source=Arjac sur la tuile de l'attaquant, `remaining = 4` | `On(UnitBlocked)` muet ; gate perdu (contrôle négatif : attaque non bloquée = 0 Ice) ; durée non convertie |
- **Volets non portés** : (~~DespoiledGround (FleshmetalGuns)~~ : **PORTÉ en #85**, cf.
  `case-85-despoiled-ground.md`), remove-self du marqueur MasterAnnihilator
  à la mort de sa source. (~~ApplyStun + FrozenAttackerAdvantage + effets 1200/1201~~ : **portés en
  #100**, cf. `case-100-anvil-shield-residus.md`.)
