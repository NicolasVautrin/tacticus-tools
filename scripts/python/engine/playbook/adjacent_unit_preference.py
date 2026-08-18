"""Famille `AdjacentUnitPreferenceTriggeredAbilityPlaybook` — utilité de MOUVEMENT des abilities DÉCLENCHÉES.

Native (ghidra gqfc5mff6c, case-36) : la feuille de tuile `TriggeredAbilitiesUtility(2)` (dispatcher,
`engine/utilities/tile.py`) itère les abilities DE L'UNITÉ QUI BOUGE (`case.unit@0x10` →
AbilitiesComponent), charge le playbook SINGLETON PAR TYPE d'ability (`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` : cache dict@0x90 + factories dict@0x88, clef = ability type) et somme leurs
`ITriggeredAbilityPlaybook.CalculateMovementUtilityInSteps` (Fix64).

Corps commun `AdjacentUnitPreferenceTriggeredAbilityPlaybook.<CalculateMovementUtilityInStepsInternal>
IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` :

    owner    = case.unit ; playerId = OwnerComponent.get_CurrentPlayerEntityId(owner)
    adjacent = IBattleQuery.<slot 0x81>(caseTile, playerId) MINUS self      (amis R1 de la tuile)
    n1       = Min(count(filtre vtbl+0x248), cap vtbl+0x228)
    val      = Σ_{i<n1} weightAdjacent(u_i, ctx)                            (vtbl+0x208)
    surround = IBattleQuery.<slot 0x7d>(caseTile, playerId, 0)              (amis R2)
    n2       = Min(count(filtre vtbl+0x258), cap vtbl+0x238)
    val     += Σ_{i<n2} weightSurrounding(u_i, ctx)                         (vtbl+0x218)
    yield Fix64.FromInt(val)

Les CONCRETS (~25 classes `IdunBattle.AI.Playbook.Loki.*Playbook`, base intermédiaire
`AdjacentToOwnerNonOwnerPlaybook<T>..IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`) overrident `GetAdjacentFriendUtility` /
`GetAdjacentEnemyUtility` = LOOKUP CONFIG PLAT `Utilities.Default.TriggeredAbilities[<clé>]`, l'unité
passée est IGNORÉE — ex. `IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$GetAdjacentFriendUtility` invoque le
délégué de lookup avec la string `"GuardianOrganism_AdjacentFriend"` (=30 BC).

Caps (vtbl+0x228/0x238) : PORTÉS depuis #212 (`MAX_ADJACENT_FRIENDS`/`MAX_ADJACENT_ENEMIES`). Les
corps sont des getters TRIVIAUX que l'ICF a fondus, donc SANS symbole propre — invisibles à
`search_symbols_by_name`, exactement le faux négatif que documente le CLAUDE.md. On les lit par le
bloc `methodPointers` du PE (`probe_8889_methodptr_vtable.py`) : les méthodes d'un type y sont
CONTIGUËS dans l'ordre des slots, et le corps fondu se lit comme n'importe quel autre. Résultat sur
les 11 concrets de ce module : **2 seulement** overrident le cap amis, et à 1 —
`SpiritualLeaderPlaybook` (mesuré liant, #212) et `FabricatorClawArrayPlaybook` (même corps fondu,
jamais mis en défaut live faute d'un montage à >=2 amis Mechanical adjacents : résidu #212 §7).
Poids surrounding :
défaut base = 0 (confirmé 909 : (4,2)=30 exactement alors que u87/u91 sont en ring-2 — s'ils
comptaient, le score dépasserait 30) ; seules les classes qui overrident (StandVigil & co, corps
propres) comptent.

Cas d'origine : `docs/rl/case-36-triggered-abilities-move.md` — 909 s4/s19, u89 tyranTyrantGuard
(passif GuardianOrganism 1181) : TrigAb = 30 × #amis-adjacents-à-la-tuile → 30/90 EXACTS vs L3.
"""
from __future__ import annotations

from .. import battle_query as bq
# Forme B (module + acces attributaire, cf. CLAUDE.md) : foyer UNIQUE du predicat
# `WeaponsComponent$$HasRangedWeapon`, partage avec le selecteur DSL `UnitsWithoutRangedWeapons`.
from ..services import battle_query as _sbq

from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_faction import UnitFaction
from ..runner.abilities.deathguard import cursed_plague_bell_damage_profile


