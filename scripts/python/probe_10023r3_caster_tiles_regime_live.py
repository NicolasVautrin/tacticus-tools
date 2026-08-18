"""#10023-r3 -- CONFRONTATION LIVE du regime de `Tiles(CasterTiles)` sur un caster SEPT-HEX.

CE QUE CE PROBE TRANCHE, ET POURQUOI IL FALLAIT DU LIVE
--------------------------------------------------------
`IdunBattle.DSL.TargetsSelector$$SelectAllUnits` ouvre par une porte VIRTUELLE, relue verbatim
sur `t6dpr4k06g` :

    lVar8 = <slot 0x17 = Select>(this, entities);
    cVar5 = (**(code **)(*(longlong *)this + 0x278))(this, ...);   // slot 20 = get_ReturnsOnlyUnits
    if (cVar5 == '\\0') { ... foreach (e in lVar8) SelectUnit(this, e, sel) -> out.Add ... }
    return <lVar8 TEL QUEL si la porte est VRAIE, sinon la liste resolue>;

Les slots sont LUS, pas deduits : `data/symbols/<build>/metadata/interface_slots.tsv` donne
`TargetsSelector 19 get_ReturnsOnlyTiles`, `TargetsSelector 20 get_ReturnsOnlyUnits`,
`TargetsSelector 23 Select` ; la vtable IL2CPP commence a `klass+0x138` par entrees de `0x10`,
donc `0x138 + 20*0x10 = 0x278` et `0x138 + 19*0x10 = 0x268` -- les deux offsets du binaire
concordent avec la table, deux sources INDEPENDANTES.

`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` construit `<+0x58>` (`CasterTiles`) et
`<+0x60>` (`Target`) depuis des classes DISTINCTES. #10023-r1 a MESURE que `Target` est du regime
« rendue TELLE QUELLE » (19 casts de `1201 SquigMine` sur une tuile TOUJOURS vide). **Rien n'avait
mesure `CasterTiles`**, et c'est lui que `1094 TheLantern` fait passer par `Tiles(origin)` avec une
empreinte de SEPT tuiles.

CETTE PROPRIETE N'EST PAS RESOLUBLE PAR LA TABLE DES SYMBOLES : IL2CPP DEDUPLIQUE les corps
triviaux `return 1` / `return 0`, et `data/symbols/<build>/frida/methods.tsv` est indexee par
ADRESSE -- elle ne porte que DEUX `get_ReturnsOnly*` pour tout le binaire, aucun `ReturnsOnlyUnits`.
« L'ABSENCE d'une methode dans les tables ne prouve RIEN » : sans capteur (aucun reinject
autorise), l'observable est la SORTIE.

LE DISCRIMINANT, DERIVE (pas suppose)
--------------------------------------
`the_lantern_area_selector` (mirror de `TheLanternAbility$$ExecuteBehaviour`) :

    ring1  = SurroundingTiles(Target,      includeCenter=0, range=1)
    ring2  = SurroundingTiles(Target,      includeCenter=0, range=2)
    cring1 = SurroundingTiles(CasterTiles, includeCenter=0, range=1)
    area   = Unique( (Target + ring1) + (ring2 & cring1) )

Soit `F` l'empreinte du caster (7 tuiles) et `M` sa main tile. `SurroundingTiles(X, ic=0)` =
`disque1(X) op_Subtraction Tiles(X)`, donc :

    regime A (`CasterTiles.ReturnsOnlyUnits` FAUX -- ce que porte le mirror aujourd'hui) :
        Tiles(CasterTiles) = { GetMainTile(occupant) } = {M}  -> cring1 = disque1(F) \\ {M}
    regime B (VRAI) :
        Tiles(CasterTiles) = F (chaque entite-tuile est SA PROPRE main tile)
                                                             -> cring1 = disque1(F) \\ F

La seule difference est `F \\ {M}` -- les SIX autres pieds. Et comme `area` ne les consomme que via
`ring2 & cring1`, et qu'un pied a distance 1 de la cible est DEJA dans `ring1` :

    area_A \\ area_B  =  { P dans F \\ {M} : hexdist(P, cible) == 2 }

C'est un ENSEMBLE CALCULE avant le cast, et le probe REFUSE de conclure s'il est vide.

⚠ LA MAIN TILE EST `feet[0]`, PAS `pos`. `decisionView.units[].pos` est le DERNIER pied projete
(`runner/snapshot.py::_load_feet` le documente, et la mesure le confirme : `pos = (3,8)` pour
`feet = [(4,8), ..., (3,8)]`). Prendre `pos` pour la main tile deplacerait l'ensemble discriminant.

L'EXPLICATION CONCURRENTE, ET COMMENT ELLE EST ECARTEE
-------------------------------------------------------
Un pied absent de l'aire s'expliquerait AUSSI par un filtre d'OCCUPATION -- les pieds sont les
seules tuiles occupees a distance 2 de la cible. Deux crans l'ecartent :

  * LECTURE. `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`
    n'appelle `IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable` que sous le flag `+0x50`
    (`onlyMovable`), et `TheLanternAbility$$ExecuteBehaviour` passe `onlyMovable = 0` aux trois
    `SurroundingTiles` (octet bas mis a zero au call-site). `IdunBattle.Core.Services.TileUtil$$IsTileValidForList`,
    lui, ne lit que `tileComponent+0x41` (mur), `IsWalkable` et -- sous `checkElevation`, ici a 0 --
    l'ecart d'elevation. **Aucun filtre d'occupation.**
  * MESURE (`--controle`). On repose l'unite adverse, par `--a-place` (donc SANS consommer
    d'activation), sur une tuile de `ring2 & cring1` qui etait marquee au bras de reference. Si
    elle reste marquee, l'occupation ne filtre pas et l'absence du pied n'a plus qu'une cause.

LE MONTAGE -- et pourquoi l'empreinte n'arrive PAS par `--p-units`
-------------------------------------------------------------------
`IdunBattle.Operations.SetupGameOperation$$AddBossUnit` est la SEULE voie qui pose un porteur sur
une LISTE de tuiles (la `BossPlatform` du board) ; `AddPredefinedUnits` n'en pose qu'UNE. Monter
Mortarion par `--p-units` donnerait donc un caster MONO-HEX, sur lequel les deux regimes
COINCIDENT -- exactement le regime degenere qui a empeche #10023 de trancher. Le montage reprend la
voie mesuree par `probe_10018r1_bossunit_footprint.py` (#894-r2 / #10018-r1) : `BC.BossUnit` ecrit
dans une COPIE du seed BC (jamais le seed partage), board `GB_Mortarion_05` dont la
`BossPlatforms[0]` porte `Size: 7`.

Usage (session Frida deja warmee ; le probe dispose SES runners, jamais ceux des autres) :

    python probe_10023r3_caster_tiles_regime_live.py [--seed 777] [--board GB_Mortarion_05]

rc 0 = un regime est etabli ET le mirror le porte ; rc 1 = le mirror porte le MAUVAIS regime, ou
aucune cible discriminante, ou le controle d'occupation invalide la mesure ; rc 2 = PAS MESURE
(session/host/montage indisponible -- jamais rabattu sur un vert). Sortie ASCII only (cp1252).
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
#: Palier de stats explicites -- le meme que `test_888_mortarion_boss_abilities_live.py`.
BOSS_STATS = BOSS + ":4"
#: SA carte : `BossPlatforms[0].Size == 7` (LU dans `data/boards/global/GB_Mortarion_05.json`).
BOARD = "GB_Mortarion_05"
#: Bouche-trou de MON equipe : `initAndStart` exige des `playerUnits`, et le boss ne doit surtout
#: pas y figurer AUSSI (il spawnerait DEUX fois -- une instance a 7 tuiles, une a 1).
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

    `Id = PLAYER_ID_HUMAN` : le boss doit etre A MOI pour que le cast parte de MON tour."""
    bc = copy.deepcopy(json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8")))
    bc["BossUnit"] = {"Id": PLAYER_ID_HUMAN, "UnitId": BOSS,
                      "Health": None, "RemainingHealth": None, "Modifiers": []}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(bc), encoding="utf-8")
    return dest


