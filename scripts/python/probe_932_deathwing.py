"""Probe #932 -- confronter LIVE les DEUX faces de degat du passif `Deathwing`
(`darkaTerminator` << Baraqiel >>, `TriggeredAbilityType 0x4dd = 1245`).

Ce que le natif fait, et que ce probe MESURE plutot que de le supposer :

    CreateTrigger   = On(9 = Attack, ownerNeedsToBeAlive: true) & get_OwnerIsTarget & WasBlock()
    CreateBehaviour = If( HasEffect(Owner, 0x526 = 1318, onlyActive: false, Both),
                          IncreaseEffectLevel(EffectFromOwner(Owner, 1318), +1, SANS cap),
                          AddEffect(1318, AbilityStateReference, Owner, Owner,
                                    turns = TurnsFromRounds(1)) )

et, sur l'effet 1318 :

    CreateEffectDamageMalusForDefense = ForSubtraction( get_OwnerIsTarget,
        GetEffectAmount(ConfigVar(0x12 = dmgReduction), isDefense: true) )
    CreateEffectDamageBonusForAttack  = ForAddition( get_OwnerIsActor
                                                     & (IsMeleeAttack | NOT IsNormalAttack),
        GetEffectAmount(ConfigVar(8 = extraDmg), isDefense: false) )
    GetEffectAmount(base, isDefense)  = If( GetDoubleEffectCondition(isDefense),
                                            Double(Multiply(base, EffectLevel)),
                                            Multiply(base, EffectLevel) )

=================================================================================================
LES DEUX BRAS
=================================================================================================

`defense` -- `darkaTerminator` est l'ENNEMI (a-unit), `--block-target 100,...` force son blocage.
    Un `aiturn` le sort de son DEEP STRIKE (`TeleportStrike_TeleportingIn` le rend non-ciblable
    tant qu'il n'a pas agi -- ce n'est PAS un obstacle, c'est un tour a jouer). Puis DEUX attaques
    de melee successives :
      * l'attaque #1 pose l'effet (niveau 1) A SA CLOTURE -- elle n'en beneficie donc PAS ;
      * l'attaque #2 SUBIT `dmgReduction x 1` et fait monter le niveau a 2.
    Le discriminant est l'attaque #2 : sans le port, le degat offline la SUR-ESTIME.

`attaque` -- `darkaTerminator` est DE MON COTE (p-unit), `--block-player 100,...`. Il agit (sort du
    Deep Strike), l'IA adverse le frappe, il bloque -> l'effet se pose ; au tour suivant SON attaque
    de melee porte `+extraDmg x niveau`. Bras GARDE par une mesure : si l'IA ne l'a pas frappe (ou
    si aucun blocage n'a eu lieu), le bras rend `verdict: indisponible` -- JAMAIS un vert par
    defaut.

Chaque bras REJOUE offline le MEME enchainement depuis la capture prise AVANT la 1re attaque, avec
le MEME flux RNG, et compare le degat COUP PAR COUP.

MUTANTS (`--mutate <nom>`) -- chacun doit MORDRE, et chacun EST un etat reel du depot :
  * `trigger` : retire `ABILITY_TRIGGERS["Deathwing"]`  -> le niveau ne monte jamais (etat d'avant
                cette tranche cote accumulation) ;
  * `effet`   : retire `EFFECT_CLASSES["Deathwing"]`    -> l'effet est materialise mais INERTE
                (etat d'avant cette tranche cote magnitude) ;
  * `double`  : force `_double_effect_condition` a FAUX -> la moitie du bonus quand la condition
                tient (mutant de FINESSE, celui qui distingue un port juste d'un port a moitie).

CLI (depuis scripts/python) :
  python probe_932_deathwing.py
  python probe_932_deathwing.py --bras attaque
  python probe_932_deathwing.py --mutate trigger

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                    # noqa: E402

BOARD = "MC1_67"
SEED = "4321"
CARRIER = "darkaTerminator"      # Baraqiel -- le SEUL porteur HERO du passif `Deathwing`
ATT_A = "tauAunShi"              # 5 coups melee, profil Power
ATT_B = "astraBullgryn"          # 4 coups melee, profil Physical -- grande-alliance IMPERIAL
#: ATTAQUANT de grande-alliance **CHAOS** (`GrandAllianceId` du gameconfig, d'ou le `UnitTrait
#: 0x7ea` que le BattleConfiguration ajoute) : quand LUI frappe, le premier disjoint de
#: `GetDoubleEffectCondition` tient et la reduction du porteur DOUBLE.
#:
#: ⚠ LE CHOIX DE L'UNITE EST UNE MESURE D'ATTRIBUTION, pas un gout. Les DEUX autres Chaos melee du
#: pool font diverger le port pour des causes qui n'ont RIEN a voir avec `Deathwing` :
#:   * `blackTerminator` -- trait `LetTheGalaxyBurn` (effet 1477, `CreateAdditionalHits`) + trait
#:     `TerminatorArmour` : ecart **-1455** quand il ATTAQUE, **-35** quand il est FRAPPE ;
#:   * `worldKharn`      -- son attaque supplementaire fait monter le stack natif a 3 la ou le port
#:     reste a 2 : c'est le RESIDU DEJA NOMME du module (une attaque declenchee par un TRIGGER ne
#:     traverse pas `On(9)` cote port), ecart **-4915**.
#: `deathBlightbringer` (Chaos, melee pur, ni l'un ni l'autre) rend `ecart = 0` et fait MORDRE les
#: deux mutants. Les deux ecarts ci-dessus sont des RESIDUS NOMMES, hors perimetre de cette tranche.
ATT_CHAOS = "deathBlightbringer"
#: VICTIME Chaos du bras `attaqueChaos` -- `worldKharn` convient ICI (le residu ci-dessus porte sur
#: son role d'ATTAQUANT, pas de cible) et n'a ni `TerminatorArmour` ni `LetTheGalaxyBurn`.
VICTIME_CHAOS = "worldKharn"
#: `darkaAsmodai` -- `FactionId == DarkAngels`, melee pur. Pose sur l'anneau du porteur, il arme le
#: SECOND disjoint (`UnitsFromFaction(AdjacentFriends(Owner), DarkAngels)` non vide).
ALLIE_DA = "darkaAsmodai"
SPECTATEUR = "spaceStormcaller"  # n'attaque JAMAIS : il empeche la CLOTURE automatique du tour
CIBLE_DU_CARRIER = "tauAunShi"   # bras `attaque` : ce que Baraqiel frappe
DEATHWING_EFFECT = 1318
#: #1073 -- VARIANTE `knight`. `DeathwingKnightAbility` DERIVE de `DeathwingAbility` et n'override
#: QUE `$$GetEffectType` (`return 0x5e8` = 1512) ; l'effet est la MEME classe native
#: `DeathwingEffect`, construite avec `triggeringAbilityType = 0x5e6` (= 1510). Le montage est donc
#: LE MEME a trois valeurs pres -- porteur, `EffectType`, cle de registre --, ce qui est
#: exactement la raison de ne PAS ecrire un second probe : un seul corps natif, un seul probe.
#: Le porteur est le jumeau NPC du summon `darkaSmnTerminator` (MEME `visualId`), amene par
#: `--explicit-stats` (table `units.npc[].stats[]`, 45 paliers) -- recette #1052.
CARRIER_KNIGHT = "darkaNpc3Terminator:45"
DEATHWING_KNIGHT_EFFECT = 1512
#: VARIANTE COURANTE, posee par `--variante` dans `main()`. Les deux bras et le rejeu la LISENT :
#: c'est ce qui garde le montage unique. `cle` indexe `ABILITY_TRIGGERS` / `EFFECT_CLASSES`
#: (un nom de `TriggeredAbilityType` cote gauche, un nom d'`EffectType` cote droit -- deux enums).
VARIANTE = "baraqiel"
BUILD_EXTRA: list = []
CLE = "Deathwing"
TERMINATOR_REDUCE = 1147
#: `EffectType.TeleportStrike_TeleportingIn` = 1035 -- le marqueur de Deep Strike du porteur, qui le
#: rend NON-CIBLABLE tant qu'il n'a pas agi. LU dans `frida/enums.tsv`, jamais devine : l'ordinal
#: voisin 1572 est `TitanhammerSquad_ExtraBlockDamage` et le lire faisait rendre un faux << sorti >>.
TELEPORTING_IN = 1035
#: `maxPump` d'`aiPlayByUnit` -- le DEFAUT de `rl_duel.py` (`--maxpump`, 2000). ⚠ Ce n'est pas un
#: reglage de confort : a 40, l'IA ne porte AUCUNE attaque (six tours joues, PV inchanges des deux
#: cotes) et le bras `attaque` rendait `indisponible` pour une cause qui n'avait rien a voir avec
#: le port. MESURE, pas supposition.
MAX_PUMP = 2000


# --------------------------------------------------------------------------- montage live


def _build(seed, board, p_units, a_units, extra, hp="400000"):
    """`hp=None` = PV NATIFS (aucun `--hp-*`).

    ⚠ CE N'EST PAS UN DETAIL DE CONFORT -- c'est une MESURE : a `--hp-target/--hp-player 400000`,
    l'IA ne porte AUCUNE attaque (six tours joues, PV inchanges des deux cotes), et le bras qui
    depend d'elle rendait `indisponible` sans qu'on sache pourquoi. Les PV natifs la font mordre du
    premier tour. Le bras `defense`, lui, garde le plafond : il pilote SES attaques lui-meme et a
    besoin que la cible survive aux deux."""
    sf = ROOT / "logs" / "runners" / ("p932-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", board, "--rank", "17",
         "--p-units", ",".join(p_units), "--a-units", ",".join(a_units),
         *(["--hp-target", hp, "--hp-player", hp] if hp else []), "--crit", "0,0",
         "--crit-target", "0,0", "--no-ai", *BUILD_EXTRA, *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-800:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _by_vis(dv, vis):
    """⚠ Le PALIER est coupe : un porteur `--explicit-stats` s'ecrit `darkaNpc3Terminator:45` au
    build (forme exigee VERBATIM par `--p-units`/`--place`), mais le `decisionView` publie le
    `visualId` NU (`darkaNpc3Terminator`). Mesure #1073, pas supposition."""
    court = str(vis).split(":")[0]
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == court), None)


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _effect_level(dv, uid, effect_type=None):
    """(present, niveau) de l'instance `effect_type` sur `uid`. `niveau` = `EffectComponent+0x68`,
    le facteur que `DSLFormulas.EffectLevel` relit dans `GetEffectAmount`.

    `effect_type=None` -> l'effet de la VARIANTE courante (#1073), jamais un 1318 en dur."""
    if effect_type is None:
        effect_type = DEATHWING_EFFECT
    for e in ((_unit(dv, uid) or {}).get("effects") or []):
        et = e.get("effectType")
        if et is not None and int(et) == int(effect_type):
            return True, e.get("level")
    return False, None


