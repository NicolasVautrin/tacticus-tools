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
prouvee (cf. doc §17.4 « present != applique »). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition, for_percent_increase
from ..base import BaseEffect
from ..magnitude import ability_var


class RitesOfBattleExtraDmgEffect(BaseEffect):
    """`RitesOfBattleExtraDmgEffect` (Effects.Loki) — AURA stat-mod +dégât de Calgar (2 EffectTypes
    permanents sur le porteur : Basic `...ExtraDmgBasic` 1002 / Imperial `...ExtraDmgImperial` 1003).
    `RitesOfBattleAbility.CreateBehaviour @181225340` → 2 `DynamicStatModifierEffect` sur le SOURCE ;
    `CreateTargetSelector` = `AdjacentUnits(1) @180de8320` (source EXCLUE) → `Friends @180df0040` →
    `With/WithoutTrait(0x1a=26)` (26 = grande-alliance Imperial, `GrandAlliance.GetTrait @1815647a0`).
    Montant `GetDynamicStatModificationAmount` = `GetVariableForLevel(idx8→extraDmg | idx9→extraDmg_2,
    niveau SOURCE)` × multiplier SOURCE (les 2 vars dans `variablesAffectedByRarityBonus`) ; ajouté à la
    **modification** du stat **Attack**. RE-validé : `extraDmg_2[L50]×1.8 = 1298` (Imperial, u92 adjacent
    à Calgar) ; `extraDmg[L50]×1.8 = 898` (basic).

    ⚠ Modélisée UNIQUEMENT côté SOURCE via `create_aura_attack_bonus` (l'effet-entité vit sur le PORTEUR,
    pas sur le buffé → PAS de `get_stat_modification_*` target-side : le porteur ne se self-buff pas,
    AdjacentUnits l'exclut). La sélection Basic/Imperial + le montant sont ré-évalués PAR CANDIDAT."""

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> int | None:
        """AURA `RitesOfBattleAbility` @181225340 (2 effets permanents sur Calgar : Basic 1002 / Imperial
        1003) : +extraDmg/_2 au DÉGÂT DE BASE des ALLIÉS ring-1 du porteur, gate grande-alliance Imperial.
        `AdjacentUnits(1) @180de8320` (source EXCLUE) → `Friends @180df0040` (même équipe) →
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
        import hexgeo
        if hexgeo.distance(op, ap) != 1:                 # AdjacentUnits(range 1) — pure adjacence HEX
            return None
        # Gate trait 0x1a=26 = grande-alliance Imperial (GrandAlliance.GetTrait @1815647a0 : Imperial→26).
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
    (`PathOfCommand_ExtraDmg` 1112). `PathOfCommandAbility.CreateBehaviour @181110f10` pose 2 effets
    DynamicStatModifier sur le SOURCE (Loki) : ExtraDmg (0x458=1112) + ExtraCrit (0x453=1107).
    `CreateTargetSelector @180f4bf30` = `SurroundingFriends(owner, range=GetNumberConstant(0x16)=2)` =
    `SurroundingTiles(range) - Tiles(self)` → `Friends` → alliés (même équipe) à distance hex <=2, SOURCE
    EXCLUE (comme RitesOfBattle mais range 2 au lieu de 1).

    Montant `GetDynamicStatModificationAmount @18119c7b0` = `If(IsSameFaction(owner, target), v8+v9, v8)`
    avec `v8 = GetVariableForLevel(8=extraDmg, niveau SOURCE)`, `v9 = (9=extraDmg_2, niveau SOURCE)` (mêmes
    enum-keys 8/9 = extraDmg/extraDmg_2 que RitesOfBattle) × multiplier SOURCE (les 2 dans
    `variablesAffectedByRarityBonus`). `IsSameFaction` = **même FACTION** (FactionId, ex. Aeldari), PAS la
    grande-alliance : `IsSameFaction` s'appuie sur `UnitExtensions.HasFaction @180ed6450` (compare le champ
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
        # (FactionId, cf. HasFaction @180ed6450), PAS grande-alliance. Confirmé live (Ork Xenos = extraDmg seul).
        ofac, afac = c.get("owner_faction"), c.get("att_faction")
        if ofac is not None and ofac == afac:
            base += ability_var("PathOfCommand", "extraDmg_2", lvl, multiplier_pct=mult) or 0
        return base or None


class DaughterOfTheAbyssExtraDamagePctEffect(BaseEffect):
    """`DaughterOfTheAbyss_ExtraDamagePctEffect` (effet 0x589=1417) — les Psykers ENNEMIS dans le rayon
    du porteur REÇOIVENT +extraDmgPct% de dégât (i2 : « Enemy Psykers within 2 hexes receive +20%
    Damage »). Même mécanique state-wide que le jumeau Friendly, polarité inverse :
    - dégât `CreateEffectDamageBonusForAttack` @180f3cb60 (bonus sur l'attaque CONTRE la cible de l'effet) ;
    - cibles `CreateTargetSelector` @180f3cd00 : `SurroundingEnemies(owner, ConfigConst 0x16=range) &
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


class BeaconOfRageFriendlyExtraDamageEffect(BaseEffect):
    """`BeaconOfRage_FriendlyExtraDamageEffect` (EffectType 0x513=1299, nom capté
    "BeaconOfRage_FriendlyExtraDamage") — variante AURA de BeaconOfRage (le SELF 0x512=1298 =
    `BeaconOfRageExtraDamageEffect`). i2 : « 50% of the extra damage from Beacon of Rage is added to the
    damage of melee attacks of adjacent friendly Chaos units. » #191.

    L'effet vit sur le PORTEUR (Azkor) : `GetUpdateFriendEffectBehaviour @180e13040` fait
    `AddEffect(0x513, owner@0x148)` + `SetEffectLevel(owner, 0x513, ...)` SUR AZKOR (jamais sur les amis)
    → capté dans decisionView.effects d'AZKOR, PAS de l'ami. Il se PROJETTE sur ses amis Chaos adjacents
    (canal AURA côté SOURCE, comme AstartesBanner / DaughterOfTheAbyss).

    - dégât `CreateEffectDamageBonusForAttack @180f33370` : `ForAddition(get_OwnerIsCaster &
      IsMeleeAttack, PercentageOf(Multiply(ConfigVar(8=extraDmg, GetAbilityState), EffectLevel(effet)),
      0x32=50, mode 0))` = FLAT additif = **50 % du bonus SELF** (`extraDmg[ablvl Azkor] × rage`), arrondi
      half-to-even. Trigger : l'AMI attaque (OwnerIsCaster projeté) en MÊLÉE (même canal additif
      `DamageModifiers.Add` que le self BeaconOfRage / SmashaEad).
    - cible `CreateTargetSelector @180f335b0` : `UnitsWithTrait(AdjacentFriends(owner@0x148, 1, 3),
      0x7ea=2026=Chaos, 3)` = amis d'Azkor ring-1 (hex-adjacents) de grande-alliance Chaos.
    - niveau/présence `GetCurrentFriendEffectLevel @180e12f10` = `If(UnitsDefeatedAmount(Azkor)>0,
      GetCurrentSelfEffectLevel, 0)` : l'effet n'est AJOUTÉ sur Azkor (behaviour @180e13040 :
      `If(UnitsDefeatedAmount>0 & !HasEffect(0x513), AddEffect)`) QUE si Azkor a ≥1 kill, avec pour level
      la même RAGE que le self (`Min(TotalTimesAttacked, 8)`). ⇒ la PRÉSENCE de l'effet dans la capture
      encode DÉJÀ le gate ≥1-kill + la rage → on lit `self.level` tel quel (comme le self, PAS de recalcul
      offline de UnitsDefeatedAmount).

    Gate grande-alliance Chaos (trait 2026) = ABSENT de gameconfig.traits → dérivé de GrandAllianceId
    (`GrandAlliance.GetTrait @1815647a0` : Imperial→26, Xenos→0x3ee, Chaos→0x7ea=2026), comme le gate
    Imperial de RitesOfBattle. Magnitude `extraDmg` = ability_var BeaconOfRage indexée sur l'ablvl PASSIF
    d'AZKOR (source), pas de l'ami (l'effet-entité porte l'ablvl d'Azkor). Ctx aura = {owner_id/pos/team,
    att_id/att_pos/att_team, att_grand_alliance, is_melee}."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                             # IsMeleeAttack @180f33370
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

    - dégât `CreateEffectDamageBonusForAttack @180f56e30` : `ForAddition(IsMeleeAttack &
      OwnerIsCaster, ConfigVar(8=extraDmg, GetAbilityState))` = +extraDmg[ablvl Dante]×mult FLAT
      additif PRÉ-perçage PAR COUP (canal `DamageModifiers.additive`, comme SmashaEad/BeaconOfRage).
    - cible `CreateTargetSelector @180f56fb0` : `Unique(UnitsWithTrait(SurroundingFriends(owner,
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
        if not c.get("is_melee"):                             # IsMeleeAttack (@180f56e30)
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

    - dégât `CreateEffectDamageBonusForAttack @180f3f780` : `ForAddition(OwnerIsTarget &
      AreFriends(attaquant, EffectSource) & !AreEqual(attaquant, EffectSource) &
      (HasFaction(attaquant, Aeldari) | IsNormalAttack), ConditionalAmount(HasFaction(att,
      Aeldari), ConfigVar(9=extraDmg_2), ConfigVar(8=extraDmg)))` — FLAT PRÉ-perçage PAR COUP.
    - cible `CreateTargetSelector @180f3fa80` : `SurroundingEnemies(owner, ConfigConst(0x16)=
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
    AURA côté SOURCE : `SpotterReworkedAbility.CreateBehaviour @1811a1920` pose les DEUX effets sur le
    PORTEUR (`AddEffect(0x40f=1039) + AddEffect(0x428=1064)`), chacun se projette sur ses amis via son
    TargetSelector. i2 : « Other friendly units within {range} hexes deal +{extraDmg} Damage with ranged
    attacks ; Heavy Weapon units deal +{extraDmg_2} instead. » Le « instead » = sélecteurs mutuellement
    exclusifs sur le trait HeavyWeapon 0x3e9=1001. Sélecteur commun (@180f6c860 / @180f6cb40) :
    `SurroundingFriends(owner, ConfigConst(0x16)=range=2, 1, 3) → UnitsWithRangedAttacks → fork trait`
    (self exclu, ami à ≤range hexes).

    ⚠ `UnitsWithRangedAttacks @180e00610` N'EST PAS un filtre arme-ranged pur : c'est l'UNION
    (`TargetsSelector.op_Addition`, même sens que LordOfTheHost RapidAssault+Flying) de
    `UnitsWithWeaponsSelector(type 2=ranged)` ET `TilesOnSameElevationSelector(réf=DSLFactory+0x28
    = entité du contexte (porteur), maxDiff=2)` — `GetElevationDifference @180ec4ee0` =
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
        """`UnitsWithRangedAttacks @180e00610` : arme ranged au kit OU |Δélévation| ≤ 2 vs porteur."""
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
    - dégât `CreateEffectDamageBonusForAttack @180f6c680` : `ForAddition(OwnerIsActor & IsRangedAttack,
      ConfigVar(8=extraDmg, GetAbilityState), source 0x5df)` = +extraDmg[ablvl Thaddeus]×mult FLAT
      additif PRÉ-perçage PAR COUP (canal `DamageModifiers.additive`, comme LordOfTheHost).
    - cible `CreateTargetSelector @180f6c860` : `UnitsWithoutTrait(UnitsWithRangedAttacks(
      SurroundingFriends(owner, range=2)), 0x3e9=HeavyWeapon)`."""

    _VAR = "extraDmg"
    _WANT_HEAVY = False

    def _trigger_ok(self, c: Mapping) -> bool:
        return c.get("is_melee") is False                     # IsRangedAttack (@180f6c680)


class SpotterReworkedHeavyWeaponEffect(_SpotterReworkedAuraBase):
    """`SpotterReworked_HeavyWeaponEffect` (effet 0x428=1064) — amis AVEC HeavyWeapon, « instead ».
    - dégât `CreateEffectDamageBonusForAttack @180f6c980` : `ForAddition(OwnerIsActor,
      ConfigVar(9=extraDmg_2, GetAbilityState), source 0x5df)` — trigger SANS IsRangedAttack (fidèle
      au décompilé : un porteur HeavyWeapon à arme ranged garde le bonus même sur un coup MÊLÉE).
    - cible `CreateTargetSelector @180f6cb40` : `UnitsWithTrait(UnitsWithRangedAttacks(
      SurroundingFriends(owner, range=2)), 0x3e9=HeavyWeapon)`."""

    _VAR = "extraDmg_2"
    _WANT_HEAVY = True

    def _trigger_ok(self, c: Mapping) -> bool:
        return True                                           # OwnerIsActor seul (@180f6c980)


class DefenderOfTheGreaterGoodExtraDmgEffect(BaseEffect):
    """`DefenderOfTheGreaterGood_ExtraDmgEffect.CreateDamageModifier @180f3e4f0` (tauShadowsun passif
    DefenderOfTheGreaterGood, TriggeredAbilityType 1155 ; EffectType 0x49e=1182 "DefenderOfTheGreaterGood_
    ExtraDmg"). AURA cote SOURCE (template SpotterReworked/LordOfTheHost). i2 : « Friendly units adjacent
    to Shadowsun or her Command-Link Drone deal +364 Damage with ranged attacks, except attacks that deal
    Psychic Damage. ... Friendly T'au Empire units within 2 hexes ... are also affected. »

    POSE (`DefenderOfTheGreaterGoodAbility.CreateBehaviour @180e203d0`, RE decompile) :
    `If(HasTrait(owner, Summon=2), AddEffect(0x51a=1306)+AddEffect(0x51b=1307),
        AddEffect(0x49e=1182)+AddEffect(0x49f=1183))` = branche NON-Summon (Shadowsun) pose 1182 (CET
    effet ExtraDmg) + 1183 (ExtraHits, coup additionnel PROBABILISTE = [fable], NON porte) ; branche Summon
    (Command-Link Drone) pose les JUMEAUX drone 1306/1307. L'effet vit sur le PORTEUR et se projette sur ses
    amis via son TargetSelector (AURA source-side, MEME canal que SpotterReworked/LordOfTheHost/Doom).

    - degat `CreateDamageModifier @180f3e4f0` (RE decompile) : `EffectBonus.ForAddition(get_OwnerIsCaster &
      IsRangedAttack & !DamageProfileIs(0xd=13=Psychic), ConfigVar(8=extraDmg, GetAbilityState, EffectSource
      @0x60))`, source AbilityOrEffect 0x483=1155 (DefenderOfTheGreaterGood, pour l'attribution -- non porte,
      cf. SpotterReworked). Canal ADDITIF pre-percage PAR COUP (`DamageModifiers.additive`). DEUX differences
      vs SpotterReworked_ExtraDamage (@180f6c680) : (1) `get_OwnerIsCaster` (vs OwnerIsActor -- meme semantique :
      ce chemin n'est appele que pour l'attaque du BENEFICIAIRE) ; (2) noeud `!DamageProfileIs(Psychic)` en plus
      (SpotterReworked forkait sur HeavyWeapon a la place).
    - cible `GetBaseBuffTargetSelector @180e20590` (RE decompile) :
      `UnitsWithRangedWeaponsExcludingDamageProfile( Unique( (AdjacentFriends(owner,1) - {owner})
        + UnitsFromFaction(SurroundingFriends(owner, range=2), UnitFaction.Tau=9) ), 0xd=Psychic )`
      = amis SOIT ADJACENTS (range 1, TOUTE faction) SOIT T'au dans range 2, ayant une arme RANGED non-Psychic.
      Selecteur d'aura partage x4 (StructuralAnalyser/SereneUnifier/DotGG/WayOfTheShortBlade, cf. case-220
      §6.6). Le filtre `UnitsWithRangedWeaponsExcludingDamageProfile(Psychic)` = eligibilite CARRIER (arme
      ranged non-Psychic) SUBSUMEE par le gate d'attaque `is_ranged & damage_profile != Psychic` du coup mesure.
    - MAGNITUDE = `ability_var("DefenderOfTheGreaterGood", "extraDmg", ablvl) x multiplier` (ConfigVar var
      index 8 = extraDmg, SEULE var d'ability, DANS variablesAffectedByRarityBonus -> scale x mult ;
      extraDmg[L1..65]=[5..364] ; i2 « +364 » = extraDmg[L65]). `GetVariableForLevel(config, 8, GetAbilityState)`
      sur le config de DefenderOfTheGreaterGood (le PASSIF de Shadowsun) -> level = niveau passif du PORTEUR
      (self.ability_level, comme SpotterReworked/LordOfTheHost). Multiplier = le GLOBAL du porteur
      (self.ability_variables_multiplier).
    - GATE : is_ranged (IsRangedAttack) ; damage_profile != Psychic (!DamageProfileIs(0xd)) ; distance
      (adjacent range 1 toute faction, OU T'au range 2). is_melee None (chemins ability combat non threades
      is_ranged) -> gate off (calque SpotterReworked `_trigger_ok`). Ne modelise PAS 1183 ExtraHits ([fable]).

    VALIDATION : le PSYCHIC-exclusion exige `damage_profile` dans le ctx aura-ally (threade par normal_attack/
    abilities/psyker/fury cote prediction ; par damage.py cote combat) et `att_faction` (FactionId) pour le
    tier T'au range-2 (deja threade cote prediction ; ajoute cote combat)."""

    _TAU_FACTION = "Tau"           # UnitFaction.Tau=9 (UnitsFromFaction(9) @180e20590) ; FactionId gameconfig="Tau"

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("att_id") == c.get("owner_id"):              # AdjacentFriends/SurroundingFriends excluent self
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                       # Friends = meme equipe que le porteur
        if c.get("is_melee") is not False:                    # IsRangedAttack (@180f3e4f0) : ranged only
            return None                                       # (None = ability combat non threade -> gate off)
        if (c.get("damage_profile") or None) == "Psychic":    # !DamageProfileIs(0xd=13=Psychic)
            return None
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        d = hexgeo.distance(op, ap)
        # Selecteur @180e20590 : (AdjacentFriends(range=1, TOUTE faction) - owner) + UnitsFromFaction(
        # SurroundingFriends(range=2, disk), Tau=9). range 1 / range 2 = litteraux DSL (pas de ConfigVar range).
        adjacent = (d == 1)
        tau_ring = (d <= 2 and c.get("att_faction") == self._TAU_FACTION)
        if not (adjacent or tau_ring):
            return None
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var("DefenderOfTheGreaterGood", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None
