"""#204 -- `MasterAnnihilator_AdditionalHitEffect` (1249) et `AstartesBanner_AdditionalHitsEffect`
(1106) : leur coup surnumeraire est un GROUPE DU CANAL #179, pas un coup d'ARME de plus.

Meme fork de port que `LetTheGalaxyBurnEffect` (#227) : l'artefact natif est
`<Effect>$$CreateAdditionalHits` -> `IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`, PAS
`CreateEffectHitsBonusForAttack`. Descripteurs lus verbatim (build gqfc5mff6c) :

  `IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits`
      condition = get_OwnerIsTarget & !AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)
      roll = display = FirstHitInCurrentAttackDamageRange ; profil = -1 (NULL)
      count = ConfigConst(0x2f = nrOfHits)   ; cap = ConfigVar(0xd = maxDmg)
  `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits`
      condition = get_OwnerIsCaster & IsMeleeAttack        (selecteur SurroundingFriends, rayon 2)
      roll = display = FirstHitInCurrentAttackDamageRange ; profil = -1 (NULL)
      count = ConfigConst(0x64 = extraHits)  ; cap = ConfigVar(0xd = maxDmg)

`FirstHitInCurrentAttackDamageRange` rend le `IdunBattle.Core.HitDamage` de l'AttackData de l'attaque
COURANTE ; sur une attaque NORMALE il est DEGENERE, donc `IdunBattle.Core.HitDamage$$GetDamage`
court-circuite (gate `min == max`) et la valeur du coup est une CONSTANTE (= base reduite). Les coups
d'ARME de la MEME attaque, eux, sont TIRES : c'est le contrefactuel qui refute le modele
« +1 coup d'ARME ».

Ce que ces tests PROUVENT, en confrontant le LIVE (aucune constante de degat en dur -- tout est
MESURE sur la session, les assertions portent sur des RELATIONS) :
  (1) LIVE, les deux porteurs : sur les attaques ou le bonus mord, le DERNIER evenement de degat est
      CONSTANT alors que les coups d'ARME de la meme campagne prennent >= 2 valeurs distinctes ; et
      cette constante vaut la stat ATTACK de l'ATTAQUANT (armure de la cible mise a 0 par
      `--hp-target`), pas une valeur du descripteur ni un tirage.
  (2) LIVE, le contrefactuel de GEOMETRIE / de POSE : hors rayon 2 (AstartesBanner) ou avant la pose
      du marqueur (MasterAnnihilator), l'attaque ne rend que ses coups d'arme.
  (3) OFFLINE, le CONTRAT DU CANAL : `attack_hits_with_modifiers` (facade
      `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`) ne bouge PLUS, et
      `create_aura_additional_hits_for_ally` rend le groupe attendu -- rien quand
      `attack_hit_damage` est absent (= face PREDICTION, hors `OngoingAttack`), rien hors gate.

Drive les positions (memoire « drive positions, don't blame geometry »). ASCII-only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatType
from engine.runner.snapshot import load_state
from engine.runner.components import UnitComponent, PositionComponent, StatsComponent

ATTACKER = "ultraApothecary"       # temoin : 1 SEUL coup melee, `mech: {}` -> lecture immediate
TARGET = "bloodSanguinary"
HP = "900000"                      # + met Armor/FixedArmor de la cible a 0 -> reduce(base) == base
BANNER = "templAncient"            # porteur AstartesBanner (passif), rayon 2
MARKER = "admecDominus"            # Vitruvius : POSE le marqueur 1249 sur sa cible d'attaque normale
MARK_NAME = "MasterAnnihilator_extraHit"
ROUNDS = 9
NEAR_FROM = 3                      # les 3 premiers tours = phase NUE (contrefactuel)


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _amounts(res, tid, ability_id):
    out = []
    for a in (res.get("actions") or []) if isinstance(res, dict) else []:
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == ability_id:
                out.append(int(td["Amount"]))
    return out


def _campaign(rpc, rid, board, carrier_vis, radius):
    """Fait attaquer l'ATTAQUANT temoin `ROUNDS` fois ; ARME le bonus a partir de `NEAR_FROM`.

    `radius` != None -> montage AstartesBanner : on RAPPROCHE (puis on avait ELOIGNE) le porteur.
    `radius` is None -> montage MasterAnnihilator : le poseur attaque la MEME cible juste avant.
    Rend [(armed, [montants])]."""
    def dview():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    dv = dview()
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    att = next((u for u in units if u.get("visualId") == ATTACKER), None)
    car = next((u for u in units if u.get("visualId") == carrier_vis), None)
    en = next((u for u in units if u.get("visualId") == TARGET), None)
    if att is None or car is None or en is None:
        pytest.skip(f"montage incomplet: {[u.get('visualId') for u in units]}")
    myp, aid, cid, tid = att.get("owner"), att["id"], car["id"], en["id"]
    a_norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    c_norm = next((a for a in (car.get("abilities") or []) if a.get("kind") == "normal"), None)
    if a_norm is None:
        pytest.skip("pas d'attaque normale sur l'attaquant temoin")
    walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    rows = []
    for rnd in range(ROUNDS):
        for _ in range(6):
            dv = dview()
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        else:
            break
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        att = next((u for u in units if u.get("id") == aid), None)
        car = next((u for u in units if u.get("id") == cid), None)
        en = next((u for u in units if u.get("id") == tid), None)
        if att is None or car is None or en is None:
            break
        T = _upos(en)
        occ = {_upos(u) for u in units if _upos(u) is not None}
        free_adj = [c for c in walk if T is not None and hexgeo.distance(c, T) == 1
                    and (c not in occ or c == _upos(att))]
        if not T or not free_adj:
            break
        A = _upos(att) if _upos(att) in free_adj else free_adj[0]
        want = rnd >= NEAR_FROM

        if radius is not None:                                    # AstartesBanner : GEOMETRIE
            cand = [c for c in walk if c not in occ and c != A
                    and ((hexgeo.distance(c, A) <= radius) if want
                         else (hexgeo.distance(c, A) > radius))]
            cand.sort(key=lambda c: hexgeo.distance(c, _upos(car)))
            if cand and _upos(car) != cand[0]:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cid, "to": {"col": cand[0][0], "row": cand[0][1]}}}, 40)
        if _upos(att) != A:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": aid, "to": {"col": A[0], "row": A[1]}}}, 40)
        if radius is None and want and c_norm is not None:        # MasterAnnihilator : POSE
            car2 = next((u for u in (dview().get("units") or []) if u.get("id") == cid), None)
            cadj = [c for c in walk if hexgeo.distance(c, T) == 1 and c != A
                    and (c not in occ or c == _upos(car2))]
            if car2 is not None and _upos(car2) not in cadj and cadj:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cid, "to": {"col": cadj[0][0], "row": cadj[0][1]}}}, 40)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cid, "targetId": tid,
                "abilityType": c_norm["id"]}}, 60)

        dv2 = dview()                                             # etat REEL au moment de l'attaque
        u2 = {u["id"]: u for u in (dv2.get("units") or []) if u.get("alive")}
        if aid not in u2 or tid not in u2:
            break
        if radius is not None:
            armed = cid in u2 and _upos(u2[cid]) is not None \
                and hexgeo.distance(_upos(u2[cid]), _upos(u2[aid])) <= radius
        else:
            armed = any((e.get("name") or "") == MARK_NAME for e in (u2[tid].get("effects") or []))
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid,
            "abilityType": a_norm["id"]}}, 60)
        am = _amounts(res, tid, a_norm["id"])
        if am:
            rows.append((bool(armed), am))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return rows


def _attacker_attack_stat(rpc, rid, board):
    """Stat ATTACK de l'attaquant temoin, LUE sur l'etat live charge offline."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    st = load_state(dv, ob, snap, board=board)
    for _uid, e in st.entities.items():
        uc, sc = e.get_component(UnitComponent), e.get_component(StatsComponent)
        if uc is not None and sc is not None and uc.visual_id == ATTACKER:
            return int(sc.ctx.stat(StatType.ATTACK)), st
    return None, st


