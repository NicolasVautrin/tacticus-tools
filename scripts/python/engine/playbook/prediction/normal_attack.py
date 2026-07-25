"""Prediction de l'ATTAQUE NORMALE : `make_normal_attack_predictions` (`ALoki_NormalAttackPlaybook.
MakeDamagePredictions @181372730`), la base display re-positionnee `_display_attack_base` (#49/#153/#57a),
l'override drone `_make_mv71_drone_predictions` (#61bis tranche 3) et les follow-ups de boss
(get_additional / get_klaw). Consomme le socle `_shared` (helpers mods/defenseur + vocabulaire commun)."""
from __future__ import annotations

from ._shared import *   # vocabulaire commun (GC, hexgeo, get_attack_prediction, ProbableDamageEvent, auras, ...)
from ._shared import (_PROFILE_INDEX, _weapon_pierce, _add_positional_and_defender_mods,
                      _target_damage_limits, _apply_ally_attack_dmg_bonus, _round_fix64)


# ── #57c-C : overrides `<Boss>_NormalAttackAbility.PredictAttack` (attaque normale + follow-up) ──
# Dispatch natif ActiveAbilityType→classe : l'attaque NORMALE de certains boss est instanciee sur une
# SOUS-CLASSE qui surcharge PredictAttack = base ALoki (@1811afa50) + prediction ADDITIONNELLE calculee
# sur scenario VIERGE puis sommee via `DamagePredictionResult.Add @18102a710` (appliedHits natif 1+1=2).
# Deux molds (corps COMDAT partages par famille — l'instance porte la CONFIG du passif du kit) :
#  - RANGED (`Boltstorm_NormalAttackAbility.PredictAttack @1811bd950`, gate arme choisie `!IsMelee`) :
#    `GetAdditionalDamagePrediction @1811bd170` = eval MODE 4 (= MIN) de `GetAdditionalDamageAmount
#    @1811bceb0` = `RandomAmount(var 0xc minDmg, var 0xd maxDmg)` → hits = ConfigConst(0x2f nrOfHits),
#    profil = `AbilityConfiguration.GetDamageProfile` du passif, slot 0x27 SANS widgets modifiers.
#    ⚠ AUCUN porteur confirme : l'hypothese « Gulgortz/LightImUp = ce mold » est REFUTEE (varTrace
#    2468 s14 : le +3×1496 de u89 = les 3 effets FoulInfusion_ExtraHits du canal #179 GLOBAL, cf.
#    FoulInfusionExtraHitsEffect ; la coincidence LightImUp.minDmg[50] == FoulInfusion.dmg[50] == 831
#    a masque la vraie source). Registre VIDE tant qu'un porteur reel du mold n'est pas mesure.
#  - MELEE (`ProperKilly_NormalAttackAbility.PredictAttack @1811fc690`, gate `!IsRanged`) :
#    `GetKlawAttack1Prediction @1811fbe10` = n = ConfigConst(0x2f nrOfHits=1) coups de
#    `GetFirstAttackDamage @1811fb760` = `PercentageOf(StatAmount(target, Health=5, part=2 Max),
#    ConfigConst(0x3b dmgPct=60), mode 0)`, profil Power(40), chaque coup via `GetKlawAttack1Hit-
#    Prediction @1811fb800` (meme slot standard). Ghazghkull — NON exerce au batch gen (port 1:1
#    du decompile, non valide live).
# Cle de dispatch = le PASSIF du kit gameconfig (l'instance native lit SA config = celle du passif).
_RANGED_FOLLOWUP_PASSIVES = ()          # vide — cf. refutation LightImUp ci-dessus (#57c-C)
_MELEE_KLAW_PASSIVES = ("ProperKilly",)


