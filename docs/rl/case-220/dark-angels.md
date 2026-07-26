> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.5 DarkAngels (13 items ; faction native id 10, codename « Loki » ; DarkTalonStrike exclu)

```
[1150 PlasmaCannon | darkaTerminator]  — [opus] direct — PORTÉ + VALIDÉ (abilities/darkangels.py)
VAs : ExecuteBehaviour @1811f95c0 ; playbook @181150b10/@181150fe0
Main 3x Plasma + PickRandomly(UnitsDirectlyBehind, 2) même plage/hits — template plasma_grenade_tree ;
UnitsDirectlyBehind DÉJÀ porté (selectors.py:157, cite PlasmaCannon).
PORT : ExecuteAtomic(op_BitwiseAnd(main, splash), 0x2a) = AtomicGroup(op_and(...)) ; splash =
AttackWithAttackDamage(UnitsDirectlyBehind(), multi=True, pick_n=2). hits main==splash==nrOfHits(0x2f)
(GetHits(0)=ArmoriumCherub$$GetHits @180fb16c0 pour les DEUX volets — PAS de nrOfHits_2).
⚠ native_factory="attack" (@180de9fb0, PROUVÉ par XREFS call-sites @1811f97ab/@1811f9866 ; PlasmaCannon
ABSENT des xrefs de @180de9c90) — CONTRE le template PlasmaGrenade "ability". Piège tip #2 évité : NE PAS
copier native_factory du template. Validé live : ratio live/offline main CONSTANT en "attack" (rng-synced,
2 tirages/coup), désync en "ability".
BACKLOG (confounds SHARED-pipeline découverts en validant — HORS ce port, candidats suivi) :
  (i)  `execute_ability_attack` (operations/damage.py:806) ne passe PAS `is_ranged` à `attacker_modifiers`
       -> les buffs ranged du caster (HeavyWeapon_ExtraDmg gated IsRangedAttack + clause ability ×2 @180f4f030,
       +/- bonus high-ground) NON appliqués aux attaques d'ABILITY. Mesuré : live PlasmaCannon = offline ×
       facteur SCALAIRE constant (×1.25 HeavyWeapon seul ; ×1.875 = HeavyWeapon × high-ground caster>cible).
       Affecte TOUTES les abilities ranged des casters HeavyWeapon. [candidat fable — cross-cutting, risque]
  (ii) SPLASH desync per-coup — FERMÉ (#130, case-130-pick-randomly-rng.md). Le `PickRandomly` natif consomme
       `min(len(pool), amount)` tirages même en piquant tout ; `_pick_randomly_n` court-circuitait. Corrigé :
       PlasmaCannon est désormais BIT-EXACT per-coup vs live sur la MAIN **et** le SPLASH (régimes pool=1 et
       pool=2, comptage direct des genrand). Résidu : pool > 2 derrière (ordre d'énumération natif).
  (iii) armure : sans --hp-target, `defender_fixed_armor(necroWarden)`=2008 offline vs `RemainingArmor`=0 live
       (à confirmer : FixedArmor stale/profil Plasma). Contourné par --hp-target dans le test. [à vérifier]
```
```
[1103 Supercharge | darkaHellblaster]  — [opus]+1 effet — PORTÉ + VALIDÉ LIVE (#112, abilities/darkangels.py)
Symboles : IdunBattleLogic.Entities.Abilities.Active.Loki.SuperchargeAbility$$ExecuteBehaviour ;
  ...$$GetDamageToSecondaryTargets / ...$$GetHitsToSecondaryTargets ;
  IdunBattle.Entities.Effects.Loki.Supercharge_ExtraPiercingEffect$$CreatePiercingBonusForAttack
ARBRE (LU) : ExecuteAtomic( AddEffect(0x4b8, stateRef, caster@0x160,
  op_Addition(target@0x178, PickRandomly(UnitsDirectlyBehind(caster,target), 2)), TurnsFromRounds(1))
  & AttackWithAttackDamage(target, MinMaxDamage=ConfigVar(0xc,0xd), Plasma, GetHits=GetNumberConstant(0x2f))
  & AttackWithAttackDamage(behind, MinMaxDamage2=ConfigVar(0x36,0x37), Plasma, GetNumberConstant(0x32)), 0x2a )
→ `supercharge_tree()` (mirror 1:1). L'`AddEffect` est le PREMIER volet du `&` : le +percage bonifie les
coups de Supercharge EUX-MÊMES (A/B offline + ordre des groupes de la cascade live).
EFFET 1208 = `ForPiercing(DamageProfileIs(GetDamageProfile(config)=Plasma) & OwnerIsTarget,
ConfigVar(0x3f=extraPierceRatio))` → NOUVEAU canal port `create_piercing_bonus_for_attack`
(`effects/base.py` + `effects/loki/damage_reduction.py`), agrégé par
`build_defender_modifiers_from_effects` et fusionné dans `mods.extra_pierce` par
`AttackDamageOperation._apply_defender_flat_reductions` (le natif somme Piercing@+0x20 attaquant ET
défenseur avant `GetBaseDamageWithFixedPiercedArmor`).
VALIDÉ LIVE (MC1_67 au contact, seed 112112) : cible SANS unité derrière → dégât **BIT-EXACT** (5618 ==
5618) ; cible AVEC 2 unités derrière → les 3 effets 1208 (cible + les 2 derrière, `RemainingTurns=2`)
posés AVANT les 2 volets de dégât, splash sur EXACTEMENT ces 2 unités.
RÉSIDU (mesure #112, partiellement fermé par #130) : avec 2 unités derrière, le live s'alignait sur le port
décalé de **+2 tirages** (volet MAIN) et **+5** (volet SPLASH). Les **+2** sont le `PickRandomly(.,2)`, qui
consomme `min(len(pool), amount)` tirages MÊME quand le pool tient dans n — loi établie au décompilé et
mesurée live par #130 (`case-130-pick-randomly-rng.md`), désormais portée dans `_pick_randomly_n` : le pick
de `_supercharge_behind` précède l'`AddEffect` ET les deux volets, donc les +2 sont résorbés sur les deux.
Le **+3 restant côté SPLASH seul** n'est PAS attribué (candidat : source de block supplémentaire
`Daemon_ExtraBlock` de la cible) — à re-mesurer par décomposition d'étage, PAS par ajustement de tirages.
```
```
[EnmityForTheUnworthy | darkaCompanion passif]  — [opus]+2 effets (passif le + facile)
VAs : @180f78ff0 ; effets 1400 @180f41fe0 (@180f41b60/@180f41d90/@180f41c20), 1399 (@180f42280/@180f42120)
1400 = +291 FLAT x amis DarkAngels adjacents ; 1399 = +20% x TOUTES unités adjacentes. Patron BeaconOfRage.
Risques : self-exclusion du comptage ; ordre flat+pct dans le pipeline.
```
```
[FearedInterrogator | darkaAsmodai passif]  — [opus]+2 effets
VAs : @180f7fcf0 ; effet 1294 @180f48c60
1294 = +728 vs ennemis Suppressed|Stunned|adjacents-à-un-DA-ami (prédicat évalué sur la CIBLE) ;
1295 = +2 coups si cible AUSSI Chaos (hits.py). Templates existants (BeastSlayer / extra-hits).
```
```
[1228 SternguardFocus | darkaSternguard]  — RE TERMINÉE (#112) — **NON PORTÉ : PORTEUR NON SPAWNABLE**
Symboles : IdunBattleLogic.Entities.Abilities.Active.Loki.SternguardFocusAbility$$ExecuteBehaviour /
  ...$$GetOverrideAttackDamageAmount ;
  IdunBattleLogic.Entities.Abilities.Triggered.Loki.SternguardFocus_CooldownAbility$$CreateBehaviour
ARBRE (LU, `AActiveAbility.Execute`, PAS d'ExecuteAtomic) :
  amount = PercentageOfAttackCappedAtMax( Subject@0x180, StatPart=**3 (INITIAL)**,
             ConfigVar(0x4cc=1228, Self@0x148, 0xd=maxDmg), ConfigVar(0x4cc, Self@0x148, 0x4a=dmgPct) )
  op_Addition( op_Addition( AddStatOverrideEffect(caster@0x160, 0x510, ATTACK, amount, 0, 1),
                            UseNormalAttack(caster@0x160, target@0x178, <options>) ),
               RemoveEffect(caster@0x160, Nullable(0x510)) )
⚠ `StatPart = 3 (INITIAL)` ici vs **0 (CURRENT)** pour ExemplarOfHate — différence LUE, à ne PAS
uniformiser. `UseNormalAttack` alloue le MÊME `UseActiveAbilityBehaviour` que `UseActiveAbility` (avec un
provider d'ability-type par-unité = l'attaque normale du sujet) ⇒ la feuille portée `UseActiveAbility`
(déjà spécialisée au dispatch attaque-normale, slice-22) est le mirror exact.
**BLOCAGE** : `darkaSternguard` (« Ramus ») a `releaseStatus = 1784419200000` (horodatage, ≈ mi-juillet
2026) et est ABSENT du roster de la seed BC (`data/seed-bc.json` : 0 occurrence) ⇒ absent du pool
`rl_duel build --list-pool` à TOUS les rangs testés (9/13/15/16/17 : 97 unités, jamais lui). Ce n'est ni
un npc ni un summon : c'est un HÉROS non encore possédé ⇒ ability **INVALIDABLE LIVE**. Conformément à
« no unvalidatable ability ports », l'ability N'EST PAS enregistrée dans `ABILITY_CLASSES`.
**Le port coûte ~10 lignes le jour où le porteur entre au pool** : toutes ses primitives sont déjà
portées ET live-validées par ExemplarOfHate (`AddStatOverrideEffect`, `percentage_of_attack_capped_at_max`,
`UseActiveAbility`, `RemoveEffect`+revert d'override) ; seul reste à écrire l'arbre ci-dessus avec
`stat_part=StatPart.INITIAL` et `Caster()` en lieu et place du collapse `GetAttacker`.
Hors port de toute façon : le cooldown 3 tours est géré par la triggered `SternguardFocus_Cooldown` (1548).
```
```
[1189 CalibaniteGreatsword | darkaCompanion]  — ex-[fable] — PORTÉ + VALIDÉ LIVE (#112) pour l'ACTIVE
Symboles : IdunBattleLogic.Entities.Abilities.Active.Loki.CalibaniteGreatswordAbility$$ExecuteBehaviour /
  ...$$AddStrikeEffects / ...$$RemoveStrikeEffects ;
  IdunBattleLogic.Entities.Abilities.Triggered.Loki.CalibaniteGreatsword_SetStartAbility$$CreateBehaviour
L'ExecuteBehaviour n'est PAS `[fable]` : c'est un TOGGLE PUR, sans attaque ni tirage. ARBRE (LU) :
  If( HasEffect(Self@0x148, 0x57c, activeOnly=0, sourceFlags=6),
      AddEffect(0x57d Sweep, Self) + RemoveStrikeEffects(),                       # THEN
      AddEffect(0x57c) + AddEffect(0x591) + AddEffect(0x3f1) + RemoveEffect(Self, 0x57d) )   # ELSE
`RemoveStrikeEffects` = RemoveEffect(0x57c, 0x591, 0x3f1, 0x57e). `AddStrikeEffects` (= la branche ELSE,
INLINÉE par le compilateur) est AUSSI le corps de la triggered `CalibaniteGreatsword_SetStartAbility`
⇒ Forcas démarre en STRIKE. `activeOnly = 0` LU (les call-sites AnvilShield passent 1).
VALIDÉ LIVE : 2 casts consécutifs — PRE 1404 seul ; cast 1 → +1405 / −1404 ; cast 2 (tour suivant) →
+1404 / −1405. Aucun dégât, ne finit pas le tour (1189 déjà dans les 2 frozensets de `abilities/base.py`).
⚠ L'étiquette « NO-OP DAMAGE(Power) » de `kit-coverage.md` est TROMPEUSE : les constantes
`damageProfile=Power` / `nrOfHits_2=3` et les variables minDmg/maxDmg/nrOfHits de la config 1189
alimentent la TRIGGERED `CalibaniteGreatsword_NormalAttackAdditionalDamage` (1316, volet Sweep), pas
cette active.
RÉSIDU DE MESURE (important) : les effets 0x591 (Strike_Overwatching) et 0x3f1 (Overwatch_AutoAttack)
n'apparaissent JAMAIS dans `decisionView.effects` — mais ce n'est PAS une preuve de non-pose : le hook
`frida/hooks/game/effects.ts` (`readEffectsByUnit`) DROPPE toute entrée dont `EffectComponent.IsActive
@+0x5c` est nul, et l'overwatch de la posture Strike ne s'active qu'EN FIN DE TOUR (i2). Le port MIRRORE
donc le décompilé (3 `AddEffect`). Conséquence bornée : le port n'a pas d'`ActiveCondition` pour ces deux
effets → ils y sont actifs dès le cast. En pratique inerte (le trigger `Overwatch_AutoAttack` du port ne
se déclenche que sur un MOUVEMENT ennemi, donc pendant le tour adverse = après la fin du tour de Forcas).
Point d'ancrage pour trancher définitivement : exposer `EffectComponent.IsActive` dans
`decisionView.effects` (exige rebuild+reinject).
PHASE 2 (hors #112) : les observables de posture vivent dans les TRIGGERED —
`CalibaniteGreatsword_NormalAttackAdditionalDamageAbility` (1316, splash adjacent-both) et
`CalibaniteGreatsword_StrikeOverwatchingEffect` (overwatch persistant + decay de coups au kill).
```
```
[LionHelm | darkaAzrael passif]  — [fable]
VAs : @1811084b0 ; effets @180f55f30/@180f561b0/@180f56540
Aura range 2 : +582 block-damage amis, +20% block-chance AUTRES DA seulement, +437 dégât des attaques
déclenchées par Overwatch. Prérequis : projection aura range-2 (template SpotterReworked) + block
défenseur (existant BeastSlayer) + bonus conditionnel-overwatch (neuf) + AddDynamicStatModifierEffect.
```
```
[GrimRetribution | darkaHellblaster passif]  — [fable]
VAs : effet @180f4c090/@180f4c280/@180f4c2b0
Riposte tour-ennemi : si AUCUN ennemi adjacent, tire 1x Plasma (compte Overwatch) sur le 1er ennemi
ayant attaqué Sarquael ou un allié DA adjacent. Prérequis : vecteur on-attacked (self+allié-adjacent),
suivi 1er-attaquant, gate no-adjacent, attribution overwatch.
```
```
[Deathwing | darkaTerminator passif]  — [fable]
VAs : @180e1fb20/@180e1fcc0 ; effet @180f3e160 ; playbooks @181165110/@181165040
À chaque BLOCK : stack DeathwingEffect (−146 dégât entrant suivant / +146 sortant melee+PlasmaCannon,
1 tour, doublé vs Chaos ou adjacent-DA). Prérequis : trigger ON-BLOCK (défenseur mid-attaque) +
IncreaseEffectLevel + effet bi-directionnel. Risques : « further incoming » = coups RESTANTS de la
même attaque (gating inter-coups #72).
```
```
[1213 DeathOnTheWind | darkaStormSpeeder MoW]  — [fable] + BLOQUÉ harnais MoW
VAs : ExecuteBehaviour @1811d22b0 ; @1811d2760/@1811d2930/@1811d26f0 ; effet 1257 @180f3dca0
      (@180f3d9c0/@180f3db60/@180f3dbc0) ; playbook @18112b430
6x HeavyRound sur LIGNE de 3 hexes + effet 1257 (+33% dégât de la prochaine attaque DA amie, avec
retrait). Sans harnais cast-par-MoW : INVALIDABLE (groupe Malleus/DutyEternal).
```
```
[1214 Hailstrike | darkaStormSpeeder MoW]  — [fable] + BLOQUÉ harnais MoW
VAs : ExecuteBehaviour @1811e57c0 ; triggered @180f84360 ; effet 1509 @180f4cdc0 ; playbook
      @181141390/@181141640
Buff ami (+15% pierce ranged/overwatch 1 tour) ; quand l'ami attaque, la MACHINE attaque la même
cible (3x Projectile, gate IsDefeated, sinon TriggerAbilityDelayed). Vecteur « attaque-liée »
genuinement nouveau (une unité attaque hors de son tour, déclenchée par l'attaque d'un ami).
```
```
[1140 ExemplarOfHate | darkaAsmodai]  — ex-[fable] — PORTÉ + VALIDÉ LIVE (#112)
Symboles : IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$ExecuteBehaviour /
  ...$$GetAttacker / ...$$GetPossibleAttackers / ...$$GetAttackDamage ;
  IdunBattle.Entities.Effects.Loki.ExemplarOfHate_TargetEffect$$CreateEffectDamageBonusForAttack ;
  IdunBattle.Entities.Selectors.SortAttackersByDamagePredictionSelector$$Select (+ <Select>b__0) ;
  IdunBattle.Entities.Selectors.UnitsWhoCanAttackTargetSelector$$Select
ARBRE (LU, ordre des `op_BitwiseAnd` vérifié) :
  AddEffect(0x50d, stateRef, caster@0x160, target@0x178, TurnsFromRounds(2))            # INCONDITIONNEL
  & If( HasTrait(target@0x178, 0x7ea),
        AddEffect(0x429 Pinned, ..., durée ZERO = DefaultAmountOfRounds)
        & AddStatOverrideEffect(attacker, 0x510, ATTACK, GetAttackDamage(), 0, 1)
        & UseActiveAbility(attacker, target, UnitNormalAttackType(attacker))
        & RemoveEffect(attacker, Nullable(0x510)) )
⚠ **0x7ea = 2026 = le PSEUDO-trait de GRANDE-ALLIANCE Chaos** (`idun.Idun.Source.Shared.GrandAlliance$$
GetTrait` : Imperial→0x1a, Xenos→0x3ee, Chaos→0x7ea) — PAS un trait gameconfig. Un
`HasTrait(Target(), 2026)` naïf (via `ctx.has_trait`, qui lit les NOMS gameconfig) serait TOUJOURS faux
⇒ branche Chaos MORTE. Le port passe par `HasGrandAlliance(Target(), CHAOS_FACTIONS)` (même dérivation
que le `HasTrait(killer, 26=Imperial)` d'ActOfFaith, live-validé). **Piège n°1 de cet item.**
`GetAttackDamage` = `PercentageOfAttackCappedAtMax(Subject@0x180, StatPart=0 CURRENT, ConfigVar(0xd
=maxDmg), ConfigVar(0x4a=dmgPct))`. Cette factory est COMPOSITE et son nœud englobant est un ctor gshared
que ghidra affiche `HasUsedActiveAbilityThisTurnTrigger..ctor` : sa sémantique **Min** est PROUVÉE PAR
IDENTITÉ DE SINGLETON (`IdunBattleLogic.Entities.DSLFactory$$Min` alloue le MÊME `DAT_18324e140` avec le
même ctor 2-champs), pas déduite du nom.
`GetAttacker` (collapse S, doctrine slice-18/19, cf. `_finaljustice_target`) = `First(
SortAttackersByDamagePrediction( UnitsWhoCanAttack(UnitsFromFaction(Friends(caster), 10), target) ), 1)`
avec clé `OrderByDescending` LUE : 0x7fffffff si WillBeKill, 0x7ffffffe si MightBeKill, sinon
`MinMaxDamage.Avg` — portée via `get_attack_prediction` PRÉ-ARMURE avec `initial_damage` = l'OVERRIDE.
VALIDÉ LIVE (Asmodai adjacent à blackObliterator, MC1_67 au contact) : `ExemplarOfHate_Target`
`RemainingTurns=4` (= TurnsFromRounds(2) × 2 joueurs) + `Pinned` `RemainingTurns=2` + attaquant élu
IDENTIQUE + `UnitStats_Attack_Override = 2008` == `min(maxDmg[50]×mult180 = 5983, round(Attack_CURRENT
2008 × dmgPct 100 / 100))` — EXACT.
CONFOND documenté (dégât de l'attaque libre NON asserté) : le passif NON PORTÉ `FearedInterrogator`
d'Asmodai ajoute +2 coups (live 6 vs `weapons[0].hits` = 4) et du dégât.
RÉSIDUS : (a) branche `IsOverwatchAttack` de l'effet 1293 non threadée (seule la moitié MELEE contribue —
MANQUE, jamais sur-compte) ; (b) `UnitsWhoCanAttack` porté = « portée d'arme max ≥ distance hex » (règle
dominante) ; LoS/obscurcissement non modélisés ; (c) le CAP de l'override n'est pas discriminé live (aucun
allié DA du roster n'a Attack > maxDmg=5983).
```
```
[SpecialIssueCombiMelta | darkaSternguard passif 1545]  — [fable] : RE À FINIR
VAs : init @1811a11a0 (AddEffect 1563+1564 self) ; trigger @1811a10c0 (On 0x26 après-attaque-normale
      & IsAtRange(3)) ; effet ExtraDmg @180e11920 ; playbook @181188c00
⚠ Sémantique des effets 1563/1564/ExtraDmg = HYPOTHÈSE (corps non décompilés, PAS d'i2) — RE
complémentaire OBLIGATOIRE avant tout port (sinon spéculatif/invalidable).
```

