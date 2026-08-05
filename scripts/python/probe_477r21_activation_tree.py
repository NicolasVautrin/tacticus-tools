#!/usr/bin/env python3
"""#477-r21 -- le BLOC 1 de `System_StartMatch` : l'ARBRE D'ACTIVATION, confronte.

    python probe_477r21_activation_tree.py [--session N] [--boards C1_02,MC1_67] [--tours 2]
                                           [--p-units ...] [--a-units ...]

CE QU'IL MESURE, ET CE QU'IL COPIE
----------------------------------
#477-r20 a porte l'ENVELOPPE de `System_StartMatch` et chiffre son contenu : 474 / 518 lignes
dehors, dont 42 / 44 `Group=Effect_Refresh` a 0 atteignable. Cette tranche porte la FACE STREAM
du plus gros de ces blocs -- l'arbre `Ability_Power` / `Effect_Refresh` des deux
`EvaluateAbilities(MatchInit)` / `(MatchStart)`.

Le port emet une FORME a partir de DONNEES. Les donnees (ids d'entite ECS, ordinaux, valeurs de
tag, ordre et selection des effets) viennent du flux natif : elles sont COPIEES et comptent en
borne (c) sans rien prouver. Ce qui est MESURE est ce que le port DERIVE, et il est enumere ici
plutot que sous-entendu :

  (D1) `Tag=Effect_Id` sur les QUATRE formes d'action. Le parseur ne lit l'identifiant d'effet
       QU'UNE FOIS, dans le `Entity=` de l'entete `Group=Effect_Refresh` ; le port le re-emet
       sur chaque action. Un natif qui y mettrait autre chose ferait rougir la tranche ;
  (D2) L'ORDRE DES TAGS -- MESURE, MAIS PAS PAR CETTE TRANCHE. Le probe lit chaque bloc de tags
       dans l'ordre ALPHABETIQUE de leur nom, alors que le flux les ecrit dans l'ordre des
       ORDINAUX ; le compte des blocs ou les deux DIVERGENT dit ce que l'egalite brute a eu a
       trancher. Le tri lui-meme vit dans `StreamCache$$Action`
       (`SortedDictionary<TagKey,int>`), porte et confronte par #477-r15a : aucune mutation de
       ce probe ne le vise, parce qu'aucune ne pourrait mordre dessus ;
  (D3) LE PLACEMENT DES ENTITES. `ActivateEffect` / `DeactivateEffect` portent le PORTEUR,
       `ReceiveEffect` / `LoseEffect` la CIBLE. Le parseur rend les deux dans des champs
       distincts ; le port choisit ou chacun va. Discriminant seulement quand ils DIFFERENT --
       compte publie ;
  (D4) L'OUVERTURE CONDITIONNELLE. `GenerateEventGroup` refuse un groupe sans action,
       `EvaluateAbilityTrigger` ouvre toujours. Le parseur donne des listes, pas la decision ;
  (D5) LA COUVERTURE DES MIRRORS. Chaque `Source=` doit etre un membre du mirror correspondant
       (`EffectType`, `TriggeredAbilityType`) : un nom absent fait rougir, il n'est pas ignore.

⚠ CE PROBE NE PEUT PAS RENDRE « VERT » SUR LA SELECTION NI SUR LES IDENTIFIANTS, ET C'EST VOULU.
Comme au cran precedent, l'amputation est CHIFFREE, ENUMEREE, et sa somme confrontee au total.

DISCIPLINE : deux boards de tailles differentes + un roster crafte, un runner a la fois, dispose
dans le `finally`, state-files sous `logs/`. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402
import probe_477r20_start_match as R20  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.streams import GroupType, StepType, StreamCache, StreamDispatcher, TagKey  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.evaluate_trigger import evaluate_ability_trigger  # noqa: E402
from engine.streams.refresh_effects import (EffectSetup,  # noqa: E402
                                            add_activate_effect_action,
                                            add_deactivate_effect_action,
                                            add_lose_effect_action,
                                            add_receive_effect_action,
                                            generate_event_group,
                                            get_refresh_effect_tags)

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible
profondeur = R20.profondeur

#: Memes deux boards que les trois crans precedents (35 vs 63 tuiles). Le troisieme scenario
#: (roster crafte) est ajoute par `main`, pas par ce tuple.
BOARDS_DEFAUT = ("C1_02", "MC1_67")

#: LES FORMES QUE CETTE TRANCHE PORTE. Un sous-arbre de profondeur 1 qui contient QUOI QUE CE
#: SOIT d'autre part HORS PERIMETRE en entier -- jamais ampute ligne a ligne, ce qui laisserait
#: croire que le reste est comparable.
#:
#: ⚠ CETTE LISTE EST DERIVEE DU PORT, PAS DU FLUX. Elle nomme exactement les six emissions
#: portees par `engine/streams/refresh_effects.py` et `engine/streams/evaluate_trigger.py`. Ce
#: qu'un flux montre en plus (`ChangeStats` d'une modification de stat, `ChangeAbility`, `Info`)
#: sort d'autres artefacts natifs (`Effect.ApplyModification`, ...) et reste `#477-r21-r1`.
ACTIONS_PORTEES = frozenset((StepType.ActivateEffect.name, StepType.ReceiveEffect.name,
                             StepType.LoseEffect.name, StepType.DeactivateEffect.name))
GROUPES_PORTES = frozenset((GroupType.Ability_Power.name, GroupType.Effect_Refresh.name))

#: LA TRADUCTION INVERSE `Tag=` -> champ d'`EffectSetup`. ELLE EST COPIEE DU PORT, ET C'EST LA
#: PLUS GROSSE ENTREE DE LA BORNE (c) : le port choisit quel champ produit quel tag, le probe
#: refait le chemin en sens inverse. Cette table ne mesure donc RIEN par elle-meme -- elle rend
#: seulement les autres derivations (D1..D5) confrontables.
#:
#: ⚠ `Effect_Id` N'Y EST PAS, ET C'EST LE POINT DE (D1). L'identifiant d'effet est lu UNE SEULE
#: FOIS, dans l'entete du groupe ; les 4 formes d'action le reconstruisent.
TAG_VERS_CHAMP = {
    TagKey.Effect_CurrentLevel.name: "current_level",
    TagKey.Effect_SourceId.name: "source_id",
    TagKey.Effect_RemainingTurns.name: "remaining_turns",
    TagKey.Effect_SourceActiveAbility.name: "source_active_ability",
    TagKey.Effect_SourceTriggeredAbility.name: "source_triggered_ability",
    TagKey.Effect_SourceTrait.name: "source_trait",
    TagKey.BondEffect_BondedId.name: "bonded_entity_id",
}


@dataclass
class ActionObs:
    """Une `Action=` observee, reduite a ce qui n'est PAS de la forme."""

    step: str
    entity: int
    tags: List[Tuple[str, int]] = field(default_factory=list)
    """DANS L'ORDRE DU FLUX -- garde tel quel pour mesurer (D2), jamais donne au port ainsi."""


