"""`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook` -- face ATTACK du triggered
`SaviorProtocols` (1120), 3e des 20 residus ATTACK de #419. Porteurs DISPATCHES : 6, tous hors
lineup -- 3 npc (`tauNpc2DroneSniper`, ...) et 3 SUMMONS (`tauSmnDroneCommandLink`,
`tauSmnDroneSniper`, `tauSmnDroneShield`).

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae et BarbedOvipositor
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__5` avec **TROIS** champs -- case @+0x20, `this` (le playbook) @+0x28, delegue scorer @+0x30 --
la ou `BarbedOvipositor$$CalculateAttackUtilityInStepsInternal` n'en ecrit que DEUX (case @+0x20,
delegue @+0x28) : son corps n'a pas besoin du playbook, celui-ci si (il y lit `state`). Et la face
MOVE de CETTE MEME classe les dispose encore autrement (`d__4` : playbook @+0x20, case @+0x28,
delegue @+0x30). La disposition se LIT dans la methode-usine ; la transposer d'un voisin -- fut-ce
l'autre face de la meme classe -- donne le mauvais champ. Corps :
`SaviorProtocolsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__5$$MoveNext` -- UN SEUL
`yield`, deux sorties :

    Fix64 u = Fix64.op_Implicit(0);
    if (EntityExtensions.HasEffect(case.Target, this.<state>, (EffectType)0x462, onlyActive: true))
        u = Fix64.op_Addition(u, Fix64.op_Implicit(GetUtilityValue("SAVIORPROTOCOLS_MarkedTarget")));
    yield return u;

Quatre lectures qui ne se devinent pas -- et aucune ne se generalise depuis un voisin de la liste :

1. **Le predicat porte sur la CIBLE et sur RIEN d'autre.** Ni stats, ni traits, ni faction, ni
   position du caster ; ni la tuile d'attaque (contrairement a `SuppressiveFire`, qui NIE
   `AreEntitiesAdjacent(casterTile, target)`) ; ni la prediction de degat du case (contrairement a
   `BarbedOvipositor`, qui lit `UtilityAttackCase@+0x28`). Le corps ne touche que `case@+0x20` (la
   cible) et le champ `state` du playbook. C'est ce qui rend l'ability GREFFABLE (`case-92` §5bis)
   sur une unite du pool : le code exerce est bien celui de 1120, et aucune propriete du greffon
   n'entre dans le resultat.

2. **`0x462` = 1122 = `EffectType.Markerlight`** (enum QUALIFIE : `IdunBattle.Entities.Enum.EffectType`,
   ni `TriggeredAbilityType` -- ou 1122 vaut `NoctilithBeacons` -- ni `ActiveAbilityType`). La cible
   est celle que les T'au ont MARQUEE ; le drone se jette d'autant plus volontiers sur elle.

3. **`onlyActive: true`, et c'est l'INVERSE de `SuppressiveFire`.** Le 4e argument du call-site est le
   litteral `1` (`SuppressiveFire` passe `0`, `ForwardObservers` passe `null`). Ce byte-la change ce
   que le natif regarde : `IdunBattle.Entities.EntityExtensions$$HasEffect` =
   `IsOwnerOfEffect(e, state, type, onlyActive) || IsTargetOfEffect(e, state, type)`, et dans
   `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` le flag `EffectComponent.IsActive @+0x5c`
   n'est consulte QUE si `onlyActive != 0`. Le mirror est donc `EffectsState.active_effects`, PAS
   `has_effect` -- exactement le choix inverse de `suppressive_fire.py`, pour un call-site voisin.
   (La seconde branche, `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffect`, exige `+0x5c`
   INCONDITIONNELLEMENT : elle est deja « active-only » dans les deux regimes.)

4. **La cle est un LITTERAL DE CHAINE du corps** (`FUN_1801f4fb0(&DAT_...)` au prologue), pas un
   champ statique : `SaviorProtocolsPlaybook` n'a **pas de `.cctor`** -- meme forme que
   `BarbedOvipositor`, l'inverse de `Lakrimae`. Les TROIS litteraux de la classe sont
   `SAVIORPROTOCOLS_MarkedTarget` (cette face) et `SAVIORPROTOCOLS_AdjacentTauFriend` /
   `SAVIORPROTOCOLS_AdjacentTauParent` (face MOVE). Poids au gameconfig **et** au seed BC servi (les
   deux concordent, pas de piege #271) : **60 / 20 / 30**. L'assignation du 60 a cette face n'est pas
   deduite du nom : elle est TRANCHEE par la mesure live (`probe_443`), ou les trois valeurs sont
   distinctes.

## La face MOVE (#443-r1) -- corps PROPRE, DEUX termes, et un prealable de STRUCTURE

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$CalculateMovementUtilityInStepsInternal` monte
la SM `d__4`, dont la disposition des champs est **LUE DANS LA METHODE-USINE** et surtout PAS
transposee de la face soeur : `d__4` = playbook @+0x20, case @+0x28, delegue scorer @+0x30 ; `d__5`
(face ATTACK, MEME classe) = case @+0x20, playbook @+0x28, delegue @+0x30 ; `BarbedOvipositor.d__5`
= case @+0x20, delegue @+0x28 (deux champs). Trois dispositions pour trois state machines : lire un
`case` la ou le champ porte le `this` donne un objet du mauvais type, silencieusement.

Corps `SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext`,
remis en C# :

    Fix64 x = Fix64.op_Implicit(0);
    foreach (var u in this.<>4__this.<query>.GetAdjacentUnits(         // slot 0x7a de l'IBattleQuery
                          case.MovementTile, friendsOf: null, enemiesOf: null, ignoreSteppables: false))
    {
        var trigger = SaviorProtocolsAbility.TargetIsValidTrigger(this.<>4__this.<ability@+0x58>);
        var tctx = new <TriggerContext>(0x128 octets, zero) { [+0x10] = u, [+0x18] = case.Unit };
        if (trigger.<vslot +0x188>(tctx, 0x20)) {
            x += Fix64.op_Implicit(GetUtilityValue("SAVIORPROTOCOLS_AdjacentTauFriend"));   // 20
            if (UnitExtensions.GetParent(case.Unit, state) == u)
                x += Fix64.op_Implicit(GetUtilityValue("SAVIORPROTOCOLS_AdjacentTauParent")); // 30
        }
    }
    yield return x;

Cinq lectures qui ne se devinent pas :

1. **Le SLOT `0x7a` = `IBattleQuery.GetAdjacentUnits(tile, friendsOf, enemiesOf, ignoreSteppables)`**
   -- identifie par le COMPTE ET L'ORDRE des arguments (4 apres `this`) contre les signatures nommees
   de `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery$$GetAdjacentUnits` (le decorateur
   les nomme : `from/tiles, friendsOf, enemiesOf, ignoreSteppables`), et corrobore par le SEUL autre
   call-site du meme slot dans tout le binaire,
   `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason`,
   qui lui passe une TUILE (verifiee `TileExtensions$$IsFreeTile` juste avant) -- donc l'overload
   TUILE, pas l'overload unite. Les trois arguments suivants sont les litteraux `0, 0, 0` :
   **AUCUN filtre de camp** (le tri ami/ennemi est fait plus bas par le trigger) et **steppables
   INCLUS**. L'adjacence est celle de `TileQuery$$IterateAdjacentTiles`, donc la porte d'elevation
   `abs(delta) < 2` -- `battle_query.is_adjacent`, jamais `hexgeo.distance == 1` nu (#271).

2. **Le contexte du trigger est construit A LA MAIN, et ses deux champs sont IDENTIFIES PAR LES
   SELECTEURS**, pas par convention : `IdunBattle.Entities.Selectors.TargetSelector$$Select` lit
   `context+0x10`, `IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `context+0x18`
   (`ActorSelector` lirait `+0x00`, qui reste NUL ici). Le corps ecrit `+0x10 = u` (le voisin) et
   `+0x18 = case.Unit` (le mover). Donc, dans l'arbre du trigger, **`Target` EST le voisin** et
   **`Owner` EST le mover**. Inverser les deux rendrait le terme constamment nul : le mover PORTE
   1120, et le predicat exige justement que son sujet ne le porte PAS.

3. **`SaviorProtocolsAbility$$TargetIsValidTrigger` (artefact natif DISTINCT, partage avec la face
   COMBAT)** -- arbre DSL a quatre noeuds, sur le bundle de selecteurs `<ability+0x28>+0x90`
   (`+0x60` = Target, `+0x30` = Owner ; le meme bundle donne `IsAdjacent(+0x30, +0x60)` dans
   `$$CreateTrigger` et `TransferDamage(..., +0x60, +0x30, ...)` dans `$$CreateBehaviour`) :

       AreFriends(Target, Owner)
       & HasFaction(Target, 9 = UnitFaction.Tau, 3)
       & !ActorHasTriggeredAbility(Target, 0x460 = 1120 SaviorProtocols)
       & !AreEqual(Target, Owner)

   C'est le predicat « ce voisin est un allie T'au que je peux PROTEGER » : un autre porteur de 1120
   est exclu (il se protege seul), et un ennemi aussi. Aucun `On(<event>)` n'entre dans CET arbre
   (le `On(0x39)` vit dans `$$CreateTrigger`, pas ici), donc le `0x20` passe au slot d'evaluation
   n'a aucun sujet a filtrer.

4. **Le bonus PARENT est IMBRIQUE dans le predicat**, pas paralle : `+AdjacentTauParent` n'est verse
   que si le parent a DEJA passe `TargetIsValidTrigger` -- un summoner qui porterait lui-meme 1120,
   ou d'un autre camp, ne vaudrait NI 20 NI 30. `UnitExtensions$$GetParent(case.Unit, state)` est le
   lien enfant -> summoner (`ChildComponent.ParentId`), porte par `Scene.parent` / `parent_of` (#378) ;
   le porteur naturel de 1120 etant un SUMMON, ce terme designe **le drone qui reste colle a son
   invocateur**.

5. **Les DEUX cles sont des litteraux de chaine du corps**, resolus PAR LEUR SLOT et dans l'ORDRE
   d'apparition (`probe_212_bc_key_literals.py`, chaine `slot -> token -> global-metadata.dat`) :
   le premier scorer lit `SAVIORPROTOCOLS_AdjacentTauFriend` (= 20), le second
   `SAVIORPROTOCOLS_AdjacentTauParent` (= 30). L'attribution n'est donc PAS deduite des noms.

### `SaviorProtocolsPlaybook$$FilterMovementTiles` -- LE CRITERE, TRANCHE (`#456-r2-r1`)

Le playbook surcharge aussi le slot 1 d'`IPlaybook`. **DEUX phrases de cette section etaient
FAUSSES et sont retirees** :

* << INERTE sur le porteur >> -- le regime que `case-443-r1` §5 declarait inatteignable est
  ATTEINT : greffe sur un porteur de MELEE (`tauAunShi`), le filtre RETIRE exactement la tuile
  `(0,3)` sur les DEUX utilities, reproductible sur deux passes, pendant que `tauCrisis` (ranged,
  MEME greffe) garde ses 12/12. Le court-circuit `HasRangedWeapon` est confirme, mais l'inertie
  ne vaut que pour les six porteurs NATURELS -- pas pour un montage.
* << NON tranche faute d'un second call-site nomme >> -- le critere se lit ENTIEREMENT dans le
  corps, sans avoir besoin d'un second call-site.

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$FilterMovementTiles(unit, allMovementTiles)`,
remis en C# :

    dc = new <>c__DisplayClass6_0 { <+0x18> = unit };
    if (UnitExtensions.HasRangedWeapon(unit, null))  return;            // COURT-CIRCUIT TOTAL
    dc.<+0x10> = SaviorProtocolsAbility.TargetIsValidTrigger(this.ability@+0x58);
    var toRemove = new List<UnitPosition>();
    for (int i = allMovementTiles.Count - 1; i >= 0; i--) {
        var units = battleQuery.<slot 119 = GetSurroundingUnits>(allMovementTiles[i],
                                                                 range: 2, includeCenter: false);
        if (!Enumerable.Any(units, dc.<FilterMovementTiles>b__0))
            toRemove.Add(allMovementTiles[i]);
    }
    if (toRemove.Count == allMovementTiles.Count)  return;              // ANTI-VIDAGE
    ListExtensions.RemoveRange(allMovementTiles, toRemove);

et le predicat `<FilterMovementTiles>b__0(u)` construit A LA MAIN le MEME contexte a 0x128 octets
que la face MOVE, avec les MEMES deux champs (`TargetSelector` lit `+0x10`, `OwnerSelector` lit
`+0x18` -- cf. §2 de la face MOVE) :

    ctx = new AbilityEntities(zero) { [+0x10] = u, [+0x18] = dc.unit };
    return dc.trigger.<vslot d'evaluation>(ctx);

QUATRE lectures qui ne se devinent pas, et deux d'entre elles REFUTENT la prediction de
`case-443-r1` §5 :

1. **Le rayon est GEOMETRIQUE, pas connectif.** Le slot 119 est `GetSurroundingUnits` (arite 3,
   `metadata/interface_slots.tsv`), qui descend a
   `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` -- une
   TRIPLE BOUCLE CUBE (`x+y+z == 0`, `|d| <= range`) **sans porte d'elevation** et **sans jamais
   consulter la liste d'adjacence STOCKEE**. C'est le CONTRAIRE d'`IterateAdjacentTiles`, que
   mirrore `battle_query.is_adjacent` et que la face MOVE de CE MEME playbook utilise (slot 0x7a
   `GetAdjacentUnits`). Deux slots, deux geometries, dans la meme classe.
2. **`includeCenter = 0` : la tuile candidate elle-meme est EXCLUE** du disque. Une unite POSEE
   sur la tuile visee ne protege donc pas cette tuile.
3. **IL Y A BIEN UNE CONDITION DE PLUS**, et c'est `TargetIsValidTrigger` -- le MEME artefact que
   la face MOVE (`AreFriends(Target, Owner) & HasFaction(Target, 9 = Tau, 3) &
   !ActorHasTriggeredAbility(Target, 0x460 = 1120) & !AreEqual(Target, Owner)`). C'est ce qui
   explique la mesure de `#456-r2` : `(0,3)` et `(1,3)` ont toutes deux `ultraTitus` a `d = 2`,
   mais << un protegeable dans le rayon >> ne suffit pas -- il faut un protegeable **VALIDE**.
4. **L'ANTI-VIDAGE est un cran a part.** Si TOUTES les tuiles tombaient, le natif n'en retire
   AUCUNE. Un port qui l'oublierait immobiliserait le mover des qu'aucun allie T'au valide n'est
   a portee -- l'inverse exact du comportement natif.

⚠ **CE QUI RESTE OUVERT, ET CE N'EST PLUS LE CRITERE** : le CABLAGE. Le natif applique ce filtre
PAR ABILITY dans `ABaseAiUnitTactic$$GenerateActionTiles`, alors que le port n'a qu'une liste de
positions partagee (`ai.context.action_tiles_for`, qui NOMME deja ce hook). `filter_movement_tiles`
ci-dessous est le mirror EXECUTABLE du critere ; aucun appelant ne le consomme encore -- residu
`#443-r1b`, desormais reduit au seul branchement.

### La 4e classe -- `IdunBattle.AI.Utilities.SaviorProtocolsUtility` -- etait DEJA portee

Elle vit dans `engine/utilities/tile.py` (`UtilityType.SaviorProtocols = 23`) et n'a RIEN a voir
avec ce playbook : c'est la feuille prise **A L'ENVERS**, du point de vue du PROTEGE.
`$$CanBeProtector(unit) = HasFaction(unit, 9) && !HasTriggeredAbility(unit, 0x460)` gate le MOVER,
et `$$GetUnitsWithUtilityForMove` compte `UnitsWithTriggeredAbility(GetFriendsAdjacentToMovementTile
(case), 0x460)` x `$$GetUtilityPerUnit` (= `SaviorProtocols.PerUnitWithAbilityInRange`). Verifie
conforme au decompile par #443-r1, sans modification.
"""
from __future__ import annotations

