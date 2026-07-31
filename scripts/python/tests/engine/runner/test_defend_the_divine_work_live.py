"""#334 -- la face COMBAT de `DefendTheDivineWork` (1117), confrontee au LIVE.

CE QUE CES TESTS VERROUILLENT. La face DECISION de 1117 etait portee depuis longtemps
(`playbook/noncomparable/heals.py::DefendTheDivineWorkPlaybook` : ciblage, utilite, choix IA), et la
face COMBAT etait un NO-OP -- 1117 n'etait pas dans `ABILITY_CLASSES`, donc `AbilityHandler` posait
les flags de tour et rendait `ported: False`. Cast accepte, tour consomme, ZERO PV restaure et
AUCUNE attaque gratuite. Meme signature de degradation silencieuse que #299.

L'artefact natif enchaine DEUX Operations, et elles n'ont PAS le meme selecteur :

    ExecuteAtomic( Repair( Caster@0x48,
                           Friends(Caster@0x48, AdjacentUnits(CasterTile@0x50, 1, 3))
                             op_Addition Caster@0x48,          # <-- le caster EST repare
                           Get(hpToRepair), ForRepair ),
                   0x2a )
    Execute( Repair_GalvanicFieldAbility.CreateAttackBehavior(
                 dsl@0x30,
                 Friends(Caster@0x48, AdjacentUnits(CasterTile@0x50, 1, 3)) ) )
                                                              # <-- SANS le caster

C'est le PIEGE du cas, et il n'est lisible qu'au DESASSEMBLAGE : le decompile reutilise le meme nom
de variable pour l'arbre avec et sans addition. Les trois tests ci-dessous le verrouillent par des
observables de bataille, pas par relecture de code.

MONTAGE : `defend_the_divine_work_case` (conftest de la tranche) = la porte pytest de
`scripts/python/probe_334_defend_the_divine_work.py`. Trois regimes, positions CONDUITES.

ASCII only (console cp1252).
"""
from __future__ import annotations

import probe_334_defend_the_divine_work as P


def test_repairs_the_caster_and_his_adjacent_friends(defend_the_divine_work_case):
    """ETAGE 1 -- `ExecuteAtomic(Repair(Friends(AdjacentUnits) + Caster, ...), 0x2a)`.

    Trois assertions qui ne se recouvrent pas :
      1. le CASTER est repare de `hpToRepair[level]` (c'est le `op_Addition Caster@0x48`) ;
      2. l'ami MECANIQUE ADJACENT l'est aussi, du MEME montant (c'est le `Friends(AdjacentUnits)`) ;
      3. l'ami MECANIQUE ELOIGNE (>= 3 hex, meme cast, meme trait) ne l'est PAS -- sans ce TEMOIN
         NEGATIF, « ca repare » et « ca repare tout le monde » rendraient le meme vert.
    Et les trois valent LIVE **et** OFFLINE, sur la meme capture.

    Le regime `repair` tient les deux camps eloignes : aucune attaque ne peut partir, donc aucun
    degat ne peut masquer un ecart de reparation."""
    r = defend_the_divine_work_case("repair")
    exp = int(r["hp_to_repair"])
    assert exp > 0, "hpToRepair illisible (lvl=%s mult=%s)" % (r["level"], r["multiplier"])
    assert r["ported"] is True, "1117 NON routee cote combat -- c'est EXACTEMENT le residu #334"
    assert int(r["amount"]) == exp, "montant du port %s != hpToRepair %d" % (r["amount"], exp)

    # le montage doit VRAIMENT blesser, sinon `RepairUnitOperation` refuse et tout est vert a tort
    for vis in (P.CASTER_VIS, P.ADJ_VIS, P.FAR_VIS):
        assert r["missing_before"].get(vis, 0) > exp, (
            "%s doit manquer PLUS que le montant (%s), sinon MaxFillUp sature et masque l'ecart"
            % (vis, r["missing_before"].get(vis)))
    assert r["geometry"]["d_caster_adj"] == 1, "l'allie ADJACENT doit etre a 1 hex du caster"
    assert r["geometry"]["d_caster_far"] >= P.FAR_MIN_DIST, (
        "le temoin negatif doit etre ELOIGNE (d=%d)" % r["geometry"]["d_caster_far"])

    for side in ("live", "off"):
        d = r[side]
        assert d.get(P.CASTER_VIS) == exp, (
            "%s : le CASTER doit etre repare de %d (mesure %s)" % (side, exp, d.get(P.CASTER_VIS)))
        assert d.get(P.ADJ_VIS) == exp, (
            "%s : l'allie ADJACENT doit etre repare de %d (mesure %s)"
            % (side, exp, d.get(P.ADJ_VIS)))
        assert d.get(P.FAR_VIS) == 0, (
            "%s : l'allie ELOIGNE ne doit PAS etre repare (mesure %s) -- la garde d'adjacence"
            " ne discrimine plus" % (side, d.get(P.FAR_VIS)))


