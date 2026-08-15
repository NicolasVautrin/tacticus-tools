#!/usr/bin/env python
"""#477-r29 -- le terme d'adjacence de `RadSaturation` (1202) compte-t-il les ALLIES, ou LES DEUX CAMPS ?

QUESTION BINAIRE, posee avant la methode : sur une MEME decision, un MEME mover et des tuiles
candidates de MEME geometrie, le `Tile(7)` NATIF monte-t-il de `+10` UNIQUEMENT sur les tuiles
adjacentes a un Marshal ALLIE (modele ALLIES), ou aussi sur celles adjacentes a un Marshal ENNEMI
(modele DEUX CAMPS) ?

CE QUE DIT LE DECOMPILE (build courant, relu ligne a ligne) --
`IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

    units = query.<slot 0x83 = GetAdjacentFriends, 2 arguments>(case.MovementTile, case.Unit)
    n     = Enumerable.Count(units, <>c.<>9__2_0)
    yield Fix64((int)(config["RadSaturation_AdjacentMarshals"] * n))

et le predicat `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003Cu003Ec$$
u003CCalculateMovementUtilityInStepsInternalu003Eb__2_0` = `HasActiveAbility(f, 0x45e)` =
`ActiveAbilityType.DoctrinaImperatives` (l'ACTIVE d'`admecMarshall`). Le poids vaut **+10**.

LE CONTRASTE QUI REND LA QUESTION NON RHETORIQUE. Le MEME predicat `HasActiveAbility(0x45e)` est
utilise par une AUTRE feuille du meme composite -- `IdunBattle.AI.Utilities.
AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` (UtilityType
`DoctrinaImperatives_AttractMechanicals`) -- et celle-la interroge le slot **`0x7a` =
`GetAdjacentUnits`, 4 arguments** (plus une exclusion explicite de `case.Unit`, que `RadSaturation`
n'a pas). Les deux slots portent des noms differents et des arites differentes
(`data/symbols/<build>/metadata/interface_slots.tsv`).

⚠ CE PROBE A UN TEMPS ECRIT ICI « donc LES DEUX CAMPS ». C'EST FAUX, et #477-r31 l'a mesure :
la signature reelle est `GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)`, le
call-site passe `friendsOf = case.Unit`, et cette feuille compte donc **les AMIS elle aussi**. Le
nom du slot designe l'ensemble AVANT filtrage -- deduire le camp du NOM etait exactement la faute
de specification de `case-26`, repetee un cran plus loin. Ce qui separe reellement les deux
feuilles : le gate (`Mechanical`), le self (exclu la, inclus ici) et l'agregation (`Any` la,
`Count` ici). Detail : `docs/rl/case-477r31-attract-mechanicals-camp.md`.

⚠ CETTE FEUILLE-LA RESTE LE CONFOND DE CETTE MESURE -- pas par son camp, mais parce qu'elle vaut
AUSSI +10 sur les memes tuiles. Elle est gatee `HasTrait(case.Unit, 5)` = Mechanical, et le greffon
est donc REFUSE s'il est Mechanical (etape 0). Le VRAI porteur (`admecSmnVanguard`) l'est : il
cumule les deux termes. La feuille est PORTEE depuis #477-r31, si bien que ce refus est desormais
ce qui garde le GATE -- retirer le gate `Mechanical` rend CE probe rouge (-10 par tuile, mesure).

MONTAGE -- ON PILOTE LES POSITIONS (`--place` / `--a-place`, #477-r5), on ne subit pas la
geometrie : le carrier est pose sur une tuile choisie, un `admecMarshall` ALLIE et un
`admecMarshall` ENNEMI sont poses SYMETRIQUEMENT de part et d'autre. Les deux bras vivent donc
dans la MEME decision, sur le MEME sweep, avec la MEME distance -- **seul le CAMP change**. Un
board ou allies et ennemis sont adjacents en meme temps serait un regime DEGENERE.

Le porteur reel de 1202 est un SUMMON (`admecSmnVanguard`) : on l'OBSERVE, on ne le COMMANDE pas.
Le passif est donc GREFFE sur un heros du pool (`catalog_inject.graft_passive_ability`), ce qui
est ici une MESURE et non un contournement -- le corps natif ne lit ni stats ni traits du caster,
seulement `case.Unit` (pour resoudre le camp) et `case.MovementTile`.

MESURE, decomposee par etage (hooks EXISTANTS de `scorer-damage-trace`, armes pour UN SEUL
`aiStepDryRun` puis desarmes -- AUCUNE reinjection) :

    X_nat (tuile) = Tile(7) - Elevation - TileEffects
    X_port(tuile) = feuilles du port, MEME retranchement (foyer unique `probe_193c.x_port`)
    X_both(tuile) = X_port - terme(ALLIES) + terme(DEUX CAMPS)      <- le modele de `case-26`

VERDICT (les deux sont exiges) :
  1. ACCORD    : `X_nat == X_port` sur toutes les tuiles hookees ;
  2. SEPARATION: il existe au moins une tuile hookee ou `terme(DEUX CAMPS) != terme(ALLIES)` --
     sans elle, la mesure ne peut pas distinguer les deux modeles, et un vert ne prouverait rien.

Usage (ASCII only, depuis scripts/python) :
  python probe_477r29_rad_saturation_camp.py --offline-only
  python probe_477r29_rad_saturation_camp.py --board MC1_67 --seed 777
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog_inject                                              # noqa: E402
from build_pin import BuildPinRefused                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                # noqa: E402
from probe_193c_move_playbook_terms import (_r, _by_tile, _one, _port_leaves,   # noqa: E402
                                            _exiger_build_des_rva, x_port,
                                            cause_x_nat_non_mesurable)
from probe_212_spiritual_leader_tile_term import _apply_native_via   # noqa: E402  (`call` injecte)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

ABILITY = 1202                       # TriggeredAbilityType.RadSaturation (0x4b2)
MARSHAL_UNIT = "admecMarshall"       # porte l'ACTIVE DoctrinaImperatives (0x45e = 1118)
GRAFT = "orksNob"                    # greffon : HERO du pool, MELEE, NON Mechanical (cf. etape 0)
TARGET_FOE = "necroWarden"           # la CIBLE melee, sans DoctrinaImperatives -- cf. ci-dessous

#: PLACEMENTS (col,row) sur `MC1_67`, cherches pour que les DEUX bras vivent dans la MEME decision.
#:
#: ⚠ LA CONTRAINTE QUI COMMANDE LA GEOMETRIE : les hooks `scorerTileTermTrace` ne voient que les
#: tuiles evaluees par le tier COMPARABLE, c.-a-d. les tuiles d'ATTAQUE (voisines d'une cible
#: rangee) -- un sous-ensemble strict des `action_tiles`. Une premiere disposition (Marshals de part
#: et d'autre du carrier) a rendu 6 tuiles hookees, TOUTES du bras ENNEMI : elles etaient les
#: voisines du Marshal adverse, donc toutes adjacentes a lui. Le bras ALLIE etait vide et la mesure
#: ne pouvait rien trancher.
#: D'ou la disposition retenue : une CIBLE NEUTRE (`necroWarden`, sans `DoctrinaImperatives`) au
#: milieu, et les deux Marshals a distance 2 d'elle, de part et d'autre. Les tuiles d'attaque de
#: cette cible se ventilent alors en trois groupes MIROIR :
#:     (3,7) (3,8) -> adjacentes au Marshal ALLIE seul
#:     (5,7) (5,8) -> adjacentes au Marshal ENNEMI seul
#:     (4,6) (4,8) -> adjacentes a aucun des deux (temoin)
#: Zone STRICTEMENT PLATE (meme elevation sur les 9 tuiles) : la porte `|dElev| < 2`
#: d'`IterateAdjacentTiles` ne peut pas introduire d'asymetrie entre les deux bras.
#: `board -> (carrier, marshal ALLIE, marshal ENNEMI, cible neutre)`. Les geometries sont
#: CHERCHEES, pas devinees : sur chaque board on enumere les triplets `(cible, A, E)` tels que les
#: voisines de la cible portent >= 2 tuiles « A seul », >= 2 tuiles « E seul » et >= 1 temoin, la
#: zone entiere etant a elevation CONSTANTE et `A` non adjacent a `E`. Deux boards sur quatre
#: essayes en admettent une (`C1_25` et `C1_02` n'en ont AUCUNE : c'est une contrainte de terrain,
#: pas un choix).
LAYOUTS = {
    "MC1_67": {"carrier": (4, 5), "ally": (2, 7), "foe": (6, 7), "target": (4, 7)},
    "C4_09":  {"carrier": (4, 2), "ally": (2, 2), "foe": (5, 1), "target": (3, 1)},
}
POS_CARRIER = LAYOUTS["MC1_67"]["carrier"]
POS_MARSHAL_ALLY = LAYOUTS["MC1_67"]["ally"]
POS_MARSHAL_FOE = LAYOUTS["MC1_67"]["foe"]
POS_TARGET = LAYOUTS["MC1_67"]["target"]


def _slot_table(build: str) -> dict:
    """`(interface, slot) -> (nom, arite)` depuis l'entree VERSIONNEE `metadata/interface_slots.tsv`."""
    p = ROOT / "data" / "symbols" / build / "metadata" / "interface_slots.tsv"
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        cells = line.split("\t")
        if len(cells) < 4:
            continue
        try:
            out[(cells[0], int(cells[1]))] = (cells[2], int(cells[3]))
        except ValueError:
            continue
    return out


