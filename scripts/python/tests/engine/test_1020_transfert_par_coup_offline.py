"""#1020 -- le CLIQUET de l'etage `On(0x39 = EventTriggerType.PreDamageTaken)` et du transfert.

CE QUE CETTE GARDE VERROUILLE, et pourquoi elle ne peut pas passer par accident.

**Aucun etage n'est un PLANCHER DE POPULATION.** Le brief de la tranche le dit et c'est mesure sur
ce depot : un critere de peuplement (`>= 20`, `any(canal peuple)`) rougit sur le PROGRES et se tait
sur la REGRESSION. Ici chaque etage garde un INVARIANT, et chacun porte son TEMOIN -- une entree
fabriquee que le predicat doit REFUSER, ou une mutation qui doit le faire TOMBER. Un etage dont le
temoin ne mordrait pas serait un vert vide, et c'est justement ce que les assertions `temoin`
ci-dessous interdisent.

Les six etages :

  1. NO-OP du chokepoint partage -- sans consommateur, `kept == total` A L'IDENTIQUE. C'est
     l'invariant de non-regression des QUATRE vecteurs de degat. TEMOIN : un consommateur qui
     consomme DOIT faire tomber `kept` (sinon l'etage 1 mesurerait un chokepoint mort).
  2. GRANULARITE -- N coups damageants => N emissions. TEMOIN : un groupe dont TOUS les coups sont
     a zero n'emet RIEN (le gate `0 < DamageAppliedResult.get_Damage(&result)`).
  3. `isFirstDamagingHit` PROPRE AU COUP -- seul le premier coup damageant le porte.
  4. CONSOMMATION CIBLEE -- consommer le coup `i` retire `per_hit_pending[i]`, et LUI SEUL.
  5. CONSERVATION -- `transfer_damage_operation` DEPLACE : la victime ne perd rien, le protecteur
     prend le montant, le pending est vide. TEMOIN : sur un pending deja vide, l'operation est un
     no-op strict (elle ne fabrique pas de degat).
  6. STRUCTURE de l'arbre natif + REGISTRE. `CreateBehaviour` est
     `If(DSLTriggers$$Maybe(ConfigConst(chance)), TransferDamage(...), null)` : la condition est un
     PREDICAT (`IdunBattle.Entities.Triggers.MaybeTrigger`), pas le noeud EFFET homonyme. TEMOIN :
     un nom d'ability FABRIQUE doit etre ABSENT du registre.
  7. NORMALISATION du selecteur mono-entite -- le bug REEL trouve en live : `Owner@<+0x30>` rend un
     DICT, et l'iterer donnerait ses CLES, donc AUCUNE cible et un transfert no-op SILENCIEUX.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

from engine.runner.components import HealthComponent, PendingDamage, UnitComponent  # noqa: E402
from engine.runner.operations.damage import AttackDamageOperation                   # noqa: E402
from engine.runner.state import State                                               # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: PRIS LARGE VOLONTAIREMENT : trop etroit serait un FAUX VERT (le fichier ne se rejouerait pas
#: sous `--since` quand ce qu'il garde a bouge). On liste les DEUX etages qu'il confronte -- le
#: chokepoint et le transfert -- plus tout ce dont ils lisent la forme.
DECLENCHEUR = {
    "chemins": (
        # L'ETAGE : le chokepoint partage et sa decomposition par coup.
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/damage_hits.py",
        # Le CANAL : `PendingDamage` et le champ `HealthComponent.pending_damage`
        # (`FillUpStatComponent+0x64`) -- l'etage 1 et l'etage 5 en dependent tous les deux.
        "scripts/python/engine/runner/components.py",
        # Le TRANSFERT : l'Operation, la feuille DSL, la TriggeredAbility, et le registre qui
        # l'apparie a son nom gameconfig (etage 6).
        "scripts/python/engine/runner/operations/transfer_damage.py",
        "scripts/python/engine/runner/abilities/behaviours/transfer.py",
        "scripts/python/engine/runner/operations/triggers/loki/savior_protocols.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # La STRUCTURE de l'arbre (etage 6) : `If` et le PREDICAT `MaybeTrigger` -- confondre ce
        # dernier avec le noeud EFFET homonyme est precisement ce que l'etage garde.
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/triggers.py",
        # Le sens des ordinaux cites (`AbilityConstantType.chance` = 0x2a,
        # `TriggeredAbilityType.SaviorProtocols` = 0x460).
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        # Le gameconfig sert `constants.chance` (etage 6, volet valeur).
        "scripts/python/gameconfig.py",
    ),
    # `build: True` -- l'etage 6 LIT `constants.chance` du gameconfig et compare deux ordinaux
    # d'enum (`AbilityConstantType.chance` = 0x2a, `TriggeredAbilityType.SaviorProtocols` = 0x460).
    # Un changement de build peut donc faire basculer ce verdict SANS qu'un seul fichier du depot
    # bouge -- c'est exactement ce que ce drapeau veut dire.
    "build": True,
    # `toujours: False` -- les chemins ci-dessus bornent VRAIMENT le verdict : les six autres
    # etages sont purement structurels (ils n'appellent que `_pre_damage_taken_per_hit`,
    # `transfer_damage_operation` et la feuille DSL, tous listes). Le doute a ete resolu du cote
    # LARGE partout ou il en restait un (les deux modules d'enum, `gameconfig.py`, `behaviours.py`
    # et `triggers.py` y sont alors qu'aucun etage n'en lit le CORPS).
    "toujours": False,
    "raison": ("garde l'etage `On(0x39 = EventTriggerType.PreDamageTaken)` (emission PAR COUP, "
               "retour LU par le champ pendant `FillUpStatComponent+0x64`) et le transfert de "
               "degat qui le consomme (`IdunBattle.Operations.TransferDamageOperation`) : les "
               "chemins couvrent le chokepoint, sa decomposition par coup, le canal pendant, les "
               "trois pieces du transfert, le registre qui les apparie, et la structure d'arbre "
               "que l'etage 6 confronte."),
}


class _Dispatch:
    """Substitut du module `triggers.dispatch.attack`. `_pre_damage_taken_per_hit` le recoit en
    ARGUMENT : aucune monkey-substitution, donc aucune forme d'import (A/B/C) ne peut desarmer
    cette garde -- le vice mesure par #484 / #429-r1 est structurellement hors de portee ici."""

    def __init__(self, consume_at=None, thc=None):
        self.calls = []
        self.consume_at = consume_at
        self.thc = thc

    def pre_damage_taken_triggers(self, state, source_id, target_id, profile=None,
                                  is_first_damaging_hit=None, source_ability=None):
        # `source_ability` (#1020-r3) = le canal `AbilityEntities+0x98`. Ce stub DOIT porter le
        # contrat REEL du vecteur : un stub en retard d'un parametre ne fait pas rougir la garde,
        # il la fait tomber sur son propre echafaudage.
        idx = len(self.calls)
        self.calls.append(is_first_damaging_hit)
        if self.consume_at is not None and idx == self.consume_at:
            self.thc.pending_damage = None      # mirror `TransferDamageOperation$$GetDamage`
        return []


