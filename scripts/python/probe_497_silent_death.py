"""probe_497 -- MESURE de `1068 SilentDeath` (`eldarJainZar` Jain Zar, Aeldari, HERO).

QUESTION BINAIRE, posee AVANT la methode : **la chaine part-elle du MAILLON PRECEDENT, ou de la
CIBLE ?** L'audit `combat-ability-coverage` classe 1068 `DAMAGE(Piercing)` et le kit annonce
`3hmp80` / `pierce` -- ce qui ne dit RIEN de la topologie. Le decompile de
`IdunBattleLogic.Entities.Abilities.Active.Loki.SilentDeathAbility$$ExecuteBehaviour` la donne : une
BOUCLE C# construit `nrOfTargets` maillons, et le pool du maillon `i` est
`AdjacentUnits(maillon i-1) & <cache ennemis> - <deja frappes>` -- c'est-a-dire le PRECEDENT, pas la
cible. L'i2 dit la meme chose : « up to {nrOfTargets} additional enemies **adjacent to each other** ».

Les deux modeles concurrents ne se separent QUE sur une geometrie en LIGNE :

    M_chaine  (decompile)  : Jain Zar -> A -> B -> C -> D   (D est a 3 hex de A)
    M_splash  (le voisin)  : Jain Zar -> A + les ennemis adjacents a A   (D jamais touche)

Le montage ci-dessous aligne QUATRE ennemis en colonne : `M_splash` ne peut pas atteindre le 4e.

ETAGES MESURES (jamais un scalaire fitte -- chaque etage a son oracle natif) :
  [1] EXECUTION portee     : `diag.ported is True` (sans quoi le cast est un NO-OP SILENCIEUX)
  [2] TOPOLOGIE            : la SUITE ORDONNEE des cibles frappees, port == natif. L'ordre natif est
                             lu dans la CASCADE du cast (`GroupType.Damage` = 26, une par coup), et
                             le groupe englobant `GroupType.DamageChain` = 29 est celui que le
                             decompile ecrit en dur (`Group(..., 0x1d)`).
  [3] CARDINAL             : `1 + nrOfTargets` = 4 -- la cible primaire N'EST PAS comptee dans la
                             constante, et l'i2 (« ... and up to N ADDITIONAL enemies ») le confirme.
  [4] DEGAT, COUP PAR COUP : `state.rng` CALE sur le MT live (`dumpRng`) -> egalite BIT-EXACTE des
                             `per_hit` de CHAQUE maillon. La mecanique `pierce` du kit est ainsi
                             DECOMPOSEE (profil `Piercing` -> `PiercingRatio` -> armure), jamais
                             absorbee dans un total.
  [5] GATE DE CIBLAGE      : le masque `TargetIsEnemy` MORD (allie et self refuses), et l'oracle du
                             refus est le natif lui-meme (`abilityTargets.targets` n'enumere que des
                             ennemis).
  [6] ADJACENCE NATIVE     : mesure de l'ECART entre la couronne hex du port (`dsl/base.py::_within`)
                             et la liste d'adjacence STOCKEE du natif (porte d'elevation |dElev| < 2).
                             C'est un RESIDU HERITE, pas un choix de ce port -- cf. `main()`.

Le placement est FORCE (`--place`/`--a-place`) et il est CHOISI SUR LES ELEVATIONS : sur MC1_67, la
colonne 2 monte de 2 a 4 entre les rangees 2 et 3, et le natif ne relie PAS deux tuiles dont
l'elevation differe de 2 ou plus. Le premier montage essaye (colonne 2, rangees 2..5) donnait donc
UNE chaine natif de longueur 1 -- pas parce que la mecanique n'existe pas, mais parce que le terrain
la coupait. « Bloque par la geometrie » n'est pas un resultat : on DEPLACE (rangees 3..7).

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_497_silent_death.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"      # SORTIES -> logs/, jamais data/ (#349)

SILENT_DEATH = 1068                # ActiveAbilityType.SilentDeath
BOARD = "MC1_67"
GROUP_DAMAGE = 26                  # GroupType.Damage      -- une par COUP dans la cascade
GROUP_DAMAGE_CHAIN = 29            # GroupType.DamageChain -- le `Group(..., 0x1d)` du decompile

#: La CHAINE de tuiles du montage, choisie sur les ELEVATIONS de MC1_67 (3 -> 2 -> 2 -> 1) : quatre
#: rangees consecutives de la colonne 2 dont les elevations ne sautent JAMAIS de 2, donc que le
#: natif relie vraiment. La rangee 3 (elevation 4) est le sommet du talus -- elle est le PLAFOND de
#: la chaine, et c'est mesure, pas suppose (cf. l'etage [6]).
CASTER_TILE = (2, 7)                                        # elevation 1
CHAIN_TILES = ((2, 6), (2, 5), (2, 4), (2, 3))              # elevations 2, 2, 3, 4
CHAIN_UNITS = ("orksNob", "orksRuntherd", "orksBigMek", "orksKillaKan")
ALLY_TILE = (6, 0)                                          # loin de tout : temoin du gate ALLIE

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/aeldari.py",
                "scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/targeting.py",
                "scripts/python/engine/runner/abilities/behaviours/**",
                "scripts/python/engine/entities/selectors/**",
                "scripts/python/engine/dsl/**",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le port de 1068 au NATIF via un runner live : il depend du code du "
              "port (arbre DSL + selecteurs d'adjacence/pick + la feuille d'attaque + le registre "
              "+ le masque de ciblage) ET du build charge (le natif est l'oracle de la topologie "
              "comme du degat).",
}


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-1500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec, bg


def seed_rng(s):
    """MT offline == MT live : `dumpRng` rend l'etat COMPLET (`mt[624]`, `mti`). Sans ce calage,
    `AttackDamageOperation.execute_ability_attack` SKIP le degat (rend None) -- degradation
    DEFENSIVE documentee, pas un bug : un replay de DEGAT doit caler le rng."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def morts_live(sid, rid) -> set:
    """Les unites MORTES cote natif (`observeBattle.isDead`, cf. la memoire « decisionView keeps
    dead units » : la vue de decision garde les cadavres, seul `observeBattle` tranche)."""
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]) for u in (ob.get("units") or []) if u.get("isDead")}


