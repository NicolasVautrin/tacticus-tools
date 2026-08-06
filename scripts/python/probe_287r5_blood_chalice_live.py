"""#287-r5 -- BASCULE LIVE de la regle dynamique 1175 `BloodChalice`, contre l'oracle NATIF.

CE QUE CE PROBE MESURE.
`IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$GetDynamicInvalidTargetReason` :

    tiles = EntityExtensions.GetTiles(target, state);
    if (battleQuery.AreEntitiesAdjacent(tiles, casterTiles)          // this+0x20, slot 0x62
        && UnitExtensions.IsAffectedByHealType(target, HealType.NonMechanical))
        return 0;
    return (caster != target) ? 2 : 0;                               // TargetMatchesDynamicRule

La regle a DEUX termes conjoints, et un port ne les distingue pas d'un seul bras : une regle qui
n'aurait porte QUE l'adjacence serait verte sur un montage ou aucune cible mecanique n'est
adjacente. Le probe monte donc TROIS bras qui isolent chaque terme, et le QUATRIEME cas que la
queue du natif traite a part :

    A  allie NON-mecanique ADJACENT   -> 0     (les deux termes vrais)
    B  allie NON-mecanique LOINTAIN   -> voir ci-dessous : l'ETAGE PORTEE le prend d'abord
    C  allie MECANIQUE     ADJACENT   -> 0x2   (terme HEAL TYPE faux -- LivingMetal)
    D  le CASTER lui-meme             -> 0     (la queue `caster != target`, que le masque
                                                `AddCasterIfAtLeastOneTarget` rend atteignable)

Chaque bras est imprime avec l'ENTREE de chaque etage (adjacence mesuree, mecanique ou non), pas
seulement le verdict : c'est la decomposition par etage, pas un scalaire ajuste.

⚠ LE TERME ADJACENCE EST STRUCTURELLEMENT MASQUE, ET LE PROBE LE VERIFIE AU LIEU DE LE TAIRE.
`BloodChaliceAbility$$.ctor` pose `TargetingRange.OverrideRange = 1` : l'etage PORTEE de la cascade
refuse donc toute cible non adjacente par `0x8000000 TargetIsInRange`, EN AMONT du delegue -- mesure
du 2026-08-06, bras B : natif `0x8000000`, port `0x8000000`, identiques. Le terme adjacence de la
regle dynamique est REDONDANT avec cette portee et n'est pas observable par `abilityReason` sur ce
montage. Le probe l'ecrit NON EXERCE, et il ASSERTE sa cause (`override_range == 1`) : si un build
changeait cette portee, le terme redeviendrait exigible et le probe le REDEMANDERAIT. Un bras non
exerce se DECLARE avec sa cause -- il ne se compte jamais vert.

ATTRIBUTION. Les memes couples sont re-mesures la regle DESARMEE. Un refus qui SURVIT vient d'un
autre etage du masque (`0xc02` = `TargetMatchesDynamicRule | TargetIsFriendly |
AddCasterIfAtLeastOneTarget`) et n'est pas imputable a cette tranche.

Usage (session warmee ; le probe monte et DISPOSE son propre runner) :
    python scripts/python/probe_287r5_blood_chalice_live.py
ASCII only ; exit 0 = les quatre bras sont reproduits, et le desarmement efface les refus.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import (                            # noqa: E402
    are_entities_adjacent, entity_tiles, is_invalid_target, is_mechanical,
)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

LOGS = HERE.parents[1] / "logs"
BC = int(ActiveAbilityType.BloodChalice)              # 1175
PORTEUR = "bloodSanguinary"
REFUS = int(TR.TargetMatchesDynamicRule)

# Le roster, et le BRAS que chaque unite incarne. `necroWarden` porte `LivingMetal`, donc
# `IdunBattle.Entities.UnitExtensions$$IsMechanical` est vrai pour lui -- c'est ce qui isole le
# terme HEAL TYPE de celui d'ADJACENCE.
ROSTER = [
    (PORTEUR, "0,0", "D caster lui-meme"),
    ("thousTzaangor", "1,0", "A non-mecanique ADJACENT"),
    ("necroWarden", "0,1", "C MECANIQUE adjacent"),
    ("orksWarboss", "5,7", "B non-mecanique LOINTAIN"),
]


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r5 : bascule live de 1175 BloodChalice")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--state-file", default="rs_287r5_bc_live.json")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    state_file = LOGS / a.state_file
    args = ["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
            "--p-units", ",".join(u for u, _p, _l in ROSTER),
            "--a-units", "tyranNeurothrope", "--state-file", str(state_file)]
    for u, pos, _l in ROSTER:
        args += ["--place", "%s:%s" % (u, pos)]
    _run(args)
    if not state_file.exists():
        print("[287r5-bc] PAS MESURE : build KO (state-file absent)")
        return 2
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])

    try:
        dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
        snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
        bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
        board = Board(bg["tiles"], adjacency="evenq")
        state = load_state(dec, ob, snap, board=board)
        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        caster = next((u for u in units if u.get("visualId") == PORTEUR), None)
        if caster is None:
            print("[287r5-bc] PAS MESURE : porteur %s absent du montage" % PORTEUR)
            return 2
        libelle = {u: l for u, _p, l in ROSTER}
        ab = P._porteur(BC)
        ctiles = entity_tiles(state, int(caster["id"]))
        lignes = []
        for u in units:
            if u.get("team") != caster.get("team"):
                continue                       # `TargetIsFriendly` : hors domaine de cette regle
            r = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                       "abilityType": BC, "targetId": u["id"]}, 60000) or {}
            nat = int((r.get("targetReason") or {}).get("hex") or "0x0", 16)
            port = int(is_invalid_target(state, int(caster["id"]), int(u["id"]), ab) or 0)
            with P.desarme(BC):
                sans = int(is_invalid_target(state, int(caster["id"]), int(u["id"]), ab) or 0)
            adj = are_entities_adjacent(board, entity_tiles(state, int(u["id"])), ctiles)
            lignes.append((u["id"], u.get("visualId"), libelle.get(u.get("visualId"), "?"),
                           nat, port, sans, adj, is_mechanical(state, int(u["id"]))))
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])

    print("[287r5-bc] board=%s seed=%d runner=%d -- porteur %s u%s"
          % (a.board, a.seed, rid, PORTEUR, caster["id"]))
    print("  %-6s %-26s %-11s %-11s %-13s %-9s %s"
          % ("cible", "bras", "natif", "port", "port DESARME", "adjacent", "mecanique"))
    for tid, vis, lib, nat, port, sans, adj, mech in lignes:
        print("  u%-5s %-26s %-11s %-11s %-13s %-9s %s"
              % (tid, lib, hex(nat), hex(port), hex(sans), adj, mech))

    reproduits = all(l[3] == l[4] for l in lignes)
    refus = [l for l in lignes if l[3] & REFUS]
    accepte = [l for l in lignes if l[3] == 0]
    imputables = [l for l in refus if l[5] == 0]
    # Les DEUX termes doivent avoir mordu, sinon un port qui n'en aurait porte qu'un serait vert.
    terme_adjacence = [l for l in refus if not l[6]]
    terme_heal = [l for l in refus if l[6] and l[7]]
    print("[287r5-bc] BASCULE")
    print("  cible(s) acceptee(s) par le natif (0)                       : %d" % len(accepte))
    print("  cible(s) refusee(s) par le natif (TargetMatchesDynamicRule) : %d" % len(refus))
    print("  le port reproduit le masque natif sur TOUTES les cibles     : %s" % reproduits)
    # Le terme ADJACENCE n'est exigible que si l'etage PORTEE ne le precede pas. La cause est LUE
    # sur les options, pas supposee : `override_range == 1` == « portee 1 == adjacent ».
    from engine.runner.abilities.targeting import targeting_options_for
    rng = targeting_options_for(BC).range
    masque_par_portee = (rng is not None and rng.override_range == 1)
    print("[287r5-bc] LES DEUX TERMES ONT-ILS MORDU ?")
    print("  terme HEAL TYPE (refus sur une cible adjacente MECANIQUE)   : %d" % len(terme_heal))
    print("  terme ADJACENCE (refus sur une cible NON adjacente)         : %d" % len(terme_adjacence))
    if masque_par_portee:
        print("     NON EXERCE, et la CAUSE est mesuree : `BloodChaliceAbility$$.ctor` pose "
              "TargetingRange.OverrideRange = 1, donc l'etage PORTEE refuse toute cible non "
              "adjacente par TargetIsInRange EN AMONT du delegue. Le terme est REDONDANT avec "
              "cette portee et non observable par `abilityReason`.")
        for l in lignes:
            if not l[6]:
                print("     temoin u%s (non adjacent) : natif=%s port=%s -- identiques, refus pose "
                      "par l'etage PORTEE" % (l[0], hex(l[3]), hex(l[4])))
    print("[287r5-bc] ATTRIBUTION -- refus qui DISPARAISSENT au desarmement : %d / %d"
          % (len(imputables), len(refus)))
    for l in refus:
        if l[5] != 0:
            print("     u%s : le port refuse ENCORE (%s) regle DESARMEE -- vient d'un AUTRE etage"
                  % (l[0], hex(l[5])))

    ok = (reproduits and bool(accepte) and len(imputables) == len(refus) and bool(terme_heal)
          and (bool(terme_adjacence) or masque_par_portee))
    print("[287r5-bc] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