def build(state_file: Path, seed_bc: Path, seed: int, board: str, a_place=None):
    """`--a-place` pose l'unite adverse sur la tuile demandee par `AddUnitMessage`, donc SANS
    consommer d'activation -- c'est ce qui rend le bras de controle comparable au bras de
    reference (meme tour, meme etat de flags)."""
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state_file), "--no-ai",
            "--seed-bc", str(seed_bc), "--explicit-stats", BOSS_STATS,
            "--p-units", BOUCHE_TROU, "--a-units", ADVERSE]
    if a_place is not None:
        argv += ["--a-place", "%s:%d,%d" % (ADVERSE, a_place[0], a_place[1])]
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


def empreinte(u: dict) -> list:
    """`decisionView.units[].feet` normalise en `(col,row)` -- capteur `#419-r1-tr10-r2`
    (`projection.ts::readEntityFeet` = `IdunBattle.Entities.EntityExtensions$$GetTiles`), donc
    l'ordre des PIEDS. `feet[0]` est la MAIN TILE ; `pos`, lui, est le DERNIER pied projete."""
    out = []
    for f in (u.get("feet") or []):
        if isinstance(f, dict) and f.get("col") is not None:
            out.append((int(f["col"]), int(f["row"])))
    if not out:
        p = _pos(u)
        out = [] if p is None else [p]
    return out