def _assert_constant_group_hit(rows, atk, label):
    """L'assertion COMMUNE aux deux porteurs : sur les attaques armees, le dernier evenement est
    UNE constante egale a la stat ATTACK, quand les coups d'ARME varient."""
    armed = [a for f, a in rows if f]
    plain = [a for f, a in rows if not f]
    print(f"\n[{label}] n={len(rows)} armees={len(armed)} nues={len(plain)} ATTACK={atk}")
    for f, a in rows:
        print(f"  {'ARMED' if f else 'nue  '} n={len(a)} {a}")
    if len(armed) < 2 or not plain:
        pytest.skip(f"[{label}] pas assez d'attaques exploitables "
                    f"(armees={len(armed)}, nues={len(plain)})")
    base = min(len(a) for a in plain)
    assert {len(a) for a in plain} == {base}, \
        f"[{label}] phase NUE non homogene: {sorted({len(a) for a in plain})}"
    assert {len(a) for a in armed} == {base + 1}, \
        (f"[{label}] le bonus n'ajoute pas exactement 1 evenement (count = ConfigConst) : "
         f"nue={base}, armees={sorted({len(a) for a in armed})}")
    lasts = [a[base] for a in armed]
    weapon = sorted({v for a in armed for v in a[:base]} | {v for a in plain for v in a})
    assert len(set(lasts)) == 1, \
        (f"[{label}] le coup surnumeraire live VARIE {sorted(set(lasts))} -> il serait TIRE ; le "
         f"natif rend une CONSTANTE (HitDamage degenere de l'attaque normale)")
    assert len(weapon) > 1, \
        f"[{label}] coups d'arme tous identiques -> le contrefactuel n'est pas discriminant"
    assert lasts[0] == atk, \
        (f"[{label}] la constante live vaut {lasts[0]} != stat ATTACK {atk} -> le coup ne sort pas "
         f"de `FirstHitInCurrentAttackDamageRange` (HitDamage de l'attaque, armure cible = 0)")
    assert min(weapon) < atk < max(weapon), \
        (f"[{label}] la constante {atk} n'est pas INTERIEURE a la dispersion des coups d'arme "
         f"[{min(weapon)}..{max(weapon)}] -> le contrefactuel « +1 coup d'ARME » ne serait pas refute")


