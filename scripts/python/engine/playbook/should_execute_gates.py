"""Les `ShouldExecute` a CORPS PROPRE encore non portes -- suite de `#419-r1-tr14-r5-r2-r1-r1-r1`
(15 classes, gate << l'attaque normale tue deja >>) et de son `-r2` (12 classes, seuil statique).

## L'inventaire, RE-DERIVE des 31 corps nommes du build

`mcp__ghidra__search_symbols_by_name(query = "Playbook.*\\$\\$ShouldExecute")` rend **31** symboles,
dont deux definitions GENERIQUES (`ALoki_NormalAttackPlaybook<T>`, `Idun.NormalAttackPlaybook<T>`).
Les **29** corps concrets se ventilent ainsi, apres les deux tranches precedentes :

| corps                                             | classes | statut a l'ouverture de CETTE tranche |
|---|---|---|
| `SpiritLeechPlaybook$$ShouldExecute`              | 14 | porte (`normal_attack_kill_gate`)    |
| `FragBombPlaybook$$ShouldExecute`                 |  2 | LU, non porte (cible = TUILE, `-r1-r1`) |
| `MultiThreatEliminatorPlaybook$$ShouldExecute`    |  1 | porte (`normal_attack_kill_gate`)    |
| famille << seuil statique de la classe >>         | 12 | porte (`static_threshold_gate`)      |
| `Loki_NormalBossAttackPlaybook$$ShouldExecute`    |  1 | porte (`common.NormalBossAttackPlaybook`) |
| `SorcerousFacadePlaybook$$ShouldExecute`          |  1 | porte (`loki_custom`)               |
| **les 10 restants**                               | 10 | **CETTE tranche + residus**          |

Les dix restants, corps LUS verbatim, `ability_id` LU dans le `.ctor` de la classe
(`ComparablePlaybook<T>..ctor(this, <id>, klass)`), jamais devine du nom :

| classe (`IdunBattle.AI.Playbook[.Loki|.Common]`) | id (`.ctor`) | corps | ici |
|---|---|---|---|
| `Loki.StranglethornCannonPlaybook`   | `0x420` = 1056 | `utility > Fix64(0)` LITTERAL | **oui** |
| `Loki.Repair_GalvanicFieldPlaybook`  | `0x45f` = 1119 | `utility > Fix64(0)` LITTERAL | atteste (route bespoke) |
| `Loki.TwistedScience_HealPlaybook`   | `0x48f` = 1167 | `utility > Fix64(0)` LITTERAL | atteste (route heal) |
| `Loki.HealingBalms_HealPlaybook`     | `0x4bc` = 1212 | `utility > Fix64(0)` LITTERAL | atteste (route heal) |
| `Common.RepairPlaybook`              | `0x1c` = 28    | `utility > Fix64(0)` LITTERAL | atteste (route repair) |
| `Common.HealPlaybook`                | `0x12` = 18    | `utility > 0` **+ clause BOSS** | **oui** (`common.HealPlaybook`) |
| `Loki.ReapingScythePlaybook`         | `0x447` = 1095 | `utility > 0` **+ TurnsStarted** | **oui** |
| `Loki.StormOfFlensingBladesPlaybook` | `0x3f2` = 1010 | `casterTile == MainTile(caster)` | **oui** |
| `Loki.HadesAutocannonsPlaybook`      | `0x47b` = 1147 | un ENNEMI porte `Summon`      | **oui** |
| `Loki.TacticalPrecisionPlaybook`     | `0x482` = 1154 | `WillBeCharging` OU `Count > 1` | **oui** (#976) |
| `Loki.ArmoriumCherubPlaybook`        | `0x3f6` = 1014 | `GetValidTargets < 2` -> `!CanKillTarget` | porte dans `loki_custom.py` |
| `BloodChalicePlaybook`               | `0x497` = 1175 | somme de deficits de PV       | **DEAD CODE**, cf. `bespoke.py` |

(La ligne `Common.HealPlaybook` est portee DANS `common.py`, la ou vit deja la premiere moitie de
son gate : la scinder aurait fait deux corps pour un seul `ShouldExecute`. Idem `1014` dans
`loki_custom.py`, ou vit deja son `CalculateCustomUtility` : le registre etant indexe par
`ability_id`, deux entrees se seraient ecrasees.)

⚠ **LES TROIS << RESIDUS >> DE L'EN-TETE PRECEDENT SONT CLOS, ET AUCUN DES TROIS PAR LA MEME
RAISON** (`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1`) :
  * `1154` etait **DEJA PORTE** quand la fiche l'annoncait ouvert (#976) -- prémisse PERIMEE ;
  * `1014` est **PORTE ICI** : sa << requete de zone >> est le slot `IBattleQuery` 0x42 =
    `GetValidTargets`, dont le port a deja un mirror (`noncomparable/_base.
    count_eligible_normal_attack_targets`, foyer partage avec `ExemplarOfTheKauyon`) ;
  * `1175` est **DEAD CODE** : `BloodChalicePlaybook` OVERRIDE `EvaluateInternal`, et
    `ShouldExecute` (slot +0x328) n'est appele que depuis
    `ComparablePlaybook<T>$$CalculateActionUtility`, elle-meme appelee depuis le SEUL
    `ComparablePlaybook<T>$$EvaluateInternal` -- que l'override remplace. Detail : `bespoke.py`.

## Les quatre corps portes ICI, verbatim

```csharp
// IdunBattle.AI.Playbook.Loki.StranglethornCannonPlaybook$$ShouldExecute
return attackHealUtility > Fix64.op_Implicit(0);

// IdunBattle.AI.Playbook.Loki.ReapingScythePlaybook$$ShouldExecute
if (!(attackHealUtility > Fix64.op_Implicit(0))) return false;
return UnitExtensions.GetStat(caster, StatType.TurnsStarted, Current, 0) > 2;

// IdunBattle.AI.Playbook.Loki.StormOfFlensingBladesPlaybook$$ShouldExecute
return casterTile == EntityExtensions.GetMainTile(caster, this.<+0x20 = state>);

// IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$ShouldExecute
foreach (u in battleQuery.<slot 0x8e>(EntityExtensions.GetCurrentOwnerEntityId(caster)))
    if (UnitExtensions.HasTrait(u, UnitTrait.Summon)) return true;
return false;
```

Trois lectures qui ne se devinent pas :

1. **`ReapingScythe` lit `StatType.TurnsStarted` (12), pas un compteur de charges.** Le littéral
   `0xc` est qualifié dans `data/symbols/<build>/frida/enums.tsv` (`12=TurnsStarted`), et c'est le
   MEME accesseur que `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` deja porte
   (`Scene.turns_started`, tri-etat). La comparaison est `> 2` STRICT, donc l'ability n'est proposee
   qu'a partir du QUATRIEME tour demarre par le caster.
2. **`StormOfFlensingBlades` compare la TUILE DE CAST a la MainTile COURANTE.** C'est un gate
   << je ne me deplace pas pour lancer >> : le sweep de tuiles du generateur d'action propose des
   positions de deplacement, et le natif les refuse toutes SAUF l'origine. Aucune autre clause -- ni
   utilite, ni cible.
3. **`HadesAutocannons` interroge les unites du PROPRIETAIRE du caster**, pas sa team au sens du
   port ; sur les duels que le harnais monte (un joueur = une team) les deux coincident, et c'est le
   meme substrat que tout `IsFriend` deja porte. Le trait est `UnitTrait.Summon` (**2**), qualifie
   par l'enum -- le littéral `2` du décompilé ne dit rien de lui-meme.

## Le rang, et ce que ce module NE change PAS

Le gate vit au slot de vtable `+0x328`, appele par
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
avec `attackHealUtility = CalculateCustomUtility + CalculateUtilityFromPredictions`, AVANT les trois
termes positionnels. `false` ==> `Nullable` VIDE = AUCUNE action dans le `Bucket`.

Les ids enregistres ici retombaient sur `DefaultActiveAbilityPlaybook` : ils en HERITENT, donc
`make_damage_predictions`, `calculate_custom_utility` et `make_effect_predictions` restent
EXACTEMENT ce qu'ils etaient. Le seul delta est `should_execute`.
"""
from __future__ import annotations