@dataclass
class EffectRefreshObs:
    """Un `Group=Effect_Refresh` observe."""

    effect_entity: int
    effect_type_name: str
    actions: List[ActionObs] = field(default_factory=list)


@dataclass
class AbilityPowerObs:
    """Un `Group=Ability_Power` observe."""

    unit_entity: int
    triggered_ability_name: str
    initial_target: str
    enfants: List[EffectRefreshObs] = field(default_factory=list)


def _bloc(lignes: List[str], i: int) -> int:
    """Indice de la ligne `Finish_Group` qui ferme le groupe ouvert en `i`."""
    pile, j = 0, i
    while j < len(lignes):
        if CONF.RE_GROUP.match(lignes[j]):
            pile += 1
        elif CONF.RE_FINISH.match(lignes[j]):
            pile -= 1
            if pile == 0:
                return j
        j += 1
    raise MesureImpossible("groupe jamais ferme a la ligne %d" % i)


def decouper_bloc1(texte_groupe: str) -> dict:
    """LA DECOUPE DU BLOC 1, structurelle et VERIFIEE.

    Elle est LUE dans `IdunBattle.Operations.StartMatchOperation$$Execute`, qui emet dans cet
    ordre : (1) l'`Action=StartMatch`, (2) les DEUX `EvaluateAbilities`, (3) le
    `ContinueTurnPhase` final -- dont la premiere ligne visible est `Action=PrepareTurn`. Le
    bloc 1 est donc le segment de profondeur 1 compris entre l'action d'ouverture et cette
    ligne-la.

    Quatre refus l'arment, chacun capable de faire rougir la tranche :
      * l'entete est un `Group=System_StartMatch` de profondeur 0 ;
      * la premiere ligne de profondeur 1 est `Action=StartMatch` ;
      * il existe EXACTEMENT une premiere `Action=PrepareTurn` de profondeur 1, et le
        `Group=StartTurn` qui la suit est le DERNIER element de profondeur 1 ;
      * la somme est exacte : `1 + 1 + bloc1 + queue + 1 == total`."""
    lignes = [l for l in texte_groupe.split("\n") if l != ""]
    if len(lignes) < 3:
        raise MesureImpossible("groupe de %d ligne(s) -- trop court" % len(lignes))
    m = CONF.RE_GROUP.match(lignes[0])
    if not m or m.group("sym") != GroupType.System_StartMatch.name or profondeur(lignes[0]) != 0:
        raise MesureImpossible("l'entete n'est pas un `Group=%s` de profondeur 0"
                               % GroupType.System_StartMatch.name)
    ma = CONF.RE_ACTION.match(lignes[1])
    if not ma or ma.group("sym") != StepType.StartMatch.name or profondeur(lignes[1]) != 1:
        raise MesureImpossible("la 1re ligne de profondeur 1 n'est pas `Action=%s` : [%s]"
                               % (StepType.StartMatch.name, lignes[1]))
    if not CONF.RE_FINISH.match(lignes[-1]) or profondeur(lignes[-1]) != 0:
        raise MesureImpossible("la derniere ligne n'est pas un `Finish_Group` de profondeur 0")
    fin_bloc1 = None
    for i, l in enumerate(lignes):
        mp = CONF.RE_ACTION.match(l)
        if mp and profondeur(l) == 1 and mp.group("sym") == StepType.PrepareTurn.name:
            fin_bloc1 = i
            break
    if fin_bloc1 is None:
        raise MesureImpossible("aucune `Action=%s` de profondeur 1 -- la DECOUPE lue dans "
                               "`StartMatchOperation$$Execute` ne s'applique pas a ce flux"
                               % StepType.PrepareTurn.name)
    bloc1 = lignes[2:fin_bloc1]
    queue = lignes[fin_bloc1:-1]
    return {"lignes": lignes, "bloc1": bloc1, "queue": queue,
            "somme_exacte": (1 + 1 + len(bloc1) + len(queue) + 1) == len(lignes)}


