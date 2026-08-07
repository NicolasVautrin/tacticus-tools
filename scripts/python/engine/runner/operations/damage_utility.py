"""Port de `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector` (noeud DSL
`IdunBattleLogic.Entities.DSLFactory$$SortUnitsByDamageUtility`) — tri de cibles par l'UTILITE IA de degat.

DECOMPILE (`…SortUnitsByDamageUtilitySelector$$Select`, lecture integrale) :

    units    = (+0x20).SelectUnits(entities, unitSelectionType)   # la source de candidats
    owner    = (+0x18).SelectUnit(entities)                       # l'attaquant           -> dc+0x18
    ownerPos = EntityExtensions.GetUnitPosition(owner)            #                       -> dc+0x20
    if ownerPos.IsEmpty : return new List<IEntity>()              # sortie SECHE
    damage   = (+0x40).Calculate(entities)                        # noeud de degat        -> dc+0x10
    hits     = 1 ; if (+0x48) != null : hits = (+0x48).Calculate(entities)  #             -> dc+0x14
    ability  = AbilityOrEffect(GetNormalAttackType(owner))
    if (+0x28) != null : ability = (+0x28).Select(entities)
    foreach u in units :
        pred = (+0x50 = IBattleQuery).<slot 0x26>(owner, u, ownerPos, ability,
                                                  () => damage, () => hits,
                                                  damageProfile: null, defenderInitialHealth: null,
                                                  previousHitsPrediction: default, null, null)
        dict[u] = UtilityDecider.CalculateUtility(+0x38 = UtilityDefinition(0x23 = Damage), u, pred)
    return units.OrderBy( u => Fix64.op_UnaryNegation(dict[u]) ).ToList()

⚠ **CE QUE #494-r1-r1 A CORRIGE, ET CE QUE L'EN-TETE PRECEDENTE DISAIT DE FAUX.** Elle lisait
`+0x48` comme un `dmgMax` optionnel : c'est le noeud **`hits`**, et son defaut est **1** (le ctor
natif l'atteste -- `SortUnitsByDamageUtilitySelector..ctor(state, battleQuery, utilitiesDatabase,
targets, caster, ability, utilityDefinition, damage, hits, aiLogger)`, `frida/methods.tsv`). Le
noeud de degat rend UN entier, jamais une paire. Et le slot `0x26` d'`IBattleQuery`
(`metadata/interface_slots.tsv` : `IBattleQuery 38 GetAttackPrediction 11`) est la surcharge
`(caster, target, casterPosition, ability, calculateDamageAtTile:Func<Int32>,
calculateHitsAtTile:Func<Int32>, damageProfile, defenderInitialHealth, previousHitsPrediction,
prePredictionAction, postPredictionAction)` -- c'est la **PREDICTION COMPLETE**, pas une plage
brute : `DamagePredictionQuery$$GetAttackPrediction` monte l'`AttackPredictionRequest` (memset 0xb8)
et appelle `DamagePrediction$$PredictAttack` -> `$$PredictAttackRaw`. ARMURE, PERCAGE, DEFENSE,
modificateurs d'attaquant et de defenseur, bouclier et scenarios de BLOCK entrent donc TOUS dans la
cle de tri. Les deux residus qui l'accusaient (`#527-r1` l'armure, `#494-r1-r1` la defense) sont la
MEME cause : le port fabriquait un `pred` synthetique.

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

LES QUATRE CALL-SITES PORTES, et ce que chacun branche sur `+0x28` / `+0x40` / `+0x48` (LU) :

  * `…AncestralFortuneAbility$$GetAttackTarget` (le corps est inline dans l'`ExecuteBehaviour`) :
    `SortUnitsByDamageUtility(targets, MinMaxDamage(entities, 1), 3, null)` -- la surcharge SANS
    noeud d'ability, donc `ability = GetNormalAttackType(owner)` (le profil et le percage sont ceux
    de l'ARME NORMALE du caster) ; `damage` = moyenne des bornes de l'ability ; `hits = 1`.
  * `…FinalJusticeAbility$$CreateBehaviour` :
    `SortUnitsByDamageUtility(ValidNormalAttackTargets, caster, UnitNormalAttackType,
    UtilityDefinition(0x23), NormalAttackDamage(caster), 0, null)`.
    `DSLFormulas$$NormalAttackDamage(unit)` = `StatAmountFormula(unit, StatType.Attack = 0,
    StatPart = 0)` -> la stat **Attack**, c.-a-d. la base d'UN coup ; `hits = 1`.
  * `…DoomboltAbility$$ExecuteBehaviour` : `ability = Direct(AbilityOrEffect(1102))`,
    `damage = Direct(GetVariableForLevel(0xc = minDmg, level))`, `hits = null`.
  * `…KillMaimBurnAbility$$GetNextTarget` : `ability = Direct(AbilityOrEffect(1132))`,
    `damage = MinMaxDamage2` (`RandomAmount(minDmg_2, maxDmg_2)`, un TIRAGE), `hits = null`.

Les QUATRE passent `hits = null` : aucun call-site porte ne fournit de noeud de coups, donc la cle
predit **UN** coup. C'est une LECTURE, pas une simplification.

⚠ RESTE NON PORTE / NOMME : `damageProfile` est passe **null** par le selecteur, et sa resolution
vit dans `DamagePrediction$$PredictAttackRaw`, qui n'a PAS ete parcouru integralement ici. Le port
passe le profil de l'ABILITY citee par `+0x28` (Doombolt `Psychic`, KillMaimBurn le
`AActiveAbility$$GetDamageProfile` = `damageProfile` de la config = `Piercing`), et celui de l'ARME
NORMALE quand `+0x28` est nul. Restent aussi hors cle : `ShouldApplyRangedInMelee` (feuille du meme
builder, mais elle ne depend que de l'ATTAQUANT ⇒ facteur COMMUN a toutes les cibles ⇒ sans effet
sur l'ORDRE) et `MightCrit`, que `PredictAttackRaw` calcule pourtant -- le live l'a REFUTE sur ce
chemin (#419-r6-r1, `test_419r6r1_face_decision_live.py`), le port reste ou la mesure l'a mis.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import HealthComponent, StatsComponent
# FORME B (`import <module>` + acces attributaire), et le differe est HISSE : classe GRATUIT, mesure
# le 2026-08-07 -- `import engine.runner.damage_model` en process FRAIS ne charge PAS
# `engine.runner.operations.damage_utility`, donc aucune arete a fermer. La forme B garde en plus la
# MORSURE d'un `monkeypatch.setattr("engine.runner.damage_model.apply_elevation_bonus", …)`.
from .. import damage_model as _damage_model
# FORME B, meme raison : le mirror de `BattleQuery$$GetMultiHitAttackPrediction` est le SERVICE que
# la boucle `foreach u` du selecteur appelle par cible (#494-r1-r1).
from . import attack_prediction as _attack_prediction
from ...services.battle_query import select_weapon_pierce as _select_weapon_pierce
from ...services.damage_modifiers import DamageModifiers, apply_all_modifiers
from ...utilities import damage_composite
from ...utilities.damage import composite_fields_from_prediction
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


def normal_attack_profile_and_pierce(state: State, owner_id, target_id):
    """`AbilityOrEffect(UnitExtensions$$GetNormalAttackType(owner))` — le defaut du noeud `+0x28` du
    selecteur : quand aucun noeud d'ability n'est branche, le natif predit l'ATTAQUE NORMALE du
    caster. Le profil de degat et le percage sont alors ceux de l'ARME que
    `BattleQuery$$GetAttackWeaponForDefaultNormalAttack` choisit pour ce couple (melee/ranged par
    adjacence hex + porte ranged) — MEME service que le combat (`services/battle_query`).

    Rend `(profile_name, pierce, is_melee)`, ou `None` si le caster n'a pas de stats ou si l'arme
    est introuvable (le natif rend alors `null` et sa prediction est `0..0` en 1 coup — le port
    prefere le dire a l'appelant plutot que d'inventer un profil)."""
    import hexgeo
    e = state.get_entity(int(owner_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return None
    pa = _damage_model._unit_pos(state, int(owner_id))
    pb = _damage_model._unit_pos(state, int(target_id))
    dist = hexgeo.distance(pa, pb) if (pa is not None and pb is not None) else None
    pierce, is_ranged, _whits, prof = _select_weapon_pierce(ctx, dist is not None and dist <= 1,
                                                           dist)
    if prof is None:
        return None
    return prof, int(pierce), (not is_ranged)


def _target_utility(state: State, target_id: int, dmin: int, dmax: int, wt,
                    might_crit: bool = False, owner_id=None, hits: int = 1,
                    damage_profile=None, pierce=None, ability_type=None,
                    is_melee=None) -> float:
    """`UtilityDecider.CalculateUtility(UtilityDefinition(0x23 = Damage), cible, prediction)` pour UNE
    cible.

    ⚠ **DEUX CHEMINS, ET LE PREMIER EST LE MIRROR (#494-r1-r1).**

    1. `owner_id` FOURNI et le couple est predictible -> la `prediction` est celle que le natif
       calcule DANS sa boucle : `IBattleQuery` slot `0x26` = la PREDICTION COMPLETE
       (`operations/attack_prediction.multi_hit_attack_prediction`, mirror de
       `BattleQuery$$GetMultiHitAttackPrediction`), donc ARMURE, PERCAGE, DEFENSE, modificateurs
       d'attaquant/defenseur, bouclier et scenarios de BLOCK. Les champs consommes par le composite
       sont lus par le foyer PARTAGE `utilities/damage.composite_fields_from_prediction`
       (`UtilityAttackCase$$ForDamagePrediction`), le MEME que la chaine playbook.
    2. `owner_id is None` (ou stats/arme indisponibles) -> cle DEGRADEE, pre-armure : les bornes
       brutes de l'appelant, comme avant #494-r1-r1. Le natif, lui, sort SEC
       (`ownerPos.IsEmpty -> new List<IEntity>()`) ; le port ne peut pas rendre une liste vide a un
       appelant qui ne lui a rien dit du caster, donc il DEGRADE en le documentant. Ce chemin est ce
       que jouent les etages OFFLINE (`test_419r6r1_face_decision_live.py` etage 1, stubs sans
       `StatsComponent`).

    `dmin`/`dmax` : le noeud `+0x40` rend UN entier ; les deux bornes sont conservees pour le chemin
    DEGRADE et pour les appelants historiques. Le chemin MIRROR n'utilise que `dmin` (= l'`amount`).

    `might_crit` -- ⚠ **CE PARAMETRE EXISTE POUR LA CONTRE-EPREUVE, PAS POUR LA PRODUCTION.** Aucune
    des entrees publiques ne l'alimente, et c'est un resultat MESURE, pas un oubli : cf. le
    bloc `#419-r6-r1` sur la cle `mightCrit` ci-dessous. `probe_419r6r1_face_decision.py` s'en sert
    pour rejouer les DEUX cotes sur le meme etat ; il est applique par-dessus les DEUX chemins."""
    e = state.get_entity(target_id)
    hc = e.get_component(HealthComponent) if e is not None else None
    hp = int(hc.hp) if (hc is not None and hc.hp is not None) else 0
    max_hp = int(hc.hp_max) if (hc is not None and hc.hp_max) else hp
    if owner_id is not None:
        pred = _prediction_fields(state, owner_id, target_id, int(dmin), int(hits),
                                  damage_profile, pierce, ability_type, is_melee)
        if pred is not None:
            if might_crit:
                pred["mightCrit"] = True
            return damage_composite(pred, max_hp, wt)
    # --- chemin DEGRADE (pre-armure) : l'appelant n'a pas dit qui attaque, ou le couple n'est pas
    # predictible (pas de stats, pas d'arme normale). #494-r1 : la plage reste celle du COUPLE
    # (caster, cible) quand `owner_id` est connu -- les deux feuilles POSITIONNELLES.
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


def _prediction_fields(state: State, owner_id, target_id: int, amount: int, hits: int,
                       damage_profile, pierce, ability_type, is_melee):
    """La PREDICTION du natif pour UNE cible, rendue sous la forme que le composite consomme.

    Mirror de l'appel que la boucle `foreach u` fait sur `+0x50` (`IBattleQuery` slot `0x26`) :
    `GetAttackPrediction(owner, u, ownerPosition, ability, () => damage, () => hits,
    damageProfile: null, defenderInitialHealth: null, previousHitsPrediction: default, null, null)`.

    `damage_profile`/`pierce`/`is_melee` non fournis -> l'ability du selecteur est nulle, donc le
    natif prend `GetNormalAttackType(owner)` : on resout l'ARME NORMALE du caster
    (`normal_attack_profile_and_pierce`). `None` en retour = couple non predictible -> l'appelant
    retombe sur la cle DEGRADEE."""
    prof, pc, melee = damage_profile, pierce, is_melee
    is_normal = False
    if prof is None or pc is None:
        na = normal_attack_profile_and_pierce(state, owner_id, target_id)
        if na is None:
            return None
        prof, pc, melee = na[0], na[1], (na[2] if melee is None else melee)
        is_normal = True
    dp = _attack_prediction.multi_hit_attack_prediction(
        state, int(owner_id), int(target_id), int(amount), max(1, int(hits)), prof, int(pc),
        is_melee=bool(melee), ability_type=ability_type, is_normal_attack=is_normal)
    if dp is None:
        return None
    return composite_fields_from_prediction(dp)


def sort_units_by_damage_utility(state: State, candidates, dmin: int, dmax: int,
                                 owner_id=None, hits: int = 1, damage_profile=None,
                                 pierce=None, ability_type=None, is_melee=None) -> list:
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

    `owner_id` = l'attaquant (`+0x20` du selecteur natif, `SelectUnit`) — **OBLIGATOIRE pour que la
    cle soit celle du natif** : c'est lui qui rend la PREDICTION calculable (#494-r1-r1). Non
    fourni -> cle DEGRADEE pre-armure (cf. `_target_utility`).

    `damage_profile`/`pierce`/`ability_type`/`is_melee` = ce que le noeud `+0x28` designe. Non
    fournis -> `GetNormalAttackType(owner)`, c.-a-d. l'ARME NORMALE du caster."""
    wt = damage_utility_weights()
    src = [int(c) for c in candidates]          # ORDRE SOURCE — `OrderBy` natif STABLE
    return sorted(src, key=lambda eid: -_target_utility(
        state, eid, dmin, dmax, wt, owner_id=owner_id, hits=hits,
        damage_profile=damage_profile, pierce=pierce, ability_type=ability_type,
        is_melee=is_melee))


def first_by_damage_utility(state: State, candidates, dmin: int, dmax: int,
                            owner_id=None, hits: int = 1, damage_profile=None,
                            pierce=None, ability_type=None, is_melee=None) -> Optional[int]:
    """`First(SortUnitsByDamageUtility(…), 1)` — l'argmax du composite `UtilityType.Damage`, ou None si aucun
    candidat. Argmax STRICT sur l'ORDRE DE `candidates` = 1er de l'ordre source en cas d'egalite parfaite
    (== la stabilite de l'`OrderBy` natif, cf. `sort_units_by_damage_utility`)."""
    best, best_util = None, None
    wt = damage_utility_weights()
    for eid in (int(c) for c in candidates):    # ORDRE SOURCE — jamais re-trie par `id`
        util = _target_utility(state, eid, dmin, dmax, wt, owner_id=owner_id, hits=hits,
                               damage_profile=damage_profile, pierce=pierce,
                               ability_type=ability_type, is_melee=is_melee)
        if best_util is None or util > best_util:
            best_util, best = util, eid
    return best
