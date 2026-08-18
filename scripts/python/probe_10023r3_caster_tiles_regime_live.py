"""#10023-r3 -- CONFRONTATION LIVE du regime de `Tiles(CasterTiles)` sur un caster SEPT-HEX.

CE QUE CE PROBE TRANCHE, ET POURQUOI IL FALLAIT DU LIVE
--------------------------------------------------------
`IdunBattle.DSL.TargetsSelector$$SelectAllUnits` ouvre par une porte VIRTUELLE, relue verbatim
sur `t6dpr4k06g` :

    lVar8 = <slot 0x17 = Select>(this, entities);
    cVar5 = (**(code **)(*(longlong *)this + 0x278))(this, ...);   // slot 20 = get_ReturnsOnlyUnits
    if (cVar5 == '\\0') { ... foreach (e in lVar8) SelectUnit(this, e, sel) -> out.Add ... }
    return <lVar8 tel quel si la porte est VRAIE, sinon la liste resolue>;

Les slots sont LUS, pas deduits : `data/symbols/<build>/metadata/interface_slots.tsv` donne
`TargetsSelector 19 get_ReturnsOnlyTiles`, `TargetsSelector 20 get_ReturnsOnlyUnits`,
`TargetsSelector 23 Select` ; la vtable IL2CPP commence a `klass+0x138` par entrees de `0x10`,
donc `0x138 + 20*0x10 = 0x278` et `0x138 + 19*0x10 = 0x268`. Les deux offsets du binaire
concordent avec la table -- deux sources INDEPENDANTES.

`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` construit `<+0x58>` (`CasterTiles`) et
`<+0x60>` (`Target`) depuis des classes DISTINCTES. #10023-r1 a MESURE que `Target` est du regime
« rendue TELLE QUELLE » (19 casts de `1201 SquigMine` sur une tuile TOUJOURS vide). **Rien n'avait
mesure `CasterTiles`**, et c'est LUI que `1094 TheLantern` fait passer par `Tiles(origin)` avec une
empreinte de SEPT tuiles.

CETTE PROPRIETE N'EST PAS RESOLUBLE PAR LA TABLE DES SYMBOLES : IL2CPP DEDUPLIQUE les corps
triviaux `return 1` / `return 0`, et `data/symbols/<build>/frida/methods.tsv` est indexee par
ADRESSE -- elle ne porte que DEUX `get_ReturnsOnly*` pour tout le binaire (mesure a l'etage 0).
« L'ABSENCE d'une methode dans les tables ne prouve RIEN » : le slot de vtable sur l'INSTANCE est
la seule voie sure, et en l'absence de capteur (aucun reinject), l'observable est la SORTIE.

LE DISCRIMINANT, DERIVE (pas suppose)
--------------------------------------
`the_lantern_area_selector` (mirror de `TheLanternAbility$$ExecuteBehaviour`) :

    ring1  = SurroundingTiles(Target,      includeCenter=0, range=1)
    ring2  = SurroundingTiles(Target,      includeCenter=0, range=2)
    cring1 = SurroundingTiles(CasterTiles, includeCenter=0, range=1)
    area   = Unique( (Target + ring1) + (ring2 & cring1) )

Soit `F` l'empreinte du caster (7 tuiles) et `M` sa main tile. `SurroundingTiles(X, ic=0)` =
`disque1(X) op_Subtraction Tiles(X)`, donc :

    regime A (`CasterTiles.ReturnsOnlyUnits == FAUX`, ce que porte le mirror aujourd'hui) :
        Tiles(CasterTiles) = { GetMainTile(occupant) } = {M}   -> cring1 = disque1(F) \\ {M}
    regime B (VRAI) :
        Tiles(CasterTiles) = F  (chaque entite-tuile est SA PROPRE main tile) -> cring1 = disque1(F) \\ F

La seule difference est donc `F \\ {M}` -- les SIX autres pieds. Et comme `area` ne les consomme
que via `ring2 & cring1`, et qu'un pied a distance 1 de la cible est DEJA dans `ring1` :

    area_A \\ area_B  =  { P dans F \\ {M} : hexdist(P, cible) == 2 }

C'est un ENSEMBLE CALCULE avant le cast, et le probe REFUSE de conclure s'il est vide (une cible
qui ne discrimine rien rendrait un vert de construction).

LE MONTAGE -- et pourquoi l'empreinte n'arrive PAS par `--p-units`
-------------------------------------------------------------------
`IdunBattle.Operations.SetupGameOperation$$AddBossUnit` est la SEULE voie qui pose un porteur sur
une LISTE de tuiles (la `BossPlatform` du board) ; `AddPredefinedUnits` n'en pose qu'UNE. Monter
Mortarion par `--p-units` donnerait donc un caster MONO-HEX, sur lequel les deux regimes
COINCIDENT -- exactement le regime degenere qui a empeche #10023 de trancher. Le montage reprend
donc la voie mesuree par `probe_10018r1_bossunit_footprint.py` (#894-r2 / #10018-r1) : `BC.BossUnit`
ecrit dans une COPIE du seed BC (jamais le seed partage), board `GB_Mortarion_05` dont la
`BossPlatforms[0]` porte `Size: 7`.

Usage (session Frida deja warmee ; le probe dispose SES runners, jamais ceux des autres) :

    python probe_10023r3_caster_tiles_regime_live.py [--seed 777] [--board GB_Mortarion_05]

rc 0 = un regime est etabli et le mirror le porte ; rc 1 = le mirror porte le MAUVAIS regime, ou
aucune cible discriminante ; rc 2 = PAS MESURE (session/host/montage indisponible -- jamais
rabattu sur un vert). Sortie ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc, PLAYER_ID_HUMAN       # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402

ROOT = PYDIR.parents[1]

#: `deathBossMortarion` -- SEUL porteur de `1094 TheLantern` (`unit_map find --ability TheLantern`).
BOSS = "deathBossMortarion"
#: Son `visualId` au gameconfig : c'est sous CE nom que le `decisionView` le publie.
BOSS_VIS = "GuildBoss5Boss1DeathMortarion"
#: Palier de stats explicites -- meme que `test_888_mortarion_boss_abilities_live.py`.
BOSS_STATS = BOSS + ":4"
#: SA carte : `BossPlatforms[0].Size == 7` (LU dans `data/boards/global/GB_Mortarion_05.json`).
BOARD = "GB_Mortarion_05"
#: Bouche-trou de MON equipe : `initAndStart` exige des `playerUnits`, et le boss ne doit surtout
#: pas y figurer AUSSI (il spawnerait deux fois -- une instance a 7 tuiles, une a 1).
BOUCHE_TROU = "admecMarshall"
ADVERSE = "admecDestroyer"

THE_LANTERN = int(ActiveAbilityType.TheLantern)                   # 1094
PENDING_TARGET = int(EffectType.TheLantern_PendingTarget)         # 0x4ab = 1195


def _r(sid, method, body, t=120):
    return (_rpc(sid, method, [body], timeout=t) or {}).get("result") or {}


# --------------------------------------------------------------------------------------------- #
#  Montage
# --------------------------------------------------------------------------------------------- #

def seed_bc_avec_bossunit(dest: Path) -> Path:
    """Copie du seed BC partage avec `BossUnit` renseigne. N'ECRIT JAMAIS le seed partage.

    `Id = PLAYER_ID_HUMAN` : le boss doit etre A MOI pour que `applyAction` le fasse caster a mon
    tour (le RPC ne verifie pas la propriete, mais le natif refuse un cast hors du tour du camp)."""
    bc = copy.deepcopy(json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8")))
    bc["BossUnit"] = {"Id": PLAYER_ID_HUMAN, "UnitId": BOSS,
                      "Health": None, "RemainingHealth": None, "Modifiers": []}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(bc), encoding="utf-8")
    return dest


def build(state_file: Path, seed_bc: Path, seed: int, board: str):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state_file), "--no-ai",
            "--seed-bc", str(seed_bc), "--explicit-stats", BOSS_STATS,
            "--p-units", BOUCHE_TROU, "--a-units", ADVERSE]
    env = dict(os.environ)
    env.setdefault("TACTICUS_ALLOW_ROSTER_DEFICIT", "1")
    state_file.unlink(missing_ok=True)
    res = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True, timeout=600,
                         env=env)
    if res.returncode != 0 or not state_file.exists():
        return None, ((res.stdout or "")[-1800:] + (res.stderr or "")[-900:])
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"]), None


# --------------------------------------------------------------------------------------------- #
#  Lecture d'etat
# --------------------------------------------------------------------------------------------- #

def _pos(u):
    p = (u or {}).get("pos") or {}
    return None if p.get("col") is None else (int(p["col"]), int(p["row"]))


def empreinte(board: Board, u: dict) -> list:
    """Les tuiles de l'unite, en (col,row). `decisionView.units[].feet` est la LISTE des tuiles de
    l'empreinte ; `pos` est la MAIN TILE. Les deux sont lus, aucun n'est deduit de l'autre."""
    out = []
    for f in (u.get("feet") or []):
        if isinstance(f, dict) and f.get("col") is not None:
            out.append((int(f["col"]), int(f["row"])))
        elif isinstance(f, int):
            c = board.coord(f)
            if c is not None:
                out.append((int(c[0]), int(c[1])))
    p = _pos(u)
    if p is not None and p not in out:
        out.insert(0, p)
    return out


