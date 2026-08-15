"""Primitives de SELECTEUR partagees par les effets-AURA a stat-mod projete.

Un `ADynamicStatModifierEffect` dont le `CreateTargetSelector` designe D'AUTRES unites doit,
cote port, RE-EVALUER ce selecteur contre l'ECS (`aura_stat_modification_targets`, interface
consommee par `runner/operations/aura_stat_mods.py`). Plusieurs effets natifs partagent
LITTERALEMENT le meme noeud DSL de tete -- le binaire lui-meme le prouve : le corps de
`CreateTargetSelector` de `LionHelm_ExtraDmgEffect` et de `LionHelm_ExtraBlockDamageEffect` est
DEDUPLIQUE (une seule adresse, cf. l'en-tete de `loki/dark_angels_passives.py`), et
`PathOfCommandExtraCritEffect$$CreateTargetSelector` ouvre sur le MEME appel a
`IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends` avec les MEMES arguments litteraux
(`unique = true`, `unitSelectionType = 3 = OnlyAliveAndTargetable`).

Un seul noeud natif = un seul port : ce module est le FOYER de ce noeud. Les effets y ajoutent
LEURS filtres propres (`UnitsFromFaction`, `UnitsWithStatBiggerThan`, ...) par-dessus.
"""
from __future__ import annotations

from typing import List

from ..effect_type import EffectType   # #270-r1-r1 : `UNTARGETABLE_EFFECT_TYPES`
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1). Aucun seeding :
# ce selecteur recoit l'ECS, donc `State.board`. `pathfinding.board` n'importe RIEN d'`engine`,
# `engine.battle_query` n'importe que `hexgeo` + `.hex_corner`.
from ..pathfinding import board as _board
from ... import battle_query as _bq