def morts_off(state) -> set:
    """Les unites MORTES cote port (`UnitComponent.alive`)."""
    from engine.runner.components import UnitComponent
    out = set()
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            out.add(int(eid))
    return out


def native_chain(act: dict) -> tuple:
    """La SUITE ORDONNEE des cibles frappees, et les degats COUP PAR COUP, lus dans la CASCADE du
    cast NATIF -- le seul canal qui porte l'ORDRE (les PV avant/apres ne rendent qu'un total).

    Format REEL (mesure) : `act.events` est une liste PLATE de `{kind, entity, group?, step?, tags?}`
    ou `tags` est une CHAINE JSON.
      * `kind == "group"`, `group == 29` : le `Group(..., GroupType.DamageChain)` du decompile ;
      * `kind == "group"`, `group == 26` : UN coup, `entity` = la cible frappee ;
      * `kind == "action"`, `step == 4`  : le resultat de ce coup,
        `tags.UnitStats_RemainingHealth` = les PV APRES.

    Rend `(ordre, per_hit, n_chain_groups)` : `ordre` = ids dans l'ordre de PREMIERE apparition,
    `per_hit` = `{id: [degat_coup_1, ...]}` derive des PV successifs."""
    ordre: list = []
    per_hit: dict = {}
    reste: dict = {}
    n_chain = 0
    courant = None
    for ev in (act.get("events") or []):
        if not isinstance(ev, dict):
            continue
        if ev.get("kind") == "group":
            g = ev.get("group")
            if g == GROUP_DAMAGE_CHAIN:
                n_chain += 1
            elif g == GROUP_DAMAGE:
                courant = int(ev.get("entity"))
                if courant not in ordre:
                    ordre.append(courant)
            continue
        if ev.get("kind") != "action" or courant is None:
            continue
        raw = ev.get("tags")
        try:
            tags = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            continue
        hp = tags.get("UnitStats_RemainingHealth")
        if hp is None:
            continue
        hp = int(hp)
        if courant in reste:
            per_hit.setdefault(courant, []).append(reste[courant] - hp)
        else:
            per_hit.setdefault(courant, []).append(None)   # 1er coup : PV AVANT lus a part
        reste[courant] = hp
    return ordre, per_hit, n_chain