def _hc(hp=1000):
    return HealthComponent(hp=hp, hp_max=hp)


def _run(thc, dispatch, pend, total, shield=0, first=True):
    return AttackDamageOperation._pre_damage_taken_per_hit(
        None, 1, 2, thc, total, shield, "Physical",
        None if pend is None else {"per_hit_pending": pend}, dispatch,
        is_first_damaging_hit=first)


# ---------------------------------------------------------------- 1. NO-OP + son TEMOIN

@pytest.mark.parametrize("pend,total,shield", [
    ([(300, 0), (250, 0), (200, 0)], 750, 0),
    ([(120, 30), (80, 0)], 200, 30),
    (None, 500, 0),                              # vecteur SANS decomposition (DoT / knockback)
    ([], 0, 0),
])
def test_sans_consommateur_le_chokepoint_est_strictement_inchange(pend, total, shield):
    """ETAGE 1 -- l'invariant de non-regression du chokepoint des QUATRE vecteurs de degat."""
    thc = _hc()
    kept_h, kept_s, transfers = _run(thc, _Dispatch(), pend, total, shield)
    assert (kept_h, kept_s, transfers) == (total, shield, 0), (
        "sans consommateur le chokepoint doit rendre EXACTEMENT ce qu'il recevait "
        "(attendu (%d, %d, 0), obtenu (%d, %d, %d))" % (total, shield, kept_h, kept_s, transfers))
    assert thc.pending_damage is None, (
        "le pending ne doit pas survivre au coup : sa portee native est UN `ApplyDamageOperation"
        "$$Execute`, pas le groupe")


