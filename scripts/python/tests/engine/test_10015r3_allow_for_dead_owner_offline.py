"""#10015-r3 -- `fire_on_death` CHANGE le resultat observable du dispatch, classe par classe.

Le cliquet `probe_10015_allow_for_dead_owner.py` confronte la VALEUR de l'attribut a celle que le
build declare (`ITriggeredAbility` slot 8 = `get_AllowForDeadOwner`). C'est necessaire et
INSUFFISANT : il compare deux tables. Rien n'y etablit que l'attribut MORD, c'est-a-dire qu'il
decide vraiment du passage par
`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger`, dont le port est le bloc de
`engine/runner/operations/triggers/dispatch/core.py::evaluate_trigger_operation` :

    if (!ability.get_AllowForDeadOwner()) {                    // ITriggeredAbility slot 8
        if (IsUnit(owner) && !IsAlive(owner))       return 0; }

Ce fichier le fait MORDRE. Le regime est ETROIT et il faut le monter exactement : owner PRESENT
dans l'ECS, portant un `UnitComponent`, et NON VIVANT. Un owner absent tombe sur le `continue` du
porteur introuvable AVANT toute lecture de l'attribut -- un montage naif ne prouverait donc rien.

L'OBSERVABLE est l'appel de `matches`, que `evaluate_trigger_operation` fait JUSTE APRES le gate :
il est atteint <=> le gate a laisse passer. On ne lit pas l'attribut, on regarde qui passe.

⚠ **LES DEUX BRAS SONT OBLIGATOIRES.** Sans le bras NEGATIF (une classe a `fire_on_death` FAUX doit
etre ECARTEE), un `evaluate_trigger_operation` casse en << laisse tout passer >> rendrait le bras
positif vert par vacuite -- et c'est exactement la panne que ce cas documente : permissive, sans
erreur, invisible en self-play.

⚠ **LE BRAS NEGATIF SE DERIVE, IL NE SE CITE PAS.** Nommer une classe temoin la perime au premier
port qui lui donne `fire_on_death = True` (il y en a eu CINQ dans le commit qui ouvre ce fichier).
Le temoin est donc CHOISI dans le registre a l'execution, et son non-vide est assertionne.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
RACINE = HERE.parent.parent.parent                                    # scripts/python
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from engine.runner.components import UnitComponent                    # noqa: E402
from engine.runner.operations.triggers import base as TB              # noqa: E402
from engine.runner.operations.triggers.dispatch import core as CORE   # noqa: E402


#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`, garde #486-r15). Pris
#: LARGE a dessein : un declencheur trop etroit est un FAUX VERT -- le fichier ne se rejouerait
#: pas sous `--since` quand ce qu'il garde a bouge.
DECLENCHEUR = {
    "chemins": (
        # LE GATE LUI-MEME (`dispatch/core.py`, bloc `CanGetAbilityTrigger`) ET LE REGISTRE
        # (`dispatch/registry.py`, ou ce fichier resout ses neuf classes PAR LEUR NOM -- une entree
        # retiree doit rougir ici avec << l'etalon est PERIME >>, pas passer inapercue).
        # ⚠ LE GLOB PORTE SUR TOUT `dispatch/`, ET CE N'EST PAS DU CONFORT : nommer les deux
        # fichiers un par un a laisse `dispatch/phase.py` dehors, que `probe_486r15` a trouve en
        # fermant les imports. Un declencheur ecrit A LA MAIN sous-estime sa propre fermeture.
        "scripts/python/engine/runner/operations/triggers/dispatch/*.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # LES PORTEUSES de l'attribut. Le glob couvre les neuf de l'etalon ET toute classe qui
        # rejoindrait le bras negatif -- ce dernier CHOISIT son temoin dans le registre, donc son
        # verdict depend de l'ensemble du repertoire, pas d'un fichier nomme.
        "scripts/python/engine/runner/operations/triggers/loki/*.py",
        "scripts/python/engine/runner/operations/triggers/*.py",
        # LE SUBSTRAT du montage (owner PRESENT, portant un `UnitComponent`, NON VIVANT).
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/state.py",
        # LE CLIQUET FRERE : ce fichier lui emprunte `classes_du_registre`, et surtout les deux se
        # CONTREDISENT si l'un derive -- l'un re-derive la valeur du build, l'autre fige ce que la
        # tranche a mesure.
        "scripts/python/probe_10015_allow_for_dead_owner.py",
        # L'ENTREE VERSIONNEE dont l'etalon ci-dessous est la transcription. Si le build change de
        # verdict sur une de ces neuf classes, ce fichier DOIT etre rejoue.
        "data/symbols/*/metadata/allow_for_dead_owner.tsv",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le gate d'owner, le registre qui nomme les neuf classes de l'etalon, les modules "
              "qui portent `fire_on_death`, le substrat ECS du montage, le cliquet frere et "
              "l'entree versionnee du build. Le bras negatif DERIVE son temoin du registre "
              "entier, d'ou les deux globs plutot qu'une liste de fichiers -- une classe qui "
              "gagne ou perd l'attribut change le temoin choisi.",
}


#: Les CINQ classes portees par #10015-r3, plus les quatre deja alignees avant lui. Chacune est
#: nommee avec le symbole natif dont la valeur a ete LUE (`metadata/allow_for_dead_owner.tsv`,
#: corps `b0 01 c3` = `mov al,1 ; ret`). La liste est un ETALON : elle fige ce que la tranche a
#: mesure, la ou `probe_10015` re-derive. Les deux se contredisent si l'un derive.
PORTEES_A_VRAI = {
    # -- portees par #10015-r3 -------------------------------------------------------------
    "ControlEdictAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility",
    "CursedPlagueBellAttackAbility":
        "IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility",
    "LifewardsAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAbility",
    "LightImUpAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility",
    "LordOfTempestsAddIceAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility",
    # -- deja alignees avant, gardees ici pour que le bras positif ne repose pas sur la seule
    #    tranche qui l'a ecrit --------------------------------------------------------------
    "AmbushSummonAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility",
    "SynapticLinchpinAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility",
    "FinalJusticeAbility":
        "IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility",
    "SplitAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility",
}

OWNER_ID = 424242


def _registre():
    abilites, _effets = __import__(
        "probe_10015_allow_for_dead_owner").classes_du_registre()
    return abilites


def _gate_laisse_passer(monkeypatch, cls) -> bool:
    """`matches` de `cls` est-il ATTEINT quand l'owner est PRESENT et MORT ?

    On substitue le collecteur : `collect_triggered_abilities` n'inscrit que ce qui porte un
    `StatsComponent`, et fabriquer un porteur complet ferait dependre le controle du substrat de
    stats plutot que du GATE qu'il teste. La fonction sous test reste la VRAIE
    (`evaluate_trigger_operation`), avec son vrai bloc de gate."""
    from engine.runner.state import State

    st = State()
    ent = st.add_entity(OWNER_ID)
    ent.add_component(UnitComponent(visual_id=None, alive=False))

    inst = cls(OWNER_ID)
    atteint: list[bool] = []

    def _mouchard(self, state, ev):                                   # noqa: ANN001
        atteint.append(True)
        return False                                                  # on n'execute aucun behaviour

    monkeypatch.setattr(type(inst), "matches", _mouchard, raising=False)
    monkeypatch.setattr(CORE, "collect_triggered_abilities", lambda s: [inst])
    monkeypatch.setattr(CORE, "collect_global_triggers", lambda: [])
    monkeypatch.setattr(CORE, "collect_effect_triggers", lambda s: [])

    ev = TB.TriggerEvent(inst.event_id, 1, 2, ranged=False, profile=None)
    CORE.evaluate_trigger_operation(st, ev)
    return bool(atteint)


@pytest.mark.parametrize("nom", sorted(PORTEES_A_VRAI))
def test_un_owner_mort_ne_bloque_pas_les_classes_a_allow_for_dead_owner(monkeypatch, nom):
    """BRAS POSITIF -- chacune de ces classes DOIT franchir le gate avec un owner mort."""
    abilites = _registre()
    cls = abilites.get(nom)
    assert cls is not None, (
        "%s a disparu du registre de triggers -- l'etalon de #10015-r3 est PERIME, "
        "il faut le relire au decompile, pas le retirer" % nom)
    assert getattr(cls, "fire_on_death", False) is True, (
        "%s doit porter `fire_on_death = True` : le build declare VRAI sur %s "
        "(`ITriggeredAbility` slot 8 = `get_AllowForDeadOwner`, corps `b0 01 c3` LU dans "
        "`metadata/allow_for_dead_owner.tsv`)" % (nom, PORTEES_A_VRAI[nom]))
    assert _gate_laisse_passer(monkeypatch, cls) is True, (
        "%s : `matches` n'a PAS ete atteint avec un owner PRESENT et MORT -- le gate d'owner de "
        "`evaluate_trigger_operation` l'a ecartee alors que le natif la laisse passer" % nom)


def test_le_gate_ecarte_bien_une_classe_a_fire_on_death_faux(monkeypatch):
    """BRAS NEGATIF -- CONTRE-EPREUVE. Sans lui, un gate casse en << tout passe >> rendrait le
    bras positif vert par vacuite. Le temoin est DERIVE du registre, jamais cite : le nommer le
    perimerait au premier port qui lui donnerait `fire_on_death = True`."""
    abilites = _registre()
    temoins = sorted(n for n, c in abilites.items()
                     if not getattr(c, "fire_on_death", False)
                     and not getattr(c, "owner_is_global", False)
                     and not getattr(c, "owner_is_tile", False))
    #: NON-VIDE ASSERTIONNE : un ensemble vide ferait passer ce test sans rien evaluer.
    assert temoins, ("aucune classe ABILITY du registre n'a `fire_on_death` FAUX -- la "
                     "contre-epreuve serait VIDE, donc vraie sans rien prouver")
    nom = temoins[0]
    assert _gate_laisse_passer(monkeypatch, abilites[nom]) is False, (
        "%s porte `fire_on_death` FAUX et son `matches` a pourtant ete atteint avec un owner MORT :"
        " le gate d'owner de `evaluate_trigger_operation` ne mord plus, et le bras positif de ce "
        "fichier est alors vert par VACUITE" % nom)
