"""Les QUATRE gates EN AMONT du calcul de zone -- ce qui ANNULE une ability avant meme qu'on
demande ou elle porte (#433-r4-r2-r1-r1-c, puis #433-r4-r2-r1-r2-r2-r1-r1-r1-r4 pour le 4e).

LE FOYER NATIF, LU VERBATIM. `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange`,
surcharge a QUATRE arguments `(unit, position, ability)` -- l'etage PAR ABILITY sous lequel passe
CHAQUE entree de l'`ActiveAbilityComponent` de l'unite :

    impl = <this.abilities @+0x18>.<slot 0>(ability.<AbilityName @+0x44>)   # IAbilitiesDatabase
    if (impl == null) throw
    if (!impl.<IActiveAbility slot 0x14>(unit, ability.<AmountOfTimesAlreadyUsed @+0x10>))
        -> ensemble VIDE
    if ( impl.<IActiveAbility slot 0x13>(unit))
        -> ensemble VIDE
    if (AttackQuery.GetInvalidCasterReason(unit, position, ability.AbilityName).IsInvalid())
        -> ensemble VIDE
    tiles = impl.<slot 9>(unit, position.MainTile) U impl.<slot 10>(unit, position.MainTile, tiles9)

L'appelant est la lambda `IdunBattle.Core.Services.AttackQuery.u003Cu003Ec__DisplayClass39_1$$
u003CGetAllTilesInAbilityRangeu003Eb__0`, qui ENUMERE `unit.GetComponent<ActiveAbilityComponent>()`
en entier -- attaque NORMALE comprise quand `includeNormalAttack` est pose (le litteral `1` du
call-site d'`IsTileInRangeOfAnyAbility`). Les trois gates s'appliquent donc AUSSI a elle.

QUI SONT CES SLOTS -- re-derives, la fiche du cas les NOMMAIT AUTREMENT. Les deux slots
d'interface sont ceux qu'`IdunBattle.Operations.AddMachineOperation$$InitializeAbilitiesStatus`
utilise pour INITIALISER deux champs de `IdunBattle.Entities.Components.ActiveAbility`, et ces
champs portent leur nom dans les metadonnees IL2CPP (resolus PAR NOM par
`frida/hooks/features/ai-step/internals.ts`) :

    comp.<CanStillBeUsed @+0x28> = impl.<slot 0x14>(unit, comp.<AmountOfTimesAlreadyUsed @+0x10>)
    comp.<IsDisabled    @+0x35> = impl.<slot 0x13>(unit)

-> **slot 0x14 = `IdunBattle.Entities.Abilities.AActiveAbility$$CanStillBeUsed(caster,
amountOfTimesAlreadyUsed)`** (2 parametres, le 2e est bien `comp+0x10`) et **slot 0x13 =
`IdunBattle.Entities.Abilities.AActiveAbility$$IsDisabled(caster)`** (1 parametre). La fiche du cas
annoncait « `CanCurrentlyBeUsed` slot 0x14 » et « `IsAbilityBlocked` slot 0x13 » : les deux noms
existent, mais AUCUN des deux n'est un slot de cette interface --
`IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` est une PROPRIETE du
composant, lue plus bas (gate 3d), et `IdunBattle.Entities.UnitExtensions$$IsAbilityBlocked` est une
autre fonction (elle lit `ActiveAbilityComponent.NormalAttackIsBlocked` /
`ActiveAbilitiesAreBlocked` / `MachinePrimaryAbilityIsBlocked`) qui n'apparait NULLE PART dans cette
chaine.

LE TROISIEME GATE, DEPLIE. `IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason(unit,
attackerPosition, activeAbilityType)`, surcharge `UnitPosition` :

    a. unit == null                                                  -> broken(1)
    b. IsMultiTileUnit(unit, state) && !HasTrait(unit, 0x418)         -> broken(1)
    c. comp = unit.GetComponent<ActiveAbilityComponent>() ; aa = comp.GetOrNull(type)
       comp == null || aa == null                                     -> broken(1)
    d. !aa.CanCurrentlyBeUsed                                         -> broken(1)
    e. aa.AbilityName == 0                                            -> broken(1)
    f. IsAlreadyUsedThisTurn(type, aa)                                -> broken(1 << 54)
    g. sinon -> <processor @+0x30>( () => impl.<slot 8>(unit, position.MainTile) )
       = `IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidCasterReason(caster, casterTile)`
       -> `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, **DEJA PORTE** par
       `engine.runner.abilities.targeting.get_invalid_caster_reason` (face RUNNER).

`IdunBattle.Core.Services.IBrokenTargetingRuleExtensions$$IsInvalid(rule)` = `rule.<slot 0>() != 0`
-> « invalide » vaut exactement « raison non nulle ».

L'ORDRE EST LE LIVRABLE. Les trois gates sont evalues dans CET ordre, et le troisieme est
lui-meme une cascade ordonnee ; un gate pose au mauvais rang donne un resultat juste sur les cas
isoles et faux des que deux conditions coexistent. Par rapport a ce que le port avait deja :
`TargetingQuery$$GetInvalidCasterReason` (porte) est la DERNIERE marche de (g), donc TOUT ce module
est EN AMONT de lui ; et `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` (porte,
face COMBAT) est un AUTRE pipeline -- celui de l'EXECUTION d'un cast, pas celui de la zone.

CE QUI EST DERIVABLE COTE DECISION, ET CE QUI NE L'EST PAS. Le canal
`decisionView.units[].abilities[]` (`allAbilities: true`) publie, POUR TOUTE UNITE des deux camps,
les cinq champs de `components.ActiveAbility` que `readAbilityState` lit PAR NOM :

    usable   <- CanStillBeUsed          @+0x28    (la valeur du slot 0x14, mise en cache)
    disabled <- IsDisabled              @+0x35    (la valeur du slot 0x13, mise en cache)
    cooldown <- RemainingCooldownTurns  @+0x2c    (`null` = Nullable vide = pret)
    ammoCost <- AmmoCost                @+0x38    (`null` = pas de cout)
    hasAmmo  <- HasEnoughAmmo           @+0x40

  * gate 1 -> `usable` ;
  * gate 2 -> DEUX sources concordantes : le champ `disabled`, et surtout le MIRROR OFFLINE
    ci-dessous, qui ne depend d'AUCUN canal ;
  * gate 3d -> `can_currently_be_used`, qui DELEGUE au foyer deja pose
    `engine.battle_query.can_currently_be_used` (les quatre champs) et n'y ajoute que le
    tri-etat ;
  * gate 3b -> INATTEIGNABLE depuis `IsTileInRangeOfAnyAbility` : son PREMIER geste est
    `if (GetFeetCount(unit) > 1) return true`, et `IsMultiTileUnit` = `unit.Type == Unit &&
    GetUnitFeetIds(unit).Count > 1` -- le meme predicat. Une unite multi-tuiles n'atteint donc
    jamais ce gate par cette voie ;
  * gate 3c -> la LISTE des abilities. Ce module ne la change pas (le substrat reste le kit
    gameconfig d'`ability_range`) ;
  * gate 3f (`IsAlreadyUsedThisTurn`) -> **NON DERIVABLE** : il lit
    `ActiveAbility.<Nullable<int> @+0x20>` (le tour de la derniere utilisation) contre
    `TurnComponent.GetAmountOfTurnsEnded(null)`, et AUCUN canal ne publie ce champ. BORNE
    EXPLICITE, sens PERMISSIF. Point d'ancrage a publier : `components.ActiveAbility+0x20` dans
    `readAbilityState`, a cote des cinq deja lus ;
  * gate 3g -> **PORTE ICI depuis `#433-r4-r2-r1-r2-r2-r1-r1-r1-r4`** (`invalid_caster_reason`),
    sur le substrat DECISION. La face RUNNER du meme natif reste
    `engine.runner.abilities.targeting.get_invalid_caster_reason` (elle consomme un `State`) : les
    deux sont deux RESTRICTIONS d'un seul natif a deux substrats, pas deux ports concurrents --
    la cascade, son ORDRE et ses litteraux sont re-lus a la MEME fonction.

NON MESURE != FAUX. Quand le canal manque (`ability_state` absent, ou champ absent de la ligne),
les gates 1 et 3 rendent `None` = « pas mesure », et l'appelant ne gate PAS : c'est le statu quo
d'avant cette tranche, une borne SUPERIEURE sur la zone. Le gate 2, lui, repond toujours.
"""
from __future__ import annotations