def test_temoin_un_consommateur_fait_bien_tomber_le_kept():
    """TEMOIN de l'etage 1. Si consommer ne changeait rien, l'etage 1 serait vert sur un
    chokepoint MORT -- exactement le vice que la tranche repare."""
    thc = _hc()
    kept_h, _ks, transfers = _run(thc, _Dispatch(consume_at=0, thc=thc),
                                  [(300, 0), (250, 0)], 550)
    assert kept_h == 250 and transfers == 1, (
        "TEMOIN AVEUGLE : consommer le pending n'a pas fait tomber `kept` (%d au lieu de 250) "
        "-- l'etage 1 ne prouverait alors rien" % kept_h)


# ---------------------------------------------------------------- 2. GRANULARITE + TEMOIN

def test_le_vecteur_est_emis_une_fois_par_coup_damageant():
    """ETAGE 2 -- `IdunBattle.Operations.ApplyDamageOperation$$Execute` est appelee UNE FOIS PAR
    COUP. Le port n'emettait qu'une fois par GROUPE : un consommateur par coup y etait inatteignable."""
    d = _Dispatch()
    _run(_hc(), d, [(300, 0), (250, 0), (200, 0)], 750)
    assert len(d.calls) == 3, (
        "granularite : 3 coups damageants doivent produire 3 emissions, obtenu %d "
        "(un port PAR GROUPE en produirait 1)" % len(d.calls))


def test_temoin_un_coup_a_zero_n_emet_rien():
    """TEMOIN de l'etage 2 -- le gate natif `if (0 < DamageAppliedResult.get_Damage(&result))`.
    Sans lui, le compte d'emissions serait celui des COUPS, pas des coups DAMAGEANTS."""
    d = _Dispatch()
    _run(_hc(), d, [(0, 0), (300, 0), (0, 40)], 300, 40)
    assert len(d.calls) == 2, (
        "gate zero : seuls les coups a `health + shield > 0` emettent (attendu 2, obtenu %d) "
        "-- le coup (0,40) DOIT emettre, le coup (0,0) NON" % len(d.calls))
    d2 = _Dispatch()
    _run(_hc(), d2, [(0, 0), (0, 0)], 0)
    assert d2.calls == [], (
        "TEMOIN AVEUGLE : un groupe entierement a zero a quand meme emis %d fois" % len(d2.calls))


# ---------------------------------------------------------------- 3. isFirstDamagingHit

def test_le_flag_premier_coup_damageant_est_propre_au_coup():
    """ETAGE 3 -- `DamageAppliedResult+0x18`. Le flag threade dit « aucun degat encore inflige dans
    CETTE attaque » ; il se consomme au premier coup qui emet, pas au premier coup tout court."""
    d = _Dispatch()
    _run(_hc(), d, [(0, 0), (300, 0), (200, 0)], 500)
    assert d.calls == [True, False], (
        "flags emis %s : le PREMIER coup damageant (et lui seul) porte le flag" % (d.calls,))
    d2 = _Dispatch()
    _run(_hc(), d2, [(300, 0), (200, 0)], 500, first=False)
    assert d2.calls == [False, False], (
        "un groupe qui n'est pas le premier damageant ne doit marquer AUCUN coup, obtenu %s"
        % (d2.calls,))