import hexgeo

from .. import battle_query as bq
from ..entities.effect_type import EffectType
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_faction import UnitFaction, faction_value
from ..services import battle_query as _sbq     # FORME B : foyer de `HasRangedWeapon(unit, null)`

# `HasEffect(case.Target, state, (EffectType)0x462, onlyActive: true)` -- 0x462 = 1122 (cf. en-tete).
_MARKERLIGHT = int(EffectType.Markerlight)
# L'UNIQUE litteral de chaine de la face ATTACK, lu dans `Utilities.Default.TriggeredAbilities`.
_WEIGHT_KEY = "SAVIORPROTOCOLS_MarkedTarget"

# Face MOVE -- les DEUX litteraux du corps `d__4$$MoveNext`, dans l'ORDRE de leurs slots (cf. en-tete
# §5 : resolus par `probe_212_bc_key_literals.py`, pas deduits des noms).
_WEIGHT_ADJACENT_TAU_FRIEND = "SAVIORPROTOCOLS_AdjacentTauFriend"   # 1er scorer -- 20 BC
_WEIGHT_ADJACENT_TAU_PARENT = "SAVIORPROTOCOLS_AdjacentTauParent"   # 2e  scorer -- 30 BC
# `DSLTriggers$$HasFaction(Target, 9, 3)` : le 3e argument est le `selectionType` du selecteur, pas
# une seconde faction -- seul le `9` porte la semantique.
_TAU = int(UnitFaction.Tau)                                          # 9
# `DSLTriggers$$ActorHasTriggeredAbility(Target, 0x460)`, enum QUALIFIE `TriggeredAbilityType`
# (homonymes a ecarter : `EffectType` 1120 = TerrorsLament_HitReduction).
_SAVIOR_PROTOCOLS = int(TriggeredAbilityType.SaviorProtocols)        # 1120 = 0x460
# `#456-r2-r1` -- les DEUX litteraux du call-site `GetSurroundingUnits(tile, 2, includeCenter: 0)`
# de `$$FilterMovementTiles` (slot 119, DISQUE HEX GEOMETRIQUE : cf. l'en-tete du module). Des
# SCALAIRES (un rayon, un booleen), aucun enum ne les designe.
_FILTER_RADIUS = 2
_FILTER_INCLUDE_CENTER = False