def find(dec, visual_id):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == visual_id), None)


def adjacence_ecart(bg) -> dict:
    """ETAGE [6] -- l'ECART entre les DEUX adjacences, mesure sur le board du montage.

    Le natif enumere la liste d'adjacence STOCKEE (`TileQuery$$IterateAdjacentTiles` :
    `foreach (nid in tile.ConnectivityComponent.Neighbours)` puis la porte `|dElev| < 2`) ; le port,
    dans `engine/dsl/base.py::_within`, teste `hexgeo.distance <= r`. La couronne hex SUR-ATTEINT
    donc la liste stockee des que le terrain saute une marche d'elevation.

    Rend `{aretes_hex, aretes_natives, sur_atteintes, tuiles_touchees}` -- toutes DIRIGEES."""
    import hexgeo
    by_id = {t["id"]: t for t in bg["tiles"]}
    pos = {(t["col"], t["row"]): t for t in bg["tiles"]}
    hexa = 0
    natif = 0
    sur = 0
    touchees = set()
    for p, t in pos.items():
        nb = {(by_id[n]["col"], by_id[n]["row"]) for n in t["neighbours"] if n in by_id}
        ring = {q for q in pos if hexgeo.distance(p, q) == 1}
        hexa += len(ring)
        natif += len(nb)
        manque = ring - nb
        sur += len(manque)
        if manque:
            touchees.add(p)
    return {"aretes_hex": hexa, "aretes_natives": natif, "sur_atteintes": sur,
            "tuiles_touchees": len(touchees)}


#: LES QUATRE VARIANTES DE GENERALISATION -- `(nom, tuile du caster, [(unite, tuile), ...], hp)`.
#: Chacune EXERCE un etage que le montage nominal ne peut pas exercer, et le comportement porte y
#: CHANGE le resultat observable. `hp = None` -> PV nominaux (le maillon MEURT).
VARIANTES = (
    # BRANCHE : le pool du 1er maillon a TROIS candidats, celui du 2e en a DEUX -> le
    # `PickRandomly(pool, 1)` est un VRAI tirage, et l'ORDRE de la chaine est decide par le PRNG.
    # Le montage nominal, lui, a des pools SINGLETON : il ne pouvait pas separer « le port tire au
    # bon moment » de « le port ne tire pas du tout ».
    ("branche", (2, 7),
     (("orksNob", (2, 6)), ("orksRuntherd", (1, 6)), ("orksBigMek", (3, 6)),
      ("orksKillaKan", (2, 5))), "200000"),
    # CAP : CINQ ennemis alignes, elevations compatibles -> le natif s'arrete a `1 + nrOfTargets`
    # = 4 et le 5e n'est JAMAIS touche. C'est la borne de la boucle, mesuree plutot que crue.
    ("cap", (2, 8),
     (("orksNob", (2, 7)), ("orksRuntherd", (2, 6)), ("orksBigMek", (2, 5)),
      ("orksKillaKan", (2, 4)), ("orksWarboss", (2, 3))), "200000"),
    # MORT : PV ECRASES A 3000 -> les 3 coups TUENT le maillon (une salve fait 3000 a 5600). La
    # chaine traverse-t-elle un CADAVRE ? Le port garde la position d'un mort (`damage.py` :
    # `alive=False` seulement, aucun retrait du board) ; le natif, lui, retire l'unite. Question
    # OUVERTE avant la mesure, et elle decide de la LONGUEUR de chaine.
    # ⚠ Les PV NOMINAUX (8000-12000) rendent ce scenario DEGENERE : personne ne meurt, l'accord ne
    #   prouve rien. Le temoin `morts` publie ci-dessous est ce qui l'interdit.
    ("mort", (2, 7),
     (("orksNob", (2, 6)), ("orksRuntherd", (2, 5)), ("orksBigMek", (2, 4)),
      ("orksKillaKan", (2, 3))), "3000"),
    # ELEVATION : la chaine traverse la marche 2 -> 4 de la colonne 2 (rangees 2 -> 3). Le natif ne
    # relie PAS ces deux tuiles (`|dElev| < 2`), le port si (couronne hex). C'est la mesure du
    # RESIDU HERITE de `dsl/base.py::_within` -- attendue DIVERGENTE, et c'est le but.
    ("elevation", (2, 1),
     (("orksNob", (2, 2)), ("orksRuntherd", (2, 3)), ("orksBigMek", (2, 4)),
      ("orksKillaKan", (2, 5))), "200000"),
)


