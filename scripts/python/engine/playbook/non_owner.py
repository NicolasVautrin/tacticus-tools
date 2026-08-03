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


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner` : singleton par TYPE d'ability, cache
# dict@0xa0 + factories dict@0x98. Le binaire declare 25 concrets `*NonOwnerPlaybook` ; seuls ceux
# qu'un case a montres decisifs sont portes ici. Absence du registre == `LoadPlaybookNonOwner`
# rend null == la paire n'est jamais yieldee : MEME degradation que le natif, pas un trou.
# ⚠ Cet argument ne vaut QUE pour un type d'ability SANS classe native `*NonOwnerPlaybook`. Pour
# une classe qui EXISTE, l'absence du registre est un ecart -- c'etait le residu #433-r4-r3, ferme
# ici pour `EcogSupport` et `PsychicFortress`. Les 22 autres concrets restent non portes, et leur
# statut est un RESIDU (nomme dans `docs/rl/case-433-r4-r3-non-owner-playbooks.md`), pas une
# equivalence.
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
}


def load_playbook_non_owner(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybookNonOwner` (movement-relevant uniquement). None -> la
    feuille skip la paire (meme chemin que le `if (playbook == null) continue` natif)."""
    return NON_OWNER_MOVE_PLAYBOOKS.get(int(ability_id))
