"""#247 -- GARDE du masque de ciblage de SpiritLeech (1104, `tyranNeurothrope`).

Le masque vient de la 3e des trois formes de ctor, **PRESET STATIQUE COPIE** :
`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$.ctor` n'appelle AUCUN
`IdunBattle.Core.Services.TargetingOptions$$.ctor` -- il recopie les 0x40 octets du champ statique
`TargetingOptions` +0x180, puis `AActiveAbility..ctor(this, &opts, 0, 0)`. Aucun litteral de masque
n'est donc visible dans le ctor : le masque EFFECTIF est la constante ecrite par
`IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x1a8)` =
**0x4002** = `TargetMatchesDynamicRule | TargetIsEnemy`. Meme preset pour la portee :
`TargetingRange` statique +0x18 = `RANGE_FROM_CONFIG` (-> `constants.range` = 3) et
`forceMeleeTarget` = `*(statics+0x1a0)` = 1 = `RangedBool.False`.

CE QUE CE TEST VERROUILLE, et pourquoi il ECHOUE sans le masque : deux volets mordent offline --
`TargetIsEnemy` (cible = soi-meme ou un allie) et le volet PORTEE arme par `RANGE_FROM_CONFIG`
(au-dela de 3 hex -> `TargetIsInRange`). Sans `TARGETING_OPTIONS`, `get_invalid_target_reason` rend 0
des sa premiere ligne (`options is None` => aucun gate) : le moteur ACCEPTE un drain sur un allie,
sur le caster lui-meme, ou sur un ennemi a 4 hex -- trois casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE.

LA VOISINE MENT, ET LE TEST LE VERROUILLE AUSSI. `ArmoriumCherub` (1014) est dans le MEME module, de
la MEME forme, avec le MEME masque 0x4002 et le MEME `RANGE_FROM_CONFIG` : son preset (+0x140) ne
differe QUE par `forceMeleeTarget = 0 = RangedBool.True`. Le contrefactuel `forceMeleeTrue` rejoue ce
preset voisin et doit faux-REFUSER une cible que le natif accepte -- sans cette assertion, recopier
le preset du voisin passerait le test.

Le bit `TargetMatchesDynamicRule` (0x2) est POSE mais INERTE : la classe native ne fournit aucun
corps `SpiritLeechAbility$$GetDynamicInvalidTargetReason`, donc le defaut `AActiveAbility` (= 0)
s'applique, et cote port `ActiveAbility.get_dynamic_invalid_target_reason` rend 0 aussi. Le test le
VERIFIE plutot que de le supposer (contrefactuel `sansDynamic` : aucun verdict ne bouge).

Le montage (geometrie DRIVEE : ennemi au contact, ennemi au SEUIL d=3, ennemi a d=4, allie a portee)
et les six lectures vivent dans `scripts/python/probe_247_spirit_leech_targeting.py` -- le probe
MESURE, ce test GARDE, une seule implementation. Lit l'etat LIVE, aucune RVA ni tuile hardcodee,
ASCII only.
"""
from __future__ import annotations

import hexgeo

import probe_247_spirit_leech_targeting as P
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.targeting import get_invalid_caster_reason, get_invalid_target_reason
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "777"


def test_spirit_leech_targeting_mask_matches_native(host, live_session):
    """Le gate de cible porte de 1104 == `AttackQuery.GetInvalidTargetReason` natif, et il REFUSE
    des drains que `master` (sans masque) acceptait."""
    sid = live_session
    rid, state_file = P._build(sid, SEED, BOARD)
    try:
        for _ in range(P.TOURS_DE_CHAUFFE):
            P._act(sid, rid, {"kind": "endturn"}, 60)
        cid, _ally_id, _foes = P._drive(sid, rid)
        P._my_turn(sid, rid)

        dv = P._dv(sid, rid)
        nat0 = P._r(sid, "abilityReason",
                    {"runnerId": rid, "casterId": cid, "abilityType": P.SPIRIT_LEECH}, 60)
        assert bool(((nat0 or {}).get("abilityState") or {}).get("usable")), (
            "1104 non utilisable -> `GetInvalidTargetReason` court-circuite sur "
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
                        "abilityType": P.SPIRIT_LEECH}, 60)
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

        print("\n[1104 targeting] caster=u%d board=%s seed=%s" % (cid, BOARD, SEED))
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

        # 3) les DEUX regimes de refus sont exerces -- sans quoi un `range` oublie, ou un
        #    `TargetIsEnemy` oublie, passerait inapercu.
        assert any(r["nat"] == int(TR.TargetIsEnemy) for r in rows), \
            "aucun refus TargetIsEnemy -> le volet CAMP n'est pas exerce"
        assert any(r["nat"] == int(TR.TargetIsInRange) for r in rows), \
            "aucun refus TargetIsInRange -> le volet PORTEE (RANGE_FROM_CONFIG=3) n'est pas exerce"

        # 3bis) le SEUIL exact de la portee de config est encadre : d=3 accepte, d=4 refuse. Sans ce
        #       couple, une portee FAUSSE (2 ou 4) passerait les assertions precedentes.
        seuil = [r for r in rows if r["d"] == P.CONFIG_RANGE and r["label"].startswith("ennemi")]
        sur = [r for r in rows if r["d"] == P.CONFIG_RANGE + 1 and r["label"].startswith("ennemi")]
        assert seuil and seuil[0]["nat"] == 0, \
            "pas d'ennemi ACCEPTE a d=%d -> le seuil de portee n'est pas encadre" % P.CONFIG_RANGE
        assert sur and sur[0]["nat"] == int(TR.TargetIsInRange), \
            ("pas d'ennemi REFUSE a d=%d -> le seuil de portee n'est pas encadre par le haut"
             % (P.CONFIG_RANGE + 1))

        # 4) CONTREFACTUELS -- chaque champ LU porte reellement son verdict.
        cf_enemy = [r["label"] for r in rows if r["nat"] not in (None, 0) and r["sansEnemy"] == 0]
        cf_range = [r["label"] for r in rows if r["nat"] not in (None, 0) and r["sansRange"] == 0]
        # `forceMeleeTrue` = le champ du preset VOISIN (1014) : il doit faux-REFUSER une cible que le
        # natif ACCEPTE. C'est l'assertion qui interdit de recopier le preset du voisin.
        cf_fm = [r["label"] for r in rows if r["nat"] == 0 and r["forceMeleeTrue"] != 0]
        assert cf_enemy, "retirer TargetIsEnemy ne change aucun verdict -> le bit est decoratif"
        assert cf_range, "retirer TargetingRange ne change aucun verdict -> la portee est decorative"
        assert cf_fm, ("inverser forceMeleeTarget ne change aucun verdict -> le champ n'est pas "
                       "discrimine par ce montage (il faut un ennemi AU CONTACT pour armer "
                       "`AttackQuery$$ShouldApplyRangedInMelee`)")

        # 5) le bit `TargetMatchesDynamicRule` est POSE mais INERTE -- verifie, pas suppose.
        assert all(r["sansDynamic"] == r["apres"] for r in rows), \
            ("retirer TargetMatchesDynamicRule change un verdict -> une regle dynamique mord, alors "
             "que la classe native n'en fournit AUCUN corps")

        # 6) le masque ne porte AUCUN bit du volet CASTER -> `casterReason` natif doit valoir 0.
        assert all(r["cr"] == 0 for r in rows), \
            "casterReason natif non nul -> une regle du volet caster mord et n'est pas portee"
        assert int(get_invalid_caster_reason(st, cid, P._ability("apres"))) == 0
    finally:
        try:
            P._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        finally:
            state_file.unlink(missing_ok=True)
