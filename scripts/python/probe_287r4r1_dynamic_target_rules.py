"""#287-r4-r1 -- MESURE des REGLES DYNAMIQUES DE CIBLE portees, et de celles qui ne le sont pas.

CE QUE CE PROBE MESURE. Sous le bit `TargetingRule.TargetMatchesDynamicRule`, la surcharge
7 arguments de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` invoque le delegue
`options+0x38`, que `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` a lie au slot de vtable
`+0x480` de la SOUS-CLASSE -- soit `<X>Ability$$GetDynamicInvalidTargetReason`. #287-r4 a rendu ce
delegue APPELABLE cote port (bug de typage : une CLASSE la ou une INSTANCE etait requise) ; il
repondait alors `0` pour la quasi-totalite des ids, faute d'avoir porte les CORPS. C'est ce que
cette tranche corrige, et ce que ce probe mesure.

QUATRE MESURES, toutes OFFLINE (aucun runner, aucune session Frida) :

  1. RECENSEMENT PAR EVALUABILITE -- et non par VOIE. `probe_287r4` ventile les 65 ids par la
     maniere dont le porteur est FABRIQUE (classe du registre / `UnportedAbilityTargeting`) ; ce
     critere-la ne dit RIEN de la regle. Ici on demande : le port sait-il EVALUER ce corps ? Trois
     etats -- surcharge dans la classe portee / entree de `DYNAMIC_TARGET_RULE_UNPORTED` / AUCUNE
     (le `0` permissif, dette nommee). Le troisieme etat est IMPRIME avec son symbole natif, pour
     que le residu #287-r5 se lise dans la sortie et pas seulement dans une doc.

  2. BASCULE, regle par regle portee. Une regle qui rend toujours `0` serait indistinguable d'une
     regle absente : on exige donc, pour CHACUNE, un substrat qui REFUSE et un substrat qui ACCEPTE.
     Les deux substrats ne different que par la grandeur que le corps natif LIT (un trait, un effet,
     le camp de l'occupant), jamais par autre chose.

  3. MUTANTS -- un par regle portee. On DESARME la regle (la classe retrouve le defaut herite
     d'`ActiveAbility` ; la table perd son entree) et l'on exige que la bascule de l'etape 2
     S'EFFONDRE. Sans cet etage, l'etape 2 serait verte sur un port qui ne consulte plus rien.
     ⚠ `a_morde` est publie SEPAREMENT du verdict : une mutation que les donnees n'exercent pas se
     DECLARE, elle ne se compte pas verte.

  4. LE ROUGE DE #287-r4-r1, REPRODUIT OFFLINE. La divergence mesuree en live (`C1_02`/seed 28704,
     `necroWarden`, `AdaptiveStrategy` 1005 : natif `targetReason = TargetMatchesDynamicRule` et
     `UnitFlag.NoActionAvailable` POSE ; port `0`, flag absent) se rejoue ici sur
     `turnflow._has_valid_targets` -- le predicat d'`IdunBattle.Core.Services.AttackQuery$$HasValidTargets`,
     donc du flag. Deux bras a UN TRAIT d'ecart : allie HEROS -> aucune cible ; allie NON-HEROS ->
     une cible. C'est le chainon qui relie la regle au flag, et il est mesure, pas suppose.

⚠ SUBSTRAT NON DEGENERE, DELIBEREMENT. `probe_287r4` se contente de deux entites NUES et doit
neutraliser le volet caster pour ne pas etre vrai par vacuite. Ici le substrat porte un BOARD, des
positions et des traits MESURES (`combatSnapshot.units[].traits` -> `ctx.traits_measured`), donc le
caster a une tuile et le volet caster ne court-circuite rien : les etages descendent reellement
jusqu'a la regle dynamique. C'est ce qui permet a l'etape 4 de mesurer `_has_valid_targets` ENTIER,
volet caster compris, au lieu d'un fragment isole.

Usage :
    python scripts/python/probe_287r4r1_dynamic_target_rules.py
    python scripts/python/probe_287r4r1_dynamic_target_rules.py --ids     # detail id par id
ASCII only ; exit 0 = les regles portees mordent toutes, et aucune ne s'est mise a mentir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hexgeo                                                                    # noqa: E402
import engine.runner.operations.turnflow as TF                                   # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402
from engine.entities.effect_type import EffectType                               # noqa: E402
from engine.entities.pathfinding.board import Board                              # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                          # noqa: E402
from engine.runner.abilities.base import ActiveAbility                           # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                      # noqa: E402
import engine.runner.abilities.targeting as TG                                   # noqa: E402
from engine.runner.abilities.targeting import (                                  # noqa: E402
    TARGETING_OPTIONS_UNPORTED, UnportedAbilityTargeting, targeting_options_for,
)

# La table des regles de la voie NON PORTEE n'existe qu'A PARTIR de #287-r4-r1. Sur un arbre
# ANTERIEUR, l'importer par son nom ferait rougir ce probe sur un `ImportError` -- un rouge de
# STRUCTURE, qui ne prouve RIEN de la mecanique gardee (meme raison qui fait de `sans_volet_caster`
# un NO-OP dans `probe_287r4`). Le repli est donc un dict VIDE : c'est litteralement l'etat d'avant
# la tranche (aucune regle portee sur cette voie), et le probe MESURE alors une bascule qui ne
# discrimine pas -- le rouge de MECANIQUE qu'on veut voir.
DYNAMIC_TARGET_RULE_UNPORTED = getattr(TG, "DYNAMIC_TARGET_RULE_UNPORTED", {})
from engine.runner.abilities.targeting_rule import TargetingRule as TR           # noqa: E402
from engine.runner.snapshot import load_state                                    # noqa: E402

COLS = ROWS = 6
REFUS = int(TR.TargetMatchesDynamicRule)

# Les corps natifs NON portes, avec leur symbole -- residu #287-r5. La table est ecrite ici (et non
# derivee) parce qu'un symbole natif ne se devine pas d'un nom d'ability : chaque ligne a ete LUE
# dans `data/symbols/<build>/ghidra/functions.tsv`. `None` = aucune surcharge n'apparait dans la
# table de symboles -- ce qui NE PROUVE PAS qu'il n'y en a pas (IL2CPP deduplique les corps triviaux
# et n'attribue qu'UN proprietaire ; cf. CLAUDE.md), seulement que le port n'a rien a lire.
SYMBOLE_NATIF = {
    1006: None, 1014: None, 1016: "SendInTheNextWaveAbility", 1025: "SkyStrikeAbility",
    1027: None, 1035: None, 1036: None, 1041: None, 1044: None, 1048: None, 1051: None,
    1062: None, 1063: None, 1066: None, 1067: None, 1069: None,
    1076: "MV71SniperDroneSquadAttackAbility", 1078: None, 1080: None,
    1087: "ExemplarOfTheKauyonAbility", 1088: None, 1093: None, 1097: None, 1098: None,
    1101: "AttemptedPossessionAbility", 1103: None, 1104: None, 1112: "AlphaWarriorAbility",
    1113: None, 1150: None, 1151: "TheQuickeningAbility", 1164: "MindControlAbility",
    1168: "EntropyCannonsAbility", 1169: None, 1171: None, 1175: "BloodChaliceAbility",
    1177: "LightOfSanguiniusAbility", 1179: "CultDemagogueAbility",
    1180: "HeroicFusilladeAbility", 1185: "ForwardObserversAbility",
    1197: "ExcruciatingFrequenciesAbility", 1200: "SquigLaunchasAbility",
    1202: "VigilanceEternalAbility", 1204: "LeadingTheChargeAbility", 1206: None,
    1213: "DeathOnTheWindAbility",
}


def _nom(aid: int) -> str:
    try:
        return ActiveAbilityType(int(aid)).name
    except ValueError:
        return "<hors ActiveAbilityType>"


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board() -> Board:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return Board(out, adjacency="evenq")


def substrat(unites: list):
    """`State` runner a traits PILOTES. `unites` = (id, visualId, team, col, row, [UnitTrait...]).

    Les traits passent par le canal `combatSnapshot.units[].traits` (#264) -- celui que
    `snapshot._load_unit_traits` pose sur `ctx.traits` avec `traits_measured = True`, donc EXACTEMENT
    l'ensemble effectif que rend `IdunBattle.Entities.UnitExtensions$$HasTrait`. Les poser ainsi
    plutot que de choisir des `visualId` dont le kit gameconfig se trouve porter le bon trait rend la
    mesure INDEPENDANTE d'une evolution du catalogue."""
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": col, "row": row}, "effects": []}
        for (uid, vid, team, col, row, _tr) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 100, "hpMax": 100} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": [int(t) for t in tr]}
                      for (uid, _v, _t, _c, _r, tr) in unites]}
    return load_state(dv, ob, snap, board=_board())


