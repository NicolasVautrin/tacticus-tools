"""Port de `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector` (noeud DSL
`IdunBattleLogic.Entities.DSLFactory$$SortUnitsByDamageUtility`) — tri de cibles par l'UTILITE IA de degat.

DECOMPILE (`…SortUnitsByDamageUtilitySelector$$Select`, lecture integrale) :

    units   = (+0x20).Select(entities)                       # la source de candidats
    owner   = (+0x18).SelectSingle(entities)                 # l'attaquant
    dmgMin  = (+0x40).Calculate(entities)                    # noeud de degat (min)
    dmgMax  = (+0x48) ? (+0x48).Calculate(entities) : dmgMin # (optionnel ; sinon min == max)
    ability = (+0x28) ? (+0x28).Calculate(...) : GetNormalAttackType(owner)
    foreach u in units :
        pred = <DamagePrediction scenario 0x25>(owner, u, ability, dmgMin, dmgMax, …)
        dict[u] = UtilityDecider.CalculateUtility(+0x38 = UtilityDefinition(0x23 = Damage), u, pred)
    return units.OrderBy( u => Fix64.op_UnaryNegation(dict[u]) ).ToList()

Le lambda de tri (`…SortUnitsByDamageUtilitySelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0`)
rend **−utilite** ⇒ `OrderBy` croissant sur −u = tri **DECROISSANT** par utilite ⇒ le `First(…)` d'un
call-site prend l'**argmax du composite `UtilityType.Damage`** = `DamageDealt` + `KillUnit` +
`OverkillUnit` (`engine.utilities.damage_composite`, poids BC `Utilities`).

⚠ CITATION CORRIGEE (#519, ex-`#504-r1`) -- elle etait PERIMEE D'UN BUILD, et melangee. Elle
annoncait `UtilityDefinition(0x22)`, `Damage = 34`, `DamageDealt = 35`, `KillUnit = 36` et
`OverkillUnit = 38`. Or `IdunBattle.Configuration.UtilityType` a vu UNE SEULE insertion entre
`gqfc5mff6c` et `rnca9r7q6c` -- `AttackTile` en 8 -- ce qui a decale de +1 les **73** membres qui
la suivent, `Damage` compris :

    gqfc5mff6c :  33 TileDistance  34 Damage  35 DamageDealt  36 KillUnit  37 OverkillUnit
    rnca9r7q6c :  34 TileDistance  35 Damage  36 DamageDealt  37 KillUnit  38 OverkillUnit

Trois des quatre ordinaux cites venaient donc de l'ANCIEN build et le quatrieme (`OverkillUnit
38`) du NOUVEAU -- une citation qu'aucun des deux builds ne rend vraie. LE CODE, LUI, ETAIT JUSTE :
il ne lit aucun ordinal en dur, il passe par le mirror `engine.utilities.utility_type.UtilityType`,
et le comportement est valide live (#504, bit-exact au tirage pres). Le natif confirme la valeur
courante : les deux surcharges de `IdunBattleLogic.Entities.DSLSelectors$$SortUnitsByDamageUtility`
qui construisent elles-memes la definition appellent
`IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(this, 0x23)`.
C'est pourquoi les ordinaux ne sont PLUS ecrits ici : seuls les NOMS le sont, et `0x23` -- le
litteral VERBATIM du decompile -- garde son commentaire de nom. Un ordinal recopie se perime en
silence au prochain build ; un nom se re-derive de `data/symbols/<build>/frida/enums.tsv`.

La prediction IA est PRE-ARMURE (`armor = 0`, cf. en-tete de `services/damage_prediction`) ⇒ la PLAGE de
degat est la MEME pour toutes les cibles ; le classement ne depend que des PV courants/max et des flags
kill/overkill PAR cible. Ce module ne porte donc que l'etage TRI (la plage vient de l'appelant, qui sait
quel noeud de degat le call-site branche sur +0x40/+0x48).

Deux call-sites portes :
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility$$CreateBehaviour` — plage =
    l'attaque NORMALE melee de l'owner (`_normal_attack_health_range`).
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.AncestralFortuneAbility$$ExecuteBehaviour` — plage =
    `MinMaxDamage(entities, 1)` = `Half(Sum(Direct(minDmg[lvl]), Direct(maxDmg[lvl])))`
    (`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` branche `useAverage != 0`), donc
    min == max == moyenne des bornes de l'ability.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import HealthComponent
from ...utilities import damage_composite
from ...weights import load as _load_weights

# Cache des poids d'utilite (BC `Utilities` — statiques par bataille, cf.
# project_ai_weights_in_battle_config) : seules KillUnit/OverkillUnit sont lues ici, les poids
# DamageDealt 80/20 etant des Fix64 codes en dur dans `DamageUtility$$.cctor`.
_DAMAGE_UTILITY_WEIGHTS = None


def damage_utility_weights():
    global _DAMAGE_UTILITY_WEIGHTS
    if _DAMAGE_UTILITY_WEIGHTS is None:
        _DAMAGE_UTILITY_WEIGHTS = _load_weights()
    return _DAMAGE_UTILITY_WEIGHTS


def _target_utility(state: State, target_id: int, dmin: int, dmax: int, wt,
                    might_crit: bool = False) -> float:
    """`UtilityDecider.CalculateUtility(UtilityDefinition(0x23 = Damage), cible, prediction)` pour UNE
    cible — mirror des champs que `UtilityAttackCase$$ForDamagePrediction` lit du `DamagePredictionResult`
    (bornes santé capées/brutes, PV avant, kill = `MightBeKill`, killSure = `WillBeKill`). Bouclier non
    modelise (`shieldBefore = 0`, meme residu que le reste du moteur).

    `might_crit` -- ⚠ **CE PARAMETRE EXISTE POUR LA CONTRE-EPREUVE, PAS POUR LA PRODUCTION.** Aucune
    des deux entrees publiques ne l'alimente, et c'est un resultat MESURE, pas un oubli : cf. le
    bloc `#419-r6-r1` sur la cle `mightCrit` ci-dessous. `probe_419r6r1_face_decision.py` s'en sert
    pour rejouer les DEUX cotes sur le meme etat."""
    e = state.get_entity(target_id)
    hc = e.get_component(HealthComponent) if e is not None else None
    hp = int(hc.hp) if (hc is not None and hc.hp is not None) else 0
    max_hp = int(hc.hp_max) if (hc is not None and hc.hp_max) else hp
    pred = {"healthDmgMin": max(0, dmin), "healthDmgMax": max(0, dmax),
            # rawHealthDmg* = plage NON capee (mirror @0x24/@0x28) : `OverkillUnit` fidele via l'over-shoot
            # (dmg >= 2*PV) — la prediction pre-armure EST deja brute.
            "rawHealthDmgMin": max(0, dmin), "rawHealthDmgMax": max(0, dmax),
            "hpBefore": hp, "shieldBefore": 0,
            # #419-r6-r1 -- `mightCrit` RESTE NON POSE PAR LES ENTREES PUBLIQUES, et c'est MESURE.
            #
            # #R34 avait NOMME l'absence de cette cle en residu (« non porte faute de pouvoir le
            # VALIDER »), et la bascule du defaut a « equiper » (#419-r6) a rendu le montage
            # constructible : `CouldCrit` passe de 0/106 a 98/106 unites normalisees, donc l'ecart
            # aurait ete REEL si le natif lisait le flag ici. Le port a donc ete ECRIT, puis
            # CONFRONTE -- et le live l'a REFUTE.
            #
            # Montage (`probe_419r6r1_face_decision.py`, Doombolt 1102 sur `thousAhriman`, 4 cibles,
            # `N = 3` coups -> repartition `[1, 1, 1, 0]` : le DERNIER se lit sans ambiguite) :
            #   * trois roles d'utilite DISTINCTS -- aucune egalite, donc le tie-break (que le port
            #     approxime par `id` croissant) ne peut pas se substituer au flag ;
            #   * `FixedArmor = Armor = 0` sur les cibles -- sinon un `MightBeKill` perdu par
            #     l'armure ferait basculer le classement pour une raison etrangere au flag ;
            #   * `--crit 100,700` sur le caster -- `CouldCrit(owner)` vrai de facon incontestable
            #     (et le crit MORD : le coup sur la cible du message passe de 1468 a 2168).
            # Resultat : port SANS le flag -> `[77, 81, 83, 79]`, **BIT-EXACT** avec le live ;
            # port AVEC le flag -> `[77, 81, 79, 83]`, DIVERGE (la cible a 0 coup n'est pas la
            # meme). Idem au regime de crit NATUREL (items equipes, sans `--crit`).
            #
            # ⇒ `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` ne fait PAS
            # entrer `MightCrit` dans son classement. Le dict d'ici est donc FIDELE en l'etat.
            # La RAISON reste ouverte au decompile (residu, cf. la case-doc) : le chemin passe bien
            # par `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` (memset 0xb8
            # de l'`AttackPredictionRequest` puis slot 4 = `PredictAttack`), `UtilityAttackCase$$
            # ForDamagePrediction` recopie la struct ENTIERE (+0x00..+0x9c) et
            # `OverkillUnitUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` appelle bien
            # `MightBeOverkill` -- l'etage exact qui neutralise le flag n'est pas encore isole.
            "mightCrit": bool(might_crit),
            "killSure": hp > 0 and dmin >= hp,          # WillBeKill  (dmg min >= PV)
            "kill": hp > 0 and dmax >= hp}              # MightBeKill (dmg max >= PV)
    return damage_composite(pred, max_hp, wt)


def sort_units_by_damage_utility(state: State, candidates, dmin: int, dmax: int) -> list:
    """`SortUnitsByDamageUtilitySelector$$Select` — les candidats TRIES par utilite Damage DECROISSANTE
    (`OrderBy(−utilite)`). Tie-break : `OrderBy` natif STABLE sur l'ordre source ; approxime ici par `id`
    croissant (les call-sites portes alimentent le selecteur avec un ensemble non ordonne).

    ⚠ L'approximation du tie-break est OBSERVABLE, et #419-r6-r1 l'a vue : sur un montage ou DEUX
    cibles avaient la MEME utilite, le live rendait `[77, 81, 83, 79]` la ou le port rend
    `[77, 81, 79, 83]`. C'est un residu NOMME, distinct du flag `mightCrit` -- un montage qui cree
    une egalite mesure le tie-break, pas ce qu'il croit mesurer."""
    wt = damage_utility_weights()
    ordered = sorted(int(c) for c in candidates)
    return sorted(ordered, key=lambda eid: -_target_utility(state, eid, dmin, dmax, wt))


def first_by_damage_utility(state: State, candidates, dmin: int, dmax: int) -> Optional[int]:
    """`First(SortUnitsByDamageUtility(…), 1)` — l'argmax du composite `UtilityType.Damage`, ou None si aucun
    candidat. Argmax STRICT sur l'ordre `id` croissant = 1er id en cas d'egalite parfaite (== la stabilite
    de l'`OrderBy` natif sur l'ordre source, cf. l'avertissement de `sort_units_by_damage_utility`)."""
    best, best_util = None, None
    wt = damage_utility_weights()
    for eid in sorted(int(c) for c in candidates):
        util = _target_utility(state, eid, dmin, dmax, wt)
        if best_util is None or util > best_util:
            best_util, best = util, eid
    return best