def _target_is_valid_trigger(neighbour: dict, is_friend: bool, mover_uid) -> bool:
    """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$TargetIsValidTrigger`
    evalue sur le contexte `{Target: <voisin>, Owner: <mover>}` que le corps MOVE construit
    (cf. en-tete §2/§3). Les quatre noeuds, dans l'ordre du decompile :

      * `AreFriends(Target, Owner)`             -> `is_friend` (les deux listes du `ctx` tile-leaf
        sont deja partitionnees par l'EQUIPE du mover, ce que compare le noeud natif) ;
      * `HasFaction(Target, 9 = Tau, 3)`        -> `faction_value(vis)`, la MEME derivation que la
        cle `unit_faction` du sujet (le natif compare `System.Enum.ToString(UnitFaction)` au
        `FactionComponent+0x30` ; le pendant offline est le `FactionId` gameconfig) ;
      * `!ActorHasTriggeredAbility(Target, 0x460)` -> le voisin ne porte PAS 1120 lui-meme ;
      * `!AreEqual(Target, Owner)`             -> mirror EXPLICITE, meme si les deux listes du `ctx`
        sont deja self-exclues : le noeud existe au decompile, et le port ne doit pas dependre d'une
        propriete du producteur de contexte pour rendre le bon resultat.

    `vis` inconnu -> `faction_value` rend `None` -> le noeud `HasFaction` est FAUX (degradation
    sure : on ne verse pas un poids sur une faction non etablie)."""
    if not is_friend:                                        # AreFriends(Target, Owner)
        return False
    if faction_value(neighbour.get("vis")) != _TAU:          # HasFaction(Target, 9, 3)
        return False
    if _SAVIOR_PROTOCOLS in set(neighbour.get("triggered") or ()):   # !ActorHasTriggeredAbility(...)
        return False
    nid, mid = neighbour.get("id"), mover_uid                # !AreEqual(Target, Owner)
    return not (nid is not None and mid is not None and int(nid) == int(mid))