# ------------------------------------------------------------------ (1)+(2) LIVE, les deux porteurs

@pytest.fixture(scope="module")
def banner_runner(rpc, build_runner):
    rid = build_runner("204101", extra=[
        "--p-units", f"{BANNER},{ATTACKER}", "--a-units", TARGET,
        "--hp-target", HP, "--hp-player", HP, "--crit", "0,0", "--block-target", "0,0"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="native_sym")}


@pytest.fixture(scope="module")
def marker_runner(rpc, build_runner):
    rid = build_runner("204102", extra=[
        "--p-units", f"{MARKER},{ATTACKER}", "--a-units", TARGET,
        "--hp-target", HP, "--hp-player", HP, "--crit", "0,0", "--block-target", "0,0"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="native_sym")}


def test_astartes_banner_extra_hit_is_a_constant_group_hit(rpc, banner_runner):
    """AstartesBanner : porteur DANS le rayon 2 -> +1 evenement, CONSTANT et egal a la stat ATTACK
    de l'attaquant. Contrefactuel de GEOMETRIE : porteur au-dela du rayon -> rien."""
    rid, board = banner_runner["rid"], banner_runner["board"]
    atk, _st = _attacker_attack_stat(rpc, rid, board)
    if atk is None:
        pytest.skip("attaquant temoin absent de l'etat charge")
    rows = _campaign(rpc, rid, board, BANNER, radius=2)
    _assert_constant_group_hit(rows, atk, "AstartesBanner")