def tuiles_marquees(sid, rid, board: Board):
    """Tuiles portant un effet ACTIF `1195 TheLantern_PendingTarget`, en `(col,row)`.

    Source : `tileMeta` (elevation + terrain + EFFETS par tuile ; substrat
    `frida/hooks/features/.../effects.ts::readEffectsByTile`). Rend `None` si AUCUNE tuile ne
    publie de canal `effects` -- un `[]` fabrique depuis une NON-MESURE serait indistinguable d'un
    cast sans effet. On apparie par l'ORDINAL `effectType`, pas par le libelle."""
    meta = _r(sid, "tileMeta", {"runnerId": rid}, 120)
    tuiles = meta.get("tiles") if isinstance(meta, dict) else None
    if not tuiles:
        return None
    vu, out = False, []
    for t in tuiles:
        effs = t.get("effects")
        if effs is None:
            continue
        vu = True
        if any(isinstance(e, dict) and int(e.get("effectType") or -1) == PENDING_TARGET
               for e in effs):
            c = (t.get("col"), t.get("row"))
            if c[0] is None and t.get("id") is not None:
                c = board.coord(int(t["id"]))
            if c and c[0] is not None:
                out.append((int(c[0]), int(c[1])))
    return sorted(out) if vu else None


def cibles_legales(sid, rid, unit_id: int) -> list:
    """Les tuiles que le NATIF declare ciblables pour `1094 TheLantern`, en `(col,row)`.

    Structure LUE : `abilityTargets.units[].abilities[]`, chaque entree portant `abilityId`,
    `targets` (ce tour, DEPLACEMENT inclus) et `fromHere` (sans bouger). On prend `fromHere`
    d'abord : le cast qui suit est alors immediat, donc aucune activation entre mesure et cast.
    Un element vaut `{kind: "tile", tile: {col,row}, targetId: <tileId>}`."""
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": int(unit_id),
                                    "allAbilities": True}, 150)
    ici, apres_move = [], []
    for u in (at.get("units") or []):
        if int(u.get("unitId") or -1) != int(unit_id):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId") or -1) != THE_LANTERN:
                continue
            for cle, dest in (("fromHere", ici), ("targets", apres_move)):
                for e in (ab.get(cle) or []):
                    tl = e.get("tile") if isinstance(e, dict) else None
                    if isinstance(tl, dict) and tl.get("col") is not None:
                        c = (int(tl["col"]), int(tl["row"]))
                        if c not in dest:
                            dest.append(c)
    return ici or apres_move


# --------------------------------------------------------------------------------------------- #
#  Le discriminant
# --------------------------------------------------------------------------------------------- #

