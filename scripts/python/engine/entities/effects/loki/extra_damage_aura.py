"""Effets `Effects.Loki` — famille BONUS DE DEGAT ATTAQUANT, volet **AURA** : l'effet-entite vit sur le
PORTEUR (la SOURCE) et se PROJETTE sur d'autres unites via son `CreateTargetSelector` natif. Scinde de
`extra_damage.py` (volet DIRECT : l'effet buffe l'attaque de son propre porteur).

Discriminant natif = la presence d'un `CreateTargetSelector` a cote du `CreateEffectDamageBonusForAttack`
/ `CreateDamageModifier` : le behaviour pose l'effet sur le source (`AddEffect(owner)`), le selecteur
designe qui en beneficie (allies ring-N, ennemis a distance exacte, fork sur trait/faction). Cote port
cela se traduit par un hook primaire distinct — `create_aura_attack_bonus`,
`create_aura_attack_damage_bonus_for_ally`, `create_aura_defense_damage_malus_for_ally` — evalue PAR
CANDIDAT (l'adjacence/portee est recalculee contre la position d'attaque evaluee, pas la position reelle).

Chaque classe override UNIQUEMENT ce qu'elle implemente dans le natif (lu en ghidra). Les magnitudes non
encore confirmees par nom gameconfig renvoient None (pas de contribution) = on N'INVENTE PAS de valeur non
prouvee (cf. doc §17.4 « present != applique »). Cf. `loki/__init__.py`.

⚠ UNE exception au critere « bonus de degat » : le KIT `PsychicStalk` est tenu GROUPE ici, ses TROIS
effets ensemble (`1215` %-list defenseur, `1435` additif attaquant, `1216` sans aucun canal de degat)
-- ils partagent la base `APsychicStalkEffect` et les constantes `PSYCHIC_STALK_ID` /
`FIRE_TILE_EFFECT_NAME`, et les separer par canal aurait disperse le kit natif sur trois modules."""
from __future__ import annotations

from collections.abc import Mapping

from ....dsl.base import Const
from ....services.effect_bonus import EffectBonus, for_addition, for_percent_increase
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentUnits
from ...unit_selection_type import UnitSelectionType
from ...damage_profile_type import DamageProfileType, PROFILE_NAME_BY_INDEX
from ...effect_type import EffectType
from ...rarity import Rarity
from ..base import (BaseEffect, is_ranged_attack as _is_ranged_attack,
                    target_is_on_fire_tile as _target_is_on_fire_tile)
from ..magnitude import ability_const_str, ability_var
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1).
# `pathfinding.board` n'importe RIEN de `engine`, et `engine.battle_query` n'importe que `hexgeo` +
# `.hex_corner` : aucune de ces deux aretes ne peut refermer le SCC `effects`.
from ...pathfinding import board as _board
from .... import battle_query as _bq


def _adjacency_channels(ctx):
    """Les DEUX canaux de l'adjacence NATIVE derives du `board` DEJA porte par le ctx d'aura, en
    TRI-ETAT (#943-r7). Aucun seeding : `aura_attack_bonus_from_allies` publie deja
    `ctx["board"] = scene.board` (cf. `playbook/prediction/normal_attack.py`).

    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(origin, unique, selType)` =
    `op_Subtraction(Units(AdjacentTiles(origin), ...), origin)`, et
    `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` ENUMERE
    `BattleQuery$$GetAdjacentTiles(t)` pour chaque tuile de l'ORIGINE -- la liste STOCKEE du
    `ConnectivityComponent`, puis la porte `|dElev| < 2` de
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`.

    La face COMBAT de ce meme selecteur (`entities/selectors/units.py::AdjacentUnits` ->
    `dsl/base._within(order='adjacent')`) lit DEJA la liste stockee : c'est la face PREDICTION qui
    divergeait, et la cabler RESORBE l'ecart au lieu d'en creer un.

    Board absent -> `(None, None)`, et `battle_query.is_adjacent` retombe sur son repli geometrique
    NOMME : le comportement d'avant, jamais un voisinage vide."""
    b = (ctx or {}).get("board")
    return _board.elevations_by_pos(b), _board.adjacent_neigh_by_pos(b)


class RitesOfBattleExtraDmgEffect(BaseEffect):
    """`RitesOfBattleExtraDmgEffect` (Effects.Loki) — AURA stat-mod +dégât de Calgar (2 EffectTypes
    permanents sur le porteur : Basic `...ExtraDmgBasic` 1002 / Imperial `...ExtraDmgImperial` 1003).
    `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfBattleAbility$$CreateBehaviour` → 2 `DynamicStatModifierEffect` sur le SOURCE ;
    `CreateTargetSelector` = `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits(1)` (source EXCLUE) → `IdunBattleLogic.Entities.DSLFactory$$Friends` →
    `With/WithoutTrait(0x1a=26)` (26 = grande-alliance Imperial, `idun.Idun.Source.Shared.GrandAlliance$$GetTrait`).
    Montant `GetDynamicStatModificationAmount` = `GetVariableForLevel(idx8→extraDmg | idx9→extraDmg_2,
    niveau SOURCE)` × multiplier SOURCE (les 2 vars dans `variablesAffectedByRarityBonus`) ; ajouté à la
    **modification** du stat **Attack**. RE-validé : `extraDmg_2[L50]×1.8 = 1298` (Imperial, u92 adjacent
    à Calgar) ; `extraDmg[L50]×1.8 = 898` (basic).

    ⚠ Modélisée UNIQUEMENT côté SOURCE via `create_aura_attack_bonus` (l'effet-entité vit sur le PORTEUR,
    pas sur le buffé → PAS de `get_stat_modification_*` target-side : le porteur ne se self-buff pas,
    AdjacentUnits l'exclut). La sélection Basic/Imperial + le montant sont ré-évalués PAR CANDIDAT."""

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> int | None:
        """AURA `RitesOfBattleAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfBattleAbility$$CreateBehaviour (2 effets permanents sur Calgar : Basic 1002 / Imperial
        1003) : +extraDmg/_2 au DÉGÂT DE BASE des ALLIÉS ring-1 du porteur, gate grande-alliance Imperial.
        `IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits(1)` (source EXCLUE) → `IdunBattleLogic.Entities.DSLFactory$$Friends` (même équipe) →
        `With/WithoutTrait(0x1a=26)`. Montant = `GetVariableForLevel(var, niveau SOURCE) × multiplier SOURCE`
        (RE-validé : `extraDmg_2[L50]×1.8 = 1298`, `extraDmg[L50]×1.8 = 898`). Modélisé CÔTÉ SOURCE
        (l'effet-entité vit sur Calgar, pas sur le buffé) et ré-évalué PAR CANDIDAT (adjacence à `att_pos`)."""
        c = ctx or {}
        if c.get("owner_id") == c.get("att_id"):
            return None                                  # AdjacentUnits exclut la source (op_Subtraction self)
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                  # Friends = même équipe que le porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        # #943-r7 : `AdjacentUnits(Owner)` -> `AdjacentTiles(Owner)` -> la liste STOCKEE. La SOURCE
        # de l'enumeration est le PORTEUR (Calgar) ; une couronne hex nue est symetrique et
        # sur-atteint la liste stockee (mesure #943-r4 : 22 aretes sur `MC2_60`, 8 sur `C4_69`).
        elev_by_pos, neigh_by_pos = _adjacency_channels(c)
        if not _bq.is_adjacent(op, ap, elev_by_pos, neigh_by_pos):
            return None
        # Gate trait 0x1a=26 = grande-alliance Imperial (idun.Idun.Source.Shared.GrandAlliance$$GetTrait : Imperial→26).
        # ABSENT de gameconfig.traits → dérivé de GrandAllianceId. Les 2 effets sont MUTUELLEMENT EXCLUSIFS
        # ("instead") : Basic→WithoutTrait(26) (non-Imperial), Imperial→WithTrait(26).
        target_imperial = (c.get("att_grand_alliance") == "Imperial")
        effect_imperial = bool(self.name and self.name.endswith("Imperial"))
        if effect_imperial != target_imperial:
            return None
        var = "extraDmg_2" if effect_imperial else "extraDmg"
        return ability_var("RitesOfBattle", var, c.get("owner_level"),
                           multiplier_pct=c.get("owner_mult") or 100)


class PathOfCommandExtraDmgEffect(BaseEffect):
    """`PathOfCommandExtraDmgEffect` (Effects.Triggered.Loki) — AURA stat-mod +Attack de Loki
    (`PathOfCommand_ExtraDmg` 1112). `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour` pose 2 effets
    DynamicStatModifier sur le SOURCE (Loki) : ExtraDmg (0x458=1112) + ExtraCrit (0x453=1107).
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandExtraDmgEffect$$CreateTargetSelector` = `SurroundingFriends(owner, range=GetNumberConstant(0x16)=2)` =
    `SurroundingTiles(range) - Tiles(self)` → `Friends` → alliés (même équipe) à distance hex <=2, SOURCE
    EXCLUE (comme RitesOfBattle mais range 2 au lieu de 1).

    Montant `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandExtraDmgEffect$$GetDynamicStatModificationAmount` = `If(IsSameFaction(owner, target), v8+v9, v8)`
    avec `v8 = GetVariableForLevel(8=extraDmg, niveau SOURCE)`, `v9 = (9=extraDmg_2, niveau SOURCE)` (mêmes
    enum-keys 8/9 = extraDmg/extraDmg_2 que RitesOfBattle) × multiplier SOURCE (les 2 dans
    `variablesAffectedByRarityBonus`). `IsSameFaction` = **même FACTION** (FactionId, ex. Aeldari), PAS la
    grande-alliance : `IsSameFaction` s'appuie sur `IdunBattle.Entities.UnitExtensions$$HasFaction` (compare le champ
    FactionId string). CONFIRMÉ RE + LIVE (discriminateur : allié Aeldari adjacent = extraDmg+extraDmg_2=+699 ;
    allié Ork = Xenos MAIS pas Aeldari = extraDmg SEUL=+400). → allié même faction → extraDmg+extraDmg_2 ; autre
    faction (même Xenos) → extraDmg seul. (⚠ DIFFÉRENT de RitesOfBattle dont le gate extraDmg_2 = grande-alliance
    Imperial via trait 26.) Ajouté à la **modification** du stat **Attack**.

    ⚠ Modélisée CÔTÉ SOURCE via `create_aura_attack_bonus` (l'effet-entité vit sur Loki, pas sur le buffé) et
    ré-évaluée PAR CANDIDAT (distance <=2 à `att_pos`). PAS de `get_stat_modification_*` target-side (Loki ne
    se self-buff pas : SurroundingFriends l'exclut). L'axe CRIT (ExtraCrit 1107 = extraCritChance) = effet
    SÉPARÉ non porté ici (nécessite un canal aura-crit dédié — TODO)."""

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> int | None:
        c = ctx or {}
        if c.get("owner_id") == c.get("att_id"):
            return None                                  # SurroundingFriends exclut la source (- Tiles(self))
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                  # Friends = même équipe que le porteur (Loki)
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("PathOfCommand", "range", is_constant=True) or 2   # GetNumberConstant(0x16)=range=2
        if hexgeo.distance(op, ap) > rng:                # SurroundingFriends(range) — portée hex du porteur
            return None
        lvl, mult = c.get("owner_level"), (c.get("owner_mult") or 100)
        base = ability_var("PathOfCommand", "extraDmg", lvl, multiplier_pct=mult) or 0
        # If(IsSameFaction(owner, target), extraDmg + extraDmg_2, extraDmg) — IsSameFaction = même FACTION
        # (FactionId, cf. IdunBattle.Entities.UnitExtensions$$HasFaction), PAS grande-alliance. Confirmé live (Ork Xenos = extraDmg seul).
        ofac, afac = c.get("owner_faction"), c.get("att_faction")
        if ofac is not None and ofac == afac:
            base += ability_var("PathOfCommand", "extraDmg_2", lvl, multiplier_pct=mult) or 0
        return base or None