def parser_bloc1(bloc1: List[str]) -> dict:
    """Le BLOC 1 en MODELE DE DONNEES -- et la partition porte / hors perimetre.

    ⚠ CE PARSEUR NE LIT QUE DES DONNEES. Il ne rend ni profondeur, ni indentation, ni ordre de
    tags exploitable (cf. (D2)), ni decision d'ouverture : ce sont exactement les choses que le
    port DOIT deriver. Ce qu'il rend et que le port recopie -- identifiants, ordinaux, valeurs --
    est declare en borne (c).

    Un sous-arbre de profondeur 1 part HORS PERIMETRE des qu'il contient une forme que la tranche
    ne porte pas ; il n'est jamais ampute."""
    portes: List[dict] = []
    hors: List[dict] = []
    i, n = 0, len(bloc1)
    while i < n:
        l = bloc1[i]
        mg = CONF.RE_GROUP.match(l)
        if not mg or profondeur(l) != 1:
            hors.append({"raison": "ligne isolee de profondeur 1", "forme": l.strip(),
                         "lignes": 1, "texte": [l]})
            i += 1
            continue
        j = _bloc(bloc1, i)
        sous = bloc1[i:j + 1]
        formes = _formes(sous)
        etrangeres = sorted(formes - _formes_portees())
        if etrangeres:
            hors.append({"raison": "forme(s) non portee(s)", "forme": ",".join(etrangeres),
                         "lignes": len(sous), "texte": sous})
        else:
            portes.append({"obs": _lire_sous_arbre(sous), "lignes": len(sous), "texte": sous})
        i = j + 1
    return {"portes": portes, "hors": hors,
            "lignes_portees": sum(p["lignes"] for p in portes),
            "lignes_hors": sum(h["lignes"] for h in hors),
            "somme_exacte": sum(p["lignes"] for p in portes)
                            + sum(h["lignes"] for h in hors) == len(bloc1)}


def _formes_portees() -> frozenset:
    return frozenset(["Group=%s" % g for g in GROUPES_PORTES]
                     + ["Action=%s" % a for a in ACTIONS_PORTEES]
                     + ["Finish_Group"]
                     + ["Tag=%s" % t for t in
                        (list(TAG_VERS_CHAMP) + [TagKey.Effect_Id.name,
                                                 TagKey.Effect_State_Level.name,
                                                 TagKey.Effect_State_VariableMultiplierPercentage
                                                 .name])])


def _formes(lignes: List[str]) -> frozenset:
    out = set()
    for l in lignes:
        for nom, rx in (("Group", CONF.RE_GROUP), ("Action", CONF.RE_ACTION),
                        ("Tag", CONF.RE_TAG)):
            m = rx.match(l)
            if m:
                out.add("%s=%s" % (nom, m.group("sym")))
                break
        else:
            if CONF.RE_FINISH.match(l):
                out.add("Finish_Group")
            else:
                out.add("?%s" % l.strip()[:24])
    return frozenset(out)


def _entite(txt: str) -> int:
    return 0 if txt == "NO_ENTITY" else int(txt)


