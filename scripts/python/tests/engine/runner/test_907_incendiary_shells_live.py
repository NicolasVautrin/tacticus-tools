"""#907 -- `1044 IncendiaryShells` (Black Templars), face COMBAT.

Ce que ces bras GARDENT (et pas seulement ce qu'ils mesurent) :

  * `test_registre_offline`   -- l'entree au registre porte SES DEUX donnees obligatoires
    (`TARGETING_OPTIONS` lu du preset statique `<TargetingOptions statics>+0x140`,
    `ABILITY_ATTACK_TYPE` = 3e argument d'`AActiveAbility$$.ctor`), et le contrat de DISJONCTION
    est verifie PAR LE CODE (1044 retiree de `TARGETING_OPTIONS_UNPORTED` par le meme commit) ;
  * `test_arbre_offline`      -- la FORME de l'arbre : `AtomicGroup(InformWeapon & Attack)`, l'ORDRE
    des deux volets du `op_BitwiseAnd`, et surtout le TRI-ETAT `is_melee` -- `None` sur l'attaque,
    `False` sur `InformWeapon`. Les deux ne mirrorent PAS le meme objet natif ;
  * `test_nature_du_coup_non_declaree_offline` -- la config 1044 n'a PAS d'`attackRangeType`, et
    ses quatre voisines de patron en ont un. Ce bras assertionne sa PROPRE discriminance : sans le
    contraste, « 1044 n'en a pas » ne distinguerait pas une absence d'une lecture ratee ;
  * `test_degats_bit_exact_live` -- la SEQUENCE de degats coup par coup, natif vs port, MT offline
    cale sur `dumpRng`, sur DEUX regimes d'armure (0 : le NOMBRE de coups est l'observable ;
    3000 : le PERCAGE du profil le devient) ;
  * `test_masque_confronte_a_l_oracle_natif_live` -- le masque cible par cible contre
    `abilityReason` (`TargetingQuery$$GetInvalidTargetReason`), sur DEUX geometries, avec le seuil
    de portee ENCADRE des deux cotes et le clamp de melee EXERCE ;
  * `test_contrefactuels_du_masque_live` -- basculer chaque champ DOIT changer au moins une ligne.
    Un champ dont la bascule ne change rien n'est pas demontre porteur.

MONTAGE. Le porteur est `templNpc2Neophyte`, le VRAI porteur npc de 1044, amene par le CHEMIN DE
STATS EXPLICITE (`--explicit-stats`, #419-r1-tr12-r2) : SES stats, SES traits, SES armes -- pas une
greffe. L'autre porteur, le SUMMON `templNeophyte`, N'A AUCUN INVOCATEUR (balayage EXHAUSTIF du
gameconfig : il n'apparait que dans sa propre entree `units`, aucune ability ne le cite). La voie
NPC n'est donc pas une commodite, c'est la SEULE.

⚠ LE PORTEUR N'EST PAS PLACE PAR `--place` (residu #605-r1 : un porteur pose par `--place`
n'emettait qu'UN coup la ou le meme porteur laisse a son SpawnPoint en emettait DEUX). Ce sont les
CIBLES qu'on deplace (`--a-place`).

Le PROBE (`probe_907_incendiary_shells.py`) MESURE et porte le montage ; ce fichier GARDE.
Aucun `pytest.skip` de complaisance : un montage qui ne s'installe pas ECHOUE (#268). ASCII only.
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
        "scripts/python/rl_duel.py", "scripts/python/hexgeo.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/probe_907_incendiary_shells.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE : charger UNE ability tire le registre, le vocabulaire
        # DSL, les Operations, la formule de coups, les effets d'AURA, l'IA et le pathfinding --
        # une liste choisie serait un faux vert. Foyers vraiment load-bearing :
        # `abilities/blacktemplars.py` (l'arbre), `handler.py` + `attack_type.py` + `targeting.py`
        # (les registres confrontes), `abilities/behaviours/combat.py` et
        # `operations/damage_ops/ability.py` (la route de degat),
        # `services/attack_hits_formula.py` + `entities/effects/loki/hits.py` (le tri-etat
        # `is_melee` et l'aura `BigTargetAdjacent`, qui EST le discriminant de ce fichier).
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de `1044 IncendiaryShells` : l'oracle est le jeu "
              "lui-meme (sequence de degats coup par coup, verdict de ciblage cible par cible). Un "
              "changement de build peut donc faire changer ce fichier d'avis sans qu'une ligne du "
              "port bouge.",
}

import pytest

import gameconfig as GC

import probe_907_incendiary_shells as P

from engine.entities.active_ability_type import ActiveAbilityType
from engine.runner.abilities.targeting_rule import TargetingRule as TR

ABILITY = int(ActiveAbilityType.IncendiaryShells)          # 1044

#: Les quatre VOISINES DE PATRON : meme famille (attaque d'ability rangee mono/multi-cible), et
#: toutes DECLARENT `attackRangeType`. C'est le contraste qui donne son sens a l'absence chez 1044.
VOISINES_RANGED = ("FragstormGrenadeLauncher", "HellfireShells", "Stikkbomb", "PlasmaGrenade")


# ------------------------------------------------------------------------------- OFFLINE

def test_registre_offline():
    """Les DEUX donnees obligatoires du registre, et le contrat de DISJONCTION -- RE-LU DANS LE
    CODE, jamais soustrait d'un compte herite."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.blacktemplars import IncendiaryShellsAbility
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,
                                                   TARGETING_OPTIONS_UNPORTED)

    assert ABILITY_CLASSES.get(ABILITY) is IncendiaryShellsAbility, \
        "1044 absente d'ABILITY_CLASSES = NO-OP SILENCIEUX : la decision caste, l'execution ignore"

    opts = IncendiaryShellsAbility.TARGETING_OPTIONS
    assert opts is not None, "sans masque, AUCUN gate n'est applique (degradation permissive)"
    # `<TargetingOptions statics>+0x168` = `<preset +0x140>+0x28` = 0x4002, LU dans le `.cctor` et
    # RE-MESURE LIVE (`docs/rl/case-302-4/tile-target-population.json` : preset=320, rules=16386).
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy) == 0x4002
    assert opts.self_cast is False                       # `<preset>+0x00 isSelfCasting = 0`
    assert opts.range is not None and opts.range.use_range_from_config is True   # statics+0x18
    assert int(opts.force_melee_target) == 0             # `<preset>+0x20` = RangedBool.True

    # 3e argument d'`AActiveAbility$$.ctor(this, &opts, 0)` -- LU au DESASSEMBLAGE (`xor r8d, r8d`).
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.DirectTargetAttack

    # DISJONCTION : le masque vivait dans `TARGETING_OPTIONS_UNPORTED` (forme STATIC-COPY) ; il a
    # MIGRE sur la classe avec la face COMBAT. Deux sources = contrat viole.
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED


def test_nature_du_coup_non_declaree_offline():
    """La config 1044 n'a PAS d'`attackRangeType` -- et ses quatre VOISINES DE PATRON en ont un.

    Ce bras assertionne sa PROPRE discriminance : sans le contraste, « 1044 n'en a pas » ne
    distinguerait pas une absence REELLE d'une lecture ratee (mauvaise cle, mauvais niveau du
    dict). C'est cette absence qui impose `is_melee=None` et non `False` -- `GetAbilityAttackRange
    Type = 0` rend `IsMeleeAttack` ET `IsRangedAttack` faux."""
    cfg = GC.ability("IncendiaryShells") or {}
    assert cfg, "config 1044 introuvable"
    assert cfg.get("attackRangeType") is None, \
        "1044 DECLARE une nature (%r) -- le tri-etat `is_melee=None` du port devient FAUX" % (
            cfg.get("attackRangeType"),)
    declarees = {n: (GC.ability(n) or {}).get("attackRangeType") for n in VOISINES_RANGED}
    assert all(v == "Ranged" for v in declarees.values()), \
        "TEMOIN NON DISCRIMINANT : les voisines ne declarent plus toutes `Ranged` -> %r" % declarees


def test_arbre_offline():
    """La FORME de l'arbre, et le TRI-ETAT qui separe ses deux `isMelee`.

    Le natif : `ExecuteAtomic(this, InformWeapon op_BitwiseAnd Attack, entities, 0x51)`. L'ordre du
    `op_BitwiseAnd` est LU (`op_BitwiseAnd(informWeapon, attack)`) : `InformWeapon` d'abord."""
    from engine.entities.behaviours import AtomicGroup
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage, InformWeapon
    from engine.runner.abilities.blacktemplars import (INCENDIARY_SHELLS_ID,
                                                       INCENDIARY_SHELLS_PROFILE,
                                                       incendiary_shells_tree)

    arbre = incendiary_shells_tree()
    assert isinstance(arbre, AtomicGroup), \
        "`AActiveAbility$$ExecuteAtomic` -> `DSLBehaviors$$AtomicGroup` : le groupe est STRUCTUREL"
    comb = arbre.child                      # `op_and` -> `Seq` (le `CombinedBehaviour` natif)
    gauche, droite = comb.left, comb.right
    assert isinstance(gauche, InformWeapon), "volet GAUCHE = InformWeapon (execute EN PREMIER)"
    assert isinstance(droite, AttackWithAttackDamage), "volet DROIT = l'attaque"

    # `InformWeapon(damageProfileType, isMelee: 0, useSpecial: 0)` -- litteraux du call-site.
    assert gauche.profile == INCENDIARY_SHELLS_PROFILE == "Flame"
    assert gauche.is_melee is False and gauche.use_special is False

    # `AttackWithAttackDamage` : `is_melee` NE mirror PAS un argument du call-site, il mirror
    # `BattleQuery$$IsMeleeAttack` -- donc `None` (nature non declaree), JAMAIS `False`.
    assert droite.is_melee is None, (
        "`is_melee=%r` ARME les gates `IsRangedAttack` que le natif laisse muets (mesure #907 : "
        "l'aura `BigTargetAdjacentEffect` retirait un coup)" % (droite.is_melee,))
    assert droite.ability_id == INCENDIARY_SHELLS_ID
    assert droite.profile == INCENDIARY_SHELLS_PROFILE
    assert droite.native_factory == "attack"      # `DSLBehaviors$$AttackWithAttackDamage` (XREF)
    assert droite.ability_type == ABILITY         # `AbilityOrEffect(this+0x10)`
    assert type(droite.target_sel).__name__ == "Target"       # `Target@DSLSelectors+0x60`
    assert droite.hits is None and droite.hits_override is None, \
        "le nb de coups vient de `GetNumberConstant(0x2f)` via la config, pas d'un override"


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def sid(live_session):
    return live_session