def _target_has_active_markerlight(scene, target_uid: int) -> bool:
    """`EntityExtensions.HasEffect(target, state, 1122, onlyActive: TRUE)` =
    `IsOwnerOfEffect(target, state, 1122, onlyActive=1) || IsTargetOfEffect(target, state, 1122)`.

    `onlyActive = 1` ==> `IsOwnerOfEffect` consulte `EffectComponent.IsActive @+0x5c` : cote port
    c'est `EffectsState.active_effects` (flag `active` + `CreateActiveCondition`), surtout PAS
    `has_effect`, qui ne filtre que `consumed` et sert les call-sites `onlyActive = 0` (le voisin
    `suppressive_fire.py`). La seconde branche passe par le foyer unique `Scene.is_effect_target`,
    tri-etat : `None` = geometrie non portee pour ce type, on ne referme pas dessus (meme discipline
    que `playbook/psyker.py` et `playbook/suppressive_fire.py`)."""
    eff = getattr(scene, "eff_state", None)
    if eff is not None:
        st = scene.unit_state(int(target_uid)) if hasattr(scene, "unit_state") else None
        for e in eff.active_effects(int(target_uid), st):
            if e.effect_type == _MARKERLIGHT:
                return True
    return getattr(scene, "is_effect_target", lambda *_a: None)(
        int(target_uid), _MARKERLIGHT) is True


