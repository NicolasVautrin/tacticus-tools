"""#247 -- GARDE du masque de ciblage de CordClaw (1122, `admecRuststalker`).

Le masque vient de la 3e des trois formes de ctor, **PRESET STATIQUE COPIE** :
`IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$.ctor` n'appelle AUCUN
`IdunBattle.Core.Services.TargetingOptions$$.ctor` -- il recopie les 0x40 octets du champ statique
`TargetingOptions` +0x40, puis `AActiveAbility..ctor(this, &opts, 0, 0)`. Le masque EFFECTIF est la
constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` =
`*(statics+0x68)` = **0x4000** = `TargetIsEnemy` SEUL. Meme preset pour la portee :
`TargetingRange` statique +0x30 = `RANGE_ADJACENT` (`onlyAdjacent = 0 = RangedBool.True`,
`overrideRange = Nullable(1)`) et `forceMeleeTarget` = `*(statics+0x60)` = 1 = `RangedBool.False`.

LE PIEGE QUE CE TEST VERROUILLE : `ThunderousAssault` (1043) RECOPIE LE MEME PRESET +0x40, mais
enchaine sur la surcharge « preset + flags » (`TargetingOptions..ctor(&opts, &preset, 0x10000000,
0)`) qui COMBINE `dst+0x28 = flags | preset+0x28` -> 0x10004000. CordClaw copie INTEGRALEMENT et
s'arrete la : son masque est le preset NU, **sans `CasterCanMove`**. Meme source statique, deux
masques -- c'est la FORME du ctor qui tranche, pas le preset. Le test l'objective en exigeant que
`casterReason` natif vaille 0 sur toutes les lignes (aucun bit du volet caster).

Pourquoi il ECHOUE sans le masque : deux volets mordent offline -- `TargetIsEnemy` (cible = soi-meme
ou un allie) et le volet PORTEE arme par `RANGE_ADJACENT` (toute cible hors CONTACT ->
`TargetIsInRange`). Sans `TARGETING_OPTIONS`, `get_invalid_target_reason` rend 0 des sa premiere
ligne : le moteur ACCEPTE un CordClaw sur un allie, sur le caster, ou sur un ennemi a 2 hex --
quatre casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE.

Le contrefactuel `rangeDist2` (meme portee NUMERIQUE, mais sans `onlyAdjacent`) est ce qui verrouille
le REGIME et pas seulement « une portee » : il doit faux-accepter la cible a d=2.

Le montage (geometrie DRIVEE : ennemi au contact, ennemi a d=2, ennemi a d=4, allie au contact) et
les six lectures vivent dans `scripts/python/probe_248_cord_claw_targeting.py` -- le probe MESURE, ce
test GARDE, une seule implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import hexgeo

import probe_248_cord_claw_targeting as P
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.targeting import get_invalid_caster_reason, get_invalid_target_reason
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "777"


def test_cord_claw_targeting_mask_matches_native(host, live_session):
    """Le gate de cible porte de 1122 == `AttackQuery.GetInvalidTargetReason` natif, et il REFUSE
    des casts que `master` (sans masque) acceptait."""
    sid = live_session
    rid, state_file = P._build(sid, SEED, BOARD)
    try:
        for _ in range(P.TOURS_DE_CHAUFFE):
            P._act(sid, rid, {"kind": "endturn"}, 60)
        cid, _ally_id, _foes = P._drive(sid, rid)
        P._my_turn(sid, rid)

        dv = P._dv(sid, rid)
        nat0 = P._r(sid, "abilityReason",
                    {"runnerId": rid, "casterId": cid, "abilityType": P.CORD_CLAW}, 60)
        assert bool(((nat0 or {}).get("abilityState") or {}).get("usable")), (
            "1122 non utilisable -> `GetInvalidTargetReason` court-circuite sur "
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
                        "abilityType": P.CORD_CLAW}, 60)
            tr = (nat or {}).get("targetReason") or {}
            cr = (nat or {}).get("casterReason") or {}
            hexv = tr.get("hex")
            natv = int(hexv, 16) if isinstance(hexv, str) else (
                0 if tr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            crv = cr.get("hex")
            crv = int(crv, 16) if isinstance(crv, str) else (
                0 if cr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            # le camp se lit sur `owner` : `ctrl` designe le joueur COURANT, et le montage a pilote
            # les DEUX camps
            side = "caster" if tid == cid else (
                "allie" if u.get("owner") == caster_u.get("owner") else "ennemi")
            row = {"label": "%s:%s" % (side, u.get("visualId")), "id": tid,
                   "d": hexgeo.distance(P._pos(caster_u), P._pos(u)), "nat": natv, "cr": crv}
            for v in P.VARIANTS:
                row[v] = int(get_invalid_target_reason(st, cid, tid, P._ability(v)))
            rows.append(row)

        print("\n[1122 targeting] caster=u%d board=%s seed=%s" % (cid, BOARD, SEED))
        for r in rows:
            print("  %-28s id=%-4d d=%-2d natif=%-11s caster=%-5s %s"
                  % (r["label"], r["id"], r["d"],
                     "-" if r["nat"] is None else hex(r["nat"]),
                     "-" if r["cr"] is None else hex(r["cr"]),
                     " ".join("%s=%s" % (v, hex(r[v])) for v in P.VARIANTS)))

        # 0) garde anti-confusion : au moins une cible ACCEPTEE par le natif -> l'ability n'est pas
        #    court-circuitee et les refus mesures viennent bien de la cascade.
        assert any(r["nat"] == 0 for r in rows), \
            "aucune cible acceptee par le natif -> les refus ne prouvent rien"

        # 1) accord natif / port APRES sur TOUTES les lignes. C'EST CETTE ASSERTION qui tombe quand
        #    `TARGETING_OPTIONS` disparait : le port rend 0 la ou le natif refuse.
        desaccords = [(r["label"], hex(r["nat"] or 0), hex(r["apres"]))
                      for r in rows if r["nat"] != r["apres"]]
        assert not desaccords, "desaccord natif/port : %s" % desaccords

        # 2) le masque SERT : au moins une ligne ou le natif REFUSE et ou `master` rendait 0.
        gains = [r["label"] for r in rows if r["nat"] not in (None, 0) and r["avant"] == 0]
        assert gains, ("aucune ligne ou le masque change le verdict -> ce test ne garderait rien "
                       "(il passerait aussi sans `TARGETING_OPTIONS`)")

        # 3) les DEUX regimes de refus sont exerces.
        assert any(r["nat"] == int(TR.TargetIsEnemy) for r in rows), \
            "aucun refus TargetIsEnemy -> le volet CAMP n'est pas exerce"
        assert any(r["nat"] == int(TR.TargetIsInRange) for r in rows), \
            "aucun refus TargetIsInRange -> le volet PORTEE (RANGE_ADJACENT) n'est pas exerce"

        # 3bis) le SEUIL de l'adjacence est encadre : d=1 accepte, d=2 refuse. C'est LA ligne qui
        #       distingue `RANGE_ADJACENT` de « pas de portee », et elle est au seuil.
        contact = [r for r in rows if r["d"] == 1 and r["label"].startswith("ennemi")]
        d2 = [r for r in rows if r["d"] == 2 and r["label"].startswith("ennemi")]
        assert contact and contact[0]["nat"] == 0, \
            "pas d'ennemi ACCEPTE au contact -> l'adjacence n'est pas encadree"
        assert d2 and d2[0]["nat"] == int(TR.TargetIsInRange), \
            "pas d'ennemi REFUSE a d=2 -> l'adjacence n'est pas encadree par le haut"

        # 4) CONTREFACTUELS -- chaque champ LU porte reellement son verdict.
        cf_enemy = [r["label"] for r in rows if r["nat"] not in (None, 0) and r["sansEnemy"] == 0]
        cf_range = [r["label"] for r in rows if r["nat"] not in (None, 0) and r["sansRange"] == 0]
        # `rangeDist2` : MEME portee numerique, mais sans `onlyAdjacent` -> doit faux-accepter d=2.
        # C'est cette assertion, et pas `sansRange`, qui verrouille le REGIME de portee.
        cf_regime = [r["label"] for r in rows if r["nat"] not in (None, 0) and r["rangeDist2"] == 0]
        assert cf_enemy, "retirer TargetIsEnemy ne change aucun verdict -> le bit est decoratif"
        assert cf_range, "retirer TargetingRange ne change aucun verdict -> la portee est decorative"
        assert cf_regime, ("remplacer RANGE_ADJACENT par une portee 2 ne change aucun verdict -> le "
                           "REGIME `onlyAdjacent` n'est pas verrouille par ce montage")

        # 5) `forceMeleeTarget` est LU mais INERTE ici : la portee EST deja l'adjacence, donc le
        #    clamp melee n'a rien a clamper. Verifie, pas suppose -- et si un jour cette assertion
        #    tombe, c'est que le regime de portee a change, pas que le champ etait faux.
        assert all(r["forceMeleeTrue"] == r["apres"] for r in rows), \
            ("inverser forceMeleeTarget change un verdict -> le champ n'est plus inerte, relire le "
             "preset et le regime de portee")

        # 6) le masque NU ne porte AUCUN bit du volet CASTER (c'est ce qui le separe de 1043).
        assert all(r["cr"] == 0 for r in rows), \
            "casterReason natif non nul -> une regle du volet caster mord et n'est pas portee"
        assert int(get_invalid_caster_reason(st, cid, P._ability("apres"))) == 0
    finally:
        try:
            P._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        finally:
            state_file.unlink(missing_ok=True)
