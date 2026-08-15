"""#894-r2 -- l'empreinte 3 TUILES ne vient PAS de l'unite : elle vient de la PLATEFORME du board,
et seul `BC.BossUnit` y amene le porteur.

CE QUE CE PROBE ETABLIT (et ce qu'il corrige de la fiche #894-r2). La fiche impute le refus
`CasterHas3Tiles` a << une variante guild-boss qui n'a pas l'empreinte 3 tuiles >>, substituee par
`--explicit-stats`. Les DEUX moities sont fausses :

  * `GuildBoss10Boss1AdmecBelisarius` n'est pas une variante substituee -- c'est le `visualId`
    d'`admecBossBelisarius` dans le gameconfig (LU : `gameconfig.unit('admecBossBelisarius')`).
    C'est la MEME unite, vue par son champ visuel ;
  * l'empreinte n'est pas une propriete de l'unite du tout. Elle est portee par le BOARD :
    `data/boards/global/GB_Belisarius_01.json` a `IsBossBoard = true` et
    `BossPlatforms = [{Size: 3, Tiles: [(3,7),(2,7),(3,8)], InitialSpawnPosition: true}]`.

MECANISME, LU AU DECOMPILE. `IdunBattle.Operations.SetupGameOperation$$AddBossUnit(bossPlatforms)` :

    plateforme = GetBossPlatform(this, bossPlatforms)         # null -> branche d'erreur
    tuiles     = [ query.<slot 0xa6>(t.Column, t.Row).Id  for t in plateforme.<+0x18> ]
    <spawn>(BC.BossUnit.UnitId, tuiles, GetPlayer(BC.BossUnit.Id), ...)   # LISTE de tuiles
    si BC.BossUnit.Health.HasValue         -> modifier (5, 2, 0)
    si BC.BossUnit.RemainingHealth.HasValue-> modifier (5, 0, 0) + ecriture du composant +0x10
    ApplyModifiers(this, entite, BC.BossUnit.Modifiers)

`AddPredefinedUnits`, lui, ne pose qu'UNE tuile. Le montage du harnais n'emprunte QUE cette
seconde voie (`--p-units` -> `initAndStart.playerUnits` ; `--a-units` -> `BC.PredefinedUnits`), et
`BC.BossUnit` vaut `null` dans `data/seed-bc.json` : il n'est ecrit NULLE PART. C'est cela, le
blocage `seeding` de #894-r2 -- une empreinte que le montage ne demande jamais.

FORME EXACTE DE `IdunBattle.Configuration.PredefinedBossUnit` (MESUREE, RPC `classFields`,
build `t6dpr4k06g` -- 56 octets, 5 champs) :

    Id              @0x10  PlayerId
    UnitId          @0x18  String
    Health          @0x20  Nullable<int>
    RemainingHealth @0x28  Nullable<int>
    Modifiers       @0x30  List<UnitModifier>

Usage :
    python probe_10018r1_bossunit_footprint.py            # monte et mesure `feet`
    python probe_10018r1_bossunit_footprint.py --temoin   # le MEME montage SANS BossUnit
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from rl_collect_batch import _resolve_session, _rpc, PLAYER_ID_HUMAN  # noqa: E402

PORTEUR = "admecBossBelisarius"
BOARD = "GB_Belisarius_01"
SOLAR_ATOMIZER = 1174          #: `ActiveAbilityType.SolarAtomizer`


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t) or {}).get("result") or {}


def seed_bc_avec_bossunit(dest: Path) -> Path:
    """Copie du seed BC partage, avec `BossUnit` RENSEIGNE. N'ecrit JAMAIS le seed partage."""
    src = REPO / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    bc = copy.deepcopy(bc)
    bc["BossUnit"] = {
        "Id": PLAYER_ID_HUMAN,          # `PlayerId` -- le boss doit etre A MOI pour etre PILOTE
        "UnitId": PORTEUR,              # String
        "Health": None,                 # Nullable<int> : absent -> aucun modifier (5,2,0)
        "RemainingHealth": None,        # Nullable<int> : absent -> aucun modifier (5,0,0)
        "Modifiers": [],                # List<UnitModifier>
    }
    dest.write_text(json.dumps(bc), encoding="utf-8")
    return dest


