"""#1041 -- le FOYER UNIQUE des VOIES de montage COMBAT d'un ITEM DE KIT, et leur PARTITION.

## Ce qu'il ferme

`audit_kit_coverage._passive_covered` etablissait « cet item de kit est porte » en testant une
LISTE BLANCHE de cinq registres, ecrite a la main. Une liste blanche ne peut pas montrer le
registre qu'elle a oublie -- et elle en avait oublie un, MESURE : `EFFECT_TRIGGERS`. Consequence
mesuree le 2026-08-14 : la relique `PhoenixGem` (`eldarAutarch`) sortait dans le bloc
<< voies conditionnelles NON PORTEES >> alors que son port existe en entier -- trois classes
(`PhoenixGemReviveAbility`, `PhoenixGemRemoveMarkerOnRevive`, `PhoenixGemRemoveMarkerOnResurrect`)
inscrites a `EFFECT_TRIGGERS[EffectType.PhoenixGem_CanRevive]`, avec 17 tests live. Le chiffre du
doc pilote les dispatchs : un agent a failli etre envoye porter du travail deja fait.

Le remede n'est PAS d'ajouter `EFFECT_TRIGGERS` a la liste -- ce serait reproduire le vice d'un
cran plus loin. C'est de PARTITIONNER un perimetre, comme `decision_face_voies` (#979) le fait sur
la face DECISION et `trait_channels` (#1015) sur l'axe TRAIT : tout conteneur du perimetre est
INSCRIT, ou ECARTE AVEC SA RAISON, ou il sort MUET -- et un MUET fait ROUGIR le cliquet.

## Le perimetre, et ce qu'il filtre

`PERIMETRE` = les arbres ou vit le montage COMBAT d'un item de kit : le runner (`engine/runner`),
la fabrique d'effets (`engine/entities/effects/factory.py`) et les services de regles
(`engine/services`). Un REPERTOIRE, jamais une liste de modules -- une liste de modules ne verrait
pas le module NEUF, qui est exactement le mode de defaillance qu'on ferme.

Tout conteneur de niveau module a nom MAJUSCULE y est visite. Il entre dans la partition des
qu'AU MOINS UN de ses elements resout comme un item de kit -- par NOM, ou par ordinal dans l'un
des trois enums. Les autres sont ECARTES PAR LE FILTRE, qui DIT son compte (et les liste sous
`--tout`).

## Le critere d'inscription, ecrit une fois

Un conteneur est une **VOIE** si son APPARTENANCE signifie « le port MONTE cet item de kit sur son
porteur, cote COMBAT ».

Il est **ECARTE** s'il enonce autre chose :
  * un FAIT NATIF recense (les valeurs d'un `.cctor`, une table de durees, un jeu d'exclusions) --
    y figurer ne monte rien ;
  * une DONNEE ANNEXE d'un item deja monte ailleurs (masque de ciblage, `AbilityAttackType`,
    regime de gate) -- l'item est porte, mais ce n'est pas CE conteneur qui l'etablit ;
  * une NEGATION d'inscription (`TARGETING_OPTIONS_UNPORTED`, `_TRAITS_WITH_DERIVED_ABILITIES`) ;
  * une donnee d'un AUTRE AXE (lecture de trait -> foyer `trait_channels`, face DECISION ->
    foyer `decision_face_voies`).

⚠ **Chaque ECARTE imprime ce qu'il COUTERAIT s'il etait inscrit** (`--tout`, colonne `bascules`).
Un ecart qui ferait basculer un item devient donc VISIBLE au lieu d'etre un jugement invisible :
c'est ce qui rend la partition falsifiable, et non seulement exhaustive.

## L'ENUM DE LA CLE SE LIT AU SITE -- il ne se devine JAMAIS

Une voie a clef ENTIERE declare l'enum qui l'indexe, LU a l'en-tete du registre. Ce n'est pas une
precaution de style : c'est ce qui separe la mesure juste des quatre faux positifs qu'un balayage
naif produit. Mesure du 2026-08-14, sur les 9 items que l'audit comptait manquants -- resoudre un
ordinal dans les trois enums en faisait basculer **5**, dont **4 FAUX** :

    ordinal   EffectType                              TriggeredAbilityType
    1451      PhoenixGem_CanRevive   <- la VRAIE      WisdomOfTheAncients    <- faux positif
    1508      HealingBalms                            MastersOfManoeuvre     <- faux positif
    1462      TheArdentBlade         <- faux positif  NetherRealmCasket
    1443      ContemptuousDisregard_DamageReduction   ObsessiveAnnunciation
              ^-- faux positif

`EFFECT_TRIGGERS` est keye par `EffectType` (son en-tete le dit : << Registre : effectType ->
effet-trigger(s) >>), donc `1451` y nomme `PhoenixGem_CanRevive` et RIEN d'autre. C'est le partage
d'ordinaux que le CLAUDE.md chiffre (`TriggeredAbilityType` partage 458 ordinaux avec `EffectType`,
233 avec `ActiveAbilityType`), applique a un recensement.

## L'APPARIEMENT nom <-> item : egalite OU prefixe `<item>_`

Un item de kit se monte souvent sous un nom DERIVE du sien : la relique `PhoenixGem` par l'effet
`PhoenixGem_CanRevive`, le passif `MartialKatah` par `MartialKatah_DmgBonus`. C'est la convention
de nommage que `audit_kit_coverage._has_effect_named_after` appliquait deja a `EFFECT_CLASSES` ;
elle est ici GENERALISEE a toutes les voies. APPROXIMATION assumee, comme le reste de l'audit :
c'est la convention du port, pas un lien lu du natif. Le compte du prefixe est imprime a part.

## LE GATE D'UNE VOIE -- appartenir a un registre ne suffit pas toujours

Le vice ferme ci-dessus fait SOUS-compter. Il en existe un SECOND, qui tire en sens INVERSE et
qu'un correctif du premier seul AGGRAVERAIT : une voie de POSE peut declarer qu'un effet est pose
au spawn alors que cet effet **n'a AUCUNE CLASSE**. L'item sort alors << porte >> et il ne
s'execute RIEN -- le << mensonge de couverture >> que le foyer `factory` s'interdit explicitement.

Mesure du 2026-08-14 : **4 mythiques** (`BlightedLand`, `CabalOfSorcerers`, `GuardianConstruct`,
`MoreGitzOverEre`) etaient creditees PORTEES par leur seule entree d'`ABILITY_INIT_OWNER_EFFECTS`,
dont la cible (`<X>_ExtraDamagePct`) est absente d'`EFFECT_CLASSES`. Ce sont **exactement** les 4
entrees de ce registre dont aucune cible n'a de classe : le critere ne designe rien d'autre.

Ce n'est pas un critere invente ici -- `audit_passive_ability_coverage` l'applique DEJA a son
canal `[O]` (<< avec AU MOINS un effet cible present dans `EFFECT_CLASSES` >>). Les deux audits
divergeaient donc sur la meme question ; c'est ce foyer qui les reconcilie.

Une voie porte donc un `gate`, LU a son site : `None` (l'appartenance suffit) ou `GATE_EFFET_CLASSE`
(la VALEUR doit nommer au moins un effet present dans `EFFECT_CLASSES`). Un item dont TOUTES les
voies ont leur gate tombe n'est ni porte ni absent : il est **PARTIEL**, et c'est un troisieme etat
rendu tel quel -- le rabattre d'un cote ou de l'autre est exactement ce qui rend un compte
inexploitable.

Sortie ASCII. Usage : depuis `scripts/python/`  ->  python kit_item_voies.py [--tout]
"""
from __future__ import annotations