# ---------------------------------------------------------------- 4. CONSOMMATION CIBLEE

@pytest.mark.parametrize("at,attendu", [(0, 450), (1, 500), (2, 550)])
def test_consommer_un_coup_retire_ce_coup_la_et_lui_seul(at, attendu):
    """ETAGE 4 -- c'est la difference entre DEPLACER et DOUBLER. Un port qui retirerait le GROUPE
    rendrait 0 dans les trois cas ; un port qui n'en retirerait aucun rendrait 750."""
    thc = _hc()
    kept_h, _ks, transfers = _run(thc, _Dispatch(consume_at=at, thc=thc),
                                  [(300, 0), (250, 0), (200, 0)], 750)
    assert (kept_h, transfers) == (attendu, 1), (
        "consommer le coup %d doit laisser %d (obtenu %d)" % (at, attendu, kept_h))


def test_la_part_bouclier_du_pending_disparait_aussi():
    """ETAGE 4 (volet bouclier) -- `DamageAppliedResult+0x08` fait partie du pending, donc de ce
    que la consommation retire. `get_Damage` = `+0x08 + +0x04`."""
    thc = _hc()
    kept_h, kept_s, _t = _run(thc, _Dispatch(consume_at=0, thc=thc), [(120, 30), (80, 0)], 200, 30)
    assert (kept_h, kept_s) == (80, 0), (
        "le coup (120,30) consomme doit retirer LES DEUX parts, obtenu (%d, %d)" % (kept_h, kept_s))


# ---------------------------------------------------------------- 5. CONSERVATION + TEMOIN

def _duo(hp_v=1000, hp_d=800):
    st = State()
    victime, drone, source = st.add_entity(), st.add_entity(), st.add_entity()
    for e, hp in ((victime, hp_v), (drone, hp_d), (source, 900)):
        e.add_component(UnitComponent(visual_id="tauCrisis", alive=True))
        e.add_component(_hc(hp))
    return st, victime, drone, source


def test_le_transfert_deplace_le_degat_il_ne_le_duplique_pas():
    """ETAGE 5 -- LA question de la tranche. On mesure LES DEUX cotes : deux hypotheses qui
    rendraient le meme total (bonus vs deplacement) sont separees par le fait que la VICTIME ne
    perd RIEN."""
    from engine.runner.operations.transfer_damage import transfer_damage_operation
    st, victime, drone, source = _duo()
    vhc, dhc = victime.get_component(HealthComponent), drone.get_component(HealthComponent)
    vhc.pending_damage = PendingDamage("Physical", 240, 0)
    hp_v0, hp_d0 = vhc.hp, dhc.hp
    res = transfer_damage_operation(st, source.id, victime.id, drone.id)
    assert res is not None, "l'operation doit rendre son compte-rendu"
    assert hp_v0 - vhc.hp == 0, (
        "la VICTIME a perdu %d PV : le degat aurait ete DUPLIQUE, pas deplace" % (hp_v0 - vhc.hp))
    assert hp_d0 - dhc.hp == 240, (
        "le PROTECTEUR devait prendre 240, il a pris %d" % (hp_d0 - dhc.hp))
    assert vhc.pending_damage is None, (
        "`TransferDamageOperation$$GetDamage` ecrit `*(qword*)(comp+0x64) = 0` : le pending DOIT "
        "etre consomme, sinon un second protecteur le prendrait une seconde fois")


