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

Le pre-gate `<slot 4> || IsFriend` est le complement de
`IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$IsInvalidEntityForPlaybook`
(= `!slot4 && !IsFriend`). `slot 4` est un predicat SANS argument de l'interface
`ITriggeredAbilityNonOwnerPlaybook`, dont le corps est TRIVIAL (fondu par l'ICF, donc sans symbole
propre).

**IL EST DESORMAIS LU (#433-r4-r3), et il vaut `false`** -- le residu que cette docstring nommait
est FERME, parce que deux playbooks SANS auto-gate entrent au registre ci-dessous. Chaine de
lecture, en trois sources qui se recoupent :

  1. **Le slot est bien 4 dans l'interface, et les slots 0/1/2 sont les trois `Calculate*`.**
     `FUN_180002590(slot, <Il2CppClass* de l'interface>, obj)` indexe
     `klass->interfaceOffsets` (+0xb0, compte +0x12e) puis la vtable (+0x138, entrees de 0x10).
     Le `DAT_` passe en 2e argument porte un token de metadata-usage de `kind == 1`
     (`kIl2CppMetadataUsageTypeInfo`), donc c'est bien le TYPE de l'interface, pas un MethodInfo.
     Les trois consommateurs nommes fixent le mapping : `<EvaluateMovementInSteps>d__0$$MoveNext`
     invoque le slot **0** avec `(case, owner)`, `<EvaluateAttackInSteps>d__1$$MoveNext` le slot
     **1**, `<EvaluateRepairInSteps>d__2$$MoveNext` le slot **2** -- et `IsInvalidEntityForPlaybook`
     / `<IterateAbilities>d__3$$MoveNext` le slot **4**.
  2. **Aucune classe concrete ne le surcharge.** Le bloc `methodPointers` du PE
     (`probe_8889_methodptr_vtable.py`) donne, pour `KustomForceFieldReworkedNonOwnerPlaybook`,
     `ECogSupportPlaybookNonOwnerPlaybook` et `PsychicFortressNonOwnerPlaybook`, EXACTEMENT deux
     entrees chacune -- `.ctor` puis `CalculateMovementUtilityInSteps` -- immediatement suivies des
     six corps de leur state machine `d__2`. Les trois heritent donc directement de
     `TriggeredAbilityNonOwnerPlaybook<T>` (`data/symbols/<build>/frida/classes.tsv` le confirme
     comme parent). C'est la lecture qui remplace « absent des tables donc pas d'override », que le
     `CLAUDE.md` interdit a bon droit.
  3. **Dans le bloc de la BASE, un seul corps rend un booleen, et il rend `false`.** Le bloc de
     `TriggeredAbilityNonOwnerPlaybook<T>` compte 21 entrees ; 19 portent un symbole propre
     (`.ctor`, les trois `Calculate*`, `GetUtilityValue`, `Init`, `get_LogSpamFilter`, `get_Logger`,
     `get_Query`, `get_State`, `get_UtilitiesDatabase`, les huit `set_*`) et TOUTES rendent un objet,
     `Fix64` ou `void`. Les deux restantes sont des corps fondus : l'un lit un champ objet (8 octets),
     l'autre est `return 0` sur **UN** octet -- la seule signature possible pour ce predicat.

Consequence portee : le pre-gate se reduit exactement a `IsFriend(case.unit ?? case.parent, owner)`,
et il est mirrore LA OU LE NATIF LE MET -- dans le dispatcher (`utilities/tile.py::
TriggeredAbilitiesNonOwnerUtility.evaluate`, mirror d'`IterateAbilities`), pas dans les corps de
playbook. `KustomForceFieldReworkedNonOwnerPlaybook` garde son propre test `IsFriend` : son corps
natif le porte VRAIMENT (redondant avec le pre-gate, mais present au decompile), et le port mirrore
le corps, pas l'economie qu'on pourrait en faire.

ASCII only dans les sorties ; les accents restent dans les docstrings non imprimees.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_faction import UnitFaction


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
        if not is_friend:                                    # UnitExtensions.IsFriend(case.unit, owner)
            return 0.0
        opos = (owner or {}).get("pos")
        if not opos:                                         # GetMainTile(owner) == null
            return 0.0
        tile, opos = (tile[0], tile[1]), (opos[0], opos[1])
        elev = (ctx or {}).get("elev_by_pos")
        if not bq.are_entities_adjacent(tile, opos, elev):             # TileExtensions.IsAdjacentTo
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
                                        ctx.get("elev_by_pos")):     # TileExtensions.IsAdjacentTo
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
    avant d'enregistrer la classe."""

    ABILITY_ID = int(TriggeredAbilityType.PsychicFortress)              # 1000
    KEY = "PSYCHICFORTRESS_AdjacentFriendly"                            # gameconfig vivant = 20

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        opos = (owner or {}).get("pos")
        if not opos:                                          # GetMainTile(owner, State) == null
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        (ctx or {}).get("elev_by_pos")):
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


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
        if ctx.get("is_spawning"):
            return 0.0
        opos = (owner or {}).get("pos")
        # `AreEntitiesAdjacent(tiles, unit)` commence par `if (unit == null) return false;` et
        # `AreTilesAdjacent` rend faux sur une liste de tuiles vide : porteur sans position -> 0.
        if not opos:
            return 0.0
        if not bq.are_entities_adjacent((tile[0], tile[1]), (opos[0], opos[1]),
                                        ctx.get("elev_by_pos")):
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
# Au registre ci-dessous : **12** faces MOVE (3 de #433-r4-r3 + 9 de ce cas -- la 10e,
# `RedemptionOfTheRisen`, est PORTEE mais delibrement HORS registre, zero porteur). Il reste **11**
# faces MOVE non portees, toutes des derivees DIRECTES, listees dans
# `docs/rl/case-433-r4-r3-non-owner-playbooks.md`.
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
}


def load_playbook_non_owner(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybookNonOwner` (movement-relevant uniquement). None -> la
    feuille skip la paire (meme chemin que le `if (playbook == null) continue` natif)."""
    return NON_OWNER_MOVE_PLAYBOOKS.get(int(ability_id))
