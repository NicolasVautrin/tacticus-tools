"""#287-r11-r1 -- CONFRONTATION LIVE des trois regles dynamiques de ciblage portees, contre l'oracle
NATIF.

    | id   | ability                 | porteur            | etage demande                        |
    |------|-------------------------|--------------------|--------------------------------------|
    | 1016 | SendInTheNextWave       | `astraYarrick`     | GetSurroundingTiles + GetUnitMaxRange |
    | 1180 | HeroicFusillade         | `genesKelermorph`  | GetMinDistance + IsInMovementRange   |
    | 1197 | ExcruciatingFrequencies | `emperNoiseMarine` | selecteur DSL (GetAttackTargets)     |

L'ORACLE est `abilityReason(casterId, abilityType, targetId)` = le masque `TargetingRule` rendu par
`TargetingQuery$$GetInvalidTargetReason` + `...GetInvalidCasterReason`. Contrat de fidelite, le meme
que `probe_287r11_regles_triggers_live` :

    natif == 0   =>  port == 0          STRICT -- c'est CE bras qui attrape le SUR-REFUS
    natif != 0   =>  port == natif      (regle PORTEE)
                 ou  port == 0          (regle NON PORTEE -> permissif, documente)
    jamais       :   port != 0 et port != natif

⚠ UN SOUS-REFUS NE SE DISCULPE PAS PAR LE DESARMEMENT. L'attribution par desarmement ne discrimine
que sur les SUR-refus : desarmer ne peut rendre le port que PLUS permissif, donc tout sous-refus
survit au temoin PAR CONSTRUCTION et serait compte « preexistant » -- un vert automatique. Les trois
familles sont donc comptees SEPAREMENT, et le SOUS-refus fait rougir sans passer par l'attribution.

⚠ LE DOMAINE DE CIBLES N'EST PAS LE MEME POUR LES TROIS. 1016 et 1180 ciblent des UNITES ennemies ;
**1197 cible une TUILE** (`TargetIsTile`, portee `RANGE_ADJACENT`) -- ses cibles sont donc les tuiles
ADJACENTES au caster, et l'oracle recoit un `targetId` d'entite-TUILE (meme voie que
`probe_249_tile_has_enemy_targeting`). Confondre les deux domaines rendrait « 0 cible » et la mesure
n'aurait pas lieu.

⚠ LA GEOMETRIE EST PLACEE, PAS SUBIE (`--place` / `--a-place`), et le BOARD est choisi POUR elle.
Le montage 1016 exige un disque de rayon `GetSpawnedUnitRange()` = 2 ENTIEREMENT sature autour de la
cible : sur un board ordinaire il faudrait 18 unites. `C4_05` porte un coin dont le disque r=2 ne
compte que **4** tuiles jouables (`(0,0)`, `(1,1)`, `(1,2)`, `(2,1)`) -- trois unites suffisent. Ce
board a ete trouve par balayage des 779 boards de `data/boards/`, pas suppose.

⚠ ET UN `--place` NON HONORE EST SILENCIEUX (#287-r13) : le probe imprime le SUBSTRAT EFFECTIVEMENT
MONTE, et la ventilation par cote -- un cote vide se voit.

Usage (session warmee ; le probe monte et DISPOSE ses propres runners, un a la fois) :
    python scripts/python/probe_287r11r1_regles_ciblage_live.py
    python scripts/python/probe_287r11r1_regles_ciblage_live.py --only 1180
ASCII only ; exit 0 = contrat respecte, bascules exercees, aucune violation imputable.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hexgeo                                                              # noqa: E402
import oracle_targeting as O                                               # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

ROOT = HERE.parents[1]
LOGS = ROOT / "logs"

WAVE = int(ActiveAbilityType.SendInTheNextWave)                # 1016
FUSILLADE = int(ActiveAbilityType.HeroicFusillade)             # 1180
FREQUENCIES = int(ActiveAbilityType.ExcruciatingFrequencies)   # 1197

# --------------------------------------------------------------------------------------------- #
# LES MONTAGES -- un par id, chacun avec sa geometrie PLACEE et son board CHOISI.
#
# `domaine` : `unites` (cibles = unites ennemies) ou `tuiles_adjacentes` (cibles = tuiles voisines
# du caster). C'est le masque qui le dicte, pas une preference : `1197` porte `TargetIsTile`.
# --------------------------------------------------------------------------------------------- #

MONTAGES = {
    # `C4_05` : 7x9, le coin (0,0) n'a que 4 tuiles jouables dans son disque r=2.
    #   Yarrick (1,1) + deux allies (1,2)/(2,1) + la cible (0,0) = les 4 tuiles occupees
    #   -> `IsEmptyOrSteppable` faux partout -> REFUS.
    #   La 2e cible (1,3) est a d=2 de Yarrick (donc DANS sa portee, `ExtraRange + 2`) et son
    #   disque r=2 compte 10 tuiles jouables -> il en reste de libres -> ACCEPTE.
    "1016": dict(
        at=WAVE, board="C4_05", seed=4242, caster="astraYarrick", domaine="unites",
        p_units="astraYarrick,ultraTitus,ultraTitus",
        a_units="necroWarden,necroDestroyer",
        place=["astraYarrick:1,1", "ultraTitus:1,2", "ultraTitus:2,1"],
        a_place=["necroWarden:0,0", "necroDestroyer:1,3"],
    ),
    # `C1_02` : 5x7. Kelermorph au coin haut (2,0), portee de charge `constants.range` = 2.
    #   (2,1) d=1            -> COURT-CIRCUIT `GetMinDistance < 2`      -> 0
    #   (2,2) d=2, ring1 a 1 -> chargeable                              -> 0
    #   (2,4) d=4, ring1 a 3 -> hors du stop-set de rayon 2             -> REFUS
    #   (1,5) d=5, ring1 a 4 -> idem                                    -> REFUS
    "1180": dict(
        at=FUSILLADE, board="C1_02", seed=4242, caster="genesKelermorph", domaine="unites",
        p_units="genesKelermorph,ultraTitus",
        a_units="necroWarden,necroWarden,necroWarden,necroDestroyer",
        place=["genesKelermorph:2,0", "ultraTitus:0,6"],
        a_place=["necroWarden:2,1", "necroWarden:2,2", "necroWarden:2,4",
                 "necroDestroyer:1,5"],
    ),
    # `C1_02`. Shiron en (1,3) : SIX tuiles adjacentes jouables, donc six cibles. Deux ennemis
    #   places sur des lignes DIFFERENTES -- les quatre autres aims ne touchent personne :
    #     aim (2,3) -> ligne [(2,3), (3,4), (4,4)]   : ennemi en (3,4)  -> ACCEPTE
    #     aim (1,4) -> ligne [(1,4), (1,5), (1,6)]   : ennemi en (1,5)  -> ACCEPTE
    #     aim (2,2) -> ligne [(2,2), (3,2), (4,1)]                      -> REFUS
    #     aim (1,2) -> ligne [(1,2), (1,1), (1,0)]                      -> REFUS
    #     aim (0,3) -> ligne [(0,3)]        (bord)                      -> REFUS
    #     aim (0,2) -> ligne [(0,2)]        (bord)                      -> REFUS
    "1197": dict(
        at=FREQUENCIES, board="C1_02", seed=4242, caster="emperNoiseMarine",
        domaine="tuiles_adjacentes",
        p_units="emperNoiseMarine,ultraTitus",
        a_units="necroWarden,necroWarden",
        place=["emperNoiseMarine:1,3", "ultraTitus:4,0"],
        a_place=["necroWarden:3,4", "necroWarden:1,5"],
    ),

    # ------------------------------------------------------------------------------------------ #
    # GENERALISATION -- deux montages CRAFTES pour SEPARER le port porte d'un port plausible mais
    # FAUX. Un accord obtenu la ou les deux modeles coincident ne prouve rien ; ces deux-la sont
    # choisis parce que le modele naif y donne l'AUTRE reponse.
    # ------------------------------------------------------------------------------------------ #

    # 1180 : PATHFINDING vs DISTANCE HEX. Kelermorph en (2,0) ; ses trois voisins « vers le bas »
    # (2,1) / (1,1) / (3,1) portent un ENNEMI, donc `WalkPathfinder$$UnitIsBlockedByEnemyUnit`
    # ferme la descente ; il ne lui reste que (1,0) et (3,0), d'ou il n'atteint AUCUN voisin de la
    # cible (2,3) en `range` = 2 pas. Or `(2,2)` -- un ring-1 de la cible -- est a DISTANCE HEX 2 du
    # caster : un port qui aurait collapse `IsInMovementRange` en `distance <= range` ACCEPTERAIT.
    # Les trois bloqueurs sont eux-memes des cibles a d = 1, donc le COURT-CIRCUIT est exerce dans le
    # meme montage (les deux verdicts, sans second build).
    "1180-bloque": dict(
        at=FUSILLADE, board="C1_02", seed=4242, caster="genesKelermorph", domaine="unites",
        p_units="genesKelermorph,ultraTitus",
        a_units="necroWarden,necroWarden,necroWarden,necroDestroyer",
        place=["genesKelermorph:2,0", "ultraTitus:4,6"],
        a_place=["necroWarden:2,1", "necroWarden:1,1", "necroWarden:3,1",
                 "necroDestroyer:2,3"],
    ),
    # 1016 : LE SEUIL `Count < 1`, PRIS AU BORD. MEME board, MEME cible en (0,0), MEME caster --
    # UNE SEULE unite deplacee : l'allie de `(2,1)` part au loin. Le disque r=2 de la cible passe
    # donc de 0 a EXACTEMENT UNE tuile libre marchable, et le verdict doit basculer de 2 a 0. C'est
    # ce qui etablit que le decideur est le COMPTE du disque, et non la distance ou la position :
    # aucune des deux ne change entre `1016` et ce montage.
    "1016-une-seule": dict(
        at=WAVE, board="C4_05", seed=4242, caster="astraYarrick", domaine="unites",
        p_units="astraYarrick,ultraTitus,ultraTitus",
        a_units="necroWarden,necroDestroyer",
        place=["astraYarrick:1,1", "ultraTitus:1,2", "ultraTitus:5,5"],
        a_place=["necroWarden:0,0", "necroDestroyer:1,3"],
    ),
    # CONTRE-EPREUVE de `1180-bloque` : MEME board, MEME caster, MEME cible en (2,3), les trois
    # bloqueurs DEPLACES au loin. Sans elle, le refus de `1180-bloque` pourrait venir de la seule
    # distance (d = 3) et l'attribution au PATHFINDING serait une supposition ; avec elle, la seule
    # variable qui change entre les deux montages est la position des bloqueurs.
    "1180-libre": dict(
        at=FUSILLADE, board="C1_02", seed=4242, caster="genesKelermorph", domaine="unites",
        p_units="genesKelermorph,ultraTitus",
        a_units="necroWarden,necroWarden,necroWarden,necroDestroyer",
        place=["genesKelermorph:2,0", "ultraTitus:4,6"],
        a_place=["necroWarden:0,5", "necroWarden:1,6", "necroWarden:3,6",
                 "necroDestroyer:2,3"],
    ),
    # 1197 : LIGNE vs VOISINAGE. L'ennemi de (0,4) est ADJACENT a l'aim (0,3) mais n'est PAS sur sa
    # ligne (`TilesBehindInLine((1,3) -> (0,3))` s'arrete au bord : `[(0,3)]`). Un port qui aurait
    # lu `GetAttackTargets` comme « les ennemis autour de la tuile visee » ACCEPTERAIT. Le second
    # ennemi, en (1,5), tient la ligne de l'aim (1,4) -> le montage reste non degenere.
    "1197-hors-ligne": dict(
        at=FREQUENCIES, board="C1_02", seed=4242, caster="emperNoiseMarine",
        domaine="tuiles_adjacentes",
        p_units="emperNoiseMarine,ultraTitus",
        a_units="necroWarden,necroWarden",
        place=["emperNoiseMarine:1,3", "ultraTitus:4,0"],
        a_place=["necroWarden:0,4", "necroWarden:1,5"],
    ),
}


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> str:
    """Rend la sortie du build. ⚠ ELLE DOIT ETRE LUE : un `--place` hors board (ou sur une tuile
    occupee / non marchable) est REFUSE ligne par ligne, et le build continue avec les autres."""
    r = subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return (r.stdout or b"").decode("utf-8", "replace")


def _pos(u):
    p = u.get("pos") or {}
    return None if p.get("col") is None else (int(p["col"]), int(p["row"]))


def _contexte(rid: int):
    dec = _rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    ob = _rpc("observeBattle", {"runnerId": rid}, 40000)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60000)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60000)
    board = Board(bg["tiles"], adjacency="native_sym")
    units = dec.get("units") or []
    by_vis = {}
    for u in units:
        by_vis.setdefault(u.get("visualId"), u)
    return dec, ob, snap, board, [u for u in units if u.get("alive")], by_vis


def _cibles(m: dict, caster, alive: list, board) -> list:
    """Le DOMAINE de cibles, dicte par le masque de l'ability.

    `unites` : les unites ENNEMIES vivantes (`TargetIsEnemy`).
    `tuiles_adjacentes` : les entites-TUILE voisines du caster (`TargetIsTile` + `RANGE_ADJACENT`).
    Rend [(target_id, libelle)]."""
    if m["domaine"] == "unites":
        mine = caster.get("team")
        return [(int(u["id"]), "%s %s" % (u.get("visualId"), _pos(u)))
                for u in alive
                if u.get("id") != caster.get("id") and u.get("team") != mine]
    cp = _pos(caster)
    if cp is None or board is None:
        return []
    out = []
    for q in hexgeo.neighbors(cp[0], cp[1]):
        tid = board.id_at(q[0], q[1])
        if tid is not None:
            out.append((int(tid), "tuile %s" % (q,)))
    return sorted(out)


def _indice(m: dict, caster, tid: int, alive: list, board) -> str:
    """INDICE geometrique imprime a cote du verdict -- PAS le verdict attendu. Le derive du port
    serait circulaire ; le derive d'un raisonnement geometrique serait un 2e port. C'est le
    critere de NON-DEGENERESCENCE (verdicts NATIFS ventiles) qui tranche, pas cette colonne."""
    at = int(m["at"])
    cp = _pos(caster)
    if board is None or cp is None:
        return "-"
    if at == FREQUENCIES:
        q = board.coord(int(tid))
        return "aim %s d=%d" % (q, hexgeo.distance(cp, q))
    cible = next((u for u in alive if int(u.get("id") or -1) == int(tid)), None)
    tp = _pos(cible) if cible else None
    if tp is None:
        return "-"
    if at == FUSILLADE:
        ring = [q for q in hexgeo.disk(tp[0], tp[1], 1)
                if q != tp and board.id_at(q[0], q[1]) is not None]
        return "d=%d ring1min=%s" % (hexgeo.distance(cp, tp),
                                     min([hexgeo.distance(cp, q) for q in ring] or [-1]))
    # 1016 : combien de tuiles du disque r=2 sont MARCHABLES et libres d'occupant. Le filtre
    # `walkable` est indispensable a l'INDICE : `boardGraph` publie aussi les tuiles injouables
    # (`ForceUnplayable`), et sans lui le coin sature de `C4_05` affichait « 4 libres » pour un
    # refus -- un indice qui contredit le verdict fait douter du verdict, pas de l'indice.
    occ = {_pos(u) for u in alive}
    libres = [q for q in hexgeo.disk(tp[0], tp[1], 2)
              if board.id_at(q[0], q[1]) is not None
              and board.walkable(board.id_at(q[0], q[1])) and q not in occ]
    return "d=%d libresR2=%d" % (hexgeo.distance(cp, tp), len(libres))


def mesurer(rid: int, m: dict, ctx) -> dict:
    dec, ob, snap, board, alive, by_vis = ctx
    at = int(m["at"])
    state = load_state(dec, ob, snap, board=board)
    out = {"exact": [], "sous_refus": [], "viol": [], "hors_regle": [], "accord_zero": [],
           "cibles": 0, "natif": {}, "absent": None, "court_circuite": None}
    out["substrat"] = ["%s t%d %s team%s" % (u.get("visualId"), u["id"], _pos(u), u.get("team"))
                       for u in alive]
    caster = by_vis.get(m["caster"])
    if caster is None:
        out["absent"] = m["caster"]
        return out
    r0 = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                "abilityType": at}, 60000) or {}
    if O.oracle_court_circuite(r0):
        out["court_circuite"] = O.cause_du_court_circuit(r0)
        return out
    ab = P._porteur(at)
    for tid, libelle in _cibles(m, caster, alive, board):
        r = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                   "abilityType": at, "targetId": int(tid)}, 60000) or {}
        tr = r.get("targetReason") or {}
        nat = int(tr.get("hex") or "0x0", 16)
        port = int(is_invalid_target(state, int(caster["id"]), int(tid), ab) or 0)
        out["natif"][hex(nat)] = out["natif"].get(hex(nat), 0) + 1
        out["cibles"] += 1
        row = (at, int(tid), "%s %s" % (libelle, _indice(m, caster, int(tid), alive, board)),
               hex(nat), ",".join(tr.get("reasons") or []) or "-", hex(port))
        if nat == 0 and port == 0:
            out["accord_zero"].append(row)
        elif nat == 0 and port != 0:
            out["viol"].append(row)                      # SUR-REFUS
        elif port == nat:
            (out["exact"] if (nat & int(TR.TargetMatchesDynamicRule))
             else out["hors_regle"]).append(row)
        elif port == 0:
            out["sous_refus"].append(row + (_diagnostic(state, caster, int(tid), at),))
        else:
            out["viol"].append(row)
    return out


def _diagnostic(state, caster, tid: int, at: int) -> str:
    """DECOMPOSITION PAR ETAGE d'un desaccord : ce que chaque etage du corps natif rend cote port,
    pas seulement le verdict final. Jamais fitter un scalaire."""
    try:
        if at == WAVE:
            from engine.runner.abilities.astramilitarum import (
                send_in_the_next_wave_spawned_unit_range)
            from engine.runner.abilities.targeting import tile_is_empty_or_steppable
            import engine.battle_query as bq
            from engine.runner.components import PositionComponent
            te = state.get_entity(int(tid))
            pc = te.get_component(PositionComponent) if te is not None else None
            b = state.board
            if pc is None or b is None:
                return "substrat absent"
            r = send_in_the_next_wave_spawned_unit_range()
            tuiles = bq.get_surrounding_tiles(
                (pc.col, pc.row), radius=r, include_center=True, check_walkable=True,
                only_empty_or_steppable=True,
                empty_or_steppable_at=lambda p: tile_is_empty_or_steppable(state, p),
                walkable_at=lambda p: b.walkable(b.id_at(p[0], p[1])),
                elevation_at=lambda p: b.elevation(b.id_at(p[0], p[1])),
                tile_exists=lambda p: b.id_at(p[0], p[1]) is not None)
            return "range=%d tuilesLibres=%d %s" % (r, len(tuiles), tuiles[:6])
        if at == FUSILLADE:
            from engine.runner.components import get_unit_feet
            from engine.services.movement_query import get_min_distance
            d = get_min_distance(get_unit_feet(state, int(tid)),
                                 get_unit_feet(state, int(caster["id"])))
            return "GetMinDistance=%d (court-circuit si < 2)" % d
        if at == FREQUENCIES:
            from engine.runner.abilities.targeting import (
                _dynamic_rule_excruciating_frequencies as f)
            return "regle=%s" % hex(int(f(state, int(caster["id"]), int(tid)) or 0))
    except Exception as exc:                                     # pragma: no cover - diagnostic
        return "diagnostic KO: %r" % (exc,)
    return "-"


def jouer(nom: str, keep: bool) -> tuple:
    m = MONTAGES[nom]
    at = int(m["at"])
    tag = uuid.uuid4().hex[:8]
    state_file = LOGS / f"rs_287r11r1_{nom}_{tag}.json"
    args = ["build", "--seed", str(m["seed"]), "--board", m["board"], "--rank", "17",
            "--p-units", m["p_units"], "--a-units", m["a_units"], "--no-ai",
            "--state-file", str(state_file)]
    for p in m.get("place") or []:
        args += ["--place", p]
    for p in m.get("a_place") or []:
        args += ["--a-place", p]
    sortie = _run(args)
    refus = [l.strip() for l in sortie.splitlines() if "placement REFUSE" in l]
    if not state_file.exists():
        return None, "PAS MESURE : build KO (state-file absent)\n      " + "\n      ".join(
            l.strip() for l in sortie.splitlines() if l.startswith("[error]")), None, None
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    debloc = "non necessaire"
    try:
        ctx = _contexte(rid)
        caster = ctx[5].get(m["caster"])
        if caster is not None and (O.cooldown_initial(at) or 0) >= 1:
            # `jouer_adverse=False` : le tour adverse DEPLACERAIT les unites et detruirait la
            # geometrie PLACEE.
            debloc = O.debloquer_oracle(_rpc, rid, int(caster["id"]), at,
                                        jouer_adverse=False) or "OK"
            ctx = _contexte(rid)
        res = mesurer(rid, m, ctx)
        with P.desarme(at):
            temoin = mesurer(rid, m, ctx)
    finally:
        if not keep:
            _run(["dispose", "--state-file", str(state_file)])
    if refus:
        res["refus_placement"] = refus
    return rid, debloc, res, temoin


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r11-r1 : confrontation live")
    ap.add_argument("--only", type=int, default=None, help="ne jouer qu'un id")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    noms = [n for n, m in MONTAGES.items() if a.only is None or int(m["at"]) == int(a.only)]
    rc = 0
    natif_par_id: dict = {}
    for nomm in noms:
        m = MONTAGES[nomm]
        at = int(m["at"])
        rid, debloc, res, temoin = jouer(nomm, a.keep)
        print("")
        print("[287r11r1-live] %s -- %d %s -- porteur %s -- board %s -- runner %s"
              % (nomm, at, ActiveAbilityType(at).name, m["caster"], m["board"], rid))
        if res is None:
            print("   %s" % debloc)
            rc = 2
            continue
        print("   deblocage du cooldown initial (#287-r6) : %s" % debloc)
        for l in (res.get("refus_placement") or []):
            print("   !! PLACEMENT REFUSE (la geometrie voulue n'est PAS celle mesuree) : %s" % l)
            rc = max(rc, 1)
        if res.get("absent"):
            print("   PAS MESURE : porteur `%s` ABSENT du montage" % res["absent"])
            rc = 2
            continue
        if res.get("court_circuite"):
            print("   PAS MESURE : oracle COURT-CIRCUITE (%s)" % res["court_circuite"])
            rc = 2
            continue
        print("   substrat monte : %s" % " | ".join(res.get("substrat") or ["<vide>"]))
        print("   domaine de cibles : %s -- %d confrontee(s)" % (m["domaine"], res["cibles"]))
        if res["cibles"] == 0:
            print("   !! AUCUNE CIBLE : la mesure n'a pas eu lieu")
            rc = 2
        print("   verdicts NATIFS observes : %s" % (res["natif"],))
        for k, v in res["natif"].items():
            natif_par_id.setdefault(at, {})[k] = natif_par_id.get(at, {}).get(k, 0) + v
        print("   refus reproduits A L'IDENTIQUE : %d" % len(res["exact"]))
        print("   accords sur 0 (cible legale des deux cotes) : %d" % len(res["accord_zero"]))
        print("   refus HORS regle dynamique (autre bit du masque) : %d" % len(res["hors_regle"]))
        for r in res["exact"] + res["accord_zero"] + res["hors_regle"]:
            print("      OK   t%-5d %-38s natif=%-8s [%s] port=%s"
                  % (r[1], r[2], r[3], r[4], r[5]))
        cle = lambda r: (r[0], r[1])                                        # noqa: E731
        preexistantes = {cle(r) for r in temoin["viol"]}
        imputables = [r for r in res["viol"] if cle(r) not in preexistantes]
        survivantes = [r for r in res["viol"] if cle(r) in preexistantes]
        print("   SUR-refus imputables a cette tranche : %d" % len(imputables))
        for r in imputables:
            print("      SUR  t%-5d %-38s natif=%-8s [%s] port=%s"
                  % (r[1], r[2], r[3], r[4], r[5]))
        if survivantes:
            print("   SUR-refus PREEXISTANTS (survivent au desarmement) : %d" % len(survivantes))
        print("   SOUS-refus (natif refuse, port accepte) : %d" % len(res["sous_refus"]))
        for r in res["sous_refus"]:
            print("      SOUS t%-5d %-38s natif=%-8s [%s] port=%s | %s"
                  % (r[1], r[2], r[3], r[4], r[5], r[6]))
        print("   TEMOIN desarme : %d refus encore reproduits (attendu 0)" % len(temoin["exact"]))
        if imputables or res["sous_refus"]:
            rc = 1
        if temoin["exact"]:
            print("   !! le TEMOIN reproduit encore des refus : le verdict ne vient pas de la regle")
            rc = 1
    print("")
    print("[287r11r1-live] NON-DEGENERESCENCE, par id :")
    for at, d in sorted(natif_par_id.items()):
        zero = sum(v for k, v in d.items() if int(k, 16) == 0)
        refus = sum(v for k, v in d.items() if int(k, 16) != 0)
        ok = zero > 0 and refus > 0
        print("   %-6d %-24s natif=%s  -> %s" % (
            at, ActiveAbilityType(at).name, d,
            "les DEUX verdicts sont exerces" if ok
            else "!! REGIME DEGENERE : un seul verdict, l'accord ne prouve rien"))
        if not ok:
            rc = max(rc, 1)
    if a.only is None and set(natif_par_id) != {WAVE, FUSILLADE, FREQUENCIES}:
        print("   !! un id n'a produit AUCUNE mesure : %s" % (sorted(natif_par_id),))
        rc = max(rc, 2)
    print("")
    print("[287r11r1-live] VERDICT : %s" % ("OK" if rc == 0 else "ROUGE (rc=%d)" % rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
