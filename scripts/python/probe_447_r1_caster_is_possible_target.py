"""#447-r1 -- `CasterIsPossibleTarget` (bit 15) : ou le natif le lit, ou le port le lit, et si
l'effet est CONFRONTE.

LA QUESTION BINAIRE. Le bit 15 est arme dans N masques. Le port le lit-il LA OU LE NATIF LE LIT, et
son effet est-il confronte -- ou n'est-il << couvert >> que parce qu'un inventaire l'enumere ?

TROIS ETATS a distinguer, et c'est tout le sujet :
    (1) PORTE ET CONFRONTE   -- le port le lit, et une mesure live montre qu'il change une decision ;
    (2) PORTE, JAMAIS EPROUVE -- le code le lit, aucune garde ne le fait mordre ;
    (3) ENUMERE SEULEMENT     -- il figure dans un inventaire, aucun chemin ne le consomme.

CE QUE LA RE ETABLIT (relecture a l'octet sur `rnca9r7q6c`) -- QUATRE lecteurs natifs :

  1. `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions`
         if ((rules >> 0xf & 1) != 0)  <ensemble>.<IOrderedSet slot 0>(bVar12 ? casterTiles : caster);
     Le caster (ou ses tuiles, domaine TUILE) est AJOUTE aux cibles POSSIBLES, en AMONT des trois
     `RemoveAll` et de la boucle de filtrage. **C'est le lecteur qui mord.**
  2. `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` -- branche `(int)range == 0`
     (`bit15 ? OrderedSet(casterTiles) : VIDE`) et le parametre `includeCenter` du slot 0x67.
  3. `IdunBattle.Core.Services.TargetingOptions$$get_CanTargetCaster` -- DECLARATIF, deux appelants,
     tous deux UI.
  4. `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` -- branche MORTE sur le
     chemin du CAST : ses DEUX seuls appelants de code n'y branchent que sous self-cast POSE, ce que
     la branche contredit (`options+0x00 == 0`).

⚠ LA PREMISSE DE #447-r1 EST RE-CADREE. Elle disait << elle vit par `TargetingQuery$$GetValidTargets`,
qui RE-APPLIQUE la cascade CIBLE complete au caster >>. `GetValidTargets` NE TESTE JAMAIS le bit 15
(relu en entier : bit 7 `AddCaster`, `isSelfCasting || bit 11`, bit 22, bit 3). Le bit vit un cran
plus haut.

⚠ LE PIEGE DE MESURE (regime DEGENERE). L'etage d'ajout de `GetValidTargets` ajoute le caster des
que `targets.Count > 0` pour toute ability SELF-CASTEE -- **quel que soit le bit 15**. Le seul regime
ou le bit 15 DECIDE seul est donc << aucune autre cible valide >>. Le montage live isole le caster.

ASCII only.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import uuid
from pathlib import Path

import gameconfig as GC                                                     # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                 # noqa: E402
from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED,  # noqa: E402
                                               targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR      # noqa: E402
from engine.services import ability_range as AR                            # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
SEED = "777"

#: LA PAIRE DISCRIMINANTE, et elle n'est pas choisie a l'oeil : les deux masques ont le MEME
#: `TargetingRange` (`RANGE_FROM_CONFIG`, reach 2 sur leur porteur), le MEME `isSelfCasting`, le MEME
#: `TargetIsFriendly` -- **seul le bit 15 les separe** (`0x8400` contre `0x400`). L'etape `paire` du
#: mode offline RE-DERIVE cette propriete et refuse de continuer si elle cesse d'etre vraie.
PAIR_WITH_BIT = 1061       # UnbreakableDuty  -- rules 0x8400
PAIR_WITHOUT = 1049        # CrusadeOfWrath   -- rules 0x400
PAIR_CARRIER_WITH = "templAncient"
PAIR_CARRIER_WITHOUT = "templHelbrecht"
PAIR_BOARD = "MC1_67"

#: Les deux bits qui AJOUTENT le caster dans `GetPossibleTargetsForOptions`.
CASTER_ADDED = int(TR.CasterIsPossibleTarget) | int(TR.TargetIsCasterOrEnemy)

#: L'ECART entre les deux casters, en distance hex. Il doit DEPASSER STRICTEMENT la portee des deux
#: abilities (reach 2, re-derivee par l'etape `paire`) : c'est ce qui vide `targets` et rend le
#: bit 15 seul decideur. 4 laisse une marge d'une tuile de chaque cote.
ECART_ISOLEMENT = 4

#: Les deux tuiles du montage ISOLE sur `PAIR_BOARD`. Ce sont des constantes, mais leur PROPRIETE
#: est re-derivee (`hexgeo.distance >= ECART_ISOLEMENT`) et `rl_duel build --place` refuse un
#: placement invalide -- il imprime `placements verifies OK (2)`.
PLACE_WITH = (0, 0)
PLACE_WITHOUT = (5, 0)


# ------------------------------------------------------------------------------------------------
# ETAPE 0 -- QUI LIT LE BIT DANS LE PORT (derivation AST, jamais une liste saisie)
# ------------------------------------------------------------------------------------------------

#: Les deux jetons par lesquels le port peut lire le bit 15 : le membre d'enum et le getter porte.
JETONS = ("CasterIsPossibleTarget", "can_target_caster")


def _enclosing(tree, lineno):
    """Le nom de la fonction (ou de la classe) qui contient cette ligne -- la plus IMBRIQUEE."""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            if node.lineno <= lineno <= end:
                if best is None or node.lineno > best.lineno:
                    best = node
    return None if best is None else best.name


def _role_occurrence(chaine) -> str:
    """ECRITURE ou LECTURE, decide par la CHAINE DES PARENTS de l'occurrence.

    C'EST LA DISTINCTION QUI TRANCHE LES TROIS ETATS, et un balayage qui l'ignore rend un verdict
    FAUX : un `TARGETING_OPTIONS = TargetingOptions(rules=... | TR.CasterIsPossibleTarget, ...)`
    **DECLARE** le bit -- c'est un masque arme, l'etat (3) << enumere seulement >>. Il ne le LIT pas.
    Seul un test (`options.has(TR.X)`, `rules & int(TR.X)`, `_bit(rules, TR.X)`) est un LECTEUR, et
    lui seul peut etre dans l'etat (1) ou (2).

    ECRITURE = l'occurrence alimente une construction de masque : argument nomme `rules=`, cible
    d'une assignation `TARGETING_OPTIONS`/`rules`, ou membre de la definition de l'enum."""
    for p in chaine:
        if isinstance(p, ast.keyword) and p.arg in ("rules", "rules_override"):
            return "ECRITURE"
        if isinstance(p, ast.Assign):
            for t in p.targets:
                nom = getattr(t, "id", None) or getattr(t, "attr", None)
                if nom in ("TARGETING_OPTIONS", "rules", "CASTER_ADDED"):
                    return "ECRITURE"
        if isinstance(p, ast.ClassDef) and p.name == "TargetingRule":
            return "ECRITURE"           # la DEFINITION du membre d'enum
    return "LECTURE"


def lecteurs_du_port(racine: Path) -> dict:
    """Les occurrences EXECUTABLES du bit 15 dans `engine/**`, derivees de l'AST et VENTILEES en
    ECRITURE (le masque le declare) / LECTURE (un chemin le consomme).

    Un COMMENTAIRE ou une docstring qui cite le bit n'apparait pas : le balayage ne regarde que les
    `Attribute`/`Name` de l'arbre, jamais le texte."""
    out: dict = {}
    for f in sorted(racine.rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        parents: dict = {}
        for p in ast.walk(tree):
            for c in ast.iter_child_nodes(p):
                parents[id(c)] = p
        for node in ast.walk(tree):
            nom = None
            if isinstance(node, ast.Attribute) and node.attr in JETONS:
                nom = node.attr
            elif isinstance(node, ast.Name) and node.id in JETONS:
                nom = node.id
            if nom is None:
                continue
            chaine, cur = [], node
            while id(cur) in parents:
                cur = parents[id(cur)]
                chaine.append(cur)
            fn = _enclosing(tree, node.lineno)
            cle = "%s::%s" % (f.relative_to(racine.parent).as_posix(), fn or "<module>")
            out.setdefault(cle, set()).add("%s/%s" % (_role_occurrence(chaine), nom))
    return {k: sorted(v) for k, v in sorted(out.items())}


def fonctions_lectrices(lect: dict) -> list:
    """Les fonctions du port qui LISENT le bit -- DERIVEES du balayage, jamais saisies."""
    return sorted({cle.rsplit("::", 1)[-1] for cle, roles in lect.items()
                   if any(r.startswith("LECTURE/") for r in roles)})


def consommateurs(racine: Path, lectrices) -> dict:
    """Les fonctions du port qui APPELLENT une lectrice -- la cloture d'appel a UN niveau.

    Elle compte : une garde qui exerce un consommateur exerce le lecteur qu'il appelle. Sans elle,
    `caster_is_valid_target` (qui DELEGUE a `caster_is_possible_target`) serait compte << absent >>,
    et son verdict serait faux."""
    lectrices = set(lectrices)
    out: dict = {}
    for f in sorted(racine.rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            fn = getattr(getattr(node, "func", None), "id", None) or \
                 getattr(getattr(node, "func", None), "attr", None)
            if isinstance(node, ast.Call) and fn in lectrices:
                appelant = _enclosing(tree, node.lineno)
                if appelant and appelant not in lectrices:
                    out.setdefault(appelant, set()).add(fn)
    return {k: sorted(v) for k, v in sorted(out.items())}


def gardes_qui_mordent(racine_tests: Path, cibles) -> dict:
    """Pour chaque fonction lectrice, les fichiers de TEST qui la nomment, ventiles LIVE / OFFLINE.

    C'EST LA MESURE QUI SEPARE (1) DE (2). Un lecteur nomme par une garde LIVE est CONFRONTE au
    natif ; nomme seulement par une garde offline, il est PORTE MAIS JAMAIS EPROUVE contre le jeu ;
    nomme par aucune, il n'est pas eprouve du tout. Derive de l'AST, jamais du texte."""
    cibles = set(cibles)
    out: dict = {c: {"live": [], "offline": []} for c in cibles}
    for f in sorted(racine_tests.rglob("test_*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        vus = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in cibles:
                vus.add(node.attr)
            elif isinstance(node, ast.Name) and node.id in cibles:
                vus.add(node.id)
        for c in vus:
            out[c]["live" if "_live" in f.name else "offline"].append(f.name)
    return out


def verdict_par_lecteur(lect: dict, cons: dict, gard: dict) -> list:
    """Les TROIS ETATS, par fonction lectrice -- derives des trois balayages ci-dessus.

    Une garde qui nomme un CONSOMMATEUR compte pour le lecteur qu'il appelle : c'est la difference
    entre << ce lecteur n'est pas teste >> et << il l'est, par son appelant >>."""
    lignes = []
    for fn in fonctions_lectrices(lect):
        via = [c for c, appeles in cons.items() if fn in appeles]
        live = list((gard.get(fn) or {}).get("live") or [])
        off = list((gard.get(fn) or {}).get("offline") or [])
        for c in via:
            live += list((gard.get(c) or {}).get("live") or [])
            off += list((gard.get(c) or {}).get("offline") or [])
        if live:
            etat, ou = "(1) PORTE ET CONFRONTE", ",".join(sorted(set(live)))
        elif off:
            etat, ou = "(2) PORTE, garde OFFLINE seule", ",".join(sorted(set(off)))
        else:
            etat, ou = "(2) PORTE, JAMAIS EPROUVE", "-"
        lignes.append((fn, etat, ou, ",".join(sorted(via)) or "-"))
    return lignes


# ------------------------------------------------------------------------------------------------
# ETAPE 1 -- LE GISEMENT
# ------------------------------------------------------------------------------------------------

def _kinds() -> dict:
    idx = GC.all_unit_ids()
    out = {}
    for kind in ("lineup", "npc", "summons"):
        for u in (idx.get(kind) or []):
            out[u] = kind
    return out


def _pool() -> set:
    """Le pool spawnable au rank courant (`rl_duel build --list-pool`). Vide = NON MESURE, et le
    probe le DIT plutot que de rendre un ensemble vide qui se lirait << aucun porteur >>."""
    kinds = _kinds()
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool"], cwd=str(PYDIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    pool = set()
    for line in (p.stdout or "").splitlines():
        for tok in line.replace(",", " ").split():
            t = tok.strip("'\"[]")
            if t in kinds:
                pool.add(t)
    return pool


def _abilities_lues() -> list:
    ids = {int(a) for a in ABILITY_CLASSES
           if getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None}
    ids |= {int(a) for a in TARGETING_OPTIONS_UNPORTED}
    return sorted(ids)


def porteurs_par_ability() -> dict:
    """Pour chaque `visualId`, la liste de ses `ActiveAbilityType` -- index inverse."""
    out: dict = {}
    for vid in sorted(_kinds()):
        try:
            ab = GC.unit_abilities(vid) or {}
        except Exception:                                                   # pragma: no cover
            continue
        for entries in ab.values():
            for e in (entries or []):
                aid = e.get("id")
                if aid is not None:
                    out.setdefault(int(aid), []).append(vid)
    return out


def gisement() -> dict:
    kinds, pool, inv = _kinds(), _pool(), porteurs_par_ability()
    lignes = []
    for aid in _abilities_lues():
        o = targeting_options_for(aid)
        r = int(getattr(o, "rules", 0) or 0)
        if not (r & int(TR.CasterIsPossibleTarget)):
            continue
        vids = inv.get(aid) or []
        lignes.append({
            "ability": aid, "rules": hex(r),
            "self_cast": bool(getattr(o, "self_cast", False)),
            "registre": aid in ABILITY_CLASSES,
            "porteurs": {k: [v for v in vids if kinds.get(v) == k]
                         for k in ("lineup", "npc", "summons")},
            "au_pool": sorted(v for v in vids if v in pool),
        })
    return {"abilities_a_masque_lu": len(_abilities_lues()),
            "porteurs_du_bit_15": len(lignes),
            "pool_mesure": len(pool) or None,
            "lignes": lignes}


# ------------------------------------------------------------------------------------------------
# ETAPE 2 -- LA PAIRE, RE-DERIVEE (offline)
# ------------------------------------------------------------------------------------------------

def paire() -> dict:
    """La propriete qui fait de (1061, 1049) un discriminant, RE-DERIVEE et non affirmee : meme
    portee, meme `isSelfCasting`, meme `TargetIsFriendly`, et le bit 15 pour SEULE difference."""
    a, b = targeting_options_for(PAIR_WITH_BIT), targeting_options_for(PAIR_WITHOUT)
    ra, rb = int(getattr(a, "rules", 0) or 0), int(getattr(b, "rules", 0) or 0)
    reach_a = AR.tiles_in_range_reach(PAIR_WITH_BIT, PAIR_CARRIER_WITH)
    reach_b = AR.tiles_in_range_reach(PAIR_WITHOUT, PAIR_CARRIER_WITHOUT)
    diff = ra ^ rb
    ok = (diff == int(TR.CasterIsPossibleTarget)
          and bool(getattr(a, "self_cast", False)) == bool(getattr(b, "self_cast", False))
          and reach_a == reach_b and reach_a is not None)
    return {"avec_bit": {"ability": PAIR_WITH_BIT, "rules": hex(ra), "reach": reach_a,
                         "self_cast": bool(getattr(a, "self_cast", False))},
            "sans_bit": {"ability": PAIR_WITHOUT, "rules": hex(rb), "reach": reach_b,
                         "self_cast": bool(getattr(b, "self_cast", False))},
            "xor": hex(diff), "discriminante": ok,
            "zone_d0_avec": AR.tiles_in_range_zone_contains(PAIR_WITH_BIT, PAIR_CARRIER_WITH, 0),
            "zone_d0_sans": AR.tiles_in_range_zone_contains(PAIR_WITHOUT, PAIR_CARRIER_WITHOUT, 0)}


# ------------------------------------------------------------------------------------------------
# LE VOLET LIVE -- oracle `abilityTargets.fromHere`
#
# `IdunBattle.Core.Services.AttackQuery$$GetValidTargets(unit, UnitPosition{GetTiles(unit)},
# abilityType)` -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetValidTargets` -> la surcharge
# 6 arguments de `TargetingQuery$$GetValidTargets` avec `skipAddCasterChecks = false` (lu au
# call-site : l'octet bas du 5e argument est ecrit a 0). Son SEUL gate amont est
# `AttackQuery$$IsAlreadyUsedThisTurn` -- pas de `get_CanCurrentlyBeUsed`, donc le cooldown ne
# masque pas la reponse (c'est le piege nomme par #447-r2).
# ------------------------------------------------------------------------------------------------

def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc
    return _resolve_session, _rpc


def _r(sid, m, b, t=90):
    _resolve_session, _rpc = _rpc_mod()
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(board, p_units, a_units, place=None, a_place=None):
    state = ROOT / "logs" / "runners" / ("p447r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    for pl in (place or []):
        argv += ["--place", pl]
    for pl in (a_place or []):
        argv += ["--a-place", pl]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1800:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                                        # pragma: no cover
        pass


def from_here_ids(sid, rid, unit_id, ability_id) -> dict:
    """`abilityTargets` restreint a (unite, ability) -- les ids d'unite de `fromHere` et `targets`.

    Rend AUSSI `err`/`present` : une ability absente de la reponse est un MONTAGE rate, pas un
    << zero cible >>. Ne jamais confondre les deux."""
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": int(unit_id),
                                    "abilityType": int(ability_id)}, 120)
    row = next((u for u in (at.get("units") or []) if int(u.get("unitId", -1)) == int(unit_id)),
               None)
    if row is None:
        return {"present": False, "err": "unite absente de abilityTargets"}
    ab = next((a for a in (row.get("abilities") or [])
               if int(a.get("abilityId", -1)) == int(ability_id)), None)
    if ab is None:
        return {"present": False,
                "err": "ability %d absente (rendues: %s)"
                       % (ability_id, [a.get("abilityId") for a in (row.get("abilities") or [])])}
    def ids(lst):
        return sorted(int(t["targetId"]) for t in (lst or [])
                      if t.get("kind") == "unit" and t.get("targetId") is not None)
    return {"present": True, "err": ab.get("err"),
            "fromHere": ids(ab.get("fromHere")), "targets": ids(ab.get("targets")),
            "fromHereTiles": len([t for t in (ab.get("fromHere") or [])
                                  if t.get("kind") == "tile"]),
            "usable": ab.get("usable"), "cooldown": ab.get("cooldown")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="offline",
                    choices=("offline", "lecteurs", "gisement", "paire", "live"))
    ap.add_argument("--board", default=PAIR_BOARD)
    args = ap.parse_args(argv)

    if args.step in ("offline", "lecteurs"):
        lect = lecteurs_du_port(PYDIR / "engine")
        lectrices = fonctions_lectrices(lect)
        cons = consommateurs(PYDIR / "engine", lectrices)
        gard = gardes_qui_mordent(PYDIR / "tests", set(lectrices) | set(cons))
        ecr = [k for k, v in lect.items() if all(r.startswith("ECRITURE/") for r in v)]
        print("== OCCURRENCES DU BIT 15 DANS `engine/**` (AST), ventilees ==")
        for k, v in lect.items():
            print("   %-70s %s" % (k, ",".join(v)))
        print("   -> %d sites DECLARENT le masque (etat 3 : enumere), %d le LISENT"
              % (len(ecr), len(lect) - len(ecr)))
        print("== VERDICT PAR FONCTION LECTRICE (garde via consommateur incluse) ==")
        for fn, etat, ou, via in verdict_par_lecteur(lect, cons, gard):
            print("   %-28s %-32s via=%-26s %s" % (fn, etat, via, ou))
        if args.step == "lecteurs":
            return 0

    if args.step in ("offline", "gisement"):
        g = gisement()
        print("== GISEMENT ==")
        print("   abilities a masque lu : %d ; porteurs du bit 15 : %d ; pool : %s"
              % (g["abilities_a_masque_lu"], g["porteurs_du_bit_15"],
                 g["pool_mesure"] if g["pool_mesure"] is not None else "NON MESURE"))
        for l in g["lignes"]:
            print("   %4d %-10s self=%-5s reg=%-5s pool=%s"
                  % (l["ability"], l["rules"], l["self_cast"], l["registre"], l["au_pool"]))
        if args.step == "gisement":
            return 0

    if args.step in ("offline", "paire"):
        p = paire()
        print("== PAIRE DISCRIMINANTE ==")
        print("   " + json.dumps(p))
        if not p["discriminante"]:
            print("FAIL -- la paire n'isole plus le bit 15 (xor=%s)" % p["xor"])
            return 1
        if p["zone_d0_avec"] is not True or p["zone_d0_sans"] is not False:
            print("FAIL -- la zone a d=0 ne separe plus les deux masques")
            return 1
        print("OK -- xor = CasterIsPossibleTarget, zone d0 : True / False")
        if args.step == "paire":
            return 0

    if args.step == "live":
        return live(args.board)
    return 0


class BareAbility:
    """Porteur MINIMAL du masque d'une ability HORS REGISTRE, du meme genre que
    `targeting._NormalAttackTargeting` : ni behaviour ni `ABILITY_TYPE`, seulement ce que la cascade
    et `caster_is_valid_target` lisent (`TARGETING_OPTIONS`, `ABILITY_ID`, les deux regles-deleguees).

    `rules_override` sert la CONTRE-EPREUVE : desarmer le bit 15 sans toucher au registre."""

    def __init__(self, ability_id: int, rules_override=None):
        self.ABILITY_ID = int(ability_id)
        opts = targeting_options_for(int(ability_id))
        if opts is None:
            raise RuntimeError("masque de %d NON LU -- substrat, pas une mesure" % ability_id)
        self.TARGETING_OPTIONS = opts if rules_override is None else _replace_rules(opts,
                                                                                    rules_override)

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
        """Le bit `TargetMatchesDynamicRule` n'est pose par AUCUN des deux masques de la paire
        (`0x8400` / `0x400`), donc la cascade ne consulte jamais cette methode."""
        return 0

    def get_dynamic_invalid_caster_reason(self, state, caster_id) -> int:
        """Idem pour `CasterMatchesDynamicRule` / `AddCasterIfMatchesDynamicRule`."""
        return 0


def _replace_rules(opts, rules):
    from dataclasses import replace as _dc_replace
    return _dc_replace(opts, rules=rules)


def _mesure(sid, rid, board, mutant=False):
    """Le natif ET le port, sur le MEME etat, pour les deux abilities de la paire."""
    from engine.runner.abilities.targeting import caster_is_valid_target
    from engine.runner.snapshot import load_state
    from engine.entities.pathfinding.board import Board

    obs = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    board_obj = Board(bg["tiles"], adjacency="native_sym")
    state = load_state(dec, obs, snap, board=board_obj)

    vivants = [u for u in (obs.get("units") or []) if not u.get("isDead")]
    by_vis = {u.get("visualId"): u for u in vivants}
    out = {}
    for vis, aid in ((PAIR_CARRIER_WITH, PAIR_WITH_BIT), (PAIR_CARRIER_WITHOUT, PAIR_WITHOUT)):
        u = by_vis.get(vis)
        if u is None:
            out[vis] = {"error": "absent du runner (%s)" % sorted(by_vis)}
            continue
        uid = int(u["squadId"])
        r = from_here_ids(sid, rid, uid, aid)
        r["unitId"] = uid
        r["pos"] = [u.get("col"), u.get("row")]
        if not r["present"]:
            out[vis] = r
            continue
        r["natif"] = uid in (r.get("fromHere") or [])
        # LE CARDINAL DES AUTRES cibles, MESURE et non suppose : c'est l'entree `other_valid_targets`
        # du port, et c'est LUI qui dit si le regime est degenere (l'etage d'ajout self-cast).
        r["autres_cibles"] = len([t for t in (r.get("fromHere") or []) if int(t) != uid])
        opts = targeting_options_for(aid)
        rules = int(getattr(opts, "rules", 0) or 0)
        if mutant:
            rules &= ~int(TR.CasterIsPossibleTarget)
        ab = BareAbility(aid, rules_override=rules)
        r["port"] = bool(caster_is_valid_target(state, uid, ab,
                                                other_valid_targets=r["autres_cibles"]))
        r["accord"] = (r["port"] == r["natif"])
        out[vis] = r
    out["_positions"] = {u.get("visualId"): [u.get("col"), u.get("row")] for u in vivants}
    return out


def live(board) -> int:
    """LA CONFRONTATION. Un seul runner porte les DEUX casters : le natif repond aux deux questions
    dans le MEME etat, aucune variable de montage ne les separe.

    DEUX PASSES, et la premiere n'est pas du gaspillage -- c'est elle qui MESURE le regime degenere
    au lieu de le supposer :

      * passe A (spawn nu) : les deux casters sont ADJACENTS, donc chacun est cible valide de
        l'autre ; l'etage d'ajout `isSelfCasting` de `GetValidTargets` met alors le caster dans
        l'ensemble **des deux cotes**, bit 15 ou pas. Un accord lu ICI ne prouverait RIEN.
      * passe B (`--place`) : ils sont ecartes de `ECART_ISOLEMENT > reach`, donc `targets.Count == 0`
        et l'etage d'ajout ne peut rien. Le bit 15 est le SEUL chemin qui reste.

    Les deux tuiles sont des CONSTANTES, mais leur propriete est RE-DERIVEE au runtime (distance
    effective >= `ECART_ISOLEMENT`, et le build refuse un placement invalide -- il imprime
    `placements verifies OK`)."""
    import hexgeo
    _resolve_session, _rpc = _rpc_mod()
    sid = _resolve_session()
    d = hexgeo.distance(PLACE_WITH, PLACE_WITHOUT)
    if d < ECART_ISOLEMENT:
        print("FAIL -- les deux tuiles du montage sont a %d (< %d)" % (d, ECART_ISOLEMENT))
        return 2

    verdicts = []
    rid, err = _build(board, "%s,%s" % (PAIR_CARRIER_WITH, PAIR_CARRIER_WITHOUT),
                      "necroWarden,necroWarden")
    if rid is None:
        print("BUILD KO (passe A) -- %s" % err)
        return 2
    try:
        degenere = _mesure(sid, rid, board)
    finally:
        _dispose(sid, rid)

    rid2, err = _build(board, "%s,%s" % (PAIR_CARRIER_WITH, PAIR_CARRIER_WITHOUT),
                       "necroWarden,necroWarden",
                       place=["%s:%d,%d" % (PAIR_CARRIER_WITH, PLACE_WITH[0], PLACE_WITH[1]),
                              "%s:%d,%d" % (PAIR_CARRIER_WITHOUT,
                                            PLACE_WITHOUT[0], PLACE_WITHOUT[1])])
    if rid2 is None:
        print("BUILD KO (passe B) -- %s" % err)
        return 2
    try:
        isole = _mesure(sid, rid2, board)
        mutant = _mesure(sid, rid2, board, mutant=True)
    finally:
        _dispose(sid, rid2)

    brut = {"board": board, "distance": d,
            "A_spawn_nu": degenere, "B_isole": isole, "B_mutant": mutant}
    print(json.dumps(brut, indent=1))
    print("[RAW] " + json.dumps(brut))

    a1, a2 = degenere.get(PAIR_CARRIER_WITH), degenere.get(PAIR_CARRIER_WITHOUT)
    b1, b2 = isole.get(PAIR_CARRIER_WITH), isole.get(PAIR_CARRIER_WITHOUT)
    m1 = mutant.get(PAIR_CARRIER_WITH)
    # A -- le regime DEGENERE doit l'etre VRAIMENT, sinon la passe B ne demontre rien de plus.
    verdicts.append(("A degenere (les deux ont le caster)",
                     bool(a1 and a2 and a1.get("natif") and a2.get("natif")
                          and a1.get("autres_cibles") and a2.get("autres_cibles"))))
    # B -- LE DISCRIMINANT : meme portee, meme self-cast, meme TargetIsFriendly, aucune autre cible.
    verdicts.append(("B isole : 1061 (bit 15) rend le CASTER",
                     bool(b1 and b1.get("natif") is True and b1.get("autres_cibles") == 0)))
    verdicts.append(("B isole : 1049 (sans le bit) ne rend RIEN",
                     bool(b2 and b2.get("natif") is False and b2.get("autres_cibles") == 0)))
    verdicts.append(("B isole : accord natif/port sur les deux",
                     bool(b1 and b2 and b1.get("accord") and b2.get("accord"))))
    # CONTRE-EPREUVE -- bit 15 desarme cote PORT : le port doit DIVERGER du natif sur 1061.
    verdicts.append(("contre-epreuve : bit 15 desarme -> DESACCORD sur 1061",
                     bool(m1 and m1.get("port") is False and m1.get("natif") is True)))
    for nom, ok in verdicts:
        print("   %-52s %s" % (nom, "OK" if ok else "FAIL"))
    return 0 if all(ok for _n, ok in verdicts) else 1


if __name__ == "__main__":                                                  # pragma: no cover
    raise SystemExit(main())