class DaughterOfTheAbyssExtraDamagePctEffect(BaseEffect):
    """`DaughterOfTheAbyss_ExtraDamagePctEffect` (effet 0x589=1417) — les Psykers ENNEMIS dans le rayon
    du porteur REÇOIVENT +extraDmgPct% de dégât (i2 : « Enemy Psykers within 2 hexes receive +20%
    Damage »). Même mécanique state-wide que le jumeau Friendly, polarité inverse :
    - dégât `IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack (bonus sur l'attaque CONTRE la cible de l'effet) ;
    - cibles `IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateTargetSelector : `SurroundingEnemies(owner, ConfigConst 0x16=range) &
      UnitsWithTrait(0x3ea=Psyker)`.
    Porté sur le canal aura-défense (le dégât REÇU par la cible augmente) — gate trait CIBLE Psyker via
    `tgt_traits` (gameconfig). MAGNITUDE : `extraDmgPct[ablvl]` (15→20, hors rarityBonus)."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("owner_team") is None or c.get("owner_team") == c.get("tgt_team"):
            return None                                       # SurroundingEnemies : cible ENNEMIE du porteur
        if "Psyker" not in (c.get("tgt_traits") or ()):        # UnitsWithTrait(0x3ea=1002 Psyker)
            return None
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo
        rng = ability_var("DaughterOfTheAbyss", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, tp) > int(rng if rng else 2):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var("DaughterOfTheAbyss", "extraDmgPct", level=lvl)
        if not pct:
            return None
        return for_percent_increase(True, abs(int(pct)))

    # #437-r1-r1-r1 : `DaughterOfTheAbyss_ExtraDamagePctEffect` implemente
    # `CreateEffectDamageBonusForAttack` (methods.tsv), pas le slot DEFENSE -- le natif verse donc
    # sa contribution dans `attackModifiers`, alors que le port l'evalue par le canal AURA-DEFENSE
    # (le seul qui balaie les porteurs TIERS). Le nom natif le disait deja ; c'est la face qui en
    # etait deduite a tort. CONSEQUENCE ARITHMETIQUE REELLE : canal POURCENT.
    # ⚠ Son JUMEAU `DaughterOfTheAbyss_FriendlyDmgReductionPct` implemente bien
    # `CreateEffectDamageMalusForDefense` -> il reste, LUI, cote defenseur. Les deux volets de la
    # MEME ability ne sont PAS sur la meme face : c'est exactement ce qu'une regle « deduite du
    # porteur » ne peut pas exprimer (meme porteur, faces opposees).
    AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"


class BeaconOfRageFriendlyExtraDamageEffect(BaseEffect):
    """`BeaconOfRage_FriendlyExtraDamageEffect` (EffectType 0x513=1299, nom capté
    "BeaconOfRage_FriendlyExtraDamage") — variante AURA de BeaconOfRage (le SELF 0x512=1298 =
    `BeaconOfRageExtraDamageEffect`). i2 : « 50% of the extra damage from Beacon of Rage is added to the
    damage of melee attacks of adjacent friendly Chaos units. » #191.

    L'effet vit sur le PORTEUR (Azkor) : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetUpdateFriendEffectBehaviour` fait
    `AddEffect(0x513, owner@0x148)` + `SetEffectLevel(owner, 0x513, ...)` SUR AZKOR (jamais sur les amis)
    → capté dans decisionView.effects d'AZKOR, PAS de l'ami. Il se PROJETTE sur ses amis Chaos adjacents
    (canal AURA côté SOURCE, comme AstartesBanner / DaughterOfTheAbyss).

    - dégât `IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateEffectDamageBonusForAttack` : `ForAddition(get_OwnerIsCaster &
      IsMeleeAttack, PercentageOf(Multiply(ConfigVar(8=extraDmg, GetAbilityState), EffectLevel(effet)),
      0x32=50, mode 0))` = FLAT additif = **50 % du bonus SELF** (`extraDmg[ablvl Azkor] × rage`), arrondi
      half-to-even. Trigger : l'AMI attaque (OwnerIsCaster projeté) en MÊLÉE (même canal additif
      `DamageModifiers.Add` que le self BeaconOfRage / SmashaEad).
    - cible `IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateTargetSelector` : `UnitsWithTrait(AdjacentFriends(owner@0x148, 1, 3),
      0x7ea=2026=Chaos, 3)` = amis d'Azkor ring-1 (hex-adjacents) de grande-alliance Chaos.
    - niveau/présence `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetCurrentFriendEffectLevel` = `If(UnitsDefeatedAmount(Azkor)>0,
      GetCurrentSelfEffectLevel, 0)` : l'effet n'est AJOUTÉ sur Azkor (behaviour IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetUpdateFriendEffectBehaviour :
      `If(UnitsDefeatedAmount>0 & !HasEffect(0x513), AddEffect)`) QUE si Azkor a ≥1 kill, avec pour level
      la même RAGE que le self (`Min(TotalTimesAttacked, 8)`). ⇒ la PRÉSENCE de l'effet dans la capture
      encode DÉJÀ le gate ≥1-kill + la rage → on lit `self.level` tel quel (comme le self, PAS de recalcul
      offline de UnitsDefeatedAmount).

    Gate grande-alliance Chaos (trait 2026) = ABSENT de gameconfig.traits → dérivé de GrandAllianceId
    (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait` : Imperial→26, Xenos→0x3ee, Chaos→0x7ea=2026), comme le gate
    Imperial de RitesOfBattle. Magnitude `extraDmg` = ability_var BeaconOfRage indexée sur l'ablvl PASSIF
    d'AZKOR (source), pas de l'ami (l'effet-entité porte l'ablvl d'Azkor). Ctx aura = {owner_id/pos/team,
    att_id/att_pos/att_team, att_grand_alliance, is_melee}."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                             # IsMeleeAttack IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateEffectDamageBonusForAttack
            return None
        if c.get("att_id") == c.get("owner_id"):              # AdjacentFriends exclut le porteur (self)
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                       # AdjacentFriends : bénéficiaire = ALLIÉ d'Azkor
        if c.get("att_grand_alliance") != "Chaos":            # UnitsWithTrait(0x7ea=2026=Chaos)
            return None
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        if hexgeo.distance(op, ap) > 1:                       # AdjacentFriends(owner, radius 1) = hex-adjacent
            return None
        if self.level is None or int(self.level) <= 0:        # rage (EffectLevel) — gate >=1-kill baké à l'écriture
            return None
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        per = ability_var("BeaconOfRage", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        from fractions import Fraction
        self_bonus = int(per) * int(self.level)               # Multiply(ConfigVar(extraDmg), EffectLevel)
        friendly = round(Fraction(self_bonus * 50, 100))      # PercentageOf(x, 0x32=50, mode 0 = half-to-even)
        return for_addition(True, friendly) if friendly else None


class LordOfTheHostExtraDamageEffect(BaseEffect):
    """`LordOfTheHost_ExtraDamageEffect` (effet 0x562=1378, nom capté "LordOfTheHost_ExtraDamage",
    passif LordOfTheHost 0x515=1301 de bloodDante) — AURA côté SOURCE : l'effet vit sur DANTE
    (capté chez lui, permanent), il se projette sur ses amis. i2 : « Other friendly units within
    2 hexes with Rapid Assault or Flying deal +extraDmg Damage with melee attacks. » #57c.

    - dégât `IdunBattle.Entities.Effects.Loki.LordOfTheHost_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` : `ForAddition(IsMeleeAttack &
      OwnerIsCaster, ConfigVar(8=extraDmg, GetAbilityState))` = +extraDmg[ablvl Dante]×mult FLAT
      additif PRÉ-perçage PAR COUP (canal `DamageModifiers.additive`, comme SmashaEad/BeaconOfRage).
    - cible `IdunBattle.Entities.Effects.Loki.LordOfTheHost_ExtraDamageEffect$$CreateTargetSelector` : `Unique(UnitsWithTrait(SurroundingFriends(owner,
      ConfigConst(0x16)=range=2), 0x413=RapidAssault) + UnitsWithTrait(idem, 4=Flying))` — amis
      (self exclu) à ≤2 hexes du porteur, porteurs du trait RapidAssault OU Flying.
    - ré-évaluation PAR TUILE CANDIDATE (#57c prouvé, modèle RitesOfBattle #49/#153) : 12345 s18
      u77 bloodSanguinary RÉEL à dist-3 de Dante (AUCUN effet posé sur lui live), le natif ajoute
      quand même le bonus à la candidate (0,4) dist-2.

    VALIDÉ (probe_57c_flathits.py A) : Dante ablvl=50 mult=180 → a = extraDmg[50]×1.8 = 898.2
    pré-perçage par coup, puis ×1.25 RapidAssault, ×4 coups → nat = off + 4488 EXACT min&max
    (7704/12324 vs 3216/7836, armure 1205 traversée pierce 20)."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                             # IsMeleeAttack (IdunBattle.Entities.Effects.Loki.LordOfTheHost_ExtraDamageEffect$$CreateEffectDamageBonusForAttack)
            return None
        if c.get("att_id") == c.get("owner_id"):              # SurroundingFriends : self exclu
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                       # bénéficiaire = AMI du porteur
        traits = c.get("att_traits") or frozenset()
        if "RapidAssault" not in traits and "Flying" not in traits:
            return None                                       # UnitsWithTrait(0x413 RapidAssault | 4 Flying)
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        rng = ability_var("LordOfTheHost", "range", is_constant=True) or 2   # ConfigConst 0x16
        import hexgeo
        if hexgeo.distance(op, ap) > int(rng):
            return None
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var("LordOfTheHost", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class DoomExtraDmgEffect(BaseEffect):
    """`Doom_extraDmgEffect` (effet 0x45a=1114, nom capté "Doom_extraDmg", passif Doom de
    eldarFarseer Eldryon) — AURA côté SOURCE gate CIBLE : les ENNEMIS à EXACTEMENT `range`(=2)
    hexes d'Eldryon prennent +extraDmg des attaques NORMALES des amis d'Eldryon (+extraDmg_2 de
    TOUTES les attaques des amis Aeldari). i2 : « All enemy units exactly 2 hexes away from
    Eldryon take +extraDmg Damage from other friendly unit's normal attacks. Other friendly
    Aeldari units deal +extraDmg_2 Damage with all their attacks to affected units instead. » #57c.

    - dégât `IdunBattle.Entities.Effects.Loki.Doom_extraDmgEffect$$CreateEffectDamageBonusForAttack` : `ForAddition(OwnerIsTarget &
      AreFriends(attaquant, EffectSource) & !AreEqual(attaquant, EffectSource) &
      (HasFaction(attaquant, Aeldari) | IsNormalAttack), ConditionalAmount(HasFaction(att,
      Aeldari), ConfigVar(9=extraDmg_2), ConfigVar(8=extraDmg)))` — FLAT PRÉ-perçage PAR COUP.
    - cible `IdunBattle.Entities.Effects.Loki.Doom_extraDmgEffect$$CreateTargetSelector` : `SurroundingEnemies(owner, ConfigConst(0x16)=
      range) − SurroundingEnemies(owner, range−1)` = ennemis à EXACTEMENT range hexes du porteur.
    - AUCUN effet posé sur la cible doomée (#57c : Shadowsun dist-2 exacte, effectAbilityStates
      vide d'un Doom chez elle) — l'effet vit sur le PORTEUR, le selector est évalué à la demande.

    VALIDÉ (probe_57c_flathits.py B, 54321 s7 u79 genesPatriarch→t95 tauShadowsun dist-2
    d'Eldryon ablvl=50 mult=180) : a = extraDmg[50]×1.8 = 898.2 pré-perçage par coup ×5 coups,
    l'armure 1806 mange la part bloquée → nat 5060/6470 = off + 2240 EXACT min&max."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        tp, op = c.get("t_pos"), c.get("owner_pos")
        if not tp or not op:
            return None
        if c.get("tgt_team") is None or c.get("tgt_team") == c.get("owner_team"):
            return None                                       # SurroundingEnemies : cible ENNEMIE du porteur
        if c.get("att_id") == c.get("owner_id"):              # !AreEqual(attaquant, EffectSource)
            return None
        if c.get("owner_team") != c.get("att_team"):          # AreFriends(attaquant, EffectSource)
            return None
        rng = int(ability_var("Doom", "range", is_constant=True) or 2)   # ConfigConst 0x16
        import hexgeo
        if hexgeo.distance(op, tp) != rng:                    # EXACTEMENT range (soustraction ring r-1)
            return None
        is_aeldari = (c.get("att_faction") == "Aeldari")      # HasFaction(attaquant, Aeldari)
        if not is_aeldari and c.get("is_normal_attack") is False:
            return None                                       # branche non-Aeldari gated IsNormalAttack
        if self.ability_level is None:
            return None
        var = "extraDmg_2" if is_aeldari else "extraDmg"      # ConditionalAmount(Aeldari -> 9, sinon 8)
        amt = ability_var("Doom", var, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class _SpotterReworkedAuraBase(BaseEffect):
    """Base commune des deux effets-aura du passif SpotterReworked 0x5df=1503 (astraOrdnance Thaddeus) —
    AURA côté SOURCE : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpotterReworkedAbility$$CreateBehaviour` pose les DEUX effets sur le
    PORTEUR (`AddEffect(0x40f=1039) + AddEffect(0x428=1064)`), chacun se projette sur ses amis via son
    TargetSelector. i2 : « Other friendly units within {range} hexes deal +{extraDmg} Damage with ranged
    attacks ; Heavy Weapon units deal +{extraDmg_2} instead. » Le « instead » = sélecteurs mutuellement
    exclusifs sur le trait HeavyWeapon 0x3e9=1001. Sélecteur commun (IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateTargetSelector / IdunBattle.Entities.Effects.Loki.SpotterReworked_HeavyWeaponEffect$$CreateTargetSelector) :
    `SurroundingFriends(owner, ConfigConst(0x16)=range=2, 1, 3) → UnitsWithRangedAttacks → fork trait`
    (self exclu, ami à ≤range hexes).

    ⚠ `IdunBattleLogic.Entities.DSLFactory$$UnitsWithRangedAttacks` N'EST PAS un filtre arme-ranged pur : c'est l'UNION
    (`TargetsSelector.op_Addition`, même sens que LordOfTheHost RapidAssault+Flying) de
    `UnitsWithWeaponsSelector(type 2=ranged)` ET `TilesOnSameElevationSelector(réf=DSLFactory+0x28
    = entité du contexte (porteur), maxDiff=2)` — `IdunBattle.Entities.TileExtensions$$GetElevationDifference` =
    abs(élév_a − élév_b), garde si ≤ 2. Un ami SANS arme ranged est donc INCLUS dès que sa tuile
    (candidate en prédiction) est à ≤2 d'élévation de la tuile du porteur — MESURÉ live (probe_66 :
    Baraqiel darkaTerminator melee-only reçoit +extraDmg_2, +~399/coup). Sur les boards à faible
    amplitude d'élévation (MC1_67 : 3–4) le nœud est un pass-through. Board absent du ctx →
    retombe sur le terme arme seul (conservateur). #66."""

    _VAR = ""                 # ConfigVar(8)=extraDmg | ConfigVar(9)=extraDmg_2
    _WANT_HEAVY = False       # UnitsWithoutTrait(1001) | UnitsWithTrait(1001)

    def _trigger_ok(self, c: Mapping) -> bool:
        raise NotImplementedError

    @staticmethod
    def _in_ranged_attacks_selector(c: Mapping) -> bool:
        """`IdunBattleLogic.Entities.DSLFactory$$UnitsWithRangedAttacks` : arme ranged au kit OU |Δélévation| ≤ 2 vs porteur."""
        if c.get("att_has_ranged_weapon"):
            return True
        b, op, ap = c.get("board"), c.get("owner_pos"), c.get("att_pos")
        if b is None or not op or not ap:
            return False
        to, ta = b.tile_at(op[0], op[1]), b.tile_at(ap[0], ap[1])
        if to is None or ta is None:
            return False
        return abs(int(ta.get("elevation") or 0) - int(to.get("elevation") or 0)) <= 2

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not self._trigger_ok(c):
            return None
        if c.get("att_id") == c.get("owner_id"):              # SurroundingFriends : self exclu
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                       # bénéficiaire = AMI du porteur
        if not self._in_ranged_attacks_selector(c):           # UnitsWithRangedAttacks (union, cf. classe)
            return None
        traits = c.get("att_traits") or frozenset()
        if ("HeavyWeapon" in traits) != self._WANT_HEAVY:     # UnitsWith[out]Trait(0x3e9=1001)
            return None
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        rng = ability_var("SpotterReworked", "range", is_constant=True) or 2   # ConfigConst 0x16
        import hexgeo
        if hexgeo.distance(op, ap) > int(rng):
            return None
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var("SpotterReworked", self._VAR, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class SpotterReworkedExtraDamageEffect(_SpotterReworkedAuraBase):
    """`SpotterReworked_ExtraDamageEffect` (effet 0x40f=1039) — amis SANS HeavyWeapon.
    - dégât `IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` : `ForAddition(OwnerIsActor & IsRangedAttack,
      ConfigVar(8=extraDmg, GetAbilityState), source 0x5df)` = +extraDmg[ablvl Thaddeus]×mult FLAT
      additif PRÉ-perçage PAR COUP (canal `DamageModifiers.additive`, comme LordOfTheHost).
    - cible `IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateTargetSelector` : `UnitsWithoutTrait(UnitsWithRangedAttacks(
      SurroundingFriends(owner, range=2)), 0x3e9=HeavyWeapon)`."""

    _VAR = "extraDmg"
    _WANT_HEAVY = False

    def _trigger_ok(self, c: Mapping) -> bool:
        return c.get("is_melee") is False                     # IsRangedAttack (IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateEffectDamageBonusForAttack)


class SpotterReworkedHeavyWeaponEffect(_SpotterReworkedAuraBase):
    """`SpotterReworked_HeavyWeaponEffect` (effet 0x428=1064) — amis AVEC HeavyWeapon, « instead ».
    - dégât `IdunBattle.Entities.Effects.Loki.SpotterReworked_HeavyWeaponEffect$$CreateEffectDamageBonusForAttack` : `ForAddition(OwnerIsActor,
      ConfigVar(9=extraDmg_2, GetAbilityState), source 0x5df)` — trigger SANS IsRangedAttack (fidèle
      au décompilé : un porteur HeavyWeapon à arme ranged garde le bonus même sur un coup MÊLÉE).
    - cible `IdunBattle.Entities.Effects.Loki.SpotterReworked_HeavyWeaponEffect$$CreateTargetSelector` : `UnitsWithTrait(UnitsWithRangedAttacks(
      SurroundingFriends(owner, range=2)), 0x3e9=HeavyWeapon)`."""

    _VAR = "extraDmg_2"
    _WANT_HEAVY = True

    def _trigger_ok(self, c: Mapping) -> bool:
        return True                                           # OwnerIsActor seul (IdunBattle.Entities.Effects.Loki.SpotterReworked_HeavyWeaponEffect$$CreateEffectDamageBonusForAttack)


class DefenderOfTheGreaterGoodExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier` (tauShadowsun passif
    DefenderOfTheGreaterGood, TriggeredAbilityType 1155 ; EffectType 0x49e=1182 "DefenderOfTheGreaterGood_
    ExtraDmg"). AURA cote SOURCE (template SpotterReworked/LordOfTheHost). i2 : « Friendly units adjacent
    to Shadowsun or her Command-Link Drone deal +364 Damage with ranged attacks, except attacks that deal
    Psychic Damage. ... Friendly T'au Empire units within 2 hexes ... are also affected. »

    POSE (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$CreateBehaviour`, RE decompile) :
    `If(HasTrait(owner, Summon=2), AddEffect(0x51a=1306)+AddEffect(0x51b=1307),
        AddEffect(0x49e=1182)+AddEffect(0x49f=1183))` = branche NON-Summon (Shadowsun) pose 1182 (CET
    effet ExtraDmg) + 1183 (ExtraHits, coup additionnel PROBABILISTE = [fable], NON porte) ; branche Summon
    (Command-Link Drone) pose les JUMEAUX drone 1306/1307. L'effet vit sur le PORTEUR et se projette sur ses
    amis via son TargetSelector (AURA source-side, MEME canal que SpotterReworked/LordOfTheHost/Doom).

    - degat `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier` (RE decompile) : `EffectBonus.ForAddition(get_OwnerIsCaster &
      IsRangedAttack & !DamageProfileIs(0xd=13=Psychic), ConfigVar(8=extraDmg, GetAbilityState, EffectSource
      @0x60))`, source AbilityOrEffect 0x483=1155 (DefenderOfTheGreaterGood, pour l'attribution -- non porte,
      cf. SpotterReworked). DEUX differences
      vs SpotterReworked_ExtraDamage (IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateEffectDamageBonusForAttack) : (1) `get_OwnerIsCaster` (vs OwnerIsActor -- meme semantique :
      ce chemin n'est appele que pour l'attaque du BENEFICIAIRE) ; (2) noeud `!DamageProfileIs(Psychic)` en plus
      (SpotterReworked forkait sur HeavyWeapon a la place).
      ⚠ `ForAddition` est INLINE dans ce corps (aucun `call`) : on le lit a la DISPOSITION des champs --
      `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` ecrit son montant a `+0x10`,
      `IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease` a `+0x08` ; ici le corps ecrit le
      trigger a `+0x00`, `0` a `+0x08`, le montant a `+0x10`. C'est donc bien le canal ADDITIF
      (`DamageModifiers.additive`), PAR COUP -- et APRES l'etage percage/armure, pas avant :
      `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` appelle
      `...$$GetBaseDamageWithFixedPiercedArmor` D'ABORD, puis le %-list, puis l'additif (#420-r1 ;
      les docstrings voisines qui disent « pre-percage » sont a corriger, cf. backlog).
    - cible `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector` (RE decompile) :
      `UnitsWithRangedWeaponsExcludingDamageProfile( Unique( (AdjacentFriends(owner, ownerTiles, unique=1) - {owner})
        + UnitsFromFaction(SurroundingFriends(owner, ownerTiles, range=2, unique=1, selectionType=3), UnitFaction.Tau=9, 3) ), 0xd=Psychic )`
      = amis SOIT ADJACENTS (TOUTE faction) SOIT T'au a distance <= 2, ayant une arme RANGED non-Psychic.
      ⚠ LES LITTERAUX NE SONT PAS TOUS DES RAYONS (piege #419) : `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(this, unit, unitTile, unique)`
      n'a AUCUN parametre de rayon -- le `1` du call-site est `unique` ; l'adjacence vient d'`AdjacentTiles`.
      `IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(this, unit, unitTile, range, unique, unitSelectionType)`
      en a un, et le call-site y passe bien `range = 2`.
      Selecteur d'aura partage x4 (StructuralAnalyser/SereneUnifier/DotGG/WayOfTheShortBlade, cf. case-220
      §6.6). Le filtre `UnitsWithRangedWeaponsExcludingDamageProfile(Psychic)` monte un
      `IdunBattle.Entities.Selectors.UnitsWithWeaponsSelector` a `minRange = 2` + `excludedDamageProfile = Psychic`
      (`...$$HasMatchingWeapon` exige qu'UNE MEME arme satisfasse les deux) = eligibilite CARRIER,
      SUBSUMEE par le gate d'attaque `is_ranged & damage_profile != Psychic` pour toute attaque d'ARME.
      RESIDU NOMME : une attaque « ranged » d'une unite SANS arme de portee >= 2 serait accordee par le
      port et refusee par le natif -- non confronte (#420-r1).
    - MAGNITUDE = `ability_var("DefenderOfTheGreaterGood", "extraDmg", ablvl) x multiplier` (ConfigVar var
      index 8 = extraDmg, SEULE var d'ability, DANS variablesAffectedByRarityBonus -> scale x mult ;
      extraDmg[L1..65]=[5..364] ; i2 « +364 » = extraDmg[L65]). `GetVariableForLevel(config, 8, GetAbilityState)`
      sur le config de DefenderOfTheGreaterGood (le PASSIF de Shadowsun) -> level = niveau passif du PORTEUR
      (self.ability_level, comme SpotterReworked/LordOfTheHost). Multiplier = le GLOBAL du porteur
      (self.ability_variables_multiplier).
    - GATE : is_ranged (IsRangedAttack) ; damage_profile != Psychic (!DamageProfileIs(0xd)) ; distance
      (adjacent toute faction, OU T'au distance <= 2). Ne modelise PAS 1183 ExtraHits (porte a part, #372).
      ⚠ LES DEUX GATES N'ONT PAS LA MEME POLARITE SUR LA CLE ABSENTE, et ca ne se devine pas :
        * `is_melee` est TRI-ETAT (calque SpotterReworked `_trigger_ok`) -- seul `False` OUVRE ; `True`
          FERME, et `None`/cle absente FERME AUSSI (le port ne devine pas la nature du coup).
          Corollaire de mesure (#422) : RETIRER cette cle FERME le gate au lieu de l'ouvrir -- pour
          l'eprouver il faut FORCER `is_melee`, jamais le supprimer ;
        * `damage_profile` absent laisse le gate de PROFIL OUVERT (le natif compare a `13` ; un contexte
          sans profil vaut `DamageProfileType.None_ = -1`, hors egalite).

    VALIDATION (#420-r1, cliquet `tests/engine/runner/test_dotgg_extra_dmg_live.py`) : le PSYCHIC-exclusion
    exige `damage_profile` dans le ctx aura-ally (threade par normal_attack/abilities/psyker/fury cote
    prediction ; par damage.py cote combat) et `att_faction` (FactionId) pour le tier T'au distance <= 2.
    Confronte LIVE des DEUX cotes de la bascule sur MC1_67 (ablvl 50 x mult 180 -> extraDmg = 499) :
    `darkaHellblaster` adjacent, coup non-Psychic -> live = offline, +624/coup vs le meme rejeu sans
    l'effet ; `ultraTigurius` adjacent, coup RANGED Psychic (`DamageProfileType = 13` lu au tag natif)
    -> live = offline = rejeu-sans-effet, delta 0. Vue ROUGE du gate retire : live=[2984] offline=[3483]."""

    _TAU_FACTION = "Tau"           # UnitFaction.Tau=9 (UnitsFromFaction(9) IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector) ; FactionId gameconfig="Tau"
    # #372 -- UNE SEULE classe native pour 1182 ET 1306 : `..._ExtraDmgEffect$$.ctor(this, isDrone)`
    # ecrit `isDrone` a `this+0x480` apres `DamageModifierAbilityEffect(0x483 = 1155, 0)`.
    _IS_DRONE = False
    _SOURCE_EFFECT_TYPE = EffectType.DefenderOfTheGreaterGood_ExtraDmg     # 0x49e -- l'effet NON-drone vise par `EntitiesIsNotTargetOfEffect`

    def aura_selector_covers(self, ctx: Mapping | None = None) -> bool:
        """Tronc commun de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector`
        (SANS la branche `isDrone`) -- extrait en methode parce que la branche DRONE
        (`EntitiesIsNotTargetOfEffect`) doit l'evaluer sur un AUTRE porteur (#372)."""
        c = ctx or {}
        if c.get("att_id") == c.get("owner_id"):              # AdjacentFriends/SurroundingFriends excluent self
            return False
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return False                                      # Friends = meme equipe que le porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return False
        import hexgeo
        d = hexgeo.distance(op, ap)
        # Selecteur IdunBattleLogic.Entities.Abilities.Triggered.Loki.DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector : (AdjacentFriends(range=1, TOUTE faction) - owner) + UnitsFromFaction(
        # SurroundingFriends(range=2, disk), Tau=9). range 1 / range 2 = litteraux DSL (pas de ConfigVar range).
        adjacent = (d == 1)
        tau_ring = (d <= 2 and c.get("att_faction") == self._TAU_FACTION)
        return bool(adjacent or tau_ring)

    def _covered_by_source_aura(self, c: Mapping) -> bool:
        """`EntitiesIsNotTargetOfEffect(sel, <effectType non-drone>)` -- branche `isDrone` du selecteur
        (#372) : le DRONE n'accorde rien a une unite deja CIBLE de l'effet de Shadowsun."""
        for p in (c.get("aura_peers") or []):
            for e in (p[-1] or []):
                if getattr(e, "effect_type", None) != self._SOURCE_EFFECT_TYPE:
                    continue
                if e.aura_selector_covers({**c, "owner_id": p[0], "owner_pos": p[1],
                                           "owner_team": p[2]}):
                    return True
        return False

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("is_melee") is not False:                    # IsRangedAttack (IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier) : ranged only
            return None                                       # TRI-ETAT : None (nature non declaree) FERME
        if (c.get("damage_profile") or None) == "Psychic":    # !DamageProfileIs(0xd=13=Psychic)
            return None                                       # profil ABSENT -> gate OUVERT (compare a 13)
        if not self.aura_selector_covers(c):
            return None
        if self._IS_DRONE and self._covered_by_source_aura(c):
            return None                                       # EntitiesIsNotTargetOfEffect
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var("DefenderOfTheGreaterGood", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class DefenderOfTheGreaterGoodExtraDmgDroneEffect(DefenderOfTheGreaterGoodExtraDmgEffect):
    """Jumeau DRONE (effet 0x51a=1306, porte par `tauSmnDroneCommandLink`, le summon d'
    `ExemplarOfTheKauyon`). MEME classe native, `isDrone = 1` a `this+0x480` (le ctor est litteralement
    le meme corps) -- donc MEME magnitude et MEME selecteur, a une difference pres : la branche
    `EntitiesIsNotTargetOfEffect(sel, 0x49e)` qui exclut les unites deja couvertes par l'aura de
    Shadowsun (anti-double-comptage natif). RE : `docs/rl/case-372-dotgg-extra-hits.md`."""

    _IS_DRONE = True


# --- PsychicStalk (passif de `thousAhriman` << Ahriman >>, TriggeredAbilityType 1179) -------------
# Nom de l'ability tel que gameconfig l'indexe (`GC.ability("PsychicStalk")`) : le natif lit sa
# config par le champ `effet+0x60` (`AbilityConfiguration`), et son NIVEAU par
# `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`.
PSYCHIC_STALK_ID = "PsychicStalk"
# `IdunBattleLogic.Entities.DSLSelectors$$EntitiesWithAnyEffect(Tiles(<sel>), effectTypes = Fire, 6)`
# -- l'entree `effectTypes` du call-site est le SCALAIRE `5`, que la surcharge 4-arguments emballe
# elle-meme dans un `int[1]` (le `6` est `effectTarget`, PAS un second type). Le canal offline des
# effets de tuile ne transporte que des NOMS (`tileMeta.tiles[].effects[].name` ->
# `Scene.tile_effects_by_pos` / `damage_model.tile_status_effects_by_pos`), d'ou la lecture par nom
# -- meme convention que `TILE_STATUS_EFFECT_NAMES` (services/static_battle_rules.py).
FIRE_TILE_EFFECT_NAME = EffectType.Fire.name                      # EffectType 5 = "Fire"


class APsychicStalkEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.APsychicStalkEffect` -- BASE ABSTRAITE des deux effets de
    degat de `PsychicStalk`, portee ici parce que le natif y met les DEUX conditions PARTAGEES que
    `1215` et `1435` intersectent chacun dans son propre canal :

      * `APsychicStalkEffect$$GetTargetIsOnFireTileCondition`
      * `APsychicStalkEffect$$GetAttackHasValidDamageProfileCondition`

    Le ctor natif (`APsychicStalkEffect$$.ctor(abilityOrEffect)`) prend son `AbilityOrEffect` en
    PARAMETRE -- aucune sous-classe n'a de `.ctor` propre dans les tables (corps mutualise), c'est la
    fabrique d'`EffectsDatabase` qui le passe. Cote port l'`AbilityState` arrive deja resolue par la
    capture (`ability_level` / `ability_variables_multiplier`), donc rien a modeliser ici.

    Cette classe n'est PAS inscrite au registre (elle est abstraite cote natif aussi)."""

    def target_is_on_fire_tile(self, ctx: Mapping | None = None) -> bool:
        """`APsychicStalkEffect$$GetTargetIsOnFireTileCondition` (MIRROR 1:1) :

            AmountIsEqualOrGreater(
                EntitiesWithAnyEffect( Tiles(Target@0x60), Fire = 5, effectTarget = 6 ),
                <DSLFormulas+0x20 = Direct(1)> )

        = « au moins UNE des tuiles de la cible porte l'effet `Fire` ». `Tiles` =
        `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` -> la MAIN TILE de la cible, donc UNE
        tuile (`t_pos`), pas l'empreinte complete. La surcharge d'arrivee est bien celle a
        3 arguments d'`AmountIsEqualOrGreater` (`this, selector, minAmount`), resolue par l'adresse
        du `call` -- pas par le nom.

        Contexte : `t_pos` (position de la cible) + `tile_effects_by_pos` (`{(col,row): [noms]}`,
        le canal deja monte pour `LetTheGalaxyBurnEffect`). Canal ABSENT -> False : le natif ne
        devine pas non plus, et « present != applique ».

        DELEGUE au foyer `effects/base.py::target_is_on_fire_tile` depuis #1005 : `VitarusEffect`
        pose la MEME question par un autre noeud (`Any(Tiles(Target), HasEffect(<element>, Fire,
        onlyActive: false, EffectTargetType.Both))`), et une TROISIEME ecriture aurait fait un
        fork."""
        return _target_is_on_fire_tile(ctx)

    def attack_has_valid_damage_profile(self, ctx: Mapping | None = None) -> bool:
        """`APsychicStalkEffect$$GetAttackHasValidDamageProfileCondition` (MIRROR 1:1) :

            DamageProfileIs( new[] { AbilityConfiguration.GetAffectedDamageProfile()  ?? 3  (Flame),
                                     AbilityConfiguration.GetAffectedDamageProfile2() ?? 0xd (Psychic) } )

        Les deux valeurs sont lues sur la config d'ability (`effet+0x60`), avec un
        `Nullable<DamageProfileType>.GetValueOrDefault(<defaut>)`. Pour `PsychicStalk` la config
        FOURNIT les deux (`affectedDamageProfile = "Flame"`, `affectedDamageProfile_2 = "Psychic"`)
        -- elles coincident avec les defauts, mais on lit la CONFIG, pas les defauts.

        `damage_profile` = NOM du profil du coup. Absent -> False (le natif compare a la liste ; un
        contexte sans profil vaut `DamageProfileType.None_ = -1`, hors liste)."""
        prof = (ctx or {}).get("damage_profile")
        if not prof:
            return False
        return prof in self._affected_damage_profiles()

    @staticmethod
    def _affected_damage_profiles() -> frozenset:
        """Les deux profils de la config, en NOMS. `GetValueOrDefault` natif : `3` = Flame pour le
        premier accesseur, `0xd` = Psychic pour le second."""
        import gameconfig as _GC                        # import paresseux (cf. `magnitude.py`)
        consts = (_GC.ability(PSYCHIC_STALK_ID) or {}).get("constants") or {}
        return frozenset({
            consts.get("affectedDamageProfile")
            or PROFILE_NAME_BY_INDEX[int(DamageProfileType.Flame)],
            consts.get("affectedDamageProfile_2")
            or PROFILE_NAME_BY_INDEX[int(DamageProfileType.Psychic)],
        })


class PsychicStalkExtraAttackDamageEffect(APsychicStalkEffect):
    """`IdunBattle.Entities.Effects.Loki.PsychicStalk_ExtraAttackDamageEffect` (EffectType 0x4bf=1215)
    -- owner-effect PERMANENT de `thousAhriman` << Ahriman >> : les attaques Flame/Psychic contre un
    ENNEMI d'Ahriman qui se tient sur un hex EN FEU font **+extraDmgPct %** de degat.
    i2 : « Attacks that deal Flame Damage and Psychic Damage to enemies that are on hexes with Fire
    deal +33% Damage. » (#366-r1)

    ## Canal : `CreateEffectDamageMalusForDefense`, mais l'operation est `ForPercentIncrease`
    `IdunBattle.Entities.Effects.Loki.PsychicStalk_ExtraAttackDamageEffect$$CreateEffectDamageMalusForDefense` :

        EffectBonus.ForPercentIncrease(
              ( IsUnit(Caster@0x48) | IsMachine(Caster@0x48) | CasterIsCasterTile )
            & AreEnemies(Target@0x60, Owner@0x30)
            & GetTargetIsOnFireTileCondition()
            & GetAttackHasValidDamageProfileCondition(),
              ConfigVar(0xa = extraDmgPct, GetAbilityState(effet), config@+0x60) )

    Le NOM de la methode dit « Malus...ForDefense » (c'est le slot d'interface : le canal DEFENSEUR),
    la FABRIQUE dit `ForPercentIncrease` -- le degat RECU par la cible AUGMENTE. C'est donc le meme
    canal que `1110 FireAndReposition_ReduceDmg` (#366-r1) mais **PAS** le meme slot : celui-la
    appelait `ForSubtraction` -> `flat_reductions` ; celui-ci alimente le **%-list** du defenseur,
    exactement comme `DaughterOfTheAbyss_ExtraDamagePct` (+extraDmgPct % aux Psykers ennemis).

    ## L'effet vit sur AHRIMAN, pas sur la cible -> canal AURA state-wide
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour` =
    `AddEffect(0x4bf=1215, ..., targets = Owner@0x30) + AddEffect(0x4c0=1216, ...) +
    AddEffect(0x59b=1435, ...)` : les TROIS effets du kit sont poses sur le PORTEUR. Le natif les
    attrape par l'enumeration GLOBALE de
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` (elle
    itere la liste des effets ACTIFS de l'etat, pas ceux du seul defenseur) -- d'ou le hook
    `create_aura_defense_damage_malus_for_ally` (agregateur `aura_defense_damage_malus_from_units`),
    et NON `create_effect_damage_malus_for_defense` (qui ne balaie que les effets de la CIBLE).

    ⚠ AUCUN `CreateTargetSelector` sur cette classe (contrairement a `DaughterOfTheAbyss` ou
    `1216 PsychicStalk_VisualEffect`, qui en ont un) : c'est le TRIGGER qui porte toute la selection.

    ## Ce que le trigger ne gate PAS : l'ATTAQUANT
    `AreEnemies` porte sur `Target` vs `Owner`, jamais sur le caster -- **n'importe qui** peut
    beneficier du +%, y compris un ennemi d'Ahriman qui tire sur un autre ennemi d'Ahriman. Le seul
    terme sur le caster est le OU `IsUnit | IsMachine | CasterIsCasterTile`, vrai pour tout
    attaquant reel. C'est conforme a l'i2, qui ne nomme aucun sujet (« Attacks that deal ... »).
    C'est aussi ce qui SEPARE proprement `1215` de son voisin `1435
    PsychicStalk_FriendlyChaosExtraDamage`, dont le trigger EXIGE `AreFriends(Owner, Caster) &
    HasTrait(Caster, 0x7ea = Chaos)` : un attaquant non-Chaos (ou non-allie d'Ahriman) fait taire
    `1435` et laisse `1215` seul -- c'est la garde d'ATTRIBUTION du montage de validation.

    ## MAGNITUDE
    `ConfigVar(0xa = extraDmgPct)` sur la config `PsychicStalk`, indexee par le niveau de l'ability
    source (`GetAbilityState`). `extraDmgPct` = 25 -> 33 sur 65 niveaux, **HORS**
    `variablesAffectedByRarityBonus` -> le multiplier de rarete ne s'y applique pas (il est passe
    quand meme : c'est `ability_var` qui applique la regle config-driven, pas l'appelant).
    `ability_level` absent (`GetAbilityState` sans etat) -> AUCUNE contribution.

    Les deux autres effets du kit sont portes juste en dessous : `1435
    PsychicStalk_FriendlyChaosExtraDamage` (canal ATTAQUANT additif) et `1216
    PsychicStalk_VisualEffect` (AUCUN canal de degat -- sortie 100 % presentation, cf. sa classe).
    La POSE du feu (`PsychicStalk_ApplyFireTileAbility$$CreateBehaviour` =
    `AddEffect(Fire = 5, targets = TargetTiles@0x78)`, trigger `OnNormalAttackOrSmite & OwnerIsCaster
    & IsRangedAttack`) n'est pas portee non plus -- l'etat offline la recoit par le seed des effets
    de tuile (`snapshot._load_tile_effects`)."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # `IsUnit(Caster@0x48) | IsMachine(Caster@0x48) | CasterIsCasterTile` -- cote port les MoW
        # portent AUSSI un `UnitComponent` (cf. `snapshot._load_machines`), donc `att_is_unit`
        # couvre les deux premiers termes ; `CasterIsCasterTile` (= `AreEqual(Caster@0x48,
        # CasterTile@0x50)`, un attaquant qui EST une entite-tuile) n'a pas de substrat offline ->
        # cle absente. Aucune des trois threadee -> gate FERME (degradation restrictive NOMMEE :
        # le canal de degat du port passe toujours son `attacker_id`).
        if not (c.get("att_is_unit") or c.get("att_is_machine")
                or c.get("caster_is_caster_tile")):
            return None
        # `AreEnemies(Target@0x60, Owner@0x30)` -- la CIBLE du coup est ennemie du PORTEUR.
        if c.get("owner_team") is None or c.get("tgt_team") is None \
                or c.get("owner_team") == c.get("tgt_team"):
            return None
        if not self.target_is_on_fire_tile(c):            # GetTargetIsOnFireTileCondition
            return None
        if not self.attack_has_valid_damage_profile(c):   # GetAttackHasValidDamageProfileCondition
            return None
        if self.ability_level is None:                    # ConfigVar sans AbilityState -> rien
            return None
        pct = ability_var(PSYCHIC_STALK_ID, "extraDmgPct", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_percent_increase(True, int(pct)) if pct else None


class PsychicStalkFriendlyChaosExtraDamageEffect(APsychicStalkEffect):
    """`IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect`
    (EffectType 0x59b = 1435) -- le TROISIEME effet du kit `PsychicStalk` (passif 1179 de
    `thousAhriman` << Ahriman >>), pose comme les deux autres SUR LE PORTEUR par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour`
    (`AddEffect(0x4bf) + AddEffect(0x4c0) + AddEffect(0x59b, targets = Owner@0x30)`).
    i2 : « Affected attacks from friendly Chaos units deal an additional +extraDmg Damage. »

    ## Canal : ADDITIF ATTAQUANT (`ForAddition`), PAS le %-list defenseur de `1215`
    `IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect$$CreateEffectDamageBonusForAttack`
    (mirror 1:1, lu au decompile) :

        EffectBonus.ForAddition(
              AreFriends(Owner@0x30, Caster@0x48, comparisonType = 0, anyEntity = false)
            & HasTrait(Caster@0x48, 0x7ea = 2026 = Chaos)
            & GetTargetIsOnFireTileCondition()
            & GetAttackHasValidDamageProfileCondition(),
              ConfigVar(8 = extraDmg, GetAbilityState(effet), config@+0x60) )

    C'est une entree de `IdunBattle.Core.Services.DamageModifiers$$Add` DIFFERENTE de celle de
    `1215` : `ForAddition` -> `additive` (pre-percage, par coup), la ou `1215` faisait
    `ForPercentIncrease` -> `pct_list` DEFENSEUR. Les deux se COMPOSENT : l'additif traverse le
    percage puis est scale UNE fois par le %-list -- c'est exactement l'ecart mesure par la
    contre-epreuve de `1215` (664 = round(extraDmg[L50] x 1.8 x 1.33)).

    ## Enumeration : STATE-WIDE, self INCLUS
    Le slot d'interface `0x16` (`CreateEffectDamageBonusForAttack`) est invoque par
    `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` sur la
    liste GLOBALE des entites porteuses d'effets actifs (une `List<KVP<entite, List<effet>>>`
    passee en argument, double boucle `GetEnumerator`/`MoveNext`) -- exactement la forme
    symetrique de `CalculateDefenderModifiersForPrediction` (cf. case-68). Il n'y a AUCUNE
    exclusion du porteur : `AreFriends(Owner, Caster)` fait tout le filtrage, et
    `IdunBattle.Entities.UnitExtensions$$IsFriend` compare deux `GetCurrentPlayer(...).index`
    SANS ecarter l'egalite -> `IsFriend(x, x)` est VRAI. Ahriman beneficie donc de son propre
    effet quand il attaque.

    Cote port l'enumeration native se scinde en DEUX foyers DISJOINTS (meme decoupage que
    `DestroyTheWitch_ExtraDamage`, dont le selecteur natif est `SurroundingFriends(Owner) +
    Owner`) : `create_effect_damage_bonus_for_attack` sert le PORTEUR-attaquant, et
    `create_aura_attack_damage_bonus_for_ally` (agregateur `aura_attack_damage_bonus_from_allies`,
    qui EXCLUT `att_id == owner_id` et ne retient que la MEME equipe) sert ses allies -- donc
    ni trou ni double-compte.

    ## AUCUN gate sur la CIBLE
    Contrairement a `1215` (`AreEnemies(Target@0x60, Owner@0x30)`), le trigger de `1435` ne porte
    RIEN sur la cible du coup : seule sa TUILE est lue (`GetTargetIsOnFireTileCondition`). Un tir
    fratricide sur un allie place sur un hex en feu declencherait donc l'additif. Le quirk est
    porte tel quel (le decompile fait foi) ; l'i2 (« Affected attacks... ») suggere l'heritage du
    « to enemies » de la phrase precedente, mais aucun noeud ne l'implemente.

    ## MAGNITUDE
    `ConfigVar(8 = extraDmg)` sur la config `PsychicStalk`, indexee par `GetAbilityState(effet)`.
    ⚠ `extraDmg` EST dans `variablesAffectedByRarityBonus` (`['maxDmg', 'extraDmg']`) -- a la
    difference de l'`extraDmgPct` de `1215` : la valeur est donc SCALEE par le multiplier de
    rarete du porteur (`extraDmg[L50] = 277`, x180 % = 499). `ability_level` absent
    (`GetAbilityState` sans etat capte) -> AUCUNE contribution (« present != applique »)."""

    # `HasTrait(Caster@0x48, 0x7ea = 2026)` -- trait de GRANDE-ALLIANCE, ABSENT de
    # `gameconfig.traits` : il est derive du `GrandAllianceId` par
    # `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` (Imperial -> 26, Xenos -> 0x3ee,
    # Chaos -> 0x7ea). MEME convention que le gate Chaos de `BeaconOfRage_FriendlyExtraDamage`
    # et le gate Imperial de `RitesOfBattle`.
    _CHAOS_GRAND_ALLIANCE = "Chaos"

    def _bonus_if_common_gates_pass(self, c: Mapping) -> EffectBonus | None:
        """Les TROIS conjoints du trigger qui ne dependent PAS de la relation porteur/attaquant,
        + la magnitude. Partage mot pour mot par les deux pattes (le natif, lui, n'a qu'un seul
        corps : la scission port self/aura est un artefact de l'enumeration cote port).

        Cle absente = contexte NON THREADE -> gate FERME (degradation RESTRICTIVE nommee, jamais
        un booleen devine) : c'est le regime des appelants qui ne passent pas encore la cible."""
        if c.get("att_grand_alliance") != self._CHAOS_GRAND_ALLIANCE:
            return None                                   # HasTrait(Caster@0x48, 0x7ea = Chaos)
        if not self.target_is_on_fire_tile(c):            # GetTargetIsOnFireTileCondition
            return None
        if not self.attack_has_valid_damage_profile(c):   # GetAttackHasValidDamageProfileCondition
            return None
        if self.ability_level is None:                    # ConfigVar sans AbilityState -> rien
            return None
        amt = ability_var(PSYCHIC_STALK_ID, "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """PATTE SELF : le PORTEUR de l'effet (Ahriman) est LUI-MEME l'attaquant. Ce foyer n'est
        appele que sur les effets de l'attaquant (`_attacker_effect_bonuses`), donc
        `AreFriends(Owner@0x30, Caster@0x48)` s'y evalue en `IsFriend(x, x)` = VRAI (lu au
        decompile : `UnitExtensions$$IsFriend` compare deux `GetCurrentPlayer(...).index`, sans
        exclusion de l'egalite). Les trois autres conjoints sont lus dans `att_ctx`, avec les
        MEMES CLES que le ctx du canal AURA -- pas de fork."""
        return self._bonus_if_common_gates_pass(att_ctx or {})

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """PATTE AURA : un ALLIE Chaos du porteur attaque. `AreFriends(Owner@0x30, Caster@0x48)` =
        `IsFriend` sur le `CurrentPlayer` des deux entites -> comparaison d'EQUIPE cote port
        (`comparisonType = 0` du call-site = branche CurrentPlayer de `UnitExtensions$$IsFriend`,
        pas OriginalPlayer). L'agregateur a deja exclu `att_id == owner_id` (patte SELF)."""
        c = ctx or {}
        if c.get("owner_team") is None or c.get("att_team") is None \
                or c.get("owner_team") != c.get("att_team"):
            return None                                   # AreFriends(Owner@0x30, Caster@0x48)
        return self._bonus_if_common_gates_pass(c)


class PsychicStalkVisualEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.PsychicStalk_VisualEffectEffect` (EffectType 0x4c0 = 1216)
    -- le TROISIEME effet du kit `PsychicStalk`, pose comme les deux autres SUR LE PORTEUR par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour`
    (`AddEffect(0x4bf) + AddEffect(0x4c0, <AbilityStateReference>, targets = Owner@0x30) +
    AddEffect(0x59b)`).

    ## Sa sortie est 100 % PRESENTATION -- etabli par LECTURE, pas par absence d'observable
    La classe native surcharge EXACTEMENT QUATRE methodes, et **aucune n'est un slot de sortie
    gameplay** (ni `CreateEffectDamage*`, ni `CreateDamageModifier`, ni `GetStatModification*`, ni
    `ApplyModification`, ni `CreateTrigger`, ni `CreateAdditionalHits`, ni `GetArmorPenetration`) :

      * `PsychicStalk_VisualEffectEffect$$.ctor`
      * `PsychicStalk_VisualEffectEffect$$CreateActiveCondition`   (portee ci-dessous)
      * `PsychicStalk_VisualEffectEffect$$CreateTargetSelector`    (portee ci-dessous)
      * `PsychicStalk_VisualEffectEffect$$GetRefreshTriggers`      (NON portable, cf. RESIDU)

    Les DEUX consommateurs sont nommes, et tous deux sont de la PRESENTATION :

      1. **VFX + SFX** -- `IdunBattle.View.AbilityConfigs.Loki.PsychicStalkEffectVisual.u003CReceiveEffectInternalu003Ed__2$$MoveNext`
         = `AbilityVisualsUtils.InstantiateEffects$$InstantiateEffectAt` puis
         `AbilityVisualsUtils.SoundEffects$$PlaySfx`. Namespace `IdunBattle.View`.
      2. **ICONE DE STATUT** -- `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$.cctor`
         inscrit `0x4c0` dans le dictionnaire `<statics>+0x10` (EffectType -> categorie d'affichage)
         avec la valeur **2**. Les accesseurs qui lisent CE dictionnaire donnent la lecture exacte :
         `IsUnitEffectShownAsGenericDebuff` teste `== 2` (VRAI), `IsUnitEffectShownAsGenericBuff`
         `== 1`, `HasUniqueIcon` `== 3`, `IsInvisible` `== 5` (donc `1216` n'est PAS invisible :
         il s'affiche, en DEBUFF generique).

    ⚠ L'absence d'un consommateur GAMEPLAY n'est PAS deduite de l'index de recherche de ghidra --
    cet index s'est montre NON EXHAUSTIF (une recherche litterale de `0x4c0` ne ramene meme pas le
    `CreateBehaviour` qui le contient pourtant). Elle est deduite de la STRUCTURE : la classe
    n'expose aucun slot de sortie, et le seul balayage exhaustif qu'on peut faire -- la lecture
    INTEGRALE du `.cctor` de `StaticBattleRules.Effect` -- ne trouve `0x4c0` qu'une seule fois, dans
    le dictionnaire d'AFFICHAGE. Il n'est notamment PAS dans le `HashSet` `<statics>+8` que lit
    `StaticBattleRules.Effect$$ShouldRefreshDuringSimulation`, ce qui a une consequence FORTE et
    directement lisible dans `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` :

        if (state.<IsSimulation>) { if (!ShouldRefreshDuringSimulation(ec.EffectType)) return; }

    -> pendant une SIMULATION (toute la face DECISION), le natif ne rafraichit JAMAIS `1216` : ni sa
    condition d'activite, ni ses cibles. La face DECISION est donc structurellement hors de portee de
    cet effet.

    ## POURQUOI l'inscrire quand meme au registre
    Meme raison que `WireweaveNet_CounterAttack` : NOMMER la classe native au lieu de router sur
    `BaseEffect`, et porter la seule chose qui soit une LECTURE du natif plutot qu'un defaut --
    sa `CreateActiveCondition`. Sans elle, `BaseEffect.is_active` rend `True` INCONDITIONNELLEMENT,
    ce qui est une VALEUR PAR DEFAUT et non une lecture (cf. le bloc de commentaire de
    `runner/operations/refresh_effects.py`)."""

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`PsychicStalk_VisualEffectEffect$$CreateActiveCondition` (MIRROR 1:1) :

            op_LogicalNot( DSLTriggers.IsDead( Owner@DSLSelectors+0x30 ) )

        `IdunBattleLogic.Entities.DSLTriggers$$IsDead` est litteralement
        `op_LogicalNot(DSLTriggers.IsAlive(unit))`, et `IsAliveAbilityTrigger$$ShouldTrigger` appelle
        `IdunBattle.Entities.UnitExtensions$$IsAlive` -> `HealthComponent$$IsAlive` = `hp >= 1`.
        Le double `NOT` se simplifie donc en **`IsAlive(Owner)`**, et le port en a deja le mirror
        exact : `runner/components.py::unit_is_alive` (`hp >= 1`, `hp` inconnu -> vivant).

        `Owner` = le PORTEUR de l'effet (Ahriman), pas sa cible : `RefreshEffectsOperation$$RefreshEffect`
        resout `owner = state.GetEntity(EffectComponent.OwnerId @+0x14)` puis ecrit CET owner dans
        l'`AbilityEntities` (slots `+0x08` et `+0x18`) avant d'appeler `ShouldBeActive`. Le
        `unit_state` que le port passe a `is_active` est justement celui de l'unite qui PORTE
        l'effet -- meme entite, aucune conversion.

        Cle `hp` absente (pas de `HealthComponent`) -> VRAI, comme `unit_is_alive` : on ne gate
        jamais sur un etat de PV non capte."""
        hp = (unit_state or {}).get("hp")
        if hp is None:
            return True
        return int(hp) >= 1

    def target_selector_covers(self, ctx: Mapping | None = None) -> bool:
        """`PsychicStalk_VisualEffectEffect$$CreateTargetSelector` (MIRROR 1:1), evalue PAR CANDIDAT :

            Units( EntitiesWithAnyEffect( Tiles( Enemies( of = Owner@DSLSelectors+0x30,
                                                          entities = AllUnits@DSLSelectors+0x20,
                                                          onlyAlive = 1 ) ),
                                          effectTypes = Fire = 5, effectTarget = 6 ),
                   unique = 1, selectionType = 3 )

        = « les unites ENNEMIES VIVANTES du porteur dont la MAIN TILE porte l'effet `Fire` ».

        Les deux surcharges ambigues sont tranchees par l'ADRESSE du `call`, pas par le nom :
        `Enemies(this, of, entities, onlyAlive)` (qui reexpedie sur `selectionType = onlyAlive + 2 = 3`)
        et `Units(this, entities, unique, selectionType)`. `Tiles` =
        `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` -> la MAIN TILE, pas l'empreinte --
        MEME noeud que `APsychicStalkEffect$$GetTargetIsOnFireTileCondition`, d'ou la lecture par
        `t_pos` seule. Le `6` est `effectTarget`, PAS un second `EffectType` (la surcharge a
        4 arguments emballe elle-meme le scalaire `5` dans un `int[1]`).

        ⚠ **AUCUN CONSOMMATEUR COTE PORT, ET C'EST VOULU.** Cote natif le resultat de ce selecteur
        part dans `RefreshEffectsOperation$$UpdateEffectTargets` -> `AddTargetsToEffect` ->
        `IdunBattle.Entities.Components.EffectComponent$$AddTargetId` : la relation vit sur
        l'ENTITE-EFFET (le champ que lit `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffectOfType`,
        `EffectComponent+0x48`), PAS dans l'`EffectsOwnedComponent.ActiveEffectIds` de la cible --
        or c'est ce dernier, et lui seul, que publie le canal `decisionView`
        (`frida/hooks/game/effects.ts::readEffectsByUnit`). La sortie MATERIALISEE de ce selecteur
        est donc HORS DE PORTEE des capteurs existants ; le mirror est confronte sur ses ENTREES
        (positions + effets de tuile de l'etat live), pas sur sa sortie native. Point d'ancrage a
        hooker pour lever le residu : la liste de cibles de l'`EffectComponent`
        (`AddTargetsToEffect` / `EffectComponent$$AddTargetId`).

        Cle absente = contexte NON THREADE -> FAUX (degradation RESTRICTIVE nommee)."""
        c = ctx or {}
        if c.get("owner_team") is None or c.get("tgt_team") is None \
                or c.get("owner_team") == c.get("tgt_team"):
            return False                                  # Enemies(of = Owner@0x30)
        if c.get("tgt_alive") is False:                   # onlyAlive = 1 -> selectionType 3
            return False
        # EntitiesWithAnyEffect(Tiles(...), Fire = 5, effectTarget = 6) -- MEME noeud, MEME canal
        # offline (noms de `tileMeta.tiles[].effects[]`) que `GetTargetIsOnFireTileCondition`,
        # donc MEME foyer (`effects/base.py::target_is_on_fire_tile`, #1005).
        return _target_is_on_fire_tile(ctx)


# =====================================================================================================
# AURAS DE MACHINE OF WAR -- les deux `ExtraDamagePct` MYTHIQUES debloques par le canal de rarete
# (#999-r3-r1 pour `att_rarity`/`tgt_rarity`, #999-r3-r1-r1 pour l'univers de porteurs board-wide).
#
# Les DEUX effets sont poses a l'init sur leur MoW porteuse par le patron
# `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` (`ABILITY_INIT_OWNER_EFFECTS`, cf.
# `factory.py`), et les DEUX implementent le slot NATIF `$$CreateEffectDamageBonusForAttack` --
# mais sur des canaux de port OPPOSES, parce que leurs `$$CreateTargetSelector` projettent sur des
# populations opposees :
#   * `BlightedLandEffect` (1442) projette sur les AMIS de la MoW -> le beneficiaire est
#     l'ATTAQUANT -> canal `create_aura_attack_damage_bonus_for_ally` ;
#   * `MoreGitzOverEre_ExtraDamagePctEffect` (1449) projette sur les ENNEMIS de la MoW -> le
#     beneficiaire est la CIBLE DU COUP -> canal `create_aura_defense_damage_malus_for_ally`, la
#     boucle state-wide `EffectWithTarget` (MEME arbitrage que
#     `DaughterOfTheAbyssExtraDamagePctEffect` ci-dessus, `AURA_DEFENSE_MALUS_NATIVE_FACE`).
# =====================================================================================================

#: `TriggeredAbilityType` 0x5a7 = 1447 -- l'ability MYTHIQUE de la MoW `deathCrawler` /
#: `deathNpcMoWCrawler`. C'est la config que `ConfigVar` de l'effet 1442 indexe (l'appariement
#: ability -> effet est LU : `BlightedLandAbility$$GetEffectType` = `return 0x5a2` = 1442).
BLIGHTED_LAND_ABILITY = "BlightedLand"
#: `TriggeredAbilityType` 0x5b0 = 1456 -- l'ability MYTHIQUE de la MoW `orksRukkatrukk` /
#: `orksNpcMoWRukkatrukk` (`MoreGitzOverEreAbility$$GetEffectType` = `return 0x5a9` = 1449).
MORE_GITZ_OVER_ERE_ABILITY = "MoreGitzOverEre"
#: `TriggeredAbilityType` 0x5ac = 1452 -- l'ability MYTHIQUE de la MoW `astraOrdnanceBattery` /
#: `astraNpcMoWOrdnanceBattery` (`OnMyPositionAbility$$GetEffectType` = `return 0x5a4` = 1444).
ON_MY_POSITION_ABILITY = "OnMyPosition"
#: `AbilityVariableType` 0xa -- la variable que les DEUX `ConfigVar(0xa, ...)` lisent. Elle est dans
#: `variablesAffectedByRarityBonus` pour les deux abilities -> le multiplicateur du PORTEUR MORD.
_VAR_EXTRA_DMG_PCT = "extraDmgPct"
#: `AbilityConstantType 0` -- `constants.unitId` de `MoreGitzOverEre` (= `"orksSmnSquig"`). Le natif
#: le passe a `VisualUnitIdFromUnitId` AVANT `UnitsWithVisualId` (contraste `HeadwoppasKillchoppa`,
#: dont la constante est DEJA un visualId), d'ou la traduction par le gameconfig ci-dessous.
_CONST_UNIT_ID = "unitId"
#: `EffectType` 0x4dc = 1244 -- l'effet de TUILE teste par `UnitsOnTilesWithEffect` (1442).
CONTAMINATED_TILE_EFFECT_NAME = EffectType.Contaminated.name
#: `Direct(2)` -- le `minAmount` d'`AmountIsEqualOrGreater` de la 2e branche du selecteur de 1449.
MIN_ADJACENT_MYTHIC_FRIENDS = 2
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de
#: `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` (#357). MEME cle et MEME semantique que
#: `NornCrownEffect` / `HeadwoppasKillchoppaEffect` : foyer UNIQUE
#: `runner/operations/triggers/base.py::triggered_ability_state`.
CTX_ABILITY_STATE_OF = "tertiary_ability_state_of"
#: PROFILS des unites ADJACENTES a la CIBLE du coup -- `(uid, team, visual_id, rarity)` par unite,
#: substrat des DEUX branches du `$$CreateTargetSelector` de 1449. Tri-etat : `None` = NON MESURE
#: (pas de position / pas de plateau) -> le gate se FERME, jamais un tuple vide invente.
CTX_TGT_ADJACENT_UNIT_PROFILES = "tgt_adjacent_unit_profiles"


def _mow_ability_state(effect, ctx, owner_id, ability_name):
    """`GetAbilityState(effet)` -- le couple `(niveau, multiplicateur)` sous lequel l'ability
    MYTHIQUE est montee sur la MoW PORTEUSE.

    Une mythique de MoW arrive par le champ TERTIAIRE (`BC.Units[].TertiaryAbility`, montage
    `rl_duel build --equip-mythic`), donc par le MEME canal qu'une relique : le foyer est
    `triggered_ability_state`, expose au ctx sous `tertiary_ability_state_of`. Lire
    `self.ability_level` rendrait le niveau des PASSIFS du porteur (50 sur tout runner normalise),
    donc `extraDmgPct[4] = 20` au lieu du palier reellement equipe -- la faute de #357 / #1011.

    Canal ABSENT (contexte offline / probe / face PREDICTION, qui ne le threade pas) -> repli NOMME
    sur les niveaux que l'instance porte deja. Il est JUSTE quand l'effet vient du seed offline
    (`spawn.py::_seed_ability_owner_effects` passe le couple TERTIAIRE pour l'ability tertiaire), et
    il clampe au dernier palier sinon : c'est une degradation DECLAREE, pas un choix."""
    c = ctx or {}
    fn = c.get(CTX_ABILITY_STATE_OF)
    lvl = mult = None
    if fn is not None and owner_id is not None:
        lvl, mult = fn(owner_id, ability_name)
    if lvl is None:
        lvl = effect.ability_level if effect.ability_level is not None else effect.level
        mult = effect.ability_variables_multiplier
    return lvl, int(mult if mult is not None else 100)


class BlightedLandEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.BlightedLandEffect` (`EffectType` 0x5a2 = 1442) -- owner-effect
    PERMANENT de l'ability MYTHIQUE `BlightedLand` (`TriggeredAbilityType` 0x5a7 = 1447) de la MoW
    `deathCrawler` / `deathNpcMoWCrawler`. Tache #1035-r2.

    i2 `Abilities/BlightedLand_CurrentLevelDescription` : << Friendly **Mythic** characters deal
    +{extraDmgPct}% Damage while on a **Contaminated** hex. >>

    QUI EN BENEFICIE -- `...BlightedLandEffect$$CreateTargetSelector`, LU au decompile ::

        UnitsOnTilesWithEffect(
            UnitsWithRarity(
                Friends( Owner@<DSLSelectors+0x30>, AllUnits@<DSLSelectors+0x20>,
                         3 = UnitSelectionType.OnlyAliveAndTargetable ),
                5 = idun.meta.Rarity.Mythic, 3 ),
            0x4dc = EffectType.Contaminated )

    ⚠ **AUCUN etage ne lit la POSITION du PORTEUR** -- ni `AdjacentUnits`, ni `SurroundingFriends`,
    ni la moindre distance. `Friends(Owner, AllUnits)` est BOARD-WIDE, `UnitsWithRarity` ne lit que
    `BaseUnitComponent+0x74`, et `UnitsOnTilesWithEffect` lit la tuile de l'ELEMENT COURANT du
    selecteur (donc du BENEFICIAIRE), pas celle du porteur. C'est ce qui rend cette aura evaluable
    depuis une MACHINE OF WAR, qui n'a AUCUNE position : elle n'a rien a taire. (Le canal des auras
    POSITIONNELLES, lui, se tait tout seul sur `owner_pos = None` -- cf. #999-r3-r1-r1.)

    CE QU'ILS GAGNENT -- `...BlightedLandEffect$$CreateEffectDamageBonusForAttack` ::

        EffectBonus.ForPercentIncrease(
            get_OwnerIsCaster,
            ConfigVar( 0xa = extraDmgPct, GetAbilityState(this), <config@this+0x60> ) )

    Le `ForPercentIncrease` est INLINE dans ce corps (pas d'appel a
    `IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease`), et c'est la STRUCTURE ECRITE qui
    l'etablit, champ par champ, contre le corps de la methode nommee : `+0x00 <- trigger`,
    `+0x08 <- formule`, `+0x10..+0x33 <- 0`, `+0x34..+0x4c <- AbilityOrEffect`. Aucun des slots
    additifs n'est ecrit => canal POURCENT, jamais additif.

    CANAL DE PORT : `create_aura_attack_damage_bonus_for_ally`. Le trigger `get_OwnerIsCaster` dit
    que le BENEFICIAIRE (l'`Owner` que la boucle native reecrit a CHAQUE cible du selecteur) doit
    etre le CASTER du coup -- donc l'ATTAQUANT. Les trois etages du selecteur se lisent alors sur
    l'attaquant : `att_team` (Friends), `att_rarity` (UnitsWithRarity), et la tuile `att_pos` dans
    `tile_effects_by_pos` (UnitsOnTilesWithEffect).

    ⚠ `Friends(Owner, AllUnits)` n'EXCLUT PAS le porteur (`UnitExtensions$$IsFriend` n'ecarte pas
    l'egalite), alors que l'agregateur du port exclut `att_id == owner_id`. L'ecart est INATTEIGNABLE
    ici : le porteur est une MoW, elle n'occupe aucune tuile, donc `UnitsOnTilesWithEffect` la
    retranche de toute facon. Ecrit parce que c'est LU, pas parce que ca change un resultat."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # `Friends( Owner@+0x30, AllUnits@+0x20, 3 )` -- meme equipe que le PORTEUR. Aucune
        # distance : l'etage natif n'en lit aucune (cf. docstring).
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None
        # `UnitsWithRarity( ..., 5 = idun.meta.Rarity.Mythic, 3 )` --
        # `UnitsWithRaritySelector$$Select` compare `GetBaseUnitComponent(e)+0x74` au LITTERAL, par
        # EGALITE stricte. TRI-ETAT : `None` = canal non mesure -> gate FERME (jamais `Common` en
        # repli, qui serait PERMISSIF).
        if c.get("att_rarity") != Rarity.Mythic:
            return None
        # `UnitsOnTilesWithEffect( ..., 0x4dc = EffectType.Contaminated )` =
        # `FromTrigger(entities, IsUnitOnTileWithEffect(<element courant>, Contaminated))` : la
        # tuile de l'element courant du selecteur, c.-a-d. celle de l'ATTAQUANT sur ce canal.
        ap, tfx = c.get("att_pos"), c.get("tile_effects_by_pos")
        if ap is None or tfx is None:
            return None
        if CONTAMINATED_TILE_EFFECT_NAME not in set(tfx.get(tuple(ap)) or ()):
            return None
        lvl, mult = _mow_ability_state(self, c, c.get("owner_id"), BLIGHTED_LAND_ABILITY)
        pct = ability_var(BLIGHTED_LAND_ABILITY, _VAR_EXTRA_DMG_PCT, lvl, multiplier_pct=mult)
        return for_percent_increase(True, int(pct)) if pct else None


def more_gitz_adjacent_units_selector():
    """L'ARBRE DSL du noeud d'ADJACENCE partage par les DEUX branches du `$$CreateTargetSelector`
    de `MoreGitzOverEre_ExtraDamagePctEffect` (doctrine #149 : l'artefact natif est un SELECTEUR,
    donc le port est un arbre) ::

        AdjacentUnits( <origine>, unique: true, UnitSelectionType.OnlyAliveAndTargetable = 3 )

    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits` n'a qu'UNE surcharge --
    `(this, origin, unique, selectionType)` = `op_Subtraction(Units(AdjacentTiles(origin), unique,
    selectionType), origin)` -- donc le `3` du call-site est LU sans ambiguite, et il est le SEUL
    filtre de l'ensemble rendu (pas de wrapper `Enemies`/`Friends` a cet etage : les `Friends` du
    natif viennent APRES, et le port les rejoue sur `owner_team` dans la classe d'effet).

    `Const(1)` est le RAYON cote port -- le ring-1 qu'`AdjacentTiles` produit ; le `unique: true`
    natif est absorbe (les selecteurs du port rendent deja des ensembles). MEME forme que
    `obsessive_annunciation::adjacent_enemies_selector`, dont c'est le voisin sans filtre d'equipe.

    L'ORIGINE est `Owner` : les DEUX branches natives l'instancient sur une entite differente
    (branche A sur les Squigs amis, branche B sur `<element courant>@DSLSelectors+0x68`), mais
    l'adjacence NATIVE est SYMETRIQUE -- liste stockee symetrique, porte `|dElev| < 2` symetrique --
    donc les deux se derivent du MEME voisinage, celui de la CIBLE DU COUP. Les ponts de face
    (`runner/components.py::adjacent_unit_ids`, `playbook/scene.py::Scene.adjacent_unit_ids`)
    donnent a cet arbre son `AbilityEntities` avec `owner = la cible`."""
    return AdjacentUnits(Owner(), Const(1),
                         selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))


def _ability_unit_id_visual_id(ability_name: str) -> "str | None":
    """`VisualUnitIdFromUnitId( Get( ConfigConstString(<config>, 0) ) )` -- le `visualId` de l'unite
    nommee par la constante `unitId` de l'ability. FOYER UNIQUE des DEUX auras mythiques de MoW qui
    portent ce noeud (`MoreGitzOverEre` -> le Squig, `OnMyPosition` -> le Cadian Guardsman) : c'est
    le MEME arbre natif, donc une seule lecture -- un fork y ferait diverger deux mirrors du meme
    noeud.

    Le natif lit `constants.unitId` PUIS le traduit en visualId par
    `IdunBattleLogic.Entities.DSLFormulas$$VisualUnitIdFromUnitId`, avant de le passer a
    `UnitsWithVisualId(..., 1 = UnitSelectionType.OnlyAlive)`. Les DEUX etages passent par le
    gameconfig (`constants.unitId`, puis `units.<unitId>.visualId`) -- rien n'est ecrit en dur ici :
    une constante de build codee en dur deviendrait une fausse verite au prochain build."""
    uid = ability_const_str(ability_name, _CONST_UNIT_ID)
    if not uid:
        return None
    try:
        import gameconfig as _GC
    except Exception:
        return None
    vis = (_GC.unit(str(uid)) or {}).get("visualId")
    return str(vis) if vis else None


def _more_gitz_squig_visual_id() -> "str | None":
    """Le `visualId` du Squig (`constants.unitId` = `"orksSmnSquig"`), branche A du selecteur de
    1449 -- cf. `_ability_unit_id_visual_id`."""
    return _ability_unit_id_visual_id(MORE_GITZ_OVER_ERE_ABILITY)


class MoreGitzOverEreExtraDamagePctEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MoreGitzOverEre_ExtraDamagePctEffect` (`EffectType` 0x5a9 =
    1449) -- owner-effect PERMANENT de l'ability MYTHIQUE `MoreGitzOverEre` (`TriggeredAbilityType`
    0x5b0 = 1456) de la MoW `orksRukkatrukk` / `orksNpcMoWRukkatrukk`. Volet restant de #1025-r1.

    i2 `Abilities/MoreGitzOverEre_CurrentLevelDescription` : << Enemies that are adjacent to a
    friendly **Squig** or adjacent to two or more friendly **Mythic** characters take
    +{extraDmgPct}% Damage from **normal melee attacks** >> ; `UnitEffects/..._Description` :
    << Takes +{extraDmgPct}% Damage from normal melee attacks by **Mythic** characters >>.

    QUI LE SUBIT -- `...MoreGitzOverEre_ExtraDamagePctEffect$$CreateTargetSelector`, LU au
    decompile (l'ordre ci-dessous est celui de la COMPOSITION, pas celui des `call`) ::

        Unique( Enemies( Owner@<DSLSelectors+0x30>,
                         op_Addition(
                           # branche A -- voisins d'un Squig ami
                           AdjacentUnits(
                             Friends( Owner@+0x30,
                                      UnitsWithVisualId(
                                        VisualUnitIdFromUnitId( ConfigConstString(<config>, 0) ),
                                        1 = UnitSelectionType.OnlyAlive ),
                                      3 ),
                             unique: true, 3 ),
                           # branche B -- au moins DEUX amis Mythiques adjacents
                           Filter( AllUnits@<DSLSelectors+0x20>,
                                   AmountIsEqualOrGreater(
                                     Friends( Owner@+0x30,
                                              UnitsWithRarity( AdjacentUnits(<element@+0x68>,
                                                                             unique: true, 3),
                                                               5 = idun.meta.Rarity.Mythic, 3 ),
                                              3 ),
                                     Direct(2) ) ) ),
                         3 ) )

    ⚠ `<DSLSelectors+0x68>` est l'ELEMENT COURANT du selecteur, pas une unite nommee : c'est le
    meme slot que lit `UnitsOnTilesWithEffect` (dont le corps fait `unit = *(this+0x68)`). La
    branche B se lit donc << l'unite evaluee a >= 2 amis-du-porteur Mythiques adjacents >>.

    CE QU'ELLES SUBISSENT -- `...$$CreateEffectDamageBonusForAttack` ::

        EffectBonus.ForPercentIncrease(
            get_OwnerIsTarget
              & ( AreFriends( Caster@<DSLSelectors+0x48>, EffectSource@<DSLSelectors+0x38>,
                              0, false )
                  & HasRarity( Caster@+0x48, 5 = idun.meta.Rarity.Mythic ) )
              & IsMeleeAttack
              & IsNormalAttack,
            ConfigVar( 0xa = extraDmgPct, GetAbilityState(this), <config@this+0x60> ) )

    (`ForPercentIncrease` est ici un APPEL nomme a `IdunBattle.Entities.Effects.EffectBonus$$
    ForPercentIncrease`, contrairement a son jumeau 1442 ou il est inline.)

    CANAL DE PORT : `create_aura_defense_damage_malus_for_ally` avec
    `AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"` -- EXACTEMENT l'arbitrage de
    `DaughterOfTheAbyssExtraDamagePctEffect` (#437-r1-r1-r1) : le slot natif est ATTAQUANT (le natif
    verse dans `attackModifiers`), mais le BENEFICIAIRE du selecteur est la CIBLE DU COUP
    (`get_OwnerIsTarget`), et le seul agregateur du port qui balaie les porteurs TIERS pour une
    cible est la boucle state-wide `EffectWithTarget` du builder DEFENSEUR.

    ⚠ `AreFriends(Caster, EffectSource)` est VRAI quand `Caster == EffectSource`
    (`UnitExtensions$$IsFriend` n'ecarte pas l'egalite) : la MoW porteuse qui attaque elle-meme un
    ennemi eligible TOUCHE le bonus. L'agregateur DEFENSE n'exclut PAS `att_id == owner_id` (il
    n'exclut que `uid == tgt_id`), donc ce chemin est servi sans code special -- et on n'ajoute
    surtout pas d'exclusion, qui serait un ecart au natif."""

    # #437-r1-r1-r1 : la FACE vient de la CLASSE. `methods.tsv` donne
    # `...MoreGitzOverEre_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` -- le slot
    # ATTAQUANT -- alors que le port l'evalue par le canal AURA-DEFENSE (le seul qui balaie les
    # porteurs TIERS pour une cible donnee). CONSEQUENCE ARITHMETIQUE REELLE : canal POURCENT
    # ATTAQUANT, pas defenseur.
    AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"

    def _selector_hits_target(self, c) -> bool:
        """`Unique(Enemies(Owner, A + B, 3))` -- la CIBLE DU COUP appartient-elle au selecteur ?

        `op_Addition` est une UNION : il suffit qu'UNE des deux branches la contienne. Les deux se
        derivent du MEME substrat `tgt_adjacent_unit_profiles` = `AdjacentUnits(<cible>, unique,
        3)`, l'adjacence NATIVE (liste stockee + porte d'elevation), enrichie de `(team, visual_id,
        rarity)`.

        BRANCHE A -- `AdjacentUnits( Friends(Owner, UnitsWithVisualId(squig, OnlyAlive), 3) )` : la
        cible est voisine d'un Squig ami du porteur. L'adjacence native est SYMETRIQUE (la liste
        stockee l'est, et la porte `|dElev| < 2` aussi), donc << la cible est dans les voisins des
        squigs >> et << un squig est dans les voisins de la cible >> sont la MEME question.

        BRANCHE B -- `AmountIsEqualOrGreater( Friends(Owner, UnitsWithRarity(AdjacentUnits(<elem>),
        Mythic, 3), 3), Direct(2) )` : au moins DEUX voisins de la cible sont des amis du porteur
        ET Mythiques."""
        prof = c.get(CTX_TGT_ADJACENT_UNIT_PROFILES)
        if prof is None:                                  # canal NON MESURE -> gate FERME
            return False
        owner_team = c.get("owner_team")
        # `Friends( Owner@+0x30, ..., 3 )` -- commun aux DEUX branches.
        friends = [p for p in prof if p[1] is not None and p[1] == owner_team]
        want = _more_gitz_squig_visual_id()
        if want is not None and any(str(p[2]) == want for p in friends if p[2] is not None):
            return True                                   # branche A
        n_mythic = sum(1 for p in friends if p[3] == Rarity.Mythic)
        return n_mythic >= MIN_ADJACENT_MYTHIC_FRIENDS    # branche B

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # `Enemies( Owner@+0x30, ..., 3 )` -- la cible de l'effet est un ENNEMI du porteur.
        if c.get("owner_team") is None or c.get("tgt_team") is None \
                or c.get("owner_team") == c.get("tgt_team"):
            return None
        # `AreFriends( Caster@+0x48, EffectSource@+0x38, 0, false )` -- l'ATTAQUANT est un ami du
        # PORTEUR (qui est aussi la `source` de l'`AddEffect`, cf. `AOwnerEffectTriggeredAbility`).
        if c.get("att_team") is None or c.get("att_team") != c.get("owner_team"):
            return None
        # `HasRarity( Caster@+0x48, 5 = idun.meta.Rarity.Mythic )` -- TRI-ETAT, gate FERME sur None.
        if c.get("att_rarity") != Rarity.Mythic:
            return None
        if c.get("is_melee") is not True:                 # IsMeleeAttack -- tri-etat
            return None
        if c.get("is_normal_attack") is not True:         # IsNormalAttack -- tri-etat
            return None
        if not self._selector_hits_target(c):             # `$$CreateTargetSelector`
            return None
        lvl, mult = _mow_ability_state(self, c, c.get("owner_id"), MORE_GITZ_OVER_ERE_ABILITY)
        pct = ability_var(MORE_GITZ_OVER_ERE_ABILITY, _VAR_EXTRA_DMG_PCT, lvl, multiplier_pct=mult)
        return for_percent_increase(True, int(pct)) if pct else None


class OnMyPositionExtraDamagePctEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.OnMyPosition_ExtraDamagePctEffect` (`EffectType` 0x5a4 =
    1444) -- owner-effect PERMANENT de l'ability MYTHIQUE `OnMyPosition` (`TriggeredAbilityType`
    0x5ac = 1452) de la MoW `astraOrdnanceBattery` / `astraNpcMoWOrdnanceBattery`. Volet PORT de
    `#1024-r2` (la RE et la confrontation live sont dans `docs/rl/case-1024-shield-of-faith-on-my-
    position.md`, qui concluait << aucun canal de rarete >> -- verrou TOMBE depuis #999-r3-r1 et
    #999-r3-r1-r1).

    i2 `Abilities/OnMyPosition_CurrentLevelDescription` : << Enemies that are adjacent to a friendly
    **Cadian Guardsman** or a friendly **Mythic** **character** take +{extraDmgPct}% Damage from
    ranged attacks by mythic characters. >> ; `UnitEffects/OnMyPosition_ExtraDamagePct_Description` :
    << Takes +{extraDmgPct}% Damage from ranged attacks by **Mythic** **characters** >>.

    QUI LE SUBIT -- `...OnMyPosition_ExtraDamagePctEffect$$CreateTargetSelector`, LU au decompile
    (l'ordre ci-dessous est celui de la COMPOSITION, pas celui des `call`) ::

        Enemies( Owner@<DSLSelectors+0x30>,
                 AdjacentUnits(
                   op_Addition(
                     # branche A -- un Cadian Guardsman AMI
                     Friends( Owner@+0x30,
                              UnitsWithVisualId(
                                VisualUnitIdFromUnitId( Get( ConfigConstString(<config>, 0) ) ),
                                1 = UnitSelectionType.OnlyAlive ),
                              3 ),
                     # branche B -- un personnage MYTHIQUE ami
                     UnitsWithRarity(
                       Friends( Owner@+0x30,
                                HeroUnits( AllUnits@<DSLSelectors+0x20>, 3 ),
                                3 ),
                       5 = idun.meta.Rarity.Mythic, 3 ) ),
                   unique: true, 3 ),
                 3 )

    ⚠ CONTRASTE avec son jumeau 1449 (`MoreGitzOverEreExtraDamagePctEffect` ci-dessus), dont la
    branche B est un `Filter(AllUnits, AmountIsEqualOrGreater(..., Direct(2)))` : ici les DEUX
    branches sont UNIES **avant** l'`AdjacentUnits`, donc **UN SEUL** voisin eligible suffit -- il
    n'y a AUCUN seuil de compte. Recopier le `>= 2` du voisin de forme serait un port FAUX.

    ⚠ Deux etages que 1449 n'a pas : `HeroUnits` = `UnitsWithTrait(entities, 0x10 =
    UnitTrait.Hero, selectionType)` (`IdunBattleLogic.Entities.DSLSelectors$$HeroUnits` n'a pas
    d'autre corps), et la branche B part d'`AllUnits@<DSLSelectors+0x20>` -- l'univers BOARD-WIDE,
    aucune position lue. C'est ce qui rend l'aura evaluable depuis une MoW (#999-r3-r1-r1).

    ⚠ `AdjacentUnits(X) = Units(AdjacentTiles(X), unique, sel) - X` RETRANCHE l'origine : les amis
    eux-memes sortent de l'ensemble. INATTEIGNABLE ici (`X` n'est fait que d'amis du porteur et le
    resultat est filtre par `Enemies(Owner, ...)`), ecrit parce que c'est LU.

    CE QU'ILS SUBISSENT -- `...OnMyPosition_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` ::

        EffectBonus.ForPercentIncrease(
            get_OwnerIsTarget
              & ( AreFriends( Caster@<DSLSelectors+0x48>, EffectSource@<DSLSelectors+0x38>,
                              0, false )
                  & HasRarity( Caster@+0x48, 5 = idun.meta.Rarity.Mythic ) )
              & IsRangedAttack,
            ConfigVar( 0xa = extraDmgPct, GetAbilityState(this), <config@this+0x60> ) )

    CANAL DE PORT : `create_aura_defense_damage_malus_for_ally` avec
    `AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"` -- MEME arbitrage que 1449 et que
    `DaughterOfTheAbyssExtraDamagePctEffect` (#437-r1-r1-r1) : le slot natif est ATTAQUANT (le natif
    verse dans `attackModifiers`), mais le BENEFICIAIRE du selecteur est la CIBLE DU COUP
    (`get_OwnerIsTarget`), et le seul agregateur du port qui balaie les porteurs TIERS pour une
    cible est la boucle state-wide `EffectWithTarget` du builder DEFENSEUR.

    ⚠ i2 dit << by mythic **characters** >> mais le trigger ne lit QUE `HasRarity(Caster, Mythic)` :
    il n'y a AUCUN `HeroUnits`/`HasTrait(Hero)` sur l'attaquant. C'est le decompile qui fait foi --
    le trait `Hero` n'apparait que dans la branche B du SELECTEUR, sur les voisins de la cible.

    ⚠ `AreFriends(Caster, EffectSource)` est VRAI quand `Caster == EffectSource`
    (`UnitExtensions$$IsFriend` n'ecarte pas l'egalite) -- la MoW porteuse qui attaquerait
    elle-meme un ennemi eligible toucherait le bonus. Aucune exclusion `att_id == owner_id` n'est
    ajoutee : elle serait un ecart au natif."""

    # #437-r1-r1-r1 : la FACE vient de la CLASSE. `methods.tsv` donne
    # `...OnMyPosition_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` -- le slot ATTAQUANT
    # -- alors que le port l'evalue par le canal AURA-DEFENSE (le seul qui balaie les porteurs
    # TIERS pour une cible donnee). CONSEQUENCE ARITHMETIQUE REELLE : canal POURCENT ATTAQUANT.
    AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"

    def _selector_hits_target(self, c) -> bool:
        """`Enemies(Owner, AdjacentUnits(A + B, unique, 3), 3)` -- la CIBLE DU COUP appartient-elle
        au selecteur ?

        `op_Addition` est une UNION, et l'`AdjacentUnits` porte sur l'UNION ENTIERE : il suffit
        qu'UN voisin de la cible soit dans A **ou** dans B. Les deux se derivent du MEME substrat
        `tgt_adjacent_unit_profiles` = `AdjacentUnits(<cible>, unique, 3)`, l'adjacence NATIVE
        (liste stockee + porte d'elevation), enrichie de `(team, visual_id, rarity, is_hero)`.
        L'adjacence native est SYMETRIQUE, donc << la cible est voisine d'un X >> et << un X est
        voisin de la cible >> sont la MEME question.

        BRANCHE A -- `Friends(Owner, UnitsWithVisualId(<Cadian Guardsman>, OnlyAlive), 3)`.
        BRANCHE B -- `UnitsWithRarity(Friends(Owner, HeroUnits(AllUnits, 3), 3), Mythic, 3)`."""
        prof = c.get(CTX_TGT_ADJACENT_UNIT_PROFILES)
        if prof is None:                                  # canal NON MESURE -> gate FERME
            return False
        owner_team = c.get("owner_team")
        # `Friends( Owner@+0x30, ..., 3 )` -- commun aux DEUX branches.
        friends = [p for p in prof if p[1] is not None and p[1] == owner_team]
        want = _ability_unit_id_visual_id(ON_MY_POSITION_ABILITY)
        if want is not None and any(str(p[2]) == want for p in friends if p[2] is not None):
            return True                                   # branche A
        # branche B : `HeroUnits` (trait 0x10) ET `UnitsWithRarity(..., Mythic)`. AUCUN seuil de
        # compte -- contraste 1449, dont la branche B exige `>= 2`.
        return any(bool(p[4]) and p[3] == Rarity.Mythic for p in friends)

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # `Enemies( Owner@+0x30, ..., 3 )` -- la cible de l'effet est un ENNEMI du porteur.
        if c.get("owner_team") is None or c.get("tgt_team") is None \
                or c.get("owner_team") == c.get("tgt_team"):
            return None
        # `AreFriends( Caster@+0x48, EffectSource@+0x38, 0, false )` -- l'ATTAQUANT est un ami du
        # PORTEUR (qui est aussi la `source` de l'`AddEffect`, cf. `AOwnerEffectTriggeredAbility`).
        if c.get("att_team") is None or c.get("att_team") != c.get("owner_team"):
            return None
        # `HasRarity( Caster@+0x48, 5 = idun.meta.Rarity.Mythic )` -- TRI-ETAT, gate FERME sur None.
        if c.get("att_rarity") != Rarity.Mythic:
            return None
        # `IsRangedAttack` -- le ctx d'aura porte la nature du coup sous `is_melee`, que le foyer
        # UNIQUE `runner/damage_model.py` pose en `(not is_ranged) if is_ranged is not None else
        # None`. On l'INVERSE pour retrouver l'argument du predicat NOMME (`effects/base.py::
        # is_ranged_attack`, tri-etat #106) au lieu de re-ecrire le test a la main : `None`
        # (nature non declaree) FERME le gate, comme le natif qui ne devine pas non plus.
        _im = c.get("is_melee")
        if not _is_ranged_attack((not _im) if _im is not None else None):
            return None
        if not self._selector_hits_target(c):             # `$$CreateTargetSelector`
            return None
        lvl, mult = _mow_ability_state(self, c, c.get("owner_id"), ON_MY_POSITION_ABILITY)
        pct = ability_var(ON_MY_POSITION_ABILITY, _VAR_EXTRA_DMG_PCT, lvl, multiplier_pct=mult)
        return for_percent_increase(True, int(pct)) if pct else None