#: Les `EffectType` dont la classe native derive d'`IdunBattle.Entities.Effects.Common.UntargetableEffect`
#: ET dont le port a CONFRONTE la tranche -- FOYER UNIQUE de la non-ciblabilite cote port
#: (`engine.ai.state_bridge._is_untargetable` le re-exporte).
#:
#: Le flag ne vient PAS de l'effet feuille : `UntargetableEffect$$ApplyInternal` fait
#: `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(0x11)` sur la CIBLE et `$$RevertInternal`
#: le retire. C'est donc un DOMAINE, pas une constante.
#: ⚠ **PAS << pour TOUTE sous-classe >>, ET C'EST LU (#433-r3-r2-r1, build `t6dpr4k06g`)** : la pose
#: est GARDEE, le retrait ne l'est pas. `UntargetableEffect$$ApplyInternal` ouvre sur
#: `if (!this.IsUntargetableEnabled(owner, target, effect)) return;` -- un VIRTUEL declare par
#: `UntargetableEffect` elle-meme, absent des deux tables de symboles (corps deduplique), donc
#: lisible seulement par le `global-metadata.dat`. `$$RevertInternal`, lui, est un tail call NU vers
#: `UnitFlagsComponent$$Remove`, sans aucun gate.
#: Fermeture NATIVE du domaine (`data/symbols/<build>/frida/classes.tsv`, parent
#: `UntargetableEffect`) : `ATeleportingEffect` -- 4 derivees, `1035 TeleportStrike_TeleportingIn`,
#: `1140 StormboyzStrike_TeleportingIn`, `1238 FearOfTheUnseen_TeleportingIn`,
#: `1573 TitanhammerSquad_TeleportingIn` -- et `JustSummonedEffect`. La base elle-meme est
#: CONCRETE et porte son propre `EffectType` : `1044 Untargetable`.
#: RESTENT DEHORS, et pour des raisons DISTINCTES :
#:   * `1573` -- **REFUS PROUVE, ce n'est PAS un manque a combler.**
#:     `TitanhammerSquad_TeleportingInEffect` SURCHARGE `IsUntargetableEnabled` avec le corps
#:     `32 c0 c3` (`xor al,al ; ret`) = **false**, donc `$$ApplyInternal` sort AVANT le
#:     `UnitFlagsComponent$$Add` : cet effet ne pose JAMAIS le flag. L'inscrire produirait une
#:     divergence **RESTRICTIVE**. C'est la SEULE classe du build a surcharger ce getter -- 2
#:     declarantes sur 465 (la base et elle). Derive deux fois par des machineries INDEPENDANTES,
#:     avec 3 controles d'alignement locaux. La mention anterieure (<< arrive avec #448-r2d >>) le
#:     rangeait parmi les manques : elle etait FAUSSE, et c'est exactement le genre de ligne qui
#:     fait porter une divergence en croyant fermer un trou.
#:   * `1044 Untargetable` (la BASE) -- **CANDIDAT NUMERO UN, non inscrit faute de CONFRONTATION.**
#:     Ses deux faces sont portees, dans le meme arbre DSL, sur 2 des 4 chemins natifs :
#:     `runner/abilities/aeldari.py` (`KissOfDeathAbility$$ExecuteBehaviour` -- `AddEffect(1044,
#:     Caster())` puis `RemoveEffect(1044, Caster())`) et `runner/abilities/loki/wall_of_mirrors.py`
#:     (`AddEffect` ... `FlyUnit` ... `RemoveEffect`). Le critere du domaine (<< les DEUX faces >>)
#:     est donc satisfait, et l'ecart serait PERMISSIF : pendant le vol, le caster reste enumerable
#:     cote port la ou le natif l'exclut. Ce qui manque est la mesure exigee par la derniere ligne
#:     de ce commentaire -- **est-ce OBSERVABLE ?** Si rien n'inspecte l'etat entre le `AddEffect` et
#:     le `RemoveEffect` du meme arbre, l'inscription serait INERTE, c'est-a-dire le vice reproche
#:     juste en dessous a `1`/`1230`/`1390`. Montage a jouer : un porteur de `KissOfDeath` ou de
#:     `WallOfMirrors`, et regarder si un overwatch se declenche sur le caster pendant le `FlyUnit`,
#:     natif contre port. Tant que ce n'est pas mesure, l'inscrire violerait la regle de ce foyer.
#:   * `JustSummonedEffect` (4 `EffectType` : 1, 1061, 1230, 1390) -- **REFUS RE-MESURE (#1074)**.
#:     L'etage manquant n'est plus le meme selon le membre, et c'est ce qui rend la regle unique :
#:     un membre n'entre au domaine que si le port porte SES DEUX FACES, le POSEUR **et** le
#:     RETIREUR.
#:       - `1`, `1230`, `1390` : AUCUN POSEUR. `1230` est pose puis retire dans le meme behaviour
#:         natif et le port l'OMET (`triggers/loki/sworn_protector.py`) ; `1390` n'est pas pose
#:         (`triggers/loki/spiritual_leader.py` : « ni le flag 17 ni l'effet 1390 ne sont poses par
#:         le port ») ; `1` n'a aucun site. Les inscrire serait **strictement inerte** (`has_effect`
#:         rendrait toujours faux) tout en donnant l'illusion d'avoir ferme le trou.
#:       - `1061` : POSE depuis #963 -- `GeminaeSuperiaAbility$$CreateBehaviour`
#:         (`triggers/loki/geminae_superia.py`) fait `AddEffect(0x425, ..., Target@+0x60)`, donc sur
#:         CELESTINE. Ce qui manque ici est le RETRAIT :
#:         `IdunBattle.Entities.Effects.Loki.JustSummonedEffect$$CreateRemoveEffectTrigger`
#:         = `On(0x3a = PhaseEnd) | (On(0x1f = PreUnitMove, true) & get_OwnerIsActor)
#:         | (On(0x2a = PreUnitAbility, true) & get_OwnerIsActor)` n'est PAS porte (aucune entree
#:         `EFFECT_TRIGGERS[1061]`), et le flag `UnitFlag 0x11` ne part QUE par `$$RevertInternal`,
#:         c'est-a-dire au retrait de l'effet. L'inscrire aujourd'hui rendrait Celestine non
#:         ciblable POUR LE RESTE DE LA BATAILLE -- divergence bien pire que l'absence
#:         d'inscription, et RESTRICTIVE au point de la rendre inattaquable en self-play.
#:     Le cran executable est BIDIRECTIONNEL (`test_448_r2b_stormboyz_teleporting_in_offline.py::
#:     test_the_just_summoned_family_stays_out_because_its_REMOVAL_is_not_ported`) : il rougit aussi
#:     le jour ou le retrait est porte sans que l'inscription suive.
#: On n'inscrit que ce qui est porte ET confronte SUR CE CANAL : un ajout speculatif retirerait des
#: cibles a l'IA sans mesure, et c'est une degradation SILENCIEUSE.
# #270-r1-r1 : membres nommes -- le commentaire ci-dessus nomme deja les quatre derivees, dont ces
# deux INSCRITES ; confronte a `frida/enums.tsv`, le nom matche 2/2 `EffectType`.
#
# `1238` INSCRIT par #448-r2b-r1. Ce n'est pas un ajout speculatif : (i) la classe native
# `IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect` derive d'`ATeleportingEffect`
# donc d'`UntargetableEffect` (`frida/classes.tsv`), (ii) l'effet est REELLEMENT POSE par le port --
# `runner/abilities/tyranids.py::fear_of_the_unseen_tree` fait `AddEffect(1238, ..., Caster(),
# duration_turns=Sum(TurnsFromRounds(1), Direct(1)))` au cast de `1115 FearOfTheUnseen`
# (`tyranDeathleaper`, HERO, AU POOL) -- et (iii) le porteur reste SUR SA TUILE cote port, donc il
# restait ENUMERABLE comme cible pendant tout son round de disparition, la ou i2 dit « The
# Deathleaper vanishes and CANNOT BE TARGETED or damaged for 1 round ». Ecart PERMISSIF ferme ;
# le sens du correctif est RESTRICTIF, et c'est pourquoi il est confronte live
# (`test_448_r2b_r1_fear_of_the_unseen_untargetable_live.py`).
UNTARGETABLE_EFFECT_TYPES = (EffectType.TeleportStrike_TeleportingIn,      # 1035
                             EffectType.StormboyzStrike_TeleportingIn,    # 1140
                             EffectType.FearOfTheUnseen_TeleportingIn)    # 1238


