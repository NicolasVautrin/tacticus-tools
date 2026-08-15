"""Famille `TriggeredAbilityNonOwnerPlaybook<T>` — utilite de MOUVEMENT que l'ability d'UNE AUTRE
unite exerce sur l'unite QUI BOUGE.

C'est la SECONDE face du moteur Playbook cote mouvement, et la symetrique exacte de la premiere :

  * feuille `TriggeredAbilities(2)` (`adjacent_unit_preference.py`) : on itere les abilities
    declenchees DU MOVER (`case.unit`), chaque playbook pese la tuile candidate. Poids dans
    `Utilities.Default.TriggeredAbilities`.
  * feuille `TriggeredAbilitiesNonOwner(4)` (CE module) : on itere les abilities declenchees des
    AUTRES unites, chaque playbook pese la tuile candidate DU MOVER du point de vue de SON porteur.
    Poids dans `Utilities.Default.TriggeredAbilitiesNonOwner` (categorie SEPAREE, 25 cles).

Chaine native (relue au decompile du build `rnca9r7q6c`) :

    IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext
        Fix64 total = 0;
        if (case.unit == null && case.parent == null) { yield 0; return; }
        foreach ((playbook, owner) in IterateAbilities(case))
            total += <somme des steps de> playbook.CalculateMovementUtilityInSteps(case, owner);
        yield total;

    IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CIterateAbilitiesu003Ed__3$$MoveNext
        subject = case.unit ?? case.parent;
        foreach (triggeredAbility in <toutes les TriggeredAbility de la bataille>) {
            if (case.unit != null && case.unit == triggeredAbility.Owner) continue;   // self exclu
            playbook = PlaybookDatabase.LoadPlaybookNonOwner(triggeredAbility.Type);
            if (playbook == null) continue;
            if (playbook.<slot 4> || UnitExtensions.IsFriend(subject, triggeredAbility.Owner, state))
                yield (playbook, triggeredAbility.Owner);
        }

⚠ **LE REGIME SPAWN N'EST PAS UN REGIME MORT (#271-r3).** Les deux gardes ci-dessus le disent, et
c'est la lecture qui a manque pendant trois tranches : `EvaluateMovementInSteps` ne rend `Zero` que
si `case.unit` **ET** `case.parent` sont nuls, et l'exclusion de self d'`IterateAbilities` est
GARDEE par `case.unit != null`. Quand un summon cherche sa tuile d'apparition
(`SortTilesByUtilityForSummon`), le natif itere donc avec le PARENT pour sujet, **le parent compris
parmi les porteurs**. TROIS corps du registre y yieldent, parce qu'ils ne lisent JAMAIS `case.unit`
(relus au decompile un par un) : `PsychicFortress` (20), `BookOfFate` (5), et la BRANCHE SPAWN de
`MawClawsOfThyrax` (5, sans le gate `Summon`). Les 17 autres portent un
`if (case.unit == null) yield break` -- leur gate `is_spawning` est donc LOAD-BEARING, pas
decoratif : le dispatcher n'ecarte plus ce regime en amont. DEUX classes ne l'avaient pas
(`KustomForceFieldReworked`, `ECogSupport`) ; il est desormais EXPLICITE partout ou le natif l'a.

Le pre-gate `<slot 4> || IsFriend` est le complement de
`IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$IsInvalidEntityForPlaybook`
(= `!slot4 && !IsFriend`). `slot 4` est un predicat SANS argument de l'interface
`ITriggeredAbilityNonOwnerPlaybook`, dont le corps est TRIVIAL (fondu par l'ICF, donc sans symbole
propre).

**LE `<slot 4>` A UN NOM, ET IL EST LU CLASSE PAR CLASSE (#477-r37).** C'est
`get_ShouldIncludingEnemiesWhenCalculate` -- la 5e methode d'`ITriggeredAbilityNonOwnerPlaybook`,
LUE dans le `global-metadata.dat` (`il2cpp_metadata.type_methods`, la meme voie que
`data/symbols/<build>/metadata/interface_slots.tsv`), qui rend pour cette interface :

    slot 0  CalculateMovementUtilityInSteps        slot 3  Init
    slot 1  CalculateAttackUtilityInSteps          slot 4  get_ShouldIncludingEnemiesWhenCalculate
    slot 2  CalculateRepairUtilityInSteps

Sur les **28** classes concretes de la famille, **2** le SURCHARGENT et **26** heritent :

  * `HaywireMineNonOwnerPlaybook`             -> `true`  (face MOVE, portee ci-dessous) ;
  * `NoHidingFromTheWatchersNonOwnerPlaybook` -> `true`  (face ATTACK, hors de cette feuille) ;
  * les 26 autres n'ont AUCUNE entree de ce nom dans leur `Il2CppTypeDefinition` -> elles prennent
    le corps de la base, mesure au runtime `xor eax,eax ; ret` = **`false`**.

TROIS sources INDEPENDANTES, et c'est le probe `probe_477r37_slot4_et_faces_restantes.py` qui les
re-derive (jamais cette docstring) :

  1. **DECLARATION** -- `global-metadata.dat` : la liste des methodes DECLAREES par chaque type.
     C'est la seule source COMPLETE (28/28) : elle ne depend ni de l'ICF ni de l'initialisation.
  2. **VALEUR (offline)** -- le bloc `methodPointers` du PE, ancre sur le `.ctor` et INDEXE par la
     position metadata. Les deux surcharges pointent le meme corps fondu
     (`UnityEngine.U2D.IK.Solver2D$$DoValidate` = `b0 01 c3` = `mov al,1 ; ret`).
  3. **VALEUR (runtime)** -- la vtable de la classe (`resolveVtableSlot`), BORNEE : on n'accepte que
     les classes dont les slots 0..3 sont les quatre virtuels d'`Object`. 13 des 28 classes sont
     initialisees dans la session ; le probe DIT les 15 autres au lieu d'en rendre un zero.

⚠ **LE CRITERE DE #477-r35 ETAIT FAUX SUR LES DEUX BORDS, et il rendait la bonne reponse.** Il
lisait l'entree qui **PRECEDE** le `.ctor` dans le bloc `methodPointers` :
  * **faux negatif** -- `NoHidingFromTheWatchersNonOwnerPlaybook` declare le getter APRES son
    `.ctor` ; le critere ne pouvait pas la voir, et elle vaut `true` ;
  * **faux positif** -- il attribuait a `ECogSupportPlaybookNonOwnerPlaybook` et
    `KustomForceFieldReworkedNonOwnerPlaybook` un override explicite `return 0`
    (`Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`). Le metadata dit qu'elles ne
    declarent RIEN : cette entree appartient au TYPE PRECEDENT de la table. La valeur (`false`)
    etait juste pour la mauvaise raison.
Le point de doctrine reste entier : le `<slot 4>` est une donnee **PAR CLASSE**, jamais une
constante de famille.

⚠ **UNE VTABLE RUNTIME NON BORNEE MENT** (piege #218). Sans la garde « slots 0..3 = les quatre
virtuels d'`Object` », `RelicOfLostCadiaNonOwnerPlaybook` -- classe NON initialisee -- rendait un
`get_ShouldIncludingEnemiesWhenCalculate` a l'index 42 : c'etait la vtable de l'`Il2CppClass`
VOISINE. Elle donnait la bonne valeur, par chance.

Consequence portee : le pre-gate est `pb.SLOT_4 || IsFriend(case.unit ?? case.parent, owner)`, et il
est mirrore LA OU LE NATIF LE MET -- dans le dispatcher (`utilities/tile.py::
TriggeredAbilitiesNonOwnerUtility.evaluate`, mirror d'`IterateAbilities`), pas dans les corps de
playbook. `KustomForceFieldReworkedNonOwnerPlaybook` garde son propre test `IsFriend` : son corps
natif le porte VRAIMENT (redondant avec le pre-gate, mais present au decompile), et le port mirrore
le corps, pas l'economie qu'on pourrait en faire.

ASCII only dans les sorties ; les accents restent dans les docstrings non imprimees.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.tile_extensions import get_steppable_unit
from ..entities.ability_constant_type import AbilityConstantType
from ..entities.rarity import Rarity
from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_faction import UnitFaction, faction_value
from ..entities.unit_team_selection_type import UnitTeamSelectionType


def _has_trait(ctx: dict, trait_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(case.unit, <id>)` sur le substrat du MOVER.

    `ctx["unit_traits"]` porte les IDS `UnitTrait` du SUJET de la decision (`entity_trait_ids` :
    kit gameconfig + traits accordes EN BATAILLE par le leaf `AddTrait`) -- c'est bien ce que
    `HasTrait` interroge, pas le kit cache par `visualId`."""
    return int(trait_id) in {int(t) for t in ((ctx or {}).get("unit_traits") or ())}


# `IdunBattle.Entities.UnitExtensions$$IsMechanical` -- LU au decompile, ce N'EST PAS
# `HasTrait(Mechanical)` seul : le corps enchaine trois `BaseUnitComponent$$HasTrait` en OU
# court-circuite, sur `5`, `0x3e8` et `0x405`. Les trois ids sont QUALIFIES contre
# `IdunBattle.Entities.Enum.UnitTrait` (5=Mechanical, 1000=LivingMetal, 1029=Vehicle) : les
# homonymes `UnitFaction`/`EffectType` a valeur egale n'ont rien a voir.
_MECHANICAL_TRAITS = frozenset((int(UnitTrait.Mechanical),      # 5
                                int(UnitTrait.LivingMetal),     # 0x3e8 = 1000
                                int(UnitTrait.Vehicle)))        # 0x405 = 1029


def _is_mechanical(ctx: dict) -> bool:
    """Mirror `IdunBattle.Entities.UnitExtensions$$IsMechanical` sur le substrat du MOVER."""
    return bool({int(t) for t in ((ctx or {}).get("unit_traits") or ())} & _MECHANICAL_TRAITS)


class TriggeredAbilityNonOwnerPlaybook:
    """Base : `IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps`
    yield 0 (la base ne pese rien ; seuls les concrets qui overrident comptent).

    Signature du port : `calculate_movement_utility_in_steps(tile, owner, is_friend, ctx, wt)` ou
      * `tile`      = la tuile candidate du mover (`UtilityMovementCase.get_MovementTile`) ;
      * `owner`     = l'enregistrement du PORTEUR de l'ability (le `owner` du natif), avec `pos` ;
      * `is_friend` = `UnitExtensions.IsFriend(case.unit, owner, state)` ;
      * `ctx`       = le dict par-decision `tile_leaf_ctx` (porte `unit_faction`, `elev_by_pos`, ...).
    Le natif passe le CASE entier ; le port passe ce que le CASE expose deja aux autres familles."""

    #: `<slot 4>` de `ITriggeredAbilityNonOwnerPlaybook` -- le predicat SANS argument du pre-gate
    #: `playbook.<slot 4> || IsFriend(sujet, owner)` d'`IterateAbilities`. C'est une donnee PAR
    #: CLASSE, jamais une constante de famille (#477-r35) : voir la docstring de tete du module.
    SLOT_4 = False
    #: La FACE du corps natif -- laquelle des TROIS entrees du dispatcher l'evalue, et donc dans
    #: QUEL composite le terme part (`Tile(7)` pour MOVE, `Damage(35)` pour ATTACK, `Repair(47)`
    #: pour REPAIR). Elle est LUE dans `data/symbols/<build>/metadata/non_owner_slot4.tsv`, jamais
    #: deduite du nom de la classe. La face ATTACK vit dans `non_owner_attack.py` (#271-r4).
    FACE = "MOVE"

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        return 0.0


class KustomForceFieldReworkedNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`KustomForceFieldReworkedNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook$$.ctor` : litteral
    `0x60b` = 1547 `KustomForceFieldReworked`, passif d'`orksBigMek` — HERO du pool spawnable).

    `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile :

        if (case.unit == null) yield break;
        if (!UnitExtensions.IsFriend(case.unit, owner, state)) yield break;
        ITile ownerTile = EntityExtensions.GetMainTile(owner, state);
        if (ownerTile == null) yield break;
        if (!TileExtensions.IsAdjacentTo(case.MovementTile, ownerTile)) yield break;
        Fix64 v = GetUtilityValue("KustomForceFieldReworked_FriendsLikeToBeAdjacent");
        if (UnitExtensions.HasFaction(case.unit, 5))            // UnitFaction.Orks
            v *= Fix64.FromInt(2);
        yield return v;

    Trois points que le decompile TRANCHE et qu'il ne faut pas deviner :

    * **Le `HasFaction` porte sur `case.unit`, PAS sur `owner`** — c'est le MOVER qui doit etre Ork
      pour doubler, pas le Big Mek (qui l'est toujours). Le terme separe donc DEUX AMIS de
      factions differentes autour du meme porteur : `x2` pour un Ork, `x1` pour un allie d'une
      autre faction. C'est ce qui le rend inexprimable par un poids unique.
    * **Le doublement est un `Fix64.op_Multiply` par `Fix64.FromInt(2)`**, pas un second poids BC :
      rien a chercher dans la table.
    * **La cle vit dans `TriggeredAbilitiesNonOwner`**, pas dans `TriggeredAbilities` (categorie
      distincte du meme `Utilities.Default`). Litteral LU (`probe_212_bc_key_literals.py` sur le
      symbole du `MoveNext`), pas devine.

    `IsAdjacentTo` = `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(a, b)` =
    `|elev(b) - elev(a)| < 2 && (a == b || ConnectivityComponent(a).IsNeighbour(b))` — mirror
    `battle_query.are_entities_adjacent`, le foyer qui porte la branche `a == b` (COURT-CIRCUIT
    D'IDENTITE, #433-r1) en plus de la distance hex 1 et de la porte d'elevation. ⚠ NE PAS retomber
    sur `battle_query.is_adjacent` : celui-la mirrore `TileQuery$$IterateAdjacentTiles` et exclut
    `a == b` a bon droit (distance 0). Cette branche est INATTEIGNABLE ici (la tuile du porteur est
    occupee, donc jamais candidate pour le mover) ; on la mirror quand meme plutot que de la
    supprimer sur un argument d'atteignabilite."""

    ABILITY_ID = int(TriggeredAbilityType.KustomForceFieldReworked)     # 0x60b = 1547
    KEY = "KustomForceFieldReworked_FriendsLikeToBeAdjacent"            # gameconfig vivant = 10

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        # `if (case.unit == null) yield break;` -- LU au desassembleur (`if (case+0x10 != 0)` garde
        # TOUT le corps). Ce gate est LOAD-BEARING depuis #271-r3 : le dispatcher n'ecarte plus le
        # regime SPAWN en amont, et sans lui ce terme verserait sa valeur sur une decision de spawn
        # ou le natif ne verse RIEN (`is_friend` y est calcule sur le PARENT, donc vrai ; le `x2`
        # d'`HasFaction` tomberait, mais le terme de base passerait) -- un +10 fantome, muet.
        if (ctx or {}).get("is_spawning"):
            return 0.0
        if not is_friend:                                    # UnitExtensions.IsFriend(case.unit, owner)
            return 0.0
        opos = (owner or {}).get("pos")
        if not opos:                                         # GetMainTile(owner) == null
            return 0.0
        tile, opos = (tile[0], tile[1]), (opos[0], opos[1])
        elev = (ctx or {}).get("elev_by_pos")
        neigh = bq.neigh_map(ctx)
        if not bq.are_entities_adjacent(tile, opos, elev, neigh):             # TileExtensions.IsAdjacentTo
            return 0.0
        v = float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
        if (ctx or {}).get("unit_faction") == int(UnitFaction.Orks):   # HasFaction(case.unit, 5)
            v *= 2.0
        return v


class ECogSupportPlaybookNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`ECogSupportPlaybookNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.ECogSupportPlaybookNonOwnerPlaybook$$.ctor` : litteral `0x5cf` =
    1487 `EcogSupport`, passif de `votanIronmaster` / Vynn -- HERO, HORS du pool par defaut).

    `IdunBattle.AI.Playbook.Loki.ECogSupportPlaybookNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps` : case @+0x20, owner @+0x28, playbook @+0x30 -- l'ordre
    n'est PAS celui de `PsychicFortressNonOwnerPlaybook`, qui met owner @+0x20 et case @+0x30) :

        if (case.unit == null) { yield return Fix64.Zero; yield break; }
        ITile ownerTile = EntityExtensions.GetMainTile(owner, State);
        if (ownerTile == null) { yield return Fix64.Zero; yield break; }
        if (!UnitExtensions.HasTrait(case.unit, 2)) yield break;                 // UnitTrait.Summon
        if (UnitExtensions.GetParent(case.unit, State, false) != owner) yield break;
        if (!TileExtensions.IsAdjacentTo(case.MovementTile, ownerTile)) yield break;
        yield return GetUtilityValue("EcogSupport_EcogAdjacentToParent");        // 10

    Quatre points que le decompile TRANCHE :

    * **`2` est `UnitTrait`.Summon** -- enum QUALIFIE. Homonymes a ecarter : `UnitFaction` 2,
      `EffectType` 2, `AbilityAttackType` 2 n'ont rien a voir. Le mover doit etre un SUMMON.
    * **`GetParent` porte le 3e argument `root = false`** (litteral `0` au call-site) : c'est le
      parent DIRECT (`ChildComponent.ParentId`), pas la racine de la chaine. Le pendant porte est
      `ctx["unit_parent_id"]` (`utilities/tile.py`), le meme canal que la face MOVE de
      `SaviorProtocolsPlaybook`.
    * **Les deux sorties precoces ne sont PAS des `yield break`** : `case.unit == null` et
      `ownerTile == null` yieldent `Fix64.Zero` (etats 1 et 2 de la SM) puis s'arretent. Sur la
      SOMME du dispatcher c'est indistinguable d'un break -- on le note parce que la structure de la
      SM le dit, pas parce que ca change le resultat.
    * **Le predicat de trait porte sur `case.unit` (le MOVER), pas sur `owner`.** Le terme dit « ce
      E-Cog aime rester colle a Vynn » : il ne se declenche donc QUE pendant le sweep de tuiles d'un
      summon du porteur, et il vaut 0 pour toute autre unite de son equipe.

    ⚠ AUCUN test `IsFriend` dans le corps -- contrairement a `KustomForceFieldReworkedNonOwnerPlaybook`.
    C'est le pre-gate `<slot 4> || IsFriend` d'`IterateAbilities` qui l'apporte (cf. en-tete du
    module). Ici il est de toute facon TRANSPARENT : `GetParent(case.unit) == owner` implique deja
    que le mover est le summon du porteur, donc de son equipe."""

    ABILITY_ID = int(TriggeredAbilityType.EcogSupport)                  # 0x5cf = 1487
    KEY = "EcogSupport_EcogAdjacentToParent"                            # gameconfig vivant = 10

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        # `if (case.unit == null) { yield return Fix64.Zero; yield break; }` -- etat 1 de la SM, LU.
        # Le gate etait IMPLICITE (en regime SPAWN `unit_traits` est absent, donc `HasTrait` tombait
        # de toute facon) ; il est EXPLICITE depuis #271-r3, parce que le dispatcher n'ecarte plus ce
        # regime en amont et qu'un gate implicite depend d'une cle que le ctx pourrait porter demain.
        if ctx.get("is_spawning"):
            return 0.0
        opos = (owner or {}).get("pos")
        if not opos:                                          # GetMainTile(owner, State) == null
            return 0.0
        # `HasTrait(case.unit, 2)` -- `ctx["unit_traits"]` porte les IDS `UnitTrait` du MOVER
        # (`entity_trait_ids` : kit gameconfig + traits accordes EN BATAILLE par le leaf `AddTrait`).
        if int(UnitTrait.Summon) not in {int(t) for t in (ctx.get("unit_traits") or ())}:
            return 0.0
        # `GetParent(case.unit, State, root: false) != owner` -> yield break.
        parent_uid, owner_uid = ctx.get("unit_parent_id"), (owner or {}).get("id")
        if parent_uid is None or owner_uid is None or int(parent_uid) != int(owner_uid):
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        ctx.get("elev_by_pos"), bq.neigh_map(ctx)):     # TileExtensions.IsAdjacentTo
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class PsychicFortressNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`PsychicFortressNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.PsychicFortressNonOwnerPlaybook$$.ctor` : litteral `1000`
    `PsychicFortress`, passif d'`ultraTigurius` -- HERO du pool spawnable).

    `IdunBattle.AI.Playbook.Loki.PsychicFortressNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# (champs de la SM : owner @+0x20, playbook @+0x28, case @+0x30 -- lus dans la
    methode-usine, PAS transposes de la classe voisine) :

        ITile ownerTile = EntityExtensions.GetMainTile(owner, State);
        if (ownerTile == null) yield break;
        if (!TileExtensions.IsAdjacentTo(case.MovementTile, ownerTile)) yield break;
        yield return GetUtilityValue("PSYCHICFORTRESS_AdjacentFriendly");        // 20

    C'est le corps le plus court de la famille : **aucun** gate sur le mover -- ni `IsFriend`, ni
    trait, ni faction, ni parent, ni `case.unit == null`. Le terme vaut donc 20 pour TOUTE tuile
    candidate adjacente au porteur, quelle que soit l'unite qui bouge.

    ⚠ Le « Friendly » du nom de la cle N'EST PAS porte par ce corps : il vient ENTIEREMENT du
    pre-gate `<slot 4> || IsFriend` d'`IterateAbilities` (slot 4 = `false`, cf. en-tete). Le porter
    dans le corps serait un doublon inoffensif ; ne pas le porter DU TOUT rendrait le terme actif
    pour les ennemis du porteur -- c'est exactement pourquoi ce residu exigeait de lire le slot
    avant d'enregistrer la classe.

    ⚠⚠ **CE CORPS YIELDE AUSSI EN REGIME SPAWN, et c'est l'un des trois seuls (#271-r3).** Ne pas
    lire `case.unit` n'est pas un detail de style : le natif itere cette feuille quand
    `case.unit == null && case.parent != null` (call-site `SortTilesByUtilityForSummon`), et rien
    ici ne s'y oppose -- le terme vaut 20 pour toute tuile de spawn adjacente au porteur AMI DU
    PARENT. **Ne JAMAIS ajouter un gate `is_spawning` a cette classe** : ce serait retirer un terme
    que le natif verse. Les DEUX autres sont `BookOfFateNonOwnerPlaybook` et la branche SPAWN de
    `MawClawsOfThyraxNonOwnerPlaybook`."""

    ABILITY_ID = int(TriggeredAbilityType.PsychicFortress)              # 1000
    KEY = "PSYCHICFORTRESS_AdjacentFriendly"                            # gameconfig vivant = 20

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        opos = (owner or {}).get("pos")
        if not opos:                                          # GetMainTile(owner, State) == null
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        (ctx or {}).get("elev_by_pos"), bq.neigh_map(ctx)):
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class KardiocoreGalvanusNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`KardiocoreGalvanusNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusNonOwnerPlaybook$$.ctor` : litteral `0x5b1` =
    1457 `KardiocoreGalvanus`, RELIQUE).

    `IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps` : `case @+0x20, playbook @+0x28, owner @+0x30` -- c'est la
    disposition d'`ECogSupport`, PAS celle de `PsychicFortress`) :

        if (case.unit == null)                       { yield return Fix64.Zero; yield break; }
        if (!UnitExtensions.IsMechanical(case.unit))   yield break;
        if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(owner, case.MovementTile))
            yield return GetUtilityValue("KardiocoreGalvanus_AdjacentFriendly");   // 20

    ⚠⚠ **CE TERME DORMAIT DANS TOUTES NOS MESURES.** `admecMarshall` ET `admecRuststalker` portent
    la relique 1457 **AU SEED** (`BC.Units[].TertiaryAbility = 1457`, niveau 1 -- etat 1 de la
    ventilation des reliques), sans que personne l'ait demandee : tout montage qui les spawne
    heritait donc de `+20` cote NATIF pendant que le port rendait 0. C'est exactement ce qui a rendu
    `#477-r31` ROUGE a sa premiere mesure (`X_nat = 30` pour `X_port = 10`), et ce cas-la avait du
    RETIRER la relique pour mesurer sa propre feuille. Depuis ce port, elle n'a plus besoin de l'etre.

    ⚠ Le slot `0x60` est `AreEntitiesAdjacent` d'ARITE 2 -- trois surcharges partagent ce nom
    (slots 96/97/98), et c'est le TYPE DES ARGUMENTS qui fixe la bonne : `(owner: IEntity,
    movementTile: ITile)` ne laisse que `AreEntitiesAdjacent(entity1, entity2)`. **Ne PAS deduire du
    NOM du slot ce que fait la methode** : c'est la faute que #477-r31 a du reparer sur un slot
    voisin. Le foyer porte est `battle_query.are_entities_adjacent` (porte d'elevation + court-circuit
    d'identite `a == b`, #433-r1), comme pour toute la famille.

    ⚠ `IsMechanical` n'est PAS `HasTrait(Mechanical)` : c'est la chaine de trois `HasTrait` en OU
    court-circuite (cf. `_is_mechanical`). Le gate est donc STRICTEMENT le meme que celui de la
    feuille `DoctrinaImperatives_AttractMechanicals` (#477-r31) -- meme gate, meme camp, memes
    tuiles : les deux termes sont INSEPARABLES par la geometrie, et seul le port des DEUX les rend
    additivement justes.

    AUCUN test `IsFriend` dans le corps : c'est le pre-gate `<slot 4> || IsFriend` d'`IterateAbilities`
    qui l'apporte (cf. en-tete du module), comme pour `PsychicFortress`.

    Porteurs (voie RELIQUE) : `admecMarshall`, `admecRuststalker` -- au pool ET **equipes au seed** ;
    `admecDestroyer` -- au pool, relique non equipee."""

    ABILITY_ID = int(TriggeredAbilityType.KardiocoreGalvanus)            # 0x5b1 = 1457
    KEY = "KardiocoreGalvanus_AdjacentFriendly"                          # gameconfig vivant = 20

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        # `if (case.unit == null) { yield Fix64.Zero; yield break; }` -- le regime SPAWN est le seul
        # ou le sujet manque. Gate LOAD-BEARING depuis #271-r3 : le dispatcher itere ce regime au
        # lieu de le court-circuiter, donc le 0 vient d'ICI, comme dans le natif.
        if ctx.get("is_spawning"):
            return 0.0
        if not _is_mechanical(ctx):                          # IsMechanical(case.unit)
            return 0.0
        opos = (owner or {}).get("pos")
        if not opos:                 # `AreEntitiesAdjacent` rend faux sur une entite sans tuile
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        ctx.get("elev_by_pos"), bq.neigh_map(ctx)):
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class BookOfFateNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`BookOfFateNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.BookOfFateNonOwnerPlaybook$$.ctor` : litteral `0x5b5` = 1461
    `BookOfFate`, RELIQUE).

    `IdunBattle.AI.Playbook.Loki.BookOfFateNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps` : `playbook @+0x20, owner @+0x28, case @+0x30` -- c'est une
    QUATRIEME disposition, distincte des trois deja mesurees par #433-r4-r3 et #433-r4-r3-r1. La
    transposition depuis une classe voisine est morte a chaque fois ; elle le serait encore ici) :

        if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(owner, case.MovementTile))
            yield return GetUtilityValue("BookOfFate_AdjacentSummons");            // 5

    C'est le corps le plus court de la famille avec `PsychicFortress` : **aucun gate**, pas meme
    `case.unit == null` -- le corps ne lit JAMAIS `case.unit`. Le terme vaut donc 5 pour toute tuile
    candidate adjacente au porteur AMI, quelle que soit l'unite qui bouge.

    ⚠ Le « Summons » du nom de la cle N'EST PAS porte par ce corps : il n'y a AUCUN
    `HasTrait(.., Summon)`. Le nom de cle decrit l'intention du designer, pas la condition -- le
    lire comme un gate ajouterait un filtre que le natif n'a pas. Le « Friendly » implicite, lui,
    vient ENTIEREMENT du pre-gate `<slot 4> || IsFriend` d'`IterateAbilities` (slot 4 = `false`).

    ⚠⚠ **CE CORPS YIELDE AUSSI EN REGIME SPAWN (#271-r3)** -- il ne lit JAMAIS `case.unit`, et le
    natif itere la feuille quand `case.unit == null && case.parent != null`. **Ne JAMAIS lui
    ajouter un gate `is_spawning`.** Cf. `PsychicFortressNonOwnerPlaybook`, meme cas.

    Porteurs (voie RELIQUE) : `blackPossession`, `thousInfernalMaster`, `thousSorcerer` -- au pool,
    relique NON equipee au seed (etat 2, montage `--equip-relic`)."""

    ABILITY_ID = int(TriggeredAbilityType.BookOfFate)                    # 0x5b5 = 1461
    KEY = "BookOfFate_AdjacentSummons"                                   # gameconfig vivant = 5

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        opos = (owner or {}).get("pos")
        if not opos:
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        (ctx or {}).get("elev_by_pos"), bq.neigh_map(ctx)):
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class NornCrownNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`NornCrownNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.NornCrownNonOwnerPlaybook$$.ctor` : litteral `0x5d7` = 1495
    `NornCrown`, RELIQUE).

    `IdunBattle.AI.Playbook.Loki.NornCrownNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps`, qui ecrit `case @+0x20, playbook @+0x28` et **N'ECRIT PAS
    `owner`**) :

        if (case.unit == null) yield break;
        if (!UnitExtensions.HasTrait(case.unit, 0x3ea) &&                 // UnitTrait.Psyker
            !UnitExtensions.HasTrait(case.unit, 0x2))   yield break;      // UnitTrait.Summon
        units = Query.<slot 0x79 = GetSurroundingFriends, arite 4>(
                    case.unit, TExtensions.ToList(case.MovementTile), 2, true);
        if (Enumerable.Any(units, <>c.<CalculateMovementUtilityInSteps>b__2_0))
            yield return GetUtilityValue("NornCrown_SummonsAndPsykers");  // 10

    predicat -- `IdunBattle.AI.Playbook.Loki.NornCrownNonOwnerPlaybook.u003Cu003Ec$$u003CCalculateMovementUtilityInStepsu003Eb__2_0` :

        return UnitExtensions.HasTrait(f, 0x7e8);                          // UnitTrait.Synapse

    QUATRE lectures qui ne se devinent pas :

    * **Le corps NE LIT PAS `owner`** -- la methode-usine ne stocke meme pas l'argument. Le terme ne
      depend donc NI de la position du porteur NI de rien de lui : il ne pese que le voisinage du
      MOVER. C'est le seul de la famille dans ce cas, et c'est ce qui le rend confrontable sans
      deplacer le porteur.
    * **Le gate est une DISJONCTION** (`Psyker` OU `Summon`), pas une conjonction -- a l'inverse de
      `RelicOfLostCadiaNonOwnerPlaybook`, qui, lui, conjugue `Imperial ET Summon`.
    * **`GetSurroundingFriends` est PUREMENT GEOMETRIQUE** : son itineraire
      (`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`) est le
      DISQUE hex de rayon 2, **sans porte d'elevation** -- donc `battle_query.is_surrounding`, et
      surtout PAS `are_entities_adjacent`, qui, lui, porte `|delta elev| < 2`.
      `includeCenter = true` (litteral `1`) : la tuile candidate elle-meme compte.
    * **L'ACTEUR N'EST PAS EXCLU.** `GetSurroundingFriends(actor, ...)` filtre « amis de `actor` » et
      ne retire jamais `actor` (meme lecture que `GetAdjacentFriends` dans `friends_in_range.py`) ;
      or pendant tout le sweep le mover est ENCORE SUR SON ORIGINE. Un mover Synapse se satisfait
      donc LUI-MEME des que son origine est dans le disque de rayon 2 de la tuile candidate. Le port
      l'inclut explicitement -- l'oublier rendrait 0 sur des tuiles ou le natif rend 10.

    Porteur (voie RELIQUE) : `tyranNeurothrope` -- au pool, relique NON equipee au seed (etat 2).
    Il est lui-meme `Synapse` ET `Psyker`, donc il peut servir a la fois de porteur et de source du
    predicat."""

    ABILITY_ID = int(TriggeredAbilityType.NornCrown)                     # 0x5d7 = 1495
    KEY = "NornCrown_SummonsAndPsykers"                                  # gameconfig vivant = 10
    RADIUS = 2                                                           # litteral du call-site

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        if ctx.get("is_spawning"):                       # `case.unit == null` -> yield break
            return 0.0
        if not (_has_trait(ctx, UnitTrait.Psyker)        # HasTrait(.., 0x3ea)
                or _has_trait(ctx, UnitTrait.Summon)):   # HasTrait(.., 0x2)
            return 0.0
        tile = (tile[0], tile[1])
        # `GetSurroundingFriends(case.unit, [MovementTile], 2, includeCenter: true)` -- les AMIS du
        # mover, disque hex de rayon 2, SANS porte d'elevation. `friend_units` porte deja le filtre
        # de camp, et ses `traits` sont des NOMS (`entity_trait_names`) la ou `ctx.unit_traits` sont
        # des IDS (`entity_trait_ids`) : les deux substrats sont les memes, pas leur forme.
        # L'ACTEUR, lui, est ABSENT de `friend_units` (self-exclu par construction du ctx) alors que
        # le natif le GARDE -> il est re-injecte juste apres.
        for u in (ctx.get("friend_units") or ()):
            p = u.get("pos")
            if p and bq.is_surrounding(tile, (p[0], p[1]), self.RADIUS, True) \
                    and UnitTrait.Synapse.name in (u.get("traits") or ()):
                return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
        sp = ctx.get("self_pos")
        if sp and bq.is_surrounding(tile, (sp[0], sp[1]), self.RADIUS, True) \
                and _has_trait(ctx, UnitTrait.Synapse):
            return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
        return 0.0


class AdjacentToOwnerNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E`
    -- base INTERMEDIAIRE, et le CORPS EST PARTAGE par ses 10 classes concretes (#433-r4-r3-r1).

    `IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps`,
    qui ecrit `case @+0x20, playbook @+0x28, owner @+0x30`) :

        if (case.unit == null) yield break;
        if (!Query.AreEntitiesAdjacent(case.Position.Tiles, owner)) yield break;
        yield return GetAdjacencyUtility(case.unit, owner);

    QUATRE lectures qui ne se devinent pas, et dont AUCUNE ne se transpose des voisins nommes :

    * **La disposition de la SM est une TROISIEME, distincte des deux deja mesurees.**
      `ECogSupportPlaybookNonOwnerPlaybook` ecrit `case@+0x20, owner@+0x28, playbook@+0x30` ;
      `PsychicFortressNonOwnerPlaybook` ecrit `owner@+0x20, playbook@+0x28, case@+0x30` ; ici
      c'est `case@+0x20, playbook@+0x28, owner@+0x30`. Les trois ordres sont DIFFERENTS.
    * **Le gate d'adjacence n'est PAS celui des voisins nommes.** Eux appellent
      `IdunBattle.Entities.EntityExtensions$$GetMainTile(owner)` puis
      `IdunBattle.Entities.TileExtensions$$IsAdjacentTo(case.MovementTile, ownerTile)` -- UNE
      tuile contre UNE tuile. Ici le corps lit le champ `Query` du playbook (`+0x60` dans le bloc
      de champs, confirme par
      `IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$get_Query`
      qui lit le MEME `+0x60` ; `get_State` lit `+0x40`) et invoque
      `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` dans sa surcharge
      `(IReadOnlyList<ITile> tiles, IEntity unit)` -- la LISTE des tuiles du mover
      (`case.Position` a `+0x18`, dont le champ 0 est la liste que
      `IdunBattle.Core.UnitPosition$$get_MainTile` indexe) contre TOUTES les tuiles du porteur.
      Cette surcharge delegue a `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(tiles1,
      tiles2)`, qui rend VRAI des qu'UN couple `(t1, t2)` satisfait la primitive tuile-a-tuile --
      la MEME que celle des voisins, court-circuit d'identite `t1 == t2` compris (#433-r1).
      ⚠ L'appariement se fait sur les TYPES DES ARGUMENTS, pas sur l'indice de slot : le 1er est
      la liste de tuiles du `UnitPosition` embarque dans le case, le 2e l'ENTITE porteur -- ce qui
      ne laisse que la surcharge `(tiles, unit)` des trois. Les indices de slot cites ailleurs dans
      le port pour cette meme methode sont DATES et ont bouge de +1 a ce build (residu #433-r3-r3) :
      s'y fier ici aurait designe une autre surcharge. De toute facon les TROIS convergent vers
      `MovementUtil$$AreTilesAdjacent` et ne different que par les `GetTiles` qu'elles interposent,
      donc le port est INSENSIBLE a cette question pour des entites d'une seule tuile.
      Pour un mover ET un porteur d'UNE seule tuile les deux formes coincident exactement ; le
      port mirrore donc `battle_query.are_entities_adjacent`. Ce qu'il ne couvre PAS : une entite
      MULTI-TUILES (Machine of War), pour laquelle le natif est PLUS permissif -- residu nomme.
    * **Le corps ne teste NI `IsFriend` NI quoi que ce soit du porteur.** Le « Friendly » que
      portent plusieurs cles vient ENTIEREMENT du pre-gate `<slot 4> || IsFriend`
      d'`IterateAbilities`, mirrore dans le dispatcher (cf. en-tete du module).
    * **`GetAdjacencyUtility(movingUnit, owner)` est le SEUL point de variation**, et les 10 corps
      concrets LU UN PAR UN ne lisent QUE `movingUnit` -- jamais `owner`, jamais l'etat, jamais une
      stat. C'est ce qui rend ces termes GREFFABLES sur une unite du pool quand leur porteur est
      npc-only (regle « npc GREFFABLE » du `CLAUDE.md`).

    Le port passe `ctx` la ou le natif passe `case.unit` : `ctx` EST le substrat du sujet de la
    decision (`unit_traits`, `unit_faction`), c'est-a-dire du mover."""

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        """`AdjacentToOwnerNonOwnerPlaybook<T>.GetAdjacencyUtility(movingUnit, owner)` -- abstrait
        cote natif (invoque par slot de vtable `+0x208` depuis le corps partage). Chaque concret le
        surcharge ; aucun ne rend la valeur de base."""
        raise NotImplementedError

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        # `if (case.unit == null) yield break;` -- le regime SPAWN est le seul ou le sujet manque.
        # Gate LOAD-BEARING depuis #271-r3 (le dispatcher itere ce regime) : il porte le 0 des DIX
        # concrets du corps partage.
        if ctx.get("is_spawning"):
            return 0.0
        opos = (owner or {}).get("pos")
        # `AreEntitiesAdjacent(tiles, unit)` commence par `if (unit == null) return false;` et
        # `AreTilesAdjacent` rend faux sur une liste de tuiles vide : porteur sans position -> 0.
        if not opos:
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        ctx.get("elev_by_pos"), bq.neigh_map(ctx)):
            return 0.0
        return float(self.get_adjacency_utility(ctx, wt))


class AmuletOfTheVoidwyrmNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.AmuletOfTheVoidwyrmNonOwnerPlaybook$$GetAdjacencyUtility` :

        if (!UnitExtensions.HasTrait(movingUnit, 2)) return Fix64.Zero;   // UnitTrait.Summon
        return GetUtilityValue("AmuletOfTheVoidwyrm_AdjacentSummons");

    Porteurs (voie RELIQUE) : `genesKelermorph`, `genesPrimus`, `genesBiophagus` -- tous au pool,
    relique NON equipee au seed (etat 2 du `CLAUDE.md`, montage `--equip-relic`)."""

    ABILITY_ID = int(TriggeredAbilityType.AmuletOfTheVoidwyrm)          # 0x5b8 = 1464
    KEY = "AmuletOfTheVoidwyrm_AdjacentSummons"                          # gameconfig vivant = 5

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if not _has_trait(ctx, UnitTrait.Summon):                        # HasTrait(.., 0x2)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class IconOfObstinacyNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattleLogic.Playbook.Triggered.Loki.IconOfObstinacyNonOwnerPlaybook$$GetAdjacencyUtility` :

        if (!UnitExtensions.HasTrait(movingUnit, 0x40f)) return Fix64.Zero;  // TerminatorArmour
        return GetUtilityValue("IconOfObstinacy_TerminatorFriendLikesToBeAdjacent");

    ⚠ `0x40f` = 1039 = `UnitTrait.TerminatorArmour` -- enum QUALIFIE, pas devine du nom de la cle.
    Porteur : `astarLysander` (HERO, hors pool par defaut -> injection catalogue)."""

    ABILITY_ID = int(TriggeredAbilityType.IconOfObstinacy)               # 0x610 = 1552
    KEY = "IconOfObstinacy_TerminatorFriendLikesToBeAdjacent"           # gameconfig vivant = 20

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if not _has_trait(ctx, UnitTrait.TerminatorArmour):              # HasTrait(.., 0x40f)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class MyWillBeDoneOverlordNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.MyWillBeDoneOverlordNonOwnerPlaybook$$GetAdjacencyUtility` :

        if (!UnitExtensions.IsMechanical(movingUnit)) return Fix64.Zero;
        return GetUtilityValue("MyWillBeDoneOverlord_FriendlyMechanicalLikeAnuphet");

    ⚠ `IsMechanical` n'est PAS `HasTrait(Mechanical)` : cf. `_is_mechanical`.
    Porteur : `necroOverlord` (Anuphet) -- HERO **du pool**, passif, donc confrontable sans aucun
    montage. C'est la cible de confrontation de ce cas."""

    ABILITY_ID = int(TriggeredAbilityType.MyWillBeDoneOverlord)          # 0x614 = 1556
    KEY = "MyWillBeDoneOverlord_FriendlyMechanicalLikeAnuphet"          # gameconfig vivant = 10

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if not _is_mechanical(ctx):                                      # IsMechanical(movingUnit)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class NetherRealmCasketNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.NetherRealmCasketNonOwnerPlaybook$$GetAdjacencyUtility` :

        if (!UnitExtensions.HasTrait(movingUnit, 5)) return Fix64.Zero;  // UnitTrait.Mechanical
        return GetUtilityValue("NetherRealmCasket_AdjacentMechanicals");

    ⚠ Ici c'est bien `HasTrait(Mechanical)` NU, PAS `IsMechanical` -- la difference se lit au
    decompile (un seul `HasTrait`, pas la chaine de trois) et elle est OBSERVABLE : un `Vehicle`
    ou un `LivingMetal` non `Mechanical` compte pour `MyWillBeDoneOverlord` et PAS pour celui-ci.

    Porteurs (voie RELIQUE) : `necroDestroyer`, `necroSpyder` -- au pool, relique non equipee."""

    ABILITY_ID = int(TriggeredAbilityType.NetherRealmCasket)             # 0x5b6 = 1462
    KEY = "NetherRealmCasket_AdjacentMechanicals"                        # gameconfig vivant = 5

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if not _has_trait(ctx, UnitTrait.Mechanical):                    # HasTrait(.., 0x5)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class PrimarchOfTheFirstLegionNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.PrimarchOfTheFirstLegionNonOwnerPlaybook$$GetAdjacencyUtility` :

        if (!UnitExtensions.HasFaction(movingUnit, 0xa)) return Fix64.Zero;  // UnitFaction.DarkAngels
        return GetUtilityValue("PrimarchOfTheFirstLegion_AdjacentDarkAngels");

    ⚠⚠ **L'ID DE CETTE CLASSE NE SE LIT PAS A SON `.ctor`.**
    `IdunBattle.AI.Playbook.Loki.PrimarchOfTheFirstLegionNonOwnerPlaybook$$.ctor` passe `0x5b6` =
    **1462** = `NetherRealmCasket` a sa base -- le MEME litteral et le MEME `MethodInfo*` de base
    inflate que `NetherRealmCasketNonOwnerPlaybook`, si bien que cette classe derive litteralement
    d'`AdjacentToOwnerNonOwnerPlaybook<NetherRealmCasketAbility>` (c'est pourquoi `classes.tsv`
    n'a AUCUNE instanciation `AdjacentToOwnerNonOwnerPlaybook<PrimarchOfTheFirstLegion...>`).
    C'est un copier-coller du jeu.

    Or ce n'est pas le `.ctor` qui indexe le registre : `IdunBattle.AI.PlaybookDatabase$$
    LoadPlaybookNonOwner` lit un dict dont la cle est posee au SITE D'ENREGISTREMENT, dans
    `IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`. Ce site a ete BALAYE
    (`probe_433_r4_r3_r1_non_owner_registry.py`) : `1511` y figure, et `1462` n'y figure QU'UNE
    fois. Donc **1511**, et aucune des deux entrees n'ecrase l'autre. Prendre le litteral du
    `.ctor` aurait, au choix, tue l'entree `1462` de `NetherRealmCasket` (dont le porteur est au
    pool par la voie relique) ou pose une entree morte -- deux regressions silencieuses.

    Porteur : `darkaBossLion` (npc UNIQUEMENT). GREFFABLE : le corps ne lit ni stat ni trait du
    caster (regle « npc GREFFABLE » du `CLAUDE.md`)."""

    ABILITY_ID = int(TriggeredAbilityType.PrimarchOfTheFirstLegion)      # 1511 -- REGISTRE, pas ctor
    KEY = "PrimarchOfTheFirstLegion_AdjacentDarkAngels"                 # gameconfig vivant = 20

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if (ctx or {}).get("unit_faction") != int(UnitFaction.DarkAngels):   # HasFaction(.., 0xa)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class PropheticSentinelNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.PropheticSentinelNonOwnerPlaybook$$GetAdjacencyUtility` -- le
    SEUL des dix dont les deux termes se CUMULENT :

        Fix64 x = Fix64.Zero;
        if (UnitExtensions.HasTrait(movingUnit, 0x3ea))  x += GetUtilityValue(<statics[0]>);
        if (UnitExtensions.HasTrait(movingUnit, 0x7ea))  x += GetUtilityValue(<statics[1]>);
        return x;

    ⚠ Les deux cles ne sont PAS des litteraux inline : le corps lit deux champs STATIQUES, que
    `IdunBattle.AI.Playbook.Loki.PropheticSentinelNonOwnerPlaybook$$.cctor` remplit -- et il les
    remplit dans l'ordre `statics[0] = "PropheticSentinel_PsykerLikesToBeAdjacent"`,
    `statics[1] = "PropheticSentinel_ChaosLikesToBeAdjacent"`. L'appariement trait -> cle est donc
    LU, pas deduit du nom : `0x3ea` = 1002 = `UnitTrait.Psyker` -> cle Psyker,
    `0x7ea` = 2026 = `UnitTrait.Chaos` -> cle Chaos. (Les deux valent 20 au gameconfig, donc
    l'appariement est numeriquement inobservable -- raison de plus pour le lire.)

    Une unite Psyker ET Chaos recoit donc **40**, pas 20 : c'est le seul terme non booleen de la
    famille. Porteur : `thousSekhetar` (HERO, hors pool par defaut)."""

    ABILITY_ID = int(TriggeredAbilityType.PropheticSentinel)             # 0x607 = 1543
    KEY_PSYKER = "PropheticSentinel_PsykerLikesToBeAdjacent"            # statics[0], vivant = 20
    KEY_CHAOS = "PropheticSentinel_ChaosLikesToBeAdjacent"              # statics[1], vivant = 20

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        x = 0.0
        if _has_trait(ctx, UnitTrait.Psyker):                            # HasTrait(.., 0x3ea)
            x += float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY_PSYKER))
        if _has_trait(ctx, UnitTrait.Chaos):                             # HasTrait(.., 0x7ea)
            x += float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY_CHAOS))
        return x


class RedemptionOfTheRisenNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.RedemptionOfTheRisenNonOwnerPlaybook$$GetAdjacencyUtility` :

        if (!UnitExtensions.HasFaction(movingUnit, 0xa)) return Fix64.Zero;  // UnitFaction.DarkAngels
        return GetUtilityValue("RedemptionOfTheRisen_AdjacentDarkAngels");

    Corps STRICTEMENT identique a celui de `PrimarchOfTheFirstLegionNonOwnerPlaybook`, cle et
    valeur comprises (20) -- seule l'ability differe.

    ⚠⚠ **VOLONTAIREMENT ABSENTE DU REGISTRE `NON_OWNER_MOVE_PLAYBOOKS` ci-dessous : DEAD CODE sur
    le build `rnca9r7q6c`.** L'ability 1522 n'est attribuee a AUCUNE unite. Deux sources
    independantes :
      * `unit_map.py find --ability RedemptionOfTheRisen` -> 0 unite sur les 5 voies derivables ;
      * balayage TEXTUEL du gameconfig entier : les 4 occurrences du nom sont sa DEFINITION
        (`variables.hp`), son `baseMultiplier`, et ses DEUX cles d'utilite
        (`RedemptionOfTheRisen_DarkAngelFriendsInRange` cote owner,
        `RedemptionOfTheRisen_AdjacentDarkAngels` cote non-owner). Aucune liste de passifs d'unite
        ne la cite -- l'ability existe au catalogue sans porteur.
    L'enregistrer ajouterait du code que le dispatcher n'itere JAMAIS : c'est exactement le patron
    #419 (« porte mais non cable »), et son cliquet le refuse. La classe est conservee parce que la
    RE est faite et juste ; la reactiver au build ou une unite portera 1522 tient en UNE ligne au
    registre. C'est un residu NOMME, pas un oubli."""

    ABILITY_ID = int(TriggeredAbilityType.RedemptionOfTheRisen)          # 0x5f2 = 1522
    KEY = "RedemptionOfTheRisen_AdjacentDarkAngels"                     # gameconfig vivant = 20

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if (ctx or {}).get("unit_faction") != int(UnitFaction.DarkAngels):   # HasFaction(.., 0xa)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class RelicOfLostCadiaNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.RelicOfLostCadiaNonOwnerPlaybook$$GetAdjacencyUtility` -- le
    seul des dix a porter une CONJONCTION de deux traits :

        if (UnitExtensions.HasTrait(movingUnit, 0x1a) &&                  // UnitTrait.Imperial
            UnitExtensions.HasTrait(movingUnit, 0x2))                     // UnitTrait.Summon
            return GetUtilityValue("RelicOfLostCadia_AdjacentImperialSummons");
        return Fix64.Zero;

    Porteurs (voie RELIQUE) : `astraBullgryn`, `astraOrdnance`, `astraPrimarisPsy` -- au pool."""

    ABILITY_ID = int(TriggeredAbilityType.RelicOfLostCadia)              # 0x5b3 = 1459
    KEY = "RelicOfLostCadia_AdjacentImperialSummons"                     # gameconfig vivant = 5

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if not (_has_trait(ctx, UnitTrait.Imperial)                       # HasTrait(.., 0x1a)
                and _has_trait(ctx, UnitTrait.Summon)):                   # HasTrait(.., 0x2)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class TimesplinterMantleNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattleLogic.Playbook.Triggered.Loki.TimesplinterMantleNonOwnerPlaybook$$GetAdjacencyUtility` :

        if (!UnitExtensions.IsMechanical(movingUnit)) return Fix64.Zero;
        return GetUtilityValue(<statics[0]>);

    La cle vient d'un champ STATIQUE, rempli par le `.cctor` avec
    `"TimesplinterMantle_FriendlyMechanicalLikeThothmek"` (LU, pas devine par prefixe).
    Porteur : `necroChronomancer` (Thothmek) -- HERO, hors pool par defaut."""

    ABILITY_ID = int(TriggeredAbilityType.TimesplinterMantle)            # 0x5fe = 1534
    KEY = "TimesplinterMantle_FriendlyMechanicalLikeThothmek"           # gameconfig vivant = 5

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        if not _is_mechanical(ctx):                                      # IsMechanical(movingUnit)
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class WatchedOverNonOwnerPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.WatchedOverNonOwnerPlaybook$$GetAdjacencyUtility` -- le corps le
    plus court des dix, AUCUN gate sur le mover :

        return GetUtilityValue("WatchedOver_AdjacentFriends");

    Le terme vaut donc 20 pour TOUTE unite amie adjacente au porteur, comme
    `PsychicFortressNonOwnerPlaybook` -- et pour la meme raison, c'est le pre-gate `IsFriend`
    d'`IterateAbilities` qui porte seul le « Friends » de la cle.

    Porteur : `darkaSmnWatcher` -- un SUMMON. Il compte (regle SUMMON du `CLAUDE.md`) : ici c'est
    le PORTEUR, donc on l'OBSERVE sur le plateau et ce sont les AUTRES unites qui bougent."""

    ABILITY_ID = int(TriggeredAbilityType.WatchedOver)                   # 0x5f4 = 1524
    KEY = "WatchedOver_AdjacentFriends"                                  # gameconfig vivant = 20

    def get_adjacency_utility(self, ctx: dict, wt) -> float:
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class PurgeResponseNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`PurgeResponseNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.PurgeResponseNonOwnerPlaybook$$.ctor` : litteral `0x5f6` = 1526
    `PurgeResponse`, PASSIF d'unite).

    `IdunBattle.AI.Playbook.Loki.PurgeResponseNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps` : `case @+0x20, playbook @+0x28, owner @+0x30` -- la
    disposition d'`ECogSupport`/`Kardiocore`, PAS celle de `BookOfFate`) :

        if (case.unit == null) yield break;
        if (!UnitExtensions.HasFaction(case.unit, 0x14)) yield break;        // UnitFaction.LeaguesOfVotann
        if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(case.MovementTile, owner))
            yield return GetUtilityValue("PurgeResponse_FriendlyVotannLikeSteeljack");   // 20

    Trois lectures qui ne se devinent pas :

    * **le gate porte sur la FACTION du MOVER**, pas sur celle du porteur ni sur un trait. C'est le
      seul de la famille dans ce cas, et c'est ce qui le rend confrontable SANS toucher au porteur :
      il suffit d'amener un mover `LeaguesOfVotann`. Le canal existait deja (`ctx.unit_faction`) ;
    * **`0x14` est QUALIFIE contre `IdunBattle.Entities.Enum.UnitFaction`** -- le TYPE DECLARE de
      l'argument, lu dans `frida/methods.tsv`
      (`UnitExtensions.HasFaction(unit:IEntity, faction:IdunBattle.Entities.Enum.UnitFaction)`),
      pas deduit de l'ordinal. La surcharge JUMELLE prend un `System.String` et n'est PAS celle-ci ;
      le natif convertit d'ailleurs l'enum en son NOM (`System.Enum$$ToString`) avant de deleguer ;
    * **l'ordre des arguments d'adjacence est INVERSE** de celui de `KardiocoreGalvanus`
      (`(tile, owner)` ici, `(owner, tile)` la-bas). Sans effet -- `AreEntitiesAdjacent(entity1,
      entity2)` est symetrique -- mais il interdit de conclure quoi que ce soit de la FORME du
      call-site : c'est la SURCHARGE (le type des arguments) qui fixe le slot, jamais leur ordre.

    AUCUN test `IsFriend` dans le corps : le « Friendly » de la cle vient ENTIEREMENT du pre-gate
    `<slot 4> || IsFriend` d'`IterateAbilities` (slot 4 = `false`), comme pour `PsychicFortress`.

    Porteurs (voie PASSIF d'unite) : `votanSmnSteeljack` (SUMMON) et `votanNpc2Steeljack` (npc) --
    aucun hero. Le corps ne lit du porteur QUE sa position (aucune stat, aucun trait), donc
    l'ability se GREFFE sur une unite du pool (`catalog_inject.graft_passive_ability`) : c'est la
    voie du `CLAUDE.md` pour un porteur npc-only. Le MOVER, lui, doit etre `LeaguesOfVotann` : les
    **9** unites de cette faction sont TOUTES hors pool, donc le montage passe par une injection
    catalogue (etat 3)."""

    ABILITY_ID = int(TriggeredAbilityType.PurgeResponse)                 # 0x5f6 = 1526
    KEY = "PurgeResponse_FriendlyVotannLikeSteeljack"                    # gameconfig vivant = 20
    FACTION = UnitFaction.LeaguesOfVotann                                # 0x14 = 20

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        # `if (case.unit == null) yield break` -- le regime SPAWN est le seul ou le sujet manque.
        # Gate LOAD-BEARING depuis #271-r3 : le dispatcher itere ce regime au lieu de le
        # court-circuiter, donc le 0 vient d'ICI, exactement comme dans le corps natif.
        if ctx.get("is_spawning"):
            return 0.0
        fac = ctx.get("unit_faction")
        if fac is None or int(fac) != int(self.FACTION):      # HasFaction(case.unit, LeaguesOfVotann)
            return 0.0
        opos = (owner or {}).get("pos")
        if not opos:                 # `AreEntitiesAdjacent` rend faux sur une entite sans tuile
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        ctx.get("elev_by_pos"), bq.neigh_map(ctx)):
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class MawClawsOfThyraxNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`MawClawsOfThyraxNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.MawClawsOfThyraxNonOwnerPlaybook$$.ctor` : litteral `0x5bd` =
    1469 `MawClawsOfThyrax`, RELIQUE).

    `IdunBattle.AI.Playbook.Loki.MawClawsOfThyraxNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps` : `case @+0x20, playbook @+0x28, owner @+0x30`) :

        if (case.unit != null) {                                        // BRANCHE SUJET
            if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(case.MovementTile, owner)
                && UnitExtensions.HasTrait(case.unit, 0x2)              // UnitTrait.Summon
                && Query.<slot 0x92 = AreFriends, arite 3>(case.unit, owner, 0))
                yield return GetUtilityValue("MawClawsOfThyrax_AdjacentSummons");   // 5
            yield break;
        }
        if (case.parent == null) yield break;                           // BRANCHE SPAWN
        if (Query.<slot 0x60 = AreEntitiesAdjacent, arite 2>(case.MovementTile, owner)
            && Query.<slot 0x92 = AreFriends, arite 3>(case.parent, owner, 0))
            yield return GetUtilityValue("MawClawsOfThyrax_AdjacentSummons");       // 5

    QUATRE lectures qui ne se devinent pas :

    * **C'est le SEUL corps de la famille a porter DEUX branches**, et la branche SPAWN
      (`case.unit == null && case.parent != null`) n'a PAS le gate `Summon` -- le sujet spawne est
      presume l'etre, c'est le PARENT qu'elle teste. **PORTEE depuis #271-r3** : le `ctx` de spawn
      porte desormais un substrat campe sur le PARENT (`utilities/tile.py::_spawn_leaf_ctx`), donc
      `is_friend` y EST `AreFriends(case.parent, owner, ByCurrentTeam)` -- exactement le second
      terme de cette branche. Les deux branches ne different que par le gate `Summon` ;
    * **le slot `0x92` est `AreFriends`, pas un predicat de position.** Resolu par la vtable RUNTIME
      (`probe_27_4g_battlequery_slots.py --slots 0x92` : slot d'interface `0x92` + 4 = index `0x96`
      = `AreFriends`). Le voisin `0x8e` est `GetAllEnemiesOf` : lire le slot a un pres ici aurait
      donne un predicat de camp INVERSE ;
    * **son 3e argument `0` est un `UnitTeamSelectionType`, pas un booleen.** Type DECLARE lu dans
      `frida/methods.tsv` (`BattleQuery.AreFriends(unit1, unit2,
      selectionType:IdunBattle.Entities.Enum.UnitTeamSelectionType)`) ; `0` = `ByCurrentTeam` ;
    * **ce gate `AreFriends` est REDONDANT, et c'est MESURE, pas suppose.**
      `BattleQuery$$AreFriends(a, b, sel)` delegue a `UnitExtensions$$IsFriend(a, b, sel, State)`,
      dont la branche `sel == ByCurrentTeam` est mot pour mot le corps de la surcharge a trois
      arguments `IsFriend(a, b, state)` -- celle du pre-gate d'`IterateAbilities`, applique au
      MEME sujet (`case.unit ?? case.parent`). Il ne peut donc jamais couper. Le port le mirrore
      quand meme (on mirrore le corps, pas l'economie qu'on pourrait en faire), via le `is_friend`
      que le dispatcher passe deja.

    Porteurs (voie RELIQUE, `catalog_inject.relic_carriers`) : `genesPatriarch`, `tyranParasite`,
    `tyranTyrantGuard`, `tyranWingedPrime` -- les QUATRE au pool, relique NON equipee au seed
    (etat 2, `--equip-relic`). Le MOVER, lui, doit porter `Summon` : les **59** unites qui le
    portent au gameconfig sont TOUTES `kind == summons` et aucune n'est au pool, donc le montage
    ACCORDE le trait (`catalog_inject.add_unit_trait`) -- c'est exactement le substrat qu'interroge
    `HasTrait` (kit + traits accordes en bataille, cf. `_has_trait`)."""

    ABILITY_ID = int(TriggeredAbilityType.MawClawsOfThyrax)              # 0x5bd = 1469
    KEY = "MawClawsOfThyrax_AdjacentSummons"                             # gameconfig vivant = 5
    #: 3e argument LITTERAL du call-site `AreFriends` -- `0`, qualifie contre le type declare.
    TEAM_SELECTION = UnitTeamSelectionType.ByCurrentTeam

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        opos = (owner or {}).get("pos")
        if not opos:
            return 0.0
        # `AreEntitiesAdjacent(case.MovementTile, owner)` -- 1er terme des DEUX branches.
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        ctx.get("elev_by_pos"), bq.neigh_map(ctx)):
            return 0.0
        # LE BRANCHEMENT. `is_spawning` == `UtilityMovementCase$$get_IsSpawning` ==
        # `case.unit == null && case.parent != null`, c'est-a-dire EXACTEMENT le `else` du natif une
        # fois sa sortie `case.parent == null -> yield break` prise en compte (ce ctx n'existe que
        # si le parent existe). La branche SPAWN n'a PAS le gate `Summon` : le sujet qui apparait
        # est presume l'etre, et c'est le PARENT que teste son `AreFriends`.
        if not ctx.get("is_spawning"):
            if not _has_trait(ctx, UnitTrait.Summon):        # HasTrait(case.unit, 0x2)
                return 0.0
        # `AreFriends(case.unit ?? case.parent, owner, ByCurrentTeam)` == `IsFriend(.., owner, state)` :
        # le dispatcher a deja calcule ce booleen pour le pre-gate -- sur le SUJET quand il existe,
        # sur le PARENT en regime SPAWN -- on le RELIT au lieu de le refaire.
        if not is_friend:
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class HaywireMineNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`HaywireMineNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.HaywireMineNonOwnerPlaybook$$.ctor` : litteral `0x5fb` = 1531
    `HaywireMine`, PASSIF d'unite).

    `IdunBattle.AI.Playbook.Loki.HaywireMineNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__5$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps` : `case @+0x20, playbook @+0x28, owner @+0x30`) :

        if (case.unit == null) yield break;
        if (!TileExtensions.GetSteppableUnit(case.MovementTile, State, out u)) yield break;
        cfg = playbook.<+0x58>.<+0x20>;                      // AbilityConfiguration du playbook
        if (!UnitExtensions.HasUnitId(u, cfg.GetStringConstant(8), State)) yield break;
        if (UnitExtensions.IsFriend(case.unit, owner, State))
            yield return GetUtilityValue("HaywireMine_FriendlyAvoidMine");   // -50
        else
            yield return GetUtilityValue("HaywireMine_EnemyAvoidMine");      // -30

    ⚠⚠ **C'EST LA SEULE FACE **MOVE** DONT LE `<slot 4>` VAUT `true`, ET C'EST CE QUI REND SA
    BRANCHE ENNEMI ATTEIGNABLE.** Le pre-gate d'`IterateAbilities` est
    `playbook.<slot 4> || IsFriend(case.unit ?? case.parent, owner)`. Le `<slot 4>` est
    `get_ShouldIncludingEnemiesWhenCalculate` (cf. l'en-tete du module) : cette classe le DECLARE
    dans son `Il2CppTypeDefinition`, et son corps -- fondu par l'ICF sur
    `UnityEngine.U2D.IK.Solver2D$$DoValidate` -- est `b0 01 c3` = `mov al,1 ; ret`. Balayage
    COMPLET des 28 concrets (#477-r37) : elle et `NoHidingFromTheWatchersNonOwnerPlaybook` (face
    ATTACK) sont les DEUX seules a surcharger ; les 26 autres heritent le `xor eax,eax ; ret` de la
    base.

    ⚠ **Le premier critere essaye etait FAUX, et il rendait VERT.** Il postulait que le bloc d'une
    classe COMMENCE a son `.ctor` -- donc que « `.ctor` + `Calculate*` + les six corps de la SM »
    valait « aucun override ». Les six classes de #477-r35 le satisfaisaient toutes, y compris
    celle-ci. C'est la MESURE LIVE qui l'a renverse : sur la tuile minee du montage `haywire`,
    `X_nat` valait **-130** pour un port a **-100** -- il manquait exactement **-30**, la valeur de
    `HaywireMine_EnemyAvoidMine`, et aucune autre ability du montage n'a de `*NonOwnerPlaybook`
    (verifie sur les six ids presents). Le critere de REMPLACEMENT (« l'entree qui PRECEDE le
    `.ctor` ») etait lui aussi faux, dans les deux sens -- cf. l'en-tete du module. Corollaire de
    doctrine, seul acquis stable : `slot 4` est une donnee PAR CLASSE.

    Deux autres lectures qui ne se devinent pas :

    * **le gate ne porte NI sur le mover NI sur le porteur, mais sur l'OCCUPANT de la tuile
      candidate.** `GetSteppableUnit` = l'occupant unique de la tuile filtre sur `UnitTrait.Steppable`
      (0x1b), puis `HasUnitId` compare son id d'unite -- via
      `idun.shared.UnitNamingConventions$$GetUnitIdWithoutRarity`, c'est-a-dire le `split(':')[0]`,
      donc SANS suffixe de rarete -- a la constante de config ;
    * **`8` est un `AbilityConstantType`, pas un entier nu** : type DECLARE lu dans
      `frida/methods.tsv` (`AbilityConfiguration.GetStringConstant(constantType:
      IdunBattle.Configuration.AbilityConstantType)`), et `8` = `unitToSpawn`. Au gameconfig vivant
      `abilities.HaywireMine.constants.unitToSpawn == "astarSmnHaywireMine"` -- la mine que pose
      l'ability. Le terme est donc un REPOUSSOIR : le mover evite les tuiles minees de son camp.

    Porteurs (voie PASSIF d'unite) : `astarCyrus` (HERO, hors pool) et `astarCyrus_LHE` (npc). Le
    corps ne lit du porteur QUE le camp (`IsFriend`, deja garanti), donc l'ability se GREFFE sur
    une unite du pool. Ce qu'il faut monter, c'est la MINE : `astarSmnHaywireMine` est un SUMMON
    `Steppable`, amene par `rl_duel build --explicit-stats`."""

    ABILITY_ID = int(TriggeredAbilityType.HaywireMine)                   # 0x5fb = 1531
    KEY_FRIENDLY = "HaywireMine_FriendlyAvoidMine"                       # gameconfig vivant = -50
    KEY_ENEMY = "HaywireMine_EnemyAvoidMine"                             # gameconfig vivant = -30
    #: SEULE classe de la famille a le porter VRAI (`return 1`, cf. docstring) : le dispatcher lui
    #: yielde donc AUSSI les porteurs ENNEMIS, ce qui rend `KEY_ENEMY` atteignable.
    SLOT_4 = True
    CONFIG_ID = "HaywireMine"
    #: `GetStringConstant(config, 8)` -- la constante, PAS son ordinal nu.
    MINE_CONSTANT = AbilityConstantType.unitToSpawn                      # 8

    def mine_unit_ids(self) -> frozenset:
        """`AbilityConfiguration.GetStringConstant(config, unitToSpawn)`, elargi a l'id VISUEL.

        Meme lecture que `GeminaeSuperiaPlaybook.summon_unit_ids` (#165b) : le `visualId` offline
        porte l'id de CONFIG pour les unites spawnees par le moteur et l'id VISUEL pour celles
        seedees depuis le live, donc on matche les deux. `HasUnitId` compare l'id SANS suffixe de
        rarete (`GetUnitIdWithoutRarity` = `split(':')[0]`), d'ou le meme decoupage ici."""
        import gameconfig as GC
        consts = (GC.ability(self.CONFIG_ID) or {}).get("constants") or {}
        uid = consts.get(self.MINE_CONSTANT.name)
        if not uid:
            return frozenset()                       # cle absente -> `GetStringConstant` LEVE ;
        uid = str(uid).split(":")[0]                 # le port se degrade a « aucun terme »
        vis = (GC.unit(uid) or {}).get("visualId")
        return frozenset(str(x).split(":")[0] for x in (uid, vis) if x)

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        if ctx.get("is_spawning"):                   # `case.unit == null` -> yield break
            return 0.0
        occ = get_steppable_unit((tile[0], tile[1]), ctx)   # GetSteppableUnit(case.MovementTile)
        if occ is None:
            return 0.0
        vis = occ.get("vis")
        if not vis or str(vis).split(":")[0] not in self.mine_unit_ids():   # HasUnitId(u, cst)
            return 0.0
        # `IsFriend(case.unit, owner, State)` -- les DEUX branches sont atteignables ici, et elles
        # seules dans toute la famille : `SLOT_4 = True` fait yielder AUSSI les porteurs ennemis.
        return float(wt.sub("TriggeredAbilitiesNonOwner",
                            self.KEY_FRIENDLY if is_friend else self.KEY_ENEMY))


class FirstAmongTraitorsNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`FirstAmongTraitorsNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.FirstAmongTraitorsNonOwnerPlaybook$$.ctor` : litteral `0x428` =
    1064 `FirstAmongTraitors`, PASSIF d'unite).

    `IdunBattle.AI.Playbook.Loki.FirstAmongTraitorsNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE
    `$$CalculateMovementUtilityInSteps` : `case @+0x20, playbook @+0x28, owner @+0x30` -- la
    disposition d'`ECogSupport`/`Kardiocore`/`PurgeResponse`) :

        if (case.unit == null) yield break;
        if (!UnitExtensions.HasTrait(case.unit, 0x7ea)) yield break;      // UnitTrait.Chaos
        ITile tile = case.MovementTile;
        var ownerTiles = EntityExtensions.GetTiles(owner, State);
        int d = Query.<slot 0x6d = GetDistance, arite 2>(tile, ownerTiles);
        if (playbook.<+0x58> == null) yield break;                       // l'ability
        if (d <= FirstAmongTraitorsAbility.GetRange(ability))
            yield return GetUtilityValue("FIRSTAMONGTRAITORS_SurroundingOwner");   // 20

    ⚠⚠ **CETTE FACE A ETE CLASSEE « TERME INERTE, 0 UNITE SUR 1083 » PAR #477-r35, ET C'EST FAUX.**
    Le compte ne regardait que `gameconfig.unit(vis).traits`, c'est-a-dire exactement la source dont
    `engine/entities/traits/unit_trait.py` ecrit qu'elle NE CONTIENT PAS le pseudo-trait de
    GRANDE-ALLIANCE (« AUCUNE unite ne le porte : la couche META l'injecte dans la
    BattleConfiguration »). Le substrat que `HasTrait` interroge est
    `BaseUnitComponent+0x40`, ou le BC a DEJA pose le trait derive de la GrandAlliance -- mirror
    `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` (`Chaos -> 0x7ea`). Re-mesure sur le foyer
    porte (`entity_trait_ids`) : **127 unites sur 683** portent `UnitTrait.Chaos`. Le terme n'est
    donc pas inerte -- il MORD, et il mordait deja cote NATIF pendant que le port rendait 0.

    ⚠ `0x6d` est `GetDistance` d'ARITE 2 -- slot LU dans
    `data/symbols/<build>/metadata/interface_slots.tsv` (`IBattleQuery` 108/109/110 partagent le
    nom `GetDistance`). La surcharge est fixee par le TYPE des arguments : `(tileA: IEntity,
    tilesB: IList<IEntity>)`. Les quatre surcharges de `BattleQuery$$GetDistance` delegent au MEME
    corps `IdunBattle.Core.Services.MovementQuery$$GetDistance(originTiles, destinationTiles)` --
    distance HEXAGONALE minimale entre deux ENSEMBLES de tuiles, sans pathfinding ni elevation, et
    `int.MaxValue` sur un ensemble vide. Le foyer porte est `battle_query.get_distance`, deja
    mirror 1:1 : le porteur sans tuile rend donc `DISTANCE_UNREACHABLE > range` -> 0, comme le natif.

    ⚠ `GetRange` n'est PAS une variable de niveau : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    FirstAmongTraitorsAbility$$GetRange` est `AbilityConfiguration.GetNumberConstant(config, 0x16)`,
    et `0x16` est un **`AbilityConstantType`** (`range`) -- type DECLARE lu dans `frida/methods.tsv`,
    pas deduit de l'ordinal. Au gameconfig vivant `abilities.FirstAmongTraitors.constants.range`
    vaut `2`. La comparaison est `<=`, donc un rayon de 2 INCLUS (la tuile du porteur comprise,
    distance 0).

    AUCUN test `IsFriend` dans le corps : le `<slot 4>` de cette classe vaut `false` (elle ne
    declare pas `get_ShouldIncludingEnemiesWhenCalculate`), donc c'est le pre-gate
    d'`IterateAbilities` qui restreint aux porteurs AMIS -- comme pour `PsychicFortress`.

    Porteur (voie PASSIF d'unite) : `blackAbaddon` -- HERO **DU POOL**, passif de kit, donc
    confrontable SANS AUCUN MONTAGE. C'est le seul confond arme sans montage que
    `probe_477r33_non_owner_registry_gaps.py --offline-only` recense (etape 0bis)."""

    ABILITY_ID = int(TriggeredAbilityType.FirstAmongTraitors)            # 0x428 = 1064
    KEY = "FIRSTAMONGTRAITORS_SurroundingOwner"                          # gameconfig vivant = 20
    CONFIG_ID = "FirstAmongTraitors"
    #: `GetNumberConstant(config, 0x16)` -- la constante, PAS son ordinal nu.
    RANGE_CONSTANT = AbilityConstantType.range                           # 0x16 = 22

    def range_tiles(self):
        """`FirstAmongTraitorsAbility$$GetRange` = `GetNumberConstant(config, AbilityConstantType.range)`.

        `None` = constante absente -> `GetNumberConstant` LEVE cote natif ; le port se degrade en
        « aucun terme » plutot que d'inventer un rayon."""
        import gameconfig as GC
        consts = (GC.ability(self.CONFIG_ID) or {}).get("constants") or {}
        v = consts.get(self.RANGE_CONSTANT.name)
        return None if v is None else int(v)

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        # `if (case.unit == null) yield break` -- le regime SPAWN est le seul ou le sujet manque.
        # Gate LOAD-BEARING depuis #271-r3 : le dispatcher itere ce regime au lieu de le
        # court-circuiter, donc le 0 vient d'ICI, exactement comme dans le corps natif.
        if ctx.get("is_spawning"):
            return 0.0
        if not _has_trait(ctx, UnitTrait.Chaos):             # HasTrait(case.unit, 0x7ea)
            return 0.0
        rng = self.range_tiles()
        if rng is None:
            return 0.0
        opos = (owner or {}).get("pos")
        # `EntityExtensions.GetTiles(owner)` vide -> `GetDistance` rend `int.MaxValue` : jamais <= range.
        d = bq.get_distance([(tile[0], tile[1])],
                            [(opos[0], opos[1])] if opos else ())
        if d > rng:
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


def _rarity_of(ctx: dict, uid):
    """`IdunBattle.Entities.Components.BaseUnitComponent.Rarity` (+0x74) de l'entite `uid`.

    C'est l'UNIQUE champ que lisent les trois gates natifs de rarete (`UnitExtensions$$HasRarity`,
    `HasRarityTrigger$$ShouldTrigger`, `UnitsWithRaritySelector$$Select`), et les corps ci-dessous
    l'inlinent directement (`GetComponent<BaseUnitComponent>(u)->[0x74] == 5`).

    Canal : `ctx["scene"].ctx(uid).rarity` (`UnitContext.rarity`, capteur #1039, consomme #999-r3).
    TRI-ETAT strict : `None` = canal NON MESURE -- les gates rendent alors FAUX. JAMAIS un repli
    sur `Rarity.Common`, qui est une valeur plausible et rendrait l'absence indiscernable.

    ⚠ DEUX des trois `*_leaf_ctx` publient `scene` (`tile_leaf_ctx` et `scene_tile_leaf_ctx`, les
    jumeaux de PREDICTION) ; `runner_tile_leaf_ctx` ne le publie PAS. Sur ce troisieme substrat les
    gates de rarete se taisent -- degradation PARTIELLE et NOMMEE, exactement celle que
    `FuryOfTheAncientsPlaybook` porte deja pour la meme raison. Mesure et cliquet :
    `probe_1036r3_porteurs_non_owner_restants.py` etape 3."""
    sc = (ctx or {}).get("scene")
    if sc is None or uid is None:
        return None
    c = sc.ctx(uid)
    return getattr(c, "rarity", None) if c is not None else None


def _has_rarity(ctx: dict, uid, rarity) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasRarity(u, r)` reduit a sa comparaison.

    ⚠ Le natif porte un gate de PLUS que l'inline des corps voisins : `HasRarity` commence par
    `u.<EntityType> == 1` (= `EntityType.Unit`), la ou `CabalOfSorcerersPlaybook` et
    `WisdomOfTheAncientsPlaybook` lisent `GetComponent<BaseUnitComponent>(u)->[0x74]` sans ce
    filtre. L'ecart n'est observable que sur une entite NON-Unit portant un `BaseUnitComponent` ;
    il est note ici plutot que gomme, parce que seul `MastersOfManoeuvre` passe par la fonction
    NOMMEE."""
    r = _rarity_of(ctx, uid)
    return r is not None and int(r) == int(rarity)


def _adjacent_friends_of_mover(tile, ctx: dict):
    """`IBattleQuery.<slot 0x83 = GetAdjacentFriends(from: IEntity, unit: IEntity)>(tile, case.unit)`.

    Corps natif LU (`IdunBattle.Core.Services.BattleQuery$$GetAdjacentFriends` @ la surcharge
    `(IEntity, IEntity)`, celle que fixe le TYPE des arguments -- `UtilityMovementCase$$
    get_MovementTile` est declaree `-> IdunBattle.Core.IEntity`) :

        var pid = unit.GetComponent<OwnerComponent>().CurrentPlayerEntityId;
        var tiles = IterateAdjacentTiles(from, onlyEmptyOrSteppable: false,
                                         onlyWalkableTiles: true, allowTemporary: true);
        return GetUnitsOnTiles(tiles, friendsOf: <joueur pid>, enemiesOf: null,
                               ignoreSteppables: false);

    Donc : les unites du camp DU MOVER posees sur une tuile VOISINE de la tuile candidate, au sens
    d'`IterateAdjacentTiles` -- liste d'adjacence STOCKEE + porte d'elevation `|dElev| < 2`, la
    primitive que `battle_query.is_adjacent` mirrore (et NON `are_entities_adjacent`, qui ajoute le
    court-circuit d'identite `a == b` que cet itinerraire-la n'a pas).

    ⚠ **LE MOVER N'EST PAS EXCLU PAR LA QUERY, ET LE PORT N'A PAS A LE RE-INJECTER.** La query le
    garde (il est encore SUR SON ORIGINE pendant tout le sweep, cf. `NornCrownNonOwnerPlaybook`),
    mais les TROIS corps qui l'appellent ouvrent leur boucle sur `if (u == case.unit) continue`.
    Or `ctx["friend_units"]` est deja SELF-EXCLU par construction. Les deux exclusions coincident
    exactement : re-injecter le mover ici puis le re-filtrer serait un aller-retour sans effet, et
    l'oublier dans un corps qui, lui, n'aurait PAS le `continue` serait un sous-comptage. Le jour
    ou un tel corps arrive, c'est ICI qu'il faudra le distinguer.

    ⚠ Le filtre `onlyWalkableTiles: true` du natif n'est PAS porte : `is_adjacent` est le foyer
    commun a tous les `GetAdjacent*` du port (cf. `battle_query.count_adjacent` et
    `non_owner_attack._adjacent_friend_count`), et lui ajouter une porte ici forkerait l'adjacence
    de la famille pour un ecart qui n'est observable que sur une unite posee sur une tuile
    non-walkable. Ecart NOMME, commun, jamais silencieux."""
    elev, neigh = (ctx or {}).get("elev_by_pos"), bq.neigh_map(ctx)
    t = (tile[0], tile[1])
    for u in ((ctx or {}).get("friend_units") or ()):
        p = u.get("pos")
        if p and bq.is_adjacent(t, (p[0], p[1]), elev, neigh):
            yield u


class CabalOfSorcerersPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.CabalOfSorcerersPlaybook`
    (`$$.ctor` : litteral `0x5d8` = 1496 `CabalOfSorcerers`, MYTHIQUE de MACHINE OF WAR).

    ⚠ Le NOM de la classe native n'a PAS le suffixe `NonOwnerPlaybook` -- c'est l'un des trois
    concrets qu'un grep par nom rate (avec `WisdomOfTheAncientsPlaybook` et
    `VoltagheistFieldPlaybook`), et c'est ce qui a fait circuler un compte de 25 concrets pour 28.

    `...CabalOfSorcerersPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`, remis en
    C# depuis le decompile (champs de la SM LUS DANS LA METHODE-USINE : `case @+0x20,
    playbook @+0x28, owner @+0x30`) :

        if (case.unit == null) yield break;
        var buc = case.unit.GetComponent<BaseUnitComponent>();
        if (buc.Rarity != 5) yield break;                          // Rarity.Mythic
        if (!buc.HasTrait(0x3ea)) yield break;                      // UnitTrait.Psyker
        foreach (u in Query.<slot 0x83 = GetAdjacentFriends>(case.MovementTile, case.unit)) {
            if (u == case.unit) continue;
            var b = u.GetComponent<BaseUnitComponent>();
            if (b.Rarity == 5 && b.HasTrait(0x10) && b.HasTrait(0x3ea))   // Mythic & Hero & Psyker
                yield return GetUtilityValue("CabalOfSorcerers_AffectUnits");
            if (u == owner)
                yield return GetUtilityValue("CabalOfSorcerers_AffectUnits");
        }

    Trois lectures qui ne se devinent pas :

    * **le second membre est un OU, pas une seconde passe** : le natif teste `u == owner` seulement
      quand le triple predicat a echoue, et les deux branches yieldent la MEME valeur. Le terme
      vaut donc 20 ou 0, jamais 40 -- il s'arrete au PREMIER voisin qualifie ;
    * **le gate du mover est une CONJONCTION `Mythic ET Psyker`**, celui du voisin une conjonction
      de TROIS (`Mythic ET Hero ET Psyker`). `WisdomOfTheAncientsPlaybook`, dont le corps est le
      jumeau, n'a ni le `Psyker` du mover ni celui du voisin : les deux ne sont PAS
      interchangeables ;
    * **`0x10` = `UnitTrait.Hero` et `0x3ea` = `UnitTrait.Psyker`** -- enums QUALIFIES contre
      `IdunBattle.Entities.Enum.UnitTrait`, pas deduits des ordinaux.

    Cle BC LUE (`probe_212_bc_key_literals.py` sur le symbole du `MoveNext`) :
    `CabalOfSorcerers_AffectUnits`, au gameconfig vivant `Default.TriggeredAbilitiesNonOwner` = 20.

    ⚠⚠ **VOLONTAIREMENT ABSENTE DU REGISTRE : BLOCAGE D'ETAGE MESURE (#1036-r3).** Ses DEUX
    porteurs (`thousDaemonPrince`, `thousNpcMowDaemonPrince`) sont des MACHINES OF WAR (voie
    `mythicAbilities`). Or l'univers de porteurs du dispatcher porte est bati sur des entites
    POSITIONNEES -- les trois `*_leaf_ctx` exigent une position pour entrer une unite dans
    `friend_units`/`enemy_units` -- et une MoW n'a AUCUNE tuile (`AddMachineOperation$$Execute` ne
    lui donne pas de `PositionComponent`, `snapshot._load_machines` non plus). La paire
    `(playbook, owner)` ne serait donc JAMAIS yieldee : l'inscrire au registre serait le patron
    #419. Le corps est porte parce que la RE est faite et juste ; le cabler tiendra en UNE ligne le
    jour ou l'univers du dispatcher s'elargira (foyer `engine/utilities/tile.py`, pendant exact de
    ce que #999-r3-r1-r1 a fait pour les deux agregateurs d'aura).
    ⚠ La fiche accusait la RARETE (<< aucun canal `rarity` cote port, verrou de CAPTEUR >>) : c'est
    PERIME depuis #1039 / #999-r3, et le canal est atteignable ici par `ctx["scene"]`. Mesure et
    cliquet : `probe_1036r3_porteurs_non_owner_restants.py`,
    `tests/engine/test_1036r3_faces_non_owner_restantes_offline.py`."""

    ABILITY_ID = int(TriggeredAbilityType.CabalOfSorcerers)              # 0x5d8 = 1496
    KEY = "CabalOfSorcerers_AffectUnits"                                 # gameconfig vivant = 20

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        if ctx.get("is_spawning"):                       # `case.unit == null` -> yield break
            return 0.0
        if not _has_rarity(ctx, ctx.get("uid"), Rarity.Mythic):          # buc.Rarity != 5
            return 0.0
        if not _has_trait(ctx, UnitTrait.Psyker):                        # !buc.HasTrait(0x3ea)
            return 0.0
        owner_uid = (owner or {}).get("id")
        for u in _adjacent_friends_of_mover(tile, ctx):
            noms = u.get("traits") or ()
            if (_has_rarity(ctx, u.get("id"), Rarity.Mythic)
                    and UnitTrait.Hero.name in noms                      # b.HasTrait(0x10)
                    and UnitTrait.Psyker.name in noms):                  # b.HasTrait(0x3ea)
                return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
            if owner_uid is not None and u.get("id") == owner_uid:       # u == owner
                return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
        return 0.0


class WisdomOfTheAncientsPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.WisdomOfTheAncientsPlaybook`
    (`$$.ctor` : litteral `0x5ab` = 1451 `WisdomOfTheAncients`, MYTHIQUE de MACHINE OF WAR).

    Second concret sans suffixe `NonOwnerPlaybook`.
    `...WisdomOfTheAncientsPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`
    (SM : `case @+0x20, playbook @+0x28, owner @+0x30`) :

        if (case.unit == null) yield break;
        if (case.unit.GetComponent<BaseUnitComponent>().Rarity != 5) yield break;   // Mythic
        foreach (u in Query.<slot 0x83 = GetAdjacentFriends>(case.MovementTile, case.unit)) {
            if (u == case.unit) continue;
            var b = u.GetComponent<BaseUnitComponent>();
            if (b.Rarity == 5 && b.HasTrait(0x10))                                  // Mythic & Hero
                yield return GetUtilityValue("WisdomOfTheAncients_AffectUnits");
            if (u == owner)
                yield return GetUtilityValue("WisdomOfTheAncients_AffectUnits");
        }

    C'est le JUMEAU de `CabalOfSorcerersPlaybook` a DEUX gates pres, et c'est la seule difference :
    **aucun `Psyker`**, ni sur le mover ni sur le voisin. Transposer l'un depuis l'autre aurait
    ajoute deux filtres que le natif n'a pas -- degradation RESTRICTIVE silencieuse.

    Cle BC LUE : `WisdomOfTheAncients_AffectUnits`, gameconfig vivant = 20.

    ⚠⚠ HORS REGISTRE, meme blocage d'ETAGE que `CabalOfSorcerersPlaybook` : porteurs
    `ultraDreadnought` / `ultraNpcMoWDreadnought`, deux MACHINES OF WAR (voie `mythicAbilities`).
    Cf. la docstring de la classe jumelle."""

    ABILITY_ID = int(TriggeredAbilityType.WisdomOfTheAncients)           # 0x5ab = 1451
    KEY = "WisdomOfTheAncients_AffectUnits"                              # gameconfig vivant = 20

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        if ctx.get("is_spawning"):                       # `case.unit == null` -> yield break
            return 0.0
        if not _has_rarity(ctx, ctx.get("uid"), Rarity.Mythic):
            return 0.0
        owner_uid = (owner or {}).get("id")
        for u in _adjacent_friends_of_mover(tile, ctx):
            if (_has_rarity(ctx, u.get("id"), Rarity.Mythic)
                    and UnitTrait.Hero.name in (u.get("traits") or ())):
                return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
            if owner_uid is not None and u.get("id") == owner_uid:
                return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
        return 0.0


class MastersOfManoeuvreNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`IdunBattle.AI.Playbook.Loki.MastersOfManoeuvreNonOwnerPlaybook`
    (`$$.ctor` : litteral `0x5e4` = 1508 `MastersOfManoeuvre`, MYTHIQUE de MACHINE OF WAR).

    `...u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`, remis en C# depuis le decompile :

        if (case.unit == null)                        { yield return Fix64.Zero; yield break; }
        if (!UnitExtensions.HasRarity(case.unit, 5))  { yield return Fix64.Zero; yield break; }
        foreach (u in Query.<slot 0x84 = GetAdjacentFriends(case.Position, case.unit)>) {
            if (u == case.unit)                        continue;
            if (!UnitExtensions.HasFaction(u, 0xa))    continue;    // UnitFaction.DarkAngels
            if (!UnitExtensions.HasRarity(u, 5))       continue;    // Rarity.Mythic
            yield return GetUtilityValue("MastersOfManoeuvre_AdjacentFriendlyMythicDA");
        }

    QUATRE lectures qui ne se devinent pas :

    * ⚠⚠ **LA METHODE-USINE N'ECRIT PAS `owner`.**
      `$$CalculateMovementUtilityInSteps` pose `playbook @+0x28` et `case @+0x20` et LAISSE `+0x30`
      -- que la SM reutilise pour son ENUMERATEUR. Ce corps ne lit donc JAMAIS le porteur, ni sa
      position ni son identite. Il partage ce trait avec `NornCrownNonOwnerPlaybook` seulement ;
    * **le gate de rarete passe par la fonction NOMMEE** `UnitExtensions$$HasRarity`, la ou les
      deux jumeaux ci-dessus inlinent la lecture du composant. `HasRarity` porte un gate de plus
      (`<EntityType> == 1`), cf. `_has_rarity` ;
    * **la surcharge d'adjacence est le slot `0x84`, pas `0x83`** : son 1er argument est
      `case.<+0x18>` = `case.Position` (un `UnitPosition`), pas la tuile. Les deux surcharges
      convergent sur le meme voisinage NATIF ; l'ecart ne porte que sur une entite MULTI-TUILES ;
    * **`0xa` est `UnitFaction.DarkAngels`** -- TYPE DECLARE lu dans `frida/methods.tsv`
      (`UnitExtensions.HasFaction(unit, faction: IdunBattle.Entities.Enum.UnitFaction)`). Le nom de
      la cle BC le CONFIRME independamment : `..._AdjacentFriendlyMythicDA`.

    Cle BC LUE : `MastersOfManoeuvre_AdjacentFriendlyMythicDA`, gameconfig vivant = 25.

    ⚠⚠ HORS REGISTRE, meme blocage d'ETAGE : porteurs `darkaStormSpeeder` /
    `darkaNpcMowStormSpeeder`, deux MACHINES OF WAR. Cf. `CabalOfSorcerersPlaybook`."""

    ABILITY_ID = int(TriggeredAbilityType.MastersOfManoeuvre)            # 0x5e4 = 1508
    KEY = "MastersOfManoeuvre_AdjacentFriendlyMythicDA"                  # gameconfig vivant = 25
    FACTION = UnitFaction.DarkAngels                                     # 0xa = 10

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        ctx = ctx or {}
        if ctx.get("is_spawning"):                       # `case.unit == null` -> yield Fix64.Zero
            return 0.0
        if not _has_rarity(ctx, ctx.get("uid"), Rarity.Mythic):          # HasRarity(case.unit, 5)
            return 0.0
        for u in _adjacent_friends_of_mover(tile, ctx):
            # `HasFaction(u, DarkAngels)` -- meme mirror que la face ATTACK (`_unit_faction`) : le
            # natif compare `Enum.ToString(UnitFaction)` au `FactionComponent+0x30`, et le pendant
            # offline est le `FactionId` du gameconfig, jamais un entier.
            if faction_value(u.get("vis")) != int(self.FACTION):
                continue
            if not _has_rarity(ctx, u.get("id"), Rarity.Mythic):         # HasRarity(u, 5)
                continue
            return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
        return 0.0


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner` : singleton par TYPE d'ability, cache
# dict@0xa0 + factories dict@0x98.
#
# COMPTE RE-DERIVE (#433-r4-r3-r1) de `data/symbols/<build>/frida/classes.tsv`, en filtrant sur le
# PARENT et non sur le nom : **28** classes concretes derivent de `TriggeredAbilityNonOwnerPlaybook
# <T>` -- **18** directement, **10** via `AdjacentToOwnerNonOwnerPlaybook<T>`.
# ⚠ Le compte de 25 qui circulait est un compte par NOM : trois concrets ne portent PAS le suffixe
# `NonOwnerPlaybook` (`CabalOfSorcerersPlaybook`, `VoltagheistFieldPlaybook`,
# `WisdomOfTheAncientsPlaybook`) et echappaient donc au grep -- deux d'entre eux ont pourtant bien
# une face MOVE (`CabalOfSorcerersPlaybook$$CalculateMovementUtilityInSteps`,
# `WisdomOfTheAncientsPlaybook$$CalculateMovementUtilityInSteps`), le troisieme une face REPAIR.
# Ventilation par FACE, lue aux state machines `<Calculate*>d__N` de chaque classe :
#   MOVE   24  (12 directes nommees + 2 directes sans suffixe + les 10 du corps partage)
#   ATTACK  3  (`ShieldOfFaith`, `NoHidingFromTheWatchers`, `WayOfTheShortBlade`)
#   REPAIR  1  (`VoltagheistFieldPlaybook`)
# ⚠ Le compte de 25 N'EST PAS le seul a s'etre re-glisse : le residu #477-r33 le citait a nouveau,
# et sa liste de « 13 manquants » melangeait TROIS faces ATTACK (`ShieldOfFaith`,
# `WayOfTheShortBlade`, `NoHidingFromTheWatchers`, qui ne passent PAS par cette feuille), oubliait
# les DEUX concrets sans suffixe (`CabalOfSorcerers`, `WisdomOfTheAncients`) et attribuait
# `MastersOfManoeuvre` a `orksRuntherd`, dont la relique du seed est en realite
# `1475 SupaCyborkBody` -- laquelle n'a AUCUN playbook non-owner. RE-DERIVER, jamais recopier :
# `probe_477r33_non_owner_registry_gaps.py --offline-only` rend le tableau complet.
# Au registre ci-dessous : **19** faces MOVE (3 de #433-r4-r3 + 9 d'#433-r4-r3-r1 + 3 de #477-r33
# + 3 de #477-r35 + 1 de #477-r37). Il reste **4** faces MOVE non portees + `RedemptionOfTheRisen`,
# PORTEE mais deliberement HORS registre (zero porteur), toutes des derivees DIRECTES.
# Ces 4 restantes, et POURQUOI elles restent (residu #477-r37-r1) :
#   `1451`, `1496`, `1508`     -- gates sur la RARETE (`HasRarity(u, Mythic)` = `BaseUnitComponent
#                                 +0x74 == 5`), et AUCUN canal `rarity` n'existe cote port. Le
#                                 verrou est un CAPTEUR MANQUANT, pas une limite de montage : le
#                                 seed BC porte deja 10 unites `Rarity == 5` et `--unit-stat
#                                 "<vis>:Rarity=5"` l'ecrit par unite. Ce qu'il faudrait :
#                                 `combatSnapshot.units[].rarity` <- `IdunBattle.Entities.Components.
#                                 BaseUnitComponent.Rarity`, donc une fenetre de reinject ;
#   `1478 SabreOfSacrifice`    -- son gate est un ARBRE DSL, pas un predicat imperatif :
#                                 `SabreOfSacrificeAbility$$IsAffectedSummon` construit
#                                 `AreEqual(Parent(mover), <caster>) & IsUnitWithVisualId(mover,
#                                 GetStringConstant(unitId))` et le playbook l'EXECUTE par vtable
#                                 `+0x188` sur une struct de contexte de 0x128 octets (owner a
#                                 `+0x18`). Il doit donc sortir en arbre DSL (#149), et il lui
#                                 manque en plus le canal `UtilityMovementCase$$StaysOnTile`.
#
# Absence du registre == `LoadPlaybookNonOwner` rend null == la paire n'est jamais yieldee : MEME
# degradation que le natif, pas un trou.
# ⚠ Cet argument ne vaut QUE pour un type d'ability SANS classe native `*NonOwnerPlaybook`. Pour
# une classe qui EXISTE, l'absence du registre est un ecart -- c'etait le residu #433-r4-r3, ferme
# pour `EcogSupport` et `PsychicFortress`, puis #433-r4-r3-r1 pour les dix d'`AdjacentToOwner`.
# ⚠ La cle est l'id du SITE D'ENREGISTREMENT (`InitializePlaybookBuilders`), pas le litteral du
# `.ctor` : les deux DIVERGENT pour `PrimarchOfTheFirstLegion` (cf. sa docstring).
NON_OWNER_MOVE_PLAYBOOKS: dict = {
    # #271 — DEMASQUE par le refresh `catalog_inject.refresh_ai_utilities` : la cle valait 0 dans la
    # table de la CAPTURE, elle vaut 10 au gameconfig VIVANT. Avant le refresh, natif et moteur
    # etaient d'accord ET faux tous les deux.
    int(TriggeredAbilityType.KustomForceFieldReworked): KustomForceFieldReworkedNonOwnerPlaybook(),
    # #433-r4-r3 — les deux classes natives dont `CalculateMovementUtilityInSteps` appelle la
    # primitive d'adjacence sans etre au registre. Les deux cles valent PAREIL dans la capture
    # (`data/seed-bc.json`) et au gameconfig vivant (10 / 20), donc pas de piege #271 ici : le terme
    # mordait deja cote NATIF pendant que le port rendait 0.
    int(TriggeredAbilityType.EcogSupport): ECogSupportPlaybookNonOwnerPlaybook(),        # 1487
    int(TriggeredAbilityType.PsychicFortress): PsychicFortressNonOwnerPlaybook(),        # 1000
    # #477-r33 -- trois derivees DIRECTES de plus, choisies par leur ATTEIGNABILITE (aucun port
    # speculatif) : `1457` est **equipee au seed** sur `admecMarshall` ET `admecRuststalker`, donc
    # elle armait un terme de +20 dans TOUT montage qui les spawne -- c'est le confond paye ROUGE
    # par #477-r31 ; `1461` et `1495` sont des reliques de porteurs DU POOL (etat 2, `--equip-relic`).
    # Recensement re-derive et decompte des confonds : `probe_477r33_non_owner_registry_gaps.py`.
    int(TriggeredAbilityType.KardiocoreGalvanus): KardiocoreGalvanusNonOwnerPlaybook(),  # 1457
    int(TriggeredAbilityType.BookOfFate): BookOfFateNonOwnerPlaybook(),                  # 1461
    int(TriggeredAbilityType.NornCrown): NornCrownNonOwnerPlaybook(),                    # 1495
    # #433-r4-r3-r1 -- les DIX concrets d'`AdjacentToOwnerNonOwnerPlaybook<T>`, fermes d'un seul
    # geste parce qu'ils PARTAGENT leur `CalculateMovementUtilityInSteps` (un unique corps gshared)
    # et ne different QUE par `GetAdjacencyUtility`. Les cles sont resolues au litteral
    # (`probe_212_bc_key_literals.py` -- pour deux d'entre elles au travers du `.cctor`, elles
    # vivent dans un champ statique et non inline) et confrontees au gameconfig VIVANT : QUATRE
    # d'entre elles (IconOfObstinacy, MyWillBeDoneOverlord, et les deux de PropheticSentinel) sont
    # ABSENTES de la capture `data/seed-bc.json` et PRESENTES au gameconfig -- c'est exactement le
    # piege #271, dans le sens ou la capture SOUS-ESTIME. Un montage qui n'appelle pas
    # `catalog_inject.refresh_ai_utilities` fait donc rendre 0 au NATIF comme au port sur ces
    # quatre-la, et l'accord y serait vide de sens.
    # ⚠ `PrimarchOfTheFirstLegion` est indexee sur l'id de son REGISTRE (1511), pas sur le
    # litteral `1462` que son `.ctor` recopie par erreur de `NetherRealmCasket` : cf. la docstring
    # de la classe et `probe_433_r4_r3_r1_non_owner_registry.py`.
    int(TriggeredAbilityType.RelicOfLostCadia): RelicOfLostCadiaNonOwnerPlaybook(),               # 1459
    int(TriggeredAbilityType.NetherRealmCasket): NetherRealmCasketNonOwnerPlaybook(),             # 1462
    int(TriggeredAbilityType.AmuletOfTheVoidwyrm): AmuletOfTheVoidwyrmNonOwnerPlaybook(),         # 1464
    int(TriggeredAbilityType.PrimarchOfTheFirstLegion): PrimarchOfTheFirstLegionNonOwnerPlaybook(),  # 1511
    # ⚠ `RedemptionOfTheRisen` (1522) est PORTEE mais VOLONTAIREMENT ABSENTE d'ici : zero porteur
    # sur ce build, donc l'enregistrer serait du code que le dispatcher n'itere jamais (patron
    # #419). Justification et sources dans la docstring de la classe.
    int(TriggeredAbilityType.WatchedOver): WatchedOverNonOwnerPlaybook(),                         # 1524
    int(TriggeredAbilityType.TimesplinterMantle): TimesplinterMantleNonOwnerPlaybook(),           # 1534
    int(TriggeredAbilityType.PropheticSentinel): PropheticSentinelNonOwnerPlaybook(),             # 1543
    int(TriggeredAbilityType.IconOfObstinacy): IconOfObstinacyNonOwnerPlaybook(),                 # 1552
    int(TriggeredAbilityType.MyWillBeDoneOverlord): MyWillBeDoneOverlordNonOwnerPlaybook(),       # 1556
    # #477-r35 -- trois derivees DIRECTES de plus, choisies par leur ATTEIGNABILITE, chacune par
    # une voie de montage DIFFERENTE (aucun port speculatif) : `1526` greffe son passif npc-only sur
    # une unite du pool et amene un mover Votann par injection catalogue ; `1469` pose sa relique sur
    # un porteur du pool et ACCORDE le trait `Summon` au mover ; `1531` amene sa mine
    # (`astarSmnHaywireMine`, summon `Steppable`) par `--explicit-stats` et greffe le passif.
    int(TriggeredAbilityType.MawClawsOfThyrax): MawClawsOfThyraxNonOwnerPlaybook(),               # 1469
    int(TriggeredAbilityType.PurgeResponse): PurgeResponseNonOwnerPlaybook(),                     # 1526
    int(TriggeredAbilityType.HaywireMine): HaywireMineNonOwnerPlaybook(),                         # 1531
    # #477-r37 -- la face que #477-r35 avait classee « terme INERTE ». Elle ne l'est pas : le gate
    # `HasTrait(mover, Chaos)` porte sur le pseudo-trait de GRANDE-ALLIANCE, que le BC pose et que
    # `gameconfig.unit().traits` ne contient JAMAIS -- 127 unites sur 683 le portent. C'est le SEUL
    # confond arme SANS MONTAGE du recensement (`blackAbaddon`, hero du pool, passif de kit).
    int(TriggeredAbilityType.FirstAmongTraitors): FirstAmongTraitorsNonOwnerPlaybook(),           # 1064
}


def load_playbook_non_owner(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybookNonOwner` (movement-relevant uniquement). None -> la
    feuille skip la paire (meme chemin que le `if (playbook == null) continue` natif)."""
    return NON_OWNER_MOVE_PLAYBOOKS.get(int(ability_id))