from .base import register
from .common import DefaultActiveAbilityPlaybook
from .prediction._shared import _entity_traits
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.traits.unit_trait import UnitTrait
# `TacticalPrecisionPlaybook.should_execute` : `WillBeCharging` (slot 0xcd) + le comptage
# d'adjacence. Forme B (le module, pas les noms) -- `engine.battle_query` est une FEUILLE, aucune
# arete de cycle a fermer, et un binding de module ne se fige pas sous `monkeypatch`.
from engine import battle_query as _bq


class LiteralZeroThresholdPlaybook(DefaultActiveAbilityPlaybook):
    """`ShouldExecute` = `attackHealUtility > Fix64.op_Implicit(0)`, seuil **LITTERAL**.

    A ne pas confondre avec `static_threshold_gate.StaticUtilityThresholdPlaybook`, dont le seuil est
    le PREMIER CHAMP STATIQUE de la classe (= `Fix64(10)`, ecrit par `ComparablePlaybook<T>$$.cctor`).
    Ici le `0` est materialise dans le corps meme, il n'a aucun ecrivain et ne peut pas glisser.

    Comparaison STRICTE (`Fix64$$op_GreaterThan`) : une utilite EGALE a 0 est REFUSEE."""

    def __init__(self, ability_id: int):
        self.ability_id = int(ability_id)

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        return utility > 0.0


