"""probe_503 -- MESURE de `1141 OverwhelmingWrath` (`worldEightbound` Azkor, WorldEaters, HERO).

QUESTION BINAIRE, posee AVANT la methode : **le CAST de 1141 inflige-t-il des degats ?**
L'audit `combat-ability-coverage` le classe `DAMAGE(Eviscerate)` (le kit porte bien
`minDmg`/`maxDmg`/`damageProfile=Eviscerate`/`nrOfHits=2`) et son profil annonce QUATRE mecaniques
(`dmg_bonus`, `dmg_reduction`, `crit`, `block`). Le decompile dit non :
`IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour` ne porte
AUCUN noeud d'attaque -- il pose TROIS effets et les compose par
`IdunBattle.DSL.AbilityBehaviour$$op_Addition` :

      AddEffect(     0x515 = 1301 OverwhelmingWrath_RangeDmgReduction, AbilityStateReference,
                     source = Caster@0x48, targets = Caster@0x48, TurnsFromRounds(1) )
    + AddBondEffect( 0x1b  = 27 Taunted_OnlySpecificTargets, AbilityStateReference,
                     source = Caster@0x48,
                     targets = NormalUnits(AdjacentEnemies(Owner@0x30, 1, 3), 3),
                     bondedEntity = Caster@0x48, TurnsFromRounds(1) )
    + AddBondEffect( 0x514 = 1300 OverwhelmingWrath_PendingAttack, AbilityStateReference,
                     source = Caster@0x48, targets = Caster@0x48,
                     bondedEntity = Caster@0x48, options = <Nullable ZERO> )

Le `2x Eviscerate` du kit appartient a la PHASE 2 --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.OverwhelmingWrath_AttackAbility$$CreateBehaviour`
(`TriggeredAbilityType.OverwhelmingWrath_Attack` = 0x4d5 = 1237, rendu par
`IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_PendingAttackEffect$$GetTriggeredAbilityType`),
NON portee (residu #503-r1). Meme patron 2-phases que `HeavyRailRifle` (1160) et
`SeekerMissileFrequencyLock` (1069).

⚠ COLLISION D'ORDINAUX A CE SITE, et elle est PIEGEUSE : `1237` est ici un `TriggeredAbilityType`
(`OverwhelmingWrath_Attack`) ET un `EffectType` (`Taunted_RefreshUnitTurnFinished`, l'un des trois
sous-effets que `TauntedEffect$$ApplyInternal` spawne). Les deux apparaissent dans CETTE mesure.

ETAGES MESURES (jamais un scalaire fitte -- chaque etage a son oracle natif) :
  [1] EXECUTION portee     : `diag.ported is True` (sans quoi le cast est un NO-OP SILENCIEUX)
  [2] empreinte d'effets   : port == natif, `{unite -> {effectType: remaining}}`
  [3] PORTEURS et BONDS    : 1301 + 1300 sur le CASTER (1300 bonde au caster) ; 27 sur CHAQUE ennemi
                             ADJACENT, bonde au CASTER ; l'ennemi NON adjacent reste INTACT
  [4] AUCUN DEGAT + AUCUN TIRAGE : HP inchanges des DEUX cotes ET `dumpRng.callCount` inchange.
                             C'est ce qui SEPARE les trois autres mecaniques du kit (`crit`,
                             `block`, `dmg_bonus`) : sans coup porte et sans tirage consomme, elles
                             sont STRUCTURELLEMENT hors de ce behaviour -- resultat, pas hypothese.
  [5] CONSEQUENCE de 1301  : la prediction NATIVE d'une attaque RANGED ennemie sur le caster passe a
                             x(100 - dmgReductionPct)/100. C'est ce qui distingue « effet pose » de
                             « effet pose ET vivant ».
  [6] CONSEQUENCE du TAUNT : les ennemis adjacents ne peuvent plus viser que le caster
                             (`UnitExtensions$$GetOnlyTargets` -> regle `TargetIsAllowedForCaster`).
  [7] GATE DE CIBLAGE      : `TargetIsEnemy` + `isSelfCasting` + `RANGE_ADJACENT`, port vs natif sur
                             CINQ cibles (soi / allie / 2 ennemis adjacents / ennemi a distance 2).

Le placement est FORCE (`--place`/`--a-place`) : il faut DEUX ennemis adjacents (pour le taunt) ET
un ennemi RANGED hors adjacence (pour l'etage [5]), ce que la geometrie de spawn ne garantit pas.
« Bloque par la geometrie » n'est pas un resultat.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_503_overwhelming_wrath.py
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

OVERWHELMING_WRATH = 1141      # ActiveAbilityType.OverwhelmingWrath
TAUNTED = 27                   # EffectType.Taunted_OnlySpecificTargets  (0x1b)
TAUNTED_BLOCK_MOVEMENT = 25    # EffectType.Taunted_BlockMovement        (0x19, sous-effet)
TAUNTED_CANT_USE_ABILITY = 26  # EffectType.Taunted_CantUseAbility       (0x1a, sous-effet)
TAUNTED_REFRESH = 1237         # EffectType.Taunted_RefreshUnitTurnFinished (0x4d5, sous-effet)
OW_PENDING_ATTACK = 1300       # EffectType.OverwhelmingWrath_PendingAttack       (0x514)
OW_RANGE_DMG_REDUCTION = 1301  # EffectType.OverwhelmingWrath_RangeDmgReduction   (0x515)
BOARD = "MC1_67"

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12 / #486-r15).
#: PERIMETRE LARGE, et c'est une MESURE : la fermeture d'import d'un probe d'ability atteint la
#: quasi-totalite de `scripts/python` (~139 modules). Declarer etroit produirait un FAUX VERT.
#: ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py` ne
#: voit PAS `scripts/python/board.py`.
DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le port de 1141 au NATIF via un runner live : il depend du code du "
              "port (arbre DSL + primitives AddEffect/AddBondEffect + le selecteur NormalUnits + "
              "TauntedEffect + OverwhelmingWrathRangeDmgReductionEffect + le registre + le masque "
              "de ciblage) ET du build charge -- l'oracle etant le jeu lui-meme, pas une constante "
              "ecrite ici.",
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
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def footprint_live(dec) -> dict:
    out = {}
    for u in (dec.get("units") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(u["id"])] = effs
    return out


def footprint_off(state) -> dict:
    """MEME empreinte cote port (`remaining_turns is None` == le `remaining 0` live = permanent)."""
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed}
        if cur:
            out[int(key)] = cur
    return out


def delta(before: dict, after: dict) -> dict:
    out = {}
    for k, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(k) or {})}
        if new:
            out[int(k)] = new
    return out


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def find(dec, visual_id):
    return next((u for u in (dec.get("units") or []) if u.get("visualId") == visual_id), None)


def rng_dump(sid, rid):
    """Etat COMPLET du MT19937 de combat (`{mt:[624], mti, callCount}`). Un CAST qui ne tire RIEN le
    laisse strictement egal -- c'est le canal qui separe « pas de degat observe » de « pas de degat
    POSSIBLE » (un crit ou un block CONSOMMENT un tirage, cf.
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`)."""
    return rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {}


def rng_key(d):
    """La cle de comparaison : `(callCount, mti, hash de l'etat interne)`. On ne compare PAS que
    `callCount` -- un tirage suivi d'un re-seed le laisserait egal."""
    mt = tuple(d.get("mt") or ())
    return (d.get("callCount"), d.get("mti"), hash(mt))


def seed_offline_rng(state, dump):
    """CALE le MT offline sur le MT LIVE (`dumpRng`), comme l'exige tout replay qui touche au canal
    de degat : sans ce calage `state.rng is None`, et `damage_ops` SKIP le degat par repli
    defensif -- on lirait un `0` FAUX au lieu d'un `0` MESURE."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


#: L'attaque NORMALE de chaque unite du montage (`decisionView.units[].abilities[kind=="normal"]`)
#: -- l'ability par laquelle on interroge le gate de ciblage d'un ENNEMI (le taunt).
NORMAL_ATTACK = 69             # ActiveAbilityType.Loki_NormalAttack


def _target_is_allowed_for_caster() -> int:
    """`TargetingRule` bit 23 -- le code que rend la cascade native quand le TAUNT
    (`UnitExtensions$$GetOnlyTargets`) refuse une cible. Pris au MEMBRE du mirror GENERE, jamais au
    litteral (`0x800000`) : un ordinal juste aujourd'hui devient faux au changement de build, en
    silence, et le cliquet `test_ability_registry_ratchet` interdit de le re-declarer ici."""
    from engine.runner.abilities.targeting_rule import TargetingRule
    return int(TargetingRule.TargetIsAllowedForCaster)


TARGET_IS_ALLOWED_FOR_CASTER = _target_is_allowed_for_caster()


def reason_live(sid, rid, caster, target, ability=NORMAL_ATTACK):
    """`abilityReason` = la raison STRUCTUREE d'un cast invalide, cote NATIF. Elle fonctionne pour
    N'IMPORTE QUEL caster (y compris une unite ennemie), contrairement a `abilityTargets` qui
    n'enumere que les unites du joueur, et a `pathDistToEnemies` qui prend son `unitId` du cote
    JOUEUR (mesure : `pathDistToEnemies(u81)` d'une unite de la team 2 rend les autres unites de la
    team 2 -- ce n'est PAS l'ensemble de cibles de u81)."""
    r = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": int(caster),
                                   "abilityType": int(ability), "targetId": int(target)}, 60) or {}
    return int((r.get("targetReason") or {}).get("hex", "0x0"), 16)


def reason_off(state, caster, target):
    """Le MEME gate cote port, pour l'attaque NORMALE : `_NormalAttackTargeting` porte le masque du
    TYPE d'attaque normale du caster (`normal_attack_targeting_options`), et la cascade
    `get_invalid_target_reason` y applique `TargetIsAllowedForCaster` (bit 23, le TAUNT)."""
    from engine.runner.abilities.targeting import (_NormalAttackTargeting,
                                                   get_invalid_target_reason,
                                                   normal_attack_targeting_options)
    porteur = _NormalAttackTargeting(normal_attack_targeting_options(state, int(caster)))
    return get_invalid_target_reason(state, int(caster), int(target), porteur)


def only_targets_off(state, unit_id):
    """`IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` cote port -- le foyer UNIQUE que lit la
    regle `TargetIsAllowedForCaster`. Liste VIDE = aucune restriction."""
    from engine.runner.abilities.targeting import get_only_targets
    return sorted(int(x) for x in (get_only_targets(state, int(unit_id)) or []))


def predict(sid, rid, attacker, target):
    """`aiPredict` = le PREVIEW natif de degat (`GetAllPredictions`), attack-based -- exactement le
    chemin qui traverse `IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$
    CreateDamageDefenseModifier` quand la CIBLE porte l'effet. Rend `(healthDmgMin, healthDmgMax)`
    ou None (shape REELLE : les bornes vivent dans `pred`, pas a la racine)."""
    r = rpc(sid, "aiPredict", {"runnerId": rid, "unitId": int(attacker),
                               "targetId": int(target), "fresh": True}, 60) or {}
    pred = r.get("pred") or {}
    lo, hi = pred.get("healthDmgMin"), pred.get("healthDmgMax")
    return (int(lo), int(hi)) if (lo is not None and hi is not None) else None


def bonds_from_cascade(act: dict) -> dict:
    """`{effectType -> [{'on': porteur, 'bonded': BondEffect_BondedId, ...}]}` lu dans la CASCADE du
    cast NATIF -- le SEUL canal qui publie le BOND (`decisionView.effects` ne porte que
    `effectType`/`remaining`).

    Format REEL : `act.events` est une liste PLATE de `{kind, entity, group?, source?, tags?}` ou
    `tags` est une CHAINE JSON. `kind == "group"` : `entity` = l'ID D'INSTANCE de l'effet, `source` =
    son NOM ; `kind == "action"` : `entity` = le PORTEUR, `tags.Effect_Id` = ce meme id d'INSTANCE.
    `Effect_Id` est donc un id D'INSTANCE, PAS un `EffectType` -> on resout instance -> NOM (canal
    `group.source`) puis NOM -> `EffectType` par le mirror (« la conversion se fait PAR NOM »).

    ⚠ LISTE par effectType (et non un dict plat comme dans probe_491) : 27 est pose sur PLUSIEURS
    porteurs a la fois."""
    from engine.entities.effect_type import EffectType
    nom_par_instance, out = {}, {}
    for ev in (act.get("events") or []):
        if not isinstance(ev, dict):
            continue
        if ev.get("kind") == "group" and ev.get("source"):
            nom_par_instance[ev.get("entity")] = str(ev.get("source"))
    for ev in (act.get("events") or []):
        if not isinstance(ev, dict) or ev.get("kind") != "action":
            continue
        raw = ev.get("tags")
        try:
            tags = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            continue
        nom = nom_par_instance.get(tags.get("Effect_Id"))
        if nom is None or "Effect_SourceId" not in tags:      # l'evenement PORTEUR de l'effet
            continue
        etype = getattr(EffectType, nom, None)
        if etype is None:
            continue
        out.setdefault(int(etype), []).append(
            {"on": ev.get("entity"), "bonded": tags.get("BondEffect_BondedId"),
             "source": tags.get("Effect_SourceId")})
    return out


def measure(sid: int, seed: str = "777", board: str = BOARD,
            state_name: str = "probe_503_overwhelming_wrath"):
    """Monte le scenario, joue le cast des DEUX cotes, rend `(mesures, dispose)`.

    Le TEST de garde (`tests/engine/runner/test_overwhelming_wrath_live.py`) appelle CETTE
    fonction : une seule implementation du montage et des lectures, donc aucune divergence possible
    entre ce qui est MESURE ici et ce qui est GARDE la-bas."""
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", "worldEightbound,worldExecutions",
        "--a-units", "orksNob,orksRuntherd,bloodMephiston",
        # DRIVE des positions -- le scenario EXIGE QUATRE regimes simultanes que la geometrie de
        # spawn ne donne pas. Adjacence RE-DERIVEE de `boardGraph` (voisins de (3,4) = (3,5), (4,4),
        # (4,3), (3,3), (2,3), (2,4) ; voisins de (3,5) = (3,6), (4,5), (4,4), (3,4), (2,4), (2,5)) :
        #   * `orksNob` (3,5) et `orksRuntherd` (2,4) sont ADJACENTS au caster -> tous deux TAUNTES
        #     (avec un seul, l'etage [3] serait degenere : le natif itere un selecteur, pas un
        #     scalaire) ;
        #   * `bloodMephiston` (1,4) est RANGED et a distance 2 -> HORS du taunt, et c'est lui qui
        #     porte l'etage [5] (sa prediction doit baisser de dmgReductionPct%) ET le TEMOIN de
        #     l'etage [6] (une unite NON tauntee ne doit RIEN perdre) ;
        #   * `worldExecutions` (4,5) est adjacent a `orksNob` mais PAS au caster -> c'est le
        #     DISCRIMINANT du taunt : avant le cast `orksNob` peut legalement l'attaquer, apres il
        #     ne le peut plus. Sans lui, « le taunt mord » ne serait mesure sur RIEN (les deux
        #     ennemis n'auraient qu'une cible legale, le caster, avant comme apres).
        #   * il sert AUSSI d'ALLIE pour l'etage [7] (`TargetIsEnemy` doit refuser un allie).
        "--place", "worldEightbound:3,4", "--place", "worldExecutions:4,5",
        "--a-place", "orksNob:3,5", "--a-place", "orksRuntherd:2,4",
        "--a-place", "bloodMephiston:1,4"])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres

    try:
        return _measure_on(sid, rid), dispose
    except Exception:
        dispose()
        raise


def _measure_on(sid: int, rid: int) -> dict:
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.operations.summon_ai import _apply_active_ability

    dec0 = decision(sid, rid)
    caster = find(dec0, "worldEightbound")
    ally = find(dec0, "worldExecutions")
    adj1 = find(dec0, "orksNob")
    adj2 = find(dec0, "orksRuntherd")
    ranged = find(dec0, "bloodMephiston")
    if None in (caster, ally, adj1, adj2, ranged):
        raise AssertionError("SCENARIO NON MONTE : une des 5 unites est absente du decisionView")
    caster_id, ally_id = int(caster["id"]), int(ally["id"])
    adj_ids = [int(adj1["id"]), int(adj2["id"])]
    ranged_id = int(ranged["id"])

    # Cibles LEGALES DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset
    # move-inclus : un cast refuse rend `mutated:false`, observable identique a « l'ability ne fait
    # rien » -- #111).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": OVERWHELMING_WRATH}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == OVERWHELMING_WRATH), {})
    from_here = [int(t.get("targetId")) for t in (ab.get("fromHere") or [])]
    if not all(a in from_here for a in adj_ids):
        raise AssertionError("SCENARIO NON MONTE : les deux ennemis places ne sont pas des cibles "
                             "legales SUR PLACE (drive des positions KO) -- fromHere=%s" % from_here)
    target_id = adj_ids[0]

    # ---- [7] GATE DE CIBLAGE : le masque MORD-il, et aux MEMES endroits que le natif ? ----
    state_gate, _ = load(sid, rid)
    ability = ABILITY_CLASSES[OVERWHELMING_WRATH]()
    sondes = {"soi": caster_id, "allie": ally_id, "adj1": adj_ids[0], "adj2": adj_ids[1],
              "ranged_dist2": ranged_id}
    gate_port = {k: get_invalid_target_reason(state_gate, caster_id, v, ability)
                 for k, v in sondes.items()}
    gate_natif = {}
    for k, v in sondes.items():
        r = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": caster_id,
                                       "abilityType": OVERWHELMING_WRATH, "targetId": v}, 60) or {}
        gate_natif[k] = int((r.get("targetReason") or {}).get("hex", "0x0"), 16)

    # ---- OFFLINE : le MEME cast, joue par le port ----------------------------------------
    # Le MT live est LU AVANT le cast des deux cotes : le port part donc du MEME etat de PRNG que
    # le natif (cf. `seed_offline_rng` -- sans lui, un `0 degat` offline serait le repli defensif
    # de `damage_ops`, pas une mesure).
    dump_pre = rng_dump(sid, rid)
    state, _ = load(sid, rid)
    seed_offline_rng(state, dump_pre)
    off_hp_before = hp_off(state)
    off_before = footprint_off(state)
    rng_off_before = state.rng.call_count
    res = _apply_active_ability(state, caster_id, target_id, OVERWHELMING_WRATH) or {}
    diag = res.get("diag") or {}
    off = delta(off_before, footprint_off(state))
    off_hp_after = hp_off(state)
    rng_off_after = state.rng.call_count
    off_bonds = {}
    for uid, effs in (state.effects.by_unit or {}).items():
        for e in effs:
            if int(e.effect_type) in (TAUNTED, OW_PENDING_ATTACK, OW_RANGE_DMG_REDUCTION) \
                    and not e.consumed:
                off_bonds.setdefault(int(e.effect_type), []).append(
                    {"on": int(uid), "bonded": getattr(e, "bonded", None)})
    off_only = {u: only_targets_off(state, u) for u in adj_ids + [ranged_id]}
    # La MATRICE de gate cote port, APRES le cast : (attaquant ennemi) x (cible du joueur).
    off_matrice = {(c, t): reason_off(state, c, t)
                   for c in adj_ids + [ranged_id] for t in (caster_id, ally_id)}

    # ---- LIVE : le MEME cast, joue par le natif ------------------------------------------
    live_before = footprint_live(dec0)
    live_hp_before = hp_live(sid, rid)
    rng_live_before = rng_key(dump_pre)
    pred_before = predict(sid, rid, ranged_id, caster_id)
    paires = [(c, t) for c in adj_ids + [ranged_id] for t in (caster_id, ally_id)]
    matrice_before = {p: reason_live(sid, rid, p[0], p[1]) for p in paires}
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": OVERWHELMING_WRATH,
        "targetId": target_id}}, 90) or {}
    act0 = (act.get("actions") or [{}])[0]
    rng_live_after = rng_key(rng_dump(sid, rid))
    dec1 = decision(sid, rid)
    matrice_after = {p: reason_live(sid, rid, p[0], p[1]) for p in paires}

    lvl = None
    for a in (caster.get("abilities") or []):
        if int(a.get("id", -1)) == OVERWHELMING_WRATH:
            lvl, mult = a.get("level"), a.get("multiplier")
            break
    else:
        mult = None
    pct = ability_var("OverwhelmingWrath", "dmgReductionPct", lvl,
                      multiplier_pct=(mult if mult is not None else 100))

    return {
        "rid": rid, "caster": caster_id, "ally": ally_id, "adj": adj_ids, "ranged": ranged_id,
        "target": target_id, "from_here": from_here,
        "routed": res.get("routed"), "ported": diag.get("ported"), "diag": diag,
        "cast_error": act0.get("error"),
        "off": off, "live": delta(live_before, footprint_live(dec1)),
        "off_bonds": off_bonds, "live_bonds": bonds_from_cascade(act0),
        "off_hp": (off_hp_before, off_hp_after),
        "live_hp": (live_hp_before, hp_live(sid, rid)),
        "rng_off": (rng_off_before, rng_off_after),
        "rng_live": (rng_live_before, rng_live_after),
        "pred_before": pred_before, "pred_after": predict(sid, rid, ranged_id, caster_id),
        "dmg_reduction_pct": pct, "ability_level": lvl, "multiplier": mult,
        "matrice_before": matrice_before, "matrice_after": matrice_after,
        "off_matrice": off_matrice, "off_only": off_only,
        "gate_port": gate_port, "gate_natif": gate_natif,
    }


def main() -> int:
    sid = _session()
    print("[build] board=%s" % BOARD)
    m, dispose = measure(sid)
    try:
        caster_id, ally_id = m["caster"], m["ally"]
        adj_ids, ranged_id = m["adj"], m["ranged"]
        off, live = m["off"], m["live"]
        off_hp_before, off_hp_after = m["off_hp"]
        live_hp_before, live_hp_after = m["live_hp"]

        print("[scenario] caster=u%d (Azkor) ally=u%d adj=%s ranged=u%d target=u%d"
              % (caster_id, ally_id, adj_ids, ranged_id, m["target"]))
        print("           fromHere=%s" % m["from_here"])

        print("\n[1] EXECUTION PORTEE")
        print("    routed=%s ported=%s" % (m["routed"], m["ported"]))
        if m["ported"] is not True:
            print("    ECHEC : 1141 reste un NO-OP SILENCIEUX cote port")
            return 1
        if m["cast_error"]:
            print("    cast natif BLOQUE : %s" % m["cast_error"])
            return 1

        print("\n[2] EMPREINTE D'EFFETS  (port vs natif)")
        print("    port  = %s" % off)
        print("    natif = %s" % live)
        ok2 = off == live
        print("    -> %s" % ("ACCORD" if ok2 else "DIVERGENCE"))

        print("\n[3] PORTEURS ET BONDS")
        attendu = {caster_id: {OW_RANGE_DMG_REDUCTION, OW_PENDING_ATTACK}}
        for a in adj_ids:
            attendu[a] = {TAUNTED, TAUNTED_BLOCK_MOVEMENT, TAUNTED_CANT_USE_ABILITY,
                          TAUNTED_REFRESH}
        obtenu = {k: set(v) for k, v in off.items()}
        print("    attendu (decompile) = %s" % {k: sorted(v) for k, v in attendu.items()})
        print("    obtenu  (port)      = %s" % {k: sorted(v) for k, v in obtenu.items()})
        ok3 = obtenu == attendu
        ok3_intact = ranged_id not in off and ranged_id not in live
        print("    ennemi NON adjacent u%d intact : %s (NormalUnits(AdjacentEnemies) ne le voit pas)"
              % (ranged_id, ok3_intact))
        bonds_port = m["off_bonds"]
        bonds_natif = m["live_bonds"]
        print("    bonds port  = %s" % bonds_port)
        print("    bonds natif = %s" % bonds_natif)

        def _bonded_ok(src):
            taunt = sorted((int(x["on"]), x["bonded"]) for x in (src.get(TAUNTED) or []))
            pend = sorted((int(x["on"]), x["bonded"]) for x in (src.get(OW_PENDING_ATTACK) or []))
            return (taunt == sorted((a, caster_id) for a in adj_ids)
                    and pend == [(caster_id, caster_id)])
        ok3b = _bonded_ok(bonds_port)
        ok3c = _bonded_ok(bonds_natif) if bonds_natif else None
        print("    -> porteurs %s | bonds port %s | bonds natif %s"
              % ("OK" if ok3 else "KO", "OK" if ok3b else "KO",
                 "NON MESURE (cascade muette)" if ok3c is None else ("OK" if ok3c else "KO")))

        print("\n[4] AUCUN DEGAT, AUCUN TIRAGE  (la refutation de DAMAGE(Eviscerate) + le partage "
              "des 4 mecaniques du kit)")
        off_dmg = {k: (off_hp_before[k], off_hp_after.get(k))
                   for k in off_hp_before if off_hp_after.get(k) != off_hp_before[k]}
        live_dmg = {k: (live_hp_before[k], live_hp_after.get(k))
                    for k in live_hp_before if live_hp_after.get(k) != live_hp_before[k]}
        print("    port  : HP changes = %s | MT call_count %s -> %s (MT CALE sur le live)"
              % (off_dmg or "AUCUN", m["rng_off"][0], m["rng_off"][1]))
        print("    natif : HP changes = %s | MT (callCount,mti,hash) %s -> %s"
              % (live_dmg or "AUCUN", m["rng_live"][0], m["rng_live"][1]))
        ok4 = not off_dmg and not live_dmg
        rng_live_stable = (m["rng_live"][0] == m["rng_live"][1]
                           and m["rng_live"][0][0] is not None)
        rng_off_stable = (m["rng_off"][0] == m["rng_off"][1]
                          and m["rng_off"][0] is not None)
        ok4 = ok4 and rng_live_stable and rng_off_stable
        print("    -> %s" % ("aucun degat ET aucun tirage des deux cotes : `crit`, `block` et "
                             "`dmg_bonus` sont STRUCTURELLEMENT hors de ce behaviour" if ok4
                             else "DEGAT ou TIRAGE observe"))

        print("\n[5] CONSEQUENCE DE 1301  (prediction NATIVE, ennemi RANGED u%d -> caster)"
              % ranged_id)
        pct = m["dmg_reduction_pct"]
        before, after = m["pred_before"], m["pred_after"]
        print("    dmgReductionPct(level=%s, mult=%s) = %s" % (m["ability_level"],
                                                               m["multiplier"], pct))
        print("    prediction avant = %s ; apres = %s" % (before, after))
        ok5 = bool(before and after and pct)
        if ok5:
            lignes = []
            for v0, v1 in zip(before, after):
                lo = (v0 - 0.5) * (100 - int(pct)) / 100
                hi = (v0 + 0.5) * (100 - int(pct)) / 100
                dedans = (lo - 0.5) <= v1 <= (hi + 0.5)
                ok5 = ok5 and dedans
                lignes.append("%d->%d in [%.1f,%.1f]%s" % (v0, v1, lo, hi, "" if dedans else " KO"))
            print("    encadrement x(100-%s)/100 : %s" % (pct, " ; ".join(lignes)))
            # ANTI-DEGENERESCENCE : un encadrement passe TRIVIALEMENT si le bonus est nul.
            if not (int(pct) > 0 and after != before):
                ok5 = False
                print("      REGIME DEGENERE : pct=%s bouge=%s -> l'encadrement ne prouve RIEN"
                      % (pct, after != before))
        print("    -> %s" % ("l'effet 1301 MORD sur la prediction native (-%s%%)" % pct if ok5
                             else "NON CONCLUANT (prediction absente, hors bornes, ou degenere)"))

        print("\n[6] CONSEQUENCE DU TAUNT  (GetOnlyTargets -> regle `TargetIsAllowedForCaster`)")
        print("    GetOnlyTargets cote port : %s (vide = aucune restriction)" % m["off_only"])
        ok6_only = (all(m["off_only"].get(a) == [caster_id] for a in adj_ids)
                    and m["off_only"].get(ranged_id) == [])
        av, ap, op = m["matrice_before"], m["matrice_after"], m["off_matrice"]
        print("    matrice `abilityReason(<ennemi>, NormalAttack, <unite du joueur>)` :")
        ok6_accord, bascules = True, []
        for (c, t) in sorted(av):
            same = ap[(c, t)] == op[(c, t)]
            ok6_accord = ok6_accord and same
            if av[(c, t)] != ap[(c, t)]:
                bascules.append((c, t, av[(c, t)], ap[(c, t)]))
            print("      u%d -> u%d : avant 0x%-9x apres natif 0x%-9x port 0x%-9x %s"
                  % (c, t, av[(c, t)], ap[(c, t)], op[(c, t)],
                     "OK" if same else "DIVERGENCE"))
        # ANTI-DEGENERESCENCE : si RIEN ne bascule, l'accord port/natif ne prouve rien du taunt.
        # Les bascules ATTENDUES : les DEUX ennemis TAUNTES perdent l'allie -- et il faut qu'au
        # moins UNE d'entre elles parte d'un 0 (cible ACCEPTEE avant), sinon on ne mesurerait qu'un
        # changement de LIBELLE de refus.
        # ⚠ Le refus qui remplace peut MASQUER un autre : `u83 -> u79` passe de `TargetIsInRange`
        # (0x8000000) a `TargetIsAllowedForCaster` (0x800000) -- le natif rend LA PREMIERE regle
        # rompue de sa cascade, et le bit 23 y est teste AVANT la portee. Le port reproduit cet
        # ordre (les deux rendent 0x800000) : c'est une propriete de la CASCADE, pas du taunt.
        attendue = [(a, ally_id) for a in adj_ids]
        ok6_bascule = (sorted((c, t) for c, t, _a, _b in bascules) == sorted(attendue)
                       and any(_a == 0 for _c, _t, _a, _b in bascules))
        ok6_bit = all(ap[(c, t)] & TARGET_IS_ALLOWED_FOR_CASTER for c, t, _a, _b in bascules)
        ok6_temoin = all(av[(ranged_id, t)] == ap[(ranged_id, t)] for t in (caster_id, ally_id))
        print("    bascules = %s ; attendues = %s ; bit 23 pose = %s ; temoin NON taunte intact = %s"
              % ([(c, t, hex(_a), hex(_b)) for c, t, _a, _b in bascules], attendue, ok6_bit,
                 ok6_temoin))
        ok6 = ok6_only and ok6_accord and ok6_bascule and ok6_bit and ok6_temoin
        print("    -> %s" % ("le taunt MORD sur les adjacents SEULS, port et natif d'accord" if ok6
                             else "le taunt ne mord pas, deborde, ou l'accord est degenere"))

        print("\n[7] GATE DE CIBLAGE  (masque 0x4000 TargetIsEnemy + isSelfCasting + RANGE_ADJACENT)")
        gp, gn = m["gate_port"], m["gate_natif"]
        ok7 = True
        for k in sorted(gp):
            same = gp[k] == gn[k]
            ok7 = ok7 and same
            print("    %-13s port=0x%-9x natif=0x%-9x %s" % (k, gp[k], gn[k],
                                                             "OK" if same else "DIVERGENCE"))
        # ANTI-DEGENERESCENCE : un accord ou TOUT vaut 0 ne prouverait rien.
        if not (gp.get("allie") and gp.get("ranged_dist2")
                and gp.get("soi") == 0 and gp.get("adj1") == 0):
            ok7 = False
            print("    REGIME DEGENERE : le gate doit REFUSER l'allie et l'ennemi hors portee, et "
                  "ACCEPTER soi (isSelfCasting) et l'ennemi adjacent")
        print("    -> %s" % ("le masque MORD, aux MEMES endroits que le natif" if ok7
                             else "divergence ou regime degenere"))

        etages = {"[2] empreinte": ok2, "[3] porteurs": ok3, "[3] non-adjacent intact": ok3_intact,
                  "[3] bonds port": ok3b, "[3] bonds natif": ok3c, "[4] 0 degat 0 tirage": ok4,
                  "[5] dmg reduction": ok5, "[6] taunt": ok6, "[7] gate ciblage": ok7}
        rouges = [k for k, v in etages.items() if v is False]
        muets = [k for k, v in etages.items() if v is None]
        print("\nETAGES : %s" % {k: ("OK" if v else ("NON MESURE" if v is None else "KO"))
                                 for k, v in etages.items()})
        if muets:
            print("NON MESURE : %s" % ", ".join(muets))
        print("PROBE OK" if not rouges else "PROBE KO -- %s" % ", ".join(rouges))
        return 0 if not rouges else 1
    finally:
        dispose()          # dispose MES runners, jamais ceux des autres


if __name__ == "__main__":
    raise SystemExit(main())