import ast
import functools
import importlib
import os
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

#: Les arbres de source visites. Un REPERTOIRE, jamais une liste de modules.
PERIMETRE: tuple[str, ...] = (
    "engine/runner",
    "engine/entities/effects/factory.py",
    "engine/services",
)

#: Les enums dans lesquels un ordinal peut resoudre. Sert au FILTRE (permissif, il ne fait
#: qu'ecarter) ; l'APPARIEMENT, lui, n'utilise que l'enum DECLARE par la voie.
_LIBELLES_ENUM = ("ActiveAbilityType", "TriggeredAbilityType", "EffectType")

#: La clef `nom` : l'element EST le nom gameconfig de l'item (ou d'un objet derive de lui).
CLE_NOM = "nom"

#: Le seul GATE en vigueur : la VALEUR de l'entree doit nommer >= 1 effet present dans
#: `EFFECT_CLASSES`. Une pose dont la cible n'a pas de classe ne monte RIEN (cf. docstring).
GATE_EFFET_CLASSE = "effet-a-une-classe"


class Voie:
    """Un conteneur dont l'APPARTENANCE monte un item de kit sur son porteur, cote COMBAT.

    `cle` -- `CLE_NOM`, ou le LIBELLE de l'enum qui indexe ses clefs entieres, LU a l'en-tete du
    registre. Jamais deduit du fait qu'un ordinal << resout >> : les trois enums en partagent des
    centaines, et 4 des 5 bascules d'un balayage naif sont fausses (cf. docstring du module).

    `gate` -- `None` (l'appartenance suffit) ou `GATE_EFFET_CLASSE`. Un gate qui TOMBE ne rend pas
    l'item absent : il le rend PARTIEL, etat distinct et rendu tel quel.
    """

    __slots__ = ("mod", "attr", "cle", "raison", "consommateur", "gate")

    def __init__(self, mod: str, attr: str, cle: str, raison: str, consommateur: str,
                 gate: "str | None" = None):
        self.mod, self.attr, self.cle = mod, attr, cle
        self.raison, self.consommateur, self.gate = raison, consommateur, gate

    @property
    def id(self) -> tuple[str, str]:
        return (self.mod, self.attr)

    def __repr__(self) -> str:
        return "%s.%s" % (self.mod, self.attr)


_FACTORY = "engine.entities.effects.factory"
_REGISTRY = "engine.runner.operations.triggers.dispatch.registry"

