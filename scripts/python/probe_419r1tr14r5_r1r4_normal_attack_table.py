"""#419-r1-tr14-r5-r1 et -r4 -- la TABLE de substitution d'attaque normale, et les DEUX TRAITS qui
la SUPPRIMENT. Les deux resident dans le meme foyer natif,
`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, d'ou un probe unique.

## Ce qui est mesure, et pourquoi ce canal-la

`GetCustomNormalAttack` est un lookup dans un `Dictionary` STATIQUE ecrit par
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$.cctor` ;
la table du port en transcrit les 14 paires. On ne CROIT pas cette transcription : on la confronte
au natif, entree par entree, par le seul canal qui publie le resultat de la fabrique --
`decisionView.units[].abilities` avec `kind == "normal"`, qui rend
`ActiveAbilityComponent.NormalAttackType@0x28` (cf. `ai-step/internals.ts`). Aucun capteur neuf
n'est requis, et le canal couvre TOUTES les unites du board, pas seulement les controlees.

## Les trois volets

* `--volet table` -- les 14 entrees, par DEUX chemins independants :
  - les CINQ passifs dont un porteur `lineup` est au pool (`--list-pool`) : on les spawne tels
    quels, aucun montage, et on lit leur attaque normale ;
  - les NEUF autres par GREFFE ecrite (`BC.Units[].PassiveAbilities = [<id>]`, une unite neutre
    par passif) -- le meme levier que le controle apparie de #446-r1 §4. S'y ajoute une unite
    `PassiveAbilities = []` : le CONTROLE, qui doit rendre `69 Loki_NormalAttack`.
    ⚠ Sans ce controle, un montage qui n'aurait rien installe rendrait des `69` partout et se
    lirait comme « aucune substitution », pas comme « montage mort ».

* `--volet order` -- la BOUCLE, pas la table. `GetCustomNormalAttackTypeFromPassive` rend au
  PREMIER passif substituant de la liste ; une table INCOMPLETE ne fait donc pas « moins de
  dispatch », elle en fait un FAUX : l'entree manquante est sautee et la main passe a la suivante.
  Le montage l'exerce sur `templAggressor` (`[HeavyBoltPistol, Boltstorm]` -- natif attendu
  `1046`, la table d'avant aurait dit `1128`), avec le bras RECIPROQUE `[Boltstorm,
  HeavyBoltPistol]` sur une autre unite (natif attendu `1128`) : deux ordres, deux reponses, meme
  paire de passifs. Cote PORT, on mesure la prediction de degat AVEC la table livree et avec la
  table REDUITE a ses quatre entrees d'avant -- la contre-epreuve doit MORDRE (le fold
  `Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction` s'ajoute a tort).

* `--volet traits` -- la garde d'entree : `Traits.Contains(0x0e Erratic)` ou `Contains(0x15
  Harmless)` -> `return` SEC, aucune attaque normale. Bras APPARIE (memes unites, memes rosters,
  seuls les `BC.Units[].Traits` different) : sur le bras `trait` le natif ne doit publier AUCUNE
  ability `kind == "normal"`, sur le bras `ctrl` il doit en publier une. Cote PORT, on lit
  `state_bridge.build_from_state(...).normal_ids` -- la voie OFFLINE, seule des deux a deriver
  l'existence de l'attaque normale (la voie LIVE lit `decisionView`, donc la mesure).
  ⚠ ZERO unite du build ne porte ces traits (683 kits gameconfig, 175 unites du seed BC balayes) :
  le montage ECRIT est le seul chemin de confrontation, et il en est un -- pas un « non pertinent ».

Usage :
    python scripts/python/probe_419r1tr14r5_r1r4_normal_attack_table.py \\
        --volet all --state-file <ABSOLU>.json

ASCII only.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject                                              # noqa: E402
import probe_124_line_elevation_decision as P124                   # noqa: E402
import probe_380_seed_bc_patch_survival as P380                    # noqa: E402
import probe_419r1tr14_heavy_bolt_pistol as P14                    # noqa: E402
import probe_419r1tr14r5_normal_attack_stages as P5                # noqa: E402
from engine import weights as W                                    # noqa: E402
from engine.ai import context as _ai_ctx                           # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                        # noqa: E402
from engine.services import custom_normal_attack as CNA            # noqa: E402

MontageError = P14.MontageError

BOARD = "MC1_67"
SEED_NAT = "9090901"
SEED_GRAFT = "9090902"
SEED_TRAIT = "9090903"

#: Les CINQ passifs substituants dont un porteur `lineup` est au pool spawnable (rank 17).
#: `{visualId: passif}` -- aucun montage, le seed BC les porte deja (`BC.Units[].PassiveAbilities`).
NATURAL = {"tauMarksman": "MV71SniperDroneSquad",
           "templAggressor": "Boltstorm",
           "adeptMorvenn": "RighteousRepugnance",
           "tyranDeathleaper": "FeederTendrils",
           "admecRuststalker": "OptimizedGait"}
NATURAL_CTRL = ("astraBullgryn", "necroWarden")     # aucun passif substituant -> `69` attendu

#: Les NEUF autres, par greffe -- une unite NEUTRE du pool par passif. Le choix des porteuses est
#: indifferent au resultat (la fabrique ne lit QUE la liste de passifs) ; ce qui compte est
#: qu'aucune ne porte NATURELLEMENT un passif substituant, sans quoi la greffe ne discriminerait
#: rien.
GRAFT = {"astraBullgryn": "HeavyBoltPistol",
         "necroWarden": "ProperKilly",
         "orksNob": "BlisteringAssault",
         "spaceHound": "FloatingDeath",
         "eldarRanger": "AncientFury",
         "bloodIntercessor": "Wraithcannon",
         "darkaTerminator": "ElectroShock",
         "tauCrisis": "TalonOfHorus",
         "ultraTitus": "Fealty"}
GRAFT_CTRL = "worldJakhal"                          # `PassiveAbilities = []` -> `69` attendu
GRAFT_P = ("astraBullgryn", "necroWarden", "orksNob", "spaceHound", "eldarRanger")
GRAFT_A = ("bloodIntercessor", "darkaTerminator", "tauCrisis", "ultraTitus", GRAFT_CTRL)

GENERIC_NORMAL_ATTACK = "Loki_NormalAttack"         # `ActiveAbilityType` 69

#: Volet ORDER. La paire est `HeavyBoltPistol` (absent de la table d'avant) devant `Boltstorm`
#: (present) : c'est l'ordre ou une table partielle se trompe. Le bras reciproque inverse la paire.
ORDER_HOST = P5.G_HOST                              # `templAggressor`, mold RANGED de #446-r1
ORDER_RECIPROCAL = P5.G_TARGET                      # `astraBullgryn`, meme paire, ordre inverse
ORDER_FIRST = "HeavyBoltPistol"
ORDER_SECOND = "Boltstorm"

#: Volet TRAITS. `{visualId: trait}` -- les deux valeurs de la garde, une unite chacune.
TRAIT_UNITS = {"necroWarden": "Harmless", "orksNob": "Erratic"}
TRAIT_P = ("necroWarden", "orksNob", "astraBullgryn")
TRAIT_A = ("spaceHound", "eldarRanger")

#: Les QUATRE entrees que le port portait avant #419-r1-tr14-r5-r1 -- la contre-epreuve du volet
#: `order` rejoue EXACTEMENT cette table, donc exactement le comportement d'avant.
TABLE_BEFORE_R1 = {"MV71SniperDroneSquad": "MV71SniperDroneSquadAttack",
                   "Boltstorm": "Boltstorm_NormalAttack",
                   "RighteousRepugnance": "RighteousRepugnance_NormalAttack",
                   "ProperKilly": "ProperKilly_NormalAttack"}


def pid(passive: str) -> int:
    return int(TriggeredAbilityType[passive])


# --------------------------------------------------------------------------- seed BC patche

def _patch_seed(out: str, passives: dict | None = None, traits: dict | None = None) -> str:
    """Ecrit un seed BC ou `BC.Units[<id>].PassiveAbilities` / `.Traits` sont REMPLACES.

    `passives` = `{visualId: [ids]}`, `traits` = `{visualId: [noms]}`. Toute unite nommee doit
    exister dans le seed -- sinon le montage n'est PAS installe et on le dit, plutot que de rendre
    un tableau de `69` qui se lirait comme une mesure."""
    bc = catalog_inject._load_seed(None)
    want = set(passives or ()) | set(traits or ())
    seen = set()
    for u in (bc.get("Units") or ()):
        uid = u.get("Id")
        if uid in (passives or {}):
            u["PassiveAbilities"] = list(passives[uid])
            seen.add(uid)
        if uid in (traits or {}):
            u["Traits"] = list(traits[uid])
            seen.add(uid)
    missing = sorted(want - seen)
    if missing:
        raise MontageError(f"montage NON INSTALLE : {missing} absent(s) du seed BC")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(bc))
    P380.assert_survives(out)
    return out


def seed_traits_of(visual_ids) -> dict:
    """Les `Traits` que le seed BC porte DEJA pour ces unites. Le volet `traits` AJOUTE le trait
    suppresseur a cette liste au lieu de la remplacer : remplacer retirerait `Hero`/l'alliance et
    ferait varier autre chose que la seule variable etudiee."""
    bc = catalog_inject._load_seed(None)
    out = {}
    for u in (bc.get("Units") or ()):
        if u.get("Id") in visual_ids:
            out[u["Id"]] = list(u.get("Traits") or ())
    missing = sorted(set(visual_ids) - set(out))
    if missing:
        raise MontageError(f"montage NON INSTALLE : {missing} absent(s) du seed BC")
    return out


def _build(state_file: str, argv_tail: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--state-file", state_file, *argv_tail]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- lecture du natif

def normal_attack_by_unit(rpc, rid: int) -> dict:
    """`{visualId: (abilityId, name) | None}` -- l'attaque normale que la FABRIQUE a posee sur
    chaque unite du board. `None` = aucune ability `kind == "normal"` publiee, c.-a-d. exactement
    ce que produit le `return` sec de `AddNormalAttackAbility`."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
    out = {}
    for u in (dv.get("units") or ()):
        na = [a for a in (u.get("abilities") or ()) if a.get("kind") == "normal"]
        out[u.get("visualId")] = (int(na[0]["id"]), na[0].get("name")) if na else None
    return out


