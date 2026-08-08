"""probe_552 -- MESURE de `1164 MindControl` (`genesMagus` << Magus >>, Genestealer Cults, HERO).

DEUX QUESTIONS BINAIRES, posees AVANT la methode :

  Q1. **Le cast de 1164 frappe-t-il ?** L'audit `docs/rl/combat-ability-coverage.md` le classe
      `EFFECT/BUFF`, mais cette colonne derive du `damageProfile` de l'ARME du porteur, pas du
      behaviour. Le decompile tranche :
      `IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour` ne
      porte AUCUN noeud d'attaque, AUCUN spawn, AUCUNE stat -- quatre poses d'effet, un `Inform`
      et deux `If`. Etage [5] le MESURE (PV inchanges ET `dumpRng` inchange des DEUX cotes).

  Q2. **Est-ce un OWNER-SWAP ?** Le NOM le suggere. Non : l'arbre ne touche ni l'appartenance
      d'equipe ni l'ordre d'activation. Le << controle >> est un TAUNT bonde. Etage [6] le MESURE
      (les cibles legales de l'ennemi mind-controle changent ; son EQUIPE et son tour, non).

ARBRE NATIF (mirror, cf. `engine/runner/abilities/loki/mind_control.py`) :

    Execute( AddEffect(1349 MindControl_OutoingDamageReduction -> Target, TurnsFromRounds(2))
           & AddEffect(1350 MindControl_IncomingDamageBonus    -> Target, meme duree)
           & If( NOT HasTrait(Target, 25 = Immune),
                 Inform(0xcb = TagKey.Custom_Unit_Id, cache)
               & If( cache, AddBondEffect(27 Taunted_OnlySpecificTargets -> Target, bonde au cache)
                          & AddBondEffect(1367 MindControl_Taunter -> cache, bonde a Target) ) ) )

    cache = Cache(First(SortByFormula(Attackable(Friends(Owner, AdjacentUnits(Target))),
                                      StatAmount(It, 5 = HEALTH), ascending = 0), 1))

ETAGES MESURES (jamais un scalaire fitte -- chaque etage a son oracle natif) :
  [1] EXECUTION portee     : `diag.ported is True` (sans quoi le cast est un NO-OP SILENCIEUX --
                             l'etat AVANT ce port).
  [2] empreinte d'effets   : port == natif, `{unite -> {effectType: remaining}}`.
  [3] PORTEURS et BONDS    : 1349 + 1350 sur la CIBLE ; 27 sur la CIBLE bonde au TAUNTEUR ; 1367
                             sur le TAUNTEUR bonde a la CIBLE. Lus dans la CASCADE du cast natif
                             (`BondEffect_BondedId`), le SEUL canal qui publie le bond.
  [4] LE DISCRIMINANT      : le taunteur est l'allie du CASTER, adjacent a la cible, a la plus
                             haute Health COURANTE. Le montage rend les TROIS lectures fausses
                             distinguables : l'allie a la plus BASSE Health est place PREMIER dans
                             l'ordre d'adjacence de la cible, donc << premier enumere >> et
                             << plus basse Health >> designent tous deux l'AUTRE unite que
                             << plus haute Health >>.
  [5] AUCUN DEGAT + AUCUN TIRAGE : PV inchanges ET etat MT19937 (`dumpRng`) strictement egal, des
                             DEUX cotes. C'est ce qui repond a Q1 : sans coup porte et sans tirage
                             consomme, le cast est STRUCTURELLEMENT hors du canal degat.
  [6] CONSEQUENCE du TAUNT : l'ennemi mind-controle ne peut plus viser que le TAUNTEUR
                             (`UnitExtensions$$GetOnlyTargets` -> `TargetIsAllowedForCaster`), et
                             son EQUIPE est inchangee (reponse a Q2).
  [7] GATE DE CIBLAGE      : masque `0x4002` (`TargetMatchesDynamicRule | TargetIsEnemy`) + la
                             REGLE DYNAMIQUE neuve. Port vs natif sur QUATRE sondes : soi / un
                             allie / la cible (ennemi AVEC allie adjacent) / un ennemi TEMOIN sans
                             AUCUN allie adjacent -- ce dernier est le seul que la regle dynamique
                             refuse, et il est a portee 3 du caster pour que le refus ne puisse pas
                             venir du volet PORTEE.

Le placement est FORCE (`--place`/`--a-place`) et les PV sont crafts (`--unit-stat`) : le
discriminant de l'etage [4] EXIGE deux allies adjacents a la cible dont l'ordre d'enumeration
CONTREDIT l'ordre des PV, ce qu'aucune geometrie de spawn ne garantit. << Bloque par la geometrie >>
n'est pas un resultat.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_552_mind_control.py [--state-name <nom>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"      # SORTIES -> logs/, jamais data/ (#349)

MIND_CONTROL = 1164            # ActiveAbilityType.MindControl
OUT_DMG_REDUCTION = 1349       # EffectType.MindControl_OutoingDamageReduction  (0x545)
IN_DMG_BONUS = 1350            # EffectType.MindControl_IncomingDamageBonus     (0x546)
TAUNTED = 27                   # EffectType.Taunted_OnlySpecificTargets         (0x1b)
TAUNTER = 1367                 # EffectType.MindControl_Taunter                 (0x557)
NORMAL_ATTACK = 69             # ActiveAbilityType.Loki_NormalAttack
BOARD = "MC1_67"

#: Geometrie FORCEE (cf. l'en-tete). Les voisins de la cible `(3,4)` sont, DANS L'ORDRE de
#: l'adjacence stockee du board : (2,3) (2,4) (3,3) (3,5) (4,3) (4,4). L'allie FAIBLE est donc pose
#: en `(2,4)` (2e voisin) et le FORT en `(4,4)` (6e et DERNIER) : << premier enumere >> designe le
#: FAIBLE, << plus haute Health >> designe le FORT. Le caster est en `(3,2)`, a distance 2 de la
#: cible mais PAS adjacent (les voisins de (3,2) sont (2,1) (2,2) (3,1) (3,3) (4,1) (4,2)) -- sans
#: quoi le Magus serait lui-meme candidat au taunt et l'etage [4] serait degenere.
POS_CASTER = "3,2"
POS_ALLY_LOW = "2,4"
POS_ALLY_HIGH = "4,4"
POS_TARGET = "3,4"
#: Ennemi TEMOIN de l'etage [7] : distance 2 du caster (DONC a portee 3 : le refus ne peut pas
#: venir du volet PORTEE), MEME ELEVATION que le caster (2) et LOS libre (le refus ne peut pas
#: venir du volet OBSCURCISSEMENT non plus), et AUCUN de ses six voisins n'est occupe par une de
#: mes unites -- c'est le SEUL terme qui reste, donc la regle dynamique.
#: ⚠ MESURE, pas un choix de confort : le premier temoin essaye, `(5,3)`, est un `Swamp` a
#: ELEVATION 4 contre 2 pour le caster -> les DEUX moteurs y rendaient `0x1000000
#: TargetIsUnobscured`, un refus REEL mais qui vient d'un AUTRE etage. Un temoin qui conflue deux
#: gates ne mesure ni l'un ni l'autre.
POS_LONE = "5,2"

CASTER_ID = "genesMagus"
ALLY_LOW_ID = "genesPrimus"
ALLY_HIGH_ID = "genesKelermorph"
TARGET_ID = "blackPossession"
LONE_ID = "orksNob"

#: PV CRAFTES -- l'ecart doit etre GRAND et de sens CONTRAIRE a l'ordre d'enumeration.
HP_LOW = 4000
HP_HIGH = 40000

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12 / #486-r15).
#: PERIMETRE LARGE, et c'est une MESURE : la fermeture d'import d'un probe d'ability atteint la
#: quasi-totalite de `scripts/python`. Declarer etroit produirait un FAUX VERT.
#: ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py` ne
#: voit PAS `scripts/python/board.py`.
DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le port de 1164 au NATIF via un runner live : il depend du code du "
              "port (arbre DSL + AddEffect/AddBondEffect + les selecteurs AdjacentUnits/Friends/"
              "Attackable/SortByFormula/First/Cache + StatAmount + TauntedEffect + les trois "
              "effets MindControl_* + le registre + le masque de ciblage + la regle dynamique) ET "
              "du build charge -- l'oracle etant le jeu lui-meme, pas une constante ecrite ici.",
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
        print((proc.stderr or proc.stdout or "")[-2000:])
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
    """Etat COMPLET du MT19937 de combat. Un CAST qui ne tire RIEN le laisse strictement egal --
    c'est le canal qui separe << pas de degat observe >> de << pas de degat POSSIBLE >>."""
    return rpc(sid, "dumpRng", {"runnerId": rid}, 40) or {}


