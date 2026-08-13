"""#287-r4 -- GARDE offline : le gate de ciblage recoit une INSTANCE, jamais une CLASSE.

Le probe `probe_287r4_targeting_needs_instance.py` MESURE ; ce fichier GARDE. Aucun runner, aucune
session Frida : le defaut est STRUCTUREL (un typage), il se reproduit sur un etat de deux entites
nues.

CE QUE CE FICHIER GARDE :

1. AUCUNE EXCEPTION -- `operations/turnflow._has_valid_targets` ne leve pour aucun des
   `ActiveAbilityType` dont le masque EFFECTIF porte `TargetingRule.TargetMatchesDynamicRule`.
   Mesure du 2026-08-06 sur l'arbre d'avant correctif : 65 ids, 65 exceptions -- 47 `TypeError`
   (voie « classe du registre » : methode NON LIEE, `state` se liait a `self`) et 18
   `AttributeError` (voie « ability non portee » : le type anonyme `_UnportedTargeting` n'avait pas
   du tout la methode).

2. LE PORTEUR -- l'objet reellement passe a `get_invalid_target_reason` est une INSTANCE dont le
   type est une classe NOMMEE de son module, et sa `get_dynamic_invalid_target_reason` est une
   methode LIEE. Cet etage-la est EXHAUSTIF : il intercepte la cascade, donc il ne depend pas de la
   profondeur que l'etat minimal permet d'atteindre.

3. LA MECANIQUE EST BIEN CONSULTEE (temoin non degenere) -- une surcharge qui REFUSE fait basculer
   le verdict de `True` a `False`, et elle recoit `(state, caster_id, target_id)`. Sans cet etage,
   les etages 1-2 seraient satisfaits par un `try/except` -- ou par le RETRAIT pur et simple de
   l'appel a la regle dynamique, ce qui supprimerait la mecanique au lieu de la reparer.

POURQUOI CETTE MECANIQUE EXISTE (la RE qui decide le correctif). Relue a l'octet sur le build
courant, la surcharge **7 arguments** de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
-- celle qu'appelle `IdunBattle.Core.Services.TargetingQuery$$GetValidTargets`, et que le port nomme
`apply_self_cast_switch=False` -- INVOQUE le delegue `options+0x38` sous le bit
`TargetMatchesDynamicRule`, entre `TargetIsNotAdjacentToEnemy` et `TargetIsCasterOrEnemy`, et SANS
garde de nullite (un delegue nul y leve). « Filtre statique pur » ne qualifiait donc que l'absence
de l'aiguillage self-cast et du volet caster -- lesquels vivent dans les surcharges 5 arguments, en
amont. Le port avait un bug de TYPAGE, pas de CADRAGE : la reponse est d'instancier, pas de retirer
l'evaluation.

ETAGE MUTANTS. Chaque invariant est re-joue contre une version DELIBEREMENT FAUSSE du site, et l'on
EXIGE que le critere rougisse. Une garde qu'aucun mutant ne fait rougir est INERTE.

ASCII only (console cp1252).
"""
from __future__ import annotations

import inspect
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import engine.runner.operations.turnflow as TF                                     # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                  # noqa: E402
from engine.runner.abilities.base import ActiveAbility                             # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                        # noqa: E402
from engine.runner.abilities.targeting import (                                    # noqa: E402
    TARGETING_OPTIONS_UNPORTED, TargetingOptions, UnportedAbilityTargeting,
    targeting_options_for,
)
from engine.runner.abilities.targeting_rule import TargetingRule as TR             # noqa: E402
from engine.runner.state import State                                              # noqa: E402

BIT = int(TR.TargetMatchesDynamicRule)


# ------------------------------------------------------------------------------------------------
# Substrat
# ------------------------------------------------------------------------------------------------

