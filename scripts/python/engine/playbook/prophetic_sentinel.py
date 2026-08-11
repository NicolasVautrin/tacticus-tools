"""`PropheticSentinelPlaybook` (1543) -- face DECISION **OWNER** du passif de kit de `thousSekhetar`.

Famille << CORPS PROPRE >> (comme `friends_in_range.py` et `rad_saturation.py`) : la classe
n'overrider PAS les accesseurs du corps partage `AdjacentUnitPreferenceTriggeredAbilityPlaybook`,
elle a SON PROPRE iterateur. Le dispatcher est le meme (feuille de tuile
`TriggeredAbilitiesUtility(2)` -> `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`), d'ou
l'enregistrement dans `TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`).

La face NON-OWNER de la MEME ability est deja portee et vit ailleurs
(`playbook/non_owner.py::PropheticSentinelNonOwnerPlaybook`, feuille `TriggeredAbilitiesNonOwner(4)`,
DEUX cles cumulatives Psyker/Chaos). Les deux faces sont DISJOINTES : celle-ci pese le mouvement du
PORTEUR, celle-la le mouvement des AUTRES vers le porteur.

`IdunBattle.AI.Playbook.Loki.PropheticSentinelPlaybook$$.ctor` passe `0x607` = 1543
(`TriggeredAbilityType.PropheticSentinel`).

CORPS MOVE -- `IdunBattle.AI.Playbook.Loki.PropheticSentinelPlaybook.
u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`, relu LIGNE A LIGNE (build
`rnca9r7q6c`) :

    query = <service IBattleQuery du playbook, champ +0x60>
    units = query.<slot 0x84 = GetAdjacentFriends, 2 arguments>( case.Position@+0x18,
                                                                 case.Unit@+0x10 )
    val   = 0
    foreach u in units :
        if (IdunBattle.Entities.UnitExtensions$$HasTrait(u, 0x3ea))       // UnitTrait.Psyker
            val += <delegue getUtilityVal>( <statics[0]> )
    yield Fix64.op_Implicit(val)

`<statics[0]>` est le champ que `IdunBattle.AI.Playbook.Loki.PropheticSentinelPlaybook$$.cctor`
remplit ; son adresse de litteral est celle de `"PropheticSentinel_LikesAdjacentPsykerFriends"`
(`metadata/string_literals.tsv`) -- la cle est donc LUE, pas devinee par prefixe.
`Utilities.Default.TriggeredAbilities["PropheticSentinel_LikesAdjacentPsykerFriends"]` = 20 au
gameconfig vivant.

⚠ LE PREDICAT EST `HasTrait(u, Psyker)` **INLINE**, pas un delegue LINQ -- contrairement a
`RadSaturationPlaybook` (`Enumerable.Count(units, <>c.<>9__2_0)`). Le comptage et la ponderation se
font dans la MEME boucle (`val += w`), ce qui est equivalent a `w x n` : `w` ne depend pas de `u`.

⚠ **LE PREDICAT DE CETTE FACE N'EST PAS CELUI DE LA FACE NON-OWNER** -- et c'est le piege du kit.
La face non-owner CUMULE `Psyker` (0x3ea) **et** `Chaos` (0x7ea) ; celle-ci ne connait QUE `Psyker`.
Un port qui recopierait le predicat d'une face sur l'autre donnerait 40 la ou le natif donne 20 (ou
20 la ou il donne 0) sur toute unite Chaos non-Psyker -- c'est-a-dire sur la MAJORITE du roster
Thousand Sons. Les deux predicats sont lus separement, dans deux corps natifs distincts.

⚠ CE PREDICAT N'EST PAS NON PLUS CELUI DU TRIGGER DE COMBAT, meme s'il porte sur le meme trait :
le trigger de `PropheticSentinel_OverwatchAbility` compte les amis adjacents Psyker autour de la
position REELLE en fin de tour ; ce playbook les compte autour de chaque TUILE CANDIDATE pendant le
sweep de mouvement. Les deux se rejoignent seulement sur la tuile finalement choisie.

SLOT / SURCHARGE. `GetAdjacentFriends` occupe les slots 129..132 (`0x81`..`0x84`) de `IBattleQuery`
(`metadata/interface_slots.tsv`, arite 2). Le corps prend le slot `0x84`, dont le 1er argument est
`case.Position@+0x18` (le `UnitPosition` du mover -- sa LISTE de tuiles), la ou
`KardiocoreGalvanusPlaybook` prend `0x83` avec `get_MovementTile(case)` (UNE tuile).
`IdunBattle.Core.Services.BattleQuery$$GetAdjacentFriends` decline les deux vers le meme couple
`IterateAdjacentTiles` + filtre `OwnerComponent.CurrentPlayerEntityId` du `unit` : pour un mover
MONO-TUILE les deux formes coincident exactement. RESIDU NOMME (#915-r2, meme forme que celui deja
inscrit pour `AdjacentToOwnerNonOwnerPlaybook`) : un mover MULTI-TUILES (Machine of War) verrait le
natif partir de TOUTES ses tuiles ; le port part de la tuile candidate. `thousSekhetar` est
mono-tuile, donc l'ecart est inerte pour le seul porteur.

SELF. Le corps n'ecrit AUCUN `RemoveAll(u.Id == case.Unit.Id)` -- comme `friends_in_range` et
`RadSaturationPlaybook`, et contrairement au corps partage `AdjacentUnitPreference`. Le mover compte
donc pour lui-meme des que son ORIGINE est ring-1 de la tuile candidate. `thousSekhetar` **PORTE**
le trait `Psyker` ? NON (kit : Hero, WeaverOfFate, Mechanical, Camouflage, Infiltrate, Overwatch) --
donc ce volet est INERTE pour son seul porteur, mais il est ecrit parce que c'est ce que le natif
fait (meme arbitrage que `RadSaturationPlaybook`).

ADJACENCE. `GetAdjacentFriends` passe par `IdunBattle.Core.Services.TileQuery.
u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : liste de voisinage STOCKEE + porte d'elevation
`|delta| < 2`. `battle_query.is_adjacent` porte les deux (#271/#433-r4).

FACE ATTACK. Le build ne porte AUCUN `PropheticSentinelPlaybook.<CalculateAttackUtilityInStepsInternal>`
(seul `<CalculateMovementUtilityInStepsInternal>d__2` existe) : la face ATTACK retombe sur la base
`TriggeredAbilityPlaybook<T>` qui yield 0. Rien a enregistrer cote attack -- l'absence du registre y
vaut 0, meme valeur.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType

#: Nom gameconfig du trait `UnitTrait.Psyker` (0x3ea = 1002). Cote DECISION, `friend_units[i]
#: ["traits"]` porte des NOMS (`entity_trait_names`) et `ctx["unit_traits"]` des IDS -- les deux
#: substrats sont lus, chacun dans sa forme.
_PSYKER_NAME = "Psyker"


class PropheticSentinelPlaybook:
    """+20 par AMI ADJACENT a trait `Psyker` autour de la tuile candidate, self inclus."""

    ABILITY_ID = TriggeredAbilityType.PropheticSentinel              # 0x607 = 1543
    #: l'argument litteral `0x3ea` du `HasTrait` inline. `UnitTrait`, et l'ordinal ne discrimine
    #: PAS : 1002 nomme `CombatRestoratives` en `EffectType` et `RitesOfBattle` en
    #: `ActiveAbilityType`. C'est la CALLEE (`UnitExtensions$$HasTrait`) qui tranche.
    PSYKER_TRAIT = UnitTrait.Psyker                                  # 0x3ea = 1002
    WEIGHT_KEY = "PropheticSentinel_LikesAdjacentPsykerFriends"      # Utilities.Default.TriggeredAbilities

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
            # `HasTrait(u, 0x3ea)` -- `Psyker` n'est PAS un trait de GRANDE ALLIANCE (ceux-la sont
            # Imperial/Xenos/Chaos, et seuls eux exigent le detour par `GrandAllianceId` du
            # gameconfig, cf. `adjacent_unit_preference._has_trait`) : il vit litteralement dans le
            # bloc `traits` du kit, donc le test d'appartenance est le mirror COMPLET du natif.
            if p and bq.is_adjacent(tile, p, elev, neigh) and _PSYKER_NAME in (u.get("traits") or ()):
                n += 1
        # SELF : cf. l'en-tete -- le corps natif n'exclut pas `case.Unit`. `ctx["unit_traits"]` porte
        # les IDS du mover (pas des noms) : on teste l'id.
        sp = ctx.get("self_pos")
        if sp and bq.is_adjacent(tile, tuple(sp), elev, neigh):
            if int(self.PSYKER_TRAIT) in {int(t) for t in (ctx.get("unit_traits") or ())}:
                n += 1
        return float(int(w) * n)