def _porteur(aid: int):
    """L'objet que la cascade recevrait pour cet id -- meme construction que `_has_valid_targets`."""
    klass = ABILITY_CLASSES.get(int(aid))
    if klass is not None and getattr(klass, "TARGETING_OPTIONS", None) is not None:
        return klass()
    return UnportedAbilityTargeting(int(aid), targeting_options_for(aid))


# ================================================================================================
# 1. RECENSEMENT PAR EVALUABILITE
# ================================================================================================

def ids_portant_le_bit() -> list:
    out = []
    for aid in sorted(set(ABILITY_CLASSES) | set(TARGETING_OPTIONS_UNPORTED)):
        opts = targeting_options_for(aid)
        if opts is not None and opts.has(TR.TargetMatchesDynamicRule):
            out.append(int(aid))
    return out


# La PARTITION rendue par `evaluabilite`. Les deux etats du milieu sont des DEFAUTS ; ils existent
# pour etre VUS, pas pour etre tolerés -- cf. la docstring ci-dessous.
ETATS = ("surcharge", "table", "ambigu", "perdue", "aucune")
#: Les etats ou le port SAIT evaluer le corps natif. `ambigu` en fait partie : le verdict effectif
#: est bien rendu (par la surcharge), c'est la PROPRETE qui est en cause, pas la mecanique.
ETATS_EVALUABLES = ("surcharge", "table", "ambigu")