def _duo_avec_bouclier(shield=200, hp_v=1000):
    """FIXTURE NOMMEE de l'etage 8 : la VICTIME porte un `ShieldComponent` non nul -- le regime que
    `#1020-r1` nommait comme NON ATTEINT par les porteurs T'au de `SaviorProtocols`, et que rien ne
    mesurait donc."""
    from engine.runner.components import ShieldComponent
    st, victime, drone, source = _duo(hp_v=hp_v)
    shc = ShieldComponent()
    shc.add_or_update_shield(int(shield))
    victime.add_component(shc)
    assert shc.get_total_shield() == int(shield), (
        "la fixture doit REELLEMENT poser un bouclier, sinon les trois bras de l'etage 8 "
        "mesureraient 0 == 0 et seraient verts sur un montage vide")
    return st, victime, drone, source, shc


# ---------------------------------------------------------------- 8. #1020-r1 : LE BOUCLIER

def test_un_coup_TRANSFERE_ne_deplete_PAS_le_bouclier_de_la_victime():
    """ETAGE 8 -- `#1020-r1`. `IdunBattle.Operations.ApplyDamageOperation$$Execute` relit le pending
    APRES l'emission d'`On(0x39)` et en tire les DEUX parts depuis le MEME `GetValueOrDefault` :

        GetValueOrDefault(healthComp[+0x64], &pending);
        local_7c8 = FillUpStatComponent$$Reduce(hp, pending.healthDamage);
        ApplyDamageOperation$$ReduceShield(this, target, pending.shieldDamage);

    Un coup consomme par `TransferDamageOperation$$GetDamage` met les DEUX a zero. Avant ce
    correctif le port annulait les PV et depletait quand meme le bouclier."""
    st, victime, drone, source, shc = _duo_avec_bouclier(shield=200)
    thc = victime.get_component(HealthComponent)
    hp0, bouclier0 = thc.hp, shc.get_total_shield()
    AttackDamageOperation._apply_damage_pipeline(
        st, victime.id, source.id, victime, thc, 300, "Physical", shield_dmg=120,
        hits_result={"per_hit_pending": [(300, 120)]},
        # Le dispatch CONSOMME le pending -- c'est ce que fait le transfert de `SaviorProtocols`.
        )
    # sans consommateur : le bouclier DOIT tomber (c'est le temoin ci-dessous qui le mesure)
    assert shc.get_total_shield() == bouclier0 - 120, (
        "TEMOIN AVEUGLE : sans transfert le bouclier doit se depleter normalement (%d -> %d)"
        % (bouclier0, shc.get_total_shield()))
    assert thc.hp == hp0 - 300


def test_le_bouclier_survit_quand_le_pending_est_CONSOMME(monkeypatch):
    """ETAGE 8 (le bras qui portait la faute). Le consommateur vide le pending pendant `On(0x39)` :
    le natif n'enleve alors NI PV NI BOUCLIER."""
    from engine.runner.operations.triggers.dispatch import attack as A
    st, victime, drone, source, shc = _duo_avec_bouclier(shield=200)
    thc = victime.get_component(HealthComponent)
    hp0, bouclier0 = thc.hp, shc.get_total_shield()

    def _consomme(state, source_id, target_id, profile=None, is_first_damaging_hit=None,
                  source_ability=None):
        thc.pending_damage = None          # mirror `TransferDamageOperation$$GetDamage`
        return []

    monkeypatch.setattr(A, "pre_damage_taken_triggers", _consomme)
    AttackDamageOperation._apply_damage_pipeline(
        st, victime.id, source.id, victime, thc, 300, "Physical", shield_dmg=120,
        hits_result={"per_hit_pending": [(300, 120)]})
    assert thc.hp == hp0, "coup transfere : la victime ne doit perdre AUCUN PV"
    assert shc.get_total_shield() == bouclier0, (
        "coup transfere : la victime ne doit perdre AUCUN BOUCLIER (%d -> %d) -- le natif lit "
        "`pending.shieldDamage`, donc 0, exactement comme `Reduce` lit `pending.healthDamage`"
        % (bouclier0, shc.get_total_shield()))


