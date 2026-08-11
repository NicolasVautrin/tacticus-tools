"""Probe #928 -- `LegacyOfCombat` (TriggeredAbilityType 0x527 = 1319, passif de `custoBladeChampion`).

RE re-derivee DU BINAIRE, jamais recopiee d'un decompile relu : le pseudo-C de
`LegacyOfCombatAbility$$CreateBehaviour` affiche `AdjacentEnemies` et `AttackWithAttackDamage`, or
ces deux noms couvrent PLUSIEURS surcharges d'arite identique (`AdjacentEnemies` : DEUX formes
d'arite 4 indiscernables, cf. `entities/selectors/units.py` ; `AttackWithAttackDamage` : cinq).
Seule l'ADRESSE resolue du `call` tranche.

  etape 1  LES FACES. Les trois corps natifs de l'ability (`CreateTrigger`, `CreateBehaviour`) et
           les deux du playbook (`CalculateAttackUtilityInStepsInternal`,
           `CalculateMovementUtilityInStepsInternal`) : presence + taille + verdict DEAD/VIF, le
           verdict DEAD etant etabli par le corps de l'iterateur (`MoveNext`), pas par la
           methode-fabrique.
  etape 2  L'ARBRE NATIF, desassemble. Cibles d'appel RESOLUES + immediats des deux `Create*` --
           c'est ce qui identifie chaque surcharge et chaque litteral d'enum.
  etape 3  LA CLE BC du playbook de mouvement, resolue au litteral de `global-metadata.dat`
           (meme chaine que `probe_212`), et sa valeur dans le gameconfig VIVANT + la capture.
  etape 4  LE PORT. Ce que le registre `ABILITY_TRIGGERS` / `TRIGGERED_MOVE_PLAYBOOKS` connait de
           1319, et le vecteur `On(0xb = UnitAbility)` : emis ou non par le port.

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_364_effect_1582_registration as p364            # noqa: E402
import probe_366_inventaire_effets_forme_b as p366           # noqa: E402

TRIGGERED_ID = 0x527                 # 1319 LegacyOfCombat
ABILITY = "LegacyOfCombat"
NS = "IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegacyOfCombatAbility$$"
PB = "IdunBattle.AI.Playbook.Loki.LegacyOfCombatPlaybook"

CREATE_TRIGGER = NS + "CreateTrigger"
CREATE_BEHAVIOUR = NS + "CreateBehaviour"
PB_MOVE = PB + ".u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext"
PB_ATTACK = PB + ".u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext"
PB_CTOR = PB + "$$.ctor"

FACES = [("COMBAT   CreateTrigger", CREATE_TRIGGER),
         ("COMBAT   CreateBehaviour", CREATE_BEHAVIOUR),
         ("DECISION playbook MOVE  ", PB_MOVE),
         ("DECISION playbook ATTACK", PB_ATTACK),
         ("DECISION playbook .ctor ", PB_CTOR)]


def _fn_calls_and_imms(buf, secs, rows, symbol):
    """(cibles d'appel RESOLUES en ordre, immediats en ordre) du corps de `symbol`.

    Les cibles sont rendues avec leur ADRESSE : c'est elle -- pas le nom, homonyme entre
    surcharges -- qui identifie l'overload appele. Copie VERBATIM de `probe_1175` etape 3."""
    import capstone
    by_addr = dict(rows)
    start, end = p364.span(rows, symbol)
    calls, imms = [], []
    for ins in p364.disasm(buf, secs, start, end):
        if ins.mnemonic == "call" and ins.operands \
                and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            tgt = ins.operands[0].imm
            calls.append((tgt, by_addr.get(tgt, "FUN_%x" % tgt)))
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM and ins.mnemonic in ("mov", "cmp", "push", "lea"):
                imms.append((ins.address, ins.mnemonic, ins.op_str))
    return calls, imms


def _span_or_none(rows, symbol):
    try:
        return p364.span(rows, symbol)
    except Exception:
        return None


def etape1(buf, secs, rows):
    print("[928] etape 1 -- LES FACES (presence + taille)")
    for label, sym in FACES:
        sp = _span_or_none(rows, sym)
        if sp is None:
            print("   %s : ABSENT de ghidra/functions.tsv" % label)
            continue
        print("   %s : %d octets" % (label, sp[1] - sp[0]))
    # verdict DEAD : le MoveNext qui ne fait qu'un `Fix64.op_Implicit(0)`
    for label, sym in (("ATTACK", PB_ATTACK), ("MOVE", PB_MOVE)):
        sp = _span_or_none(rows, sym)
        if sp is None:
            continue
        calls, _ = _fn_calls_and_imms(buf, secs, rows, sym)
        names = [n for (_a, n) in calls]
        interesting = [n for n in names
                       if not n.startswith("FUN_") and "il2cpp_runtime_class_init" not in n]
        print("   playbook %s -- appels: %s" % (label, ", ".join(interesting) or "(aucun)"))


def etape2(buf, secs, rows):
    print("[928] etape 2 -- L'ARBRE NATIF desassemble (surcharges tranchees par ADRESSE)")
    for label, sym in (("CreateTrigger", CREATE_TRIGGER), ("CreateBehaviour", CREATE_BEHAVIOUR)):
        if _span_or_none(rows, sym) is None:
            print("   %s : ABSENT" % label)
            continue
        calls, imms = _fn_calls_and_imms(buf, secs, rows, sym)
        print("   --- %s : %d appels" % (label, len(calls)))
        for (addr, name) in calls:
            print("       %012x  %s" % (addr, name))
        print("   --- %s : immediats" % label)
        for (a, m, ops) in imms:
            print("       %012x  %s %s" % (a, m, ops))


def etape3():
    print("[928] etape 3 -- CLE BC du playbook de MOUVEMENT")
    import probe_212_bc_key_literals as p212
    try:
        rc = p212.report([PB_MOVE])
    except Exception as exc:                       # pragma: no cover - diagnostic
        print("   INDISPONIBLE : %s" % exc)
        return
    if rc is not None:
        print("   (probe_212 rc=%s)" % rc)


def etape4():
    print("[928] etape 4 -- ETAT DU PORT")
    sys.path.insert(0, str(PYDIR))
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert int(TriggeredAbilityType.LegacyOfCombat) == TRIGGERED_ID
    # `ABILITY_TRIGGERS` est indexe par le NOM de la passiveAbility du kit gameconfig, pas par id.
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    print("   ABILITY_TRIGGERS[%r] : %s"
          % (ABILITY, [c.__name__ for c in ABILITY_TRIGGERS.get(ABILITY, ())] or "ABSENT"))
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    print("   TRIGGERED_ATTACK_PLAYBOOKS[%d] : %s   (DEAD attendu -> ABSENT)"
          % (TRIGGERED_ID, TRIGGERED_ATTACK_PLAYBOOKS.get(TRIGGERED_ID, "ABSENT")))
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    print("   TRIGGERED_MOVE_PLAYBOOKS[%d] : %s"
          % (TRIGGERED_ID, TRIGGERED_MOVE_PLAYBOOKS.get(TRIGGERED_ID, "ABSENT")))
    from engine.runner.operations.triggers.dispatch import ability as ab
    print("   vecteur On(0xb = UnitAbility) emis par le port : %s"
          % ("OUI (unit_ability_triggers)" if hasattr(ab, "unit_ability_triggers") else "NON"))


# --------------------------------------------------------------------- etape 5 : CONFRONTATION LIVE

#: Le montage reutilise INTEGRALEMENT celui de `probe_509` (Kariyan `custoBladeChampion` en (5,8),
#: deux ennemis ADJACENTS en (6,8) et (6,7), un figurant joueur au loin pour que le cast ne bascule
#: pas le tour) : c'est le seul foyer de montage de ce porteur, et le dupliquer en creerait un
#: second qui pourrait deriver. Ce qui CHANGE ici est le CRITERE -- `probe_509` filtre les
#: `UnitDamaged` sur `Active_Ability_Type = 1191` et jette le reste ; on garde ici exactement le
#: RESTE, c'est-a-dire les coups de `1319 LegacyOfCombat`.
_BIG_TARGET_UNITS = ("astraBullgryn", "tauCrisis", "blackObliterator", "tauFarsight")


def _seq_par_ability(stdout, caster_id):
    """`{Active_Ability_Type: [(cible, montant, profil), ...]}` -- TOUS les coups portes par
    `caster_id` pendant l'appel `act`, ventiles par l'ability qui les porte."""
    import probe_509_martial_inspiration as P
    out = {}
    for _e, att, tgt, amt, prof, aid in P.RE_DMG.findall(stdout or ""):
        if int(att) != int(caster_id):
            continue
        out.setdefault(int(aid), []).append((int(tgt), int(amt), int(prof)))
    return out


def _port_seq_1319(last):
    """Sequence coup par coup que le PORT attribue a 1319, lue dans le diagnostic que
    `AbilityHandler` publie desormais (`last['unit_ability_triggers']`). Le diag du trigger porte
    `targets` (l'ordre des cibles) et `attacks` (le detail par cible, dans le MEME ordre)."""
    seq = []
    for d in (last.get("unit_ability_triggers") or ()):
        for t, atk in zip(d.get("targets") or (), d.get("attacks") or ()):
            for m in ((atk or {}).get("per_hit_health") or ()):
                seq.append((int(t), int(m)))
    return seq


def mesure_live(sid, state_file, seed, board, a_units, a_places, tours=6, big_target=False):
    """Un cast de `1191 MartialInspiration` par tour ; a chaque cast on capture l'etat, on REJOUE
    hors-ligne par le chemin COMPLET (`Runner.apply`, donc le vecteur `On(0xb)` et le trigger 1319),
    puis on joue le cast NATIF et on confronte les deux sequences de `1319`."""
    import probe_509_martial_inspiration as P
    argv = ["build", "--seed", str(seed), "--board", board, "--rank", str(P.RANK),
            "--p-units", "%s,%s" % (P.CASTER, P.P_FILLER),
            "--a-units", ",".join(a_units),
            "--crit", "0,0", "--block-target", "0,0",
            "--place", "%s:%s" % (P.CASTER, P.PLACE_CASTER),
            "--place", "%s:%s" % (P.P_FILLER, P.PLACE_FILLER),
            "--state-file", state_file]
    for vid, tile in a_places:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    for vid, _t in a_places:
        argv += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (vid, P.HP_FOE, P.HP_FOE)]
    p = P._duel(argv)
    if p.returncode != 0 or not os.path.exists(state_file):
        print("[928] build rc=%s\n%s\n%s" % (p.returncode, (p.stdout or "")[-1500:],
                                             (p.stderr or "")[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        rid = int(json.load(f)["runnerId"])
    casts = []
    try:
        u, dv = P.unites(sid, rid)
        cid = u[P.CASTER]["id"]
        tid = u[a_places[0][0]]["id"]
        me = u[P.CASTER]["owner"]
        nid = P._normal_id(u[P.CASTER])
        adj = {v: u[v]["id"] for v, _t in a_places if v in u}
        print("[928] runner=%s caster=u%s cible=u%s adversaires=%s" % (rid, cid, tid, adj))
        for _tour in range(int(tours)):
            u, dv = P.unites(sid, rid)
            if dv.get("currentPlayer") != me:
                P._rendre_la_main(sid, rid, me)
                u, dv = P.unites(sid, rid)
            ent = P._ability_entry(u[P.CASTER], P.MARTIAL_INSPIRATION)
            dispo = bool(ent and ent.get("usable") and not ent.get("disabled")
                         and not ent.get("cooldown"))
            if not dispo:
                P._cast(state_file, rid, cid, tid, nid)
                P._rendre_la_main(sid, rid, me)
                continue
            hp_avant = {v: u[v]["hp"] for v in adj}
            cnt = (P._counters(sid, rid) or {}).get(cid)
            cap = P.capture(sid, rid)
            port = _rejeu(cap, cid, tid, adj)
            mut = contre_epreuves(cap, cid, tid, adj, big_target)
            proc = P._cast(state_file, rid, cid, tid, P.MARTIAL_INSPIRATION)
            par_ab = _seq_par_ability(proc.stdout or "", cid)
            u2, _dv2 = P.unites(sid, rid)
            hp_apres = {v: u2[v]["hp"] for v in adj if v in u2}
            rng_apres = P._rpc(sid, "dumpRng", {"runnerId": rid}, 60)
            casts.append({
                "port": port,
                "mutants": mut,
                "compteur_live": (cnt or (None, None))[0],
                "natif_par_ability": par_ab,
                "hp_natif": {v: int(hp_avant[v] or 0) - int(hp_apres.get(v) or 0) for v in adj},
                "brut": [l.strip() for l in (proc.stdout or "").splitlines()
                         if "UnitDamaged" in l][:24],
                "tirages_natif": (P.tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                                  if isinstance(rng_apres, dict) and rng_apres.get("mt") else None),
                "tirages_port": P.tirages(cap["rng"], port["mt"][0], port["mt"][1]),
                "rc": proc.returncode,
            })
            P._rendre_la_main(sid, rid, me)
        return {"rid": rid, "caster": cid, "cible": tid, "adj": adj, "casts": casts}
    finally:
        P._duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


def _rejeu(cap, caster_id, target_id, adj):
    """`Runner.apply(ActiveAbilityMessage(1191))` -- chemin COMPLET, donc `On(0xb)` puis 1319.

    Rend AUSSI le delta de PV par cible : c'est l'observable de bout en bout, celui qui ne depend
    d'aucun canal de diagnostic (les `UnitDamaged` natifs, eux, ne portent pas tous une
    `Active_Ability_Type`)."""
    import probe_509_martial_inspiration as P
    from engine.runner.components import HealthComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = P.etat_porte(cap)

    def _hp(uid):
        e = st.get_entity(int(uid))
        hc = e.get_component(HealthComponent) if e is not None else None
        return int(getattr(hc, "hp", 0) or 0)

    avant = {v: _hp(uid) for v, uid in (adj or {}).items()}
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=P.MARTIAL_INSPIRATION))
    last = getattr(runner.ability_handler, "last", None) or {}
    seq_1191 = [(int(a.get("target")), int(m)) for a in (last.get("attacks") or [])
                for m in ((a.get("attack") or {}).get("per_hit_health") or [])]
    return {"seq_1191": seq_1191, "seq_1319": _port_seq_1319(last),
            "diag": last.get("unit_ability_triggers"),
            "hp": {v: avant[v] - _hp(uid) for v, uid in (adj or {}).items()},
            "tirages": P.tirages(cap["rng"], list(st.rng.mt), st.rng.mti),
            "mt": (list(st.rng.mt), st.rng.mti)}


def contre_epreuves(cap, caster_id, target_id, adj, big_target: bool):
    """MUTANTS. Chacun ne change QU'UNE lecture du mirror, sur la MEME capture (donc le MEME MT).
    Si l'un rendait le MEME couple (delta de PV, tirages) que la reference, la lecture
    correspondante ne serait PAS mesuree par ce montage -- et l'accord port/natif serait un accord
    de hasard.

    Le rejeu passe par le CHEMIN COMPLET (`Runner.apply`), donc chaque mutant traverse aussi le
    vecteur `On(0xb)` et le registre : c'est ce qui rend `sans_trigger` mordant.

    ⚠ Les mutants sont CHOISIS PAR REGIME : muter la branche `else` pendant que le `If` prend la
    branche `then` ne prouverait rien (le noeud mute n'est pas execute). C'est le piege du
    << mutant vert par pauvrete du pilotage >> -- ici il serait vert par pauvrete du MUTANT."""
    import engine.runner.operations.triggers.loki.legacy_of_combat as LOC
    from engine.runner.operations.triggers.dispatch import registry as REG
    from engine.entities.behaviours import If
    from engine.entities.selectors.units import UnitsWithTrait
    from engine.entities.triggers import AmountIsGreaterThanZero
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage

    ref_tree = LOC.legacy_of_combat_tree
    ref_reg = REG.ABILITY_TRIGGERS.get("LegacyOfCombat")
    ref_big = LOC.big_target_selector

    def _arbre(then=None, els=None):
        """`then`/`els` = surcharges de la feuille de CETTE branche (les autres restent au mirror)."""
        then, els = dict(then or {}), dict(els or {})

        def _f(state, owner_id):
            first_bt = LOC.big_target_selector(state, owner_id)
            return If(
                AmountIsGreaterThanZero(first_bt),
                AttackWithAttackDamage(first_bt, LOC.ABILITY_ID,
                                       then.get("profile", LOC.PROFILE_BIG_TARGET), is_melee=True,
                                       min_key=then.get("min_key", LOC.MIN_KEY_BIG_TARGET),
                                       max_key=then.get("max_key", LOC.MAX_KEY_BIG_TARGET),
                                       hits_key=then.get("hits_key", LOC.HITS_KEY_BIG_TARGET),
                                       multi=True, level_slot="passive",
                                       ability_type=then.get("ability_type", LOC.LEGACY_OF_COMBAT)),
                AttackWithAttackDamage(LOC.adjacent_enemies_selector(), LOC.ABILITY_ID,
                                       els.get("profile", LOC.PROFILE_ADJACENT), is_melee=True,
                                       min_key=els.get("min_key", LOC.MIN_KEY_ADJACENT),
                                       max_key=els.get("max_key", LOC.MAX_KEY_ADJACENT),
                                       hits_key=els.get("hits_key", LOC.HITS_KEY_ADJACENT),
                                       multi=True, level_slot="passive",
                                       ability_type=els.get("ability_type", LOC.LEGACY_OF_COMBAT)))
        return _f

    def _sans_filtre_bigtarget(state, owner_id):
        """`UnitsWithTrait(..., BigTarget)` RETIRE : la condition du `If` devient << au moins un
        ennemi adjacent >>, donc la branche `then` (1x Piercing) remplace la branche `else`."""
        from engine.entities.selectors.geometry import Randomize
        from engine.entities.selectors.accessors import Owner as _Owner
        from engine.runner.abilities.base import ability_attack_params
        from engine.runner.operations.damage_prediction_sort import SortTargetsByDamagePrediction
        from engine.entities.selectors.units import First as _First
        bmin, bmax, pierce, hits = ability_attack_params(
            state, owner_id, LOC.ABILITY_ID, LOC.PROFILE_BIG_TARGET, ranged=False,
            min_key=LOC.MIN_KEY_BIG_TARGET, max_key=LOC.MAX_KEY_BIG_TARGET,
            hits_key=LOC.HITS_KEY_BIG_TARGET, level_slot="passive")
        return _First(SortTargetsByDamagePrediction(
            state=state, attacker=_Owner(), targets=Randomize(LOC.adjacent_enemies_selector()),
            ability_type=LOC.LEGACY_OF_COMBAT, damage_min=bmin, damage_max=bmax, hits=hits,
            damage_profile=LOC.PROFILE_BIG_TARGET, pierce=pierce, is_melee=True))

    def _sans_randomize(state, owner_id):
        """`Randomize` RETIRE : meme cible a pool 1, mais la CONSOMMATION RNG change (le natif
        tire `len(pool)` fois, DEUX fois -- une par evaluation du sous-arbre)."""
        from engine.entities.selectors.accessors import Owner as _Owner
        from engine.runner.abilities.base import ability_attack_params
        from engine.runner.operations.damage_prediction_sort import SortTargetsByDamagePrediction
        from engine.entities.selectors.units import First as _First
        bmin, bmax, pierce, hits = ability_attack_params(
            state, owner_id, LOC.ABILITY_ID, LOC.PROFILE_BIG_TARGET, ranged=False,
            min_key=LOC.MIN_KEY_BIG_TARGET, max_key=LOC.MAX_KEY_BIG_TARGET,
            hits_key=LOC.HITS_KEY_BIG_TARGET, level_slot="passive")
        big = UnitsWithTrait(LOC.adjacent_enemies_selector(), int(LOC.UnitTrait.BigTarget),
                             selection_type=LOC._SELECTION_ALIVE_AND_TARGETABLE)
        return _First(SortTargetsByDamagePrediction(
            state=state, attacker=_Owner(), targets=big,
            ability_type=LOC.LEGACY_OF_COMBAT, damage_min=bmin, damage_max=bmax, hits=hits,
            damage_profile=LOC.PROFILE_BIG_TARGET, pierce=pierce, is_melee=True))

    # (tree, registre, selecteur-BigTarget) ; `None` = on garde le mirror.
    variantes = {"ref": (None, None, None),
                 # le trigger n'est PAS enregistre -> seule 1191 joue (l'etat d'AVANT #928).
                 "sans_trigger": (None, [], None)}
    if big_target:
        # branche `then` prise : on mute SES lectures + le selecteur qui l'a fait prendre.
        variantes.update({
            "then_profil_volet1": (_arbre(then={"profile": LOC.PROFILE_ADJACENT}), None, None),
            "then_hits_volet1": (_arbre(then={"hits_key": LOC.HITS_KEY_ADJACENT}), None, None),
            "then_bornes_volet1": (_arbre(then={"min_key": LOC.MIN_KEY_ADJACENT,
                                                "max_key": LOC.MAX_KEY_ADJACENT}), None, None),
            "then_sans_ability_type": (_arbre(then={"ability_type": None}), None, None),
            "sans_randomize": (None, None, _sans_randomize),
        })
    else:
        # branche `else` prise : on mute SES lectures, et on verifie que le FILTRE `BigTarget`
        # est bien ce qui l'a fait prendre.
        variantes.update({
            "else_profil_volet2": (_arbre(els={"profile": LOC.PROFILE_BIG_TARGET}), None, None),
            "else_hits_volet2": (_arbre(els={"hits_key": LOC.HITS_KEY_BIG_TARGET}), None, None),
            "else_bornes_volet2": (_arbre(els={"min_key": LOC.MIN_KEY_BIG_TARGET,
                                               "max_key": LOC.MAX_KEY_BIG_TARGET}), None, None),
            "else_sans_ability_type": (_arbre(els={"ability_type": None}), None, None),
            "sans_filtre_bigtarget": (None, None, _sans_filtre_bigtarget),
        })
    out = {}
    for nom, (tree, reg, bigsel) in variantes.items():
        try:
            if tree is not None:
                LOC.legacy_of_combat_tree = tree
            if bigsel is not None:
                LOC.big_target_selector = bigsel
            if reg is not None:
                REG.ABILITY_TRIGGERS["LegacyOfCombat"] = reg
            out[nom] = _rejeu(cap, caster_id, target_id, adj)
        finally:
            LOC.legacy_of_combat_tree = ref_tree
            LOC.big_target_selector = ref_big
            if ref_reg is not None:
                REG.ABILITY_TRIGGERS["LegacyOfCombat"] = ref_reg
    return out


def etape5(seed, board, tours, big_target: bool):
    import probe_509_martial_inspiration as P
    try:
        sid = P._sid()
    except Exception as exc:
        print("[928] host indisponible : %s" % (exc,))
        return False
    if big_target:
        # BRANCHE `then` : un ennemi PORTANT `UnitTrait.BigTarget` a distance 1 de Kariyan.
        a_places = (("astraBullgryn", "6,8"), (P.FILLER, "6,7"))
    else:
        a_places = P.A_PLACES
    a_units = [v for v, _t in a_places]
    sf = os.path.join(os.environ.get("TEMP", "."),
                      "p928_%s_%d.json" % ("bt" if big_target else "adj", os.getpid()))
    m = mesure_live(sid, sf, seed, board, a_units, a_places, tours=tours, big_target=big_target)
    try:
        os.remove(sf)
    except OSError:
        pass
    if m is None:
        return False
    return rapport5(m, big_target)


def rapport5(m, big_target: bool) -> bool:
    ok = True
    vus = 0
    for c in m["casts"]:
        nat = c["natif_par_ability"]
        n1319 = [(t, a) for (t, a, _p) in nat.get(TRIGGERED_ID, ())]
        prof = sorted({p for (_t, _a, p) in nat.get(TRIGGERED_ID, ())})
        p1319 = c["port"]["seq_1319"]
        print("  -- cast --")
        print("     1191  PORT=%s" % ([a for _t, a in c["port"]["seq_1191"]],))
        print("           NATIF=%s" % ([a for (_t, a, _p) in nat.get(1191, ())],))
        print("     1319  PORT (%d coups) = %s" % (len(p1319), p1319))
        print("           NATIF(%d coups) = %s  profils=%s" % (len(n1319), n1319, prof))
        print("     TIRAGES genrand_int32 : PORT=%s  NATIF=%s"
              % (c["tirages_port"], c["tirages_natif"]))
        print("     abilities natives vues : %s" % (sorted(nat),))
        print("     DELTA PV par cible : PORT=%s  NATIF=%s" % (c["port"]["hp"], c["hp_natif"]))
        # L'observable de BOUT EN BOUT : il ne depend d'aucun canal de diagnostic. La ventilation
        # par `Active_Ability_Type` ci-dessus n'est qu'un CONFORT (les `UnitDamaged` des coups
        # declenches n'en portent pas toujours une).
        if c["port"]["hp"] != c["hp_natif"]:
            print("     !! DELTA PV DIVERGENT")
            ok = False
        else:
            vus += 1
        if n1319 and p1319 != n1319:
            print("     !! SEQUENCE 1319 DIVERGENTE")
            ok = False
        if c["tirages_port"] != c["tirages_natif"]:
            print("     !! TIRAGES divergents (port %s / natif %s)"
                  % (c["tirages_port"], c["tirages_natif"]))
            ok = False
        # MUTANTS : chacun doit MORDRE (delta de PV different de la reference), sinon la lecture
        # qu'il retire n'est pas mesuree par ce montage.
        mut = c.get("mutants") or {}
        ref = mut.get("ref") or {}
        ref_cle = (ref.get("hp"), ref.get("tirages"))
        print("     -- mutants (hors-ligne, MEME capture, MEME MT ; compteur = %s) --"
              % (c.get("compteur_live"),))
        for nom, r in mut.items():
            if nom == "ref":
                continue
            # Un mutant MORD s'il change le delta de PV **ou** la consommation RNG : `sans_randomize`
            # ne deplace aucun montant a pool de 1, mais il change le nombre de tirages -- et c'est
            # exactement l'etage qu'il est cense mesurer.
            mord = (r.get("hp"), r.get("tirages")) != ref_cle
            print("        %-24s hp=%-40s tirages=%-4s %s"
                  % (nom, r["hp"], r.get("tirages"), "MORD" if mord else "== REF !!"))
            if not mord:
                ok = False
        if ref.get("hp") != c["port"]["hp"]:
            print("     !! le mutant `ref` ne reproduit pas le rejeu de reference")
            ok = False
        touchees = {v for v, d in c["hp_natif"].items() if d and v not in ("__na__",)}
        # Retire la contribution de 1191, qui ne frappe QUE la cible du cast.
        cible_1191 = {t for (t, _a, _p) in nat.get(1191, ())}
        if big_target:
            # branche `then` : UN SEUL coup (nrOfHits_2 = 1) sur UNE SEULE cible.
            if len(p1319) != 1:
                print("     !! branche BigTarget : le port joue %d coups 1319, attendu 1 "
                      "(nrOfHits_2)" % len(p1319))
                ok = False
        else:
            # branche `else` : `nrOfHits` coups sur CHAQUE ennemi adjacent -> au moins 2 cibles
            # distinctes dans la sequence portee, dont une AUTRE que la cible de 1191.
            cibles = {t for t, _a in p1319}
            if len(cibles) < 2:
                print("     !! branche adjacents : le port ne frappe que %s -- le montage ne "
                      "discrimine pas le << each adjacent >> (cible 1191 = %s, touchees natif = %s)"
                      % (cibles, cible_1191, touchees))
                ok = False
    if not vus:
        print("  AUCUN cast confronte -- verdict IMPOSSIBLE")
        ok = False
    return ok


# --------------------------------------------------------- etape 7 : la face DECISION MOVE, live

def etape7(seed, board, mutant: bool):
    """Confrontation PAR TUILE du terme de mouvement, contre le `Tile(7)` natif.

    DELEGUE a `probe_193c_move_playbook_terms.run` -- foyer UNIQUE de cette mesure (`X_nat =
    Tile(7) - Elevation - TileEffects` sur les hooks EXISTANTS de `scorer-damage-trace`, armes pour
    UN SEUL `aiStepDryRun` puis desarmes ; aucune reinjection). Le probe CHERCHE lui-meme un pas ou
    le terme prend au moins DEUX valeurs distinctes sur les tuiles HOOKEES : un pas ou il est plat
    ne pourrait rien contredire.

    `mutant = True` remplace l'entree de registre par un playbook NUL (et non par son retrait, qui
    ferait planter le pilotage sur `pb0 = None`) : le terme disparait de `X_port` et TOUTES les
    tuiles hookees doivent alors passer en desaccord. Sans ce bras, un `X_nat` qui vaudrait zero
    partout rendrait l'accord trivial."""
    import probe_193c_move_playbook_terms as P193
    from build_pin import BuildPinRefused
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from rl_collect_batch import _resolve_session

    class _Nul:
        def calculate_movement_utility_in_steps(self, tile, ctx, wt):
            return 0.0

    aid = int(TriggeredAbilityType.LegacyOfCombat)
    ref = TRIGGERED_MOVE_PLAYBOOKS.get(aid)
    try:
        P193._exiger_build_des_rva()
    except BuildPinRefused as exc:
        print("[928] hooks de terme de tuile NON armables sur ce build : %s" % (exc,))
        return False
    sid = _resolve_session()
    extra = ["--rank", "17", "--p-units", "custoBladeChampion,deathRotbone",
             "--a-units", "necroWarden,necroOverlord,astraCreed"]
    rid, state = P193._build(seed, board, extra)
    if rid is None:
        return False
    try:
        if mutant:
            TRIGGERED_MOVE_PLAYBOOKS[aid] = _Nul()
        rc = P193.run(sid, rid, "custoBladeChampion", aid, 30)
    finally:
        if ref is not None:
            TRIGGERED_MOVE_PLAYBOOKS[aid] = ref
        P193._r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass
    # `run` rend 0 quand TOUTES les tuiles s'accordent, non nul sinon.
    if not mutant:
        return rc == 0
    # BRAS MUTANT : le terme du port devient PLAT A ZERO sur toutes les tuiles candidates, donc le
    # pilotage ne trouve meme plus un pas discriminant (`rc != 0`, message << aucun pas
    # DISCRIMINANT >>). C'EST le verdict : le natif, lui, met 10/20/30 dans son `Tile(7)` sur les
    # memes tuiles (bras de reference ci-dessus), donc un port sans cette entree de registre serait
    # en desaccord sur 7 tuiles sur 7. La contre-epreuve MORD -- elle ne peut simplement pas
    # s'exprimer en << desaccord >> puisque, sans terme variable, le probe n'arme plus les hooks.
    print("[928] contre-epreuve : sans l'entree de registre, le terme du port est PLAT A ZERO "
          "(rc=%s) -- le natif, lui, vaut 10/20/30 sur ces memes tuiles" % rc)
    return rc != 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, action="append", default=None, help="etape(s) 1..8")
    ap.add_argument("--seed", type=int, default=50901)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--tours", type=int, default=6)
    a = ap.parse_args()
    steps = set(a.step) if a.step else {1, 2, 3, 4}

    bhash, buf, secs, rows = None, None, None, None
    if steps & {1, 2}:
        bhash, buf, secs, rows, _members = p366.load()
        print("[928] build %s -- ability %d (%s)" % (bhash, TRIGGERED_ID, ABILITY))
    if 1 in steps:
        etape1(buf, secs, rows)
    if 2 in steps:
        etape2(buf, secs, rows)
    if 3 in steps:
        etape3()
    if 4 in steps:
        etape4()
    rc = 0
    if 5 in steps:
        print("[928] etape 5 -- CONFRONTATION LIVE, branche << each adjacent enemy >>")
        rc |= 0 if etape5(a.seed, a.board, a.tours, big_target=False) else 1
    if 6 in steps:
        print("[928] etape 6 -- CONFRONTATION LIVE, branche << adjacent Big Target >>")
        rc |= 0 if etape5(a.seed, a.board, a.tours, big_target=True) else 1
    if 7 in steps:
        print("[928] etape 7 -- FACE DECISION MOVE : terme de tuile, port contre natif")
        rc |= 0 if etape7(777, a.board, mutant=False) else 1
    if 8 in steps:
        print("[928] etape 8 -- CONTRE-EPREUVE : registre NEUTRALISE, le desaccord doit APPARAITRE")
        rc |= 0 if etape7(777, a.board, mutant=True) else 1
    if steps & {5, 6, 7, 8}:
        print("[928] VERDICT : %s" % ("OK" if rc == 0 else "DIVERGENCE"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
