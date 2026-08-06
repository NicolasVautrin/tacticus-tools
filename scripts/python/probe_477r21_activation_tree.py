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

CE QUE `#477-r21-r1` Y A AJOUTE -- les formes `ChangeStats` / `ChangeAbility` du bloc 1
--------------------------------------------------------------------------------------
Elles sortent de TROIS operations natives distinctes, dont AUCUNE n'est
`RefreshEffectsOperation` : `TransformUnitOperation$$Execute` (les `UnitStats_*_Modification*`
+ `UnitStats_Transformed`), `RemoveActiveAbilityOperation$$Execute` (un seul tag) et
`AddActiveAbilityOperation$$Execute` (les six `UnitStats_ActiveAbility_*`). Quatre derivations
de plus :

  (D6) `Tag=UnitStats_Transformed` -- le port le pose SANS GARDE en tete de chaque
       `Action=ChangeStats` de transformation ; le parseur ne le lui demande jamais ;
  (D7) L'ENTITE DU MODIFICATEUR, reconstruite depuis le `Entity=` de l'entete du
       `Group=Effect_Refresh` englobant -- le tag `..._Modification_Entity` est LU POUR RIEN.
       C'est le jumeau exact de (D1) ;
  (D8) LES CLES DE TAG, derivees de la table `StatType -> ModStatTransformConfig` lue dans
       `TransformUnitOperation$$.cctor`. Le parseur donne un `StatType`, le port choisit trois
       ordinaux -- que l'arithmetique ne donne pas (`Movement` numerote
       `Modification/Entity/Change`, `MaxHealth` numerote `Modification/Change/Entity`) ;
  (D9) L'AIGUILLAGE entre les trois producteurs, par deux invariants LUS : un retrait n'ecrit
       qu'un tag, une transformation ecrit toujours `UnitStats_Transformed`, et seul l'ajout
       emet un `StepType.ChangeAbility`.

⚠ REGIME PUBLIE : `_Modification` et `_Modification_Change` sont EGAUX sur tous les couples des
flux temoins (un seul modificateur par stat). L'egalite brute ne SEPARE donc pas ces deux cles
ici -- le compte est imprime plutot que sous-entendu.

⚠ CHAQUE MUTATION PORTE SON DOMAINE. Une mutation qui ne mord pas parce que le corpus n'a aucun
site a muter (`domaine == 0`) est une ATTENTION, pas un ROUGE ; une mutation qui ne mord pas
avec un domaine NON NUL reste un ROUGE. Sans ce compte, les deux se lisent pareil -- et le
premier roster crafte (2v2) est exactement dans le premier cas pour les cinq mutations de
`#477-r21-r1`.

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
from typing import Dict, List, Optional, Tuple  # noqa: F401

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
from engine.streams.inform_ops import (get_inform_tags,  # noqa: E402
                                       get_inform_weapon_tags, inform)
from engine.entities.stats import StatPart, StatType  # noqa: E402
from engine.streams.active_ability_ops import (AddedActiveAbility,  # noqa: E402
                                               add_active_ability,
                                               remove_active_ability)
from engine.streams.refresh_effects import (EffectSetup,  # noqa: E402
                                            add_activate_effect_action,
                                            add_deactivate_effect_action,
                                            add_lose_effect_action,
                                            add_receive_effect_action,
                                            generate_event_group,
                                            get_refresh_effect_tags)
from engine.streams.transform_unit import (FILL_STAT_TRANSFORM_CONFIG,  # noqa: E402
                                           MOD_STAT_TRANSFORM_CONFIG,
                                           StatModifierSetup, build_transform_tags,
                                           transform_unit)
from engine.streams.unit_extensions import ActiveAbilityState  # noqa: E402
from engine.streams.unit_extensions import \
    get_full_state_update_tags_for_active  # noqa: E402

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
#: ⚠ CETTE LISTE EST DERIVEE DU PORT, PAS DU FLUX. Elle nomme exactement les emissions portees
#: par `engine/streams/refresh_effects.py`, `evaluate_trigger.py`, `transform_unit.py` et
#: `active_ability_ops.py`. Ce qu'un flux montre en plus (`Action=Info`, ...) sort d'autres
#: artefacts natifs et reste hors perimetre -- ENUMERE, jamais absorbe.
#:
#: ⚠ `ChangeStats` ET `ChangeAbility` Y SONT ENTREES AVEC `#477-r21-r1`. Elles sortent de TROIS
#: operations natives distinctes, dont aucune n'est `RefreshEffectsOperation` :
#: `TransformUnitOperation$$Execute`, `RemoveActiveAbilityOperation$$Execute` et
#: `AddActiveAbilityOperation$$Execute`.
#:
#: ⚠ `Info` Y EST ENTREE AVEC `#477-r21-r1-r1` (residu `#477-r22-r1`), et son PERIMETRE est le
#: couple ACTION + CLE, jamais l'action seule. Elle sort d'une QUATRIEME operation --
#: `IdunBattle.Operations.InformOperation$$Execute`, deja portee par `engine/streams/inform_ops.py`
#: -- dont le dictionnaire est construit en amont par une surcharge de
#: `IdunBattleLogic.Entities.DSLBehaviors$$Inform`. Seule la surcharge A UNE CLE est portee
#: (`get_inform_tags`), donc seul `Tag=Custom_Data` entre au perimetre : une `Action=Info` qui
#: porterait les cles d'ARME (`Attack_Weapon_*`, l'autre foyer) reste HORS, ENUMEREE.
ACTIONS_PORTEES = frozenset((StepType.ActivateEffect.name, StepType.ReceiveEffect.name,
                             StepType.LoseEffect.name, StepType.DeactivateEffect.name,
                             StepType.ChangeStats.name, StepType.ChangeAbility.name,
                             StepType.Info.name))