# --------------------------------------------------------------------------- volet TABLE

def run_table(rpc, build, verbose: bool = True) -> list:
    """Les 14 entrees + 3 controles. `build(seed, extra) -> rid`. Rend une ligne par entree."""
    rows = []

    rid_n = build(SEED_NAT, ["--board", BOARD,
                             "--p-units", ",".join(NATURAL),
                             "--a-units", ",".join(NATURAL_CTRL)])
    got = normal_attack_by_unit(rpc, rid_n)
    for vis, passive in NATURAL.items():
        rows.append(_row("natural", vis, passive,
                         _expected(passive), got.get(vis)))
    for vis in NATURAL_CTRL:
        rows.append(_row("natural-ctrl", vis, None, GENERIC_NORMAL_ATTACK, got.get(vis)))

    logs = os.environ.get("A35_LOGS") or _HERE
    seed_bc = _patch_seed(os.path.join(logs, "tr14r5_r1_graft_seedbc.json"),
                          passives={**{v: [pid(p)] for v, p in GRAFT.items()},
                                    GRAFT_CTRL: []})
    rid_g = build(SEED_GRAFT, ["--board", BOARD, "--p-units", ",".join(GRAFT_P),
                               "--a-units", ",".join(GRAFT_A), "--seed-bc", seed_bc])
    got = normal_attack_by_unit(rpc, rid_g)
    for vis, passive in GRAFT.items():
        rows.append(_row("graft", vis, passive,
                         _expected(passive), got.get(vis)))
    rows.append(_row("graft-ctrl", GRAFT_CTRL, None, GENERIC_NORMAL_ATTACK, got.get(GRAFT_CTRL)))

    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<12}] {r['unit']:<18} passif={str(r['passive']):<22} "
                  f"natif={str(r['native']):<34} attendu={r['expected']:<34} "
                  f"{'OK' if r['ok'] else 'MISMATCH'}")
    return rows


