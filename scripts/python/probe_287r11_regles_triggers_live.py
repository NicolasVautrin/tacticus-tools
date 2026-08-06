"""#287-r11 -- CONFRONTATION LIVE des regles dynamiques de ciblage portees, contre l'oracle NATIF.

    | id   | ability          | porteur                        | etage demande                    |
    |------|------------------|--------------------------------|----------------------------------|
    | 1200 | SquigLaunchas    | `orksRukkatrukk` (MACHINE OF WAR) | triggers DSL AmountIsEqualOrGreater |
    | 1168 | EntropyCannons   | `deathCrawler`   (MACHINE OF WAR) | IsInTeamAura + HasNegativeModifier |
    | 1179 | CultDemagogue    | `genesPrimus`    (pool)           | GetFreeSurroundingTiles + GetAllAliveUnits |

L'ORACLE est `abilityReason(casterId, abilityType, targetId)` = le masque `TargetingRule` rendu par
`TargetingQuery$$GetInvalidTargetReason` + `...GetInvalidCasterReason`. Contrat de fidelite, le meme
que `probe_287r8_regles_battlequery_live` :

    natif == 0   =>  port == 0          STRICT -- c'est CE bras qui attrape le SUR-REFUS
    natif != 0   =>  port == natif      (regle PORTEE)
                 ou  port == 0          (regle NON PORTEE -> permissif, documente)
    jamais       :   port != 0 et port != natif

⚠ UN SOUS-REFUS NE SE DISCULPE PAS PAR LE DESARMEMENT, et c'est la lecon la plus chere de la tranche
parente. L'attribution par desarmement ne discrimine que sur les SUR-refus : desarmer ne peut rendre
le port que PLUS permissif, donc tout sous-refus survit au temoin PAR CONSTRUCTION et serait compte
« preexistant » -- un vert automatique. Les trois familles sont donc comptees SEPAREMENT, et le
SOUS-refus fait rougir sans passer par l'attribution.

⚠ LA GEOMETRIE EST PLACEE, PAS SUBIE (`--place` / `--a-place`). Les trois regles sont des predicats
de VOISINAGE ou de PORTEE ; un placement de spawn les mettrait toutes du meme cote et le vert ne
prouverait rien. Chaque montage pose donc des cibles des DEUX cotes de sa bascule, et la ventilation
est IMPRIMEE -- un cote vide se voit.

⚠ ORACLE COURT-CIRCUITE (#287-r6). `SquigLaunchas` porte `constants.initialCooldownTurns = 1` :
`AttackQuery$$GetInvalidTargetReason` refuse EN AMONT (`ValidRequest`) et l'oracle ne traverse jamais
la cascade. La parade est `oracle_targeting.debloquer_oracle` avec `jouer_adverse=False` -- le tour
adverse DEPLACERAIT les unites et detruirait la geometrie qu'on vient de placer.

Usage (session warmee ; le probe monte et DISPOSE ses propres runners, un a la fois) :
    python scripts/python/probe_287r11_regles_triggers_live.py
    python scripts/python/probe_287r11_regles_triggers_live.py --only 1168
ASCII only ; exit 0 = contrat respecte, bascules exercees, aucune violation imputable.
"""
from __future__ import annotations

import argparse
import contextlib
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

SQUIG = int(ActiveAbilityType.SquigLaunchas)          # 1200
ENTROPY = int(ActiveAbilityType.EntropyCannons)       # 1168
DEMAGOGUE = int(ActiveAbilityType.CultDemagogue)      # 1179

# --------------------------------------------------------------------------------------------- #
# LES MONTAGES -- un par id, chacun avec sa geometrie PLACEE.
#
# `board` : les deux montages MoW exigent un board portant un `MachineOfWarPosition` pour les DEUX
# camps (`rl_duel._board_mow_ok`) -- sans quoi la MoW drop SILENCIEUSEMENT au deploiement
# (project_mow_deploy_gate). `C1_02` est celui que `probe_249_deathguard_targeting` utilise deja
# pour monter `deathCrawler`, donc il est MESURE MoW-capable, pas suppose.
# --------------------------------------------------------------------------------------------- #

