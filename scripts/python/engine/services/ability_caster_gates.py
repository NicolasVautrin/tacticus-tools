"""Les TROIS gates EN AMONT du calcul de zone -- ce qui ANNULE une ability avant meme qu'on
demande ou elle porte (#433-r4-r2-r1-r1-c).

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
  * gate 3d -> `can_currently_be_used`, mirror EXACT de la propriete (les quatre champs) ;
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
  * gate 3g -> face RUNNER seulement (il consomme un `State`).

NON MESURE != FAUX. Quand le canal manque (`ability_state` absent, ou champ absent de la ligne),
les gates 1 et 3 rendent `None` = « pas mesure », et l'appelant ne gate PAS : c'est le statu quo
d'avant cette tranche, une borne SUPERIEURE sur la zone. Le gate 2, lui, repond toujours.
"""
from __future__ import annotations

import gameconfig as GC

from ..runner.abilities.attack_type import is_regular_attack

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
    from ..entities.active_ability_type import ActiveAbilityType
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
    """GATE 3d -- `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed`, mirror
    1:1 des QUATRE champs que la propriete lit :

        if (!CanStillBeUsed || IsDisabled) return false;
        a = !RemainingCooldownTurns.HasValue || RemainingCooldownTurns.Value < 1;
        b =  !AmmoCost.HasValue ? true : HasEnoughAmmo;
        return a && b;

    Les quatre sont publies par `decisionView` (`usable`, `disabled`, `cooldown`, `ammoCost` /
    `hasAmmo`). Tri-etat : `None` des que le canal ne dit rien du couple `usable`/`disabled` --
    on ne fabrique pas un `True`. Un champ de detail absent (`cooldown` / `ammoCost` non emis)
    vaut « Nullable vide », ce qui est EXACTEMENT ce que `readAbilityState` ecrit quand le
    `hasValue` du natif est faux."""
    still = can_still_be_used(state)
    disabled = _flag(state, "disabled")
    if still is None and disabled is None:
        return None
    if still is False or disabled is True:
        return False
    cd = (state or {}).get("cooldown")
    if cd is not None:
        try:
            if int(cd) >= 1:
                return False
        except (TypeError, ValueError):
            pass
    cost = (state or {}).get("ammoCost")
    if cost is not None:
        return bool(_flag(state, "hasAmmo"))
    return True


# ------------------------------------------------------------------------------------------------
# La composition, DANS L'ORDRE NATIF
# ------------------------------------------------------------------------------------------------
#: Nom du gate qui a mordu -- ce sont les symboles natifs, pas des etiquettes libres.
REASON_CAN_STILL_BE_USED = "CanStillBeUsed"          # slot 0x14
REASON_IS_DISABLED = "IsDisabled"                    # slot 0x13
REASON_CAN_CURRENTLY_BE_USED = "CanCurrentlyBeUsed"  # AttackQuery$$GetInvalidCasterReason, marche d


def caster_gate_reason(ability_id, ability_state=None) -> str | None:
    """Le PREMIER gate qui annule l'ability, ou `None` si elle passe les trois.

    L'ordre est celui du decompile et il n'est pas cosmetique : c'est lui qui fixe LEQUEL des
    trois est rapporte quand plusieurs sont rompus, donc la seule chose qu'un port puisse
    encore rater une fois les trois presents."""
    still = can_still_be_used(ability_state)
    if still is False:
        return REASON_CAN_STILL_BE_USED
    if is_disabled(ability_id):
        return REASON_IS_DISABLED
    if can_currently_be_used(ability_state) is False:
        return REASON_CAN_CURRENTLY_BE_USED
    return None


def gates_allow(ability_id, ability_state=None) -> bool:
    """L'ability CONTRIBUE-t-elle sa zone ? -- `GetAllTilesInAbilityRange` rend un ensemble VIDE
    quand l'un des trois gates mord.

    Canal absent -> `True` (aucun gate mesurable hors `IsDisabled`) : borne SUPERIEURE nommee,
    exactement le comportement d'avant `#433-r4-r2-r1-r1-c`."""
    return caster_gate_reason(ability_id, ability_state) is None


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
