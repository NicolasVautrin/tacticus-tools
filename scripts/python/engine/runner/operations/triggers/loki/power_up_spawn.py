"""`APowerup_SpawnAbility` + `PowerUp_HeroSpawn*` / `PowerUp_SummonSpawn*` (#10004) -- tranche 3 de
la famille `APowerUpAbility`.

Les tranches 1 (#1083-r1) et 2 (#1083-r3) ont porte la base `APowerUpAbility` : le trigger
`On(PreUnitDeath)` + `DamageReason.Steppable` + `NOT HasTrait(Actor, Steppable)`, et le
`CreateBehaviour` commun. Ce module ajoute la sous-famille SPAWN.

--------------------------------------------------------------------------------------------------
IL N'Y A PAS ONZE MECANIQUES -- IL Y EN A DEUX, ET NEUF CONFIGS
--------------------------------------------------------------------------------------------------

`search_symbols_by_name` sur `Loki\\.PowerUp_(HeroSpawn|SummonSpawn)\\w*\\$\\$` rend EXACTEMENT deux
corps de `CreateBehaviour` (`PowerUp_HeroSpawnAbility`, `PowerUp_SummonSpawnAbility`). Les NEUF
variantes n'ont aucun symbole propre et ne different que par UNE cle de gameconfig.

⚠ Cette absence ne prouve rien SEULE (IL2CPP deduplique les corps triviaux) : elle est CROISEE avec
le gameconfig, qui montre que les neuf portent une constante de plus et rien d'autre. Deux sources
concordantes ; aucune suffisante seule.

⚠ `PowerUp_HeroSpawn` (1434) et `PowerUp_SummonSpawn` (1532) n'ont AUCUNE constante -> leur
`GetStringConstant` ne rend aucun identifiant, donc elles ne spawnent RIEN. Elles ne sont PAS
inscrites au registre, et c'est un fait mesure, pas un oubli : il y a NEUF mecaniques vivantes.

--------------------------------------------------------------------------------------------------
ARTEFACTS NATIFS (decompile ghidra, build `t6dpr4k06g` -- decompile = verite)
--------------------------------------------------------------------------------------------------

`DSLSelectors+0x18` = `AllTiles`, `+0x30` = `Owner`, `+0x40` = `Actor`, `+0x68` = `ActiveTarget`.

`PowerUp_HeroSpawnAbility$$CreateBehaviour` :

    unitId  = GetStringConstant(config, 0x7e = heroId)
    tuile   = Cache( GetSpawnTile(), unique = 1 )
    options = new SpawnUnitOptions();  options.<+0x61> = 1
    spawn   = Spawn(Player(1), tuile, unitId, options)
    return If( IsInTeam(Actor, 1), GetKillBehaviour(tuile) & spawn, null )

`PowerUp_SummonSpawnAbility$$CreateBehaviour` -- MEME structure, TROIS differences :

    unitId  = GetStringConstant(config, 0x0 = unitId)          # 1. la CLE
    options = SpawnUnitOptions.WithStatsFromConfig(config, abilityState, null, null)   # 2. les OPTIONS
    options.<+0x18> = PerformAIAttackFromCurrentPosition(ActiveTarget, null, null, false)  # 3. l'ORDRE IA
    spawn   = Spawn(Player(1), tuile, unitId, options)
    return If( IsInTeam(Actor, 1), GetKillBehaviour(tuile) & spawn, null )

⚠ L'ASYMETRIE HERO/SUMMON EST LE PREMIER ENDROIT OU CE PORT PEUT SE TROMPER : seul le SUMMON recoit
l'ordre d'attaque IA immediat (`<+0x18>`), le heros ne le recoit pas. Ce n'est pas une commodite --
c'est ce qui fait qu'un summon agit dans la foulee de son apparition et qu'un heros attend son tour.

`APowerup_SpawnAbility$$GetSpawnTile` -- une CASCADE a QUATRE rangs :

    tuilesE = Filter( Tiles(NormalUnits(Enemies(Actor, AllUnits(), 3), 3)),
                      NOT IsSpawnTile(ActiveTarget) )
    libres  = SortByDistance( CanAddUnit( Randomize(AllTiles) ), Actor )
    return First( pref(tuilesE).Otherwise( pref(libres) )
                               .Otherwise( tuilesE )
                               .Otherwise( libres ), 1, 0 )

`APowerup_SpawnAbility$$GetPreferredTiles(validTiles)` :

    return TilesWithoutPowerUps( Filter(validTiles, NOT IsTerritoryTile(ActiveTarget)) )

⚠ `Otherwise` n'est PAS un `or` booleen : c'est le repli d'un SELECTEUR VIDE sur le suivant, et
cote port c'est une CLASSE `Otherwise(primary, fallback)` -- la cascade s'IMBRIQUE, elle ne se
chaine pas.

`APowerup_SpawnAbility$$GetKillBehaviour(spawnTile)` :

    cond = HasUnit(spawnTile, 3) & NOT HasTrait( Units(spawnTile, 1, 3), 0x1b = Steppable )
    return If( cond, Kill(Owner, spawnTile, KillUnitBehaviourOptions.ForClearTile()), null )

C'est-a-dire : si la tuile choisie porte deja une unite NON-`Steppable`, elle est TUEE pour liberer
la place. Le `NOT HasTrait(Steppable)` protege les autres power-ups ; et l'ordre du `&` dans
`CreateBehaviour` (`kill & spawn`) fait que le nettoyage PRECEDE le spawn.

CONFIRME LIVE (build `t6dpr4k06g`) : `ultraCalgar` (team 1) ecrase `powupHeroSpawn_Uthar` ->
`votanUthar` APPARAIT, et `orksNob` -- l'ennemi normal dont la tuile a ete choisie au rang 1 de la
cascade -- passe `dead = True`. Les deux volets se voient d'un coup.

⚠ `IsInTeam(Actor, 1)` est LOAD-BEARING : rien ne spawne si le ramasseur n'est pas de la team 1.
Contrairement au `PlayerType` du gate d'`PowerUp_Bomb` (#1083-r4), la TEAM est portee -- c'est ce
qui rend cette tranche portable la ou celle-la est bloquee.

⚠ Le `1` de `Player(1)` et celui d'`IsInTeam(..., 1)` ne sont PAS le meme axe (parent du spawn vs
team du ramasseur) : deux arguments homonymes, deux roles. Ne pas les fusionner en une constante.

RESIDUS NOMMES :
  1. `IsSpawnTile` et `IsTerritoryTile` ne sont PAS portes (aucun noeud, et la donnee `isTerritory`
     = `TileComponent+0x2e` ne vit que dans le contexte IA, pas dans `ctx.board`). Les deux sont des
     filtres RESTRICTIFS : sans eux le port peut retenir une tuile que le natif aurait ECARTEE. Le
     regime confronte y est INSENSIBLE (mesure : natif et port choisissent la meme tuile), mais
     c'est une MESURE de ce regime, pas une preuve generale.
  2. `KillUnitBehaviourOptions.ForClearTile()` : la feuille portee `Kill` ne lit AUCUNE option
     (residu deja nomme dans sa docstring). Ecart a MESURER, jamais suppose nul.
  3. `Player(1)` : aucun selecteur `Player` n'existe cote port. Le parent du spawn est collapse sur
     le proprietaire du power-up, ce que la feuille `Spawn` portee fait deja.
  4. Les arguments `selectionType` (3 = `OnlyAliveAndTargetable`) des selecteurs natifs n'ont pas
     tous d'equivalent porte -- meme residu que les autres call-sites de la famille.
"""
from __future__ import annotations