MONTAGES = {
    # ⚠ `C1_02` fait 5 colonnes x 7 lignes (col 0..4, row 0..6). Toute tuile hors de ce rectangle
    # fait REFUSER le placement et le build ne construit AUCUN runner -- panne qui se lit comme un
    # « porteur absent » si on ne regarde pas la sortie du build.
    "1200": dict(
        at=SQUIG, board="C1_02", seed=4242, mow="orksRukkatrukk",
        # UN Ork (`orksNob`) et TROIS non-Orks : les QUATRE bras du predicat ont chacun leur temoin.
        p_units="orksNob,ultraTitus,ultraTitus,ultraTitus",
        # ⚠ `necroWarden` n'existe qu'en TROIS exemplaires dans le seed BC : un 4e n'est pas
        # REFUSE, il n'arrive simplement pas -- mesure de ce probe, la 4e cible manquait sans
        # aucun message. D'ou le 4e id DISTINCT.
        a_units="necroWarden,necroWarden,necroWarden,necroDestroyer",
        # E1 (2,3) : `orksNob` en (2,2)          -> 1 Ork  , 1 ami  -> bras `nrOfUnits`   (>=1 Ork)
        # E2 (1,1) : deux `ultraTitus` (0,1)/(1,2) -> 0 Ork, 2 amis -> bras `nrOfUnits_2` (>=2 amis)
        # E3 (4,6) : UN seul `ultraTitus` (4,5)  -> 0 Ork  , 1 ami  -> REFUS (1 < 2)
        # E4 (0,6) : isole                       -> 0 Ork  , 0 ami  -> REFUS
        place=["orksNob:2,2", "ultraTitus:0,1", "ultraTitus:1,2", "ultraTitus:4,5"],
        a_place=["necroWarden:2,3", "necroWarden:1,1", "necroWarden:4,6", "necroDestroyer:0,6"],
    ),
    "1168": dict(
        at=ENTROPY, board="C1_02", seed=4242, mow="deathCrawler",
        # `deathTyphus` est le porteur de l'aura `ContagionsOfNurgle_ArmorReduction1` du montage
        # MoW de `probe_249_deathguard_targeting` -- reutilise tel quel.
        p_units="deathTyphus,deathPutrifier",
        a_units="ultraTitus,ultraTitus,ultraTitus,ultraTitus",
        place=["deathTyphus:2,3", "deathPutrifier:0,0"],
        # d = 1 / 2 / 3 / 4 depuis `deathTyphus`. Le rayon natif de l'aura vaut 1/2/3 selon
        # `TurnsStarted(porteur)` (case-224) : quel qu'il soit, il y a des cibles des DEUX cotes.
        a_place=["ultraTitus:2,4", "ultraTitus:2,5", "ultraTitus:2,6", "ultraTitus:4,0"],
    ),
    # ⚠ LA REGLE DE 1179 NE LIT PAS LA CIBLE (ses deux termes ne dependent que du caster) : sa
    # bascule ne peut PAS s'exercer cible par cible, seulement entre DEUX MONTAGES. D'ou les deux
    # entrees ci-dessous, jouees a la suite, et le critere de non-degenerescence qui porte alors sur
    # la PAIRE et non sur un montage seul.
    "1179-libre": dict(
        at=DEMAGOGUE, board="C1_02", seed=4242, mow=None,
        p_units="genesPrimus,ultraTitus",
        a_units="necroWarden,necroWarden",
        # caster au centre, tuiles libres tout autour -> `freeTiles` NON VIDE -> natif 0.
        # Les deux cibles sont a d <= 2 = `constants.range`, pour que le refus mesure soit bien
        # celui de la regle dynamique et non `TargetIsInRange`.
        place=["genesPrimus:2,3", "ultraTitus:0,0"],
        a_place=["necroWarden:2,4", "necroWarden:2,5"],
    ),
    "1179-encercle": dict(
        at=DEMAGOGUE, board="C1_02", seed=4242, mow=None,
        p_units="genesPrimus,ultraTitus",
        a_units="necroWarden,necroWarden,necroWarden",
        # `genesPrimus` dans le COIN (0,0), dont les TROIS voisins portent un ennemi : le BFS ne
        # sort pas (`WalkPathfinder$$UnitIsBlockedByEnemyUnit`) et aucune tuile occupee n'entre dans
        # le stop_set -> `freeTiles` VIDE. Aucun `genesSmnDecoy` en jeu -> 2e terme faux -> natif 2.
        place=["genesPrimus:0,0", "ultraTitus:4,6"],
        a_place=["necroWarden:0,1", "necroWarden:1,0", "necroWarden:1,1"],
    ),
}