#: Les VOIES, avec leur POINT DE CONSOMMATION -- c'est lui qui etablit qu'elles montent l'item, pas
#: leur nom. Ordre : par module, ajouts EN FIN DE BLOC (registre partage).
VOIES: list[Voie] = [
    # --- la fabrique d'effets ------------------------------------------------------------------
    Voie(_FACTORY, "EFFECT_CLASSES", CLE_NOM,
         "l'effet HOMONYME ou PREFIXE porte toute la mecanique de l'item, seede depuis "
         "`decisionView.effects` sans qu'aucun registre item->X ne le mentionne",
         "EffectFactory.create"),
    Voie(_FACTORY, "ABILITY_INIT_OWNER_EFFECTS", CLE_NOM,
         "`<X>_InitAbility.CreateBehaviour` -> `AddEffect(Owner)` : l'effet est pose au spawn du "
         "porteur parce qu'il possede l'ability",
         "runner.operations.spawn._seed_ability_owner_effects",
         gate=GATE_EFFET_CLASSE),
    Voie(_FACTORY, "ABILITY_INIT_OWNER_FLAGS", CLE_NOM,
         "le PENDANT exact du precedent sur l'autre canal d'init (`AddFlag(Owner)` au lieu "
         "d'`AddEffect`), meme trigger natif et meme boucle consommatrice. Chaque entree NOMME son "
         "lecteur, donc l'appartenance n'est jamais un drapeau que personne ne lit",
         "runner.operations.spawn._seed_ability_owner_effects"),
    Voie(_FACTORY, "ABILITY_OWNER_EFFECTS", CLE_NOM,
         "`StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility` -- owner-effect "
         "ajoute au PORTEUR a la creation, chemin DIRECT distinct du `CreateBehaviour`",
         "InitializeActorAbilitiesOperation$$Execute, boucle ABILITIES",
         gate=GATE_EFFET_CLASSE),
    Voie(_FACTORY, "TRAIT_DERIVED_ABILITIES", CLE_NOM,
         "le trait fait porter une ability DERIVEE, portee cote port",
         "runner.operations.spawn / collect_triggered_abilities"),
    Voie(_FACTORY, "TRAIT_OWNER_EFFECTS", CLE_NOM,
         "owner-effect pose au spawn PAR LE TRAIT : 3e chemin de port d'un trait, ni trigger ni "
         "ability derivee (son oubli faisait compter `MartialKatah` manquant sur 4 Custodes)",
         "runner.operations.spawn._seed_ability_owner_effects",
         gate=GATE_EFFET_CLASSE),
    # --- le dispatch de triggers ---------------------------------------------------------------
    Voie(_REGISTRY, "ABILITY_TRIGGERS", CLE_NOM,
         "canal CANONIQUE d'un PASSIF : cote natif le passif EST une `TriggeredAbilityType`, et "
         "son entree ici dit que la triggered qu'il accorde est portee",
         "collect_triggered_abilities"),
    Voie(_REGISTRY, "TRAIT_TRIGGERS", CLE_NOM,
         "canal canonique d'un TRAIT : la triggered accordee par le trait est portee",
         "collect_triggered_abilities"),
    Voie(_REGISTRY, "RELIC_ABILITY_TRIGGERS", CLE_NOM,
         "montage natif DISTINCT (`TertiaryAbility` / `relicAbilities`), donc registre SEPARE "
         "a dessein -- et c'est cette separation qui l'avait rendu invisible a un predicat qui ne "
         "lisait qu'`ABILITY_TRIGGERS` (faux manquant `DawnBlade`, #951-r2)",
         "collect_triggered_abilities (deduplique le doublon des deux formes)"),
    Voie(_REGISTRY, "ACTIVE_ABILITY_TRIGGERS", CLE_NOM,
         "`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` : posseder l'ability "
         "ACTIVE fait porter la triggered derivee DES L'INIT, sans aucun cast -- le SEUL chemin "
         "pour une triggered greffee sur une active (cas des MoW, ni trait ni passif dedie)",
         "collect_triggered_abilities"),
    Voie(_REGISTRY, "PASSIVE_HELPER_ABILITY_TRIGGERS", CLE_NOM,
         "meme forme que le precedent sur l'autre dict statique natif ; registre SEPARE pour "
         "qu'aucune entree ne porte une triggered par un chemin que le natif n'emprunte pas",
         "collect_triggered_abilities"),
    Voie(_REGISTRY, "EFFECT_TRIGGERS", "EffectType",
         "l'EFFET pose par l'item porte lui-meme ses `Triggered(trigger, behaviour)` "
         "(`BaseEffect.CreateHandleTriggerAbilitiesInternal`). C'EST LA VOIE QUE LA LISTE BLANCHE "
         "AVAIT OUBLIEE : `PhoenixGem` y vit sous `EffectType.PhoenixGem_CanRevive`",
         "collect_effect_triggers"),
    Voie(_REGISTRY, "CUSTOM_TRIGGERED_ABILITIES", "TriggeredAbilityType",
         "la branche `triggerType == 0x20 = Custom` du `CreateBehaviour` est portee ; atteinte par "
         "le drain de `state.pending_triggered_abilities`, jamais par le bus d'events",
         "runner.operations.triggers.dispatch.pending"),
    Voie("engine.runner.operations.triggers.dispatch.ability", "IMPERATIVE_ABILITY_VECTORS",
         CLE_NOM,
         "le passif est joue par un APPEL IMPERATIF depuis un vecteur d'event, donc il n'a par "
         "construction AUCUNE entree de registre -- declare a son foyer (faux manquant mesure : "
         "`FireOfAbsolution`, porte en entier, #951-r2)",
         "dispatch.ability.evaluate_abilities_for_event"),
    Voie("engine.runner.operations.behaviour", "BEHAVIOUR_TRAIT_TRIGGERS", CLE_NOM,
         "registre trait -> trigger(s) des mecaniques de COMPORTEMENT, fusionne lazily avec "
         "`TRAIT_TRIGGERS` (le lazy evite le cycle behaviour<->triggers)",
         "collect_triggered_abilities"),
    # --- les operations qui montent un effet de l'item -----------------------------------------
    Voie("engine.runner.operations.triggers.bond_removal", "BOND_REMOVAL_GATES", "EffectType",
         "les gates de retrait du LIEN pose par l'item (taunt, possession, transfert) sont "
         "portes : sans eux l'effet ne se retire jamais",
         "runner.operations.triggers.bond_removal"),
    Voie("engine.runner.operations.triggers.pending_attack", "PENDING_ATTACK_EFFECTS", "EffectType",
         "l'effet d'ATTAQUE DIFFEREE pose par l'item porte sa spec (patron 2-PHASES : le cast pose "
         "l'effet, le degat tombe a la phase 2)",
         "runner.operations.triggers.pending_attack"),
    Voie("engine.runner.abilities.loki.additional_targets", "NORMAL_ATTACK_CLEAVES", CLE_NOM,
         "le passif fait CLEAVER l'attaque normale substituee de son porteur "
         "(`<X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior`) ; meme clef et meme "
         "substrat d'entite que `CUSTOM_NORMAL_ATTACK_BY_PASSIVE`",
         "runner.abilities.loki.additional_targets"),
    Voie("engine.services.custom_normal_attack", "CUSTOM_NORMAL_ATTACK_BY_PASSIVE", CLE_NOM,
         "4e voie d'un PASSIF (#925) : il SUBSTITUE l'attaque normale de son porteur au lieu de "
         "poser un trigger ou un effet -- `Boltstorm` n'a NI `CreateTrigger` NI `CreateBehaviour`, "
         "donc aucun registre de trigger ne peut le voir, quel que soit l'etat du port",
         "UnitFactory$$AddNormalAttackAbility cote port"),
    Voie("engine.runner.abilities.handler", "ABILITY_CLASSES", "ActiveAbilityType",
         "le registre d'EXECUTION des actives : un `ActiveAbilityType` absent fait un NO-OP "
         "SILENCIEUX au cast. Une voie conditionnelle peut etre une active (`Maugetar` est portee "
         "en `activeAbilities` par un npc), d'ou sa presence ici",
         "AbilityHandler.visit_ActiveAbilityMessage"),
]