**Synthèse DA** — état au #112 :
- **PORTÉS + VALIDÉS LIVE** : PlasmaCannon (1150), **Supercharge (1103)**, **ExemplarOfHate (1140)**,
  **CalibaniteGreatsword (1189)** — les 3 derniers livrés par #112 (ex-`[fable]` pour 1140/1189 : la RE
  a montré que ni l'un ni l'autre ne résiste — 1189 est un toggle pur, 1140 tient en un collapse S +
  un mirror d'arbre).
- **RE TERMINÉE, NON PORTÉ (invalidable)** : SternguardFocus (1228) — porteur hors roster (cf. ci-dessus).
- **RESTE `[opus]`** : EnmityForTheUnworthy, FearedInterrogator (passifs).
- **RESTE `[fable]` x6** : LionHelm, GrimRetribution, Deathwing, DeathOnTheWind (MoW), Hailstrike (MoW),
  SpecialIssueCombiMelta (RE à finir). + PHASE 2 de CalibaniteGreatsword (triggered 1316 / overwatching).

**Machinerie SOCLE ajoutée par #112** (justifiée par 1103 + 1140, vérifiée non-régressive) :
`DSLFactory$$PercentageOfAttackCappedAtMax` (`entities/formulas.py`, = `Min(cap, PercentageOf(StatAmount(
unit, ATTACK, statPart), pct))` — Min PROUVÉ par identité de singleton) ; feuille
`DSLFactory$$AddStatOverrideEffect` (`abilities/behaviours/stats.py`, avec le binding du slot SUJET que
fait `AddStatOverrideEffectBehaviour$$Execute`) ; part OVERRIDE du `RevertInternal` dans la feuille
`RemoveEffect` (no-op strict pour tout effet sans `stat_override_stats`) ; slot d'interface
`CreatePiercingBonusForAttack` + sa fusion défenseur→attaquant dans `mods.extra_pierce`.
Gardes rejouées sans régression : nightshroud / act_of_faith_reset / mv71 / damage_roll / damage_ability /
the_quickening / plasma_cannon / terrifying_defense / effect_duration_rounds.