def test_une_cible_deja_OVERKILLEE_ne_perd_plus_son_bouclier():
    """ETAGE 8 (second effet, LU au meme endroit). Le SITE (A) `if (HasFlag(target, 8 = Overkilled))
    { ...; return; }` precede l'ecriture du pending, donc AUSSI le `ReduceShield`. La depletion
    ayant quitte les appelants pour le chokepoint, elle passe desormais sous ce gate."""
    from engine.runner.components import UnitFlagsComponent
    st, victime, drone, source, shc = _duo_avec_bouclier(shield=200)
    thc = victime.get_component(HealthComponent)
    fl = UnitFlagsComponent()
    fl.add(UnitFlagsComponent.OVERKILLED)
    victime.add_component(fl)
    bouclier0 = shc.get_total_shield()
    AttackDamageOperation._apply_damage_pipeline(
        st, victime.id, source.id, victime, thc, 300, "Physical", shield_dmg=120,
        hits_result={"per_hit_pending": [(300, 120)]})
    assert shc.get_total_shield() == bouclier0, (
        "cible overkillee : le natif `return` AVANT le pending, donc avant `ReduceShield`")


def test_temoin_sur_un_pending_vide_l_operation_ne_fabrique_rien():
    """TEMOIN de l'etage 5 -- `if (*pcVar7 != '\\0')` garde toute la boucle de transfert. Sans ce
    temoin, une operation qui inventerait un montant par defaut passerait l'etage 5."""
    from engine.runner.operations.transfer_damage import transfer_damage_operation
    st, victime, drone, source = _duo()
    dhc = drone.get_component(HealthComponent)
    hp_d0 = dhc.hp
    assert transfer_damage_operation(st, source.id, victime.id, drone.id) is None, (
        "pending vide : l'operation doit rendre None")
    assert dhc.hp == hp_d0, "pending vide : le protecteur ne doit RIEN perdre"


# ---------------------------------------------------------------- 6. STRUCTURE + REGISTRE + TEMOIN

def test_l_arbre_natif_est_un_If_dont_la_condition_est_le_predicat_Maybe():
    """ETAGE 6 -- `SaviorProtocolsAbility$$CreateBehaviour` appelle
    `IdunBattleLogic.Entities.DSLTriggers$$Maybe` (surcharge PREDICAT ->
    `IdunBattle.Entities.Triggers.MaybeTrigger`) puis `DSLBehaviors$$If(maybe, transfer, 0)`.

    Le confondre avec le noeud EFFET homonyme (`MaybeBehaviour`) changerait la STRUCTURE pour un
    resultat en apparence identique -- exactement la recopie de voisin que la doctrine interdit."""
    from engine.entities.behaviours import If
    from engine.entities.triggers import MaybeTrigger
    from engine.runner.abilities.behaviours.transfer import TransferDamage
    from engine.runner.operations.triggers.loki.savior_protocols import savior_behaviour_tree
    tree = savior_behaviour_tree(None)
    assert isinstance(tree, If), "le noeud de tete est un `If` (`DSLBehaviors$$If`)"
    assert isinstance(tree.cond, MaybeTrigger), (
        "la CONDITION doit etre le PREDICAT `MaybeTrigger` (`DSLTriggers$$Maybe`), obtenu %s"
        % type(tree.cond).__name__)
    assert isinstance(tree.then, TransferDamage), (
        "la branche THEN doit etre la feuille `TransferDamage`, obtenu %s" % type(tree.then).__name__)
    assert tree.otherwise is None, "le 4e argument natif est `(void *)0x0` -> pas de branche ELSE"


