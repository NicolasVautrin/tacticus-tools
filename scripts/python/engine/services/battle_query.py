"""BattleQuery — sélection d'arme de l'attaque normale (`IdunBattle.Core.Services.BattleQuery`).

`GetAttackWeaponForDefaultNormalAttack` choisit l'arme DISTANCE-AWARE, et il en existe **TROIS
surcharges que le slot sépare** (détail et appariement : `get_attack_weapon_for_default_normal_
attack_from_tiles`) :
  - `0xae` `(attacker, attackerTiles)` : chaîne de repli **croisé** mêlée<->distance. Aucun
    consommateur porté.
  - `0xaf` `(attacker, attackerTiles, **target**)` : `rangeType = IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType`
    (0=None, 1=Melee, 2=Ranged, 3=Normal) ; si 1 -> mêlée ; si 3 ET !HasFlag(att, 0x15) ET
    `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` -> mêlée ; sinon
    `IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon` avec la porte `dist <= Range`.
    **AUCUN repli croisé** : un ensemble vide rend `null`. C'est le FOYER de l'attaque normale, sur
    les DEUX faces (`ALoki_NormalAttackAbility$$PredictAttack` et `$$ExecuteBehaviour`, via
    `$$FindAttackWeapon`) -> `get_attack_weapon_for_default_normal_attack`.
  - `0xb0` `(attacker, attackerTiles, **targetTiles**)` : `AreTilesAdjacent` -> mêlée sinon distance,
    sans porte de portée -> `get_attack_weapon_for_default_normal_attack_from_tiles`.
Le `DamageProfile` de l'arme choisie est lu à `weapon+0x10` (perçage : `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`).

⚠ NE PAS confondre avec `IdunBattle.ViewLogic.BattleSource.ObjectivesBattleQuery$$GetAmountOfHitsRangedFirstOrMelee` : ranged-first
INCONDITIONNEL, chemin OBJECTIFS de bataille, HORS prédiction de dégât. C'était le bug de l'ancien
`NormalAttackAbility` (sélection ranged-first au lieu de distance-aware).

Port : critère distance-aware (adjacent -> mêlée sinon ranged **en portée**, cf. #419-r1-tr14-r1-r1),
confronté live sur `adeptCanoness` aux trois issues (mêlée / distance au boundary `dist == Range` /
aucune arme). `rangeType` et le flag `0x15` entrent par l'`is_adjacent` que l'appelant calcule : les
branches `Melee(1)` (mêlée INCONDITIONNELLE) et `ForceRangedAttack` restent NON EXERCÉES ici — leur
mirror est `is_melee_attack`, pour un autre consommateur.
"""
from __future__ import annotations

import gameconfig as GC
import hexgeo

from ..entities.pathfinding.board import connectivity_neighbours
from .static_battle_rules import get_piercing_ratio
from .. import battle_query as _bq
from ..entities.damage_trait import DamageTrait
from ..entities.traits.unit_trait import UnitTrait
from .victory_config import get_max_rounds   # `BattleQuery$$GetMaxRounds` (#287-r11-r1-r1)


def are_tiles_adjacent(a_pos, t_pos, board=None):
    """`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` / `AreUnitsInMelee` — ADJACENCE HEX (PAS Chebyshev),
    service PARTAGÉ prédiction↔runner. Le natif folde DEUX conditions dans la primitive :
    `return (|Δelev| < 2) & (A==B || ConnectivityComponent.IsNeighbour(A, B))` — l'adjacence hex ET une
    PORTE d'élévation (deux tuiles voisines séparées de ≥2 crans d'élévation ne sont PAS adjacentes ;
    élévation = `tileMeta.elevation`, lue via `FUN_180007ae0(...)→[+0x18]`). Le port réplique les deux.

    `board` fourni (runner `state.board`, ou `Scene.board`) → le `ConnectivityComponent` BRUT
    (`connectivity_neighbours`, ce que lit littéralement `IsNeighbour`) + élévation par tuile
    (`by_id[tid]["elevation"]`, capteur boardGraph) ; sinon
    géométrie **evenq** (= le mode d'adjacence combat du runner, cf. `damage.py`), via `hexgeo.distance==1`
    (parité evenq validée vs boardGraph) SANS porte d'élévation (aucune info dispo → dégradation sûre =
    adjacence hex pure, comme le playbook `is_adjacent` sans `elev_by_pos`). Sur un board PLAT
    (Δelev=0<2 partout) la porte ne mord jamais → aucune régression ; elle ne discrimine que les boards
    à élévation. Renvoie `True`/`False`, ou `None` si une position est inconnue (→ ranged).

    ⚠ Le COURT-CIRCUIT D'IDENTITÉ (`A == B` → vrai sans consulter la connectivité) vaut dans les DEUX
    branches, et c'est la branche SANS board qui l'avait perdu : `hexgeo.distance(p, p)` vaut `0`,
    donc `== 1` rendait FAUX là où le natif rend VRAI. Le gate d'élévation ne le contredit jamais
    (`|Δelev| = 0 < 2` sur une tuile et elle-même), donc le natif rend VRAI **inconditionnellement**
    sur une paire identique — cf. `docs/rl/case-433-r1-identite-adjacence.md`."""
    if a_pos is None or t_pos is None:
        return None
    if (a_pos[0], a_pos[1]) == (t_pos[0], t_pos[1]):
        return True     # `tile1 == tile2` -> `b = 1`, et `|Delta elev| = 0 < 2` : VRAI des deux cotes
    if board is not None:
        a_tile = board.id_at(a_pos[0], a_pos[1])
        t_tile = board.id_at(t_pos[0], t_pos[1])
        if a_tile is not None and t_tile is not None:
            # `IsNeighbour` lit le `ConnectivityComponent` (`return this[+0x10].Contains(id)`),
            # canal BRUT -- et surtout PAS `board.neighbours()`, qui depend du `adjacency=` de
            # l'instance donc du MONTAGE de l'appelant (#448-r1-r1-r1-r1-r2-r1 ; c'est le meme
            # vice que `#381-r3` a ferme pour les pathfinders). Repli sur `board.neighbours()`
            # quand le canal n'est pas capte : le comportement anterieur, jamais un graphe vide.
            # MESURE (3 boards, 11718 paires) : en `native_sym` -- le mode de la PRODUCTION
            # (`playbook/scene.py`, le runner) -- le rebranchement change **0** verdict ; en
            # `evenq` il en corrige **4**, les aretes des deux `Bridge` de `C1_74` que
            # `TileComponent$$HasEdge` refuse et que la couronne hex inventait.
            conn = connectivity_neighbours(board, a_tile)
            ring = board.neighbours(a_tile) if conn is None else conn
            neighbour = (a_tile == t_tile) or (t_tile in ring)   # A==B || IsNeighbour
            if not neighbour:
                return False
            # IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent : porte d'élévation |Δelev| < 2, foldée dans la primitive.
            ae = board.by_id.get(a_tile, {}).get("elevation")
            te = board.by_id.get(t_tile, {}).get("elevation")
            if ae is not None and te is not None:
                return abs(int(ae) - int(te)) < 2
            return True    # élévation non captée (board ancien) → dégradation sûre (adjacence hex pure)
    return hexgeo.distance(a_pos, t_pos) == 1