#: Les conteneurs du PERIMETRE qui DESIGNENT un item de kit sans le MONTER. Chacun sa RAISON --
#: c'est ce qui distingue un ecart raisonne d'un oubli. `--tout` imprime en plus, pour chacun, le
#: nombre d'items qu'il ferait BASCULER s'il etait inscrit : un ecart couteux devient visible.
ECARTES: dict[tuple[str, str], str] = {
    # --- FAITS NATIFS recenses : y figurer ne monte RIEN -----------------------------------------
    ("engine.runner.abilities.attack_type", "REGULAR_ATTACK_ABILITY_TYPES"):
        "FAIT NATIF : l'`OrderedSet` du `.cctor` que lit `ActiveAbility$$IsRegularAttack`. "
        "Transcription verbatim d'un predicat natif, aucun montage.",
    ("engine.runner.abilities.attack_type", "NOT_ACTIVE_ABILITY_TYPES"):
        "FAIT NATIF : les cinq litteraux qu'`IsActiveAbility` exclut. C'est une EXCLUSION -- "
        "y figurer dit le contraire d'un montage.",
    ("engine.runner.abilities.base", "NO_ABILITY_USED_FLAG_ABILITY_TYPES"):
        "FAIT NATIF : les classes qui overrident `SetsActiveAbilityUsedFlag`. Donnee de flag "
        "d'une active montee ailleurs (`ABILITY_CLASSES`).",
    ("engine.runner.abilities.base", "NO_END_TURN_ABILITY_TYPES"):
        "FAIT NATIF : les classes qui overrident `SetsEndTurnFlags`. Meme statut que son voisin.",
    ("engine.runner.abilities.repair", "REGULAR_REPAIR_IDS"):
        "FAIT NATIF : les DEUX valeurs comparees par `ActiveAbility$$IsRegularRepair`.",
    ("engine.runner.operations.effects", "_DEFAULT_ROUNDS"):
        "FAIT NATIF : la table `StaticBattleRules.Effect$$DefaultAmountOfRounds`. Une duree par "
        "defaut ne dit rien de la presence d'une classe d'effet.",
    ("engine.runner.operations.triggers.loki.fuelled_by_fury", "ABILITY_COUNTED_ONCE_PER_BATTLE"):
        "FAIT NATIF : le `HashSet` du `.cctor` que lit "
        "`ShouldAbilityOnlyBeCountedOncePerBattleAbility`.",
    ("engine.runner.operations.triggers.tiles", "LIGHT_COVER_EXCLUDED_TRAITS"):
        "FAIT NATIF : les traits que le `.cctor` de `LightCoverAbility` EXCLUT du cover. "
        "Exclusion, pas montage.",
    ("engine.services.movement_query", "SPECIAL_MOVEMENT_EFFECT_TYPES"):
        "FAIT NATIF : les quatre etats << je descends du ciel >> testes, DANS L'ORDRE du "
        "decompile. Table de routage de pathfinder, pas un montage d'item.",
    ("engine.services.movement_query", "SPECIAL_MOVEMENT_PATHFINDER_TYPES"):
        "FAIT NATIF : les huit `PathfinderType` que rend la branche MOUVEMENT SPECIAL. Ses "
        "VALEURS sont d'un autre enum encore, et ses clefs sont celles du voisin ci-dessus.",
    ("engine.services.static_battle_rules", "TILE_STATUS_EFFECT_TYPES"):
        "FAIT NATIF : les effets de STATUT DE TUILE. Aucun n'est monte par un item de kit -- ils "
        "sont poses par le terrain.",
    ("engine.runner.components", "_TELEPORT_MOVE_EFFECTS"):
        "FAIT NATIF : les quatre effets dont la presence fait qu'un move est un TELEPORT "
        "(`IsTeleporting`). C'est une LECTURE d'etat, pas la pose de l'effet.",
    # --- NEGATIONS d'inscription : elles disent explicitement que RIEN n'est monte ---------------
    ("engine.runner.abilities.targeting", "TARGETING_OPTIONS_UNPORTED"):
        "NEGATION : le module l'ecrit -- cette table porte le masque des abilities dont la "
        "behaviour est un NO-OP, et son CONTRAT est d'etre DISJOINTE d'`ABILITY_CLASSES`. "
        "L'inscrire compterait porte exactement ce qui ne l'est pas.",
    ("engine.runner.operations.traits", "_TRAITS_WITH_DERIVED_ABILITIES"):
        "NEGATION : le module l'ecrit -- << l'etage n'est PAS porte : ce jeu sert a REFUSER en "
        "silence-zero plutot qu'a l'ignorer >>. Mesure : l'inscrire ferait basculer `Healer` "
        "(6 porteurs lineup, le total ENTIER de l'audit) sur un etage que personne ne porte.",
    # --- DONNEES ANNEXES d'un item deja monte ailleurs -------------------------------------------
    ("engine.runner.abilities.attack_type", "ABILITY_ATTACK_TYPE"):
        "DONNEE ANNEXE : le 3e argument d'`AActiveAbility$$.ctor`, pose DANS LE MEME COMMIT que "
        "l'entree d'`ABILITY_CLASSES` (doctrine CLAUDE.md). C'est cette derniere qui monte "
        "l'ability ; celle-ci la parametre.",
    ("engine.runner.abilities.targeting", "NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE"):
        "DONNEE ANNEXE : le masque de ciblage de l'ATTAQUE NORMALE par type. Parametre un "
        "montage, ne l'etablit pas.",
    ("engine.services.ability_caster_gates", "DYNAMIC_CASTER_GATE_BY_ABILITY"):
        "DONNEE ANNEXE : le regime de la regle-delegue CASTER d'une ability. Son propre en-tete "
        "renvoie a la meme regle qu'`ABILITY_ATTACK_TYPE` -- inscrite dans le meme commit que le "
        "port, jamais a sa place.",
    ("engine.services.ability_range", "DYNAMIC_TARGET_GATE_BY_ABILITY"):
        "DONNEE ANNEXE : le regime du gate de portee. Une entree ABSENTE signifie `GATE_NONE`, "
        "donc l'absence n'est pas un manque -- et la presence n'est pas un montage.",
    ("engine.runner.operations.triggers.loki.cursed_plague_bell", "AURA_TRAIT_BY_EFFECT"):
        "DONNEE ANNEXE : le `IAuraEffect.GetTrait()` d'UN effect-def, lu pour une formule d'aura.",
    ("engine.runner.operations.triggers.loki.fury_from_the_delve", "FURY_PERSISTENT_KEY"):
        "DONNEE ANNEXE : une clef composite `(abilityOrEffect, dataKey)` du sac persistant. "
        "L'ability est montee par son registre de trigger ; ceci n'est qu'une adresse de stockage.",
    ("engine.runner.operations.triggers.loki.my_will_be_done_overlord", "PERSISTENT_DATA_KEY"):
        "DONNEE ANNEXE : meme forme que son voisin ci-dessus.",
    ("engine.runner.abilities.behaviours.lifecycle", "TRIGGERED_ABILITY_BEHAVIOURS"):
        "DONNEE ANNEXE : l'ARBRE de behaviour d'une triggered DEJA montee par son registre. Le "
        "dict est peuple A L'IMPORT par les modules d'abilities, donc son contenu SUIT le port au "
        "lieu de l'etablir -- aucun item n'y arrive seul (mesure : 0 bascule).",
    ("engine.runner.abilities.behaviours.lifecycle", "TRIGGERED_ABILITY_DELAYED_BEHAVIOURS"):
        "DONNEE ANNEXE : meme forme, pour les arbres declenchables par `TriggerAbilityDelayed`.",
    ("engine.entities.effects.factory", "TERTIARY_ABILITY_POSED_EFFECTS"):
        "DONNEE ANNEXE (#1038) : quel `AbilityStateReference` RE-BAKER pour un effet qu'une "
        "tertiaire pose SUR AUTRUI (level 1..4 / mult 100 de la SOURCE, et non le couple des "
        "passifs du PORTEUR). C'est une correction de NIVEAU sur un effet deja monte -- le montage, "
        "lui, est etabli par la classe d'effet (`EFFECT_CLASSES`). Mesure : 0 bascule, son unique "
        "item (`MastersOfManoeuvre`) etant deja PORTE par cette voie-la. "
        "⚠ CE CONTENEUR EST ARRIVE PENDANT LA TRANCHE #1041, livre par un autre agent, et il est "
        "sorti MUET tout seul -- c'est exactement le mode de defaillance que la liste blanche "
        "laissait passer en silence.",
    # --- AUTRE AXE : ces conteneurs ont deja leur foyer, et deux foyers se contrediraient ---------
    ("engine.runner.components", "NOT_DISPLACEABLE_TRAITS"):
        "AUTRE AXE (trait) : les trois traits refuses par `UnitExtensions$$IsDisplaceable`. Une "
        "LECTURE de trait releve de `trait_channels` (#1015), dont c'est precisement le canal "
        "dominant ; la compter ici la compterait deux fois.",
    ("engine.runner.operations.summon_ai", "AUTOMATIC_TRAITS"):
        "AUTRE AXE (trait) : les deux traits testes par `UnitExtensions$$IsAutomatic`. Meme "
        "raison que ci-dessus.",
    ("engine.runner.operations.triggers.loki.control_edict", "SUMMON_TRAITS"):
        "AUTRE AXE (trait) : l'intersection de traits d'UN selecteur natif.",
    ("engine.services.static_battle_rules", "_MOVEMENT_EXEMPT_TRAIT_IDS"):
        "AUTRE AXE (trait) : les traits exemptes de la penalite de mouvement.",
}