def evaluabilite(aid: int) -> str:
    """PARTITION -- tout id sort dans EXACTEMENT un des cinq `ETATS`, jamais implicitement.

    ⚠ Ce critere n'est PAS celui de `probe_287r4` (qui ventile par VOIE de fabrication du porteur).
    Une classe portee peut ne PAS surcharger, et une ability sans classe peut avoir sa regle : les
    deux axes sont independants, et c'est celui-ci qui dit ce que le port sait EVALUER.

    ⚠ ELLE PRESUMAIT, ELLE MESURE (#1015). La version d'avant testait la classe D'ABORD et rendait
    `table` dans le seul `else` : une entree de table doublee d'une classe portee etait donc
    INVISIBLE -- masquee par une priorite silencieuse. C'est exactement l'etat dans lequel #996 a
    laisse `1185 ForwardObservers` (entree conservee alors que sa classe la surchargeait), et
    personne ne pouvait le voir. Les deux etats de DEFAUT ci-dessous sont la reponse : la
    contradiction sort sous un libelle, au lieu d'etre absorbee.

    Les deux booleens qui decident sont MESURES, pas supposes :

      `voie_classe` -- `_porteur(aid)` rendra-t-il la CLASSE ? C'est la meme condition, mot pour mot
        (`klass.TARGETING_OPTIONS is not None`). Quand elle est vraie, `UnportedAbilityTargeting`
        n'est JAMAIS construit pour cet id, donc l'entree de table est INATTEIGNABLE.
      `en_table`    -- l'id a-t-il une entree dans `DYNAMIC_TARGET_RULE_UNPORTED` ?

    Les cinq etats, et ce que chacun signifie :

      `surcharge` -- la classe portee surcharge. Canal nominal des behaviours portees.
      `table`     -- pas de classe portee ; le porteur non porte lit la table. Canal nominal de la
                     voie NON portee.
      `ambigu`    -- DEFAUT : les deux canaux declarent la regle. Le verdict vient de la surcharge,
                     l'entree de table est du code MORT -- deux mirrors du meme corps natif, dont un
                     seul est consulte, qui divergeront au premier correctif applique d'un seul cote.
      `perdue`    -- DEFAUT GRAVE : une entree de table existe, mais la classe portee capture le
                     porteur SANS surcharger. Le mirror est ecrit et jamais appele : l'id devient
                     PERMISSIF en silence, la degradation exacte que #287-r4-r1 avait pour but de
                     supprimer.
      `aucune`    -- le port n'evalue rien (le `0` permissif, dette nommee du residu #287-r5)."""
    klass = ABILITY_CLASSES.get(int(aid))
    voie_classe = klass is not None and getattr(klass, "TARGETING_OPTIONS", None) is not None
    en_table = int(aid) in DYNAMIC_TARGET_RULE_UNPORTED
    if not voie_classe:
        return "table" if en_table else "aucune"
    surcharge = (getattr(klass, "get_dynamic_invalid_target_reason", None)
                 is not ActiveAbility.get_dynamic_invalid_target_reason)
    if en_table:
        return "ambigu" if surcharge else "perdue"
    return "surcharge" if surcharge else "aucune"


