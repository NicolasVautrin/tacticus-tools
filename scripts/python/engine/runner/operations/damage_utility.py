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

⚠ **« PRE-ARMURE » N'IMPLIQUE PAS « MEME PLAGE POUR TOUTES LES CIBLES » — cette en-tete l'affirmait, et
c'etait FAUX (#494-r1).** Le natif appelle la prediction **PAR CIBLE**, DANS la boucle `foreach u`, et il
lui passe la **POSITION DU CASTER** (`dc+0x20 = GetUnitPosition(owner)`) en plus de `u` : le couple
(caster, cible) entre donc dans la cle. Les feuilles POSITIONNELLES du builder partage
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` —
`…$$CalculateElevationBonusModifier` (+ElevationBonus % si la tuile de l'attaquant est plus haute) et
`…$$CalculateTrenchReduction` — rendent la plage predite **differente d'une cible a l'autre**, sans
qu'aucune stat de cible n'ait bouge. Le classement ne depend donc PAS que des PV et des flags
kill/overkill : il depend AUSSI de la GEOMETRIE.

MESURE qui l'etablit (`probe_494_doombolt_sort_order.py`, board `MC1_67`, seed 777, 4 x `orksNob`
IDENTIQUES, `--hp-target` -> `Armor = FixedArmor = 0`, `statDelta` vide, 2026-08-07) :

    | regime | elevations des cibles | ordre SOURCE lex(x,y) | NATIF joue              |
    | L1     | 3 3 3 3   (= caster)  | [81, 83, 79, 85]      | [79, 81, 83]  ordre SOURCE |
    | L2     | 3 3 3 2               | [81, 83, 79, 85]      | [79, 85, 81]  u85 REMONTE  |
    | L3     | 3 2 3 3               | [81, 83, 79, 85]      | [79, 81, 83]  u81 RESTE    |

`L1` est le temoin : elevation PLATE ⇒ cle constante ⇒ le tri stable rend l'ordre SOURCE tel quel.
`L2`/`L3` sont des predictions HORS ECHANTILLON, ecrites avant la mesure : la seule cible plus BASSE
que le caster remonte en tete (bonus x1,5 mesure sur le degat joue : 2216 contre 1204 et 1477).

⚠ Ce que cette mesure REFUTE : la « rotation d'un cran vers la gauche » que #494 avait mesuree sur sept
geometries et laissee NON ATTRIBUEE. Elle predisait `[79, 83, 85, 81]` sur les TROIS regimes ci-dessus,
et les trois la contredisent. Ce n'etait pas une loi d'ordre : c'etait l'OMBRE d'une cle non constante,
tous les montages de #494 ayant par hasard melange des elevations.

Le tie-break, lui, est celui de `System.Linq.Enumerable.OrderBy` — **STABLE** ⇒ a utilite egale, l'ORDRE
SOURCE du selecteur est conserve tel quel. Ce n'est PAS l'ordre par `id` : la chaine complete
(`…TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` triple boucle cube -> `BattleQuery$$GetSurroundingTiles`
`OrderedSet.Add` -> `SurroundingTilesSelector$$Select` `OrderedSet.AddRange` -> `CombinedSelector$$SelectExclusion`
-> `TargetsSelector$$SelectUniqueUnits` `ArraySet.Add`/`ToList` -> `UnitsByTeamSelector` -> `UnobscuredEntitiesSelector`
-> `DSLSelectors$$Damageable`) preserve l'ordre d'insertion a chaque etage, et cet ordre est
`cube-lex (x, y)` ASCENDANT.

Ce module porte donc l'etage TRI **et** la part POSITIONNELLE de la cle (la plage brute vient toujours de
l'appelant, qui sait quel noeud de degat le call-site branche sur +0x40/+0x48).

⚠ RESTE NON PORTE dans la cle, et NOMME : l'**ARMURE** (`#527-r1` — la prediction IA est pre-armure cote
port alors que le natif en tient compte, mesure independamment sur `AncestralFortune` puis confirmee sur
Doombolt), le `ShouldApplyRangedInMelee` (feuille du meme builder, mais elle ne depend que de
l'ATTAQUANT ⇒ facteur COMMUN a toutes les cibles ⇒ sans effet sur l'ORDRE, seulement sur les seuils
kill/overkill), et les modificateurs d'EFFETS par cible.

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
# FORME B (`import <module>` + acces attributaire), et le differe est HISSE : classe GRATUIT, mesure
# le 2026-08-07 -- `import engine.runner.damage_model` en process FRAIS ne charge PAS
# `engine.runner.operations.damage_utility`, donc aucune arete a fermer. La forme B garde en plus la
# MORSURE d'un `monkeypatch.setattr("engine.runner.damage_model.apply_elevation_bonus", …)`.
from .. import damage_model as _damage_model
from ...services.damage_modifiers import DamageModifiers, apply_all_modifiers
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