from typing import Optional

from .....entities.behaviours import If as IfBehaviour, op_and
from .....entities.selectors.accessors import Actor, Owner
from .....entities.selectors.geometry import Cache, Otherwise, Randomize
from .....entities.selectors.tiles import AllTiles, AllUnits, CanAddUnit, TilesWithoutPowerUps
from .....entities.selectors.units import (Enemies, Filter, First, NormalUnits, SortByDistance,
                                           Tiles, Units)
from .....entities.traits.unit_trait import UnitTrait
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import HasUnit
from ....abilities.behaviours.lifecycle import Kill
from ....abilities.behaviours.summon import PerformAIAttack, Spawn
from ....state import State
from ..base import _unit_trait_names
from .power_up import APowerUpAbility

#: `GetStringConstant(config, 0x7e)` d'`PowerUp_HeroSpawnAbility` -- la cle que la feuille `Spawn`
#: portee doit lire A LA PLACE de son defaut `unitId`.
CLE_HERO = "heroId"
#: `GetStringConstant(config, 0x0)` d'`PowerUp_SummonSpawnAbility` -- c'est deja le defaut de `Spawn`.
CLE_SUMMON = "unitId"
#: `IsInTeam(Actor@sel+0x40, 1)` -- le litteral natif, lu au site des DEUX `CreateBehaviour`.
TEAM_QUI_SPAWNE = 1
#: `NOT HasTrait(Units(spawnTile, 1, 3), 0x1b)` de `GetKillBehaviour`.
TRAIT_STEPPABLE = UnitTrait.Steppable                       # 0x1b = 27


