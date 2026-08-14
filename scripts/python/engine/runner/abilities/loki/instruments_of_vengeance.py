"""`InstrumentsOfVengeance` (1215, `darkaBossLion` « le Lion », GuildBoss DarkAngels) -- #889-r6.

PHASE 1 d'un patron 2-PHASES, et **LE CAST NE FRAPPE PAS**. La colonne `DAMAGE(HeavyRound)` de
`docs/rl/combat-ability-coverage.md` derive du `damageProfile` de la CONFIG, pas du behaviour :
celui-ci choisit DEUX lignes de tir en travers du plateau, les MARQUE (`1518
InstrumentsOfVengeance_LocationTarget` sur chaque tuile), arme la phase 2 (`1519
InstrumentsOfVengeance_PendingAttack` sur le caster) et, si le Lion n'a personne au contact,
reactive son overwatch (`1009 Overwatch_AutoAttack`). Le DEGAT appartient a la phase 2
(`InstrumentsOfVengeance_AttackAbility`), **NON PORTEE** -- residu nomme, cf. §RESIDU ci-dessous.

ROUGE MESURE AVANT CE PORT : 1215 etait ABSENTE d'`ABILITY_CLASSES` -> `AbilityHandler` acceptait le
cast, posait les flags de tour, et n'executait RIEN. Zero effet, zero degat, zero erreur -- un NO-OP
SILENCIEUX, alors que la face DECISION est portee depuis #27-r6
(`playbook/loki_custom.py::InstrumentsOfVengeancePlaybook`, base d'utilite **20000** : des que 1215
est legale, elle est l'action la plus prioritaire du jeu). L'IA CHOISISSAIT donc une ability qui ne
faisait rien.

## L'ARTEFACT NATIF -- un arbre de noeuds `DSLFactory` PUR

`IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$ExecuteBehaviour`,
MIRROR 1:1 du decompile (build `rnca9r7q6c`), lu de bout en bout :

    a = GetEffectBehavior(direction = 1, first = true) op_Addition
        GetEffectBehavior(direction = 5, first = false)
    b = GetEffectBehavior(direction = 2, first = true) op_Addition
        GetEffectBehavior(direction = 4, first = false)
    r = DSLBehaviors$$If( DSLTriggers$$Maybe(0x32 = 50), a, b )
    r = r op_Addition DSLBehaviors$$AddBondEffect(
            0x5ef = 1519 InstrumentsOfVengeance_PendingAttack,
            AActiveAbility$$get_AbilityStateReference(this),
            source = Owner@DSLSelectors+0x30, targets = Owner@+0x30,
            bondedEntity = Owner@+0x30, options = <struct ZEROEE> )
    r = r op_Addition DSLBehaviors$$If(
            AbilityTrigger$$op_LogicalNot(
                DSLTriggers$$HasAdjacentEnemies(Owner@+0x30, Owner@+0x30, false, false) ),
            DSLBehaviors$$ActivateEffect( Owner@+0x30, 0x3f1 = 1009 Overwatch_AutoAttack ),
            null )
    return AActiveAbility$$Execute(entities, this, r)

et `...InstrumentsOfVengeanceAbility$$GetEffectBehavior(direction, first)` -- un arbre de la taille
d'une ability a lui seul :

    i      = first ? 0 : 1                       # `((byte)first & 0xff) ^ 1`
    behind = DSLSelectors$$TilesBehindInLine( origin    = ActiveTarget@DSLSelectors+0x68,
                                              direction = DSLFormulas$$Get(
                                                  EdgeExtensions$$Rotate(direction, 3)) )
    edge   = DSLSelectors$$EdgeTilesByDirection( DSLFormulas$$Get(direction) )
    if (!first)                                  # la 2e passe RETRANCHE la ligne deja prise
        edge -= DSLSelectors$$TilesBehindInLine(
                    Entity(GetPersistentData(AbilityOrEffect(this), Owner@+0x30, KEY_TARGET + "0")),
                    Entity(GetPersistentData(AbilityOrEffect(this), Owner@+0x30, KEY_DIR    + "0")) )
    sel = DSLSelectors$$Randomize(edge)
    sel = DSLSelectors$$SortByFormula(sel, Count(behind),                       ascending = 0)
    sel = DSLSelectors$$SortByFormula(sel, Count(Friends(Owner@+0x30,
              Units(behind op_Addition ActiveTarget@+0x68, unique: true, 3), 3)), ascending = 1)
    sel = DSLSelectors$$SortByFormula(sel, Count(Enemies(Owner@+0x30,
              Units(behind op_Addition ActiveTarget@+0x68, unique: true, 3), 3)), ascending = 0)
    sel = DSLSelectors$$Cache( DSLSelectors$$First(sel, 1, 0), true )
    line = DSLSelectors$$TilesBehindInLine( origin    = sel,
                                            direction = Get(EdgeExtensions$$Rotate(direction, 3)) )
    r = DSLBehaviors$$SetPersistentData( AbilityOrEffect(this), Caster@DSLSelectors+0x48,
                                         KEY_TARGET + i, EntityId(sel) )
      op_Addition
        DSLBehaviors$$SetPersistentData( AbilityOrEffect(this), Caster@+0x48,
                                         KEY_DIR + i, EntityId(First(line, 1, 0)) )
    return r op_Addition DSLBehaviors$$AddEffect(
        0x5ee = 1518 InstrumentsOfVengeance_LocationTarget,
        AActiveAbility$$get_AbilityStateReference(this),
        source = Owner@+0x30, targets = sel op_Addition line, options = <struct ZEROEE> )

## SEPT points de transcription, tous LUS

1. **`EdgeExtensions$$Rotate(direction, 3)` est evalue A LA CONSTRUCTION**, pas dans l'arbre : c'est
   un appel statique du `GetEffectBehavior`, dont le resultat alimente `DSLFormulas$$Get`. Le port
   le calcule donc en Python (`hex_edge.rotate`), et n'ecrit AUCUN noeud pour lui.
2. **`DSLFormulas$$Get(<edge>)` est la surcharge VECTEUR** (tranchee par XREF entrante : les trois
   appels de `GetEffectBehavior` visent celle a `vector`, pas celle a `amount` ni celle a `s`), et
   son corps construit `Vector(direction = <edge>, amount = 1)`. Le `1` est LU (`TerrainTileCoord..
   ctor(&v, edge, 1, 0)`, ctor a 2 champs mislabelise). Le consommateur,
   `IdunBattle.Entities.Selectors.TilesBehindInLineSelector$$Select`, en fait
   `to = battleQuery.GetTileInDirection(origin, vector)` -- un PAS UNITAIRE. D'ou la composition
   portee `TilesBehindInLine(origin, TileFromVector(origin, edge))`, deja etablie par
   `NextTileInLine` et par `SolarAtomizerAbility$$GetTargetTiles` (`admec.py`).
3. **`settings = null`** : `TilesBehindInLineSelector$$.ctor` alloue alors un
   `TilesBehindInLineSettings` par defaut, dont les deux bools `+0x10`/`+0x11` restent a **0** ->
   `check_walkable = False`, `update_reference = False`. Le gate d'elevation est donc DESARME (il
   vit dans la branche walkable d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`), et la
   ligne traverse le plateau jusqu'au bord.
4. **LES TROIS TRIS SONT CHAINES, DONC LE DERNIER EST LA CLE PRIMAIRE** (`sorted` est STABLE des
   deux cotes) : ennemis DESC, puis amis ASC, puis tuiles-derriere DESC, puis l'ordre du
   `Randomize`. Le natif nomme son 4e argument `ascending`
   (`IdunBattleLogic.Entities.DSLSelectors$$SortByFormula(entities, formula, ascending)`) et le port
   l'expose tel quel : **0 = DESC, 1 = ASC**. Le tri des AMIS est le SEUL a `1` -- la ligne retenue
   est celle qui couvre le PLUS d'ennemis et le MOINS d'allies.
   ⚠ La redaction de `docs/rl/case-1022` §7 ecrivait `desc` sur ce tri-la : c'est FAUX, le litteral
   au call-site est `1`. Corrige ici, au decompile.
5. **`ActiveTarget@+0x68` est l'ELEMENT COURANT DU TRI**, pas une cible de cast : `SortByFormula`
   lie le slot `AbilityEntities+0x20` avant chaque evaluation de la formule (#927), et le port lie
   `subject` ET `active_target`. Dans `behind` comme dans `Units(behind + ActiveTarget)`, il designe
   donc la TUILE DE BORD candidate -- un id de tuile NU.
6. **LA LECTURE ET L'ECRITURE DE LA DONNEE PERSISTANTE NE PORTENT PAS SUR LE MEME SLOT** :
   `GetPersistentData` lit sur `Owner@DSLSelectors+0x30`, `SetPersistentData` ecrit sur
   `Caster@+0x48`. Les deux coincident sur une ACTIVE (convention `Owner == Caster`, `case-224`),
   mais le port ecrit les deux LITTERALEMENT -- c'est ce qui rend la ligne re-verifiable.
7. **LES CLES SONT COMPOSITES** : `String.Concat(<litteral>, i.ToString())`. Les deux litteraux sont
   resolus au `global-metadata.dat` du build (`data/symbols/<build>/metadata/string_literals.tsv`,
   slots `0x3364300` et `0x3364070`) : `"InstrumentsOfVengeance_TargetTile_"` et
   `"InstrumentsOfVengeance_DirectionTile_"`. La 1re passe (`first = true`) ecrit l'indice **0**, la
   2e (`first = false`) **RELIT l'indice 0** puis ecrit l'indice **1**.

## POURQUOI DEUX BRANCHES QUI VISENT LES MEMES BORDS

`EdgeTilesByDirectionSelector$$Select` fond `North_East`/`South_East` sur la MEME bordure (colonne
`COLS - 1`) et `South_West`/`North_West` sur la MEME bordure (colonne `0`) -- deux `case` qui
partagent litteralement le meme bloc. Les deux branches du `Maybe` visent donc le MEME couple de
bordures (droite puis gauche) ; ce qui les separe est la DIRECTION de la ligne tiree depuis chacune,
`Rotate(direction, 3)` valant `4 SW` / `2 SE` pour la branche `{1, 5}` et `5 NW` / `1 NE` pour la
branche `{2, 4}`. Le tirage a 50 % choisit donc l'INCLINAISON des deux lignes, pas leur cote.

## RESIDU -- la PHASE 2 n'est pas portee

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InstrumentsOfVengeance_AttackAbility$$
CreateBehaviour` (+ `$$AttackLine`, `$$AttackTargetTiles`, `$$AttackTileBehavior`) et l'entree de
`1519` dans `PENDING_ATTACK_EFFECTS` (`runner/operations/triggers/pending_attack.py`) sont HORS de
cette tranche. **CONSEQUENCE ASSUMEE ET NOMMEE** : les marques `1518` posees par ce cast ne sont
jamais consommees, et aucun degat ne part au tour suivant. C'est une degradation par DEFAUT
(le moteur fait MOINS que le natif), pas permissive -- a l'oppose exact du no-op silencieux qu'elle
remplace, ou l'IA depensait un tour pour rien ET sans trace. Ce que le port publie desormais : les
deux lignes marquees, l'effet d'armement, et l'overwatch. Residu `#889-r6-r1`.

⚠ **C'EST POURQUOI `1519` N'ENTRE PAS DANS `PENDING_ATTACK_EFFECTS`** : l'y mettre ferait firer
`TriggerAbility(Caster(), 1519)` sur une ability triggered ABSENTE du registre -- le `RemoveEffect`
du meme arbre consommerait alors la marque, et le port RETIRERAIT l'armement sans jamais frapper.
Un no-op silencieux de plus, au lieu d'un manque visible.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import If, op_add
from ....entities.effect_type import EffectType
from ....entities.formulas import Count, EntityId, GetPersistentData
from ....entities.selectors.accessors import ActiveTarget, Owner
from ....entities.selectors.geometry import (Cache, EdgeTilesByDirection, Entity, PickFirstN,
                                             Randomize, TileFromVector, TilesBehindInLine)
from ....entities.selectors.tiles import Caster, TileUnion
from ....entities.selectors.units import Enemies, Friends, SortByFormula, Sub, Units
from ....entities.triggers import MaybeTrigger, Not, has_adjacent_enemies
from ....entities.unit_selection_type import UnitSelectionType
from ....hex_edge import Edge, rotate
from ..base import ActiveAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import ActivateEffect, AddBondEffect, AddEffect
from ..behaviours.persistent_data import SetPersistentData
from ..targeting import RANGE_SELF, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting_rule import TargetingRule as TR

if TYPE_CHECKING:
    from ...state import State


#: `ActiveAbilityType.InstrumentsOfVengeance` -- l'id 1215, et la cle du gameconfig.
IOV_ID = ActiveAbilityType.InstrumentsOfVengeance.name
IOV_ABILITY = int(ActiveAbilityType.InstrumentsOfVengeance)               # 0x4bf = 1215
#: `EffectType.InstrumentsOfVengeance_LocationTarget` -- la MARQUE, posee sur les TUILES de la ligne.
IOV_LOCATION_TARGET = int(EffectType.InstrumentsOfVengeance_LocationTarget)   # 0x5ee = 1518
#: `EffectType.InstrumentsOfVengeance_PendingAttack` -- l'ARMEMENT de la phase 2, sur le CASTER.
IOV_PENDING_ATTACK = int(EffectType.InstrumentsOfVengeance_PendingAttack)     # 0x5ef = 1519
#: `EffectType.Overwatch_AutoAttack` -- l'overwatch que le cast RE-ARME s'il n'a personne au contact.
IOV_OVERWATCH = int(EffectType.Overwatch_AutoAttack)                          # 0x3f1 = 1009
#: Le `0x32` de `DSLTriggers$$Maybe(chance)` -- un POURCENTAGE, pas un ordinal d'enum.
IOV_MAYBE_CHANCE = 50
#: `UnitSelectionType` LU au dernier argument des `Units`/`Friends`/`Enemies` du decompile.
IOV_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)                 # 3
#: Cles de donnee persistante, LUES : string literals du build resolus par
#: `data/symbols/<build>/metadata/string_literals.tsv` (slots `0x3364300` et `0x3364070`), passees a
#: `System.String$$Concat(<litteral>, i.ToString())` puis aux quatre noeuds `*PersistentData`.
IOV_KEY_TARGET_TILE = "InstrumentsOfVengeance_TargetTile_"
IOV_KEY_DIRECTION_TILE = "InstrumentsOfVengeance_DirectionTile_"


def instruments_of_vengeance_line(origin, direction: int):
    """`DSLSelectors$$TilesBehindInLine( origin, DSLFormulas$$Get(EdgeExtensions$$Rotate(direction, 3)) )`
    -- la surcharge dont le 2e argument est une formule VECTEUR (xrefs entrantes : les appels de
    `...InstrumentsOfVengeanceAbility$$GetEffectBehavior` visent
    `IdunBattleLogic.Entities.DSLSelectors$$TilesBehindInLine(origin, direction, settings, maxAmount)`,
    pas la surcharge `directionTileSelector`).

    `TilesBehindInLineSelector$$Select` resout `to = battleQuery.GetTileInDirection(origin, vector)`
    avec `vector.amount = 1` -> le VOISIN de `origin` dans la direction opposee a `direction`. D'ou
    `TileFromVector(origin, <arete opposee>)`, meme composition que `NextTileInLine`.

    `settings = null` -> defauts `check_walkable = False` / `update_reference = False` (les deux
    champs du `TilesBehindInLineSettings` alloue par le ctor restent a zero) ; `maxAmount = null` ->
    la ligne va JUSQU'AU BORD du plateau. La 1re tuile rendue est `to`, pas `origin`."""
    back = rotate(direction, 3)             # `EdgeExtensions$$Rotate(direction, 3)`, cote PYTHON
    return TilesBehindInLine(origin, TileFromVector(origin, Const(int(back))))