# ============================================================================================
#  Le perimetre, visite
# ============================================================================================

def _fichiers_du_perimetre() -> list[str]:
    out = []
    for rel in PERIMETRE:
        p = os.path.join(_PYROOT, rel.replace("/", os.sep))
        if os.path.isdir(p):
            for racine, _dirs, fics in os.walk(p):
                out += [os.path.join(racine, f) for f in fics if f.endswith(".py")]
        elif os.path.exists(p):
            out.append(p)
    return sorted(out)


def _nom_de_module(path: str) -> str:
    rel = os.path.relpath(path, _PYROOT).replace(os.sep, "/")[:-3]
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    return rel.replace("/", ".")


def conteneurs_du_perimetre() -> list[tuple[str, str]]:
    """`(module, NOM)` de tout conteneur de niveau module a nom MAJUSCULE du perimetre.

    Par AST : le nom se lit sans importer, donc l'inventaire reste lisible meme si un module casse.
    La VALEUR, elle, exige l'import (cf. `elements`)."""
    out = []
    for path in _fichiers_du_perimetre():
        mod = _nom_de_module(path)
        with open(path, encoding="utf-8") as f:
            arbre = ast.parse(f.read())
        for n in arbre.body:
            if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                continue
            cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in cibles:
                if isinstance(t, ast.Name) and t.id.isupper():
                    out.append((mod, t.id))
    return sorted(set(out))


