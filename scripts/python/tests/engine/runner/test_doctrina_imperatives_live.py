"""AdMech S4a : DoctrinaImperatives (id 1118, Tan Gi'da / admecMarshall) confronte au LIVE.

RE (re-expert, build gqfc5mff6c, namespace natif "Loki") :
  - DECISION : `DoctrinaImperativesPlaybook` = NonComparablePlaybook (ctor @18112ccf0, id 0x45e=1118) ;
    `GetUseProbability @18112cbf0` = 1 (si pas utilise ce tour) sinon 0 ; utilite fixe 100 (l'IA decide
    seulement DE l'utiliser -- le toggle est deterministe, pas un choix d'IA).
  - EXECUTION `ExecuteBehaviour @1811d4d20` : `If(HasEffect(1247 Protector),
       THEN = AddEffect(1248 Conqueror) + RemoveEffect(1247),
       ELSE = AddProtector(1247)     + RemoveEffect(1248))`.
    Etat "Imperative courant" = quel des 2 effets (1247/1248) est present sur le caster (pas de composant).
  - Protector (1247) = DynamicStatModifierEffect +extraArmor sur **FixedArmor(16)** (ground-truth live tranche
    stat 16, PAS une stat 27 separee) ; `DoctrinaImperatives_SetStart` (1201, @1811d5100) pose Protector PAR
    DEFAUT au debut de bataille -> Protector = etat initial. Portee = self + amis Mechanical adjacents (incr. B).
  - Conqueror (1248) = DamageModifierAbilityEffect +extraDmg gate `HasNegativeModifier(cible, FixedArmor<0)`
    (@180f39650) ; selecteur self + Mechanical adjacents (@180f39890). extraDmg/extraArmor = config-var
    (582@lvl65, rarity-scaled).

CE TEST fait DEUX choses :
  1. ORACLE LIVE (runnable maintenant, RE-independant) : caste 1118 et confirme le TOGGLE observable natif
     (Protector initial -> Conqueror apres 1 cast), + DUMPE la ground-truth (quelle stat porte le +extraArmor,
     portee sur Mechanical adjacent) dans un fichier scratchpad pour trancher les 3 points ouverts du validator.
  2. SCAFFOLD offline-agreement (a completer au port S4a) : `load_state` + behaviour porte + assert
     effets offline == live.

DRIVE POSITIONS (doctrine) : allie Mechanical repositionne adjacent a Tan Gi'da pour mesurer la portee de
l'aura. Board+stats REELS, seules les positions controlees. ASCII only. Skip propre si geometrie/tour KO.
"""
from __future__ import annotations

import json
import os
import pytest

TAN_VIS = "admecMarshall"        # Tan Gi'da
ALLY_VIS = "admecRuststalker"    # Exitor-Rho : Mechanical (cible de l'aura self+adjacent)
ABILITY = 1118                   # DoctrinaImperatives
PROTECTOR = 1247                 # ProtectorImperative (+extraArmor)
CONQUEROR = 1248                 # ConquerorImperative (+extraDmg vs reduced Armour)
BUILD = ["--roster", "1", "--p-units", f"{TAN_VIS},{ALLY_VIS}",
         "--a-units", "necroWarden,necroWarden"]

_DUMP = os.path.join(
    os.environ.get("TEMP", "/tmp"), "doctrina_imperatives_groundtruth.json")


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _effect_ids(u):
    """Set des effectType actifs d'une unite de decisionView."""
    return {e.get("effectType") for e in (u.get("effects") or [])}


def _find(dec, vis, alive=True):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and (u.get("alive") or not alive)), None)


def _advance_to_my_turn(rpc, rid, vis, max_iter=20):
    """Avance jusqu'a ce que ce soit le tour du proprietaire de `vis`. Renvoie (dec, unit) ou (None, None)."""
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if not _ok(dec):
            return None, None
        u = _find(dec, vis)
        if u is None:
            return dec, None
        if dec.get("currentPlayer") == u.get("owner"):
            return dec, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": False}, 60)
    return None, None


def _dump(payload):
    with open(_DUMP, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=1)