def measure_montage(sid: int, caster_tile, places, hp_target, seed: str = "777",
                    board: str = BOARD, state_name: str = "probe_497_silent_death"):
    """Monte UN scenario arbitraire et rend `(mesures, dispose)` -- le corps commun de `measure()`
    et des variantes de generalisation."""
    state_path = LOGS / ("%s.json" % state_name)
    args = ["--seed", seed, "--board", board,
            "--p-units", "eldarJainZar,eldarRanger",
            "--a-units", ",".join(u for u, _ in places),
            "--place", "eldarJainZar:%d,%d" % caster_tile,
            "--place", "eldarRanger:%d,%d" % ALLY_TILE]
    if hp_target:
        args += ["--hp-target", str(hp_target)]
    for unit, tile in places:
        args += ["--a-place", "%s:%d,%d" % (unit, tile[0], tile[1])]
    rid = build(state_path, args)

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid, [u for u, _ in places]), dispose
    except Exception:
        dispose()
        raise


def measure(sid: int, seed: str = "777", board: str = BOARD, hp_target: str = "200000",
            state_name: str = "probe_497_silent_death"):
    """Monte le scenario CHAINE, joue le cast des DEUX cotes sur le MEME etat MT, rend
    `(mesures, dispose)`.

    Le TEST de garde (`tests/engine/runner/test_silent_death_live.py`) appelle CETTE fonction : une
    seule implementation du montage et des lectures, donc aucune divergence possible entre ce qui est
    MESURE ici et ce qui est GARDE la-bas.

    `hp_target` haut (defaut 200000) est DELIBERE et il ISOLE l'etage [2] : avec des PV nominaux, le
    premier maillon meurt sous les 3 coups et la question « une chaine traverse-t-elle un cadavre ? »
    se superpose a la question de la TOPOLOGIE. Les deux se mesurent separement (variante `mort`)."""
    return measure_montage(sid, CASTER_TILE, tuple(zip(CHAIN_UNITS, CHAIN_TILES)), hp_target,
                           seed=seed, board=board, state_name=state_name)