def _normal_attack_id(dv, uid):
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _move(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _hp(dv, uid):
    u = _unit(dv, uid)
    return None if u is None else int(u.get("hp", 0))


def _attack(rpc, rid, cid, tid, ab):
    """Attaque NORMALE live + ledger par coup (`Amount` des evenements de la cascade)."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ab)}, "captureEvents": True}, 150)
    hits = []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and int(td.get("Target_Id", td.get("TargetId", tid)) or tid) == int(tid):
                hits.append(int(td["Amount"]))
    return res, hits


# --------------------------------------------------------------------------- rejeu offline


def _port_level(state, uid, effect_type=None):
    if effect_type is None:
        effect_type = DEATHWING_EFFECT              # variante courante (#1073)
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(uid), []):
        if e.effect_type == effect_type and not e.consumed:
            return int(e.level or 0)
    return None


def _replay(cap, board, paires, mutate=None):
    """Rejoue les attaques `paires = [(attaquant, cible), ...]` ENCHAINEES sur le MEME `State` et le
    MEME flux RNG. C'est l'ENCHAINEMENT qui compte : le port n'est exerce que si l'attaque #2 voit
    l'etat laisse par l'attaque #1. Un rejeu attaque-par-attaque depuis une capture FRAICHE serait
    tautologique (le `decisionView` d'apres porte deja le stack)."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki import deathwing as DW

    # ⚠ LES MUTANTS SONT POSES **AVANT** `load_state`, et l'ordre est LOAD-BEARING : `EFFECT_CLASSES`
    # n'est lu qu'a la CREATION des instances d'effet (`EffectFactory.create`), donc un `pop` fait
    # apres `load_state` arrive TROP TARD pour un effet deja present au seed. Mesure : dans cet
    # ordre-la, le mutant `effet` du bras `attaque` rendait EGAL -- un FAUX VERT, exactement la
    # forme que le brief nomme (<< un mutant inerte >>). Le bras `defense`, lui, mordait quand meme,
    # parce que son effet est pose PENDANT le rejeu : deux bras, deux regimes, un seul ordre correct.
    saved_trig = saved_eff = saved_cond = None
    if mutate == "trigger":
        saved_trig = ABILITY_TRIGGERS.pop(CLE, None)
        assert saved_trig is not None, "MUTANT INOPERANT : ABILITY_TRIGGERS[%r] absent" % CLE
    elif mutate == "effet":
        saved_eff = EFFECT_CLASSES.pop(CLE, None)
        assert saved_eff is not None, "MUTANT INOPERANT : EFFECT_CLASSES[%r] absent" % CLE
    elif mutate == "double":
        saved_cond = DW.DeathwingEffect._double_effect_condition
        DW.DeathwingEffect._double_effect_condition = classmethod(
            lambda cls, ctx, **kw: False)
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        out = []
        for att, tgt in paires:
            e = st.get_entity(int(tgt))
            hc = e.get_component(HealthComponent)
            h0 = int(hc.hp)
            runner.apply(AttackUnitMessage(int(att), int(tgt)))
            last = runner.damage_handler.last or {}
            out.append({"attacker": int(att), "target": int(tgt), "hp_delta": h0 - int(hc.hp),
                        "total": last.get("total"), "per_hit": last.get("per_hit")})
        niveaux = {int(u): _port_level(st, int(u))
                   for u in {p[1] for p in paires} | {p[0] for p in paires}}
    finally:
        if saved_trig is not None:
            ABILITY_TRIGGERS[CLE] = saved_trig
        if saved_eff is not None:
            EFFECT_CLASSES[CLE] = saved_eff
        if saved_cond is not None:
            DW.DeathwingEffect._double_effect_condition = saved_cond
    return {"attacks": out, "niveaux": niveaux}


# --------------------------------------------------------------------------- bras `defense`


def _bras_defense(rpc, board_id, seed, mutate, verbose, att_b=None, allie_da=None, nom="defense"):
    from engine.entities.pathfinding.board import Board

    att_b = att_b or ATT_B
    # GEOMETRIE DRIVEE au BUILD (`--place` / `--a-place`) : le porteur est pose au CENTRE et DEUX
    # attaquants sur son anneau, pour que l'IA ait une raison de le faire AGIR -- c'est la seule
    # facon de le sortir de son Deep Strike (`TeleportStrike_TeleportingIn` = 1035). Le laisser a
    # son SpawnPoint le fait rester non-ciblable, et l'attaque rend alors une cascade VIDE (mesure).
    # Voisins de (3,4) sur MC1_67, LUS au `boardGraph` : (2,3) (2,4) (3,3) (3,5) (4,3) (4,4).
    a_units = [CARRIER] + ([allie_da] if allie_da else [])
    extra = ["--block-target", "100,50", "--block-player", "0,0",
             "--a-place", "%s:3,4" % CARRIER,
             "--place", "%s:2,4" % ATT_A, "--place", "%s:3,3" % att_b,
             "--place", "%s:0,0" % SPECTATEUR]
    if allie_da:
        # l'AMI Dark Angel se pose sur l'anneau du porteur -> `AmountIsGreaterThanZero(
        # UnitsFromFaction(AdjacentFriends(Owner), DarkAngels))` devient VRAI, et le DOUBLEMENT
        # s'arme par le SECOND disjoint (celui que le bras `chaos` n'exerce pas).
        extra += ["--a-place", "%s:4,4" % allie_da]
    rid, sf, err = _build(seed, board_id, [ATT_A, att_b, SPECTATEUR], a_units, extra)
    if rid is None:
        return {"verdict": "indisponible", "cause": "build KO : %s" % err}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _view(rpc, rid, inactive=True)
        ids = {}
        for v in [CARRIER, ATT_A, att_b, SPECTATEUR] + ([allie_da] if allie_da else []):
            u = _by_vis(dv, v)
            if u is None:
                return {"verdict": "indisponible", "cause": "unite absente : %s" % v}
            ids[v] = int(u["id"])
        # `TeleportStrike_TeleportingIn` (`EffectType` 1035) : le porteur est NON-CIBLABLE tant
        # qu'il n'a pas agi, et l'attaque rend alors une cascade VIDE. Il faut DEUX appels
        # d'`aiPlayByUnit` -- MESURE, pas supposition : le premier joue MON tour (`finalPlayer` 3 ->
        # 4), le second celui de l'ADVERSAIRE, et c'est celui-la qui fait agir le porteur. On boucle
        # jusqu'a la sortie, avec un PLAFOND : depasser le plafond rend `indisponible`, pas un vert.
        # ⚠ 1035 est LU dans `frida/enums.tsv` -- l'ordinal voisin 1572 est
        # `TitanhammerSquad_ExtraBlockDamage`, et le lire a fait rendre un faux << sorti >>.
        for _ in range(4):
            present, _ = _effect_level(dv, ids[CARRIER], TELEPORTING_IN)
            if not present:
                break
            rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                                 "maxPump": MAX_PUMP, "captureEvents": True}, 300)
            dv = _view(rpc, rid, inactive=True)
        present, _ = _effect_level(dv, ids[CARRIER], TELEPORTING_IN)
        if present:
            return {"verdict": "indisponible",
                    "cause": "le porteur est encore en Deep Strike (1035) apres 4 tours d'IA"}
        if dv.get("currentPlayer") is None:
            return {"verdict": "indisponible", "cause": "currentPlayer non publie"}
        cible = _unit(dv, ids[CARRIER])
        if cible is None:
            return {"verdict": "indisponible", "cause": "porteur absent du view"}
        ctile = board.id_at(int(cible["pos"]["col"]), int(cible["pos"]["row"]))
        occupees = {(int(u["pos"]["col"]), int(u["pos"]["row"]))
                    for u in (dv.get("units") or []) if u.get("pos")}
        ring = [t for t in board.neighbours(ctile)
                if board.coord(t) not in occupees or board.coord(t) in
                {(int(_unit(dv, ids[v])["pos"]["col"]), int(_unit(dv, ids[v])["pos"]["row"]))
                 for v in (ATT_A, att_b)}]
        if len(ring) < 2:
            return {"verdict": "indisponible", "cause": "anneau trop pauvre (%d)" % len(ring)}
        for i, v in enumerate([ATT_A, att_b]):
            _move(rpc, rid, ids[v], *board.coord(ring[i]))
        dv = _view(rpc, rid, inactive=True)
        na = {v: _normal_attack_id(dv, ids[v]) for v in (ATT_A, att_b)}
        if any(x is None for x in na.values()):
            return {"verdict": "indisponible", "cause": "attaque normale introuvable : %s" % na}

        cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        avant, _ = _effect_level(_view(rpc, rid, inactive=True), ids[CARRIER])

        natif = []
        for v in (ATT_A, att_b):
            _r, hits = _attack(rpc, rid, ids[v], ids[CARRIER], na[v])
            d = _view(rpc, rid, inactive=True)
            pres, lvl = _effect_level(d, ids[CARRIER])
            # Une cascade VIDE n'est pas << 0 degat >>, c'est une attaque qui n'a pas eu lieu : la
            # confondre ferait rendre un DIVERGE qui accuse le port au lieu du montage.
            if not hits:
                return {"verdict": "indisponible",
                        "cause": "cascade VIDE pour %s -> l'attaque n'a pas eu lieu (ok=%s)"
                                 % (v, _r.get("ok"))}
            natif.append({"attacker": v, "hits": hits, "total": sum(hits),
                          "deathwing_apres": (pres, lvl)})
        port = _replay(cap, board, [(ids[ATT_A], ids[CARRIER]), (ids[att_b], ids[CARRIER])],
                       mutate=mutate)
        # LE NIVEAU EST UNE MESURE A PART ENTIERE : deux ports peuvent rendre le meme degat sur ce
        # montage et diverger sur le stack. On confronte donc `EffectComponent+0x68` des deux cotes.
        niv_natif = natif[-1]["deathwing_apres"][1]
        niv_port = port["niveaux"].get(int(ids[CARRIER]))
        return _verdict(nom, natif, port,
                        {"deathwing_avant": avant, "porteur": int(ids[CARRIER]),
                         "niveau_natif_fin": niv_natif, "niveau_port_fin": niv_port,
                         "niveau_egal": (niv_natif is not None and niv_natif == niv_port)},
                        verbose)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