# ================================================================================================
# 2. BASCULE -- un couple de substrats par regle portee
# ================================================================================================
# Chaque entree : (aid, libelle, substrat_qui_REFUSE, substrat_qui_ACCEPTE). Les deux ne different
# que par la grandeur LUE par le corps natif.

CASTER, CIBLE = 1, 2


def _cas_adaptive_strategy():
    """1005 -- `AdaptiveStrategyAbility$$GetDynamicInvalidTargetReason` : `HasTrait(target, Hero)`."""
    refuse = substrat([(CASTER, "necroWarden", 1, 0, 0, [UnitTrait.Hero]),
                       (CIBLE, "necroImmortal", 1, 1, 0, [UnitTrait.Hero])])
    passe = substrat([(CASTER, "necroWarden", 1, 0, 0, [UnitTrait.Hero]),
                      (CIBLE, "necroImmortal", 1, 1, 0, [UnitTrait.Mechanical])])
    return refuse, passe


def _cas_foul_infusion():
    """1038 -- `FoulInfusionAbility$$GetDynamicInvalidTargetReason` : `!HasTrait(target, Chaos)`.

    SENS INVERSE d'AdaptiveStrategy : ici c'est l'ABSENCE du trait qui refuse. Les deux entrees de
    la table sont donc des contre-epreuves l'une de l'autre -- une confusion de sens ferait rougir
    l'une des deux."""
    refuse = substrat([(CASTER, "deathPutrifier", 1, 0, 0, [UnitTrait.Chaos]),
                       (CIBLE, "deathPlagueMarine", 1, 1, 0, [UnitTrait.Imperial])])
    passe = substrat([(CASTER, "deathPutrifier", 1, 0, 0, [UnitTrait.Chaos]),
                      (CIBLE, "deathPlagueMarine", 1, 1, 0, [UnitTrait.Chaos])])
    return refuse, passe


def _cas_squig_mine():
    """1201 -- `SquigMineAbility$$GetDynamicInvalidTargetReason` : une unite `Steppable` sur la tuile
    (le SECOND terme ; le premier, l'effet `SquigMine_Tile`, a son propre bras plus bas)."""
    refuse = substrat([(CASTER, "orksRukkatrukk", 1, 0, 0, []),
                       (CIBLE, "orksSmnSquig", 2, 1, 0, [UnitTrait.Steppable])])
    passe = substrat([(CASTER, "orksRukkatrukk", 1, 0, 0, []),
                      (CIBLE, "orksOrkBoys", 2, 1, 0, [UnitTrait.Mechanical])])
    return refuse, passe


def _cas_spore_mine_launcher():
    """1145 -- `SporeMineLauncherAbility$$GetDynamicInvalidTargetReason` : `Steppable` **ET** ENNEMI.

    Le bras ACCEPTE garde le trait `Steppable` et ne change QUE le camp : c'est ce qui separe cette
    regle de celle de SquigMine, dont le terme steppable ignore le camp. Sans ce choix, les deux
    regles seraient indistinguables par leur bascule."""
    refuse = substrat([(CASTER, "tyranBiovore", 1, 0, 0, []),
                       (CIBLE, "tyranSmnSporeMine", 2, 1, 0, [UnitTrait.Steppable])])
    passe = substrat([(CASTER, "tyranBiovore", 1, 0, 0, []),
                      (CIBLE, "tyranSmnSporeMine", 1, 1, 0, [UnitTrait.Steppable])])
    return refuse, passe


