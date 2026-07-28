"""Prediction des abilities SPECIALES : `generate_multi_hit_attack_prediction` (per-cible de
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`), le registre d'overrides d'ENTREE per-ability
(`_MAKE_DMG_INPUT_OVERRIDES` / `_PLAYBOOK_PROFILE_OVERRIDE`), l'orchestrateur `make_damage_predictions`
(`<Ability>Playbook.MakeDamagePredictions` : cible + AoE + self) et le chemin dedie HammerOfWrath.
Consomme `_shared` (helpers mods/defenseur + vocabulaire) et `normal_attack` (via_normal).

C'est ICI qu'atterrissent les nouveaux handlers `_<ability>_inputs` de la phase de port case-220 (chaque
ability qui SURCHARGE la base/hits/profil generiques ajoute son handler HOMONYME + une entree registre)."""
from __future__ import annotations

from ._shared import *   # vocabulaire commun (GC, dsl, active_ability_for, ProbableDamageEvent, ...)
from ._shared import (_PROFILE_INDEX, _add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
                      _prediction_is_charging, _target_damage_limits)
from .normal_attack import make_normal_attack_predictions


def generate_multi_hit_attack_prediction(scene, uid, tgt, ability_id, ability_name, attack_pos=None,
                                         base_bonus: int = 0, base_override=None,
                                         hits_override=None, profile_override=None):
    """Per-cible de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` : `DamagePredictionResult`
    d'UNE cible via le `(damage, hits, profile, pierce)` PROPRE de l'ability (`<Ability>.PredictAttack`,
    slot +0x27). None si non-attaque.

    `base_override`/`hits_override`/`profile_override` (defaut None = comportement inchange) : substituent
    la base/hits/profil lus de l'ability. Requis par l'utilite de DECISION NonComparable de HammerOfWrath
    (#114), dont `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent/IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent appelle `PredictAttack(0x27)` avec
    `damage=GetMinDamage`(var12) + `hits=GetHits`(const47) [primary] / `GetMinDamage2`(var54)+
    `GetHitsToBonusTarget`(const50)+profil2 [secondary] au lieu de avg(minDmg,maxDmg)/hits config. Le RESTE
    du pipeline (spread ±20%, pierce, armure, mods attaquant/positionnels, bouclier per-coup) est identique."""
    ctx = scene.ctx(uid)
    if ctx is None:
        return None
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if cfg is None or not (cfg.has_variable("minDmg") or cfg.has_variable("maxDmg")):
        return None
    # AbilityState PER-ABILITY (#100) : le natif indexe les variables config par le couple
    # {Level, VariableMultiplierPercentage} PROPRE de l'ability (entree ActiveAbilityComponent
    # ._abilityState @0x4c, forwarde au playbook en 5e arg de MakeDamagePredictions) — consomme par
    # IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel (idx = Level.ToZeroBasedIndex clampe ; × mult/100 si
    # var ∈ variablesAffectedByRarityBonus). Le canal global (ctx.active_ability_level ×
    # scene.mult) est un AUTRE couple (mesure u80 PlasmaCannon : per-ability 65×120 → 1396 vs
    # global 50×180 → 1594, faux) → capteur combatSnapshot.abilityStates, fallback global.
    st = scene.ability_state(uid, ability_id)
    ab = active_ability_for(ability_name, ability_id, ctx, cfg, ability_state=st)
    # Base de la PREDICTION speciale = `GetDamageFormula` du playbook (PlasmaCannonPlaybook
    # IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions) = `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` (avgFlag) = **avg(minDmg, maxDmg)**
    # scales per-entree ×mult/100 (ab.get_damage, DECOMPOSE PAR ETAGE #100 : varLevelDumps
    # min 1197 + max 1595 → avg 1396 ; bouts prediction [1117,1675] = ±20% EXACT ; ×mods 1.875
    # → per-coup [2094,3141] == aiPlaybookPredict). Le « base = maxDmg seul » (#96) est REFUTE —
    # 1396 se decomposait AUSSI en maxDmg[65]×1.2 (sous-determination du degat final). Le couple
    # (level, mult) = AbilityState PER-ABILITY (capteur, fallback global via ab.level/ab.multiplier).
    lvl = ab.level
    base = ab.get_damage() if base_override is None else float(base_override)   # HammerOfWrath: GetMinDamage
    if base <= 0:
        return None
    # #108 GetCorrectDamage : clause conditionnelle sur le NB de cibles AJOUTEE A LA BASE avant spread/mods
    # (ex. MurderousSwing single-enemy +extraDmg). `base_bonus` fourni par `make_damage_predictions` (qui
    # connait le compte AoE) ; 0 pour toutes les abilities sans clause (get_correct_damage identite).
    base += int(base_bonus or 0)
    a = GC.ability(ability_name) or {}
    is_melee = (a.get("attackRangeType") or "").lower() == "melee"
    hits = max(1, ab.get_special_hits(is_melee) if hits_override is None else int(hits_override))
    profile_name = ab.get_damage_profile() if profile_override is None else profile_override
    profile_idx = _PROFILE_INDEX.get(profile_name, 0)
    dp = GC.damage_profile(profile_name) or {}
    dir_pierce = ctx.extra_pierce_melee if is_melee else ctx.extra_pierce_ranged
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    # Mods attaquant : MEME builder IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction que la normale (le natif ne distingue pas par ability) —
    # threader la nature du coup + le flag has-moved de la tuile candidate (gates IsRangedAttack /
    # NOT HasMoved des effets, ex. HeavyWeapon +25% ranged not-moved s'applique aux speciales ranged).
    _hm = (attack_pos != scene.pos(uid)) if attack_pos else None
    # gate ConquerorImperative (#22) : +extraDmg s'applique AUSSI aux attaques SPECIALES du porteur (trigger
    # OwnerIsCaster & HasNegativeModifier, AUCUN IsNormalAttack) vs cible a armure reduite.
    _tctx = scene.ctx(tgt)
    _tgt_armor_reduced = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                          if _tctx is not None and _tctx.stats is not None else None)
    mods = calculate_attacker_modifiers_for_prediction(scene.effects(uid), is_ranged=not is_melee,
                                                       has_moved=_hm, is_normal_attack=False,
                                                       target_armor_reduced=_tgt_armor_reduced,
                                                       att_ctx={"att_pos": attack_pos or scene.pos(uid),
                                                                "tile_effects_by_pos":
                                                                    scene.tile_effects_by_pos,
                                                                # `IsCharging` depuis la tuile candidate
                                                                # (case-r32) — AvalancheOfMuscle 1025 n'a
                                                                # AUCUN gate IsNormalAttack, il entre donc
                                                                # aussi sur ce vecteur ABILITY.
                                                                "is_charging": _prediction_is_charging(
                                                                    scene, uid, attack_pos, tgt)})
    t_pos = scene.pos(tgt)
    _add_positional_and_defender_mods(mods, scene, uid, tgt, is_melee, attack_pos, t_pos,
                                      damage_profile=profile_name, is_normal_attack=False)
    # AURA ALLIEE +extraDmg (ConquerorImperative #23 / BeaconOfRage #191) : le +extraDmg de Conqueror n'a AUCUN
    # gate IsNormalAttack -> s'applique aussi quand un ami Mechanical adjacent utilise une attaque SPECIALE vs
    # cible a armure reduite (symetrique de la normale). Gates dans le create_aura_ (Mechanical/adjacence/team/
    # target_armor_reduced ; BeaconOfRage : is_melee/Chaos).
    _apply_ally_attack_dmg_bonus(mods, scene, uid, attack_pos or scene.pos(uid), is_melee, _tgt_armor_reduced,
                                 tgt_id=tgt, is_normal_attack=False, damage_profile=profile_name)
    tgt_shield = scene.shield(tgt)
    # Base speciale = `base` (avg(minDmg,maxDmg) scale rarete) route par le MEME chemin que la normale
    # (GetBaseDamageFix64 ±20% dans predict_attack_raw). L'ancien chemin `get_multi_hit_attack_prediction(
    # damage=...)` (plage empirique 0.8/2.2·d/hits) etait FAUX (RE IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw : base = 1 int
    # -> ±20% [0.8/1.2], aucun 2.2) -> SUPPRIME. Les specials Attack-based (PlasmaCannon/SpiritLeech) ne
    # passent PAS ici (routes via _PREDICT_VIA_NORMAL_ATTACK). Le bouclier est deplete PAR COUP (prev).
    # MkXGravis (trait CIBLE 0x3f5) : armure traversee 2× aussi pour les speciales (CalculateBaseDamage
    # WithAllModifiers appele quel que soit l'ability). No-op (=1) si la cible n'a pas le trait hit-twice.
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt)) or {}).get("traits")))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt) or 0, initial_damage=base, hits=hits,
        profile_type=profile_idx, pierce_pct=pierce, armor=scene.armor(tgt),
        mods=mods, target_shield=tgt_shield, hit_mult=tgt_hit_mult,
        target_limits=_target_damage_limits(scene, tgt, profile_name),
        target_prevents_overkill=scene.prevents_overkill(tgt),   # #195 : HasFlag(cible, 0x13)
        defender_block_amount=defender_prediction_block_amount(scene, tgt, profile_name),  # #69 gate NoBlocking
        attacker_effects=scene.effects(uid),   # #202 : max-out evalue DANS predict_attack_raw (specials aussi)
        attacker_ctx=ctx)                      # #R34 : MightCrit = CouldCrit(attaquant), specials aussi