@pytest.fixture(scope="module")
def montage_gate(sid):
    """Les DEUX geometries du volet GATE, mesurees UNE fois. Chaque runner est dispose des que ses
    lignes sont lues -- on ne tient pas deux slots pour rien."""
    out = {}
    from pathlib import Path
    import os
    for nom, places in P.GEOMETRIES.items():
        sf = P.PYDIR.parents[1] / "logs" / (
            "_t907-%s-%d.json" % (nom, os.getpid()))
        sf.parent.mkdir(parents=True, exist_ok=True)
        rid = P._build(sid, str(sf), places)
        try:
            _rc, rows = P.volet_gate(sid, rid, nom)
            out[nom] = rows
        finally:
            P._rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            sf.unlink(missing_ok=True)
    return out


def test_masque_confronte_a_l_oracle_natif_live(montage_gate):
    """Accord cible par cible avec `TargetingQuery$$GetInvalidTargetReason`, sur les DEUX
    geometries, PLUS les trois proprietes qui font qu'un accord veut dire quelque chose."""
    toutes = [r for rows in montage_gate.values() for r in rows]
    assert toutes, "aucune ligne mesuree -- montage non installe"
    ko = [(r["geo"], r["vis"], r["dist"], hex(r["nat"]), hex(r["port"]))
          for r in toutes if r["nat"] != r["port"]]
    assert not ko, "desaccord natif/port : %s" % (ko,)

    # (a) au moins une cible ACCEPTEE : sans elle, « le natif refuse tout » ne distingue pas le
    #     masque d'une ability indisponible (l'oracle court-circuite a `ValidRequest` 0x1).
    assert any(r["nat"] == 0 for r in toutes), "aucune cible acceptee -> temoin SATURE"

    # (b) le seuil de portee ENCADRE des DEUX cotes, sur la geometrie LIBRE (aucun clamp).
    libre = [r for r in montage_gate["libre"] if r["side"] == "ENNEMI"]
    d2 = [r for r in libre if r["dist"] == 2]
    d3 = [r for r in libre if (r["dist"] or 0) >= 3]
    assert d2 and d3, "spectre insuffisant (d=2 ET d>=3 requis) : %r" % [r["dist"] for r in libre]
    assert all(r["nat"] == 0 for r in d2), d2
    assert all(r["nat"] == int(TR.TargetIsInRange) for r in d3), d3

    # (c) le CLAMP DE MELEE exerce : avec un ennemi au contact, la MEME cible a d=2 bascule.
    melee = [r for r in montage_gate["melee"] if r["side"] == "ENNEMI"]
    assert any(r["dist"] == 1 for r in melee), \
        "aucun ennemi au contact -> `ShouldApplyRangedInMelee` faux, le clamp n'est PAS exerce"
    m2 = [r for r in melee if r["dist"] == 2]
    assert m2 and all(r["nat"] == int(TR.TargetIsInRange) for r in m2), (
        "d=2 devrait etre REFUSEE en regime melee (`forceMeleeTarget = RangedBool.True` -> "
        "`v = min(1, v)`) : %r" % (m2,))

    # (d) `TargetIsEnemy` mord : allies et caster refuses des DEUX cotes.
    allies = [r for r in toutes if r["side"] == "ALLIE"]
    assert allies and all(r["nat"] == int(TR.TargetIsEnemy) for r in allies), allies