def _cas_squig_mine_effet():
    """1201, PREMIER terme -- `HasEffect(target, SquigMine_Tile)`. Bras separe : les deux termes du
    `||` natif doivent mordre CHACUN, sinon un seul porterait la bascule et l'autre pourrait
    disparaitre sans que rien ne rougisse."""
    from engine.entities.effects_state import EffectsState
    refuse = substrat([(CASTER, "orksRukkatrukk", 1, 0, 0, []),
                       (CIBLE, "orksOrkBoys", 2, 1, 0, [UnitTrait.Mechanical])])
    if refuse.effects is None:
        refuse.effects = EffectsState()
    refuse.effects.add_effect(CIBLE, _EffetMine(CIBLE))
    passe = substrat([(CASTER, "orksRukkatrukk", 1, 0, 0, []),
                      (CIBLE, "orksOrkBoys", 2, 1, 0, [UnitTrait.Mechanical])])
    if passe.effects is None:
        passe.effects = EffectsState()
    return refuse, passe


def _cas_forward_observers():
    """1185 -- `ForwardObserversAbility$$GetDynamicInvalidTargetReason` : `HasEffect(target, 0x462 =
    EffectType.Markerlight, onlyActive: false)` -> on ne RE-marque pas une cible deja marquee.

    ⚠ CE BRAS A CHANGE DE CANAL, ET C'EST LA CAUSE DU ROUGE DE `master` (#1015). Il etait le SEUL a
    exercer le canal `table` ; #996 (`b061a916`) a porte la face COMBAT de 1185, donc `_porteur(1185)`
    rend desormais `tau.ForwardObserversAbility` et ce bras exerce le canal `surcharge`, comme les
    cinq autres. La table est du coup VIDE -- ce qui a fait tomber les gardes ecrites en « les deux
    canaux sont PEUPLES ».

    Le peuplement de `table` n'est donc PAS une propriete a garder ici : il suit la cadence de
    portage et retombera a zero chaque fois qu'on aura fini de porter. Ce qui se garde, c'est que le
    cablage soit ARME -- teste a table vide par une entree TEMOIN
    (`test_287r4r1_dynamic_target_rules_offline::test_le_cablage_de_la_table_est_ARME`)."""
    from engine.entities.effects_state import EffectsState
    refuse = substrat([(CASTER, "tauNpc5StealthSuit", 1, 0, 0, []),
                       (CIBLE, "tauCrisis", 2, 1, 0, [])])
    if refuse.effects is None:
        refuse.effects = EffectsState()
    refuse.effects.add_effect(CIBLE, _EffetPorte(CIBLE, EffectType.Markerlight))
    passe = substrat([(CASTER, "tauNpc5StealthSuit", 1, 0, 0, []),
                      (CIBLE, "tauCrisis", 2, 1, 0, [])])
    if passe.effects is None:
        passe.effects = EffectsState()
    return refuse, passe


class _EffetPorte:
    """Porteur minimal d'un effet d'un `EffectType` donne sur une entite, pour l'`EffectsState`."""
    __slots__ = ("unit_id", "effect_type", "consumed", "source", "remaining_turns")

    def __init__(self, unit_id: int, effect_type):
        self.unit_id = int(unit_id)
        self.effect_type = int(effect_type)
        self.consumed = False
        self.source = None
        self.remaining_turns = 0


def _EffetMine(unit_id: int):
    """Porteur d'un `SquigMine_Tile` -- conserve comme nom d'appel du bras 1201."""
    return _EffetPorte(unit_id, EffectType.SquigMine_Tile)


CAS = [
    (int(ActiveAbilityType.AdaptiveStrategy), "trait Hero sur la cible", _cas_adaptive_strategy),
    (int(ActiveAbilityType.FoulInfusion), "trait Chaos ABSENT de la cible", _cas_foul_infusion),
    (int(ActiveAbilityType.SquigMine), "unite Steppable sur la tuile", _cas_squig_mine),
    (int(ActiveAbilityType.SquigMine), "effet SquigMine_Tile deja pose", _cas_squig_mine_effet),
    (int(ActiveAbilityType.SporeMineLauncher), "Steppable ENNEMI (vs allie)",
     _cas_spore_mine_launcher),
    (int(ActiveAbilityType.ForwardObservers), "effet Markerlight deja pose (canal TABLE)",
     _cas_forward_observers),
]


def mesurer_bascule() -> list:
    """Rend [(aid, libelle, raison_refus, raison_passe, discrimine)]."""
    out = []
    for aid, libelle, fabrique in CAS:
        st_refuse, st_passe = fabrique()
        ab = _porteur(aid)
        r1 = int(ab.get_dynamic_invalid_target_reason(st_refuse, CASTER, CIBLE) or 0)
        r2 = int(ab.get_dynamic_invalid_target_reason(st_passe, CASTER, CIBLE) or 0)
        out.append((aid, libelle, r1, r2, r1 == REFUS and r2 == 0))
    return out