class AdjacentUnitPreferenceTriggeredAbilityPlaybook:
    """Base : Σ poids sur AMIS R1 (adjacents) + Σ poids sur ENNEMIS R1 (adjacents) de la tuile candidate.

    Corps natif `<CalculateMovementUtilityInStepsInternal>IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` (#57i) : DEUX branches,
    toutes deux à DISTANCE 1 de la tuile candidate (PAS adjacent+surrounding — verdict corrigé par le
    comptage d'args de la query interface : GetAdjacentFriends=this+2, GetAdjacentEnemies=this+3,
    GetSurrounding*=this+4) :
      B1 = IBattleQuery.GetAdjacentFriends(caseTile, playerId) MINUS self  (slot 0x81, this+2 args)
           filtre vtbl+0x248 (défaut identité) ; cap vtbl+0x228 (jamais liante <=6 voisins) ;
           Σ get_adjacent_friend_utility (vtbl+0x208)
      B2 = IBattleQuery.GetAdjacentEnemies(caseTile, playerId, false)      (slot 0x7d, this+3 args)
           filtre vtbl+0x258 (défaut identité) ; cap vtbl+0x238 ;
           Σ get_adjacent_enemy_utility (vtbl+0x218)
      yield Fix64.FromInt(val)
    Les poids (vtbl+0x208/0x218) sont `Utilities.Default.TriggeredAbilities[<clé>]`, mais la SIGNATURE
    native est `GetAdjacent{Friend,Enemy}Utility(unit, ctx)` : le voisin est un ARGUMENT, et trois
    formes coexistent au décompilé —
      * LOOKUP PLAT, argument ignoré : `IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$GetAdjacentEnemyUtility`, `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$GetAdjacentFriendUtility`,
        `IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$GetAdjacentFriendUtility`, `IdunBattle.AI.Playbook.Loki.RitesOfBattlePlaybook$$GetAdjacentFriendUtility` (les 4 concrets portés avant #193c) ;
      * GATE sur le voisin, UN poids : `IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$GetAdjacentFriendUtility`
        (`HasFaction(u, 10)` sinon 0), `IdunBattle.AI.Playbook.Loki.DeathwingPlaybook$$GetAdjacentFriendUtility`, `IdunBattle.AI.Playbook.Loki.TaintedNartheciumPlaybook$$GetAdjacentFriendUtility` ;
      * DEUX poids selon le voisin : `IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$GetAdjacentEnemyUtility`
        (`HasRangedWeapon(u) ? _AdjacentEnemyRanged : _AdjacentEnemyDefault`), `IdunBattle.AI.Playbook.Loki.ExplosiveMaladiesPlaybook$$GetAdjacentFriendUtility`.
    ⚠ La 3e forme n'est PAS exprimable par un `FilterAdjacent*` (qui ne sait que garder ou jeter) :
    c'est le poids lui-même qui varie. D'où l'argument `unit` sur les deux accesseurs.
    L'ancien modèle (amis R1+R2) rendait EXACT pour GuardianOrganism/RitesOfBattle (poids surrounding
    + enemy = 0) mais RATAIT la branche ennemis — d'où MartialApotheosis(1045) muet (#57i : miss S14 12345).

    Signature du dispatcher (#32) : `calculate_movement_utility_in_steps(tile, ctx, wt)` où `ctx` = le dict
    par-décision `tile_leaf_ctx` (mirror du natif qui passe le CASE entier — chaque famille y lit ses clés :
    ici `friend_units`/`enemy_units` = {pos,traits} vivants self-exclu ; `FuryOfTheAncientsPlaybook` lit
    `enemies`/`scene`/…)."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:   # vtbl+0x208 (défaut base : 0)
        return 0.0

    def get_adjacent_enemy_utility(self, unit: dict, wt) -> float:    # vtbl+0x218 (défaut base : 0)
        return 0.0

    def filter_adjacent_friend(self, unit: dict, ctx: dict) -> bool:   # vtbl+0x248 (défaut : identité)
        return True

    def filter_adjacent_enemy(self, unit: dict, ctx: dict) -> bool:    # vtbl+0x258 (défaut : identité)
        return True

    # CAPS `vtbl+0x228` (amis) / `vtbl+0x238` (ennemis) — le corps commun fait
    # `n = Min(count(<liste FILTRÉE>), cap)` puis ne somme que les `n` PREMIERS éléments.
    # `None` = « le concret n'override pas le slot » : le défaut de la base n'a jamais été lu, mais
    # il est forcément >= 3 (`GuardianOrganismPlaybook`, qui ne l'override pas, somme bien 3 amis —
    # case-36 : 30/90 exacts). On ne borne donc pas quand le concret est muet, au lieu d'inventer une
    # valeur de base.
    MAX_ADJACENT_FRIENDS: "int | None" = None    # vtbl+0x228
    MAX_ADJACENT_ENEMIES: "int | None" = None    # vtbl+0x238

    @staticmethod
    def _capped(units: list, cap) -> list:
        """`Min(count, cap)` PUIS les `n` premiers (mirror du `for (i = 0; i < Min(...); i++)`).

        Quand le poids est un LOOKUP PLAT (l'accesseur ignore son argument), quels éléments sont
        retenus n'a aucune importance — seul leur NOMBRE compte, donc l'ordre d'énumération natif de
        `GetAdjacentFriends` n'a pas à être répliqué. Ce serait à re-regarder le jour où un concret
        combinerait un cap ET un accesseur qui lit son `unit` : aucun ne le fait dans ce build (les
        deux seuls porteurs de cap, `FabricatorClawArrayPlaybook` et `SpiritualLeaderPlaybook`, ont
        un accesseur plat)."""
        return units if cap is None else units[:max(0, int(cap))]

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        # Le poids est demandé PAR UNITÉ VOISINE, à l'intérieur de la boucle — c'est la forme du
        # corps commun natif (`val += virt_0x208(this, u_i, ctx)` pour chaque `u_i` retenu), et ce
        # n'est PAS une équivalence : `IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$
        # GetAdjacentEnemyUtility` rend DEUX poids différents selon `HasRangedWeapon(u_i)`, et
        # `IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$GetAdjacentFriendUtility` rend 0
        # pour un ami hors faction. Hisser l'appel hors de la boucle (ce que faisait ce port tant
        # que les 4 seuls concrets portés étaient des lookups PLATS) rend un terme faux dès qu'un
        # override lit son argument `unit`.
        ctx = ctx or {}
        val = 0.0
        # ADJACENCE NATIVE, pas hexgeo nu (#271). `IBattleQuery.GetAdjacent{Friends,Enemies}` passe
        # par `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui
        # applique un gate INCONDITIONNEL `abs(elev(tuile) - elev(voisin)) < 2` : deux tuiles
        # cote a cote mais separees de 2 niveaux ne sont PAS voisines pour le natif. `battle_query.
        # is_adjacent` porte ce gate ; `hexgeo.distance == 1` seul SUR-COMPTE.
        # ⚠ MESURE (#271, `probe_271_kustom_force_field_reworked.py --adjacency`) : sur le voisinage
        # NATIF (`boardGraph`) de TROIS boards, `bq.is_adjacent` est EXACT — **0 faux sur 4 963
        # paires** (MC1_67 1953, C4_09 2415, C1_25 595) — la ou `hexgeo.distance == 1` seul se
        # trompe 9 / 22 / 2 fois, TOUJOURS dans le sens PERMISSIF (le voisinage natif est un
        # SOUS-ENSEMBLE de hexgeo). Le trou etait invisible parce qu'il ne mord qu'au bord d'une
        # marche d'elevation >= 2 — et c'est exactement ce qui a d'abord fait rendre a l'A/B de
        # #271 un faux « le natif n'applique pas le terme », y compris sur `GuardianOrganism`.
        elev = ctx.get("elev_by_pos")
        neigh = bq.neigh_map(ctx)
        friends = [u for u in (ctx.get("friend_units") or ())
                   if bq.is_adjacent(tile, u["pos"], elev, neigh) and self.filter_adjacent_friend(u, ctx)]
        for u in self._capped(friends, self.MAX_ADJACENT_FRIENDS):
            val += self.get_adjacent_friend_utility(u, wt)
        enemies = [u for u in (ctx.get("enemy_units") or ())
                   if bq.is_adjacent(tile, u["pos"], elev, neigh) and self.filter_adjacent_enemy(u, ctx)]
        for u in self._capped(enemies, self.MAX_ADJACENT_ENEMIES):
            val += self.get_adjacent_enemy_utility(u, wt)
        return val


class AdjacentToOwnerNonOwnerPlaybook(AdjacentUnitPreferenceTriggeredAbilityPlaybook):
    """Base intermédiaire des concrets (`..IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`). Porte AUSSI la face NON-OWNER
    (`<CalculateMovementUtilityInSteps>d__2 IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` : poids UNIQUE gaté « tuile adjacente au
    porteur ») consommée par la feuille TriggeredAbilitiesNonOwner(4) — NON portée (=0 observé 909 ;
    config séparée `Utilities.Default.TriggeredAbilitiesNonOwner`, 25 clés)."""


class GuardianOrganismPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`GuardianOrganismPlaybook` (`..IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$.ctor` : ability 0x49d=1181 GuardianOrganism — passif
    Tyrant Guard). `IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$GetAdjacentFriendUtility` = TriggeredAbilities
    ["GuardianOrganism_AdjacentFriend"] (=30 BC) — LOOKUP PLAT : l'argument `unit` du natif n'est
    lu par AUCUNE instruction du corps (relu au décompilé #193c)."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "GuardianOrganism_AdjacentFriend")


class MedicusMinistorumPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`MedicusMinistorumPlaybook` (`IdunBattle.AI.Playbook.Loki.MedicusMinistorumPlaybook$$.ctor` :
    ability 0x42d = 1069 MedicusMinistorum -- passif d'`adeptHospitaller` << Isabella >>). Le `.ctor`
    delegue a `IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybook<...>$$.ctor(this, 0x42d, ...)`
    -- la base est LUE dans `classes.tsv`, pas deduite du nom.

    `IdunBattle.AI.Playbook.Loki.MedicusMinistorumPlaybook$$GetAdjacentFriendUtility` =
    TriggeredAbilities["MEDICUSMINISTORUM_AdjacentFriend"] -- **LOOKUP PLAT** : le corps ENTIER est
    l'appel `getUtilityVal(<literal>)` suivi du `return`, et le parametre `friend` n'est lu par
    AUCUNE instruction (relu au decompile sur `rnca9r7q6c`). La clef est le literal `0x33ca658` de
    `metadata/string_literals.tsv`, LU et non reconstruit depuis le nom de l'ability -- la casse
    (`MEDICUSMINISTORUM` en capitales, comme `RITESOFBATTLE` et contrairement a
    `GuardianOrganism`) n'est pas derivable.

    Aucun `GetAdjacentEnemyUtility` propre (la classe n'a que **2** corps dans `methods.tsv` :
    `.ctor` et `GetAdjacentFriendUtility`) -> la branche ENNEMIS garde le 0.0 de la base."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "MEDICUSMINISTORUM_AdjacentFriend")


class RitesOfBattlePlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`RitesOfBattlePlaybook` (`..IdunBattle.AI.Playbook.Loki.RitesOfBattlePlaybook$$.ctor` : ability 0x3f6=1014 RitesOfBattle — passif aura
    ultraCalgar). `IdunBattle.AI.Playbook.Loki.RitesOfBattlePlaybook$$GetAdjacentFriendUtility` = TriggeredAbilities
    ["RITESOFBATTLE_AdjacentFriend"] (=10 BC) — LOOKUP PLAT (argument `unit` non lu, relu #193c).
    Case-49 résiduel (31337) : ce terme
    manquant faussait les Tile7 de u87 → miss move s3 ((2,2) vs (3,2)) ET miss CIBLE s14
    (l'argmax attaque u_full = paire + Tile7 flippait vers 79@(4,3) au lieu de 81@(3,4))."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "RITESOFBATTLE_AdjacentFriend")


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` : singleton par TYPE d'ability. Seuls les types dont le
# playbook CONTRIBUE au mouvement sont enregistrés — les autres (playbooks de cast Comparable/
# NonComparable ; base `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps`) yield 0
# nativement : absence du registre == 0, même dégradation. Étendre en portant les autres concrets
# `GetAdjacent{Friend,Enemy}Utility` (~25, mêmes 3 lignes chacun) quand un case les montre décisifs.
# Le registre accueille TOUTE famille de playbook move-relevant (protocole = la méthode
# `calculate_movement_utility_in_steps(tile, ctx, wt)`) — pas seulement AdjacentUnitPreference :
# `FuryOfTheAncientsPlaybook` (#32) est de la famille `TriggeredAbilityPlaybook<T>` (ennemis
# adjacents + prédiction de dégât), module `fury_of_the_ancients.py`.
class MartialApotheosisPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`MartialApotheosisPlaybook` (`..IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$.ctor` : ability 0x415=1045 MartialApotheosis — passif
    necroOverlord). `IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$GetAdjacentEnemyUtility` = TriggeredAbilities["MARTIALAPOTHEOSIS_AdjacentEnemy"]
    (=15 BC) — LOOKUP PLAT (argument `unit` non lu, relu #193c) ; branche ENNEMIS R1 (B2). Pas de
    filtre custom (défaut identité). #57i :
    12345 s14, u87 préfère (3,5) [3 ennemis adjacents -> +45] a (4,3) [0] -> flip cible 69->t77."""

    def get_adjacent_enemy_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "MARTIALAPOTHEOSIS_AdjacentEnemy")


class FabricatorClawArrayPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`FabricatorClawArrayPlaybook` (`..IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$.ctor` : ability 0x3ee=1006 FabricatorClawArray — passif
    necroSpyder). `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$GetAdjacentFriendUtility` = TriggeredAbilities["FABRICATORCLAWARRAY_AdjacentFriend"]
    (=30 BC) — LOOKUP PLAT (argument `unit` non lu, relu #193c) ; branche AMIS R1 (B1).
    `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$FilterAdjacentFriends` : garde les amis
    ayant le trait Mechanical (UnitTrait 5) — ICI le tri du voisin est bien dans le FILTRE, pas dans
    l'accesseur de poids. #57i : 2468 s16, u79 préfère (3,4) [1 ami mécanique adjacent
    admecRuststalker -> +30] a (4,2) [0] -> flip cible 69->t89.

    ⚠ LE CAP MORD (`vtbl+0x228` = 1) — MESURÉ (#242, deux couples board/seed) : le terme vaut **30
    dès qu'il y a AU MOINS UN ami retenu**, PAS 30 x n. Le corps commun fait
    `n = Min(count(<filtré>), vtbl+0x228)` ; le getter du cap est un corps TRIVIAL fondu par l'ICF
    (`b8 01 00 00 00 c3` = `mov eax,1 ; ret`), donc absent des tables de symboles — lu dans le bloc
    `methodPointers` du PE, où le groupe de cette classe est
    `[.ctor, GetAdjacentFriendUtility, <ret 0>, <ret 1>, FilterAdjacentFriends]`, **exactement** le
    même que `SpiritualLeaderPlaybook` (mêmes deux corps fondus, mêmes positions relatives).
    Confrontation live : `X_nat` vaut **30 pour 1, 2, 3 amis retenus** (`probe_242_fabricator_claw
    _cap.py`). #57i/#193c n'avaient exercé que `n <= 1`, régime où le cap est transparent — aucun de
    leurs verdicts n'était donc contredit, ni ne le confirmait.

    ⚠ ÉTAT DE VALIDATION (`case-242` §7) — le cap EST confronté live (`MC1_67`/777, régime
    `nRep` = 1, 2, 3, `X_nat` plat à 30, build `gqfc5mff6c`), et la RE a été REFAITE au binaire du
    build suivant (`rnca9r7q6c`) : bloc `methodPointers` inchangé, mêmes corps fondus aux mêmes
    positions. La garde `tests/engine/test_fabricator_claw_cap_live.py` y passe (10/10) et rougit
    bien quand on retire le cap (2 échecs, `n = 4 -> 120`) sur les DEUX montages.
    Reste NON CONFRONTÉ : un second couple board/seed discriminant au NATIF (`C4_09`/31337 plafonne
    à UN allié blessé, régime où tout cap `>= 1` donne le même résultat). `X_nat` n'est pas
    re-mesurable sur `rnca9r7q6c` sans réinjection — les hooks de `scorer-damage-trace` portent des
    RVA `gqfc5mff6c` ; la voie « argmax sans hook » a été tentée et ne conclut pas (`case-242` §7.4).

    ⚠ RÉSIDU MESURÉ, NON PORTÉ — le filtre natif a un SECOND gate que ce port n'applique pas :

        HasTrait(u, 5) && IBattleQuery.<slot 0x2f = CanBeRepaired>(u, false)

    `IdunBattle.Core.Services.BattleQuery$$CanBeRepaired` délègue à
    `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired`, dont les branches ACTIVES sous ces
    arguments (attacker null, `checkGroupLimit` false, `includeNegativeEffects` false) sont :
    `!EntityExtensions.IsMachine(u)` ET (`AttackQuery.IsDamagedUnit(u)` — soit
    `HealthComponent.IsWounded`, hp < hpMax — OU `UnitExtensions.GetStat(u, 4, 4) > 0`) ET
    `!UnitExtensions.HasHealBlockers(u)` ET `UnitExtensions.IsAffectedByHealType(u, 1)` (cette
    dernière est automatiquement vraie ici : le trait Mechanical implique `IsMechanical`).
    Conséquence MESURÉE : un ami Mechanical à PV PLEINS ne compte pas — `nMech=1, nRep=0 -> X_nat=0`
    alors que ce port rend 30. Le porter demande `hp`/`hp_max` dans les `friend_units` du
    `tile_leaf_ctx` (deux clés à ajouter dans `engine/utilities/tile.py::_adjacent_units`, fichier
    hors périmètre de #242). Poser le cap sans ce gate est strictement moins faux : sur les 6
    régimes mesurés, il corrige 3 tuiles et n'en dégrade aucune.
    ⚠ `StatType` 4 = `Armor`, et la branche `GetStat(u, 4, …) > 0` était ÉTEINTE par le montage
    (`--hp-target`/`--hp-player` mettent `Armor` ET `FixedArmor` à 0) ; le second littéral n'est pas
    qualifié. Le gate OBSERVÉ se réduit donc à `IsWounded`, mais hors de ce régime il peut être PLUS
    permissif : ne pas porter « blessé » seul sans relire ce prédicat."""
    MAX_ADJACENT_FRIENDS = 1                                       # vtbl+0x228 : `mov eax,1 ; ret`

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "FABRICATORCLAWARRAY_AdjacentFriend")

    def filter_adjacent_friend(self, unit: dict, ctx: dict) -> bool:
        return "Mechanical" in (unit.get("traits") or ())          # HasTrait(u, 5) ; cf. ⚠ ci-dessus


def _unit_faction(unit: dict) -> str | None:
    """`IdunBattle.Entities.UnitExtensions$$HasFaction(u, <UnitFaction>)` côté offline.

    Le natif ne compare PAS un entier : il fait `System.Enum.ToString(UnitFaction)` puis
    `String.Equals` avec le champ `FactionComponent+0x30`. La faction est donc une CHAÎNE, et le
    pendant offline est le `FactionId` du gameconfig (`UnitFaction.DarkAngels` = 10 <-> `"DarkAngels"`,
    cf. `IdunBattle.Entities.Enum.UnitFaction` dans `data/symbols/<build>/frida/enums.tsv`).
    Même substrat que `engine/entities/selectors/units.py::UnitsFromFaction`."""
    import gameconfig as GC
    return (GC.unit(unit.get("vis") or "") or {}).get("FactionId")


def _unit_weapons(unit: dict) -> tuple:
    """Le `List<WeaponProfile>` que le natif lit sur le `WeaponsComponent` du voisin.

    Le natif passe par le composant ECS ; le pendant offline est le `weapons` du gameconfig. Ce
    n'est PAS une approximation de commodité : `UnitConfiguration.Weapons` du BattleConfiguration
    (ce que la bataille consomme) est le décalque du gameconfig — mesuré sur `data/seed-bc.json`,
    **246 armes / 175 unités, 0 divergence** sur `DamageProfileType` ET sur `IsMelee`
    (`probe_211_cursed_plague_bell.py --offline-only`). Ce que ce substrat ne voit pas, ce sont les armes
    AJOUTÉES/MODIFIÉES en cours de bataille par un effet — même limite que `_unit_faction`."""
    import gameconfig as GC
    return tuple(((GC.unit(unit.get("vis") or "") or {}).get("weapons")) or ())


def _weapon_is_melee(w: dict) -> bool:
    """`IdunShared.Battle.WeaponProfile$$get_IsMelee` = `!Range.HasValue || Range.Value < 2` : une
    arme SANS `Range` est melee, et **`Range == 1` le serait aussi**. Le seuil est donc `>= 2`, pas
    « `Range` présent » — les deux coïncident sur ce gameconfig (0 arme à `Range == 1`, compté), mais
    c'est le décompilé qui fait foi, pas la coïncidence."""
    r = w.get("Range")
    return r is None or int(r) < 2


def _has_ranged_weapon(unit: dict) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasRangedWeapon(u, minRange=null)` ->
    `IdunBattle.Entities.Components.WeaponsComponent$$HasRangedWeapon` : `true` dès qu'UNE arme
    n'est pas `IsMelee` (le `minRange` nul court-circuite la comparaison de portée).

    DÉLÈGUE au foyer UNIQUE `engine.services.battle_query.has_ranged_weapon` (#601) : le sélecteur
    DSL (`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithoutRangedWeapons` -- REPLIE SUR UNE SEULE
    LIGNE : coupe en deux par le retour a la ligne, il etait INGREPABLE, #1032-r3)
    consomme le MÊME prédicat natif, et deux implémentations du même corps auraient été un
    fork de port. Forme B (`import <module>` + accès attributaire) : un `monkeypatch.setattr` sur le
    foyer MORD toujours, ce qu'une liaison `from X import f` au niveau module gèlerait.
    L'adaptation de signature reste ici : ce site tient un DICT d'unité (`vis`), le foyer un
    `visualId` — même clé gameconfig."""
    return _sbq.has_ranged_weapon(unit.get("vis") or "")


class FearedInterrogatorPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`FearedInterrogatorPlaybook` (`IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$.ctor` :
    ability 0x4d3=1235 FearedInterrogator — passif `darkaAsmodai`).

    `IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$GetAdjacentFriendUtility` :

        if (!UnitExtensions.HasFaction(unit, 10)) return 0;      // UnitFaction.DarkAngels
        return ctx["FearedInterrogator_AdjacentDAFriend"];        // 30 BC

    Le gate est DANS l'accesseur de poids, pas dans un `FilterAdjacentFriends` (le natif n'en
    override aucun) : le port le mirror au même endroit. Terme = 30 x #amis DarkAngels à R1 de la
    tuile candidate — non constant dès que deux tuiles candidates n'ont pas le même nombre de
    voisins Dark Angels."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        if _unit_faction(unit) != "DarkAngels":                   # HasFaction(unit, 10)
            return 0.0
        return wt.sub("TriggeredAbilities", "FearedInterrogator_AdjacentDAFriend")


class HatefulAssaultPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`HatefulAssaultPlaybook` (`IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$.ctor` :
    ability 0x40e=1038 HatefulAssault — passif `blackTerminator`).

    `IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$GetAdjacentEnemyUtility` :

        return UnitExtensions.HasRangedWeapon(unit)
             ? ctx["HATEFULASSAULT_AdjacentEnemyRanged"]          // 20 BC
             : ctx["HATEFULASSAULT_AdjacentEnemyDefault"];        // 10 BC

    DEUX poids selon le voisin : c'est le concret qui rend l'argument `unit` indispensable (aucun
    filtre ne peut l'exprimer). Branche ENNEMIS R1 (B2), aucun `FilterAdjacentEnemies` override.
    Terme = 20 x #ennemis à arme de portée à R1 + 10 x #ennemis melee à R1 — il départage donc deux
    tuiles à MÊME nombre d'ennemis adjacents, ce qu'aucun poids unique ne peut faire."""

    def get_adjacent_enemy_utility(self, unit: dict, wt) -> float:
        key = ("HATEFULASSAULT_AdjacentEnemyRanged" if _has_ranged_weapon(unit)
               else "HATEFULASSAULT_AdjacentEnemyDefault")
        return wt.sub("TriggeredAbilities", key)


# Les trois traits que `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` DÉRIVE du `GrandAllianceId`
# (`UnitTrait` : Imperial=26=0x1a, Xenos=1006=0x3ee, Chaos=2026=0x7ea) — homonymes de l'id d'alliance.
# Ils ne sont PAS dans le `traits` du gameconfig : c'est le BattleConfiguration qui les ajoute, et
# `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` recopie ce `UnitConfiguration.Traits`
# (config+0xd0) dans le `BaseUnitComponent.Traits` (+0x40) que `HasTrait` interroge. Mesuré sur
# `data/seed-bc.json` : les 175 unités ont EXACTEMENT ce trait en plus de leur `traits` gameconfig.
_GRAND_ALLIANCE_TRAITS = frozenset(("Imperial", "Xenos", "Chaos"))


def _has_trait(unit: dict, trait: str) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(u, <UnitTrait>)` ->
    `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` :

        if (RemovedTraits(+0x50).Contains(t)) return false;
        return Traits(+0x40).Contains(t) || AddedTraits(+0x48).Contains(t);

    Côté offline, `unit["traits"]` (gameconfig) couvre `Traits(+0x40)` SAUF le trait d'alliance,
    qui n'existe que dans le BC — d'où la seconde branche. Les traits accordés/retirés en cours de
    bataille (`AddTraitOperation`, +0x48/+0x50) ne sont pas dans ce substrat : même limite que
    `_unit_faction`, et même limite que le `filter_adjacent_friend` de `FabricatorClawArrayPlaybook`
    qui lit déjà `unit["traits"]`."""
    if trait in (unit.get("traits") or ()):
        return True
    if trait not in _GRAND_ALLIANCE_TRAITS:
        return False
    import gameconfig as GC
    return (GC.unit(unit.get("vis") or "") or {}).get("GrandAllianceId") == trait


def _cursed_plague_bell_damage_profile() -> str:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$GetDamageProfile`
    = `AbilityConfiguration.GetAffectedDamageProfile().GetValueOrDefault(<DamageProfileType>)`, où le
    littéral de défaut lu au décompilé est `0xd` = 13 = `Psychic`
    (`IdunBattle.Entities.Enum.DamageProfileType`).

    DÉLÈGUE au foyer UNIQUE `runner.abilities.deathguard.cursed_plague_bell_damage_profile` (case-224
    item 5) : le natif n'a qu'UN `GetDamageProfile`, et il a désormais DEUX consommateurs portés —
    ce prédicat de playbook (`b__4_0`) et le `damageProfile` de l'`AttackWithAttackDamage` de
    `CursedPlagueBellAttackAbility$$CreateBehaviour`. Deux copies offline d'un seul nœud natif
    seraient le fork que la doctrine `check-own-port` interdit. Import paresseux : la dépendance
    établie du dépôt va playbook -> runner (jamais l'inverse)."""
    return cursed_plague_bell_damage_profile()


class CursedPlagueBellPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`CursedPlagueBellPlaybook` (`IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$.ctor` :
    ability 0x42f=1071 CursedPlagueBell — passif `deathBlightbringer`/Corrodius, HERO du pool).

    Les DEUX faces sont surchargées, et chacune LIT son argument `unit` :

    `IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$GetAdjacentFriendUtility` :

        if (!UnitExtensions.HasTrait(unit, 0x7ea)) return 0;      // UnitTrait.Chaos
        return ctx["CursedPlagueBell_AdjacentChaosFriend"];        // 20 BC

    `IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$GetAdjacentEnemyUtility` :

        weapons = unit.<WeaponsComponent>.Weapons;
        if (!Enumerable.Any(weapons, this.<GetAdjacentEnemyUtility>b__4_0)) return 0;
        return ctx["CursedPlagueBell_AdjacentPsychicEnemy"];       // 10 BC

    avec `IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$u003CGetAdjacentEnemyUtilityu003Eb__4_0` :

        return w.DamageProfile == _ability.GetDamageProfile() && w.IsMelee;

    ⚠ Le prédicat exige les DEUX conditions : profil `Psychic` ET arme de MÊLÉE. Un psyker à arme
    psychique de PORTÉE (`Range >= 2`) ne compte pas — c'est ce que le seuil de
    `IdunShared.Battle.WeaponProfile$$get_IsMelee` tranche, et c'est le piège de cet item : le nom de
    la clé BC (`..._AdjacentPsychicEnemy`) ne dit RIEN de la contrainte de mêlée.
    ⚠ Le poids ne s'applique qu'UNE FOIS par voisin (`Any`, pas `Count`) même si le voisin porte
    plusieurs armes melee Psychic.

    Aucun `FilterAdjacent*` n'est surchargé : le bloc de code de la classe est CONTIGU
    (`GetAdjacentEnemyUtility`, `GetAdjacentFriendUtility`, `b__4_0`, `.ctor`) entre les blocs
    `CosmicHorrorPlaybook` et `DaRevolushunPlaybook`, sans trou. Pas de
    `CalculateAttackUtilityInStepsInternal` non plus : ce playbook ne pèse QUE le mouvement."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        if not _has_trait(unit, "Chaos"):                          # HasTrait(unit, 0x7ea)
            return 0.0
        return wt.sub("TriggeredAbilities", "CursedPlagueBell_AdjacentChaosFriend")

    def get_adjacent_enemy_utility(self, unit: dict, wt) -> float:
        profile = _cursed_plague_bell_damage_profile()
        if not any(w.get("DamageProfile") == profile and _weapon_is_melee(w)
                   for w in _unit_weapons(unit)):                  # Enumerable.Any(.., b__4_0)
            return 0.0
        return wt.sub("TriggeredAbilities", "CursedPlagueBell_AdjacentPsychicEnemy")


class SpiritualLeaderPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`SpiritualLeaderPlaybook` (`IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$.ctor` :
    ability 0x4fb=1275 SpiritualLeader — passif `genesMagus`/Xybia).

    `IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$FilterAdjacentFriends` :

        foreach (u in friends) if (UnitExtensions.HasTrait(u, 0x41d)) result.Add(u);

    `IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$GetAdjacentFriendUtility` :

        return ctx["SPIRITUALLDEADER_AdjacentDecoy"];             // 30 BC

    LOOKUP PLAT — l'argument `unit` n'est lu par AUCUNE instruction du corps, qui est identique
    instruction pour instruction à `IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$
    GetAdjacentFriendUtility` (seul le slot de string literal diffère). Le tri du voisin est donc
    DANS LE FILTRE, comme `FabricatorClawArrayPlaybook` — pas dans l'accesseur comme
    `FearedInterrogatorPlaybook`.

    ⚠ La clé BC porte une FAUTE DE FRAPPE du jeu : `SPIRITUALLDEADER_` (L-D-E-A-D-E-R), pas
    `SPIRITUALLEADER_`. `case-193c` §7 l'avait cherchée par préfixe, ne l'avait pas trouvée, et avait
    laissé le terme non résolu. Elle est LUE au décompilé (slot de metadata usage -> string literal de
    `global-metadata.dat`, `scripts/python/probe_212_bc_key_literals.py`), pas devinée — ne pas la
    « corriger » : c'est la clé que la BC porte réellement (`case-212`).

    ⚠ `0x41d = 1053` est **UnitTrait**.Decoy — homonymes à écarter : EffectType 1053 =
    ShadowInTheWarp_LessDmg_Effect, ActiveAbilityType 1053 = DevoutPush, TriggeredAbilityType 1053 =
    BroodProgenitor. Même enum que la face COMBAT (`runner/operations/triggers/loki/spiritual_leader.py`).

    ⚠ LE CAP MORD (`vtbl+0x228` = 1) : le terme vaut **30 dès qu'il y a AU MOINS UN decoy adjacent**,
    PAS 30 x n. Le corps commun fait `n = Min(count(<filtré>), vtbl+0x228)` ; le getter du cap est un
    corps TRIVIAL fondu par l'ICF (`b8 01 00 00 00 c3` = `mov eax,1 ; ret`), donc absent des tables de
    symboles — lu dans le bloc `methodPointers` du PE, où le groupe de méthodes de cette classe est
    `[.ctor, GetAdjacentFriendUtility, <ret 0>, <ret 1>, FilterAdjacentFriends]`, soit exactement
    l'ordre des slots `0x208, 0x218, 0x228, 0x248`. Corroboré live : `X_nat` vaut 30 pour 1, 2 ET 3
    decoys adjacents (#212 §6). Sur les 11 concrets du module, seuls ce playbook et
    `FabricatorClawArrayPlaybook` portent ce corps `<ret 1>` — les 9 autres n'ont que `<ret 0>`
    (la face d'utilité NON surchargée), et `CursedPlagueBellPlaybook`, qui surcharge les DEUX faces,
    n'en a aucun.

    Terme = 30 si >=1 decoy ALLIÉ à distance 1 de la tuile candidate, sinon 0. Aucune face ENNEMIS
    surchargée (défaut base = 0), aucun `FilterAdjacentEnemies`."""
    MAX_ADJACENT_FRIENDS = 1                                       # vtbl+0x228 : `mov eax,1 ; ret`

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "SPIRITUALLDEADER_AdjacentDecoy")

    def filter_adjacent_friend(self, unit: dict, ctx: dict) -> bool:
        return _has_trait(unit, "Decoy")                           # HasTrait(u, 0x41d = 1053)


class KustomForceFieldReworkedPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`KustomForceFieldReworkedPlaybook` (`IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedPlaybook$$.ctor` :
    ability `0x60b` = 1547 `KustomForceFieldReworked` — passif d'`orksBigMek`, HERO du pool).

    `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedPlaybook$$GetAdjacentFriendUtility` :

        int v = ctx["KustomForceFieldReworked_LikesAdjacentFriends"];   // 10 (gameconfig VIVANT)
        if (UnitExtensions.HasFaction(unit, 5)) v *= 2;                 // UnitFaction.Orks
        return v;

    ⚠ Le facteur 2 est un `imul` du littéral, PAS un second poids BC — rien à chercher dans la
    table. Le gate est DANS l'accesseur (comme `FearedInterrogatorPlaybook`), pas dans un
    `FilterAdjacentFriends` : le natif n'en override AUCUN. Lu au bloc `methodPointers` du PE, le
    groupe de cette classe est `[.ctor, GetAdjacentFriendUtility, <ret 0>]` — strictement le même
    que `GuardianOrganismPlaybook` (donc ni cap `vtbl+0x228`, ni filtre `vtbl+0x248` : les corps
    `<ret 1>` et `FilterAdjacentFriends` que porte `SpiritualLeaderPlaybook` sont ABSENTS ici).

    Terme = 10 × #amis NON-Orks à R1 de la tuile candidate + 20 × #amis Orks à R1. Il départage
    donc deux tuiles à MÊME nombre d'amis adjacents dès que leurs factions diffèrent — ce qu'aucun
    poids unique ne peut faire.

    ⚠ POURQUOI CE TERME N'EXISTAIT PAS AVANT (#271) : la clé valait **0** dans la table
    `BC.Utilities` de la CAPTURE (`data/seed-bc.json`), et **10** au gameconfig VIVANT. Tant que le
    natif et le moteur lisaient tous deux la capture, ils étaient d'accord — et faux tous les deux.
    Le refresh `catalog_inject.refresh_ai_utilities` (mergé `dd129216`) sert désormais les poids
    vivants aux DEUX côtés, ce qui a démasqué le terme. Une mesure d'A/B menée avant ce refresh
    aurait rendu « aucun écart », et l'aurait conclu à tort inerte."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        v = float(wt.sub("TriggeredAbilities", "KustomForceFieldReworked_LikesAdjacentFriends"))
        if _unit_faction(unit) == "Orks":                          # HasFaction(unit, 5)
            v *= 2.0
        return v


class IconOfObstinacyPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IconOfObstinacyPlaybook` (`IdunBattle.AI.Playbook.Loki.IconOfObstinacyPlaybook$$.ctor` :
    littéral `0x610` = 1552 `IconOfObstinacy` — passif d'`astarLysander`, HERO hors pool par défaut).

    `IdunBattle.AI.Playbook.Loki.IconOfObstinacyPlaybook$$GetAdjacentFriendUtility` :

        if (!UnitExtensions.HasTrait(friend, 0x40f)) return 0;   // UnitTrait.TerminatorArmour
        return GetUtilityValue("IconOfObstinacy_LikesAdjacentTerminatorFriends");

    Le gate est DANS l'accesseur de poids (forme `FearedInterrogatorPlaybook`), pas dans un
    `FilterAdjacentFriends` : **le metadata dit que la classe n'en déclare aucun**.

    ⚠ `0x40f` = 1039 = `UnitTrait`.TerminatorArmour — enum QUALIFIÉ, jamais déduit du nom de la clé.
    Homonymes à écarter : `EffectType` 1039 et `ActiveAbilityType` 1039 n'ont rien à voir.

    ⚠ CE QUE LA CLASSE DÉCLARE, LU DANS `global-metadata.dat` (`il2cpp_metadata.type_methods`,
    la même voie que `metadata/non_owner_slot4.tsv`) — et NON déduit de la présence d'un symbole
    ghidra, qui est structurellement aveugle aux corps fondus par l'ICF :

        [.ctor (65535), GetAdjacentFriendUtility (slot 13), GetAdjacentEnemyUtility (slot 14)]

    Le bloc `methodPointers` du PE, ancré sur le `.ctor`, donne dans CE MÊME ORDRE
    `[.ctor, GetAdjacentFriendUtility, <ret 0>]` : le `<ret 0>` est donc
    `GetAdjacentEnemyUtility`, un override EXPLICITE qui rend 0 — sémantiquement identique au
    défaut de la base, d'où l'absence de surcharge ici. **NI cap** (`GetMaxAdjacentFriendsToCount`
    absent du metadata, contrairement à `FabricatorClawArrayPlaybook`/`SpiritualLeaderPlaybook`)
    **NI filtre** (`FilterAdjacentFriends` absent).

    Terme = 20 (gameconfig vivant) x #amis à distance 1 de la tuile candidate PORTANT
    `TerminatorArmour`. Face NON-OWNER de la MÊME ability : `playbook/non_owner.py`
    (`IconOfObstinacyNonOwnerPlaybook`, clé `IconOfObstinacy_TerminatorFriendLikesToBeAdjacent`) —
    les deux faces sont indépendantes et se cumulent sur une même décision de mouvement.

    ⚠ Le paramètre générique du natif est `AdjacentUnitPreferenceTriggeredAbilityPlaybook<
    IconOfObstinacy_AddDamageBuffAbility>` (`frida/classes.tsv`) : c'est la sous-ability du BUFF DE
    DÉGÂT que ce playbook sert, pas celle du buff d'armure (servie, elle, par la face non-owner
    `AdjacentToOwnerNonOwnerPlaybook<IconOfObstinacy_AddArmourBuffAbility>`). Ghidra MISLABELLE le
    `.ctor` gshared en `AdjacentToOwnerNonOwnerPlaybook<...>..ctor` — les deux bases partagent le
    même corps ; c'est `classes.tsv` qui tranche la parenté, jamais le nom du callee."""

    KEY = "IconOfObstinacy_LikesAdjacentTerminatorFriends"          # gameconfig vivant = 20

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        if not _has_trait(unit, UnitTrait.TerminatorArmour.name):   # HasTrait(friend, 0x40f)
            return 0.0
        return float(wt.sub("TriggeredAbilities", self.KEY))


class RedRampagePlaybook(AdjacentUnitPreferenceTriggeredAbilityPlaybook):
    """`RedRampagePlaybook` (`IdunBattle.AI.Playbook.Loki.RedRampagePlaybook` -- passif de kit
    `RedRampage` 0x60f = 1551 de `bloodTerminator` << Cezare >>, #963).

    ⚠ PARENTE LUE dans `frida/classes.tsv` :
    `AdjacentUnitPreferenceTriggeredAbilityPlaybook<...RedRampage_AttackAbility>` -- la base
    DIRECTE, **pas** `AdjacentToOwnerNonOwnerPlaybook` (meme piege de mislabel que `Deathwing` /
    `IconOfObstinacy`). Et le parametre generique dit lequel des DEUX artefacts natifs du kit porte
    la face DECISION : `RedRampage_AttackAbility`, jamais `_BuffAbility`.

    `IdunBattle.AI.Playbook.Loki.RedRampagePlaybook$$GetAdjacentEnemyUtility` -- **LOOKUP PLAT**,
    corps ENTIER relu au decompile :

        return getUtilityVal( <champ statique pose par le .cctor> );

    Le `.cctor` (`RedRampagePlaybook$$.cctor`) ecrit ce champ avec le literal `0x33be408`, LU dans
    `data/symbols/<build>/metadata/string_literals.tsv` = **`"RedRampage_LikesAdjacentEnemies"`**
    (poids BC `Utilities.Default.TriggeredAbilities` = **20**). La cle n'est PAS derivable du nom de
    l'ability : la casse n'est ni celle de `MEDICUSMINISTORUM_` ni celle de `GuardianOrganism` --
    c'est la lecon de `SPIRITUALLDEADER_` (#212).

    Le parametre `enemy` n'est lu par AUCUNE instruction (aucun gate de faction/trait/profil,
    contraste `Deathwing`/`FearedInterrogator`/`CursedPlagueBell`).

    AUCUN `GetAdjacentFriendUtility` propre (`methods.tsv` ne donne a cette classe que
    `GetAdjacentEnemyUtility`, `.ctor` et `.cctor`) -> la branche AMIS garde le 0.0 de la base.

    Terme = 20 x #ennemis a distance 1 de la tuile candidate. Il pousse Cezare a finir son
    deplacement AU CONTACT du plus d'ennemis possible -- exactement ce que son passif recompense
    (`RedRampage_AttackAbility` frappe TOUS les ennemis adjacents a l'arrivee)."""

    def get_adjacent_enemy_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "RedRampage_LikesAdjacentEnemies")


class PsychicFortressPlaybook(AdjacentUnitPreferenceTriggeredAbilityPlaybook):
    """`PsychicFortressPlaybook` -- la face **OWNER** du passif `PsychicFortress` (1000,
    `ultraTigurius`), dont seule la face NON-OWNER etait portee (`non_owner.py`, cle
    `PSYCHICFORTRESS_AdjacentFriendly` = 20). #433-r4-r3-r2.

    ⚠ **LE MISLABEL QUI TENAIT CE RESIDU FERME.** Le `.ctor` decompile appelle un thunk gshared que
    ghidra nomme `AdjacentToOwnerNonOwnerPlaybook<...>$$.ctor(this, 1000, ...)`, et
    `IdunBattle.AI.Playbook.Loki.PsychicFortressPlaybook$$GetAdjacentFriendUtility` n'a **AUCUN
    appelant de code** (2 xrefs DATA) : la fiche en concluait << c'est un DELEGUE, son consommateur
    reste a nommer >>, d'ou un `BLOCAGE: etage`. La DECLARATION dit autre chose, et c'est elle qui
    fait foi -- la parente reelle est
    `AdjacentUnitPreferenceTriggeredAbilityPlaybook<PsychicFortressAbility>`, et les deux xrefs DATA
    sont les DEUX SLOTS DE VTABLE (13 = `GetAdjacentFriendUtility`, 14 = `GetAdjacentEnemyUtility`).
    Le consommateur est donc le corps PARTAGE de la base -- deja porte ici depuis #57i. Meme piege
    de mislabel que `RedRampage`, `Deathwing` et `IconOfObstinacy`.

    `IdunBattle.AI.Playbook.Loki.PsychicFortressPlaybook$$GetAdjacentFriendUtility` -- **LOOKUP
    PLAT**, corps ENTIER relu au decompile :

        return getUtilityVal( DAT_183372ba8 );

    Le literal est `0x3372ba8` dans `data/symbols/<build>/metadata/string_literals.tsv` =
    **`"PSYCHICFORTRESS_AdjacentFriend"`** (poids BC `Utilities.Default.TriggeredAbilities` = **5**).
    ⚠ Il ne faut PAS le confondre avec `PSYCHICFORTRESS_AdjacentFriendl**y**` (0x3372cf8), la cle de
    la face NON-OWNER, qui vit dans une AUTRE section (`TriggeredAbilitiesNonOwner` = 20) : les deux
    noms ne different que d'une lettre, et une derivation par prefixe les confondrait.
    Le parametre `friend` n'est lu par AUCUNE instruction.

    `GetAdjacentEnemyUtility` (slot 14) EST declaree surchargee, mais son corps est **DEDUPLIQUE
    par ICF** avec 112 autres du binaire -- dont ceux de `GuardianOrganismPlaybook` et
    `FabricatorClawArrayPlaybook`, dont la branche ENNEMIS est mesuree NULLE en live (case-36,
    30/90 exacts). C'est donc `return 0`, et la base le rend deja.

    Porteur : `ultraTigurius`, **HERO du pool** (kind `lineup`) -- confrontable sans montage."""

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        return wt.sub("TriggeredAbilities", "PSYCHICFORTRESS_AdjacentFriend")


class DeathwingPlaybook(AdjacentUnitPreferenceTriggeredAbilityPlaybook):
    """`DeathwingPlaybook` (`IdunBattle.AI.Playbook.Loki.DeathwingPlaybook$$.ctor` : litteral
    `0x4dd` = 1245 `TriggeredAbilityType.Deathwing` -- passif de `darkaTerminator` << Baraqiel >>,
    HERO **DU POOL** au rank courant, aucune injection ni greffe).

    `IdunBattle.AI.Playbook.Loki.DeathwingPlaybook$$GetAdjacentFriendUtility` :

        if (!UnitExtensions.HasFaction(friend, 0xa)) return 0;    // UnitFaction.DarkAngels
        return GetUtilityValue("DEATHWING_AdjacentDAFriend");     // 10

    Corps STRICTEMENT identique a celui de `FearedInterrogatorPlaybook` a la CLE de chaine pres
    (meme `HasFaction(u, 0xa)`, meme forme). La cle est LUE au slot de string literal
    (`0x33fa868` dans `data/symbols/<build>/metadata/string_literals.tsv`), pas devinee par
    prefixe -- c'est la lecon de `SPIRITUALLDEADER_` (#212).

    ⚠ PARENTE : `frida/classes.tsv` donne `DeathwingPlaybook ->
    AdjacentUnitPreferenceTriggeredAbilityPlaybook`1` -- **PAS** `AdjacentToOwnerNonOwnerPlaybook`,
    que le pseudo-C du `.ctor` designe pourtant (les deux bases partagent le meme corps gshared,
    ghidra le MISLABELLE : meme piege que `IconOfObstinacyPlaybook`). Le port herite donc de la base
    DIRECTE. Consequence LUE, pas deduite : il n'existe **aucune** `DeathwingNonOwnerPlaybook` dans
    ce build, et **aucune** cle `DEATHWING*` dans `Utilities.Default.TriggeredAbilitiesNonOwner`
    (25 cles) -- la face NON-OWNER n'existe pas pour ce passif.

    ⚠ CE QUE LA CLASSE DECLARE, lu dans `global-metadata.dat` (`il2cpp_metadata.type_methods`) :

        [.ctor (65535), GetAdjacentFriendUtility (slot 13), GetAdjacentEnemyUtility (slot 14)]

    Le bloc `methodPointers` du PE, ancre sur le `.ctor`, donne dans CE MEME ORDRE
    `[.ctor, GetAdjacentFriendUtility, <ret 0>]` : `GetAdjacentEnemyUtility` est un override
    EXPLICITE qui rend 0 -- semantiquement identique au defaut de la base, d'ou l'absence de
    surcharge ici (meme forme qu'`IconOfObstinacyPlaybook`). **NI cap** (`GetMaxAdjacentFriendsToCount`
    absent du metadata) **NI filtre** (`FilterAdjacentFriends` absent) : le gate est DANS l'accesseur.

    Terme = 10 x #amis a distance 1 de la tuile candidate dont le `FactionId` est `DarkAngels`.
    Il departage donc deux tuiles a MEME nombre d'amis adjacents des que leurs factions different.

    ⚠ `DeathwingKnightPlaybook` (ability `DeathwingKnight` 1510) porte le MEME corps a la cle pres.
    Elle est portee juste en dessous (#932-r1) -- et c'est une CLASSE NATIVE DISTINCTE, pas une
    instance de celle-ci."""

    KEY = "DEATHWING_AdjacentDAFriend"                            # slot literal 0x33fca48

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        if _unit_faction(unit) != UnitFaction.DarkAngels.name:    # HasFaction(friend, 0xa)
            return 0.0
        return float(wt.sub("TriggeredAbilities", self.KEY))


class DeathwingKnightPlaybook(AdjacentUnitPreferenceTriggeredAbilityPlaybook):
    """`DeathwingKnightPlaybook` (`IdunBattle.AI.Playbook.Loki.DeathwingKnightPlaybook$$.ctor` :
    litteral `0x5e6` = 1510 `TriggeredAbilityType.DeathwingKnight` -- passif du SUMMON
    `darkaSmnTerminator` et de son jumeau npc `darkaNpc3Terminator`). #932-r1.

    `IdunBattle.AI.Playbook.Loki.DeathwingKnightPlaybook$$GetAdjacentFriendUtility`, corps ENTIER
    relu au decompile sur `t6dpr4k06g` :

        if (!UnitExtensions.HasFaction(friend, 0xa)) return 0;         // UnitFaction.DarkAngels
        return getUtilityVal("DEATHWINGKNIGHT_AdjacentDAFriend");      // 10

    ⚠ **DEUX CLASSES NATIVES, DEUX CORPS DISTINCTS -- pas une instance de `DeathwingPlaybook`.**
    Le port ne DERIVE donc pas de sa jumelle : `classes.tsv` donne aux DEUX
    `AdjacentUnitPreferenceTriggeredAbilityPlaybook`1` comme base, et leurs corps vivent a deux
    adresses (l'ICF ne peut pas les fondre, le slot de litteral differe). Les octets sont par
    ailleurs identiques : meme `HasFaction(friend, 0xa)`, meme forme.

    ⚠ LA CLE EST LUE AU SLOT DE LITTERAL, JAMAIS DERIVEE DU NOM. Le corps charge `DAT_1833fc908` ;
    `data/symbols/t6dpr4k06g/metadata/string_literals.tsv` donne
    `0x33fc908 -> "DEATHWINGKNIGHT_AdjacentDAFriend"` -- a UNE LETTRE de casse pres du prefixe de sa
    jumelle (`0x33fca48 -> "DEATHWING_AdjacentDAFriend"`), et les deux slots sont voisins dans la
    table. Poids `Utilities.Default.TriggeredAbilities` = **10**, comme `Deathwing` (mesure sur
    `data/seed-bc.json`) : c'est une COINCIDENCE de valeur, pas une cle partagee.

    ⚠ PARENTE : le pseudo-C du `.ctor` appelle
    `AdjacentToOwnerNonOwnerPlaybook<__Il2CppFullySharedGenericType>$$.ctor(this, 0x5e6, ...)` --
    c'est le MISLABEL de thunk gshared deja documente pour `Deathwing`, `RedRampage`,
    `IconOfObstinacy` et `PsychicFortress`. `frida/classes.tsv` dit
    `AdjacentUnitPreferenceTriggeredAbilityPlaybook`1`, et c'est elle qui fait foi.

    ⚠ CE QUE LA CLASSE DECLARE, lu au bloc `methodPointers` du PE (ancre sur le `.ctor`, trois
    entrees CONTIGUES) : `[.ctor, GetAdjacentFriendUtility, <corps `return 0` fondu par l'ICF>]`.
    La troisieme entree est le MEME corps que la troisieme de `DeathwingPlaybook` --
    `GetAdjacentEnemyUtility` (slot 14) est un override EXPLICITE qui rend 0, semantiquement egal
    au defaut de la base, d'ou l'absence de surcharge ici. **NI cap NI filtre** : aucun
    `GetMaxAdjacentFriendsToCount` ni `FilterAdjacentFriends` dans le bloc -- le gate est DANS
    l'accesseur. Faces ATTACK / REPAIR : aucun corps propre, donc le `yield Fix64(0)` herite de
    `TriggeredAbilityPlaybook<T>` -- DEAD, comme chez sa jumelle.

    Terme = 10 x #amis a distance 1 de la tuile candidate dont le `FactionId` est `DarkAngels`.

    REGISTRE : `metadata/active_playbook_builders.tsv` porte `triggered 1510
    IdunBattle.AI.Playbook.Loki.DeathwingKnightPlaybook` -- le playbook est CHARGE par
    `PlaybookDatabase$$LoadPlaybook`, pas du code enregistre-mais-mort. Aucune face NON-OWNER :
    `non_owner_slot4.tsv` ne porte rien pour cette famille, et `TriggeredAbilitiesNonOwner`
    (`data/seed-bc.json`) n'a aucune cle `DEATHWING*`.

    PORTEURS (`unit_map.py find --ability DeathwingKnight`) : `darkaNpc3Terminator` (**npc**) et
    `darkaSmnTerminator` (**SUMMON**, HP/DMG/ARM a 0 au catalogue). Aucun n'est un hero du pool.
    L'accesseur ne lit NI stat NI trait DU CASTER (seulement la faction du VOISIN), donc l'ability
    se GREFFE sur une unite du pool -- c'est la voie de confrontation retenue (gate de
    confrontabilite, cas `1194 NovaShield`)."""

    KEY = "DEATHWINGKNIGHT_AdjacentDAFriend"                      # slot literal 0x33fc908

    def get_adjacent_friend_utility(self, unit: dict, wt) -> float:
        if _unit_faction(unit) != UnitFaction.DarkAngels.name:    # HasFaction(friend, 0xa)
            return 0.0
        return float(wt.sub("TriggeredAbilities", self.KEY))


from .adjacent_summons import MawClawsOfThyraxPlaybook       # noqa: E402  (#920 : corps propre)
from .fury_of_the_ancients import FuryOfTheAncientsPlaybook   # noqa: E402  (après les bases)
from .friends_in_range import (AstartesBannerPlaybook,       # noqa: E402  (N13 : corps propres)
                               ECogSupportPlaybook,          # noqa: E402  (#433-r4-r3-r2)
                               FirstAmongTraitorsPlaybook,   # noqa: E402  (#926)
                               GrimEfficiencyPlaybook,       # noqa: E402  (#959-r1)
                               KardiocoreGalvanusPlaybook)
from .geminae_superia import GeminaeSuperiaPlaybook          # noqa: E402  (case-165b : corps propre)
from .intoxicating_elixir import IntoxicatingElixirPlaybook  # noqa: E402  (#922 : corps propre, PAR EFFET)
from .legacy_of_combat import LegacyOfCombatPlaybook         # noqa: E402  (#928 : corps propre, ENNEMIS)
from .obsessive_annunciation import ObsessiveAnnunciationPlaybook   # noqa: E402  (#954 : slot 128)
from .modified_exoarmour import ModifiedExoarmourPlaybook    # noqa: E402  (#304 : corps propre, PAR TUILE)
from .savior_protocols import SaviorProtocolsPlaybook        # noqa: E402  (#443-r1 : face MOVE, cf. module)
from .serene_unifier import SereneUnifierPlaybook            # noqa: E402  (#456-r1 : corps propre, 101/ami)
from .rad_saturation import RadSaturationPlaybook            # noqa: E402  (#477-r29 : corps propre, +10/marshal)
from .prophetic_sentinel import PropheticSentinelPlaybook    # noqa: E402  (#915 : corps propre, +20/Psyker adjacent)
from .sanguinary_priest import SanguinaryPriestPlaybook      # noqa: E402  (#921-r1 : corps propre, 5 + 6 si blesse)
from .close_combat_weakness import CloseCombatWeaknessPlaybook  # noqa: E402  (#1015-r1 : corps propre, -40/ennemi)
from .vengeance_for_the_omnissiah import VengeanceForTheOmnissiahPlaybook  # noqa: E402  (#1071 : corps propre, BINAIRE)

TRIGGERED_MOVE_PLAYBOOKS: dict = {
    # #1071 -- la PREMIERE feuille du registre dont le terme est BINAIRE et non un produit : le
    # corps natif `break` au PREMIER ami mecanique (autre que le mover) adjacent a la tuile
    # candidate, donc la valeur vaut `30` ou `0`, jamais `30 x N`. Recopier le `count_adjacent` de
    # ses voisins de forme (`legacy_of_combat`, `close_combat_weakness`) multiplierait le terme
    # silencieusement des la 2e unite qualifiee. Query = `GetAdjacentFriends` (slot 0x83 = 131, LU
    # dans `metadata/interface_slots.tsv`), filtre = `IsMechanical` (DISJONCTION de 3 traits) plus
    # l'exclusion du mover lui-meme (il est son propre allie ET il est Mechanical). Sa face ATTAQUE
    # est une CONSTANTE ZERO, d'ou son absence de `psyker.TRIGGERED_ATTACK_PLAYBOOKS` (cf. le
    # module). La face COMBAT du meme passif vit dans
    # `runner/operations/triggers/loki/vengeance_for_the_omnissiah.py`.
    int(TriggeredAbilityType.VengeanceForTheOmnissiah): VengeanceForTheOmnissiahPlaybook(),  # 1298 (30, BINAIRE)
    # #1015-r1 -- la PREMIERE feuille du registre dont le poids est NEGATIF : le porteur T'AU FUIT le
    # contact (-40 par ennemi ring-1 de la tuile visee, `CLOSECOMBATWEAKNESS_PerAdjacentEnemy`).
    # Corps PROPRE (`Count x poids`, ni cap ni filtre ni branche amis) -> module dedie. L'ability est
    # DERIVEE DU TRAIT (aucun `passiveAbilities` ne la porte) : elle n'atteint le dispatcher que par
    # `TRAIT_TRIGGERED_ABILITY_IDS["CloseCombatWeakness"]`. Sa face ATTAQUE est une CONSTANTE ZERO,
    # d'ou son absence de `psyker.TRIGGERED_ATTACK_PLAYBOOKS` (cf. le module).
    int(TriggeredAbilityType.CloseCombatWeakness): CloseCombatWeaknessPlaybook(),  # 1130 (-40 / ennemi)
    # #433-r4-r3-r2 -- les DEUX faces OWNER dont seule la face NON-OWNER etait portee. Leur
    # `BLOCAGE` etait `etage` (`PsychicFortress` : « delegue a un consommateur non nomme ») et
    # `seeding` (`ECogSupport` : « le ctx ne publie le parent QUE DU SUJET ») ; les deux sont
    # REFUTES -- le consommateur de `GetAdjacentFriendUtility` est le corps PARTAGE de
    # `AdjacentUnitPreferenceTriggeredAbilityPlaybook` (la parente ghidra etait un MISLABEL de
    # thunk gshared), et la cle `parent` est desormais posee par les TROIS jumeaux de `leaf_ctx`.
    int(TriggeredAbilityType.PsychicFortress): PsychicFortressPlaybook(),        # 1000 (5 / ami adjacent)
    int(TriggeredAbilityType.EcogSupport): ECogSupportPlaybook(),                # 1487 (30 / E-Cog adjacent)
    int(TriggeredAbilityType.GuardianOrganism): GuardianOrganismPlaybook(),
    int(TriggeredAbilityType.RitesOfBattle): RitesOfBattlePlaybook(),
    # 1069 (#958) -- `MedicusMinistorumPlaybook$$.ctor` delegue a `AdjacentToOwnerNonOwnerPlaybook`
    # avec `0x42d` ; son `GetAdjacentFriendUtility` est un LOOKUP PLAT sur
    # `MEDICUSMINISTORUM_AdjacentFriend`. Aucune branche ENNEMIS (2 corps propres seulement).
    int(TriggeredAbilityType.MedicusMinistorum): MedicusMinistorumPlaybook(),
    int(TriggeredAbilityType.MartialApotheosis): MartialApotheosisPlaybook(),   # 1045 (#57i, branche ennemis)
    int(TriggeredAbilityType.FabricatorClawArray): FabricatorClawArrayPlaybook(),  # 1006 (#57i, amis mecaniques)
    int(TriggeredAbilityType.FuryOfTheAncients): FuryOfTheAncientsPlaybook(),   # 1247 (#32)
    # N13 — famille « corps propre » (`friends_in_range.py`) : elles COMPTENT les amis autour de la
    # tuile candidate, SELF INCLUS. C'est le terme qui manquait au composite Tile(7) et qui
    # fabriquait les faux ties du sweep de position (case-n13).
    int(TriggeredAbilityType.AstartesBanner): AstartesBannerPlaybook(),         # 1106
    int(TriggeredAbilityType.KardiocoreGalvanus): KardiocoreGalvanusPlaybook(),  # 1457 (RELIQUE)
    # #920 -- meme famille « corps propre », mais la query est `GetAdjacentUnits` (slot 0x7a,
    # arite 4, litteraux `0, 0, 0`) et non `GetAdjacentFriends` : elle compte les summons des DEUX
    # camps. Et contrairement a `KardiocoreGalvanus` (dont le corps DISCARDE le `get_Current`),
    # celui-ci FILTRE par `HasTrait(u, 0x2 = Summon)`. Cf. `playbook/adjacent_summons.py`.
    int(TriggeredAbilityType.MawClawsOfThyrax): MawClawsOfThyraxPlaybook(),      # 1469 (RELIQUE)
    # case-165b — meme famille « corps propre », mais elle compte des TUILES LIBRES (pas des amis) :
    # `10 x |CanAddUnit(AdjacentTiles(tuile))|`. Constante en plein plateau, DECISIVE au bord.
    int(TriggeredAbilityType.GeminaeSuperia): GeminaeSuperiaPlaybook(),         # 1048
    # #963 -- LOOKUP PLAT sur `RedRampage_LikesAdjacentEnemies` (= 20), branche ENNEMIS, base
    # DIRECTE (`AdjacentUnitPreferenceTriggeredAbilityPlaybook<RedRampage_AttackAbility>` lu dans
    # `classes.tsv`). Porteur `bloodTerminator`, HORS POOL -> injection catalogue.
    int(TriggeredAbilityType.RedRampage): RedRampagePlaybook(),                 # 1551
    # #193c — les deux premiers concrets dont `GetAdjacent*Utility` LIT son argument `unit`.
    # Porteurs POOL-HERO au rank courant (`rl_duel build --list-pool`) : darkaAsmodai, blackTerminator.
    int(TriggeredAbilityType.FearedInterrogator): FearedInterrogatorPlaybook(),  # 1235 (gate faction)
    int(TriggeredAbilityType.HatefulAssault): HatefulAssaultPlaybook(),          # 1038 (2 poids)
    # #211 — le premier concret qui surcharge les DEUX faces, et le premier dont le gate ennemi lit
    # le `WeaponsComponent` du voisin (profil de degat x melee). Porteur POOL-HERO : deathBlightbringer.
    int(TriggeredAbilityType.CursedPlagueBell): CursedPlagueBellPlaybook(),      # 1071 (Chaos / Psychic-melee)
    # #212 — le terme manquait parce que sa CLE BC etait introuvable par prefixe (faute de frappe du
    # jeu : `SPIRITUALLDEADER_`). Resolue au litteral natif, elle vaut 30. Porteur POOL-HERO :
    # genesMagus, qui fabrique elle-meme les decoys que ce terme compte.
    int(TriggeredAbilityType.SpiritualLeader): SpiritualLeaderPlaybook(),        # 1275 (filtre Decoy)
    # #271 — DEMASQUE par le refresh `refresh_ai_utilities` (la cle valait 0 dans la CAPTURE, 10 au
    # gameconfig vivant). Porteur POOL-HERO : orksBigMek. Face NON-OWNER de la meme ability :
    # `playbook/non_owner.py` (feuille `TriggeredAbilitiesNonOwner(4)`).
    int(TriggeredAbilityType.KustomForceFieldReworked): KustomForceFieldReworkedPlaybook(),  # 1547 (x2 si ami Ork)
    # #304 -- la PREMIERE feuille du registre qui se paie PAR TUILE PARCOURUE (`5 x |chemin|`, donc
    # croissante avec la distance) et la premiere qui appelle le PATHFINDING natif. Porteur
    # POOL-HERO par injection : `votanChampion` (Kimm). Cle BC AJOUTEE par ce build.
    int(TriggeredAbilityType.ModifiedExoarmour): ModifiedExoarmourPlaybook(),    # 1529 (5 / tuile de chemin)
    # #443-r1 -- la face MOVE de la MEME classe native que la face ATTACK de #443 (registre attack :
    # `psyker.py`). Deux termes : +20 par ALLIE T'AU ADJACENT a la tuile candidate qui ne porte pas
    # 1120 lui-meme (predicat DSL `SaviorProtocolsAbility$$TargetIsValidTrigger`, artefact natif
    # distinct, partage avec la face COMBAT), +30 de PLUS si cet allie est le SUMMONER du mover
    # (`UnitExtensions$$GetParent`). Porteurs : 3 npc + 3 SUMMONS `tauSmn*Drone*` -- le porteur
    # confronte est `tauSmnDroneSniper`, invoque par l'attaque RANGED de `tauMarksman` (1076).
    int(TriggeredAbilityType.SaviorProtocols): SaviorProtocolsPlaybook(),        # 1120 (20 / +30 parent)
    # #456-r1 -- la PREMIERE feuille du registre dont le facteur est un LITTERAL du corps natif
    # (`imul 0x65` = 101), sans AUCUNE cle `BC.Utilities` : il n'y a rien a chercher dans la table,
    # et une cle inventee la serait une fausse verite. C'est aussi la seule qui EXCLUE explicitement
    # le mover de son comptage d'amis adjacents (`RemoveAll(u.Id == case.Unit.Id)`), la ou la famille
    # `friends_in_range` le compte pour lui-meme. Porteur POOL-HERO : `tauAunShi` (kit NATIF verifie
    # par `unitAbilityStates`, pas deduit du gameconfig).
    int(TriggeredAbilityType.SereneUnifier): SereneUnifierPlaybook(),            # 1145 (101 / ami adjacent)
    # #477-r29 -- la PREMIERE feuille du registre dont le predicat porte sur le KIT ACTIF du voisin
    # (`HasActiveAbility(f, 0x45e = DoctrinaImperatives)`), et non sur un trait ou une faction.
    # `case-26` l'avait declaree AI-INERTE (« TriggeredAbilitiesUtility enregistree-mais-morte ») :
    # ce verdict est REFUTE par les mesures live de la MEME feuille (case-36 30/90 exacts, #212,
    # #242, #271). Porteur : `admecSmnVanguard` (SUMMON) et deux npc Vanguard -- confronte par
    # GREFFE du passif sur un heros du pool (`catalog_inject.graft_passive_ability`), le corps ne
    # lisant ni stats ni traits du caster.
    int(TriggeredAbilityType.RadSaturation): RadSaturationPlaybook(),            # 1202 (10 / marshal adjacent)
    # #915 -- la face OWNER du passif `PropheticSentinel`, dont la face NON-OWNER etait DEJA portee
    # (`non_owner.py`) : le registre non-owner ne couvre PAS celui-ci, et l'absence ici valait 0
    # alors que le natif rend `20 x |amis Psyker adjacents a la tuile candidate|`. Les DEUX faces
    # ont des predicats DIFFERENTS -- non-owner CUMULE Psyker+Chaos, owner ne connait que Psyker.
    # Porteur : `thousSekhetar` (HERO hors pool -> injection catalogue, case-92 §6).
    int(TriggeredAbilityType.PropheticSentinel): PropheticSentinelPlaybook(),    # 1543 (20 / Psyker adjacent)
    # #919 -- face OWNER du passif `IconOfObstinacy`, dont seule la face NON-OWNER etait portee
    # (#433-r4-r3-r1). Les deux cles sont NEUVES a ce build (`refresh_ai_utilities` les ajoute) et
    # les deux faces se cumulent sur une meme decision. Porteur : `astarLysander`, HERO HORS du pool
    # -> injection catalogue (`catalog_inject`, cf. `case-270d`). Gate `TerminatorArmour` DANS
    # l'accesseur ; ni cap ni filtre (metadata : la classe ne declare que les deux accesseurs).
    int(TriggeredAbilityType.IconOfObstinacy): IconOfObstinacyPlaybook(),        # 1552 (20 / ami Terminator)
    # #922 -- la PREMIERE feuille du registre dont le predicat porte sur les EFFETS du voisin (les
    # autres lisent un trait, une faction ou un kit), la premiere SANS filtre d'equipe (amis ET
    # ennemis), la premiere sur un DISQUE CUBE de rayon 2 (`IterateSurroundingTiles`, sans porte
    # d'elevation -- pas le ring-1 STOCKE d'`IterateAdjacentTiles`) et la premiere PLAFONNEE
    # (`Min(..., nrOfUnits = 6)`). Elle appelle LITTERALEMENT la `$$GetLevelFormula` de l'effet de
    # COMBAT `1459 IntoxicatingElixir`, seule l'ancre changeant (`Get(<tuile candidate>)` au lieu de
    # `Tiles(Owner)`) -- d'ou l'arbre PARTAGE avec `entities/effects/loki/intoxicating_elixir.py`.
    # Porteurs : 4 heroes Emperor's Children par RELIQUE (`emperKakophonist` et `emperNoiseMarine`
    # au pool, `emperExultant` et `emperFlawlessBlade` par injection catalogue).
    int(TriggeredAbilityType.IntoxicatingElixir): IntoxicatingElixirPlaybook(),  # 1463 (RELIQUE, 5 / debuffe)
    # #926 -- face OWNER du passif `FirstAmongTraitors`, dont seule la face NON-OWNER etait portee
    # (#477-r37, `non_owner.py`). MEME famille « corps propre » qu'`AstartesBanner` (MEME slot de
    # query `0x75 = GetSurroundingUnits`, MEME `includeCenter = true`), mais le corps porte DEUX
    # filtres que son voisin n'a pas : `u != case.unit` (le mover s'exclut) et
    # `HasTrait(u, 0x7ea = UnitTrait.Chaos)`. Les DEUX faces lisent des CLES BC differentes, dans
    # des SECTIONS differentes (`TriggeredAbilities` vs `TriggeredAbilitiesNonOwner`), et se
    # cumulent sur une meme decision. Porteur : `blackAbaddon`, HERO **DU POOL** -- confrontable
    # sans aucun montage.
    int(TriggeredAbilityType.FirstAmongTraitors): FirstAmongTraitorsPlaybook(),  # 1064 (10 / ami Chaos)
    # #928 -- meme famille « corps propre », mais la query est un `GetAdjacentEnemies` (slot 127,
    # arite 3, ancre TUILE + argument UNITE) : c'est la PREMIERE feuille du registre qui compte des
    # ENNEMIS a partir d'un corps propre, donc SANS l'inclusion de self qui fait la signature de
    # `friends_in_range`. Aucun filtre, aucun cap : `10 x |ennemis adjacents a la tuile candidate|`.
    # Porteur POOL-HERO : `custoBladeChampion`. Cf. `playbook/legacy_of_combat.py`.
    int(TriggeredAbilityType.LegacyOfCombat): LegacyOfCombatPlaybook(),          # 1319 (10 / ennemi adjacent)
    # #932 -- face DECISION OWNER du passif `Deathwing` de `darkaTerminator` << Baraqiel >>, HERO
    # **DU POOL** (confrontable sans montage). MEME corps que `FearedInterrogatorPlaybook` a la CLE
    # pres. Ce passif n'a PAS de face non-owner (aucune `DeathwingNonOwnerPlaybook` dans le build,
    # aucune cle `DEATHWING*` dans `TriggeredAbilitiesNonOwner`), et ses faces ATTACK / REPAIR sont
    # DEAD (corps herite `yield return Fix64.op_Implicit(0)` de `TriggeredAbilityPlaybook<T>`).
    int(TriggeredAbilityType.Deathwing): DeathwingPlaybook(),                    # 1245 (10 / ami DarkAngels)
    # #932-r1 -- la JUMELLE de la ligne ci-dessus, classe native DISTINCTE (deux corps, deux
    # adresses) a la seule CLE de litteral pres (`0x33fc908` vs `0x33fca48`). Porteurs
    # `darkaSmnTerminator` (SUMMON) et `darkaNpc3Terminator` (npc) : aucun hero du pool, mais
    # l'accesseur ne lit ni stat ni trait DU CASTER -> l'ability se GREFFE sur une unite du pool.
    # `triggered 1510` est bien dans `metadata/active_playbook_builders.tsv` (registre natif).
    int(TriggeredAbilityType.DeathwingKnight): DeathwingKnightPlaybook(),        # 1510 (10 / ami DarkAngels)
    # #954 -- MEME famille « corps propre » que `LegacyOfCombat` juste au-dessus, et MEME forme de
    # produit plat, mais la query est la QUATRIEME surcharge de `GetAdjacentEnemies` (**slot 128**,
    # ancre `UnitPosition` + argument UNITE) et non la troisieme (slot 127, ancre TUILE via
    # `get_MovementTile`). Le discriminant est le litteral `mov r8d, 0x80` / `0x7f` relu aux OCTETS,
    # pas le pseudo-C, qui est identique. Aucun filtre, aucun cap : `10 x |ennemis adjacents a la
    # tuile candidate|`. Sa face ATTAQUE est DEAD (`yield Fix64.op_Implicit(0)` constant).
    # Porteur POOL-HERO : `emperKakophonist`. Cf. `playbook/obsessive_annunciation.py`.
    int(TriggeredAbilityType.ObsessiveAnnunciation): ObsessiveAnnunciationPlaybook(),  # 1443 (10 / ennemi adjacent)
    # #959-r1 -- face DECISION de `GrimEfficiency`, la seule des deux passifs d'AURA Votann de #959
    # a en avoir une (`PredictiveGuidance` n'a AUCUN playbook dans le build : c'est un fait mesure,
    # pas un oubli). Meme famille « corps propre » qu'`AstartesBanner`, et pourtant DEUX ecarts
    # LUS au call-site qui changent le compte : `includeCenter = 0` (l'ami sur la tuile candidate
    # ne compte pas) et `units.Remove(case.unit)` (le mover ne se compte pas lui-meme depuis son
    # origine). Query = `GetSurroundingFriends` (**slot 121**, filtre `IsFriend` applique par
    # `FilterInPlace` APRES coup), pas `GetSurroundingUnits` (slot 117, filtre `!IsEnemy` INTERNE).
    # Porteur HORS POOL -> injection catalogue. Cf. `playbook/friends_in_range.py`.
    int(TriggeredAbilityType.GrimEfficiency): GrimEfficiencyPlaybook(),          # 1490 (5 / ami en portee)
    # #921-r1 -- corps PROPRE (il n'herite PAS de la base de ce module), et la PREMIERE feuille du
    # registre dont un terme lit les PV d'un voisin : `IsDamagedUnit(u)` =
    # `GetStat(u, StatType.Health = 5, StatPart.Missing = 4) > 0`. Elle cumule DEUX poids sur un
    # meme ami (5 + 6), le second `+=` etant IMBRIQUE dans le premier `if` -- un ami Mechanical
    # sans `AffectedByHealAndRepair` ne rapporte donc RIEN, meme blesse. Elle n'exclut PAS le mover
    # (aucun `RemoveAll`, et `IsFriend` n'ecarte pas l'egalite), a l'inverse de `SereneUnifier`.
    # Sa face ATTACK est un `yield Fix64(0)` PROPRE (pas herite) : elle n'a rien a enregistrer.
    # Porteur POOL-HERO : `bloodSanguinary` << Nicodemus >>. Cf. `playbook/sanguinary_priest.py`.
    int(TriggeredAbilityType.SanguinaryPriest): SanguinaryPriestPlaybook(),      # 1296 (5 / ami + 6 si blesse)
}


def load_playbook(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybook` (movement-relevant uniquement). None → le dispatcher skip
    (même chemin que le `if playbook == null: continue` natif)."""
    return TRIGGERED_MOVE_PLAYBOOKS.get(int(ability_id))