def test_galvanic_field_free_attack_fires_from_the_adjacent_friend(defend_the_divine_work_case):
    """ETAGE 2, face POSITIVE -- l'ami adjacent MECANIQUE attaque bien.

    Regime `attack` : l'allie est amene au CONTACT d'un ennemi, le caster est pose adjacent a
    l'allie mais LOIN de tout ennemi. Un ennemi DOIT perdre des PV, live comme offline, et
    l'attaquant rendu par le port doit etre l'ALLIE.

    Le CHOIX de cible n'est plus approxime depuis #338 : `perform_ai_ability_unit_behaviour` passe
    par le moteur d'utilite natif (`AiControl$$ExecuteAbilityActionFor` ->
    `DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`), donc le delta HP
    est verrouille PAR ENNEMI et plus seulement en total."""
    r = defend_the_divine_work_case("attack")
    exp = int(r["hp_to_repair"])
    assert r["normal_targets"][P.ADJ_VIS] > 0, (
        "l'allie adjacent doit AVOIR une cible d'attaque normale, sinon le regime n'est pas atteint")
    assert r["live_enemy_loss"] > 0, (
        "le natif n'a inflige AUCUN degat -- l'etage 2 n'a pas mordu, montage invalide")
    assert r["off_enemy_loss"] > 0, "le port n'a inflige AUCUN degat (etage 2 non porte ?)"
    assert r["live_enemy_loss"] == r["off_enemy_loss"], (
        "degat total live %s != port %s" % (r["live_enemy_loss"], r["off_enemy_loss"]))
    attackers = {a["attacker"] for a in (r["attacks"] or [])}
    assert len(attackers) == 1, "exactement UN attaquant attendu (mesure : %s)" % (r["attacks"],)
    # #338 : la VICTIME aussi, pas seulement le total.
    for vis in P.ENEMY_VIS:
        assert r["off"].get(vis, 0) == r["live"].get(vis, 0), (
            "%s : delta HP port %s != live %s -- le choix de cible a diverge"
            % (vis, r["off"].get(vis), r["live"].get(vis)))
    # la reparation reste, elle, bit-exacte des deux cotes
    for side in ("live", "off"):
        assert r[side].get(P.CASTER_VIS) == exp and r[side].get(P.ADJ_VIS) == exp, (
            "%s : la reparation doit rester %d sur le caster ET l'allie adjacent" % (side, exp))


def test_galvanic_field_free_attack_never_fires_from_the_caster(defend_the_divine_work_case):
    """ETAGE 2, face NEGATIVE -- LE test du cas : le caster n'est PAS dans l'`actingUnits`.

    Regime `caster`, exactement le MIROIR du precedent : c'est le CASTER qui est au contact d'un
    ennemi et l'allie adjacent qui est hors de portee. Si le natif passait `Friends(...) + Caster` a
    `CreateAttackBehavior` (comme il le fait a l'etage 1), un ennemi perdrait des PV.

    CONTRE-EPREUVE DE DISCRIMINANCE, sans quoi « zero degat » ne prouverait rien : `normal_targets`
    mesure, avec le mirror MEME que consomme `PerformAIAttackFromCurrentPosition`
    (`AttackQuery$$HasValidTargets` depuis la tuile COURANTE), que le caster AVAIT une cible et que
    l'allie n'en avait pas. Mesure : caster=1, allie=0 -> zero degat. Le regime `attack` inverse ce
    couple et donne, lui, un degat non nul."""
    r = defend_the_divine_work_case("caster")
    exp = int(r["hp_to_repair"])
    assert r["normal_targets"][P.CASTER_VIS] > 0, (
        "le caster doit POUVOIR frapper depuis sa tuile, sinon le test ne discrimine rien")
    assert r["normal_targets"][P.ADJ_VIS] == 0, (
        "l'allie adjacent ne doit avoir AUCUNE cible, sinon c'est LUI qui expliquerait un degat")
    assert r["live_enemy_loss"] == 0, (
        "le NATIF a inflige %s degats alors que seul le caster pouvait frapper -- le caster serait"
        " donc dans l'actingUnits de l'etage 2" % r["live_enemy_loss"])
    assert r["off_enemy_loss"] == 0, (
        "le PORT a inflige %s degats -- il a garde le `+ Caster` de l'etage 1 dans l'etage 2"
        % r["off_enemy_loss"])
    assert not r["attacks"], "aucune attaque attendue (mesure : %s)" % (r["attacks"],)
    for side in ("live", "off"):
        assert r[side].get(P.CASTER_VIS) == exp and r[side].get(P.ADJ_VIS) == exp, (
            "%s : la reparation, elle, DOIT avoir eu lieu sur les deux (%d)" % (side, exp))