def _expected(passive: str) -> str:
    """Ce que la table PORTEE annonce pour ce passif -- ou le marqueur `<absent de la table>`.

    ⚠ Volontairement un `.get`, pas un `[]` : une entree RETIREE de la table doit produire un
    MISMATCH assertionnel dans la garde, pas un `KeyError` qui ferait ERROR la fixture. Un rouge de
    fixture est un rouge, mais il ne dit pas CE QUI a bouge -- et c'est justement ce que ce fichier
    doit dire."""
    return CNA.CUSTOM_NORMAL_ATTACK_BY_PASSIVE.get(passive) or "<absent de la table portee>"


def _row(arm, unit, passive, expected, native) -> dict:
    name = None if native is None else native[1]
    return {"arm": arm, "unit": unit, "passive": passive, "expected": expected,
            "native": name, "native_id": None if native is None else native[0],
            "ok": name == expected}


# --------------------------------------------------------------------------- volet ORDER

@contextlib.contextmanager
def table_before_r1():
    """Rejoue la table du port TELLE QU'ELLE ETAIT avant #419-r1-tr14-r5-r1 (quatre entrees).
    On mute la TABLE, jamais le code livre : c'est la contre-epreuve qui doit MORDRE."""
    saved = CNA.CUSTOM_NORMAL_ATTACK_BY_PASSIVE
    CNA.CUSTOM_NORMAL_ATTACK_BY_PASSIVE = dict(TABLE_BEFORE_R1)
    try:
        yield
    finally:
        CNA.CUSTOM_NORMAL_ATTACK_BY_PASSIVE = saved