class ReapingScythePlaybook(LiteralZeroThresholdPlaybook):
    """`IdunBattle.AI.Playbook.Loki.ReapingScythePlaybook$$ShouldExecute` (1095) :

        if (!(attackHealUtility > Fix64(0))) return false;
        return GetStat(caster, StatType.TurnsStarted, Current, 0) > 2;

    Le court-circuit est LU : la stat n'est interrogee que si le seuil passe. Sans effet observable
    (l'accesseur est pur), mais c'est l'ordre du natif.

    TRI-ETAT sur `turns_started` -- `Scene.turns_started` rend `None` quand l'uid est absent de ses
    tables, et c'est la convention du port (<< un canal muet se DIT muet >>). Un `0` invente ferait
    REFUSER l'ability, c.-a-d. prononcer un refus que le natif n'a pas prononce : degradation
    RESTRICTIVE silencieuse. On degrade donc la clause en VRAI, exactement comme le port d'avant."""

    ability_id = int(ActiveAbilityType.ReapingScythe)      # 0x447 = 1095

    #: `GetStat(caster, 12, ...) > 2` -- STRICT, lu au decompile.
    MIN_TURNS_STARTED: int = 2

    def __init__(self):
        super().__init__(int(ActiveAbilityType.ReapingScythe))

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        if not utility > 0.0:
            return False
        sc = getattr(ctx, "scene", None)
        ts = None if sc is None else sc.turns_started(getattr(ctx, "uid", None))
        if ts is None:
            return True                       # canal muet -> clause degradee en VRAI (cf. docstring)
        return int(ts) > self.MIN_TURNS_STARTED


class StormOfFlensingBladesPlaybook(DefaultActiveAbilityPlaybook):
    """`IdunBattle.AI.Playbook.Loki.StormOfFlensingBladesPlaybook$$ShouldExecute` (1010) :

        return casterTile == EntityExtensions.GetMainTile(caster, this.<+0x20 = state>);

    UNE clause, et elle ne lit NI l'utilite NI la cible : l'ability n'est proposee QUE depuis la
    tuile courante du caster. Le sweep de tuiles du generateur d'action balaie les positions de
    deplacement ; le natif les refuse toutes sauf l'origine.

    ⚠ Le natif compare des ENTITES DE TUILE (`==` de reference sur `ITile`), le port des positions
    `(col,row)` -- meme relation, une tuile par position. `this@+0x20` est le `state`, LU dans
    `IdunBattle.AI.Playbook.BasePlaybook$$Init`, pas deduit.

    DEGRADATION : caster sans position connue -> VRAI (aucun refus invente). Le natif, lui, ne peut
    pas recevoir un caster hors plateau sur ce chemin."""

    ability_id = int(ActiveAbilityType.StormOfFlensingBlades)   # 0x3f2 = 1010

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        sc = getattr(ctx, "scene", None)
        main = None if sc is None else sc.pos(getattr(ctx, "uid", None))
        if main is None or caster_tile is None:
            return True
        return (int(caster_tile[0]), int(caster_tile[1])) == (int(main[0]), int(main[1]))


