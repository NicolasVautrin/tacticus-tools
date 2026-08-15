"""#969-r1 / #971-r2 -- CONFRONTATION de la PROBABILITE portee a celle que le natif TIRE.

CE QUE CE PROBE ETABLIT, ET CE QU'IL N'ETABLIT PAS
---------------------------------------------------
Il ne mesure PAS un taux d'agrement. Il mesure **une seule chose** : est-ce que le `p` calcule par
`NonComparablePlaybook.use_probability` EGALE le `p` que le natif passe a son PRNG ?

C'est la question que les deux residus posaient et qu'aucun montage ne pouvait trancher, parce que
`IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` ne rend qu'un `bool` -- `p` ne sort jamais de
la fonction. Le capteur `shouldEvaluateTrace` (`frida/hooks/probes/should-evaluate-trace.ts`) ancre
donc AUSSI `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextBool` (l'overload `Fix64`, slot 4
d'`IdunBattle.Utils.PRNG.IPseudoRNG`), dont `args[1]` EST `p`, et n'attribue un tirage que s'il est
IMBRIQUE dans un `ShouldEvaluate` sur le MEME thread.

POURQUOI LE TIRAGE LUI-MEME N'EST PAS REPRODUIT -- ET CE N'EST PAS UN RENONCEMENT
----------------------------------------------------------------------------------
La chaine a ete lue de bout en bout avant d'ecrire ce probe :

  * `IdunBattle.Utils.PRNG.MersenneTwister$$NextBool(p)` = `genrand_real2() < p` (Mersenne Twister) ;
  * le PRNG est INJECTE : `IdunBattle.AI.Playbook.BasePlaybook$$Init(..., random, ...)` ecrit
    `this.<+0x30>`, et il vient d'`IdunBattle.AI.PlaybookDatabase$$.ctor(..., random, ...)` ;
  * `IdunBattle.Runner.IdunRunner$$Initialize` construit **DEUX** `PlaybookDatabase`, et
    `IdunBattle.Core.Services.AiControl$$Init` NOMME ses parametres : celle de l'IA adverse recoit
    le `pseudoRNG` de la bataille (`MersenneTwister$$.ctor(rngSeed)`), celle du joueur
    (`humanAiPlaybook` / `humanAiRandom`) recoit un MT NEUF seede par
    `System.DateTime$$get_Now().Ticks` -- **non reproductible EN PRINCIPE** ;
  * et le MT de bataille est **PARTAGE** : le meme objet est passe a
    `IdunBattleLogic.Entities.DSLFactory$$.ctor` (qui l'enveloppe dans
    `IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$.ctor`), a
    `IdunBattle.Core.Services.DamageCalculations$$Init`, a
    `IdunBattle.Core.Services.UtilitiesDatabase$$.ctor` et a `AiControl$$Init`.

Reproduire le tirage exigerait donc de rejouer TOUTE la sequence de consommation du meme flux
depuis le debut de la bataille (degats, esquive, blocage, selecteurs DSL, utilities, strategie),
dans l'ordre exact -- et une seule consommation non modelisee decale tout le reste SANS ERREUR.
Le choix ECRIT est donc : modeliser la porte comme une PROBABILITE, et rendre cette probabilite
CONFRONTABLE. C'est ce que ce probe fait.

DEROULE
--------
  1. ARME le capteur et EXIGE sa resolution complete (`nextBoolFix64` compris) -- un capteur a
     demi arme rendrait `prob = null` partout, ce qui se lirait a tort comme << regime
     deterministe >>.
  2. Pour chaque porteur, construit le `NCContext` LIVE et calcule `use_probability` AVANT de
     declencher quoi que ce soit : le natif tirera sur CET etat-la.
  3. Declenche `aiDryRunAllUnits` (READ-ONLY, passe par le generateur, donc par `ShouldEvaluate`).
  4. Relit les traces et apparie par `unitId`.

⚠ L'APPARIEMENT EST PAR UNITE, PAS PAR ABILITY -- et c'est une LIMITE, pas un detail :
`ShouldEvaluate` ne publie pas l'ability. Le probe n'en conclut donc RIEN tout seul ; il IMPRIME
les valeurs distinctes vues pour l'unite, et le verdict n'est prononce que si l'unite n'a produit
qu'UNE SEULE valeur de tirage (auquel cas elle est forcement celle de l'ability etudiee, les autres
abilities du kit ayant une `GetUseProbability` constante qui ne tire pas). Deux valeurs ou plus ->
`AMBIGU`, jamais un appariement devine.

Usage : `python probe_969r1_prob_confrontee.py --runner <id> [--session <sid>]`
"""
from __future__ import annotations