def hex_distance(a, b) -> "int | None":
    if not a or not b:
        return None
    import hexgeo
    return hexgeo.distance(tuple(a), tuple(b))


def is_targetable(state, unit_id: int) -> bool:
    """Volet `OnlyAliveAndTargetable` du `unitSelectionType = 3` : une unite en DEEP STRIKE
    n'est PAS ciblable, donc PAS selectionnee. Mesure live (LionHelm, `docs/rl/` case Dark Angels) :
    `darkaTerminator` en teleport-in ne recoit RIEN.

    Le flag natif vient de la BASE `IdunBattle.Entities.Effects.Common.UntargetableEffect`
    (`$$ApplyInternal` -> `UnitFlagsComponent$$Add(0x11)`), pas de l'effet feuille -- d'ou un
    DOMAINE (`UNTARGETABLE_EFFECT_TYPES`, en tete de module) et non une constante.

    ## ⚠ NE PAS << HARMONISER >> LES DEUX CANAUX D'AURA (#926-r1)

    Ce gate est appele par `surrounding_friends` / `adjacent_friends_including_owner` (canal
    STAT-MOD) et **PAS** par `loki/first_among_traitors.py::create_aura_attack_damage_bonus_for_ally`
    (canal DAMAGE-AURA). Les deux mesures qui l'imposent sont fermes et OPPOSEES -- `darkaTerminator`
    en `TeleportStrike_TeleportingIn` ne recoit RIEN de `LionHelm` ; `blackTerminator` dans le meme
    etat RECOIT le bonus de `FirstAmongTraitors`, oracle natif en accord sur 25 tuiles. Ajouter le
    gate au second, ou le retirer du premier, casserait l'un des deux.

    **L'ASYMETRIE N'EST PAS DANS LE SELECTEUR -- c'est LU, les deux corps ont ete decompiles cote a
    cote.** `IdunBattle.Entities.Effects.Loki.LionHelm_ExtraBlockDamageEffect$$CreateTargetSelector`
    et `IdunBattle.Entities.Effects.Loki.FirstAmongTraitors_ExtraDmgEffect$$CreateTargetSelector`
    ouvrent sur le MEME `IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(Owner@+0x30,
    <range>, unique = 1, unitSelectionType = 3)` ; le second n'ajoute qu'un
    `UnitsWithTrait(_, 0x7ea = UnitTrait.Chaos, 3)` par-dessus. Meme litteral, meme noeud.

    **CE QUI DIFFERE EST LA FENETRE DE RE-EVALUATION**, et il y a DEUX lectures :

      1. `IdunBattle.Entities.Effects.Loki.FirstAmongTraitors_ExtraDmgEffect$$GetRefreshTriggers`
         rend `new RefreshEffectTrigger[2] { 5 = UnitsChanged, 7 = UnitPositionChanged }` -- ecrit
         **INLINE** (`arr[0] = 5 ; arr[1] = 7`), donc entierement lisible, contrairement aux
         surcharges qui passent par `System.Runtime.CompilerServices.RuntimeHelpers$$InitializeArray`.
         `EffectsChanged = 4` n'y est **PAS**. Les DEUX `LionHelm_*`, eux, ne declarent AUCUN
         `GetRefreshTriggers` (aucune des surcharges du build ne leur appartient) -> defaut `null`,
         et `IdunBattle.Entities.Effects.BaseEffect$$ShouldRefreshForTrigger` traite `null` comme
         << rafraichir sur TOUT >>. L'ensemble des declencheurs de `LionHelm` est donc un
         **SUR-ENSEMBLE STRICT** de celui de `FirstAmongTraitors`.
      2. `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` **SORT EN AMONT** quand
         l'etat est en SIMULATION et que
         `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$ShouldRefreshDuringSimulation`
         rend faux : ni la condition d'activite ni les cibles ne sont rafraichies. Pendant toute la
         face DECISION/PREDICTION, `EffectComponent.Targets@+0x48` est donc **FIGE**.

    **POURQUOI LA CAUSE << flag pas encore visible >> EST REFUTEE, et ce n'est pas une elimination.**
    Le flag `UnitFlag 0x11` est pose par `UntargetableEffect$$ApplyInternal` **sur la CIBLE** : c'est
    un etat PARTAGE, que les deux selecteurs -- identiques -- interrogent de la meme facon. Un etat
    partage ne peut pas rendre deux reponses differentes a deux predicats identiques **au meme
    instant** ; il ne le peut que s'ils sont evalues a des instants DIFFERENTS. C'est un argument de
    structure, et il designe la fenetre, pas le predicat.

    RESTE OUVERT (#926-r1, retreci) : quel `RefreshEffectTrigger` la POSE d'un `UntargetableEffect`
    emet, et si `1063`/`1214` appartiennent au `HashSet` de simulation (le `.cctor` de
    `StaticBattleRules.Effect` depasse le budget du decompilateur ; les appels au slot 0x2f de
    `Core.Services.OperationProcessor` ne sont pas atteignables par xref)."""
    if state.effects is None:
        return True
    for e in state.effects.by_unit.get(int(unit_id), []) or []:
        if not e.consumed and int(getattr(e, "effect_type", -1)) in UNTARGETABLE_EFFECT_TYPES:
            return False
    return True


