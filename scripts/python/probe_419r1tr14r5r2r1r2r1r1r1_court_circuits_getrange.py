"""#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1 / -r2 / -r4-r1 -- les TROIS lectures que `GetRange` faisait
sans mirror, et leurs porteurs RE-ETABLIS.

LES TROIS QUESTIONS BINAIRES, toutes dans `IdunBattle.Core.Services.TargetingQuery$$GetRange` :

  1. `-r1` -- le TROISIEME champ du `Range` rendu (`UseWholeBoard @+0x05`) porte-t-il une
     information que `options.Range.UseWholeBoard` n'a pas ? **NON** : les trois sorties du corps
     natif l'ecrivent depuis cette meme source (etape `champ_alias`). Le port le modelise donc sans
     rien deviner -- et ce qui rendait l'ancien arbitrage fragile n'etait pas sa conclusion mais sa
     JUSTIFICATION : elle reposait sur l'inventaire des consommateurs portes, donc se serait
     perimee au premier consommateur neuf.
  2. `-r2` -- le court-circuit `casterTiles` vide a-t-il un PORTEUR ? **OUI, et la fiche disait le
     contraire.** C'est la MACHINE OF WAR : `decisionView.mows[]` rend `pos: null`, `feet: []`,
     `platformTiles: []` -- MESURE, etape `mow_sans_tuile`. Le regime d'ECART, lui, est vide, et
     c'est une autre mesure : les 22/22 masques a `AllowNullCasterTile` portent `use_whole_board`,
     et les 22 unites `MachineOfWar` du gameconfig n'ont que ces deux actives-la (etape `mow_masques`).
  3. `-r4-r1` -- `GetStat(caster, StatType.Range = 2)` est-il observable ? **OUI, et la docstring du
     port disait le contraire.** `combatSnapshot` publie `stats.range` et son catalogue `statTypes`
     l'apparie a l'index **2** (etape `stat_range`).

CE QUE LA MESURE `stat_range` DECOMPOSE, PAR ETAGE -- parce qu'un balayage d'unites seul ne
prouverait rien sur les 81 sans arme :

  * ETAGE CATALOGUE : `UnitConfiguration.Range` = l'INITIAL du `StatComponent`. `data/seed-bc.json`
    en porte **175** entrees, toutes a **0** ;
  * ETAGE MODIFICATION : aucun champ `statType`/`stat` du gameconfig ne nomme `range` (les seules
    valeurs rencontrees sont `hp`, `dmg`, `fixedArmor`) -- donc aucune stat-modification de config
    ne peut deplacer cette stat ;
  * ETAGE RESOLU : `combatSnapshot.units[].stats.range` en bataille, avec son `statDelta`. La
    branche `!HasAnyWeapon` du natif ne lit QUE cet etage-la.

Les MoW sont le porteur le moins cher de l'etage RESOLU : elles sont **sans arme** (les 22 sont dans
les 81) et **8 d'entre elles sont au pool**, donc atteignables par `rl_duel build --p-mow/--a-mow`
sans aucune injection de catalogue.

Le TEST qui garde le port est
`tests/engine/test_419r1tr14r5r2r1r2r1r1r1_court_circuits_getrange_live.py`. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import gameconfig as GC                                                   # noqa: E402
from engine.entities.stats import StatType                                # noqa: E402
from engine.runner.abilities import targeting as TGT                      # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES               # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR    # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
SEED = "4192"
BOARD = "MC1_67"

#: Les MoW du pool spawnable au rank courant -- le porteur du court-circuit `casterTiles` vide ET
#: de la branche `!HasAnyWeapon`. RE-DERIVE par `--step mow_masques`, jamais affirme : la liste
#: ci-dessous n'est qu'un ORDRE de passage pour les builds.
MOW_POOL = ["adeptExorcist", "astraOrdnanceBattery", "blackForgefiend", "deathCrawler",
            "orksRukkatrukk", "tauBroadside", "tyranBiovore", "ultraDreadnought"]

#: Des unites ARMEES, pour que chaque bataille porte aussi un TEMOIN : si `stats.range` valait 0
#: pour les seules unites sans arme, la mesure ne dirait rien sur la stat elle-meme.
ESCORTE_P = "tauCrisis,tauMarksman"
ESCORTE_A = "necroSpyder,ultraEliminatorSgt"


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rq(sid, method, body=None, timeout=90):
    return _res(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _masques_lus() -> dict:
    """`{abilityId: TargetingOptions}` pour toutes les abilities dont le masque est RE-lu."""
    out = {}
    for a in ABILITY_CLASSES:
        o = TGT.targeting_options_for(a)
        if o is not None and getattr(o, "rules", None) is not None:
            out[int(a)] = o
    return out


# ------------------------------------------------------------------------------------------------
# ETAPE `champ_alias` -- le 3e champ du `Range` est un ALIAS d'`options.Range.UseWholeBoard`
# ------------------------------------------------------------------------------------------------

def _caster(State, UnitComponent, PositionComponent, OwnerComponent, avec_tuile: bool):
    """Un caster SYNTHETIQUE minimal : seul le couple (options, presence d'une `PositionComponent`)
    commande le champ mesure ici. `avec_tuile=False` mirrore `casterTiles` vide -- le regime de la
    MACHINE OF WAR, dont `EntityExtensions$$GetMainTile` rend `null`.

    `visual_id` est laisse VIDE a dessein : la branche d'arme n'intervient pas dans les deux
    court-circuits, qui precedent toute resolution d'arme dans le corps natif."""
    st = State()
    ent = st.add_entity()
    ent.add_component(UnitComponent(visual_id="", alive=True))
    if avec_tuile:
        ent.add_component(PositionComponent(col=3, row=3))
    ent.add_component(OwnerComponent(team=0))
    return st, int(next(k for k, v in st.entities.items() if v is ent))


def champ_alias() -> dict:
    """Le port rend-il, pour TOUT jeu d'options RE-lu, `range.use_whole_board ==
    options.range.use_whole_board` ?

    C'est la propriete que le decompile etablit (les trois sorties de `GetRange` ecrivent le champ
    depuis cette meme source), et la seule qui rende le mirror sur : si elle tient, aucun
    consommateur -- porte ou futur -- ne peut diverger en lisant l'un plutot que l'autre.

    Le balayage porte sur un `State` SYNTHETIQUE minimal : seul le couple (options, presence d'une
    tuile) commande le champ, jamais les stats du caster."""
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.state import State

    st, cid = _caster(State, UnitComponent, PositionComponent, OwnerComponent, avec_tuile=True)
    sans_tuile, cid2 = _caster(State, UnitComponent, PositionComponent, OwnerComponent,
                               avec_tuile=False)

    lus = _masques_lus()
    ecarts, n = [], 0
    for aid, opts in sorted(lus.items()):
        if opts.range is None:
            continue
        attendu = bool(opts.range.use_whole_board)
        for nom, s, c in (("avec_tuile", st, cid), ("sans_tuile", sans_tuile, cid2)):
            rr = TGT.get_range(s, c, opts)
            n += 1
            if rr is None or bool(rr.use_whole_board) != attendu:
                ecarts.append({"ability": aid, "regime": nom,
                               "attendu": attendu,
                               "rendu": None if rr is None else bool(rr.use_whole_board)})
    return {"couples_balayes": n, "abilities": len(lus), "ecarts": ecarts,
            "alias_exact": not ecarts}


def court_circuits() -> dict:
    """Les DEUX court-circuits rendent-ils le triplet natif exact ?

    `casterTiles` vide -> `Range(0, false, options.Range.UseWholeBoard)` ;
    `UseWholeBoard`     -> `Range(1, false, true)`, le litteral `0x10000000001`.

    Et le consommateur `get_range_broken_rule` ne pose AUCUN refus dans les deux cas -- ce qui est
    la non-regression : avant le mirror, ces deux regimes sortaient par un `return None`."""
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.state import State

    st, cid = _caster(State, UnitComponent, PositionComponent, OwnerComponent, avec_tuile=True)
    sans, cid2 = _caster(State, UnitComponent, PositionComponent, OwnerComponent, avec_tuile=False)

    lus = _masques_lus()
    wb = [(a, o) for a, o in sorted(lus.items())
          if o.range is not None and o.range.use_whole_board]
    non_wb = [(a, o) for a, o in sorted(lus.items())
              if o.range is not None and not o.range.use_whole_board]
    out = {"whole_board": len(wb), "non_whole_board": len(non_wb),
           "ecarts_uwb": [], "ecarts_sans_tuile": [], "refus_poses": []}
    for a, o in wb:
        rr = TGT.get_range(st, cid, o)
        if rr is None or (rr.value, rr.only_adjacent, rr.use_whole_board) != (1, False, True):
            out["ecarts_uwb"].append({"ability": a, "rendu": None if rr is None else
                                      [rr.value, rr.only_adjacent, rr.use_whole_board]})
        if TGT.get_range_broken_rule(st, cid, None, o) != 0:
            out["refus_poses"].append({"ability": a, "regime": "whole_board"})
    for a, o in wb + non_wb:
        rr = TGT.get_range(sans, cid2, o)
        attendu = (0, False, bool(o.range.use_whole_board))
        if rr is None or (rr.value, rr.only_adjacent, rr.use_whole_board) != attendu:
            out["ecarts_sans_tuile"].append({"ability": a, "attendu": list(attendu),
                                             "rendu": None if rr is None else
                                             [rr.value, rr.only_adjacent, rr.use_whole_board]})
        if TGT.get_range_broken_rule(sans, cid2, None, o) != 0:
            out["refus_poses"].append({"ability": a, "regime": "sans_tuile"})
    out["ok"] = not (out["ecarts_uwb"] or out["ecarts_sans_tuile"] or out["refus_poses"])
    return out


# ------------------------------------------------------------------------------------------------
# ETAPE `mow_masques` -- le regime d'ECART du court-circuit `casterTiles` vide est-il vide ?
# ------------------------------------------------------------------------------------------------

def mow_masques() -> dict:
    """`AllowNullCasterTile` (bit 30) est la trace NATIVE du regime « caster sans tuile ». Ses
    porteurs portent-ils TOUS `use_whole_board` -- auquel cas le gate de DISTANCE, qui est le seul
    a lire `(int)range`, ne s'evalue jamais pour eux ?

    Et les unites `MachineOfWar` du gameconfig n'ont-elles QUE ces abilities-la ? Une seule active
    non-`UseWholeBoard` sur une MoW rouvrirait le gisement."""
    lus = _masques_lus()
    b30 = {a: o for a, o in lus.items() if int(o.rules) & int(TR.AllowNullCasterTile)}
    sans_wb = sorted(a for a, o in b30.items()
                     if o.range is None or not o.range.use_whole_board)
    idx = GC.all_unit_ids()
    mow, hors = [], []
    for k in idx:
        for u in idx[k]:
            d = GC.unit(u) or {}
            noms = [t.get("name") if isinstance(t, dict) else t for t in (d.get("traits") or [])]
            if not any(str(n) == "MachineOfWar" for n in noms):
                continue
            mow.append(u)
            for ent in GC.unit_abilities(u)["active"]:
                aid = ent["id"]
                o = lus.get(int(aid)) if aid is not None else None
                if o is None or o.range is None or not o.range.use_whole_board:
                    hors.append({"unit": u, "ability": aid, "nom": ent["name"]})
            # l'attaque normale : `MachineFactory$$Build` n'appelle jamais `AddNormalAttackAbility`
    return {"porteurs_bit30": len(b30), "bit30_sans_whole_board": sans_wb,
            "mow_gameconfig": len(mow),
            "actives_de_mow_hors_whole_board": hors,
            "gisement_vide": not sans_wb and not hors}


# ------------------------------------------------------------------------------------------------
# ETAPES LIVE
# ------------------------------------------------------------------------------------------------

def _build(p_mow, a_mow):
    state = ROOT / "logs" / "runners" / ("p419cc-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state), "--p-units", ESCORTE_P, "--a-units", ESCORTE_A,
            "--p-mow", p_mow]
    if a_mow:
        argv += ["--a-mow", a_mow]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    try:
        _rq(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


def mow_sans_tuile(paires=None) -> dict:
    """Le natif rend-il une MoW SANS TUILE -- c'est-a-dire `casterTiles` VIDE ?

    Canal : `decisionView.mows[]`, dont `pos` / `feet` / `platformTiles` projettent
    `EntityExtensions$$GetMainTile` / `GetTiles` sur la machine. Un `pos: null` avec `feet: []` EST
    le court-circuit `-r2`, observe chez le natif."""
    sid = _resolve_session()
    lignes, erreurs = [], []
    for p_mow, a_mow in (paires or [(MOW_POOL[0], MOW_POOL[1])]):
        rid, err = _build(p_mow, a_mow)
        if rid is None:
            erreurs.append({"p_mow": p_mow, "a_mow": a_mow, "err": err})
            continue
        try:
            dv = _rq(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
            for m in (dv.get("mows") or []):
                lignes.append({"visualId": m.get("visualId"), "pos": m.get("pos"),
                               "feet": m.get("feet"), "platformTiles": m.get("platformTiles"),
                               "abilities": [a.get("id") for a in (m.get("abilities") or [])]})
        finally:
            _dispose(sid, rid)
    sans_tuile = [l for l in lignes if l["pos"] is None and not l["feet"]]
    return {"mows_observees": len(lignes), "sans_tuile": len(sans_tuile),
            "lignes": lignes, "erreurs": erreurs,
            "toutes_sans_tuile": bool(lignes) and len(sans_tuile) == len(lignes)}


def stat_range(paires=None) -> dict:
    """`GetStat(caster, StatType.Range = 2)` -- les TROIS etages, mesures.

    L'etage RESOLU se lit sur `combatSnapshot.units[].stats.range`, dont le catalogue `statTypes`
    apparie la cle `range` a l'index **2**. On VERIFIE cet appariement au lieu de le supposer : sans
    lui, on mesurerait une cle homonyme."""
    # --- etage CATALOGUE ------------------------------------------------------------------------
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cfg = [c.get("Range") for c in (bc.get("Units") or []) if isinstance(c, dict)]
    catalogue = {"entrees": len(cfg), "valeurs_distinctes": sorted(set(map(repr, cfg)))}

    # --- etage MODIFICATION ---------------------------------------------------------------------
    gcj = json.loads((ROOT / "data" / "symbols" / _build_hash() / "gameconfig.json")
                     .read_text(encoding="utf-8"))
    noms = set()

    def _walk(o, p=""):
        if isinstance(o, dict):
            for k, v in o.items():
                _walk(v, p + "/" + str(k))
        elif isinstance(o, list):
            for v in o:
                _walk(v, p + "/[]")
        else:
            bas = p.lower()
            if bas.endswith("/stattype") or bas.endswith("/stat"):
                noms.add(repr(o))

    _walk(gcj)
    modification = {"valeurs_de_statType_du_gameconfig": sorted(noms),
                    "aucune_ne_nomme_range": not any("range" in n.lower() for n in noms)}

    # --- etage RESOLU ---------------------------------------------------------------------------
    sid = _resolve_session()
    obs, erreurs, appariement = [], [], []
    for p_mow, a_mow in (paires or [(MOW_POOL[i], MOW_POOL[i + 1]) for i in range(0, 8, 2)]):
        rid, err = _build(p_mow, a_mow)
        if rid is None:
            erreurs.append({"p_mow": p_mow, "a_mow": a_mow, "err": err})
            continue
        try:
            cs = _rq(sid, "combatSnapshot", {"runnerId": rid})
            appariement.append((cs.get("statTypes") or {}).get("range"))
            for u in (cs.get("units") or []):
                vid = u.get("configId")
                st = (u.get("stats") or {})
                obs.append({"configId": vid,
                            "arme": bool(((GC.unit(vid or "") or {}).get("weapons")) or []),
                            "range": st.get("range"),
                            "extraRange": st.get("extraRange"),
                            "delta_range": (u.get("statDelta") or {}).get("range")})
        finally:
            _dispose(sid, rid)
    sans_arme = [o for o in obs if not o["arme"]]
    return {"catalogue": catalogue, "modification": modification,
            "appariement_statTypes_range": sorted(set(appariement)),
            "appariement_est_bien_2": appariement != [] and set(appariement) == {int(StatType.RANGE)},
            "unites_observees": len(obs), "distinctes": len(set(o["configId"] for o in obs)),
            "sans_arme_observees": len(sans_arme),
            "sans_arme_distinctes": sorted(set(o["configId"] for o in sans_arme)),
            "toutes_a_zero": all(o["range"] == 0 for o in obs),
            "non_nulles": [o for o in obs if o["range"] not in (0, None)],
            "erreurs": erreurs}


def _build_hash() -> str:
    d = ROOT / "data" / "symbols"
    noms = [p.name for p in d.iterdir() if p.is_dir() and (p / "gameconfig.json").exists()]
    if len(noms) != 1:
        # plusieurs builds sur disque : on prend celui que la table de symboles ESTAMPILLE
        for n in noms:
            b = d / n / "BUILD"
            if b.exists() and b.read_text(encoding="utf-8").strip() == n:
                return n
    return noms[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="offline",
                    choices=["offline", "champ_alias", "court_circuits", "mow_masques",
                             "mow_sans_tuile", "stat_range"])
    a = ap.parse_args()
    if a.step in ("offline", "champ_alias"):
        print("champ_alias    :", json.dumps(champ_alias())[:900])
    if a.step in ("offline", "court_circuits"):
        print("court_circuits :", json.dumps(court_circuits())[:900])
    if a.step in ("offline", "mow_masques"):
        print("mow_masques    :", json.dumps(mow_masques())[:900])
    if a.step == "mow_sans_tuile":
        print("mow_sans_tuile :", json.dumps(mow_sans_tuile(), indent=1)[:2500])
    if a.step == "stat_range":
        print("stat_range     :", json.dumps(stat_range(), indent=1)[:3500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