def _etat_minimal() -> State:
    """Deux entites NUES : la cascade y degrade en permissif a chaque regle qu'elle ne sait pas
    mesurer, donc elle DESCEND jusqu'au bit dynamique. Le regime le plus court qui atteigne le
    site."""
    st = State()
    st.add_entity(1)
    st.add_entity(2)
    return st


def _ids_portant_le_bit() -> list:
    """Les ids dont le masque EFFECTIF porte le bit -- lu au FOYER UNIQUE `targeting_options_for`.

    Ce n'est PAS « les classes qui surchargent la regle dynamique » : le bit se lit sur le MASQUE,
    et c'est lui seul qui fait entrer la cascade dans la branche. Mesure du 2026-08-06 : sur les 65
    ids concernes, plusieurs (dont `MultiThreatEliminator`, `ArmoriumCherub`, `SkyStrike`) NE
    surchargent pas -- ils levaient sur le defaut herite d'`ActiveAbility`. Un recensement par
    surcharge en aurait manque la majeure partie."""
    return [int(a) for a in sorted(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED))
            if (o := targeting_options_for(a)) is not None and o.has(TR.TargetMatchesDynamicRule)]


def _nom(aid: int) -> str:
    try:
        return ActiveAbilityType(int(aid)).name
    except ValueError:
        return "<hors ActiveAbilityType>"


class sans_volet_caster:
    """Neutralise le VOLET CASTER de `_has_valid_targets` le temps d'une mesure.

    POURQUOI, ET POURQUOI CE N'EST PAS UNE TRICHE. Sur l'etat minimal le caster n'a AUCUNE tuile,
    donc `get_invalid_caster_reason` rend legitimement `AllowNullCasterTile` (la clause tuile-nulle,
    portee par #366-r1) pour 39 des 47 ids a classe portee : `_has_valid_targets` sortirait AVANT la
    cascade, et les etages 1-2 -- qui portent sur le PORTEUR -- deviendraient vrais par VACUITE.
    On isole donc l'etage mesure ; le volet caster a son PROPRE etage, avec un substrat ou il
    discrimine.

    Sur un arbre ou `turnflow` n'importe pas ce nom (l'etat d'avant correctif), le remplacement est
    un NO-OP et la restauration retire l'attribut : la mesure reste jouable des deux cotes."""

    def __enter__(self):
        self._avait = hasattr(TF, "get_invalid_caster_reason")
        self._origine = getattr(TF, "get_invalid_caster_reason", None)
        TF.get_invalid_caster_reason = lambda state, caster_id, ability: 0
        return self

    def __exit__(self, *exc):
        if self._avait:
            TF.get_invalid_caster_reason = self._origine
        else:
            del TF.get_invalid_caster_reason
        return False


def _porteur_de(aid: int, fabrique=None):
    """L'objet REELLEMENT passe a la cascade pour `aid`.

    On substitue `get_invalid_target_reason` DANS `turnflow` (le nom qu'il a importe) par un espion
    qui capture et rend 0 : la mesure est independante de la profondeur atteinte. `fabrique` permet
    de jouer un MUTANT du site a la place de `_has_valid_targets`."""
    captures = []

    def espion(state, caster_id, target_id, ability, **kwargs):
        captures.append(ability)
        return 0

    origine = TF.get_invalid_target_reason
    TF.get_invalid_target_reason = espion
    try:
        with sans_volet_caster():
            (fabrique or TF._has_valid_targets)(_etat_minimal(), 1, aid)
    finally:
        TF.get_invalid_target_reason = origine
    return captures[0] if captures else None


def _est_instance_de_classe_nommee(obj) -> bool:
    """DEUX refus, tous deux observes sur l'arbre d'avant correctif : le porteur EST une classe
    (jamais instanciee), ou son type est fabrique au site (`type("_X", (), {...})` dans un corps de
    fonction n'est reference par aucun attribut de son module)."""
    if isinstance(obj, type):
        return False
    t = type(obj)
    module = sys.modules.get(t.__module__)
    return module is not None and getattr(module, t.__name__, None) is t