GROUPES_PORTES = frozenset((GroupType.Ability_Power.name, GroupType.Effect_Refresh.name))

#: Les SIX tags qu'`AddActiveAbilityOperation$$Execute` inline, nommes par le port.
TAGS_ADD_ACTIVE = (TagKey.UnitStats_ActiveAbility_Id, TagKey.UnitStats_ActiveAbility_Level,
                   TagKey.UnitStats_ActiveAbility_VariableMultiplierPercentage,
                   TagKey.UnitStats_ActiveAbility_CanStillBeUsed,
                   TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns,
                   TagKey.UnitStats_ActiveAbility_IsDisabled)


def _tags_de_transformation() -> frozenset:
    """Les `TagKey` qu'une `Action=ChangeStats` de `TransformUnitOperation` peut porter.

    ⚠ DERIVEE DES TABLES DU PORT, ET C'EST VOULU : c'est le PERIMETRE (« cette forme est-elle
    portee ? »), jamais une valeur. Un `StatType` que le port ne connait pas sort donc du
    perimetre au lieu d'etre ampute -- exactement la regle du reste de ce probe."""
    out = {int(TagKey.UnitStats_Transformed), int(TagKey.UnitStats_Modification_Hidden),
           int(TagKey.UnitStats_NumberOfMembers), int(TagKey.UnitStats_ActiveAbility_Level)}
    for cfg in MOD_STAT_TRANSFORM_CONFIG.values():
        out.update((int(cfg.current_key), int(cfg.modification_key),
                    int(cfg.modification_change_key), int(cfg.modification_entity_key),
                    int(cfg.override_key), int(cfg.override_entity_key),
                    int(cfg.override_is_modifiable_key)))
    for fcfg in FILL_STAT_TRANSFORM_CONFIG.values():
        out.update((int(fcfg.remaining_key), int(fcfg.max_key), int(fcfg.modification_key),
                    int(fcfg.modification_change_key), int(fcfg.modification_entity_key),
                    int(fcfg.override_key), int(fcfg.override_entity_key),
                    int(fcfg.override_is_modifiable_key)))
    out.discard(int(TagKey.UnitStats_Unimplemented))
    return frozenset(out)


