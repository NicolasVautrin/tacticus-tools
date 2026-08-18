"""PROBE #577 -- `AdaptiveStrategy` (1005, `necroWarden` « Makhotep ») CONFRONTEE au natif.

LE CRITERE, en une question binaire : **apres un cast de 1005, l'allie NON-Hero adjacent a-t-il
AGI ?** -- posee au NATIF et au PORT sur le MEME etat de depart. Avant ce port, 1005 etait absente
d'`ABILITY_CLASSES` : `AbilityHandler` l'ignorait, donc le port repondait « non » -- 0 degat,
0 effet, AUCUNE erreur. La DECISION pouvait la choisir, l'EXECUTION ne faisait rien.

LE MONTAGE, et pourquoi il est CE montage-la
--------------------------------------------
Le gate dynamique de 1005 est `HasTrait(target, Hero) -> TargetMatchesDynamicRule`
(`...AdaptiveStrategyAbility$$GetDynamicInvalidTargetReason`) : en bataille de lineup TOUTE unite
deployee porte `Hero`, donc le cast n'a AUCUNE cible legale. Le porteur d'un allie NON-Hero est un
SUMMON -- et le pool en produit un, Necrons, sans aucune greffe : `necroOverlord` caste
`ResurrectionOrb` (1009, DEJA portee) qui spawne des `necroSmnWarrior` sur les tuiles adjacentes.

    1. build `necroWarden` + `necroOverlord` (les deux dans le pool rank 17) ;
    2. l'Overlord caste 1009 -> N `necroSmnWarrior` NON-Hero apparaissent autour de lui ;
    3. le Warden se DEPLACE sur une tuile adjacente a l'un d'eux (on FORCE la configuration --
       on ne se declare pas « bloque par la geometrie de spawn ») ;
    4. CAPTURE de l'etat pre-cast -> rejeu OFFLINE par la voie COMPLETE
       (`Runner.apply(ActiveAbilityMessage)` : gates de ciblage, `On(0x2a)`, behaviour, flags)
       -> cast LIVE -> RECHARGEMENT de l'etat natif d'apres -> comparaison terme a terme.

⚠ LE SUMMON A DEJA FINI SON TOUR quand il apparait -- `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`
appelle `FinishUnitTurn(spawned, isTerminated: true)`. C'est precisement ce qui rend l'etape (3) du
behaviour DISCRIMINANTE : `PerformAIAction(..., resetTurnFlags: 1)` sauvegarde, EFFACE puis restaure
ses flags de tour -- l'unite agit MEME si elle avait deja fini, et l'action ne consomme pas son tour.
Un port qui aurait oublie ce booleen rendrait un no-op parfaitement silencieux.

ETAGES
------
  E0  offline pur : registre, masque, `AbilityAttackType`, FORME de l'arbre (4 noeuds dans l'ordre
      du `op_Addition`), et le DISCRIMINANT DE SELECTEUR -- le noeud (4) balaie TOUS les allies
      non-Hero, le noeud (2) les seuls ADJACENTS.
  E1  le gate de cible, LIVE : le summon est une cible legale, un allie HERO adjacent ne l'est PAS.
      Sans ce bras, le port pourrait accepter n'importe quel allie sans qu'aucun test ne rougisse.
  E2  la CONFRONTATION : etat natif d'apres vs etat porte d'apres, terme a terme.
  E3  NET-ZERO : aucune instance de 1012 `AdaptiveStrategy_DmgOverride` ne subsiste, des DEUX cotes
      (le noeud (4) retire ce que le noeud (2) a pose).
  E4  ANTI-TAUTOLOGIE : le cast a REELLEMENT execute cote port (ability au registre, gate non
      declenche, au moins un override pose et une action jouee).
  E5/E6 DECOMPOSITION de l'ecart de TUILE (sensibilite au montant, borne du PRNG).
  E7  le noeud (1) sur un observable PERSISTANT : les porteurs de 1011.
  E8  le RE-CIBLAGE de 1011 sur son observable de CONSEQUENCE -- la stat MOUVEMENT des unites que
      le natif a SORTIES du selecteur geometrique (#577-r1).

⚠ Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268). Sorties ASCII, aucune VA en dur.
RE : `docs/rl/case-577-adaptive-strategy.md`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as L  # noqa: E402

LOGS = ROOT / "logs" / "probe577"
STATE = LOGS / "state_577_adaptive_strategy.json"     # SORTIE -> logs/ (#349), JAMAIS data/

ADAPTIVE = 1005           # ActiveAbilityType.AdaptiveStrategy
RESURRECTION_ORB = 1009   # ActiveAbilityType.ResurrectionOrb (le producteur de summons)
OVERRIDE = 1012           # EffectType.AdaptiveStrategy_DmgOverride
RELENTLESS = 1004         # TriggeredAbilityType.RelentlessMarch
MARCH_EFFECT = 1011       # EffectType.RelentlessMarch_Effect (+1 Mouvement, `turns` = 1)
WARDEN = "necroWarden"
OVERLORD = "necroOverlord"
BOARD = "MC1_67"
SEED = "777"
P_UNITS = WARDEN + "," + OVERLORD
A_UNITS = "ultraTitus,ultraInceptorSgt"


# --------------------------------------------------------------------------- transport

def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result")


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def build(seed_value: str = SEED, board_id: str = BOARD) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17",
               "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(STATE)])
    if not STATE.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure): "
                         + (p.stderr or p.stdout or "")[-800:])
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- lectures

def units(rid) -> dict:
    out = {}
    for u in (rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                   "includeInactive": True}, 90).get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = {"vid": u.get("visualId"), "ctrl": u.get("ctrl"),
                            "pos": (p.get("col"), p.get("row")), "alive": u.get("alive"),
                            "hp": u.get("hp"), "hasAction": u.get("hasAction"),
                            "team": u.get("team")}
    return out


def capture(rid) -> dict:
    """Les CINQ canaux dont `load_state` a besoin pour materialiser l'etat offline."""
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                        "includeInactive": True}, 90),
            "ob": rpc("observeBattle", {"runnerId": rid}, 40),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
            "tm": rpc("tileMeta", {"runnerId": rid}, 60),
            "bg": rpc("boardGraph", {"runnerId": rid}, 60)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def legal_unit_targets(rid, caster, ability) -> set:
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster,
                                "abilityType": ability}, 90) or {}
    for u in (at.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ability:
                continue
            return {t.get("targetId") for t in (a.get("targets") or [])
                    if t.get("targetId") is not None}
    return set()


def offline_view(st, uid: int) -> dict:
    """Ce que l'ETAT PORTE dit d'une unite -- la forme EXACTE que rend le canal live, pour que la
    comparaison soit terme a terme."""
    from engine.runner.components import (HealthComponent, PositionComponent, UnitComponent,
                                          UnitFlagsComponent)
    e = st.get_entity(int(uid))
    if e is None:
        return {"pos": None, "alive": None, "hp": None}
    pc = e.get_component(PositionComponent)
    uc = e.get_component(UnitComponent)
    hc = e.get_component(HealthComponent)
    fl = e.get_component(UnitFlagsComponent)
    return {"pos": ((pc.col, pc.row) if pc is not None else None),
            "alive": (uc.alive if uc is not None else None),
            "hp": (hc.hp if hc is not None else None),
            "flags": (sorted(fl.active()) if (fl is not None and hasattr(fl, "active")) else None)}


def override_carriers(st) -> list:
    """Les unites portant une instance NON consommee de 1012, cote port."""
    return sorted(uid for uid, effs in (st.effects.by_unit or {}).items()
                  if any(int(getattr(x, "effect_type", -1)) == OVERRIDE and not x.consumed
                         for x in effs))


def _native_effect_rows(cap):
    """Les lignes d'effet du canal NATIF, avec leur PORTEUR.

    ⚠ LE CANAL EST `decisionView.units[].effects` -- PAR UNITE. Une premiere version lisait
    `decisionView.effects` (une liste a la RACINE) : ce champ N'EXISTE PAS, donc toute question
    posee a ce canal rendait `[]`, et ce `[]` se lisait comme « aucun porteur ». C'est le TEMOIN
    NON NUL ci-dessous qui l'a montre -- l'accord port/natif etait un accord en regime DEGENERE."""
    for u in (cap["dec"].get("units") or []):
        uid = u.get("id")
        for e in (u.get("effects") or []):
            if isinstance(e, dict) and uid is not None:
                yield int(uid), e


def _row_type(e) -> int:
    """`EffectType` d'une ligne du canal, quel que soit le nom du champ publie."""
    for k in ("effectType", "type", "effectTypeId"):
        if e.get(k) is not None:
            try:
                return int(e[k])
            except (TypeError, ValueError):
                pass
    return -1


def native_carriers(cap, effect_type: int) -> list:
    """Porteurs d'un `EffectType` cote NATIF (`decisionView.units[].effects`)."""
    return sorted({uid for uid, e in _native_effect_rows(cap)
                   if _row_type(e) == int(effect_type)})


def native_effect_census(cap) -> dict:
    """TEMOIN NON NUL du canal d'effets natif. Un `[]` rendu par `native_carriers` ne prouve RIEN
    tant qu'on n'a pas montre que la lecture VOIT des effets et sait en nommer le TYPE -- « accord
    en regime DEGENERE = zero preuve ». Il a DEJA servi : il a fait rougir la premiere version du
    probe, qui interrogeait un champ inexistant."""
    rows = list(_native_effect_rows(cap))
    return {"n": len(rows), "with_owner": len(rows),
            "keys": sorted({k for _u, e in rows for k in e}),
            "typed": sum(1 for _u, e in rows if _row_type(e) >= 0),
            "types": sorted({_row_type(e) for _u, e in rows})}


def port_carriers_of(st, effect_type: int) -> list:
    """Porteurs d'un `EffectType` cote PORT (instances NON consommees)."""
    return sorted(uid for uid, effs in (st.effects.by_unit or {}).items()
                  if any(int(getattr(x, "effect_type", -1)) == int(effect_type) and not x.consumed
                         for x in effs))


# ------------------------------------------------------- E8 : l'observable STAT du re-ciblage

def native_stat(cap, uid: int, stat_type: int):
    """La valeur RESOLUE d'un stat cote NATIF, lue dans `combatSnapshot`.

    `combatSnapshot.units[].stats` est un dict {NOM -> Current} et `combatSnapshot.statTypes` le
    mapping {NOM -> index `StatType`} (cf. `engine/entities/stats.seed_unit_stats`, dont c'est la
    signature). On resout donc le NOM par l'index -- jamais l'inverse, et jamais un nom devine :
    une renumerotation d'enum se verrait, un nom en dur non.

    Rend `None` quand la mesure n'a pas pu etre prise (tri-etat : `None` != 0)."""
    snap = cap.get("snap") or {}
    ids = snap.get("statTypes") or {}
    names = [n for n, i in ids.items() if _as_int(i) == int(stat_type)]
    if not names:
        return None
    for su in (snap.get("units") or []):
        if _as_int(su.get("entityId")) != int(uid):
            continue
        s = su.get("stats") or {}
        for n in names:
            if s.get(n) is not None:
                return _as_int(s[n])
        return None
    return None


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def port_stat(st, uid: int, stat_type: int):
    """La valeur RESOLUE du MEME stat cote PORT (`UnitStats.get_stat(<type>, CURRENT)`)."""
    from engine.runner.components import StatsComponent
    e = st.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    us = getattr(getattr(sc, "ctx", None), "stats", None) if sc is not None else None
    if us is None:
        return None
    return int(us.get_stat(int(stat_type)))


# --------------------------------------------------------------------------- etages

def e0_offline(fails):
    """E0 -- FORME du port, sans aucun live. C'est ici que la STRUCTURE de l'arbre est gardee :
    quatre noeuds, dans l'ordre du `op_Addition` natif, et DEUX selecteurs DIFFERENTS."""
    from engine.entities.behaviours import If as IfBehaviour, Seq
    from engine.entities.triggers import ActorHasTriggeredAbility
    from engine.runner.abilities import necrons as N
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.behaviours.ai_control import PerformAIAction
    from engine.runner.abilities.behaviours.effects import RemoveEffect
    from engine.runner.abilities.behaviours.lifecycle import (TRIGGERED_ABILITY_BEHAVIOURS,
                                                              TriggerAbility)
    from engine.runner.abilities.behaviours.stats import AddStatOverrideEffect
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    cls = ABILITY_CLASSES.get(ADAPTIVE)
    if cls is not N.AdaptiveStrategyAbility:
        fails.append("E0 registre: ABILITY_CLASSES[%d] = %r" % (ADAPTIVE, cls))
        return
    opts = cls.TARGETING_OPTIONS
    if int(opts.rules) != (int(TR.TargetMatchesDynamicRule) | int(TR.TargetIsFriendly)):
        fails.append("E0 masque = 0x%x (attendu 0x402)" % int(opts.rules))
    if not opts.self_cast or int(opts.force_melee_target) != 1:
        fails.append("E0 selfCast/forceMeleeTarget = %r/%r" % (opts.self_cast,
                                                              opts.force_melee_target))
    if ABILITY_ATTACK_TYPE.get(ADAPTIVE) != AbilityAttackType.Others:
        fails.append("E0 AbilityAttackType = %r (attendu Others=2)"
                     % ABILITY_ATTACK_TYPE.get(ADAPTIVE))
    # CONTRAT DE DISJONCTION : une face COMBAT portee SORT des deux tables `*_UNPORTED`.
    if ADAPTIVE in TARGETING_OPTIONS_UNPORTED:
        fails.append("E0 1005 est ENCORE dans TARGETING_OPTIONS_UNPORTED (double source)")
    if ADAPTIVE in DYNAMIC_TARGET_RULE_UNPORTED:
        fails.append("E0 1005 est ENCORE dans DYNAMIC_TARGET_RULE_UNPORTED (double source)")
    if TRIGGERED_ABILITY_BEHAVIOURS.get(RELENTLESS) is None:
        fails.append("E0 TRIGGERED_ABILITY_BEHAVIOURS[%d] absent : la branche `Custom` de "
                     "RelentlessMarch n'a toujours aucun appelant" % RELENTLESS)

    # FORME de l'arbre : `((If + AddStatOverride) + PerformAIAction) + RemoveEffect`.
    tree = N.adaptive_strategy_tree(None)
    def _flat(n):
        return (_flat(n.left) + _flat(n.right)) if isinstance(n, Seq) else [n]
    seq = _flat(tree)
    kinds = [type(n).__name__ for n in seq]
    if kinds != ["If", "AddStatOverrideEffect", "PerformAIAction", "RemoveEffect"]:
        fails.append("E0 FORME de l'arbre = %r" % (kinds,))
        return
    cond = seq[0].cond
    if not isinstance(cond, ActorHasTriggeredAbility) or \
            int(cond.triggered_ability_type) != RELENTLESS:
        fails.append("E0 condition du If = %r" % (cond,))
    if not isinstance(seq[0].then, TriggerAbility) or int(seq[0].then.ability_type) != RELENTLESS:
        fails.append("E0 branche then du If = %r" % (seq[0].then,))
    if seq[0].otherwise is not None:
        fails.append("E0 le If porte une branche else (le natif passe 0)")
    if int(seq[1].effect_type) != OVERRIDE or int(seq[1].stat_type) != 0:
        fails.append("E0 AddStatOverrideEffect(effect=%r, stat=%r)" % (seq[1].effect_type,
                                                                      seq[1].stat_type))
    if seq[1].duration_rounds is not None or seq[1].duration_turns is not None:
        fails.append("E0 duree de l'override non nulle (le natif passe un Nullable VIDE)")
    if seq[2].as_group is not False or seq[2].reset_turn_flags is not True:
        fails.append("E0 PerformAIAction(asGroup=%r, resetTurnFlags=%r)" % (seq[2].as_group,
                                                                           seq[2].reset_turn_flags))
    if int(seq[3].effect_type) != OVERRIDE:
        fails.append("E0 RemoveEffect(effect=%r)" % (seq[3].effect_type,))
    # DISCRIMINANT DE SELECTEUR : (4) balaie TOUT le plateau, (2) les seuls ADJACENTS. Les deux
    # arbres ne doivent pas etre le meme objet, ni la meme forme.
    if repr(type(seq[1].unit_sel)) == repr(type(seq[3].target_sel)) and \
            _src_kind(seq[1].unit_sel) == _src_kind(seq[3].target_sel):
        fails.append("E0 les selecteurs du (2) et du (4) ont la MEME source : le nettoyage "
                     "n'atteint pas les allies non adjacents")
    print("[E0] registre OK | masque 0x%x | attackType Others | arbre %r"
          % (int(opts.rules), kinds))


def _src_kind(sel):
    """Nom de la classe de la SOURCE d'un `Sub(Friends(src, ...), hero_units(src))` -- ce qui
    distingue `AdjacentUnits` (noeud (2)) d'`AllAliveUnits` (noeud (4))."""
    inner = getattr(getattr(sel, "a", None), "inner", None)
    return type(inner).__name__ if inner is not None else type(sel).__name__


def cast_orb(rid, overlord) -> list:
    """L'Overlord caste `ResurrectionOrb` -> les `necroSmnWarrior` NON-Hero apparaissent. Rend les
    ids des unites APPARUES (diff avant/apres)."""
    before = set(units(rid))
    r = _duel(["act", "ability", "--caster", str(overlord), "--ability", str(RESURRECTION_ORB),
               "--target", str(overlord), "--state-file", str(STATE), "--runner", str(rid)])
    after = units(rid)
    born = sorted(set(after) - before)
    if not born:
        raise SystemExit("MONTAGE: aucun summon apres 1009 (rc=%d) : %s"
                         % (r.returncode, (r.stdout or r.stderr or "")[-600:]))
    print("[montage] 1009 -> %d summon(s) : %s"
          % (len(born), [(b, after[b]["vid"], after[b]["pos"]) for b in born]))
    return born


def move_warden_next_to(rid, warden, summon_id) -> tuple:
    """DEPLACE le Warden sur une tuile legale ADJACENTE au summon -- on force la configuration
    plutot que de se declarer « bloque par la geometrie de spawn ». No-op s'il l'est deja (le spawn
    de 1009 se fait sur les tuiles adjacentes a l'Overlord, qui deploie a cote du Warden).

    Le domaine de move est celui du RPC `aiMovableTiles` -- LA source du natif
    (`BattleQuery$$GetCurrentAndMovablePositionsFor`), la meme que `rl_duel moves` affiche."""
    import hexgeo
    us = units(rid)
    spos = us[summon_id]["pos"]
    wpos = us[warden]["pos"]
    if hexgeo.distance(wpos, spos) == 1:
        print("[montage] Warden deja adjacent au summon %d (%r <-> %r)" % (summon_id, wpos, spos))
        return wpos, spos
    mv = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
    cand = []
    for u in (mv.get("units") or []):
        if int(u.get("unitId") or -1) != int(warden):
            continue
        for t in (u.get("tiles") or []):
            cand.append((t.get("col"), t.get("row")))
    adj = [c for c in cand if hexgeo.distance(c, spos) == 1]
    if not adj:
        raise SystemExit("MONTAGE: aucune tuile de move du Warden n'est adjacente au summon %r "
                         "(candidates=%r, summon=%r)" % (summon_id, sorted(cand)[:12], spos))
    dest = sorted(adj)[0]
    r = _duel(["act", "move", "--unit", str(warden), "--to", "%d,%d" % dest,
               "--state-file", str(STATE), "--runner", str(rid)])
    got = units(rid)[warden]["pos"]
    if got != dest:
        raise SystemExit("MONTAGE: le Warden est en %r au lieu de %r (rc=%d) : %s"
                         % (got, dest, r.returncode, (r.stdout or r.stderr or "")[-400:]))
    print("[montage] Warden -> %r (adjacent au summon %d en %r)" % (dest, summon_id, spos))
    return dest, spos


def run() -> dict:
    fails: list = []
    e0_offline(fails)
    rid = build()
    try:
        us = units(rid)
        warden = next(u for u, v in us.items() if v["vid"] == WARDEN)
        overlord = next(u for u, v in us.items() if v["vid"] == OVERLORD)
        born = cast_orb(rid, overlord)
        summon = born[0]

        # --- E1a : le gate MORD, mesure prise AVANT le deplacement ------------------------------
        # Au deploiement le Warden est ADJACENT a l'Overlord, un allie HERO : c'est LA position ou
        # le refus `HasTrait(target, Hero)` est DISCRIMINANT. Apres le move il ne l'est plus (les
        # deux heros ne sont plus voisins), donc la mesure ne se prend qu'ICI.
        import hexgeo
        us0 = units(rid)
        adjacent_hero = (hexgeo.distance(us0[warden]["pos"], us0[overlord]["pos"]) == 1)
        legal0 = legal_unit_targets(rid, warden, ADAPTIVE)
        if not adjacent_hero:
            fails.append("E1a MONTAGE : le Warden %r n'est pas adjacent a l'Overlord %r -- le "
                         "refus `HasTrait(Hero)` ne discrimine rien a cette position"
                         % (us0[warden]["pos"], us0[overlord]["pos"]))
        elif overlord in legal0:
            fails.append("E1a l'allie HERO adjacent %d est une cible legale de 1005 (legales=%r) "
                         "-- le gate `HasTrait(target, Hero)` ne mord pas" % (overlord, sorted(legal0)))
        print("[E1a] Warden %r / Overlord %r adjacents=%s | cibles legales = %r (HERO exclu=%s)"
              % (us0[warden]["pos"], us0[overlord]["pos"], adjacent_hero, sorted(legal0),
                 overlord not in legal0))

        move_warden_next_to(rid, warden, summon)

        # --- E1b : le summon NON-Hero, lui, EST une cible legale --------------------------------
        # ⚠ Le CASTER lui-meme figure dans la liste, et ce n'est pas une anomalie du gate :
        # `isSelfCasting = 1` fait rabattre le role `target` sur le caster par
        # `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` (branche self-cast, en TETE de
        # ses quatre). On l'ECARTE de la mesure au lieu de le compter comme un « HERO accepte ».
        legal = legal_unit_targets(rid, warden, ADAPTIVE)
        if summon not in legal:
            fails.append("E1b le summon %d (NON-Hero, adjacent) n'est PAS une cible legale de "
                         "1005 (legales=%r)" % (summon, sorted(legal)))
        us1 = units(rid)
        heroes = [u for u in legal if u != warden
                  and "Hero" in ((us1.get(u) or {}).get("traits") or ())]
        if heroes:
            fails.append("E1b des allies HERO sont cibles legales de 1005 : %r" % (heroes,))
        print("[E1b] cibles legales de u%d/1005 = %r (summon %d inclus=%s, caster ECARTE)"
              % (warden, sorted(legal), summon, summon in legal))

        # --- CAPTURE -> rejeu OFFLINE ----------------------------------------------------------
        cap = capture(rid)
        cens = native_effect_census(cap)
        st, _board = offline_state(cap)
        before_port = {u: offline_view(st, u) for u in (warden, overlord, summon)}
        # ETAT D'ENTREE des deux effets suivis -- indispensable pour comparer des DELTAS (E3, E7).
        march_nat_before = native_carriers(cap, MARCH_EFFECT)
        march_port_before = port_carriers_of(st, MARCH_EFFECT)
        ovr_nat_before = native_carriers(cap, OVERRIDE)
        ovr_port_before = port_carriers_of(st, OVERRIDE)
        from engine.runner.messages import ActiveAbilityMessage
        from engine.runner.runner import Runner
        # La voie COMPLETE : gates de ciblage, `On(0x2a = PreUnitAbility)`, behaviour, flags de
        # tour. `install_default_handlers` est OBLIGATOIRE -- sans lui `apply` ne route rien et le
        # cast est un no-op qui se lit comme une mesure.
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=int(warden), target_id=int(summon),
                                          ability_type=ADAPTIVE))
        last = runner.ability_handler.last or {}
        port_after = {u: offline_view(st, u) for u in (warden, overlord, summon)}
        port_carriers = port_carriers_of(st, OVERRIDE)

        # --- CAST LIVE -------------------------------------------------------------------------
        r = _duel(["act", "ability", "--caster", str(warden), "--ability", str(ADAPTIVE),
                   "--target", str(summon), "--state-file", str(STATE), "--runner", str(rid)])
        if r.returncode != 0:
            raise SystemExit("cast 1005 LIVE refuse (MONTAGE) : %s"
                             % (r.stdout or r.stderr or "")[-800:])
        cap2 = capture(rid)
        nat = units(rid)
        native_after = {u: {"pos": nat[u]["pos"], "alive": nat[u]["alive"], "hp": nat[u]["hp"]}
                        for u in (warden, overlord, summon) if u in nat}
        nat_carriers = native_carriers(cap2, OVERRIDE)

        # --- E2 : confrontation terme a terme --------------------------------------------------
        # `alive` et `hp` sur les TROIS unites, `pos` sur le CASTER et l'OVERLORD. Le `hp` du summon
        # est le canal qui porte le noeud (1) : `RelentlessMarch` en mode `Custom` REPARE les allies
        # adjacents Mecaniques, et un `necroSmnWarrior` en est un. Une egalite de PV a l'unite pres
        # entre les deux cotes est donc une confrontation du re-trigger, pas un accord trivial.
        for u in (warden, overlord, summon):
            n = native_after.get(u) or {}
            p = port_after.get(u) or {}
            for k in ("alive", "hp"):
                if n.get(k) != p.get(k):
                    fails.append("E2 u%d.%s : natif=%r port=%r" % (u, k, n.get(k), p.get(k)))
        for u in (warden, overlord):
            if (native_after.get(u) or {}).get("pos") != (port_after.get(u) or {}).get("pos"):
                fails.append("E2 u%d.pos : natif=%r port=%r"
                             % (u, (native_after.get(u) or {}).get("pos"),
                                (port_after.get(u) or {}).get("pos")))
        # `pos` du SUMMON : les DEUX cotes doivent l'avoir fait AGIR (c'est la question binaire du
        # probe). La TUILE choisie, elle, releve de l'etage `decide_and_apply` -- cf. E5, qui
        # l'IMPUTE par mesure au lieu de le supposer.
        origin = (before_port.get(summon) or {}).get("pos")
        if (native_after.get(summon) or {}).get("pos") == origin:
            fails.append("E2 le NATIF n'a pas fait agir le summon (toujours en %r)" % (origin,))
        if (port_after.get(summon) or {}).get("pos") == origin:
            fails.append("E2 le PORT n'a pas fait agir le summon (toujours en %r) -- le noeud (3) "
                         "est reste un no-op" % (origin,))

        # --- E3 : NET-ZERO ---------------------------------------------------------------------
        # Le noeud (4) retire ce que le noeud (2) a pose : apres le cast, PLUS AUCUN porteur de
        # 1012 -- ni de nouveau (delta vide), ni de rescape. On exige l'ETAT VIDE et non un delta :
        # `RemoveEffect` balaie TOUS les allies non-Character du plateau, pas les seuls adjacents.
        if nat_carriers:
            fails.append("E3 le NATIF garde 1012 sur %r apres le cast (avant : %r)"
                         % (nat_carriers, ovr_nat_before))
        if port_carriers:
            fails.append("E3 le PORT garde 1012 sur %r apres le cast (avant : %r) -- le noeud (4) "
                         "n'a pas nettoye" % (port_carriers, ovr_port_before))

        # --- E4 : ANTI-TAUTOLOGIE --------------------------------------------------------------
        if last.get("ported") is not True:
            fails.append("E4 1005 non executee offline : %r" % (last,))
        if "invalid_target" in last:
            fails.append("E4 cast refuse par le gate de cible offline : %r" % (last,))
        if not last.get("overrides"):
            fails.append("E4 aucun `AddStatOverrideEffect` emis : %r"
                         % ({k: last.get(k) for k in ("overrides", "actions", "retriggered")},))
        acts = (last.get("actions") or {}).get("units") or []
        if summon not in [int(x) for x in acts]:
            fails.append("E4 le summon %d n'est pas dans les cibles de `PerformAIAction` (%r) -- "
                         "le noeud (3) ne l'atteint pas" % (summon, acts))
        # --- E5/E6 : DECOMPOSITION PAR ETAGE de l'ecart de TUILE ---------------------------------
        # Les deux cotes font AGIR le summon (E2), mais peuvent choisir une TUILE differente. On ne
        # se contente pas de l'imputer a « l'IA » : on mesure DE QUOI depend le choix.
        #
        # ETAGE 1 -- le MONTANT. `MinMaxDamage(isPrediction: FALSE)` = `RandomAmount(minDmg[lvl],
        # maxDmg[lvl])`, un TIRAGE. Le PRNG de bataille du natif n'est PAS synchronisable depuis un
        # etat RECHARGE (`load_state` ne restitue pas l'etat interne du Mersenne Twister), donc
        # `state.rng is None` et `RandomAmount` prend sa degradation DOCUMENTEE : la borne MIN. Le
        # natif, lui, a tire quelque part dans [minDmg, maxDmg]. Les deux etages ne partent donc
        # PAS de la meme Attack -- et c'est une limite du MONTAGE, pas du port.
        #
        # ETAGE 2 -- la SENSIBILITE. On rejoue `decide_and_apply(summon)` sur deux copies FRAICHES
        # de l'etat capture, override pose a `lo` puis a `hi`. Si les deux tuiles different, l'etage
        # IA est SENSIBLE au montant : l'ecart natif <-> port est alors ENTIEREMENT explique sous le
        # noeud (3), par une entree que le montage ne peut pas egaliser. Si elles sont EGALES et que
        # le natif diverge quand meme, la cause est AILLEURS et le probe doit ROUGIR.
        from engine.runner.operations.stat_ops import apply_stat_override
        from engine.runner.operations.summon_ai import ComputerActionOperation
        lo, hi = int(last.get("min") or 0), int(last.get("max") or 0)
        amt = int((last.get("overrides") or [{}])[0].get("amount") or 0)
        port_tile = (port_after.get(summon) or {}).get("pos")
        nat_tile = (native_after.get(summon) or {}).get("pos")
        sens = {}
        solo_march = None
        for v in (lo, hi):
            st2, _b2 = offline_state(cap)
            apply_stat_override(st2, int(summon), 0, int(v), is_modifiable=True)   # 0 = ATTACK
            ComputerActionOperation.execute(st2, int(summon), True)
            sens[v] = offline_view(st2, summon)["pos"]
            if solo_march is None:
                solo_march = port_carriers_of(st2, MARCH_EFFECT)
        rng_cale = (st.rng is not None)
        # ⚠ MESURE, PAS VERDICT. Ce bras a d'abord ete ecrit comme un test (« le port doit rendre
        # la tuile de l'IA jouee sous override ») et il a ROUGI -- a raison : l'etage IA seul rend
        # (0,3), le cast porte (3,3). La cause est que l'override N'EST PAS la seule entree que
        # l'arbre fournit au noeud (3) : le noeud (1) a deja pose `RelentlessMarch_Effect` (+1
        # Mouvement) et REPARE la cible, ce que cette contre-epreuve ne rejoue pas. Reconstituer
        # exactement l'etat d'entree du noeud (3) reviendrait a rejouer les noeuds (1) et (2),
        # c'est-a-dire le cast lui-meme : la contre-epreuve serait TAUTOLOGIQUE. On imprime donc les
        # trois tuiles et la sensibilite au montant comme des FAITS de decomposition, et le verdict
        # sur le noeud (1) est porte par E7 (un observable PERSISTANT), pas par la tuile.
        print("[E5] tuile summon : natif=%r port=%r | etage IA SEUL sous override lo=%d -> %r, "
              "hi=%d -> %r (sensible au montant=%s)"
              % (nat_tile, port_tile, lo, sens[lo], hi, sens[hi], sens[lo] != sens[hi]))

        # ETAGE 1, la mesure : le montant EST dans [minDmg, maxDmg], et on DIT s'il touche la borne
        # min parce que le PRNG n'est pas cale (limite du montage, jamais un vert qui ment).
        if not (lo > 0 and hi >= lo):
            fails.append("E6 bornes minDmg/maxDmg non resolues : %r/%r" % (lo, hi))
        elif not (lo <= amt <= hi):
            fails.append("E6 override=%d hors de [%d, %d]" % (amt, lo, hi))
        if not rng_cale and amt != lo:
            fails.append("E6 `state.rng` est None mais le montant (%d) n'est pas la borne min "
                         "(%d) : `RandomAmount` ne prend pas sa degradation documentee" % (amt, lo))
        print("[E6] override = %d dans [%d, %d] | state.rng cale=%s (borne min touchee=%s)"
              % (amt, lo, hi, rng_cale, amt == lo))

        # --- E7 : le noeud (1) sur un observable PERSISTANT --------------------------------------
        # Le re-trigger de `RelentlessMarch` en mode `Custom` fait DEUX choses : il REPARE (confronte
        # par le `hp` d'E2, a l'unite pres) et il pose `EffectType.RelentlessMarch_Effect` (0x3f3 =
        # 1011, +1 Mouvement, `turns = Nullable<int>(1)`) sur les allies adjacents non-Hero
        # NON-`Stationary`. Cet effet-la, contrairement a 1012, N'EST PAS retire par le cast : il
        # SURVIT, donc il se lit des DEUX cotes apres coup. C'est le discriminant du noeud (1) --
        # sans lui, un port qui aurait oublie le `If`/`TriggerAbility` passerait E2 (le `hp` est
        # aussi ce que 1011 repare... mais pas seulement : cf. la remarque ci-dessous).
        # ⚠ QUALIFICATION D'ENUM : 1011 est ici un `EffectType`. Dans `ActiveAbilityType`, 1011
        # nomme `TunnelingHorror` -- une ability de `necroSmnDestroyer`, sans aucun rapport.
        # ⚠ ON COMPARE DES DELTAS, PAS DES ETATS. L'etat d'ENTREE porte deja des instances de 1011
        # (le `RelentlessMarch` NORMAL du Warden, `On(TurnStart_Other)`, s'est declenche au debut du
        # tour) : comparer les etats FINAUX imputerait au cast ce que le montage avait deja pose.
        march_nat_after, march_port_after = native_carriers(cap2, MARCH_EFFECT), \
            port_carriers_of(st, MARCH_EFFECT)
        d_nat = sorted(set(march_nat_after) - set(march_nat_before))
        d_port = sorted(set(march_port_after) - set(march_port_before))
        if cens["n"] == 0 or cens["typed"] == 0:
            fails.append("E7 CANAL MUET : `decisionView.units[].effects` rend %d ligne(s), %d avec "
                         "un `EffectType` lisible (cles=%r) -- un `[]` ne prouverait RIEN"
                         % (cens["n"], cens["typed"], cens["keys"]))
        # VERDICT (1) : le port DOIT poser 1011 sur le summon -- c'est le noeud (1) qui a mordu.
        if summon not in d_port:
            fails.append("E7 le PORT n'a pose AUCUN %d sur le summon %d (delta=%r) -- le noeud (1) "
                         "n'a pas mordu" % (MARCH_EFFECT, summon, d_port))
        # VERDICT (2) : l'ECART avec le natif est un RE-CIBLAGE, et on le MESURE.
        # ⚠ L'IMPUTATION ECRITE ICI JUSQU'AU 2026-08-18 -- « le natif a EXPIRE les instances a
        # duree 1 tour pendant que le summon jouait (`ApplyAiMessages` -> `FinishUnitTurn`) » --
        # EST FAUSSE, et deux fois. (a) `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`
        # n'expire RIEN : le SEUL ecrivain decroissant de `Duration@+0x64` est
        # `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn`, enfile par
        # `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`. (b) Le natif POSE 1011 sur le
        # summon pendant ce cast MEME puis le retire dans la meme cascade -- un effet pose a
        # l'instant ne peut pas avoir expire.
        # LE MECANISME REEL EST UN RE-CIBLAGE : les cibles de 1011 sont un SELECTEUR GEOMETRIQUE
        # (`UnitsWithoutTrait(Friends(AdjacentUnits(Owner)), 0x418 Stationary)`) que
        # `IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` recalcule a chaque
        # refresh via `$$GetDesiredEffectTargets` (qui rejoue le slot `IEffect+0xd` de l'effet), puis
        # DIFFERENCE (`$$GetTargetsToRemove` -> `$$RemoveTargetsFromEffect` -> `$$RevertEffects
        # ForTargets` -> `RevertInternal`). Les deux porteurs sortent du selecteur parce que le
        # montage a DEPLACE le Warden puis le summon.
        # La contre-epreuve DISJOINTE de 1005 reste jouee (`ComputerActionOperation.execute(summon)`
        # SEUL) : elle etablit que l'ecart NE VIENT PAS de l'arbre de 1005.
        if march_nat_after != march_port_after and solo_march is not None \
                and (set(march_port_before) - set(solo_march)):
            fails.append("E7 porteurs de %d apres : natif=%r port=%r -- et l'etage IA SEUL, "
                         "lui, RETIRE (%r depuis %r) : l'ecart n'est donc PAS un re-ciblage "
                         "general, c'est l'arbre de 1005 qui l'empeche"
                         % (MARCH_EFFECT, march_nat_after, march_port_after, solo_march,
                            march_port_before))
        print("[E7] %d RelentlessMarch_Effect -- avant: natif=%r port=%r | apres: natif=%r "
              "port=%r | DELTA natif=%r port=%r | temoin canal: %d ligne(s), %d typee(s), "
              "types=%r"
              % (MARCH_EFFECT, march_nat_before, march_port_before, march_nat_after,
                 march_port_after, d_nat, d_port, cens["n"], cens["typed"], cens["types"]))

        # --- E8 : LE RE-CIBLAGE SUR SON OBSERVABLE LE PLUS DISCRIMINANT -- LA STAT ---------------
        # La liste des porteurs est un observable de STRUCTURE ; la STAT est l'observable de
        # CONSEQUENCE, et c'est celui qui dit si l'ecart COUTE quelque chose.
        # `IdunBattle.Entities.Effects.Loki.RelentlessMarchEffect$$ApplyInternal` fait
        # `ChangeStat(Entity(target), Stat(1 = Movement, 5 = Modification), Modify, Direct(1), ...)`
        # et `$$RevertInternal` rejoue le meme appel en `Stat(1 = Movement, 6 = ResetModification)`.
        # Une unite que le natif a SORTIE du selecteur a donc perdu son +1 Mouvement ; si le port la
        # garde, elle vaut UN de plus -- et cette unite peut atteindre une tuile que le natif lui
        # interdit. C'est mesurable sans rien deviner.
        # ⚠ TEMOIN NON NUL OBLIGATOIRE : la mesure ne vaut que si le canal REND une valeur. Un
        # `None` des DEUX cotes serait un accord en regime degenere -- on le fait ROUGIR.
        from engine.entities.stats import StatType as _ST
        sortis = sorted(set(march_port_after) - set(march_nat_after))
        moves = {}
        for u in sortis:
            moves[u] = (native_stat(cap2, u, int(_ST.MOVEMENT)), port_stat(st, u, int(_ST.MOVEMENT)))
        temoin = native_stat(cap2, warden, int(_ST.MOVEMENT))
        if temoin is None:
            fails.append("E8 CANAL MUET : `combatSnapshot` ne rend AUCUN Mouvement pour le Warden "
                         "%d -- un accord sur `None` ne prouverait RIEN" % (warden,))
        for u, (nm, pm) in sorted(moves.items()):
            if nm is None or pm is None:
                fails.append("E8 Mouvement non mesure sur u%d : natif=%r port=%r" % (u, nm, pm))
        print("[E8] sortis du selecteur (port garde, natif a retire) = %r | Mouvement natif/port = "
              "%r | temoin Warden(Mouvement natif) = %r" % (sortis, moves, temoin))

        # --- E9 : LE TOUR D'EQUIPE A-T-IL CHANGE ? -- l'etage QUI DEPARTAGE ----------------------
        # Le SEUL ecrivain decroissant de `EffectComponent.RemainingTurns @+0x64` est
        # `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` (xrefs : UN appelant),
        # enfile par `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`, dont l'appelant est
        # `IdunBattle.Operations.EndTurnOperation$$Execute`, lui-meme appele par le SEUL
        # `IdunBattle.Core.Services.OperationProcessor$$EndTurn`. Un effet `turns = 1` ne peut donc
        # disparaitre QUE si un TOUR D'EQUIPE se termine.
        # Ce bras mesure exactement ca -- `observeBattle.currentPlayer` avant/apres le cast LIVE --
        # et il DEPARTAGE les deux explications concurrentes : si le joueur courant a CHANGE, le
        # natif a joue une fin de tour que le rejeu offline (`Runner.apply(ActiveAbilityMessage)`)
        # ne joue pas ; si le joueur courant est le MEME, aucune fin de tour n'a eu lieu et la
        # disparition de 1011 a une AUTRE cause, qu'il faut alors chercher ailleurs.
        cp_avant = (cap.get("ob") or {}).get("currentPlayer")
        cp_apres = (cap2.get("ob") or {}).get("currentPlayer")
        act_avant = sorted(u for u, v in us1.items() if v.get("hasAction"))
        nat_apres = units(rid)
        act_apres = sorted(u for u, v in nat_apres.items() if v.get("hasAction"))
        tour_change = (cp_avant != cp_apres)
        print("[E9] currentPlayer natif : avant=%r apres=%r (CHANGE=%s) | hasAction avant=%r "
              "apres=%r | port.current_player_id=%r"
              % (cp_avant, cp_apres, tour_change, act_avant, act_apres,
                 getattr(st, "current_player_id", None)))

        # --- E10 : LA CONTRE-EPREUVE PAR SUBSTITUTION -------------------------------------------
        # E9 etablit que le NATIF a joue une FIN DE TOUR D'EQUIPE pendant le pas que le port rejoue
        # sans elle -- le cast du Warden consomme la DERNIERE action amie (l'Overlord a deja caste
        # 1009, le summon est ne `NoActionAvailable`), donc le jeu bascule tout seul. On ne compare
        # alors pas la meme chose des deux cotes : N+1 operations natives contre N portees.
        # LA SUBSTITUTION : on rejoue le MEME cast sur une copie FRAICHE de l'etat capture, puis on
        # applique `EndTurnMessage` -- rien d'autre. Si les DEUX observables (porteurs de 1011 ET
        # stat MOUVEMENT) rejoignent le natif, l'ecart d'E7/E8 est un ARTEFACT DU MONTAGE et le port
        # ne manque RIEN. S'ils ne rejoignent pas, le port manque bien une transition, et c'est LA
        # qu'il faut porter.
        # ⚠ On ne touche NI la formule NI le pipeline : on donne au port l'operation que le natif a
        # jouee et que le harnais ne jouait pas. C'est la meme forme de contre-epreuve que celle qui
        # a localise le troisieme etage de #922.
        from engine.runner.messages import EndTurnMessage
        st3, _b3 = offline_state(cap)
        r3 = Runner(st3).install_default_handlers(20)
        r3.apply(ActiveAbilityMessage(caster_id=int(warden), target_id=int(summon),
                                      ability_type=ADAPTIVE))
        r3.apply(EndTurnMessage())
        march_sub = port_carriers_of(st3, MARCH_EFFECT)
        moves_sub = {u: port_stat(st3, u, int(_ST.MOVEMENT)) for u in sortis}
        accord_porteurs = (march_sub == march_nat_after)
        accord_moves = all(moves[u][0] == moves_sub.get(u) for u in sortis)
        print("[E10] SUBSTITUTION (cast + EndTurnMessage) : porteurs de %d = %r (natif %r, "
              "accord=%s) | Mouvement port = %r (natif %r, accord=%s)"
              % (MARCH_EFFECT, march_sub, march_nat_after, accord_porteurs,
                 moves_sub, {u: moves[u][0] for u in sortis}, accord_moves))
        if not tour_change:
            fails.append("E10 le tour natif n'a PAS change (currentPlayer %r) : la substitution "
                         "n'a alors aucune raison d'etre jouee, et l'ecart d'E7/E8 accuse autre "
                         "chose -- a re-instruire" % (cp_avant,))
        elif accord_porteurs and accord_moves:
            print("      -> ARTEFACT DU MONTAGE : le port porte DEJA la mecanique (le tick d'un "
                  "tour de `EndTurnOperation$$RefreshEffects`), le harnais ne la jouait pas. "
                  "#577-r1 n'accuse aucun port sur ce vecteur.")
        else:
            fails.append("E10 la substitution NE FERME PAS l'ecart : porteurs port=%r natif=%r, "
                         "Mouvement port=%r natif=%r -- le port manque bien une transition"
                         % (march_sub, march_nat_after, moves_sub,
                            {u: moves[u][0] for u in sortis}))

        moved = (port_after[summon]["pos"] != before_port[summon]["pos"])
        print("[E2/E3/E4] natif=%r | port=%r | 1012 natif=%r port=%r | summon a bouge=%s"
              % (native_after, {u: {k: v[k] for k in ("pos", "alive", "hp")}
                                for u, v in port_after.items()},
                 nat_carriers, port_carriers, moved))
        print("[E4] retour du port : overrides=%r actions=%r retriggered=%r"
              % (last.get("overrides"), last.get("actions"), last.get("retriggered")))
        return {"runner": rid, "warden": warden, "overlord": overlord, "summon": summon,
                "legal": sorted(legal), "native": native_after, "port": port_after,
                "before": before_port, "last": last, "moved": moved,
                "nat_carriers": nat_carriers, "port_carriers": port_carriers, "fails": fails}
    finally:
        _duel(["dispose", "--state-file", str(STATE), "--runner", str(rid)])


if __name__ == "__main__":
    res = run()
    print("FAILS: %r" % (res["fails"],))
    print("PROBE OK" if not res["fails"] else "PROBE KO")
    sys.exit(0 if not res["fails"] else 1)