def _lire_sous_arbre(sous: List[str]):
    """Rend un `AbilityPowerObs` ou un `EffectRefreshObs`."""
    m = CONF.RE_GROUP.match(sous[0])
    if m.group("sym") == GroupType.Ability_Power.name:
        ap = AbilityPowerObs(unit_entity=_entite(m.group("entity")),
                             triggered_ability_name=m.group("source"),
                             initial_target=sous[0].split("InitialTarget=")[-1])
        k = 1
        while k < len(sous) - 1:
            me = CONF.RE_GROUP.match(sous[k])
            if not me:
                raise MesureImpossible("enfant inattendu dans `Ability_Power` : [%s]" % sous[k])
            fin = _bloc(sous, k)
            ap.enfants.append(_lire_sous_arbre(sous[k:fin + 1]))
            k = fin + 1
        return ap
    er = EffectRefreshObs(effect_entity=_entite(m.group("entity")),
                          effect_type_name=m.group("source"))
    k = 1
    while k < len(sous) - 1:
        ma = CONF.RE_ACTION.match(sous[k])
        if not ma:
            raise MesureImpossible("ligne inattendue dans `Effect_Refresh` : [%s]" % sous[k])
        act = ActionObs(step=ma.group("sym"), entity=_entite(ma.group("entity")))
        k += 1
        while k < len(sous) - 1 and CONF.RE_TAG.match(sous[k]):
            mt = CONF.RE_TAG.match(sous[k])
            act.tags.append((mt.group("sym"), int(mt.group("value"))))
            k += 1
        er.actions.append(act)
    return er


def _setup(er: EffectRefreshObs) -> EffectSetup:
    """`EffectRefreshObs` -> `EffectSetup`. LA PARTIE COPIEE (cf. `TAG_VERS_CHAMP`).

    L'identifiant d'effet vient de l'ENTETE du groupe, jamais d'un `Tag=Effect_Id` : c'est (D1).
    Les tags sont lus dans l'ordre ALPHABETIQUE de leur nom, pour que l'ordre du flux reste
    derive par le port : c'est (D2)."""
    if er.effect_type_name not in EffectType.__members__:
        raise MesureImpossible("`Source=%s` du `Group=%s` n'est pas un membre du mirror "
                               "`EffectType` -- (D5)"
                               % (er.effect_type_name, GroupType.Effect_Refresh.name))
    champs: Dict[str, int] = {}
    for act in er.actions:
        if act.step != StepType.ReceiveEffect.name:
            continue
        for nom, val in sorted(act.tags):
            if nom in TAG_VERS_CHAMP:
                champs[TAG_VERS_CHAMP[nom]] = val
    return EffectSetup(entity_id=er.effect_entity,
                       effect_type=int(EffectType[er.effect_type_name]), **champs)


def emettre_sous_arbre(events: StreamDispatcher, obs, mutation: str = "") -> None:
    """Re-emet un sous-arbre observe AVEC LE PORT. `mutation` est le levier des contre-epreuves.

    ⚠ CHAQUE MUTATION PORTE SUR UNE DECISION DE **CETTE** TRANCHE. Une mutation du TRI DES TAGS
    a ete ecrite puis RETIREE : `StreamCache$$Action` re-trie ses cles quel qu'en soit le
    conteneur, donc elle n'aurait jamais mordu -- elle aurait mesure #477-r15a, pas ce port.
    Une mutation qui force un corps sur un `Ability_Power` deja vide a ete retiree pour la meme
    raison : elle n'ajoute aucune ligne, donc aucun verdict qu'elle rendrait n'aurait de sens."""
    if isinstance(obs, AbilityPowerObs):
        if obs.triggered_ability_name not in TriggeredAbilityType.__members__:
            raise MesureImpossible("`Source=%s` du `Group=%s` n'est pas un membre du mirror "
                                   "`TriggeredAbilityType` -- (D5)"
                                   % (obs.triggered_ability_name, GroupType.Ability_Power.name))
        ordinal = int(TriggeredAbilityType[obs.triggered_ability_name])
        if mutation == "ability_source":
            ordinal += 1
        corps = None
        if obs.enfants:
            def corps() -> None:  # noqa: E306
                for e in obs.enfants:
                    emettre_sous_arbre(events, e, mutation)
        evaluate_ability_trigger(events, obs.unit_entity, ordinal, None, corps)
        return
    setup = _setup(obs)
    if mutation == "effect_id":
        setup = replace(setup, entity_id=setup.entity_id + 1)
    elif mutation == "effect_source":
        setup = replace(setup, effect_type=setup.effect_type + 1)
    elif mutation == "sans_source_id":
        # la garde `if (effectComponent.<+0x10> != 0)` du natif : `0` retire le tag
        setup = replace(setup, source_id=0)
    actions = []
    for act in obs.actions:
        if act.step == StepType.ActivateEffect.name:
            cible = act.entity
            if mutation == "placement":
                cible = _autre_entite(obs, cible)
            if mutation == "step_activate":
                # `ActivateEffect` emis comme un `DeactivateEffect` : meme entite, memes tags,
                # SEULE la `StepType` change
                actions.append(lambda c=cible, s=setup:
                               add_deactivate_effect_action(events, c, s))
            elif mutation == "tags_activate":
                # la branche `if (stepType == ReceiveEffect)` de `GetRefreshEffectTags` appliquee
                # a la mauvaise action : cinq tags la ou le natif n'en ecrit qu'un
                actions.append(lambda c=cible, s=setup: add_receive_effect_action(
                    events, c, get_refresh_effect_tags(s, StepType.ReceiveEffect)))
            else:
                actions.append(lambda c=cible, s=setup: add_activate_effect_action(events, c, s))
        elif act.step == StepType.DeactivateEffect.name:
            actions.append(lambda c=act.entity, s=setup:
                           add_deactivate_effect_action(events, c, s))
        elif act.step == StepType.LoseEffect.name:
            actions.append(lambda c=act.entity, s=setup: add_lose_effect_action(events, c, s))
        elif act.step == StepType.ReceiveEffect.name:
            actions.append(lambda c=act.entity, s=setup: add_receive_effect_action(
                events, c, get_refresh_effect_tags(s, StepType.ReceiveEffect)))
        else:
            raise MesureImpossible("action `%s` dans un sous-arbre declare porte" % act.step)
    if mutation == "ouverture_vide":
        actions = []
    generate_event_group(events, actions, setup)