from dataclasses import dataclass

import gameconfig as GC
import hexgeo

from ..entities.active_ability_type import ActiveAbilityType
from ..runner.abilities.attack_type import is_regular_attack
from ..runner.abilities.targeting_rule import TargetingRule as TR
from ..entities.traits.unit_trait import UnitTrait   # #270-r1-r1-r3
from .. import battle_query as bq
# FORME B (le MODULE, pas le nom). Le contre-factuel `_SansRegle` de
# `probe_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason.py` substitue `TGT.targeting_options_for` :
# une liaison de NOM ici le DESARMERAIT en silence, et c'est ce qui rendait `master` rouge sur
# `test_contre_epreuve_sans_le_bit_du_masque_le_port_ACCEPTE` (le port refusait encore `0x10` alors
# que le bit etait cense avoir ete retire). Meme cause, meme correctif qu'`ability_range._options_of`.
import engine.runner.abilities.targeting as TGT

# ------------------------------------------------------------------------------------------------
# `IdunBattle.Configuration.AbilityConfiguration$$TryGetNumberConstant` sur le substrat gameconfig.
#
# Les cles sont les membres d'`IdunBattle.Configuration.AbilityConstantType` (enums.tsv) ; le
# natif indexe par ORDINAL, le kit gameconfig par NOM -- c'est la meme table, et c'est deja le
# canal qu'`engine.services.ability_range` utilise pour `range` (0x16).
# ------------------------------------------------------------------------------------------------
CONST_NR_OF_TARGETS = "nrOfTargets"          # AbilityConstantType 0x11 = 17
CONST_NR_OF_HITS = "nrOfHits"                # AbilityConstantType 0x2f = 47
CONST_COOLDOWN_TURNS = "cooldownTurns"       # AbilityConstantType 0x27 = 39
CONST_INITIAL_COOLDOWN = "initialCooldownTurns"   # AbilityConstantType 0x68 = 104
CONST_MUNITIONS_COST = "munitionsCost"       # AbilityConstantType 0x6b = 107


def _ability_name(ability_id):
    try:
        return ActiveAbilityType(int(ability_id)).name
    except (TypeError, ValueError):
        return None


def try_get_number_constant(ability_id, key: str):
    """`IdunBattle.Configuration.AbilityConfiguration$$TryGetNumberConstant(config, <key>, out v)`
    -- `None` = la cle est ABSENTE de la config (le `false` du natif), jamais un zero invente."""
    name = _ability_name(ability_id)
    if name is None:
        return None
    raw = ((GC.ability(name) or {}).get("constants") or {}).get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------
# GATE 2 -- `IActiveAbility` slot 0x13 = `AActiveAbility$$IsDisabled(caster)`
# ------------------------------------------------------------------------------------------------
def is_disabled(ability_id) -> bool:
    """`IdunBattle.Entities.Abilities.AActiveAbility$$IsDisabled(caster)` -- mirror 1:1.

    Son corps est UN SEUL appel, qui n'utilise PAS `caster` :

        return StaticBattleRules.ActiveAbility.IsDisabled(this.<AbilityType @+0x10>,
                                                          this.<AbilityConfiguration @+0x60>)

    et `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsDisabled`
    est, VERBATIM :

        if (IsRegularAttack(abilityType)) return false;
        if (abilityConfig == null)        return false;
        if (config.TryGetNumberConstant(nrOfTargets, out v)) return v < 1;
        if (config.TryGetNumberConstant(nrOfHits,    out v)) return v < 1;
        return false;

    L'ORDRE des deux constantes compte : `nrOfHits` n'est LU QUE si `nrOfTargets` est ABSENTE.
    Une ability portant `nrOfTargets = 2` et `nrOfHits = 0` n'est donc PAS disabled.

    Entierement derivable du kit gameconfig -- aucun canal live requis. MESURE sur le catalogue
    (`probe_433_r4_r2_r1_r1_c_caster_gates.py --step inventaire`) : sur les 175 abilities ACTIVES
    distinctes du gameconfig, **0** sont disabled (3 portent `nrOfTargets`, 110 `nrOfHits`, toutes
    `>= 1`). Le gate est donc porte parce que le natif l'a, et son gisement est VIDE a ce build --
    ce qui est un resultat, pas une raison de ne pas le porter."""
    try:
        aid = int(ability_id)
    except (TypeError, ValueError):
        return False
    if is_regular_attack(aid):
        return False
    v = try_get_number_constant(aid, CONST_NR_OF_TARGETS)
    if v is not None:
        return v < 1
    v = try_get_number_constant(aid, CONST_NR_OF_HITS)
    if v is not None:
        return v < 1
    return False


# ------------------------------------------------------------------------------------------------
# GATE 1 et GATE 3d -- l'etat LIVE du composant, via `decisionView.units[].abilities[]`
# ------------------------------------------------------------------------------------------------
def _flag(state, key):
    """Le champ `key` de la ligne, en TRI-ETAT : `None` = pas publie (**pas mesure**)."""
    if not isinstance(state, dict):
        return None
    v = state.get(key)
    return None if v is None else bool(v)