def rng_key(d):
    mt = tuple(d.get("mt") or ())
    return (d.get("callCount"), d.get("mti"), hash(mt))


def seed_offline_rng(state, dump):
    """CALE le MT offline sur le MT LIVE : sans ce calage `state.rng is None` et le port rendrait
    un `0 degat` de REPLI defensif au lieu d'un `0` MESURE."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = int(dump["mti"])
    state.rng = rng
    return rng


def bonds_from_cascade(act: dict) -> dict:
    """`{effectType -> [{'on': porteur, 'bonded': BondEffect_BondedId, 'source': ...}]}` lu dans la
    CASCADE du cast NATIF -- le SEUL canal qui publie le BOND (`decisionView.effects` ne porte que
    `effectType`/`remaining`). Meme lecture que `probe_503_overwhelming_wrath.bonds_from_cascade`
    (instance d'effet -> NOM par le canal `group.source`, puis NOM -> `EffectType` par le mirror :
    << la conversion se fait PAR NOM >>)."""
    from engine.entities.effect_type import EffectType
    nom_par_instance, out = {}, {}
    for ev in (act.get("events") or []):
        if isinstance(ev, dict) and ev.get("kind") == "group" and ev.get("source"):
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
        if nom is None or "Effect_SourceId" not in tags:
            continue
        etype = getattr(EffectType, nom, None)
        if etype is None:
            continue
        out.setdefault(int(etype), []).append(
            {"on": ev.get("entity"), "bonded": tags.get("BondEffect_BondedId"),
             "source": tags.get("Effect_SourceId")})
    return out


def only_targets_off(state, unit_id):
    """`IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` cote port -- le foyer UNIQUE que lit la
    regle `TargetIsAllowedForCaster`. Liste VIDE = aucune restriction."""
    from engine.runner.abilities.targeting import get_only_targets
    return sorted(int(x) for x in (get_only_targets(state, int(unit_id)) or []))


def reason_live(sid, rid, caster, target, ability):
    r = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": int(caster),
                                   "abilityType": int(ability), "targetId": int(target)}, 60) or {}
    return int((r.get("targetReason") or {}).get("hex", "0x0"), 16)


def reason_off_normal(state, caster, target):
    from engine.runner.abilities.targeting import (_NormalAttackTargeting,
                                                   get_invalid_target_reason,
                                                   normal_attack_targeting_options)
    porteur = _NormalAttackTargeting(normal_attack_targeting_options(state, int(caster)))
    return get_invalid_target_reason(state, int(caster), int(target), porteur)


def predict(sid, rid, attacker, target):
    """`aiPredict` = le PREVIEW natif de degat (`GetAllPredictions`) -- exactement le chemin qui
    traverse `CalculateAttackerModifiersForPrediction` / `CalculateDefenderModifiersForPrediction`,
    donc les deux slots que les effets 1349 / 1350 alimentent. Rend `(healthDmgMin, healthDmgMax)`
    ou None (shape REELLE : les bornes vivent dans `pred`, pas a la racine)."""
    r = rpc(sid, "aiPredict", {"runnerId": rid, "unitId": int(attacker),
                               "targetId": int(target), "fresh": True}, 60) or {}
    pred = r.get("pred") or {}
    lo, hi = pred.get("healthDmgMin"), pred.get("healthDmgMax")
    return (int(lo), int(hi)) if (lo is not None and hi is not None) else None


def effect_bonus_off(state, unit_id, effect_type):
    """Le `EffectBonus` que rend l'instance MATERIALISEE de `effect_type` portee par `unit_id`,
    sur SON canal. C'est le pendant UNITAIRE de la mesure de prediction : il dit le KIND, le SIGNE,
    la MAGNITUDE et la FACE, la ou `aiPredict` ne dit qu'un scalaire compose."""
    for e in (state.effects.by_unit.get(int(unit_id)) or []):
        if int(e.effect_type) != int(effect_type) or e.consumed:
            continue
        b = e.create_effect_damage_bonus_for_attack()
        canal, face = "attack_bonus", e.ATTACK_BONUS_NATIVE_FACE
        if b is None:
            b = e.create_effect_damage_malus_for_defense()
            canal, face = "defense_malus", e.DEFENSE_MALUS_NATIVE_FACE
        if b is None:
            return {"canal": None}
        return {"canal": canal, "kind": b.kind, "value": b.value,
                "owner_is_caster": b.owner_is_caster, "native_face": face,
                "classe": type(e).__name__}
    return None