def elements(mod: str, attr: str):
    """Les elements a confronter : les CLES d'un dict, les membres d'un set/tuple/list. `None` si
    l'attribut n'est pas un conteneur (ou n'existe plus)."""
    v = getattr(importlib.import_module(mod), attr, None)
    if isinstance(v, dict):
        return list(v.keys())
    if isinstance(v, (set, frozenset, tuple, list)):
        return list(v)
    return None


# ============================================================================================
#  Les items de kit, et l'appariement
# ============================================================================================

@functools.lru_cache(maxsize=1)
def items_de_kit() -> frozenset:
    """Tous les NOMS que `audit_kit_coverage` interroge : `activeAbilities`, `passiveAbilities`,
    traits, et les deux voies CONDITIONNELLES (`mythic`, `item`), sur TOUT le parc.

    Le parc entier et non les seules `lineup` : une voie est une voie quel que soit le porteur, et
    borner ici ferait dependre la partition du kind, qui ment (cf. gate de confrontabilite).

    ⚠ CACHE, et le decoupage n'est pas indifferent : c'est le GAMECONFIG qui est cache ici, jamais
    les REGISTRES. `voies_par_item` les relit a chaque appel, sans quoi le predicat deviendrait
    INSENSIBLE a une mutation de registre -- et c'est un regime mesure : trois etages de
    `test_951r2_voies_de_couverture_offline` (qui retirent une entree et exigent que la couverture
    tombe) sont passes au ROUGE quand un instantane fige avait ete pris a l'import."""
    import gameconfig as GC
    import unit_map as UM
    noms = set()
    for k in UM.all_kits():
        u = GC.unit(k["id"]) or {}
        for cle in ("activeAbilities", "passiveAbilities", "traits"):
            for nm in (u.get(cle) or []):
                noms.add(nm)
        for voie in ("mythic", "item"):
            for nm in (k.get("voies") or {}).get(voie, []):
                noms.add(nm)
    return frozenset(noms)


def _tables() -> dict:
    import enum_maps as EM
    return {"ActiveAbilityType": EM.ACTIVE_ABILITY_TYPE,
            "TriggeredAbilityType": EM.PASSIVE_ABILITY_TYPE,
            "EffectType": EM.EFFECT_TYPE}


def nom_designe(el, cle: str, tables: dict) -> "str | None":
    """Le NOM que cet element designe SOUS LA CLEF DECLAREE, ou `None`.

    `bool` est exclu : c'est un `int` en Python, et `True` vaudrait l'ordinal 1."""
    if isinstance(el, bool):
        return None
    if cle == CLE_NOM:
        return el if isinstance(el, str) else None
    if isinstance(el, int):
        return tables[cle].get(int(el))
    return None