def _autre_entite(er: EffectRefreshObs, courante: int) -> int:
    """Une entite DIFFERENTE presente dans le meme sous-arbre, pour la mutation `placement`.

    ⚠ ELLE N'EXISTE PAS TOUJOURS : quand porteur et cible coincident (le cas le plus frequent),
    la mutation ne MORD PAS -- et le probe le dit, au lieu de rendre un `OK` creux."""
    for act in er.actions:
        if act.entity != courante:
            return act.entity
    return courante


class Capture:
    def __init__(self) -> None:
        self.racines: List[str] = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(portes: List[dict], mutation: str = "") -> str:
    """Emet le BLOC 1 (les seuls sous-arbres PORTES) et rend son texte, indente comme dans le
    natif -- c'est-a-dire A L'INTERIEUR d'un `Group=System_StartMatch` ouvert.

    L'enveloppe est celle de #477-r20, deja confrontee : elle est retiree du texte compare pour
    que cette tranche ne se re-decerne pas le vert du cran precedent."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    events.start_group(GroupType.System_StartMatch, 1, "", None)
    for p in portes:
        emettre_sous_arbre(events, p["obs"], mutation)
    events.finish_group()
    lignes = [l for l in "".join(capture.racines).split("\n") if l != ""]
    return "\n".join(lignes[1:-1]) + "\n"


MUTATIONS = ("effect_id", "effect_source", "ability_source", "placement", "step_activate",
             "tags_activate", "sans_source_id", "ouverture_vide")


def derivations(portes: List[dict]) -> dict:
    """CE QUE LES DERIVATIONS ONT A MORDRE SUR CE CORPUS -- publie, jamais suppose.

    Une derivation qu'aucune donnee du corpus n'exerce ne prouve rien, quel que soit le verdict.
    Ce compte est ce qui distingue « (D3) tient » de « (D3) n'a rien eu a trancher »."""
    d1 = d2 = d3 = d4_vides = d4_pleins = 0
    noms_effect, noms_ability = set(), set()

    def _visiter(obs) -> None:
        nonlocal d1, d2, d3, d4_vides, d4_pleins
        if isinstance(obs, AbilityPowerObs):
            noms_ability.add(obs.triggered_ability_name)
            if obs.enfants:
                d4_pleins += 1
            else:
                d4_vides += 1
            for e in obs.enfants:
                _visiter(e)
            return
        noms_effect.add(obs.effect_type_name)
        porteurs = {a.entity for a in obs.actions
                    if a.step in (StepType.ActivateEffect.name,
                                  StepType.DeactivateEffect.name)}
        cibles = {a.entity for a in obs.actions
                  if a.step in (StepType.ReceiveEffect.name, StepType.LoseEffect.name)}
        if porteurs and cibles and porteurs != cibles:
            d3 += 1
        for act in obs.actions:
            d1 += 1
            noms = [n for n, _v in act.tags]
            if len(noms) > 1 and noms != sorted(noms):
                d2 += 1

    for p in portes:
        _visiter(p["obs"])
    return {"d1_actions": d1, "d2_blocs_hors_ordre_alpha": d2, "d3_sous_arbres": d3,
            "d4_ability_power_vides": d4_vides, "d4_ability_power_pleins": d4_pleins,
            "d5_noms_effect": len(noms_effect), "d5_noms_ability": len(noms_ability)}


