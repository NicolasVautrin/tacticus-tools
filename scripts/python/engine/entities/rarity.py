"""engine.entities.rarity -- enum natif `idun.meta.Rarity` (rarete d'une unite EN BATAILLE).

Mirror 1:1 d'`idun.meta.Rarity`, transcrit depuis la table de symboles VERSIONNEE du build
(`data/symbols/<build>/frida/enums.tsv`). Meme precedent que `UnitFaction` / `UnitTrait` : un enum
natif standalone -> son propre module, foyer unique du mapping.

⚠ CINQ enums du build ont EXACTEMENT ces six membres aux memes ordinaux -- `idun.meta.Rarity`,
`IdunMetaLogic.UserProgress.Model.UnitRarity`, `...ItemRarity`, `...UpgradeRarity`,
`...XpBookRarity`. Se tromper d'appariement serait donc SILENCIEUX EN ORDINAL, et c'est
exactement pourquoi le nom PLEIN est ce qu'on inscrit au registre de `probe_313`.

**Celui que le COMBAT lit est `idun.meta.Rarity`**, et c'est LU dans `frida/methods.tsv` au TYPE
DECLARE du parametre -- jamais deduit du nom court. Trois foyers concordants :

    IdunBattleLogic.Entities.DSLSelectors.UnitsWithRarity   rarity:idun.meta.Rarity
    IdunBattleLogic.Entities.DSLTriggers.HasRarity          rarity:idun.meta.Rarity
    IdunBattle.Entities.UnitExtensions.HasRarity            rarity:idun.meta.Rarity

(`docs/rl/case-1024-shield-of-faith-on-my-position.md` §4 nomme `...Model.UnitRarity` : cet enum
existe bien, mais c'est l'enum META -- ce n'est pas celui que les gates de bataille prennent.)

SUBSTRAT DE LA VALEUR :
`IdunBattle.Entities.UnitExtensions$$HasRarity(unit, rarity)` et
`IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` lisent tous deux
`IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent(e)` puis comparent son champ `+0x74`.

⚠ LE CANAL EXISTE DEPUIS #1039 ET IL EST CONSOMME DEPUIS #999-r3 -- la phrase qui vivait ici
(« ce champ n'est publie par AUCUN RPC... ce module donne le VOCABULAIRE, pas le CANAL ») est
PERIMEE. `combatSnapshot.units[].rarity` porte l'ordinal lu sur le COMPOSANT (donc MoW comprises,
cf. `case-1039` §4), `combatSnapshot.rarityEnum` le nom PLEIN de l'enum, et `measured_rarity` /
`assert_rarity_channel` ci-dessous sont le FOYER UNIQUE par lequel le port l'entre
(`UnitContext.rarity`). Cf. `docs/rl/case-1039-capteur-rarete.md` et `case-999r3-canal-rarete.md`.

⚠ NE PAS le seeder depuis `GC.unit(<id>)["BaseRarity"]` : c'est la rarete de BASE (chaine
`"Common"` pour des MoW qui sont Mythic en bataille), pas la rarete EFFECTIVE, qui depend de la
progression. Et ne pas le seeder depuis le `targetRarity = 5` que `rl_duel build` impose non plus :
ce serait vrai dans le regime par defaut du harnais et FAUX des qu'une unite est montee par
`--unit-stat "<vis>:Rarity=N"`.
"""
from __future__ import annotations

from enum import IntEnum


class Rarity(IntEnum):
    """`idun.meta.Rarity`. Valeur == valeur d'enum natif ; nom == nom natif verbatim."""
    Common = 0
    Uncommon = 1
    Rare = 2
    Epic = 3
    Legendary = 4
    Mythic = 5


#: Nom PLEIN de l'enum que le COMBAT lit, tel que le capteur le publie sous `combatSnapshot
#: .rarityEnum` (`fieldTypeClass(BaseUnitComponent, "Rarity")` cote hook, #1039). C'est le SEUL
#: discriminant : CINQ enums du build portent les six memes membres aux memes ordinaux, donc une
#: confusion d'appariement serait SILENCIEUSE EN ORDINAL (cf. l'entete de ce module).
RARITY_ENUM_FULL_NAME = "idun.meta.Rarity"


def measured_rarity(snap_unit) -> "Rarity | None":
    """`Rarity` d'une ligne `combatSnapshot.units[]` (ou `unitsNotAlive[]`) -- TRI-ETAT STRICT.

    `None` = **pas mesure** : champ absent (capteur anterieur a #1039), ou `null` rendu par le
    capteur -- soit parce que la resolution du canal a echoue, soit parce que la sous-lecture
    `debugOnly: [...]` ne l'a pas demandee. JAMAIS `0` en repli : `0` est `Rarity.Common`, une
    valeur parfaitement plausible (meme discipline que le capteur, `case-1039` §5).

    Un ordinal HORS de l'enum LEVE au lieu de se degrader en `None` : il ne peut vouloir dire
    qu'une chose -- le build a bouge sous le mirror, et un `None` silencieux ferait basculer tous
    les gates de rarete en RESTRICTIF sans que personne ne le voie. C'est exactement la
    degradation muette que ce canal existe pour supprimer."""
    if snap_unit is None:
        return None
    v = snap_unit.get("rarity")
    if v is None:
        return None
    try:
        return Rarity(int(v))
    except ValueError as exc:                     # ordinal hors mirror -> LEVER, jamais `None`
        raise ValueError(
            "combatSnapshot.units[].rarity = %r n'est pas un membre d'%s : le mirror "
            "`engine/entities/rarity.py` est en retard sur le build (re-jouer probe_313)."
            % (v, RARITY_ENUM_FULL_NAME)) from exc


def assert_rarity_channel(snapshot) -> "str | None":
    """Confronte `combatSnapshot.rarityEnum` au nom PLEIN attendu. Rend le nom lu, ou `None`.

    `None` = le capteur n'a pas publie de nom -- soit qu'il soit anterieur a #1039, soit que SON
    resolveur ait REFUSE le canal (il rend alors `rarityEnum: null` ET `rarity: null` partout,
    donc rien a garder). Ce n'est pas une faute : c'est un canal muet, et `measured_rarity` le
    traduit deja en « pas mesure ».

    Un nom PRESENT et DIFFERENT, en revanche, est le seul symptome visible d'une confusion
    d'appariement -- les quatre `IdunMetaLogic.UserProgress.Model.{Unit,Item,Upgrade,XpBook}Rarity`
    portent les MEMES six membres aux MEMES ordinaux, donc aucune valeur ne trahirait l'echange.
    On LEVE : un canal qu'on ne sait pas nommer ne doit pas armer un gate."""
    if not isinstance(snapshot, dict):
        return None
    name = snapshot.get("rarityEnum")
    if name is None:
        return None
    if str(name) != RARITY_ENUM_FULL_NAME:
        raise RuntimeError(
            "canal de rarete REFUSE : combatSnapshot.rarityEnum = %r, attendu %r. Les cinq enums "
            "de rarete du build partagent leurs six membres aux memes ordinaux -- la valeur ne "
            "trahirait PAS l'echange, seul ce nom le fait (cf. docs/rl/case-1039-capteur-rarete.md "
            "Sec.3)." % (str(name), RARITY_ENUM_FULL_NAME))
    return str(name)