PORTEUR_VIS = {SQUIG: "orksRukkatrukk", ENTROPY: "deathCrawler", DEMAGOGUE: "genesPrimus"}


def _rpc(method, body, timeout=90000):
    return INV.rpc(INV._session_id(), method, [body], timeout)


def _run(args) -> str:
    """Rend la sortie du build. ⚠ ELLE DOIT ETRE LUE : un `--place` hors board (ou sur une tuile
    occupee / non marchable) est REFUSE ligne par ligne, et le build continue avec les autres. Une
    cible manquante se lit alors comme « la geometrie n'a pas ce cote », pas comme un placement
    rate. Mesure de ce probe : `necroWarden:0,6` a disparu silencieusement du premier montage."""
    r = subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return (r.stdout or b"").decode("utf-8", "replace")


def seed_bc_with_ammo(tag: str, ammo: int = 9) -> Path:
    """Seed BC PATCHE : `Player.Players[].MachineOfWarAmmo <- ammo`, ecrit sous `logs/` (JAMAIS
    dans `data/`, qui est versionne et ne contient que des ENTREES). Repris VERBATIM de
    `probe_250_blacklegion_targeting.seed_bc_with_ammo`.

    SANS LUI, LES DEUX MONTAGES MoW NE MESURENT RIEN, et c'est MESURE, pas redoute : les deux
    abilities portent `constants.munitionsCost = 1`, le seed BC partage part a
    `MachineOfWarAmmo = 0`, et `AttackQuery$$GetInvalidTargetReason` court-circuite sur
    `ActiveAbility$$get_CanCurrentlyBeUsed` en rendant le litteral `1` (`ValidRequest`) AVANT la
    cascade. Premier jet de ce probe : `casterReason=1`, « munitions epuisees », APRES quatre tours
    de deblocage -- aucun nombre de tours ne leve ce court-circuit-la. Le patch n'ouvre QUE la porte
    de `CanCurrentlyBeUsed` ; il ne touche a aucune regle de ciblage."""
    src = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for pl in (((src.get("Player") or {}).get("Players")) or {}).values():
        if isinstance(pl, dict) and "MachineOfWarAmmo" in pl:
            pl["MachineOfWarAmmo"] = int(ammo)
    out = LOGS / ("_287r11-seedbc-%s.json" % tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


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
    for m in (dec.get("mows") or []):
        if m.get("casterId") is not None:
            by_vis.setdefault(m.get("visualId"),
                              {"id": m["casterId"], "visualId": m.get("visualId"),
                               "team": m.get("team"), "pos": {}})
    return dec, ob, snap, board, [u for u in units if u.get("alive")], by_vis


def _cote(at: int, caster, cible, alive: list, board) -> str:
    """Le cote de la bascule ou tombe cette cible, DERIVE DE LA GEOMETRIE (jamais du verdict natif :
    ventiler par la reponse qu'on veut confronter ne prouverait rien).

    Un cote VIDE est imprime par l'appelant -- c'est ce qui empeche de lire comme un succes un
    montage ou la regle n'a jamais eu l'occasion de mordre."""
    cp = _pos(cible)
    if cp is None:
        return "?"
    if at == SQUIG:
        # `Friends(Owner)` : le referent est le caster (la MoW), donc son EQUIPE.
        mine = caster.get("team")
        voisins = {board.coord(n) for n in board.neighbours(_tid(board, cp))} if board else set()
        amis = [u for u in alive if u.get("team") == mine and _pos(u) in voisins]
        orks = [u for u in amis if str(u.get("visualId") or "").startswith("orks")]
        return "dedans" if (len(orks) >= 1 or len(amis) >= 2) else "dehors"
    if at == ENTROPY:
        porteur = next((u for u in alive if u.get("visualId") == "deathTyphus"), None)
        pp = _pos(porteur) if porteur else None
        return "dedans" if (pp and hexgeo.distance(pp, cp) <= 3) else "dehors"
    if at == DEMAGOGUE:
        return "-"
    return "-"


def _tid(board, coord):
    for t in board.by_id:
        if board.coord(t) == coord:
            return t
    return None


def mesurer(rid: int, at: int, ctx) -> dict:
    dec, ob, snap, board, alive, by_vis = ctx
    state = load_state(dec, ob, snap, board=board)
    out = {"exact": [], "sous_refus": [], "viol": [], "hors_regle": [], "accord_zero": [],
           "cibles": 0, "cotes": {"dedans": 0, "dehors": 0}, "natif": {}, "absent": None,
           "court_circuite": None}
    # SUBSTRAT EFFECTIVEMENT MONTE, imprime tel quel : une unite demandee par `--place` qui
    # n'arrive PAS en bataille (sans pour autant faire refuser le placement) retirerait un cote de
    # la bascule en silence.
    out["substrat"] = ["%s t%d %s %s" % (u.get("visualId"), u["id"], _pos(u),
                                         "team%s" % u.get("team")) for u in alive]
    caster = by_vis.get(PORTEUR_VIS[at])
    if caster is None:
        out["absent"] = PORTEUR_VIS[at]
        return out
    r0 = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                "abilityType": at}, 60000) or {}
    if O.oracle_court_circuite(r0):
        out["court_circuite"] = O.cause_du_court_circuit(r0)
        return out
    ab = P._porteur(at)
    mine = caster.get("team")
    for u in alive:
        if u.get("id") == caster.get("id") or u.get("team") == mine:
            continue                                     # `TargetIsEnemy` : cibles ENNEMIES
        tid = int(u["id"])
        r = _rpc("abilityReason", {"runnerId": rid, "casterId": caster["id"],
                                   "abilityType": at, "targetId": tid}, 60000) or {}
        tr = r.get("targetReason") or {}
        nat = int(tr.get("hex") or "0x0", 16)
        port = int(is_invalid_target(state, int(caster["id"]), tid, ab) or 0)
        cote = _cote(at, caster, u, alive, board)
        if cote in out["cotes"]:
            out["cotes"][cote] += 1
        out["natif"][hex(nat)] = out["natif"].get(hex(nat), 0) + 1
        out["cibles"] += 1
        row = (at, tid, "%s %s %s" % (u.get("visualId"), _pos(u), cote), hex(nat),
               ",".join(tr.get("reasons") or []) or "-", hex(port))
        if nat == 0 and port == 0:
            out["accord_zero"].append(row)
        elif nat == 0 and port != 0:
            out["viol"].append(row)                      # SUR-REFUS
        elif port == nat:
            (out["exact"] if (nat & int(TR.TargetMatchesDynamicRule))
             else out["hors_regle"]).append(row)
        elif port == 0:
            out["sous_refus"].append(row + (_diagnostic(state, caster, tid, at),))
        else:
            out["viol"].append(row)
    return out


