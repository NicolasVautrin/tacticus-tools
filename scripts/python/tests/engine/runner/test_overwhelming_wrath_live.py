"""CONFRONT LIVE de `1141 OverwhelmingWrath` (`worldEightbound` Azkor, WorldEaters, HERO) -- #503.

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * le cast NE FRAPPE PAS -- ET NE TIRE RIEN. L'audit `combat-ability-coverage` classe 1141
    `DAMAGE(Eviscerate)` et son profil annonce QUATRE mecaniques (`dmg_bonus`, `dmg_reduction`,
    `crit`, `block`), mais
    `IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour`
    ne porte AUCUN noeud d'attaque : il pose TROIS effets. Le `2x Eviscerate` appartient a la
    PHASE 2 (`...Triggered.Loki.OverwhelmingWrath_AttackAbility`,
    `TriggeredAbilityType.OverwhelmingWrath_Attack` = 1237), NON portee (residu #503-r1).
    Le critere n'est pas « 0 degat observe » mais « 0 degat ET flux MT STRICTEMENT identique » :
    un jet de crit ou de block CONSOMME un tirage
    (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`), donc un MT fige PROUVE que
    `crit` et `block` sont hors de ce behaviour -- c'est ce qui SEPARE les quatre mecaniques du
    kit au lieu de les supposer.
  * l'empreinte D'EFFETS et les BONDS. 27 `Taunted_OnlySpecificTargets` est un effet COMPOSITE
    (`TauntedEffect$$ApplyInternal` spawne 25/26/1237 en `AddSubEffectWithSameTurns`) pose sur
    CHAQUE ennemi adjacent et BONDE au caster ; 1300 et 1301 sont sur le caster. Le bond n'est pas
    visible dans `decisionView.effects` -> la garde lit la CASCADE du cast natif.
  * les DEUX effets MORDENT, ils ne sont pas que POSES : 1301 fait tomber la prediction NATIVE
    d'une attaque RANGED ennemie de `dmgReductionPct`%, et 27 retire l'allie des cibles legales
    de l'ennemi taunte (`UnitExtensions$$GetOnlyTargets` -> `TargetIsAllowedForCaster`).
  * le GATE DE CIBLAGE mord, et sur les MEMES cibles que le natif. `TARGETING_OPTIONS` absent =>
    `get_invalid_target_reason` rend 0 immediatement : degradation PERMISSIVE, invisible en
    self-play. Le masque de 1141 a MIGRE ici depuis `TARGETING_OPTIONS_UNPORTED` (contrat de
    DISJONCTION) -- ce test verifie AUSSI qu'il n'y est plus.

Le montage (build + DRIVE des positions par `--place`/`--a-place`) et TOUTES les lectures vivent
dans `scripts/python/probe_503_overwhelming_wrath.py` : le probe MESURE, ce test GARDE, une seule
implementation -- aucune divergence possible entre les deux.

Contre-epreuves ADVERSARIALES (selecteur vide, cast sur soi, allie adjacent, crit/block forces,
autre board, trait Steppable) : `scripts/python/probe_503_generalisation.py`.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_503_overwhelming_wrath as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE, pas une facilite : ce fichier importe le PROBE, qui
    # importe `ABILITY_CLASSES` -- sa fermeture d'import atteint la quasi-totalite de
    # `scripts/python` (~139 modules pour un test d'ability). Declarer etroit produirait un FAUX
    # VERT (le test ne serait pas rejoue quand ce qu'il mesure change).
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle des sept gardes : un changement de build peut les faire changer d'avis
    # sans qu'une ligne du port bouge.
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de 1141. Le verdict depend du code du port (arbre "
              "DSL + primitives AddEffect/AddBondEffect + le selecteur NormalUnits + TauntedEffect "
              "+ OverwhelmingWrathRangeDmgReductionEffect + le registre + le masque de ciblage), "
              "du MONTAGE (le probe, qui porte le drive des positions et TOUTES les lectures), des "
              "entrees versionnees du runner, et du BUILD charge -- l'oracle etant le jeu lui-meme, "
              "pas une constante ecrite ici.",
}

OVERWHELMING_WRATH = P.OVERWHELMING_WRATH          # 1141 ActiveAbilityType.OverwhelmingWrath
TAUNTED = P.TAUNTED                                # 27   EffectType.Taunted_OnlySpecificTargets
TAUNTED_SUBS = (P.TAUNTED_BLOCK_MOVEMENT,          # 25
                P.TAUNTED_CANT_USE_ABILITY,        # 26
                P.TAUNTED_REFRESH)                 # 1237 (EffectType, PAS le TriggeredAbilityType)
OW_PENDING_ATTACK = P.OW_PENDING_ATTACK            # 1300
OW_RANGE_DMG_REDUCTION = P.OW_RANGE_DMG_REDUCTION  # 1301
#: `TargetingRule` bit 23 -- le code que rend la cascade quand le TAUNT refuse une cible. Pris au
#: MEMBRE du mirror genere (`targeting_rule.py`), jamais au litteral : un ordinal juste aujourd'hui
#: devient faux au changement de build, en silence.
TARGET_IS_ALLOWED_FOR_CASTER = P.TARGET_IS_ALLOWED_FOR_CASTER


@pytest.fixture(scope="module")
def wrath(live_session):
    """UN SEUL runner pour tout le fichier : le cast est joue une fois des DEUX cotes, les gardes
    ci-dessous relisent la MEME mesure (le cast n'est pas rejouable -- il consomme l'actif)."""
    m, dispose = P.measure(live_session, state_name="test_503_wrath")
    try:
        yield m
    finally:
        dispose()


def test_wrath_execution_is_ported(wrath):
    """La face EXECUTION est portee : sans elle, la decision CHOISIT le cast et l'execution
    l'IGNORE -- 0 degat, 0 effet, AUCUNE erreur (le no-op silencieux que #503 ferme)."""
    assert wrath["routed"] == "handler" and wrath["ported"] is True, \
        "1141 non portee (routed=%s ported=%s)" % (wrath["routed"], wrath["ported"])
    assert not wrath["cast_error"], "cast natif bloque: %s" % wrath["cast_error"]