def _regle_dynamique_est_liee(obj) -> bool:
    attr = getattr(obj, "get_dynamic_invalid_target_reason", None)
    return attr is not None and inspect.ismethod(attr)


# ------------------------------------------------------------------------------------------------
# Etage 0 -- le recensement, et son propre NON-VIDE
# ------------------------------------------------------------------------------------------------

def ids_non_portes_du_bit() -> list:
    """Les ids posant le bit que la voie NON PORTEE sert REELLEMENT (porteur =
    `UnportedAbilityTargeting`). VIDE aujourd'hui -- et c'est une MESURE, pas un oubli (#1015)."""
    classes = {a for a in _ids_portant_le_bit()
               if getattr(ABILITY_CLASSES.get(a), "TARGETING_OPTIONS", None) is not None}
    return [a for a in _ids_portant_le_bit() if a not in classes]


def porteurs_a_confronter() -> list:
    """Les porteurs que les etages 1-2 doivent traverser : ceux de PRODUCTION, plus un porteur
    TEMOIN pour toute voie qu'aucun id n'emprunte plus (#1015).

    C'EST LA REPARATION DU TROISIEME ROUGE, ET C'EST LA MEME QUE POUR LES DEUX AUTRES. L'etage 0
    exigeait que la voie non portee soit PEUPLEE ; elle ne l'est plus, parce que les 80 ids qui
    posent `TargetMatchesDynamicRule` ont TOUS acquis une classe portee avec masque. Exiger un
    peuplement, c'est faire dependre une garde de la cadence de portage -- elle expire alors par le
    travail accompli, en silence. Ce qui doit rester vrai est que les DEUX FACES du defaut de
    #287-r4 restent EXERCEES : la face `TypeError` (porteur = une CLASSE au lieu d'une instance) et
    la face `AttributeError` (porteur sans `get_dynamic_invalid_target_reason`). Un porteur temoin
    les exerce sans rien devoir a la population."""
    out = [(aid, _porteur_de(aid)) for aid in _ids_portant_le_bit()]
    if not ids_non_portes_du_bit():
        # Aucun id ne passe plus par la voie non portee : on la confronte quand meme, sur le porteur
        # que le site FABRIQUERAIT. Meme construction que `turnflow._has_valid_targets`.
        temoin = int(ActiveAbilityType.PsychicMaelstrom)
        out.append((temoin, UnportedAbilityTargeting(temoin, targeting_options_for(temoin))))
    return out


def test_le_recensement_du_bit_dynamique_n_est_pas_vide():
    """Un recensement vide rendrait TOUS les etages suivants vrais par vacuite -- un vert qui ment.
    On assertionne donc son non-vide, et le fait que les DEUX voies restent EXERCEES.

    ⚠ « EXERCEES », ET NON PLUS « PEUPLEES » (#1015). Cette assertion exigeait
    `assert non_portes` -- que des ids empruntent encore la voie non portee. Mesure du 2026-08-13 :
    il n'y en a plus AUCUN sur les 80 qui posent le bit, tous ayant acquis une classe portee. La
    premisse etait devenue structurellement infaisable, et `master` en restait rouge. Le peuplement
    d'une voie suit la cadence de portage ; ce qui se garde est que les deux FACES du defaut
    d'origine restent traversees, ce dont `porteurs_a_confronter()` se charge par un temoin."""
    ids = _ids_portant_le_bit()
    assert ids, "aucun id ne porte TargetMatchesDynamicRule -- le recensement ne visite rien"
    classes = [a for a in ids
               if getattr(ABILITY_CLASSES.get(a), "TARGETING_OPTIONS", None) is not None]
    assert classes, "voie 'classe du registre' VIDE -- la face TypeError n'est plus couverte"
    # La face AttributeError est exercee soit par la production, soit par le temoin -- jamais par
    # personne. On le verifie sur les porteurs REELLEMENT confrontes, pas sur une population.
    types = {type(ab).__name__ for _a, ab in porteurs_a_confronter() if ab is not None}
    assert "UnportedAbilityTargeting" in types, (
        "la face AttributeError n'est plus couverte : aucun porteur confronte n'est un "
        "`UnportedAbilityTargeting`, ni en production ni par temoin. Types vus : %r" % sorted(types))