def can_still_be_used(state) -> bool | None:
    """GATE 1 -- le champ `CanStillBeUsed @+0x28`, c'est-a-dire la valeur que le slot 0x14 a rendue.

    Le natif RE-EVALUE `impl.CanStillBeUsed(unit, comp.AmountOfTimesAlreadyUsed)` au call-site ;
    le port lit le champ que la meme methode a ecrit. Les deux entrees sont les memes (l'unite et
    son compteur d'utilisations), donc la seule divergence possible est un DECALAGE TEMPOREL entre
    l'ecriture du champ et la question. C'est le regime que la mesure live du cas confronte.

    Corps de la methode, pour memoire (`AActiveAbility$$CanStillBeUsed`) :

        if (UnitExtensions.IsBoss(caster))       return true;
        if (EntityExtensions.IsMachine(caster)) {
            if (!IsMachinePrimaryAbilityType(caster, AbilityType))                  return true;
            if (GetOriginalPlayer(caster).<comp+0x20> != 1 || amountUsed == 0)      return true;
        }
        cd = this.<vtable +0x3d8>();                # GetCooldownAfterUse = constants.cooldownTurns
        if (cd.HasValue && cd.Value > 0)         return true;
        return amountOfTimesAlreadyUsed == 0;

    -- une ability SANS `cooldownTurns` est donc « une fois par reset » (le compteur est remis a
    zero par `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute`, qui ecrit ensemble
    `comp.AmountOfTimesAlreadyUsed = 0` et `comp.CanStillBeUsed = 1`)."""
    return _flag(state, "usable")


def can_currently_be_used(state) -> bool | None:
    """GATE 3d -- `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed`.

    ⚠ **CE N'EST PAS UN NOUVEAU MIRROR.** Le foyer existe deja et il est UNIQUE cote DECISION :
    `engine.battle_query.can_currently_be_used` (pose par le lot MoW-ammo, consomme par
    `engine.ai.context` pour filtrer les abilities du caster). Le RE-ecrire ici aurait cree un
    FORK de port -- deux corps pour la meme propriete, qui derivent silencieusement.

    Ce que cette fonction AJOUTE, et c'est tout, c'est le TRI-ETAT que le foyer ne peut pas
    exprimer (il rend un `bool`) : `None` = le canal ne dit RIEN de cette ability. La distinction
    est indispensable ici, parce que l'appelant n'est pas « le caster choisit une ability » (ou
    un `True` par defaut est le bon repli) mais « quelle zone menace cet ENNEMI » -- ou un `True`
    par defaut et un `True` mesure doivent rester distinguables pour que la borne soit nommee.

    Le critere de « pas mesure » est le couple `usable`/`disabled` : ce sont les deux champs que
    `readAbilityState` ecrit INCONDITIONNELLEMENT des qu'un objet `ActiveAbility` existe. Leur
    absence conjointe signifie qu'il n'y en a pas -- c'est le cas de l'attaque NORMALE, poussee
    depuis `NormalAttackType @0x28` sans entree de composant, que le foyer traite deja a part."""
    if _flag(state, "usable") is None and _flag(state, "disabled") is None:
        return None
    return bool(bq.can_currently_be_used(state))


