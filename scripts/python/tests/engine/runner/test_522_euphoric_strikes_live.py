"""#522 -- `EuphoricStrikes` (ActiveAbilityType 1198, `emperExultant` << Laviscus >>), face COMBAT.

Avant cette tranche, 1198 etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, la decision
pouvait la choisir et l'execution l'ignorait -- 0 degat, 0 effet, AUCUNE erreur.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline`   -- l'entree au registre porte SES DEUX donnees obligatoires
    (`TARGETING_OPTIONS` lu du preset statique `<TargetingOptions statics>+0x40` PRIS TEL QUEL,
    `ABILITY_ATTACK_TYPE` = 3e argument d'`AActiveAbility$$.ctor`), et le contrat de DISJONCTION
    est verifie PAR LE CODE (1198 dans AUCUNE des listes `*_UNPORTED`). Le masque est confronte a
    celui de `ThunderousAssault`, qui lit LE MEME preset mais y OR-e `0x10000000` : c'est le seul
    voisin capable de faire ecrire un masque faux par copier-coller ;
  * `test_arbre_offline`      -- la FORME de l'arbre : DEUX volets, dans l'ORDRE du decompile
    (`attaque & AddEffect`), le selecteur de chacun, et surtout la DUREE, qui est `Direct(1)` (un
    nombre de TOURS deja resolu) et NON un `TurnsFromRounds(1)` -- la conversion changerait la
    duree ;
  * `test_canal_gates_offline` -- les DEUX noeuds du trigger du canal crit, chacun avec sa
    contre-epreuve : `get_OwnerIsTarget` (le porteur EST le defenseur) et
    `AmountIsGreaterThanZero(StatAmount(Caster, CritChance, Current))` (le SUJET est l'ATTAQUANT).
    Une cle absente doit FERMER le noeud, jamais l'ouvrir ;
  * `test_retrait_registre_offline` -- `EFFECT_TRIGGERS[1429]` existe et ecoute LES DEUX events du
    `op_BitwiseOr` natif (`On(9 = Attack)` et `On(0 = UnitDeath)`). Sans cette entree le +crit ne
    serait pas une charge a usage unique mais un buff de tout le tour ;
  * `test_cast_bit_exact_live` -- le degat du cast, natif vs port, MT offline cale sur `dumpRng`,
    ET le nombre de tirages `genrand_int32` consomme de part et d'autre ;
  * `test_marque_posee_live`   -- 1429 est pose sur la CIBLE, cote natif comme cote port ;
  * `test_canal_crit_live`     -- l'attaque SUIVANTE portee contre la cible marquee coute
    exactement ce que le port calcule AVEC la marque, et la contre-epreuve HORS LIGNE sur la MEME
    capture (marque consommee) rend un resultat DIFFERENT : sans elle, le vert de l'accord serait
    un accord en regime DEGENERE ;
  * `test_retrait_live`        -- apres cette attaque, 1429 a DISPARU des deux cotes.

Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268). Le porteur
`emperExultant` est un HERO `lineup` HORS seed BC -> `catalog_inject`
(cf. `docs/rl/case-92-catalog-injection.md` §6) ; `--list-pool` ne le rend pas, et ce n'est PAS un
refus (aucun `data/unspawnable_rank*.json` n'existe).

⚠ Le trait `ThrillSeekers` du caster est RETIRE du montage (`--unit-stat`), et ce n'est pas une
commodite : avec le kit complet a `--crit 0,700` le port consomme UN tirage de plus que le natif
(residu `#522-r1`, mesure et attribuee dans `probe_522_euphoric_strikes.py`). Le regime NOMINAL
avec kit COMPLET, lui, est bit-exact -- c'est le probe qui le tient.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE et non feuille a feuille : charger UNE ability tire le
        # registre, le vocabulaire DSL, les Operations, le canal CRIT et le dispatch de triggers --
        # une liste choisie serait un faux vert, elle ne pourrait pas montrer le module qu'elle a
        # oublie. Foyers vraiment load-bearing, pour la relecture humaine :
        # `abilities/emperorschildren.py` (l'arbre), `entities/effects/loki/euphoric_strikes.py`
        # (le canal), `operations/triggers/loki/euphoric_strikes.py` (le retrait),
        # `handler.py` + `attack_type.py` + `targeting.py` (les registres confrontes),
        # `entities/effects/factory.py` et `operations/triggers/dispatch/registry.py` (les deux
        # autres registres), `operations/damage.py` (`_crit_params`, le foyer du canal).
        "scripts/python/engine/**/*.py",
        # Les modules de la RACINE : la cascade des conftest de `tests/engine/runner` en importe
        # une vingtaine. Ils entrent dans la fermeture de CE fichier, qu'il les cite ou non.
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1198 EuphoricStrikes` : l'oracle est le jeu "
              "lui-meme (degat, ORDRE des tirages, pose de la marque, valeur du bonus de crit, "
              "retrait sur `On(Attack)`). Un changement de build peut donc faire changer ce "
              "fichier d'avis sans qu'une ligne du port bouge.",
}

import uuid

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.euphoric_strikes import EuphoricStrikesExtraCritEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatPart, StatType
from engine.dsl.event_trigger_type import EventTriggerType
from engine.runner.abilities.emperorschildren import (EUPHORIC_STRIKES_EFFECT, EUPHORIC_STRIKES_ID,
                                                      EuphoricStrikesAbility,
                                                      euphoric_strikes_profile,
                                                      euphoric_strikes_tree)
from engine.runner.components import HealthComponent, StatsComponent, unit_state_for_effects
from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "522"
CASTER = "emperExultant"                # HERO `lineup` hors seed BC -> catalog_inject
ALLY = "ultraTitus"                     # l'attaquant qui exerce le canal crit
FOE = "necroWarden"                     # la CIBLE marquee
FOE_B = "orksNob"                       # temoin LOIN, jamais marque
ABILITY = int(ActiveAbilityType.EuphoricStrikes)          # 1198 = 0x4ae
EFFECT = int(EffectType.EuphoricStrikes_ExtraCrit)        # 1429 = 0x595
CRIT_BASE = 70                          # `--crit` : 70 + extraCritChance(30) = 100 -> discriminant


# ------------------------------------------------------------------ helpers de lecture live

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _by_vis(dv, vis):
    return next((u for u in _units(dv) if (u.get("visualId") or "") == vis), None)


def _hp(ob, uid):
    """`observeBattle` indexe par `squadId`, PAS par `id` : lire `id` rend `None` partout et
    fabrique un accord en regime DEGENERE (deux dicts vides), donc zero preuve."""
    for u in ((ob or {}).get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _effets(dv, uid):
    for u in _units(dv):
        if u.get("id") == uid:
            return sorted(e.get("effectType") for e in (u.get("effects") or [])
                          if isinstance(e, dict) and e.get("effectType") is not None)
    return None


def _effets_port(st, uid):
    if st.effects is None:
        return []
    return sorted(e.effect_type for e in st.effects.by_unit.get(int(uid), []) if not e.consumed)


def _hp_port(st, uid):
    e = st.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _act(rpc, rid, action, timeout=240):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _etat(rpc, rid, board):
    """La capture COMPLETE + le MT cale sur `dumpRng` : sans lui le degat offline est un faux 0."""
    dv = _vue(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 90)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 90)
    assert _ok(dv) and _ok(ob) and _ok(snap), "capture live KO -- montage non installe"
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    assert _ok(s), "dumpRng KO -- MT non calable ; sans lui le degat offline est un faux 0"
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(s["mt"]), s["mti"]
    st.rng = rng
    return dv, ob, st, s


def _tirages(rng0, mt_c, mti_c, cap=4000):
    """Nombre de `genrand_int32` pour aller de l'etat INITIAL a l'etat CIBLE.

    ⚠ Une soustraction de `mti` serait FAUSSE : le compteur MT19937 se recharge tous les 624
    tirages et rendrait alors un delta NEGATIF."""
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng0["mt"]), rng0["mti"]
    for n in range(cap + 1):
        if r.mti == mti_c and r.mt == list(mt_c):
            return n
        r.genrand_int32()
    return None


def _crit_effectif(st, att_id, tgt_id):
    """La crit chance EFFECTIVE du coup, par le FOYER UNIQUE du canal -- l'ETAGE isole, pas un
    scalaire de sortie : un ecart de degat total peut naitre de dix endroits, une crit chance de
    100 au lieu de 70 n'en a qu'un."""
    e = st.get_entity(att_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return (None, None, None)
    eff = ([] if st.effects is None
           else list(st.effects.active_effects(int(att_id),
                                               unit_state_for_effects(st, int(att_id)))))
    return AttackDamageOperation._crit_params(sc.ctx, eff, state=st, att_id=int(att_id),
                                              tgt_id=int(tgt_id), is_ranged=False,
                                              is_normal_attack=True)


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION -- RE-LUES PAR LE
    CODE, jamais recopiees d'un voisin."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert ABILITY_CLASSES.get(ABILITY) is EuphoricStrikesAbility, "1198 absente du registre"
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack, (
        "3e argument d'`AActiveAbility$$.ctor` = 0 = DirectTargetAttack")

    opts = EuphoricStrikesAbility.TARGETING_OPTIONS
    assert opts is not None, ("sans TARGETING_OPTIONS, `get_invalid_target_reason` rend 0 "
                              "immediatement : degradation PERMISSIVE et silencieuse")
    # Le preset `<TargetingOptions statics>+0x40` est PRIS TEL QUEL : `rules` = 0x4000, un seul bit.
    assert int(opts.rules) == int(TR.TargetIsEnemy) == 0x4000
    assert opts.self_cast is False
    # `TargetingRange` statics+0x30 : `onlyAdjacent = RangedBool.True`, `overrideRange = 1`.
    assert opts.range.override_range == 1 and not opts.range.use_whole_board
    assert not opts.range.use_range_from_config

    # ⚠ LE VOISIN MENT, et il est a portee de copier-coller : `ThunderousAssaultAbility$$.ctor` lit
    # LE MEME preset `+0x40`, mais le passe a la surcharge PRESET + FLAGS -- son masque effectif
    # vaut `0x10000000 | 0x4000`. Si les deux masques devenaient egaux, c'est qu'un des deux aurait
    # ete recopie de l'autre.
    from engine.runner.abilities.loki.strike import ThunderousAssaultAbility
    assert int(ThunderousAssaultAbility.TARGETING_OPTIONS.rules) != int(opts.rules), (
        "1043 et 1198 lisent le MEME preset mais PAS la meme surcharge de ctor")
    assert int(ThunderousAssaultAbility.TARGETING_OPTIONS.rules) & int(TR.CasterCanMove), (
        "le bit 28 `CasterCanMove` appartient a 1043 seul (flag OR-e), jamais a 1198")

    # DISJONCTION : une ability PORTEE ne doit figurer dans AUCUNE liste `*_UNPORTED`.
    from engine.runner.abilities import targeting as _tg
    for nom in ("TARGETING_OPTIONS_UNPORTED", "DYNAMIC_TARGET_RULE_UNPORTED"):
        table = getattr(_tg, nom, None)
        if table is not None:
            assert ABILITY not in table, "1198 est PORTEE : elle n'a rien a faire dans %s" % nom


def test_arbre_offline():
    """La FORME de l'arbre, terme a terme : deux volets `op_and`, dans l'ORDRE du decompile."""
    from engine.entities.behaviours import Seq
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import AddEffect

    arbre = euphoric_strikes_tree()
    assert isinstance(arbre, Seq), "`op_BitwiseAnd` -> `op_and` (`CombinedBehaviour`)"
    feuilles = list(getattr(arbre, "children", ()) or ())
    if len(feuilles) != 2:                     # arbre binaire : (gauche, droite)
        feuilles = [getattr(arbre, "left", None), getattr(arbre, "right", None)]
    assert len(feuilles) == 2 and all(f is not None for f in feuilles), (
        "l'arbre natif a EXACTEMENT deux volets : l'attaque puis l'AddEffect")
    attaque, marque = feuilles
    assert isinstance(attaque, AttackWithAttackDamage)
    assert isinstance(marque, AddEffect)

    # L'attaque : config 1198, profil LU du gameconfig (jamais code en dur), melee, famille ATTACK.
    assert getattr(attaque, "ability_id", None) == EUPHORIC_STRIKES_ID
    assert euphoric_strikes_profile() == "Power", (
        "`GetDamageProfile` = la constante `damageProfile` du gameconfig")
    assert getattr(attaque, "profile", None) == euphoric_strikes_profile()
    assert getattr(attaque, "is_melee", None) is True     # `attackRangeType = Melee`
    assert getattr(attaque, "native_factory", "attack") == "attack", (
        "`DSLBehaviors$$AttackWithAttackDamage`, jamais `AttackWithAbilityDamage`")

    # La marque : effet 1429, sur la CIBLE, UN TOUR, source par DEFAUT (= le caster @+0x48).
    assert marque.effect_type == EFFECT == 1429
    assert marque.name == EffectType.EuphoricStrikes_ExtraCrit.name
    assert marque.duration_turns == 1, (
        "`turns = <DSLFormulas+0x20> = Direct(1)` : un nombre de TOURS deja resolu -- un "
        "`TurnsFromRounds(1)` passerait par `ConvertRoundsToTurns` et changerait la duree")
    assert marque.source_ref is None, ("source = `Caster@DSLSelectors+0x48`, ce qui est le DEFAUT "
                                       "de la feuille (`entities.caster`)")
    assert marque.scale_from_source is True, (
        "3e argument natif = `AActiveAbility$$get_AbilityStateReference(this)` : l'effet resout "
        "son `ConfigVar` contre l'etat d'ability de sa SOURCE")


def test_canal_gates_offline():
    """Les DEUX noeuds du trigger du canal, chacun avec sa contre-epreuve. Une cle ABSENTE doit
    FERMER le noeud (« present != applique »), jamais l'ouvrir."""
    eff = EuphoricStrikesExtraCritEffect(effect_type=EFFECT,
                                         name=EffectType.EuphoricStrikes_ExtraCrit.name)
    eff.active_ability_level = 50
    extra = int(ability_var(EUPHORIC_STRIKES_ID, "extraCritChance", 50, multiplier_pct=100) or 0)
    assert extra > 0, "contre-epreuve VACUE si `extraCritChance` est nul"

    plein = {"owner_id": 7, "tgt_id": 7, "caster_crit_chance": 20}
    assert eff.create_effect_crit_chance_bonus_for_attack(plein) == extra

    # `get_OwnerIsTarget` = `AreEqual(Owner@+0x30, Target@+0x60)`.
    assert eff.create_effect_crit_chance_bonus_for_attack(
        {**plein, "tgt_id": 8}) is None, "le porteur n'est pas le defenseur -> AUCUN bonus"
    for cle in ("owner_id", "tgt_id"):
        ctx = dict(plein)
        ctx.pop(cle)
        assert eff.create_effect_crit_chance_bonus_for_attack(ctx) is None, (
            "identite NON PROUVEE (%s absente) => noeud FAUX, jamais permissif" % cle)

    # `AmountIsGreaterThanZero(StatAmount(Caster@+0x48, CritChance, Current))` -- le SUJET est
    # l'ATTAQUANT. Une unite a crit chance de base nulle ne gagne RIEN.
    assert eff.create_effect_crit_chance_bonus_for_attack({**plein, "caster_crit_chance": 0}) is None
    ctx = dict(plein)
    ctx.pop("caster_crit_chance")
    assert eff.create_effect_crit_chance_bonus_for_attack(ctx) is None, (
        "grandeur NON MESUREE => noeud FAUX (tri-etat), jamais permissif")

    # Les deux enums qualifies au site, pour que le NOM soit ce qui est confronte, pas l'ordinal.
    assert int(StatType.CRIT_CHANCE) == 9 and int(StatPart.CURRENT) == 0

    # UN SEUL canal : le build ne porte AUCUN `CreateCritDamageBonus` pour cette classe.
    assert eff.create_effect_crit_damage_bonus_for_attack(plein) is None, (
        "1429 n'a pas de canal crit-DEGAT -- en ajouter un serait une invention")


