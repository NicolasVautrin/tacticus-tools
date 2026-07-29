"""#245 -- GARDE du masque de ciblage de ValkyrieStrike (1018, `astraSmnVoxcaster`).

Le masque est celui du PRESET STATIQUE `TargetingOptions` +0x1c0 recopie par
`IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$.ctor` (la 3e forme de ctor :
aucun appel a `IdunBattle.Core.Services.TargetingOptions$$.ctor`). Sa valeur EFFECTIVE est la
constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` =
`*(statics+0x1e8)` = `0x6000040` = `TargetIsTile | AllowObscuredTargetByElevation |
AllowObscuredTargetByWalls`. Detail complet : `docs/rl/case-245-valkyrie-strike-targeting.md`.

CE QUE CE TEST VERROUILLE, et pourquoi il ECHOUE sans le masque : la seule regle du masque qui
MORD offline est `TargetIsTile` -- « tuile-cible NON MARCHABLE » -> le natif rend le litteral `1`
(`TargetingRule.ValidRequest`, qu'il REUTILISE pour ce refus). Sans `TARGETING_OPTIONS`,
`get_invalid_target_reason` rend 0 sur la premiere ligne (`options is None` => aucun gate) : le
moteur ACCEPTE un cast que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE.
Le test mesure les trois versions sur le MEME etat fige -- natif (oracle), port APRES, port AVANT
(`TARGETING_OPTIONS = None`, l'etat de `master`) -- et exige l'accord natif/APRES sur toutes les
lignes PLUS au moins une ligne ou AVANT « refusait de refuser ».

Montage : le porteur est un SUMMON sans summoner de heros (ses seuls poseurs gameconfig sont 4
`EnvFactionSummons:Armageddon*`, cote ENVIRONNEMENT), mais il est DEJA au catalogue `BC.Units` du
seed BC -> spawnable via `initAndStart(playerUnits=...)`. Deux champs de son entree sont amenages
(`Health`, et le trait `Summon` retire, qui desarme `CanStillBeUsed` et ferait court-circuiter
l'oracle) ; la justification detaillee, appuyee sur le decompile, est dans l'en-tete du probe.

Le montage et les trois lectures vivent dans `scripts/python/probe_245_valkyrie_targeting.py` (le
probe MESURE, ce test GARDE) -- une seule implementation, aucune divergence possible entre les deux.
Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_245_valkyrie_targeting as P
from engine.entities.pathfinding.board import Board

BOARD = "C3_26"     # 31 tuiles NON marchables sur 63 -> le regime refuse est largement exerce
SEED = 31337
TILES = 6           # echantillon par categorie (marchable / non marchable)


def _rpc(sid, method, body, timeout=90):
    return P._r(sid, method, body, timeout)


def test_valkyrie_strike_targeting_mask_matches_native(host, live_session):
    """Le gate de cible porte de 1018 == `AttackQuery.GetInvalidTargetReason` natif, et il REFUSE
    des tuiles que `master` (sans masque) acceptait."""
    sid = live_session
    rid, _added, _ab, state_file = P._build(sid, SEED, BOARD)
    try:
        dv, vox = P._to_my_turn(sid, rid)
        assert vox is not None, "Voxcaster absent du decisionView -- spawn KO"
        cid = int(vox["id"])
        assert P._ability_usable(sid, rid, cid), (
            "1018 non utilisable -> `GetInvalidTargetReason` court-circuite sur "
            "`ActiveAbility.CanCurrentlyBeUsed` et rend 0x1 pour la MAUVAISE raison : rien de "
            "mesurable (cf. l'en-tete du probe)")

        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible"
        board = Board(bg["tiles"], adjacency="native_sym")

        allw = [t for t in bg["tiles"] if t.get("walkable")]
        allnw = [t for t in bg["tiles"] if not t.get("walkable")]
        assert allnw, ("board %s sans tuile non marchable -> le regime REFUSE n'est pas exerce, "
                       "le test ne garderait rien" % BOARD)
        walk = allw[::max(1, len(allw) // TILES)][:TILES]
        nowalk = allnw[::max(1, len(allnw) // TILES)][:TILES]

        cases = [("unit:%s" % u.get("visualId"), int(u["id"])) for u in (dv.get("units") or [])]
        cases += [("walk:%d,%d" % (t["col"], t["row"]), int(t["id"])) for t in walk]
        cases += [("nowalk:%d,%d" % (t["col"], t["row"]), int(t["id"])) for t in nowalk]

        rows = []
        for label, tid in cases:
            nat = _rpc(sid, "abilityReason",
                       {"runnerId": rid, "casterId": cid, "targetId": tid,
                        "abilityType": P.VALKYRIE_STRIKE}, 60)
            tr = (nat or {}).get("targetReason") or {}
            hexv = tr.get("hex")
            natv = int(hexv, 16) if isinstance(hexv, str) else (
                0 if tr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            rows.append((label, tid, natv,
                         P._port_reason(dv, ob, snap, board, cid, tid, "apres"),
                         P._port_reason(dv, ob, snap, board, cid, tid, "avant")))

        print("\n[1018 targeting] caster=u%d board=%s seed=%d" % (cid, BOARD, SEED))
        for label, tid, natv, apres, avant in rows:
            print("  %-22s id=%-4d natif=%-6s apres=%-6s avant=%s"
                  % (label, tid, "-" if natv is None else hex(natv), hex(apres), hex(avant)))

        # 0) la garde anti-confusion du code 0x1 : au moins une tuile MARCHABLE est ACCEPTEE, donc
        #    le court-circuit d'ability ne mord pas et les 0x1 mesures viennent de `TargetIsTile`.
        assert any(natv == 0 for label, _t, natv, *_ in rows if label.startswith("walk:")), \
            "aucune tuile marchable acceptee par le natif -> les 0x1 ne prouvent rien"

        # 1) accord natif / port APRES sur TOUTES les lignes. C'EST CETTE ASSERTION qui tombe
        #    quand `TARGETING_OPTIONS` disparait : le port rend 0 la ou le natif rend 0x1.
        desaccords = [(label, hex(natv or 0), hex(apres))
                      for label, _t, natv, apres, _a in rows if natv != apres]
        assert not desaccords, "desaccord natif/port : %s" % desaccords

        # 2) le masque SERT : au moins une ligne ou le natif REFUSE et ou `master` rendait 0.
        gains = [label for label, _t, natv, _ap, avant in rows
                 if natv not in (None, 0) and avant == 0]
        assert gains, ("aucune ligne ou le masque change le verdict -> ce test ne garderait rien "
                       "(il passerait aussi sans `TARGETING_OPTIONS`)")

        # 3) CONTREFACTUEL -- apres les assertions de fond, pour qu'un masque absent tombe sur (1),
        #    son vrai motif, et pas ici. C'est bien `TargetIsTile` qui porte le refus : prive de ce
        #    seul bit, le masque faux-accepte EXACTEMENT les lignes que le natif refuse.
        faux_accepts = [label for label, tid, natv, _ap, _av in rows
                        if natv not in (None, 0)
                        and P._port_reason(dv, ob, snap, board, cid, tid, "sansTile") == 0]
        assert len(faux_accepts) == len(gains), (
            "le masque prive de `TargetIsTile` devrait faux-accepter les %d lignes refusees, il "
            "n'en faux-accepte que %d" % (len(gains), len(faux_accepts)))
    finally:
        try:
            P._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        finally:
            state_file.unlink(missing_ok=True)
