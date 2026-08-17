"""#10007-r1 -- `ModifiedExoarmour_PierceReduction` (1543) CONFRONTE BIT-EXACT, coup par coup.

CE QUE #10007 A LAISSE. Le slot d'interface **25** (`0x19 CreatePiercingMalusForDefense`) a ete
porte par #10007 (`BaseEffect.create_piercing_malus_for_defense`, appele par
`build_defender_modifiers_from_effects`) mais **AUCUN effet ne l'empruntait** : la seule
surchargeante native du build, `IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_
PierceReductionEffect$$CreatePiercingMalusForDefense`, n'avait pas de classe. Le canal etait pose
et MUET -- exactement la forme de dette que ce fichier ferme.

LE CORPS NATIF, mirror 1:1 :

    EffectBonus.ForSubtraction(
        get_OwnerIsTarget
          & !DamageProfileIs( AbilityConfiguration.GetDamageProfile (cfg@+0x60) )   # Psychic
          & !DamageProfileIs( AbilityConfiguration.GetDamageProfile2(cfg@+0x60) ),  # DirectDamage
        DSLFormulas.ConfigVar(0x3f = extraPierceRatio, GetAbilityState(this), cfg@+0x60) )

⚠ **LE SIGNE.** `IdunBattle.Entities.Effects.BaseEffect$$PiercingMalusForDefense` et
`$$PiercingBonusForAttack` ont des corps IDENTIQUES a l'octet pres (seul le champ de cache differe),
et ce corps commun sert les DEUX fabriques : `ForPiercing` rend la valeur telle quelle,
`ForSubtraction` la rend **NIEE**. Une reduction se porte donc par `for_piercing(..., -v)`.

LE MONTAGE. `votanChampion` << Kimm >> est un HERO **hors pool** : il entre par
`catalog_inject.write_augmented_seed_bc` + `rl_duel build --seed-bc`. Son passif
`ModifiedExoarmour` pose 1543 des le deploiement (aucun `CreateActiveCondition` -- il est
inconditionnel, donc TOUJOURS capte par `decisionView`), sans aucun montage supplementaire.

CE QUI REND LE TEMOIN NON DEGENERE, ET LE TEST L'ASSERTIONNE. Un malus de percage n'est
observable que si la branche PERCAGE de
`...StaticBattleRules.Damage$$GetDamageWithPiercing` (`max(0, d - armure, d x p/100)`) l'emporte :
si la branche ARMURE domine, `p` ne change RIEN et le test serait vert sans rien mesurer. D'ou la
CONTRE-EPREUVE JOUEE en fin de test : la MEME salve est rejouee avec le slot 25 neutralise, et le
degat DOIT differer.

⚠ Ce fichier monte un runner : il est LIVE.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.entities.effect_type import EffectType
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

#: le PORTEUR du passif `ModifiedExoarmour` -- HERO hors pool, donc injecte au catalogue.
KIMM = "votanChampion"
#: l'ATTAQUANT : `Gauss` porte `PiercingRatio = 60`, et 6 coups par salve. Il est AU POOL.
ATTACKER = "necroDestroyer"
PIERCE_REDUCTION = int(EffectType.ModifiedExoarmour_PierceReduction)      # 0x607 = 1543

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/damage_reduction.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/services/damage_modifiers.py",
        "scripts/python/engine/services/damage_prediction.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation BIT-EXACT du slot d'interface 25 (`CreatePiercingMalusForDefense`) et de "
              "son unique emprunteur natif (#10007-r1) : elle rougit si le signe, la magnitude, les "
              "deux gates de profil ou le routage vers l'axe percage bougent.",
}


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


@pytest.fixture(scope="module")
def kimm_seed_bc(tmp_path_factory):
    """FIXTURE NOMMEE : un seed BC augmente du porteur HORS POOL (bloc `Units` **ET** configs
    `Abilities` -- sans la seconde ecriture, le porteur se deploie puis FAUTE au cast)."""
    import catalog_inject as CI
    out = tmp_path_factory.mktemp("bc10007r1") / "seed-bc-kimm.json"
    p, ajoutees, configs = CI.write_augmented_seed_bc(str(out), [KIMM])
    if not ajoutees:
        pytest.skip("%s deja dans le seed BC ou injection impossible (%s)" % (KIMM, configs))
    return str(p)


@pytest.fixture(scope="module")
def kimm_case(live_session, rpc, build_runner, kimm_seed_bc):
    """FIXTURE NOMMEE ET REUTILISABLE : monte le duel, amene l'attaquant a portee, JOUE l'attaque
    live et rend de quoi la rejouer offline (etat AVANT + MT cale + tuile)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=["--seed-bc", kimm_seed_bc,
                                     "--p-units", ATTACKER, "--a-units", KIMM])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def tof(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec):
        pytest.skip("decisionView KO")
    att0 = next((u for u in (dec.get("units") or []) if u.get("visualId") == ATTACKER), None)
    tgt0 = next((u for u in (dec.get("units") or []) if u.get("visualId") == KIMM), None)
    if att0 is None or tgt0 is None:
        pytest.skip("unite absente (att=%s kimm=%s)" % (bool(att0), bool(tgt0)))
    att_id, tgt_id, my_player = att0["id"], tgt0["id"], att0.get("owner")

    import gameconfig as GC
    R = max([int(w.get("Range") or 0) for w in ((GC.unit(ATTACKER) or {}).get("weapons") or [])]
            or [0]) or 1

    for _turn in range(30):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        a = next((u for u in (dec.get("units") or []) if u["id"] == att_id and u.get("alive")), None)
        t = next((u for u in (dec.get("units") or []) if u["id"] == tgt_id and u.get("alive")), None)
        if a is None or t is None:
            pytest.skip("attaquant/cible disparu pendant l'approche")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        dgoal = _bfs(board, tof(t))
        cur = tof(a)
        if dgoal.get(cur, 99) > R:
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == att_id), None)
            reach = {board.id_at(x["col"], x["row"]): (x["col"], x["row"])
                     for x in ((cmt or {}).get("tiles") or [])}
            pool = [x for x in reach if x in dgoal and dgoal[x] < dgoal.get(cur, 99)]
            if pool:
                best = min(pool, key=lambda x: dgoal[x]); col, row = reach[best]
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": att_id, "to": {"col": col, "row": row}}}, 40)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue

        # A PORTEE -- on capture, on tire, on rejouera.
        norm = next((ab for ab in (a.get("abilities") or []) if ab.get("kind") == "normal"), None)
        if norm is None:
            pytest.skip("pas d'attaque normale exposee sur l'attaquant")
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")
        hp_before = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == tgt_id), None)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": att_id, "targetId": tgt_id,
            "abilityType": norm["id"]}}, 60)
        if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
            pytest.skip("attaque refusee : %s" % (json.dumps(res)[:300],))
        hp_after = next((u.get("hp") for u in (res.get("units") or [])
                         if u.get("squadId") == tgt_id), None)
        if hp_before is None or hp_after is None:
            pytest.skip("PV de la cible non mesures")
        return {"dec": dec, "ob": ob, "snap": snap, "rng": s0, "board": board,
                "att": att_id, "tgt": tgt_id, "hp_before": hp_before, "hp_after": int(hp_after),
                "rid": rid}
    pytest.skip("attaquant jamais amene a portee en 30 tours")


