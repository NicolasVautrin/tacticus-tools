"""#1026 -- la face DECISION de `BasiliskBarrage` (1026) : le terme PREDICTION, mesure au natif.

QUESTION BINAIRE, et c'est la SEULE qui bloque le port :
`IdunBattle.AI.Playbook.Loki.BasiliskBarragePlaybook$$GenerateAttackPredictionsForShells` passe a
`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` un `targetsSelector` =
`DSLSelectors$$Entity(<element du pool d'obus>)`, et `IdunBattle.Entities.Selectors.EntitySelector
$$Select` rend l'entite TELLE QUELLE (elle n'appelle PAS `GetUnit`). Or le pool d'obus est fait de
TUILES (`TilesAtDistance`, `TargetTiles`). Donc le `ProbableDamageEvent.Target` du natif est une
ENTITE-TUILE.

    -> Le natif RESOUT-IL l'occupant de chaque tuile d'obus quelque part en aval
       (`PredictAttack`), ou le terme est-il structurellement NUL ?

Le decompile ne tranche pas seul : `PredictAttack` est un dispatch par objet-requete
(`IdunBattle.Core.Services.DamagePrediction$$PredictAttack`), et le port ne peut pas etre ecrit
sans la reponse -- un port qui mapperait tuile -> occupant alors que le natif ne le fait pas
INVENTERAIT de l'utilite, et l'inverse en PERDRAIT.

L'ORACLE : `pairUtility(caster, <tileEntityId>, 1026)` EST
`ComparablePlaybook$$CalculateUtilityFromPredictions` sur une cible TUILE -- le terme PREDICTION
SEUL (ni custom, ni terme `Tile`). Meme oracle et meme forme que `probe_302_2` pour 1169.

MONTAGE (un seul build, deux tuiles-cibles LEGALES -- le masque de 1026 porte
`TargetTileHasEnemyUnit`, donc une tuile VIDE n'est pas ciblable) :

        (1,1) astraOrdnance     -- le CASTER (`CasterHasNotMoved` : on ne le deplace pas)
        (4,5) <ennemi GROUPE>   -- cible T1
        (4,6) <ennemi VOISIN>   -- ring-1 de T1 : il n'est atteint que si le natif resout les
                                   occupants des tuiles d'obus
        (1,7) <ennemi ISOLE>    -- cible T3, aucun voisin dans ses anneaux 1 et 2

DISCRIMINANT : `u(T1)` vs `u(T3)`. Le tirage n'entre PAS dans la decision (le playbook ENUMERE le
pool et pondere par `numShells / count`), donc les deux tuiles ont EXACTEMENT la meme structure de
pool -- seule l'OCCUPATION differe.

  * `u(T1) > u(T3) > 0`  -> le natif RESOUT les occupants : le port doit mapper tuile -> occupant.
  * `u(T1) == u(T3) > 0` -> il predit contre l'entite TUILE (valeur independante de l'occupation).
  * `u(T1) == u(T3) == 0` -> terme structurellement NUL : rien a porter sur cet axe.

Sortie ASCII only. Discipline runner : `--state-file` ABSOLU sous `logs/`, runner DISPOSE en sortie.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_duel as R                                                            # noqa: E402
import rl_collect_batch as B                                                   # noqa: E402

BOARD = "MC1_67"
SEED = 777
CASTER = "astraOrdnance"
FOE_GROUPE = "tyranTyrantGuard"     # cible T1
FOE_VOISIN = "necroWarden"          # le TEMOIN dont on DEPLACE la position entre les deux bras
FOE_ISOLE = "tyranNeurothrope"      # cible T3, toujours isolee (temoin de non-degenerescence)
POS_CASTER, POS_T1, POS_VOISIN, POS_T3 = (1, 1), (4, 5), (4, 6), (1, 7)
#: Bras `isole` : le MEME temoin, hors des anneaux 1 ET 2 de T1 (distance >= 3).
POS_VOISIN_LOIN = (0, 3)
ABILITY_1026 = 1026
#: Les deux bras : position du TEMOIN. Tout le reste est IDENTIQUE -- meme caster, meme tuile
#: cible, memes unites. La SEULE variable est l'occupation d'une tuile de l'anneau 1 de T1.
ARMS = {"voisin": POS_VOISIN, "isole": POS_VOISIN_LOIN}


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def dispose(rid) -> None:
    if rid is None:
        return
    try:
        B._rpc(B._resolve_session(), "disposeRunner", [{"runnerId": rid}], timeout=20)
    except Exception:
        pass


def run(arm: str = "voisin", seed: int = SEED, board: str = BOARD, keep: bool = False) -> dict:
    if arm not in ARMS:
        raise RuntimeError("bras inconnu : %s" % arm)
    pos_voisin = ARMS[arm]
    sf = str(PYDIR.parents[1] / "logs" / ("probe1026_face_decision_%s.json" % arm))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    argv = ["build", "--seed", str(int(seed)), "--board", str(board),
            "--p-units", CASTER,
            "--a-units", "%s,%s,%s" % (FOE_GROUPE, FOE_VOISIN, FOE_ISOLE),
            "--place", "%s:%d,%d" % (CASTER, POS_CASTER[0], POS_CASTER[1]),
            "--a-place", "%s:%d,%d" % (FOE_GROUPE, POS_T1[0], POS_T1[1]),
            "--a-place", "%s:%d,%d" % (FOE_VOISIN, pos_voisin[0], pos_voisin[1]),
            "--a-place", "%s:%d,%d" % (FOE_ISOLE, POS_T3[0], POS_T3[1]),
            "--state-file", sf]
    print("[1026] build %s" % " ".join(argv))
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE : %s" % " ".join(argv))
    rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId")
    sid = B._resolve_session()

    def rpc(method, body=None, timeout=120):
        return _unwrap(B._rpc(sid, method, [{**(body or {}), "runnerId": rid}],
                              timeout=timeout)) or {}

    out: dict = {"runnerId": rid, "arm": arm, "posVoisin": pos_voisin}
    try:
        dv = rpc("decisionView", {"maxRank": 32, "allAbilities": True}, 180)
        # ⚠ `tileMeta.tiles[]` ne porte PAS d'`id` : la correspondance `(col,row) -> entite-TUILE`
        # vient du contexte de DECISION (`AiDecisionContext.tile_id_by_pos`), meme voie que
        # `probe_302_2`. Une premiere redaction lisait `t["id"]` et rendait `None` partout.
        ids = {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or []) if u.get("alive")}
        for k in (CASTER, FOE_GROUPE, FOE_VOISIN, FOE_ISOLE):
            if k not in ids:
                raise RuntimeError("montage NON INSTALLE : %s absent (%s)" % (k, sorted(ids)))
        cid = ids[CASTER]
        out["ids"] = ids
        out["posByVis"] = {u.get("visualId"): ((u.get("pos") or {}).get("col"),
                                               (u.get("pos") or {}).get("row"))
                           for u in (dv.get("units") or []) if u.get("alive")}
        from engine import weights as W
        from engine.ai import context as AICTX
        from engine.playbook import scene as _scene

        def _seam(method, body, timeout=90):
            return _unwrap(B._rpc(sid, method, [body], timeout=timeout)) or {}

        mov = rpc("aiMovableTiles", {}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        predictor = _scene.build_predictor(_seam, rid)
        ctx = AICTX.build(_seam, rid, dv, mov_by_unit, cid, W.load(), predictor)
        tid_by_pos = dict(ctx.tile_id_by_pos or {})
        out["tileT1"] = tid_by_pos.get(POS_T1)
        out["tileT3"] = tid_by_pos.get(POS_T3)
        out["tileVoisin"] = tid_by_pos.get(POS_VOISIN)
        if out["tileT1"] is None or out["tileT3"] is None:
            raise RuntimeError("tuiles introuvables : %d entrees dans tile_id_by_pos"
                               % len(tid_by_pos))
        for nom, cible in (("T1_groupe", out["tileT1"]), ("T3_isole", out["tileT3"]),
                           ("unite_groupe", ids[FOE_GROUPE]), ("unite_isolee", ids[FOE_ISOLE])):
            r = rpc("pairUtility", {"unitId": cid, "targetId": int(cible),
                                    "abilityType": ABILITY_1026}, 120)
            out["u_%s" % nom] = r
            print("[1026] pairUtility(unit=%s, target=%s [%s], 1026) -> %s"
                  % (cid, cible, nom, json.dumps(r, sort_keys=True)[:600]))
    finally:
        if not keep:
            dispose(rid)
            out["runnerId"] = None
    return out


def _u(r) -> float:
    return float((r or {}).get("utility") or 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS) + ["all"], default="all")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    arms = sorted(ARMS) if a.arm == "all" else [a.arm]
    res = {}
    for arm in arms:
        res[arm] = run(arm=arm, seed=a.seed, board=a.board, keep=a.keep)
    print()
    print("=== VERDICT (terme PREDICTION du playbook 1026, cible = la TUILE de T1) ===")
    for arm in arms:
        o = res[arm]
        print("  bras=%-7s temoin@%s  u(T1_tuile)=%.6f  u(T1_unite)=%.6f  u(T3_isole)=%.6f"
              % (arm, o["posVoisin"], _u(o.get("u_T1_groupe")), _u(o.get("u_unite_groupe")),
                 _u(o.get("u_T3_isole"))))
        print("     playbookClass=%s  targetEntityType(tuile)=%s"
              % ((o.get("u_T1_groupe") or {}).get("playbookClass"),
                 (o.get("u_T1_groupe") or {}).get("targetEntityType")))
    if len(arms) == 2:
        uv, ui = _u(res["voisin"]["u_T1_groupe"]), _u(res["isole"]["u_T1_groupe"])
        t3v, t3i = _u(res["voisin"]["u_T3_isole"]), _u(res["isole"]["u_T3_isole"])
        print()
        print("  ECART sur T1 (la SEULE variable est l'occupation d'une tuile ring-1) : %+.6f"
              % (uv - ui))
        print("  TEMOIN T3 (aucune tuile de ses anneaux ne change) : %+.6f  <- doit etre 0"
              % (t3v - t3i))
        print()
        if abs(t3v - t3i) > 1e-9:
            print("VERDICT : MONTAGE NON SEPARANT -- le temoin T3 bouge aussi, une autre cause agit.")
            return 1
        if uv > ui:
            print("VERDICT : le natif RESOUT l'occupant des tuiles d'obus et SOMME leurs "
                  "contributions -> le port doit mapper tuile -> occupant.")
        elif abs(uv - ui) <= 1e-9:
            print("VERDICT : l'occupation du voisinage NE CHANGE RIEN -> le terme ne porte que sur "
                  "la cible, jamais sur les tuiles d'obus voisines.")
        else:
            print("VERDICT : l'utilite BAISSE avec un voisin occupe -- resultat non prevu, a "
                  "instruire avant tout port.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