import argparse
import json
import sys

import rl_collect_batch as R

#: Les trois porteurs du residu, par `visualId` -> (ability, libelle). L'ability sert a nommer la
#: mesure, pas a l'apparier (cf. l'avertissement de l'en-tete).
PORTEURS = {
    "templHelbrecht": (1049, "CrusadeOfWrath"),
    "spaceBlackmane": (1106, "WarHowl"),
    "orksWarboss": (1058, "Waaagh"),
}

#: Tolerance de comparaison des deux `p`. Le natif calcule en Fix64 (Q32.32) et le capteur reconvertit
#: par `raw / 2^32` ; le port calcule en flottant. L'ecart de representation est de l'ordre de 2^-32.
EPS = 1e-6


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(sid, method, body=None, timeout=90):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _armer(sid) -> dict:
    """⚠ DESARME D'ABORD, TOUJOURS. Sur un capteur DEJA arme, `{action:"arm"}` court-circuite et rend
    `{ok, armed, note}` **SANS `resolution`** -- le controle ci-dessous lirait alors un dict vide et
    accuserait une resolution manquante qui n'existe pas. Le cas se produit des qu'un run precedent
    s'est interrompu avant son `disarm` (vecu). Desarmer-puis-armer rend le probe IDEMPOTENT et
    garantit qu'on lit une resolution FRAICHE plutot qu'une resolution supposee."""
    _rpc(sid, "shouldEvaluateTrace", {"action": "disarm"}, 60)
    r = _rpc(sid, "shouldEvaluateTrace", {"action": "arm"}, 60)
    if not r.get("armed"):
        raise RuntimeError("capteur NON arme : %s" % json.dumps(r, default=str)[:400])
    res = r.get("resolution") or {}
    if not res.get("nextBoolFix64"):
        raise RuntimeError("`NextBool(Fix64)` non resolu -> `prob` serait TOUJOURS null, ce qui se "
                           "lirait a tort comme un regime deterministe : %s" % json.dumps(res))
    return res


