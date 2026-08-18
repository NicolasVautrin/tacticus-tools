"""#1013-r1 -- LA PREVISION D'UN PORTEUR DE `ParagonSpear` EST-ELLE MAXEE ? (natif)

## L'hypothese, et pourquoi elle se tranche par UN observable

`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` rend, pour un porteur de
`0x5d6 = 1494 ParagonSpear`, le champ `<entities + 0xf8>` -- le parametre **`wasCrit`** d'
`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (position LUE dans la signature a 32
parametres, jamais comptee a l'oeil : le ctor y ecrit `*(undefined1 *)(this + 0xf8) = wasCrit`).

Or `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` NE PASSE PAS l'`AbilityEntities`
qu'il a recu : il en construit un NEUF -- `memset` a 0 sur ses 0x128 octets, puis `.ctor` avec
`caster = actor = <attaquant>`, `target = <cible>` et TOUS les autres parametres a ZERO. Donc
`wasCrit == false`, donc la branche rend `false` : **la prevision ne maxe pas**.

Si cette lecture est JUSTE, la prevision garde son AMPLITUDE et ne bouge pas d'un iota quand on
equipe la relique. Si elle est FAUSSE, la prevision est DEGENEREE (`min == max`) -- et le port,
qui ne porte que la branche effet `1185`, divergerait. Aucune arithmetique n'est requise.

## Les DEUX bras, et ce que le probe REFUSE plutot que de subir

Bras `AVEC` = `--equip-relic custoKyrus:ParagonSpear:1` ; bras `SANS` = le MEME montage, meme
seed, memes positions FORCEES, sans la relique.

  * la relique n'est pas REELLEMENT montee -- les trois ecritures de #237 echouent EN SILENCE.
    Controle DIRECT sur le capteur `combatSnapshot.units[].tertiary` (`ability`, `level`), jamais
    sur `decisionView.abilities` qui ne publie QUE les actives -> `REFUS` ;
  * la prevision de REFERENCE est deja degeneree -> les deux hypotheses y coincident, le montage
    ne separe rien -> `REFUS`.

⚠ ON COMPARE `totalDmg`, PAS `healthDmg`. `healthDmgMax` est CAPE par les PV RESTANTS de la cible
(`DamagePredictionResult.AccurateHealthDamage@0x58`), et dans le bras AVEC la lance a DEJA frappe
au turn-start -- la cible y a donc moins de PV. `totalDmg` (`@0x88`) ne porte pas ce cap : c'est
la grandeur que les deux bras peuvent comparer.

ASCII only. Usage :
  python probe_1013r1_max_out_prediction_live.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
REPO = ROOT.parents[1]

from rl_collect_batch import _resolve_session, _rpc          # noqa: E402

#: ETAT 2 de la gate relique : `custoKyrus` est DANS le pool rank 17 -> `--equip-relic` suffit,
#: aucune injection catalogue.
PORTEUR = "custoKyrus"
RELIQUE = "ParagonSpear"
RELIQUE_ID = 1494          # `TriggeredAbilityType` 0x5d6
VICTIME = "orksNob"
#: Niveau 1 : le SEUL palier qui separe les deux hypotheses de niveau (#1013 sec.5), et le seul
#: qui exerce le verrou `TryGetVariableArrayForLevel` (`0` = verrouille).
NIVEAU = 1
#: Positions FORCEES : sans elles la cible est hors de portee et `aiPredict` rend
#: `err: "get_Item: system error"` avec `dictCount: 0` -- un montage muet, pas un verdict.
POS_PORTEUR = "2,3"
POS_VICTIME = "3,3"


class MontageError(RuntimeError):
    pass


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t) or {}).get("result") or {}


def build(seed: int, board_id: str, avec_relique: bool):
    sf = REPO / "logs" / "runners" / ("p1013r1-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
           "--state-file", str(sf),
           "--p-units", PORTEUR, "--place", "%s:%s" % (PORTEUR, POS_PORTEUR),
           "--a-units", VICTIME, "--a-place", "%s:%s" % (VICTIME, POS_VICTIME)]
    if avec_relique:
        # #237 : les TROIS ecritures, posees APRES la normalisation -> le niveau joue est
        # EXACTEMENT celui demande (`buildNormalizedBC` l'ecraserait a 50 s'il etait pose avant).
        cmd += ["--equip-relic", "%s:%s:%d" % (PORTEUR, RELIQUE, NIVEAU)]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not sf.exists():
        raise MontageError("build KO (rc=%d) : %s" % (p.returncode, (p.stderr or "")[-500:]))
    return int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"]), sf


def bras(seed: int, board_id: str, avec_relique: bool) -> dict:
    sid = _resolve_session()
    rid, sf = build(seed, board_id, avec_relique)
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ids = {}
        for u in (dv.get("units") or []):
            vis = (u.get("visualId") or "")
            if vis.startswith(PORTEUR):
                ids["porteur"] = int(u["id"])
            elif vis.startswith(VICTIME):
                ids["victime"] = int(u["id"])
        if "porteur" not in ids or "victime" not in ids:
            raise MontageError("entites introuvables : %s" % sorted(ids))
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
        tert = None
        for u in (snap.get("units") or []):
            if int(u.get("entityId", -1)) == ids["porteur"]:
                tert = u.get("tertiary") or {}
        pred = _r(sid, "aiPredict", {"runnerId": rid, "unitId": ids["porteur"],
                                     "targetId": ids["victime"], "fresh": True}, 120)
        return {"tertiary": tert, "pred": pred.get("pred"), "err": pred.get("err"),
                "ids": ids}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        Path(sf).unlink(missing_ok=True)


def _total(p):
    if not isinstance(p, dict):
        return None
    lo, hi = p.get("totalDmgMin"), p.get("totalDmgMax")
    return None if not isinstance(lo, int) or not isinstance(hi, int) else (lo, hi)


def _sante(p):
    if not isinstance(p, dict):
        return None
    lo, hi = p.get("healthDmgMin"), p.get("healthDmgMax")
    return None if not isinstance(lo, int) or not isinstance(hi, int) else (lo, hi)


def run(seed: int, board_id: str) -> int:
    rc = 0
    avec = bras(seed, board_id, True)
    sans = bras(seed, board_id, False)
    t_avec, t_sans = _total(avec["pred"]), _total(sans["pred"])
    s_avec, s_sans = _sante(avec["pred"]), _sante(sans["pred"])
    print("== #1013-r1 %s (relique %s niveau %d) -> %s | board %s seed %d"
          % (PORTEUR, RELIQUE, NIVEAU, VICTIME, board_id, seed))
    print("   AVEC : tertiary=%s totalDmg=%s healthDmg=%s err=%s"
          % (avec["tertiary"], t_avec, s_avec, avec["err"]))
    print("   SANS : tertiary=%s totalDmg=%s healthDmg=%s err=%s"
          % (sans["tertiary"], t_sans, s_sans, sans["err"]))
    ta = avec["tertiary"] or {}
    ts = sans["tertiary"] or {}
    if not (ta.get("abilityHasValue") and int(ta.get("ability") or 0) == RELIQUE_ID
            and int(ta.get("level") or 0) == NIVEAU):
        print("REFUS : la relique n'est PAS montee (tertiary=%s) -- les trois ecritures de #237 "
              "echouent EN SILENCE, ce bras ne dit RIEN." % ta)
        return 2
    if ts.get("abilityHasValue"):
        print("REFUS : le bras SANS porte quand meme une tertiaire (%s) -- pas discriminant." % ts)
        return 2
    if t_avec is None or t_sans is None:
        print("REFUS : `aiPredict` ne rend pas de bornes (err AVEC=%s SANS=%s)."
              % (avec["err"], sans["err"]))
        return 2
    if t_sans[0] >= t_sans[1]:
        print("REFUS : la prevision de REFERENCE est deja degeneree %s -- les deux hypotheses y "
              "coincident, le montage ne separe rien." % (t_sans,))
        return 2
    # LE VERDICT. Une prevision maxee serait DEGENEREE (`GetBaseDamageFix64(is_max_out=True)` pose
    # `min = max`) ; la lecture de `PredictAttackRaw` dit qu'elle ne l'est pas.
    if t_avec[0] >= t_avec[1]:
        print("!! MAXEE : la prevision du porteur est degeneree %s -- la branche `ParagonSpear` "
              "MORD cote prediction, contre la lecture de `PredictAttackRaw`." % (t_avec,))
        rc |= 1
    if t_avec != t_sans:
        print("!! LA RELIQUE DEPLACE LA PREVISION : avec=%s sans=%s -- un canal non porte."
              % (t_avec, t_sans))
        rc |= 1
    print("VERDICT: %s" % ("PASS -- relique MONTEE (%s niveau %s) et prevision INCHANGEE %s : la "
                           "branche `ParagonSpear` est INERTE cote prediction."
                           % (ta.get("ability"), ta.get("level"), t_avec) if rc == 0
                           else "FAIL rc=%d" % rc))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    return run(a.seed, a.board)


if __name__ == "__main__":
    raise SystemExit(main())