def _resout_quelque_part(el, tables: dict, items: set) -> bool:
    """FILTRE du perimetre, deliberement PERMISSIF : l'element designe-t-il un item par N'IMPORTE
    laquelle des resolutions ? Il ne sert qu'a ECARTER ce qui ne parle pas d'items ; l'appariement
    reel, lui, n'utilise que l'enum DECLARE. Un filtre permissif laisse plus de conteneurs a
    trancher, jamais moins -- c'est le sens sur : il ne peut pas cacher une voie."""
    if isinstance(el, bool):
        return False
    if isinstance(el, str):
        return _item_de(el, items) is not None
    if isinstance(el, int):
        for lib in _LIBELLES_ENUM:
            nm = tables[lib].get(int(el))
            if nm and _item_de(nm, items) is not None:
                return True
    return False


def _item_de(nom: str, items: set) -> "str | None":
    """L'item de kit que ce nom designe : EGALITE, ou PREFIXE `<item>_` (convention de nommage du
    port, cf. docstring du module). Le plus LONG item gagne, pour qu'un item dont le nom est le
    prefixe d'un autre ne capte pas les derives du second."""
    if nom in items:
        return nom
    gagnant = None
    for it in items:
        if nom.startswith(it + "_") and (gagnant is None or len(it) > len(gagnant)):
            gagnant = it
    return gagnant


# ============================================================================================
#  La partition
# ============================================================================================

def partition() -> dict:
    """La PARTITION du perimetre. Rien n'en sort sans etiquette :

      inscrits   -- (mod, attr) present dans `VOIES`
      ecartes    -- present dans `ECARTES`, donc avec sa raison ecrite
      muets      -- designe un item de kit, et NI l'un NI l'autre  ==> le cliquet ROUGIT
      hors_sujet -- aucun element ne designe un item (compte imprime, liste sur `--tout`)
      inertes    -- l'attribut n'est pas un conteneur, ou il est VIDE
      fantomes   -- inscrit dans `VOIES`/`ECARTES` mais introuvable dans le perimetre
    """
    tables, items = _tables(), items_de_kit()
    v_ids = {v.id for v in VOIES}
    vus = set()
    out = {"inscrits": [], "ecartes": [], "muets": [], "hors_sujet": [], "inertes": [],
           "fantomes": []}
    for mod, attr in conteneurs_du_perimetre():
        vus.add((mod, attr))
        els = elements(mod, attr)
        if not els:
            out["inertes"].append((mod, attr))
            continue
        n_ok = sum(1 for e in els if _resout_quelque_part(e, tables, items))
        if (mod, attr) in v_ids:
            out["inscrits"].append((mod, attr, n_ok, len(els)))
        elif (mod, attr) in ECARTES:
            out["ecartes"].append((mod, attr, n_ok, len(els)))
        elif n_ok == 0:
            out["hors_sujet"].append((mod, attr, len(els)))
        else:
            out["muets"].append((mod, attr, n_ok, len(els)))
    for cle in sorted(v_ids | set(ECARTES)):
        if cle not in vus:
            out["fantomes"].append(cle)
    return out


# ============================================================================================
#  Ce que les consommateurs (audit_kit_coverage) appellent
# ============================================================================================

def _gate_passe(v: Voie, valeur) -> bool:
    """Le GATE de cette voie passe-t-il pour CETTE entree ? (cf. `GATE_EFFET_CLASSE`.)"""
    if v.gate is None:
        return True
    from engine.entities.effects.factory import EFFECT_CLASSES
    cibles = valeur if isinstance(valeur, (list, tuple, set, frozenset)) else [valeur]
    return any(isinstance(c, str) and c in EFFECT_CLASSES for c in cibles)


def voies_par_item() -> dict:
    """`nom d'item de kit -> {"portee": [voies], "gate_tombe": [(voie, raison)]}`.

    Tous les ordinaux sont resolus SOUS LA CLEF DECLAREE de chaque voie -- jamais dans les trois
    enums, sans quoi 4 bascules sur 5 sont fausses (cf. docstring du module)."""
    tables, items = _tables(), items_de_kit()
    out: dict[str, dict] = {}
    for v in VOIES:
        conteneur = getattr(importlib.import_module(v.mod), v.attr, None)
        for el in (elements(v.mod, v.attr) or []):
            nom = nom_designe(el, v.cle, tables)
            if nom is None:
                continue
            it = _item_de(nom, items)
            if it is None:
                continue
            e = out.setdefault(it, {"portee": [], "gate_tombe": []})
            valeur = conteneur.get(el) if isinstance(conteneur, dict) else None
            if _gate_passe(v, valeur):
                if v.attr not in e["portee"]:
                    e["portee"].append(v.attr)
            elif v.attr not in [a for a, _r in e["gate_tombe"]]:
                e["gate_tombe"].append((v.attr, v.gate))
    for e in out.values():
        e["portee"].sort()
        e["gate_tombe"].sort()
    return out


#: Les TROIS etats d'un item de kit. `PARTIEL` n'est PAS un demi-`PORTE` a arrondir : c'est
#: << le montage est DECLARE mais rien ne s'execute >>, et le rabattre d'un cote ou de l'autre
#: rend le compte inexploitable (il fait soit renoncer, soit re-dispatcher).
PORTE, PARTIEL, ABSENT = "PORTE", "PARTIEL", "ABSENT"