def test_two_adjacent_mechanics_both_attack_and_the_caster_still_does_not(
        defend_the_divine_work_case):
    """GENERALISATION la plus discriminante du lot -- DEUX allies mecaniques adjacents.

    Les trois autres regimes n'en placent qu'UN : un port qui ne ferait attaquer que la PREMIERE
    unite du selecteur (ou qui poserait/retirerait l'override sur un seul) y serait invisible. Ici
    l'`actingUnits` en contient deux, tous deux au contact d'un ennemi.

    Trois choses a la fois, et aucune n'est redondante :
      1. TROIS reparations de `hpToRepair` (les 2 adjacents + le caster) ;
      2. DEUX attaques, et le degat ENNEMI TOTAL est le meme live et offline ;
      3. le caster ne frappe TOUJOURS pas -- alors qu'ici `normal_targets` lui donne des cibles.

    C'EST LE REGIME QUI A REVELE #338, et il en est desormais la GARDE. Avant le fix, les deux
    attaquants concentraient leurs coups sur UN ennemi (le plus proche, tie-break id) la ou le
    natif les VENTILE : total identique des deux cotes (18038), repartition fausse (18038 sur un
    seul vs 7795 + 10243 sur deux). Aucun test ne l'attrapait, parce qu'aucun ne comparait autre
    chose que le total. On verrouille donc le delta HP **par ennemi**."""
    r = defend_the_divine_work_case("two")
    exp = int(r["hp_to_repair"])
    assert r["geometry"]["d_caster_adj"] == 1 and r["geometry"]["d_caster_far"] == 1, (
        "les DEUX allies doivent etre adjacents au caster (mesure %s / %s)"
        % (r["geometry"]["d_caster_adj"], r["geometry"]["d_caster_far"]))
    assert r["normal_targets"][P.ADJ_VIS] > 0 and r["normal_targets"][P.FAR_VIS] > 0, (
        "les DEUX allies doivent avoir une cible, sinon une seule attaque partirait")
    assert len(r["repairs"] or []) == 3, (
        "trois reparations attendues (2 adjacents + caster) : %s" % (r["repairs"],))
    for vis in (P.CASTER_VIS, P.ADJ_VIS, P.FAR_VIS):
        for side in ("live", "off"):
            assert r[side].get(vis) == exp, "%s : %s doit etre repare de %d" % (side, vis, exp)
    assert len({a["attacker"] for a in (r["attacks"] or [])}) == 2, (
        "DEUX attaquants distincts attendus : %s" % (r["attacks"],))
    assert r["live_enemy_loss"] == r["off_enemy_loss"] > 0, (
        "degat ENNEMI TOTAL live %s != port %s" % (r["live_enemy_loss"], r["off_enemy_loss"]))
    # #338 -- LA garde du choix de cible : la VENTILATION, pas seulement la somme.
    for vis in P.ENEMY_VIS:
        assert r["off"].get(vis, 0) == r["live"].get(vis, 0), (
            "%s : delta HP port %s != live %s -- les deux attaquants ne choisissent plus les memes"
            " cibles que le natif" % (vis, r["off"].get(vis), r["live"].get(vis)))
    assert len([v for v in P.ENEMY_VIS if r["live"].get(v, 0) < 0]) == 2, (
        "le natif VENTILE ses deux attaques sur DEUX ennemis (mesure de reference : -7795 / -10243)"
        " -- si ce montage n'en touche plus qu'un, il ne discrimine plus rien : %s" % (r["live"],))
    caster_off = next((a for a in (r["attacks"] or [])
                       if a["attacker"] == r["repairs"][-1]["target"]), None)
    assert caster_off is None, (
        "le CASTER (dernier repare, cf. `Friends(...) + Caster`) ne doit jamais attaquer : %s"
        % (r["attacks"],))


def test_1117_is_in_the_combat_registry_with_its_mask_and_attack_type():
    """GARDE DE NON-REGRESSION -- le CLIQUET du CLAUDE.md : une ability qui entre dans
    `ABILITY_CLASSES` pose son `TARGETING_OPTIONS` **et** son `ABILITY_ATTACK_TYPE` dans le MEME
    commit. Les deux litteraux sont ceux de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$.ctor` :

        TargetingOptions..ctor(&opts, 1, &<TargetingRange statics>+0x30, 1, 0x8c02, 0, 0)
        AActiveAbility..ctor(this, &opts, 2)

    (surcharge « FLAGS DIRECTS » a 7 arguments -> le litteral EST le masque effectif)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.targeting import RANGE_ADJACENT, RANGED_BOOL_FALSE
    assert 1117 in ABILITY_CLASSES, "1117 absente d'ABILITY_CLASSES"
    opts = getattr(ABILITY_CLASSES[1117], "TARGETING_OPTIONS", None)
    assert opts is not None, "1117 sans TARGETING_OPTIONS"
    assert int(opts.rules) == 0x8c02, "masque 0x%x != 0x8c02" % int(opts.rules)
    assert opts.self_cast is True, "isSelfCasting = 1 au ctor"
    assert opts.range == RANGE_ADJACENT, "range = TargetingRange statics+0x30 = RANGE_ADJACENT"
    assert opts.force_melee_target == RANGED_BOOL_FALSE, "forceMeleeTarget = 1 = RangedBool.False"
    assert ABILITY_ATTACK_TYPE.get(1117) == AbilityAttackType.Others, (
        "1117 sans AbilityAttackType.Others (3e argument du ctor de base)")