def instruments_of_vengeance_effect_behavior(direction: int, first: bool):
    """`...InstrumentsOfVengeanceAbility$$GetEffectBehavior(direction, first)` -- MIRROR 1:1, cf. la
    docstring du module pour le decompile terme a terme.

    `first` porte DEUX roles distincts, tous deux lus : (a) l'INDICE de la cle composite
    (`((byte)first & 0xff) ^ 1` -> `0` quand `first`, `1` sinon), et (b) la presence du terme de
    SOUSTRACTION, qui n'existe que sur la 2e passe et retranche la ligne ecrite par la 1re."""
    idx = 0 if first else 1                       # `local_res8[0] = ((uint)first & 0xff) ^ 1`
    # `behind` : la ligne tiree DEPUIS la tuile candidate -- `ActiveTarget` est l'element courant du
    # tri, donc cette formule se re-evalue par tuile de bord.
    behind = instruments_of_vengeance_line(ActiveTarget(), direction)
    edge = EdgeTilesByDirection(Const(int(direction)))
    if not first:
        # `edge -= TilesBehindInLine(Entity(pd(KEY_TARGET + "0")), Entity(pd(KEY_DIR + "0")))` --
        # la surcharge `directionTileSelector` (DEUX selecteurs), pas la surcharge vecteur : c'est
        # l'autre adresse de `DSLSelectors$$TilesBehindInLine`, tranchee par la xref entrante.
        # L'indice relu est le litteral **0** (`local_res18[0] = 0`), jamais `idx`.
        prev_target = Entity(GetPersistentData(IOV_ABILITY, Owner(), IOV_KEY_TARGET_TILE + "0"))
        prev_dir = Entity(GetPersistentData(IOV_ABILITY, Owner(), IOV_KEY_DIRECTION_TILE + "0"))
        edge = Sub(edge, TilesBehindInLine(prev_target, prev_dir))
    # `Units(behind op_Addition ActiveTarget@+0x68, unique: true, 3)` -- les occupants de la ligne,
    # tuile candidate COMPRISE. Le flag `unique` n'est pas materialise par le port (residu anterieur
    # #433-r3-r1a-r1) ; `TileUnion` dedoublonne deja les TUILES.
    on_line = Units(TileUnion(behind, ActiveTarget()), selection_type=IOV_SELECTION)
    sel = Randomize(edge)
    # ⚠ TROIS TRIS CHAINES, STABLES : le DERNIER est la cle PRIMAIRE. Les litteraux `ascending`
    # sont lus un par un au call-site (`0`, `1`, `0`), jamais deduits par symetrie.
    sel = SortByFormula(sel, Count(behind), ascending=False)
    sel = SortByFormula(sel, Count(Friends(on_line, reference=Owner(),
                                           selection_type=IOV_SELECTION)), ascending=True)
    sel = SortByFormula(sel, Count(Enemies(on_line, reference=Owner(),
                                           selection_type=IOV_SELECTION)), ascending=False)
    # `Cache(First(sel, 1, 0), true)` : la tuile RETENUE. Le `Cache` compte -- ce selecteur est
    # evalue QUATRE fois en aval (deux `SetPersistentData`, la ligne, l'`AddEffect`), et le natif
    # memoise entre elles. Sans memoisation le `Randomize` en amont rendrait un choix DIFFERENT a
    # chaque lecture, et les deux cles persistantes designeraient deux lignes distinctes.
    chosen = Cache(PickFirstN(sel, 1))
    line = instruments_of_vengeance_line(chosen, direction)
    # ⚠ ECRITURE sur `Caster@+0x48`, alors que la LECTURE ci-dessus porte sur `Owner@+0x30`.
    set_target = SetPersistentData(IOV_ABILITY, Caster(), IOV_KEY_TARGET_TILE + str(idx),
                                   EntityId(chosen))
    # `EntityId(First(line, 1, 0))` : la PREMIERE tuile de la ligne, c.-a-d. le voisin de `chosen`
    # dans la direction opposee -- c'est ce couple (tuile, voisin) que la phase 2 rejoue en
    # `TilesBehindInLine(from = <cle TARGET>, to = <cle DIRECTION>)`.
    set_dir = SetPersistentData(IOV_ABILITY, Caster(), IOV_KEY_DIRECTION_TILE + str(idx),
                                EntityId(PickFirstN(line, 1)))
    mark = AddEffect(IOV_LOCATION_TARGET, EffectType.InstrumentsOfVengeance_LocationTarget.name,
                     TileUnion(chosen, line),          # `targets = sel op_Addition line`
                     duration_rounds=None,             # `options` ZEROEE -> DefaultAmountOfRounds
                     source_ref=Owner())               # `source = Owner@+0x30` (4e argument natif)
    return op_add(op_add(set_target, set_dir), mark)


