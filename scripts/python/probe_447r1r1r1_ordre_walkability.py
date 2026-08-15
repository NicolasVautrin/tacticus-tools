"""#447-r1-r1-r1 -- l'ORDRE du retrait des NON MARCHABLES vs l'ajout aval de `casterTiles`.

LA QUESTION BINAIRE. Le `RemoveAll` de walkability s'applique-t-il a la tuile que
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` RE-AJOUTE apres coup ?

LA REPONSE EST DANS LA STRUCTURE, et elle est NON. Relu a l'octet sur le build courant :

    // IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange -- DERNIERE instruction du corps
    if ((options.Rules & AllowUnwalkableTargetTile) == 0)                       // bit 43
        RemoveAll(zone, TargetingQuery.u003Cu003Ec$$u003CGetTilesInRangeu003Eb__36_0);

    // IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions -- APRES l'appel
    tiles = GetTilesInRange(...)
    if (rules >> 0xf & 1)          tiles.<IOrderedSet slot 0>(casterTiles)      // bit 15
    if (rules & 0x200000000000000) tiles.<IOrderedSet slot 0>(casterTiles)      // bit 57
    ... puis les TROIS `RemoveAll` (b__0 portee/ami, b__1 ligne de vue, b__2 gate dynamique)

Le filtre de walkability est donc STRICTEMENT EN AMONT des deux ajouts, contrairement aux trois
predicats, qui sont en aval et s'y appliquent bien. Le port appliquait `_unwalkable` APRES
`tiles_in_range_zone_contains`, donc aussi a une tuile entree par le seul ajout aval : ecart
RESTRICTIF, corrige par `ability_range.verse_par_ajout_aval`.

CE QUE CE PROBE MESURE, ET CE QU'IL NE PEUT PAS. La condition d'ecart porte sur `casterTiles`,
c'est-a-dire la tuile OU SE TIENT LE CASTER : il faut qu'elle soit NON MARCHABLE ou EN BROUILLARD.

  * **etape `synthetique`** -- EXERCE le quirk, sans bataille : on interroge
    `is_tile_in_range_of_any_ability` a `d = 0` avec une carte `is_in_fog_by_pos` qui met la tuile
    du caster en brouillard. Avant le correctif le port RETIRE, apres il GARDE (et le controle sans
    bit 15 continue de retirer, sinon on aurait juste desarme la walkability) ;
  * **etape `gisement`** -- mesure LIVE l'intersection « tuile OCCUPEE et (fog ou non marchable) »
    sur des boards contrastes, via `boardGraph` (`walkable`, `isInFog`, `occupantUnitId`). Elle est
    attendue VIDE, et la CAUSE est structurelle : `AddUnitOperation$$AreTilesDisallowedAndLog`
    refuse une tuile qui ne passe pas son gate `<IBattleQuery slot 0xa1>` ou dont le
    `TileContentComponent$$IsFilled` est vrai, `GetMovableTilesFor` ne rend pas de tuile en
    brouillard, et le brouillard RECULE (il se leve a l'exploration) au lieu d'avancer.

⚠ LE BOARD A BROUILLARD EST INDISPENSABLE, et un board pvp ne dit rien. Mesure : `MC1_67` porte
**0** tuile en fog sur 63 -- y conclure << pas de gisement >> serait un accord en regime DEGENERE.
`C6_02` en porte **32** sur 63 : c'est LUI qui rend la mesure non vide du cote du fog.

⚠ CE QUE LE CANAL NE PEUT PAS MONTRER, et le probe le DIT plutot que de rendre un zero : sur un
board a salles, les unites d'une salle fermee ne sont pas ENCORE instanciees (mesure : trois
unites adverses demandees au build, `observeBattle.counts.units` en rend **3** au lieu de 6). Le
zero de l'intersection ne peut donc pas etre lu comme << une unite ne peut jamais etre dans le fog >>
sans l'argument structurel ci-dessus. C'est pourquoi le verdict de la tranche est
<< quirk PORTE, exerce par un cran SYNTHETIQUE, NON CONFRONTE live >>, jamais << gisement vide >>
tout court.

Le TEST qui garde le port est `tests/engine/test_447r1r1r1_ordre_walkability_offline.py`.
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from engine.runner.abilities import targeting as TGT                      # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES               # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR    # noqa: E402
from engine.services import ability_range as AR                           # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: Les boards du sondage : un pvp SANS brouillard (temoin du regime degenere) et un board de
#: campagne a SALLES, qui en porte. Le second est ce qui rend la mesure discriminante.
BOARDS = ["MC1_67", "C6_02"]
P_UNITS = "tauCrisis,tauMarksman,astraCreed"
A_UNITS = "necroSpyder,ultraEliminatorSgt,orksNob"


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rq(sid, method, body=None, timeout=90):
    return _res(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _porteur_bit15():
    """Une ability du registre a bit 15 (ou 57) ET sans `AllowUnwalkableTargetTile` -- le seul
    regime ou le quirk peut mordre. Rendue avec un controle SANS ces bits, meme `TargetingRange`
    autant que possible."""
    lus = {}
    for a in ABILITY_CLASSES:
        o = TGT.targeting_options_for(a)
        if o is not None and getattr(o, "rules", None) is not None:
            lus[int(a)] = o
    aval = int(TR.CasterIsPossibleTarget) | int(TR.TargetIsCasterOrEnemy)
    porteurs = sorted(a for a, o in lus.items()
                      if (int(o.rules) & aval) and not (int(o.rules) & int(TR.AllowUnwalkableTargetTile)))
    controles = sorted(a for a, o in lus.items()
                       if not (int(o.rules) & aval)
                       and not (int(o.rules) & int(TR.AllowUnwalkableTargetTile)))
    return porteurs, controles, lus


def synthetique() -> dict:
    """EXERCE le quirk sur une carte de brouillard FABRIQUEE. DEUX bras, et le second existe parce
    que le premier seul ne distinguerait pas le correctif d'un simple DESARMEMENT de la walkability.

    BRAS A -- la tuile SOURCE (`d = 0`) d'un porteur de l'ajout aval, mise en brouillard. Le
    critere n'est PAS « elle est gardee » mais « le brouillard n'y change RIEN » : plusieurs
    porteurs du bit 15 sont deja retires par un etage AMONT (le court-circuit
    `TargetIsFriendly && !TargetIsEnemy` de `GetPossibleTargetTiles`), et exiger `True` melangerait
    les deux etages. `garde_sous_fog == garde_sans_fog` isole exactement le quirk.

    BRAS B -- une tuile a `d = 1` du MEME porteur, mise en brouillard. Elle, elle entre par
    `GetTilesInRange`, donc le `RemoveAll` DOIT continuer a la retirer. Sans ce bras, un correctif
    qui aurait simplement supprime l'appel a `_unwalkable` passerait pour juste."""
    porteurs, controles, lus = _porteur_bit15()
    if not porteurs:
        return {"ok": False, "raison": "aucun porteur de l'ajout aval dans le registre"}
    src = (3, 3)
    voisine = (4, 3)
    walkable_ok = {src: True, voisine: True}
    bras_a, bras_b = [], []
    for aid in porteurs:
        o = lus[aid]
        # `visual_id` VIDE : l'ajout aval ne consulte NI la portee NI la branche prise -- c'est le
        # fait porte par `#447-r1-r1` §4, et c'est pourquoi il echappe au filtre amont.
        sous = AR.is_tile_in_range_of_any_ability(
            src, src, "", ability_ids=[aid],
            walkable_by_pos=walkable_ok, is_in_fog_by_pos={src: True, voisine: False})
        sans = AR.is_tile_in_range_of_any_ability(
            src, src, "", ability_ids=[aid],
            walkable_by_pos=walkable_ok, is_in_fog_by_pos={src: False, voisine: False})
        bras_a.append({"ability": aid, "rules": hex(int(o.rules)),
                       "sous_fog": bool(sous), "sans_fog": bool(sans),
                       "inchange": bool(sous) == bool(sans)})
        v_sous = AR.is_tile_in_range_of_any_ability(
            src, voisine, "", ability_ids=[aid],
            walkable_by_pos=walkable_ok, is_in_fog_by_pos={src: False, voisine: True})
        v_sans = AR.is_tile_in_range_of_any_ability(
            src, voisine, "", ability_ids=[aid],
            walkable_by_pos=walkable_ok, is_in_fog_by_pos={src: False, voisine: False})
        bras_b.append({"ability": aid, "sous_fog": bool(v_sous), "sans_fog": bool(v_sans),
                       "retire_par_le_fog": bool(v_sans) and not bool(v_sous)})
    a_ok = all(l["inchange"] for l in bras_a)
    discriminants = [l for l in bras_b if l["sans_fog"]]
    b_ok = bool(discriminants) and all(l["retire_par_le_fog"] for l in discriminants)
    return {"porteurs_de_l_ajout_aval": len(porteurs),
            "bras_a_source": bras_a, "bras_b_voisine": bras_b,
            "A_le_fog_sur_la_source_ne_change_rien": a_ok,
            "B_le_fog_retire_encore_une_tuile_de_GetTilesInRange": b_ok,
            "B_lignes_discriminantes": len(discriminants),
            "ok": a_ok and b_ok}