def spawn_tile_tree():
    """`APowerup_SpawnAbility$$GetSpawnTile` -- la cascade a QUATRE rangs, MIRROR 1:1.

    ⚠ `Otherwise` cote port est une CLASSE `Otherwise(primary, fallback)` : la cascade native
    `a.Otherwise(b).Otherwise(c).Otherwise(d)` s'ecrit donc en IMBRIQUANT, jamais en chainant.
    Ecrite a plat, elle donnerait un arbre different (associativite a droite au lieu de gauche).

    RESIDU 1 : les deux `Filter(..., NOT IsSpawnTile/IsTerritoryTile(...))` du natif ne sont pas
    portes -- ils RESTREIGNENT, donc le port retient un sur-ensemble."""
    ennemis = NormalUnits(Enemies(Actor(), AllUnits()))
    tuiles_ennemis = Tiles(ennemis)
    libres = SortByDistance(CanAddUnit(Randomize(AllTiles())), Actor())
    # `GetPreferredTiles(x)` = `TilesWithoutPowerUps(Filter(x, NOT IsTerritoryTile(...)))` -- le
    # `Filter` interne est le RESIDU 1, le `TilesWithoutPowerUps` est porte.
    pref_ennemis = TilesWithoutPowerUps(tuiles_ennemis)
    pref_libres = TilesWithoutPowerUps(libres)
    cascade = Otherwise(pref_ennemis,
                        Otherwise(pref_libres,
                                  Otherwise(tuiles_ennemis, libres)))
    return First(cascade)


def kill_behaviour_tree(tuile):
    """`APowerup_SpawnAbility$$GetKillBehaviour(spawnTile)` -- MIRROR 1:1.

        If( HasUnit(tuile) & NOT HasTrait(Units(tuile), Steppable),
            Kill(Owner, tuile, ForClearTile()), null )

    Le `NOT HasTrait(Steppable)` est ce qui empeche de detruire un AUTRE power-up pose sur la tuile
    visee. RESIDU 2 : `Kill` ne lit pas d'options, donc `ForClearTile()` n'est pas transmis."""
    return IfBehaviour(_TuileOccupeeParUnNonSteppable(tuile), Kill(tuile))


class _TuileOccupeeParUnNonSteppable(HasUnit):
    """`HasUnit(spawnTile, 3) & NOT HasTrait(Units(spawnTile, 1, 3), Steppable)` -- les deux
    conjoints du gate de `GetKillBehaviour`, en un predicat.

    Ecrit comme une sous-classe de `HasUnit` plutot qu'avec un `op_and` de triggers parce que le
    second conjoint porte sur les UNITES de la tuile, que `HasUnit` a deja resolues : les separer
    ferait resoudre le selecteur DEUX fois, et le natif ne le fait qu'une."""

    def __init__(self, tiles):
        super().__init__(tiles)

    def should_trigger(self, ctx):
        if not super().should_trigger(ctx):
            return False                       # `HasUnit(spawnTile)` faux -> pas de kill
        occupants = Units(self.tiles).select(ctx) or []
        etat = getattr(ctx, "state", None)
        for u in occupants:
            uid = u.get("id") if isinstance(u, dict) else u
            if uid is None:
                continue
            if TRAIT_STEPPABLE in _unit_trait_names(etat, int(uid)):
                return False                   # `NOT HasTrait(..., Steppable)`
        return True


class APowerupSpawnAbility(APowerUpAbility):
    """La base SPAWN. Elle NE surcharge PAS `CreateTrigger` -- `APowerup_SpawnAbility` n'en a pas de
    corps propre, ce qui confirme sur `t6dpr4k06g` le fait etabli par la tranche 2 : AUCUN des 22
    `PowerUp_*` ne surcharge le trigger. Le vecteur vient donc d'`APowerUpAbility`.

    Elle surcharge en revanche `behaviour_tree` EN ENTIER : la famille SPAWN ne passe NI par
    `AddShield` NI par les getters de boost (aucune des deux classes ne les surcharge, et leur
    gameconfig ne porte ni `shieldPct` ni `nrOfRounds`)."""

    #: La cle de gameconfig que la feuille `Spawn` doit lire (`heroId` ou `unitId`).
    CLE_UNITE: str = CLE_SUMMON
    #: `<+0x18>` : le SUMMON seul recoit un ordre d'attaque IA immediat.
    ORDRE_IA_A_L_APPARITION: bool = False

    def behaviour_tree(self, state: State, entities):
        tuile = Cache(spawn_tile_tree())
        on_app = (PerformAIAttack(Actor()) if self.ORDRE_IA_A_L_APPARITION else None)
        spawn = Spawn(tuile, self.ABILITY_NAME, unit_id_constant=self.CLE_UNITE,
                      on_appearance=on_app)
        # `kill & spawn` -- l'ORDRE compte : le nettoyage de la tuile precede le spawn.
        return IfBehaviour(_ActeurDansLaTeam(TEAM_QUI_SPAWNE),
                           op_and(kill_behaviour_tree(tuile), spawn))