def instruments_of_vengeance_tree(rng):
    """Arbre de `...InstrumentsOfVengeanceAbility$$ExecuteBehaviour` -- MIRROR 1:1, cf. la docstring
    du module.

    `rng` est pris au CONSTRUCTEUR, comme le natif : `MaybeTrigger` porte son PRNG en champ
    (`+0x18`, pose par la factory depuis `DSLFactory+0x18`), pas en entree de contexte.

    ⚠ **LES DEUX BRANCHES NE SONT PAS SYMETRIQUES DANS L'ORDRE DES PASSES** : chacune commence par
    `first = true` (qui ECRIT l'indice 0) puis enchaine `first = false` (qui RELIT l'indice 0 pour
    s'exclure, puis ecrit l'indice 1). Inverser les deux appels ferait relire une cle vide et les
    deux lignes pourraient se superposer."""
    branch_a = op_add(instruments_of_vengeance_effect_behavior(int(Edge.North_East), True),
                      instruments_of_vengeance_effect_behavior(int(Edge.North_West), False))
    branch_b = op_add(instruments_of_vengeance_effect_behavior(int(Edge.South_East), True),
                      instruments_of_vengeance_effect_behavior(int(Edge.South_West), False))
    r = If(MaybeTrigger(rng, IOV_MAYBE_CHANCE), branch_a, branch_b)
    arm = AddBondEffect(IOV_PENDING_ATTACK, EffectType.InstrumentsOfVengeance_PendingAttack.name,
                        Owner(), Owner(), duration_rounds=None, bonded_ref=Owner())
    overwatch = If(Not(has_adjacent_enemies(Owner(), Owner())),
                   ActivateEffect(Owner(), IOV_OVERWATCH, EffectType.Overwatch_AutoAttack.name))
    return op_add(op_add(r, arm), overwatch)


class InstrumentsOfVengeanceAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$ExecuteBehaviour`
    (id 1215, `darkaBossLion` « le Lion » -- GuildBoss DarkAngels, kind `npc`).
    Arbre DSL `instruments_of_vengeance_tree`.

    CONFRONTABILITE : porteur `npc`. Le playbook (`#27-r6`) etablit deja que l'utilite de 1215 ne
    lit du caster que son CAMP -- ni stat, ni trait, ni arme, ni portee --, ce qui rend l'ability
    GREFFABLE sur une unite du pool (`case-92` §5bis). Le behaviour porte ici ne lit pas davantage
    du caster : seuls `Owner@+0x30` et `Caster@+0x48` y entrent, comme references d'entite.

    Turn-flags = defauts base (1215 ABSENT des overrides `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> le cast termine le tour et pose `ActiveAbilityUsed`.

    Diag : `{posed: [...], marked: [...], persisted: [...], activated: [...], dsl: True}`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.InstrumentsOfVengeance)   # 1215
    ABILITY_ID = IOV_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme **STATIC-COPY** : l'ability n'appelle AUCUNE
    # surcharge de `IdunBattle.Core.Services.TargetingOptions$$.ctor`.
    # `...InstrumentsOfVengeanceAbility$$.ctor` recopie les 0x40 octets du preset
    # `<TargetingOptions statics>+0x280` dans une struct locale et la passe TELLE QUELLE a
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, 2)`.
    # Le masque effectif est donc la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` en `<preset>+0x28` -- RELUE au decompile de
    # `rnca9r7q6c` pour CETTE ability, pas heritee d'une voisine :
    #     `*(lVar4 + 0x2a8) = 0x8004`   avec `lVar4 = <TargetingOptions statics>`, preset a `+0x280`
    #     0x8004 = CasterIsPossibleTarget(0x8000) | CasterMatchesDynamicRule(0x4)
    # ⚠ C'est le MEME preset que `1216 MartialExemplar`, mais 1216 passe ENSUITE par la surcharge
    # PRESET+FLAGS avec `additionalRules = 0x10` -> `0x8014`. **1215 n'a donc PAS
    # `CasterHasNotMoved`** : elle reste castable APRES deplacement, la ou 1216 ne l'est pas. C'est
    # cette difference que la face DECISION exploite (l'utilite de 1215 est POSITION-DEPENDANTE,
    # evaluee par tuile atteignable -- cf. `playbook/loki_custom.py`).
    # `isSelfCasting` = `<preset>+0x00` = 1 ; `forceMeleeTarget` = `<preset>+0x20` = 1 =
    # `RangedBool.False`.
    # PORTEE : le bloc `<preset>+0x08..0x1f` est copie par le `cctor` depuis
    # `<TargetingRange statics>+0x60`, que `IdunBattle.Core.Services.TargetingRange$$.cctor` pose a
    # `{onlyAdjacent = RangedBool.False, overrideRange = Nullable(0), overrideRangeFunc = null}` =
    # **RANGE_SELF**, portee NULLE -- le gate attendu d'un self-cast `CasterIsPossibleTarget`.
    # ⚠ Ces quatre valeurs MIGRENT depuis `TARGETING_OPTIONS_UNPORTED[1215]` (contrat de DISJONCTION
    # d'`abilities/targeting.py` : une ability a UNE source de masque, jamais deux) ; elles ont ete
    # RE-LUES au decompile avant migration et sont bit-identiques a celles qui vivaient la-bas.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterIsPossibleTarget | TR.CasterMatchesDynamicRule,
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        instruments_of_vengeance_tree(state.rng).execute(entities, ectx)
        posed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                  "source": p.get("source"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddBondEffect")]
        persisted = [{"key": p.get("key"), "unit": p.get("unit"), "value": p.get("value")}
                     for n, p in ectx.emitted if n == "SetPersistentData"]
        activated = [{"owner": p.get("owner"), "effect": p.get("effect_type"),
                      "created": p.get("created"), "activated": p.get("activated")}
                     for n, p in ectx.emitted if n == "ActivateEffect"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "posed": posed,
                # Les TUILES marquees -- c'est l'observable de la phase 1, et le seul.
                "marked": [p.get("target") for p in posed
                           if p.get("effect") == IOV_LOCATION_TARGET],
                "armed": [p.get("target") for p in posed
                          if p.get("effect") == IOV_PENDING_ATTACK],
                "persisted": persisted, "activated": activated,
                "dsl": True}