def get_additional_damage_prediction(scene, att_id, tgt_id, ability_name):
    """`Boltstorm_NormalAttackAbility.GetAdditionalDamagePrediction @1811bd170` — follow-up RANGED :
    amount = MIN du `RandomAmount(minDmg, maxDmg)` (eval mode 4), hits = nrOfHits, profil propre du
    passif, mods attaquant ABSENTS (le call slot 0x27 natif ne passe pas les widgets modifiers),
    scenario VIERGE (armure/bouclier de la cible re-disponibles — quirk natif mirrore)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    lvl = scene.ablvl_by_id.get(att_id)
    amount = ability_var(ability_name, "minDmg", lvl, multiplier_pct=scene.mult(att_id))
    n = ability_var(ability_name, "nrOfHits", is_constant=True)
    if not amount or amount <= 0 or not n or n <= 0:
        return None
    prof = ((GC.ability(ability_name) or {}).get("constants") or {}).get("damageProfile") or ""
    prof_ratio = int((GC.damage_profile(prof) or {}).get("PiercingRatio") or 0)
    # pierce = profil + ExtraPierce stat (GetAttackPiercingDamageRatio @181030a20, meme pipeline 0x27)
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + ctx.extra_pierce_ranged))
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits")))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=int(n),
        profile_type=_PROFILE_INDEX.get(prof, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=None, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof),
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof),  # #69 gate NoBlocking
        attacker_effects=scene.effects(att_id))   # #202 : PredictAttackRaw universel


def get_klaw_attack1_prediction(scene, att_id, tgt_id, ability_name):
    """`ProperKilly_NormalAttackAbility.GetKlawAttack1Prediction @1811fbe10` — klaw MELEE : n coups de
    `PercentageOf(MaxHealth EFFECTIF de la cible, dmgPct, mode 0)` (`GetFirstAttackDamage @1811fb760`),
    profil propre (Power 40), scenario VIERGE, coups chaines (armure depletee entre coups — c'est le
    per-coup standard de get_attack_prediction)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    pct = ability_var(ability_name, "dmgPct", is_constant=True)
    n = ability_var(ability_name, "nrOfHits", is_constant=True)
    hpmax = scene.hpmax(tgt_id)
    if not pct or pct <= 0 or not n or n <= 0 or not hpmax:
        return None
    amount = _round_fix64(Fraction(int(pct) * int(hpmax), 100), 0)   # PercentageOf mode 0 (half-to-even)
    prof = ((GC.ability(ability_name) or {}).get("constants") or {}).get("damageProfile") or ""
    prof_ratio = int((GC.damage_profile(prof) or {}).get("PiercingRatio") or 0)
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + ctx.extra_pierce_melee))
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits")))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=int(n),
        profile_type=_PROFILE_INDEX.get(prof, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=None, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof),
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof),  # #69 gate NoBlocking
        attacker_effects=scene.effects(att_id))   # #202 : PredictAttackRaw universel


def _normal_attack_followup_prediction(scene, att_id, tgt_id, is_melee, weapon_found):
    """Selecteur du mold follow-up de l'attaquant (cf. bloc ci-dessus). None = pas de fold
    (pas d'arme trouvee / kit sans passif concerne / gate melee-ranged non satisfaite)."""
    if not weapon_found:
        return None                       # mirror `FindAttackWeapon != null` (@1811bd950 / @1811fc690)
    try:
        kit = GC.unit_abilities(scene.vis_by_id.get(att_id)) or {}
    except Exception:
        return None
    names = {(a.get("name") or "") for lst in (kit.get("passive"), kit.get("active"))
             for a in (lst or [])}
    if not is_melee:
        for nm in _RANGED_FOLLOWUP_PASSIVES:
            if nm in names:
                return get_additional_damage_prediction(scene, att_id, tgt_id, nm)
    else:
        for nm in _MELEE_KLAW_PASSIVES:
            if nm in names:
                return get_klaw_attack1_prediction(scene, att_id, tgt_id, nm)
    return None