def _table_inverse_stat() -> Dict[int, Tuple[int, str]]:
    """`<ordinal de TagKey>` -> `(StatType, role)`, role dans `total` / `change` / `entity`.

    ⚠ C'EST LE PENDANT DE `TAG_VERS_CHAMP`, ET ELLE EST DECLAREE EN BORNE (c) POUR LA MEME
    RAISON : le port choisit quelle cle porte quelle grandeur, ce parseur refait le chemin en
    sens inverse. Elle ne mesure donc RIEN par elle-meme.
    Ce qui reste MESURE est enumere en (D6)..(D9) -- et le role `entity` n'est JAMAIS consomme :
    l'entite du modificateur est RECONSTRUITE depuis l'entete du groupe (D7)."""
    out: Dict[int, Tuple[int, str]] = {}
    for stat_type, cfg in MOD_STAT_TRANSFORM_CONFIG.items():
        out[int(cfg.modification_key)] = (int(stat_type), "total")
        out[int(cfg.modification_change_key)] = (int(stat_type), "change")
        out[int(cfg.modification_entity_key)] = (int(stat_type), "entity")
    for stat_type, fcfg in FILL_STAT_TRANSFORM_CONFIG.items():
        out[int(fcfg.modification_key)] = (int(stat_type), "total")
        out[int(fcfg.modification_change_key)] = (int(stat_type), "change")
        out[int(fcfg.modification_entity_key)] = (int(stat_type), "entity")
    return out

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
    tags = (list(TAG_VERS_CHAMP)
            + [TagKey.Effect_Id.name, TagKey.Effect_State_Level.name,
               TagKey.Effect_State_VariableMultiplierPercentage.name,
               TagKey.UnitStats_RemoveActiveAbility.name,
               # #477-r22-r1 : l'unique cle que la surcharge portee de `DSLBehaviors$$Inform`
               # sait ecrire. Les `Attack_Weapon_*` de l'AUTRE foyer restent hors perimetre.
               # ⚠ `UnitStats_ActionsAvailable` N'EST PAS ICI, ET C'EST VOULU : sa ligne n'est
               # jamais dans un SOUS-ARBRE mais a la profondeur du groupe, et #477-r22-r1 la
               # reconnait par une regle STRUCTURELLE (`_marque` de `probe_477r22`). L'ajouter
               # ici declarerait « porte » tout sous-arbre qui en contiendrait une, alors
               # qu'aucun producteur de ce paquet ne l'ecrit a cet endroit-la.
               TagKey.Custom_Data.name]
            + [t.name for t in TAGS_ADD_ACTIVE]
            + [TagKey(o).name for o in _tags_de_transformation()])
    return frozenset(["Group=%s" % g for g in GROUPES_PORTES]
                     + ["Action=%s" % a for a in ACTIONS_PORTEES]
                     + ["Finish_Group"]
                     + ["Tag=%s" % t for t in tags])


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
            if me:
                fin = _bloc(sous, k)
                ap.enfants.append(_lire_sous_arbre(sous[k:fin + 1]))
                k = fin + 1
                continue
            # ⚠ UN `Ability_Power` PORTE AUSSI DES ACTIONS DIRECTES, sans `Effect_Refresh`
            # intermediaire : c'est le motif `TwistedScience` (`RemoveActiveAbilityOperation`
            # puis `AddActiveAbilityOperation`, appelees par le behaviour DSL de l'ability).
            ma = CONF.RE_ACTION.match(sous[k])
            if not ma:
                raise MesureImpossible("enfant inattendu dans `Ability_Power` : [%s]" % sous[k])
            act = ActionObs(step=ma.group("sym"), entity=_entite(ma.group("entity")))
            k += 1
            while k < len(sous) - 1 and CONF.RE_TAG.match(sous[k]):
                mt = CONF.RE_TAG.match(sous[k])
                act.tags.append((mt.group("sym"), int(mt.group("value"))))
                k += 1
            ap.enfants.append(act)
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


_TABLE_INVERSE_STAT = _table_inverse_stat()


def _nom_stat(valeur: int) -> str:
    try:
        return StatType(int(valeur)).name
    except ValueError:
        return str(int(valeur))


def _tag(act: ActionObs, cle: TagKey) -> Optional[int]:
    for nom, val in act.tags:
        if nom == cle.name:
            return val
    return None


def _est_retrait_ability(act: ActionObs) -> bool:
    return _tag(act, TagKey.UnitStats_RemoveActiveAbility) is not None


def _est_transformation(act: ActionObs) -> bool:
    return _tag(act, TagKey.UnitStats_Transformed) is not None


def _setups_stat(act: ActionObs, entite_modificateur: int,
                 mutation: str = "") -> List[StatModifierSetup]:
    """Les `StatModifierSetup` d'une `Action=ChangeStats` de transformation.

    ⚠ L'ENTITE DU MODIFICATEUR NE VIENT PAS DU TAG, C'EST (D7). Le parseur la prend dans le
    `Entity=` de l'entete du `Group=Effect_Refresh` englobant -- le meme canal unique que (D1)
    pour `Effect_Id`. Le tag `..._Modification_Entity` est LU pour rien : le port le
    reconstruit.

    ⚠ LE `StatPart` EST UNE CONSTANTE, ET LE CORPUS NE PEUT PAS LA TRANCHER.
    `AddTagsForModifiable` partage le MEME corps entre `StatPart.Modification` (5) et
    `MultiplierModification` (9) : les deux produisent un texte identique. Le probe ecrit
    `Modification` et le DIT, plutot que de laisser croire qu'il l'a mesure."""
    par_stat: Dict[int, Dict[str, int]] = {}
    for nom, val in act.tags:
        ordinal = int(TagKey[nom])
        if ordinal not in _TABLE_INVERSE_STAT:
            continue
        stat_type, role = _TABLE_INVERSE_STAT[ordinal]
        par_stat.setdefault(stat_type, {})[role] = val
    if not par_stat:
        raise MesureImpossible(
            "`Action=%s` declaree portee mais sans aucun tag de modification reconnu : %s"
            % (StepType.ChangeStats.name, [n for n, _v in act.tags]))
    connus = sorted(MOD_STAT_TRANSFORM_CONFIG)
    out: List[StatModifierSetup] = []
    for stat_type in sorted(par_stat):
        roles = par_stat[stat_type]
        if "total" not in roles:
            raise MesureImpossible(
                "`Action=%s` sur StatType=%s sans cle de modification totale"
                % (StepType.ChangeStats.name, stat_type))
        cible = stat_type
        if mutation == "stat_table" and stat_type in connus:
            # la config d'un AUTRE `StatType` : memes valeurs, cles de tag differentes
            cible = connus[(connus.index(stat_type) + 1) % len(connus)]
        entite = entite_modificateur
        if mutation == "modifier_entity":
            entite = entite + 1
        out.append(StatModifierSetup(
            stat_type=cible, stat_part=StatPart.MODIFICATION,
            entity_id=entite if "change" in roles else None,
            stat_current=roles["total"], stat_from_modifier=roles.get("change")))
    return out