def _build_hash() -> str:
    import build_pin
    return build_pin.installed_build()


# --------------------------------------------------------------------------------------------
# ETAPE 0 -- offline : le SLOT lu dans la table, le POIDS, et la garde de CONFOND
# --------------------------------------------------------------------------------------------
def step0() -> int:
    import io
    import contextlib
    import gameconfig as GC
    from engine import weights as W
    from engine.playbook.adjacent_unit_preference import load_playbook
    from engine.playbook.rad_saturation import RadSaturationPlaybook
    from engine.entities.traits.unit_trait import UnitTrait

    print("=== ETAPE 0 (offline) ===")
    rc = 0
    build = _build_hash()
    tbl = _slot_table(build)
    # 0x83 = le slot APPELE par RadSaturationPlaybook ; 0x7a = celui de la feuille CONFOND.
    for iface, slot, attendu_nom, attendu_arite in (("IBattleQuery", 0x83, "GetAdjacentFriends", 2),
                                                    ("IBattleQuery", 0x7a, "GetAdjacentUnits", 4)):
        got = tbl.get((iface, slot))
        ok = got == (attendu_nom, attendu_arite)
        print("  slot 0x%02x -> %-20s arite %s   [%s]"
              % (slot, (got or ("?", "?"))[0], (got or ("?", "?"))[1], "OK" if ok else "ROUGE"))
        if not ok:
            rc = 1
    print("  => le slot du playbook est un GetAdjacentFriends (ALLIES), celui de la feuille "
          "DoctrinaImperatives_AttractMechanicals un GetAdjacentUnits (DEUX CAMPS)")

    # POIDS : capture vs gameconfig VIVANT (piege #271 -- une mesure menee sur la capture peut
    # rendre « aucun ecart » et conclure a tort a l'inertie).
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = (((bc.get("Utilities") or {}).get("Default") or {})
           .get("TriggeredAbilities") or {}).get(RadSaturationPlaybook.WEIGHT_KEY)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    live = wt.sub("TriggeredAbilities", RadSaturationPlaybook.WEIGHT_KEY)
    repli = "repli" in (err.getvalue() or "").lower()
    print("  poids %-32s capture=%s  moteur=%s%s"
          % (RadSaturationPlaybook.WEIGHT_KEY, cap, live, "  [REPLI CAPTURE]" if repli else ""))
    if not live:
        print("  ROUGE : poids nul -> le terme serait plat, la mesure ne peut rien contredire")
        rc = 1

    # PORT : la feuille est-elle enregistree ?
    pb = load_playbook(ABILITY)
    print("  registre TRIGGERED_MOVE_PLAYBOOKS[%d] = %s" % (ABILITY, type(pb).__name__ if pb else None))
    if pb is None:
        print("  ROUGE : 1202 absente du registre -> le port ne calcule AUCUN terme")
        rc = 1

    # CONFOND : le greffon ne doit PAS etre Mechanical (feuille 57, residu #477-r31).
    traits = (GC.unit(GRAFT) or {}).get("traits") or []
    mech = UnitTrait.Mechanical.name in traits
    print("  greffon %-14s traits=%s  Mechanical=%s" % (GRAFT, traits, mech))
    if mech:
        print("  ROUGE : greffon Mechanical -> la feuille DoctrinaImperatives_AttractMechanicals "
              "ajoute son propre +10 sur LES MEMES tuiles ; X_nat ne trancherait rien")
        rc = 1
    # et il doit porter DoctrinaImperatives... non : c'est le MARSHAL qui la porte.
    act = (GC.unit(MARSHAL_UNIT) or {}).get("activeAbilities") or []
    print("  %-14s activeAbilities=%s" % (MARSHAL_UNIT, act))
    if "DoctrinaImperatives" not in act:
        print("  ROUGE : le porteur du predicat ne porte pas DoctrinaImperatives")
        rc = 1
    print("  ETAPE 0 : %s" % ("OK" if rc == 0 else "ROUGE"))
    return rc