class HadesAutocannonsPlaybook(DefaultActiveAbilityPlaybook):
    """`IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$ShouldExecute` (1147) :

        owner = EntityExtensions.GetCurrentOwnerEntityId(caster);
        foreach (u in battleQuery.<slot d'interface 0x8e = 142 GetAllEnemiesOf>(owner))
            if (UnitExtensions.HasTrait(u, UnitTrait.Summon)) return true;
        return false;

    Vrai ssi **l'ADVERSAIRE** du caster possede au moins une unite portant `UnitTrait.Summon` (**2**,
    qualifie par l'enum -- le littéral du décompilé ne le dit pas). L'utilite, la cible et la tuile
    de cast ne sont pas lues.

    ⚠ **LE SLOT DIT `GetAllEnemiesOf`, ET LE PORT LISAIT LES ALLIES**
    (`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1`). Le slot `0x8e`
    est `GetAllEnemiesOf` dans `data/symbols/<build>/metadata/interface_slots.tsv`
    (`GetAllFriendsOf` est le slot VOISIN, `0x8d = 141`), et les deux corps ne different QUE par le
    sens de la comparaison :

        // IdunBattle.Core.Services.BattleQuery$$GetAllEnemiesOf(playerEntityId)
        foreach (e in matchState.<slot 0x2f = GetPool>(0))
            if (EntityExtensions.GetCurrentOwnerEntityId(e) != playerEntityId) set.Add(e);
        // IdunBattle.Core.Services.BattleQuery$$GetAllFriendsOf : le MEME corps avec `==`.

    Le sens tactique confirme la lecture : les autocanons Hades sont l'arme anti-nuee de la MoW
    `blackForgefiend` -- elle les sort quand l'ADVERSAIRE a invoque, pas quand elle-meme a invoque
    (`blackForgefiend` n'invoque rien). Voisin de FORME deja porte, meme slot, meme quantificateur :
    `noncomparable/hellfyre_missile_rack.py` (`Sum(Select(GetAllEnemiesOf(owner), ...))`).

    ⚠ Le CASTER lui-meme n'entre PAS dans l'enumeration : `GetAllEnemiesOf` exclut par construction
    tout ce qui partage le proprietaire. (Le port d'avant, qui lisait les ALLIES, l'incluait -- d'ou
    la mise en garde qu'il portait, devenue sans objet.)

    SUBSTRAT : `scene.team` pour le proprietaire (le port n'a pas d'entite JOUEUR distincte ; sur les
    duels du harnais un joueur = une team, meme equivalence que `fire_of_absolution`), et
    `prediction._shared._entity_traits` pour `HasTrait` -- le FOYER de traits de la face DECISION,
    tri-etat (mesure `combatSnapshot` si presente, kit + grande-alliance sinon).

    ⚠ `GetAllEnemiesOf` ne filtre NI la mort NI la position (cf. `battle_query.all_enemies_of`, qui
    porte le meme natif sur le substrat `ctx.units`/`ctrl`) : ce mirror ne les filtre pas non plus.
    Un summon MORT valide donc le gate, cote natif comme ici.

    ⚠ **SUR LA ROUTE DU NATIF, CE GATE EST UNE TAUTOLOGIE -- et c'est ce qui a rendu l'inversion
    RESTRICTIVE plutot que permissive.** Le masque de `HadesAutocannonsAbility` porte
    `TargetIsSummon` (bit 13), mesure au RPC `abilityReason` (`hex: 0x2000`, `reasons:
    ["TargetIsSummon"]`), et ce bit EST le meme predicat que le gate -- `HasTrait(target,
    UnitTrait.Summon)`, cf. le bloc TRAITS de `runner/abilities/targeting.py`. Or
    `CalculateActionUtility` n'est appelee que pour une cible que `GetEligibleTargetsSelectable` a
    laissee passer : elle est donc DEJA un summon ENNEMI, et la boucle ci-dessous en trouve
    forcement un. **Le natif ne peut pas refuser ici.** L'ancienne lecture (les ALLIES), elle,
    REFUSAIT des que le camp du caster n'avait pas de summon a lui -- mesure live :
    `natif=OUI port_ancien=NON` sur un bras a un seul summon, cote ENNEMI."""

    ability_id = int(ActiveAbilityType.HadesAutocannons)        # 0x47b = 1147

    #: `HasTrait(u, 2)` du decompile -- `UnitTrait.Summon`, nomme, jamais l'ordinal nu.
    REQUIRED_ENEMY_TRAIT = UnitTrait.Summon

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return True                       # substrat absent -> aucun refus invente
        team = sc.team(getattr(ctx, "uid", None))
        if team is None:
            return True
        want = self.REQUIRED_ENEMY_TRAIT.name
        for u in (sc.units or ()):
            uid = u.get("id")
            # `GetAllEnemiesOf(owner)` : `GetCurrentOwnerEntityId(u) != owner`. Aucun filtre de vie
            # ni de position -- c'est le corps natif, relu.
            if uid is None or u.get("team") == team:
                continue
            if want in _entity_traits(sc, uid):
                return True
        return False