def test_wrath_effect_footprint_matches_native(wrath):
    """Empreinte `{unite -> {effectType: remaining}}` : le port doit poser EXACTEMENT les effets du
    natif, sur les MEMES porteurs, avec les MEMES durees.

    1301 et 27 portent `TurnsFromRounds(1)` (litteral `1` au decompile, PAS un
    `GetNumberConstant(nrOfRounds)` : 1141 n'a pas cette constante au gameconfig) ; 1300 recoit une
    struct d'options ZERO -> duree `DefaultAmountOfRounds`, publiee `remaining 0` (permanent, l'effet
    est consomme par la phase 2, pas expire par un timer). Les trois sous-effets du taunt heritent la
    duree du parent (`AddSubEffectWithSameTurns`)."""
    off, live = wrath["off"], wrath["live"]
    assert off == live, "empreinte d'effets offline %s != live %s" % (off, live)
    caster, adj = wrath["caster"], wrath["adj"]
    assert set(off.get(caster, {})) == {OW_RANGE_DMG_REDUCTION, OW_PENDING_ATTACK}, \
        "le CASTER u%d porte %s, attendu {1301, 1300}" % (caster, off.get(caster))
    for a in adj:
        assert set(off.get(a, {})) == {TAUNTED} | set(TAUNTED_SUBS), \
            "l'ennemi ADJACENT u%d porte %s, attendu 27 + ses 3 sous-effets" % (a, off.get(a))
        assert off[a][TAUNTED] == off[caster][OW_RANGE_DMG_REDUCTION] > 0, \
            "27 et 1301 partagent `TurnsFromRounds(1)` -- durees %s / %s" % (
                off[a][TAUNTED], off[caster][OW_RANGE_DMG_REDUCTION])
    assert off[caster][OW_PENDING_ATTACK] == 0, \
        "1300 recoit une struct d'options ZERO -> duree DEFAUT (remaining 0), pas une duree explicite"