def tuiles_marquees(sid, rid, board: Board) -> list:
    """Tuiles portant un effet ACTIF `1195 TheLantern_PendingTarget`, en (col,row).

    Source : `tileMeta` (elevation + terrain + EFFETS par tuile ; son substrat est
    `frida/hooks/.../effects.ts::readEffectsByTile`). Rend `None` si le RPC ne publie aucun canal
    d'effet -- un `[]` fabrique depuis une NON-MESURE serait indistinguable d'un cast sans effet."""
    meta = _r(sid, "tileMeta", {"runnerId": rid}, 120)
    tuiles = meta.get("tiles") if isinstance(meta, dict) else None
    if not tuiles:
        return None
    vu_un_canal = False
    out = []
    for t in tuiles:
        effs = t.get("effects")
        if effs is None:
            continue
        vu_un_canal = True
        noms = []
        for e in effs:
            if isinstance(e, dict):
                noms.append(str(e.get("name") or e.get("effectType") or e.get("type") or ""))
            else:
                noms.append(str(e))
        if any(str(PENDING_TARGET) == n or "TheLantern_PendingTarget" in n for n in noms):
            c = (t.get("col"), t.get("row"))
            if c[0] is None and t.get("id") is not None:
                c = board.coord(int(t["id"]))
            if c and c[0] is not None:
                out.append((int(c[0]), int(c[1])))
    return out if vu_un_canal else None