def positional_damage_range(state: State, owner_id, target_id: int, dmin: int, dmax: int):
    """Les bornes `(dmin, dmax)` passees par les feuilles POSITIONNELLES du builder natif partage
    `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` — c'est ce
    qui rend la prediction DEPENDANTE DU COUPLE (caster, cible), donc la cle de tri non constante
    (#494-r1).

    Les deux feuilles portees sont celles que le moteur expose deja, nommees, sur la signature
    `(state, mods, attacker_id, target_id)` — MEMES fonctions que le COMBAT, pas de fork :
      * `apply_elevation_bonus`  -> `…$$CalculateElevationBonusModifier`
      * `apply_trench_reduction` -> `…$$CalculateTrenchReduction`

    `owner_id is None` (l'appelant ne sait pas qui attaque) -> bornes rendues INCHANGEES : le port ne
    devine pas une geometrie qu'on ne lui a pas donnee. `state.board` absent -> les deux helpers sont
    des no-op documentes, meme resultat."""
    if owner_id is None:
        return int(dmin), int(dmax)
    mods = DamageModifiers()
    _damage_model.apply_elevation_bonus(state, mods, int(owner_id), int(target_id))
    _damage_model.apply_trench_reduction(state, mods, int(owner_id), int(target_id))
    if not mods.pct_list and not mods.additive:
        return int(dmin), int(dmax)          # aucun modifier -> pas de materialisation parasite
    return (apply_all_modifiers(int(dmin), mods), apply_all_modifiers(int(dmax), mods))


def _target_utility(state: State, target_id: int, dmin: int, dmax: int, wt,
                    might_crit: bool = False, owner_id=None) -> float:
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
    # #494-r1 : la plage est celle du COUPLE (caster, cible), pas une constante de l'appelant.
    dmin, dmax = positional_damage_range(state, owner_id, target_id, dmin, dmax)
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


def sort_units_by_damage_utility(state: State, candidates, dmin: int, dmax: int,
                                 owner_id=None) -> list:
    """`SortUnitsByDamageUtilitySelector$$Select` — les candidats TRIES par utilite Damage DECROISSANTE
    (`OrderBy(−utilite)`).

    TIE-BREAK = l'ORDRE DE `candidates`, tel quel (#494-r1). `System.Linq.Enumerable.OrderBy` est
    STABLE, et `sorted(key=…)` de Python l'est aussi : a utilite egale, l'ordre SOURCE du selecteur
    est rendu intact. **C'est la responsabilite de l'appelant de fournir l'ordre du selecteur natif**
    (pour Doombolt : l'enumeration de tuiles `cube-lex (x, y)` ASCENDANTE de
    `…TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`, preservee par les sept etages qui
    suivent).

    ⚠ Le `sorted(int(c) for c in candidates)` qui vivait ici — un tri par `id` — est SUPPRIME : il
    n'approximait pas la stabilite de l'`OrderBy`, il la DETRUISAIT en imposant un ordre source
    different de celui du natif. Mesure : regime `L1` de `probe_494_doombolt_sort_order.py`, ou les
    quatre utilites sont egales, le natif rend `[79, 81, 83, 85]` = l'ordre SOURCE.

    `owner_id` = l'attaquant (`+0x20` du selecteur natif, `SelectUnit`) — necessaire a la part
    POSITIONNELLE de la cle (cf. `positional_damage_range`). Non fourni -> cle sans geometrie."""
    wt = damage_utility_weights()
    src = [int(c) for c in candidates]          # ORDRE SOURCE — `OrderBy` natif STABLE
    return sorted(src, key=lambda eid: -_target_utility(state, eid, dmin, dmax, wt,
                                                        owner_id=owner_id))


def first_by_damage_utility(state: State, candidates, dmin: int, dmax: int,
                            owner_id=None) -> Optional[int]:
    """`First(SortUnitsByDamageUtility(…), 1)` — l'argmax du composite `UtilityType.Damage`, ou None si aucun
    candidat. Argmax STRICT sur l'ORDRE DE `candidates` = 1er de l'ordre source en cas d'egalite parfaite
    (== la stabilite de l'`OrderBy` natif, cf. `sort_units_by_damage_utility`)."""
    best, best_util = None, None
    wt = damage_utility_weights()
    for eid in (int(c) for c in candidates):    # ORDRE SOURCE — jamais re-trie par `id`
        util = _target_utility(state, eid, dmin, dmax, wt, owner_id=owner_id)
        if best_util is None or util > best_util:
            best_util, best = util, eid
    return best
