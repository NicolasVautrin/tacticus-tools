"""`IntoxicatingElixirPlaybook` (1463) -- face DECISION **OWNER** de la RELIQUE `IntoxicatingElixir`.

Famille << CORPS PROPRE >> (comme `friends_in_range.py`, `rad_saturation.py`,
`prophetic_sentinel.py`) : la classe n'override PAS les accesseurs du corps partage
`AdjacentUnitPreferenceTriggeredAbilityPlaybook`, elle a SON PROPRE iterateur. Le dispatcher est le
meme (feuille de tuile `TriggeredAbilitiesUtility(2)` ->
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`), d'ou l'enregistrement dans
`TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`).

`IdunBattle.AI.Playbook.Loki.IntoxicatingElixirPlaybook$$.ctor` passe `0x5b7` = 1463
(`TriggeredAbilityType.IntoxicatingElixir`) ; `classes.tsv` donne la parente
`TriggeredAbilityPlaybook<IntoxicatingElixirAbility>`. Aucune face NON-OWNER n'existe dans le build
(pas de `IntoxicatingElixirNonOwnerPlaybook`) -- contrairement a `KardiocoreGalvanus`, qui en a une.

## CORPS MOVE -- relu LIGNE A LIGNE (build `rnca9r7q6c`)

`IdunBattle.AI.Playbook.Loki.IntoxicatingElixirPlaybook.
u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

    dsl    = <DSL du playbook>
    config = <AbilityConfiguration, champ +0x58 -> +0x20>
    tile   = IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile(case)  // TUILE CANDIDATE
    sel    = IdunBattleLogic.Entities.DSLSelectors$$Get(tile)                     // selecteur sur ELLE
    f      = IdunBattle.Entities.Effects.Loki.IntoxicatingElixir_ExtraCritDmgEffect$$GetLevelFormula(
                 dsl, config, sel)
    n      = f.Calculate(<AbilityEntities du case, +0x10>)
    w      = <delegue getUtilityVal>( "IntoxicatingElixir_LikesSuppressionStunTauntThrilled" )
    yield Fix64.op_Implicit(w * n)

⚠ **CE PLAYBOOK APPELLE LITTERALEMENT LA FORMULE DE L'EFFET DE COMBAT** -- meme `$$GetLevelFormula`,
meme corps natif, seule l'ANCRE change (`Get(<tuile candidate>)` ici, `Tiles(Owner)` dans
`$$GetCalculateLevel`). Le port partage donc son ARBRE avec la classe d'effet
(`entities/effects/loki/intoxicating_elixir.py`) et n'en re-derive AUCUN etage : plafond `Min(...,
nrOfUnits)`, `includeCenter = 1`, absence de filtre d'equipe et bloc des quatre `EffectType` sont
lus UNE fois, la-bas. Un fork ici ferait diverger DECISION et COMBAT sur la meme grandeur.

La cle BC est LUE, pas devinee par prefixe : le `DAT_` du site porte l'index de metadata encode
`kind = 5 = StringLiteral`, et son slot est celui de
`"IntoxicatingElixir_LikesSuppressionStunTauntThrilled"` (`metadata/string_literals.tsv`).
`Utilities.Default.TriggeredAbilities[<cette cle>]` = 5 au seed BC.

## FACE ATTACK -- yield 0, et c'est un CORPS PROPRE, pas une absence

`...IntoxicatingElixirPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` EXISTE
et son corps ENTIER est `yield Fix64.op_Implicit(0)`. Rien a enregistrer cote attack -- l'absence du
registre y vaut 0, meme valeur. On le DIT plutot que de le supposer.

## GEOMETRIE -- disque CUBE, PAS le ring-1 des voisins de registre

`SurroundingUnits` passe par `IdunBattle.Core.Services.TileQuery.
u003CIterateSurroundingTilesu003Ed__6$$MoveNext` : triple boucle en coordonnees CUBE, **AUCUNE liste
stockee et AUCUNE porte d'elevation** (#515). C'est `battle_query.is_surrounding` /
`count_surrounding`, et surtout PAS `is_adjacent` (qui, lui, porte les deux etages). Confondre les
deux ferait tomber des unites que le natif compte, sur 86,8 % des boards.

`includeCenter = 1` : l'unite DEBOUT SUR la tuile candidate compte. Pendant un sweep de mouvement la
tuile candidate est libre, donc ce terme est generalement muet -- il est ecrit parce que c'est ce
que le natif fait.

## SELF -- le mover compte pour lui-meme, et c'est ce qui a impose une cle NEUVE

Le corps n'ecrit AUCUN `RemoveAll(u.Id == case.Unit.Id)` : le mover est encore SUR SON ORIGINE
pendant tout le sweep, donc il entre dans son propre voisinage des que cette origine est a <= 2 hex
de la tuile candidate (meme fait que N13 pour `friends_in_range`). Ici le filtre porte sur les
EFFETS, d'ou la cle `self_effects` ajoutee aux TROIS constructeurs de `leaf_ctx`
(`engine/utilities/tile.py`). Ce n'est pas un cas exotique : les quatre porteurs sont Emperor's
Children, et `ThrillSeekers` (`Thrilled`) se pose sur eux a leur PROPRE attaque.

## AUCUN FILTRE D'EQUIPE -- amis ET ennemis

`SurroundingUnits` n'est ni `SurroundingFriends` ni `SurroundingEnemies` : le port lit donc
`friend_units` **et** `enemy_units`. C'est la difference la plus facile a rater en recopiant un
voisin de registre, ou tous comptent des AMIS.

## BORNE DU SUBSTRAT, NOMMEE

Cote DECISION les effets viennent de `decisionView.effects`, canal **ACTIF-ONLY** (#100), la ou le
selecteur natif `EntitiesWithAnyEffect` ne filtre PAS sur l'activite (`onlyActive` non resolu,
case-229). Les quatre effets comptes ici (`Pinned`, `Stunned`, `Taunted_OnlySpecificTargets`,
`ThrillSeekers`) sont des debuffs a DUREE, actifs tant qu'ils vivent -- l'ecart est donc borne aux
instances desactivees, qu'aucun de ces quatre types ne produit aujourd'hui. Cote RUNNER
(`runner_tile_leaf_ctx` / `scene_tile_leaf_ctx`) le substrat est l'`EffectsState` filtre sur
`consumed` SEUL, qui colle exactement au `onlyActive: 0` natif.

ASCII only.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.effects.loki.intoxicating_elixir import DEBUFFS, _CONST_NR_OF_UNITS, _CONST_RANGE, _const
from ..entities.triggered_ability_type import TriggeredAbilityType

#: Les NOMS des quatre `EffectType` du bloc lu dans `global-metadata.dat`. Cote DECISION comme cote
#: RUNNER, le `leaf_ctx` porte des NOMS d'effet (`decisionView.effects[].name` / `EffectsState`),
#: pas des ordinaux -- on derive donc les noms du MEME tuple d'enum que la classe d'effet, sans
#: recopier aucune chaine (un nom recopie se perimerait en silence au prochain build).
DEBUFF_NAMES = frozenset(e.name for e in DEBUFFS)


class IntoxicatingElixirPlaybook:
    """`w x min(|unites DEBUFFEES a <= range hex de la tuile candidate, centre INCLUS|, nrOfUnits)`.

    `w` = `Utilities.Default.TriggeredAbilities["IntoxicatingElixir_LikesSuppressionStunTauntThrilled"]`
    (= 5), `range` = 2 et `nrOfUnits` = 6 sont les `GetNumberConstant` du gameconfig -- aucun des
    trois n'est ecrit en dur."""

    ABILITY_ID = TriggeredAbilityType.IntoxicatingElixir            # 0x5b7 = 1463
    WEIGHT_KEY = "IntoxicatingElixir_LikesSuppressionStunTauntThrilled"

    @staticmethod
    def _is_debuffed(effects) -> bool:
        """`EntityExtensions$$HasOneOfEffects(entity, [Pinned, Stunned, Taunted_OnlySpecificTargets,
        ThrillSeekers], ...)` -- appartenance d'AU MOINS UN nom au bloc lu.

        ⚠ `Taunted` y est le COMPOSITE `Taunted_OnlySpecificTargets` (27) et PAS ses trois
        sous-effets (`Taunted_BlockMovement` 25, `Taunted_CantUseAbility` 26,
        `Taunted_RefreshUnitTurnFinished` 1237), que `TauntedEffect$$ApplyInternal` spawne en meme
        temps : les compter tous ferait valoir QUATRE une cible tauntee UNE fois."""
        return any(n in DEBUFF_NAMES for n in (effects or ()))

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        rng = _const(_CONST_RANGE)                    # GetNumberConstant(0x16 = range) = 2
        cap = _const(_CONST_NR_OF_UNITS)              # GetNumberConstant(0x78 = nrOfUnits) = 6
        if rng is None:
            return 0.0                                # constante absente -> le noeud se tait
        n = 0
        # AUCUN filtre d'equipe : `SurroundingUnits`, pas `SurroundingFriends` (cf. l'en-tete).
        for u in list(ctx.get("friend_units") or ()) + list(ctx.get("enemy_units") or ()):
            p = u.get("pos")
            if p and self._is_debuffed(u.get("effects")) \
                    and bq.is_surrounding(tile, p, int(rng), True):
                n += 1
        # SELF : le corps natif n'exclut pas `case.Unit`, encore sur son ORIGINE pendant le sweep.
        sp = ctx.get("self_pos")
        if sp and self._is_debuffed(ctx.get("self_effects")) \
                and bq.is_surrounding(tile, tuple(sp), int(rng), True):
            n += 1
        if cap is not None:
            n = min(n, int(cap))                      # Min(Count(...), Get(nrOfUnits))
        return float(int(w) * n)
