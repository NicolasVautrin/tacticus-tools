"""#927 -- `FuryOfTheAncients` (1247, `bloodMephiston`) : les crans OFFLINE du port.

Six etages, tous derives du DECOMPILE et re-derivables du build -- aucun ne monte de runner :

  1. le passif est INSCRIT (registre de trigger) et son effet 1320 aussi (registre d'effet) ;
  2. les LITTERAUX du decompile sont figes AU SITE (un `probe_313` sur les enums ne les verrait
     pas : ce sont des constantes de module, pas des ordinaux d'enum) ;
  3. `SortByFormula` lie bien `AbilityEntities.ActiveTarget@+0x20`, le slot LU dans la lambda ;
  4. `DamagePredictionFormula` CONSOMME son tirage AVANT ses null-guards ;
  5. la face DECISION/ATTAQUE du playbook 1247 est DEAD -- verdict GRAVE, pas suppose ;
  6. `has_heal_blockers` mord sur la famille `HealBlockingEffect`, et sur elle SEULE.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.dsl.base import Const, DslContext                          # noqa: E402
from engine.entities.effect_type import EffectType                     # noqa: E402
from engine.entities.effects.factory import EffectFactory              # noqa: E402
from engine.entities.effects.loki.heal_blocking import (               # noqa: E402
    FuryOfTheAncientsEffect, HealBlockingEffect
)
from engine.entities.formulas import DamagePredictionFormula           # noqa: E402
from engine.entities.selectors.accessors import ActiveTarget           # noqa: E402
from engine.entities.selectors.units import SortByFormula, UnitSet     # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS   # noqa: E402
from engine.runner.operations.triggers.loki import fury_of_the_ancients as F       # noqa: E402

#: ⚠ `normpath` N'EST PAS COSMETIQUE (#931) : le capteur d'empreinte de `probe_457` enregistre le
#: chemin TEL QU'OUVERT, et `probe_486r15` le confronte au `DECLENCHEUR` sous forme RELATIVE A LA
#: RACINE. Sans lui, le temoin s'inscrit
#: `scripts/python/tests/engine/../../../../data/symbols/<build>/frida/methods.tsv`, que le
#: `data/symbols/**` ajoute par `build: True` ne peut pas apparier -> `DECLARE TROP ETROIT`.
#: Le defaut est INVISIBLE tant que l'empreinte de ce fichier n'est pas mesuree, et c'est en la
#: mesurant (ordre #486-r29) qu'il est apparu.
#: ⚠ #931, #937 ET #936 ont trouve ce meme defaut INDEPENDAMMENT, en gravant l'empreinte chacun de
#: son cote -- TROIS mesures concordantes, une seule correction. Ce n'est plus une coincidence :
#: c'est la signature d'un defaut LATENT DE FORME, arme par tout test qui construit un chemin de
#: `data/` a coups de `".."` et qui obtient ensuite une empreinte. Les trois tranches l'ont trouve
#: dans la meme journee, aucune ne pouvait voir les deux autres.
#: `normpath` et non `realpath` (la 3e tranche proposait `realpath`) : la resolution doit rester
#: LEXICALE. `realpath` suivrait un point de reparse, or un worktree ne doit jamais en porter vers
#: l'arbre principal -- resoudre physiquement y ferait pointer le temoin hors du checkout courant.
BUILD_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "symbols"))

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # VIDE, et c'est une MESURE : `--proposer` rend « RIEN A DECLARER hors de la cascade » -- les
    # neuf foyers de la tranche (le passif, son registre, `formulas`, `units`, `heal_blocking`,
    # `factory`, `attack_query`, `chain`, `context`) sont TOUS dans la fermeture d'imports que le
    # foyer derive lui-meme (#531). Les recopier ici serait du bruit, pas un cran de plus.
    "chemins": (),
    # L'etape 5 LIT `data/symbols/<build>/frida/methods.tsv` : ce test rougit si un build futur
    # ajoute une voie ATTAQUE propre au playbook 1247 -- c.-a-d. si le verdict DEAD cesse d'etre
    # vrai. C'est la SEULE entree hors-import du fichier, et elle n'est visible d'aucun import.
    "build": True,
    "toujours": False,
    "raison": ("100 % offline. Grave : les deux registres (trigger + effet), les litteraux du "
               "decompile AU SITE (dont `maxTargets = Direct(1)`, la ou un commentaire du depot "
               "annote `DSLFormulas+0x20` comme le Zero), le slot lie par `SortByFormula` "
               "(`ActiveTarget@+0x20`, LU dans la lambda), l'ORDRE du tirage de "
               "`DamagePredictionFormula` (avant ses null-guards), le verdict DEAD de la face "
               "DECISION/ATTAQUE -- confronte a la table de symboles du BUILD, d'ou `build: True` "
               "-- et le predicat `has_heal_blockers`, qui degrade du cote RESTRICTIF."),
}


# ---------------------------------------------------------------- 1. les DEUX registres ---------
def test_etape1_le_passif_et_son_effet_sont_inscrits():
    """Entrer dans `ABILITY_TRIGGERS` SANS inscrire l'effet que le behaviour pose (ou l'inverse)
    donne une degradation SILENCIEUSE : la chaine frappe mais ne bloque plus le soin, ou pose un
    `BaseEffect` nu que `has_heal_blockers` ne voit pas. Les deux crans dans le meme test."""
    assert F.FuryOfTheAncientsAbility in ABILITY_TRIGGERS.get("FuryOfTheAncients", ()), (
        "le passif n'est dans AUCUN registre de trigger -> il ne fire jamais, sans erreur")
    assert (F.FuryOfTheAncientsAbility.TRIGGERED_ABILITY_ID
            == int(TriggeredAbilityType.FuryOfTheAncients) == 1247)
    made = EffectFactory.create({"name": "FuryOfTheAncients",
                                 "effectType": int(EffectType.FuryOfTheAncients)}, 100, None, None)
    assert isinstance(made, FuryOfTheAncientsEffect), (
        "l'effet 1320 se materialise en %s -- un `BaseEffect` nu serait INVISIBLE de "
        "`has_heal_blockers`" % type(made).__name__)
    assert isinstance(made, HealBlockingEffect)
    assert int(EffectType.FuryOfTheAncients) == 0x528 == 1320


# ---------------------------------------------------------------- 2. les LITTERAUX du natif -----
def test_etape2_litteraux_du_decompile_figes_au_site():
    """Les constantes que le decompile DONNE, figees a l'endroit ou elles sont ECRITES.

    ⚠ `MAX_TARGETS` est le cran le plus important du fichier, et sa valeur vient de la MESURE, pas
    d'un offset : `CreateBehaviour` lit `<DSLFormulas + 0x20>`, mais `DSLTriggers$$AmountIsZero` lit
    le MEME offset comme son `minAmount`, et les deux comportements mesures sont incompatibles
    (1 cote chaine, 0 cote gate -- cf. l'en-tete du module porte et `probe_927 --solo`). A 0, le
    behaviour ne ferait AUCUN saut : une seule cible, la moitie de l'ability, sans erreur ni crash."""
    assert F.MAX_TARGETS == 1, "1 saut supplementaire = 2 cibles (mesure, 3 montages)"
    assert F.UNIT_SELECTION_TYPE == 3          # OnlyAliveAndTargetable, surcharge A d'AdjacentEnemies
    assert F.ADJACENT_UNIQUE == 1
    assert F.DAMAGE_PROFILE == "Psychic"       # GetDamageProfileOrDefault(DamageProfileType 0xd)
    assert F.IS_MELEE is True                  # gameconfig attackRangeType
    # `chainOptions` : le ctor natif n'ecrit QUE `+0x12`.
    assert (F.CHAIN_DEFERRED_HIT, F.CHAIN_ALLOW_REPEAT_TARGETS,
            F.CHAIN_ALLOW_IMMEDIATE_REPEAT) == (True, False, False)
    # les DEUX `ConfigConst` du decompile, relus dans le gameconfig VIVANT (pas recopies)
    assert F._config_const(F.HITS_KEY) == 2            # AbilityConstantType 0x2f = nrOfHits
    assert F._config_const(F.EFFECT_TURNS_KEY) == 2    # AbilityConstantType 0x69 = effectTurns
    # `prioritizeKills` = FAUX (idiome `<< 8` du pseudo-C) -> pas de bonus x3/x2 dans la cle de tri.
    node = F.fury_damage_prediction_formula(ActiveTarget(), Const(10), 2)
    assert isinstance(node, DamagePredictionFormula)
    assert node.prioritize_kills is False
    assert node.damage_profile == "Psychic" and node.is_melee is True


# ---------------------------------------------------------------- 3. le slot lie par le tri -----
def test_etape3_sortbyformula_lie_active_target():
    """`SortByFormulaSelector.u003Cu003Ec__DisplayClass4_0$$u003CSelectu003Eb__0` ecrit
    `closure+0x30 = s`, c.-a-d. `<la copie d'AbilityEntities>+0x20` = **ActiveTarget**, puis appelle
    `formula.Calculate(<la copie>)`.

    Sans ce binding, toute formule ecrite avec `ActiveTarget()` -- le nom que le decompile CITE --
    rend la meme cle pour tous les candidats, et le tri degenere en ordre SOURCE. C'est exactement
    le mutant 3 de `probe_927`, qui MORD sur MC1_63."""
    class _Key:
        """Formule VALEUR qui lit `ActiveTarget` : la cle est l'id de l'element courant."""
        def evaluate(self, ctx):
            from engine.dsl.base import resolve_unit
            u = resolve_unit(ActiveTarget(), ctx)
            return 0 if u is None else int(u["id"])

    units = [{"id": 1, "team": 0, "alive": True, "hp": 10},
             {"id": 3, "team": 0, "alive": True, "hp": 10},
             {"id": 2, "team": 0, "alive": True, "hp": 10}]
    ctx = DslContext(units=list(units))
    got = [u["id"] for u in SortByFormula(UnitSet(units), _Key()).evaluate(ctx)]
    assert got == [3, 2, 1], (
        "le tri DESC par la cle lue sur `ActiveTarget` doit rendre [3,2,1] ; obtenu %s -- le slot "
        "lie n'est pas le bon" % got)
    got_asc = [u["id"] for u in SortByFormula(UnitSet(units), _Key(), ascending=True).evaluate(ctx)]
    assert got_asc == [1, 2, 3], "flag natif : 0 = DESC, 1 = ASC"


# ---------------------------------------------------------------- 4. l'ORDRE du tirage ----------
def test_etape4_la_prediction_tire_avant_ses_null_guards():
    """`DamagePredictionFormula$$Calculate` evalue `(+0x40).Calculate(entities, out MinMaxDamage)`
    -- le slot **1**, donc un TIRAGE quand la formule est un `RandomAmount` -- **AVANT** le
    `if (defender == null || attacker == null || GetUnit(defender) == null) return 0`.

    Un port qui sortirait sur le null-guard sans tirer desalignerait le MT des qu'un candidat du
    tri n'a pas de seconde cible (loi #215). C'est le mutant 4 de `probe_927`, qui MORD sur MC1_63."""
    tirages = []

    class _Damage:
        def evaluate(self, ctx):
            tirages.append(1)
            return 7

    class _Nothing:
        """Selecteur VIDE -- le `defender` est nul, le natif sort en `return 0` APRES avoir tire."""
        def evaluate(self, ctx):
            return []

    ctx = DslContext(units=[], caster={"id": 1, "team": 0, "alive": True, "hp": 10})
    node = DamagePredictionFormula(_Nothing(), None, _Nothing(), None, _Damage(), 2,
                                   damage_profile="Psychic")
    assert node.evaluate(ctx) == 0, "defender nul -> 0"
    assert tirages == [1], (
        "le tirage doit avoir ete CONSOMME malgre la sortie a 0 ; obtenu %s tirage(s)"
        % len(tirages))


# ---------------------------------------------------------------- 5. la face DECISION DEAD ------
def _methods_tsv():
    """La table `frida/methods.tsv` du build **COURANT** (`data/symbols/CURRENT`).

    ⚠ CORRIGE PAR #937 : la version d'avant prenait le **premier** repertoire rendu par
    `os.listdir(BUILD_DIR)`, c'est-a-dire `gqfc5mff6c` (ordre alphabetique) -- un build **PERIME**.
    Le verdict DEAD de l'etape 5 etait donc rendu contre le mauvais dump, et l'annonce
    « si un build futur ajoute une voie ATTAQUE, ce test rougit » etait FAUSSE : le fichier lu ne
    bougeait jamais. C'est le vice que le CLAUDE.md nomme (« une RVA resolue contre le mauvais dump
    donne un nom incoherent »), applique a un nom de methode. Trouve en gravant l'empreinte #457 de
    ce fichier, qui a rendu son DECLENCHEUR TROP ETROIT en pointant `data/symbols/gqfc5mff6c/...`.

    Repli sur l'ancien balayage si `CURRENT` est absent -- l'etape SKIPPE alors comme avant, elle ne
    ment pas."""
    cur = os.path.join(BUILD_DIR, "CURRENT")
    if os.path.exists(cur):
        with open(cur, encoding="utf-8") as fh:
            build = fh.read().strip()
        p = os.path.join(BUILD_DIR, build, "frida", "methods.tsv")
        if build and os.path.exists(p):
            return p
    builds = [d for d in os.listdir(BUILD_DIR)
              if os.path.isdir(os.path.join(BUILD_DIR, d)) and not d.startswith(".")]
    for b in builds:
        p = os.path.join(BUILD_DIR, b, "frida", "methods.tsv")
        if os.path.exists(p):
            return p
    return None


def test_etape5_face_decision_attaque_est_dead():
    """VERDICT GRAVE : `FuryOfTheAncientsPlaybook` ne surcharge AUCUNE voie ATTAQUE.

    Le dump ne lui connait que `.ctor`, `GetDamagePrediction`, `GetDamagedEnemyUtility`,
    `GetAdjacentEnemyUtility` et `CalculateMovementUtilityInStepsInternal` : les voies attaque
    (`AttackUtility*`, `CalculateAttackUtility*`) restent celles de `TriggeredAbilityPlaybook<T>`,
    dont le corps rend `yield Fix64.op_Implicit(0)` des que `IsRegularAttack` est faux (#375). Le
    port ne DOIT donc pas en ecrire une -- et si un build futur en ajoute une, ce test rougit.

    ⚠ Le critere porte sur la table FRIDA (indexee par adresse) : elle ne prouve pas l'ABSENCE
    d'une surcharge en general (corps dedupliques), mais elle prouve que la voie attaque n'a PAS de
    corps PROPRE a cette classe -- ce qui est precisement la question ici, la face mouvement, elle,
    en ayant un."""
    tsv = _methods_tsv()
    if tsv is None:
        pytest.skip("aucune table `frida/methods.tsv` sous data/symbols")
    prefix = "IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook."
    noms = set()
    with open(tsv, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            cols = line.split("\t")
            if len(cols) > 1 and cols[1].startswith(prefix):
                noms.add(cols[1][len(prefix):])
    assert noms, "la classe native est introuvable dans la table -- montage a revoir"
    # la face MOUVEMENT existe (temoin NON VIDE : sans lui l'assertion suivante serait creuse)
    assert any("Movement" in n for n in noms), (
        "la face MOUVEMENT devrait etre presente ; noms lus : %s" % sorted(noms))
    attaque = sorted(n for n in noms if "Attack" in n)
    assert not attaque, (
        "une voie ATTAQUE propre est apparue sur le playbook 1247 (%s) -- le verdict DEAD de #927 "
        "n'est plus vrai, il faut la RE et la porter" % attaque)


# ---------------------------------------------------------------- 6. le bloqueur de soin --------
class _FakeEffects:
    def __init__(self, by_unit):
        self.by_unit = by_unit


class _FakeState:
    def __init__(self, effects):
        self.effects = effects


def test_etape6_has_heal_blockers_lit_la_famille_et_elle_seule():
    """`UnitExtensions$$HasHealBlockers` = « le dict `HealthComponent+0x78` est non vide », et ce
    dict n'est ecrit QUE par `HealBlockingEffect$$ApplyInternal`/`RevertInternal`.

    Le port teste donc la FAMILLE. Deux crans : il MORD sur une instance vivante de 1320 (sinon le
    passif serait porte a moitie -- degat sans blocage), et il ne mord PAS sur un effet quelconque
    (sinon on refuserait des soins que le natif accorde -- degradation RESTRICTIVE)."""
    from engine.entities.effects.base import BaseEffect
    import engine.runner.abilities.attack_query as AQ

    fury = FuryOfTheAncientsEffect(name="FuryOfTheAncients",
                                   effect_type=int(EffectType.FuryOfTheAncients))
    autre = BaseEffect(name="Whatever", effect_type=1)
    st = _FakeState(_FakeEffects({10: [fury], 11: [autre], 12: []}))

    # `_resolves_to_unit` interroge le State reel -> on le neutralise pour isoler CE predicat.
    orig = AQ._resolves_to_unit
    try:
        AQ._resolves_to_unit = lambda state, eid: True
        assert AQ.has_heal_blockers(st, 10) is True, "1320 vivant -> bloqueur"
        assert AQ.has_heal_blockers(st, 11) is False, "un effet quelconque n'est PAS un bloqueur"
        assert AQ.has_heal_blockers(st, 12) is False, "aucun effet -> pas de bloqueur"
        fury.consumed = True
        assert AQ.has_heal_blockers(st, 10) is False, (
            "`consumed` = retire d'`EffectsOwnedComponent` -> `RevertInternal` a joue")
        # `expired` est DERIVE (`remaining_turns <= 0`), pas assignable -- on pose la cause.
        fury.consumed, fury.remaining_turns = False, 0
        assert fury.expired is True
        assert AQ.has_heal_blockers(st, 10) is False, "`expired` = timer a 0 -> retire aussi"
    finally:
        AQ._resolves_to_unit = orig