def _filtres(sid, rid, board: Board):
    """`{(col,row): passe}` -- les TROIS gates de `SurroundingTiles`, LUS et non supposes :
    `tileComponent+0x41` (mur, INCONDITIONNEL), `tileComponent+0x40` (fog, INCONDITIONNEL) et
    `IsWalkable` (arme ici, `includeNonWalkable = 0`). Aucun filtre d'OCCUPATION : le decompile de
    `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` ne teste `IsEmptyOrSteppable` que
    sous `onlyMovable`, et `TheLanternAbility$$ExecuteBehaviour` le passe a 0."""
    meta = _r(sid, "tileMeta", {"runnerId": rid}, 120)
    out = {}
    for t in (meta.get("tiles") or []):
        c = (t.get("col"), t.get("row"))
        if c[0] is None:
            continue
        tid = board.id_at(int(c[0]), int(c[1]))
        ok = (not t.get("isWall")) and (not t.get("isInFog"))
        if tid is not None:
            ok = ok and bool(board.walkable(tid))
        out[(int(c[0]), int(c[1]))] = bool(ok)
    return out


def _disque(centres, r, passe):
    """Union des disques hex de rayon `r` autour de `centres`, filtree. `passe` est la table des
    trois gates : une tuile absente de la table n'existe pas sur ce board."""
    return {t for t, ok in passe.items()
            if ok and any(hexgeo.distance(t, c) <= r for c in centres)}


def aires_predites(feet, main, tgt, passe):
    """`(area_A, area_B)` -- les deux regimes, calcules de bout en bout.

    C'est la DECOMPOSITION PAR ETAGE : on ne compare pas UNE tuile, on compare l'AIRE ENTIERE.
    Un accord sur les 9 tuiles vaut infiniment plus qu'un desaccord sur une seule, qui pourrait
    tenir a un troisieme etage (mur, fog, elevation) qu'on aurait mal lu."""
    ring1 = _disque([tgt], 1, passe) - {tgt}
    ring2 = _disque([tgt], 2, passe) - {tgt}
    d1F = _disque(feet, 1, passe)
    cring_a = d1F - {main}
    cring_b = d1F - set(feet)
    base = {tgt} | ring1
    return (base | (ring2 & cring_a)), (base | (ring2 & cring_b))


def ecart_des_deux_regimes(feet: list, main: tuple, cible: tuple) -> list:
    """`area_A \\ area_B` = les pieds NON-main a distance hex EXACTEMENT 2 de la cible.

    Derivation en tete de module. Un pied a distance 1 est deja dans `ring1` (donc dans les DEUX
    aires), un pied a distance >= 3 n'entre dans aucun `ring2`."""
    return sorted(p for p in feet if p != main and hexgeo.distance(p, cible) == 2)


def caster_et_lire(sid, rid, board, boss_id, cible):
    """Cast tile-target + delta des tuiles marquees. Rend `(neuves, ok, avant, apres)`."""
    avant = tuiles_marquees(sid, rid, board)
    act = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(boss_id), "abilityType": THE_LANTERN,
        "to": {"col": int(cible[0]), "row": int(cible[1])}}}, 150)
    a0 = (act.get("actions") or [{}])[0] if isinstance(act, dict) else {}
    apres = tuiles_marquees(sid, rid, board)
    if apres is None or avant is None:
        return None, bool(a0.get("ok")), avant, apres
    return sorted(set(apres) - set(avant)), bool(a0.get("ok")), avant, apres