# ================================================================================================
# 3. MUTANTS -- desarmer chaque regle, et exiger que la bascule s'effondre
# ================================================================================================

class desarme:
    """Retire la regle dynamique d'un id, des DEUX cotes (classe portee / table).

    C'est le mutant : le port revient a ce qu'il faisait AVANT cette tranche (`0` partout). Ce que
    la garde exige, c'est que la mesure de l'etape 2 le VOIE."""

    def __init__(self, aid: int):
        self.aid = int(aid)
        self.klass = ABILITY_CLASSES.get(self.aid)
        self.avait_table = self.aid in DYNAMIC_TARGET_RULE_UNPORTED
        self.avait_surcharge = False

    def __enter__(self):
        if self.avait_table:
            self.regle = DYNAMIC_TARGET_RULE_UNPORTED.pop(self.aid)
        if self.klass is not None and "get_dynamic_invalid_target_reason" in vars(self.klass):
            self.avait_surcharge = True
            self.surcharge = vars(self.klass)["get_dynamic_invalid_target_reason"]
            delattr(self.klass, "get_dynamic_invalid_target_reason")
        return self

    def __exit__(self, *exc):
        if self.avait_table:
            DYNAMIC_TARGET_RULE_UNPORTED[self.aid] = self.regle
        if self.avait_surcharge:
            setattr(self.klass, "get_dynamic_invalid_target_reason", self.surcharge)
        return False


def ids_sans_regle_portee() -> list:
    """Les ids qui posent le bit et dont AUCUN canal ne porte la regle (etat `aucune`).

    DERIVE, jamais ecrit en dur : c'est la lecon du rouge de #883-r1 (un id cite en dur dans un test
    avait migre de canal, et le test accusait un regime qui n'existait plus)."""
    return [a for a in ids_portant_le_bit() if evaluabilite(a) == "aucune"]


def ids_servis_par_la_voie_non_portee() -> list:
    """Les ids posant le bit pour lesquels `_porteur` rend REELLEMENT un `UnportedAbilityTargeting`
    -- les seuls qui puissent LIRE `DYNAMIC_TARGET_RULE_UNPORTED` en production.

    ⚠ IL EST VIDE AUJOURD'HUI, ET C'EST UN RESULTAT MESURE, PAS UN OUBLI (#1015). Les 80 ids qui
    posent `TargetMatchesDynamicRule` ont TOUS une classe portee avec son masque ; les 3 entrees
    restantes de `TARGETING_OPTIONS_UNPORTED` n'en posent aucune. Le canal `table` est donc
    doublement vide : sans entree, et sans lecteur. Il redevient atteignable des qu'un masque
    portant ce bit est lu AVANT que la behaviour soit portee -- le regime normal d'une reconnaissance
    de kit, et la raison pour laquelle le cablage se garde par une entree TEMOIN plutot que par le
    peuplement (cf. `entree_temoin`)."""
    return [a for a in ids_portant_le_bit()
            if isinstance(_porteur(a), UnportedAbilityTargeting)]


REFUS_TEMOIN = int(TR.TargetMatchesDynamicRule)