# ------------------------------------------------------------------------------------------------
# Etage 1 -- aucune exception
# ------------------------------------------------------------------------------------------------

def test_has_valid_targets_ne_leve_pour_aucun_porteur_du_bit():
    """LE ROUGE DU JOUR. Avant correctif : 65 ids, 65 exceptions (47 TypeError + 18 AttributeError).
    `_has_valid_targets` est le predicat de `HasActionAvailable`, donc du flag
    `UnitFlag.NoActionAvailable` -- une exception y remonte jusqu'au tour."""
    fautes = {}
    st = _etat_minimal()
    with sans_volet_caster():          # sinon 39/47 sortent AVANT la cascade -> vert par vacuite
        for aid in _ids_portant_le_bit():
            try:
                TF._has_valid_targets(st, 1, aid)
            except Exception as exc:                              # noqa: BLE001 -- c'est la mesure
                fautes[aid] = "%s: %s" % (type(exc).__name__, exc)
    assert not fautes, "%d id(s) font lever le gate de ciblage : %s" % (
        len(fautes), [(a, _nom(a), fautes[a]) for a in sorted(fautes)[:5]])


# ------------------------------------------------------------------------------------------------
# Etage 2 -- le porteur est une INSTANCE d'une classe NOMMEE, methode LIEE
# ------------------------------------------------------------------------------------------------

def test_le_porteur_passe_a_la_cascade_est_une_instance_a_regle_liee():
    """EXHAUSTIF sur les 65 : l'espion court-circuite la cascade, donc aucun id n'echappe a la
    mesure parce que l'etat minimal l'aurait fait sortir plus tot."""
    mauvais = []
    # `porteurs_a_confronter` et non `_ids_portant_le_bit` (#1015) : la voie non portee n'a plus
    # aucun id en production, et la balayer seule laissait la face `AttributeError` non exercee.
    for aid, ab in porteurs_a_confronter():
        if ab is None:
            mauvais.append((aid, _nom(aid), "aucun porteur construit"))
        elif not _est_instance_de_classe_nommee(ab):
            mauvais.append((aid, _nom(aid), "pas une instance de classe nommee: %r" % (ab,)))
        elif not _regle_dynamique_est_liee(ab):
            mauvais.append((aid, _nom(aid), "regle dynamique non liee sur %s" % type(ab).__name__))
    assert not mauvais, "%d porteur(s) fautif(s) : %s" % (len(mauvais), mauvais[:5])


# ------------------------------------------------------------------------------------------------
# Etage 3 -- la regle dynamique est CONSULTEE (temoin non degenere)
# ------------------------------------------------------------------------------------------------

def _paire_de_temoins():
    """Deux classes de meme masque (le bit SEUL), l'une permissive, l'autre qui REFUSE.

    Le masque ne porte QUE `TargetMatchesDynamicRule` : aucune autre regle ne peut donc expliquer un
    refus, et l'ecart entre les deux verdicts ne peut venir QUE de la regle dynamique."""
    recu = []

    class TemoinPermissif(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=BIT)

    class TemoinRefus(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=BIT)

        def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
            recu.append((state, caster_id, target_id))
            return BIT

    return TemoinPermissif, TemoinRefus, recu


def _joue_avec(klass, aid=None, fabrique=None, volet_caster=False):
    aid = aid or (max(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED)) + 1)
    ABILITY_CLASSES[aid] = klass
    try:
        if volet_caster:
            return (fabrique or TF._has_valid_targets)(_etat_minimal(), 1, aid)
        with sans_volet_caster():
            return (fabrique or TF._has_valid_targets)(_etat_minimal(), 1, aid)
    finally:
        del ABILITY_CLASSES[aid]