class _ActeurDansLaTeam(HasUnit):
    """`IdunBattleLogic.Entities.DSLTriggers$$IsInTeam(Actor@sel+0x40, 1)` -- LOAD-BEARING : rien ne
    spawne si l'unite qui a ecrase le power-up n'appartient pas a la team visee.

    Aucun noeud `IsInTeam` n'existait cote port (seul `IsInTeamAura`, qui est autre chose). La TEAM,
    elle, EST portee -- c'est toute la difference avec le gate `IsHumanPlayer` d'`PowerUp_Bomb`
    (#1083-r4), qui reste inevaluable faute de `PlayerType` projete."""

    def __init__(self, team: int):
        super().__init__(Actor())
        self.team = int(team)

    def should_trigger(self, ctx):
        acteurs = Actor().select(ctx)
        if isinstance(acteurs, dict):
            acteurs = [acteurs]
        for u in (acteurs or []):
            if isinstance(u, dict) and u.get("team") is not None:
                return int(u["team"]) == self.team
        return False                            # acteur illisible -> le natif ne spawnerait pas


class PowerUpHeroSpawnAbility(APowerupSpawnAbility):
    """`PowerUp_HeroSpawnAbility$$CreateBehaviour` -- lit `heroId`, et ne donne AUCUN ordre IA."""
    CLE_UNITE = CLE_HERO
    ORDRE_IA_A_L_APPARITION = False


class PowerUpSummonSpawnAbility(APowerupSpawnAbility):
    """`PowerUp_SummonSpawnAbility$$CreateBehaviour` -- lit `unitId`, et pose
    `PerformAIAttackFromCurrentPosition` en `on_appearance` (`<+0x18>`).

    `PerformAIAttackFromCurrentPosition` n'a pas de classe propre cote port : c'est la variante par
    DEFAUT de `PerformAIAttack` (`allow_move_action=False`, `move_amount=0`)."""
    CLE_UNITE = CLE_SUMMON
    ORDRE_IA_A_L_APPARITION = True


def _classe(nom: str, base, tid: int):
    """Fabrique une sous-classe par VARIANTE. Les neuf variantes n'ont aucun corps natif propre :
    elles ne different que par leur nom gameconfig (donc par la constante `heroId`/`unitId` que
    `Spawn` ira lire) et par leur `TriggeredAbilityType`."""
    return type(nom.replace("_", "") + "Ability", (base,),
                {"ABILITY_NAME": nom, "TRIGGERED_ABILITY_ID": int(tid), "__doc__":
                 "Variante de config de `%s` -- aucun corps natif propre." % base.__name__})


#: Les NEUF mecaniques VIVANTES. `PowerUp_HeroSpawn` (1434) et `PowerUp_SummonSpawn` (1532) en sont
#: ABSENTES a dessein : leur gameconfig ne porte AUCUNE constante, donc leur `GetStringConstant` ne
#: rend aucun identifiant et elles ne spawnent rien. Les inscrire ferait croire a onze mecaniques.
POWER_UP_SPAWN_ABILITIES = {
    nom: _classe(nom, base, tid) for nom, base, tid in (
        ("PowerUp_HeroSpawn_VexilusPraetor", PowerUpHeroSpawnAbility,
         TriggeredAbilityType.PowerUp_HeroSpawn_VexilusPraetor),
        ("PowerUp_HeroSpawn_BladeChampion", PowerUpHeroSpawnAbility,
         TriggeredAbilityType.PowerUp_HeroSpawn_BladeChampion),
        ("PowerUp_HeroSpawn_Uthar", PowerUpHeroSpawnAbility,
         TriggeredAbilityType.PowerUp_HeroSpawn_Uthar),
        ("PowerUp_SummonSpawn_ultraSmnInceptor", PowerUpSummonSpawnAbility,
         TriggeredAbilityType.PowerUp_SummonSpawn_ultraSmnInceptor),
        ("PowerUp_SummonSpawn_ultraSmnHeavyIntercessor", PowerUpSummonSpawnAbility,
         TriggeredAbilityType.PowerUp_SummonSpawn_ultraSmnHeavyIntercessor),
        ("PowerUp_SummonSpawn_bloodSmnIntercessor", PowerUpSummonSpawnAbility,
         TriggeredAbilityType.PowerUp_SummonSpawn_bloodSmnIntercessor),
        ("PowerUp_SummonSpawn_darkaSmnHellblaster", PowerUpSummonSpawnAbility,
         TriggeredAbilityType.PowerUp_SummonSpawn_darkaSmnHellblaster),
        ("PowerUp_SummonSpawn_darkaSmnTerminator", PowerUpSummonSpawnAbility,
         TriggeredAbilityType.PowerUp_SummonSpawn_darkaSmnTerminator),
        ("PowerUp_SummonSpawn_templSmnAggressor", PowerUpSummonSpawnAbility,
         TriggeredAbilityType.PowerUp_SummonSpawn_templSmnAggressor),
    )
}