def team_of(dec, uid):
    u = next((x for x in (dec.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)
    return None if u is None else u.get("team")


def measure(sid: int, seed: str = "777", board: str = BOARD,
            state_name: str = "probe_552_mind_control"):
    """Monte le scenario, joue le cast des DEUX cotes, rend `(mesures, dispose)`.

    Le TEST de garde (`tests/engine/runner/test_552_mind_control_live.py`) appelle CETTE fonction :
    une seule implementation du montage et des lectures, donc aucune divergence possible entre ce
    qui est MESURE ici et ce qui est GARDE la-bas."""
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", "%s,%s,%s" % (CASTER_ID, ALLY_LOW_ID, ALLY_HIGH_ID),
        "--a-units", "%s,%s" % (TARGET_ID, LONE_ID),
        # PV CRAFTES : le seul levier qui produit un ECART INTRA-CAMP (les flags globaux forcent
        # une valeur UNIQUE sur tout un cote, donc AUCUN ecart -- cf. runner.md).
        "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (ALLY_LOW_ID, HP_LOW, HP_LOW),
        "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (ALLY_HIGH_ID, HP_HIGH, HP_HIGH),
        "--place", "%s:%s" % (CASTER_ID, POS_CASTER),
        "--place", "%s:%s" % (ALLY_LOW_ID, POS_ALLY_LOW),
        "--place", "%s:%s" % (ALLY_HIGH_ID, POS_ALLY_HIGH),
        "--a-place", "%s:%s" % (TARGET_ID, POS_TARGET),
        "--a-place", "%s:%s" % (LONE_ID, POS_LONE)])

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
    caster = find(dec0, CASTER_ID)
    low = find(dec0, ALLY_LOW_ID)
    high = find(dec0, ALLY_HIGH_ID)
    target = find(dec0, TARGET_ID)
    lone = find(dec0, LONE_ID)
    if None in (caster, low, high, target, lone):
        raise AssertionError("SCENARIO NON MONTE : une des 5 unites est absente du decisionView")
    caster_id, low_id, high_id = int(caster["id"]), int(low["id"]), int(high["id"])
    target_id, lone_id = int(target["id"]), int(lone["id"])

    hp0 = hp_live(sid, rid)
    if not (hp0.get(high_id, 0) > hp0.get(low_id, 0)):
        raise AssertionError("SCENARIO NON MONTE : le craft de PV n'a pas mordu (%s vs %s)"
                             % (hp0.get(high_id), hp0.get(low_id)))

    # Cibles LEGALES DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset
    # move-inclus : un cast refuse rend `mutated:false`, observable identique a << l'ability ne fait
    # rien >> -- #111).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": MIND_CONTROL}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == MIND_CONTROL), {})
    from_here = [int(t.get("targetId")) for t in (ab.get("fromHere") or [])]
    if target_id not in from_here:
        raise AssertionError("SCENARIO NON MONTE : la cible n'est pas legale SUR PLACE "
                             "(drive des positions KO) -- fromHere=%s" % from_here)

    # ---- [7] GATE DE CIBLAGE : le masque + la regle dynamique MORDENT-ils comme le natif ? ----
    state_gate, _ = load(sid, rid)
    ability = ABILITY_CLASSES[MIND_CONTROL]()
    sondes = {"soi": caster_id, "allie": high_id, "cible": target_id, "ennemi_isole": lone_id}
    gate_port = {k: get_invalid_target_reason(state_gate, caster_id, v, ability)
                 for k, v in sondes.items()}
    gate_natif = {k: reason_live(sid, rid, caster_id, v, MIND_CONTROL)
                  for k, v in sondes.items()}
    # La regle dynamique SEULE (hors cascade), pour attribuer un refus a l'etage qui le produit.
    regle_port = {k: ability.get_dynamic_invalid_target_reason(state_gate, caster_id, v)
                  for k, v in sondes.items()}

    # ---- OFFLINE : le MEME cast, joue par le port ----------------------------------------
    dump_pre = rng_dump(sid, rid)
    state, _ = load(sid, rid)
    seed_offline_rng(state, dump_pre)
    off_hp_before = hp_off(state)
    off_before = footprint_off(state)
    rng_off_before = state.rng.call_count
    res = _apply_active_ability(state, caster_id, target_id, MIND_CONTROL) or {}
    diag = res.get("diag") or {}
    off = delta(off_before, footprint_off(state))
    off_hp_after = hp_off(state)
    rng_off_after = state.rng.call_count
    off_bonds = {}
    for uid, effs in (state.effects.by_unit or {}).items():
        for e in effs:
            if int(e.effect_type) in (OUT_DMG_REDUCTION, IN_DMG_BONUS, TAUNTED, TAUNTER) \
                    and not e.consumed:
                off_bonds.setdefault(int(e.effect_type), []).append(
                    {"on": int(uid), "bonded": getattr(e, "bonded", None)})
    off_only = {u: only_targets_off(state, u) for u in (target_id, lone_id)}
    off_matrice = {(target_id, t): reason_off_normal(state, target_id, t)
                   for t in (low_id, high_id, caster_id)}
    # [8] ce que les DEUX classes d'effet du port RENDENT, une fois materialisees sur la cible.
    off_bonus = {OUT_DMG_REDUCTION: effect_bonus_off(state, target_id, OUT_DMG_REDUCTION),
                 IN_DMG_BONUS: effect_bonus_off(state, target_id, IN_DMG_BONUS)}

    # ---- LIVE : le MEME cast, joue par le natif ------------------------------------------
    live_before = footprint_live(dec0)
    live_hp_before = hp_live(sid, rid)
    rng_live_before = rng_key(dump_pre)
    paires = [(target_id, t) for t in (low_id, high_id, caster_id)]
    matrice_before = {p: reason_live(sid, rid, p[0], p[1], NORMAL_ATTACK) for p in paires}
    # [8] deux directions, deux effets, deux SIGNES attendus :
    #   sortant : la CIBLE attaque -> `1349` (get_OwnerIsCaster) doit FAIRE BAISSER ;
    #   entrant : un ALLIE attaque la CIBLE -> `1350` (get_OwnerIsTarget) doit FAIRE MONTER.
    pred_out_before = predict(sid, rid, target_id, high_id)
    pred_in_before = predict(sid, rid, high_id, target_id)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": MIND_CONTROL,
        "targetId": target_id}}, 90) or {}
    act0 = (act.get("actions") or [{}])[0]
    rng_live_after = rng_key(rng_dump(sid, rid))
    dec1 = decision(sid, rid)
    matrice_after = {p: reason_live(sid, rid, p[0], p[1], NORMAL_ATTACK) for p in paires}

    lvl = mult = None
    for a in (caster.get("abilities") or []):
        if int(a.get("id", -1)) == MIND_CONTROL:
            lvl, mult = a.get("level"), a.get("multiplier")
            break
    dmg_reduction = ability_var("MindControl", "dmgReduction", lvl,
                                multiplier_pct=(mult if mult is not None else 100))
    extra_dmg_pct = ability_var("MindControl", "extraDmgPct", lvl,
                                multiplier_pct=(mult if mult is not None else 100))

    return {
        "rid": rid, "caster": caster_id, "low": low_id, "high": high_id,
        "target": target_id, "lone": lone_id, "from_here": from_here,
        "hp_allies": {"low": hp0.get(low_id), "high": hp0.get(high_id)},
        "routed": res.get("routed"), "ported": diag.get("ported"), "diag": diag,
        "cast_error": act0.get("error"), "mutated": act0.get("mutated"),
        "off": off, "live": delta(live_before, footprint_live(dec1)),
        "off_bonds": off_bonds, "live_bonds": bonds_from_cascade(act0),
        "off_hp": (off_hp_before, off_hp_after),
        "live_hp": (live_hp_before, hp_live(sid, rid)),
        "rng_off": (rng_off_before, rng_off_after),
        "rng_live": (rng_live_before, rng_live_after),
        "team_target_before": team_of(dec0, target_id),
        "team_target_after": team_of(dec1, target_id),
        "matrice_before": matrice_before, "matrice_after": matrice_after,
        "off_matrice": off_matrice, "off_only": off_only, "off_bonus": off_bonus,
        "pred_out": (pred_out_before, predict(sid, rid, target_id, high_id)),
        "pred_in": (pred_in_before, predict(sid, rid, high_id, target_id)),
        "gate_port": gate_port, "gate_natif": gate_natif, "regle_port": regle_port,
        "dmg_reduction": dmg_reduction, "extra_dmg_pct": extra_dmg_pct,
        "ability_level": lvl, "multiplier": mult,
    }