def test_la_regle_dynamique_de_la_sous_classe_est_effectivement_consultee():
    """LE TEMOIN. Sans lui, les etages 1-2 seraient verts sur un code qui aurait simplement RETIRE
    l'evaluation de la regle dynamique -- or le natif, lui, l'evalue (surcharge 7 arguments,
    `options+0x38`). On exige la BASCULE de verdict, pas seulement l'absence d'erreur."""
    permissif, refus, recu = _paire_de_temoins()
    assert _joue_avec(permissif) is True, (
        "regime DEGENERE : le temoin permissif ne trouve deja aucune cible, "
        "la bascule ci-dessous ne prouverait rien")
    assert _joue_avec(refus) is False, (
        "la surcharge REFUSE toute cible et pourtant le gate en trouve une : "
        "la regle dynamique n'est PAS consultee")
    assert recu, "la surcharge n'a jamais ete appelee"
    state, caster_id, target_id = recu[0]
    assert isinstance(state, State), "1er argument attendu = l'etat, recu %r" % (state,)
    assert int(caster_id) == 1, "2e argument attendu = le caster (1), recu %r" % (caster_id,)
    assert target_id is not None, "3e argument attendu = la cible, recu None"


# ------------------------------------------------------------------------------------------------
# Etage 4 -- la voie « ability non portee »
# ------------------------------------------------------------------------------------------------

def test_la_voie_non_portee_porte_une_regle_dynamique_nommee():
    """Masque LU sans classe de behaviour. Le porteur doit etre une classe NOMMEE exposant la
    regle-delegue -- et non un type fabrique au site, qui la laissait absente.

    La methode rend 0 : degradation PERMISSIVE, NOMMEE dans la classe. Le natif, lui, a toujours un
    delegue (`AActiveAbility$$.ctor` l'ecrit) et LEVE s'il est nul ; le port ne peut pas evaluer un
    corps qu'il n'a pas porte, et n'invente donc aucun refus."""
    aid = max(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED)) + 2
    TARGETING_OPTIONS_UNPORTED[aid] = TargetingOptions(rules=BIT)
    try:
        ab = _porteur_de(aid)
        assert ab is not None, "aucun porteur construit pour la voie non portee"
        assert _est_instance_de_classe_nommee(ab), (
            "porteur fabrique au site (%r) -- une classe NOMMEE est requise" % (ab,))
        assert _regle_dynamique_est_liee(ab), (
            "%s n'expose pas de regle dynamique LIEE" % type(ab).__name__)
        assert ab.get_dynamic_invalid_target_reason(_etat_minimal(), 1, 2) == 0, (
            "la degradation de la voie non portee doit etre PERMISSIVE (aucun refus invente)")
        # et le chemin complet ne leve pas
        with sans_volet_caster():
            TF._has_valid_targets(_etat_minimal(), 1, aid)
    finally:
        del TARGETING_OPTIONS_UNPORTED[aid]


# ------------------------------------------------------------------------------------------------
# Etage 5 -- le VOLET CASTER, consulte EN TETE
# ------------------------------------------------------------------------------------------------

def _paire_de_masques_caster():
    """Deux masques a UN BIT d'ecart, donc deux verdicts opposes sur le meme substrat.

    Sur l'etat minimal le caster n'a AUCUNE tuile : la clause tuile-nulle du volet caster
    (`GetInvalidCasterReason`) rend `AllowNullCasterTile` -- SAUF si le masque pose ce bit, qui la
    desarme (`(rules & AllowNullCasterTile) == 0 && (rules & CasterHasNoTile) == 0 &&
    IsNullOrEmpty(casterTiles)`). Le discriminant est donc entierement OFFLINE."""
    rules = BIT

    class CasterRefuse(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=rules)

    class CasterTolere(ActiveAbility):
        TARGETING_OPTIONS = TargetingOptions(rules=rules | int(TR.AllowNullCasterTile))

    return CasterRefuse, CasterTolere