# --------------------------------------------------------------------------- bras `attaque`


def _bras_attaque(rpc, board_id, seed, mutate, verbose, chaos=False, nom="attaque"):
    """Le porteur est de MON cote : il agit (sort du Deep Strike), encaisse un tour d'IA (ou il
    bloque, `--block-player 100,...`), puis ATTAQUE avec `+extraDmg x niveau`.

    `chaos=True` : la CIBLE du porteur est de grande-alliance CHAOS -> le premier disjoint de
    `GetDoubleEffectCondition` tient, et le bonus est DOUBLE. C'est le SEUL regime ou le mutant
    `double` peut mordre sur cette face.

    ⚠ Ce bras DEPEND de l'IA adverse : si elle ne frappe pas Baraqiel, ou si aucun coup n'est
    bloque, l'effet n'existe pas et il n'y a RIEN a confronter. Le bras rend alors
    `verdict: indisponible` avec sa cause -- jamais un vert par defaut."""
    from engine.entities.pathfinding.board import Board

    victime = VICTIME_CHAOS if chaos else CIBLE_DU_CARRIER
    autre = ATT_B
    # MEME geometrie DRIVEE que le bras `defense`, camps INVERSES : le porteur au centre, les deux
    # ennemis sur son anneau -- sans placement, l'IA n'a aucune raison de le frapper et le bras
    # rendait `indisponible` a chaque coup (mesure).
    rid, sf, err = _build(seed, board_id, [CARRIER], [victime, autre],
                          ["--block-player", "100,50", "--block-target", "0,0",
                           "--place", "%s:3,4" % CARRIER,
                           "--a-place", "%s:2,4" % victime, "--a-place", "%s:3,3" % autre],
                          hp=None)                      # PV NATIFS -- cf. `_build` (mesure)
    if rid is None:
        return {"verdict": "indisponible", "cause": "build KO : %s" % err}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _view(rpc, rid, inactive=True)
        ids = {}
        for v in [CARRIER, victime, autre]:
            u = _by_vis(dv, v)
            if u is None:
                return {"verdict": "indisponible", "cause": "unite absente : %s" % v}
            ids[v] = int(u["id"])
        # Boucle d'IA : un appel joue MON tour (le porteur AGIT -> il sort du Deep Strike), le
        # suivant celui de l'adversaire (il frappe, le porteur BLOQUE -> l'effet se pose). PLAFOND
        # explicite : le depasser rend `indisponible`, JAMAIS un vert par defaut.
        pres = lvl = None
        for _ in range(6):
            rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                                 "maxPump": MAX_PUMP, "captureEvents": True}, 300)
            dv = _view(rpc, rid, inactive=True)
            pres, lvl = _effect_level(dv, ids[CARRIER])
            if pres and lvl:
                break
        if not pres or not lvl:
            return {"verdict": "indisponible",
                    "cause": "l'IA n'a pose aucun Deathwing sur le porteur (pres=%s lvl=%s) -- "
                             "aucun blocage subi, rien a confronter" % (pres, lvl)}
        # amener le porteur au contact de sa cible
        vic = _unit(dv, ids[victime])
        if vic is None:
            return {"verdict": "indisponible", "cause": "cible absente"}
        vtile = board.id_at(int(vic["pos"]["col"]), int(vic["pos"]["row"]))
        occupees = {(int(u["pos"]["col"]), int(u["pos"]["row"]))
                    for u in (dv.get("units") or []) if u.get("pos")
                    and int(u.get("id", -1)) != int(ids[CARRIER])}
        ring = [t for t in board.neighbours(vtile) if board.coord(t) not in occupees]
        if not ring:
            return {"verdict": "indisponible", "cause": "anneau LIBRE vide autour de la cible"}
        _move(rpc, rid, ids[CARRIER], *board.coord(ring[0]))
        dv = _view(rpc, rid, inactive=True)
        na = _normal_attack_id(dv, ids[CARRIER])
        if na is None:
            return {"verdict": "indisponible", "cause": "attaque normale du porteur introuvable"}
        cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        _r, hits = _attack(rpc, rid, ids[CARRIER], ids[victime], na)
        if not hits:
            return {"verdict": "indisponible",
                    "cause": "cascade VIDE -> l'attaque du porteur n'a pas eu lieu (ok=%s)"
                             % _r.get("ok")}
        natif = [{"attacker": CARRIER, "hits": hits, "total": sum(hits),
                  "deathwing_avant": (pres, lvl)}]
        port = _replay(cap, board, [(ids[CARRIER], ids[victime])], mutate=mutate)
        return _verdict(nom, natif, port,
                        {"deathwing_avant": (pres, lvl), "victime": victime}, verbose)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