def _nc_context(sid, rid: int, uid: int):
    """MEME construction que celle des probes de face DECISION (patron
    `probe_1066_rites_of_morkai_decision_live._nc_context`) : un seul foyer de verite pour le
    contexte, sinon on comparerait le natif a un etat que le moteur ne voit jamais."""
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine import weights
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32})
    mov = _rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _rpc(sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _rpc(sid, m, b, t), rid, dv, mov_by_unit, uid,
                      weights.load(), predictor)
    return PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        is_wall_by_pos=getattr(c, "is_wall_by_pos", None) or {},
        is_in_fog_by_pos=getattr(c, "is_in_fog_by_pos", None) or {},
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        current_player=getattr(c, "cur", None),
        machine_of_war_position=c.machine_of_war_position,
        triggered_kits=getattr(c, "live_triggered_kits", None),
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--session", type=int, default=None)
    args = ap.parse_args()
    sid = args.session if args.session is not None else R._resolve_session()
    rid = args.runner

    from engine.playbook import noncomparable as PB

    res = _armer(sid)
    print("[969-r1] capteur ARME : %s" % json.dumps(res))
    _rpc(sid, "shouldEvaluateTrace", {"action": "read", "clear": True}, 60)

    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    cibles = {}
    for u in (dv.get("units") or []):
        vis = u.get("visualId")
        if vis in PORTEURS and u.get("alive"):
            cibles[u.get("id")] = (vis,) + PORTEURS[vis]
    if not cibles:
        print("[969-r1] ECHEC : aucun des trois porteurs n'est sur le plateau")
        return 2
    print("[969-r1] porteurs vivants : %s" % {k: v[0] for k, v in cibles.items()})

    # ETAPE 2 -- le `p` du PORT, calcule sur l'etat COURANT, avant tout declenchement.
    porte = {}
    for uid, (vis, aid, nom) in sorted(cibles.items()):
        nc = _nc_context(sid, rid, uid)
        pb = PB.PLAYBOOKS.get(aid)
        if pb is None:
            print("[969-r1] %s : ability %s ABSENTE du registre -- rien a confronter" % (vis, aid))
            continue
        p = pb.use_probability(nc)
        porte[uid] = (vis, aid, nom, p)
        print("[969-r1] PORT   u%-4s %-16s %-16s p=%s" % (uid, vis, nom, p))

    # ETAPE 3 -- le generateur natif, READ-ONLY (aucune action appliquee).
    _rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 300)

    # ETAPE 4 -- relecture des tirages.
    tr = _rpc(sid, "shouldEvaluateTrace", {"action": "read"}, 60)
    diag = tr.get("diag") or {}
    print("[969-r1] traces : %s appels, diag=%s" % (tr.get("callCount"), json.dumps(diag)))
    if not diag.get("gateFires"):
        print("[969-r1] ECHEC : ZERO fire de `ShouldEvaluate` -- le capteur est arme mais rien ne "
              "l'a traverse. Une comparaison ici ne mesurerait RIEN.")
        return 2

    par_unite = {}
    for c in (tr.get("calls") or []):
        if c.get("prob") is None:
            continue                              # regime DETERMINISTE : aucun tirage, pas de `p`
        par_unite.setdefault(c.get("unitId"), []).append(c)

    rc = 0
    for uid, (vis, aid, nom, p) in sorted(porte.items()):
        rows = par_unite.get(uid) or []
        probs = sorted({round(float(c["prob"]), 9) for c in rows})
        if not probs:
            # ABSENCE DE TIRAGE = MESURE, pas absence de mesure : `BasePlaybook$$ShouldEvaluate` ne
            # consulte son PRNG que dans la bande OUVERTE. Un port qui annonce une EXTREMITE
            # (`p <= 0` ou `p >= 1`) est donc CONFIRME par ce silence, et un port qui annonce la
            # bande est CONTREDIT par lui. Ne rien conclure ici laisserait passer la seconde faute.
            if p is None:
                verdict = "NON MESURE des deux cotes"
            elif p <= 0.0 or p >= 1.0:
                verdict = "ACCORD (extremite DETERMINISTE : le natif ne consulte pas son PRNG)"
            else:
                verdict = "DIVERGENCE : le port annonce la bande OUVERTE, le natif n'a PAS tire"
                rc = 1
            print("[969-r1] NATIF  u%-4s %-16s %-16s AUCUN TIRAGE, port p=%s -> %s"
                  % (uid, vis, nom, p, verdict))
            continue
        if len(probs) > 1:
            print("[969-r1] NATIF  u%-4s %-16s %-16s AMBIGU : %s valeurs distinctes %s -- "
                  "`ShouldEvaluate` ne publie pas l'ability, aucun appariement n'est prononce"
                  % (uid, vis, nom, len(probs), probs))
            continue
        pn = probs[0]
        drew = [c.get("drew") for c in rows]
        ok = (p is not None and abs(float(p) - pn) <= EPS)
        print("[969-r1] NATIF  u%-4s %-16s %-16s p=%s tirages=%s -> %s"
              % (uid, vis, nom, pn, drew, "ACCORD" if ok else "DIVERGENCE"))
        if not ok:
            print("         port=%s natif=%s ecart=%s" % (p, pn, None if p is None else abs(p - pn)))
            rc = 1

    _rpc(sid, "shouldEvaluateTrace", {"action": "disarm"}, 60)
    print("[969-r1] capteur DESARME")
    return rc


if __name__ == "__main__":
    # Le `disarm` vit ICI et pas seulement en fin de `main` : une exception en cours de route
    # laisserait sinon les `Interceptor` poses sur une session PARTAGEE avec d'autres agents.
    try:
        _rc = main()
    finally:
        try:
            _rpc(R._resolve_session(), "shouldEvaluateTrace", {"action": "disarm"}, 60)
        except Exception as _exc:                                          # noqa: BLE001
            print("[969-r1] AVERTISSEMENT : desarmement impossible (%s) -- le capteur peut etre "
                  "reste arme sur la session PARTAGEE" % _exc)
    sys.exit(_rc)