def test_le_volet_caster_est_consulte_avant_toute_enumeration():
    """`TargetingQuery$$GetValidTargets` -- la fonction dont `_has_valid_targets` est le mirror --
    OUVRE par `GetInvalidCasterReason` et rend `ValidTargets.Empty` si le caster est refuse, AVANT
    `GetRange` et avant la boucle. Ses QUATRE surcharges convergent vers ce corps, donc le volet est
    dans le chemin quel que soit l'overload.

    Ce n'est PAS en contradiction avec `apply_self_cast_switch=False` : la surcharge 7 arguments
    n'a pas le volet caster ; c'est son APPELANTE qui le porte. Deux etages distincts.

    MESURE LIVE qui a impose cet etage (C1_02 / seed 28704, `orksWarboss` apres un pas) : natif
    `abilityReason.casterReason = CasterHasNotMoved` et `UnitFlag.NoActionAvailable` POSE ; sans cet
    etage le port trouvait `Waaagh` castable et laissait l'unite jouable a tort."""
    refuse, tolere = _paire_de_masques_caster()
    assert _joue_avec(tolere, volet_caster=True) is True, (
        "regime DEGENERE : meme le masque TOLERANT ne trouve aucune cible, "
        "la bascule ci-dessous ne prouverait rien")
    assert _joue_avec(refuse, volet_caster=True) is False, (
        "le volet caster REFUSE (aucune tuile) et pourtant le gate trouve une cible : "
        "`get_invalid_caster_reason` n'est PAS consulte en tete de `_has_valid_targets`")


# ------------------------------------------------------------------------------------------------
# Etage 5 -- MUTANTS : chaque critere doit MORDRE
# ------------------------------------------------------------------------------------------------

def _mutant_passe_la_classe(state, unit_id, ability_type):
    """MUTANT A -- le site tel qu'il etait sur `master` pour la voie « classe du registre » :
    `ABILITY_CLASSES.get(...)` passe TEL QUEL, sans instanciation."""
    opts = targeting_options_for(int(ability_type))
    if opts is None:
        return None
    ability = ABILITY_CLASSES.get(int(ability_type))
    if ability is None or getattr(ability, "TARGETING_OPTIONS", None) is None:
        ability = type("_UnportedTargeting", (), {"TARGETING_OPTIONS": opts,
                                                  "ABILITY_ID": int(ability_type)})
    for tid in list(state.entities.keys()):
        if TF.get_invalid_target_reason(state, int(unit_id), int(tid), ability,
                                        apply_self_cast_switch=False) == 0:
            return True
    return False


def _mutant_regle_dynamique_retiree(state, unit_id, ability_type):
    """MUTANT B -- le correctif PARESSEUX qu'il fallait ecarter : instancier, mais desarmer le bit
    pour que la cascade n'atteigne jamais la regle dynamique. Les etages 1 et 2 le laissent passer ;
    seul le temoin de l'etage 3 le voit."""
    from dataclasses import replace
    opts = targeting_options_for(int(ability_type))
    if opts is None:
        return None
    klass = ABILITY_CLASSES.get(int(ability_type))
    ability = klass() if klass is not None else None
    if ability is None or getattr(ability, "TARGETING_OPTIONS", None) is None:
        return None
    ability.__class__ = type(type(ability).__name__, (type(ability),),
                             {"TARGETING_OPTIONS": replace(
                                 opts, rules=int(opts.rules) & ~BIT)})
    for tid in list(state.entities.keys()):
        if TF.get_invalid_target_reason(state, int(unit_id), int(tid), ability,
                                        apply_self_cast_switch=False) == 0:
            return True
    return False