def _ability_ajoutee(act: ActionObs) -> AddedActiveAbility:
    manquants = [t.name for t in TAGS_ADD_ACTIVE if _tag(act, t) is None]
    if manquants:
        raise MesureImpossible("`Action=%s` sans les tags %s"
                               % (StepType.ChangeAbility.name, ",".join(manquants)))
    return AddedActiveAbility(
        ability_name=_tag(act, TagKey.UnitStats_ActiveAbility_Id),
        level=_tag(act, TagKey.UnitStats_ActiveAbility_Level),
        variable_multiplier_percentage=_tag(
            act, TagKey.UnitStats_ActiveAbility_VariableMultiplierPercentage),
        can_still_be_used=bool(_tag(act, TagKey.UnitStats_ActiveAbility_CanStillBeUsed)),
        remaining_cooldown_turns=_tag(act, TagKey.UnitStats_ActiveAbility_RemainingCooldownTurns),
        is_disabled=bool(_tag(act, TagKey.UnitStats_ActiveAbility_IsDisabled)))


def emettre_action_stat(events: StreamDispatcher, act: ActionObs, entite_modificateur: int,
                        mutation: str = "") -> None:
    """Emet une `Action=ChangeStats` / `ChangeAbility` AVEC LE PORT -- `#477-r21-r1`.

    ⚠ L'AIGUILLAGE ENTRE LES TROIS PRODUCTEURS EST (D9), ET IL EST DERIVE D'UN INVARIANT LU :
    `RemoveActiveAbilityOperation` ecrit UN SEUL tag (`UnitStats_RemoveActiveAbility`),
    `TransformUnitOperation` ecrit TOUJOURS `UnitStats_Transformed` (sans garde, avant sa
    boucle), et `AddActiveAbilityOperation` est la seule des trois a emettre un
    `StepType.ChangeAbility`. Une `Action=ChangeStats` qui ne porte aucun des deux marqueurs
    sort du perimetre au lieu d'etre devinee."""
    if act.step == StepType.ChangeAbility.name:
        if mutation == "ability_tags_ammo":
            # `GetFullStateUpdateTags(activeAbility)` A LA PLACE de l'inline natif : la
            # surcharge d'`UnitExtensions` ajoute DEUX tags de munitions que
            # `AddActiveAbilityOperation` n'ecrit jamais.
            a = _ability_ajoutee(act)
            events.action(StepType.ChangeAbility, act.entity,
                          get_full_state_update_tags_for_active(ActiveAbilityState(
                              ability_name=a.ability_name, level=a.level,
                              variable_multiplier_percentage=a.variable_multiplier_percentage,
                              can_still_be_used=a.can_still_be_used,
                              remaining_cooldown_turns=a.remaining_cooldown_turns,
                              is_disabled=a.is_disabled, ammo_cost=0)))
            return
        add_active_ability(events, act.entity, _ability_ajoutee(act))
        return
    if _est_retrait_ability(act):
        cible = _tag(act, TagKey.UnitStats_RemoveActiveAbility)
        if mutation == "remove_step":
            # meme entite, meme tag, SEULE la `StepType` change (`ChangeStats` -> `ChangeAbility`)
            events.action(StepType.ChangeAbility, act.entity,
                          {int(TagKey.UnitStats_RemoveActiveAbility): int(cible)})
            return
        remove_active_ability(events, act.entity, cible)
        return
    if not _est_transformation(act):
        raise MesureImpossible(
            "`Action=%s` sans `Tag=%s` ni `Tag=%s` -- producteur natif non identifie"
            % (act.step, TagKey.UnitStats_Transformed.name,
               TagKey.UnitStats_RemoveActiveAbility.name))
    setups = _setups_stat(act, entite_modificateur, mutation)
    if mutation == "sans_transformed":
        # le tag INCONDITIONNEL de `TransformUnitOperation$$Execute`, retire
        tags = dict(build_transform_tags(setups))
        tags.pop(int(TagKey.UnitStats_Transformed), None)
        events.action(StepType.ChangeStats, act.entity, tags)
        return
    transform_unit(events, act.entity, setups)