def _diagnostic(state, caster, tid: int, at: int) -> str:
    """DECOMPOSITION PAR ETAGE d'un desaccord : ce que chaque etage du corps natif rend cote port,
    pas seulement le verdict final. Jamais fitter un scalaire."""
    try:
        from engine.runner.abilities.behaviours.context import entities_from_state
        ents = entities_from_state(state, int(caster["id"]), int(tid))
        if at == SQUIG:
            import gameconfig as GC
            from engine.runner.abilities.orks import (
                squig_launchas_has_minimum_adjacent_friendly_units,
                squig_launchas_has_minimum_adjacent_orks)
            c = (GC.ability("SquigLaunchas") or {}).get("constants") or {}
            a = squig_launchas_has_minimum_adjacent_orks(int(c.get("nrOfUnits") or 0))
            b = squig_launchas_has_minimum_adjacent_friendly_units(
                int(c.get("nrOfUnits_2") or 0))
            return "orks(>=%s)=%s amis(>=%s)=%s" % (
                c.get("nrOfUnits"), a.should_trigger(ents),
                c.get("nrOfUnits_2"), b.should_trigger(ents))
        if at == ENTROPY:
            from engine.entities.effect_type import EffectType
            from engine.entities.selectors.accessors import Target
            from engine.entities.selectors.tiles import Caster
            from engine.entities.stats import StatPart, StatType
            from engine.entities.formulas import StatAmount
            from engine.entities.triggers import (AmountIsGreaterThanZero, HasNegativeModifier,
                                                  IsInTeamAura)
            aura = IsInTeamAura(Target(),
                                int(EffectType.ContagionsOfNurgle_ArmorReduction1), Caster())
            neg = HasNegativeModifier(Target(), (int(StatType.FIXED_ARMOR),))
            init = AmountIsGreaterThanZero(StatAmount(Target(), int(StatType.FIXED_ARMOR),
                                                      int(StatPart.INITIAL)))
            return "aura=%s hasNeg=%s fixedArmorInitial>0=%s" % (
                aura.should_trigger(ents), neg.should_trigger(ents), init.should_trigger(ents))
        if at == DEMAGOGUE:
            from engine.runner.abilities.genestealer import (cult_demagogue_free_spawn_tiles,
                                                             cult_demagogue_has_living_decoy)
            return "freeTiles=%d decoyVivant=%s" % (
                len(cult_demagogue_free_spawn_tiles(state, int(caster["id"]))),
                cult_demagogue_has_living_decoy(state, int(caster["id"])))
    except Exception as exc:                                     # pragma: no cover - diagnostic
        return "diagnostic KO: %r" % (exc,)
    return "-"