class SaviorProtocolsPlaybook:
    """`SaviorProtocolsPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1120) -- les DEUX faces,
    comme le natif, qui n'a qu'UNE classe et qu'UN singleton par type d'ability
    (`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook`, cache dict@0x90). La classe est SANS ETAT, donc
    les deux registres du port (`psyker.TRIGGERED_ATTACK_PLAYBOOKS` et
    `adjacent_unit_preference.TRIGGERED_MOVE_PLAYBOOKS`) peuvent en tenir chacun une instance sans
    ecart observable avec le singleton natif."""

    ability_id: int = int(TriggeredAbilityType.SaviorProtocols)      # 1120 = 0x460

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__5$$MoveNext` (cf. en-tete) : la CIBLE
        porte-t-elle un `Markerlight` ACTIF ? oui -> le poids `SAVIORPROTOCOLS_MarkedTarget` ;
        non -> 0. AUCUN autre terme : ni tuile d'attaque, ni caster, ni prediction.

        `prediction` (= `case.DamagePrediction`, `UtilityAttackCase@+0x28`, canal ouvert par #438)
        est ACCEPTE et IGNORE -- comme le corps natif, qui ne lit pas ce champ du case."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        if not _target_has_active_markerlight(sc, int(case_tgt_id)):
            return 0.0
        return float(ctx.wt.triggered(_WEIGHT_KEY))            # `GetUtilityValue(<cle>)`

    def filter_movement_tiles(self, tiles: list, ctx: dict, mover_visual_id) -> list:
        """`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$FilterMovementTiles` -- MIRROR du
        critere, TRANCHE par `#456-r2-r1` (le corps natif remis en C# est dans l'en-tete du module).

            if (HasRangedWeapon(unit, null))                 return <tiles INCHANGE>
            garde = [ T for T in tiles
                        if EXISTS u dans GetSurroundingUnits(T, 2, includeCenter: false)
                           tel que TargetIsValidTrigger{Target: u, Owner: unit} ]
            if (garde est VIDE)                              return <tiles INCHANGE>   # ANTI-VIDAGE
            return garde

        QUATRE crans, et chacun vient d'une ligne du decompile :

        1. `HasRangedWeapon(unit, null)` -> foyer `services.battle_query.has_ranged_weapon`, le MEME
           que `war_howl.war_howl_other_buff_targets` (`WeaponsComponent$$HasRangedWeapon` : << au
           moins une arme n'est pas `IsMelee` >>). Vrai -> le natif SORT sans rien retirer.
        2. Le disque est **GEOMETRIQUE** (`hexgeo.distance <= 2`), pas la liste d'adjacence stockee :
           `GetSurroundingUnits` descend a `IterateSurroundingTiles`, triple boucle cube SANS porte
           d'elevation. Ne PAS y brancher `battle_query.is_adjacent`, qui mirrore une AUTRE
           primitive -- c'est la faute exacte que `#433-r4-r1-r4-r2-r2` a corrigee ailleurs.
        3. `includeCenter = 0` -> la tuile candidate elle-meme est EXCLUE (`d >= 1`).
        4. L'ANTI-VIDAGE (`toRemove.Count == allMovementTiles.Count -> return`) : si AUCUNE tuile ne
           passe, le natif n'en retire AUCUNE. Sans ce cran, le mover serait immobilise des
           qu'aucun protegeable valide n'est a portee.

        `mover_visual_id` -- le `visualId` du MOVER, seul substrat du cran 1. `None` = non mesure ->
        on ne court-circuite pas (le filtre s'applique), degradation NOMMEE : le cran 1 ne peut que
        GARDER des tuiles, donc l'ignorer est la lecture RESTRICTIVE ; c'est le seul endroit ou ce
        mirror ne suit pas la regle << non mesure = permissif >>, et c'est DELIBERE -- le natif
        n'a pas de troisieme etat, et rendre `tiles` inchange masquerait le filtre entier.

        ⚠ **AUCUN APPELANT NE LE CONSOMME ENCORE** : le natif l'applique PAR ABILITY dans
        `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles`, la ou le port n'a qu'une
        liste de positions PARTAGEE par tous les playbooks (`engine.ai.context.action_tiles_for`).
        Le cablage est ce qui reste de `#443-r1b`."""
        tiles = list(tiles or [])
        if not tiles:
            return tiles
        if mover_visual_id is not None and _sbq.has_ranged_weapon(mover_visual_id):
            return tiles                          # `if (HasRangedWeapon(unit)) return;`
        ctx = ctx or {}
        mover_uid = ctx.get("uid")
        garde = []
        for T in tiles:
            ok = False
            for units, is_friend in ((ctx.get("friend_units") or (), True),
                                     (ctx.get("enemy_units") or (), False)):
                for u in units:
                    p = u.get("pos")
                    if not p:
                        continue
                    d = hexgeo.distance((T[0], T[1]), (p[0], p[1]))
                    # disque GEOMETRIQUE de rayon 2, centre EXCLU (`includeCenter = 0`)
                    if d > _FILTER_RADIUS or (d == 0 and not _FILTER_INCLUDE_CENTER):
                        continue
                    if _target_is_valid_trigger(u, is_friend, mover_uid):
                        ok = True
                        break
                if ok:
                    break
            if ok:
                garde.append(T)
        # `if (toRemove.Count == allMovementTiles.Count) return;` -- on ne vide JAMAIS la liste.
        return garde if garde else tiles

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        """Mirror de `<CalculateMovementUtilityInStepsInternal>d__4$$MoveNext` (cf. en-tete) :

            pour chaque unite ADJACENTE a la tuile candidate (slot 0x7a = `GetAdjacentUnits(tile,
            null, null, false)` -- aucun filtre de camp, steppables inclus),
                si `TargetIsValidTrigger{Target: voisin, Owner: mover}` passe :
                    + AdjacentTauFriend
                    si ce voisin EST le parent (summoner) du mover : + AdjacentTauParent

        `ctx` = le dict tile-leaf des DEUX foyers (`tile_leaf_ctx` cote decision,
        `runner_tile_leaf_ctx` cote runner). Le natif n'applique NI cap NI tri : la somme court sur
        toutes les unites adjacentes retenues, et `GetAdjacentUnits` rend un `OrderedSet` (pas de
        doublon) -- les deux listes du `ctx` sont disjointes, donc l'union non plus.

        REGIME SPAWN (`case.unit == null`) : le natif ecrirait `Owner = null` dans le contexte du
        trigger, `AreFriends` serait faux pour tout voisin et la somme resterait 0. Le port y arrive
        par le meme chemin (aucune cle d'unite dans le `ctx` de spawn -> aucune iteration), et le
        dispatcher `TriggeredAbilitiesUtility` court-circuite deja sur `is_spawning` (case-205).

        DEGRADATION du terme PARENT : `unit_parent_id` absent du `ctx` (producteur sans canal
        parent) -> le bonus n'est pas verse, le terme FRIEND l'est quand meme. C'est la meme
        degradation partielle que les autres feuilles gatees sur une cle absente ; le canal existe
        des deux cotes depuis #378 (`Scene.parent` / `components.parent_of`)."""
        ctx = ctx or {}
        elev = ctx.get("elev_by_pos")
        neigh = bq.neigh_map(ctx)
        mover_uid = ctx.get("uid")
        parent_uid = ctx.get("unit_parent_id")               # `UnitExtensions$$GetParent(case.Unit, state)`
        w_friend = float(wt.sub("TriggeredAbilities", _WEIGHT_ADJACENT_TAU_FRIEND))
        w_parent = float(wt.sub("TriggeredAbilities", _WEIGHT_ADJACENT_TAU_PARENT))
        total = 0.0
        # `GetAdjacentUnits(tile, friendsOf: null, enemiesOf: null, ignoreSteppables: false)` : le
        # natif ne filtre PAS le camp ici -- c'est `AreFriends` DANS le trigger qui le fait. On
        # parcourt donc les DEUX listes, et `_target_is_valid_trigger` rejette les ennemis.
        for units, is_friend in ((ctx.get("friend_units") or (), True),
                                 (ctx.get("enemy_units") or (), False)):
            for u in units:
                if not bq.is_adjacent(tile, u["pos"], elev, neigh):
                    continue
                if not _target_is_valid_trigger(u, is_friend, mover_uid):
                    continue
                total += w_friend
                # `if (GetParent(case.Unit, state) == u)` -- IMBRIQUE dans le predicat (en-tete §4).
                if parent_uid is not None and u.get("id") is not None \
                        and int(u["id"]) == int(parent_uid):
                    total += w_parent
        return total