# --------------------------------------------------------------------------------------------
# MODELES compares -- le port (ALLIES) et celui de `case-26` (DEUX CAMPS)
# --------------------------------------------------------------------------------------------
def _marshals(units, tile, leaf_ctx):
    """Nombre d'unites de `units` ADJACENTES a `tile` (adjacence NATIVE) portant 0x45e."""
    from engine import battle_query as bq
    from engine.playbook.rad_saturation import RadSaturationPlaybook
    elev = leaf_ctx.get("elev_by_pos")
    neigh = bq.neigh_map(leaf_ctx)
    n = 0
    for u in (units or ()):
        p = u.get("pos")
        if p and bq.is_adjacent(tile, p, elev, neigh) \
                and int(RadSaturationPlaybook.MARSHAL_ABILITY) in (u.get("active") or ()):
            n += 1
    return n


def _profile(tile, leaf_ctx):
    """`(nAllies, nEnnemis)` de Marshals adjacents a la tuile candidate."""
    return (_marshals(leaf_ctx.get("friend_units"), tile, leaf_ctx),
            _marshals(leaf_ctx.get("enemy_units"), tile, leaf_ctx))


def _self_is_marshal(tile, leaf_ctx) -> int:
    """1 si le MOVER lui-meme (encore sur son origine) est un Marshal adjacent a `tile`."""
    from engine import battle_query as bq
    from engine.playbook.rad_saturation import RadSaturationPlaybook
    sp = leaf_ctx.get("self_pos")
    if not sp:
        return 0
    if not bq.is_adjacent(tile, tuple(sp), leaf_ctx.get("elev_by_pos"), bq.neigh_map(leaf_ctx)):
        return 0
    return int(int(RadSaturationPlaybook.MARSHAL_ABILITY)
               in (leaf_ctx.get("unit_active_abilities") or ()))