def test_la_chance_vient_de_la_constante_du_gameconfig():
    """ETAGE 6 (volet valeur) -- `ConfigConst(0x2a = AbilityConstantType.chance, abilityState)`.
    C'est une CONSTANTE d'ability, donc ni le rang ni le niveau du passif ne la bougent."""
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.runner.operations.triggers.loki import savior_protocols as SP
    assert int(AbilityConstantType.chance) == 0x2a, (
        "l'ordinal de `AbilityConstantType.chance` a bouge (%d) -- le mirror lit une autre cle"
        % int(AbilityConstantType.chance))
    assert SP.savior_chance() > 0, (
        "`constants.chance` introuvable au gameconfig -> `Maybe(0)` ne declencherait jamais et "
        "la face COMBAT serait un no-op silencieux")


def test_le_registre_porte_l_ability_et_refuse_un_nom_fabrique():
    """ETAGE 6 (volet registre) + son TEMOIN. Le temoin est un NOM FABRIQUE, pas un plancher de
    population : il reste juste quel que soit le nombre d'abilities portees."""
    import engine.runner.operations.triggers.dispatch.registry as REG
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.operations.triggers.loki.savior_protocols import SaviorProtocolsAbility
    assert REG.ABILITY_TRIGGERS.get("SaviorProtocols") == [SaviorProtocolsAbility], (
        "`SaviorProtocols` doit etre inscrite dans `ABILITY_TRIGGERS` sous son NOM gameconfig")
    assert SaviorProtocolsAbility.TRIGGERED_ABILITY_ID == int(TriggeredAbilityType.SaviorProtocols)
    assert SaviorProtocolsAbility.TRIGGERED_ABILITY_ID == 0x460, (
        "l'ordinal 1120 est celui LU au `ActorHasTriggeredAbility(Target, 0x460)` du gate natif")
    assert "SaviorProtocolsXX" not in REG.ABILITY_TRIGGERS, (
        "TEMOIN AVEUGLE : le registre accepte un nom FABRIQUE -- l'assertion ci-dessus ne "
        "prouverait alors rien sur l'appariement nom <-> classe")


# ---------------------------------------------------------------- 7. le bug REEL trouve en live

def test_un_selecteur_mono_entite_designe_bien_une_cible_de_transfert():
    """ETAGE 7 -- LE BUG QUE LE LIVE A TROUVE, et il etait SILENCIEUX.

    `SaviorProtocols` passe `Owner@<DSLSelectors+0x30>` en `transferTargets`. Un selecteur
    mono-entite rend un **DICT** d'unite ; l'iterer nu donne ses CLES (des chaines), donc
    `isinstance(u, dict)` est faux, donc `continue`, donc AUCUNE cible -- le trigger matchait, le
    behaviour s'executait, et RIEN ne partait. Aucune erreur, aucun crash.

    Meme piege et meme parade que `entities/behaviours.py::Foreach`."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.behaviours.transfer import TransferDamage
    from engine.entities.selectors.accessors import Actor, Target
    from engine.entities.selectors.tiles import Caster
    st, victime, drone, source = _duo()
    vhc, dhc = victime.get_component(HealthComponent), drone.get_component(HealthComponent)
    vhc.pending_damage = PendingDamage("Physical", 175, 0)
    hp_d0 = dhc.hp
    ent = entities_from_state(st, drone.id, victime.id, actor_id=source.id)
    ectx = ExecutionContext(state=st, rng=None)
    TransferDamage(caster_sel=Actor(), original_target_sel=Target(),
                   transfer_targets_sel=Caster()).execute(ent, ectx)
    emis = [p for (n, p) in ectx.emitted if n == "TransferDamage"]
    assert emis and emis[0].get("transfer_target") == drone.id, (
        "le selecteur mono-entite `Caster()` (= `Owner@<+0x30>`) n'a designe AUCUNE cible : "
        "la normalisation dict -> [dict] a saute, et le transfert est un no-op SILENCIEUX")
    assert hp_d0 - dhc.hp == 175, (
        "le protecteur devait prendre 175, il a pris %d" % (hp_d0 - dhc.hp))