def test_doctrina_imperatives_toggle_live(live_session, rpc, build_runner):
    """ORACLE LIVE : (a) Protector (1247) present AVANT tout cast (SetStart 1201) ;
    (b) caster 1118 bascule -> Conqueror (1248) present + Protector (1247) retire (toggle @1811d4d20).
    DUMPE la ground-truth (stats/effets self+allie pre/post) pour trancher stat-27 + portee de l'aura."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    ally = _find(dec, ALLY_VIS)

    eff_pre = _effect_ids(tan)

    # capture full ground-truth AVANT cast (self + allie) pour extraction offline.
    gt = {"note": "DoctrinaImperatives ground-truth (RE cross-check + validator open points)",
          "tan_id": tan_id, "ally_id": (ally or {}).get("id"),
          "pre": {"tan": tan, "ally": ally}}

    # cast LIVE (self-cast : targetId = caster).
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": tan_id, "targetId": tan_id, "abilityType": ABILITY},
        "captureEvents": True}, 90)

    dec2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    tan2 = _find(dec2, TAN_VIS)
    ally2 = _find(dec2, ALLY_VIS)
    eff_post = _effect_ids(tan2) if tan2 else set()
    gt["cast_result_ok"] = _ok(res)
    gt["post"] = {"tan": tan2, "ally": ally2}
    gt["effects"] = {"tan_pre": sorted(x for x in eff_pre if x is not None),
                     "tan_post": sorted(x for x in eff_post if x is not None)}
    _dump(gt)

    # --- invariant ROBUSTE : le toggle natif ---
    # (a) etat initial = Protector (SetStart). decisionView.effects peut ne pas exposer 1247 -> soft.
    if PROTECTOR not in eff_pre:
        print(f"[DoctrinaImp] NOTE : Protector(1247) non expose pre-cast (eff_pre={sorted(x for x in eff_pre if x)})")
    # (b) apres 1 cast : Conqueror present, Protector absent (toggle) -- l'assertion dure.
    if not gt["cast_result_ok"]:
        pytest.skip(f"cast 1118 non applique (gate/tour) : {str(res)[:200]}")
    assert CONQUEROR in eff_post, \
        f"apres cast, Conqueror(1248) absent (toggle KO). eff_post={sorted(x for x in eff_post if x)}"
    assert PROTECTOR not in eff_post, \
        f"apres cast, Protector(1247) toujours present (RemoveEffect KO). eff_post={sorted(x for x in eff_post if x)}"
    print(f"[DoctrinaImp] TOGGLE OK : pre={sorted(x for x in eff_pre if x)} -> "
          f"post={sorted(x for x in eff_post if x)} ; ground-truth -> {_DUMP}")


def test_doctrina_protector_aura_live(live_session, rpc, build_runner):
    """GROUND-TRUTH Protector : au debut de bataille (SetStart pose Protector 1247), mesure via
    `statModSources` QUELLE stat porte le +extraArmor sur Tan Gi'da (tranche stat 0x1b=27 vs FixedArmor 16)
    et SI l'aura atteint un allie Mechanical ADJACENT (tranche la portee self-only vs self+adjacent -- point
    #1 du validator). DUMP les mods par-source (soft asserts : geometrie de deploiement non garantie)."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    ally = _find(dec, ALLY_VIS)
    ally_id = (ally or {}).get("id")
    # Protector doit etre actif (SetStart) AVANT tout cast.
    if PROTECTOR not in _effect_ids(tan):
        pytest.skip(f"Protector(1247) non actif pre-cast (effets={sorted(x for x in _effect_ids(tan) if x)})")

    sm_tan = rpc("statModSources", {"runnerId": rid, "unitId": tan_id, "minAbs": 1}, 90)
    sm_ally = rpc("statModSources", {"runnerId": rid, "unitId": ally_id, "minAbs": 1}, 90) if ally_id else None

    def _fixed_armor_mod(sm):
        """(total, source_effect_id) du mod POSITIF de FixedArmor attribue a UNE entite-effet (sourceIsUnit=
        false, residual 0). L'aura Protector est keyee par l'ENTITE-EFFET (pas l'unite porteuse) -- cf.
        statModSources aura blind-spot. Renvoie (0, None) si pas de mod FixedArmor positif effet-source."""
        for uu in (sm.get("units") or []) if isinstance(sm, dict) else []:
            fa = (uu.get("mods") or {}).get("fixedArmor")
            if not fa:
                continue
            src = [s for s in (fa.get("bySource") or [])
                   if not s.get("sourceIsUnit") and (s.get("amount") or 0) > 0]
            if src and (fa.get("total") or 0) > 0:
                best = max(src, key=lambda s: s.get("amount") or 0)
                return int(fa["total"]), best.get("source")
        return 0, None

    tan_pos = tan.get("pos"); ally_pos = (ally or {}).get("pos")
    adj = None
    if tan_pos and ally_pos:
        import hexgeo
        try:
            adj = hexgeo.distance((tan_pos["col"], tan_pos["row"]), (ally_pos["col"], ally_pos["row"])) == 1
        except Exception:
            adj = None

    tan_fa, tan_src = _fixed_armor_mod(sm_tan)
    ally_fa, ally_src = _fixed_armor_mod(sm_ally) if sm_ally else (0, None)
    dump = {"tan_id": tan_id, "ally_id": ally_id, "tan_pos": tan_pos, "ally_pos": ally_pos,
            "ally_adjacent": adj, "tan_fixedArmor_mod": [tan_fa, tan_src],
            "ally_fixedArmor_mod": [ally_fa, ally_src], "sm_tan": sm_tan, "sm_ally": sm_ally}
    with open(os.path.join(os.environ.get("TEMP", "/tmp"),
                           "doctrina_protector_aura.json"), "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=True, indent=1)
    print(f"[Protector aura] tan FixedArmor +{tan_fa} (src effect {tan_src}) ; "
          f"ally +{ally_fa} (src {ally_src}) adjacent={adj} -> dump doctrina_protector_aura.json")

    # INVARIANT 1 (stat, point #2) : Protector = mod POSITIF de FixedArmor(16) sur Tan Gi'da, attribue a
    # l'entite-effet (residual 0). Prouve que le +extraArmor tombe sur FixedArmor (pas une stat 27 separee).
    assert tan_fa > 0 and tan_src is not None, \
        f"Protector n'ajoute pas de FixedArmor positif effet-source sur Tan Gi'da (sm={sm_tan})"

    # INVARIANT 2 (portee, point #1) : l'aura atteint l'allie Mechanical ADJACENT -- meme montant, meme
    # entite-effet source que sur Tan Gi'da. Skip si le deploiement ne l'a pas mis adjacent (geometrie).
    if not (ally_id and adj):
        pytest.skip(f"allie Mechanical non adjacent au deploiement (adjacent={adj}) -> portee non mesurable")
    assert ally_fa == tan_fa and ally_src == tan_src, \
        (f"aura Protector n'atteint PAS l'allie Mechanical adjacent a l'identique : "
         f"ally +{ally_fa} (src {ally_src}) != tan +{tan_fa} (src {tan_src})")


def test_doctrina_imperatives_offline_agreement(live_session, rpc, build_runner):
    """OFFLINE-AGREEMENT (port S4a incr. A) : reconstruit l'etat pre-cast (Tan Gi'da a Protector via SetStart)
    et confronte le behaviour porte `DoctrinaImperativesAbility.execute_behaviour` au LIVE :
      (1) TOGGLE : offline 1 cast -> Conqueror(1248) present + Protector(1247) retire == resultat LIVE ;
      (2) Protector +FixedArmor : un Protector FRAICHEMENT pose offline (toggle #2 Conqueror->Protector)
          materialise un +FixedArmor == le +armor LIVE de Protector (statModSources, oracle = moteur natif) ;
      (3) le montant offline == `ability_var("DoctrinaImperatives","extraArmor", level, mult)` (self-consistance).
    """
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.abilities.loki import DoctrinaImperativesAbility

    rid = build_runner("777", extra=BUILD)["rid"]
    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    if PROTECTOR not in _effect_ids(tan):
        pytest.skip("Protector(1247) non actif pre-cast (SetStart) -> agreement toggle non amorcable")

    # --- capture etat pre-cast + le +armor LIVE de Protector (oracle natif) ---
    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    sm = rpc("statModSources", {"runnerId": rid, "unitId": tan_id, "minAbs": 1}, 90)
    live_armor = 0
    for uu in (sm.get("units") or []) if isinstance(sm, dict) else []:
        fa = (uu.get("mods") or {}).get("fixedArmor")
        if fa and (fa.get("total") or 0) > 0:
            live_armor = int(fa["total"])

    # --- LIVE cast -> toggle Protector->Conqueror ---
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": tan_id, "targetId": tan_id, "abilityType": ABILITY}}, 90)
    dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    tan1 = _find(dec1, TAN_VIS)
    live_post = _effect_ids(tan1) if tan1 else set()

    # --- OFFLINE : load pre-cast + toggle porte ---
    state = load_state(dec0, ob0, snap0)
    ent = state.get_entity(tan_id)
    if ent is None or ent.get_component(StatsComponent) is None or state.effects is None:
        pytest.skip("Tan Gi'da sans StatsComponent/effects offline (snapshot incomplet)")

    # (1) TOGGLE offline #1 : Protector present -> Conqueror + retrait Protector.
    DoctrinaImperativesAbility().execute_behaviour(state, tan_id, tan_id)
    off_has_conq = state.effects.has_effect(tan_id, effect_type=CONQUEROR)
    off_has_prot = state.effects.has_effect(tan_id, effect_type=PROTECTOR)
    assert off_has_conq and not off_has_prot, \
        f"toggle offline #1 KO : Conqueror={off_has_conq} Protector={off_has_prot}"
    # agreement direction avec le LIVE (le cast live a bascule vers Conqueror).
    assert (CONQUEROR in live_post) == off_has_conq, \
        f"toggle offline (Conqueror={off_has_conq}) != live (post={sorted(x for x in live_post if x)})"

    # (2)+(3) Protector +FixedArmor : delta d'un Protector FRAICHEMENT pose (toggle #2 Conqueror->Protector).
    ctx = ent.get_component(StatsComponent).ctx
    before = int(ctx.stat(StatType.FIXED_ARMOR) or 0)
    DoctrinaImperativesAbility().execute_behaviour(state, tan_id, tan_id)   # #2 : re-pose Protector (fresh)
    assert state.effects.has_effect(tan_id, effect_type=PROTECTOR), "toggle #2 n'a pas re-pose Protector"
    after = int(ctx.stat(StatType.FIXED_ARMOR) or 0)
    delta = after - before

    lvl = getattr(ctx, "active_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    oracle = int(ability_var("DoctrinaImperatives", "extraArmor", lvl, multiplier_pct=mult) or 0)
    print(f"[DoctrinaImp offline] toggle #1 -> Conqueror OK ; Protector +FixedArmor delta={delta} "
          f"; oracle ability_var={oracle} ; live statModSources={live_armor}")
    assert oracle > 0, f"extraArmor non resoluble offline (level={lvl}, mult={mult})"
    assert delta == oracle, f"Protector fresh-add FixedArmor delta={delta} != oracle extraArmor {oracle}"
    if live_armor > 0:
        assert delta == live_armor, \
            f"Protector +FixedArmor offline {delta} != +armor LIVE (statModSources) {live_armor}"


def test_doctrina_protector_aura_offline_agreement(live_session, rpc, build_runner):
    """OFFLINE-AGREEMENT (port S4a incr. B) : le canal aura +FixedArmor (`defender_fixed_armor`, FOYER partage
    de resolution armure defenseur) projette le +extraArmor de Protector sur un allie Mechanical ADJACENT a
    Tan Gi'da, a l'identique du LIVE ; le porteur (self) est deja couvert par le stat-mod EAGER (GetStat) =>
    l'aura NE double PAS (auto-exclusion def==owner). DRIVE la position de l'allie offline (adjacent vs eloigne)
    pour mesurer la portee sans dependre de la geometrie de deploiement (doctrine drive-positions)."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, PositionComponent
    from engine.entities.stats import StatType
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.damage_model import defender_fixed_armor
    import hexgeo

    rid = build_runner("777", extra=BUILD)["rid"]
    dec, tan = _advance_to_my_turn(rpc, rid, TAN_VIS)
    if tan is None:
        pytest.skip("Tan Gi'da absent / pas atteint son tour")
    tan_id = tan["id"]
    ally = _find(dec, ALLY_VIS)
    ally_id = (ally or {}).get("id")
    if ally_id is None:
        pytest.skip("allie Mechanical (admecRuststalker) absent")
    if PROTECTOR not in _effect_ids(tan):
        pytest.skip("Protector(1247) non actif pre-cast (SetStart) -> portee non amorcable")

    dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    # +armor LIVE de l'allie (oracle natif) -- la portee live est deja validee par test_doctrina_protector_aura_live ;
    # ici on confronte le MONTANT reproduit OFFLINE. 0 si l'allie n'est pas adjacent au deploiement (aura absente live).
    sm_ally = rpc("statModSources", {"runnerId": rid, "unitId": ally_id, "minAbs": 1}, 90)
    live_ally_armor = 0
    for uu in (sm_ally.get("units") or []) if isinstance(sm_ally, dict) else []:
        fa = (uu.get("mods") or {}).get("fixedArmor")
        if fa and (fa.get("total") or 0) > 0:
            live_ally_armor = int(fa["total"])

    state = load_state(dec0, ob0, snap0)
    tan_ent = state.get_entity(tan_id)
    ally_ent = state.get_entity(ally_id)
    if tan_ent is None or ally_ent is None:
        pytest.skip("entites offline incompletes (snapshot)")
    tpc = tan_ent.get_component(PositionComponent)
    apc = ally_ent.get_component(PositionComponent)
    asc = ally_ent.get_component(StatsComponent)
    tsc = tan_ent.get_component(StatsComponent)
    if tpc is None or apc is None or asc is None or tsc is None or state.effects is None:
        pytest.skip("composants position/stats/effects offline manquants")

    # oracle extraArmor = niveau/mult de Tan Gi'da (SOURCE de l'aura), meme var que le self.
    tctx = tsc.ctx
    lvl = getattr(tctx, "active_ability_level", None)
    mult = int(getattr(tctx, "ability_variables_multiplier", 100) or 100)
    extra = int(ability_var("DoctrinaImperatives", "extraArmor", lvl, multiplier_pct=mult) or 0)
    assert extra > 0, f"extraArmor non resoluble offline (level={lvl}, mult={mult})"

    ally_base = int(asc.ctx.stat(StatType.FIXED_ARMOR) or 0)

    # DRIVE : allie ELOIGNE (>1) -> aura ABSENTE (base seule).
    apc.col, apc.row = tpc.col + 4, tpc.row + 4
    far = defender_fixed_armor(state, ally_id)
    assert far == ally_base, f"aura appliquee hors-portee : far={far} != base allie {ally_base}"

    # DRIVE : allie ADJACENT (ring-1, parite hexgeo) -> +extraArmor.
    adj_col, adj_row = hexgeo.neighbors(tpc.col, tpc.row)[0]
    apc.col, apc.row = adj_col, adj_row
    assert hexgeo.distance((tpc.col, tpc.row), (apc.col, apc.row)) == 1, "drive adjacency KO (parite hexgeo)"
    near = defender_fixed_armor(state, ally_id)
    print(f"[Protector aura offline] allie base={ally_base} adjacent={near} (+{near - ally_base}) ; "
          f"oracle extraArmor={extra} ; live_ally=+{live_ally_armor}")
    assert near == ally_base + extra, \
        f"aura offline allie Mechanical adjacent {near} != base {ally_base} + extraArmor {extra}"
    if live_ally_armor > 0:
        assert near - ally_base == live_ally_armor, \
            f"aura offline (+{near - ally_base}) != +armor LIVE allie (statModSources +{live_ally_armor})"

    # SELF (Tan Gi'da) : deja couvert par le stat-mod EAGER (GetStat) -> defender_fixed_armor(self) == GetStat
    # (l'aura s'auto-exclut def==owner : PAS de double-compte).
    tan_get = int(tctx.stat(StatType.FIXED_ARMOR) or 0)
    tan_resolved = defender_fixed_armor(state, tan_id)
    assert tan_resolved == tan_get, \
        f"self double-compte : defender_fixed_armor(tan)={tan_resolved} != GetStat(16) {tan_get}"