def jouer(nom: str, keep: bool) -> tuple:
    m = MONTAGES[nom]
    at = int(m["at"])
    tag = uuid.uuid4().hex[:8]
    state_file = LOGS / f"rs_287r11_{nom}_{tag}.json"
    args = ["build", "--seed", str(m["seed"]), "--board", m["board"], "--rank", "17",
            "--p-units", m["p_units"], "--a-units", m["a_units"], "--no-ai",
            "--state-file", str(state_file)]
    bc = None
    if m.get("mow"):
        bc = seed_bc_with_ammo(tag)
        args += ["--p-mow", m["mow"], "--seed-bc", str(bc)]
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
        caster = ctx[5].get(PORTEUR_VIS[at])
        if caster is not None and (O.cooldown_initial(at) or 0) >= 1:
            # `jouer_adverse=False` : le tour adverse DEPLACERAIT les unites et detruirait la
            # geometrie PLACEE -- c'est exactement le regime que `cycler_sans_ia` documente.
            debloc = O.debloquer_oracle(_rpc, rid, int(caster["id"]), at,
                                        jouer_adverse=False) or "OK"
            ctx = _contexte(rid)
        res = mesurer(rid, at, ctx)
        with P.desarme(at):
            temoin = mesurer(rid, at, ctx)
    finally:
        if not keep:
            _run(["dispose", "--state-file", str(state_file)])
        if bc is not None:
            with contextlib.suppress(Exception):
                bc.unlink()
    if refus:
        res["refus_placement"] = refus
    return rid, debloc, res, temoin


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r11 : confrontation live")
    ap.add_argument("--only", type=int, default=None, help="ne jouer qu'un id")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    noms = [n for n, m in MONTAGES.items()
            if a.only is None or int(m["at"]) == int(a.only)]
    rc = 0
    # Verdicts NATIFS agreges PAR ID (et non par montage) : 1179 ne peut faire basculer sa regle
    # qu'entre deux montages, donc son critere de non-degenerescence porte sur la PAIRE.
    natif_par_id: dict = {}
    for nomm in noms:
        at = int(MONTAGES[nomm]["at"])
        rid, debloc, res, temoin = jouer(nomm, a.keep)
        nom = ActiveAbilityType(at).name
        print("")
        print("[287r11-live] %s -- %d %s -- porteur %s -- runner %s"
              % (nomm, at, nom, PORTEUR_VIS[at], rid))
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
        d, h = res["cotes"]["dedans"], res["cotes"]["dehors"]
        print("   cibles confrontees : %d   (geometrie : dedans=%d dehors=%d%s)"
              % (res["cibles"], d, h, "" if (d and h) or at == DEMAGOGUE else "  !! UN COTE VIDE"))
        if res["cibles"] == 0:
            print("   !! AUCUNE CIBLE : la mesure n'a pas eu lieu")
            rc = 2
        print("   verdicts NATIFS observes : %s" % (res["natif"],))
        for k, v in res["natif"].items():
            natif_par_id.setdefault(at, {})[k] = natif_par_id.get(at, {}).get(k, 0) + v
        print("   refus reproduits A L'IDENTIQUE : %d" % len(res["exact"]))
        print("   accords sur 0 (cible legale des deux cotes) : %d" % len(res["accord_zero"]))
        print("   refus HORS regle dynamique (autre bit du masque) : %d" % len(res["hors_regle"]))
        for r in res["exact"] + res["accord_zero"]:
            print("      OK   t%-4d %-34s natif=%-8s [%s] port=%s"
                  % (r[1], r[2], r[3], r[4], r[5]))
        # ATTRIBUTION -- uniquement sur les SUR-refus. Un sous-refus survit au desarmement par
        # construction (desarmer ne peut que rendre le port plus permissif) : l'y soumettre serait
        # un vert automatique.
        cle = lambda r: (r[0], r[1])                                        # noqa: E731
        preexistantes = {cle(r) for r in temoin["viol"]}
        imputables = [r for r in res["viol"] if cle(r) not in preexistantes]
        survivantes = [r for r in res["viol"] if cle(r) in preexistantes]
        print("   SUR-refus imputables a cette tranche : %d" % len(imputables))
        for r in imputables:
            print("      SUR  t%-4d %-34s natif=%-8s [%s] port=%s"
                  % (r[1], r[2], r[3], r[4], r[5]))
        if survivantes:
            print("   SUR-refus PREEXISTANTS (survivent au desarmement) : %d" % len(survivantes))
        print("   SOUS-refus (natif refuse, port accepte) : %d" % len(res["sous_refus"]))
        for r in res["sous_refus"]:
            print("      SOUS t%-4d %-34s natif=%-8s [%s] port=%s | %s"
                  % (r[1], r[2], r[3], r[4], r[5], r[6]))
        # TEMOIN : desarmee, la regle ne doit plus reproduire aucun refus. Sans ce cran, un vert
        # pourrait venir d'un autre bit du masque et non de la regle mesuree.
        print("   TEMOIN desarme : %d refus encore reproduits (attendu 0)" % len(temoin["exact"]))
        if res["cibles"] == 0:
            print("   !! AUCUNE CIBLE : la mesure n'a pas eu lieu")
            rc = 2
        if imputables or res["sous_refus"]:
            rc = 1
        if temoin["exact"]:
            print("   !! le TEMOIN reproduit encore des refus : le verdict ne vient pas de la regle")
            rc = 1
    # LE CRITERE DE NON-DEGENERESCENCE, et c'est LUI le vrai -- pas la ventilation geometrique.
    # Celle-ci est un INDICE derive d'un rayon suppose (le rayon de l'aura Contagion vaut 1/2/3
    # selon `TurnsStarted`, on ne le connait pas d'avance) ; le fait qu'un accord ne soit pas vrai
    # par vacuite se lit sur les verdicts NATIFS. Il porte sur l'ID (tous montages confondus), parce
    # que la regle de 1179 ne PEUT pas basculer a l'interieur d'un montage : elle ne lit pas la
    # cible.
    print("")
    print("[287r11-live] NON-DEGENERESCENCE, par id (tous montages confondus) :")
    for at, d in sorted(natif_par_id.items()):
        zero = sum(v for k, v in d.items() if int(k, 16) == 0)
        refus = sum(v for k, v in d.items() if int(k, 16) != 0)
        ok = zero > 0 and refus > 0
        print("   %-6d %-22s natif=%s  -> %s" % (
            at, ActiveAbilityType(at).name, d,
            "les DEUX verdicts sont exerces" if ok
            else "!! REGIME DEGENERE : un seul verdict, l'accord ne prouve rien"))
        if not ok:
            rc = max(rc, 1)
    if a.only is None and set(natif_par_id) != {SQUIG, ENTROPY, DEMAGOGUE}:
        print("   !! un id n'a produit AUCUNE mesure : %s" % (sorted(natif_par_id),))
        rc = max(rc, 2)
    print("")
    print("[287r11-live] VERDICT : %s" % ("OK" if rc == 0 else "ROUGE (rc=%d)" % rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