def emettre_action_info(events: StreamDispatcher, act: ActionObs, entite_groupe: int,
                        mutation: str = "") -> None:
    """Emet une `Action=Info` AVEC LE PORT -- `#477-r22-r1`, second motif.

    DEUX foyers portes, l'un au-dessus de l'autre :
      * `engine/streams/inform_ops.get_inform_tags(tag, amount)` = la surcharge A UNE CLE de
        `IdunBattleLogic.Entities.DSLBehaviors$$Inform(TagKey, IAmountFormula)` ;
      * `engine/streams/inform_ops.inform(tags)` = `IdunBattle.Operations.InformOperation$$Execute`,
        qui ecrit `Entity=NO_ENTITY` (le litteral `0` du quatrieme argument) -- l'entite du
        CASTER est portee par le `Group=Ability_Power` englobant, jamais par la ligne.

    ⚠ LE PERIMETRE EST LE COUPLE ACTION + CLE. Une `Action=Info` a deux ou trois cles sort de
    l'AUTRE surcharge (`DSLBehaviors$$InformWeapon`, cles `Attack_Weapon_*`) : le probe REFUSE
    de l'emettre par ce foyer-ci plutot que de fabriquer un dictionnaire que le natif ne
    construit pas la."""
    if len(act.tags) != 1:
        raise MesureImpossible(
            "`Action=%s` a %d cle(s) (%s) -- la surcharge portee de `DSLBehaviors$$Inform` n'en "
            "ecrit qu'UNE ; les cles d'ARME sortent d'un autre foyer"
            % (StepType.Info.name, len(act.tags), ",".join(n for n, _v in act.tags)))
    nom, valeur = act.tags[0]
    if mutation == "info_tag_arme":
        # l'AUTRE foyer d'`Inform` a la place du bon : `DSLBehaviors$$InformWeapon` ecrit DEUX
        # cles obligatoires (`Attack_Weapon_DamageProfile`, `Attack_Weapon_IsMelee`) -- la
        # confusion naturelle entre les deux surcharges homonymes
        inform(events, get_inform_weapon_tags(int(valeur), True, False))
        return
    tags = get_inform_tags(int(TagKey[nom]), int(valeur))
    if mutation == "info_entite":
        # l'entite du CASTER a la place du litteral `0` : elle est disponible dans l'entete du
        # `Group=Ability_Power`, et c'est exactement ce que le natif NE passe PAS
        events.action(int(StepType.Info), int(entite_groupe), tags)
        return
    inform(events, tags)


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
                    if isinstance(e, ActionObs):
                        if e.step == StepType.Info.name:
                            # #477-r22-r1 : le motif `StandVigil` -- une `Action=Info` directe,
                            # emise par `InformOperation$$Execute` depuis le behaviour DSL de
                            # l'ability, PAS par une operation de stat.
                            emettre_action_info(events, e, obs.unit_entity, mutation)
                            continue
                        # ⚠ ENTITE DU MODIFICATEUR : il n'y a PAS de `Group=Effect_Refresh`
                        # englobant ici, donc rien a en deriver -- et le motif confronte
                        # (`TwistedScience`) n'en a pas besoin : ses deux actions sont des
                        # operations d'ABILITY, pas de stat.
                        emettre_action_stat(events, e, e.entity, mutation)
                        continue
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
        elif act.step == StepType.Info.name:
            # #477-r22-r1 : le perimetre d'`Action=Info` est le motif « enfant DIRECT d'un
            # `Group=Ability_Power` » (le behaviour DSL de l'ability informe). Aucune des
            # closures de `RefreshEffectsOperation$$UpdateEffectTargets` n'emet un `Info` -- si
            # le flux en montrait un ICI, ce serait un producteur qu'on n'a pas lu, et le probe
            # doit le DIRE plutot que de l'emettre par un foyer qui ne le produit pas.
            raise MesureImpossible(
                "`Action=%s` DANS un `Group=%s` -- aucun producteur lu de ce paquet ne l'y met"
                % (StepType.Info.name, GroupType.Effect_Refresh.name))
        elif act.step in (StepType.ChangeStats.name, StepType.ChangeAbility.name):
            # ⚠ CE N'EST PAS `RefreshEffectsOperation` QUI L'EMET. C'est la DERNIERE closure de
            # la `List<Action>` construite par `UpdateEffectTargets` --
            # `ApplyEffectsForTargets` -> `AStatModifierEffect$$ApplyModification` ->
            # `TransformUnitOperation$$Execute`. Le port la glisse donc dans `event_actions`,
            # exactement comme le natif : `generate_event_group` prend une SEQUENCE de
            # callables pour cette raison-la.
            actions.append(lambda a=act, e=obs.effect_entity:
                           emettre_action_stat(events, a, e, mutation))
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
             "tags_activate", "sans_source_id", "ouverture_vide",
             # `#477-r21-r1`
             "stat_table", "sans_transformed", "modifier_entity", "remove_step",
             "ability_tags_ammo")