# ============================ FACE DECISION (montage SEPARE) ==================================
#
# La face COMBAT ci-dessus ne dit RIEN de la DECISION : `MindControlPlaybook` choisit la CIBLE, et
# son utilite est `Fix64(GetStat(cible, 5 = HEALTH))` -- les PV COURANTS de l'ENNEMI vise, alors
# que l'arbre de COMBAT trie les TAUNTEURS (mes allies) par la MEME stat. Confondre les deux
# donnerait une decision qui a l'air juste et vise la mauvaise unite.
#
# MONTAGE : DEUX ennemis LEGAUX (chacun a un allie adjacent, tous deux a portee 3 et NON obscurcis)
# aux PV tres differents. L'oracle est `aiDryRunAllUnits` (read-only, `mutated=false` verifie) ; le
# port repond par `engine_validate.engine_decide` sur le MEME etat.
POS_D_CASTER = "3,2"
POS_D_ALLY_A = "2,4"        # adjacent a l'ennemi FAIBLE
POS_D_ALLY_B = "4,1"        # adjacent a l'ennemi FORT
POS_D_ENEMY_LOW = "3,4"     # elevation 3
POS_D_ENEMY_HIGH = "5,2"    # elevation 2 (== celle du caster) -> non obscurci
ALLY_B_ID = "genesBiophagus"
ENEMY_LOW_ID = "blackPossession"
ENEMY_HIGH_ID = "orksNob"
HP_ENEMY_LOW = 5000
HP_ENEMY_HIGH = 50000


