"""#1066 (residus #906-r1 / #985-r1) -- CONFRONTATION LIVE de la face DECISION `1211 RitesOfMorkai`.

CE QUE CE PROBE CONFRONTE
================================================================================================
`util = 1 + 100 * |{f in GetSurroundingFriends(caster, casterPosition, range, includeCenter:false)
: f != caster}|`, sous le gate de cible `GetAdjacentEnemies(casterPosition, caster, false).Count
> 0` et le gate AMONT `ShouldEvaluate` = `adj.Any(IsFriend) && adj.Any(IsEnemy)`.

Aucun tirage : les deux cotes rendent un NOMBRE, donc on confronte le NOMBRE.

    NATIF  `ncPlaybookPredict(via="evaluate")` -> `bucketUtil` (ou `bucket == "empty"`)
    PORT   `PLAYBOOKS[1211].generate_candidates(NCContext)` -> `pred`

LE TEMOIN NON NUL, ET CE QUI SEPARE
================================================================================================
Le terme utile est un COMPTE d'amis : le faire varier fait varier l'utilite de 100 en 100, donc
les regimes sont separes par construction et non par chance.

  * **A** -- gate AMONT tombe (aucun ENNEMI adjacent au caster, alors qu'un ami l'est). Le natif
    ne doit produire AUCUNE action.
  * **B** -- 1 ennemi adjacent, 1 ami dans le rayon -> `1 + 100 * 1 = 101`.
  * **C** -- 1 ennemi adjacent, 2 amis dans le rayon -> `1 + 100 * 2 = 201`.

⚠ LE RAYON N'EST PAS UN LITTERAL DU PORT : il est lu au gameconfig
(`AbilityConfiguration$$GetNumberConstant(0x16 = range)`, = 1 pour cette ability). C'est ce qui
retire le `BLOCAGE: seeding` de la fiche `#985-r1`, laquelle le croyait non publie. On ne peut pas
le faire VARIER live (il n'y a qu'une valeur au gameconfig), mais on peut MUTER le port pour
verifier qu'il le consomme reellement -- c'est l'objet de `--mutant rayon`.

LE PORTEUR EST HORS POOL, ET CE N'EST PAS UN REFUS
================================================================================================
`spaceWolfPriest` n'est pas dans `rl_duel build --list-pool` : il entre par INJECTION CATALOGUE
(`catalog_inject.write_augmented_seed_bc` + `build --seed-bc`), la voie deja mesuree par
`probe_906_rites_of_morkai_live.py` pour la face COMBAT. << Hors pool >> n'est jamais
<< non confrontable >>.

    python probe_1066_rites_of_morkai_decision_live.py [--board MC1_67] [--seed 777]
                                                       [--mutant rayon|gate|centre]

Discipline runner : state-file ABSOLU sous `logs/`, runner DISPOSE en fin de run. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import catalog_inject as CI                                         # noqa: E402
from rl_collect_batch import _rpc, _resolve_session                 # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402

RITES = int(ActiveAbilityType.RitesOfMorkai)          # 0x4bb = 1211
CASTER_VIS = "spaceWolfPriest"
P_UNITS = "spaceWolfPriest,astraCreed,adeptCanoness"
A_UNITS = "orksNob,orksWarboss"
LOGS = HERE.parents[1] / "logs" / "ad948076"

#: Le caster est ancre en (3,4). (3,5) et (4,4) lui sont adjacentes sur `MC1_67` -- VERIFIE a la
#: mesure par `_voisinage`, jamais presume : un montage dont l'adjacence n'est pas constatee est
#: un montage CREUX, et le verdict le dit.
CASTER_POS = (3, 4)
MONTAGES = (
    # (libelle, place allies, place ennemis, utilite NATIVE attendue -- None = aucune action)
    ("A: gate AMONT tombe (aucun ennemi adjacent)",
     ["spaceWolfPriest:3,4", "astraCreed:3,5", "adeptCanoness:0,0"],
     ["orksNob:6,6", "orksWarboss:6,5"], None),
    ("B: 1 ennemi adjacent, 1 ami au rayon",
     ["spaceWolfPriest:3,4", "astraCreed:3,3", "adeptCanoness:0,0"],
     ["orksNob:3,5", "orksWarboss:6,5"], 101.0),
    ("C: 1 ennemi adjacent, 2 amis au rayon",
     ["spaceWolfPriest:3,4", "astraCreed:3,3", "adeptCanoness:4,4"],
     ["orksNob:3,5", "orksWarboss:6,5"], 201.0),
    # D -- EXERCE LE RAYON. Un ami a distance EXACTEMENT 2 (`(3,2)`, anneau 2 de `(3,4)` calcule
    # par `hexgeo`, pas devine) : au rayon LU (1) il ne compte PAS, donc `101`. Sans ce regime, un
    # port qui lirait un rayon de 2 rendrait la MEME valeur partout -- mesure : le mutant `rayon`
    # NE MORDAIT PAS avant qu'il existe.
    ("D: 1 ami a distance 1, 1 ami a distance 2 (RAYON exerce)",
     ["spaceWolfPriest:3,4", "astraCreed:3,3", "adeptCanoness:3,2"],
     ["orksNob:3,5", "orksWarboss:6,5"], 101.0),
    # E -- EXERCE LE GATE AMONT SEUL. Un ennemi ADJACENT (donc le gate de CIBLE passe) et AUCUN ami
    # adjacent (donc `ShouldEvaluate` = False). C'est le SEUL regime qui les separe : en A, les
    # deux tombent ensemble, ce qui masquait le gate amont -- mesure, le mutant `gate` NE MORDAIT
    # PAS avant. L'attendu est DELIBEREMENT laisse a `1.0` : c'est ce que rend `Evaluate/3` SEUL
    # (`1 + 100*0`), et la question mesuree est de savoir si l'oracle applique `ShouldEvaluate`
    # avant. Le verdict traite ce regime a part (cf. `verdict`).
    ("E: ennemi adjacent, AUCUN ami adjacent (gate AMONT seul)",
     ["spaceWolfPriest:3,4", "astraCreed:0,0", "adeptCanoness:6,0"],
     ["orksNob:3,5", "orksWarboss:6,5"], 1.0),
)


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed_bc: Path, seed: int, board: str,
          place: list, a_place: list, verbose: bool) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--seed-bc", str(seed_bc), "--state-file", str(state_file), "--no-ai",
           "--p-units", P_UNITS, "--a-units", A_UNITS]
    for p in place:
        cmd += ["--place", p]
    for p in a_place:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-2000:]))
    rid = int(json.loads(state_file.read_text())["runnerId"])
    if verbose:
        print("[1066/1211] runner %d" % rid)
    return rid


def _caster_id(sid, rid: int):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    for u in (dv.get("units") or []):
        if u.get("visualId") == CASTER_VIS:
            return u.get("id")
    return None


def _oracle_natif(sid, rid: int, caster_id: int) -> dict:
    """⚠ UN ECHEC RENDU N'EST PAS UNE MESURE : `ok: false` LEVE, sinon un capteur muet se lirait
    comme un refus du gate (la faute exacte que `probe_970r3` documente)."""
    r = _r(sid, "ncPlaybookPredict",
           {"runnerId": rid, "unitId": caster_id, "abilityType": RITES, "via": "evaluate"}, 300)
    if not r.get("ok"):
        raise RuntimeError("ncPlaybookPredict a ECHOUE (capteur muet, PAS un refus) : %s"
                           % json.dumps(r, default=str)[:400])
    if r.get("playbookClass") != "RitesOfMorkaiPlaybook":
        raise RuntimeError("le natif a charge %s, pas RitesOfMorkaiPlaybook" % r.get("playbookClass"))
    return {"util": (None if r.get("bucket") == "empty" else r.get("bucketUtil")),
            "actions": r.get("bucketActionCount"), "vide": r.get("bucket") == "empty"}


def _nc_context(sid, rid: int, caster_id: int):
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine import weights
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32})
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, caster_id,
                      weights.load(), predictor)
    return PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        is_wall_by_pos=getattr(c, "is_wall_by_pos", None) or {},
        is_in_fog_by_pos=getattr(c, "is_in_fog_by_pos", None) or {},
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        current_player=getattr(c, "cur", None),
        machine_of_war_position=c.machine_of_war_position,
        triggered_kits=getattr(c, "live_triggered_kits", None),
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


def _voisinage(nc) -> dict:
    """L'ETAT MESURE du montage : combien d'amis / d'ennemis sont REELLEMENT adjacents au caster,
    et combien d'amis sont dans le disque du rayon LU. Sans cela, un `--place` reloge par le natif
    ferait mesurer un regime qu'on croit monte et qui ne l'est pas."""
    from engine import battle_query as bq
    from engine.playbook import noncomparable as PB
    pb = PB.PLAYBOOKS[RITES]
    if nc.origin is None:
        return {"origin": None, "amis_adj": 0, "ennemis_adj": 0, "amis_rayon": 0, "rayon": None}
    neigh = bq.neigh_map(nc)
    rng = pb._range()
    return {"origin": nc.origin, "rayon": rng,
            "amis_adj": bq.count_adjacent(nc.origin, nc.fpos, nc.elev_by_pos, neigh),
            "ennemis_adj": bq.count_adjacent(nc.origin, nc.epos, nc.elev_by_pos, neigh),
            "amis_rayon": (bq.count_surrounding(nc.origin, nc.fpos, rng, include_center_tile=False)
                           if rng is not None else 0)}


def _oracle_generateur(sid, rid: int, caster_id: int) -> dict:
    """`aiDryRunAllUnits` -- l'action que l'IA PROPOSE pour chaque unite, via
    `CalculateNextActionForUnit`, c.-a-d. EN PASSANT PAR LE GENERATEUR.

    ⚠ POURQUOI CE SECOND ORACLE EXISTE. `ncPlaybookPredict(via="evaluate")` invoque le wrapper
    `Evaluate/3` du playbook -- il ne traverse PAS `ShouldEvaluate`, qui est appele en amont par
    `ActiveAbilityActionGenerator.<GenerateActions>d__7`. MESURE (regime E) : sur un etat ou aucun
    ami n'est adjacent, `Evaluate/3` rend `1` alors que le gate amont est FAUX. Le premier oracle
    est donc STRUCTURELLEMENT AVEUGLE au gate amont, et une contre-epreuve qui le desarme ne
    pouvait pas mordre -- c'est exactement ce qui a ete observe avant l'ajout de ce volet.

    La reponse porte `units[].proposed[]`, une LISTE de messages (`MoveUnitMessage` puis
    `ActiveAbilityMessage`), et non un champ `action` -- forme LUE sur la reponse, pas supposee :
    une premiere version lisait `u["action"]["abilityId"]` et rendait `None` PARTOUT, ce qui
    faisait passer le temoin pour nul alors que l'IA proposait bien 1211.

    Rend `{"ability": <abilityType ou None>, "target": ..., "proposed": [...]}`."""
    r = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 300)
    for u in (r.get("units") or []):
        if u.get("unitId") != caster_id:
            continue
        prop = u.get("proposed") or []
        act = next((m for m in prop if m.get("cls") == "ActiveAbilityMessage"), None)
        mv = next((m for m in prop if m.get("cls") == "MoveUnitMessage"), None)
        to = ((mv["to"]["col"], mv["to"]["row"]) if mv and mv.get("to") else None)
        return {"ability": (act or {}).get("abilityType"), "target": (act or {}).get("targetId"),
                "to": to, "proposed": [m.get("cls") for m in prop]}
    return {}


def _mesurer(sid, rid, caster_id, libelle, attendu, verbose) -> dict:
    from engine.playbook import noncomparable as PB
    nat = _oracle_natif(sid, rid, caster_id)
    nc = _nc_context(sid, rid, caster_id)
    v = _voisinage(nc)
    cands = PB.PLAYBOOKS[RITES].generate_candidates(nc)
    row = {"libelle": libelle, "attendu": attendu, "natif_util": nat["util"],
           "natif_vide": nat["vide"], "natif_actions": nat["actions"],
           # ⚠ DEUX GRANDEURS DISTINCTES, et les confondre fait comparer des choses differentes :
           #  * `port_util_origine` = `Evaluate` a la position COURANTE, SANS le gate slot 6 --
           #    c'est l'homologue exact de `bucketUtil`, que `ncPlaybookPredict` obtient en
           #    invoquant `Evaluate/3` a la position courante ;
           #  * `port_util` = le choix du SWEEP (gate slot 6 compris, toutes positions candidates)
           #    -- son homologue est la proposition d'`aiDryRunAllUnits`, pas `bucketUtil`.
           "port_util_origine": PB.PLAYBOOKS[RITES].evaluate_non_comparable(nc.origin, None, nc),
           "port_util": (cands[0]["pred"] if cands else None),
           "port_target": (cands[0]["target"] if cands else None),
           "port_to": (cands[0]["to"] if cands else None),
           # Le gate propre a 1211 est le slot 6, PAR POSITION : on l'evalue a l'ORIGINE, la seule
           # position ou il est comparable au `Evaluate/3` de `ncPlaybookPredict` (qui, lui, est
           # invoque a la position courante).
           "gate_amont": PB.PLAYBOOKS[RITES].should_evaluate_at(nc, nc.origin),
           "ia": _oracle_generateur(sid, rid, caster_id), **v}
    if verbose:
        print("  [%s]\n     etat : origin=%s rayon=%s amis_adj=%d ennemis_adj=%d amis_rayon=%d"
              % (libelle, v["origin"], v["rayon"], v["amis_adj"], v["ennemis_adj"],
                 v["amis_rayon"]))
        print("     NATIF util=%s (vide=%s actions=%s) | PORT util=%s cible=%s to=%s gate@origine=%s"
              % (row["natif_util"], row["natif_vide"], row["natif_actions"], row["port_util"],
                 row["port_target"], row["port_to"], row["gate_amont"]))
        print("     IA (aiDryRunAllUnits, PASSE par le generateur) : ability=%s cible=%s (%s)"
              % (row["ia"].get("ability"), row["ia"].get("target"), row["ia"].get("proposed")))
    return row


def appliquer_mutant(nom: str) -> str:
    """CONTRE-EPREUVE : casse UN terme du port. Chaque mutant DOIT faire rougir le verdict ; un
    mutant qui laisse vert designe un terme que cette confrontation n'exerce pas."""
    from engine.playbook import noncomparable as PB
    from engine import battle_query as bq
    cls = type(PB.PLAYBOOKS[RITES])
    if nom == "rayon":                 # le rayon LU remplace par un litteral 2
        cls._range = lambda self: 2
        return "_range() force a 2 (au lieu du GetNumberConstant(0x16) = 1)"
    if nom == "gate":                  # gate slot 6 desarme (PAR POSITION)
        cls.should_evaluate_at = lambda self, ctx, pos: True
        return "should_evaluate_at() force a True -- le gate slot 6 ne filtre plus aucune position"
    if nom == "caster_ami":            # le caster ne compte plus comme ami adjacent au gate
        cls._amis_pour_le_gate = lambda self, ctx, pos: list(ctx.fpos or [])
        return ("_amis_pour_le_gate() reduit a `fpos` -- le CASTER ne compte plus comme ami "
                "adjacent, la lecture que la confrontation a etablie")
    raise SystemExit("mutant inconnu: %s" % nom)