def _display_attack_base(scene, att_id, attack_pos, is_melee):
    """Base ATTACK de la chaine DISPLAY, re-positionnee a la tuile candidate (#49/#153/#57a) :
    base = CURRENT(du pas) − aura_modele(position reelle) + aura_modele(tuile candidate). Les AURAS
    stat-mod d'allies (RitesOfBattle @181225340, PathOfCommand @181110f10) sont re-evaluees a
    `attack_pos` ; les mods NON-positionnels (ex. SummaryExecution_BaseEffect 1043 +400, #57a)
    restent inclus via CURRENT. FOYER PARTAGE (#61bis tranche 3) : l'attaque normale ALoki
    (`GetAttackHitPrediction @1811af4e0` = GetStat(Attack, Current) + arme) ET le chemin drone MV71
    (delegue b__1 @181119590 = `StatAmount(Caster, ATTACK, CURRENT)`) font la MEME lecture native.
    Renvoie `(attack_base, carriers, att_grand, att_faction, _ap)` (carriers/gates reutilises par
    l'appelant normal pour les hits/auras)."""
    _ap = attack_pos or scene.pos(att_id)
    # #153 (tranche le flip-flop #45/#58/#67) : la chaine display threade la position candidate de bout
    # en bout — `DamagePredictionQuery.GetAllPredictions @181090f50` construit `UnitPosition(tuile de
    # selection)` et la passe au service ; `DamagePrediction.PredictNormalAttack @181037cd0` en tire
    # `get_MainTile` et la pose comme CasterTile dans `AbilityEntities.ctor`. Les auras d'attaque-stat
    # sont donc re-evaluees PAR TUILE CANDIDATE (PAS la valeur bakee a la position reelle). MESURE
    # discriminante seed-31337 (1 decisionView, attaquant reel FIXE adjacent au porteur, seule la tuile
    # varie) : u92 out-ring 12/12 = base Initial (aura PERDUE malgre le stat-mod +1298 present live) ;
    # u96 (reel LOIN du porteur, aucun stat-mod) sur tuile in-ring = base Initial+aura (aura GAGNEE).
    # L'ancien verdict #67 (« aura bakee a la position reelle, GetStat sans position ») etait un artefact :
    # son test etait circulaire (port-vs-port) et son unique GetStat de GetAttackHitPrediction @1811af4e0
    # lit en realite `GetStat(AbilityEntities.Target@+0x10, Health=5, Current)` (HP cible), pas un Attack.
    _att_gu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    att_grand = _att_gu.get("GrandAllianceId")           # gate RitesOfBattle (Imperial)
    att_faction = _att_gu.get("FactionId")               # gate PathOfCommand (IsSameFaction = FactionId)
    # #41 : gate de MATERIALISATION pour la MELEE SEULEMENT (att_real_pos=None -> gate inactif).
    # Mesures seed-31337 (2026-07-20) : RANGED suit purement la tuile CANDIDATE (#153 confirme, gain
    # inclus — u95 thousAhriman reel dist-3 de Calgar, candidate (4,5) in-ring : natif = base+898 sur
    # les 2 canaux ranked/aiPlaybookPredict) ; MELEE ne gagne PAS l'aura d'une tuile candidate (u93
    # deathRotbone s13 : candidate (2,3) in-ring, natif = base Initial ×1.5 elevation EXACT). Le seul
    # cas melee+materialise mesure ((6,5) u91) est candidate-out-ring (les deux modeles le couvrent) —
    # si un futur contre-cas melee+materialise+in-ring sort sans aura native, passer la melee en
    # « jamais d'aura » (v4) et RE le read natif du stat Attack en prediction.
    aura_ctx = {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                "att_grand_alliance": att_grand, "att_faction": att_faction, "board": scene.board,
                "att_real_pos": scene.pos(att_id) if is_melee else None}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),   # owner grande-alliance
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"),         # owner faction
                 scene.effects(uid)) for uid in scene.pos_by_id                      # (type-level, miroir-safe)
                if uid != att_id and (scene.hp(uid) or 0) > 0]
    # #41 : tuile candidate NON-ENTRABLE (BlockEnteringUnits, ex. mur Thorns (1,3) MC1_67) -> le natif
    # perd l'aura MEME materialisee+in-ring (u89 s11 : candidate (1,3) = base Initial 803 ×1.5 elevation
    # EXACT, vs (3,3) propre = 2101 garde) : `GetUnitPositionAtTile` sur tuile bloquee rend une position
    # degeneree -> l'adjacence du re-check echoue. L'elevation, lue sur la TUILE, s'applique toujours.
    _cand_blocked = "BlockEnteringUnits" in ((scene.tile_effects_by_pos or {}).get(tuple(_ap)) or ())
    # #57a : la base CONSERVE les stat-mods NON-positionnels courants (SummaryExecution_BaseEffect
    # 1043 : +400 flat aux Friends(UnitsWithTrait), selecteur SANS noeud d'adjacence — decompile
    # `SummaryExecutionEffect.CreateTargetSelector @180f6f8a0` ; vecu 1357 s15 u135 : natif per-hit
    # = 1.2/1.8 × 1496 (CURRENT) et non ×1096 (INITIAL)). Modele : base = CURRENT(du pas)
    # − aura_modele(position reelle) + aura_modele(tuile candidate) — algebriquement
    # = INITIAL + mods-non-aura + auras re-evaluees (#153) ; identique a l'ancien INITIAL+aura
    # quand aucun mod non-aura n'est pose (aura_baked == aura_modele(reel), cf. #49 exact).
    _aura_cand = 0 if _cand_blocked else aura_attack_bonus_from_allies(carriers, aura_ctx)
    _rp = scene.pos(att_id)
    _aura_real = (aura_attack_bonus_from_allies(
        carriers, {**aura_ctx, "att_pos": _rp, "att_real_pos": _rp if is_melee else None})
        if _rp is not None else 0)
    attack_base = scene.attack_current(att_id) - _aura_real + _aura_cand
    return attack_base, carriers, att_grand, att_faction, _ap


_MV71_CONFIG = "MV71SniperDroneSquad"    # l'entree gameconfig (passif 1119) qui porte constants/variables