def _build(board):
    state = ROOT / "logs" / "runners" / ("p447r1r1r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", board,
            "--state-file", str(state), "--p-units", P_UNITS, "--a-units", A_UNITS]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1200:]
    return json.loads(state.read_text())["runnerId"], None


def gisement(boards=None) -> dict:
    """L'intersection « tuile OCCUPEE et (en fog ou non marchable) », par board."""
    sid = _resolve_session()
    out, erreurs = [], []
    for b in (boards or BOARDS):
        rid, err = _build(b)
        if rid is None:
            erreurs.append({"board": b, "err": err})
            continue
        try:
            bg = _rq(sid, "boardGraph", {"runnerId": rid})
            ob = _rq(sid, "observeBattle", {"runnerId": rid})
            tiles = bg.get("tiles") or []
            occ = [t for t in tiles if t.get("occupantUnitId")]
            out.append({
                "board": b, "tuiles": len(tiles),
                "en_fog": sum(1 for t in tiles if t.get("isInFog")),
                "non_marchables": sum(1 for t in tiles if not t.get("walkable")),
                "occupees": len(occ),
                "OCCUPEES_ET_FOG": sum(1 for t in occ if t.get("isInFog")),
                "OCCUPEES_ET_NON_MARCHABLES": sum(1 for t in occ if not t.get("walkable")),
                # ce que le canal ne montre PAS : les unites d'une salle fermee ne sont pas encore
                # instanciees -- on l'IMPRIME au lieu de laisser le zero se lire comme une preuve.
                "unites_instanciees": (ob.get("counts") or {}).get("units"),
                "unites_demandees_au_build": len(P_UNITS.split(",")) + len(A_UNITS.split(",")),
            })
        finally:
            try:
                _rq(sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    contraste = any(o["en_fog"] > 0 for o in out)
    return {"boards": out, "erreurs": erreurs,
            "au_moins_un_board_a_du_fog": contraste,
            "intersection_totale": sum(o["OCCUPEES_ET_FOG"] + o["OCCUPEES_ET_NON_MARCHABLES"]
                                       for o in out),
            "regime_non_degenere": contraste}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="synthetique", choices=["synthetique", "gisement"])
    a = ap.parse_args()
    if a.step == "synthetique":
        print("synthetique :", json.dumps(synthetique(), indent=1)[:2500])
    if a.step == "gisement":
        print("gisement    :", json.dumps(gisement(), indent=1)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