def _rejouer(case):
    """Rejoue l'attaque OFFLINE depuis l'etat capture, MT cale.

    La CONTRE-EPREUVE ne passe pas par un parametre : elle substitue le slot 25 lui-meme
    (`monkeypatch` sur la classe), pour que le bras mutant traverse EXACTEMENT le meme chemin que
    le bras nominal -- un `if` local ne le garantirait pas."""
    state = load_state(case["dec"], case["ob"], case["snap"], board=case["board"])
    state.rng = _seed_rng(case["rng"])
    runner = Runner(state).install_default_handlers()
    runner.apply(AttackUnitMessage(case["att"], case["tgt"]))
    hp = state.get_entity(case["tgt"]).get_component(HealthComponent).hp
    return hp, runner.damage_handler.last


def test_10007r1_leffet_1543_est_bien_porte_par_kimm(kimm_case):
    """SANITY et non-degenerescence : sans l'instance de 1543 dans l'etat offline, tout ce qui
    suit mesurerait le vide. 1543 n'a AUCUN `CreateActiveCondition` -> toujours actif, toujours
    capte par le canal `decisionView` par defaut."""
    state = load_state(kimm_case["dec"], kimm_case["ob"], kimm_case["snap"], board=kimm_case["board"])
    effs = state.effects.by_unit.get(kimm_case["tgt"]) or [] if state.effects else []
    types = {int(getattr(e, "effect_type", 0) or 0) for e in effs}
    assert PIERCE_REDUCTION in types, (
        "1543 absent de l'etat offline de Kimm (effets vus : %s)" % sorted(types))
    porteur = next(e for e in effs if int(getattr(e, "effect_type", 0) or 0) == PIERCE_REDUCTION)
    assert porteur.create_piercing_malus_for_defense("Physical") is not None, \
        "l'instance ne rend aucun malus : la classe n'est pas celle du registre"


