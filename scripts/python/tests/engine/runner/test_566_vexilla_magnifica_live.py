"""GARDE de `1183 VexillaMagnifica` (#566) -- les DEUX faces, et ce qui les separe.

Avant #566 l'ability etait un **NO-OP SILENCIEUX cote COMBAT** : absente d'`ABILITY_CLASSES`, donc
`AbilityHandler.visit_ActiveAbilityMessage` l'ignorait -- 0 degat, 0 effet, AUCUNE erreur -- pendant
que la face DECISION, elle, la CHOISISSAIT (playbook porte de longue date). Et cette face DECISION
etait elle-meme INCOMPLETE : elle n'appliquait pas le `continue` sur `HasEffect(cible, Stunned)` du
corps natif (sa docstring portait `[filtre HasEffect 0x48a : TODO]`).

CE QUE LE PORT DOIT PRODUIRE, et ce que ce fichier garde :

    ExecuteAtomic( ((b1 & b2) & b3) & b4, 0x2a = GroupType.Ability_AtomicGroup )
      b1 = AttackWithAttackDamage(Caster, Target,  MinMaxDamage, Physical, nrOfHits)
      b2 = AttackWithAttackDamage(Caster, sec,     MinMaxDamage, Physical, nrOfHits)
      b3 = AddEffect(1162 Stunned, source = Caster, targets = Target + sec, options ZEROEES)
      b4 = AddEffect(1383 VexillaMagnifica_DmgReduction, Caster, TurnsFromRounds(nrOfRounds))
      sec = Cache(First(SortUnitsByDamageUtility(NormalUnits(AdjacentEnemies(Caster)) - Target,
                                                 MinMaxDamage(isPrediction: 0), 3), 1), 1)

QUATRE REGIMES LIVE, et le deuxieme est OBLIGATOIRE. `sec` est un ARGMAX d'utilite de degat ; un
port qui prendrait la TETE de l'enumeration d'adjacence tomberait juste tant que les deux
coincident. Le regime `bascule` pousse l'armure du candidat prefere au-dela des bornes de degat de
l'ability -- la prediction du selecteur etant SANS PERCAGE (`damageProfile: null`), son utilite
s'effondre et l'argmax DOIT changer de cible. Le montage EXIGE cette bascule ; sans elle il ECHOUE,
il ne rend pas un vert de regime degenere.

Le troisieme (`alea`) rend crit et block NATURELS : l'identite arithmetique sur les tirages n'y
tient plus, mais le pipeline COMPLET y est exerce (les deux premiers debranchent l'alea).

Le quatrieme (`solo`) EXILE les deux candidats : le pool du selecteur est VIDE. Le natif ne frappe
et ne stunne QUE la cible du message -- et il CONSOMME QUAND MEME le tirage du tri, parce que
`SortUnitsByDamageUtilitySelector$$Select` evalue `damage.Calculate(entities)` AVANT sa boucle par
cible. C'est une PREDICTION du decompile, falsifiable en un entier (`2 x 1 + 1 = 3`).

CE QUI EST ASSERTIONNE, et pourquoi ce n'est pas un total :
  * la SEQUENCE coup par coup (`UnitDamaged` natifs filtres sur `Active_Ability_Type = 1183` vs les
    `per_hit_health` des DEUX feuilles) ;
  * la SECONDE CIBLE, natif contre port, dans les DEUX regimes ou elle differe ;
  * les TIRAGES `genrand_int32` : `PORT == NATIF` partout, et -- a alea neutralise --
    l'identite `2 x <coups> + 1`, dont le `+1` EST le `RandomAmount.Calculate` que
    `SortUnitsByDamageUtilitySelector$$Select` consomme. C'est l'etage qui separe une faute
    d'ARITHMETIQUE d'une faute de STRUCTURE, et qui mesure que le tri est bien PLACE ;
  * les EFFETS : `Stunned` sur les DEUX cibles frappees et `VexillaMagnifica_DmgReduction` sur le
    SEUL caster, avec les MEMES `RemainingTurns` que le natif -- c'est ce qui garde la lecture
    « le Stun n'a AUCUN override de duree, le buff self en a un » (deux surcharges natives
    distinctes d'`AddEffect`, tranchees par leurs XREFS entrantes) ;
  * QUATRE contre-epreuves, chacune ne retirant QU'UNE lecture du mirror.

FACE DECISION -- deux scenarios sur le MEME etat, a UNE difference pres (le stun), plus une
contre-epreuve qui NEUTRALISE le filtre et doit MORDRE. Sans elle, l'accord pourrait venir d'autre
chose que du filtre.

MESURES = `probe_566_vexilla_magnifica.py` (COMBAT) et `probe_566_vexilla_magnifica_decision.py`
(DECISION) : ce fichier ne duplique NI les montages NI les criteres, il les appelle.

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) -- sauf
indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        # Elles portent des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest) -- donc aucun graphe d'imports ne les verrait.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- les DEUX probes qui portent les montages ET les criteres, et le
        # probe DECISION dont le premier importe les helpers d'oracle :
        "scripts/python/probe_566_vexilla_magnifica.py",
        "scripts/python/probe_566_vexilla_magnifica_decision.py",
        "scripts/python/probe_119_supreme_commander_decision.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu COMBAT passe par
        # `Runner.apply(ActiveAbilityMessage)` et la face DECISION par `engine_decide` -- leurs
        # fermetures d'imports MESUREES traversent le pipeline de degat, le PRNG, la couche
        # d'effets, le selecteur de tri (`operations/damage_utility` -> `attack_prediction` ->
        # `damage_prediction`) et tout l'etage de playbook. Enumerer les seuls fichiers de #566
        # serait DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul -- et
        # `scripts/python/**/*.py` seul raterait `scripts/python/board.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1183 (arbre DSL `runner/abilities/custodes.py` : deux "
              "`AttackWithAttackDamage` + `AddEffect(1162)` + `AddEffect(1383)`, sous "
              "`AtomicGroup`), son collapse de selecteur `VexillaMagnificaSecondTarget` "
              "(`operations/damage_utility.first_by_damage_utility`), le cablage (registre "
              "`ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`, masque migre depuis `targeting.py`), les "
              "effets `entities/effects/loki/{status,damage_reduction}.py`, le filtre "
              "`HasEffect(Stunned)` de `playbook/noncomparable/vexilla_magnifica.py` et son foyer "
              "`battle_query.scene_has_effect` -- et tout le moteur que les deux rejeux "
              "traversent. `build: True` parce que la sequence confronte le NATIF au tirage pres.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_566_vexilla_magnifica as P                            # noqa: E402
import probe_566_vexilla_magnifica_decision as D                   # noqa: E402

VEXILLA_MAGNIFICA = P.VEXILLA_MAGNIFICA


# ---------------------------------------------------------------- 0. le cablage, hors live

def test_le_cablage_du_registre_est_complet():
    """Une ability qui entre dans `ABILITY_CLASSES` pose son masque ET son `AbilityAttackType`
    DANS LE MEME COMMIT, et SORT de `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : une
    ability a UNE source de masque, jamais deux). Sans masque, `get_invalid_target_reason` rend 0
    et le moteur accepte des casts que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE."""
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    cls = ABILITY_CLASSES.get(VEXILLA_MAGNIFICA)
    assert cls is not None, "1183 absente d'ABILITY_CLASSES : c'est le NO-OP d'avant #566"
    assert VEXILLA_MAGNIFICA not in TARGETING_OPTIONS_UNPORTED, (
        "1183 est portee ET encore dans TARGETING_OPTIONS_UNPORTED (disjonction rompue)")
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "1183 au registre SANS masque = gate de ciblage DESARME"
    # Forme PRESET + FLAGS : `rules = additionalRules | template.rules`, LU dans la surcharge
    # `TargetingOptions..ctor(this, template, additionalRules)`. Preset `<statics>+0x40` -> `0x4000`
    # (`.cctor` : `*(statics + 0x68) = 0x4000`), flags `0x200000000`.
    assert int(opts.rules) == int(TR.TargetIsEnemy) | int(TR.TargetIsNotAnObject), (
        "masque 1183 attendu = TargetIsEnemy | TargetIsNotAnObject (0x200004000), lu %s"
        % (opts.rules,))
    assert int(opts.rules) == 0x200004000
    assert opts.self_cast is False
    # 3e argument LITTERAL d'`AActiveAbility..ctor(this, &opts, 0)` -- TRANSCRIT, pas deduit.
    assert ABILITY_ATTACK_TYPE.get(VEXILLA_MAGNIFICA) == AbilityAttackType.DirectTargetAttack


def test_le_perimetre_hors_registre_a_perdu_son_entree():
    """Le CINQUIEME endroit du contrat de disjonction (#433) : la liste FIGEE des abilities du
    pool spawnable hors `ABILITY_CLASSES`. Une ability qui entre au registre en SORT dans le meme
    commit, sinon son masque aurait DEUX sources."""
    import importlib
    mod = importlib.import_module("tests.engine.test_433_r4_r2_r1_r2_ability_range_offline")
    assert VEXILLA_MAGNIFICA not in mod.POOL_ABILITIES_WITHOUT_COMBAT_CLASS


def test_les_deux_effets_sont_au_registre_des_effets():
    """Sans ces entrees, `EffectFactory.create` rendrait un `BaseEffect` NU : l'effet serait pose,
    `active`, et ne contribuerait RIEN -- le no-op silencieux, deplace d'un cran. La cle est le NOM
    gameconfig, apparie au membre d'enum (jamais un ordinal nu)."""
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.damage_reduction import VexillaMagnificaDmgReductionEffect
    from engine.entities.effects.loki.status import StunnedEffect
    assert EFFECT_CLASSES.get(EffectType.VexillaMagnifica_DmgReduction.name) is \
        VexillaMagnificaDmgReductionEffect
    assert EFFECT_CLASSES.get(EffectType.Stunned.name) is StunnedEffect


def test_les_ordinaux_du_port_nomment_AUTRE_CHOSE_ailleurs():
    """Ce qui rend le NOM obligatoire : les trois ordinaux ecrits par cette tranche sont AUSSI des
    membres valides d'autres enums, et ils y nomment autre chose. Une confusion serait SILENCIEUSE.

    Ce test assertionne son propre NON-VIDE : un controle « les homonymes different » qui ne
    trouverait AUCUN homonyme passerait pour vert sans rien mesurer."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType
    import engine.runner.abilities.custodes as CU
    assert CU.VM_STUNNED == int(EffectType.Stunned) == 0x48a
    assert CU.VM_DMG_REDUCTION == int(EffectType.VexillaMagnifica_DmgReduction) == 0x567
    assert VEXILLA_MAGNIFICA == int(ActiveAbilityType.VexillaMagnifica) == 0x49f
    homonymes = [(0x48a, "ActiveAbilityType"), (0x49f, "EffectType")]
    assert homonymes, "aucun homonyme a confronter -- le controle serait vide"
    assert ActiveAbilityType(0x48a).name != EffectType(0x48a).name
    assert EffectType(0x49f).name != ActiveAbilityType(0x49f).name


def test_l_arbre_a_QUATRE_feuilles_dans_l_ordre_natif():
    """MIRROR STRUCTUREL : `AtomicGroup( ((b1 & b2) & b3) & b4 )`. L'ordre est LOAD-BEARING (le
    Stun est pose APRES les deux attaques) et le noeud de tete est un `AtomicGroup` --
    `ExecuteAtomic`, pas `Execute` PLAIN."""
    from engine.entities.behaviours import AtomicGroup, Seq
    from engine.entities.selectors.units import Union
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import AddEffect
    from engine.entities.selectors.geometry import Nothing
    import engine.runner.abilities.custodes as CU

    arbre = CU.vexilla_magnifica_tree("Physical", Nothing(), 2)
    assert isinstance(arbre, AtomicGroup)
    n = arbre.child
    feuilles = []
    while isinstance(n, Seq):
        feuilles.append(n.right)
        n = n.left
    feuilles.append(n)
    feuilles.reverse()
    assert [type(f).__name__ for f in feuilles] == [
        "AttackWithAttackDamage", "AttackWithAttackDamage", "AddEffect", "AddEffect"]
    b1, b2, b3, b4 = feuilles
    assert isinstance(b1, AttackWithAttackDamage) and isinstance(b2, AttackWithAttackDamage)
    assert isinstance(b3, AddEffect) and isinstance(b4, AddEffect)
    assert b3.effect_type == CU.VM_STUNNED and isinstance(b3.target_sel, Union)
    # Surcharge OPTIONS a struct ZEROEE -> AUCUN override de duree pour le Stun.
    assert b3.duration_rounds is None and b3.duration_turns is None
    # Surcharge TURNS -> `TurnsFromRounds(GetNumberConstant(nrOfRounds))`, deja converti en TOURS.
    assert b4.effect_type == CU.VM_DMG_REDUCTION and b4.duration_turns == 2
    assert b4.scale_from_source is True
    assert b1.ability_type == b2.ability_type == VEXILLA_MAGNIFICA


def test_le_pool_du_selecteur_soustrait_la_cible():
    """`NormalUnits(AdjacentEnemies(Caster)) op_Subtraction Target` -- c'est la SOUSTRACTION qui
    garantit que la 2e attaque frappe une AUTRE unite. Le mirror est verifie sur la STRUCTURE (le
    live, lui, le verifie sur l'observable : cf. la contre-epreuve `pool_sans_soustraction`)."""
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.units import AdjacentEnemies, NormalUnits, Sub
    import engine.runner.abilities.custodes as CU
    pool = CU.vexilla_magnifica_pool()
    assert isinstance(pool, Sub)
    assert isinstance(pool.b, Target)
    assert isinstance(pool.a, NormalUnits)
    assert isinstance(pool.a.entities, AdjacentEnemies)


# ---------------------------------------------------------------- 1. le filtre DECISION, hors live

class _SceneStub:
    """Substrat MINIMAL de `EntityExtensions$$HasEffect(entity, state, type, onlyActive: null)` :
    seule la branche `IsOwnerOfEffect` est alimentee (`EffectsState.has_effect`)."""

    class _Eff:
        def __init__(self, porteurs):
            self.porteurs = porteurs

        def has_effect(self, uid, effect_type=None):
            return int(effect_type) in self.porteurs.get(int(uid), set())

    def __init__(self, porteurs):
        self.eff_state = self._Eff(porteurs)

    @staticmethod
    def is_effect_target(_uid, _t):
        return None                       # TRI-ETAT : geometrie non portee, PAS un `False`


class _NCStub:
    def __init__(self, hp, scene=None):
        self.hp_cur_by_id = hp
        self.scene = scene


def test_le_filtre_ecarte_une_cible_STUNNEE_et_seulement_elle():
    """`if (HasEffect(entity, state, 0x48a, onlyActive: null)) continue;` -- le `continue` du corps
    natif. Une cible stunnee rend `None` (donc n'entre pas au bucket) ; les autres rendent leurs PV."""
    from engine.entities.effect_type import EffectType
    from engine.playbook.noncomparable.vexilla_magnifica import VexillaMagnificaPlaybook
    pb = VexillaMagnificaPlaybook()
    scene = _SceneStub({7: {int(EffectType.Stunned)}, 9: {int(EffectType.Pinned)}})
    ctx = _NCStub({7: 5000, 8: 3000, 9: 4000}, scene)
    assert pb.evaluate_non_comparable((0, 0), 7, ctx) is None, "cible STUNNEE non ecartee"
    assert pb.evaluate_non_comparable((0, 0), 8, ctx) == 3000.0
    # Un AUTRE effet ne ferme pas le filtre : c'est bien `Stunned` (1162) qui est lu, pas « un
    # effet quelconque ».
    assert pb.evaluate_non_comparable((0, 0), 9, ctx) == 4000.0


def test_sans_substrat_le_filtre_degrade_en_PERMISSIF():
    """`ctx.scene` absent -> le port ne peut pas AFFIRMER une presence d'effet. Il rend alors les PV
    (comportement d'avant #566), jamais un `None` invente : une degradation qui REFUSE serait une
    decision fabriquee."""
    from engine.playbook.noncomparable.vexilla_magnifica import VexillaMagnificaPlaybook
    pb = VexillaMagnificaPlaybook()
    assert pb.evaluate_non_comparable((0, 0), 7, _NCStub({7: 5000}, None)) == 5000.0
    assert pb.evaluate_non_comparable((0, 0), 7, _NCStub({}, None)) is None   # PV inconnus


# ---------------------------------------------------------------- 2. la confrontation LIVE COMBAT

@pytest.fixture(scope="module")
def combat():
    """Les TROIS regimes, joues DANS L'ORDRE (`bascule` neutralise le candidat MESURE au regime
    `nominal`). Le probe dispose ses runners au fil de l'eau."""
    try:
        sid = P._sid()
    except Exception as e:                                    # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    base = os.path.join(os.environ.get("TEMP", "."), "t566_%s.json" % os.getpid())
    mesures, _ok = P.campagne(sid, base, 56600, P.BOARD,
                              ["nominal", "bascule", "alea", "solo"])
    if not mesures:
        pytest.skip("build KO -- session/host indisponible")
    return {m["regime"]: m for m in mesures}


def _assert_cast(m):
    pool_vide = P.REGIMES[m["regime"]][2]
    sp, sn = m["port"]["seq"], m["natif"]["seq"]
    assert m["port"]["ported"] is True, "1183 non routee par le registre (NO-OP d'avant #566)"
    assert sn, "aucun `UnitDamaged` natif attribue a 1183"
    assert sp == sn, "SEQUENCE divergente (%s) : port=%r natif=%r" % (m["regime"], sp, sn)
    cibles = sorted({t for t, _a in sn})
    sec_n = [t for t in cibles if t != m["cible"]]
    if pool_vide:
        # POOL VIDE : le natif frappe la SEULE cible du message, et le port ne s'invente pas de
        # cible de repli. Le tirage du tri, lui, tombe QUAND MEME (cf. l'identite ci-dessous).
        assert len(sn) == 1, "regime `solo` : le natif a frappe %d cibles (%s)" % (len(sn), sn)
        assert sec_n == [], "regime `solo` : une seconde cible native est apparue (%s)" % (sec_n,)
        assert m["port"]["second"] is None, (
            "regime `solo` : le port s'invente une seconde cible (u%s)" % m["port"]["second"])
    else:
        assert len(sn) == 2, ("le cast doit frapper DEUX cibles (%s) -- une seule = la 2e feuille "
                              "est inerte" % (sn,))
        assert len(sec_n) == 1
        assert m["port"]["second"] == sec_n[0], (
            "SECONDE CIBLE divergente (%s) : port=u%s natif=u%s"
            % (m["regime"], m["port"]["second"], sec_n[0]))
    assert m["tirages_port"] is not None and m["tirages_port"] == m["tirages_natif"], (
        "TIRAGES divergents (%s) : port=%s natif=%s"
        % (m["regime"], m["tirages_port"], m["tirages_natif"]))
    if P.REGIMES[m["regime"]][0]:
        # Alea NEUTRALISE : l'identite est lisible, et son `+1` EST le tirage du selecteur de tri.
        attendu = P.TIRAGES_PAR_COUP * len(sp) + P.TIRAGES_DU_TRI
        assert m["tirages_port"] == attendu, (
            "le port ne consomme pas 2/coup + 1 (tri) : %s pour %d coups"
            % (m["tirages_port"], len(sp)))
        assert m["natif"]["coups_tous"] == len(sn), (
            "des coups natifs hors 1183 polluent l'attribution des tirages")
        assert m["tirages_natif"] == attendu


def _assert_effets(m):
    """Le Stun sur les DEUX cibles frappees, le buff self sur le SEUL caster, MEMES durees."""
    cibles = sorted({t for t, _a in m["natif"]["seq"]})
    stun_n = {k: dict(v).get(P.NOM_STUN) for k, v in (m["natif"]["effets"] or {}).items()
              if any(n == P.NOM_STUN for n, _t in v)}
    assert sorted(stun_n) == cibles and stun_n, (
        "le natif ne stunne pas exactement les cibles frappees : %s vs %s" % (sorted(stun_n), cibles))
    stun_p = {k: t for k, rows in m["port"]["poses"].items() for e, t in rows if e == P.EFFET_STUN}
    assert stun_p == stun_n, "STUN divergent (%s) : port=%s natif=%s" % (m["regime"], stun_p, stun_n)
    red_n = {k: dict(v).get(P.NOM_DMG_REDUCTION) for k, v in (m["natif"]["effets"] or {}).items()
             if any(n == P.NOM_DMG_REDUCTION for n, _t in v)}
    assert list(red_n) == [m["caster"]], "le natif pose 1383 ailleurs que sur le caster : %s" % (red_n,)
    red_p = {k: t for k, rows in m["port"]["poses"].items()
             for e, t in rows if e == P.EFFET_DMG_REDUCTION}
    assert red_p == red_n, "BUFF SELF divergent (%s) : port=%s natif=%s" % (m["regime"], red_p, red_n)


CONTRE_EPREUVES = ("sans_2e_attaque", "pool_sans_soustraction", "tri_par_ordre_source",
                   "stun_sur_cible_seule")


def _assert_contre_epreuves(m):
    """L'arbre du module rend la sequence native ; les contre-epreuves, elles, sont jugees
    GLOBALEMENT (`test_chaque_contre_epreuve_est_discriminante`) et non par regime : le regime
    `solo` a un pool VIDE, donc trois d'entre elles y coincident avec la reference par
    CONSTRUCTION -- exiger la divergence regime par regime rendrait un rouge qui ne dit rien."""
    ab, sn = m["ab"], m["natif"]["seq"]
    assert ab["ref"]["seq"] == sn, "l'arbre du module ne rend pas la sequence native"
    assert sorted(ab["ref"]["stun"]) == sorted({t for t, _a in sn})


@pytest.mark.parametrize("regime", ["nominal", "bascule", "alea", "solo"])
def test_sequence_seconde_cible_et_tirages(combat, regime):
    assert regime in combat, "regime %s non mesure -- montage sterile" % regime
    _assert_cast(combat[regime])
    _assert_contre_epreuves(combat[regime])


@pytest.mark.parametrize("regime", ["nominal", "bascule", "alea", "solo"])
def test_les_effets_poses(combat, regime):
    _assert_effets(combat[regime])


def test_chaque_contre_epreuve_est_discriminante(combat):
    """CHAQUE contre-epreuve doit diverger dans AU MOINS UN regime : sinon la lecture qu'elle
    retire n'est mesuree NULLE PART, et l'accord du port serait un accord de hasard."""
    for nom in CONTRE_EPREUVES:
        diverge = [r for r, m in combat.items()
                   if (m["ab"][nom]["seq"], m["ab"][nom]["stun"])
                   != (m["ab"]["ref"]["seq"], m["ab"]["ref"]["stun"])]
        assert diverge, "contre-epreuve %s NON discriminante sur AUCUN regime" % nom


def test_le_tirage_du_tri_tombe_MEME_a_pool_VIDE(combat):
    """PREDICTION FALSIFIABLE de la lecture du decompile :
    `SortUnitsByDamageUtilitySelector$$Select` evalue `damage.Calculate(entities)` **AVANT** sa
    boucle par cible, donc le `RandomAmount` est tire meme quand AUCUN candidat n'entre. Au regime
    `solo` cela vaut `2 x 1 coup + 1 = 3` -- et la contre-epreuve `tri_par_ordre_source` (qui n'a
    pas de tri du tout) en consomme UN DE MOINS, ce qui ATTRIBUE le tirage au tri plutot qu'a une
    coincidence."""
    m = combat["solo"]
    assert m["tirages_natif"] == m["tirages_port"] == P.TIRAGES_PAR_COUP * 1 + P.TIRAGES_DU_TRI
    assert m["ab"]["tri_par_ordre_source"]["tirages"] == m["ab"]["ref"]["tirages"] - 1, (
        "le tirage retire par `tri_par_ordre_source` n'est pas celui du selecteur de tri")


def test_la_seconde_cible_BASCULE_avec_l_armure(combat):
    """LE REGIME QUI COMPTE. `sec` est un ARGMAX ; un port qui prendrait la TETE de l'enumeration
    d'adjacence serait juste tant que les deux coincident. Le natif DOIT changer de cible quand
    l'armure du prefere passe au-dessus des bornes de degat -- et le port avec lui."""
    assert {"nominal", "bascule"} <= set(combat), "les deux regimes sont requis"
    a, b = combat["nominal"], combat["bascule"]
    assert a["port"]["second"] != b["port"]["second"], (
        "REGIME DEGENERE : la 2e cible ne bascule pas (%s) -- le montage ne peut pas distinguer "
        "l'argmax d'un `First` d'ordre source" % (a["port"]["second"],))
    # Et c'est bien le NATIF qui bascule, pas seulement le port.
    sec = lambda m: [t for t, _x in m["natif"]["seq"] if t != m["cible"]]          # noqa: E731
    assert sec(a) != sec(b)


# ---------------------------------------------------------------- 3. la confrontation LIVE DECISION

@pytest.fixture(scope="module")
def decision():
    """Les DEUX scenarios (`sans_stun` / `avec_stun`) sur le MEME runner, plus la contre-epreuve
    port-sans-filtre."""
    try:
        sid = D._resolve_session()
    except Exception as e:
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t566d_%s.json" % os.getpid())
    recs = D.campagne(sid, sf, 56601, D.BOARD)
    if not recs:
        pytest.skip("build KO -- session/host indisponible")
    return {rec["tag"]: rec for rec in recs}


def test_temoin_l_utilite_est_les_PV_de_la_cible(decision):
    """`utility = Fix64(GetStat(entity, 5 = Health))` -> le natif prefere la cible aux PV les plus
    HAUTS. TEMOIN : il etablit l'utilite AVANT que le filtre n'entre en jeu."""
    rec = decision["sans_stun"]
    assert rec["natif"]["ability"] == VEXILLA_MAGNIFICA, (
        "le natif ne caste pas 1183 sans stun -- montage sterile : %r" % (rec["natif"],))
    assert rec["port"].get("ability") == VEXILLA_MAGNIFICA
    assert rec["port"].get("target") == rec["natif"]["target"] == rec["attendu"]


def test_une_cible_STUNNEE_est_ECARTEE_par_le_natif_ET_par_le_port(decision):
    """L'ETAGE de #566. MEME etat, a UNE difference pres : la cible aux PV les plus hauts est
    desormais `Stunned`. Le natif BASCULE sur l'autre ; le port doit basculer avec lui."""
    rec = decision["avec_stun"]
    assert rec["natif"]["ability"] == VEXILLA_MAGNIFICA
    assert rec["natif"]["target"] == rec["attendu"], (
        "le natif n'a pas ecarte la cible stunnee (%r)" % (rec["natif"],))
    assert rec["port"].get("target") == rec["natif"]["target"]


def test_la_contre_epreuve_sans_filtre_MORD(decision):
    """Neutraliser `_target_is_stunned` doit RAMENER le port sur la cible stunnee. Sans cette
    morsure, l'accord ci-dessus pourrait venir de n'importe quoi d'autre que du filtre."""
    rec = decision["avec_stun"]
    assert rec["sans_filtre"].get("target") != rec["port"].get("target"), (
        "contre-epreuve NON discriminante : le filtre n'est pas ce qui decide")
    assert rec["sans_filtre"].get("target") == decision["sans_stun"]["natif"]["target"]