def test_retrait_registre_offline():
    """`EFFECT_TRIGGERS[1429]` existe et ecoute LES DEUX events du `op_BitwiseOr` natif."""
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.runner.operations.triggers.loki.euphoric_strikes import EuphoricStrikesExtraCritRemove

    entrees = EFFECT_TRIGGERS.get(EFFECT) or []
    assert EuphoricStrikesExtraCritRemove in entrees, (
        "sans cette entree le +crit ne serait pas une CHARGE A USAGE UNIQUE mais un buff de tout "
        "le tour : regression PERMISSIVE et silencieuse")
    ev = set(EuphoricStrikesExtraCritRemove.event_ids)
    assert ev == {int(EventTriggerType.Attack), int(EventTriggerType.UnitDeath)}, (
        "`On(9) & OwnerIsTarget | On(0) & AreEqual(Target, EffectSource)` -- DEUX events")
    assert EuphoricStrikesExtraCritRemove.effect_type == EFFECT


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner, tmp_path_factory):
    """Runner ou `emperExultant` est INJECTE au catalogue (il est hors seed BC), positions FORCEES.

    ⚠ Le trait `ThrillSeekers` du caster est retire : residu `#522-r1` (cf. l'en-tete). Le regime
    NOMINAL avec kit COMPLET est tenu par `probe_522_euphoric_strikes.py`."""
    import catalog_inject
    bc = tmp_path_factory.mktemp("seedbc") / ("laviscus-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [CASTER])
    built = build_runner(SEED, extra=[
        "--seed-bc", str(bc), "--board", BOARD, "--rank", "17", "--no-ai",
        "--crit", "%d,700" % CRIT_BASE, "--hp-target", "400000",
        "--unit-stat", '%s:Traits=["Hero"]' % CASTER,
        "--p-units", "%s,%s" % (CASTER, ALLY), "--a-units", "%s,%s" % (FOE, FOE_B),
        "--place", "%s:4,5" % CASTER, "--place", "%s:4,7" % ALLY,
        "--a-place", "%s:4,6" % FOE, "--a-place", "%s:0,3" % FOE_B], keep=True)
    rid = built["rid"]
    dv = _vue(rpc, rid)
    for vis in (CASTER, ALLY, FOE, FOE_B):
        assert _by_vis(dv, vis) is not None, "%s absent du plateau -- montage KO" % vis
    voulu = {CASTER: (4, 5), ALLY: (4, 7), FOE: (4, 6), FOE_B: (0, 3)}
    for vis, p in voulu.items():
        u = _by_vis(dv, vis)
        pos = ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
        assert pos == p, "placement REFUSE pour %s : %r != %r" % (vis, pos, p)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq"),
            "ids": {vis: _by_vis(dv, vis)["id"] for vis in voulu}}