# ------------------------------------------------------------------------------------------------
# GATE 4 (la marche `g`) -- `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`
#
# CE QUE C'EST, ET POURQUOI C'EST UN GATE A PART. La marche (g) de la cascade de tete n'est pas une
# clause de plus : c'est un APPEL a une AUTRE fonction native, qui porte a elle seule onze regles.
# Chaine complete, relue a l'octet :
#
#   AttackQuery$$GetInvalidCasterReason(unit, position, type)   [marche g]
#     -> <processor @+0x30>( () => impl.<IActiveAbility slot 8>(unit, position.MainTile) )
#     -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetInvalidCasterReason(caster, casterTile)`
#          if (caster == null) return GenericBrokenTargetingRule(1);
#          SetConfigValuesInTargetingOptions(this, &this.<TargetingOptions @+0x70>);
#          return targetingQuery.GetInvalidCasterReason(caster, casterTile, options);
#     -> `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` surcharge TUILE
#          casterTiles = TExtensions.ToList(casterTile);      // SINGLETON
#          -> la surcharge LISTE, ci-dessous.
#
# LA CASCADE, VERBATIM (surcharge `IList<IEntity> casterTiles` ; `rules` = `options+0x28`) :
#
#   if (battleQuery.IsTurnOfUnit(caster) && (rules & 0x10))         // CasterHasNotMoved
#       if (!(!DidMove(caster) && GetTiles(caster).IsEquivalentTo(casterTiles))) return 0x10;
#   if ((rules & 0x10000000) && !CanMove(caster))            return 0x10000000;   // CasterCanMove
#   if ((rules & 0x80000000) && GetStat(caster, 0xc) <= 1)   return 0x80000000;   // ...CompletedOneTurn
#   if (!(rules & 0x40000000) && !(rules & 0x80000000000000)
#       && CollectionExtensions.IsNullOrEmpty(casterTiles))  return broken(0x40000000);
#   if ((rules & 0x80000000000000) && !IsNullOrEmpty(casterTiles)) return 0x80000000000000;
#   if (rules & 4) { r = options[+0x30].Invoke(caster, casterTiles); if (r) return broken(r); }
#   feet = GetFeetCount(caster, state);
#   if ((rules >> 0x23 & 1) && feet != 1) return broken(0x800000000);     // CasterHas1Tiles
#   if ((rules >> 0x24 & 1) && feet != 3) return broken(0x1000000000);    // CasterHas3Tiles
#   if ((rules >> 0x25 & 1) && feet != 7) return broken(0x2000000000);    // CasterHas7Tiles
#   if ((rules >> 0x34 & 1) && !<IBattleQuery slot 0x1b>(caster, 2)) return broken(0x10000000000000);
#   if ((rules >> 0x35 & 1) && !IsMachine(caster))            return broken(0x20000000000000);
#   return 0;                                                            // VALIDE
#
# LE PREFIXE DE LA CLAUSE 1 N'EST PAS DECORATIF -- il a ete DEDUIT DU DECOMPILE, puis MESURE.
# Le decompile appelle `<IBattleQuery slot 0x35>(this.<+0x18>, caster)` ; le SEUL autre site du
# binaire qui invoque ce couple (slot, classe d'interface) est la lambda
# `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass86_0$$
# u003CIsTurnOfUnitu003Eb__0`, dont le NOM donne la methode : le slot 0x35 est
# `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit(caster)`, c'est-a-dire
#
#     GetOriginalOwnerEntity(GetUnit(caster)).Id == StateExtensions.GetMatchTurn(state).CurrentPlayerId
#
# -- « c'est le tour du PROPRIETAIRE D'ORIGINE de cette unite ». Quand c'est faux, la regle
# `CasterHasNotMoved` est ENTIEREMENT sautee, quel que soit le flag `Moved`.
# MESURE (#433-...-r4, `probe --step cascade`, 42 paires portant le bit) : separation PARFAITE --
# le natif rend `CasterHasNotMoved` exactement quand `has_moved && IsTurnOfUnit`, et rend 0 sur les
# 11 paires ou l'unite a bouge mais n'est pas du joueur courant. Sans ce prefixe le port refusait
# ces 11 cas : un ecart RESTRICTIF, et le pire possible ici, puisque le consommateur cote DECISION
# (`is_tile_in_range_of_any_ability`) evalue la menace des unites ENNEMIES -- precisement celles
# dont ce n'est PAS le tour.
#
# LE GISEMENT, RE-DERIVE (#943) des 169 masques que le foyer `targeting_options_for` publie (et non
# herite) : `CasterHasNotMoved` 15 porteurs, `CasterMatchesDynamicRule` 16, `CasterHas2TurnsLeft` 3,
# `CasterCanMove` 2, `CasterHas1Tiles` 1, `CasterIsMachine` 1, `CasterHasCompletedOneTurn` 0,
# `CasterHasNoTile` 0, `CasterHas3Tiles` 0, `CasterHas7Tiles` 0. Les quatre a ZERO sont des mirrors
# STRUCTURELS : ils sont ecrits parce que le natif les a, et leur gisement vide est un RESULTAT.
# ⚠ CES CHIFFRES SE RE-DERIVENT (le test `..._caster_reason_offline` le fait), ils ne se citent pas :
# 148 -> 169 masques et 12 -> 16 porteurs en trois jours -- dont UN arrive PENDANT #943, par notre PROPRE cadence de portage.
#
# ⚠ L'ETAT LU EST CELUI DU CASTER, PAS CELUI DE LA POSITION INTERROGEE -- et les deux se separent.
# `AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions, includeNormalAttack)` itere les
# positions CANDIDATES et passe chacune en `attackerPosition`, donc en `casterTiles`. Mais la
# regle-delegue, elle, n'est pas obligee de lire `casterTiles` : celle de `1045 GetEmRuntz` evalue
# `GetSpawnTileSelector` sur un `SelectorContext` dont la source de tuiles est
# `AdjacentTiles(Caster())`, et `IdunBattle.Entities.Selectors.CasterSelector$$Select` rend
# `entities.<caster @+0x08>` -- l'ENTITE -- dont `SelectTiles` prend le `GetMainTile`. Son verdict
# est donc celui de la tuile COURANTE, identique pour toutes les positions candidates. D'ou le
# champ `pos` de `CasterSubstrate` : c'est `GetMainTile(caster)`, jamais la position balayee.
# Les regles qui lisent VRAIMENT `casterTiles` existent (1023 `Burrowers` : « une tuile de
# `casterTiles` est-elle TEMPORAIRE ») -- elles sont dans la table ci-dessous, non derivables.
# ------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class CasterSubstrate:
    """Ce que la face DECISION publie du CASTER, et rien d'autre -- l'argument du 4e gate.

    Chaque champ est en TRI-ETAT : `None` = **pas mesure**, donc aucune regle qui le lit ne peut
    refuser (meme convention permissive que tout le module). Un `CasterSubstrate` entierement vide
    est le statu quo d'avant cette tranche.

      * `pos`             -- `IdunBattle.Entities.EntityExtensions$$GetMainTile(caster)`, la tuile
                             COURANTE (cf. l'avertissement ci-dessus). `None` = non publie ; c'est
                             DIFFERENT de la clause TUILE-NULLE, que `has_tile` porte.
      * `has_tile`        -- `!CollectionExtensions.IsNullOrEmpty(casterTiles)`. Separe de `pos`
                             parce qu'un appelant peut connaitre l'un sans l'autre.
      * `has_moved`       -- `IdunBattle.Entities.UnitExtensions$$DidMove`, dont le corps est
                             `GetComponent<UnitFlagsComponent>(unit).Has(UnitFlag.Moved)` apres un
                             `Type == Unit` ; `UnitFlag.Moved` vaut **0** (`enums.tsv`).
                             ⚠ Ni `decisionView` ni `projectUnitsFull` ne le publient, mais
                             `combatSnapshot.units[].unitFlags` SI (tri-etat : `null` = non mesure,
                             `[]` = mesure sans flag), et il porte aussi `unitFlagTypes` pour ne pas
                             recopier l'id. `is_tile_in_range_of_any_ability` ne le branche PAS --
                             c'est un canal de la face RUNNER, que son appelant (`NCContext`) ne
                             transporte pas -> `None` en pratique par CE chemin. Le probe du cas, lui,
                             le nourrit, et c'est ce qui a rendu la regle confrontable.
      * `is_turn_of_unit` -- `IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit`, le PREFIXE de la
                             regle `CasterHasNotMoved` (cf. l'encadre ci-dessus). Derivable cote
                             DECISION sans capteur neuf : `observeBattle.units[].playerId` est
                             `OwnerComponent.PlayerEntityId` -- le proprietaire d'ORIGINE, celui que
                             `GetOriginalOwnerEntity` resout -- et `observeBattle.currentPlayer` est
                             `TurnComponent._currentPlayerId`, celui-la meme que le natif compare.
                             ⚠ NE PAS le confondre avec `decisionView.units[].ctrl`
                             (`UnitExtensions$$IsControlledByCurrentPlayer`), qui lit
                             `OwnerComponent.CurrentPlayerEntityId` : les deux divergent sous
                             controle mental.
      * `feet_count`      -- `IdunBattle.Entities.UnitExtensions$$GetFeetCount`.
      * `is_machine`      -- `IdunBattle.Entities.EntityExtensions$$IsMachine`.
      * `has_minimum_remaining_turns` -- la valeur du slot `0x1b` d'`IBattleQuery`, c'est-a-dire
                             `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns
                             (caster, 2)`, le substrat du bit `CasterHas2TurnsLeft` (#287-r11-r1-r1).
                             ⚠ Le natif N'UTILISE PAS son parametre `unit` : le gate est GLOBAL au
                             match (plafond de rounds vs tours termines par `GetPlayerTurnOrder()[0]`),
                             donc ce champ ne depend PAS du caster interroge -- un appelant le
                             calcule UNE fois par bataille. Le foyer de calcul est
                             `engine.services.battle_query.has_minimum_remaining_turns` ; il rend
                             `True` **par lecture** des que `BC.Victory.VictoryConditions` ne porte
                             pas `MainPlayerRoundLimitation`, ce qui est le cas de la seed
                             versionnee et donc de tous les runners `rl_duel build`. `None` = pas
                             mesure (aucun canal DECISION ne publie `BC.Victory`) -> ne refuse pas.
      * `interrogated_pos` -- le `casterTiles` INTERROGE, c'est-a-dire la position que l'appelant
                             passe a la requete, PAS la tuile courante (`pos`). C'est la 2e clause
                             de `CasterHasNotMoved` qui le lit
                             (`GetTiles(caster).IsEquivalentTo(casterTiles)`), et elle n'est INERTE
                             que chez `BattleQuery$$IsTileInRangeOfAnyAbility`, ou les deux
                             coincident par construction. Chez l'autre consommateur --
                             `AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions, true)`,
                             l'oracle `aiMovableTiles` -- elle MORD : le natif refuse toute position
                             candidate DIFFERENTE de la tuile courante (#447-r1-r1). `None` = non
                             mesure -> la clause ne peut pas refuser.
      * `team`, `team_by_pos`, `walkable_by_pos`, `elev_by_pos`, `neigh_by_pos` -- le substrat de
                             plateau des regles-delegues derivables (aujourd'hui la seule qui l'est,
                             `1045`). Memes cartes que celles d'`is_tile_in_range_of_any_ability`.
    """
    pos: tuple | None = None
    has_tile: bool | None = None
    has_moved: bool | None = None
    is_turn_of_unit: bool | None = None
    interrogated_pos: tuple | None = None
    feet_count: int | None = None
    is_machine: bool | None = None
    has_minimum_remaining_turns: bool | None = None
    team: int | None = None
    team_by_pos: dict | None = None
    walkable_by_pos: dict | None = None
    elev_by_pos: dict | None = None
    neigh_by_pos: dict | None = None