def measure_decision(sid: int, seed: str = "777", board: str = BOARD,
                     state_name: str = "probe_552_mind_control_dec"):
    """Face DECISION : le natif et le port choisissent-ils la MEME cible pour 1164 ?"""
    state_path = LOGS / ("%s.json" % state_name)
    rid = build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", "%s,%s,%s" % (CASTER_ID, ALLY_LOW_ID, ALLY_B_ID),
        "--a-units", "%s,%s" % (ENEMY_LOW_ID, ENEMY_HIGH_ID),
        "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (ENEMY_LOW_ID, HP_ENEMY_LOW,
                                                            HP_ENEMY_LOW),
        "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (ENEMY_HIGH_ID, HP_ENEMY_HIGH,
                                                            HP_ENEMY_HIGH),
        "--place", "%s:%s" % (CASTER_ID, POS_D_CASTER),
        "--place", "%s:%s" % (ALLY_LOW_ID, POS_D_ALLY_A),
        "--place", "%s:%s" % (ALLY_B_ID, POS_D_ALLY_B),
        "--a-place", "%s:%s" % (ENEMY_LOW_ID, POS_D_ENEMY_LOW),
        "--a-place", "%s:%s" % (ENEMY_HIGH_ID, POS_D_ENEMY_HIGH)])

    def dispose():
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)

    try:
        return _decision_on(sid, rid), dispose
    except Exception:
        dispose()
        raise