@pytest.fixture(scope="module")
def scenario(env, rpc):
    """LE SCENARIO COMPLET, joue UNE fois, dans l'ORDRE ; les tests n'en sont que des LECTURES.

    L'ordre est CONTRAINT : l'attaque de l'allie CONSOMME la marque (`EFFECT_TRIGGERS[1429]`), donc
    tout ce qui lit la crit chance doit etre mesure AVANT elle -- lire apres rendrait la valeur NUE
    des deux cotes et accuserait le canal a tort."""
    rid, board, ids = env["rid"], env["board"], env["ids"]
    cid, tid, aid, bid = ids[CASTER], ids[FOE], ids[ALLY], ids[FOE_B]

    # --- LE CAST ---------------------------------------------------------------------------
    dv0, ob0, st, rng0 = _etat(rpc, rid, board)
    hp0_nat, hp0_off = _hp(ob0, tid), _hp_port(st, tid)
    runner = Runner(st).install_default_handlers(20)
    res = _act(rpc, rid, {"kind": "ability", "casterId": cid, "targetId": tid,
                          "abilityType": ABILITY})
    a0 = ((res or {}).get("actions") or [{}])[0]
    assert a0.get("ok") and a0.get("mutated"), "le natif REFUSE le cast : %r" % (a0,)
    rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
    ob1 = rpc("observeBattle", {"runnerId": rid}, 90)
    runner.apply(ActiveAbilityMessage(cid, tid, ABILITY))
    diag = runner.ability_handler.last or {}
    out = {"rid": rid, "cid": cid, "tid": tid, "aid": aid, "bid": bid, "diag": diag,
           "cast_nat": (hp0_nat or 0) - (_hp(ob1, tid) or 0),
           "cast_off": (hp0_off or 0) - (_hp_port(st, tid) or 0),
           "tirages_nat": _tirages(rng0, rng1.get("mt"), rng1.get("mti")),
           "tirages_off": _tirages(rng0, st.rng.mt, st.rng.mti),
           "eff_nat": _effets(_vue(rpc, rid), tid), "eff_off": _effets_port(st, tid)}

    # --- LE CANAL : deux etats JUMEAUX depuis la MEME capture -------------------------------
    dv2, ob2, st_avec, rng2 = _etat(rpc, rid, board)
    _dv2b, _ob2b, st_sans, _r2b = _etat(rpc, rid, board)
    for e in (st_sans.effects.by_unit.get(int(tid)) or []):
        if e.effect_type == EFFECT:
            e.consumed = True                      # CONTRE-EPREUVE : la marque retiree
    out["cc_marque"] = _crit_effectif(st_avec, aid, tid)[0]
    out["cc_sans"] = _crit_effectif(st_sans, aid, tid)[0]
    out["cc_autre"] = _crit_effectif(st_avec, aid, bid)[0]

    att = _by_vis(dv2, ALLY)
    na = next((a["id"] for a in (att.get("abilities") or [])
               if a.get("kind") == "normal" and a.get("id") is not None), None)
    assert na is not None, "attaque normale de l'allie introuvable -- montage non conforme"
    hp1_nat = _hp(ob2, tid)
    res2 = _act(rpc, rid, {"kind": "ability", "casterId": aid, "targetId": tid,
                           "abilityType": int(na)})
    b0 = ((res2 or {}).get("actions") or [{}])[0]
    assert b0.get("ok") and b0.get("mutated"), "l'attaque de l'allie est REFUSEE : %r" % (b0,)
    ob3 = rpc("observeBattle", {"runnerId": rid}, 90)
    out["na_nat"] = (hp1_nat or 0) - (_hp(ob3, tid) or 0)

    h = _hp_port(st_avec, tid)
    Runner(st_avec).install_default_handlers(20).apply(AttackUnitMessage(aid, tid))
    out["na_avec"] = (h or 0) - (_hp_port(st_avec, tid) or 0)
    h = _hp_port(st_sans, tid)
    Runner(st_sans).install_default_handlers(20).apply(AttackUnitMessage(aid, tid))
    out["na_sans"] = (h or 0) - (_hp_port(st_sans, tid) or 0)

    out["eff2_nat"] = _effets(_vue(rpc, rid), tid)
    out["eff2_off"] = _effets_port(st_avec, tid)
    return out


