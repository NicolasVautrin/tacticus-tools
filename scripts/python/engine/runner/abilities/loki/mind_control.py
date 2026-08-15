"""`1164 MindControl` (`genesMagus` << Magus >>, Genestealer Cults) -- #552.

`IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour` -- MIRROR du
DECOMPILE (build `rnca9r7q6c`), terme a terme, dans l'ordre. Slots de `DSLSelectors`
(`factory+0x90`) : `sel+0x30 = Owner`, `sel+0x38 = Effect`, `sel+0x48 = Caster`,
`sel+0x60 = Target`, `sel+0x68 = It` ; `factory+0x78 = DSLBehaviors`, `+0x80 = DSLFormulas`,
`+0x88 = DSLTriggers`, `+0x90 = DSLSelectors`.

    duree  = DSLFormulas.TurnsFromRounds( 2 )                       # LITTERAL 2, pas un ConfigVar

    out    = AddEffect( 0x545 = 1349 MindControl_OutoingDamageReduction,
                        AActiveAbility.get_AbilityStateReference(this),
                        source = Caster@0x48, targets = Target@0x60, turns = duree )
    inc    = AddEffect( 0x546 = 1350 MindControl_IncomingDamageBonus,
                        AActiveAbility.get_AbilityStateReference(this),
                        source = Caster@0x48, targets = Target@0x60, turns = duree )

    hp     = DSLFormulas.StatAmount( It@0x68, statType: 5 = HEALTH, statPart: 0,
                                     modificationEntity: null, selectionType: 0 )
    cache  = DSLSelectors.Cache(
                 DSLSelectors.First(
                     DSLSelectors.SortByFormula(
                         DSLSelectors.Attackable(
                             DSLSelectors.Friends( of: Owner@0x30,
                                 DSLSelectors.AdjacentUnits( Target@0x60, unique: 1,
                                                             selectionType: 3 ),
                                 selectionType: 3 ),
                             selectionType: 3 ),
                         hp, ascending: 0 ),
                     amount: 1, ignoreForcedTargets: 0 ),
                 matchAbilityEntities: 1 )

    taunt  = AddBondEffect( 0x1b = 27 Taunted_OnlySpecificTargets, stateRef,
                            source = Caster@0x48, targets = Target@0x60,
                            bondedEntity = cache, turns = duree )
    marque = AddBondEffect( 0x557 = 1367 MindControl_Taunter, stateRef,
                            source = Caster@0x48, targets = cache,
                            bondedEntity = Target@0x60, turns = duree )

    lien   = DSLBehaviors.If( cache, taunt & marque )               # surcharge SELECTEUR
    info   = DSLBehaviors.Inform( 0xcb = TagKey.Custom_Unit_Id, cache )
    immune = DSLTriggers.HasTrait( Target@0x60, 0x19 = 25 Immune )

    AActiveAbility.Execute( (out & inc) & If( !immune, info & lien ) )

CATEGORIE REELLE : **EFFECT/BUFF**, et l'audit `docs/rl/combat-ability-coverage.md` a donc RAISON
sur cette ligne. **LE CAST NE FRAPPE PAS** : l'arbre ne contient AUCUN `AttackWithAttackDamage`,
AUCUN `UseActiveAbility`, AUCUN `Spawn`, AUCUNE stat -- quatre `AddEffect`/`AddBondEffect`, un
`Inform` et deux `If`. (Le litteral `AbilityAttackType` du ctor vaut pourtant `0` =
`DirectTargetAttack` -- on le TRANSCRIT sans en rien deduire, cf. `abilities/attack_type.py`.)

⚠ **CE N'EST PAS UN OWNER-SWAP.** Le nom << MindControl >> evoque une prise de controle ; l'arbre
ne touche NI l'appartenance d'equipe (aucun `OwnerComponent`, aucun `ChangeTeam`), NI l'ordre
d'activation (aucun `PerformAIAction`, aucun `FinishUnitTurn`, aucun `ResetTurnFlags`). Le
<< controle >> est un TAUNT : la cible ne peut plus attaquer que l'allie designe, et elle frappe
moins fort en encaissant plus. Hypothese refutee des #219 ; re-lue ici sur `rnca9r7q6c`.

i2 (`GC.ability_description("MindControl")`, verbatim) :
  << Targets an enemy unit within 3 hexes that is adjacent to one or more friendly units. For this
  round and the next, that enemy unit deals -582 Damage, takes +20% Damage, and becomes Taunted by
  the adjacent unit with the highest current Health. >>

⚠ **`Friends(of: Owner@0x30, ...)` = les allies du CASTER, pas ceux de la cible.** Le 1er argument
de `IdunBattleLogic.Entities.DSLSelectors$$Friends(this, of, entities, selectionType)` est le
REFERENT ; c'est `sel+0x30` (Owner), donc le Magus. Corrobore mot a mot par l'i2 (<< adjacent to
one or more **friendly** units >>) : le taunteur est une de NOS unites.

⚠ **`SortByFormula(..., ascending = 0)` trie DESCENDANT** (le flag natif est `ascending`, pas
`descending`), donc `First(..., amount: 1)` rend l'allie a la Health COURANTE la plus HAUTE --
l'i2 << highest current Health >>. Inverser ce flag donnerait le plus FAIBLE sans rien casser
d'autre : c'est exactement le genre de bit qu'un test de garde doit tenir.

⚠ **Le gate `Immune` ne couvre QUE le taunt.** Les deux debuffs sont dans le membre GAUCHE du
`op_BitwiseAnd` de tete, hors du `If(!HasTrait(Target, Immune))` : une cible `Immune` prend bien le
`-dmgReduction` et le `+extraDmgPct %`. Et ce n'est pas une redite du gate d'immunite generique
d'`AddEffectOperation` : `data/symbols/<build>/metadata/can_be_immune_to.tsv` ne liste, de cette
famille, que `IdunBattle.Entities.Effects.TauntedEffect` -- 1349, 1350 et 1367 ne sont PAS
immuno-gates.

⚠ **`Execute`, PAS `ExecuteAtomic`** : la callee de queue est
`IdunBattle.Entities.Abilities.AActiveAbility$$Execute(behaviour, entities)` -- aucun `AtomicGroup`.

⚠ **Le `Cache` est PARTAGE par quatre consommateurs** (`Inform`, la condition du `If`, le
`bondedEntity` du taunt, la CIBLE de la marque) : c'est UNE instance de noeud, donc UNE seule
evaluation. Le port rebatit l'arbre a chaque cast (`mind_control_tree()`), donc le cache est
par-cast, comme le natif. ECART NOMME, sans consequence mesurable : la feuille `Inform` du port
DROPPE sa charge utile (elle n'a pas de bus de messages), donc la 1re evaluation du cache a lieu
au `If` qui suit immediatement, au lieu du `Inform` qui le precede. Rien ne mute l'etat entre les
deux (les deux `AddEffect` d'amont posent sur la CIBLE et ne touchent ni les positions, ni les PV,
ni les equipes -- les trois seules entrees du sous-arbre cache).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import If as IfBehaviour, Inform, op_and
from ....entities.effect_type import EffectType
from ....entities.formulas import Count, StatAmount
from ....entities.selectors.accessors import Owner, Subject, Target
from ....entities.selectors.geometry import Cache
from ....entities.selectors.tiles import Caster
from ....entities.selectors.units import (AdjacentUnits, First, Friends, SortByFormula,
                                          UnitsWithoutTrait)
from ....entities.stats import StatType
from ....entities.traits.unit_trait import UnitTrait
from ....entities.triggers import AmountIsGreaterThanZero, HasTrait, Not
# `Inform(0xcb, cache)` -- `0xcb` est une cle de message du bus natif, et l'enum qui la nomme est
# `TagKey` (meme registre que `Inform(0xb3 = Target_Id)` de FireOfAbsolution).
from ....streams.tag_key import TagKey
from ..base import ActiveAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddBondEffect, AddEffect
from ..targeting import (RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions,
                         get_adjacent_units)
from ..targeting_rule import TargetingRule as TR

if TYPE_CHECKING:
    from ...state import State


#: La cle gameconfig de l'ability 1164 (les `ConfigVar` des deux debuffs s'y indexent).
ABILITY_ID = "MindControl"

#: `DSLFormulas.TurnsFromRounds(2)` -- le `2` est un LITTERAL de l'arbre (aucun `ConfigVar`, aucune
#: constante de config : `MindControl.constants` ne porte que `range`). i2 : << for this round and
#: the next >>.
MIND_CONTROL_ROUNDS = 2

#: `AddEffect(0x545, ...)` / `AddEffect(0x546, ...)` -- les deux debuffs poses sur la CIBLE.
OUTGOING_DMG_REDUCTION = int(EffectType.MindControl_OutoingDamageReduction)   # 0x545 = 1349
INCOMING_DMG_BONUS = int(EffectType.MindControl_IncomingDamageBonus)          # 0x546 = 1350
#: `AddBondEffect(0x1b, ...)` -- le MEME composite `TauntedEffect` (enfants 25/26/1237) que posent
#: `CrushingClaws`, `GetEmRuntz`, `LashOfTorment` et `OverwhelmingWrath`.
TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)                         # 0x1b = 27
#: `AddBondEffect(0x557, ...)` -- le marqueur miroir, pose sur l'ALLIE taunteur.
TAUNTER = int(EffectType.MindControl_Taunter)                                 # 0x557 = 1367


def mind_control_taunter_selector():
    """`Cache(First(SortByFormula(Attackable(Friends(Owner, AdjacentUnits(Target)))), StatAmount(
    It, HEALTH)), 1)` -- MIRROR 1:1 du sous-arbre de SELECTION du taunteur.

    Cinq etages, tous natifs et tous deja portes :

    1. `AdjacentUnits(Target@0x60, unique: 1, selectionType: 3)` =
       `Units(AdjacentTiles(Target), 1, 3) - Target` (lu dans
       `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits`) : TOUTES les unites du ring 1 de la
       cible, sans filtre d'equipe, la cible elle-meme EXCLUE.
    2. `Friends(of: Owner@0x30, ..., 3)` -> `UnitsFromFactionSelector(state, of, entities, 1, 3)` :
       ne garde que les ALLIES du caster.
    3. `Attackable(..., 3)` = `UnitsWithoutTrait(entities, 0x1b = Steppable, 3)` -- LU, le natif
       n'alloue aucun selecteur dedie, il COMPOSE textuellement
       (`IdunBattleLogic.Entities.DSLSelectors$$Attackable`).
    4. `SortByFormula(..., StatAmount(It@0x68, 5 = HEALTH, 0, null, 0), ascending: 0)` : tri
       DESCENDANT par PV COURANTS. Le sujet de la formule est `It@sel+0x68`, c'est-a-dire l'element
       courant du tri -> `Subject()` cote port (c'est le binding que `SortByFormula.select` pose).
    5. `First(..., amount: 1, ignoreForcedTargets: 0)` puis `Cache(..., matchAbilityEntities: 1)`.

    ⚠ Le `selectionType: 3` (`OnlyAliveAndTargetable`) des etages 1-3 n'est PAS consomme par la
    couche selecteur du port -- residu NOMME `#433-r3-r2`, PARTAGE par tous les call-sites portes
    (orks 1058, genestealer, sisterhood, custodes). Consequence bornee ici : un cadavre allie
    adjacent a la cible resterait candidat au taunt cote port. Le regime est etroit (il faut un
    allie MORT qui occupe encore sa tuile au moment du cast) et la degradation est PERMISSIVE.

    ⚠ Ce call-site portait l'unique `index=` explicite du depot, et c'est ce qui a fait trouver
    #1032-r2 : le noeud `First` du port prenait un INDEX alors qu'AUCUNE surcharge native ne le
    fait. Il prend desormais l'`amount` natif -- ici `1`, le litteral LU ci-dessus, qui est aussi
    son defaut. `ignoreForcedTargets: 0` est le defaut : les cibles FORCEES priment donc, comme
    dans le natif."""
    adjacents = AdjacentUnits(Target())                       # etage 1 (radius 1 par defaut)
    amis = Friends(adjacents, reference=Owner())              # etage 2 (`of` = 1er arg natif)
    attaquables = UnitsWithoutTrait(amis, int(UnitTrait.Steppable))     # etage 3 (`Attackable`)
    tries = SortByFormula(attaquables,                                  # etage 4
                          StatAmount(Subject(), int(StatType.HEALTH)),
                          ascending=False)                    # flag natif `ascending = 0`
    return Cache(First(tries, 1))                             # etage 5 (`First(sel, 1, 0)`)


def mind_control_tree(taunteur):
    """Arbre COMPLET de `...MindControlAbility$$ExecuteBehaviour` (cf. l'en-tete de module).

    `taunteur` = l'instance PARTAGEE du noeud `Cache` (`mind_control_taunter_selector()`), passee
    par l'appelant pour que les QUATRE consommateurs natifs voient le MEME cache -- la memoisation
    est le sens du noeud, pas un detail d'implementation.

    - `op_and` = `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` -> `CombinedBehaviour` : gauche
      PUIS droite, sans court-circuit ici (aucune de ces feuilles ne propage le flag `stop` --
      `AddEffectBehaviour` et `InformBehaviour` rendent un resultat zero-initialise).
    - `IfBehaviour(AmountIsGreaterThanZero(Count(cache)), ...)` mirror la surcharge SELECTEUR de
      `IdunBattleLogic.Entities.DSLBehaviors$$If`, dont le corps est LITTERALEMENT
      `If(DSLTriggers.AmountIsGreaterThanZero(selector), ifBehaviour, elseBehaviour)` (LU). Le
      `Count` est la facon dont le port rend un selecteur a un trigger numerique.
    - `scale_from_source=True` sur les deux `AddEffect` : le 3e argument natif est
      `AActiveAbility$$get_AbilityStateReference(this)`, et les deux effets s'indexent dessus
      (`ConfigVar(..., GetAbilityState(effet), ...)`).
    - `scale_from_source` reste FAUX sur les deux `AddBondEffect` : `Taunted_OnlySpecificTargets`
      est un composite qui ne lit AUCUN `ConfigVar`, et `MindControl_Taunter` n'a pas d'autre corps
      que `get_Range` et `CreateActiveCondition` -- meme lecture que `lash_of_torment_tree`."""
    out = AddEffect(OUTGOING_DMG_REDUCTION, EffectType.MindControl_OutoingDamageReduction.name,
                    Target(), duration_rounds=MIND_CONTROL_ROUNDS, scale_from_source=True)
    inc = AddEffect(INCOMING_DMG_BONUS, EffectType.MindControl_IncomingDamageBonus.name,
                    Target(), duration_rounds=MIND_CONTROL_ROUNDS, scale_from_source=True)
    taunt = AddBondEffect(TAUNTED, EffectType.Taunted_OnlySpecificTargets.name,
                          Caster(), Target(), duration_rounds=MIND_CONTROL_ROUNDS,
                          bonded_ref=taunteur)
    marque = AddBondEffect(TAUNTER, EffectType.MindControl_Taunter.name,
                           Caster(), taunteur, duration_rounds=MIND_CONTROL_ROUNDS,
                           bonded_ref=Target())
    lien = IfBehaviour(AmountIsGreaterThanZero(Count(taunteur)), op_and(taunt, marque))
    info = Inform(int(TagKey.Custom_Unit_Id))                  # `Inform(0xcb, cache)` -- NO-OP porte
    immune = HasTrait(Target(), int(UnitTrait.Immune))         # `HasTrait(Target@0x60, 0x19)`
    return op_and(op_and(out, inc),
                  IfBehaviour(Not(immune), op_and(info, lien)))


class MindControlAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour`
    (id 1164, `genesMagus` << Magus >>, HERO Genestealer Cults -- au pool `rl_duel build
    --list-pool` du rank courant). Arbre DSL `mind_control_tree()`, cf. l'en-tete de module.

    ROUGE MESURE AVANT CE PORT : 1164 etait ABSENTE d'`ABILITY_CLASSES` -> le cast etait ACCEPTE
    par la DECISION (`MindControlPlaybook`, cf. `playbook/noncomparable/mind_control.py`) et
    IGNORE par l'EXECUTION : 0 debuff, 0 taunt, AUCUNE erreur. C'est ce no-op silencieux que ce
    port ferme.

    Termine le tour (1164 n'est dans aucun des deux frozensets de `base.py` -> flags par defaut).

    Retour : {ability, caster, target, posed, taunt, taunter, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MindControl)      # 1164
    ABILITY_ID = ABILITY_ID

    # GATE DE CIBLE (#115) + PORTEE (#241). FORME A (ctor a LITTERAL) :
    #     `...MindControlAbility$$.ctor` recopie les 3 qwords du champ statique
    #     `<TargetingRange statics>+0x18` dans un temporaire, puis
    #         TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x18>, 1, 0x4002, 0, 0)
    #         AActiveAbility..ctor(this, &opts, 0)
    #     -- le masque `0x4002` est le 5e argument EN CLAIR, il n'y a ni preset `+0x28` ni OR.
    # Decomposition EXHAUSTIVE de `0x4002` (0x2 + 0x4000, aucun bit residuel) :
    #     0x2     (bit  1) TargetMatchesDynamicRule -> consulte `get_dynamic_invalid_target_reason`,
    #                      SURCHARGE ci-dessous (le natif a un vrai corps).
    #     0x4000  (bit 14) TargetIsEnemy            -> refus sur soi-meme / un allie.
    # `isSelfCasting = 0`, `forceMeleeTarget = 1 = RangedBool.False` (l'enum natif est INVERSE :
    # True = 0, False = 1). PORTEE : `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValues
    # InTargetingOptions` pose `OverrideRange = GetNumberConstant(0x16 = range)` =
    # `MindControl.constants.range` = **3** (== l'i2 << within 3 hexes >>).
    # ⚠ Valeur MIGREE depuis la table de repli `TARGETING_OPTIONS_UNPORTED` d'`abilities/
    # targeting.py` (contrat de DISJONCTION : une ability au registre porte son masque sur SA
    # classe). Le ctor a ete RELU au decompile avant migration et le masque est bit-identique a
    # celui qui vivait la-bas.
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy),   # 5e arg du ctor = 0x4002
        self_cast=False, range=RANGE_FROM_CONFIG,
        force_melee_target=RANGED_BOOL_FALSE)                        # 4e arg du ctor = 1

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...MindControlAbility$$GetDynamicInvalidTargetReason` -- MIRROR PARTIEL du decompile,
        et le terme NON PORTE est NOMME.

            units = battleQuery.<slot 0x7c>(targetTiles, friendsOf: caster,
                                            enemiesOf: null, ignoreSteppables: false);
            ListExtensions.FilterInPlace(units, <Func<IEntity,bool> statique de MindControlAbility.<>c>);
            return Enumerable.Count(units) != 0 ? 0 : 2;      // 2 = TargetMatchesDynamicRule

        `slot 0x7c` = `IBattleQuery 124 GetAdjacentUnits/4` (`data/symbols/<build>/metadata/
        interface_slots.tsv`), la surcharge `(IList<IEntity> tiles, IEntity friendsOf,
        IEntity enemiesOf, bool ignoreSteppables)` -- LUE dans `frida/methods.tsv`, et dont le corps
        (`IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits` @ cette signature) est
        `GetUnitsOnTiles(IterateAdjacentTiles(chaque tuile), friendsOf, enemiesOf,
        ignoreSteppables)`. Avec `friendsOf = caster`, c'est litteralement l'i2 : << an enemy unit
        ... that is adjacent to one or more friendly units >>.

        ⚠ **LE PREDICAT DU `FilterInPlace` N'EST PAS LISIBLE, ET LE PORT NE L'INVENTE PAS.** C'est
        un `Func<IEntity,bool>` SANS capture, mis en cache dans le singleton
        `IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility.<>c` (son `$$.cctor` est
        dans les deux tables ; le corps du lambda, lui, est DEDUPLIQUE et n'apparait NI dans
        `frida/methods.tsv` NI dans `ghidra/functions.tsv` -- la classe `<>c` n'y a qu'UNE ligne, son
        cctor). Le debloquer demande un RPC qui enumere les methodes d'une classe IMBRIQUEE, donc
        une fenetre de reinject : residu `#552-r2` (`BLOCAGE: capteur`).

        CE QUI RESTE VRAI SANS LE LIRE, et qui justifie de porter quand meme : `FilterInPlace` ne
        peut que RETIRER des elements (son corps, LU @`idun.shared.extensions.ListExtensions$$
        FilterInPlace<T>`, fait `RemoveAt(i)` quand le predicat rend FAUX -- il ne peut ni en
        ajouter ni en substituer). Donc `units` VIDE avant le filtre => VIDE apres => refus `2`,
        quel que soit le predicat. Le port rend donc le refus sur l'ensemble AVANT filtre : il
        n'accepte JAMAIS une cible que le natif refuse, et il peut accepter une cible que le natif
        refuserait (degradation PERMISSIVE, la convention du module) -- strictement plus proche du
        natif que le `0` inconditionnel d'avant ce port.

        ⚠ `ignoreSteppables = false` est LU (5e argument litteral `0`) : les unites `Steppable`
        COMPTENT pour cette legalite. C'est ce qui interdit de rabattre le predicat inconnu sur
        `!IsSteppable` << par symetrie avec l'`Attackable` de l'arbre >> : le natif avait le flag
        sous la main et ne l'a PAS arme, donc les deux etages ne posent pas la meme question.

        `get_adjacent_units` est le mirror deja porte de cet etage (meme
        `CountOrGetUnitsOnTiles`, meme porte d'elevation, meme `requireWalkable`), et il prend
        `friends_of` en parametre : le call-site 1087 le passe NUL, celui-ci passe le caster.

        Cible non resolue -> `0` ; board absent -> `0` (on ne fabrique pas un refus sur un substrat
        non mesure) -- meme convention que `_dynamic_rule_blood_chalice`."""
        if target_id is None or state.get_entity(int(target_id)) is None:
            return 0
        if state.board is None:
            return 0
        units = get_adjacent_units(state, int(target_id), friends_of=int(caster_id),
                                   enemies_of=None, ignore_steppables=False)
        return 0 if units else int(TR.TargetMatchesDynamicRule)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # UNE instance de `Cache`, partagee par les quatre consommateurs natifs (cf. l'en-tete).
        taunteur = mind_control_taunter_selector()
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        mind_control_tree(taunteur).execute(entities, ectx)
        posee = [{"effect_type": p.get("effect_type"), "target": p.get("target"),
                  "placed": p.get("placed"), "active": p.get("active")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        bonds = [{"effect_type": p.get("effect_type"), "target": p.get("target"),
                  "bonded": p.get("bonded")}
                 for n, p in ectx.emitted if n == "AddBondEffect"]
        taunt = next((b for b in bonds if b["effect_type"] == TAUNTED), None)
        marque = next((b for b in bonds if b["effect_type"] == TAUNTER), None)
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "posed": posee, "taunt": taunt, "taunter": marque,
                "rounds": MIND_CONTROL_ROUNDS, "dsl": True}