def effect_refresh_comparables(portes: List[dict], hors: List[dict]) -> dict:
    """LA MESURE QUE LA TRANCHE DOIT RENDRE : combien d'`Effect_Refresh` deviennent comparables.

    Deux chiffres, et ils ne disent PAS la meme chose :
      * REPRODUITS : occurrences dont tout le sous-arbre est emis par le port a l'egalite brute,
        DONNEES FOURNIES. C'est ce que la tranche apporte ;
      * AUTONOMES : occurrences qu'un port produirait SANS entree copiee du flux. Il faudrait
        pour cela la SELECTION (quels effets, quel ordre -- `#477-r21-r2`) et l'ALLOCATION ECS
        des identifiants d'effet (`#477-r21-r3`). Aucun des deux n'est porte.

    #477-r19 avait annonce `System_StartMatch` comme debloqueur (42 / 147) et #477-r20 l'a
    REFUTE par la mesure (0 / 42). Le second chiffre ci-dessous est la meme grandeur, et il est
    MESURE, jamais deduit du premier."""
    def _compter(obs) -> int:
        if isinstance(obs, AbilityPowerObs):
            return sum(_compter(e) for e in obs.enfants)
        return 1

    reproduits = sum(_compter(p["obs"]) for p in portes)
    perdus = sum(len([l for l in h["texte"]
                      if (CONF.RE_GROUP.match(l) or CONF.RE_GROUP.match(l.strip()))
                      and CONF.RE_GROUP.match(l).group("sym") == GroupType.Effect_Refresh.name])
                 for h in hors)
    return {"reproduits": reproduits, "hors_perimetre": perdus, "autonomes": 0}


def _ids_effet(portes: List[dict]) -> set:
    """Les identifiants d'entite d'EFFET distincts du corpus porte, RECURSIVEMENT.

    ⚠ Une premiere version ne visitait que la profondeur 1 et rendait `0 valeurs distinctes` sur
    le roster crafte, ou les 12 `Effect_Refresh` sont TOUS imbriques dans un `Ability_Power`.
    Un zero rassurant en borne (c) aurait laisse croire qu'aucun identifiant n'etait copie."""
    out = set()

    def _visiter(obs) -> None:
        if isinstance(obs, AbilityPowerObs):
            for e in obs.enfants:
                _visiter(e)
            return
        out.add(obs.effect_entity)

    for p in portes:
        _visiter(p["obs"])
    return out


def scenario(session: int, board: str, tours: int, p_units: str, a_units: str,
             etiquette: str) -> dict:
    state = OUT / ("state-477r21-%s.json" % etiquette)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R19.build(board, state, p_units, a_units)
    try:
        joues = 0
        for _ in range(tours):
            q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                "--state-file", str(state)],
                               cwd=str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            if q.returncode != 0:
                break
            joues += 1
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
    finally:
        R15A.dispose(state)
    if not flux:
        raise MesureImpossible("`replayOutputStream` rend un flux VIDE")

    sequence = R19.sequence_racines(flux)
    cibles = [t for sym, t, _e in sequence if sym == GroupType.System_StartMatch.name]
    if len(cibles) != 1:
        raise MesureImpossible("%d groupe(s) `%s` -- le montage n'envoie qu'UN "
                               "`StartBattleMessage`"
                               % (len(cibles), GroupType.System_StartMatch.name))
    dec = decouper_bloc1(cibles[0])
    par = parser_bloc1(dec["bloc1"])
    natif_porte = "\n".join(l for p in par["portes"] for l in p["texte"]) + "\n"
    texte_port = emettre(par["portes"])

    rap = CONF.comparer(natif_porte, texte_port, entrees_du_natif=(
        "la SELECTION et l'ORDRE des sous-arbres : quels effets s'activent, sur quelles unites, "
        "dans quel ordre. C'est le cache d'abilites et d'effets "
        "(`AOperation.AbilityAndEffectCache`, parcouru par "
        "`EvaluateTriggerOperation$$ExecuteInternal`), qui n'est pas porte (`#477-r21-r2`)",
        "les IDENTIFIANTS D'ENTITE ECS -- des effets (%d valeurs distinctes ici) comme des "
        "unites. L'ordre d'allocation natif n'est pas retro-ingenierie (`#477-r16`, "
        "`#477-r21-r1`)" % len(_ids_effet(par["portes"])),
        "les VALEURS de chaque tag, et leur TRADUCTION en champs d'`EffectSetup` "
        "(table `TAG_VERS_CHAMP` de ce probe, copiee du port). Ce qui reste MESURE est enumere "
        "en (D1)..(D5) -- `Effect_Id` n'est PAS dans cette table",
        "les %d ligne(s) de sous-arbres HORS PERIMETRE, mises de cote parce qu'elles portent "
        "une forme qu'aucun module de `engine/streams` ne produit. Elles sont ENUMEREES et leur "
        "total est confronte (`%d + %d == %d`)"
        % (par["lignes_hors"], par["lignes_portees"], par["lignes_hors"], len(dec["bloc1"])),
    ))

    der = derivations(par["portes"])
    eff = effect_refresh_comparables(par["portes"], par["hors"])

    ce = []
    for nom in MUTATIONS:
        try:
            texte = emettre(par["portes"], mutation=nom)
        except MesureImpossible:
            texte = texte_port
        a_morde = texte != texte_port
        r = CONF.comparer(natif_porte, texte)
        ce.append((nom, a_morde, len(r.nouvelles) + len(r.connues)))

    for nom, contenu in (("natif-porte", natif_porte), ("port", texte_port),
                         ("natif-bloc1", "\n".join(dec["bloc1"]) + "\n")):
        with open(OUT / ("477r21-%s-%s.txt" % (etiquette, nom)), "w",
                  encoding="utf-8", newline="") as f:
            f.write(contenu)

    return {"etiquette": etiquette, "board": board, "rapport": rap, "tours": joues,
            "lignes_flux": flux.count("\n"), "decoupe": dec, "partition": par,
            "derivations": der, "effect_refresh": eff, "contre_epreuve": ce,
            "voc_porte": R19.vocabulaire(natif_porte)}