def test_contrefactuels_du_masque_live(sid, montage_gate):
    """Chaque champ du masque DOIT changer au moins une ligne -- sinon il est « pose » sans etre
    demontre porteur. Les deux champs de PORTEE sont exerces par des geometries DIFFERENTES, et
    c'est attendu : sans ennemi au contact le clamp ne s'arme pas, avec ennemi au contact la portee
    de config est deja rabattue a 1."""
    from dataclasses import replace
    from engine.runner.abilities.blacktemplars import IncendiaryShellsAbility
    from engine.runner.abilities.targeting import (RANGE_ADJACENT, RANGED_BOOL_FALSE,
                                                   get_invalid_target_reason)

    from pathlib import Path
    import os

    attendu = {                                   # champ -> geometrie ou il DOIT mordre
        "force_melee_target": "melee",
        "range": "libre",
        "rules": "libre",
        "none": "libre",
    }
    for nom, places in P.GEOMETRIES.items():
        sf = P.PYDIR.parents[1] / "logs" / (
            "_t907cf-%s-%d.json" % (nom, os.getpid()))
        sf.parent.mkdir(parents=True, exist_ok=True)
        rid = P._build(sid, str(sf), places)
        try:
            cap = P._capture(sid, rid)
            st = P._state(cap)
            caster = P._by_vis(cap, P.PORTEUR_VIS)
            cid = int(caster["id"])
            base = IncendiaryShellsAbility.TARGETING_OPTIONS
            variantes = {
                "force_melee_target": replace(base, force_melee_target=RANGED_BOOL_FALSE),
                "range": replace(base, range=RANGE_ADJACENT),
                "rules": replace(base, rules=TR.TargetMatchesDynamicRule),
                "none": None,
            }
            rows = montage_gate[nom]
            for champ, opts in variantes.items():
                class _Mut(IncendiaryShellsAbility):
                    __slots__ = ()
                _Mut.TARGETING_OPTIONS = opts
                m = _Mut()
                diffs = [r for r in rows
                         if int(get_invalid_target_reason(st, cid, r["uid"], m) or 0) != r["port"]]
                if attendu[champ] == nom:
                    assert diffs, (
                        "CONTREFACTUEL AVEUGLE sur %s/%s : basculer ce champ ne change AUCUNE "
                        "ligne -> il n'est pas demontre porteur" % (nom, champ))
        finally:
            P._rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            sf.unlink(missing_ok=True)