class TacticalPrecisionPlaybook(DefaultActiveAbilityPlaybook):
    """`IdunBattle.AI.Playbook.Loki.TacticalPrecisionPlaybook$$ShouldExecute` (1154, `ultraTitus`) --
    le residu que le tableau d'en-tete listait « requete + `Count > 1` », ferme par #976 :

        entities = AbilityEntities(caster, caster, target, caster, casterTile, ...)
        if (battleQuery.<slot 0xcd>(caster, casterTile, target)) return true;   // WillBeCharging
        sel = TacticalPrecisionAbility$$GetNonChargingAttackTargets()
            = DSLSelectors$$AdjacentEnemies(Caster@+0x48, unique: 1, selectionType: 3)
        return sel.<ITargetsSelector slot 2 = Count>(entities) > 1;             // STRICT

    DEUX clauses, en COURT-CIRCUIT `||`, et elles ne lisent NI l'utilite NI la tuile autrement que
    par `WillBeCharging`. Autrement dit : Titus lance si le pas le met AU CONTACT de sa cible
    (branche mono-cible du cast), ou s'il a DEJA au moins DEUX ennemis adjacents (branche AoE, qui
    frappe `AdjacentEnemies(Caster)`) -- c'est le gate qui empeche de gaspiller la branche AoE sur
    un seul ennemi. Le meme couple de branches gouverne `MakeDamagePredictions`
    (`entities.abilities.active_ability.TacticalPrecisionAbility`) et la face COMBAT
    (`runner/abilities/ultramarines.py`).

    ⚠ `WillBeCharging` (slot 0xcd, arite **3**) n'est PAS `IsCharging` (arite 2) : le premier
    compare deux voisinages pour un pas NON JOUE, le second lit `UnitComponent.ChargedUnitIds`, qui
    est vide tant que le caster n'a pas bouge. Prendre `IsCharging` ici rendrait la 1re clause
    TOUJOURS FAUSSE au moment ou le playbook s'execute -- un refus silencieux de toute la branche
    charge. Slot et arite LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`.

    ⚠ L'ANCRE du 2e terme est l'ENTITE caster, donc sa position REELLE -- pas `casterTile`. Le natif
    passe `Caster@+0x48` au selecteur, et `AdjacentTiles(<entite>)` resout `GetTiles(caster)`. Le
    sweep de tuiles ne deplace donc PAS ce comptage ; seul le 1er terme lit `casterTile`.

    DEGRADATION : substrat absent (pas de scene, pas de position) -> VRAI, aucun refus invente
    (meme convention que les quatre gates ci-dessus)."""

    ability_id = int(ActiveAbilityType.TacticalPrecision)       # 0x482 = 1154

    #: `1 < Count(...)` du corps natif -- comparaison STRICTE sur l'ENTIER rendu par le slot 2.
    MIN_ADJACENT_ENEMIES: int = 1

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return True
        uid = getattr(ctx, "uid", None)
        cur = sc.pos(uid)
        if cur is None:
            return True
        elev = getattr(sc, "elev_by_pos", None)
        team = sc.team(uid)
        # --- 1re clause : `WillBeCharging(caster, casterTile, target)` -------------------------
        pos_by_id = {}
        for u in (sc.units or ()):
            i = u.get("id")
            p = (u.get("pos") or {}) if isinstance(u.get("pos"), dict) else {}
            if i is None or i == uid or p.get("col") is None:
                continue
            pos_by_id[int(i)] = (p["col"], p["row"])
        if _bq.will_be_charging(target, cur, caster_tile, pos_by_id, elev, None):
            return True
        # --- 2e clause : `Count(AdjacentEnemies(Caster)) > 1`, ancre sur la position REELLE -----
        if team is None:
            return True
        epos = []
        for u in (sc.units or ()):
            i = u.get("id")
            p = (u.get("pos") or {}) if isinstance(u.get("pos"), dict) else {}
            if i is None or i == uid or p.get("col") is None or u.get("team") == team:
                continue
            epos.append((p["col"], p["row"]))
        return _bq.count_adjacent(cur, epos, elev, None) > self.MIN_ADJACENT_ENEMIES