def run_order(sid, rpc, build, verbose: bool = True) -> dict:
    """Un runner. Deux ordres de la MEME paire de passifs, plus la mesure de prediction du port
    avec la table livree et avec la table d'avant."""
    logs = os.environ.get("A35_LOGS") or _HERE
    first, second = pid(ORDER_FIRST), pid(ORDER_SECOND)
    seed_bc = _patch_seed(os.path.join(logs, "tr14r5_r1_order_seedbc.json"),
                          passives={ORDER_HOST: [first, second],
                                    ORDER_RECIPROCAL: [second, first]})
    stats = ";".join(f"{v}:Health={P14.HP},RemainingHealth={P14.HP}"
                     for v in (P5.G_HOST, P5.G_ALLY, P5.G_TARGET, P5.G_FOE1))
    rid = build(P5.G_SEED, ["--board", P5.G_BOARD, "--p-units", f"{P5.G_HOST},{P5.G_ALLY}",
                            "--a-units", f"{P5.G_TARGET},{P5.G_FOE1}",
                            "--unit-stat", stats, "--seed-bc", seed_bc])
    got = normal_attack_by_unit(rpc, rid)
    want_host, want_recip = _expected(ORDER_FIRST), _expected(ORDER_SECOND)
    rows = [_row("order-first", ORDER_HOST, f"[{ORDER_FIRST},{ORDER_SECOND}]", want_host,
                 got.get(ORDER_HOST)),
            _row("order-recip", ORDER_RECIPROCAL, f"[{ORDER_SECOND},{ORDER_FIRST}]", want_recip,
                 got.get(ORDER_RECIPROCAL))]

    case = P5.g_stage(sid, rpc, rid, None)
    P14.place(sid, case, "B")
    tile = case["layout"]["B"]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or ())}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, case["cid"], W.load(),
                        _scene.build_predictor(rpc, rid))
    ab = P5._normal_ability(ctx)
    tgt = case["ids"]["T"]
    if tile not in [t for t in (ctx.action_tiles or ()) if t and t[0] is not None]:
        raise MontageError(f"volet order NON MESURABLE : tuile {tile} hors des tuiles d'action")
    nat = P5._native_prediction(rpc, rid, case["cid"], tgt, ab, tile)
    port = P5._port_prediction(ctx.scene, case["cid"], tgt, tile)
    with table_before_r1():
        before = P5._port_prediction(ctx.scene, case["cid"], tgt, tile)
    pred = {"tile": tile, "ab": ab, "nat": nat, "port": port, "before": before}
    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<12}] {r['unit']:<18} passifs={str(r['passive']):<28} "
                  f"natif={str(r['native']):<34} attendu={r['expected']:<34} "
                  f"{'OK' if r['ok'] else 'MISMATCH'}")
        print(f"  [prediction  ] tuile={tile} ab={ab} natif={nat['dmin']}..{nat['dmax']} "
              f"port={port['dmin']}..{port['dmax']} "
              f"table-d-avant={before['dmin']}..{before['dmax']}")
    return {"rows": rows, "pred": pred, "rid": rid}


# --------------------------------------------------------------------------- volet TRAITS

@contextlib.contextmanager
def no_trait_gate():
    """COUPE la garde des traits dans la voie OFFLINE -- `has_normal_attack` rend `True` quoi qu'il
    arrive, c.-a-d. STRICTEMENT le comportement d'avant #419-r1-tr14-r5-r4. C'est la mutation qui
    doit MORDRE sur le bras `trait` : sans elle, un vert du volet ne prouverait pas que la garde est
    ce qui le produit (l'unite pourrait n'avoir aucune arme, ou le montage etre mort)."""
    from engine.ai import state_bridge as SB
    saved = SB.has_normal_attack
    SB.has_normal_attack = lambda traits: True
    try:
        yield
    finally:
        SB.has_normal_attack = saved


def _port_normal_ids(rpc, rid: int, uid: int, gated: bool = True) -> set:
    """`normal_ids` de la voie OFFLINE (`state_bridge.build_from_state`) -- la seule des deux faces
    a DERIVER l'existence de l'attaque normale ; la voie LIVE la lit dans `decisionView`."""
    from engine.ai.state_bridge import build_from_state
    from engine.runner.snapshot import load_state
    from engine.entities.pathfinding.board import Board
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
    ob = rpc("observeBattle", {"runnerId": rid}, 120)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    bg = rpc("boardGraph", {"runnerId": rid}, 120)
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    if gated:
        return set(build_from_state(st, uid).normal_ids or ())
    with no_trait_gate():
        return set(build_from_state(st, uid).normal_ids or ())


