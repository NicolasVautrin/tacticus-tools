"""#905 -- `1228 SternguardFocus` (`darkaSternguard` << Ramus >>) : face COMBAT, confront LIVE.

Le porteur est HORS du pool capture : il entre en bataille par INJECTION CATALOGUE
(`catalog_inject.write_augmented_seed_bc`, `docs/rl/case-92-catalog-injection.md` SS6). Le second
porteur, `darkaBossSternguardLHE`, est un npc de MEME kit (memes deux armes, meme active, meme
passif) : le confronter par `--explicit-stats` melangerait << port de l'ability >> et << port des
stats npc >>, on prend donc le porteur LINEUP.

Ce que ces tests PROUVENT (mesures du 2026-08-11, board MC1_67, seed 905905, rank 17) :

  (1) L'arbre est BIT-EXACT sur TROIS regimes de distance, qui sont trois mecaniques differentes
      (le passif `SpecialIssueCombiMelta` mord a `d == 1` / `2` / `3` EXACTEMENT) :
        d=1 -> 4435 live == 4435 port  (arme `Melta`, melee)
        d=2 -> [2201, 2358] live == 2201 + 2358 port (le second est le COUP ADDITIONNEL 1563,
               qui n'est PAS soumis a l'override -- il vit dans `additional_hits`, pas dans
               `total`)
        d=3 -> 2201 live == 2201 port  (arme `Bolter`, + `Pinned` 1065 sur la cible)
  (2) Le montant d'override `PercentageOfAttackCappedAtMax` est EXACT sur les DEUX branches du
      `Min` : branche CAP (regime naturel, override = `maxDmg[50] x mult 180` = 3989) ET branche
      POURCENTAGE (`Damage` du caster abaisse a 1200 -> override = 1200).
  (3) L'override est NET-ZERO : aucun `TemporaryStatOverride` (1296) ne subsiste apres le cast.
  (4) 1228 NE TERMINE PAS le tour -- et le TEMOIN de discrimination est joue dans le meme fichier
      (`1150 PlasmaCannon`, hors `NO_END_TURN_ABILITY_TYPES`, rend `hasAction = False` et refuse
      l'attaque normale enchainee).

CE QUE CES TESTS NE COUVRENT PAS, et il faut le lire avant de s'y fier :
  * l'axe `statPart = 3 Initial` vs `0 Current` n'est PAS discrimine LIVE : dans tous les regimes
    joues le caster n'a AUCUNE modification d'`Attack`, donc les deux lectures coincident. Le `3`
    est LU sur DEUX artefacts natifs independants (`...$$ExecuteBehaviour` et
    `...$$GetOverrideAttackDamageAmount`) ; l'etage 6 ci-dessous le discrimine OFFLINE en posant
    une vraie modification d'`Attack` sur l'etat charge ;
  * `SetsActiveAbilityUsedFlag` : le cooldown (`cooldownTurns = 3`) rend le flag inobservable au
    tour du cast -- le port garde le DEFAUT de base (le flag EST pose) ;
  * le porteur npc `darkaBossSternguardLHE` n'est PAS joue.

ASCII-only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_905_sternguard_focus as PR
from engine.entities.selectors.accessors import Subject
from engine.entities.stats import StatPart, StatType
from engine.dsl.base import Const
from engine.entities.formulas import percentage_of_attack_capped_at_max
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.base import (NO_ABILITY_USED_FLAG_ABILITY_TYPES,
                                          NO_END_TURN_ABILITY_TYPES,
                                          sets_end_turn_flags_for)
from engine.runner.abilities.darkangels import (SternguardFocusAbility,
                                                _sternguard_capped_attack_vars,
                                                sternguard_focus_tree)
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (RANGE_ADJACENT_IF_MELEE_CASTER,
                                               RANGED_BOOL_IF_RANGED_CASTER)
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    # PERIMETRE LARGE, et DERIVE : ces tests rejouent l'arbre DSL de 1228 contre le JEU. L'arbre
    # traverse les feuilles partagees (`AddStatOverrideEffect`, `UseNormalAttack`, `RemoveEffect`),
    # tout le pipeline d'attaque normale (`AttackDamageOperation`, armes, percage, armure, spread),
    # les EFFETS du porteur (`SpecialIssueCombiMelta` 1563/1564/1065) et le chargement d'etat
    # (`runner/snapshot.py`). N'importe lequel de ces fichiers peut faire changer le verdict sans
    # qu'une ligne de `darkangels.py` bouge -- une liste choisie serait un FAUX VERT.
    # Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    "build": True,
    "toujours": False,
    "raison": "Le verdict est un CONFRONT LIVE : il depend du BUILD du jeu (valeurs de "
              "`SternguardFocus.variables`, formule de stats, PRNG) autant que du code. Une mise "
              "a jour peut le faire changer d'avis sans qu'une ligne de `scripts/python` bouge.",
}

STERNGUARD_FOCUS = int(ActiveAbilityType.SternguardFocus)          # 1228
PLASMA_CANNON = int(ActiveAbilityType.PlasmaCannon)                # 1150 -- le TEMOIN
TEMPORARY_STAT_OVERRIDE = int(EffectType.TemporaryStatOverride)    # 1296
PINNED = int(EffectType.Pinned)                                    # 1065


@pytest.fixture(scope="module")
def seedbc(tmp_path_factory):
    """Seed BC AUGMENTE de `darkaSternguard` -- ecrit sous le `tmp_path` de la passe (jamais sous
    `data/`, qui ne porte que des ENTREES versionnees)."""
    return PR.ensure_seed_bc(str(tmp_path_factory.mktemp("905") / "seedbc.json"))


def _confront(sid, seedbc_path, dist, unit_stats=None):
    """Monte un runner a `dist`, rejoue le port sur l'etat PRE-cast (meme `dumpRng`), CASTE live,
    et rend `(port, live_amounts, hp_delta, override_live, effets_post_caster, has_action_post,
    suivi_mutated)`."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    rid = PR.build(sid, seedbc_path, dist, unit_stats=unit_stats)
    try:
        board, dv, ob, cs, rng = PR.snapshot(sid, rid)
        if board is None or not (isinstance(rng, dict) and rng.get("mt")):
            pytest.skip("boardGraph/dumpRng indisponibles")
        bv = PR.units_by_visual(dv)
        assert PR.CASTER_ID in bv, "le porteur injecte n'est pas en bataille : %s" % sorted(bv)
        caster = bv[PR.CASTER_ID]["id"]
        legal = PR.legal_from_here(sid, rid, caster)
        assert legal, ("aucune cible legale a d=%d -- le natif REFUSE le cast, il n'y a rien a "
                       "confronter (verifier que la cible n'est pas en deep-strike)" % dist)
        tgt = legal[0]
        st = load_state(dv, ob, cs, board=board)
        r = IntBasedMersenneTwister()
        r.mt = list(rng["mt"]); r.mti = rng["mti"]
        st.rng = r
        from engine.runner.components import StatsComponent
        sc = st.get_entity(caster).get_component(StatsComponent)
        atk_pre = int(sc.ctx.stat(StatType.ATTACK))
        off = SternguardFocusAbility().execute_behaviour(st, caster, tgt)
        # NET-ZERO cote PORT (et pas seulement cote natif) : l'effet 1296 doit avoir disparu de
        # l'etat charge ET l'`Attack` etre revenue a sa valeur d'avant le cast. Sans ces deux
        # lignes, retirer la feuille `ResetTemporaryAttackOverrideEffect` de l'arbre ne ferait
        # rougir AUCUN test -- la mesure live, elle, ne juge que le natif.
        port_eff = [e.effect_type for e in (st.effects.by_unit.get(int(caster)) or [])
                    if not e.consumed]
        port_atk_post = int(sc.ctx.stat(StatType.ATTACK))
        hp_pre = {u["squadId"]: u.get("hp") for u in (ob.get("units") or [])}
        res = PR.cast(sid, rid, caster, tgt)
        assert res.get("mutated"), "le cast live n'a rien mute : %s" % str(res)[:200]
        live = PR.dmg_by_target(res).get(tgt) or []
        ov_pairs = PR.tag_values(res, "UnitStats_Attack_Override")
        ov_live = [v for v, _e in ov_pairs]
        ov_ent = [e for _v, e in ov_pairs]
        ob2 = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        hp_post = {u["squadId"]: u.get("hp") for u in (ob2.get("units") or [])}
        dv2 = PR.rpc(sid, "decisionView",
                     {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        u2 = next((x for x in (dv2.get("units") or []) if x.get("id") == caster), None)
        eff_post = [e[0] for e in PR.eff_names(dv2, caster)]
        eff_tgt = [e[0] for e in PR.eff_names(dv2, tgt)]
        follow = PR.cast(sid, rid, caster, tgt, 69)
        return {"port": off, "live": live, "caster": caster, "target": tgt,
                "hp_delta": (hp_pre.get(tgt) or 0) - (hp_post.get(tgt) or 0),
                "override_live": ov_live, "override_ent": ov_ent,
                "port_override_unit": (off or {}).get("override_unit"),
                "eff_caster": eff_post, "eff_target": eff_tgt,
                "port_eff_caster": port_eff, "atk_pre": atk_pre, "port_atk_post": port_atk_post,
                "has_action_post": (u2 or {}).get("hasAction"),
                "follow_mutated": bool(follow.get("mutated"))}
    finally:
        PR.dispose(sid, rid)


# ------------------------------------------------------------------ 0. le REGISTRE (offline)

def test_etage0_registre_masque_et_attack_type():
    """1228 est au registre, et les DEUX donnees obligatoires y sont, LUES au ctor.

    Le masque vient du preset STATIQUE `<TargetingOptions statics>+0x00` (forme PRESET-COPIE : le
    ctor n'appelle AUCUN `TargetingOptions..ctor`), dont `TargetingOptions$$.cctor` ecrit
    `rules = 0x4002`, `forceMeleeTarget = 2`, `range <- TargetingRange statics+0x00`. Le
    `AbilityAttackType` est le 3e argument LITTERAL (`mov r8d, 2` au desassemblage)."""
    assert STERNGUARD_FOCUS in ABILITY_CLASSES
    cls = ABILITY_CLASSES[STERNGUARD_FOCUS]
    opts = cls.TARGETING_OPTIONS
    assert opts is not None
    assert int(opts.rules) == 0x4002 == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy)
    assert opts.range == RANGE_ADJACENT_IF_MELEE_CASTER
    assert opts.force_melee_target == RANGED_BOOL_IF_RANGED_CASTER
    assert opts.self_cast is False
    assert ABILITY_ATTACK_TYPE[STERNGUARD_FOCUS] == AbilityAttackType.Others


def test_etage0b_les_deux_frozensets_de_flags_de_tour():
    """1228 est dans `NO_END_TURN_ABILITY_TYPES` (mesure live, etage 4) et HORS de
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES` (elle ne surcharge PAS `SetsActiveAbilityUsedFlag`)."""
    assert ActiveAbilityType.SternguardFocus in NO_END_TURN_ABILITY_TYPES
    assert ActiveAbilityType.SternguardFocus not in NO_ABILITY_USED_FLAG_ABILITY_TYPES
    assert sets_end_turn_flags_for(STERNGUARD_FOCUS, None, None) is False
    # TEMOIN : le verdict n'est pas rendu pour toutes les abilities.
    assert sets_end_turn_flags_for(PLASMA_CANNON, None, None) is True


# ------------------------------------------------------------------ 1-3. confront LIVE

@pytest.mark.parametrize("dist", [1, 2, 3])
def test_etage1_degat_bit_exact_aux_trois_distances(live_session, seedbc, dist):
    """Les TROIS regimes du passif `SpecialIssueCombiMelta` -- et ils changent le resultat.

    `damage_total` du port = `total` (le coup de l'attaque normale, sous override) + le total des
    COUPS ADDITIONNELS (`additional_hits`, qui NE SONT PAS sous override). Comparer le seul
    `total` avait fait croire a une divergence a `d = 2`."""
    m = _confront(live_session, seedbc, dist)
    off = m["port"]
    assert off is not None and off.get("dsl") is True
    assert sum(m["live"]) == m["hp_delta"], "la cascade live ne somme pas au delta de PV"
    assert off["damage_total"] == m["hp_delta"], (
        "d=%d : port %s vs live %s (cascade %s)"
        % (dist, off["damage_total"], m["hp_delta"], m["live"]))
    # Le nombre de COUPS distingue les regimes : 1 a d=1 et d=3, 2 a d=2 (coup additionnel 1563).
    assert len(m["live"]) == (2 if dist == 2 else 1), (
        "d=%d : le regime attendu du passif n'est pas celui joue (%s)" % (dist, m["live"]))
    if dist == 3:
        assert PINNED in m["eff_target"], "d=3 : le `Pinned` du passif (1065) n'est pas pose"


def test_etage2_override_branche_cap(live_session, seedbc):
    """Branche CAP du `Min` : `maxDmg[50] x multiplier 180` = 3989, et l'`Attack` du caster la
    depasse -> l'override VAUT le cap. Le port et la cascade live doivent poser LE MEME nombre."""
    m = _confront(live_session, seedbc, 3)
    cap = m["port"]["cap"]
    assert cap == 3989, "le cap derive du gameconfig a change : %s" % cap
    assert m["port"]["override"] == cap
    assert m["override_live"][0] == cap, (
        "override live %s vs port %s" % (m["override_live"], m["port"]["override"]))
    # L'override porte sur le CASTER (`targets = Caster@+0x48`), JAMAIS sur la cible : la cascade
    # live etiquette `UnitStats_Attack_Override` de l'ENTITE qui le recoit. Sans cette assertion,
    # remplacer `Caster()` par `Target()` dans l'arbre ne ferait rougir aucun test de degat (la
    # cible n'attaque pas dans ce cast).
    assert set(m["override_ent"]) == {m["caster"]}, (
        "l'override live est pose sur %s, pas sur le caster u%s"
        % (m["override_ent"], m["caster"]))
    assert m["port_override_unit"] == m["caster"], (
        "le PORT pose l'override sur %s au lieu du caster u%s"
        % (m["port_override_unit"], m["caster"]))


def test_etage3_override_branche_pourcentage(live_session, seedbc):
    """Branche POURCENTAGE du `Min` -- l'AUTRE branche, et le regime naturel ne l'atteint JAMAIS.

    On abaisse l'`Attack` du caster SOUS le cap (`--unit-stat`-equivalent sur le BC normalise) :
    `dmgPct[50] = 100` -> l'override vaut alors l'`Attack` elle-meme. Sans ce regime, le `Min`
    n'aurait ete confronte que d'un cote."""
    m = _confront(live_session, seedbc, 2, unit_stats=["darkaSternguard:Damage=1200"])
    assert m["port"]["override"] == 1200
    assert m["override_live"][0] == 1200, (
        "override live %s vs 1200 attendu" % m["override_live"])
    assert m["port"]["override"] < m["port"]["cap"], "le regime ne mord pas la bonne branche"
    assert m["port"]["damage_total"] == m["hp_delta"]


# ------------------------------------------------------------------ 4. NET-ZERO + flags de tour

def test_etage4_net_zero_et_ne_termine_pas_le_tour(live_session, seedbc):
    """L'override est POSE puis RETIRE dans le cast (aucun 1296 residuel), et le cast NE TERMINE
    PAS le tour du caster."""
    m = _confront(live_session, seedbc, 1)
    # cote NATIF
    assert TEMPORARY_STAT_OVERRIDE not in m["eff_caster"], (
        "l'override 1296 SUBSISTE apres le cast : %s" % m["eff_caster"])
    assert m["override_live"][-1] == -2147483648, (
        "la cascade live ne porte pas le RETRAIT de l'override : %s" % m["override_live"])
    # cote PORT -- c'est CE volet qui rougit si la feuille `ResetTemporaryAttackOverrideEffect`
    # disparait de l'arbre (la mesure live, elle, ne juge que le natif).
    assert TEMPORARY_STAT_OVERRIDE not in m["port_eff_caster"], (
        "le PORT laisse l'effet 1296 sur le caster : %s" % m["port_eff_caster"])
    assert m["port_atk_post"] == m["atk_pre"], (
        "le PORT laisse l'`Attack` overridee : %s au lieu de %s"
        % (m["port_atk_post"], m["atk_pre"]))
    # FLAGS DE TOUR -- et le PORT doit dire la MEME chose que la mesure.
    assert m["has_action_post"] is True
    assert m["follow_mutated"] is True, (
        "l'attaque normale enchainee n'a rien mute -- 1228 aurait termine le tour")
    assert sets_end_turn_flags_for(STERNGUARD_FOCUS, None, None) is False, (
        "le natif MESURE ne termine pas le tour, le port dit le contraire")


def test_etage4b_temoin_de_discrimination_du_verdict_de_tour(live_session, seedbc):
    """TEMOIN. Sans lui, l'etage 4 ne dirait RIEN : il faut etablir que ce harnais SAIT refuser
    une action apres une ability qui TERMINE le tour. `1150 PlasmaCannon` (hors
    `NO_END_TURN_ABILITY_TYPES`) est jouee dans le MEME runner, avec la MEME sequence."""
    rid = PR.build(live_session, seedbc, 2, p_units=[PR.CASTER_ID, "darkaTerminator"])
    try:
        dv = PR.rpc(live_session, "decisionView",
                    {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        term = PR.units_by_visual(dv)["darkaTerminator"]["id"]
        legal = PR.legal_from_here(live_session, rid, term, PLASMA_CANNON)
        assert legal, "temoin INJOUABLE : aucune cible legale pour 1150"
        res = PR.cast(live_session, rid, term, legal[0], PLASMA_CANNON)
        assert res.get("mutated"), "le temoin n'a pas caste"
        dv2 = PR.rpc(live_session, "decisionView",
                     {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        u2 = next((x for x in (dv2.get("units") or []) if x.get("id") == term), None)
        assert (u2 or {}).get("hasAction") is False, (
            "le TEMOIN ne discrimine pas : 1150 devrait terminer le tour")
        follow = PR.cast(live_session, rid, term, legal[0], 69)
        assert not follow.get("mutated"), (
            "le TEMOIN ne discrimine pas : l'attaque normale passe apres une ability "
            "qui termine le tour -> la mesure de l'etage 4 ne vaudrait rien")
    finally:
        PR.dispose(live_session, rid)


# ------------------------------------------------------------------ 5-6. discriminants OFFLINE

def test_etage5_les_deux_configvar_viennent_du_gameconfig(live_session, seedbc):
    """`cap`/`pct` sont les deux `ConfigVar` COLLAPSEES : elles doivent suivre le NIVEAU et le
    MULTIPLICATEUR du caster, pas etre des constantes ecrites au site."""
    from engine.runner.snapshot import load_state
    rid = PR.build(live_session, seedbc, 2)
    try:
        board, dv, ob, cs, _rng = PR.snapshot(live_session, rid)
        caster = PR.units_by_visual(dv)[PR.CASTER_ID]["id"]
        st = load_state(dv, ob, cs, board=board)
        cap, pct = _sternguard_capped_attack_vars(st, caster)
        assert (cap, pct) == (3989, 100)
        # MUTANT : un niveau d'ability plus bas doit CHANGER les deux valeurs -- sinon le collapse
        # ne lit pas vraiment le gameconfig et l'assertion ci-dessus ne prouverait rien.
        from engine.runner.components import StatsComponent
        sc = st.get_entity(caster).get_component(StatsComponent)
        sc.ctx.active_ability_level = 1
        cap1, pct1 = _sternguard_capped_attack_vars(st, caster)
        assert (cap1, pct1) != (cap, pct) and pct1 == 80, (
            "le collapse ConfigVar ne suit pas le niveau : %s" % ((cap1, pct1),))
    finally:
        PR.dispose(live_session, rid)


def test_etage6_statpart_initial_discrimine_offline(live_session, seedbc):
    """`statPart = 3 Initial` (LU sur DEUX artefacts natifs) vs `0 Current` -- NON discrimine LIVE.

    Aucun regime joue ci-dessus ne pose de modification d'`Attack` sur le caster, donc les deux
    lectures y coincident et une assertion live ne dirait RIEN. On POSE donc une vraie
    modification sur l'etat charge et on verifie (a) que les deux lectures divergent alors, et
    (b) que l'arbre porte prend bien `Initial`."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    rid = PR.build(live_session, seedbc, 2, unit_stats=["darkaSternguard:Damage=1200"])
    try:
        board, dv, ob, cs, _rng = PR.snapshot(live_session, rid)
        caster = PR.units_by_visual(dv)[PR.CASTER_ID]["id"]
        st = load_state(dv, ob, cs, board=board)
        sc = st.get_entity(caster).get_component(StatsComponent)
        initial = int(sc.ctx.stats.get_stat(int(StatType.ATTACK), int(StatPart.INITIAL)))
        # +500 de MODIFICATION d'Attack (`ChangeStat` part 5 = apply) -> `Current != Initial`.
        sc.ctx.stats.change_stat(int(StatType.ATTACK), "probe905", 500)
        cur = int(sc.ctx.stats.get_stat(int(StatType.ATTACK), int(StatPart.CURRENT)))
        assert cur != initial, "le mutant N'A PAS MORDU : Current == Initial (%s)" % cur
        ents = entities_from_state(st, caster, caster)
        n_ini = percentage_of_attack_capped_at_max(Subject(), Const(10 ** 9), Const(100),
                                                  stat_part=int(StatPart.INITIAL))
        n_cur = percentage_of_attack_capped_at_max(Subject(), Const(10 ** 9), Const(100),
                                                  stat_part=int(StatPart.CURRENT))
        from dataclasses import replace
        sub = replace(ents, subject=next(u for u in ents.units if u.get("id") == caster))
        v_ini, v_cur = int(n_ini.evaluate(sub)), int(n_cur.evaluate(sub))
        assert v_ini != v_cur, "le temoin ne discrimine pas les deux `statPart`"
        assert v_ini == initial and v_cur == cur
        # Et l'ARBRE porte prend `Initial` : son montant doit valoir `v_ini`, pas `v_cur`.
        ectx = ExecutionContext(state=st, rng=None)
        sternguard_focus_tree(10 ** 9, 100).execute(ents, ectx)
        posed = [p for n, p in ectx.emitted if n == "AddStatOverrideEffect"]
        assert posed and posed[0]["amount"] == v_ini, (
            "l'arbre lit `Current` (%s) la ou le natif lit `Initial` (%s)"
            % (posed[0]["amount"] if posed else None, v_ini))
    finally:
        PR.dispose(live_session, rid)