class entree_temoin:
    """Injecte une regle TEMOIN dans `DYNAMIC_TARGET_RULE_UNPORTED`, pour exercer le CABLAGE de la
    voie non portee QUAND LA TABLE EST VIDE (#1015).

    POURQUOI CE MECANISME EXISTE. Le canal `table` se vide par le travail accompli : chaque behaviour
    portee fait migrer sa regle en surcharge, et les huit qui y ont vecu sont toutes parties. Une
    garde ecrite « la table est PEUPLEE » expire donc toute seule -- c'est litteralement ce qui a
    rendu `master` rouge. Mais le cablage, lui, doit rester ARME : le jour ou un corps du residu
    #287-r5 sera mirrore sans que sa classe le soit, il entrera par ici, et personne ne re-testera
    la plomberie a ce moment-la.

    ⚠ CE QUE L'ID EST ICI, ET CE QU'IL N'EST PAS. Il ne sert qu'a INDEXER : le sujet mesure est le
    CABLAGE (`UnportedAbilityTargeting.get_dynamic_invalid_target_reason` lit-elle la table par son
    `ABILITY_TYPE` ?), et l'appelant construit ce porteur EXPLICITEMENT. On ne pretend donc pas que
    la voie non portee serve cet id en production -- `ids_servis_par_la_voie_non_portee()` mesure
    qu'elle n'en sert AUCUN aujourd'hui, et une premiere ecriture de cette docstring l'affirmait a
    tort. L'id est seulement pris dans `ids_sans_regle_portee()`, ce qui garantit le seul fait dont
    la mesure a besoin : aucune vraie regle n'est masquee par le temoin."""

    def __init__(self, aid: int, refus: int = REFUS_TEMOIN):
        self.aid = int(aid)
        self.refus = int(refus)
        self.vue = []          # les (state, caster, target) que la regle temoin a reellement recus

    def _regle(self, state, caster_id, target_id) -> int:
        self.vue.append((state, caster_id, target_id))
        return self.refus

    def __enter__(self):
        assert self.aid not in DYNAMIC_TARGET_RULE_UNPORTED, (
            "%d a DEJA une entree : le temoin masquerait une vraie regle" % self.aid)
        DYNAMIC_TARGET_RULE_UNPORTED[self.aid] = self._regle
        return self

    def __exit__(self, *exc):
        DYNAMIC_TARGET_RULE_UNPORTED.pop(self.aid, None)
        return False


def canaux_exerces() -> set:
    """Les canaux d'evaluabilite que les bras de `CAS` exercent REELLEMENT.

    C'est le pendant mesure de `canaux_peuples` : les gardes confrontent les deux ensembles, au lieu
    d'exiger d'un canal nomme en dur qu'il soit peuple."""
    return {evaluabilite(aid) for aid, _l, _f in CAS}


def mesurer_mutants() -> list:
    """Rend [(aid, libelle, a_morde, avant, apres)].

    `a_morde` = la mutation a CHANGE le verdict (`avant != apres`), et pas seulement « apres vaut
    0 ». La difference n'est pas theorique : re-mesure du 2026-08-06 sur l'arbre d'AVANT la tranche,
    le critere `apres == 0` rendait **5/5 a_morde** alors qu'AUCUNE regle n'y etait portee -- la
    mutation ne retirait rien, et son inertie se comptait comme un vert. C'est exactement le faux
    vert que le mandat interdit : une mutation que les donnees n'exercent pas se DECLARE.

    On exige donc les deux faces : `avant` REFUSE et `apres` ne refuse plus."""
    out = []
    for aid, libelle, fabrique in CAS:
        st_refuse, _ = fabrique()
        avant = int(_porteur(aid).get_dynamic_invalid_target_reason(st_refuse, CASTER, CIBLE) or 0)
        with desarme(aid):
            apres = int(_porteur(aid).get_dynamic_invalid_target_reason(
                st_refuse, CASTER, CIBLE) or 0)
        out.append((aid, libelle, avant == REFUS and apres == 0, avant, apres))
    return out


# ================================================================================================
# 4. LE ROUGE, REPRODUIT -- de la regle jusqu'au predicat du flag
# ================================================================================================