#: LES MUTATIONS QUE CE MODULE SAIT EMETTRE MAIS QUE CE PROBE NE JOUE PAS -- elles portent sur la
#: forme `Action=Info` (`#477-r22-r1`), et le BLOC 1 n'en contient AUCUNE : leur domaine y est NUL
#: sur les QUATRE scenarios. Les laisser dans `MUTATIONS` faisait rougir ce probe par son propre
#: garde-fou (« rien ne les confronte »), et c'est la bonne reponse : une mutation qu'aucun
#: scenario n'exerce ne mesure rien ICI. Elles sont jouees par `probe_477r22_turn_phase.py`, dont
#: le corpus -- le contenu du `Group=StartTurn` -- porte 3 `Action=Info` sur deux scenarios.
MUTATIONS_RELAYEES = ("info_entite", "info_tag_arme")


def derivations(portes: List[dict]) -> dict:
    """CE QUE LES DERIVATIONS ONT A MORDRE SUR CE CORPUS -- publie, jamais suppose.

    Une derivation qu'aucune donnee du corpus n'exerce ne prouve rien, quel que soit le verdict.
    Ce compte est ce qui distingue « (D3) tient » de « (D3) n'a rien eu a trancher »."""
    d1 = d2 = d3 = d4_vides = d4_pleins = 0
    d6_transform = d7_entites = d9_retrait = d9_add = d10_info = 0
    degeneres = exercees = 0
    noms_effect, noms_ability = set(), set()
    stats_exercees = set()

    def _compter_action_stat(act: ActionObs) -> None:
        # ⚠ PAS DE `d1` ICI, ET C'EST VOULU : (D1) compte les actions dont le port RECONSTRUIT
        # `Tag=Effect_Id`, or aucune des trois formes de `#477-r21-r1` ne le porte. Les y
        # ajouter gonflerait un compte d'exercice avec des sites qui n'exercent PAS la
        # derivation -- exactement ce qu'un compte d'exercice doit interdire.
        nonlocal d2, d6_transform, d7_entites, d9_retrait, d9_add, degeneres, exercees
        noms = [n for n, _v in act.tags]
        if len(noms) > 1 and noms != sorted(noms):
            d2 += 1
        if act.step == StepType.Info.name:
            # #477-r22-r1 : `Action=Info` n'exerce AUCUNE des derivations de stat -- elle a la
            # sienne (`d10`), comptee par `_visiter`.
            return
        if act.step == StepType.ChangeAbility.name:
            d9_add += 1
            return
        if _est_retrait_ability(act):
            d9_retrait += 1
            return
        if not _est_transformation(act):
            return
        d6_transform += 1
        par_stat: Dict[int, Dict[str, int]] = {}
        for nom, val in act.tags:
            ordinal = int(TagKey[nom])
            if ordinal in _TABLE_INVERSE_STAT:
                stat_type, role = _TABLE_INVERSE_STAT[ordinal]
                par_stat.setdefault(stat_type, {})[role] = val
        for stat_type, roles in par_stat.items():
            stats_exercees.add(stat_type)
            if "entity" in roles:
                d7_entites += 1
            if "change" in roles and "total" in roles:
                exercees += 1
                if roles["change"] != roles["total"]:
                    degeneres += 1

    def _visiter(obs) -> None:
        nonlocal d1, d2, d3, d4_vides, d4_pleins, d10_info
        if isinstance(obs, ActionObs):
            if obs.step == StepType.Info.name:
                # (D10) #477-r22-r1 : le port ecrit `Entity=NO_ENTITY` et UNE seule cle. Le
                # parseur lui donne le couple (cle, valeur), jamais l'entite ni le nombre de
                # cles -- ce sont les deux decisions que les mutations `info_*` visent.
                d10_info += 1
                return
            _compter_action_stat(obs)
            return
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
            if act.step in (StepType.ChangeStats.name, StepType.ChangeAbility.name):
                _compter_action_stat(act)
                continue
            d1 += 1
            noms = [n for n, _v in act.tags]
            if len(noms) > 1 and noms != sorted(noms):
                d2 += 1

    for p in portes:
        _visiter(p["obs"])
    return {"d1_actions": d1, "d2_blocs_hors_ordre_alpha": d2, "d3_sous_arbres": d3,
            "d4_ability_power_vides": d4_vides, "d4_ability_power_pleins": d4_pleins,
            "d5_noms_effect": len(noms_effect), "d5_noms_ability": len(noms_ability),
            "d6_transformations": d6_transform, "d7_entites_reconstruites": d7_entites,
            "d8_stats_exercees": sorted(stats_exercees),
            "d9_retraits": d9_retrait, "d9_ajouts": d9_add, "d10_info": d10_info,
            "r1_total_diff_change": degeneres, "r1_couples": exercees}


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
        if isinstance(obs, ActionObs):
            return 0
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
        if isinstance(obs, ActionObs):
            return
        if isinstance(obs, AbilityPowerObs):
            for e in obs.enfants:
                _visiter(e)
            return
        out.add(obs.effect_entity)

    for p in portes:
        _visiter(p["obs"])
    return out


