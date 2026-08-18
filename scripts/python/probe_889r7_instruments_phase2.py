"""#889-r7 -- la PHASE 2 de `1215 InstrumentsOfVengeance` confrontee au NATIF.

CE QUE CE PROBE DISCRIMINE, et ce qu'il ne discrimine pas -- a lire AVANT ses verts :

  * [A] LE CAST (phase 1) sert de PREMISSE, pas d'observable : il est deja confronte par
    `probe_889r6_instruments_of_vengeance.py` (ensembles de tuiles IDENTIQUES sur DEUX regimes). On
    le rejoue ici seulement pour armer la phase 2 des deux cotes.
  * [B] LE COUP DIFFERE. Au DEBUT DU TOUR SUIVANT du Lion, le `Triggered()` d'
    `IdunBattle.Entities.Effects.APendingAttackEffect` fire `TriggerAbility(1519)` et
    `...InstrumentsOfVengeance_AttackAbility$$CreateBehaviour` relit les QUATRE cles persistantes,
    frappe les occupants ENNEMIS des deux lignes, retire les marques `1518` et vide les cles.
    Observables : le DELTA DE PV par unite, et la DISPARITION des marques.
  * [C] LE SPAWN. Le meme arbre pose `nrOfSummons` `darkaSmnTerminator` sur des tuiles libres, avec
    un on-appearance `PerformAIAttackFromCurrentPosition`. Observable : le nombre d'unites de
    l'equipe du Lion, avant et apres.

  NON DISCRIMINE, et il faut le dire :
  * l'ORDRE des trois viviers de tuiles de spawn (`(t2 + t1) + t3`) n'est pas separable ici : les
    trois sont `Randomize`, donc deux implementations qui tirent dans un ordre different peuvent
    rendre le meme ENSEMBLE de tuiles. Le probe compare le CARDINAL et l'appartenance au vivier,
    pas la tuile exacte ;
  * le `Inform(0xc1)` est un hint AI/UI, NO-OP des deux cotes -- rien ne l'observe ;
  * la branche `On(0x25 = UnitRemoved)` n'existe PAS pour cet effet (lecture : la table de symboles
    ne publie aucun `$$CreateHandleTriggerAbilitiesInternal` pour
    `...InstrumentsOfVengeance_PendingAttackEffect`, alors qu'elle publie celui de son homologue
    `TheLionsWrath` -- le temoin est present).

MONTAGE. `--board CE6_boss` (SA carte), boss au palier `:4`, DEUX ennemis places au contact pour que
les lignes portent des occupants. Le Lion est SEUL dans son camp : son cast TERMINE donc le tour,
et UN SEUL `endturn` suffit a rouvrir son tour -- c'est la que la phase 2 part. Les pas sont
APPARIES sur `decisionView.currentPlayer`, jamais sur le NOM qu'on donne au pas (#889-r4), et le
RNG offline est re-seede AVANT chaque bascule (sinon le port tire depuis un etat que le natif a
deja consomme).
⚠ `TACTICUS_ALLOW_ROSTER_DEFICIT=1` est POSE PAR CE PROBE : le jeu publie le boss sous l'id
d'entite REMAPPE `GuildBoss12Boss1DarkaLion`, faux negatif connu du garde de roster.

ASCII only. SORTIES -> logs/, jamais data/ (#349).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"

IOV = 1215                      # ActiveAbilityType.InstrumentsOfVengeance
IOV_LOCATION_TARGET = 1518      # EffectType.InstrumentsOfVengeance_LocationTarget
IOV_PENDING_ATTACK = 1519       # EffectType.InstrumentsOfVengeance_PendingAttack
BOARD = "CE6_boss"
BOSS = "darkaBossLion:4"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/operations/triggers/loki/"
                "instruments_of_vengeance_attack.py",
                "scripts/python/engine/runner/operations/triggers/pending_attack.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
                "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
                "scripts/python/engine/runner/abilities/loki/instruments_of_vengeance.py",
                "scripts/python/engine/runner/abilities/behaviours/summon.py",
                "scripts/python/engine/entities/selectors/**",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF la PHASE 2 de 1215 -- le coup differe des deux lignes, le "
              "retrait des marques 1518 et le volet SPAWN de "
              "`InstrumentsOfVengeance_AttackAbility$$CreateBehaviour`.",
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
    env = dict(os.environ)
    env["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-2500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def bind(sid: int):
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(lambda method, body=None, timeout=60: rpc(sid, method, body or {}, timeout))


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    abst = rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles, ability_states=abst), dec


def seed_offline_rng(state, dump):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def unites_live(sid, rid) -> dict:
    """`{squadId: (team, visualId)}` -- ce qui rend le SPAWN observable."""
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): (u.get("team"), u.get("visualId") or u.get("unitId"))
            for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def unites_off(state) -> set:
    return {int(eid) for eid in state.entities}


def _pos_off(state, eid: int):
    from engine.runner.components import PositionComponent
    e = state.get_entity(int(eid))
    pc = e.get_component(PositionComponent) if e is not None else None
    return (int(eid), None if pc is None else (int(pc.col), int(pc.row)))


def marques_off(state) -> dict:
    """`{cle: [effect_type, ...]}` des instances NON consommees -- pour voir le retrait du 1518."""
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        v = sorted(int(e.effect_type) for e in effs if not e.consumed)
        if v:
            out[int(key)] = v
    return out


def _dhp(avant: dict, apres: dict) -> dict:
    return {int(k): (int(avant[k]), int(apres.get(k, avant[k])))
            for k in avant if int(apres.get(k, avant[k])) != int(avant[k])}


def _coups_natifs(act: dict) -> dict:
    """`{targetId: [Amount, ...]}` -- les coups NATIFS du pas, dans l'ORDRE d'emission. C'est ce qui
    DECOMPOSE un ecart de degat par ETAGE au lieu de le laisser en total (doctrine slice-18/19)."""
    out = {}
    for a in (act.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            try:
                tags = json.loads(td) if isinstance(td, str) else td
            except Exception:
                continue
            amt = tags.get("Amount") if isinstance(tags, dict) else None
            if amt is None:
                continue
            tid = tags.get("Target_Id") or tags.get("TargetId") or tags.get("Damage_Target_Id")
            out.setdefault(int(tid) if tid is not None else -1, []).append(int(amt))
    return out


def _gate_par_tuile(state, caster_id: int, lignes: dict) -> dict:
    """`{tuile: {HasUnit, Units, AreEnemies}}` -- le `cond` d'`AttackTileBehavior` DECOMPOSE.

    C'est la decomposition par ETAGE de la doctrine, appliquee a un PREDICAT : un total de degat
    nul ne dit pas si c'est le `HasUnit` ou l'`AreEnemies` qui a refuse, ni si la resolution
    d'occupant a rendu vide."""
    from dataclasses import replace as _replace
    from engine.entities.selectors.accessors import ActiveTarget, Owner
    from engine.entities.selectors.units import Units
    from engine.entities.triggers import AreEnemies, HasUnit
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.operations.triggers.loki import instruments_of_vengeance_attack as M

    ents = entities_from_state(state, int(caster_id), int(caster_id), actor_id=int(caster_id))
    out = {}
    for i in (0, 1):
        for tid in (lignes.get("ligne_%d" % i) or []):
            if not isinstance(tid, int) or tid in out:
                continue
            sub = _replace(ents, subject=tid, active_target=tid)
            row = {}
            for nom, noeud in (("HasUnit", HasUnit(ActiveTarget())),
                               ("Units", Units(ActiveTarget(),
                                               selection_type=M.IOV_UNIT_SELECTION)),
                               ("AreEnemies", AreEnemies(
                                   Owner(),
                                   Units(ActiveTarget(), selection_type=M.IOV_UNIT_SELECTION),
                                   selection_type=M.IOV_TEAM_SELECTION))):
                try:
                    v = noeud.evaluate(sub)
                except Exception as exc:
                    v = "ERREUR %s" % exc
                row[nom] = (len(v) if isinstance(v, list) else v)
            out[tid] = row
    return out