def _measure_on(sid: int, rid: int, ordre_attendu=CHAIN_UNITS) -> dict:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.operations.summon_ai import _apply_active_ability

    state, dec0, bg = load(sid, rid)
    caster = find(dec0, "eldarJainZar")
    ally = find(dec0, "eldarRanger")
    if caster is None or ally is None:
        raise AssertionError("SCENARIO NON MONTE : eldarJainZar/eldarRanger absents du decisionView")
    caster_id, ally_id = int(caster["id"]), int(ally["id"])
    par_visual = {u.get("visualId"): int(u["id"]) for u in (dec0.get("units") or [])}
    attendu = [par_visual[v] for v in ordre_attendu if v in par_visual]

    # Cible = une cible LEGALE DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset
    # move-inclus : un cast refuse rend `mutated:false`, observable identique a « l'ability ne fait
    # rien » -- #111).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": SILENT_DEATH}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == SILENT_DEATH), {})
    from_here = [int(t.get("targetId")) for t in (ab.get("fromHere") or [])]
    targets_superset = [int(t.get("targetId")) for t in (ab.get("targets") or [])]
    if not from_here:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale SUR PLACE pour 1068 "
                             "(drive des positions KO) -- fromHere vide")
    target_id = attendu[0] if attendu and attendu[0] in from_here else from_here[0]

    # ---- GATE DE CIBLAGE : le masque TargetIsEnemy MORD-il ? ------------------------------------
    # C'est la donnee posee AVEC l'entree au registre. Sans elle, `get_invalid_target_reason` rend 0
    # immediatement : degradation PERMISSIVE, invisible en self-play.
    ability = ABILITY_CLASSES[SILENT_DEATH]()
    gate = {
        "ennemi": get_invalid_target_reason(state, caster_id, target_id, ability),
        "allie": get_invalid_target_reason(state, caster_id, ally_id, ability),
        "soi": get_invalid_target_reason(state, caster_id, caster_id, ability),
    }
    gate_natif = {"allie_dans_targets": ally_id in targets_superset,
                  "soi_dans_targets": caster_id in targets_superset}

    # ---- MT COMMUN : cale AVANT les deux casts ---------------------------------------------------
    rng0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    if not isinstance(rng0, dict) or "mt" not in rng0:
        raise AssertionError("dumpRng indisponible -> le degat n'est pas confrontable bit-exact")
    state.rng = seed_rng(rng0)

    # ---- OFFLINE : le cast, joue par le port -----------------------------------------------------
    off_hp_before = hp_off(state)
    off_morts_avant = morts_off(state)
    res = _apply_active_ability(state, caster_id, target_id, SILENT_DEATH) or {}
    diag = res.get("diag") or {}
    off_hp_after = hp_off(state)
    off_morts = sorted(morts_off(state) - off_morts_avant)
    off_chain = [int(c["target"]) for c in (diag.get("chain") or []) if c.get("target") is not None]
    off_per_hit = {int(c["target"]): list(((c.get("attack") or {}).get("per_hit")) or [])
                   for c in (diag.get("chain") or []) if c.get("target") is not None}

    # ---- LIVE : le MEME cast, joue par le natif, depuis le MEME etat MT --------------------------
    live_hp_before = hp_live(sid, rid)
    live_morts_avant = morts_live(sid, rid)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": SILENT_DEATH,
        "targetId": target_id}, "captureEvents": True}, 90) or {}
    act0 = (act.get("actions") or [{}])[0]
    live_hp_after = hp_live(sid, rid)
    ordre, per_hit_brut, n_chain_groups = native_chain(act0)
    # 1er coup de chaque cible : le delta se prend contre les PV D'AVANT le cast (la cascade ne
    # publie que les PV APRES chaque coup).
    live_per_hit = {}
    for uid, serie in per_hit_brut.items():
        base = live_hp_before.get(uid)
        live_per_hit[uid] = [serie[0] if serie[0] is not None else None] + serie[1:]
        if serie and serie[0] is None and base is not None:
            reste_apres_1 = base - sum(x for x in serie[1:] if x is not None)
            live_per_hit[uid][0] = base - (live_hp_after.get(uid, base)
                                           + sum(x for x in serie[1:] if x is not None))
            del reste_apres_1

    return {
        "rid": rid, "caster": caster_id, "ally": ally_id, "target": target_id,
        "attendu": attendu, "from_here": from_here, "targets_superset": targets_superset,
        "routed": res.get("routed"), "ported": diag.get("ported"), "diag": diag,
        "cast_error": act0.get("error"), "mutated": act0.get("mutated"),
        "off_chain": off_chain, "live_chain": ordre,
        "off_per_hit": off_per_hit, "live_per_hit": live_per_hit,
        "off_delta": {k: off_hp_before[k] - off_hp_after[k] for k in off_hp_before
                      if off_hp_before[k] != off_hp_after.get(k)},
        "live_delta": {k: live_hp_before[k] - live_hp_after[k] for k in live_hp_before
                       if live_hp_before[k] != live_hp_after.get(k)},
        "n_chain_groups": n_chain_groups, "max_targets": diag.get("max_targets"),
        "gate": gate, "gate_natif": gate_natif,
        "adjacence": adjacence_ecart(bg),
        # TEMOIN DE NON-DEGENERESCENCE de la variante `mort` : sans lui, « la chaine traverse un
        # cadavre » se lirait sur un scenario ou PERSONNE ne meurt (accord en regime degenere =
        # zero preuve). On publie les DEUX cotes, ils doivent concorder eux aussi.
        "off_morts": off_morts,
        "live_morts": sorted(morts_live(sid, rid) - live_morts_avant),
        "hp_avant": {int(k): int(v) for k, v in live_hp_before.items()},
    }