def domaines(portes: List[dict]) -> Dict[str, int]:
    """LE NOMBRE DE SITES QUE CHAQUE MUTATION PEUT TOUCHER -- calcule DEPUIS LES DONNEES.

    ⚠ SANS CE COMPTE, DEUX ECHECS DIFFERENTS SE LISENT PAREIL. Une mutation qui ne mord pas
    parce qu'elle est INERTE PAR CONSTRUCTION (elle ne change rien a ce qu'elle mute) est un
    ROUGE : elle ne mesure rien, quel que soit son verdict. Une mutation qui ne mord pas parce
    que le corpus n'a AUCUN site a muter est une ATTENTION : elle n'a rien pu mesurer ICI, ce
    qui n'accuse ni le port ni elle. Les distinguer demande un domaine, pas un verdict --
    mesure sur le roster 2v2, ou les cinq mutations de `#477-r21-r1` ont un domaine NUL parce
    que ce roster ne produit aucune de ces trois formes."""
    d = {nom: 0 for nom in MUTATIONS}
    der = derivations(portes)

    def _visiter(obs) -> None:
        if isinstance(obs, ActionObs):
            if obs.step == StepType.Info.name:
                # domaine des mutations RELAYEES : compte tenu ici, joue par #477-r22
                for nom in MUTATIONS_RELAYEES:
                    d[nom] = d.get(nom, 0) + 1
            elif obs.step == StepType.ChangeAbility.name:
                d["ability_tags_ammo"] += 1
            elif _est_retrait_ability(obs):
                d["remove_step"] += 1
            elif _est_transformation(obs):
                d["stat_table"] += 1
                d["sans_transformed"] += 1
                d["modifier_entity"] += 1
            return
        if isinstance(obs, AbilityPowerObs):
            d["ability_source"] += 1
            for e in obs.enfants:
                _visiter(e)
            return
        d["effect_id"] += 1
        d["effect_source"] += 1
        d["sans_source_id"] += 1
        d["ouverture_vide"] += 1
        for act in obs.actions:
            if act.step == StepType.ActivateEffect.name:
                d["step_activate"] += 1
                d["tags_activate"] += 1
            elif act.step in (StepType.ChangeStats.name, StepType.ChangeAbility.name):
                _visiter(act)

    for p in portes:
        _visiter(p["obs"])
    d["placement"] = der["d3_sous_arbres"]
    return d


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
        "unites. CE N'EST PLUS LA REGLE QUI MANQUE : `engine/streams/entity_allocator.py` la "
        "porte, et elle reproduit 63/63, 67/67 et 22/22 allocations une fois la SEQUENCE DE "
        "CREATION donnee (`#477-r21-r3`). Ce qui manque est cette sequence -- le flux n'ordonne "
        "que les APPARITIONS, qui en different, et il TAIT des creations entieres. C'est donc "
        "la MEME entree que la premiere de cette liste, la SELECTION (`#477-r21-r2`)"
        % len(_ids_effet(par["portes"])),
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

    dom = domaines(par["portes"])
    ce = []
    for nom in MUTATIONS:
        try:
            texte = emettre(par["portes"], mutation=nom)
        except MesureImpossible:
            texte = texte_port
        a_morde = texte != texte_port
        r = CONF.comparer(natif_porte, texte)
        ce.append((nom, a_morde, len(r.nouvelles) + len(r.connues), dom[nom]))

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
    print("      (D6) `Tag=%s` pose sans garde sur %d `Action=%s` de transformation"
          % (TagKey.UnitStats_Transformed.name, der["d6_transformations"],
             StepType.ChangeStats.name))
    print("      (D7) entite du modificateur reconstruite depuis l'entete du groupe : %d tag(s) "
          "`..._Modification_Entity` que le port NE LIT PAS" % der["d7_entites_reconstruites"])
    print("      (D8) cles de tag derivees de la table `StatType -> config` : StatType %s"
          % (",".join(_nom_stat(s) for s in der["d8_stats_exercees"]) or "-"))
    print("      (D9) aiguillage des 3 producteurs : %d retrait(s) d'ability, %d ajout(s), "
          "%d transformation(s)"
          % (der["d9_retraits"], der["d9_ajouts"], der["d6_transformations"]))
    print("      (D10) `Action=%s` : %d occurrence(s) -- `Entity=NO_ENTITY` et UNE seule cle, "
          "toutes deux derivees (`#477-r22-r1`)" % (StepType.Info.name, der["d10_info"]))
    if der["r1_couples"]:
        print("      REGIME : `_Modification` != `_Modification_Change` sur %d / %d couple(s) -- "
              "%s" % (der["r1_total_diff_change"], der["r1_couples"],
                      "les deux cles sont DISCRIMINEES"
                      if der["r1_total_diff_change"] else
                      "EGAUX partout : l'egalite du flux NE SEPARE PAS ces deux cles ici"))
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
    for nom, a_morde, divs, dom in res["contre_epreuve"]:
        if dom == 0:
            etat = "NON EXERCEE"
        elif a_morde and divs:
            etat = "OK"
        else:
            etat = "ROUGE"
        print("      %-18s domaine=%-4d a_morde=%-5s divergences=%-4d %s"
              % (nom, dom, a_morde, divs, etat))
        if dom == 0:
            print("          - domaine NUL : aucun site a muter dans ce scenario. La mutation "
                  "n'a rien pu mesurer ICI -- ce n'est pas une inertie de construction.")
        elif not a_morde:
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
        # ⚠ LE SECOND ROSTER CRAFTE EXISTE PARCE QUE LE PREMIER NE PROUVE RIEN SUR
        # `#477-r21-r1` : il porte ZERO `ChangeStats` / `ChangeAbility`, donc les cinq
        # mutations de cette tranche y ont un domaine NUL. Celui-ci est choisi PAR PORTEUR,
        # sur les trois voies mesurees par `unit_map.py find --ability` :
        #   `custoVexilusPraetor` -> `StandVigil`     (1308) -> `UnitStats_FixedArmor_*`
        #   `bloodIntercessor`    -> `RapidAssault`   (1188) -> `UnitStats_Movement_*`
        #   `genesBiophagus`      -> `TwistedScience`        -> Remove + Add d'ability active
        # Il joue sur un board DIFFERENT des deux precedents, pour que l'accord ne puisse pas
        # venir d'une geometrie partagee.
        plans.append(("C1_02", "custoVexilusPraetor,bloodIntercessor",
                      "genesBiophagus,astraBullgryn", "C1_02-r1"))
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
             for nom, a_morde, divs, dom in r["contre_epreuve"]
             if dom > 0 and not (a_morde and divs)]
    if ce_ko:
        print("  ROUGE : %d mutation(s) NE ROUGISSENT PAS malgre un domaine NON NUL -- le vert "
              "du scenario sain ne prouve alors rien : %s"
              % (len(ce_ko), ", ".join("%s/%s" % (b, n) for b, n in ce_ko)))
        rc = 1
    # ⚠ UNE MUTATION QU'AUCUN SCENARIO N'EXERCE EST UN ROUGE DU CORPUS, pas une attention : elle
    # est alors ecrite sans que rien ne la confronte, exactement comme les deux mutations
    # retirees de cette tranche parce qu'inertes par construction.
    jamais = [nom for nom in MUTATIONS
              if all(dom == 0 for r in resultats
                     for n, _m, _d, dom in r["contre_epreuve"] if n == nom)]
    if jamais:
        print("  ROUGE : %d mutation(s) au domaine NUL sur TOUS les scenarios -- rien ne les "
              "confronte : %s" % (len(jamais), ", ".join(jamais)))
        rc = 1
    non_exercees = [(r["etiquette"], nom) for r in resultats
                    for nom, _m, _d, dom in r["contre_epreuve"] if dom == 0]
    if non_exercees:
        print("  ATTENTION : %d couple(s) scenario/mutation au domaine NUL -- le vert de ce "
              "scenario ne dit rien sur elles : %s"
              % (len(non_exercees), ", ".join("%s/%s" % (b, n) for b, n in non_exercees)))
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
        print("  NON COUVERT : la SELECTION (`#477-r21-r2`) -- dont la SEQUENCE DE CREATION "
              "des effets, seul terme qui manque encore a l'allocateur porte par `#477-r21-r3`, "
              "et l'ORDRE des six blocs d'`eventActions` que fixe "
              "`RefreshEffectsOperation$$UpdateEffectTargets`. "
              "`%s` AUTONOMES : %s -- mesure, pas deduite."
              % (GroupType.Effect_Refresh.name,
                 "/".join(str(r["effect_refresh"]["autonomes"]) for r in resultats)))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