#: La regle-delegue `options+0x30` (slot vtable `<klass>+0x470` = `<X>Ability$$GetDynamicInvalidCasterReason`)
#: ne retire RIEN -- soit la classe ne surcharge pas, soit son corps rend 0 dans le regime pose.
CASTER_GATE_NONE = "none"

#: `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetDynamicInvalidCasterReason`
#: -- la SEULE des douze qui soit derivable du substrat DECISION (cf. `_spawn_tile_gate_allows`).
CASTER_GATE_SPAWN_TILE = "spawn_tile"

#: Corps LU, et LU comme non derivable hors etat de bataille (effets, stats, tuiles temporaires,
#: selecteurs d'ennemis a portee). Le port ne refuse pas -> ecart PERMISSIF nomme.
CASTER_GATE_NOT_DERIVABLE = "not_derivable"

#: Le bit est pose, mais AUCUN symbole `<X>Ability$$GetDynamicInvalidCasterReason` n'existe dans les
#: tables pour cette classe. ⚠ Ce n'est PAS « elle ne surcharge pas » : IL2CPP DEDUPLIQUE les corps
#: triviaux, donc l'absence ne prouve rien (cf. le CLAUDE.md). Trancher exigerait le slot de vtable
#: de l'INSTANCE au runtime, ce que cette tranche n'a pas fait -> le port ne refuse pas.
CASTER_GATE_NOT_READ = "not_read"