def test_wrath_spares_the_non_adjacent_enemy(wrath):
    """`NormalUnits(AdjacentEnemies(Owner@0x30, 1, 3), 3)` -- l'ennemi RANGED a distance 2 ne doit
    RIEN recevoir. C'est le temoin qui distingue « le taunt vise les adjacents » de « le taunt vise
    tous les ennemis » : sans lui, un port qui aurait ecrit `Enemies(AllUnits())` passerait."""
    ranged = wrath["ranged"]
    assert ranged not in wrath["off"] and ranged not in wrath["live"], \
        "l'ennemi NON adjacent u%d a recu quelque chose (port=%s natif=%s)" % (
            ranged, wrath["off"].get(ranged), wrath["live"].get(ranged))


def test_wrath_bonds_point_to_the_caster(wrath):
    """Le 5e argument natif d'`AddBondEffect` (`bondedEntity`) est `Caster@0x48` pour les DEUX bonds.

    C'est l'etage que l'empreinte ne voit pas (`decisionView.effects` ne publie pas le bond) et le
    seul qui rende le taunt OPPOSABLE : `TauntedEffect$$ApplyInternal` ecrit
    `ForcedAttackTargetsComponent.<+0x50> = [BondedEntityId]`. Un bond nul laisserait le builder
    ORDINAIRE (aucun bond) et le taunt serait un effet INERTE."""
    caster, adj = wrath["caster"], wrath["adj"]
    attendu_taunt = sorted((a, caster) for a in adj)
    for cote, src in (("port", wrath["off_bonds"]), ("natif", wrath["live_bonds"])):
        assert src, "%s : aucun bond publie -- l'oracle est MUET, l'accord ne peut pas etre " \
                    "confirme (canal a re-verifier)" % cote
        got = sorted((int(x["on"]), x["bonded"]) for x in (src.get(TAUNTED) or []))
        assert got == attendu_taunt, \
            "%s : 27 pose/bonde %s, attendu %s" % (cote, got, attendu_taunt)
        pend = sorted((int(x["on"]), x["bonded"]) for x in (src.get(OW_PENDING_ATTACK) or []))
        assert pend == [(caster, caster)], \
            "%s : 1300 pose/bonde %s, attendu [(%d, %d)]" % (cote, pend, caster, caster)


def test_wrath_cast_deals_no_damage_and_draws_nothing(wrath):
    """LA REFUTATION de la classification `DAMAGE(Eviscerate)` -- et le PARTAGE des quatre
    mecaniques du kit.

    Le degat existe : il appartient a la triggered 1237 (phase 2, non portee, residu #503-r1). Un
    port qui le poserait au CAST diverge du natif d'un TOUR entier et d'un PORTEUR.
    Le flux MT fige (`dumpRng` cote natif, `call_count` cote port sur un MT CALE sur le live) est ce
    qui transforme « aucun crit/block observe » en « crit et block INATTEIGNABLES » : un jet en
    consommerait un."""
    for cote, (before, after) in (("port", wrath["off_hp"]), ("natif", wrath["live_hp"])):
        changes = {k: (before[k], after.get(k)) for k in before if after.get(k) != before[k]}
        assert not changes, "%s : le CAST a change des HP %s -- il ne doit RIEN infliger" % (
            cote, changes)
    off0, off1 = wrath["rng_off"]
    assert off0 is not None and off0 == off1, \
        "port : le MT a avance (%s -> %s) -- le cast ne doit consommer AUCUN tirage" % (off0, off1)
    live0, live1 = wrath["rng_live"]
    assert live0[0] is not None, "natif : `dumpRng` muet -- le MT n'est PAS mesure (pas un vert)"
    assert live0 == live1, \
        "natif : le MT a avance (%s -> %s) -- le cast ne doit consommer AUCUN tirage" % (
            live0, live1)