def faction_of(state, unit_id: int) -> "str | None":
    """`FactionId` gameconfig de l'unite (resolu par `visual_id`) -- le pendant offline des DEUX
    noeuds natifs qui interrogent la faction d'une entite du selecteur :
    `IdunBattleLogic.Entities.DSLSelectors$$UnitsFromFaction` (LionHelm_ExtraBlockChance) et
    `IdunBattleLogic.Entities.DSLTriggers$$HasFaction` pose en filtre
    (`IdunBattle.Entities.Effects.Loki.KustomForceFieldEffectReworked$$CreateTargetSelector`).

    Les DEUX resolvent `IdunBattle.Entities.UnitExtensions$$HasFaction`, qui compare
    `System.Enum.ToString(UnitFaction)` au `FactionComponent+0x30` (une CHAINE) -- d'ou la
    comparaison par NOM cote port, jamais par ordinal.

    HISSE ICI (#930) depuis `loki/dark_angels_passives.py`, ou il vivait en prive : le module est le
    FOYER declare des primitives de selecteur d'aura (`is_targetable`, `surrounding_friends`), et un
    second porteur du meme accesseur aurait ete un fork."""
    from ...runner.components import StatsComponent
    ent = state.get_entity(unit_id)
    sc = ent.get_component(StatsComponent) if ent is not None else None
    vid = getattr(getattr(sc, "ctx", None), "visual_id", None)
    if vid is None:
        return None
    import gameconfig as GC
    return (GC.unit(vid) or {}).get("FactionId")