# --------------------------------------------------------------------------- verdict


def _verdict(bras, natif, port, extra, verbose):
    lignes, ok = [], True
    for i, (n, p) in enumerate(zip(natif, port["attacks"])):
        nt, pt = int(n["total"]), (None if p["total"] is None else int(p["total"]))
        egal = (pt is not None and nt == pt)
        ok = ok and egal
        lignes.append({"rang": i + 1, "attacker": n["attacker"], "natif": nt, "port": pt,
                       "ecart": (None if pt is None else pt - nt), "egal": egal,
                       "natif_hits": n["hits"], "port_hits": p.get("per_hit")})
    # Le NIVEAU compte dans le verdict au meme titre que le degat : `niveau_egal` a False rend
    # DIVERGE meme si les totaux coincident (ils le peuvent sur un montage court).
    if extra.get("niveau_egal") is False:
        ok = False
    out = {"bras": bras, "verdict": "EGAL" if ok else "DIVERGE", "lignes": lignes,
           "port_niveaux": port["niveaux"], **extra}
    if verbose:
        print("[932] bras=%s" % bras)
        for k, v in extra.items():
            print("   %-24s %s" % (k, v))
        for l in lignes:
            print("   #%d %-16s natif=%-8s port=%-8s ecart=%-6s %s"
                  % (l["rang"], l["attacker"], l["natif"], l["port"], l["ecart"],
                     "OK" if l["egal"] else "<<< DIVERGE"))
        print("   niveaux Deathwing cote port : %s" % port["niveaux"])
        print("[932] VERDICT: %s" % out["verdict"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", default="defense",
                    choices=("defense", "chaos", "amiDA", "attaque", "attaqueChaos", "both"))
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--mutate", default=None, choices=("trigger", "effet", "double"))
    ap.add_argument("--variante", default="baraqiel", choices=("baraqiel", "knight"),
                    help="baraqiel: le HERO `darkaTerminator` (passif `Deathwing` 1245, effet "
                         "1318) ; knight: le jumeau NPC du summon `darkaSmnTerminator` (passif "
                         "`DeathwingKnight` 1510, effet 1512), amene par `--explicit-stats`. UN "
                         "SEUL corps natif, un seul probe (#1073).")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.variante == "knight":
        # `DeathwingKnightAbility` n'override QUE `$$GetEffectType` : trigger, behaviour et
        # `GetEffect` viennent litteralement de `DeathwingAbility`. Les trois valeurs ci-dessous
        # sont donc TOUT le delta du montage.
        global CARRIER, DEATHWING_EFFECT, BUILD_EXTRA, CLE, VARIANTE                # noqa: PLW0603
        VARIANTE = "knight"
        CARRIER = CARRIER_KNIGHT
        DEATHWING_EFFECT = DEATHWING_KNIGHT_EFFECT
        CLE = "DeathwingKnight"
        BUILD_EXTRA = ["--explicit-stats", CARRIER_KNIGHT]
    rpc = _mkrpc()
    res = {}
    tous = (("defense", "chaos", "amiDA", "attaque", "attaqueChaos")
            if a.bras == "both" else (a.bras,))
    for bras in tous:
        if bras in ("attaque", "attaqueChaos"):
            # `attaqueChaos` : la CIBLE du porteur est CHAOS -> le premier disjoint de
            # `GetDoubleEffectCondition` tient cote ATTAQUE, et c'est le SEUL regime ou le mutant
            # `double` peut mordre sur cette face.
            res[bras] = _bras_attaque(rpc, a.board, a.seed, a.mutate, not a.json,
                                      chaos=(bras == "attaqueChaos"), nom=bras)
        else:
            # `chaos`  -> le 2e attaquant est CHAOS : disjoint 1 (`HasTrait(Actor, 0x7ea)`) ;
            # `amiDA`  -> un ami Dark Angel adjacent au porteur : disjoint 2 (le compteur).
            res[bras] = _bras_defense(
                rpc, a.board, a.seed, a.mutate, not a.json,
                att_b=(ATT_CHAOS if bras == "chaos" else None),
                allie_da=(ALLIE_DA if bras == "amiDA" else None), nom=bras)
    if a.json:
        print(json.dumps(res, indent=1))
    if not a.json:
        print("[932] variante=%s porteur=%s effet=%s cle=%s"
              % (VARIANTE, CARRIER, DEATHWING_EFFECT, CLE))
    verdicts = [v.get("verdict") for v in res.values()]
    if "indisponible" in verdicts:
        return 2                                     # verdict INDISPONIBLE, jamais un vert
    return 0 if all(v == "EGAL" for v in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