def un_bras(sid, seed, board_id, tag, a_place=None, cible_imposee=None, occuper=None):
    """Monte un runner, caste, rend le dictionnaire de mesure. Dispose TOUJOURS son runner.

    `occuper=(col,row)` : deplace MON bouche-trou sur cette tuile AVANT le cast. C'est MON
    activation qui est consommee (pas celle du boss, qui reste dans `toActivate`), donc le cast
    part du meme tour que le bras de reference. On passe par `applyAction move` et non par
    `--a-place` parce que le board de BOSS refuse tout placement hors zone autorisee
    (`AddUnitOperation$$Execute` rend NUL en silence : tuile reservee / pending drafting / fog)."""
    sf = ROOT / "logs" / "runners" / ("p10023r3-%s-%s.json" % (tag, uuid.uuid4().hex[:6]))
    bc = seed_bc_avec_bossunit(sf.with_name(sf.stem + "-bc.json"))
    rid, err = build(sf, bc, seed, board_id, a_place=a_place)
    if rid is None:
        return {"erreur": "build KO : %s" % (err or "")[-900:]}
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
        if not bg.get("tiles"):
            return {"erreur": "boardGraph vide"}
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        boss = next((u for u in (dv.get("units") or [])
                     if str(u.get("visualId") or "") == BOSS_VIS and u.get("alive")), None)
        if boss is None:
            return {"erreur": "%s absent du decisionView (vus %r)"
                              % (BOSS_VIS, sorted({str(u.get('visualId'))
                                                   for u in (dv.get('units') or [])}))}
        feet = empreinte(boss)
        if len(feet) < 2:
            return {"erreur": "le boss est MONO-HEX (feet=%d) : les deux regimes coincident, ce "
                              "montage ne peut rien trancher (BC.BossUnit non consomme ?)"
                              % len(feet)}
        main = feet[0]
        occupant = None
        if occuper is not None:
            bt = next((u for u in (dv.get("units") or [])
                       if u.get("alive") and u.get("owner") == boss.get("owner")
                       and u.get("id") != boss.get("id")), None)
            if bt is None:
                return {"erreur": "aucune unite alliee a deplacer pour occuper %r" % (occuper,)}
            _r(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(bt["id"]),
                "to": {"col": int(occuper[0]), "row": int(occuper[1])}}}, 90)
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            boss = next((u for u in (dv.get("units") or [])
                         if str(u.get("visualId") or "") == BOSS_VIS and u.get("alive")), boss)
            occupant = next((_pos(u) for u in (dv.get("units") or [])
                             if u.get("id") == int(bt["id"])), None)
        etat_tuiles = {_pos(u): u.get("id") for u in (dv.get("units") or []) if u.get("alive")}
        cibles = [cible_imposee] if cible_imposee else cibles_legales(sid, rid, boss["id"])
        if not cibles:
            return {"erreur": "aucune tuile ciblable declaree par le natif pour 1094"}
        classees = sorted(((len(ecart_des_deux_regimes(feet, main, c)), c) for c in cibles),
                          key=lambda x: (-x[0], x[1]))
        n, cible = classees[0]
        ec = ecart_des_deux_regimes(feet, main, cible)
        passe = _filtres(sid, rid, board)
        aire_a, aire_b = aires_predites(feet, main, cible, passe)
        neuves, ok, _av, _ap = caster_et_lire(sid, rid, board, boss["id"], cible)
        return {"aire_a": sorted(aire_a), "aire_b": sorted(aire_b),
                "rid": rid, "board": board, "boss": boss["id"], "feet": feet, "main": main,
                "occupant": occupant, "occupees": sorted(p for p in etat_tuiles if p),
                "cibles": cibles, "cible": cible, "ecart": ec,
                "neuves": neuves, "ok": ok, "currentPlayer": dv.get("currentPlayer"),
                "owner": boss.get("owner")}
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception as exc:                                   # noqa: BLE001
            print("[10023-r3-live] disposeRunner(%s) a leve (%s)" % (rid, exc))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--sans-controle", action="store_true",
                    help="ne joue QUE le bras de reference (debug ; le verdict reste SUSPENDU)")
    a = ap.parse_args(argv)

    try:
        sid = _resolve_session()
    except Exception as exc:                                       # noqa: BLE001
        print("[10023-r3-live] NON MESURE : session Frida introuvable (%s) -- rc 2" % exc)
        return 2
    if sid is None:
        print("[10023-r3-live] NON MESURE : aucune session running -- rc 2")
        return 2
    print("[10023-r3-live] session=%s board=%s seed=%d" % (sid, a.board, a.seed))

    # ---------------------------------------------------------------- BRAS DE REFERENCE
    ref = un_bras(sid, a.seed, a.board, "ref")
    if "erreur" in ref:
        print("[10023-r3-live] NON MESURE (reference) : %s -- rc 2" % ref["erreur"])
        return 2
    print("[10023-r3-live] [ref] boss u%s owner=%s currentPlayer=%s"
          % (ref["boss"], ref["owner"], ref["currentPlayer"]))
    print("[10023-r3-live] [ref] feet=%s  main(feet[0])=%s  pos(dernier pied)=ignore"
          % (ref["feet"], ref["main"]))
    print("[10023-r3-live] [ref] cibles legales (fromHere) : %s" % (ref["cibles"],))
    print("[10023-r3-live] [ref] cible=%s ok=%s" % (ref["cible"], ref["ok"]))
    print("[10023-r3-live] [ref] ecart des deux regimes (pieds non-main a d=2) : %s"
          % (ref["ecart"],))
    print("[10023-r3-live] [ref] tuiles 1195 NEUVES (%s) : %s"
          % ("None" if ref["neuves"] is None else len(ref["neuves"]), ref["neuves"]))

    if ref["neuves"] is None:
        print("[10023-r3-live] NON MESURE : `tileMeta` ne publie aucun canal d'effet par tuile "
              "-- l'observable n'existe pas par ce RPC. -- rc 2")
        return 2
    if not ref["ecart"]:
        print("[10023-r3-live] ROUGE : AUCUNE cible legale ne discrimine les deux regimes (aucun "
              "pied non-main a distance 2). Le montage ne peut rien trancher -- ce n'est pas un "
              "succes, c'est un echec de montage.")
        return 1
    if not ref["neuves"]:
        print("[10023-r3-live] NON MESURE : le cast n'a pose AUCUN effet 1195 (natif refuse en "
              "silence, signature #111 : `ok=True` sans mutation). -- rc 2")
        return 2

    marquees = set(ref["neuves"])
    # DECOMPOSITION PAR ETAGE : on confronte l'AIRE ENTIERE aux deux predictions, pas une tuile.
    # Un desaccord sur une seule tuile pourrait tenir a un troisieme etage mal lu ; un accord
    # EXACT sur l'aire complete ne le peut pas.
    print("[10023-r3-live] [ref] aire predite REGIME A (retranche la main tile seule, %d) : %s"
          % (len(ref["aire_a"]), ref["aire_a"]))
    print("[10023-r3-live] [ref] aire predite REGIME B (retranche l'empreinte, %d)      : %s"
          % (len(ref["aire_b"]), ref["aire_b"]))
    acc_a, acc_b = (marquees == set(ref["aire_a"])), (marquees == set(ref["aire_b"]))
    print("[10023-r3-live] [ref] aire NATIVE == A ? %s ; == B ? %s "
          "(A\\natif=%s natif\\A=%s | B\\natif=%s natif\\B=%s)"
          % (acc_a, acc_b,
             sorted(set(ref["aire_a"]) - marquees), sorted(marquees - set(ref["aire_a"])),
             sorted(set(ref["aire_b"]) - marquees), sorted(marquees - set(ref["aire_b"]))))
    if not (acc_a or acc_b):
        print("[10023-r3-live] ROUGE : l'aire NATIVE ne coincide avec AUCUN des deux regimes. Un "
              "etage supplementaire intervient (mur / fog / elevation / gate non lu) : ne rien "
              "conclure de `ReturnsOnlyUnits` sur cette mesure.")
        return 1
    portes = [p for p in ref["ecart"] if p in marquees]
    # Les tuiles VIDES du meme etage (`ring2 & cring1`) : distance 2 de la cible, marquees.
    # Ce sont les TEMOINS du controle d'occupation.
    temoins = sorted(t for t in marquees
                     if hexgeo.distance(t, ref["cible"]) == 2 and t not in set(ref["feet"]))
    print("[10023-r3-live] [ref] pieds discriminants MARQUES : %d/%d ; temoins vides du meme "
          "etage (d=2, marquees, hors empreinte) : %s" % (len(portes), len(ref["ecart"]), temoins))

    if len(portes) == len(ref["ecart"]):
        print("")
        print("[10023-r3-live] VERT : les %d pied(s) non-main a distance 2 SONT dans l'aire "
              "marquee => `Tiles(CasterTiles)` ne retranche QUE la main tile => "
              "`CasterTiles.ReturnsOnlyUnits == FAUX`. C'est EXACTEMENT le regime que porte "
              "`engine/dsl/base.py::_main_tiles` : #10023 est CONFRONTE LIVE." % len(ref["ecart"]))
        return 0
    if portes:
        print("")
        print("[10023-r3-live] ROUGE : verdict MIXTE (%d/%d pieds marques) -- ni l'un ni l'autre "
              "des deux regimes. Un troisieme etage intervient : ne rien conclure."
              % (len(portes), len(ref["ecart"])))
        return 1

    # --------------------------------------------------- BRAS DE CONTROLE (occupation)
    if a.sans_controle:
        print("")
        print("[10023-r3-live] SUSPENDU : aucun pied discriminant n'est marque, mais le controle "
              "d'occupation n'a pas ete joue (--sans-controle). Sans lui, l'absence du pied "
              "s'explique aussi par un filtre d'occupation. -- rc 2")
        return 2
    if not temoins:
        print("")
        print("[10023-r3-live] NON MESURE : aucune tuile VIDE marquee a distance 2 -- le controle "
              "d'occupation n'a pas de temoin possible sur cette cible. -- rc 2")
        return 2

    cible_ctrl = temoins[0]
    print("")
    print("[10023-r3-live] [ctrl] on pose une unite ALLIEE sur %s (tuile VIDE marquee du meme "
          "etage) et on rejoue le MEME cast sur %s." % (cible_ctrl, ref["cible"]))
    ctl = un_bras(sid, a.seed, a.board, "ctrl", cible_imposee=ref["cible"], occuper=cible_ctrl)
    if "erreur" in ctl:
        print("[10023-r3-live] NON MESURE (controle) : %s -- rc 2" % ctl["erreur"])
        return 2
    print("[10023-r3-live] [ctrl] occupant pose en %s (demande %s) ; cible=%s ok=%s"
          % (ctl["occupant"], cible_ctrl, ctl["cible"], ctl["ok"]))
    print("[10023-r3-live] [ctrl] tuiles 1195 NEUVES (%s) : %s"
          % ("None" if ctl["neuves"] is None else len(ctl["neuves"]), ctl["neuves"]))
    if not ctl["neuves"]:
        print("[10023-r3-live] NON MESURE : le cast de controle n'a rien pose. -- rc 2")
        return 2
    occupee_encore_marquee = cible_ctrl in set(ctl["neuves"])
    sur_place = (ctl["occupant"] == cible_ctrl)
    print("[10023-r3-live] [ctrl] l'unite est-elle bien sur %s ? %s ; la tuile est-elle encore "
          "marquee ? %s" % (cible_ctrl, sur_place, occupee_encore_marquee))
    if not sur_place:
        print("[10023-r3-live] NON MESURE : le `move` n'a pas pose l'unite sur la tuile demandee "
              "-- le controle n'a pas eu lieu. -- rc 2")
        return 2
    if not occupee_encore_marquee:
        print("")
        print("[10023-r3-live] SUSPENDU (rc 1) : une tuile OCCUPEE sort de l'aire. L'absence des "
              "pieds ne discrimine donc PAS les deux regimes -- elle s'explique par l'occupation. "
              "Ce montage ne peut pas trancher `CasterTiles.ReturnsOnlyUnits` ; il faudrait un "
              "call-site ou l'origine multi-tuile n'est pas occupee par son propre caster.")
        return 1
    print("")
    print("[10023-r3-live] ROUGE : une tuile OCCUPEE reste dans l'aire (controle), donc "
          "l'occupation ne filtre pas ; et AUCUN des %d pied(s) non-main a distance 2 n'y est. "
          "=> `Tiles(CasterTiles)` retranche TOUTE l'empreinte => "
          "`CasterTiles.ReturnsOnlyUnits == VRAI`. Le mirror actuel ne retranche QU'UNE tuile : "
          "il est FAUX sur ce call-site." % len(ref["ecart"]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