# Abilities dont la PREDICTION de degat SANTE est Attack-based (== l'attaque NORMALE), PAS le config
# minDmg/maxDmg. Chemin natif (RE #92) : `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeDamagePredictions` calcule
# `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage` (config) MAIS le passe a `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
# qui invoque le slot virtuel +0x27 (`PredictAttack`) — lequel RECALCULE Attack-based (`FindAttackWeapon`
# IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$FindAttackWeapon -> `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackHitPrediction` = `GetStat(Attack,Current)`+arme), ignorant le config.
# PROUVE par le calcul : config-avg-scaled 2593 / config-max 2992 != base live 2670 / dmax live 3205 (==
# native normale(69) EXACT). Le `GetAttackDamage` config alimente le HEAL (`GetHealAmountForPrediction`)
# + le COMBAT reel (`ExecuteBehaviour`), PAS ce preview. On route donc l'event de degat principal vers
# `make_normal_attack_predictions` (mirror du slot 0x27 Attack-based : base/hits/mods/auras = la normale).
# ── Specials "Attack-based" : IL N'Y EN A AUCUN — set VIDE (reframing #99/#101a, decompile + live ;
#    detail : docs/rl/case-99-specials-attackbased-reframe.md). Prouve ARTEFACT-FREE via le RPC
#    `resolveVtableSlot` (slot vtable PredictAttack = byte 0x328) : les 5 specials audites (SpiritLeech,
#    PlasmaCannon, Doombolt, JakhalStimms, GauntletsOfUltramar) resolvent tous PredictAttack vers le STUB
#    ABSTRAIT QUI THROW `IdunBattle.Entities.Abilities.AActiveAbility$$PredictAttack` — AUCUN n'herite
#    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack` (Attack-based). L'HYPOTHESE #92 « SpiritLeech
#    herite ALoki » (jamais lue au binaire) est REFUTEE. Le vrai chemin de prediction = chaque
#    `<Special>Playbook.MakeDamagePredictions → ComparablePlaybook.GenerateMultiHit(base = ability.GetAttackDamage(),
#    hits, profile)` ; `base` = CONFIG (`MinMaxDamage`) pour tous — `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage`
#    = DSL `ConditionalAmount(¬HasEffect(Suppressed=1065), MinMaxDamage, +ConfigVar(8)=+1601)`, config.
# ⚠ Le "== normale 2670 bit-exact" historique (#90/#92) etait l'ARTEFACT du preview
#    `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions` (Attack-based quel que soit l'abilityType — piege #96/#101a) — CONFIRME LIVE
#    (predict_sweep Neurothrope) : `aiPlaybookPredict(SpiritLeech)=[2074,3112]` (config) != `disp`/artefact
#    `GetAllPredictions=[3111,4668]`. ⇒ SpiritLeech RETIRE ; tout special passe par le chemin CONFIG generique.
#    (PlasmaCannon avait deja ete retire au #96.) La verite per-ability = `aiPlaybookPredict` (#102), JAMAIS aiPredict.
# #171 — SorcerousFacade (1100, thousTzaangor) EST un membre LEGITIME (distinct des specials #99 ci-dessus).
#    Son `IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions` construit pour la cible ENNEMIE
#    (`TargetsSelector.SelectFirst IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions+0x160`) un EVENT #1 = ATTAQUE NORMALE du caster, via l'interface
#    `DAT_18327ff80` slot 0x21 @~18115bd60 — le MEME mecanisme que `NormalAttackPlaybook.MakeDamagePredictions
#    IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions` (= "profil d'attaque normale du caster vs target"). PUIS un event #2 secondaire
#    `GenerateMultiHit(base=Half(Sum(minDmg,maxDmg)) config, profile=null)` = [1197,1795] (AddRange) que
#    l'ORACLE ne remonte PAS (dedup aval + regle : l'ennemi ne subit QUE l'attaque normale declenchee ; le
#    728-1455 Psychic est un BUFF pour les futures attaques normales). L'event ennemi expose par
#    aiPlaybookPredict = l'attaque normale -> [1623,3591] bit-exact live (probe171, side-by-side vs id 69).
#    Ce N'EST PAS le cas #92 refute (heritage vtable PredictAttack Attack-based) : ici le playbook EMET
#    explicitement une prediction d'attaque normale. Cf. docs/rl/case-171-sorcerousfacade-normal-attack.md.
_PREDICT_VIA_NORMAL_ATTACK = frozenset({"SorcerousFacade"})