def as_unit_position(value) -> list:
    """`IdunBattle.Core.UnitPosition` -- l'EMPREINTE, normalisee en liste de `(col, row)`.

    LECTURE (build `t6dpr4k06g`), et c'est elle qui rend le reste de ce module possible :
    `UnitPosition` est un `System.ValueType` a **UN SEUL CHAMP**, une `List<IEntity>` de TUILES.
    Les quatre membres le disent tous :
      * `IdunBattle.Core.UnitPosition$$.ctor(tile:IdunBattle.Core.IEntity)` construit une `List`
        VIDE, n'y ajoute `tile` que si elle est non nulle, et ecrit la liste au champ `+0x0` ;
      * `IdunBattle.Core.UnitPosition$$get_MainTile` rend `list[0]` (et `null` sur liste vide) --
        la main tile est donc la PREMIERE tuile de l'empreinte, jamais son identite ;
      * `IdunBattle.Core.UnitPosition$$IsEmpty` est exactement `MainTile == null` ;
      * `IdunBattle.Core.UnitPosition$$NullPosition` rend une `List` VIDE.
    C'est pourquoi `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` peut passer son 3e
    parametre TEL QUEL a la surcharge `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(tiles:IList<IEntity>,
    unit:IEntity)` : au niveau ABI, la struct EST le pointeur de liste (8 octets).

    ⚠ ET `IdunBattle.Entities.EntityExtensions$$GetUnitPosition(unit, state)` EST UN ALIAS DE
    `IdunBattle.Entities.EntityExtensions$$GetTiles(unit, state)` -- son corps entier est
    `return GetTiles(unit, state);`. La position d'une unite qui n'a pas d'ancre d'ability est donc
    son EMPREINTE COMPLETE, pas sa main tile. C'etait l'ecart `#10024`.

    ADAPTATEUR, pas deduction : le port accepte les DEUX ecritures parce que ses appelants ont les
    deux, et chacune a son artefact natif.
      * une TUILE `(col, row)` -> `[(col, row)]`, ce qu'ecrit litteralement `UnitPosition$$.ctor(tile)`
        -- le cas de la position CANDIDATE, qu'`IdunBattle.Entities.Abilities.AbilityEntities$$get_CasterPosition`
        emballe ainsi (`return +0x48 != 0 ? +0x48 : new UnitPosition(+0x40)`) ;
      * une SEQUENCE de tuiles -> l'empreinte telle quelle (`EntityExtensions$$GetTiles`) ;
      * `None` / vide -> `[]`, soit `UnitPosition$$NullPosition`.
    Le discriminant est le PREMIER element : un scalaire numerique -> c'est une tuile ; autre chose
    -> c'est une empreinte. Aucune autre forme n'est acceptee.

    ⚠ **DEUX FORMES DE TUILE, ET C'EST LU AU PRODUCTEUR, PAS SUPPOSE** -- exactement le meme piege
    que celui qui a fait LEVER `dsl/base.py::_feet` (`KeyError: 0`) quand le capteur `#419-r1-tr10-r2`
    a ouvert le canal DECISION :
      * face COMBAT (`runner.components.get_unit_feet`) -> des COUPLES `(col, row)` ;
      * face DECISION (`decisionView.units[].feet`, `projection.ts::readEntityFeet`) -> des DICTS
        `{"col", "row"}`, la forme de `readTileCoord`.
    Les deux sont normalisees ici. Une forme INCONNUE est **SAUTEE**, jamais devinee : sans ce
    refus, `list("ab")` fabriquerait la tuile `('a', 'b')` -- un couple parfaitement plausible qui
    ne designe rien, donc un faux silencieux, la faute meme que ce module interdit ailleurs."""
    if value is None:
        return []
    if isinstance(value, dict):                      # une TUILE dict, pas une empreinte
        t = _tuile(value)
        return [] if t is None else [t]
    if isinstance(value, (str, bytes)):
        return []                                    # jamais une tuile ni une empreinte
    try:
        items = list(value)
    except TypeError:
        return []                       # ni tuile ni empreinte -> `NullPosition`
    if not items:
        return []                       # `UnitPosition$$NullPosition` : liste VIDE
    head = items[0]
    if isinstance(head, (int, float)) and not isinstance(head, bool):
        t = _tuile(items)                            # `.ctor(tile)` : UNE tuile `(col, row)`
        return [] if t is None else [t]
    out = []
    for brut in items:
        if brut is None:
            continue                    # `.ctor` n'ajoute pas une tuile nulle
        t = _tuile(brut)
        if t is not None:
            out.append(t)
    return out


def _tuile(brut):
    """UNE tuile, sous l'une des deux formes que le port produit -> `(col, row)`, ou `None`.

    `None` est un REFUS, jamais un `(0, 0)` de repli : une tuile inventee ferait accorder ou
    refuser une adjacence sur une position qui n'existe pas."""
    if isinstance(brut, dict):
        c, r = brut.get("col"), brut.get("row")
        return None if c is None or r is None else (int(c), int(r))
    if isinstance(brut, (str, bytes)):
        return None
    try:
        seq = list(brut)
    except TypeError:
        return None
    if len(seq) < 2:
        return None
    a, b = seq[0], seq[1]
    if isinstance(a, bool) or isinstance(b, bool):
        return None
    if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return None
    return (a, b)