def _types_events(act: dict) -> dict:
    """`{type: n}` -- la VENTILATION des events natifs du pas. Un `_coups_natifs` VIDE ne dit pas
    si le natif n'a pas frappe ou si ce lecteur-la ne sait pas lire ses events : ce compte-ci
    tranche."""
    out = {}
    for a in (act.get("actions") or []):
        for e in (a.get("events") or []):
            k = str(e.get("type") or e.get("name") or e.get("eventType") or "?")
            out[k] = out.get(k, 0) + 1
    return out


def _lignes_port(state, board) -> dict:
    """Les DEUX lignes que la phase 2 relit, resolues DEPUIS les cles persistantes -- l'etage
    juste au-dessus du degat. Sans lui, un ecart de degat ne dit pas s'il vient des TUILES ou du
    coup."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.operations.triggers.loki import instruments_of_vengeance_attack as M
    from engine.entities.selectors.tiles import TileUnion
    from engine.entities.selectors.geometry import TilesBehindInLine
    out = {}
    for i in (0, 1):
        edge = M._persistent_tile(M.IOV_KEY_TARGET_TILE, i)
        direction = M._persistent_tile(M.IOV_KEY_DIRECTION_TILE, i)
        sel = TileUnion(edge, TilesBehindInLine(edge, direction))
        for uid in list(state.entities):
            ents = entities_from_state(state, int(uid), int(uid), actor_id=int(uid))
            ectx = ExecutionContext(state=state, rng=state.rng)
            try:
                tuiles = [int(t) for t in sel.evaluate(ents)]
            except Exception as exc:                       # pragma: no cover
                tuiles = ["ERREUR: %s" % exc]
            out["ligne_%d" % i] = tuiles
            # LES COORDONNEES, pas seulement les ids : c'est ce qui permet de REPLACER une cible
            # SUR la ligne au run suivant (le montage n'est confrontable que si un occupant y est).
            out["ligne_%d_pos" % i] = [
                (lambda c: None if c is None else (int(c["col"]), int(c["row"])))(
                    board.by_id.get(int(t)) if isinstance(t, int) else None)
                for t in tuiles]
            break
    return out


# ---------------------------------------------------------------- LA FIXTURE, nommee et reutilisable

#: Le roster ADVERSE par defaut. ⚠ Plus qu'un decor : les deux lignes de la phase 2 traversent le
#: plateau de bord a bord, et le coup differe n'est OBSERVABLE que si un ennemi se tient DESSUS. Un
#: duel a deux ennemis colles au Lion ne discrimine RIEN -- mesure du 2026-08-17, `port emis` sans
#: aucun `AttackWithAttackDamage` et `dhp` explique en entier par les summons.
#: ⚠ `ultraEliminator` A QUITTE LE POOL du rank 17 -- le build echoue desormais dessus
#: (`--a-units: hors pool / non spawnables au rank 17`). Remplace par `ultraEliminatorSgt`, qui y
#: est. C'est un CHANGEMENT DE MONTAGE, et il faut le dire : les mesures de #889-r11 (seed 31337,
#: tuiles de spawn divergentes) ont ete prises avec l'ANCIEN roster et ne sont plus reproductibles
#: telles quelles -- le 5e adversaire change la consommation de PRNG et le contenu
#: d'`UnitsDamagedThisPhase`, qui sont deux des trois causes candidates.
A_UNITS = "custoVexilusPraetor,orksBigMek,orksNob,tauCrisis,ultraEliminatorSgt"


def monter_scenario(sid: int, *, seed: str = "777", board: str = BOARD,
                    hp_target: str | None = "400000", tag: str = "x",
                    a_units: str = A_UNITS, a_place: list | None = None):
    """Monte le duel du Lion sur SA carte.

    `hp_target` gonfle les PV de la cible : sans lui les coups de la phase 1 puis de la phase 2
    tuent, et les deltas des DEUX phases se confondent en un seul kill non comparable.

    `a_place` = les placements ADVERSES, `["<unitId>:<col>,<row>", ...]`. Le montage se joue en DEUX
    passes : une de RECONNAISSANCE qui lit les deux lignes (`--reco`), puis une seconde ou les
    ennemis sont poses DESSUS. C'est le << DEPLACE les unites pour forcer la configuration >> de la
    doctrine, et non un montage bloque par la geometrie de spawn."""
    state_path = LOGS / ("probe_889r7_%s.json" % tag)
    args = ["--seed", seed, "--board", board,
            "--explicit-stats", BOSS, "--p-units", BOSS,
            "--a-units", a_units,
            "--place", "%s:3,3" % BOSS]
    for p in (a_place or ["custoVexilusPraetor:3,4", "orksBigMek:2,2"]):
        args += ["--a-place", p]
    if hp_target:
        args += ["--hp-target", str(hp_target)]
    rid = build(state_path, args)

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 30)   # MES runners, jamais ceux des autres

    return rid, dispose


def _forme_selecteur(sel, profondeur: int = 4) -> str:
    """La CHAINE de classes d'un selecteur, en descendant `source`/`inner`/`a`. C'est ce qui NOMME
    un vivier sans avoir a le reconnaitre a son contenu (le contenu, lui, est ce qu'on mesure)."""
    noms, cur = [], sel
    for _ in range(profondeur):
        if cur is None:
            break
        noms.append(type(cur).__name__)
        cur = next((getattr(cur, a) for a in ("source", "inner", "a", "sel", "src")
                    if getattr(cur, a, None) is not None), None)
    return "/".join(noms)


def _etages_selecteur(G, sel, ctx, profondeur: int = 4) -> dict:
    """Chaque ETAGE d'un vivier, evalue SEPAREMENT -- `UnitsDamagedThisPhase` d'abord, puis
    `AdjacentTiles`, puis `CanAddUnit`. C'est ce qui separe la cause (ii) de la cause (iii) : un
    ecart deja present au premier etage n'a rien a voir avec le `HasAdjacentEnemies` du dernier.

    ⚠ ON N'EVALUE JAMAIS UN ETAGE ALEATOIRE : un `Randomize`/`PickRandomly` intermediaire
    consommerait du PRNG et la mesure changerait ce qu'elle mesure. On l'ARRETE et on le DIT."""
    out, cur = {}, sel
    for _ in range(profondeur):
        if cur is None:
            break
        nom = type(cur).__name__
        if isinstance(cur, G.PickRandomly):
            out[nom] = "NON EVALUE (aleatoire -- l'evaluer consommerait du PRNG)"
            break
        try:
            # ⚠ UN ETAGE NE REND PAS TOUJOURS DES IDS DE TUILE : `UnitsDamagedThisPhase` et `Owner`
            # rendent des UNITES (des `LiveUnit`), pas des entiers. On les rend par leur `id`
            # plutot que de laisser la conversion lever -- une ERREUR a cet etage masquerait
            # exactement l'information que la cause (ii) demande (QUELLES unites ont ete blessees).
            vals = []
            for x in G._units_of(cur, ctx):
                vals.append(int(x) if isinstance(x, int)
                            else int(x.get("id")) if isinstance(x, dict) and x.get("id") is not None
                            else int(getattr(x, "id", None) or -1))
            out[nom] = sorted(vals)
        except Exception as exc:                  # une lecture de diagnostic ne casse pas la mesure
            out[nom] = "ERREUR: %s" % (exc,)
        cur = next((getattr(cur, a) for a in ("source", "inner", "a", "sel", "src")
                    if getattr(cur, a, None) is not None), None)
    return out


class _TraceViviers:
    """#889-r11 -- LE MONTAGE QUI TRANCHE : comparer les tuiles de CHAQUE VIVIER separement,
    AVANT l'union `(t2 + t1) + t3` et AVANT le `First(..., nrOfSummons)`.

    Le cardinal des summons accorde TOUJOURS (4/4) ; c'est la POSITION qui diverge, et seulement sur
    une seed. Trois causes etaient NON DEPARTAGEES : (i) la consommation de PRNG des trois
    `Randomize` ; (ii) le contenu d'`UnitsDamagedThisPhase` (le coup differe qui PRECEDE ne blesse
    pas forcement dans le meme ordre des deux cotes) ; (iii) le vivier `t3` et son
    `HasAdjacentEnemies`. Un releve pris sur l'UNION ne peut pas les separer -- une tuile presente
    dans l'union ne dit pas DE QUEL vivier elle vient, ni si l'ecart tient au contenu ou a l'ordre.

    On enregistre donc, par appel de `Randomize.select` : la FORME du selecteur source (qui NOMME le
    vivier), le pool AVANT melange, et la permutation APRES. Le comportement n'est pas modifie --
    on appelle le `select` d'origine, donc la consommation PRNG est INCHANGEE (une mesure qui
    perturberait le tirage mesurerait autre chose que ce qui se joue)."""

    def __init__(self):
        self.appels: list = []

    def __enter__(self):
        from engine.entities.selectors import geometry as G
        self._G = G
        self._orig = G.Randomize.__dict__.get("select")     # None -> herite de `PickRandomly`
        trace = self

        def select(self_sel, ctx):
            avant = list(G._units_of(self_sel.source, ctx))
            etages = _etages_selecteur(G, self_sel.source, ctx)
            apres = G.PickRandomly.select(self_sel, ctx)
            trace.appels.append({"vivier": _forme_selecteur(self_sel.source),
                                 "avant": [int(x) for x in avant],
                                 "apres": [int(x) for x in (apres or [])],
                                 "etages": etages})
            return apres

        G.Randomize.select = select
        return self

    def __exit__(self, *exc):
        if self._orig is None:
            del self._G.Randomize.select
        else:
            self._G.Randomize.select = self._orig
        return False


def _tid(board, pos):
    """`(col, row)` -> id de tuile. `None` quand la position n'est pas sur le plateau : on rend le
    tri-etat plutot qu'un 0 (une tuile inconnue n'est PAS la tuile 0)."""
    if not pos or pos[0] is None or pos[1] is None:
        return None
    return board.id_at(int(pos[0]), int(pos[1]))


def _classer_par_vivier(tuiles, appels) -> dict:
    """Pour chaque tuile CHOISIE (natif ou port), DE QUEL vivier elle vient -- l'appartenance est
    prise sur le pool AVANT melange, donc elle est INDEPENDANTE de l'ordre.

    Une tuile qui n'appartient a AUCUN vivier du port sort en `HORS_VIVIERS` : c'est le verdict le
    plus fort possible, il exclut la cause (i) et accuse le CONTENU (ii ou iii)."""
    out = {}
    for t in tuiles:
        dedans = [a["vivier"] for a in appels if int(t) in a["avant"]]
        out[int(t)] = dedans or ["HORS_VIVIERS"]
    return out


def _mesure(sid: int, rid: int) -> dict:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers

    bind(sid)
    state, dec0 = load(sid, rid)
    caster = next((u for u in (dec0.get("units") or [])
                   if "DarkaLion" in str(u.get("visualId") or "")), None)
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : le Lion est absent du decisionView")
    caster_id = int(caster["id"])
    mon_joueur = dec0.get("currentPlayer")

    # ---- [A] LE CAST, des DEUX cotes (premisse, pas observable) ----------------------------
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})
    diag_cast = ABILITY_CLASSES[IOV]().execute_behaviour(state, caster_id, caster_id) or {}
    act = rpc(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": IOV,
        "targetId": caster_id}}, 120) or {}
    cast_error = (act.get("actions") or [{}])[0].get("error")
    dec1 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tours = {"apres_cast": dec1.get("currentPlayer")}

    marques_apres_cast = marques_off(state)
    hp_l0, hp_o0 = hp_live(sid, rid), hp_off(state)
    unites_l0, unites_o0 = unites_live(sid, rid), unites_off(state)
    # LES DEUX LIGNES, resolues AVANT la phase 2 (apres, le `ClearAllPersistentData` les a vidées).
    from engine.entities.pathfinding.board import Board
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    lignes = _lignes_port(state, board)
    occupants = {}
    for u in (dec1.get("units") or []):
        p = u.get("pos") or {}
        occupants[int(u["id"])] = (u.get("visualId"), p.get("col"), p.get("row"),
                                   u.get("team"), u.get("owner"))
    # LE GATE, TUILE PAR TUILE. Un `AttackWithAttackDamage` absent du flux d'emissions ne dit pas
    # LEQUEL des deux predicats a refuse : ce releve-ci le dit, et il est pris sur les MEMES
    # entites que celles du `Foreach`.
    gate = _gate_par_tuile(state, caster_id, lignes)

    # ---- [B]/[C] LA BASCULE : le natif rouvre le tour du Lion -------------------------------
    # ⚠ Le RNG se re-seede AVANT la bascule (#889-r4) : sinon le port tire ses rolls depuis un etat
    # que le natif a deja consomme et les deux montants ne sont plus comparables.
    seed_offline_rng(state, rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {})
    act2 = rpc(sid, "applyAction",
               {"runnerId": rid, "captureEvents": True, "action": {"kind": "endturn"}}, 120) or {}
    dec2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    tours["apres_endturn_1"] = dec2.get("currentPlayer")
    # Le port joue la MEME bascule, pour le MEME joueur que celui a qui le natif vient de donner la
    # main -- lu APRES la bascule, jamais devine d'apres le nom du pas.
    # #889-r11 -- LE MONTAGE QUI TRANCHE : on enregistre CHAQUE vivier separement pendant que la
    # phase 2 s'execute. Cf. `_TraceViviers` : pool AVANT melange, permutation APRES, etages.
    with _TraceViviers() as trace:
        off_phase2 = delayed_attack_triggers(state, dec2.get("currentPlayer"))
    viviers = trace.appels

    hp_l1, hp_o1 = hp_live(sid, rid), hp_off(state)
    unites_l1, unites_o1 = unites_live(sid, rid), unites_off(state)

    spawn_pos_natif = sorted(
        (int(c["squadId"]), (int((c.get("to") or {}).get("col")),
                             int((c.get("to") or {}).get("row"))))
        for a in (act2.get("actions") or []) for c in (a.get("changes") or [])
        if c.get("appeared") and (c.get("to") or {}).get("col") is not None)
    spawn_pos_port = sorted(_pos_off(state, int(e)) for e in (unites_o1 - unites_o0))

    return {
        "rid": rid, "caster": caster_id, "mon_joueur": mon_joueur, "tours": tours,
        "cast_error": cast_error,
        "cast_port": {k: diag_cast.get(k) for k in ("marked", "armed", "activated", "persisted")},
        "marques_apres_cast": marques_apres_cast,
        "off_phase2": off_phase2,
        "lignes_port": lignes,
        "occupants": occupants,
        "gate_par_tuile": gate,
        "coups_natifs_phase2": _coups_natifs(act2),
        # DUMP BRUT : un `{}` de `_coups_natifs` peut vouloir dire « le natif n'a pas frappe » OU
        # « ce lecteur ne sait pas lire ces events ». On imprime donc la VENTILATION des types.
        "events_natifs_types": _types_events(act2),
        # Les CLES brutes de la reponse : un `{}` de `_types_events` peut aussi vouloir dire que
        # `captureEvents` ne remonte rien sur un `endturn`. On imprime la FORME, pas un zero.
        "act2_cles": sorted((act2 or {}).keys()),
        "act2_actions_cles": sorted({k for a in (act2.get("actions") or []) for k in a}),
        "act2_brut": json.dumps(act2, default=str)[:4000],
        "emis_port": sorted({n for r in (off_phase2 or [])
                             for f in ((r or {}).get("fired") or [])
                             for res in (f.get("results") or []) if isinstance(res, dict)
                             for n in (res.get("emis") or [])}),
        "dhp_natif": _dhp(hp_l0, hp_l1),
        "dhp_port": _dhp(hp_o0, hp_o1),
        "spawn_natif": {str(k): v for k, v in unites_l1.items() if k not in unites_l0},
        "spawn_port": sorted(unites_o1 - unites_o0),
        # LES TUILES de spawn, des DEUX cotes. C'est l'etage qui separe « le coup differe diverge »
        # de « les SUMMONS ne sont pas nes au meme endroit, donc ils n'ont pas frappe pareil » --
        # les deux se presentent comme un simple ecart de PV.
        "spawn_pos_natif": spawn_pos_natif,
        "spawn_pos_port": spawn_pos_port,
        "marques_apres_phase2": marques_off(state),
        "events_bascule": len(act2.get("actions") or []),
        # #889-r11 -- LES TROIS VIVIERS, SEPARES. `viviers` = un enregistrement par `Randomize`
        # (forme du selecteur, pool AVANT melange, permutation APRES, etages). `classement_*` dit
        # de QUEL vivier vient chaque tuile effectivement occupee -- natif et port -- ce qui separe
        # « le contenu du vivier differe » (causes ii/iii) de « seul l'ordre differe » (cause i).
        "viviers": viviers,
        "classement_natif": _classer_par_vivier(
            [t for t in (_tid(board, p) for _sq, p in spawn_pos_natif) if t is not None], viviers),
        "classement_port": _classer_par_vivier(
            [t for t in (_tid(board, p) for _e, p in spawn_pos_port) if t is not None], viviers),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--hp-target", default="400000")
    ap.add_argument("--tag", default=str(os.getpid()))
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--a-place", action="append", default=None,
                    help="placement adverse `<unitId>:<col>,<row>` (repetable). Passe DEUX FOIS : "
                         "une passe de reconnaissance lit les lignes, la seconde y pose les cibles.")
    a = ap.parse_args()

    sid = _session()
    rid, dispose = monter_scenario(sid, seed=a.seed, board=a.board,
                                   hp_target=a.hp_target, tag=a.tag,
                                   a_units=a.a_units, a_place=a.a_place)
    try:
        m = _mesure(sid, rid)
    finally:
        dispose()

    print("[889r7] runner=%s caster=%s err=%s" % (m["rid"], m["caster"], m["cast_error"]))
    print("[889r7] currentPlayer par pas : %s (mon_joueur=%s)" % (m["tours"], m["mon_joueur"]))
    if m["tours"].get("apres_cast") == m["mon_joueur"]:
        print("        -> ATTENTION : le cast n'a PAS bascule le tour. Un seul endturn ne suffit "
              "alors pas a rouvrir le tour du Lion : la phase 2 n'est PAS exercee.")
    print("[889r7] [A] cast port : marked=%s armed=%s activated=%s persisted=%s"
          % (len(m["cast_port"].get("marked") or []), len(m["cast_port"].get("armed") or []),
             len(m["cast_port"].get("activated") or []),
             [p.get("key") for p in (m["cast_port"].get("persisted") or [])]))
    for i in (0, 1):
        print("[889r7] ligne_%d ids=%s" % (i, m["lignes_port"].get("ligne_%d" % i)))
        print("[889r7] ligne_%d pos=%s" % (i, m["lignes_port"].get("ligne_%d_pos" % i)))
    print("[889r7] OCCUPANTS (id -> visualId, col, row, team, owner) :")
    for uid, o in sorted(m["occupants"].items()):
        print("        u%-4s %s" % (uid, o))
    print("[889r7] GATE par tuile (HasUnit / Units / AreEnemies) :")
    for tid, g in sorted(m["gate_par_tuile"].items(), key=lambda kv: int(kv[0])):
        print("        t%-4s %s" % (tid, g))
    print("[889r7] [B] COUP DIFFERE")
    print("        natif dhp   = %s" % json.dumps(m["dhp_natif"], sort_keys=True))
    print("        natif coups = %s" % json.dumps(m["coups_natifs_phase2"], sort_keys=True))
    print("        natif events= %s" % json.dumps(m["events_natifs_types"], sort_keys=True))
    print("        port  dhp   = %s" % json.dumps(m["dhp_port"], sort_keys=True))
    print("        port  emis  = %s" % m["emis_port"])
    print("        port  phase2 = %s" % json.dumps(m["off_phase2"], default=str)[:1200])
    print("[889r7] [C] SPAWN")
    print("        natif = %s" % json.dumps(m["spawn_natif"], sort_keys=True))
    print("        port  = %s" % m["spawn_port"])
    print("        tuiles natif = %s" % m["spawn_pos_natif"])
    print("        tuiles port  = %s" % m["spawn_pos_port"])
    # #889-r11 -- LES VIVIERS, AVANT L'UNION ET AVANT LE `First`. C'est le releve qui separe les
    # trois causes NON DEPARTAGEES ; un releve pris sur l'union ne le peut pas.
    print("[889r7] [C] VIVIERS (chaque `Randomize`, dans l'ordre d'evaluation) :")
    for i, viv in enumerate(m.get("viviers") or []):
        print("        v%d %s | AVANT(%d)=%s" % (i, viv["vivier"], len(viv["avant"]), viv["avant"]))
        print("           APRES(%d)=%s" % (len(viv["apres"]), viv["apres"]))
        for nom, val in (viv.get("etages") or {}).items():
            print("           etage %-24s = %s" % (nom, val))
    if not (m.get("viviers") or []):
        print("        AUCUN `Randomize` INTERCEPTE -- le releve est MUET, il ne prouve rien "
              "(la phase 2 n'a pas atteint le volet SPAWN, ou le traceur n'a pas mordu).")
    print("        classement natif (tuile -> viviers du PORT) = %s" % m.get("classement_natif"))
    print("        classement port  (tuile -> viviers du PORT) = %s" % m.get("classement_port"))
    _hors = sorted(t for t, v in (m.get("classement_natif") or {}).items() if v == ["HORS_VIVIERS"])
    if _hors:
        print("        -> %d tuile(s) NATIVE(s) HORS de tout vivier du port : %s. La cause n'est "
              "donc PAS l'ordre des tirages (i) mais le CONTENU d'un vivier (ii/iii)." % (len(_hors), _hors))
    print("[889r7] MARQUES 1518 (port) : apres cast = %d cles, apres phase 2 = %d cles"
          % (sum(1 for v in m["marques_apres_cast"].values() if IOV_LOCATION_TARGET in v),
             sum(1 for v in m["marques_apres_phase2"].values() if IOV_LOCATION_TARGET in v)))

    out = LOGS / ("probe_889r7_instruments_phase2_%s.json" % a.tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")
    print("[889r7] -> %s" % out)

    # ------------------------------------------------------------------ VERDICT, pas une lecture
    ok = True
    # NON-DEGENERESCENCE d'abord : un accord sur `{}` contre `{}` ne prouve RIEN.
    frappes = [n for n, _ in [(1, 1)] if m["dhp_natif"]]
    if not m["dhp_natif"]:
        print("[889r7] REGIME DEGENERE : le natif n'a inflige AUCUN degat -- aucune tuile des deux "
              "lignes ne portait d'ennemi. Replacer une cible SUR une ligne (cf. `ligne_i pos`).")
        ok = False
    elif m["dhp_natif"] != m["dhp_port"]:
        # ⚠ **UN VERDICT DOIT DIRE A QUOI IL S'APPLIQUE.** Le `dhp` de ce pas AGREGE le coup differe
        # ET les attaques des summons (`PerformAIAttackFromCurrentPosition`, on-appearance). Si les
        # TUILES de spawn different, les summons n'ont pas frappe depuis les memes cases et le
        # `dhp` n'est tout simplement PAS comparable -- accuser le coup differe serait accuser le
        # mauvais etage. MESURE (2026-08-17) : seed 777, tuiles IDENTIQUES -> accord BIT-EXACT ;
        # seed 31337, tuiles differentes (natif [(3,5),(4,4),(3,2),(2,1)] / port
        # [(2,3),(1,2),(4,4),(2,1)]) -> ecart de 984 PV sur ~36 000. Residu `#889-r11`.
        memes_tuiles = ([p for _, p in (m["spawn_pos_natif"] or [])]
                        == [p for _, p in (m["spawn_pos_port"] or [])])
        if not memes_tuiles:
            print("[889r7] [B] NON COMPARABLE : les TUILES DE SPAWN different, donc le `dhp` de ce "
                  "pas melange deux etages. natif=%s port=%s"
                  % (m["spawn_pos_natif"], m["spawn_pos_port"]))
            print("        (l'ecart de PV %s / %s N'ACCUSE PAS le coup differe -- residu #889-r11)"
                  % (json.dumps(m["dhp_natif"], sort_keys=True),
                     json.dumps(m["dhp_port"], sort_keys=True)))
        else:
            print("[889r7] [B] ECART REEL (memes tuiles de spawn) : natif %s != port %s"
                  % (json.dumps(m["dhp_natif"], sort_keys=True),
                     json.dumps(m["dhp_port"], sort_keys=True)))
        ok = False
    else:
        print("[889r7] [B] ACCORD BIT-EXACT sur le delta de PV : %s"
              % json.dumps(m["dhp_natif"], sort_keys=True))
    if "AttackWithAttackDamage" not in (m["emis_port"] or []):
        print("[889r7] [B] LE PORT N'A EMIS AUCUN `AttackWithAttackDamage` -- l'accord de PV "
              "ci-dessus viendrait alors des SUMMONS seuls, pas du coup differe.")
        ok = False
    n_nat, n_port = len(m["spawn_natif"] or {}), len(m["spawn_port"] or [])
    print("[889r7] [C] SPAWN : natif %d / port %d -> %s"
          % (n_nat, n_port, "ACCORD" if n_nat == n_port else "ECART"))
    ok = ok and (n_nat == n_port) and n_nat > 0
    restantes = sum(1 for v in m["marques_apres_phase2"].values() if IOV_LOCATION_TARGET in v)
    posees = sum(1 for v in m["marques_apres_cast"].values() if IOV_LOCATION_TARGET in v)
    print("[889r7] MARQUES 1518 : %d posees -> %d restantes -> %s"
          % (posees, restantes, "CONSOMMEES" if (posees > 0 and restantes == 0) else "ECART"))
    ok = ok and posees > 0 and restantes == 0
    print("[889r7] VERDICT : %s" % ("OK" if ok else "KO"))
    _ = frappes
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