def _friends_adjacent(tile, leaf_ctx) -> int:
    """Tous les AMIS adjacents, self inclus -- sans le predicat `HasActiveAbility`."""
    from engine import battle_query as bq
    elev, neigh = leaf_ctx.get("elev_by_pos"), bq.neigh_map(leaf_ctx)
    n = sum(1 for u in (leaf_ctx.get("friend_units") or ())
            if u.get("pos") and bq.is_adjacent(tile, u["pos"], elev, neigh))
    sp = leaf_ctx.get("self_pos")
    if sp and bq.is_adjacent(tile, tuple(sp), elev, neigh):
        n += 1
    return n


def _models(tile, leaf_ctx, wt, pb) -> dict:
    """Le terme rendu par CHAQUE modele confronte -- le port, et les mutants de la contre-epreuve.

    Le port est appele par son VRAI foyer (`pb.calculate_movement_utility_in_steps`) ; les mutants
    sont recalcules ici a partir des memes entrees. `a_mordu` se lit ensuite modele par modele,
    SEPAREMENT du verdict."""
    from engine.playbook.rad_saturation import RadSaturationPlaybook
    w = int(wt.sub("TriggeredAbilities", RadSaturationPlaybook.WEIGHT_KEY))
    na, ne = _profile(tile, leaf_ctx)
    slf = _self_is_marshal(tile, leaf_ctx)
    return {
        "PORT (allies)":      pb.calculate_movement_utility_in_steps(tile, leaf_ctx, wt),
        "DEUX-CAMPS":         float(w * (na + ne + slf)),        # la spec de `case-26`
        "ENNEMIS":            float(w * ne),                     # camp inverse
        "SANS-PREDICAT":      float(w * _friends_adjacent(tile, leaf_ctx)),
        "POIDS -25":          float(-25 * (na + slf)),           # le multiplicateur de `case-26`
        "ABSENT (avant)":     0.0,                               # le port d'avant cette tranche
        "SELF-EXCLU":         float(w * na),                     # inertie PAR ALGEBRE, cf. verdict
    }