def run(seed: int, board: str, verbose: bool = True) -> dict:
    LOGS.mkdir(parents=True, exist_ok=True)
    # Chemins PAR PROCESSUS : les quatre invocations (temoin + 3 mutants) peuvent tourner en
    # parallele, et un litteral partage les ferait se marcher dessus -- le gisement que le
    # CLAUDE.md chiffre (4 groupes, 16 probes sur 526).
    tag = "p%d" % os.getpid()
    seed_bc = LOGS / ("seed_bc_1066_swp_%s.json" % tag)
    p, units, abils = CI.write_augmented_seed_bc(seed_bc, [CASTER_VIS])
    if verbose:
        print("[1066/1211] seed BC augmente (HORS data/) -> %s | units=%s abils=%s"
              % (p, units, abils))
    sid = _resolve_session()
    out = {"board": board, "seed": seed, "regimes": [], "erreurs": []}
    for libelle, place, a_place, attendu in MONTAGES:
        sf = LOGS / ("st_1066_rites_%s_%s.json" % (libelle[0], tag))
        rid = build(sf, seed_bc, seed, board, place, a_place, verbose)
        try:
            cid = _caster_id(sid, rid)
            if cid is None:
                out["erreurs"].append("%s absent de decisionView (%s)" % (CASTER_VIS, libelle))
                continue
            out["casterId"] = cid
            out["regimes"].append(_mesurer(sid, rid, cid, libelle, attendu, verbose))
        finally:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
                if verbose:
                    print("     runner %d dispose" % rid)
            except Exception as exc:                  # pragma: no cover
                out["erreurs"].append("dispose KO: %s" % exc)
    return out