def test_cast_bit_exact_live(scenario):
    """Le degat du cast, natif vs port -- ET le nombre de tirages, qui LOCALISE une divergence."""
    diag = scenario["diag"]
    # FACE EXECUTER : sans ce booleen, un cast non porte serait un no-op SILENCIEUX (0 degat,
    # 0 erreur), et la comparaison de deltas passerait pour un accord.
    assert diag.get("ported") is True, "1198 non portee : %r" % (diag,)
    assert diag.get("emitted") == ["AttackWithAttackDamage", "AddEffect"], (
        "l'arbre doit emettre SES DEUX volets, dans l'ordre : %r" % (diag.get("emitted"),))
    assert scenario["cast_nat"] > 0, ("temoin NUL -- un accord en regime DEGENERE ne prouve rien")
    assert scenario["cast_off"] == scenario["cast_nat"], (
        "degat du cast : port %s vs natif %s" % (scenario["cast_off"], scenario["cast_nat"]))
    assert scenario["tirages_nat"] is not None and scenario["tirages_off"] is not None
    assert scenario["tirages_off"] == scenario["tirages_nat"], (
        "meme degat mais tirages differents (%s vs %s) => STRUCTURE, pas arithmetique"
        % (scenario["tirages_off"], scenario["tirages_nat"]))