def _decision_on(sid: int, rid: int) -> dict:
    import engine_validate as EV
    from engine import weights
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene

    dec0 = decision(sid, rid)
    caster = find(dec0, CASTER_ID)
    e_low = find(dec0, ENEMY_LOW_ID)
    e_high = find(dec0, ENEMY_HIGH_ID)
    if None in (caster, e_low, e_high):
        raise AssertionError("SCENARIO DECISION NON MONTE : une unite est absente")
    cid, low_id, high_id = int(caster["id"]), int(e_low["id"]), int(e_high["id"])
    hp = hp_live(sid, rid)
    if not (hp.get(high_id, 0) > hp.get(low_id, 0)):
        raise AssertionError("SCENARIO DECISION NON MONTE : le craft de PV n'a pas mordu")

    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": cid, "abilityType": MIND_CONTROL}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == MIND_CONTROL), {})
    from_here = [int(t.get("targetId")) for t in (ab.get("fromHere") or [])]

    # --- oracle NATIF (read-only) ---
    res = rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 180) or {}
    if not res.get("ok"):
        raise AssertionError("aiDryRunAllUnits KO: " + str(res)[:300])
    if res.get("mutated"):
        raise AssertionError("aiDryRunAllUnits a MUTE l'etat -> oracle invalide")
    ligne = next((u for u in (res.get("units") or []) if u.get("unitId") == cid), None)
    nat_ab = nat_tgt = None
    for m in ((ligne or {}).get("proposed") or []):
        if m.get("cls") == "ActiveAbilityMessage":
            nat_ab, nat_tgt = m.get("abilityType"), m.get("targetId")
            break

    # --- le PORT sur le MEME etat ---
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: rpc(sid, m, b, t), rid)
    port = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, weights.load(), predictor)

    # --- et le playbook SEUL (diagnostic par etage, pas un oracle) ---
    c = _ai_ctx.build(lambda m, b, t: rpc(sid, m, b, t), rid, dv, mov_by_unit, cid,
                      weights.load(), predictor)
    nc = PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)
    pb = PB.playbook_for(MIND_CONTROL)
    cands = pb.generate_candidates(nc) if pb is not None else []
    utilites = {int(t): pb.evaluate_non_comparable(c.origin, int(t), nc)
                for t in (low_id, high_id)} if pb is not None else {}

    return {"rid": rid, "caster": cid, "low": low_id, "high": high_id,
            "hp": {"low": hp.get(low_id), "high": hp.get(high_id)},
            "from_here": from_here,
            "natif": {"ability": nat_ab, "target": nat_tgt},
            "port": {"ability": (port or {}).get("ability"),
                     "target": (port or {}).get("target"), "brut": port},
            "playbook_candidats": cands, "playbook_utilites": utilites,
            "playbook_min_utility": (None if pb is None else pb.MIN_UTILITY)}