# --------------------------------------------------------------------------------------------- #
#  Le discriminant
# --------------------------------------------------------------------------------------------- #

def ecart_des_deux_regimes(feet: list, main: tuple, cible: tuple) -> list:
    """`area_A \\ area_B` = les pieds NON-main a distance hex EXACTEMENT 2 de la cible.

    Derivation en tete de module. Un pied a distance 1 est deja dans `ring1` (donc dans les deux
    aires), un pied a distance >= 3 n'est dans aucun `ring2`."""
    return sorted(p for p in feet if p != main and hexgeo.distance(p, cible) == 2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--garder", action="store_true", help="ne PAS disposer le runner (debug)")
    a = ap.parse_args(argv)

    try:
        sid = _resolve_session()
    except Exception as exc:                                       # noqa: BLE001
        print("[10023-r3-live] NON MESURE : session Frida introuvable (%s) -- rc 2" % exc)
        return 2
    if sid is None:
        print("[10023-r3-live] NON MESURE : aucune session running -- rc 2")
        return 2

    tag = uuid.uuid4().hex[:6]
    sf = ROOT / "logs" / "runners" / ("p10023r3-%s.json" % tag)
    bc = seed_bc_avec_bossunit(sf.with_name(sf.stem + "-bc.json"))
    rid, err = build(sf, bc, a.seed, a.board)
    if rid is None:
        print("[10023-r3-live] NON MESURE : build KO -- rc 2\n%s" % (err or ""))
        return 2
    print("[10023-r3-live] session=%s runner=%s board=%s seed=%d" % (sid, rid, a.board, a.seed))

    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
        if not bg.get("tiles"):
            print("[10023-r3-live] NON MESURE : boardGraph vide -- rc 2")
            return 2
        board = Board(bg["tiles"], adjacency="native_sym")
        idof = {(t["col"], t["row"]): t["id"] for t in board.by_id.values()}

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        boss = next((u for u in (dv.get("units") or [])
                     if str(u.get("visualId") or "") == BOSS_VIS and u.get("alive")), None)
        if boss is None:
            print("[10023-r3-live] NON MESURE : %s absent du decisionView "
                  "(vus : %r) -- rc 2"
                  % (BOSS_VIS, sorted({str(u.get('visualId')) for u in (dv.get('units') or [])})))
            return 2
        feet = empreinte(board, boss)
        main_tile = _pos(boss)
        print("[10023-r3-live] boss u%s pos=%s feet=%d %s"
              % (boss.get("id"), main_tile, len(feet), feet))
        if len(feet) < 2:
            print("[10023-r3-live] NON MESURE : le boss est MONO-HEX (feet=%d) -- les deux regimes "
                  "coincident, ce montage ne peut rien trancher. `BC.BossUnit` n'a pas pris, ou la "
                  "`BossPlatform` du board n'a pas ete consommee. -- rc 2" % len(feet))
            return 2

        # --------- cibles legales, et laquelle discrimine
        at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": boss["id"],
                                        "abilityType": THE_LANTERN, "allAbilities": True}, 150)
        cibles = []
        for bloc in (at.get("abilities") or []):
            if int(bloc.get("abilityType") or bloc.get("id") or -1) != THE_LANTERN:
                continue
            for src in ("fromHere", "targets", "tiles", "afterMove"):
                for e in (bloc.get(src) or []):
                    c = None
                    if isinstance(e, dict):
                        if e.get("col") is not None:
                            c = (int(e["col"]), int(e["row"]))
                        elif e.get("tileId") is not None:
                            c = board.coord(int(e["tileId"]))
                        elif e.get("targetTileId") is not None:
                            c = board.coord(int(e["targetTileId"]))
                    elif isinstance(e, int):
                        c = board.coord(e)
                    if c and tuple(c) not in cibles:
                        cibles.append(tuple(c))
        print("[10023-r3-live] abilityTargets : %d tuile(s) ciblable(s) publiee(s)" % len(cibles))
        if not cibles:
            # Repli MESURE, pas devine : toute tuile marchable du board, filtree par
            # `abilityReason` (le gate natif), ce qui reste une lecture du natif.
            print("[10023-r3-live] repli : balayage des tuiles marchables via `abilityReason`")
            cibles = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

        classees = []
        for c in cibles:
            ec = ecart_des_deux_regimes(feet, main_tile, c)
            if ec:
                classees.append((len(ec), c, ec))
        classees.sort(key=lambda x: (-x[0], x[1]))
        if not classees:
            print("[10023-r3-live] ROUGE : AUCUNE cible ne discrimine les deux regimes "
                  "(aucun pied non-main a distance 2 d'une tuile ciblable). Le montage ne peut "
                  "rien trancher -- ce n'est pas un succes.")
            return 1
        print("[10023-r3-live] %d cible(s) discriminante(s) ; meilleures : %s"
              % (len(classees), [(c, n) for (n, c, _e) in classees[:5]]))

        # --------- le cast
        verdicts = []
        for (n, cible, ec) in classees[:3]:
            tid = idof.get(cible)
            rs = _r(sid, "abilityReason", {"runnerId": rid, "casterId": boss["id"],
                                           "abilityType": THE_LANTERN,
                                           "targetTileId": tid}, 60)
            avant = tuiles_marquees(sid, rid, board)
            act = _r(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": boss["id"], "abilityType": THE_LANTERN,
                "to": {"col": int(cible[0]), "row": int(cible[1])}}}, 120)
            a0 = (act.get("actions") or [{}])[0] if isinstance(act, dict) else {}
            apres = tuiles_marquees(sid, rid, board)
            if apres is None:
                print("[10023-r3-live] NON MESURE : `tileMeta` ne publie aucun canal d'effet par "
                      "tuile -- l'observable n'existe pas par ce RPC. -- rc 2")
                return 2
            neuves = sorted(set(apres) - set(avant or []))
            print("")
            print("[10023-r3-live] cible=%s tid=%s ok=%s reason=%r"
                  % (cible, tid, a0.get("ok"), {k: rs.get(k) for k in
                                                ("casterReason", "targetReason", "ok")}))
            print("[10023-r3-live]   ecart des deux regimes (pieds non-main a d=2) : %s" % (ec,))
            print("[10023-r3-live]   tuiles 1195 NEUVES (%d) : %s" % (len(neuves), neuves))
            if not neuves:
                verdicts.append(("SANS EFFET", cible, neuves, ec))
                continue
            porte = [p for p in ec if p in set(neuves)]
            if len(porte) == len(ec):
                verdicts.append(("REGIME_A", cible, neuves, ec))
            elif not porte:
                verdicts.append(("REGIME_B", cible, neuves, ec))
            else:
                verdicts.append(("MIXTE", cible, neuves, ec))
            break                                    # un cast suffit : l'effet reste pose

        print("")
        if not verdicts or verdicts[0][0] == "SANS EFFET":
            print("[10023-r3-live] NON MESURE : le cast n'a pose AUCUN effet 1195 -- le natif a "
                  "refuse (gate de ciblage) ou l'observable n'est pas celui-la. -- rc 2")
            return 2
        v, cible, neuves, ec = verdicts[0]
        if v == "REGIME_A":
            print("[10023-r3-live] VERT : les %d pied(s) non-main a distance 2 SONT dans l'aire "
                  "marquee => `Tiles(CasterTiles)` ne retranche QUE la main tile => "
                  "`CasterTiles.ReturnsOnlyUnits == FAUX`. C'est EXACTEMENT le regime que porte "
                  "`engine/dsl/base.py::_main_tiles` : #10023 est CONFRONTE." % len(ec))
            return 0
        if v == "REGIME_B":
            print("[10023-r3-live] ROUGE : AUCUN des %d pied(s) non-main a distance 2 n'est dans "
                  "l'aire marquee => `Tiles(CasterTiles)` retranche TOUTE l'empreinte => "
                  "`CasterTiles.ReturnsOnlyUnits == VRAI`. Le mirror actuel retranche UNE tuile : "
                  "il est FAUX sur ce call-site." % len(ec))
            return 1
        print("[10023-r3-live] ROUGE : verdict MIXTE (%d/%d pieds marques) -- ni l'un ni l'autre "
              "des deux regimes. Un troisieme etage intervient : ne rien conclure." % (
                  len([p for p in ec if p in set(neuves)]), len(ec)))
        return 1
    finally:
        if not a.garder:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception as exc:                               # noqa: BLE001
                print("[10023-r3-live] disposeRunner a leve (%s)" % exc)


if __name__ == "__main__":
    raise SystemExit(main())