def test_master_annihilator_extra_hit_is_a_constant_group_hit(rpc, marker_runner):
    """MasterAnnihilator : marqueur 1249 pose sur la cible -> +nrOfHits evenement(s), CONSTANT(s) et
    egaux a la stat ATTACK de l'attaquant. Contrefactuel de POSE : avant la premiere attaque normale
    de Vitruvius, la cible n'est pas marquee -> rien."""
    rid, board = marker_runner["rid"], marker_runner["board"]
    atk, _st = _attacker_attack_stat(rpc, rid, board)
    if atk is None:
        pytest.skip("attaquant temoin absent de l'etat charge")
    rows = _campaign(rpc, rid, board, MARKER, radius=None)
    _assert_constant_group_hit(rows, atk, "MasterAnnihilator")


# ------------------------------------------------------------------ (3) CONTRAT DU CANAL (offline)

def test_both_descriptors_are_channel_179_groups_not_hits_bonuses(rpc, banner_runner):
    """CONTRAT, les deux faces.

    (a) `attack_hits_with_modifiers` ne doit RIEN ajouter : ni pour le porteur AstartesBanner dans
        le rayon (l'aura a quitte la formule de coups), ni pour la cible marquee 1249.
    (b) `create_aura_additional_hits_for_ally` rend le groupe attendu, et RIEN quand
        `attack_hit_damage` est absent (face PREDICTION : `IdunBattle.Entities.Abilities.
        AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction` tourne hors `OngoingAttack` ->
        `FirstHitInCurrentAttackDamageRange` rend 0), ni hors gate (geometrie / `OwnerIsTarget` /
        `IsMeleeAttack` / profil Psychic)."""
    from engine.entities.effects.loki.hits import (AstartesBannerExtraHitEffect,
                                                   MasterAnnihilatorAdditionalHitEffect)
    from engine.entities.effects.magnitude import ability_var
    from engine.services.attack_hits_formula import attack_hits_with_modifiers
    from engine.runner.damage_model import build_hits_board, select_weapon_pierce

    rid, board = banner_runner["rid"], banner_runner["board"]
    atk, st = _attacker_attack_stat(rpc, rid, board)
    if atk is None:
        pytest.skip("attaquant temoin absent de l'etat charge")

    def by_vis(v):
        return next((u for u, e in st.entities.items()
                     if e.get_component(UnitComponent) is not None
                     and e.get_component(UnitComponent).visual_id == v), None)
    aid, cid, tid = by_vis(ATTACKER), by_vis(BANNER), by_vis(TARGET)
    if aid is None or cid is None or tid is None:
        pytest.skip("montage offline incomplet")

    # --- DRIVE : attaquant colle a la cible, porteur a distance 1 de l'attaquant (dans le rayon) ---
    tp = st.entities[tid].get_component(PositionComponent)
    nb = [board.coord(t) for t in board.neighbours(board.id_at(tp.col, tp.row))
          if board.walkable(t)]
    assert len(nb) >= 2, "board sans deux voisins marchables autour de la cible"
    ap = st.entities[aid].get_component(PositionComponent)
    ap.col, ap.row = nb[0]
    cp = st.entities[cid].get_component(PositionComponent)
    cp.col, cp.row = nb[1]
    a_pos, t_pos = (ap.col, ap.row), (tp.col, tp.row)

    banner = next((e for e in st.effects.active_effects(cid, {"hp": None})
                   if isinstance(e, AstartesBannerExtraHitEffect)), None)
    if banner is None:
        pytest.skip(f"{BANNER} ne porte pas AstartesBanner_ExtraHit dans l'etat charge")
    mark = MasterAnnihilatorAdditionalHitEffect(name=MARK_NAME, effect_type=1249)

    # --- (a) la FORMULE DE COUPS ne bouge plus ---
    sc = st.entities[aid].get_component(StatsComponent)
    _p, _r, whits = select_weapon_pierce(sc.ctx, 1)
    hb, auras, tgt_eff = build_hits_board(st, aid, tid, a_pos, t_pos, is_melee=True)
    hits = attack_hits_with_modifiers(
        weapon_hits=whits, extra_hits=sc.ctx.stat(StatType.EXTRA_HITS),
        extra_hits_melee=sc.ctx.extra_hits_melee,
        attacker_effects=st.effects.active_effects(aid, {"hp": None}),
        trait_objects=sc.ctx.trait_objects(),
        target_effects=list(tgt_eff) + [mark], aura_sources=auras, board=hb,
        is_melee=True, damage_profile="Piercing", include_bonus_hit_behaviours=True)
    expected = whits + sc.ctx.stat(StatType.EXTRA_HITS) + sc.ctx.extra_hits_melee
    print(f"\n[canal #204] formule={hits} (attendu {expected}) ATTACK={atk}")
    assert hits == expected, \
        (f"la formule de coups rend {hits} != base d'arme {expected} -> un terme AstartesBanner ou "
         f"MasterAnnihilator y subsiste (les deux doivent vivre dans le canal #179)")

    # --- (a-bis) #10019 : la MEME formule, face PREDICTION, DOIT bouger -- et d'exactement `n_mark`
    #
    # Ce cliquet gardait un contrat formule sans FACE, alors que l'appel ci-dessus est monte en
    # regime COMBAT (`build_hits_board`, ECS) tout en passant `include_bonus_hit_behaviours=True`.
    # Laisse tel quel apres #10019 il serait devenu VACANT sur la face prediction : vert quel que
    # soit ce que le port y fait. Les deux faces sont donc gardees ICI, cote a cote, parce qu'elles
    # ne rendent PAS la meme chose et que les deux rendus sont MESURES --
    #   * COMBAT (#204)     : evenement CONSTANT (stat ATTACK a l'unite, 4617 sur 5/5) => GROUPE,
    #                         la formule ne compte RIEN  (assertion ci-dessus) ;
    #   * PREDICTION (#10019) : un coup de plus au degat EXACT d'un coup d'arme (trois paires vers
    #                         la meme cible, six nombres, rapports entiers `(h+1)/h` sur les DEUX
    #                         bornes) => la formule compte `nrOfHits`.
    # Un correctif qui ferait bouger la premiere, ou qui laisserait la seconde immobile, rougit.
    n_mark_face = int(ability_var("MasterAnnihilator", "nrOfHits", is_constant=True) or 0)
    assert n_mark_face > 0, "ConfigConst 0x2f introuvable -- l'assertion de face serait VACANTE"
    hits_pred = attack_hits_with_modifiers(
        weapon_hits=whits, extra_hits=sc.ctx.stat(StatType.EXTRA_HITS),
        extra_hits_melee=sc.ctx.extra_hits_melee,
        attacker_effects=st.effects.active_effects(aid, {"hp": None}),
        trait_objects=sc.ctx.trait_objects(),
        target_effects=list(tgt_eff) + [mark], aura_sources=auras, board=hb,
        is_melee=True, damage_profile="Piercing", include_bonus_hit_behaviours=True,
        is_prediction=True)
    print(f"[#10019] formule PREDICTION={hits_pred} (attendu {hits + n_mark_face})")
    assert hits_pred == hits + n_mark_face, (
        f"face PREDICTION : la formule rend {hits_pred}, attendu {hits + n_mark_face} "
        f"(= COMBAT {hits} + nrOfHits {n_mark_face}). Le natif predit un coup de plus des que la "
        f"cible porte la marque 1249 ; sans lui l'IA DECIDE sur un compte trop bas.")
    # TEMOIN de la meme face : sans la marque, la prediction ne doit RIEN gagner. Sans cette ligne
    # l'assertion ci-dessus passerait aussi pour un +1 inconditionnel, qui serait faux.
    hits_pred_nu = attack_hits_with_modifiers(
        weapon_hits=whits, extra_hits=sc.ctx.stat(StatType.EXTRA_HITS),
        extra_hits_melee=sc.ctx.extra_hits_melee,
        attacker_effects=st.effects.active_effects(aid, {"hp": None}),
        trait_objects=sc.ctx.trait_objects(),
        target_effects=list(tgt_eff), aura_sources=auras, board=hb,
        is_melee=True, damage_profile="Piercing", include_bonus_hit_behaviours=True,
        is_prediction=True)
    assert hits_pred_nu == hits, (
        f"face PREDICTION SANS la marque : {hits_pred_nu} != {hits} -- le gain n'est pas attribue "
        f"a la marque, donc il mord pour la mauvaise raison")

    # --- (b) le CANAL #179 : gate x contexte ---
    n_banner = int(ability_var("AstartesBanner", "extraHits", is_constant=True) or 0)
    n_mark = int(ability_var("MasterAnnihilator", "nrOfHits", is_constant=True) or 0)
    assert n_banner > 0 and n_mark > 0, "constantes de config introuvables (ConfigConst 0x64 / 0x2f)"

    bctx = {"owner_id": cid, "owner_pos": (cp.col, cp.row), "owner_team": 0,
            "att_id": aid, "att_pos": a_pos, "att_team": 0, "is_melee": True,
            "tgt_id": tid, "damage_profile": "Piercing", "attack_hit_damage": (atk, atk)}
    mctx = {**bctx, "owner_id": tid}          # le marqueur est porte par la CIBLE (OwnerIsTarget)

    g_b = banner.create_aura_additional_hits_for_ally(bctx)
    g_m = mark.create_aura_additional_hits_for_ally(mctx)
    print(f"[canal #204] banner={g_b} mark={g_m}")
    assert g_b == {"count": n_banner, "min": atk, "max": atk, "profile": None}, \
        f"AstartesBanner: groupe #179 attendu ({n_banner} coup(s), [{atk},{atk}], profil NULL), obtenu {g_b}"
    assert g_m == {"count": n_mark, "min": atk, "max": atk, "profile": None}, \
        f"MasterAnnihilator: groupe #179 attendu ({n_mark} coup(s), [{atk},{atk}], profil NULL), obtenu {g_m}"

    # face PREDICTION : hors `OngoingAttack`, le noeud rend 0 -> AUCUN groupe (sinon sur-prediction
    # d'un coup PLEIN, exactement le bug corrige par #227 sur LetTheGalaxyBurn).
    assert banner.create_aura_additional_hits_for_ally(
        {k: v for k, v in bctx.items() if k != "attack_hit_damage"}) is None
    assert mark.create_aura_additional_hits_for_ally(
        {k: v for k, v in mctx.items() if k != "attack_hit_damage"}) is None
    # gates
    assert banner.create_aura_additional_hits_for_ally({**bctx, "is_melee": False}) is None, \
        "AstartesBanner sans `IsMeleeAttack` -> aucun groupe"
    assert banner.create_aura_additional_hits_for_ally({**bctx, "att_id": cid}) is None, \
        "`SurroundingFriends` exclut le porteur lui-meme"
    assert banner.create_aura_additional_hits_for_ally({**bctx, "att_team": 1}) is None, \
        "`SurroundingFriends` = ALLIES du porteur"
    rng = int(ability_var("AstartesBanner", "range", is_constant=True) or 2)
    far = next((board.coord(t) for t in sorted(board.by_id) if board.walkable(t)
                and hexgeo.distance(board.coord(t), a_pos) > rng), None)
    assert far is not None and banner.create_aura_additional_hits_for_ally(
        {**bctx, "owner_pos": far}) is None, f"porteur au-dela du rayon {rng} -> aucun groupe"
    assert mark.create_aura_additional_hits_for_ally({**mctx, "damage_profile": "Psychic"}) is None, \
        "`!AreEqual(CurrentAttackDamageProfile, 0xd = Psychic)` non applique"
    assert mark.create_aura_additional_hits_for_ally({**mctx, "owner_id": aid}) is None, \
        "`get_OwnerIsTarget` non applique (le marqueur doit etre porte par la CIBLE)"
    # non-regression croisee : AstartesBanner n'a AUCUN gate de profil (mesure live #204, meme
    # attaquant Psychic -> 0 coup sous MasterAnnihilator, +1 sous AstartesBanner).
    assert banner.create_aura_additional_hits_for_ally({**bctx, "damage_profile": "Psychic"}) \
        == {"count": n_banner, "min": atk, "max": atk, "profile": None}, \
        "AstartesBanner ne doit PAS heriter du gate Psychic de MasterAnnihilator"