def test_10007r1_le_degat_offline_reproduit_le_live_a_lunite(kimm_case):
    """CONFRONTATION : meme etat, meme MT, meme attaque -- les PV de Kimm doivent coincider."""
    hp, last = _rejouer(kimm_case)
    print("\n[10007-r1] Kimm hp %s -> live %s | offline %s | pierce=%s armor=%s per_hit=%s"
          % (kimm_case["hp_before"], kimm_case["hp_after"], hp,
             (last or {}).get("pierce"), (last or {}).get("armor"), (last or {}).get("per_hit")))
    assert hp == kimm_case["hp_after"], (
        "PV Kimm offline %s != live %s (live dmg=%s, offline dmg=%s). Le malus de percage "
        "defenseur (`ModifiedExoarmour_PierceReductionEffect$$CreatePiercingMalusForDefense`, slot "
        "d'interface 25) n'est pas -- ou mal -- porte."
        % (hp, kimm_case["hp_after"], kimm_case["hp_before"] - kimm_case["hp_after"],
           kimm_case["hp_before"] - hp))


def test_10007r1_le_regime_est_DISCRIMINANT_contre_epreuve_jouee(kimm_case, monkeypatch):
    """CONTRE-EPREUVE JOUEE -- sans elle, ce fichier serait vert dans un regime ou le malus de
    percage ne change RIEN (branche ARMURE dominante de `GetDamageWithPiercing`).

    On rejoue la MEME salve avec le slot 25 neutralise : le degat DOIT differer."""
    from engine.entities.effects.loki import damage_reduction as DR
    nominal, last = _rejouer(kimm_case)
    monkeypatch.setattr(DR.ModifiedExoarmourPierceReductionEffect,
                        "create_piercing_malus_for_defense",
                        lambda self, damage_profile=None, is_melee=None, attacker_ctx=None: None)
    mutant, last_m = _rejouer(kimm_case)
    print("[10007-r1] contre-epreuve : nominal hp=%s (pierce=%s) | mutant hp=%s (pierce=%s)"
          % (nominal, (last or {}).get("pierce"), mutant, (last_m or {}).get("pierce")))
    assert nominal != mutant, (
        "neutraliser le slot 25 ne change RIEN au degat : le regime est DEGENERE (la branche "
        "ARMURE de `GetDamageWithPiercing` domine, ou l'effet ne remonte pas jusqu'au calcul). "
        "Ce test ne mesure alors pas ce qu'il croit -- changer d'attaquant ou d'armure de cible.")
    assert nominal == kimm_case["hp_after"], "le bras nominal doit rester celui qui matche le live"