#: Bouche-trou de MON equipe. `initAndStart` exige des `playerUnits` ; quand le boss arrive par
#: `BC.BossUnit` il ne doit surtout PAS etre AUSSI dans `--p-units`, sinon il spawne DEUX FOIS --
#: une instance a 3 tuiles (la plateforme) et une a 1 (le placement ordinaire).
BOUCHE_TROU = "admecMarshall"


def build(sf: Path, seed_bc: Path | None, seed: int = 777) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
           "--state-file", str(sf),
           "--explicit-stats", PORTEUR,
           "--a-units", "admecDestroyer"]
    if seed_bc is None:
        # TEMOIN : le regime d'AVANT -- le porteur passe par `--p-units`, donc par
        # `initAndStart.playerUnits`, donc par une seule tuile.
        cmd += ["--p-units", PORTEUR]
    else:
        cmd += ["--p-units", BOUCHE_TROU, "--seed-bc", str(seed_bc)]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError("build KO (rc=%d) : %s" % (p.returncode, (p.stderr or "")[-700:]))
    return int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"])


#: `visualId` d'`admecBossBelisarius`, LU au gameconfig -- ce n'est PAS une variante substituee.
VISUAL_PORTEUR = "GuildBoss10Boss1AdmecBelisarius"


def mesurer(sid, rid) -> dict:
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {"unites": [], "porteurs": []}
    for u in (dv.get("units") or []):
        vis = str(u.get("visualId") or u.get("unitId") or "")
        pieds = u.get("feet")
        ligne = {"id": u.get("id"), "vis": vis,
                 "feet": (None if pieds is None else len(pieds)), "pos": u.get("pos")}
        out["unites"].append(ligne)
        if vis == VISUAL_PORTEUR:
            ligne["abilities"] = [(a.get("id"), a.get("kind"), a.get("usable"))
                                  for a in (u.get("abilities") or [])]
            out["porteurs"].append(ligne)
    # On interroge CHAQUE instance du porteur : c'est ce qui separe << l'empreinte est arrivee >>
    # de << une empreinte est arrivee, sur une AUTRE instance >>.
    for p in out["porteurs"]:
        rs = _r(sid, "abilityReason", {"runnerId": rid, "casterId": p["id"],
                                       "abilityType": SOLAR_ATOMIZER}, 60)
        p["raison"] = {k: rs.get(k) for k in ("casterReason", "targetReason", "ok")}
    return out


def run(avec_bossunit: bool, seed: int = 777) -> dict:
    sid = _resolve_session()
    tag = "avec" if avec_bossunit else "temoin"
    sf = REPO / "logs" / "runners" / ("bu10016-%s-%s.json" % (tag, uuid.uuid4().hex[:6]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    bc = None
    if avec_bossunit:
        bc = seed_bc_avec_bossunit(sf.with_name(sf.stem + "-bc.json"))
    rid = build(sf, bc, seed)
    try:
        out = mesurer(sid, rid)
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(sf)],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    out["rid"], out["bossunit"] = rid, avec_bossunit
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--temoin", action="store_true",
                    help="le MEME montage SANS BossUnit (le regime d'avant)")
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    out = run(not a.temoin, a.seed)
    print("=== #894-r2 -- empreinte du porteur (BossUnit %s, runner %s) ==="
          % ("ECRIT" if out["bossunit"] else "ABSENT", out["rid"]))
    for u in out["unites"]:
        print("  u%-4s %-34s feet=%s pos=%s" % (u["id"], u["vis"], u["feet"], u["pos"]))
    if not out["porteurs"]:
        print("  PORTEUR ABSENT du decisionView")
        return 1
    for p in out["porteurs"]:
        print("")
        print("  u%s feet=%s -- abilities %r" % (p["id"], p["feet"], p.get("abilities")))
        print("     cast SolarAtomizer : %r" % (p.get("raison"),))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