# ── Overrides d'ENTREE per-ability — mirror des `<Ability>Playbook.MakeDamagePredictions` qui SURCHARGENT
#    la base/hits generiques. Le natif dispatche par type d'ability (registre playbook / vtable) ; le port,
#    qui collapse tous les playbooks dans `make_damage_predictions`, dispatche par id via ce registre. Chaque
#    handler = HOMONYME du playbook natif + VA ; rend un dict `{base_override?, hits_override?, profile_override?}`
#    (kwargs de `generate_multi_hit_attack_prediction`) ou `{}`. La methode generique reste GENERIQUE : aucune
#    logique ability-specifique inline (ajouter une ability divergente = un handler + une entree registre).
#    Cle META supplementaire `aoe_overrides` (dict de MEMES kwargs) : entrees PROPRES au 2e batch, pour les
#    playbooks qui appellent `GenerateMultiHitAttackPredictions` deux fois avec des arguments differents
#    (FrenziedFiring). Consommee et RETIREE par `make_damage_predictions` — jamais transmise en kwarg.
def _martial_inspiration_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`MartialInspirationPlaybook.MakeDamagePredictions` (yield machine `<MakeDamagePredictions>IdunBattle.AI.Playbook.Loki.MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext ; Kariyan/custoBladeChampion, ability 1191) — SURCHARGE la base/hits generiques (#106) :
    emet UN coup (hits=1 literal `*(puVar25+0x40)=1`) de base `round(var12 * buff)`, PAS `avg(minDmg,maxDmg)`
    sur `nrOfHits=3` config (d'ou l'ancienne sur-pred x3.3).
        var12 = minDmg (id 0xc, GetVariableForLevel, rarity-scaled) ; var10 = extraDmgPct (id 0xa, +33%/tour
        CAP, NON rarity-scaled -> mult no-op) ; buff = (var10*count + 100)/100 ; count = TotalAttacksMade
        (+0x20, capteur actorStats -- PAS TotalTurnsWithAttacksMade +0x30 qu'utilise le COMBAT GetBuffPct :
        divergence prediction<->combat portee telle quelle). count=0 debut de bataille -> buff=1 -> base=minDmg.
    slot0x10 = `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` = `round(a*b)`. Le RESTE (x1.875
    = DamageModifiers.Multiplier attaquant ; spread +/-20% ; pierce/armure) = pipeline STANDARD en aval."""
    lvl, mult = ab.level, ab.multiplier
    minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)          # var12 (rarity-scaled)
    extra = cfg.get_variable_for_level("extraDmgPct", lvl, 0, mult)    # var10 (NON rarity -> mult no-op)
    count = scene.total_attacks_made(caster_id)                        # TotalAttacksMade (+0x20)
    buff = (extra * count + 100) / 100.0
    return {"base_override": round(minv * buff), "hits_override": 1}


def _crushing_claws_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.CrushingClawsPlaybook$$MakeDamagePredictions` (tyranTyrantGuard, ability 1105) — la
    PREDICTION ignore le `damageProfile` de l'ability : le playbook passe **`param_8 = null`**
    (`Nullable<DamageProfile>` sans valeur) a `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`, pour la cible
    principale ET chaque splash (les DEUX appels natifs passent 0). Le profil de prediction vient de CE
    param_8 (choix du playbook), PAS de `ability.damageProfile` -> null = profil `None` (enum -1) -> **pierce 0**
    (l'armure s'applique PLEINE), au lieu du `Piercing{PiercingRatio:80}` de l'ability. C'est un quirk NATIF
    (le playbook « oublie » de passer le profil) : l'IA SOUS-evalue CrushingClaws face a une cible blindee.
        Contraste `HarvesterOfSoulsPlaybook IdunBattle.AI.Playbook.Loki.HarvesterOfSoulsPlaybook$$MakeDamagePredictions` : passe `Nullable(0x13=19=HeavyRound)` -> pierce 55
        (le port le retrouve via `ab.get_damage_profile()`, d'ou sa justesse generique).
    PROUVE LIVE (2 niveaux d'armure, base avg 1746 = (minDmg1496+maxDmg1996)/2, pierce 0) :
      - cible armure 2312 : base±20% [1397,2095] − 2312 < 0 -> plancher 1/coup -> main [2,2] / splash [1,1] EXACT.
      - cible armure 1003 : [1397−1003, 2095−1003] = [394,1092]/coup -> main(2c) [788,2184] / splash(1c) [394,1092] EXACT.
    Le port appliquait `dp.PiercingRatio=80` -> [2236,3352] (sur-prediction). Fix = mirror param_8=null =
    profil `None` (pierce 0, profile_idx -1). Cf. docs/rl/case-164-crushingclaws-pierce.md."""
    return {"profile_override": "None"}


def _hellfire_shells_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """`IdunBattle.AI.Playbook.Loki.HellfireShellsPlaybook$$MakeDamagePredictions` (carrier NPC/summon ultraNpc4Heavy-
    Intercessor / ultraSmnHeavyIntercessor, ability 1080) — mirror parfait de `CrushingClawsPlaybook
    IdunBattle.AI.Playbook.Loki.CrushingClawsPlaybook$$MakeDamagePredictions` (meme signature, meme appel `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`). SURCHARGE :
      - BASE = `IdunBattleLogic.Entities.DSLFactory$$Direct(GetVariableForLevel(0xc=minDmg)) = minDmg SEUL (rarity-scaled), PAS
        l'avg(minDmg,maxDmg) generique (@lvl65 mult100 : minDmg 582 vs avg 727 -> generique sur-pred +145/coup).
      - HITS = `GetNumberConstant(0x2f=nrOfHits)` + (`HasTrait(target, 0x3f9=BigTarget)` ?
        `GetNumberConstant(0x2b=extraHit)` : 0) = 2 vs cible normale, 4 vs BigTarget. Litteral (PAS +ExtraHits
        stat). Trait lu sur la CIBLE (`param_4`). Concorde avec le COMBAT `HellfireShellsAbility.Execute-
        Behaviour IdunBattleLogic.Entities.Abilities.Active.Loki.HellfireShellsAbility$$ExecuteBehaviour` (meme `If(HasTrait(target,BigTarget), base+bonus, base)`).
      - PROFIL = param_8 null -> `None` (pierce 0, armure PLEINE), MEME quirk que CrushingClaws #164.
    NON mesurable live (carrier NPC campagne + summon Environment, non-spawnable via rl_duel build) -> verdict
    decompile-proof (standard #169 HarbingerOfDestruction). Cf. docs/rl/case-173-hellfire-shells-base-hits.md."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)     # var 0xc = minDmg (Direct), rarity-scaled
    hits = int((cfg.constants or {}).get("nrOfHits") or 0)        # const 0x2f = nrOfHits
    tgt_traits = (GC.unit(scene.vis_by_id.get(target_id)) or {}).get("traits") or ()
    if "BigTarget" in tgt_traits:                                # HasTrait(target, 0x3f9=BigTarget)
        hits += int((cfg.constants or {}).get("extraHit") or 0)   # const 0x2b = extraHit (+2)
    return {"base_override": base, "hits_override": hits, "profile_override": "None"}


def _great_frost_axe_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignore (contrat registre)
    """`IdunBattle.AI.Playbook.Loki.GreatFrostAxePlaybook$$MakeDamagePredictions` (ability 1089) — BASE =
    `Get(GetVariableForLevel(0xc=minDmg, state))` = **minDmg SEUL** (rarity-scaled), PAS l'avg
    (minDmg+maxDmg)/2 generique. hits = GetNumberConstant(0x2f=nrOfHits=4) et profil =
    GetDamageProfile config (Piercing 80) = identiques au chemin generique -> pas d'override.
    Mesure 54321 s18 (u85 ab1089 -> t93) : off avg-based [4020,6032] vs nat minDmg-based
    [3576,5364] — centres per-hit 1256.4 vs 1117.5, ratio = (1+1.25)/2 = le maxDmg/minDmg
    config exact. Meme mold que HellfireShells #173 (Direct minDmg). #57e."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)     # var 0xc = minDmg (Get), rarity-scaled
    return {"base_override": base}


def _frenzied_firing_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """`IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions` (ability 1036,
    blackObliterator « Volk ») — le nb de coups de l'event PRINCIPAL n'est PAS `nrOfHits` : le playbook
    evalue le noeud `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetHitsForOriginalTarget`
    et le passe en 7e arg de `GenerateMultiHitAttackPredictions`. Transcription EXACTE de l'arbre natif :

        Min( Cache( Sum( Get(GetHits),                       # GetHits = GetNumberConstant(0x2f=nrOfHits)=1
                         Count( Filter( Walkable(AdjacentTiles(target@0x178)),
                                        Not(HasUnit(tile)) | Not(AreEnemies(Units(tile), caster@0x160)) ) ) ) ),
             ConfigConst(0x48 = maxNrOfHits) )

    = `nrOfHits` + le nombre de tuiles ADJACENTES A LA CIBLE qui sont marchables ET **pas occupees par un
    ennemi du caster** (une tuile vide compte ; une tuile tenue par un ALLIE du caster compte AUSSI —
    seule la presence d'un ennemi l'exclut), plafonne a `maxNrOfHits`. C'est donc une base GEOMETRIQUE :
    plus la cible est degagee, plus Volk la crible.

    GROUND TRUTH live (case-61, runner isole, board MC1_67, oracle `aiPlaybookPredict.appliedHits`) :
      - cible en plein champ, 6 voisins marchables, 1 ALLIE du caster sur l'un d'eux -> natif **7** = 1+6
        (l'allie ne retranche RIEN) ;
      - un ENNEMI place sur un voisin -> natif **6** = 1+5 ; deplacer l'allie d'un voisin a un autre ne
        change RIEN (toujours 6) ; un CADAVRE sur un voisin ne compte pas comme unite (tuile comptee).
    Le port rendait **1** (= `nrOfHits` config seul) dans TOUS les cas -> l'IA sous-estimait FrenziedFiring
    d'un facteur ~7. C'est la vraie cause du datapoint « 4 ou 5 selon la cible » de #87 (geometrie), et non
    un effet de la cible : ni `Diminutive` ni `Camouflage` ne modifient ce compte (le canal de coups n'est
    PAS interpose en prediction, cf. `services/attack_hits_formula.py`).

    Vivants seulement (`Units(tile)` = occupation REELLE ; `decisionView` garde les cadavres, cf. #57m).
    Board/positions absents -> `{}` = base generique (degradation fidele, aucune sur-prediction).

    VOLET AoE (2e batch, porte) : le playbook enchaine un SECOND
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    sur `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets` (= ennemis du
    caster adjacents a la CIBLE, `get_aoe_targets` de `FrenziedFiringAbility`) avec `hits = 1` **LITTERAL**
    (7e arg immediat du call-site : le natif n'evalue AUCUN noeud de coups pour ce batch — `nrOfHits`
    vaut 1 en config, mais le recopier serait une coincidence, pas un mirror), puis CONCATENE ses events
    dans la liste du 1er batch. Meme `GetDamageFormula` et meme `Nullable(GetDamageProfile)` que le batch
    d'origine -> `aoe_overrides` ne surcharge QUE les coups. `param_10` (poids Fix64) = 0 sur les deux
    batchs -> probabilite 1, aucune ponderation `GetMaxSecondaryTargets`.

    L'ARBRE de coups est celui de `FrenziedFiringAbility.get_hits_for_original_target` (DEFINITION
    UNIQUE, partagee avec la face COMBAT `runner/abilities/blacklegion.py` — un seul artefact natif,
    un seul port). Ce handler ne fait que lui fournir son `DslContext` (units/caster/target/board de
    la SCENE) et les deux constantes de config resolues."""
    board = getattr(scene, "board", None)
    n = int((cfg.constants or {}).get("nrOfHits") or 0)          # Get(GetHits) = GetNumberConstant(0x2f)
    cap = int((cfg.constants or {}).get("maxNrOfHits") or 0)     # ConfigConst 0x48
    # `hits = 1` LITTERAL du 2e batch — porte par la classe d'ability (constante native, pas config).
    aoe = {"aoe_overrides": {"hits_override": FrenziedFiringAbility.AOE_HITS}}
    by_id = {u.get("id"): u for u in (scene.units or [])}
    caster, target = by_id.get(caster_id), by_id.get(target_id)
    # Board/positions/constantes absents -> `{}` = base generique (degradation fidele, aucune
    # sur-prediction). `cap` absent est IMPOSSIBLE nativement (`GetNumberConstant` THROW sur cle
    # manquante) : la garde est un garde-fou offline, pas une branche native.
    if board is None or caster is None or target is None or not scene.pos(target_id) \
            or not n or not cap:
        return aoe
    dctx = dsl.DslContext(units=scene.units, caster=caster, target=target, board=board)
    # Min(., ConfigConst(maxNrOfHits)) pour le batch d'ORIGINE ; `aoe_overrides` garde hits=1.
    hits = int(FrenziedFiringAbility.get_hits_for_original_target(n, cap).evaluate(dctx))
    return {"hits_override": hits, **aoe}


# {ability_id: handler(scene, caster_id, target_id, ab, cfg) -> {base/hits/profile_override}}. Mirror du dispatch
# playbook natif (par type d'ability). HammerOfWrath (1153) a son propre chemin (make_hammer_wrath_events,
# NonComparable) ; ici = les playbooks Comparable qui surchargent juste les INPUTS de GenerateMultiHit.
_MAKE_DMG_INPUT_OVERRIDES = {1191: _martial_inspiration_inputs, 1105: _crushing_claws_inputs,
                             1080: _hellfire_shells_inputs, 1089: _great_frost_axe_inputs,
                             1036: _frenzied_firing_inputs}


# Override de PROFIL DE PREDICTION par-ability (audit #165) — mirror du `param_8`
# (`Nullable<DamageProfile>`) que le `<Ability>Playbook.MakeDamagePredictions` bespoke passe a
# `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`. Le port derive par defaut le profil de
# `ab.get_damage_profile()` (damageProfile config, sinon arme ranged-first) ; ces playbooks passent
# EXPLICITEMENT un autre profil (ou `null` = profil `None`, enum -1 -> pierce 0, armure PLEINE). Sans
# override, le port applique le PiercingRatio du profil derive -> sur/sous-prediction vs le natif.
# {ability_id: nom de profil passe par le playbook natif}. "None" = param_8 null (pierce 0). VA = playbook.
# CrushingClaws (1105) reste dans _crushing_claws_inputs (case-164, bit-exact live). Les autres candidats de
# l'audit #165 (param_8=null confirme par decompile) NE sont retenus QUE s'ils sont VALIDES LIVE OK sur cible
# blindee (ultraTitus armure 2312) : le seul override pierce ne corrige que les abilities dont le pierce est le
# SEUL gap. La confrontation live a montre que la majorite des candidats null ont un gap PLUS PROFOND (hits/base)
# que l'override ne touche pas -> NON retenus (taches dediees). Cf. docs/rl/case-165-playbook-param8-profile.md.
_PLAYBOOK_PROFILE_OVERRIDE = {
    1020: "None",     # HeraldOfTheApocalypse IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$MakeDamagePredictions (blackHaarken ; null ; Piercing 80) — VALIDE LIVE OK
    1062: "None",     # SanctorumMissile IdunBattle.AI.Playbook.Loki.SanctorumMissilePlaybook$$MakeDamagePredictions (adeptMorvenn ; null, main+bonus ; Blast 15) — VALIDE LIVE OK
    1017: "None",     # FragBomb IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$MakeDamagePredictions (astraBullgryn ; null ; Blast 15) — hits config 6 OK, pierce SEUL gap. VALIDE LIVE [6,6] [#168]
    1006: "None",     # MultiThreatEliminator IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$MakeDamagePredictions (necroDestroyer ; null ; Gauss 60) — + hits static 6 (subclass). VALIDE LIVE [6,6] [#167]
    1066: "Psychic",  # Executioner IdunBattle.AI.Playbook.Loki.ExecutionerPlaybook$$GeneratePredictions (eldarFarseer ; Nullable(0xd=13=Psychic, pierce 100)) — hits=RoundsStarted (subclass) [#166]
    1008: "None",     # HarbingerOfDestruction IdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions (necroPlasmancer ; nullIdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions+0x1cc ; ability DirectDamage pierce 100) [#169]
    #   RE PROUVE pierce-SEUL gap : base=ArcScourge.GetDamage=avgIdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions+0x13c OK, hits=ArmoriumCherub.GetHits configIdunBattle.AI.Playbook.Loki.HarbingerOfDestructionPlaybook$$MakeDamagePredictions+0x16e OK.
    #   NON confronte live (necroPlasmancer = UNSPAWNABLE_FALLBACK ; autres carriers = NPC necroBoss*). Retenu sur preuve
    #   decompile (structure IDENTIQUE aux 1020/1062 valides live) — le deep-read RE a explicitement exclu tout gap base/hits.
    # --- audit #165 param_8=null : les 5 AUTRES candidats NE sont PAS des overrides pierce (confronte #169) :
    #   1027 PsychicMaelstrom IdunBattle.AI.Playbook.Loki.PsychicMaelstromPlaybook$$MakeDamagePredictions : param_8 = Nullable(BasiliskBarrage.GetDamageProfile) EXPLICITE (PAS null ; l'audit
    #     d'arite confondait param_8=profil et param_9=poids Fix64). Live OK bit-exact [2792,4188] (astraPrimarisPsy). AUCUN override.
    #   1100 SorcerousFacade IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions : base=Half(Sum(var0xc,var0xd)) DSL != avg -> gap BASE (tache dediee).
    1148: "None",     # DaemonicOrdnance IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$MakeDamagePredictions (blackForgefiend MoW) ; param_8=null -> pierce 0/armure pleine [#172]
    1147: "None",     # HadesAutocannons IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$MakeDamagePredictions (blackForgefiend MoW) ; param_8=null -> pierce 0/armure pleine [#172]
    #   ^1148/1147 : RE #172 REFUTE l'ancienne hypothese "gap BASE". base = IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetDamage /
    #   IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$GetDamage = IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(avgFlag) = Half(Sum(minDmg 0xc,maxDmg 0xd))
    #   = avg GENERIQUE (== ab.get_damage) ; hits = IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits = nrOfHits GENERIQUE. Seul gap = param_8=null.
    #   param_8 (GenerateMultiHit sig IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions) = profil passe a PredictAttack slot 0x27 ; 1147/1148 ont 0 en param_8 ET param_10
    #   (poids Fix64) -> l'arite qui confondait 1027 (param_8 vs param_10) est ici tranchee. Decompile-proof (base/hits exclus,
    #   meme standard que 1008) ; carrier MoW -> confront live via aiPlaybookPredict (harnais #172) = gate ideal residuel.
    #   1080 HellfireShells IdunBattle.AI.Playbook.Loki.HellfireShellsPlaybook$$MakeDamagePredictions : base=Direct(0xc=minDmg SEUL) + hits=nrOfHits(+extraHit si cible BigTarget)
    #     + param_8=null -> PORTE #173 via _hellfire_shells_inputs (base+hits+profile ensemble). Cf. case-173.
}


def make_damage_predictions(scene, caster_id, main_tgt_id, ability_id, ability_name, attack_pos=None):
    """`<Ability>Playbook.MakeDamagePredictions` : LISTE de `ProbableDamageEvent` = cible PRINCIPALE + AoE
    (`GetSurroundingUnits`/`GetOtherTargets`) + event SELF negatif (cout PV). `[]` si non-attaque."""
    if not makes_damage_predictions(ability_name):
        return []
    # #99 REFRAMING (case-99) : les specials ne sont PAS Attack-based. L'hypothese historique
    # « SpiritLeech herite ALoki_NormalAttackAbility.PredictAttack (slot vtable 0x27) » est REFUTEE — les
    # 5 specials audites resolvent `PredictAttack` vers le STUB ABSTRAIT `AActiveAbility.PredictAttack
    # IdunBattle.Entities.Abilities.AActiveAbility$$PredictAttack` (qui THROW). Le vrai chemin = `<Special>Playbook.MakeDamagePredictions` ->
    # `GenerateMultiHitAttackPredictions(base = ability.GetAttackDamage() = CONFIG minmax)`. Donc
    # `_PREDICT_VIA_NORMAL_ATTACK` est VIDE (via_normal toujours False) ; la branche est conservee morte
    # au cas ou un special s'avererait un jour reellement Attack-based.
    via_normal = ability_name in _PREDICT_VIA_NORMAL_ATTACK
    # ab/cfg/aoe construits ICI (AVANT le main event) car le compte AoE TOTAL (nrEnemies = 1 + secondaires)
    # est requis pour la clause `GetCorrectDamage` (MurderousSwing : +extraDmg AJOUTE A LA BASE si UN seul
    # ennemi touche, #108). `base_bonus` = delta de base, 0 pour toute ability sans clause (get_correct_damage
    # = identite) -> aucun autre chemin affecte. Le natif calcule `nrEnemies=Count(targets)` de meme AVANT
    # d'appeler GetCorrectDamage puis GenerateMultiHitAttackPredictions par cible (MakeDamagePredictions).
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    ab = active_ability_for(ability_name, ability_id, ctx0, cfg,
                            ability_state=scene.ability_state(caster_id, ability_id)) \
        if (ctx0 is not None and cfg is not None) else None
    aoe = []
    if ab is not None:
        by_id = {u.get("id"): u for u in scene.units}
        dctx = dsl.DslContext(units=scene.units, caster=by_id.get(caster_id),
                              target=by_id.get(main_tgt_id), config=cfg, ability_level=ab.level,
                              times_attacked=getattr(ctx0, "times_attacked", 0) or 0,
                              caster_pos=attack_pos, elev_by_pos=scene.elev_by_pos)
        aoe = [t for t in ab.get_aoe_targets(dctx)
               if t.get("id") is not None and t.get("id") != main_tgt_id]
    base_bonus = 0
    if ab is not None:                               # GetCorrectDamage(base, nrEnemies) - base (>= 0)
        _b = ab.get_damage()
        base_bonus = max(0, ab.get_correct_damage(_b, 1 + len(aoe)) - _b)

    # Dispatch per-ability (mirror du registre playbook natif) : un handler ability-specifique fournit ses
    # overrides d'ENTREE (base/hits/profile) ; sinon `{}` -> chemin generique config inchange. La logique
    # ability-specifique vit dans son handler HOMONYME (cf. `_MAKE_DMG_INPUT_OVERRIDES`), jamais inline ici.
    _ovr_fn = _MAKE_DMG_INPUT_OVERRIDES.get(ability_id)
    overrides = _ovr_fn(scene, caster_id, main_tgt_id, ab, cfg) if (_ovr_fn and ab is not None and cfg is not None) else {}
    # BATCH SECONDAIRE a entrees PROPRES (`aoe_overrides`) — mirror des playbooks qui appellent
    # `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    # DEUX fois avec des arguments differents (ex. FrenziedFiring : `hits` = noeud geometrique pour la cible
    # d'origine, `hits = 1` LITTERAL pour `FrenziedFiringAbility$$GetTargets`). Cle META consommee ici, JAMAIS
    # transmise en kwarg. Absente -> le batch AoE herite exactement des entrees du batch principal (cas de
    # tous les autres playbooks portes, qui repassent les memes formule/hits/profil aux deux boucles).
    _aoe_ovr = overrides.pop("aoe_overrides", None) if overrides else None
    # Profil de prediction par-ability (audit #165) : le playbook natif passe un param_8 explicite (ou null).
    _prof_ovr = _PLAYBOOK_PROFILE_OVERRIDE.get(ability_id)
    if _prof_ovr is not None and "profile_override" not in overrides:
        overrides = {**overrides, "profile_override": _prof_ovr}
    aoe_overrides = {**overrides, **_aoe_ovr} if _aoe_ovr else overrides

    def _event(tid, prob1=1.0, ovr=None):
        if via_normal:
            ev = make_normal_attack_predictions(scene, caster_id, tid, attack_pos)
            if ev is not None and prob1 != 1.0:
                ev.probability1 = prob1
            return ev
        dp = generate_multi_hit_attack_prediction(scene, caster_id, tid, ability_id, ability_name,
                                                  attack_pos=attack_pos, base_bonus=base_bonus,
                                                  **(overrides if ovr is None else ovr))
        return ProbableDamageEvent(target=tid, prediction=dp, probability1=prob1) if dp is not None else None

    main = _event(main_tgt_id)
    if main is None:
        return []
    events = [main]
    if ab is None:
        return events
    # Plafond secondaire (`GetMaxSecondaryTargets`) -> poids batch `min(1, max/n)` = probability1.
    maxsec = ab.get_max_secondary_targets()
    prob1 = (min(1.0, maxsec / len(aoe)) if (maxsec is not None and aoe) else 1.0)
    for t in aoe:
        aev = _event(t.get("id"), prob1, aoe_overrides)
        if aev is not None:
            events.append(aev)
    # #108 count² : les abilities AoE SELF-centrees (MurderousSwing) RE-EMETTENT la liste d'events de degat
    # `count` fois — le playbook natif boucle sur le set `AdjacentEnemies(caster)` (EXTERNE) ET
    # `GenerateMultiHitAttackPredictions` re-boucle sur ce MEME set (INTERNE) -> count² events, chaque cible
    # `count` fois (CONFIRME LIVE : K=1->1, K=2->4, K=3->9). `get_prediction_set_repeat` = count (= 1+len(aoe),
    # taille du set) pour ces abilities, 1 sinon (lineaire INCHANGE pour toutes les autres). Ordre = blocs
    # [main,aoe...] repetes (mirror boucle externe). Refs partagees OK (util Sigma read-only). AVANT l'event SELF.
    rep = ab.get_prediction_set_repeat(1 + len(aoe))
    if rep > 1:
        events = events * rep
    # Event SELF negatif — cout en PV (`ability.GetHealthToLose`), utilite NEGEE (friendly).
    hp_c = scene.hp(caster_id) or 0
    max_c = scene.hpmax(caster_id) or hp_c
    hl = ab.get_health_to_lose(max_c)
    if hl:
        self_dp = _self_damage_prediction(hp_c, hl)
        events.append(ProbableDamageEvent(target=caster_id, prediction=self_dp, friendly=True))
    return events


_HAMMER_ABILITY_NAME = "HammerOfWrath"
_HAMMER_MAX_SECONDARY = 3   # SelectUniqueUnits(GetAdjacentTargets, 3)


def make_hammer_wrath_events(scene, caster_id, target_id, attack_pos):
    """Events degat INTERNES de HammerOfWrath (id 1153) pour scorer son utilite de DECISION NonComparable
    (`IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable`), depuis `attack_pos` (tuile ou le caster
    charge). Bypass du gate d'affichage #109 (Hammer n'emet AUCUN ProbableDamageEvent affiche ; le degat est
    consomme EN INTERNE par l'utilite). Chaque event = `PredictAttack(0x27)` avec les `(damage, hits, profile)`
    PROPRES de Hammer (config gqfc5mff6c verifiee) :
      - PRIMARY (cible) : base=`minDmg` (AbilityVariableType 12, IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetMinDamage), hits=`nrOfHits`
        (AbilityConstantType 47, IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits = 2), profil=`damageProfile` (Power).
      - SECONDARY (chaque ennemi VIVANT adjacent a la cible, `IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetAdjacentTargets` =
        `Enemies(AdjacentUnits(TARGET, r=1))` ou `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` = `Units(AdjacentTiles(target))
        − target` : unites lues par OCCUPATION DE TUILE → un mort n'est plus sur le board (notre
        pos_by_id garde les cadavres, d'ou le filtre hp>0 explicite — #57m, corpse u95 +120 a 54321 s8),
        plafond `SelectUniqueUnits(3)`) : base=`minDmg_2` (var 54,
        IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$GetMinDamage2), hits=`nrOfHits_2` (const 50, BringerOfDespair.GetHitsToBonusTarget = 1),
        profil=`damageProfile_2` (Physical).
    Le reste du pipeline (spread ±20%, pierce, armure, mods attaquant/positionnels, bouclier) est identique au
    chemin normal via `generate_multi_hit_attack_prediction` (base/hits/profile override). `[]` si indisponible."""
    import hexgeo
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(_HAMMER_ABILITY_NAME, GC.ability(_HAMMER_ABILITY_NAME))
    if ctx0 is None or cfg is None:
        return []
    ab = active_ability_for(_HAMMER_ABILITY_NAME, 1153, ctx0, cfg,
                            ability_state=scene.ability_state(caster_id, 1153))
    lvl, mult = ab.level, ab.multiplier
    minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)         # var 12 (GetMinDamage)
    minv2 = cfg.get_variable_for_level("minDmg_2", lvl, 0, mult)      # var 54 (GetMinDamage2)
    consts = cfg.constants or {}
    hits1 = max(1, int(consts.get("nrOfHits") or 1))                  # const 47 (GetHits = 2)
    hits2 = max(1, int(consts.get("nrOfHits_2") or 1))               # const 50 (GetHitsToBonusTarget = 1)
    prof1 = consts.get("damageProfile")                              # Power
    prof2 = consts.get("damageProfile_2")                            # Physical
    dp = generate_multi_hit_attack_prediction(scene, caster_id, target_id, 1153, _HAMMER_ABILITY_NAME,
                                              attack_pos=attack_pos, base_override=minv,
                                              hits_override=hits1, profile_override=prof1)
    if dp is None:
        return []
    events = [ProbableDamageEvent(target=target_id, prediction=dp)]
    # SECONDARIES : Enemies(du caster) adjacents a la CIBLE (hex dist 1), plafond 3.
    caster_team = scene.team(caster_id)
    t_pos = scene.pos(target_id)
    if t_pos is not None:
        # `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits` = Units(AdjacentTiles(target)) − target : occupation de TUILE
        # → vivants seulement (pos_by_id garde les cadavres ; idiome hp>0 = IsAlive, cf. l.227/276).
        adj = [u for u in scene.pos_by_id
               if u != target_id and scene.team(u) != caster_team
               and (scene.hp(u) or 0) > 0
               and scene.pos(u) is not None and hexgeo.distance(scene.pos(u), t_pos) == 1]
        for sid in adj[:_HAMMER_MAX_SECONDARY]:
            sdp = generate_multi_hit_attack_prediction(scene, caster_id, sid, 1153, _HAMMER_ABILITY_NAME,
                                                      attack_pos=attack_pos, base_override=minv2,
                                                      hits_override=hits2, profile_override=prof2)
            if sdp is not None:
                events.append(ProbableDamageEvent(target=sid, prediction=sdp))
    return events


def _self_damage_prediction(hp_c: int, hl: int):
    """`DamagePredictionResult` du cout self (sante perdue `hl`, pas de bouclier, appliedHits=0)."""
    from engine.services.damage_prediction import DamagePredictionResult
    return DamagePredictionResult(
        current_health=hp_c, shield=0,
        accurate_health_damage=MinMaxDamage(min=min(hl, hp_c), max=min(hl, hp_c)),
        accurate_shield_damage=MinMaxDamage(min=0, max=0), applied_hits=0)