def run_traits(rpc, build, verbose: bool = True) -> list:
    """Bras APPARIE. Seuls les `BC.Units[].Traits` des deux unites etudiees different."""
    logs = os.environ.get("A35_LOGS") or _HERE
    base = seed_traits_of(TRAIT_UNITS)
    arms = {}
    for arm in ("ctrl", "trait"):
        traits = {v: (list(base[v]) + [t]) if arm == "trait" else list(base[v])
                  for v, t in TRAIT_UNITS.items()}
        seed_bc = _patch_seed(os.path.join(logs, f"tr14r5_r4_{arm}_seedbc.json"), traits=traits)
        arms[arm] = build(SEED_TRAIT, ["--board", BOARD, "--p-units", ",".join(TRAIT_P),
                                       "--a-units", ",".join(TRAIT_A), "--seed-bc", seed_bc])
    rows = []
    for arm, rid in arms.items():
        got = normal_attack_by_unit(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 4}, 300)
        id_by_vis = {u.get("visualId"): u.get("id") for u in (dv.get("units") or ())}
        for vis, trait in TRAIT_UNITS.items():
            if vis not in got:
                raise MontageError(f"montage NON INSTALLE : {vis} absent du board (bras {arm})")
            uid = id_by_vis.get(vis)
            port = _port_normal_ids(rpc, rid, uid) if uid is not None else None
            # CONTRE-EPREUVE : garde COUPEE = le port d'avant #419-r1-tr14-r5-r4.
            ungated = _port_normal_ids(rpc, rid, uid, gated=False) if uid is not None else None
            rows.append({"arm": arm, "unit": vis, "trait": trait,
                         "native": None if got[vis] is None else got[vis][1],
                         "port_normal_ids": sorted(port or ()),
                         "port_ungated": sorted(ungated or ()),
                         "expect_native": arm == "ctrl"})
        # CONTROLE : une unite du MEME bras SANS le trait garde son attaque normale -- sans lui, un
        # bras `trait` qui aurait casse le montage entier se lirait comme un succes.
        rows.append({"arm": arm, "unit": "astraBullgryn", "trait": None,
                     "native": None if got.get("astraBullgryn") is None
                               else got["astraBullgryn"][1],
                     "port_normal_ids": None, "port_ungated": None, "expect_native": True})
    if verbose:
        for r in rows:
            print(f"  [{r['arm']:<5}] {r['unit']:<16} trait={str(r['trait']):<10} "
                  f"natif={str(r['native']):<20} port={r['port_normal_ids']} "
                  f"garde-coupee={r['port_ungated']} "
                  f"(attaque normale attendue : {'OUI' if r['expect_native'] else 'NON'})")
    return rows


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
    ap.add_argument("--volet", default="all", choices=("all", "table", "order", "traits"))
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    logs = os.path.dirname(os.path.abspath(args.state_file))
    os.makedirs(logs, exist_ok=True)
    os.environ["A35_LOGS"] = logs
    stem = os.path.splitext(os.path.basename(args.state_file))[0]
    seq, rids = {"n": 0}, []

    def build(seed, extra):
        seq["n"] += 1
        sf = os.path.join(logs, f"{stem}_{seq['n']}.json")
        rid = _build(sf, ["--seed", str(seed), *extra])
        rids.append(rid)
        return rid

    print("session", sid)
    rc = 0
    try:
        if args.volet in ("all", "table"):
            print("== volet TABLE (14 entrees + 3 controles) ==")
            rows = run_table(rpc, build)
            bad = [r for r in rows if not r["ok"]]
            print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
            rc |= 1 if bad else 0
        if args.volet in ("all", "order"):
            print("== volet ORDER (premier passif gagnant) ==")
            out = run_order(sid, rpc, build)
            bad = [r for r in out["rows"] if not r["ok"]]
            rc |= 1 if bad else 0
        if args.volet in ("all", "traits"):
            print("== volet TRAITS (Erratic / Harmless) ==")
            rows = run_traits(rpc, build)
            bad = [r for r in rows if (r["native"] is not None) != r["expect_native"]]
            print(f"   -> {len(rows) - len(bad)}/{len(rows)} conformes")
            rc |= 1 if bad else 0
    finally:
        for rid in rids:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
