"""#246 -- GARDE du masque de ciblage de ThunderousAssault (1043, `templSwordBrother`).

Le masque vient de la 2e des trois formes de ctor, **PRESET + FLAGS** :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$.ctor` recopie le preset
STATIQUE `TargetingOptions` +0x40 PUIS appelle `IdunBattle.Core.Services.TargetingOptions$$.ctor`
dans sa surcharge `(dst, preset, flags)`, qui recopie tout SAUF `Rules` -- champ qu'elle COMBINE :
`dst+0x28 = flags | preset+0x28`. Le masque EFFECTIF vaut donc `0x10000000 | *(statics+0x68)` =
`0x10000000 | 0x4000` = **0x10004000** = `CasterCanMove | TargetIsEnemy`, et NI le litteral visible
(0x10000000) NI le preset seul (0x4000) ne sont ce masque. Meme preset : `TargetingRange`
statique +0x30 = `RANGE_ADJACENT` (`onlyAdjacent = RangedBool.True`, `overrideRange = 1`).

CE QUE CE TEST VERROUILLE, et pourquoi il ECHOUE sans le masque : DEUX volets mordent offline sur ce
porteur -- `TargetIsEnemy` (cible = soi-meme ou un allie) et le volet PORTEE arme par
`RANGE_ADJACENT` (cible hors CONTACT -> `TargetIsInRange`). Sans `TARGETING_OPTIONS`,
`get_invalid_target_reason` rend 0 des sa premiere ligne (`options is None` => aucun gate) : le
moteur ACCEPTE une charge sur un allie, sur le caster lui-meme, ou sur un ennemi a 4 hex -- trois
casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE.

Le bit 28 `CasterCanMove` est une regle du volet CASTER (`TargetingQuery$$GetInvalidCasterReason`)
et n'est PAS portee (son 2e volet `MovementComponent.IsAllowedToMove` = `movementBlockers.Count == 0`
n'est pas modelise). Le test le VERIFIE plutot que de le supposer : il exige `casterReason` natif = 0
sur toutes les lignes, ce qui etablit que le non-port ne peut pas creer de desaccord ici.

Le montage (geometrie DRIVEE : ennemi au contact, ennemi a 2, ennemi a 4, allie au contact) et les
quatre lectures vivent dans `scripts/python/probe_246_thunderous_targeting.py` -- le probe MESURE, ce
test GARDE, une seule implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import hexgeo

import probe_246_thunderous_targeting as P
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.targeting import get_invalid_caster_reason, get_invalid_target_reason
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "777"


def test_thunderous_assault_targeting_mask_matches_native(host, live_session):
    """Le gate de cible porte de 1043 == `AttackQuery.GetInvalidTargetReason` natif, et il REFUSE
    des charges que `master` (sans masque) acceptait."""
    sid = live_session
    rid, state_file = P._build(sid, SEED, BOARD)
    try:
        for _ in range(P.TOURS_DE_CHAUFFE):
            P._act(sid, rid, {"kind": "endturn"}, 60)
        cid, _ally_id, _near_id, far_id = P._drive_contact(sid, rid)
        d0 = P._dv(sid, rid)
        c0 = next(u for u in d0["units"] if int(u["id"]) == cid)
        if hexgeo.distance(P._pos(c0), P._pos(next(u for u in d0["units"]
                                                   if int(u["id"]) == far_id))) != 2:
            P._step_toward(sid, rid, far_id, P._pos(c0), 2)
        P._my_turn(sid, rid)

        dv = P._dv(sid, rid)
        nat0 = P._r(sid, "abilityReason",
                    {"runnerId": rid, "casterId": cid, "abilityType": P.THUNDEROUS}, 60)
        assert bool(((nat0 or {}).get("abilityState") or {}).get("usable")), (
            "1043 non utilisable -> `GetInvalidTargetReason` court-circuite sur "
            "`ActiveAbility.CanCurrentlyBeUsed` et rend 0x1 pour la MAUVAISE raison : rien de "
            "mesurable")

        ob = P._r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = P._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = P._r(sid, "boardGraph", {"runnerId": rid}, 90)
        assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible"
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        caster_u = next(u for u in dv["units"] if int(u["id"]) == cid)

        rows = []
        for u in (dv.get("units") or []):
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            nat = P._r(sid, "abilityReason",
                       {"runnerId": rid, "casterId": cid, "targetId": tid,
                        "abilityType": P.THUNDEROUS}, 60)
            tr = (nat or {}).get("targetReason") or {}
            cr = (nat or {}).get("casterReason") or {}
            hexv = tr.get("hex")
            natv = int(hexv, 16) if isinstance(hexv, str) else (
                0 if tr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            crv = cr.get("hex")
            crv = int(crv, 16) if isinstance(crv, str) else (
                0 if cr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            # le camp se lit sur `owner` : `ctrl` designe le joueur COURANT, et le montage a
            # pilote les DEUX camps
            side = "caster" if tid == cid else (
                "allie" if u.get("owner") == caster_u.get("owner") else "ennemi")
            rows.append(("%s:%s" % (side, u.get("visualId")), tid,
                         hexgeo.distance(P._pos(caster_u), P._pos(u)), natv, crv,
                         int(get_invalid_target_reason(st, cid, tid, P._ability("apres"))),
                         int(get_invalid_target_reason(st, cid, tid, P._ability("avant"))),
                         int(get_invalid_target_reason(st, cid, tid, P._ability("sansEnemy"))),
                         int(get_invalid_target_reason(st, cid, tid, P._ability("sansRange")))))

        print("\n[1043 targeting] caster=u%d board=%s seed=%s" % (cid, BOARD, SEED))
        for label, tid, dist, natv, crv, ap, av, se, sr in rows:
            print("  %-28s id=%-4d d=%-2d natif=%-11s caster=%-5s apres=%-11s avant=%-6s "
                  "sansEnemy=%-11s sansRange=%s"
                  % (label, tid, dist, "-" if natv is None else hex(natv),
                     "-" if crv is None else hex(crv), hex(ap), hex(av), hex(se), hex(sr)))

        # 0) garde anti-confusion : au moins une cible ACCEPTEE par le natif -> l'ability n'est pas
        #    court-circuitee et les refus mesures viennent bien de la cascade.
        assert any(natv == 0 for _l, _t, _d, natv, *_ in rows), \
            "aucune cible acceptee par le natif -> les refus ne prouvent rien"

        # 1) accord natif / port APRES sur TOUTES les lignes. C'EST CETTE ASSERTION qui tombe quand
        #    `TARGETING_OPTIONS` disparait : le port rend 0 la ou le natif refuse.
        desaccords = [(label, hex(natv or 0), hex(ap))
                      for label, _t, _d, natv, _c, ap, _av, _se, _sr in rows if natv != ap]
        assert not desaccords, "desaccord natif/port : %s" % desaccords

        # 2) le masque SERT : au moins une ligne ou le natif REFUSE et ou `master` rendait 0.
        gains = [label for label, _t, _d, natv, _c, _ap, av, _se, _sr in rows
                 if natv not in (None, 0) and av == 0]
        assert gains, ("aucune ligne ou le masque change le verdict -> ce test ne garderait rien "
                       "(il passerait aussi sans `TARGETING_OPTIONS`)")

        # 3) les DEUX regimes de refus sont exerces -- sans quoi le test ne garderait qu'un demi
        #    masque (un `range` oublie, ou un `TargetIsEnemy` oublie, passerait inapercu).
        assert any(natv == int(TR.TargetIsEnemy) for _l, _t, _d, natv, *_ in rows), \
            "aucun refus TargetIsEnemy -> le volet CAMP n'est pas exerce"
        assert any(natv == int(TR.TargetIsInRange) for _l, _t, _d, natv, *_ in rows), \
            "aucun refus TargetIsInRange -> le volet PORTEE (RANGE_ADJACENT) n'est pas exerce"

        # 4) CONTREFACTUELS -- chaque volet PORTE reellement son refus : prive du bit 14 le masque
        #    faux-accepte les cibles amies, prive du `TargetingRange` il faux-accepte les cibles
        #    hors contact.
        cf_enemy = [label for label, _t, _d, natv, _c, _ap, _av, se, _sr in rows
                    if natv not in (None, 0) and se == 0]
        cf_range = [label for label, _t, _d, natv, _c, _ap, _av, _se, sr in rows
                    if natv not in (None, 0) and sr == 0]
        assert cf_enemy, "retirer TargetIsEnemy ne change aucun verdict -> le bit est decoratif"
        assert cf_range, "retirer TargetingRange ne change aucun verdict -> la portee est decorative"

        # 5) le volet CASTER non porte (`CasterCanMove`, bit 28) est INERTE ici -- verifie, pas
        #    suppose : le natif rend 0 pour le caster sur toutes les lignes, comme le port.
        assert all(crv == 0 for _l, _t, _d, _n, crv, *_ in rows), \
            "casterReason natif non nul -> `CasterCanMove` mord, le non-port cree un desaccord"
        assert int(get_invalid_caster_reason(st, cid, P._ability("apres"))) == 0
    finally:
        try:
            P._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        finally:
            state_file.unlink(missing_ok=True)