def test_mutant_A_le_site_qui_passe_la_classe_fait_rougir_les_etages_1_et_2():
    """Sans ce mutant, les etages 1-2 pourraient etre verts pour une raison etrangere au correctif
    (par exemple si plus aucun id ne portait le bit). Ils doivent MORDRE sur le code d'avant."""
    ids = _ids_portant_le_bit()
    leve = 0
    for aid in ids:
        try:
            _mutant_passe_la_classe(_etat_minimal(), 1, aid)
        except Exception:                                         # noqa: BLE001 -- c'est la mesure
            leve += 1
    assert leve == len(ids), (
        "etage 1 INERTE : le site d'avant correctif ne leve que %d fois sur %d" % (leve, len(ids)))
    # etage 2 : le porteur du mutant n'est jamais une instance a regle liee
    ab = _porteur_de(ids[0], fabrique=_mutant_passe_la_classe)
    assert not _est_instance_de_classe_nommee(ab) or not _regle_dynamique_est_liee(ab), (
        "etage 2 INERTE : il accepte le porteur du site d'avant correctif")


def test_mutant_B_desarmer_le_bit_fait_rougir_le_temoin():
    """Le mutant qui compte le plus. Il ne leve pas, et son porteur est une instance en bonne et due
    forme : les etages 1 et 2 le declarent VERT. C'est le temoin de l'etage 3 -- et lui seul -- qui
    voit que la regle dynamique n'est plus consultee."""
    _, refus, recu = _paire_de_temoins()
    verdict = _joue_avec(refus, fabrique=_mutant_regle_dynamique_retiree)
    assert verdict is not False or not recu, (
        "le mutant B est cense NE PAS consulter la regle dynamique, or il l'a fait")
    assert not recu, "etage 3 INERTE : la surcharge a ete appelee alors que le bit est desarme"
    assert verdict is True, (
        "etage 3 INERTE : le mutant rend %r au lieu de True -- la bascule ne discriminerait rien"
        % (verdict,))


def _mutant_sans_volet_caster(state, unit_id, ability_type):
    """MUTANT D -- le site AVEC l'instanciation mais SANS le volet caster (l'etat intermediaire de
    cette tranche). Les etages 1 a 4 le declarent vert ; seul l'etage 5 le voit."""
    opts = targeting_options_for(int(ability_type))
    if opts is None:
        return None
    klass = ABILITY_CLASSES.get(int(ability_type))
    ability = klass() if klass is not None else None
    if ability is None:
        return None
    for tid in list(state.entities.keys()):
        if TF.get_invalid_target_reason(state, int(unit_id), int(tid), ability,
                                        apply_self_cast_switch=False) == 0:
            return True
    return False


def test_mutant_D_omettre_le_volet_caster_fait_rougir_l_etage_5():
    """Le mutant qui garde l'etage 5. Il instancie correctement -- donc les etages 1 a 4 sont verts
    sur lui -- et se contente d'omettre le volet caster. L'etage 5 doit le voir rendre `True` la ou
    le natif rend un ensemble VIDE."""
    refuse, _ = _paire_de_masques_caster()
    verdict = _joue_avec(refuse, fabrique=_mutant_sans_volet_caster, volet_caster=True)
    assert verdict is True, (
        "etage 5 INERTE : le mutant sans volet caster rend %r au lieu de True -- la bascule ne "
        "discriminerait rien" % (verdict,))


def test_mutant_C_une_regle_dynamique_absente_fait_rougir_l_etage_4():
    """Le porteur « non porte » sans la methode -- exactement le type anonyme d'avant correctif."""
    faux = type("_UnportedTargeting", (), {"TARGETING_OPTIONS": TargetingOptions(rules=BIT),
                                           "ABILITY_ID": 1})
    assert not _est_instance_de_classe_nommee(faux)
    assert not _regle_dynamique_est_liee(faux)
    with pytest.raises(AttributeError):
        faux.get_dynamic_invalid_target_reason(_etat_minimal(), 1, 2)
