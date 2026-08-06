"""`RadSaturationPlaybook` (1202) -- face DECISION du passif de contamination du Skitarii Vanguard.

Famille « CORPS PROPRE » (comme `friends_in_range.py`) : la classe n'overriden PAS les accesseurs
du corps partage `AdjacentUnitPreferenceTriggeredAbilityPlaybook`, elle a son PROPRE iterateur.
Le dispatcher est le meme (feuille de tuile `TriggeredAbilitiesUtility(2)` ->
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`), d'ou l'enregistrement dans
`TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`).

`IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook$$.ctor` passe `0x4b2` = 1202
(`TriggeredAbilityType.RadSaturation`).

CORPS MOVE -- `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.
u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`, relu LIGNE A LIGNE sur le build
courant :

    query  = <service IBattleQuery du playbook>
    tile   = UtilityMovementCase.get_MovementTile(case)
    units  = query.<slot 0x83 = GetAdjacentFriends, 2 arguments>(tile, case.Unit@+0x10)
    n      = System.Linq.Enumerable.Count(units, <>c.<>9__2_0)
    w      = <delegue de lookup>("RadSaturation_AdjacentMarshals")
    yield Fix64.op_Implicit((int)(w * n))

et le PREDICAT, qui a un SYMBOLE sur ce build (il n'en avait pas sur `gqfc5mff6c`, d'ou le pari
d'alors) -- `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.u003Cu003Ec$$
u003CCalculateMovementUtilityInStepsInternalu003Eb__2_0` :

    return IdunBattle.Entities.UnitExtensions$$HasActiveAbility(f, 0x45e);

`0x45e` = 1118 = `ActiveAbilityType.DoctrinaImperatives` -- l'ACTIVE du Skitarii Marshal
(`admecMarshall`, « Tan Gi'da »). D'ou le nom de la cle BC : `..._AdjacentMarshals`.

⇒ **Le terme compte les AMIS (slot `GetAdjacentFriends`, arite 2), et parmi eux les seuls
MARSHALS.** Il vaut `+10 x n` (`Utilities.Default.TriggeredAbilities`), donc il ATTIRE le porteur
vers son Marshal ; il ne penalise rien.

⚠ TROIS FAITS DE `case-26` SONT MORTS AVEC CETTE RELECTURE, et ils allaient tous dans le meme
sens (un terme NEGATIF sur les deux camps) :
  * le slot n'est pas un `GetAdjacentUnits` « both teams » : c'est `0x83`, un `GetAdjacentFriends`
    a DEUX arguments (`data/symbols/<build>/metadata/interface_slots.tsv` : `GetAdjacentUnits` =
    122..124 arite 4, `GetAdjacentEnemies` = 125..128 arite 3, `GetAdjacentFriends` = 129..132
    arite 2). Un port qui compterait les deux camps serait FAUX ;
  * le multiplicateur n'est pas `Utilities.Default.Contaminated.AffectedUnit` (= -25) mais
    `Utilities.Default.TriggeredAbilities.RadSaturation_AdjacentMarshals` (= +10), litteral
    RESOLU (`probe_212_bc_key_literals.py --symbol ...`), pas devine ;
  * le predicat n'est pas « allie non immunise a Contaminated » : `ContaminatedEffect$$
    EntityIsImmuneToEffect` n'intervient PAS ici. C'est `HasActiveAbility(DoctrinaImperatives)`.

SELF. Le corps n'ecrit AUCUN `RemoveAll(u.Id == case.Unit.Id)` -- contrairement au corps partage
`AdjacentUnitPreference`, qui, lui, en ecrit un. Le mover compte donc pour lui-meme des que son
ORIGINE est ring-1 de la tuile candidate (meme regime que `friends_in_range.py`), d'ou la lecture
d'`unit_active_abilities`. Aucune unite de ce build ne porte a la fois 1202 et 1118, donc ce volet
est INERTE en pratique -- il est ecrit parce que c'est ce que le natif fait, pas parce qu'on l'a vu
mordre.

ADJACENCE. `GetAdjacentFriends` passe par `IdunBattle.Core.Services.TileQuery.
u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : liste de voisinage STOCKEE + porte d'elevation
`|delta| < 2`. `battle_query.is_adjacent` porte les deux (#271/#433-r4) -- `hexgeo.distance == 1`
seul SUR-COMPTE.

FACE ATTACK. `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook.
u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` rend `Fix64.op_Implicit(0)`
inconditionnellement : RadSaturation ne pese QUE le mouvement. Rien a enregistrer cote attack
(`playbook/psyker.py`) -- l'absence du registre y vaut 0, meme valeur.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.triggered_ability_type import TriggeredAbilityType


class RadSaturationPlaybook:
    """+10 par AMI ADJACENT porteur de l'active `DoctrinaImperatives`, self inclus."""

    ABILITY_ID = TriggeredAbilityType.RadSaturation                 # 0x4b2 = 1202
    #: l'argument litteral `0x45e` du predicat `<>c.<...>b__2_0` -- `ActiveAbilityType`, et
    #: l'ordinal ne discrimine PAS : 1118 nomme `TerrorsLament` en `TriggeredAbilityType` et
    #: `WhipcoilBody_ReduceDmg` en `EffectType`. C'est la CALLEE (`HasActiveAbility`) qui tranche.
    MARSHAL_ABILITY = ActiveAbilityType.DoctrinaImperatives         # 0x45e = 1118
    WEIGHT_KEY = "RadSaturation_AdjacentMarshals"                   # Utilities.Default.TriggeredAbilities

    def _is_marshal(self, active_ids) -> bool:
        """`IdunBattle.Entities.UnitExtensions$$HasActiveAbility(u, 0x45e)` cote offline.

        `active_ids` = le kit ACTIF de l'ENTITE (`entities.active_abilities.
        entity_active_ability_ids`), c.-a-d. l'`ActiveAbilityComponent` mesure quand le canal
        `unitAbilityStates` a parle, le kit gameconfig sinon."""
        return int(self.MARSHAL_ABILITY) in (active_ids or ())

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        elev = ctx.get("elev_by_pos")
        neigh = bq.neigh_map(ctx)
        n = 0
        for u in (ctx.get("friend_units") or ()):
            p = u.get("pos")
            if p and bq.is_adjacent(tile, p, elev, neigh) and self._is_marshal(u.get("active")):
                n += 1
        # SELF : cf. l'en-tete -- le corps natif n'exclut pas `case.Unit`.
        sp = ctx.get("self_pos")
        if (sp and bq.is_adjacent(tile, tuple(sp), elev, neigh)
                and self._is_marshal(ctx.get("unit_active_abilities"))):
            n += 1
        return float(int(w) * n)