def etat(nm: str, table=None) -> tuple:
    """L'etat TERNAIRE de cet item : `(PORTE|PARTIEL|ABSENT, detail)`.

    `PARTIEL` = des voies le DESIGNENT, mais TOUTES ont leur gate tombe -- typiquement une pose
    d'owner-effect dont la cible n'a aucune classe. Il reste du travail, et le detail dit lequel."""
    e = (table if table is not None else voies_par_item()).get(nm)
    if e is None:
        return ABSENT, ""
    if e["portee"]:
        return PORTE, ",".join(e["portee"])
    if e["gate_tombe"]:
        return PARTIEL, ",".join("%s(%s)" % (a, r) for a, r in e["gate_tombe"])
    return ABSENT, ""


def item_porte(nm: str, table=None) -> list:
    """Les VOIES qui montent EFFECTIVEMENT cet item (gate passe). Liste VIDE = non monte -- mais
    l'item peut etre PARTIEL (cf. `etat`) ou avoir un verdict ATTESTE (`coverage_attestations`)."""
    e = (table if table is not None else voies_par_item()).get(nm)
    return list(e["portee"]) if e else []


# ============================================================================================
#  CLI / cliquet
# ============================================================================================

def _bascules_si_inscrit(mod: str, attr: str, tables: dict, items: set, deja: dict) -> list:
    """Les items qu'un ECARTE ferait basculer s'il etait inscrit -- sous CHAQUE clef possible,
    puisqu'un ecarte n'en declare aucune. C'est ce qui rend l'ecart falsifiable : un ecart qui
    couterait une bascule se VOIT, au lieu d'etre un jugement invisible."""
    out = set()
    for cle in (CLE_NOM,) + _LIBELLES_ENUM:
        for el in (elements(mod, attr) or []):
            nom = nom_designe(el, cle, tables)
            if nom is None:
                continue
            it = _item_de(nom, items)
            if it is not None and not (deja.get(it) or {}).get("portee"):
                out.add(it)
    return sorted(out)


def main() -> int:
    tout = "--tout" in sys.argv
    p = partition()
    tables, items = _tables(), items_de_kit()
    par_item = voies_par_item()

    print("[1041] PARTITION du perimetre des voies de montage COMBAT d'un item de kit")
    print("   perimetre : %s" % ", ".join(PERIMETRE))
    print("   fichiers visites            : %d" % len(_fichiers_du_perimetre()))
    print("   conteneurs de niveau module : %d" % len(conteneurs_du_perimetre()))
    print("   INSCRITS (VOIES)            : %d" % len(p["inscrits"]))
    print("   ECARTES AVEC RAISON         : %d" % len(p["ecartes"]))
    print("   MUETS                       : %d" % len(p["muets"]))
    print("   ECARTES PAR CE FILTRE (aucun element ne designe un item de kit) : %d"
          % len(p["hors_sujet"]))
    print("   inertes (non-conteneur ou vide) : %d" % len(p["inertes"]))
    if p["fantomes"]:
        print("   FANTOMES (inscrits mais introuvables) : %d" % len(p["fantomes"]))
        for mod, attr in p["fantomes"]:
            print("      %s.%s" % (mod, attr))
    for mod, attr, n_ok, n in p["muets"]:
        print("   MUET   %s.%s -- %d/%d elements designent un item de kit, et il n'est NI inscrit "
              "dans VOIES NI ecarte avec sa raison" % (mod, attr, n_ok, n))

    etats = {nm: etat(nm, par_item)[0] for nm in items}
    n_porte = sum(1 for e in etats.values() if e == PORTE)
    n_part = sum(1 for e in etats.values() if e == PARTIEL)
    print("\n[1041] items de kit du parc : %d -- PORTE %d / PARTIEL %d / ABSENT %d"
          % (len(items), n_porte, n_part, len(items) - n_porte - n_part))
    exact = sum(1 for nm, e in par_item.items()
                if e["portee"] and any(
                    nom_designe(el, v.cle, tables) == nm
                    for v in VOIES if v.attr in e["portee"]
                    for el in (elements(v.mod, v.attr) or [])))
    print("   apparies par EGALITE : %d ; par PREFIXE `<item>_` SEULEMENT : %d"
          % (exact, n_porte - exact))
    if n_part:
        print("   PARTIELS (montage declare, rien ne s'execute) :")
        for nm in sorted(nm for nm, e in etats.items() if e == PARTIEL):
            print("      %-30s %s" % (nm, etat(nm, par_item)[1]))

    if tout:
        print("\n   -- INSCRITS")
        for mod, attr, n_ok, n in sorted(p["inscrits"]):
            v = next(x for x in VOIES if x.id == (mod, attr))
            print("      %-52s %-38s %4d/%4d  cle=%-22s gate=%s"
                  % (mod, attr, n_ok, n, v.cle, v.gate or "-"))
        print("   -- ECARTES (colonne `bascules` = ce que l'ecart coute)")
        for mod, attr, n_ok, n in sorted(p["ecartes"]):
            b = _bascules_si_inscrit(mod, attr, tables, items, par_item)
            print("      %-52s %-38s %4d/%4d  bascules=%d%s"
                  % (mod, attr, n_ok, n, len(b), (" -> " + ", ".join(b)) if b else ""))
        print("   -- ECARTES PAR LE FILTRE")
        for mod, attr, n in sorted(p["hors_sujet"]):
            print("      %-52s %-38s    0/%4d" % (mod, attr, n))
    return 1 if (p["muets"] or p["fantomes"]) else 0


if __name__ == "__main__":
    sys.exit(main())