def temoin_has_valid_targets() -> dict:
    """`turnflow._has_valid_targets` sur les DEUX bras d'AdaptiveStrategy, a UN TRAIT d'ecart.

    C'est le chainon complet : masque -> cascade -> regle dynamique -> predicat
    d'`AttackQuery$$HasValidTargets`, donc du flag `UnitFlag.NoActionAvailable`. Le substrat porte un
    board et des positions ADJACENTES (le masque de 1005 pose `range = TargetingRange` statics+0x30
    = ADJACENT), donc aucun etage amont ne court-circuite avant la regle."""
    aid = int(ActiveAbilityType.AdaptiveStrategy)
    refuse, passe = _cas_adaptive_strategy()
    return {"tous_heros": TF._has_valid_targets(refuse, CASTER, aid),
            "un_non_heros": TF._has_valid_targets(passe, CASTER, aid)}


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r4-r1 : les regles dynamiques de ciblage")
    ap.add_argument("--ids", action="store_true", help="detail id par id")
    args = ap.parse_args()

    ids = ids_portant_le_bit()
    par_etat = {e: [] for e in ETATS}
    for aid in ids:
        par_etat[evaluabilite(aid)].append(aid)
    print("[287-r4-r1] RECENSEMENT -- la regle dynamique est-elle EVALUABLE ?")
    print("  ids posant TargetMatchesDynamicRule : %d" % len(ids))
    print("  surcharge dans la classe portee     : %d" % len(par_etat["surcharge"]))
    print("  entree de DYNAMIC_TARGET_RULE_UNPORTED : %d" % len(par_etat["table"]))
    print("  AUCUNE (0 permissif, residu #287-r5)   : %d" % len(par_etat["aucune"]))
    # La somme est imprimee comme PARTITION : un etat oublie se verrait ici, pas dans un total juste
    # par accident (meme discipline que le recenseur d'enums, cf. CLAUDE.md).
    print("  --- partition : %d = %s"
          % (sum(len(v) for v in par_etat.values()),
             " + ".join("%s %d" % (e, len(par_etat[e])) for e in ETATS)))
    if not ids:
        print("  ECHEC : recensement VIDE -- un probe qui ne visite rien ne mesure rien.")
        return 1

    # Les DEUX etats de DEFAUT (#1015). Ils ne sont pas des categories a tolerer : chacun nomme une
    # contradiction entre les deux canaux, et le verdict les compte comme des FAUTES.
    for aid in par_etat["ambigu"]:
        print("  AMBIGU %-6d %-28s la classe SURCHARGE **et** l'entree de table subsiste : deux "
              "mirrors du meme corps, un seul consulte" % (aid, _nom(aid)))
    for aid in par_etat["perdue"]:
        print("  PERDUE %-6d %-28s entree de table PRESENTE mais la classe portee capture le "
              "porteur SANS surcharger -> id PERMISSIF en silence" % (aid, _nom(aid)))

    avec_symbole = [a for a in par_etat["aucune"] if SYMBOLE_NATIF.get(a)]
    print("[287-r4-r1] RESIDU #287-r5 -- corps natifs NON portes")
    print("  dont une surcharge NATIVE est lisible dans la table de symboles : %d / %d"
          % (len(avec_symbole), len(par_etat["aucune"])))
    for a in avec_symbole[:8]:
        print("    %-6d %-28s IdunBattleLogic...%s$$GetDynamicInvalidTargetReason"
              % (a, _nom(a), SYMBOLE_NATIF[a]))
    if len(avec_symbole) > 8:
        print("    ... et %d de plus (liste complete : la case-doc)" % (len(avec_symbole) - 8))

    bascules = mesurer_bascule()
    print("[287-r4-r1] BASCULE -- chaque regle portee DISCRIMINE-t-elle ?")
    for aid, libelle, r1, r2, ok in bascules:
        print("  %-6d %-34s refus=%-3d passe=%-3d %s"
              % (aid, libelle, r1, r2, "OK" if ok else "NON DISCRIMINANT"))

    mutants = mesurer_mutants()
    morts = [m for m in mutants if not m[2]]
    print("[287-r4-r1] MUTANTS -- desarmer la regle CHANGE-t-il le verdict ?")
    print("  a_morde : %d / %d  (critere : avant == %d ET apres == 0)"
          % (len(mutants) - len(morts), len(mutants), REFUS))
    for aid, libelle, a_morde, avant, apres in mutants:
        if not a_morde:
            print("    NON EXERCE %-6d %-34s avant=%-3d apres=%-3d -- la mutation ne retire RIEN : "
                  "ce bras ne garde rien" % (aid, libelle, avant, apres))

    tem = temoin_has_valid_targets()
    print("[287-r4-r1] LE ROUGE -- `_has_valid_targets` sur AdaptiveStrategy (1005)")
    print("  tous les allies HEROS   -> %s (attendu False : natif pose NoActionAvailable)"
          % tem["tous_heros"])
    print("  un allie NON-HEROS      -> %s (attendu True  : la cible passe)" % tem["un_non_heros"])

    if args.ids:
        print("[287-r4-r1] DETAIL")
        for aid in ids:
            print("  %-6d %-34s %s" % (aid, _nom(aid), evaluabilite(aid)))

    ok = (all(b[4] for b in bascules) and not morts
          and tem["tous_heros"] is False and tem["un_non_heros"] is True
          and not par_etat["ambigu"] and not par_etat["perdue"]
          and len(par_etat["surcharge"]) + len(par_etat["table"]) > 0)
    print("[287-r4-r1] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
