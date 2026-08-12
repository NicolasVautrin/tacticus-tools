"""#985 -- confrontation LIVE des faces DECISION portees par ce lot (1068, 1160).

Ce probe ne se contente pas de << ca tourne >> : il CRAFTE une configuration ou le comportement
porte CHANGE le resultat observable, en PLACANT les unites (`--place` / `--a-place`) au lieu de
subir la geometrie de spawn.

## Le montage de `1068 SilentDeath`, et pourquoi il DISCRIMINE

`SilentDeath` est `attackRangeType = Melee` : une cible n'est eligible que si elle est ADJACENTE
au caster. Le playbook, lui, ajoute un gate PROPRE -- la cible doit avoir au moins un ennemi-du-
caster adjacent (`Enemies(of: caster, AdjacentUnits(cible) - cible)`), c.-a-d. un allie A ELLE
colle a elle. Le texte de regles du jeu dit la meme chose par l'autre bout : << and up to
3 additional enemies adjacent to each other >>.

On place donc (board `C1_74`, odd-q, col impaire decalee +1/2) :

    caster  eldarJainZar   (3,3)
    cible A                (3,4)   voisine du caster ET voisine de son allie -> gate PASSE
    allie A                (3,5)   voisin de A ; NON eligible (pas voisin du caster)
    cible B                (2,3)   voisine du caster, AUCUN allie a elle adjacent -> gate REFUSE

Voisins de `(3,3)` (col impaire) = `(3,2) (3,4) (2,3) (2,4) (4,3) (4,4)` : A et B y sont, l'allie
non. Voisins de `(2,3)` (col paire) = `(2,2) (2,4) (1,2) (1,3) (3,2) (3,3)` : seul le CASTER s'y
trouve, et le caster n'est pas un << ennemi du caster >>. B est donc eligible mais gatee.

DISCRIMINANT : les deux cibles sont eligibles, l'utilite est PLATE (1) -- donc un port sans le
gate rendrait `A` ou `B` selon l'ordre d'enumeration, et un port avec le gate rend `A`
NECESSAIREMENT. Le montage separe les deux hypotheses au lieu de les confondre.

## Ce que ce probe REFUSE de faire passer pour une mesure

`ncEvaluate` peut etre structurellement AVEUGLE (mesure #1043 : il decode `Bucket+0x20`, que
`GenerateBucketWithMultipleStrategies` n'ecrit jamais). Si l'oracle rend VIDE alors que le regime
est atteint, ce probe ecrit NON CONFRONTE et rend 2 -- jamais un ecart, jamais un vert.

Codes de retour : 0 = confronte et conforme ; 1 = ECART ; 2 = NON CONFRONTE (regime non atteint
ou oracle aveugle) ; 3 = montage impossible.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_985_faces_live.py --ability 1068 --state-file <ABSOLU>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: Les DEUX montages de 1068. Meme caster, meme cible eligible ; SEULE bouge la position de
#: l'allie de la cible -- c'est-a-dire EXACTEMENT la variable du gate, et rien d'autre.
_BASE_1068 = {
    "ability": 1068,
    "board": "C1_74",
    "seed": "777",
    "caster": "eldarJainZar",
    "p_units": "eldarJainZar",
    "a_units": "ultraTitus,ultraApothecary,worldJakhal",
    "place": ["eldarJainZar:3,3"],
    "cible": (3, 4),
}

FIXTURES_1068 = {
    # L'allie est COLLE a la cible -> `Enemies(of: caster, AdjacentUnits(cible))` NON VIDE.
    "passe": dict(_BASE_1068, regime="passe",
                  a_place=["ultraTitus:3,4", "ultraApothecary:3,5", "worldJakhal:3,2"],
                  attendu_cible=True),
    # MEME cible, MEME position ; l'allie est renvoye a l'autre bout du plateau -> gate VIDE.
    "refuse": dict(_BASE_1068, regime="refuse",
                   a_place=["ultraTitus:3,4", "ultraApothecary:0,8", "worldJakhal:3,2"],
                   attendu_cible=False),
}

# ⚠ POURQUOI DEUX MONTAGES A UNE SEULE CIBLE, ET PAS UN SEUL A DEUX CIBLES.
# Le premier montage tente ici opposait une cible ENTOUREE (3,4) a une cible ISOLEE (3,2), toutes
# deux voisines du caster selon le modele d'adjacence du port (`battle_query.is_adjacent`, qui
# rend `True` et `dist=1`). MESURE : le natif REFUSE (3,2) avec
# `targetReason.hex = 0x0000000008000000` = `TargetIsInRange` -- le meme flag geometrique que
# celui documente par `probe_350r3`. La cible isolee n'etait donc jamais eligible, et le gate
# n'etait pas discrimine (`abilityTargets` = [79] seul, aux deux essais (2,3) puis (3,2)).
# On ne conclut RIEN de ce refus quant au port : on change de montage. Faire varier la position
# de l'ALLIE, a cible constante, isole la variable du gate sans dependre de l'ordre
# d'enumeration ni d'une seconde cible eligible.


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _build(fx, state_file: Path) -> str | None:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", fx["seed"],
            "--state-file", str(state_file), "--board", fx["board"],
            "--p-units", fx["p_units"], "--a-units", fx["a_units"], "--no-ai"]
    for p in fx["place"]:
        argv += ["--place", p]
    for p in fx["a_place"]:
        argv += ["--a-place", p]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[985] build KO : %s" % ((proc.stderr or proc.stdout or "")[-500:]), file=sys.stderr)
        return None
    return json.loads(state_file.read_text()).get("runnerId")


def _run(fx, state_file: Path) -> int:
    """Joue UN regime. 0 = conforme, 1 = ecart, 2 = non confronte, 3 = montage impossible."""
    state_file = Path(state_file)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        state_file.unlink()

    sid = _resolve_session()
    rid = _build(fx, state_file)
    if rid is None:
        return 3
    print("[985] runner=%s board=%s seed=%s" % (rid, fx["board"], fx["seed"]))
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        units = dv.get("units") or []
        by_pos, caster = {}, None
        for u in units:
            p = u.get("pos") or {}
            if p.get("col") is None:
                continue
            by_pos[(p["col"], p["row"])] = u
            if u.get("visualId") == fx["caster"]:
                caster = u
        print("[985] plateau :")
        for pos, u in sorted(by_pos.items()):
            print("   %-8s id=%-4s vis=%-22s team=%s" % (str(pos), u.get("id"),
                                                         u.get("visualId"), u.get("team")))
        if caster is None:
            print("[985] MONTAGE IMPOSSIBLE : le caster n'est pas sur le plateau")
            return 3
        cp = caster.get("pos") or {}
        if (cp.get("col"), cp.get("row")) != (3, 3):
            print("[985] MONTAGE NON ATTEINT : caster en (%s,%s), attendu (3,3)"
                  % (cp.get("col"), cp.get("row")))
            return 2
        if fx["cible"] not in by_pos:
            print("[985] MONTAGE NON ATTEINT : rien en %s" % (str(fx["cible"])))
            return 2

        cid = caster["id"]
        cible_id = by_pos[fx["cible"]]["id"]

        # --- le regime est-il ATTEINT ? la cible doit etre ELIGIBLE dans LES DEUX regimes -----
        # C'est le pivot du montage : si l'eligibilite bougeait avec la position de l'allie, on
        # ne mesurerait plus le gate mais la geometrie.
        at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": cid,
                                        "abilityType": fx["ability"]}, 120)
        elig = set()
        for u in (at.get("units") or []):
            for ab in (u.get("abilities") or []):
                if ab.get("abilityId") != fx["ability"]:
                    continue
                for t in (ab.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        elig.add(t["targetId"])
        print("[985] cibles ELIGIBLES (abilityTargets) : %s" % sorted(elig))
        if cible_id not in elig:
            rr = _r(sid, "abilityReason", {"runnerId": rid, "casterId": cid,
                                           "targetId": cible_id,
                                           "abilityType": fx["ability"]}, 90)
            print("[985]   refus natif -> %s" % json.dumps(rr.get("targetReason"), default=str))
            print("[985] NON CONFRONTE -- la cible n'est pas eligible dans le regime '%s' ; le"
                  " gate n'est donc pas atteint." % fx["regime"])
            return 2

        # --- le PORT --------------------------------------------------------------------------
        import engine_validate as EV                             # noqa: F401
        from engine.playbook import scene as scene_mod
        from engine import weights as W
        from engine.ai import context as _ai_ctx
        from engine.playbook import noncomparable as playbooks

        rpc = lambda m, b, t=60: _r(sid, m, b, t)                # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, cid, W.load(), predictor, debug=False)
        nc_ctx = playbooks.NCContext(
            uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
            enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos,
            walkable_by_pos=ctx.walkable_by_pos,
            plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
            elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
            wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
            tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
            units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=False)
        pb = playbooks.playbook_for(fx["ability"])
        if pb is None:
            print("[985] ECART : aucun playbook porte pour %d" % fx["ability"])
            return 1
        cands = pb.generate_candidates(nc_ctx)
        print("[985] PORT generate_candidates -> %s" % json.dumps(cands, default=str))

        # --- l'ORACLE natif, en REGARD ---------------------------------------------------------
        nc = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": cid,
                                    "abilityType": fx["ability"], "sweep": True}, 240)
        natif = [(row.get("pos"), row.get("bucket")) for row in (nc.get("positions") or [])
                 if row.get("bucket")]
        print("[985] ncEvaluate ok=%s playbook=%s buckets_non_vides=%d"
              % (nc.get("ok"), nc.get("playbookClass"), len(natif)))
        for pos, bk in natif[:6]:
            print("   pos=%s bucket=%s" % (pos, json.dumps(bk, default=str)[:200]))

        propose = bool(cands)
        attendu = bool(fx["attendu_cible"])
        if propose and cands[0].get("target") != cible_id:
            print("[985] ECART : le port propose la cible %s, or la SEULE eligible est %s"
                  % (cands[0].get("target"), cible_id))
            return 1

        # --- LE CRAN QUI CONFRONTE AU NATIF, et pas seulement le port a lui-meme ---------------
        # `ncEvaluate` est structurellement AVEUGLE au bucket que CETTE forme de generation
        # remplit (il decode `Bucket+0x20`) : il ne rend donc jamais l'action choisie. Mais il
        # rend `"empty"` quand le playbook n'en produit AUCUNE -- et c'est un signal EXPLOITABLE,
        # parce qu'il est ASYMETRIQUE entre les deux regimes. On l'exige donc dans le sens ou il
        # parle, et on l'exige ABSENT dans l'autre.
        vide_natif = any(bk == "empty" for _pos, bk in natif)
        if nc.get("playbookClass") != "SilentDeathPlaybook":
            print("[985] NON CONFRONTE -- `ncEvaluate` a charge `%s`, pas `SilentDeathPlaybook` :"
                  % nc.get("playbookClass"))
            print("      le zero n'accuserait pas la bonne classe (fallbackToDefault).")
            return 2
        if attendu and vide_natif:
            print("[985] ECART : le natif declare son bucket `empty` alors que le port PROPOSE.")
            return 1
        if (not attendu) and not vide_natif:
            print("[985] NON CONFRONTE -- le port ne propose rien, mais le natif ne declare pas")
            print("      `empty` : sans ce temoin, le refus du port n'est pas confronte.")
            return 2
        print("[985] natif : playbook=%s, bucket `empty` %s (temoin ASYMETRIQUE attendu pour "
              "ce regime)" % (nc.get("playbookClass"), "PRESENT" if vide_natif else "ABSENT"))

        if propose == attendu:
            print("[985] CONFORME [regime %s] : le port %s -- le gate << la cible a un allie "
                  "adjacent >> %s, comme au decompile."
                  % (fx["regime"], "PROPOSE la cible" if propose else "ne propose RIEN",
                     "PASSE" if attendu else "REFUSE"))
            return 0
        print("[985] ECART [regime %s] : le port %s, attendu %s."
              % (fx["regime"], "propose" if propose else "ne propose rien",
                 "qu'il propose" if attendu else "qu'il ne propose rien"))
        if not attendu:
            print("      Le gate n'a PAS mordu : l'allie est en (0,8), donc la cible en %s n'a"
                  % str(fx["cible"]))
            print("      aucun ennemi-du-caster adjacent.")
        return 1
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("[985] runner %s dispose" % rid)
        except Exception as e:                                   # noqa: BLE001
            print("[985] dispose KO : %s" % e, file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", type=int, default=1068)
    ap.add_argument("--regime", choices=sorted(FIXTURES_1068) + ["tous"], default="tous")
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU, nom UNIQUE (jamais sous data/)")
    a = ap.parse_args()
    if a.ability != 1068:
        print("[985] seule 1068 a un montage ecrit ici ; 1160 exige un porteur MoW "
              "(`--p-mow tauBroadside`) et une confrontation d'UTILITE, pas de gate")
        return 3
    regimes = sorted(FIXTURES_1068) if a.regime == "tous" else [a.regime]
    codes = {}
    for r in regimes:
        print("\n=== [985] regime '%s' ===" % r)
        # Un state-file DISTINCT par regime : deux runners de ce probe ne se marchent pas dessus.
        sf = Path(a.state_file)
        sf = sf.with_name("%s_%s%s" % (sf.stem, r, sf.suffix))
        codes[r] = _run(FIXTURES_1068[r], sf)
    print("\n[985] BILAN 1068 : %s" % ", ".join("%s=%d" % kv for kv in sorted(codes.items())))
    if any(c == 1 for c in codes.values()):
        return 1
    if any(c == 3 for c in codes.values()):
        return 3
    if any(c == 2 for c in codes.values()):
        return 2
    print("[985] les DEUX regimes sont conformes : le gate PASSE quand l'allie est colle a la")
    print("      cible, et REFUSE quand il ne l'est pas -- a cible et position CONSTANTES.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