#: Ids dont le gate est `utility > Fix64(0)` LITTERAL **et** dont la route est le generateur
#: d'attaque Comparable (`_best_attack` -> `calculate_action_utility`). Les quatre autres porteurs de
#: ce meme corps ont leur gate AILLEURS, et les inscrire serait un port MORT :
#:   * `28 Repair` / `1119 Repair_GalvanicField` -> `_repair_candidates` / `_repair_galvanic_candidates` ;
#:   * `18 Heal` / `1167 TwistedScience_Heal` / `1212 HealingBalms_Heal` -> `_heal_candidates`
#:     (`HealPlaybook.score` / `HealingBalms_HealPlaybook.score`, gate `pred > 0` deja pose).
LITERAL_ZERO_THRESHOLD_IDS: tuple[int, ...] = (
    int(ActiveAbilityType.StranglethornCannon),   # 0x420 = 1056
)

#: Les ids dont le corps natif EST `utility > Fix64(0)` mais dont le gate vit sur une autre route --
#: le fait est ATTESTE ici (et garde par un cran) pour qu'on ne les croie pas oublies.
LITERAL_ZERO_ELSEWHERE: dict[int, str] = {
    int(ActiveAbilityType.Repair): "action_generators._repair_candidates",                  # 28
    int(ActiveAbilityType.Heal): "common.HealPlaybook.score",                               # 18
    int(ActiveAbilityType.Repair_GalvanicField): "action_generators._repair_galvanic_candidates",  # 1119
    # ⚠ Le PLAYBOOK natif s'appelle `TwistedScience_HealPlaybook`, l'ABILITY `Heal_TwistedScience` :
    # les deux noms sont inverses dans le build, et seul l'id `0x48f` lu au `.ctor` les apparie.
    int(ActiveAbilityType.Heal_TwistedScience): "common.HealPlaybook.score",                # 1167
    int(ActiveAbilityType.HealingBalms_Heal): "common.HealingBalms_HealPlaybook.score",     # 1212
}


def _register_all() -> None:
    for aid in LITERAL_ZERO_THRESHOLD_IDS:
        register(LiteralZeroThresholdPlaybook(aid))
    register(ReapingScythePlaybook())
    register(StormOfFlensingBladesPlaybook())
    register(HadesAutocannonsPlaybook())
    register(TacticalPrecisionPlaybook())        # 1154 (#976) -- WillBeCharging || adj > 1


_register_all()