def _fmt(d):
    return json.dumps(d, sort_keys=True, default=str)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-name", default="probe_552_mind_control")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--face", choices=("combat", "decision", "les-deux"), default="les-deux")
    a = ap.parse_args()
    sid = _session()
    if a.face == "decision":
        d, dispose_d = measure_decision(sid, seed=a.seed, board=a.board)
        try:
            _print_decision(d)
        finally:
            dispose_d()
        return
    m, dispose = measure(sid, seed=a.seed, board=a.board, state_name=a.state_name)
    try:
        print("=== probe_552 -- 1164 MindControl (runner %s) ===" % m["rid"])
        print("caster=%s low=%s(%s PV) high=%s(%s PV) target=%s lone=%s"
              % (m["caster"], m["low"], m["hp_allies"]["low"], m["high"],
                 m["hp_allies"]["high"], m["target"], m["lone"]))
        print("gameconfig: dmgReduction=%s extraDmgPct=%s (level=%s mult=%s)"
              % (m["dmg_reduction"], m["extra_dmg_pct"], m["ability_level"], m["multiplier"]))
        print()
        print("[1] EXECUTION portee   : routed=%s ported=%s cast_error=%s mutated=%s"
              % (m["routed"], m["ported"], m["cast_error"], m["mutated"]))
        print("[2] effets PORT        : %s" % _fmt(m["off"]))
        print("    effets NATIF       : %s" % _fmt(m["live"]))
        print("[3] bonds PORT         : %s" % _fmt(m["off_bonds"]))
        print("    bonds NATIF        : %s" % _fmt(m["live_bonds"]))
        print("[4] discriminant       : taunteur attendu = high(%s) ; low(%s) est le PREMIER voisin"
              % (m["high"], m["low"]))
        print("[5] PV port  %s -> %s" % (_fmt(m["off_hp"][0]), _fmt(m["off_hp"][1])))
        print("    PV natif %s -> %s" % (_fmt(m["live_hp"][0]), _fmt(m["live_hp"][1])))
        print("    rng port %s ; rng natif %s" % (m["rng_off"], m["rng_live"]))
        print("[6] only_targets PORT  : %s" % _fmt(m["off_only"]))
        print("    gate normale NATIF avant : %s" % _fmt({str(k): v for k, v in
                                                          m["matrice_before"].items()}))
        print("    gate normale NATIF apres : %s" % _fmt({str(k): v for k, v in
                                                          m["matrice_after"].items()}))
        print("    gate normale PORT  apres : %s" % _fmt({str(k): v for k, v in
                                                          m["off_matrice"].items()}))
        print("    equipe cible %s -> %s" % (m["team_target_before"], m["team_target_after"]))
        print("[7] gate PORT          : %s" % _fmt(m["gate_port"]))
        print("    gate NATIF         : %s" % _fmt(m["gate_natif"]))
        print("    regle dyn PORT     : %s" % _fmt(m["regle_port"]))
        print("[8] pred SORTANTE natif (cible -> allie) : %s -> %s   (attendu : BAISSE, -%s plat)"
              % (m["pred_out"][0], m["pred_out"][1], m["dmg_reduction"]))
        print("    pred ENTRANTE natif (allie -> cible) : %s -> %s   (attendu : HAUSSE, +%s %%)"
              % (m["pred_in"][0], m["pred_in"][1], m["extra_dmg_pct"]))
        print("    EffectBonus PORT   : %s" % _fmt(m["off_bonus"]))
    finally:
        dispose()
    if a.face == "les-deux":
        print()
        d, dispose_d = measure_decision(sid, seed=a.seed, board=a.board)
        try:
            _print_decision(d)
        finally:
            dispose_d()


def _print_decision(d):
    print("=== probe_552 -- FACE DECISION (runner %s) ===" % d["rid"])
    print("caster=%s enemy_low=%s(%s PV) enemy_high=%s(%s PV) fromHere=%s"
          % (d["caster"], d["low"], d["hp"]["low"], d["high"], d["hp"]["high"], d["from_here"]))
    print("[D1] proposition NATIVE : %s" % _fmt(d["natif"]))
    print("[D2] decision PORT      : ability=%s target=%s"
          % (d["port"]["ability"], d["port"]["target"]))
    print("[D3] playbook 1164      : utilites=%s MIN_UTILITY=%s candidats=%s"
          % (_fmt(d["playbook_utilites"]), d["playbook_min_utility"],
             _fmt(d["playbook_candidats"])))


if __name__ == "__main__":
    main()