def are_entities_adjacent(feet_a, feet_b, board=None, elev_by_pos=None, neigh_by_pos=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(entity1, entity2)` -- la surcharge
    ENTITE/ENTITE, celle que le DSL invoque (slot 0x60 d'`IBattleQuery`) :

        tiles1 = EntityExtensions.GetTiles(entity1, state);
        tiles2 = EntityExtensions.GetTiles(entity2, state);
        return MovementUtil.AreTilesAdjacent(tiles1, tiles2);

    Elle compare donc les EMPREINTES COMPLETES, pas les main tiles. Et la surcharge LISTE de
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(IList, IList)` est un OU sur les paires
    (mirror du decompile) :

        foreach (t1 in tiles1) foreach (t2 in tiles2)
            if (AreTilesAdjacent(t1, t2)) return true;      // la surcharge SCALAIRE
        return false;                                       // enumeration epuisee

    Une liste VIDE rend donc FAUX (aucune paire evaluee) ; une liste NULLE fait LEVER cote natif --
    ici `None` est traite comme vide, le port n'ayant pas de domaine null distinct.

    UN SEUL LIEU boucle sur les empreintes dans tout le port, et c'est celui-ci -- TROIS voies de
    substrat, par ordre de fidelite decroissante :
      * `board` fourni -> DELEGUE a `engine.runner.abilities.targeting.are_entities_adjacent`, le
        foyer pose par #R30 (tuiles resolues par `board.id_at`, gate d'elevation et court-circuit
        d'identite par `targeting.are_tiles_adjacent`). Rien n'est reimplemente ici : le verdict
        de ciblage et le verdict DSL sortent litteralement de la meme fonction.
      * `elev_by_pos` / `neigh_by_pos` (les CARTES du board, `Board.walk_maps_by_pos()`) -> meme
        double boucle, primitive `engine.battle_query.are_entities_adjacent`, qui porte le MEME
        `ConnectivityComponent$$IsNeighbour` et la MEME porte `|dElev| < 2`. C'est la voie des
        trois slots ci-dessous (#10024) : ils recoivent des cartes, pas un `Board`.
      * NI l'un NI l'autre (contexte de FORMULE, scene de test) -> DEGRADATION NOMMEE : la meme
        primitive avec ses deux cartes a `None`, c.-a-d. adjacence hex pure + court-circuit
        d'identite, SANS porte d'elevation (aucune elevation lisible). Sure sur un board plat,
        jamais un mirror. Value-preserving par rapport a l'ecriture d'avant #10024
        (`are_tiles_adjacent(a, b, None)`) : les deux rendent `a == b` puis `hexgeo.distance == 1`.

    `feet_a`/`feet_b` sont normalises par `as_unit_position` ci-dessus -- une TUILE y vaut une
    empreinte a un element (`UnitPosition$$.ctor(tile)`), une SEQUENCE de tuiles vaut l'empreinte
    (`EntityExtensions$$GetTiles`, cf. `dsl/base.py::_feet` cote DSL et
    `runner/components.get_unit_feet` cote ECS)."""
    fa = as_unit_position(feet_a)
    fb = as_unit_position(feet_b)
    if not fa or not fb:
        return False                       # `AreTilesAdjacent(IList, IList)` : boucle vide -> false
    if board is not None:
        from ..runner.abilities.targeting import are_entities_adjacent as _r30   # lazy : anti-cycle
        return bool(_r30(board, fa, fb))
    return any(_bq.are_entities_adjacent(a, b, elev_by_pos, neigh_by_pos) for a in fa for b in fb)


def is_melee_attack(ability_name, caster_position, target_position, elev_by_pos=None,
                    force_ranged_attack: bool = False, neigh_by_pos=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition,
    target)` -- le slot **2** d'`IBattleQuery`, mirror 1:1 du decompile :

        if (!ability.HasValue) return false;
        switch (GetAbilityAttackRangeType(ability)) {   // 0 None, 1 Melee, 2 Ranged, 3 Normal
          case 0: return false;
          case 1: return true;
          case 2: return false;
          case 3: return !UnitExtensions.HasFlag(caster, 0x15)      // UnitFlag.ForceRangedAttack
                         && AreEntitiesAdjacent(casterPosition, target);
          default: throw new NotImplementedException();
        }

    FOYER UNIQUE de ce predicat : il est consomme par DEUX chemins natifs distincts, et les deux
    passent ici -- la gate `TriggeredAbilityPlaybook<T>$$IsMeleeAttack(case)` (cote DECISION, ex.
    `playbook/light_im_up.py`) et le predicat des effets d'attaquant
    (`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger`, qui appelle le MEME
    slot 2 sur `AbilityEntities.Ability`). Un service natif appele par N chemins = UNE fonction.

    `ability_name` = le NOM gameconfig de l'ability EVALUEE (`case.AbilityType` cote playbook) ;
    `None` / nom inconnu -> `attackRangeType` absent -> branche `Normal(3)`, qui est CELLE QUE LE
    NATIF PREND pour les attaques normales concretes (leur id per-unite n'a pas d'entree nommee au
    gameconfig, cf. `light_im_up` residu `#419-r1-tr5-r3`).

    `caster_position` = le 3e argument du natif, une **`IdunBattle.Core.UnitPosition`, c'est-a-dire
    une EMPREINTE** (#10024) -- pas une main tile. Deux lectures le fixent, et le port les portait
    toutes deux a faux :
      * le corps ci-dessus appelle la surcharge `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(tiles:IList<IEntity>,
        unit:IEntity)` (xref LUE : `BattleQuery$$IsMeleeAttack` -> cette surcharge-la, et non les
        deux autres), qui fait `MovementUtil.AreTilesAdjacent(tiles, GetTiles(unit))` = un OU sur
        **toutes les paires** empreinte du caster x empreinte de la cible ;
      * `IdunBattle.Entities.EntityExtensions$$GetUnitPosition` -- ce que passe tout appelant sans
        ancre d'ability -- a pour corps entier `return GetTiles(unit, state);`.
    Le port acceptait deux TUPLES et comparait deux MAIN TILES : sur une unite multi-hex (MoW,
    Galatian pose au sol, escouades multi-pieds), il REFUSAIT une adjacence que le natif accorde,
    sans erreur ni trace. Le predicat delegue desormais a `are_entities_adjacent` ci-dessus, foyer
    UNIQUE de la double boucle. Une TUILE reste acceptee et vaut l'empreinte a un element
    (`UnitPosition$$.ctor(tile)`), ce qui est la forme EXACTE d'une position CANDIDATE
    (`AbilityEntities+0x40` emballe par `$$get_CasterPosition`).

    `force_ranged_attack` = `UnitFlag.ForceRangedAttack` (21) ; le capteur
    `combatSnapshot.unitFlags` ne le publie pas (residu `#419-r1-tr5-r1`), donc l'appelant le laisse
    a `False` -- degradation PERMISSIVE-EN-PLUS, nommee.

    ⚠ HOMONYME A NE PAS CONFONDRE : `engine.entities.effects.base.is_melee_attack(is_ranged)` est un
    AUTRE artefact -- le gate TRI-ETAT (`is_ranged is False`) que les effets d'attaquant consomment
    une fois la nature du coup DEJA resolue. Celui-ci la RESOUT."""
    # ⚠ ECART NOMME, ANTERIEUR A #10024 ET **NON TOUCHE PAR ELLE** : le natif teste `ability.HasValue`
    # PUIS branche, et ses cases `Melee(1)` / `Ranged(2)` / `None(0)` ne lisent AUCUNE position --
    # une ability `attackRangeType: Melee` interrogee sans position rend donc `true` cote natif et
    # `false` ici. Le garder tel quel est un choix : cette tranche porte l'axe MAIN TILE -> EMPREINTE,
    # et deplacer cette garde changerait un verdict sur un axe DIFFERENT. Residu `#10024-r1`.
    if caster_position is None or target_position is None:
        return False
    rt = attack_range_type(ability_name)    # `BattleQuery$$GetAbilityAttackRangeType` (etage separe)
    if rt == "Melee":                       # `AttackRangeType.Melee` (1)
        return True
    if rt == "Ranged":                      # `AttackRangeType.Ranged` (2)
        return False
    if rt == "None":                        # `AttackRangeType.None` (0)
        return False
    if force_ranged_attack:                 # `HasFlag(caster, 0x15)` -> pas de melee
        return False
    # `neigh_by_pos` = la liste STOCKEE (#433-r4-r1-r4-r2). Le substrat de `MovementUtil$$AreTilesAdjacent`
    # est le `ConnectivityComponent` BRUT (`IsNeighbour`) et non le champ `neighbours` gate ; lire
    # le second est NEANMOINS exact ici, parce que la porte est un terme SEPARE du meme predicat :
    # `(|dElev| < 2) & IsNeighbour` == `(|dElev| < 2) & (arete de C ^ gate)` == `C ^ gate`.
    # `AreEntitiesAdjacent(casterPosition, target)` -- surcharge (IList, IEntity), donc la DOUBLE
    # boucle du foyer ci-dessus, jamais une comparaison de main tiles (#10024).
    return bool(are_entities_adjacent(caster_position, target_position,
                                      elev_by_pos=elev_by_pos, neigh_by_pos=neigh_by_pos))


def attack_range_type(ability_name):
    """`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(Nullable<AbilityOrEffect>)`
    -- l'ETAGE SEPARE que les slots 2 (`IsMeleeAttack`) et 3 (`IsRangedAttack`) consultent tous les
    deux. Rend le NOM du membre d'`IdunBattle.Entities.Enum.AttackRangeType`
    (`0=None,1=Melee,2=Ranged,3=Normal`, LU dans `data/symbols/<build>/frida/enums.tsv`), ou `None`
    quand l'ability n'a pas d'entree nommee au gameconfig.

    Corps natif : l'`AbilityOrEffect` est un triplet `(ActiveAbilityType, TriggeredAbilityType,
    EffectType)` et le natif branche sur celui des trois qui est renseigne -- id ACTIF ->
    `AbilityConfiguration` (getter slot `0xf`) ; id TRIGGERED -> `SelectAbilityAttackRangeType
    FromMultiple` ; EFFET -> resolution de l'ability porteuse puis RECURSION. Le port ne resout que
    la voie ACTIVE (`gameconfig.abilities[<nom>].attackRangeType`) ; les deux autres retombent sur
    `None` -> branche `Normal(3)` chez les appelants. RESIDU NOMME, pas une equivalence.

    `None` de retour n'est PAS `AttackRangeType.None` : c'est « pas d'entree », que les deux
    appelants traitent comme la branche `Normal(3)` (cf. leur docstring). La CHAINE `"None"`, elle,
    EST le membre 0."""
    if not ability_name:
        return None
    return (GC.ability(ability_name) or {}).get("attackRangeType")


def is_ranged_attack(ability_name, caster_position, target_position, elev_by_pos=None,
                     force_ranged_attack: bool = False, neigh_by_pos=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsRangedAttack(ability, caster, casterPosition,
    target)` -- le slot **3** d'`IBattleQuery`, mirror 1:1 du decompile (build `rnca9r7q6c`) :

        if (!ability.HasValue) return false;
        switch (GetAbilityAttackRangeType(ability)) {   // 0 None, 1 Melee, 2 Ranged, 3 Normal
          case 0: return false;
          case 1: return false;
          case 2: return true;                          // INCONDITIONNEL -- aucun test de position
          case 3: return UnitExtensions.HasFlag(caster, 0x15)      // UnitFlag.ForceRangedAttack
                         || !AreEntitiesAdjacent(casterPosition, target);
          default: throw new NotImplementedException();
        }

    ⚠ **CE N'EST PAS LA NEGATION d'`is_melee_attack`.** Les deux slots coincident sur `Normal(3)`
    (la ou l'un teste `!ForceRanged && adjacent`, l'autre teste `ForceRanged || !adjacent`) mais
    DIVERGENT sur `None(0)`, ou les DEUX rendent `false`. C'est pour ca qu'ils sont deux fonctions
    natives distinctes, et pourquoi ce mirror en est une aussi.

    ⚠ **`Ranged(2)` ne consulte AUCUNE position** -- une ability declaree `attackRangeType: Ranged`
    est une attaque a distance MEME contre une cible ADJACENTE. C'est la lecture qui manquait au
    port : `triggers/base._is_ranged_position` n'implemente que le repli positionnel de la branche
    `Normal(3)`, et l'appliquer a une ability `Ranged` DESARME le predicat sur toute cible au
    contact. Mesure (#512-r1, `1197 ExcruciatingFrequencies`, `attackRangeType = Ranged` au
    gameconfig ET `AttackRangeType = 2` dans `BC.Abilities.ActiveAbilities`) : la 1re cible du rayon
    est ADJACENTE au caster, et le natif la suppresse quand meme.
    Distribution `attackRangeType` au gameconfig (572 abilities) : `None` 406, `Ranged` 85,
    `Melee` 71, `Normal` 10 -- a RE-DERIVER, jamais citer cette ligne.

    `ability_name` = le NOM gameconfig de l'ability qui porte l'attaque. `None` / nom inconnu ->
    `attackRangeType` absent -> branche `Normal(3)`, MEME convention et MEME justification que
    `is_melee_attack` : les attaques normales CONCRETES (id per-unite) n'ont pas d'entree nommee au
    gameconfig, et c'est la branche que le natif y prend. Confirme par le LIVE : le discriminant
    melee/ranged de `test_suppressive_fire_live.py` (Pinned pose a d==2, absent a d==1, attaque
    NORMALE) n'est exactement la branche `Normal(3)`.

    `force_ranged_attack` = `UnitFlag.ForceRangedAttack` (21, nom LU dans
    `data/symbols/<build>/frida/enums.tsv`, `IdunBattle.Entities.Enum.UnitFlag`) ; le capteur
    `combatSnapshot.unitFlags` ne le publie pas (residu `#419-r1-tr5-r1`), donc l'appelant le laisse
    a `False` -- degradation RESTRICTIVE-EN-MOINS ici (le natif rendrait `true` sans regarder
    l'adjacence), nommee."""
    rt = attack_range_type(ability_name)
    if rt == "Ranged":                      # `AttackRangeType.Ranged` (2) -- aucune position lue
        return True
    if rt == "Melee":                       # `AttackRangeType.Melee` (1)
        return False
    if rt == "None":                        # `AttackRangeType.None` (0)
        return False
    if force_ranged_attack:                 # `HasFlag(caster, 0x15)` -> ranged sans lire la position
        return True
    # branche `Normal(3)` : `!AreEntitiesAdjacent(casterPosition, target)`. Positions manquantes ->
    # False (melee), le defaut conservateur deja retenu par `_is_ranged_position`.
    if caster_position is None or target_position is None:
        return False
    # MEME surcharge (IList, IEntity) que le slot 2, donc MEME foyer d'EMPREINTE (#10024) : ce
    # slot-ci lit `casterPosition:IdunBattle.Core.UnitPosition` exactement comme son frere.
    return not bool(are_entities_adjacent(caster_position, target_position,
                                          elev_by_pos=elev_by_pos, neigh_by_pos=neigh_by_pos))


def get_attack_range_type(ability_name, caster_position, target_position, elev_by_pos=None,
                          force_ranged_attack: bool = False, neigh_by_pos=None):
    """`IdunBattle.Core.Services.BattleQuery$$GetAttackRangeType(ability, caster, casterPosition,
    target)` -- le slot **4** d'`IBattleQuery` (arite 4, LU dans
    `data/symbols/<build>/metadata/interface_slots.tsv`), TROISIEME frere des slots 2
    (`is_melee_attack`) et 3 (`is_ranged_attack`). Mirror 1:1 du decompile :

        if (!ability.HasValue) return AttackRangeType.None;         // 0
        switch (GetAbilityAttackRangeType(ability)) {   // 0 None, 1 Melee, 2 Ranged, 3 Normal
          case 0: return 0;                            // None
          case 1: return 1;                            // Melee
          case 2: return 2;                            // Ranged
          case 3: if (!UnitExtensions.HasFlag(caster, 0x15)        // UnitFlag.ForceRangedAttack
                      && AreEntitiesAdjacent(casterPosition, target)) return 1;   // Melee
                  return 2;                                                        // Ranged
          default: throw new NotImplementedException();
        }

    ⚠ **CE N'EST NI `is_melee_attack` NI `is_ranged_attack`, ET LA DIFFERENCE EST LOAD-BEARING** :
    les deux booleens rendent FAUX sur `None(0)`, alors que celui-ci rend le membre `None` --
    c'est-a-dire une TROISIEME valeur, que ses deux consommateurs distinguent d'un `Melee` et d'un
    `Ranged`. Un port qui le simulerait par `is_melee_attack ? Melee : Ranged` classerait toute
    ability sans `attackRangeType` en `Ranged`, et incrementerait un compteur que le natif laisse
    a zero.

    DEUX CONSOMMATEURS NATIFS, tous deux LUS (c'est ce qui a leve les blocages `etage` annonces
    par `#508-r2` et `#951-r1`) :

      * `IdunBattle.Operations.FinishAttackOperation$$Execute` -- il appelle ce slot avec
        `(ability = <AttackOptions+0x10>, caster = attaquant, casterPosition =
        EntityExtensions$$GetUnitPosition(attaquant), target = cible)`, emballe le resultat dans un
        `Nullable<AttackRangeType>` **toujours renseigne**, et le passe en 3e argument de
        `IOperationProcessor` slot **74** (`RegisterAttack`, arite 4) -> `ActorStatisticsComponent$$
        RegisterAttackMade`, qui incremente `@+0x2c` sur `Melee(1)` et `@+0x28` sur `Ranged(2)`.
        C'est le call-site que `#508-r2` declarait NON LOCALISE.
      * `IdunBattle.Operations.RecordKillOperation$$Execute` -- meme appel (ability = le
        `killTrigger` du `KillUnitContext`), resultat enfile par `IdunBattle.Core.MatchState$$
        AddDeath(killer, killed, killTrigger, attackTrigger, **AttackRangeType**), recopie en
        `KillUnitOptions+0x3c` par la lambda de drain, et lu par
        `IdunBattle.Operations.KillUnitOperation$$Execute` sous la forme
        `inMelee = rangeType.HasValue && rangeType.Value == Melee(1)`. C'est l'ECRIVAIN que
        `#951-r1` declarait NON LOCALISE.
        ⚠ Sur la voie DEGAT le contexte porte DEJA la valeur (`IdunBattle.Operations.
        ApplyDamageOperation$$Execute` appelle ce meme slot 4 avant de la poser dans le
        `KillUnitContext@+0x38`) -> `RecordKillOperation` prend la branche `HasValue` et ne
        recalcule pas. Le port fait pareil : il calcule au foyer de degat
        (`damage.py::_fire_death_if_killed`) et transporte la valeur.

    Rend le NOM du membre d'`IdunBattle.Entities.Enum.AttackRangeType` (`"None"`, `"Melee"`,
    `"Ranged"`) -- MEME vocabulaire que `attack_range_type` et que les deux slots freres de ce
    module, qui parlent tous en noms de membres et jamais en ordinaux. `ability_name = None` /
    nom inconnu -> pas d'entree gameconfig -> branche `Normal(3)`, MEME convention et MEME
    justification que ses deux freres (les attaques normales CONCRETES n'ont pas d'entree nommee).

    `force_ranged_attack` = `UnitFlag.ForceRangedAttack` (21) ; aucun capteur ne le publie (residu
    `#419-r1-tr5-r1`), donc l'appelant le laisse a `False` -- degradation nommee, identique a celle
    des deux freres."""
    rt = attack_range_type(ability_name)    # `BattleQuery$$GetAbilityAttackRangeType` (etage separe)
    if rt in ("Melee", "Ranged", "None"):   # `case 1` / `case 2` / `case 0` -- rendus TELS QUELS
        return rt
    # branche `Normal(3)` : melee SSI (pas de `ForceRangedAttack`) ET adjacence, sinon ranged.
    if force_ranged_attack:                 # `HasFlag(caster, 0x15)` -> ranged sans lire la position
        return "Ranged"
    if caster_position is None or target_position is None:
        return "Ranged"                     # `AreEntitiesAdjacent` sur une position absente = FAUX
    # TROISIEME frere du meme switch, MEME surcharge (IList, IEntity) -> MEME foyer d'EMPREINTE
    # (#10024). Les trois slots partagent litteralement l'appel dans le decompile.
    return "Melee" if bool(are_entities_adjacent(
        caster_position, target_position,
        elev_by_pos=elev_by_pos, neigh_by_pos=neigh_by_pos)) else "Ranged"


def _find_by_hits(cands: list, prefer_hits) -> dict:
    """Parmi les armes candidates (même type), celle dont `hits == prefer_hits` (capté), sinon la 1re."""
    if prefer_hits is not None:
        return next((w for w in cands if int(w.get("hits") or 0) == prefer_hits), cands[0])
    return cands[0]


def get_attack_weapon_for_default_normal_attack(visual_id, is_adjacent: bool, prefer_hits=None,
                                                dist=None, force_ranged_attack: bool = False):
    """`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
    attackerTiles, **target**)` -- la surcharge du slot `0xaf`. Renvoie `(weapon_dict|None, is_ranged)`.

    C'EST BIEN CELLE-CI, ET C'EST UN FOYER PARTAGE DECISION<->COMBAT (#419-r1-tr14-r1-r1). La
    surcharge est etablie par lecture, pas par ressemblance :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$FindAttackWeapon(this,
    entities)` -- la surcharge a DEUX arguments -- invoque le slot `0xaf` avec `(caster, casterTiles,
    target)`, et ses appelants sont `ALoki_NormalAttackAbility$$PredictAttack` **et**
    `ALoki_NormalAttackAbility$$ExecuteBehaviour` (plus les huit attaques normales derivees :
    `ProperKilly`, `RighteousRepugnance`, `TalonOfHorus`, `Boltstorm`, `Fealty`, `FeederTendrils`,
    `OptimizedGait`). L'appariement slot<->arite vient des delegues du proxy
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass209_0$$u003CGetAttackWeaponForDefaultNormalAttacku003Eb__0`
    (slot `0xaf`, 3 parametres) et `...DisplayClass210_0$$...` (slot `0xb0`, `targetTiles`).

    Corps natif, LU :

        rangeType = GetAbilityAttackRangeType(GetNormalAttackType(attacker));   // 0 None 1 Melee 2 Ranged 3 Normal
        if (rangeType == Melee) return FindMeleeWeapon(attacker, attackerTiles, target);
        if (rangeType == Normal && !UnitExtensions.HasFlag(attacker, 0x15)      // ForceRangedAttack
                                && AreEntitiesAdjacent(attackerTiles, target))
            return FindMeleeWeapon(attacker, attackerTiles, target);
        return FindRangedWeapon(attacker, attackerTiles, target, distance);     // AUCUN repli croise

    ⚠ **AUCUN REPLI CROISE, DANS AUCUN SENS** -- et c'est le correctif de cette tranche. Le port
    retombait sur l'autre type d'arme quand la branche choisie ne rendait rien ; le natif rend `null`,
    et ses deux consommateurs le traitent comme « pas d'attaque » :
      * `PredictAttack` : `if (weapon == null)` -> branche SANS ARME (prediction `0..0` en `1` coup) ;
      * `ExecuteBehaviour` : `if (weapon == null) return;` -- ni `ExecuteInformWeapon`, ni
        `ExecuteNormalAttack`, ni `ExecuteTriggerAbilities`.
    Le repli croise n'existe QUE sur la surcharge du slot `0xae` `(attacker, attackerTiles)`, qu'aucun
    consommateur porte n'emprunte.

    `FindMeleeWeapon` / `FindRangedWeapon` rendent `null` sur un ENSEMBLE VIDE : les deux terminent par
    `SelectBestDamageWeapon` (target non nul) ou `SelectMaxRangeWeapon`, et les deux commencent par
    `if (weapons.Count == 0) return null`.

    PORTE DE PORTEE ranged (#188) : `FindRangedWeapon(unit, unitPosition, target, distance)` n'ajoute
    une arme QUE si `distance <= weapon.Range + rangeStatBonus` (`(int)distance <= local_88[0] + iVar6`,
    `iVar6` = `IdunBattle.Entities.Components.StatComponent$$get_CurrentValue` du stat de portee =
    **0 sur tous les units connus**, cf. sweep case-184 §gaps#2 : boundary exactement a Range).
    `dist` = distance HEX attaquant->cible (int) ; `None` = distance NON MESUREE -> porte non
    appliquee (degradation nommee, le natif la calcule toujours).

    TRI melee/ranged = `IdunShared.Battle.WeaponProfile$$get_IsMelee` (`Range is None || Range < 2`),
    via `weapon_is_melee` -- le predicat que `FindMeleeWeapon`/`FindRangedWeapon` lisent tous deux.
    Il remplace l'ancien `bool(w["Range"])`, qui rangeait une arme `Range == 1` en DISTANCE ;
    value-preserving MESURE sur le catalogue courant (`probe_419r1tr14r1r1_weapon_range_gate.py` :
    **0** arme `Range == 1` sur 683 unites), mais il fallait l'aligner ici, la disparition du repli
    rendant cette divergence observable.

    `force_ranged_attack` (#1019-r2) = `UnitExtensions.HasFlag(attacker, 0x15 =
    UnitFlag.ForceRangedAttack)`, le SECOND conjoint de la branche `rangeType == Normal` ci-dessus.
    Il vivait dans le corps natif depuis toujours et n'etait porte NULLE PART sur cette voie : le
    port choisissait la branche melee sur la seule adjacence. Le drapeau est POSE par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_AttackAbility$$
    CreateBehaviour` (`AddFlag(Caster, 0x15)` juste avant son `UseNormalAttackIfAble`, `RemoveFlag`
    juste apres) -- c'est litteralement le << even if they are adjacent to it >> de l'i2, et sans ce
    conjoint l'attaque supplementaire repartirait en MELEE, l'exact contraire.
    ⚠ **Defaut `False` = strict no-op** : aucun appelant existant ne le passe, et le seul poseur du
    drapeau cote port est le noeud ci-dessus. La face DECISION ne le passe pas non plus, et c'est
    un residu DEJA NOMME, pas un oubli de cette tranche -- `#419-r1-tr5-r1` : le drapeau n'est
    publie par AUCUN capteur (`combatSnapshot`), donc une unite qui le porterait live arriverait
    offline sans lui.
    ⚠ Il ne gate QUE la branche `rangeType == Normal`. La branche `rangeType == Melee` (melee
    INCONDITIONNELLE) l'ignore cote natif -- elle reste NON PORTEE ici, comme l'annonce l'en-tete du
    module : ce site ne modelise pas `rangeType`.

    RESIDU NOMME : le natif departage plusieurs armes eligibles par `SelectBestDamageWeapon` (la
    prediction de degat la plus forte, ou `SelectMaxRangeWeapon` quand `target` est nul) ; le port
    garde `_find_by_hits` (l'arme dont `hits` egale celui capte, sinon la premiere)."""
    gu = GC.unit(visual_id or "") or {}
    weapons = gu.get("weapons") or []
    if not weapons:
        return None, False
    melee = [w for w in weapons if weapon_is_melee(w)]          # `get_IsMelee`
    ranged = [w for w in weapons if not weapon_is_melee(w)]
    # `rangeType == Normal && !HasFlag(attacker, 0x15) && AreEntitiesAdjacent(...)` -- le drapeau
    # ETEINT la branche melee, il n'en ouvre aucune autre : on retombe sur `FindRangedWeapon`.
    if force_ranged_attack:
        is_adjacent = False
    if is_adjacent:                    # branche `FindMeleeWeapon(attacker, attackerTiles, target)`
        cand = melee
    elif dist is None:                 # distance NON MESUREE -> porte inapplicable (degradation)
        cand = ranged
    else:                              # `FindRangedWeapon(..., distance)` : porte `dist <= Range`
        cand = [w for w in ranged if dist <= int(w.get("Range") or 0)]
    if not cand:                       # ensemble vide -> `SelectMaxRangeWeapon`/`SelectBestDamageWeapon` = null
        return None, False
    w = _find_by_hits(cand, prefer_hits)
    return w, not weapon_is_melee(w)


def select_weapon_pierce(ctx, is_adjacent, dist=None, effect_bonus: int = 0,
                         force_ranged_attack: bool = False):
    """SÉLECTION D'ARME + PERÇAGE — service PARTAGÉ prédiction↔runner (foyer natif `BattleQuery`).
    `GetAttackWeaponForDefaultNormalAttack` (arme mêlée/ranged par adjacence HEX + porte de portée
    ranged `dist`, cf. #188) + `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` (profil.PiercingRatio +
    ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}). UN seul port : prédiction (`prediction._weapon_pierce`)
    ET combat (`damage_model.select_weapon_pierce`) l'appellent (un service natif appelé par N chemins =
    UNE fonction). `ctx` = UnitContext (les 2 en ont un). `dist` = distance HEX attaquant->cible (porte
    ranged ; `None` = legacy). Renvoie `(pierce, is_ranged, weapon_hits, profile_name)`.

    #71 : le BONUS LasCannon (+50) est appliqué ICI via `get_piercing_ratio` — mirror du natif
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` qui fait `base = GetPiercingRatio(profile, attackerTraits)`
    (bonus lascannon INCLUS) PUIS `+ ExtraPierce`. `GetAttackPiercingDamageRatio` n'a que des xrefs DATA
    (invoqué par delegate/slot) = service PARTAGÉ prédiction+combat -> le fix ici couvre LES DEUX faces.

    `effect_bonus` (case-117 phase 2) = Σ des `EffectBonus` de perçage des effets ACTIFS de l'attaquant
    (`IdunBattle.Entities.Effects.BaseEffect$$PiercingBonusForAttack`). C'est l'un des DEUX termes `Fix64`
    que le natif passe EN ARGUMENT à `GetAttackPiercingDamageRatio` (`param_6`/`param_7`, sommés DANS le
    `Max`/`Min` unique : `Min(100, Max(base>0, dirPierce + extraPierce + bonusB + bonusA + basePierce))`)
    -> il entre ici DANS la même somme, avant le clamp, jamais dans un second clamp. Défaut 0 =
    comportement historique. L'appelant COMBAT (attaque normale) le calcule après avoir résolu la nature
    du coup (`is_ranged`), que les gates d'effet consomment ; la PRÉDICTION ne le passe pas encore
    (résidu documenté : la face décision ignore ce canal, comme elle ignorait déjà GravitonRifle).

    `force_ranged_attack` (#1019-r2) : simple passe-plat vers
    `get_attack_weapon_for_default_normal_attack` -- cf. sa docstring pour la lecture native et le
    no-op par defaut."""
    w, is_ranged = get_attack_weapon_for_default_normal_attack(
        ctx.visual_id, is_adjacent, prefer_hits=ctx.normal_hits, dist=dist,
        force_ranged_attack=force_ranged_attack)
    if w is None:
        return 100, False, 1, None
    dp = GC.damage_profile(w.get("DamageProfile")) or {}
    prof_ratio = int(dp.get("PiercingRatio") or 0)
    # #71 : base pierce = GetPiercingRatio(profile, attackerTraits) = prof_ratio + 50 SI le profil porte
    # DamageTrait.LasCannon(3) ET l'attaquant UnitTrait.HeavyWeapon(1001)|Emplacement(1016). Les traits
    # gameconfig sont des NOMS de chaîne (DamageProfile.Traits / unit.traits) -> checks name-based.
    profile_has_lascannon = DamageTrait.LasCannon.name in (dp.get("Traits") or ())
    att_traits = getattr(ctx, "traits", None) or ()
    attacker_hw_emp = (UnitTrait.HeavyWeapon.name in att_traits
                       or UnitTrait.Emplacement.name in att_traits)
    base_pierce = get_piercing_ratio(prof_ratio, profile_has_lascannon, attacker_hw_emp)
    dir_pierce = ctx.extra_pierce_ranged if is_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, base_pierce + ctx.extra_pierce + dir_pierce + int(effect_bonus or 0)))
    return pierce, is_ranged, int(w.get("hits") or 1), w.get("DamageProfile")


def weapon_is_melee(weapon: dict | None) -> bool:
    """`IdunShared.Battle.WeaponProfile$$get_IsMelee` -- le predicat NATIF, et il n'est PAS
    « Range absent » :

        if (!this.Range.HasValue)  return true;      // champ `Nullable<int>` @ WeaponProfile+0x24
        return this.Range.Value < 2;                 // une portee de 1 est encore de la MELEE

    Le seuil `< 2` est LU (`local_res8[0] < 2` en sortie de `Nullable.get_Value`), pas deduit.
    Consequence : une arme a `Range == 1` est MELEE pour le natif, alors que le tri historique de
    `get_attack_weapon_for_default_normal_attack` (`bool(w.get("Range"))`) la range en DISTANCE.
    Les deux tris coexistent VOLONTAIREMENT ici : celui-la mirroir `FindMeleeWeapon`/`FindRangedWeapon`
    tels que la selection d'arme de l'attaque normale les appelle (residu nomme, non touche par cette
    tranche) ; celui-ci mirroir `get_IsMelee`, le seul que consultent `FindRangedWeapon` et
    `AttackWeaponRangeFormula$$Calculate`."""
    r = (weapon or {}).get("Range")
    if r is None:
        return True
    return int(r) < 2


def select_max_range_weapon(weapons: list) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$SelectMaxRangeWeapon(weapons)` -- mirror 1:1 :

        if (weapons.Count == 0) return null;
        if (weapons.Count == 1) return weapons[0];
        best = null; bestRange = 0;
        for (i = 0; i < weapons.Count; i++) {
            r = weapons[i].Range.GetValueOrDefault(0);   // `Nullable.GetValueOrDefault` @+0x24
            if (bestRange <= r) { best = weapons[i]; bestRange = r; }
        }
        return best;

    Deux details LUS qui ne se devinent pas : la comparaison est `<=` (a EGALITE de portee, c'est
    la DERNIERE arme de la liste qui gagne, pas la premiere), et `bestRange` part de `0` avec
    `GetValueOrDefault` -- une arme sans portee ne fait donc pas planter le balayage."""
    ws = list(weapons or [])
    if not ws:
        return None
    if len(ws) == 1:
        return ws[0]
    best, best_range = None, 0
    for w in ws:
        r = int((w or {}).get("Range") or 0)      # `Nullable<int>.GetValueOrDefault(0)`
        if best_range <= r:                        # `<=` : le DERNIER max gagne
            best, best_range = w, r
    return best


def get_unit_max_range(visual_id) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetUnitMaxRange(unitId)` (slot **171** d'`IBattleQuery`,
    LU dans `data/symbols/<build>/metadata/interface_slots.tsv`) -- MIRROR du decompile :

        config = GetUnitConfig(unitId);
        if (config == null || config.Weapons == null) return 0;
        max = 0;
        for (i = 0; i < config.Weapons.Count; i++) {
            w = config.Weapons[i];
            r = w.Range.HasValue ? w.Range.Value : 1;   // `Nullable<int>` @ WeaponProfile+0x24
            max = Math.Max(max, r);
        }
        return max;

    ⚠ TROIS lectures qui ne se devinent pas :
    * l'argument est un **unitId de CONFIG** (une chaine), pas une entite -- le natif passe par
      `BattleQuery$$GetUnitConfig`, donc le substrat est le CATALOGUE, pas l'ECS. Le port lit donc
      `GC.unit(visual_id)`, ce qui le rend disponible OFFLINE (l'ancienne note de
      `SendInTheNextWaveAbility` disait « le service de config d'unites n'est pas expose offline » --
      c'etait le cas tant qu'on visait le service ; le catalogue, lui, est la) ;
    * le defaut d'une arme SANS portee est **1**, pas 0 ni « ignoree » -- c'est le litteral
      `uVar6 = 1` de la branche `!HasValue`. Une unite purement corps-a-corps rend donc `1` ;
    * mais une unite INCONNUE (ou sans liste d'armes) rend **0**, pas 1 : les deux zeros du haut de
      corps sont des `return 0` distincts de la boucle. Le port garde la distinction.

    Utilise par `SendInTheNextWaveAbility$$GetSpawnedUnitRange`
    (`GetUnitMaxRange(GetStringConstant(0x0 unitId))`)."""
    cfg = GC.unit(visual_id or "")
    if cfg is None:
        return 0                                  # `GetUnitConfig(unitId) == null`
    weapons = cfg.get("weapons")
    if not weapons:
        return 0                                  # `config.Weapons == null`
    best = 0
    for w in weapons:
        r = (w or {}).get("Range")
        best = max(best, 1 if r is None else int(r))   # `HasValue ? Value : 1`
    return best


def get_player_turn_order(state=None) -> list:
    """`IdunBattle.Core.Services.BattleQuery$$GetPlayerTurnOrder` = le slot `IBattleQuery` **0x18**
    (arite **0**, lu dans `data/symbols/<build>/metadata/interface_slots.tsv`). Son corps est un pur
    accesseur de CONFIG :

        return this.<+0xa0 : BattleConfiguration>.<+0x30>.<+0x18>      # IList<PlayerId>

    soit, cote BC, **`BC.Player.TurnOrder`**.

    ⚠ STAND-IN NOMME, et sa portee est bornee -- le port ne recoit NI la liste `TurnOrder` NI la
    table `PlayerId -> BEntityId` : `decisionView` ne publie que `units[].owner`, un **BEntityId** de
    joueur. L'ordre est donc RECONSTRUIT par les ids d'entite CROISSANTS des joueurs porteurs
    d'unites. Les deux coincident sur le seed BC (`TurnOrder` trie par `PlayerId`, entites joueur
    creees dans cet ordre), et rien ne le garantit pour une BC dont le `TurnOrder` ne serait pas
    trie. Residu `#462-r4e-o-r2-r1-r1-r1-r1` : le publier demanderait un capteur sur
    `GetPlayerTurnOrder`.

    ⚠ AUCUN filtre `alive` : `TurnOrder` est une donnee de CONFIGURATION, un joueur n'en sort JAMAIS,
    meme toutes ses unites mortes. C'est le SKIP (`ShouldPlayerSkipTurn`, evalue DANS la boucle de
    `FindNextPlayer`) qui l'ecarte, pas l'ordre.

    FOYER UNIQUE, et il est ICI depuis `#287-r11-r1-r1-r1` : le corps vivait dans
    `engine.runner.operations.turnflow`, alors que `GetPlayerTurnOrder` est une methode de
    `BattleQuery` -- et `BattleQuery$$HasMinimumRemainingTurns`, ci-dessous, l'appelle. Deux
    stand-ins qui derivent seraient un bug silencieux ; `turnflow.player_turn_order` DELEGUE
    desormais a celui-la."""
    # DIFFERE, et il est PORTEUR -- classe par la mesure prescrite (charger X seul dans un process
    # FRAIS et regarder si M y atterrit) : `python -c "import engine.runner.components"` charge
    # `engine.services.battle_query` (chaine `components -> entities.effects.loki.* ->
    # services.damage_modifiers -> services.battle_query`, 107 modules). Le hisser fermerait donc un
    # cycle. Ni (1) DEPLACER ni (2) ALLEGER un `__init__` ne s'appliquent : `OwnerComponent` est un
    # composant du RUNNER, et la cascade ne passe par aucun baril.
    from ..runner.components import OwnerComponent
    players = set()
    for e in (getattr(state, "entities", None) or {}).values():
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.player is None:
            continue
        players.add(int(oc.player))
    return sorted(players)


def get_amount_of_turns_ended_by_player(state=None, player_id=None) -> int:
    """`IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEndedByPlayer(playerId)` --
    MIRROR du decompile, verbatim :

        if (this.<Dictionary @+0x40>.ContainsKey(playerId)) return this.<+0x40>[playerId];
        return 0;

    Une cle ABSENTE rend donc **0**, et c'est une LECTURE du natif -- pas une convention permissive :
    le dictionnaire nait VIDE (`TurnComponent$$.ctor` construit `+0x38` et `+0x40` vides) et ne
    recoit une cle qu'au premier changement de joueur.

    SUBSTRAT COTE PORT : `State.turns_ended`, le mirror de `+0x40`, ecrit par le SEUL ecrivain natif
    (`turnflow.set_current_player`) et seede par `snapshot._load_turns_ended`. NE PAS CONFONDRE avec
    `State.turn_counts`, qui mirroir `+0x38` (tours **DEMARRES**,
    `TurnComponent$$GetAmountOfTurnsStartedByPlayer`), ni avec `decisionView.turnsEnded`, qui publie
    `GetAmountOfTurnsEnded(matchTurn, 0)` = `Sum(dict.Values)`, la SOMME sur tous les joueurs."""
    d = getattr(state, "turns_ended", None) or {}
    if player_id is None:
        return 0
    key = int(player_id)
    if key not in d:                                  # `if (!ContainsKey(playerId)) return 0`
        return 0
    return int(d[key])


def has_minimum_remaining_turns(unit_id, turns: int, state=None, victory_conditions=None,
                                turns_ended_by_first_player=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns(unit, turns)` (slot **27**
    d'`IBattleQuery`, arite **2**, LU dans `data/symbols/<build>/metadata/interface_slots.tsv`) --
    MIRROR du decompile :

        limit = <GetMaxRounds() INLINE>              # victoryConfig.<+0x18>.TryGetValue(1)
        if (!limit.HasValue)                return true;
        matchTurn = StateExtensions.GetMatchTurn(state);
        first     = StateExtensions.GetPlayer(state, GetPlayerTurnOrder()[0]);
        ended     = matchTurn.GetAmountOfTurnsEndedByPlayer(first.Id);
        return turns <= limit.Value - ended;

    ⚠ **LE PARAMETRE `unit` N'EST PAS LU.** Ce n'est pas une omission du port : le corps natif ne
    le reference nulle part, et le joueur dont on compte les tours est `GetPlayerTurnOrder()[0]`,
    pas le proprietaire du caster. Le gate est donc GLOBAL AU MATCH, neutre au porteur -- le meme
    constat que `TheLionsWrathPlaybook$$ShouldEvaluate` (cf. `playbook/loki_custom.py`). Il est
    garde ici parce qu'il fixe cette lecture : un port qui filtrerait par joueur serait faux sur
    un match a plus de deux camps.

    ⚠ **LE SLOT ETAIT MAL LU (#287-r11-r1-r1).** Quatre sites du port ecrivaient « slot 0x1a
    d'`IBattleQuery` ... non resolu », c'est-a-dire un DECALAGE DE UN : `0x1a` = 26 =
    `ShouldPlayerSkipTurn` (arite 1), et c'est cette arite qui ne collait pas avec les deux
    arguments lus. Le vrai slot est `0x1b` = 27, et TROIS sources concordantes le disent :
    le call-site de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`
    (`<slot 0x1b>(this.<+0x18>, caster, 2)`, cinq arguments) ; la lambda du decorateur
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass68_0$$
    u003CHasMinimumRemainingTurnsu003Eb__0`, qui relaie le MEME couple (slot 0x1b, classe
    `IBattleQuery`) et dont le NOM donne la methode ; et la table de metadonnee, qui publie
    `27 HasMinimumRemainingTurns 2`. La table ne se trompait pas -- le port si.

    LES DEUX BRAS NE SONT PAS SYMETRIQUES, et c'est ce qui rend le port possible :

    * **bras 1 (`limit` VIDE) -> `True`, MESURE.** Le natif ne lit RIEN d'autre. Le plafond vient
      de `BC.Victory.VictoryConditions[MainPlayerRoundLimitation]`, que le port lit
      (`engine.services.victory_config.get_max_rounds`, defaut DERIVE de `data/seed-bc.json` ou la
      cle est ABSENTE). C'est donc une lecture, pas une convention permissive -- et c'est le
      regime de TOUS les runners `rl_duel build` a ce jour.
    * **bras 2 (`limit` PRESENT) -> LA FORMULE**, depuis `#287-r11-r1-r1-r1`. Le compteur
      `TurnComponent.<Dictionary @+0x40>` a desormais un substrat porte : `State.turns_ended`,
      lu par `get_amount_of_turns_ended_by_player` ci-dessus. Il ETAIT absent, et le port LEVAIT
      plutot que de degrader ; ce n'est plus le cas.

      ⚠ CE SUBSTRAT N'EST NI `State.turn_counts` NI `decisionView.turnsEnded` -- les deux candidats
      voisins, tous deux FAUX ici : `turn_counts` mirroir `+0x38` (tours **DEMARRES**), et
      `decisionView.turnsEnded` publie `GetAmountOfTurnsEnded(matchTurn, 0)` = `Sum(dict.Values)`,
      la SOMME sur tous les joueurs. Ce qui a debloque la tranche est le fait que
      `IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` est l'**UNIQUE ecrivain**
      des DEUX dictionnaires (verifie sur les 19 methodes de `TurnComponent` : seuls `.ctor` les
      construit vides et `Copy` les clone), qu'il est appele depuis un SEUL site
      (`IdunBattle.Operations.ChangeTurnOperation$$Execute`), et qu'il y fait exactement, dans cet
      ordre : `if (cur == next) return;` puis `started.TryAdd(next, 0)`, puis
      `if (cur != 0) { ended.TryAdd(cur, 0); ended[cur] += 1; }`, puis `<+0x24> = next` et
      `started[CurrentPlayerId] += 1`. Le port mirroir CE site (`turnflow.set_current_player`), donc
      le dictionnaire est TENU, pas devine.

    `turns_ended_by_first_player` reste accepte : c'est le canal d'un appelant qui a MESURE le
    compteur autrement (encadrement du probe, garde offline). `None` = non fourni -> le port lit son
    propre substrat, comme le natif lit le sien."""
    limit = get_max_rounds(state=state, victory_conditions=victory_conditions)
    if limit is None:
        return True                                   # `if (!limit.HasValue) return true;`
    if turns_ended_by_first_player is None:
        # `first = StateExtensions.GetPlayer(state, GetPlayerTurnOrder()[0])` puis
        # `matchTurn.GetAmountOfTurnsEndedByPlayer(first.Id)`.
        # ⚠ ORDRE VIDE : le natif indexerait `[0]` sur une liste vide (le `TurnOrder` d'une BC en
        # porte toujours au moins un). Le port n'a pas de joueur a nommer -> `player_id=None`, que
        # l'accesseur rend a `0` par sa branche `!ContainsKey` -- la MEME valeur que le natif rendrait
        # pour un joueur qui n'a encore termine aucun tour.
        order = get_player_turn_order(state)
        turns_ended_by_first_player = get_amount_of_turns_ended_by_player(
            state, order[0] if order else None)
    return int(turns) <= int(limit) - int(turns_ended_by_first_player)


def find_melee_weapon(visual_id) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$FindMeleeWeapon(unit)` -- la surcharge a UN SEUL
    argument (celle que l'interface `IBattleQuery` expose au slot `0xb2`, identifie par son proxy
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass212_0$$u003CFindMeleeWeaponu003Eb__0`).
    Son corps est UN SEUL appel : `FindMeleeWeapon(unit, unitPosition: null, target: null)`, la
    surcharge a QUATRE arguments, dont le corps est le SYMETRIQUE EXACT de `find_ranged_weapon` :

        if (!EntityExtensions.IsUnit(unit)) return null;
        set = new OrderedSet<WeaponProfile>();
        foreach (w in unit.WeaponsComponent.Weapons)
            if (w.IsMelee) set.Add(w);                   // le filtre est INVERSE de FindRangedWeapon
        if (target != null) return SelectBestDamageWeapon(unit, unitPosition, target, set);
        return SelectMaxRangeWeapon(set);

    `target` etant NUL sur cette surcharge, la branche `SelectBestDamageWeapon` est MORTE ici : c'est
    toujours `SelectMaxRangeWeapon` qui tranche -- donc, parmi les armes de MELEE, celle de plus
    longue portee (`Range.GetValueOrDefault(0)`, `<=` -> la DERNIERE a egalite). Une unite dont
    toutes les armes de melee sont sans `Range` rend donc la DERNIERE de la liste.

    CONSOMMATEUR PORTE : `...TheLionsWrathPlaybook$$CalculateCustomUtility` (#27-r4), qui lit le
    `Hits` (`WeaponProfile+0x20`) de l'arme rendue pour la CIBLE -- jamais pour le caster.

    SUBSTRAT : identique a `find_ranged_weapon` (kit gameconfig par `visualId`) ; unite inconnue ou
    sans arme de melee -> `None`, qui mirroir le `null` natif (set vide -> `SelectMaxRangeWeapon`
    rend `null`)."""
    weapons = (GC.unit(visual_id or "") or {}).get("weapons") or []
    return select_max_range_weapon([w for w in weapons if weapon_is_melee(w)])


def get_attack_weapon_for_default_normal_attack_from_tiles(visual_id, is_adjacent: bool) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
    attackerTiles, **targetTiles**)` -- la surcharge que l'interface `IBattleQuery` expose au slot
    `0xb0`, et la SEULE que la regle dynamique de l'attaque normale consulte. Corps natif :

        t1 = attackerTiles[0]; t2 = targetTiles[0];              // deux `First()`
        if (MovementUtil.AreTilesAdjacent(t1, t2))
             return FindMeleeWeapon(attacker, unitPosition: null, target: null);
        else return FindRangedWeapon(attacker);

    `AreTilesAdjacent` y est la surcharge **LISTE** (`MovementUtil$$AreTilesAdjacent(IList, IList)`,
    xref LUE depuis ce corps) : un produit cartesien vrai des qu'UNE paire de tuiles est adjacente --
    donc l'EMPREINTE complete, exactement le predicat de `BattleQuery$$AreEntitiesAdjacent`, et non
    la seule tuile principale. C'est pourquoi l'adjacence est calculee par l'appelant et arrive ici
    en booleen : ce module n'a pas de board.

    ⚠ TROIS SURCHARGES, ET ELLES NE FONT PAS LA MEME CHOSE -- ne pas les confondre, le slot les
    separe :
      * `0xae` `(attacker, attackerTiles)` -- chaine de repli melee<->ranged ; c'est celle que
        `IdunBattle.View.FSM.VisualBattleQuery$$GetAttackWeaponForDefaultNormalAttack` delegue
        (lecture qui FIXE l'appariement slot<->arite) ;
      * `0xaf` `(attacker, attackerTiles, **target**)` -- resout `GetNormalAttackType` puis
        `BattleQuery$$GetAbilityAttackRangeType`, teste `UnitExtensions$$HasFlag(attacker, 0x15)`
        et `AreEntitiesAdjacent`, et n'a **AUCUN repli croise** ; c'est
        `get_attack_weapon_for_default_normal_attack` ci-dessus.
        ⚠ Cette ligne a longtemps dit « NON PORTEE, aucun consommateur porte ne l'emprunte » -- c'etait
        FAUX, et c'est ce qui a laisse vivre `#419-r1-tr14-r1-r1` : `ALoki_NormalAttackAbility$$
        FindAttackWeapon(this, entities)` (la surcharge a DEUX arguments) invoque ce slot, et ses
        appelants sont `PredictAttack` **et** `ExecuteBehaviour`. C'est le foyer de TOUTE attaque
        normale, sur les DEUX faces ;
      * `0xb0` `(attacker, attackerTiles, **targetTiles**)` -- CELLE-CI.
    L'appariement `0xaf`/`0xb0` est LU sur les deux surcharges de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$FindAttackWeapon`,
    qui appellent respectivement le slot `0xaf` (parametre `target`) et le slot `0xb0` (parametre
    `targetTiles`) -- et c'est le slot `0xb0` que
    `ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason` invoque.

    SUBSTRAT : le kit gameconfig, via `find_melee_weapon` / `find_ranged_weapon` (meme borne, meme
    citation). `None` = le natif rendrait `null` -- ce que la regle dynamique traduit en REFUS."""
    return find_melee_weapon(visual_id) if is_adjacent else find_ranged_weapon(visual_id)


def weapon_hits(weapon: dict | None) -> int:
    """`WeaponProfile+0x20` = `Hits`, le nombre de coups du profil -- et `null -> 0`, la valeur que
    le natif garde quand `FindMeleeWeapon` ne rend rien (`iVar8` initialise a 0 et laisse tel quel
    dans `...TheLionsWrathPlaybook$$CalculateCustomUtility`).

    L'offset est etabli par DEUX lectures concordantes, jamais par le nom :
    `IdunBattle.Core.Services.BattleQuery$$u003CGetBestWeaponu003Eb__316_0` calcule
    `GetDamageProfile(w.<+0x10>).<+0x14> * w.<+0x20>` (degat par coup x nombre de coups), et
    `...$$SelectMaxRangeWeapon` / `IdunShared.Battle.WeaponProfile$$get_IsMelee` lisent tous deux
    `+0x24` comme le `Nullable<int> Range` -- donc `+0x20` n'est pas la portee.

    ⚠ Le defaut est `0`, PAS `1` : `get_attack_weapon_for_default_normal_attack` retombe sur `1`
    parce qu'une attaque porte au moins un coup, mais ici l'absence d'arme doit rendre un TERME NUL,
    et un `1` implicite vaudrait 30 points d'utilite offerts."""
    return int((weapon or {}).get("hits") or 0)


def has_ranged_weapon(visual_id, min_range=None) -> bool:
    """`IdunBattle.Entities.Components.WeaponsComponent$$HasRangedWeapon(minRange)` -- le predicat
    que `IdunBattle.Entities.UnitExtensions$$HasRangedWeapon(unit, minRange)` delegue apres avoir
    resolu le composant. Corps natif relu (build courant), boucle VERBATIM :

        foreach (w in this.Weapons) {
            if (w.IsMelee)               continue;          // WeaponProfile$$get_IsMelee
            if (!minRange.HasValue)      return true;       // minRange nul -> aucune comparaison
            if (minRange.Value <= w.Range.Value) return true;
        }
        return false;

    Le `minRange` nul COURT-CIRCUITE la comparaison de portee : tous nos call-sites portes passent
    `null`, donc le predicat s'y reduit a « au moins une arme n'est pas `IsMelee` », c.-a-d.
    `WeaponProfile$$get_IsRanged` (dont le corps EST `get_IsMelee ^ 1`).

    ⚠ CE N'EST PAS le tri de `IdunBattle.Entities.UnitExtensions$$IsRanged` porte par
    `engine.services.ability_range._has_ranged_weapon` (`HasTrait(0xb Ranged) || presence d'un
    Range`) : deux fonctions natives distinctes, deux seuils. Ici le seuil est celui de
    `weapon_is_melee` (`Range >= 2`).

    SUBSTRAT : le natif itere le `WeaponsComponent` de l'ECS ; le port lit le kit gameconfig
    (`GC.unit(visualId).weapons`), meme source que `find_ranged_weapon` / `find_melee_weapon`
    ci-dessus -- decalque MESURE du `UnitConfiguration.Weapons` de la BC (246 armes / 175 unites,
    0 divergence sur `IsMelee`). Ce que ce substrat ne voit pas : une arme AJOUTEE/MODIFIEE en
    cours de bataille par un effet. Unite inconnue -> `False` (aucune arme -> la boucle native
    n'entre jamais et rend `false`).

    FOYER UNIQUE du predicat : consomme par le selecteur DSL `UnitsWithoutRangedWeapons`
    (`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithoutRangedWeapons` ->
    `IdunBattle.Entities.Selectors.UnitsWithoutWeaponsSelector$$Select`, qui inline exactement
    cette boucle) et par `engine.playbook.adjacent_unit_preference` (les DEUX poids de
    `...HatefulAssaultPlaybook$$GetAdjacentEnemyUtility`)."""
    for w in ((GC.unit(visual_id or "") or {}).get("weapons") or []):
        if weapon_is_melee(w):
            continue
        if min_range is None:
            return True
        r = w.get("Range")
        if r is not None and int(min_range) <= int(r):
            return True
    return False


def find_ranged_weapon(visual_id) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon(unit)` -- la surcharge a UN SEUL
    argument (celle que l'interface `IBattleQuery` expose au slot `0xb3`, identifie par son proxy
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass213_0$$u003CFindRangedWeaponu003Eb__0`,
    dont tout le corps est cet appel-la). Corps natif :

        if (!EntityExtensions.IsUnit(unit)) return null;
        set = new OrderedSet<WeaponProfile>();
        foreach (w in unit.WeaponsComponent.Weapons)
            if (!w.IsMelee) set.Add(w);
        return SelectMaxRangeWeapon(set);

    ⚠ A NE PAS confondre avec la surcharge a CINQ arguments
    `FindRangedWeapon(unit, unitPosition, target, distance)`, qui filtre en plus par
    `distance <= Range + rangeStatBonus` et peut basculer sur `SelectBestDamageWeapon`. Celle-ci
    n'a AUCUNE porte de distance et AUCUNE cible : elle rend l'arme de plus longue portee, point.

    SUBSTRAT : le natif itere le `WeaponsComponent` de l'ECS ; la face DECISION n'a que le kit
    gameconfig (`GC.unit(visualId).weapons`), exactement la source de
    `get_attack_weapon_for_default_normal_attack`. Unite inconnue / sans arme distance -> `None`,
    qui mirroir le `null` natif (set vide -> `SelectMaxRangeWeapon` rend `null`)."""
    weapons = (GC.unit(visual_id or "") or {}).get("weapons") or []
    return select_max_range_weapon([w for w in weapons if not weapon_is_melee(w)])