def _make_mv71_drone_predictions(scene, att_id, tgt_id, attack_pos, *, meta=False):
    """`MV71SniperDroneSquadAttackAbility.PredictAttack @18110a5f0`, branche DISTANCE (#61bis
    tranche 3 — la branche melee delegue a ALoki et reste dans `make_normal_attack_predictions`).

    Mirror du decompile (re-lu 2026-07-22) :
      - tile = PickTile — delegue b__0 @1811194e0 = `() => PickTile(entities, firstOnly=0)`, LE MEME
        PickTile que l'execution (memoise par un service de cache) -> `pick_tile_scene` (hydrateur
        scene du port runner, scoring partage). Parent = la POSITION CANDIDATE (#153).
        **Aucune tuile -> prediction VIDE** (memset 0xc0 + liste block vide = resultat ZERO, pas
        d'absence d'event).
      - hits = `ExtraHitsComponent(CASTER).CurrentValue + 1`, stocke DisplayClass@0x148 et consomme
        par le 3e delegue (DAT_183279860 — « b__2 » sans symbole ghidra, alias « m860 ») : role
        compte-de-coups tranche PAR ELIMINATION (b__0 = tile, b__1 = degat : aucun autre lecteur
        possible du champ @0x148) + position = celle du delegue hits par defaut du fallback ALoki
        (slot 0x25, DAT_183283000). Confronte live via `appliedHits` d'aiPlaybookPredict.
      - degat = delegue b__1 @181119590 = `StatAmount(Caster, ATTACK, CURRENT)` ->
        `_display_attack_base` (MEME lecture display que la normale, re-positionnee #153).
      - arme = la config d'attaque du DRONE (service slot 0xc0 = unit-config par id, champ @0x18),
        resolue par la distance TUILE DU DRONE -> cible (le drone tire de SA tuile) ; pierce =
        PiercingRatio du profil + ExtraPierce de l'unite passee au service (`GetUnit(tile) ?? caster`
        -> le CASTER a la prediction, aucun drone encore pose — flag : au fallback-cap la tuile porte
        un drone, l'unite native serait CE drone, ExtraPierce 0 dans les deux cas).
      - attribution = Nullable<AbilityOrEffect>(1076) ; canal additional-hits keye sur l'attackTypeId
        du drone (unit-config @0x10) : `GetAdditionalHitsFromEffectsForPrediction` +
        `AddAdditionalHitsToPrediction` — MEME canal #179 que la normale (effets du CASTER + auras).
      - modifiers (ARBITRE LIVE, probe_61bis_pred seed 61011) : le widget attaquant est **ZEROE**
        (memset `&local_3f8` — le `param_4` du playbook N'EST PAS forwarde, contrairement a la
        branche melee qui le passe a ALoki) -> AUCUN mod ATTAQUANT-effets (builder @181000590 cote
        appelant ; residu flagge : aucun datapoint caster-avec-effet-d'attaque encore). MAIS les
        mods POSITIONNELS + DEFENSEUR sont calcules EN AVAL DANS le service et S'APPLIQUENT :
          . ELEVATION evaluee a la TUILE DU DRONE vs cible (rows x1.5 EXACT quand la tuile choisie
            est surelevee : (3,6)/(2,6)/(6,6) elev2 vs cible elev1 — le flip post-cast de (4,6)
            1.5->1.15 quand le drone reel occupe (3,6) le prouve) ;
          . DEFENSEUR : cible Markerlit -> x1.15 EXACT sur les rows plates (3694,5541 = 3212,4818
            x1.15), compose x1.725 = 1.5x1.15 sur les rows surelevees.
        -> port : `_add_positional_and_defender_mods(attack_pos = TUILE DU DRONE)` sur un
        `DamageModifiers()` vierge (l'attaquant du coup = le drone, identite/niveau = caster,
        mirror du `unit` passe au service)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    consts = (GC.ability(_MV71_CONFIG) or {}).get("constants") or {}
    unit_id = consts.get("unitId")                       # GetStringConstant(cfg, 0) = tauSmnDroneSniper
    max_summons = int(consts.get("maxSummons") or 3)
    t_pos = scene.pos(tgt_id)
    if unit_id is None or t_pos is None:
        return None
    from engine.runner.abilities.loki.mv71 import pick_tile_scene
    tile_pos = pick_tile_scene(scene, att_id, tgt_id, unit_id, max_summons,
                               parent_pos=attack_pos or scene.pos(att_id))
    if tile_pos is None:
        from engine.services.damage_prediction import DamagePredictionResult
        ev = ProbableDamageEvent(target=tgt_id, prediction=DamagePredictionResult())
        return (ev, {"mv71": True, "tile": None}) if meta else ev
    # hits (delegue « m860 ») = ExtraHits CURRENT du CASTER + 1 — PAS la formule arme
    # (AttackHitsWithModifiersFormula n'est PAS appelee sur ce chemin : ni GetStuckIn, ni malus
    # defenseur LightCover/Parry, ni hits d'arme).
    _xh = scene.extra_hits_current(att_id)
    hits = 1 + int(_xh if _xh is not None else (ctx.stat(StatType.EXTRA_HITS) or 0))
    # degat (delegue b__1) = StatAmount(Caster, ATTACK, CURRENT) — foyer partage display (#153).
    attack_base, carriers, att_grand, att_faction, _ap = _display_attack_base(
        scene, att_id, attack_pos, is_melee=False)
    # arme du drone par distance tuile->cible (mirror config d'attaque @0x18 du unit-config drone).
    from engine.services.battle_query import get_attack_weapon_for_default_normal_attack
    _adj = are_tiles_adjacent(tile_pos, t_pos, scene.board)
    _d = hexgeo.distance(tile_pos, t_pos)
    w, w_ranged = get_attack_weapon_for_default_normal_attack(unit_id, _adj, dist=_d)
    prof_name = (w or {}).get("DamageProfile")
    _dpw = GC.damage_profile(prof_name) or {}
    dir_pierce = ctx.extra_pierce_ranged if w_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, int(_dpw.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    from engine.services.damage_modifiers import DamageModifiers
    mods = DamageModifiers()                             # widget attaquant ZEROE (cf. docstring)
    # POSITIONNELS + DEFENSEUR (service-side, arbitre live) : attack_pos = LA TUILE DU DRONE
    # (elevation drone->cible), defenseur incl. Markerlight (faction caster = T'au, threadee #61bis).
    _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, not w_ranged, tuple(tile_pos),
                                      t_pos, damage_profile=prof_name)
    # canal additional-hits #179 (cle native = attackTypeId du drone) — memes sources que la normale.
    att_effects = scene.effects(att_id)
    _ah_ctx = {"is_melee": False,
               "tgt_traits": frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or ()),
               "tgt_effect_names": frozenset(
                   n for n in (getattr(_e, "name", None) for _e in (scene.effects(tgt_id) or [])) if n)}
    _aura_hits = aura_additional_hits_from_allies(
        carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                   "att_faction": att_faction, "att_grand_alliance": att_grand,
                   # #202-B : traits gameconfig de l'ATTAQUANT (gate Daemon d'InfernalPacts —
                   # disjunct HasTrait(0x3fb) du trigger @180f52430).
                   "att_traits": frozenset((GC.unit(scene.vis_by_id.get(att_id)) or {}).get("traits") or ()),
                   "is_melee": False})
    _extra_groups = []
    for _g in list(additional_hit_groups(att_effects, _ah_ctx)) + _aura_hits:
        _dp2 = GC.damage_profile(_g["profile"]) or {}
        _gp = max(0, min(100, int(_dp2.get("PiercingRatio") or 0) + ctx.extra_pierce))
        _entry = {"count": _g["count"], "pierce_pct": _gp,
                  "profile_type": _PROFILE_INDEX.get(_g["profile"], 0), "mods": mods,
                  "profile_has_hits_multiple_members":
                      DamageTrait.HitsMultipleMembers.name in (_dp2.get("Traits") or [])}
        if "amount" in _g:
            _entry["amount"] = _g["amount"]
        else:
            _entry["predefined"] = MinMaxDamage(min=_g["min"], max=_g["max"])
        _extra_groups.append(_entry)
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits")))
    res = get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=attack_base, hits=hits,
        profile_type=_PROFILE_INDEX.get(prof_name, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=mods, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof_name),
        extra_groups=_extra_groups,
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof_name),  # #69 gate NoBlocking
        attacker_effects=att_effects)   # #202 : max-out evalue DANS predict_attack_raw (foyer natif)
    ev = ProbableDamageEvent(target=tgt_id, prediction=res)
    if meta:
        return ev, {"mv71": True, "tile": tile_pos, "base": attack_base, "hits": hits,
                    "pierce": pierce, "profile": prof_name}
    return ev


def make_normal_attack_predictions(scene, att_id, tgt_id, attack_pos, *, meta=False):
    """`ALoki_NormalAttackPlaybook.MakeDamagePredictions @181372730` -> `ability.PredictAttack @1811afa50` :
    base=Attack × hits + percage + armure + MODIFIER (effets attaquant + ElevationBonus + defenseur).
    Renvoie 1 `ProbableDamageEvent` (l'attaque normale n'est pas AoE) ou None. `meta=True` -> `(event,
    meta_dict)` (base/pierce/armure/hits/mods/effets — diagnostic pour le harnais de validation)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    att_effects = scene.effects(att_id)
    t_pos = scene.pos(tgt_id)
    # Selection d'arme melee<->ranged : service PARTAGE `BattleQuery.are_tiles_adjacent` (MEME que le
    # runner combat). ADJACENCE HEX, PAS Chebyshev — une unite a armes mixtes (u92 : melee 4x + ranged
    # 3x Blast) bascule melee UNIQUEMENT sur une tuile hex-adjacente ; les tuiles cheby=1 mais hex=2
    # (ex. (5,5)->(6,6)) restent ranged. `scene.board` (si fourni) = voisins natifs, sinon evenq.
    is_adjacent = are_tiles_adjacent(attack_pos, t_pos, scene.board)
    # --- #61bis tranche 3 : dispatch NormalAttackType CONCRET -> override `MV71SniperDroneSquad-
    # AttackAbility.PredictAttack @18110a5f0` (1076). Le natif dispatche par vtable (l'attaque normale
    # per-unit EST l'instance MV71 pour un porteur du passif) ; le port dispatche par kit. MELEE
    # (`IsMeleeAttack @181109960`, evaluee sur la POSITION CANDIDATE threadee par la chaine display) ->
    # delegation TOTALE a ALoki.PredictAttack AVEC les modifiers d'origine = on RESTE ici (chemin
    # arme) ; DISTANCE -> chemin drone (config du drone, degat StatAmount(caster), widget mods zeroe).
    if is_adjacent is not True:
        from engine.runner.abilities.loki.mv71 import is_mv71_normal_attacker
        if is_mv71_normal_attacker(scene.vis_by_id.get(att_id)):
            return _make_mv71_drone_predictions(scene, att_id, tgt_id, attack_pos, meta=meta)
    _dist = hexgeo.distance(attack_pos, t_pos) if (attack_pos and t_pos) else None   # porte portee ranged #188
    pierce, _ranged, whits, prof_name = _weapon_pierce(scene, att_id, is_adjacent, _dist)
    is_melee = not _ranged
    _hm = (attack_pos != scene.pos(att_id)) if attack_pos else None
    # PREDICTION (slot 0xd) — branche distincte du combat (runner). Le debuff stat-modifications
    # (CalculateModifiersFromStatModifications @181004380, prediction-only) reste GATE off : ce
    # N'EST PAS un modifier post-percage mais un effet AU NIVEAU DE LA BASE (cf. base=Initial ci-dessous).
    # BeastSlayer (target-conditionnel) : traits de la CIBLE (mirror HasTrait) -> gate BigTarget/Vehicle.
    _tgt_traits = frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or [])
    # gate ConquerorImperative (#22, self face) : la CIBLE a-t-elle l'armure REDUITE (>=1 mod <0 sur
    # ARMOR/FIXED_ARMOR) -> +extraDmg FLAT du porteur. OwnerIsCaster TRUE en display (cf. DecoysAndMisdirection).
    _tctx = scene.ctx(tgt_id)
    _tgt_armor_reduced = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                          if _tctx is not None and _tctx.stats is not None else None)
    # att_ctx POSITIONNEL (#29) : magnitude re-countee a la TUILE CANDIDATE pour les bonus dont le DSL lit
    # la UnitPosition hypothetique (LordOfTempests : Count(Ice ring-1) @180f56b40 — meme threading candidat
    # que les auras #153). tile_effects_by_pos = tileMeta FRAIS du pas (la glace s'accumule).
    _att_ctx = {"att_pos": attack_pos or scene.pos(att_id),
                "tile_effects_by_pos": scene.tile_effects_by_pos}
    mods = calculate_attacker_modifiers_for_prediction(att_effects, is_ranged=_ranged, has_moved=_hm,
                                                       target_traits=_tgt_traits,
                                                       target_armor_reduced=_tgt_armor_reduced,
                                                       att_ctx=_att_ctx)
    # #49/#153/#57a : base display re-positionnee a la tuile candidate — foyer PARTAGE `_display_
    # attack_base` (aussi consomme par le chemin drone MV71, #61bis tranche 3 : delegue b__1 = la
    # meme lecture native StatAmount(Caster, ATTACK, CURRENT)).
    attack_base, carriers, att_grand, att_faction, _ap = _display_attack_base(
        scene, att_id, attack_pos, is_melee)
    _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_pos, t_pos,
                                      damage_profile=prof_name)
    # AURA ENNEMIE %-degat projetee sur l'ATTAQUANT : ShadowInTheWarp_LessDmg_Effect (-25% Psychic aux
    # ennemis a portee du porteur) — reutilise `carriers` (toutes les autres unites vivantes), gate Psychic
    # + team ennemie + portee dans le create_aura_. Ajoute aux modifiers %-list de l'attaquant.
    for _eb in aura_attack_damage_malus_from_enemies(
            carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                       "damage_profile": prof_name}):
        add_modifier(mods, _eb)
    # AURA ALLIEE FLAT-degat projetee sur l'ATTAQUANT (canal cote SOURCE) : BeaconOfRage_FriendlyExtraDamage
    # (+50% rage aux amis Chaos adjacents en melee, #191) + ConquerorImperative (+extraDmg aux amis Mechanical
    # ring-1 vs cible a armure reduite, #23). Reutilise `carriers` (8-tuple) ; gates (is_melee/grande-alliance ;
    # Mechanical/target_armor_reduced) dans le create_aura_. Additif -> mods.additive (meme canal que le self,
    # deja bit-exact). NB : le self (le porteur attaque) et l'aura (un ami attaque) portent sur des ATTAQUANTS
    # distincts -> jamais cumules.
    _apply_ally_attack_dmg_bonus(mods, scene, att_id, _ap, is_melee, _tgt_armor_reduced, carriers,
                                 tgt_id=tgt_id, is_normal_attack=True, damage_profile=prof_name)
    # Nb de coups : cette prediction EST la facade `DamagePrediction.GetAttackHits @18102f240` — elle
    # rassemble les entrees depuis la Scene puis appelle la FORMULE PARTAGEE `attack_hits_with_modifiers`
    # (`AttackHitsWithModifiersFormula.Calculate @180f0bf50`, MEME formule que la facade combat runner) :
    # base weapon+ExtraHits+effets, +GetStuckIn/traits, +malus defenseur (LightCover/Parry) + auras (BigTarget).
    # VIVANTS SEULEMENT (#57m) : le board natif = OCCUPATION DE TUILE (`AdjacentUnits @180de8320` =
    # `Units(AdjacentTiles(.)) - .`) — les cadavres de scene.pos_by_id (decisionView les garde) n'y
    # sont plus : ni compte GetStuckIn (@180f83460), ni porteur d'aura (idiome hp>0, cf. l.227/276).
    _alive_ids = [uid for uid in scene.pos_by_id
                  if uid in (att_id, tgt_id) or (scene.hp(uid) or 0) > 0]
    board = {"att_id": att_id, "tgt_id": tgt_id, "attack_pos": attack_pos, "t_pos": t_pos,
             "tgt_team": scene.team(tgt_id), "is_melee": is_melee,
             "pos_by_id": {uid: scene.pos_by_id[uid] for uid in _alive_ids},
             "team_by_id": scene.team_by_id,
             # faction par unite — gate GetBonusHitChance de GetStuckIn (orks_adj>=2, @180f83460, #98)
             "faction_by_id": {uid: scene.faction(uid) for uid in _alive_ids}}
    tgt_effects = scene.effects(tgt_id)
    aura_sources = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                    for uid in _alive_ids if uid != tgt_id]
    # #57a : EXTRA_HITS DU PAS (scene, refresh par-pas) et non le cold ctx — les stat-mods hits
    # dynamiques (Swarm_HitReduction : -1 hit/membre perdu) sont poses APRES l'hydratation.
    _xh = scene.extra_hits_current(att_id)
    # #62 : gates/branches TUILE compute-time des malus defenseur — le natif les evalue AUSSI en
    # prediction (formule PARTAGEE @180f0bf50) : LightCover `AreEqual(coverPatch, target)` @180f556b0,
    # Camouflage branche -3 `HasTile(TilesWithTriggeredAbility(Tiles(Target), 57))` @181107180. Terrain
    # de la CIBLE (immobile : seule la tuile candidate de l'attaquant varie) via scene.board (#124),
    # mirror du call-site combat (operations/damage.py). Board KO -> None = applique-sur-presence.
    _t_terrain = scene.board.terrain_at(t_pos[0], t_pos[1]) if scene.board is not None else None
    _on_cover = (_t_terrain == LIGHT_COVER_TILE_ID) if _t_terrain is not None else None
    hits = attack_hits_with_modifiers(weapon_hits=whits,
                                      extra_hits=_xh if _xh is not None else ctx.stat(StatType.EXTRA_HITS),
                                      extra_hits_melee=ctx.extra_hits_melee,
                                      attacker_effects=att_effects, trait_objects=ctx.trait_objects(),
                                      target_effects=tgt_effects, aura_sources=aura_sources, board=board,
                                      is_melee=is_melee, damage_profile=prof_name,
                                      include_bonus_hit_behaviours=True,  # prediction folde GetStuckIn (deterministe)
                                      defender_on_cover=_on_cover,
                                      # #84 : contexte CIBLE du canal (1) -- `HasTileStatusEffect(Targets)`
                                      # @180df13f0 (status-effects DYNAMIQUES de la tuile de la cible,
                                      # tileMeta FRAIS du pas). Le second volet du gate LetTheGalaxyBurn
                                      # (`IsPersistentData`) est un flag INTRA-ATTAQUE arme au
                                      # `On(PreAttack=5)` : la PREDICTION n'execute aucun behaviour, donc
                                      # il est TOUJOURS faux ici -- ce n'est pas une omission mais le
                                      # comportement natif MESURE (#62/#65 : contribution 0 tant que la
                                      # cible n'est pas sur un hex-effect).
                                      tile_effects_by_pos=scene.tile_effects_by_pos)
    # MkXGravis (trait CIBLE 0x3f5) : l'armure est traversee 2× → hit_mult=2 dans predict_attack_raw
    # (GetBaseDamageWithFixedPiercedArmor @181030d10). No-op (=1) pour toute cible sans trait hit-twice.
    tgt_hit_mult = target_hit_multiplier(TraitFactory.create_many(_tgt_traits))
    # #179 : coups additionnels HETEROGENES (SquigHound_AdditionalHits) — degat/profil PROPRE, prev-threades
    # APRES les coups d'arme (overkill continu). Chaine native (RE) : `AActiveAbility.AddAdditionalHitsTo-
    # Prediction @180faff30` -> par coup `get_DefaultBlockScenario(result)` (prev threade) puis `GetEffect-
    # AdditionalHitPrediction @180fb1260` -> le MEME delegate PredictAttack (slot 0x26) / `PredictAttackRaw
    # @181032fb0` que les coups d'arme, avec le CONTEXTE MODIFIERS COURANT. Donc chaque groupe : `count` coups
    # [min,max] (predefined, sans spread ±20% = RandomAmount natif) au profil propre (pierce = PiercingRatio du
    # profil + extra_pierce), MEME armure/hp/bouclier/hit_mult(MkXGravis) que la cible, ET `mods` COMPLET — le
    # coup subit le meme pipeline : reductions defenseur plates (Nightshroud_DmgReduction, fusionnees dans
    # mods.additive) + %-mods/additif attaquant. Mirror `EffectAdditionalHits.Create @180f405b0`. [] hors carrier.
    # #57c-C : deux sources de groupes — (a) effets du PORTEUR (SquigHound/CordClaw/FoulInfusion,
    # triggers OwnerIsActor/OwnerIsCaster+IsMeleeAttack EVALUES : ctx is_melee threade) ; (b) effets-
    # AURA d'ALLIES adjacents (ExplosiveMaladies : adjacence re-evaluee a la TUILE CANDIDATE, mirror
    # de l'enumeration globale @180e59150 + selecteur @180f43ef0). Les groupes "amount" (ConfigVar
    # seul) prennent le spread ±20% du pipeline ; TOUS les groupes recoivent les %-mods attaquant
    # (mesure 2468 s14 : le coup ExplosiveMaladies de u89 subit bien le x1.5 CrushingStrike).
    _extra_groups = []
    # #57e : gates CIBLE des descripteurs additional-hits (ex. CyclicIonBlaster ConditionalAmount
    # HasEffect(target, Markerlight) | HasTrait(target, Mechanical)) — traits gameconfig + noms
    # d'effets ACTIFS de la cible threades dans le ctx du canal #179.
    _ah_ctx = {"is_melee": is_melee,
               "tgt_traits": frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or ()),
               "tgt_effect_names": frozenset(
                   n for n in (getattr(_e, "name", None) for _e in (scene.effects(tgt_id) or [])) if n)}
    _aura_hits = aura_additional_hits_from_allies(
        carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                   "att_faction": att_faction, "att_grand_alliance": att_grand,
                   # #202-B : traits gameconfig de l'ATTAQUANT (gate Daemon d'InfernalPacts —
                   # disjunct HasTrait(0x3fb) du trigger @180f52430).
                   "att_traits": frozenset((GC.unit(scene.vis_by_id.get(att_id)) or {}).get("traits") or ()),
                   "is_melee": is_melee})
    for _g in list(additional_hit_groups(att_effects, _ah_ctx)) + _aura_hits:
        _dp = GC.damage_profile(_g["profile"]) or {}
        _gp = max(0, min(100, int(_dp.get("PiercingRatio") or 0) + ctx.extra_pierce))
        _entry = {"count": _g["count"], "pierce_pct": _gp,
                  "profile_type": _PROFILE_INDEX.get(_g["profile"], 0), "mods": mods,
                  # #57d : le member-cap Swarm lit le profil DU COUP (param_5 d'@18102bfe0) — un coup
                  # additionnel Blast (HitsMultipleMembers) skippe le cap meme si l'arme ne le fait pas.
                  "profile_has_hits_multiple_members":
                      DamageTrait.HitsMultipleMembers.name in (_dp.get("Traits") or [])}
        if "amount" in _g:
            # #65 : PAS de troncature int — un amount midpoint (Average natif, ex. FleshmetalGuns)
            # peut valoir x.5 ; le spread Fix64 (`calculate_damage_spread` from_number) le gere exact.
            _entry["amount"] = _g["amount"]
        else:
            _entry["predefined"] = MinMaxDamage(min=_g["min"], max=_g["max"])
        _extra_groups.append(_entry)
    res = get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=attack_base, hits=hits,
        profile_type=0, pierce_pct=pierce, armor=scene.armor(tgt_id), mods=mods, hit_mult=tgt_hit_mult,
        target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id, prof_name),
        extra_groups=_extra_groups,
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id, prof_name),  # #69 gate NoBlocking
        attacker_effects=att_effects)   # #202 : max-out evalue DANS predict_attack_raw (foyer natif)
    # #57c-C : override PredictAttack des attaques normales de boss (Gulgortz/LightImUp, Ghazghkull/
    # ProperKilly) — prediction ADDITIONNELLE sur scenario VIERGE sommee via DamagePredictionResult.add
    # (@18102a710), cf. bloc _RANGED_FOLLOWUP_PASSIVES ci-dessus.
    _fw = _normal_attack_followup_prediction(scene, att_id, tgt_id, is_melee, prof_name is not None)
    if _fw is not None:
        res.add(_fw)
    ev = ProbableDamageEvent(target=tgt_id, prediction=res)
    if meta:
        _m = {"base": attack_base, "pierce": pierce, "armor": scene.armor(tgt_id), "hits": hits,
              "mods": [round(m, 3) for m, _c in mods.pct_list] or None,
              "effects": [e.name for e in att_effects] or None}
        if _fw is not None:
            _m["followup"] = {"min": _fw.raw_health_damage.min, "max": _fw.raw_health_damage.max}
        return ev, _m
    return ev