#: Le regime de la regle-delegue CASTER, ability par ability. **N'y figurent QUE les porteurs du bit
#: `CasterMatchesDynamicRule`** -- pour les autres le natif n'invoque jamais le delegue, et une
#: entree serait du bruit. Les SEIZE porteurs des 169 masques lus y sont, aucun de plus (compte
#: RE-DERIVE #943 ; il etait de DOUZE sur 148, et les QUATRE entrants sont marques ci-dessous).
#: ⚠ TU PORTES UNE ABILITY DONT LE MASQUE POSE `CasterMatchesDynamicRule` ? Tu inscris sa ligne ICI,
#: DANS LE MEME COMMIT -- meme regle que `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` au registre des
#: abilities, et meme signature de degradation : un porteur ABSENT est traite comme « pas de regle ».
DYNAMIC_CASTER_GATE_BY_ABILITY: dict[int, str] = {
    # --- DERIVABLE ---------------------------------------------------------------------------
    ActiveAbilityType.GetEmRuntz: CASTER_GATE_SPAWN_TILE,   # 1045 GetEmRuntzAbility : `GetSpawnTileSelector(caster).Count > 0 ? 0 : 2`
    # --- LU, NON derivable hors etat de bataille ------------------------------------------------
    ActiveAbilityType.HarbingerOfDestruction: CASTER_GATE_NOT_DERIVABLE,  # 1008 HarbingerOfDestructionAbility : `GetEnemiesInRange(targetAmount,
    #     GetNumberConstant(0x16 range), ...)` puis `Count(sel) < 1` -> `0x200`. Lit les ENNEMIS a
    #     portee par un selecteur, et son `targetAmount` sort de la config d'ability.
    ActiveAbilityType.PrecisionShot: CASTER_GATE_NOT_DERIVABLE,  # 1015 PrecisionShotAbility : `HasEffect(caster, 0x3f7)` -> 0, sinon
    #     **2**. L'ability n'est castable QUE si le caster porte l'effet ; aucun canal DECISION ne
    #     publie les effets -> ne pas refuser (permissif).
    ActiveAbilityType.PrecisionShot_Aim: CASTER_GATE_NOT_DERIVABLE,  # 1012 PrecisionShot_AimAbility : la regle INVERSE
    #     de 1015 ci-dessus -- `HasEffect(caster, 0x3f7 EffectType.PrecisionShot_Aim)` -> **2**,
    #     sinon 0 : viser n'est legal que si l'on ne vise pas DEJA. MEME motif de non-derivabilite
    #     que sa soeur (aucun canal DECISION ne publie les effets), et MEME masque `0x8014` -- les
    #     deux `$$.ctor` sont identiques instruction pour instruction. Entree au registre COMBAT par
    #     #996-r1-r3, DANS LE MEME COMMIT que sa ligne ici.
    ActiveAbilityType.Burrowers: CASTER_GATE_NOT_DERIVABLE,  # 1023 BurrowersAbility : parcourt `casterTiles` et rend 0 des qu'une
    #     tuile est `TileExtensions$$IsTemporary`, sinon **4**. C'est l'une des rares regles-delegues
    #     qui lise VRAIMENT `casterTiles` (cf. l'avertissement ci-dessus).
    ActiveAbilityType.Poxwalkers: CASTER_GATE_NOT_DERIVABLE,  # 1040 SpawnPoxwalkersAbility : pour chaque tuile de `casterTiles`,
    #     `<IBattleQuery slot 0x68>(tile, ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange(caster),
    #     0, 0)` ; `Count > 0` -> 0, sinon **4**. Portee derivee d'un EFFET.
    ActiveAbilityType.Doombolt: CASTER_GATE_NOT_DERIVABLE,  # 1102 DoomboltAbility : `Count(DoomboltAbility$$GetTargets()) < 1`
    #     -> `0x8000000` (`TargetIsInRange`).
    ActiveAbilityType.AncestralFortune: CASTER_GATE_NOT_DERIVABLE,  # 1207 AncestralFortuneAbility : `CanAddCritChance` puis
    #     `CanAddBlockChance` (deux selecteurs sur les STATS du caster), puis
    #     `NormalUnits(AdjacentEnemies(...), 3)` ; le dernier `Count > 0` -> 0, sinon **2**.
    # #943 -- 1173 et 1192, entrees au registre par #894 (`cf11fd3b`) et #895 (`d87b2095`) sans leur
    # ligne ici, d'ou `master` ROUGE. Les DEUX corps EXISTENT dans `ghidra/functions.tsv` et ont ete
    # RELUS au decompile (build `rnca9r7q6c`) -- ce ne sont donc pas des `NOT_READ`.
    ActiveAbilityType.ArcScourge: CASTER_GATE_NOT_DERIVABLE,  # 1173 ArcScourgeAbility :
    #     `eff = EntityExtensions.GetOwnedEffect(caster, state, 0x555 = EffectType.MachineVengeance)`
    #     puis `if (eff != null && GetNumberConstant(0x76 = effectLevel_2) <= GetEffectLevel(eff))
    #     return 4` ; sinon `st = ActiveAbilityComponent.GetActive(caster, 1173).<Nullable<int>+0x18>`
    #     et `if (st.HasValue && st.Value == TurnComponent.GetAmountOfTurnsEnded(null))
    #     return 0x40000000000000` (`AlreadyUseThisTurn`). Les DEUX bras lisent un substrat qu'aucun
    #     canal DECISION ne publie (les EFFETS du caster ; le tour de derniere utilisation PAR
    #     ability). La face RUNNER, elle, porte le 1er bras
    #     (`runner/abilities/admec.py::ArcScourgeAbility.get_dynamic_invalid_caster_reason`) -- les
    #     deux lectures CONCORDENT terme a terme.
    ActiveAbilityType.NovaBoost: CASTER_GATE_NOT_DERIVABLE,  # 1192 NovaBoostAbility :
    #     `AbilityEntities(caster, ..., casterTiles)` local, puis
    #     `Enemies(Caster@DSLSelectors+0x48, GetMarkedTilesSelector(), selectionType = 3)` et
    #     `return (count > 1) ? 0 : 4` -- « AU MOINS DEUX ennemis dans la couronne ».
    #     `GetMarkedTilesSelector` = `Filter(AdjacentTiles(Caster), NOT IsTrenchTile(ActiveTarget))` :
    #     le substrat DECISION ne publie PAS les tuiles TRANCHEE, donc la condition n'est pas
    #     derivable telle quelle (meme famille que 1207 : un selecteur d'ennemis a portee).
    # --- BIT POSE, surcharge NON ETABLIE (residu, cf. `CASTER_GATE_NOT_READ`) --------------------
    # #943 -- 1032, entree par #697 (`c94aa0e2`) sans sa ligne. `CatalystAbility` ne porte QUE TROIS
    # corps nommes dans le binaire (`.ctor`, `GetEffectTargetsSelector`, `ExecuteBehaviour`) : aucun
    # `GetDynamicInvalidCasterReason`. ⚠ Ce n'est PAS « elle ne surcharge pas » -- IL2CPP DEDUPLIQUE
    # les corps triviaux, donc l'absence ne prouve rien. Meme regime que les cinq ci-dessous.
    ActiveAbilityType.Catalyst: CASTER_GATE_NOT_READ,               # 1032
    # #943 (au REBASE) -- 1210, entree par #935 PENDANT cette tranche : le compte se RE-DERIVE,
    # il ne se soustrait pas. MEME mesure que 1032 -- `ExemplarOfTheMontkaAbility` ne porte que
    # `.ctor` et `ExecuteBehaviour` (`ghidra/functions.tsv` ET `search_symbols_by_name`, 14 symboles
    # pour tout le nom, dont aucun `GetDynamicInvalidCasterReason`), et l'absence ne prouve rien.
    ActiveAbilityType.ExemplarOfTheMontka: CASTER_GATE_NOT_READ,    # 1210
    ActiveAbilityType.EarlyWarningOverride: CASTER_GATE_NOT_READ,   # 1077
    ActiveAbilityType.WarHowl: CASTER_GATE_NOT_READ,                # 1106
    ActiveAbilityType.MomentShackle: CASTER_GATE_NOT_READ,          # 1184
    ActiveAbilityType.InstrumentsOfVengeance: CASTER_GATE_NOT_READ,  # 1215
    ActiveAbilityType.MartialExemplar: CASTER_GATE_NOT_READ,        # 1216
    # 1052, entree par #1032 sans sa ligne -- le cliquet
    # `test_433_..._caster_reason_offline::test_la_table_de_regime_couvre_EXACTEMENT_les_porteurs_du_bit`
    # rougissait dessus sur `master`. MEME mesure, MEME preset (`<preset>+0x28 = 0x8004`) et MEME
    # forme de preuve que 1210 : le port de 1052 a LU que `CallRipperSwarmsAbility` ne porte que
    # `ExecuteBehaviour` et `.ctor` dans son bloc de `methodPointers`, sans
    # `GetDynamicInvalidCasterReason`. ⚠ C'est `NOT_READ`, pas `NONE` : l'absence d'un symbole ne
    # prouve PAS l'absence de surcharge (IL2CPP DEDUPLIQUE les corps triviaux et n'en attribue
    # qu'UN proprietaire). Trancher exigerait le slot de vtable de l'INSTANCE au runtime. Les deux
    # regimes ne divergent que si la surcharge existe ET refuse -- le port ne refuse pas, donc
    # l'ecart reste PERMISSIF et NOMME, du meme cote que ses six voisines.
    ActiveAbilityType.CallRipperSwarms: CASTER_GATE_NOT_READ,       # 1052
}

#: `IdunBattle.Entities.Enum.UnitTrait.Steppable` = 0x1b -- le trait que `GetSpawnTileSelector`
#: EXCLUT des ennemis (`UnitsWithoutTrait(Enemies(AllUnits), 0x1b)`).
UNIT_TRAIT_STEPPABLE = UnitTrait.Steppable


def dynamic_caster_gate_of(ability_id) -> str:
    """Le regime de la regle-delegue CASTER de cette ability.

    L'ABSENCE de la table vaut `CASTER_GATE_NONE` -- ce qui est exact pour toute ability qui ne pose
    pas `CasterMatchesDynamicRule` (le natif n'invoque alors JAMAIS le delegue), et c'est le seul
    cas ou l'appelant l'interroge."""
    try:
        aid = int(ability_id)
    except (TypeError, ValueError):
        return CASTER_GATE_NONE
    return DYNAMIC_CASTER_GATE_BY_ABILITY.get(aid, CASTER_GATE_NONE)