def main() -> int:
    sid = _session()
    print("[build] board=%s chaine=%s" % (BOARD, list(CHAIN_TILES)))
    m, dispose = measure(sid)
    try:
        print("[1] routed=%s ported=%s cast_error=%s mutated=%s"
              % (m["routed"], m["ported"], m["cast_error"], m["mutated"]))
        print("[2] chaine PORT  = %s" % m["off_chain"])
        print("    chaine NATIF = %s   (attendue = %s)" % (m["live_chain"], m["attendu"]))
        print("    groupes GroupType.DamageChain dans la cascade = %d" % m["n_chain_groups"])
        print("[3] cardinal port=%d natif=%d  max_targets=%s"
              % (len(m["off_chain"]), len(m["live_chain"]), m["max_targets"]))
        print("[4] degat COUP PAR COUP")
        for uid in m["live_chain"]:
            print("    unite %-4d natif=%-28s port=%s"
                  % (uid, m["live_per_hit"].get(uid), m["off_per_hit"].get(uid)))
        print("    total natif=%s" % m["live_delta"])
        print("    total port =%s" % m["off_delta"])
        print("[5] gate port  : ennemi=%s allie=%s soi=%s"
              % (m["gate"]["ennemi"], m["gate"]["allie"], m["gate"]["soi"]))
        print("    gate natif : allie_dans_targets=%s soi_dans_targets=%s"
              % (m["gate_natif"]["allie_dans_targets"], m["gate_natif"]["soi_dans_targets"]))
        a = m["adjacence"]
        print("[6] adjacence %s : aretes hex=%d natives=%d -> SUR-ATTEINTES par le port=%d "
              "(sur %d tuiles)" % (BOARD, a["aretes_hex"], a["aretes_natives"],
                                   a["sur_atteintes"], a["tuiles_touchees"]))
        ok = (m["ported"] is True and m["off_chain"] == m["live_chain"] == m["attendu"]
              and all(m["off_per_hit"].get(u) == m["live_per_hit"].get(u)
                      for u in m["live_chain"]))
        print("PROBE %s" % ("OK" if ok else "DIVERGENT"))
    finally:
        dispose()

    if "--variantes" not in sys.argv:
        return 0 if ok else 1
    for nom, ctile, places, hp in VARIANTES:
        print("")
        print("[variante %s] caster=%s places=%s hp=%s"
              % (nom, ctile, [(u, t) for u, t in places], hp or "NOMINAUX"))
        v, vdispose = measure_montage(sid, ctile, places, hp,
                                      state_name="probe_497_variante_%s" % nom)
        try:
            accord = (v["off_chain"] == v["live_chain"]
                      and all(v["off_per_hit"].get(u) == v["live_per_hit"].get(u)
                              for u in v["live_chain"]))
            print("    chaine PORT  = %s" % v["off_chain"])
            print("    chaine NATIF = %s" % v["live_chain"])
            print("    total port  = %s" % v["off_delta"])
            print("    total natif = %s" % v["live_delta"])
            print("    PV avant    = %s" % v["hp_avant"])
            print("    morts port=%s natif=%s" % (v["off_morts"], v["live_morts"]))
            for uid in v["live_chain"]:
                if v["off_per_hit"].get(uid) != v["live_per_hit"].get(uid):
                    print("    COUP PAR COUP DIVERGENT sur %d : natif=%s port=%s"
                          % (uid, v["live_per_hit"].get(uid), v["off_per_hit"].get(uid)))
            print("    -> %s" % ("ACCORD" if accord else "DIVERGENT"))
        finally:
            vdispose()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