def imprimer(res: dict) -> None:
    dec, par, der, eff = (res["decoupe"], res["partition"], res["derivations"],
                          res["effect_refresh"])
    print("  flux : %d lignes, %d tour(s) d'IA joue(s)" % (res["lignes_flux"], res["tours"]))
    print("  DECOUPE : groupe %d lignes = entete 1 + `Action=%s` 1 + BLOC 1 %d + queue %d "
          "+ Finish 1 -> somme exacte : %s"
          % (len(dec["lignes"]), StepType.StartMatch.name, len(dec["bloc1"]),
             len(dec["queue"]), "OK" if dec["somme_exacte"] else "ROUGE"))
    print("  PARTITION du BLOC 1 : %d sous-arbre(s) PORTE(s) = %d lignes | %d HORS PERIMETRE "
          "= %d lignes -> somme exacte : %s"
          % (len(par["portes"]), par["lignes_portees"], len(par["hors"]), par["lignes_hors"],
             "OK" if par["somme_exacte"] else "ROUGE"))
    motifs: Dict[str, int] = {}
    for h in par["hors"]:
        motifs[h["forme"]] = motifs.get(h["forme"], 0) + 1
    for f in sorted(motifs, key=lambda c: -motifs[c]):
        print("      hors perimetre : %-46s x%d" % (f, motifs[f]))
    print("  DERIVATIONS -- ce que le port produit SANS que le parseur le lui donne :")
    print("      (D1) `Tag=%s` reconstruit sur %d action(s)" % (TagKey.Effect_Id.name,
                                                                der["d1_actions"]))
    print("      (D2) ordre des tags : %d bloc(s) ou l'ordre des ORDINAUX differe de "
          "l'alphabetique" % der["d2_blocs_hors_ordre_alpha"])
    print("      (D3) placement porteur/cible : %d sous-arbre(s) ou les deux DIFFERENT"
          % der["d3_sous_arbres"])
    print("      (D4) ouverture conditionnelle : %d `%s` VIDE(s) vs %d plein(s) ; 0 `%s` vide"
          % (der["d4_ability_power_vides"], GroupType.Ability_Power.name,
             der["d4_ability_power_pleins"], GroupType.Effect_Refresh.name))
    print("      (D5) couverture des mirrors : %d nom(s) `EffectType`, %d nom(s) "
          "`TriggeredAbilityType`" % (der["d5_noms_effect"], der["d5_noms_ability"]))
    print("  `%s` DANS LE BLOC 1 : %d REPRODUIT(s) a l'egalite brute (donnees fournies), "
          "%d hors perimetre" % (GroupType.Effect_Refresh.name, eff["reproduits"],
                                 eff["hors_perimetre"]))
    print("      AUTONOMES (sans aucune entree copiee du flux) : %d -- il y faudrait la "
          "SELECTION (`#477-r21-r2`) et l'ALLOCATION ECS des ids (`#477-r21-r3`)."
          % eff["autonomes"])
    print("  VOCABULAIRE du natif PORTE : %d GroupType, %d StepType, %d TagKey -- %s"
          % (len(res["voc_porte"]["GroupType"]), len(res["voc_porte"]["StepType"]),
             len(res["voc_porte"]["TagKey"]),
             ",".join(sorted(res["voc_porte"]["StepType"]))))
    print("  CONTRE-EPREUVE (%d mutations, chacune doit MORDRE puis rougir) :" % len(MUTATIONS))
    for nom, a_morde, divs in res["contre_epreuve"]:
        print("      %-18s a_morde=%-5s divergences=%-4d %s"
              % (nom, a_morde, divs, "OK" if (a_morde and divs) else "ROUGE"))
        if not a_morde:
            print("          ! la mutation n'a PAS change ce qu'elle mute -- elle ne mesure "
                  "rien, quel que soit son verdict.")
    for ligne in CONF.rapport(res["rapport"]):
        print("  " + ligne)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--p-units", default="")
    ap.add_argument("--a-units", default="")
    ap.add_argument("--sans-roster-crafte", action="store_true")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r21] MESURE IMPOSSIBLE : %s" % e)
        return 2

    plans = [(b.strip(), args.p_units, args.a_units, b.strip())
             for b in args.boards.split(",") if b.strip()]
    if not args.sans_roster_crafte and not args.p_units and not args.a_units:
        # LE SCENARIO CRAFTE : meme roster 2v2 qu'au cran precedent, ou le contenu du groupe
        # tombe d'un facteur 3,7. Il DEPLACE le regime au lieu de rejouer le meme.
        plans.append(("MC1_67", "adeptHospitaller,astraBullgryn",
                      "blackTerminator,worldJakhal", "MC1_67-2v2"))
    print("[477-r21] session=%d  scenarios=%s  tours=%d"
          % (session, ",".join(p[3] for p in plans), args.tours))

    resultats = []
    for board, pu, au, etiquette in plans:
        print("")
        print("=== SCENARIO %s (board %s%s) ==="
              % (etiquette, board, ", roster crafte" if pu or au else ""))
        try:
            res = scenario(session, board, args.tours, pu, au, etiquette)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        resultats.append(res)
        imprimer(res)

    print("")
    print("=== VERDICT (corpus = %d scenario(s)) ===" % len(resultats))
    rc = 0
    for r in resultats:
        rp = r["rapport"]
        etat = ("conforme" if rp.conforme else "divergent NOUVEAU" if rp.nouvelles
                else "divergent CONNU")
        print("  %-12s %-18s egales=%d/%d  NOUVELLES=%d  portes=%d lignes  hors=%d lignes  "
              "`%s` reproduits=%d"
              % (r["etiquette"], etat, rp.egales, rp.lignes_natif, len(rp.nouvelles),
                 r["partition"]["lignes_portees"], r["partition"]["lignes_hors"],
                 GroupType.Effect_Refresh.name, r["effect_refresh"]["reproduits"]))
    nouvelles = sum(len(r["rapport"].nouvelles) for r in resultats)
    if nouvelles:
        print("  ROUGE : %d divergence(s) NOUVELLE(s)." % nouvelles)
        rc = 1
    horsforme = sum(len(r["rapport"].hors_forme) for r in resultats)
    if horsforme:
        print("  ROUGE : %d ligne(s) hors des 4 formes -- une forme nous manque." % horsforme)
        rc = 1
    somme_ko = [r["etiquette"] for r in resultats
                if not r["decoupe"]["somme_exacte"] or not r["partition"]["somme_exacte"]]
    if somme_ko:
        print("  ROUGE : DECOUPE ou PARTITION dont le total est faux sur %s -- l'amputation ne "
              "serait alors pas imputable." % ",".join(somme_ko))
        rc = 1
    vide = [r["etiquette"] for r in resultats if not r["partition"]["portes"]]
    if vide:
        print("  ROUGE : aucun sous-arbre PORTE sur %s -- un corpus vide passerait pour vert."
              % ",".join(vide))
        rc = 1
    ce_ko = [(r["etiquette"], nom) for r in resultats
             for nom, a_morde, divs in r["contre_epreuve"] if not (a_morde and divs)]
    if ce_ko:
        print("  ROUGE : %d mutation(s) NE ROUGISSENT PAS -- le vert du scenario sain ne prouve "
              "alors rien : %s" % (len(ce_ko), ", ".join("%s/%s" % (b, n) for b, n in ce_ko)))
        rc = 1
    inertes = [(r["etiquette"], cle) for r in resultats for cle in
               ("d1_actions", "d3_sous_arbres", "d4_ability_power_vides")
               if r["derivations"][cle] == 0]
    if inertes:
        print("  ATTENTION : derivation(s) qu'AUCUNE donnee du corpus n'exerce -- le vert ne "
              "dit rien sur elles : %s" % ", ".join("%s/%s" % (b, c) for b, c in inertes))
    if rc == 0:
        print("  VERT sur le BLOC 1 : les %s sous-arbres `%s` / `%s` sont reproduits a "
              "l'EGALITE BRUTE, donnees fournies."
              % ("/".join(str(len(r["partition"]["portes"])) for r in resultats),
                 GroupType.Ability_Power.name, GroupType.Effect_Refresh.name))
        print("  NON COUVERT : les formes `ChangeStats` / `ChangeAbility` du bloc "
              "(`#477-r21-r1`), la SELECTION (`#477-r21-r2`) et l'ALLOCATION ECS des ids "
              "(`#477-r21-r3`). `%s` AUTONOMES : %s -- mesure, pas deduite."
              % (GroupType.Effect_Refresh.name,
                 "/".join(str(r["effect_refresh"]["autonomes"]) for r in resultats)))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