def _spawn_tile_gate_allows(caster: "CasterSubstrate") -> bool | None:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector`,
    evalue sur le substrat DECISION -- `True` = au moins une tuile de spawn, donc le delegue rend 0.

    Le selecteur, MIRROR 1:1 (le meme que la face COMBAT porte deja dans
    `engine.entities.selectors.composites.get_spawn_tile_selector`, confirme LIVE #200) :

        op_BitwiseAnd( CanAddUnit(AdjacentTiles(Caster())),
                       Unique(AdjacentTiles(UnitsWithoutTrait(Enemies(AllUnits), 0x1b))) )

    = les tuiles LIBRES et MARCHABLES adjacentes au CASTER qui sont AUSSI adjacentes a un ennemi
    vivant non-`Steppable`. `AdjacentTiles` passe par
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(t, false, true, true)`, donc par
    `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` et sa porte d'elevation : le foyer
    porte est `engine.battle_query.is_adjacent`, exactement comme pour le gate CIBLE
    `GATE_FREE_ADJACENT_IN_CONFIG_RANGE`.

    `None` = **pas mesure** : il manque la tuile du caster, la carte des occupants ou celle de la
    walkability. Le natif, lui, repond toujours -- mais un port qui inventerait « aucune tuile de
    spawn » RETIRERAIT une zone, l'ecart RESTRICTIF que ce module refuse.

    ECARTS NOMMES, tous PERMISSIFS (le port trouve une tuile la ou le natif n'en trouve pas) :
      * le trait `Steppable` de l'occupant n'est publie par AUCUN canal DECISION -> un ennemi
        Steppable compte ici alors que `UnitsWithoutTrait` l'exclut ;
      * `team_by_pos` ne porte que l'occupant VIVANT d'une tuile, ce qui est bien le filtre
        `AllUnits` (= `AllAliveMachinesSelector`), mais il ne dit pas si l'entite est une UNITE :
        une machine y compterait comme ennemi."""
    pos = caster.pos if caster is not None else None
    if pos is None or caster.team_by_pos is None or caster.walkable_by_pos is None:
        return None
    if caster.team is None:
        return None
    p = (int(pos[0]), int(pos[1]))
    elev, neigh = caster.elev_by_pos, caster.neigh_by_pos
    enemies = [t for t, team in caster.team_by_pos.items()
               if team is not None and int(team) != int(caster.team)]
    for n in hexgeo.neighbors(p[0], p[1]):
        t = (int(n[0]), int(n[1]))
        if t == p or not bq.is_adjacent(p, t, elev, neigh):
            continue                            # `AdjacentTiles(Caster())` -- porte d'elevation
        if t in caster.team_by_pos or not caster.walkable_by_pos.get(t):
            continue                            # `CanAddUnit` -- LIBRE et MARCHABLE
        for e in enemies:                       # `AdjacentTiles(UnitsWithoutTrait(Enemies, 0x1b))`
            if bq.is_adjacent(e, t, elev, neigh):
                return True
    return False


def dynamic_caster_reason(ability_id, caster: "CasterSubstrate" = None) -> int | None:
    """La regle-delegue CASTER `options+0x30` -- le code qu'elle rend, ou `None` = pas mesure.

    Le natif re-emballe ce code TEL QUEL (`if (r != 0) return GenericBrokenTargetingRule(r)`), donc
    la valeur rendue ici est celle de la delegue, jamais le bit `CasterMatchesDynamicRule` qui l'a
    armee -- meme discipline que `get_caster_not_added_reason` cote RUNNER."""
    gate = dynamic_caster_gate_of(ability_id)
    if gate == CASTER_GATE_SPAWN_TILE:
        ok = _spawn_tile_gate_allows(caster)
        if ok is None:
            return None
        # `return (list.Count > 0) ? 0 : 2;` -- le litteral **2**, que l'enum genere nomme
        # `TargetMatchesDynamicRule`. Le natif reutilise ce code pour le volet CASTER (cf.
        # `GetEmRuntzAbility.get_dynamic_invalid_caster_reason`, face RUNNER, meme litteral).
        return 0 if ok else int(TR.TargetMatchesDynamicRule)
    return None                                  # NONE / NOT_DERIVABLE / NOT_READ -> pas de refus


def invalid_caster_reason(ability_id, caster: "CasterSubstrate" = None) -> int | None:
    """`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` -- le PREMIER
    `TargetingRule` rompu du volet CASTER, `0` si le caster est valide, `None` si RIEN n'a pu etre
    mesure (masque non RE-lu).

    L'ORDRE EST LE LIVRABLE : c'est lui qui fixe LAQUELLE des onze regles est rendue quand
    plusieurs sont rompues. Il est transcrit du decompile cite en tete de section, clause par
    clause, y compris les quatre a gisement VIDE."""
    try:
        aid = int(ability_id)
    except (TypeError, ValueError):
        return None
    opts = TGT.targeting_options_for(aid)
    if opts is None:
        return None                              # masque NON RE-lu -> aucune regle lisible
    rules = int(getattr(opts, "rules", 0) or 0)

    # 1. `CasterHasNotMoved` (0x10), sous son PREFIXE `BattleQuery$$IsTurnOfUnit(caster)` -- les
    #    DEUX conditions, dans cet ordre, et il faut que les deux soient MESUREES vraies (tri-etat :
    #    un `None` ne refuse pas). Omettre le prefixe faisait refuser 11 paires sur 42 que le natif
    #    ACCEPTE (cf. l'encadre de la section GATE 4).
    #    La 2e clause (`GetTiles(caster).IsEquivalentTo(casterTiles)`) N'EST INERTE QUE CHEZ UN
    #    consommateur : `BattleQuery$$IsTileInRangeOfAnyAbility`, qui passe le singleton
    #    `{GetMainTile(caster)}` -- donc toujours equivalent. Chez l'AUTRE,
    #    `AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions, true)` (l'oracle
    #    `aiMovableTiles`), `casterTiles` est la position CANDIDATE balayee, et la clause MORD des
    #    qu'elle differe de la tuile courante. MESURE (#447-r1-r1, greffe sur un cul-de-sac, deux
    #    abilities du MEME preset dont le masque ne differe que par ce bit) : `1215` (`0x8004`) --
    #    le natif verse la tuile source ; `1216` (`0x8014`) -- il ne verse RIEN, alors que
    #    `abilityReason.casterReason` (evalue depuis la tuile COURANTE) rend `0` des deux cotes.
    #    Les deux termes sont en TRI-ETAT : un fait non mesure ne refuse jamais.
    if rules & int(TR.CasterHasNotMoved):
        if caster is not None and caster.is_turn_of_unit:
            if caster.has_moved:
                return int(TR.CasterHasNotMoved)
            if (caster.interrogated_pos is not None and caster.pos is not None
                    and tuple(caster.interrogated_pos) != tuple(caster.pos)):
                return int(TR.CasterHasNotMoved)
    # 2. `CasterCanMove` (0x10000000) -- `UnitExtensions$$CanMove` n'est publie par aucun canal
    #    DECISION. 2 porteurs (1043, 1152). NON PORTEE, degradation permissive.
    # 3. `CasterHasCompletedOneTurn` (0x80000000) -- `GetStat(caster, 0xc) <= 1`. **0 porteur**.
    # 4a. La clause TUILE-NULLE. Le litteral rendu est `AllowNullCasterTile`, la PERMISSION dont
    #     l'absence declenche le refus -- pas une regle homonyme.
    if not (rules & (int(TR.AllowNullCasterTile) | int(TR.CasterHasNoTile))):
        if caster is not None and caster.has_tile is False:
            return int(TR.AllowNullCasterTile)
    # 4b. `CasterHasNoTile` (bit 55) pose ET `casterTiles` NON vide -> refus. **0 porteur** : mirror
    #     STRUCTUREL.
    if rules & int(TR.CasterHasNoTile):
        if caster is not None and caster.has_tile is True:
            return int(TR.CasterHasNoTile)
    # 5. `CasterMatchesDynamicRule` (0x4) -- LE POINT D'EXTENSION du volet caster. 12 porteurs.
    if rules & int(TR.CasterMatchesDynamicRule):
        r = dynamic_caster_reason(aid, caster)
        if r:
            return int(r)
    # 6. Les trois filtres de `GetFeetCount`. 1 porteur (1151, `CasterHas1Tiles`), 0 pour les deux
    #    autres. Ils ne mordent que sur un compte MESURE.
    feet = None if caster is None else caster.feet_count
    if feet is not None:
        if (rules & int(TR.CasterHas1Tiles)) and int(feet) != 1:
            return int(TR.CasterHas1Tiles)
        if (rules & int(TR.CasterHas3Tiles)) and int(feet) != 3:
            return int(TR.CasterHas3Tiles)
        if (rules & int(TR.CasterHas7Tiles)) and int(feet) != 7:
            return int(TR.CasterHas7Tiles)
    # 7. `CasterHas2TurnsLeft` (bit 52) -- PORTEE depuis #287-r11-r1-r1. Le slot `0x1b` est 27
    #    `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` (arite 2, table de
    #    metadonnee ; confirme par la lambda `...u003Cu003Ec__DisplayClass68_0$$
    #    u003CHasMinimumRemainingTurnsu003Eb__0`). Il etait declare « non resolu » PARCE QUE
    #    quatre sites du port ecrivaient `0x1a` (= 26 `ShouldPlayerSkipTurn`, arite **1**) : un
    #    decalage de UN, pas une limite de lecture.
    #    3 porteurs, tous MACHINE OF WAR (1142, 1160, 1188). Le champ est en TRI-ETAT : aucun canal
    #    DECISION ne publie `BC.Victory`, donc `None` par ce chemin -> ne refuse pas, comme le reste
    #    du module. Un appelant qui connait sa BC le calcule par
    #    `engine.services.battle_query.has_minimum_remaining_turns`.
    if rules & int(TR.CasterHas2TurnsLeft):
        if caster is not None and caster.has_minimum_remaining_turns is False:
            return int(TR.CasterHas2TurnsLeft)
    # 8. `CasterIsMachine` (bit 53). 1 porteur (1158 `DutyEternal`, une MoW -> INERTE chez lui).
    if rules & int(TR.CasterIsMachine):
        if caster is not None and caster.is_machine is False:
            return int(TR.CasterIsMachine)
    return 0


# ------------------------------------------------------------------------------------------------
# La composition, DANS L'ORDRE NATIF
# ------------------------------------------------------------------------------------------------
#: Nom du gate qui a mordu -- ce sont les symboles natifs, pas des etiquettes libres.
REASON_CAN_STILL_BE_USED = "CanStillBeUsed"          # slot 0x14
REASON_IS_DISABLED = "IsDisabled"                    # slot 0x13
REASON_CAN_CURRENTLY_BE_USED = "CanCurrentlyBeUsed"  # slot 0xb `AttackQuery$$GetInvalidCasterReason`


def caster_gate_reason(ability_id, ability_state=None,
                       caster: "CasterSubstrate" = None) -> str | None:
    """Le PREMIER gate qui annule l'ability, ou `None` si elle passe les quatre.

    L'ordre est celui du decompile et il n'est pas cosmetique : c'est lui qui fixe LEQUEL des
    quatre est rapporte quand plusieurs sont rompus, donc la seule chose qu'un port puisse
    encore rater une fois les quatre presents.

    Le 4e rend le NOM NATIF de la regle rompue (`TargetingRule`), pas une etiquette de gate : c'est
    la seule facon de distinguer ses onze causes, et c'est ce que l'oracle `abilityReason` publie."""
    still = can_still_be_used(ability_state)
    if still is False:
        return REASON_CAN_STILL_BE_USED
    if is_disabled(ability_id):
        return REASON_IS_DISABLED
    if can_currently_be_used(ability_state) is False:
        return REASON_CAN_CURRENTLY_BE_USED
    reason = invalid_caster_reason(ability_id, caster)
    if reason:
        try:
            return TR(int(reason)).name
        except ValueError:                       # combinaison de bits : la rendre en hexa BRUT
            return "0x%x" % int(reason)
    return None


def gates_allow(ability_id, ability_state=None, caster: "CasterSubstrate" = None) -> bool:
    """L'ability CONTRIBUE-t-elle sa zone ? -- `GetAllTilesInAbilityRange` rend un ensemble VIDE
    quand l'un des quatre gates mord.

    Canal absent -> `True` (aucun gate mesurable hors `IsDisabled`) : borne SUPERIEURE nommee,
    exactement le comportement d'avant `#433-r4-r2-r1-r1-c`."""
    return caster_gate_reason(ability_id, ability_state, caster) is None


def ability_state_map(unit_row) -> dict:
    """`{abilityId: ligne d'etat}` depuis une ligne `decisionView.units[]` / `.mows[]`.

    La cle emise par `projectUnitsFull` (`frida/hooks/features/ai-step/projection.ts`) est `id`,
    pas `abilityId` -- et l'etat n'est present que si l'appelant a demande `allAbilities: true`
    (sans quoi `unitAbilityTypes` n'emet que l'attaque NORMALE, sans etat). Ligne sans `id` ->
    ECARTEE, jamais une entree inventee."""
    out: dict = {}
    for a in ((unit_row or {}).get("abilities") or []):
        aid = a.get("id")
        if aid is None:
            continue
        try:
            out[int(aid)] = a
        except (TypeError, ValueError):
            continue
    return out


def normal_attack_id(unit_row):
    """L'id CONCRET de l'attaque normale de la ligne (`kind == "normal"`, cf.
    `NormalAttackType @0x28` -- per-unit, jamais l'abstrait 17). `None` = non publie."""
    for a in ((unit_row or {}).get("abilities") or []):
        if a.get("kind") == "normal" and a.get("id") is not None:
            try:
                return int(a["id"])
            except (TypeError, ValueError):
                return None
    return None