def test_marque_posee_live(scenario):
    """1429 est pose sur la CIBLE, des deux cotes -- c'est le second volet de l'arbre."""
    assert EFFECT in (scenario["eff_nat"] or []), (
        "le NATIF ne pose pas 1429 : la RE de l'`AddEffect` serait fausse (%r)"
        % (scenario["eff_nat"],))
    assert EFFECT in scenario["eff_off"], "le PORT ne pose pas 1429 (%r)" % (scenario["eff_off"],)


def test_canal_crit_live(scenario):
    """Le canal, a DEUX etages : la crit chance EFFECTIVE (isolee) puis le DEGAT (observable)."""
    extra = int(ability_var(EUPHORIC_STRIKES_ID, "extraCritChance", 50, multiplier_pct=100) or 0)
    assert extra > 0, "contre-epreuve VACUE si `extraCritChance` est nul"
    assert scenario["cc_sans"] == CRIT_BASE, (
        "la crit chance NUE de l'allie doit valoir le `--crit` du montage : %r"
        % (scenario["cc_sans"],))
    assert scenario["cc_marque"] == scenario["cc_sans"] + extra, (
        "le bonus applique n'est pas `extraCritChance` : %r vs %r + %r"
        % (scenario["cc_marque"], scenario["cc_sans"], extra))
    # `get_OwnerIsTarget` : la marque vit sur la CIBLE ; un coup porte sur une AUTRE unite ne doit
    # RIEN recevoir. Sans ce noeud, tout porteur du board bufferait tout le monde.
    assert scenario["cc_autre"] == scenario["cc_sans"], (
        "la marque buffe un coup porte sur une AUTRE unite (%r)" % (scenario["cc_autre"],))

    assert scenario["na_avec"] != scenario["na_sans"], (
        "regime NON DISCRIMINANT : avec et sans la marque donnent le meme degat, donc ce bras "
        "ne mesure PAS le canal (%r)" % (scenario["na_avec"],))
    assert scenario["na_nat"] == scenario["na_avec"], (
        "le natif ne suit PAS le port marque : %s vs %s"
        % (scenario["na_nat"], scenario["na_avec"]))


def test_retrait_live(scenario):
    """`On(9 = Attack) & OwnerIsTarget` : la marque est une CHARGE A USAGE UNIQUE."""
    assert EFFECT not in (scenario["eff2_nat"] or []), (
        "le NATIF garde 1429 apres l'attaque -- la lecture du `CreateRemoveEffectTrigger` serait "
        "fausse (%r)" % (scenario["eff2_nat"],))
    assert EFFECT not in scenario["eff2_off"], (
        "le PORT garde 1429 : `EFFECT_TRIGGERS[1429]` est muet, le +crit deviendrait un buff de "
        "tout le tour (%r)" % (scenario["eff2_off"],))
