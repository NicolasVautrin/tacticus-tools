"""`MachineVengeance` (`EffectType` 0x555 = 1365) -- le canal DEGAT de la pile posee par
`ArcScourge` / `InvocationOfMachineVengeance`. RE : decompile ghidra, build `rnca9r7q6c` (#1081,
ex-residu `#1023-r1`).

===================================================================================================
LE BLOC `methodPointers` EST SEGMENTE -- QUATRE faces, pas les DEUX que les tables nomment
===================================================================================================

La 1ere tache du residu etait de segmenter le bloc, parce que `frida/methods.tsv` (indexe par
ADRESSE) ne nomme que les corps dont cette classe est PROPRIETAIRE -- deux ici -- et qu'un
`CreateActiveCondition` / `CreateTargetSelector` trivial est fondu par l'ICF chez un proprietaire
arbitraire. Fait, en lisant les pointeurs contigus autour du `.ctor` (`18326e9c8`, borne haute
donnee par le `.ctor` de la classe SUIVANTE) puis en resolvant chacun :

    slot 0   `MachineVengeanceEffect$$.ctor`                              (corps PROPRE)
    slot 1   corps NOMME `WisdomOfTheAncients_DamageReductionEffect$$CreateActiveCondition`   ICF
    slot 2   corps NOMME `WhisperingWebEffect$$CreateTargetSelector`                          ICF
    slot 3   `MachineVengeanceEffect$$CreateEffectDamageBonusForAttack`   (corps PROPRE)

La crainte du residu etait donc FONDEE -- la classe porte bien deux faces de plus que ce que les
tables lui attribuent -- et les DEUX corps fondus sont TRIVIAUX, ce qui est le resultat :

    slot 1 = `return <DSLTriggers+0x70>`   = `YesTrigger`  -> l'effet est TOUJOURS ACTIF
    slot 2 = `return <DSLSelectors+0x30>`  = `Owner`       -> AUCUNE projection : l'effet ne
                                                             s'applique qu'a son propre porteur

Il n'y a donc **pas** de `GetCalculateLevel` dans ce bloc : le niveau lu par la magnitude est le
niveau STOCKE (`EffectComponent+0x68`), celui qu'incrementent les poses successives de la pile --
et non un compteur recalcule a chaque rafraichissement comme celui de `SupaCyborkBody`.

===================================================================================================
LA MAGNITUDE -- `MachineVengeanceEffect$$CreateEffectDamageBonusForAttack`
===================================================================================================

    EffectBonus.ForPercentIncrease(
        get_OwnerIsCaster,
        Multiply( Get( EffectConfig(7 = MachineVengeanceExtraPct) ),
                  EffectLevel( Effect@<DSLSelectors+0x38> ) ) )

`.ctor` = `BaseEffect..ctor(this, AbilityOrEffect(<litteral>), hasAutomaticActivation = 1)`.

⚠ **L'ENUM DE LA CONSTANTE N'EST PAS CELUI QU'ON CROIT, ET LE NOM SEUL LE MONTRE.** L'enonce du
residu ecrivait « `AbilityConstantType 7 = MachineVengeanceExtraPct` ». Le NOM est juste, l'ENUM
est FAUX : `AbilityConstantType 7` vaut `unitId_2_blue`. Le bon enum est un QUATRIEME,
`IdunBattle.Entities.Enum.EffectConfigType`, dont le membre `7` est bien
`MachineVengeanceExtraPct` -- et il n'indexe pas le gameconfig des abilities mais la section
`Effect` de la BattleConfiguration (`BC.Effect["MachineVengeanceExtraPct"] = 5`), que le port lit
par `bc_effect_config`. Suivre l'enonce aurait fait chercher une variable d'ability qui n'existe
pas : `gameconfig.ability("MachineVengeance")` rend `None` (1365 est un EFFET, pas une ability ;
l'ability qui le pose est `InvocationOfMachineVengeance`, `ActiveAbilityType` 1172).

⇒ La constante est GLOBALE : ni palier de niveau, ni `AbilityVariablesMultiplier`. Le seul terme
variable est le NIVEAU DE L'EFFET, c.-a-d. la hauteur de la pile.

    bonus = +(5 * niveau) %

===================================================================================================
POURQUOI CE CANAL, ET PAS UNE AURA
===================================================================================================

`CreateTargetSelector` = `Owner` : l'effet n'a aucune projection, il modifie les attaques de
l'unite qui le PORTE. Le canal port est donc `create_effect_damage_bonus_for_attack`, celui que
`_attacker_effect_bonuses` parcourt sur les effets de l'ATTAQUANT -- pas un
`create_aura_attack_damage_bonus_for_ally`. Le `get_OwnerIsCaster` du natif y est STRUCTUREL (ce
canal n'est appele que pour l'attaque du porteur), meme lecture que pour
`DefenderOfTheGreaterGoodExtraDmgEffect` et `WayOfTheShortBladeDamageBuffEffect` ; il est
NEANMOINS confronte ci-dessous quand le contexte porte de quoi le faire, plutot que suppose.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_percent_increase
from ..base import BaseEffect
from ..magnitude import bc_effect_config

#: `IdunBattle.Entities.Enum.EffectConfigType` 7 -- membre LU dans `frida/enums.tsv`, PAS deduit du
#: nom de l'effet. Indexe la section `Effect` de la BattleConfiguration, pas le gameconfig.
EFFECT_CONFIG_KEY = "MachineVengeanceExtraPct"          # EffectConfig(7) ; BC.Effect -> 5


class MachineVengeanceEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MachineVengeanceEffect` (`EffectType` 1365), pose en PILE
    sur sa cible et lu a chaque attaque de celle-ci.

    Hierarchie LUE dans `data/symbols/<build>/frida/classes.tsv` : elle derive directement de
    `IdunBattle.Entities.Effects.BaseEffect` -- **pas** de `HealBlockingEffect`, malgre le
    voisinage des deux entrees dans le registre.

    Les DEUX faces triviales du bloc (`CreateActiveCondition` = `YesTrigger`,
    `CreateTargetSelector` = `Owner`) n'ont RIEN a surcharger cote port : `is_active` vaut deja
    True par defaut sur `BaseEffect`, et l'absence de `aura_selector_covers` vaut deja « aucune
    projection ». Les surcharger a vide ferait croire a une lecture la ou il n'y a qu'un defaut --
    elles sont donc ECRITES dans l'en-tete et NON codees."""

    def _effect_level(self, att_ctx: Mapping | None = None) -> int | None:
        """`DSLFormulas.EffectLevel(Effect@<DSLSelectors+0x38>)` = `EffectComponent+0x68`.

        Le niveau STOCKE, et lui seul : le bloc `methodPointers` de cette classe ne porte AUCUN
        `GetCalculateLevel` (cf. l'en-tete), donc rien ne le recalcule depuis l'etat du board --
        c'est la hauteur de la pile telle que les poses l'ont ecrite.

        ⚠ TRI-ETAT : `None` = niveau NON MESURE, jamais 0. Un 0 invente annulerait le produit et
        ferait passer une pile reelle pour une absence de pile -- l'erreur est SILENCIEUSE, puisque
        les deux rendent « pas de bonus ».
        ⚠ Ce n'est PAS le niveau d'ability (`self.ability_level`) : la constante etant globale,
        aucun palier d'ability n'entre dans cette magnitude."""
        return None if self.level is None else int(self.level)

    def _owner_is_caster(self, att_ctx: Mapping | None = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster`.

        STRUCTUREL sur ce canal (il n'est parcouru que pour l'attaque du porteur), donc le defaut
        est OUVERT. Quand le contexte porte les deux identites, on les CONFRONTE quand meme : un
        appelant qui parcourrait ces effets pour une AUTRE unite serait alors visible, au lieu de
        recevoir un bonus qui ne lui revient pas."""
        c = att_ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        if oid is None or aid is None:
            return True                                  # identite non mesuree -> gate structurel
        return oid == aid

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """MIRROR de `...MachineVengeanceEffect$$CreateEffectDamageBonusForAttack` :

            EffectBonus.ForPercentIncrease( get_OwnerIsCaster,
                                            Multiply( Get(EffectConfig(7)), EffectLevel(effet) ) )

        Les etages sont SEPARES et chacun se tait independamment -- aucun scalaire n'est fitte :
          1. `get_OwnerIsCaster` -- le porteur est-il bien l'attaquant courant ?
          2. `EffectLevel`       -- la hauteur de la pile, tri-etat ;
          3. `EffectConfig(7)`   -- la constante GLOBALE de `BC.Effect`, relue, jamais en dur ;
          4. `Multiply`          -- le produit, verse au canal POURCENT.

        Le natif n'ecrit AUCUN gate de nature de coup (ni `IsRangedAttack`, ni `IsNormalAttack`,
        ni `DamageProfileIs`) : les parametres correspondants sont donc recus et volontairement
        IGNORES. En ajouter un serait un gate INVENTE."""
        if not self._owner_is_caster(att_ctx):                             # 1
            return None
        lvl = self._effect_level(att_ctx)                                  # 2
        if lvl is None:
            return None
        pct = bc_effect_config(EFFECT_CONFIG_KEY)                          # 3
        if not pct:
            return None
        total = int(pct) * int(lvl)                                        # 4
        if total <= 0:
            return None
        return for_percent_increase(True, total)