@pytest.mark.parametrize("armure", [0, 3000])
def test_degats_bit_exact_live(sid, armure):
    """UN cast, SEQUENCE coup par coup confrontee au natif, sur DEUX regimes d'armure.

      * `armure = 0`    : le NOMBRE de coups est l'observable (chaque coup se voit) ;
      * `armure = 3000` : le PERCAGE du profil le devient (`max(0, d - armure, d * pierce%)`) --
        sans ce regime, `Flame` (pierce 25) et `Physical` (pierce 1) rendent la MEME sequence, et
        le profil ne serait pas garde.

    Les MUTANTS sont rejoues sur un `State` RECHARGE du MEME instantane : `hits`, `profile` (regime
    arme seulement) et `native_factory` DOIVENT ecarter la sequence."""
    from pathlib import Path
    import os
    sf = P.PYDIR.parents[1] / "logs" / ("_t907d-%d-%d.json" % (armure, os.getpid()))
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = P._build(sid, str(sf), P.GEOMETRIES["libre"], armure=armure)
    try:
        cap = P._capture(sid, rid)
        caster = P._by_vis(cap, P.PORTEUR_VIS)
        assert caster is not None, "porteur absent -- `--explicit-stats` KO"
        cibles = sorted((u for u in P._units(cap) if u.get("team") != caster.get("team")),
                        key=lambda u: (P._dist(caster, u) or 99, int(u["id"])))
        assert cibles, "aucune cible sur le plateau"
        cible = cibles[0]

        port, diag = P._port_sequence(cap, caster["id"], cible["id"])
        res = P._rpc(sid, "applyAction",
                     {"runnerId": rid,
                      "action": {"kind": "ability", "casterId": int(caster["id"]),
                                 "targetId": int(cible["id"]), "abilityType": ABILITY}}, 240)
        a0 = ((res or {}).get("actions") or [{}])[0]
        assert a0.get("ok") and a0.get("mutated"), "le natif REFUSE le cast : %r" % (a0,)
        natif = P._montants_natifs(res, cible["id"])

        hits_cfg = int(((GC.ability("IncendiaryShells") or {}).get("constants") or {})["nrOfHits"])
        assert len(natif) == hits_cfg, \
            "NATIF %d coup(s), `nrOfHits` = %d -- %r" % (len(natif), hits_cfg, natif)
        assert port == natif, "sequence PORT %r != NATIF %r" % (port, natif)
        assert diag.get("informed_weapon") == "Flame"

        # Le TEMOIN discrimine-t-il ? Une sequence CONSTANTE n'exercerait aucun tirage.
        assert len(set(natif)) > 1, \
            "temoin SATURE : les %d coups rendent la meme valeur %r" % (len(natif), natif)

        mordent = {}
        for nom, fab in P._mutants():
            seq, _ = P._port_sequence(cap, caster["id"], cible["id"], tree_factory=fab)
            mordent[nom] = (seq != natif)
        exiges = [n for n in mordent if n.startswith(("hits=", "native_factory=", "is_melee=False"))]
        if armure:
            exiges += [n for n in mordent if n.startswith("profile=")]
        aveugles = [n for n in exiges if not mordent[n]]
        assert not aveugles, (
            "MUTANT(S) AVEUGLE(S) sur armure=%d : %r -- un temoin qu'aucune faute ne fait rougir "
            "ne garde rien" % (armure, aveugles))
    finally:
        P._rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        sf.unlink(missing_ok=True)