# --------------------------------------------------------------------------------------------
# ETAPE 1 -- live
# --------------------------------------------------------------------------------------------
def _seed_bc_greffe(out_path: Path) -> Path:
    """Copie du seed BC ou `GRAFT` porte le passif `RadSaturation` et RIEN d'autre."""
    bc = catalog_inject._load_seed(None)
    rep = catalog_inject.graft_passive_ability(bc, GRAFT, "RadSaturation", replace=True)
    print("  greffe : %s passifs %s -> %s (config ajoutee: %s)"
          % (rep["unitId"], rep["passiveAbilitiesBefore"], rep["passiveAbilitiesAfter"],
             rep["configAdded"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    return out_path


def build_extra(board: str) -> list:
    """Les arguments `rl_duel build` du montage -- FOYER UNIQUE, partage avec la garde.

    Refuse un board sans geometrie plutot que de replier sur celle d'un autre : un placement
    hors zone plate reintroduirait l'asymetrie d'elevation que le montage exclut."""
    lay = LAYOUTS.get(board)
    if lay is None:
        raise SystemExit("[477-r29] aucune geometrie pour le board %r (connus : %s). En chercher "
                         "une : triplet (cible, ALLIE, ENNEMI) a elevation CONSTANTE tel que les "
                         "voisines de la cible portent >= 2 tuiles 'ALLIE seul', >= 2 'ENNEMI "
                         "seul' et >= 1 temoin." % (board, ", ".join(sorted(LAYOUTS))))
    return ["--seed-bc", "<pose par l'appelant>",
            "--p-units", "%s,%s" % (GRAFT, MARSHAL_UNIT),
            "--a-units", "%s,%s" % (MARSHAL_UNIT, TARGET_FOE),
            "--place", "%s:%d,%d" % (GRAFT, lay["carrier"][0], lay["carrier"][1]),
            "--place", "%s:%d,%d" % (MARSHAL_UNIT, lay["ally"][0], lay["ally"][1]),
            "--a-place", "%s:%d,%d" % (MARSHAL_UNIT, lay["foe"][0], lay["foe"][1]),
            "--a-place", "%s:%d,%d" % (TARGET_FOE, lay["target"][0], lay["target"][1]),
            "--hp-player", "100000", "--hp-target", "100000"]


def _build(seed, board, seed_bc: Path, state: Path):
    extra = build_extra(board)
    extra[1] = str(seed_bc)
    argv = ([sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
             "--state-file", str(state)] + extra)
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:\n%s" % ((p.stderr or p.stdout or "")[-2500:]))
        return None
    print((p.stdout or "").strip()[-900:])
    return json.loads(state.read_text())["runnerId"]


def mesurer(call, rid, max_steps=25, trace=print) -> dict:
    """Marche la trajectoire NATIVE jusqu'au pas ou les DEUX bras sont HOOKES, arme les hooks de
    `scorer-damage-trace` pour UN SEUL `aiStepDryRun`, et rend la mesure.

    `call(method, body, timeout)` est INJECTE : le probe passe son RPC de session, la garde
    (`tests/engine/test_477r29_rad_saturation_camp_live.py`) passe la fixture du harnais -- un
    seul montage, deux consommateurs, aucun fork.

    Rend `{"erreur": <str>}` si le regime n'est pas atteint, sinon
    `{"rows": [...], "prof": {...}, "ctx": ..., "wt": ..., "step": n, "uid": n}` ou chaque ligne
    est `{"tile", "x_nat", "x_port", "models", "na", "ne", "self"}`."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.adjacent_unit_preference import load_playbook

    pb = load_playbook(ABILITY)
    if pb is None:
        return {"erreur": "ability %d absente de TRIGGERED_MOVE_PLAYBOOKS" % ABILITY}
    dv0 = call("decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    carrier_id = next((u.get("id") for u in (dv0.get("units") or [])
                       if u.get("visualId") == GRAFT and u.get("ctrl")), None)
    trace("  carrier u%s (%s)" % (carrier_id, GRAFT))
    if carrier_id is None:
        return {"erreur": "greffon %s absent de la bataille" % GRAFT}

    step, seen = 0, 0
    while step < max_steps:
        dry = call("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"erreur": "trajectoire native epuisee au pas %d (%s) apres %d activation(s)"
                              % (step, dry.get("error"), seen)}
        if dry.get("activatedUnitId") != carrier_id:
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        seen += 1
        dv = call("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = call("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        wt = W.load()
        pred = _scene.build_predictor(call, rid)
        ctx = _ai_ctx.build(call, rid, dv, mov_by_unit, carrier_id, wt, pred)
        tiles = list(ctx.action_tiles or [])
        prof = {t: _profile(t, _port_leaves(ctx, t)[1]) for t in tiles}
        bras_a = [t for t, (na, ne) in prof.items() if na > 0 and ne == 0]
        bras_e = [t for t, (na, ne) in prof.items() if ne > 0 and na == 0]
        trace("  pas %-3d activation #%d : %d candidates | bras ALLIE=%d bras ENNEMI=%d"
              % (step, seen, len(tiles), len(bras_a), len(bras_e)))
        if not (bras_a and bras_e):
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        # --- regime realise : on arme les hooks pour UN SEUL dry-run ------------------------
        call("scorerDamageTraceOn", {"runnerId": rid}, 90)
        call("scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
        try:
            call("aiStepDryRun", {"runnerId": rid}, 90)
            tterm = call("scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
            elev = call("scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
            leaf = call("scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
        finally:
            call("scorerDamageTraceOff", {"runnerId": rid}, 60)

        tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
        el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
        te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                      "col", "row", "value")
        if not tt:
            return {"erreur": "aucun event tileTerm -- hooks non armes ou aucun tier Comparable"}
        hooked = [t for t in tiles if t in tt]
        ha = [t for t in hooked if prof[t][0] > 0 and prof[t][1] == 0]
        he = [t for t in hooked if prof[t][1] > 0 and prof[t][0] == 0]
        trace("  tuiles HOOKEES=%d | bras ALLIE=%d bras ENNEMI=%d"
              % (len(hooked), len(ha), len(he)))
        if not (ha and he):
            trace("  les hooks n'ont pas couvert les DEUX bras -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        rows = []
        for t in sorted(hooked):
            vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
            leaves, lc = _port_leaves(ctx, t)
            x = (vt - ve - vf) if None not in (vt, ve, vf) else None
            rows.append({"tile": t, "x_nat": x, "x_port": x_port(leaves),
                         "models": _models(t, lc, wt, pb),
                         "na": prof[t][0], "ne": prof[t][1],
                         "self": _self_is_marshal(t, lc),
                         "tile7": vt, "elev": ve, "tile_eff": vf})
        out = {"rows": rows, "prof": prof, "ctx": ctx, "wt": wt, "step": step, "uid": carrier_id,
               "bras_allie": ha, "bras_ennemi": he}
        # LE CRAN (#10011) : aucune ligne mesurable = un SILENCE, pas une mesure. Sans lui,
        # `divergences` rend 0 pour TOUS les modeles et le verdict d'accord passe A VIDE. CHAMP et
        # non ecrasement : le MONTAGE est mesure et juste, seul le canal NATIF manque.
        if not any(r["x_nat"] is not None for r in rows):
            out["x_nat_indisponible"] = cause_x_nat_non_mesurable(call, rid, tt, el, te)
        return out

    return {"erreur": "aucun pas DISCRIMINANT en %d pas (%d activations du carrier)"
                      % (max_steps, seen)}


def divergences(rows) -> dict:
    """`{nom de modele: nombre de tuiles ou X_nat != X_<modele>}` -- la contre-epreuve, chiffree.

    Le modele `PORT (allies)` y figure comme les autres : sa colonne EST le verdict d'accord, et
    `a_mordu` se lit de la meme facon pour tous, SEPAREMENT du verdict."""
    out = {}
    for nom in (rows[0]["models"] if rows else {}):
        n = 0
        for r in rows:
            if r["x_nat"] is None:
                continue
            xm = r["x_port"] - r["models"]["PORT (allies)"] + r["models"][nom]
            if abs(r["x_nat"] - xm) > 1e-6:
                n += 1
        out[nom] = n
    return out


def run(call, rid, max_steps=25) -> int:
    mes = mesurer(call, rid, max_steps)
    if mes.get("erreur"):
        print("  ROUGE : %s" % mes["erreur"])
        return 1
    rows = mes["rows"]
    print("\n  tuile      nA nE self | Tile7nat  Elev  TileEff  X_nat  | X_port  DELTA")
    bad = 0
    for r in rows:
        d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
        if d is not None and abs(d) > 1e-6:
            bad += 1
        print("  %-10s %2d %2d %4d | %-9s %-5s %-8s %-6s | %-7.4g %s"
              % (r["tile"], r["na"], r["ne"], r["self"], r["tile7"], r["elev"], r["tile_eff"],
                 r["x_nat"], r["x_port"], ("%.4g" % d) if d is not None else "?"))

    # ---- CONTRE-EPREUVE : chaque modele mutant DOIT diverger du natif ----------------------
    # `a_mordu` est rendu SEPAREMENT du verdict : un mutant qui ne mord pas n'invalide pas la
    # mesure, il DIT que ce montage ne le separe pas -- et c'est une information, pas un vert.
    mordu = divergences(rows)
    print("\n  CONTRE-EPREUVE (X_nat vs X_<modele>, sur les %d tuiles hookees) :" % len(rows))
    for nom, n in mordu.items():
        print("    %-16s divergences = %d / %d   a_mordu=%s"
              % (nom, n, len(rows), "OUI" if n else "NON"))

    rc = 0
    if bad:
        print("\n  ACCORD : ROUGE -- %d tuile(s) en desaccord X_nat vs X_port sur %d"
              % (bad, len(rows)))
        rc = 1
    else:
        print("\n  ACCORD : VERT -- 0 desaccord X_nat vs X_port sur %d tuiles" % len(rows))
    # SEPARATION : le mutant qui EST la question du cas doit mordre.
    if not mordu.get("DEUX-CAMPS"):
        print("  SEPARATION : ROUGE -- le modele DEUX CAMPS rend la MEME chose que le modele "
              "ALLIES sur ce montage : REGIME DEGENERE, rien n'est tranche")
        rc = 1
    else:
        print("  SEPARATION : VERT -- le modele DEUX CAMPS diverge du natif sur %d tuile(s) : "
              "le natif compte les ALLIES" % mordu["DEUX-CAMPS"])
    # INERTIE PAR ALGEBRE, declaree et assertionnee DANS LES DEUX SENS : aucune unite de ce build
    # ne porte a la fois 1202 (RadSaturation) et 1118 (DoctrinaImperatives), donc le volet SELF du
    # corps natif ne peut pas mordre -- ici comme ailleurs.
    self_actif = any(r["self"] for r in rows)
    if mordu.get("SELF-EXCLU") or self_actif:
        print("  SELF : le volet self a MORDU (self_marshal=%s) -- l'inertie declaree est FAUSSE"
              % self_actif)
        rc = 1
    else:
        print("  SELF : INERTE PAR ALGEBRE sur ce montage (le mover ne porte pas 0x45e) -- "
              "le mutant SELF-EXCLU ne peut pas mordre, et c'est ASSERTIONNE")
    print("  VERDICT : %s" % ("ROUGE" if rc else "VERT"))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=25)
    a = ap.parse_args()

    rc0 = step0()
    if a.offline_only:
        return rc0
    if rc0:
        print("ETAPE 0 ROUGE -> on n'arme rien (une mesure sur un montage faux ne prouve rien)")
        return rc0
    try:
        _exiger_build_des_rva()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    call = (lambda m, b, t=90: _r(sid, m, b, t))
    print("\n=== ETAPE 1 (live) ===")
    if a.runner is not None:
        return run(call, a.runner, a.max_steps)
    tag = uuid.uuid4().hex[:8]
    state = ROOT / "logs" / "runners" / ("probe477r29-%s.json" % tag)
    seed_bc = ROOT / "logs" / "runners" / ("probe477r29-seedbc-%s.json" % tag)
    _seed_bc_greffe(seed_bc)
    rid = _build(a.seed, a.board, seed_bc, state)
    if rid is None:
        return 1
    print("  runner %d seed=%s board=%s" % (rid, a.seed, a.board))
    try:
        return run(call, rid, a.max_steps)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        for p in (state, seed_bc):
            try:
                p.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