def test_wrath_damage_reduction_bites_on_the_native_prediction(wrath):
    """GENERALISATION : l'effet 1301 est-il VIVANT, ou seulement present ?

    `OverwhelmingWrath_RangeDmgReductionEffect$$CreateDamageDefenseModifier` =
    `ForPercentDecrease(get_OwnerIsTarget & IsRangedAttack, ConfigVar(0x46 = dmgReductionPct))`. On
    lit la prediction NATIVE d'une attaque RANGED ennemie sur le caster, avant et apres le cast.

    ⚠ ON NE RECONSTITUE PAS L'ARRONDI NATIF : `healthDmgMin/Max` sont DEJA arrondis, donc la valeur
    interne derriere `2006` vit dans [2005.5, 2006.5) et x0.36 la place dans [721.98, 722.34) --
    plusieurs sorties entieres sont legitimes. Le critere est l'ENCADREMENT.
    ANTI-DEGENERESCENCE : un encadrement passe TRIVIALEMENT si le pourcentage est nul -> on EXIGE
    `pct > 0` et une prediction qui BOUGE."""
    pct = wrath["dmg_reduction_pct"]
    before, after = wrath["pred_before"], wrath["pred_after"]
    assert before and after, "prediction native absente (avant=%s apres=%s)" % (before, after)
    assert pct and int(pct) > 0 and after != before, \
        "REGIME DEGENERE : pct=%s, prediction %s -> %s -- l'encadrement ne prouverait RIEN" % (
            pct, before, after)
    for v0, v1 in zip(before, after):
        lo = (v0 - 0.5) * (100 - int(pct)) / 100
        hi = (v0 + 0.5) * (100 - int(pct)) / 100
        assert (lo - 0.5) <= v1 <= (hi + 0.5), \
            "1301 ne mord pas comme attendu : %d -> %d hors de [%.1f, %.1f] (x(100-%s)/100)" % (
                v0, v1, lo, hi, pct)


def test_wrath_taunt_restricts_the_adjacent_enemies_only(wrath):
    """GENERALISATION : le taunt est-il OPPOSABLE ?

    Deux lectures INDEPENDANTES du meme fait :
      * cote port, `UnitExtensions$$GetOnlyTargets` rend `[caster]` pour chaque ennemi taunte, `[]`
        pour l'ennemi NON adjacent ;
      * cote natif, la matrice `abilityReason(<ennemi>, NormalAttack, <unite du joueur>)` BASCULE :
        l'allie sort des cibles legales des DEUX ennemis tauntes (bit 23
        `TargetIsAllowedForCaster`), et le temoin NON taunte ne perd RIEN.

    ⚠ Le refus qui remplace peut en MASQUER un autre : `orksRuntherd -> allie` passe de
    `TargetIsInRange` a `TargetIsAllowedForCaster` -- le natif rend LA PREMIERE regle rompue de sa
    cascade, et le bit 23 y est teste AVANT la portee. Le port reproduit cet ORDRE (les deux rendent
    0x800000) : c'est une propriete de la CASCADE que ce test fige au passage.
    ANTI-DEGENERESCENCE : au moins UNE bascule doit partir d'une cible ACCEPTEE (0), sinon on ne
    mesurerait qu'un changement de LIBELLE de refus."""
    caster, adj, ranged = wrath["caster"], wrath["adj"], wrath["ranged"]
    for a in adj:
        assert wrath["off_only"].get(a) == [caster], \
            "port : GetOnlyTargets(u%d) = %s, attendu [%d]" % (a, wrath["off_only"].get(a), caster)
    assert wrath["off_only"].get(ranged) == [], \
        "port : l'ennemi NON adjacent u%d est restreint (%s) -- il ne doit pas l'etre" % (
            ranged, wrath["off_only"].get(ranged))

    av, ap, op = wrath["matrice_before"], wrath["matrice_after"], wrath["off_matrice"]
    assert ap == op, "la matrice de gate diverge port/natif : natif=%s port=%s" % (ap, op)
    bascules = [(c, t, av[(c, t)], ap[(c, t)]) for (c, t) in av if av[(c, t)] != ap[(c, t)]]
    attendues = sorted((a, wrath["ally"]) for a in adj)
    assert sorted((c, t) for c, t, _a, _b in bascules) == attendues, \
        "les bascules du taunt sont %s, attendues %s" % (bascules, attendues)
    assert all(b & TARGET_IS_ALLOWED_FOR_CASTER for _c, _t, _a, b in bascules), \
        "une bascule ne pose pas le bit 23 TargetIsAllowedForCaster : %s" % (bascules,)
    assert any(a == 0 for _c, _t, a, _b in bascules), \
        "REGIME DEGENERE : aucune bascule ne part d'une cible ACCEPTEE -- on ne mesurerait qu'un " \
        "changement de libelle de refus"
    for t in (caster, wrath["ally"]):
        assert av[(ranged, t)] == ap[(ranged, t)], \
            "le temoin NON taunte u%d a change d'avis sur u%d (%s -> %s)" % (
                ranged, t, hex(av[(ranged, t)]), hex(ap[(ranged, t)]))