def verdict(r: dict) -> list:
    f = list(r.get("erreurs") or [])
    regs = {x["libelle"][0]: x for x in (r.get("regimes") or [])}
    A, B, C, D, E = (regs.get(k) for k in "ABCDE")
    if not all((A, B, C, D, E)):
        return f + ["regimes incomplets -- NON CONFRONTE"]
    # MONTAGE CONSTATE, jamais declare.
    if A["ennemis_adj"] != 0 or A["amis_adj"] < 1:
        f.append("MONTAGE CREUX en A : amis_adj=%d ennemis_adj=%d (attendu >=1 et 0)"
                 % (A["amis_adj"], A["ennemis_adj"]))
    for tag, row, n in (("B", B, 1), ("C", C, 2), ("D", D, 1)):
        if row["ennemis_adj"] < 1:
            f.append("MONTAGE CREUX en %s : aucun ennemi adjacent" % tag)
        if row["amis_rayon"] != n:
            f.append("MONTAGE CREUX en %s : amis_rayon=%d (attendu %d)"
                     % (tag, row["amis_rayon"], n))
    # D doit VRAIMENT porter un ami hors rayon, sinon il n'exerce rien de plus que B.
    if D["amis_adj"] != 1:
        f.append("MONTAGE CREUX en D : amis_adj=%d (attendu 1 -- le second ami doit etre HORS "
                 "du rayon)" % D["amis_adj"])
    # E : gate de CIBLE passant, gate AMONT tombant. C'est ce qui les SEPARE.
    if E["ennemis_adj"] < 1 or E["amis_adj"] != 0:
        f.append("MONTAGE CREUX en E : amis_adj=%d ennemis_adj=%d (attendu 0 et >=1)"
                 % (E["amis_adj"], E["ennemis_adj"]))
    if E["gate_amont"]:
        f.append("le gate AMONT du PORT est VRAI en E alors qu'aucun ami n'est adjacent : la "
                 "conjonction est mal portee")
    for tag, row in (("A", A), ("B", B), ("C", C), ("D", D)):
        att = row["attendu"]
        if att is None:
            if not row["natif_vide"]:
                f.append("LE NATIF EMET en regime %s (util=%s) : la RE du gate est FAUSSE"
                         % (tag, row["natif_util"]))
            if row["port_util"] is not None:
                f.append("LE PORT EMET en regime %s (util=%s) la ou le natif refuse"
                         % (tag, row["port_util"]))
            continue
        if row["natif_vide"] or row["natif_util"] is None:
            f.append("TEMOIN NUL en regime %s : le natif n'emet rien alors qu'on attend %s"
                     % (tag, att))
            continue
        if abs(float(row["natif_util"]) - att) > 1e-6:
            f.append("UTILITE NATIVE en regime %s : %s, attendu %s (la RE de la formule est "
                     "FAUSSE, pas le port)" % (tag, row["natif_util"], att))
        # `bucketUtil` s'obtient par `Evaluate/3` A LA POSITION COURANTE : son homologue est
        # `port_util_origine`, jamais le choix du sweep.
        if row["port_util_origine"] is None:
            f.append("le PORT ne calcule RIEN a l'origine en regime %s alors que le natif y rend "
                     "%s" % (tag, row["natif_util"]))
            continue
        if abs(float(row["port_util_origine"]) - float(row["natif_util"])) > 1e-6:
            f.append("PORT != NATIF a l'origine en regime %s : port=%s natif=%s"
                     % (tag, row["port_util_origine"], row["natif_util"]))
    # E -- CE QUE L'ORACLE APPLIQUE, MESURE PLUTOT QUE PRESUME. `ncPlaybookPredict(via="evaluate")`
    # invoque le wrapper `Evaluate/3` ; rien ne dit qu'il traverse `ShouldEvaluate`, qui est appele
    # par le GENERATEUR (`ActiveAbilityActionGenerator.<GenerateActions>d__7`). Deux issues, et les
    # deux sont des resultats :
    #   * natif VIDE   -> l'oracle applique bien le gate amont, et le port (qui refuse aussi) est
    #                     confronte dessus ;
    #   * natif = 1,0  -> l'oracle ne l'applique PAS. Le port, lui, refuse : l'ecart est ALORS
    #                     ATTENDU, et c'est la PREUVE que le gate amont n'est pas confrontable par
    #                     ce capteur. Ce n'est pas une faute -- mais ca doit etre DIT, pas tu.
    if not E["natif_vide"] and abs(float(E["natif_util"] or 0) - 1.0) > 1e-6:
        f.append("REGIME E : `Evaluate/3` rend %s a l'origine, attendu 1,0 (`1 + 100*0`) -- la RE "
                 "de la formule est FAUSSE" % E["natif_util"])
    # LE GATE slot 6 SE CONFRONTE SUR L'AUTRE ORACLE, celui qui passe par le GENERATEUR.
    # `ncPlaybookPredict` invoque `Evaluate/3` DIRECTEMENT : il ne traverse ni le slot 6 ni le
    # sweep de positions, donc il est structurellement aveugle a ce gate (MESURE : en E il rend 1
    # alors que le gate est faux a l'origine). `aiDryRunAllUnits`, lui, passe par
    # `CalculateNextActionForUnit` -> le generateur.
    if not any(x["ia"].get("ability") == RITES for x in (B, C, D, E)):
        f.append("TEMOIN NUL cote GENERATEUR : l'IA ne propose 1211 dans AUCUN regime -- la "
                 "confrontation du CHOIX ne prouverait rien (propositions : %s)"
                 % [x["ia"].get("ability") for x in (B, C, D, E)])
    # LE CHOIX COMPLET : ability, CIBLE et POSITION. `aiDryRunAllUnits` les rend en CLAIR
    # (contrairement au demi-pointeur de `ncPlaybookPredict`), donc c'est LE cran de fidelite.
    for tag, row in (("A", A), ("B", B), ("C", C), ("D", D), ("E", E)):
        ia_prend = row["ia"].get("ability") == RITES
        port_prend = row["port_util"] is not None
        if ia_prend != port_prend:
            f.append("CHOIX en regime %s : l'IA %s 1211, le port %s (port_util=%s, IA=%s)"
                     % (tag, "PREND" if ia_prend else "ne prend PAS",
                        "le prend" if port_prend else "ne le prend PAS",
                        row["port_util"], row["ia"].get("ability")))
            continue
        if not ia_prend:
            continue
        if row["ia"].get("target") != row["port_target"]:
            f.append("CIBLE en regime %s : l'IA vise %s, le port %s"
                     % (tag, row["ia"].get("target"), row["port_target"]))
        # LA POSITION DE CAST -- le cran le plus fort du lot. C'est elle qui distingue << le gate
        # est evalue par position, et le caster y compte comme ami >> de toute autre lecture : en
        # regime E le natif se DEPLACE pour caster, et le port doit designer la MEME tuile.
        if row["ia"].get("to") != row["port_to"]:
            f.append("POSITION DE CAST en regime %s : l'IA va en %s, le port en %s"
                     % (tag, row["ia"].get("to"), row["port_to"]))
    # SEPARATION : sans plusieurs valeurs distinctes, l'accord serait DEGENERE.
    valeurs = {x["natif_util"] for x in (B, C, D) if x["natif_util"] is not None}
    if len(valeurs) < 2:
        f.append("LE MONTAGE NE SEPARE PAS : B/C/D rendent %d valeur(s) native(s) distincte(s) (%s)"
                 % (len(valeurs), sorted(valeurs)))
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--mutant", choices=("rayon", "gate", "caster_ami"),
                    help="CONTRE-EPREUVE : casse un terme du port ; le verdict DOIT rougir")
    a = ap.parse_args()
    if a.mutant:
        print("[MUTANT] %s -> %s" % (a.mutant, appliquer_mutant(a.mutant)))
    r = run(a.seed, a.board, verbose=True)
    print()
    f = verdict(r)
    for x in f:
        print("[1066/1211] FAUTE : %s" % x)
    print("[1066/1211] VERDICT : %s" % ("OK" if not f else "FAUTES (%d)" % len(f)))
    if a.mutant:
        print("[1066/1211] MUTANT `%s` : %s" % (a.mutant, "MORD" if f else "NE MORD PAS (!!)"))
        return 0 if f else 1
    return 0 if not f else 1


if __name__ == "__main__":
    raise SystemExit(main())