def adjacent_friends_including_owner(state, owner_id: int) -> List[int]:
    """`Owner@DSLSelectors+0x30 + AdjacentFriends(Owner, unique = true, unitSelectionType = 3)`
    evalue contre l'ECS -- le noeud de TETE, commun aux DEUX `CreateTargetSelector` de
    `KustomForceFieldReworked` (#930).

    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends`, surcharge `(unit, unique,
    selectionType)` -- tranchee par le TYPE des arguments du call-site (le 3e est le litteral
    booleen `1`, pas un `TargetsSelector*` : la surcharge `(unit, unitTile, unique)` est donc
    exclue), corps natif :

        Friends( unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType )

    Le `op_Subtraction` EXCLUT le porteur -- puis le `IdunBattle.DSL.TargetsSelector$$op_Addition`
    du `CreateTargetSelector` appelant le RE-AJOUTE. Le porteur est donc DANS sa propre aura, et
    c'est ce qui distingue ce noeud de `surrounding_friends` (qui l'exclut definitivement) et
    d'`IconOfObstinacy`, qui porte le MEME `AdjacentFriends` **sans** le `op_Addition`.
    GROUND TRUTH live (#930, `statModSources`, `orksBigMek`) : le porteur se buffe lui-meme.

    ⚠ ~~L'adjacence est `hexgeo.distance == 1` ... Le corriger ICI seulement serait un fork.~~
    **CABLE (#943-r7, 2026-08-15)**, et l'argument du fork est TOMBE avec le fait qui le portait :
    la famille est desormais sur le foyer `engine.battle_query.is_adjacent`
    (`entities/effect_targets.py::_adjacent_friends`, les quatre compteurs de `Scene`, les ctx
    d'aura de `hits.py`/`imperative.py`/`icon_of_obstinacy.py`, `traits/combat.py`). Ce site-ci
    n'avait AUCUN blocage propre -- il recoit l'ECS, donc `State.board` -- et il n'a qu'UNE face
    (`kustom_force_field.py`, cote runner), donc aucune jumelle ne peut diverger.
    Substrat : `Units(AdjacentTiles(unit), ...)` -> la liste STOCKEE du `ConnectivityComponent`,
    puis la porte `|elev(a) - elev(b)| < 2` de
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` (#271).
    L'ENUMERATION part du PORTEUR : `is_adjacent(owner, ami)`, pas l'inverse."""
    from ...runner.components import (PositionComponent, OwnerComponent, UnitComponent,
                                      HealthComponent)
    owner = state.get_entity(owner_id)
    if owner is None:
        return []
    opc = owner.get_component(PositionComponent)
    ooc = owner.get_component(OwnerComponent)
    if opc is None or ooc is None:
        return []
    # #943-r7 -- board absent (`State.board is None`) -> `(None, None)` -> repli geometrique NOMME.
    elev_by_pos, neigh_by_pos = _board.adjacency_channels(getattr(state, "board", None))
    out: List[int] = [int(owner_id)]           # `op_Addition(Owner, ...)` : le porteur est cible
    for uid, ent in state.entities.items():
        if int(uid) == int(owner_id):
            continue                           # deja pose par le terme `Owner` ci-dessus
        uc = ent.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue                           # OnlyAlive
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != ooc.team:
            continue                           # `Friends` = meme equipe que le porteur
        if not _bq.is_adjacent((opc.col, opc.row), (pc.col, pc.row),
                               elev_by_pos, neigh_by_pos):
            continue                           # `AdjacentTiles(Owner)` : la liste STOCKEE (#943-r7)
        if not is_targetable(state, uid):      # volet Targetable du `unitSelectionType = 3`
            continue
        out.append(int(uid))
    return out


def surrounding_friends(state, owner_id: int, rng: int) -> List[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(unit = Owner@0x148, range,
    unique = true, unitSelectionType = 3 = OnlyAliveAndTargetable)` evalue contre l'ECS.

    = `SurroundingTiles(range) - Tiles(self)` -> `Friends` : les unites de la MEME equipe que le
    porteur, a distance hex <= `range`, **le porteur EXCLU** (le noeud retire sa propre tuile), et
    seulement celles qui sont VIVANTES et CIBLABLES.

    Renvoie les entity-ids (ordre de `state.entities`, sans importance : le consommateur en fait
    un `set`)."""
    from ...runner.components import (PositionComponent, OwnerComponent, UnitComponent,
                                      HealthComponent)
    owner = state.get_entity(owner_id)
    if owner is None:
        return []
    opc = owner.get_component(PositionComponent)
    ooc = owner.get_component(OwnerComponent)
    if opc is None or ooc is None:
        return []
    out: List[int] = []
    for uid, ent in state.entities.items():
        if uid == owner_id:                        # `- Tiles(self)` : la source est exclue
            continue
        uc = ent.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue                               # OnlyAlive
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != ooc.team:
            continue                               # Friends = meme equipe que le porteur
        d = hex_distance((opc.col, opc.row), (pc.col, pc.row))
        if d is None or d > int(rng):
            continue
        if not is_targetable(state, uid):          # volet Targetable du unitSelectionType
            continue
        out.append(uid)
    return out