def test_wrath_targeting_gate_matches_the_native(wrath):
    """Le masque `0x4000 TargetIsEnemy` + `isSelfCasting = 1` + `RANGE_ADJACENT`, confronte sur CINQ
    cibles : soi, un allie, les deux ennemis adjacents, un ennemi a distance 2.

    ANTI-DEGENERESCENCE : un accord ou TOUT vaut 0 ne prouverait rien -> on exige que le gate
    REFUSE l'allie et l'ennemi hors portee, et ACCEPTE soi (c'est `isSelfCasting`) et l'adjacent."""
    gp, gn = wrath["gate_port"], wrath["gate_natif"]
    assert gp == gn, "gate port %s != natif %s" % (
        {k: hex(v) for k, v in gp.items()}, {k: hex(v) for k, v in gn.items()})
    assert gp["soi"] == 0 and gp["adj1"] == 0 and gp["adj2"] == 0, \
        "le gate REFUSE une cible que le natif accepte : %s" % {k: hex(v) for k, v in gp.items()}
    assert gp["allie"] != 0 and gp["ranged_dist2"] != 0, \
        "REGIME DEGENERE : le masque n'a REFUSE personne -- il ne mord pas"


def test_wrath_mask_has_exactly_one_source():
    """CONTRAT DE DISJONCTION : le masque de 1141 a MIGRE sur la classe, il ne doit plus vivre dans
    `TARGETING_OPTIONS_UNPORTED`. Deux sources divergeraient EN SILENCE."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    assert OVERWHELMING_WRATH in ABILITY_CLASSES, "1141 absente du registre COMBAT"
    assert getattr(ABILITY_CLASSES[OVERWHELMING_WRATH], "TARGETING_OPTIONS", None) is not None, \
        "1141 est au registre SANS son masque -- gate desarme, degradation permissive"
    assert OVERWHELMING_WRATH not in TARGETING_OPTIONS_UNPORTED, \
        "1141 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (contrat de disjonction rompu)"


def test_wrath_attack_type_literal_is_transcribed():
    """`AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType.Others`. LITTERAL transcrit, pas
    deduit : l'audit classe 1141 `DAMAGE(Eviscerate)` et le ctor dit quand meme `2`. Une ability au
    registre SANS son litteral se degrade en `Others` sans le dire (cf. `probe_120` etape 0)."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    assert ABILITY_ATTACK_TYPE.get(OVERWHELMING_WRATH) == AbilityAttackType.Others, \
        "litteral de ctor absent ou faux : %s" % ABILITY_ATTACK_TYPE.get(OVERWHELMING_WRATH)
