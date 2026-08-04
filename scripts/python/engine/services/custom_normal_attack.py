"""Substitution de l'ATTAQUE NORMALE par un passif -- mirror d'
`IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive`.

L'attaque normale d'une unite n'est PAS toujours la generique `Loki_NormalAttack` (69) : la fabrique
lui en substitue une CONCRETE quand un passif de sa CONFIGURATION le prescrit. Le corps, lu verbatim
(`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` puis
`...$$GetCustomNormalAttackTypeFromPassive`) :

```csharp
// AddNormalAttackAbility(this, entity, config, activeAbilityState, triggeredAbilityState)
// config.Traits = `UnitConfiguration.Traits` (config@+0xd0) ; 0x0e = Erratic, 0x15 = Harmless.
if (config.Traits.Contains(0x0e) || config.Traits.Contains(0x15)) return;   // aucune attaque normale
var fromPassive = GetCustomNormalAttackTypeFromPassive(this, config);
if (fromPassive.HasValue) { type = fromPassive.Value; state = triggeredAbilityState; }
else {
    var fromActive = GetCustomNormalAttackTypeFromActive(this, config);
    if (fromActive.HasValue) { type = fromActive.Value; state = activeAbilityState; }
    else if (config.Traits.Contains(0x7e7)) { type = 0x406; state = activeAbilityState; }
    else { ... repli generique ... }
}
ActiveAbilityComponent.Add(comp, type, state, null);

// GetCustomNormalAttackTypeFromPassive(this, config)
foreach (var passive in config.<+0xa8> /* UnitConfiguration.PassiveAbilities */) {
    var custom = StaticBattleRules.TriggeredAbility.GetCustomNormalAttack(passive);
    if (custom.HasValue) return custom;          // le PREMIER passif gagnant s'impose
}
if (config.<+0xb0>.HasValue) { ... }             // la branche TERTIAIRE (relique)
return null;

// GetCustomNormalAttackTypeFromActive(this, config)   -- #419-r1-tr14-r5-r2
foreach (var active in config.<+0xa0> /* UnitConfiguration.ActiveAbilities */) {
    var custom = StaticBattleRules.ActiveAbility.GetCustomNormalAttack(active);
    if (custom.HasValue) return custom;          // le PREMIER actif gagnant s'impose
}
return null;                                     // PAS de branche tertiaire ici
```

`StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack` est un lookup dans un
`Dictionary<TriggeredAbilityType, ActiveAbilityType>` STATIQUE ; son homologue
`StaticBattleRules.ActiveAbility$$GetCustomNormalAttack` en est un dans un
`Dictionary<ActiveAbilityType, ActiveAbilityType>` STATIQUE **distinct** (cf. les deux tables
plus bas).

## Pourquoi ce module existe -- le fork qu'il ferme (#419-r1-tr14-r5)

La cle de dispatch native est `UnitConfiguration.PassiveAbilities`, c'est-a-dire
`BattleConfiguration.Units[].PassiveAbilities` : un fait d'ENTITE. Le port, lui, la re-derivait du
**KIT gameconfig** par `visualId`, a trois call-sites (`prediction/normal_attack.py` x2,
`runner/operations/damage.py` x1). Les deux coincident tant que personne ne touche a la liste de
passifs -- et divergent SILENCIEUSEMENT des qu'un montage la modifie, ce que fait tout bras
`catalog_inject.write_grafted_seed_bc(..., replace=True)`.

MESURE (`probe_419r1tr14r5_normal_attack_stages.py`, `tauMarksman` / `astraBullgryn`, `MC1_67`) --
deux bras qui ne different QUE par `PassiveAbilities`, quatre crans, contre-epreuve RECIPROQUE :

| bras | `PassiveAbilities` | attaque normale NATIVE | ecart port - natif (tuile a distance) |
|---|---|---|---|
| `kit`   | `[1119]` | **1076** `MV71SniperDroneSquadAttack` | `0.000000` / `0.000000` |
| `strip` | `[]`     | **69** `Loki_NormalAttack`            | `+5.458908` / `+16.056789` |

et, dispatch du port FORCE sur le chemin arme, les deux colonnes s'echangent exactement
(`kit` devient `-5.458908` / `-16.056789`, `strip` devient `0.000000` / `0.000000`). Le chemin arme
du port reproduit donc le natif BIT A BIT dans les DEUX regimes de mouvement : les deux termes de
l'ecart ont UN SEUL foyer, et c'est ce dispatch.

C'est le meme vice que #366-r1 (`collect_triggered_abilities` derivait les passifs du kit) et que
#264 sur l'axe TRAITS : le natif monte `BC.Units[].PassiveAbilities`, jamais le kit.

## Tri-etat, et pourquoi le repli KIT reste

`passive_abilities` est la liste MESUREE des passifs de l'entite (`UnitContext.passive_abilities`,
hierarchie 2 du `TriggeredAbilityComponent`, cf. `runner.snapshot.PASSIVE_HIERARCHY`) :

* une LISTE (fut-elle vide) = mesure -> mirror STRICT de la fabrique ;
* `None` = canal muet (State nu, capture rejouee hors harnais live) -> repli sur le KIT, c'est-a-dire
  STRICTEMENT le comportement d'avant. On ne devine pas, et on ne degrade pas non plus un
  consommateur qui n'a pas le canal.
"""
from __future__ import annotations

import gameconfig as GC

# Le dictionnaire statique de `StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack`,
# {`TriggeredAbilityType` -> `ActiveAbilityType`} -- QUATORZE entrees, transcrites du `.cctor`.
#
# ## D'ou vient cette table (#419-r1-tr14-r5-r1)
#
# `GetCustomNormalAttack` est un `ContainsKey` + `get_Item` sur le champ STATIQUE `+0x50` de
# `StaticBattleRules.TriggeredAbility` ; ce champ est ecrit UNE fois par
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$.cctor`,
# qui construit le `Dictionary` puis empile 14 `Add(key, value)` a litteraux CONSTANTS avant de
# l'assigner. Les 14 paires sont donc LUES, pas deduites.
#
# TROIS controles independants les valident :
#  1. les QUATRE entrees deja portees avant #419-r1-tr14-r5-r1 (mesurees live, une par une) sont
#     retrouvees a l'identique dans le `.cctor` -- 4/4, dans la meme orientation cle/valeur ;
#  2. `StaticBattleRules.TriggeredAbility$$IsCustomNormalAttackDerivedFromTriggeredAbility` fait
#     `dict.Values.Contains(<ActiveAbilityType>)` : les VALEURS sont bien des `ActiveAbilityType`
#     et les CLES des `TriggeredAbilityType` -- l'orientation est prouvee par un second corps ;
#  3. les 14 valeurs sont exactement les `ActiveAbilityType` en `*NormalAttack*` du build, moins
#     les deux generiques (`17 NormalAttack`, `69 Loki_NormalAttack`) et moins
#     `1126 RogalDorn_NormalAttack`, qui n'est dans AUCUNE des deux tables passives.
#
# ⚠ AUCUNE entree ne se devine par son nom, et deux d'entre elles le prouvent : la cle
# `HeavyBoltPistol` rend `TemplarInitiateNormalAttack` (zero parente lexicale), et
# `RogalDorn_NormalAttack` -- qui PORTE le suffixe -- n'est la valeur d'aucune cle passive.
# Une table dressee « par les noms en *NormalAttack* » aurait donc rate la premiere et invente
# la seconde.
#
# ## Pourquoi la table doit etre COMPLETE, et pas seulement « celle des molds portes »
#
# `custom_normal_attack_from_passives` mirrore la boucle « le PREMIER passif gagnant s'impose ».
# Une table PARTIELLE ne fait pas « moins de dispatch » : elle fait un dispatch FAUX des qu'une
# unite porte, AVANT un passif porte, un passif substituant absent de la table -- l'entree
# manquante est sautee et la main passe a la suivante, ce que le natif ne fait jamais.
# Exemple mesurable : `PassiveAbilities = [HeavyBoltPistol, Boltstorm]` -> natif
# `TemplarInitiateNormalAttack`, port a table partielle `Boltstorm_NormalAttack` (donc le fold
# `GetAdditionalDamagePrediction` de #446-r1, que le natif ne joue pas).
#
# La table dit QUELLE attaque normale l'entite porte ; elle ne dit rien du mold de PREDICTION.
# Les molds portes restent les quatre de `prediction/normal_attack.py` (`Boltstorm`,
# `RighteousRepugnance`, `ProperKilly`) et du chemin drone (`MV71SniperDroneSquad`) : pour les dix
# autres attaques normales concretes, le port reste sur la branche generique -- c'est la
# couverture des molds, pas le dispatch, et ce sont deux axes distincts.
CUSTOM_NORMAL_ATTACK_BY_PASSIVE: dict[str, str] = {
    "HeavyBoltPistol": "TemplarInitiateNormalAttack",            # 1083 -> 1046
    "MV71SniperDroneSquad": "MV71SniperDroneSquadAttack",        # 1119 -> 1076
    "ProperKilly": "ProperKilly_NormalAttack",                   # 1147 -> 1086
    "BlisteringAssault": "BlisteringAssault_NormalAttack",       # 1190 -> 1114
    "FeederTendrils": "FeederTendrils_NormalAttack",             # 1197 -> 1120
    "Boltstorm": "Boltstorm_NormalAttack",                       # 1090 -> 1128
    "OptimizedGait": "OptimizedGait_NormalAttack",               # 1205 -> 1123
    "FloatingDeath": "FloatingDeath_NormalAttack",               # 1243 -> 1146
    "AncientFury": "AncientFury_NormalAttack",                   # 1256 -> 1162
    "Wraithcannon": "Wraithcannon_NormalAttack",                 # 1220 -> 1138
    "ElectroShock": "ElectroShock_NormalAttack",                 # 1303 -> 1178
    "RighteousRepugnance": "RighteousRepugnance_NormalAttack",   # 1107 -> 1182
    "TalonOfHorus": "TalonOfHorus_NormalAttack",                 # 1484 -> 1205
    "Fealty": "Fealty_NormalAttack",                             # 1512 -> 1220
}

# Le dictionnaire statique de `StaticBattleRules.ActiveAbility$$GetCustomNormalAttack` --
# {`ActiveAbilityType` -> `ActiveAbilityType`}. La SECONDE voie de la cascade (#419-r1-tr14-r5-r2).
#
# ## Une AUTRE table, pas une extension de la precedente
#
# Le foyer de lecture est `statics+0x28` de `StaticBattleRules.ActiveAbility`, la ou la voie passive
# lit `statics+0x50` de `StaticBattleRules.TriggeredAbility` : deux classes, deux champs, deux types
# de cle. Le `.cctor` d'`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility`
# construit le `Dictionary`, empile **UN SEUL** `Add` a litteraux constants, puis l'assigne -- il n'y
# a rien d'autre entre le ctor et l'assignation.
#
# ORIENTATION cle/valeur : la voie passive la tenait d'un second corps
# (`IsCustomNormalAttackDerivedFromTriggeredAbility`, un `dict.Values.Contains`) ; ici ce corps
# n'existe pas, et l'orientation se lit dans le foyer LUI-MEME -- `GetCustomNormalAttack(param)` fait
# `ContainsKey(dict, param)` puis `get_Item(dict, param, out res)`, donc le parametre est la CLE, et
# le `.cctor` appelle `Add(dict, 0x464, 0x466)` aux MEMES positions d'argument.
#
# ## Ce que la CONFRONTATION a etabli (probe_419r1tr14r5r2_active_normal_attack.py, 4 bras)
#
# `PoundThemToDust` n'a AUCUN porteur -- 0 sur les 683 kits gameconfig (5 voies), 0 sur les 175
# unites du seed BC. Le substrat `BC.Units[].ActiveAbilities` est en revanche ECRIVABLE
# (`catalog_inject.graft_active_ability`, #447), et c'est par la que les quatre bras passent :
#
#   | unite           | PassiveAbilities | ActiveAbilities  | natif MESURE               |
#   |-----------------|------------------|------------------|----------------------------|
#   | `astraBullgryn` | `[]`             | `[PoundThemToDust]` | **`RogalDorn_NormalAttack`** |
#   | `necroWarden`   | `[]`             | (origine)        | `Loki_NormalAttack` (temoin) |
#   | `orksNob`       | `[Boltstorm]`    | `[PoundThemToDust]` | **`Boltstorm_NormalAttack`** |
#   | `eldarRanger`   | `[Boltstorm]`    | (origine)        | `Boltstorm_NormalAttack`     |
#
# La 3e ligne est ce qui rend la CASCADE obligatoire et non decorative : la cle active EST montee
# (`unitAbilityStates` rend `ActiveAbilityComponent = [1124, 1128]` pour cette unite), et pourtant
# l'attaque normale est celle de la voie PASSIVE. Un port qui repondrait « 1124 present donc 1126 »
# se tromperait exactement la.
#
# ## Ce que cette voie NE change PAS -- mesure, pas supposition
#
# Meme montage, meme porteur (`templAggressor` passifs vides), meme cible, meme tuile, deux runners
# qui ne different QUE par `ActiveAbilities` : `aiPlaybookPredict` rend **`1299..1950`, 3 coups** des
# DEUX cotes. La substitution par la voie active ne deplace donc aucun chiffre de degat, et le
# playbook ne bouge pas non plus -- `IdunBattle.AI.Playbook.Loki.RogalDorn_NormalAttackPlaybook$$.ctor`
# delegue au MEME generique `ALoki_NormalAttackPlaybook<T>$$.ctor` que
# `IdunBattle.AI.Playbook.Loki.Loki_NormalAttackPlaybook$$.ctor`, seul l'`ActiveAbilityType` passe en
# argument change (`0x466` contre `0x45`), et il n'a AUCUN override (contraste sur le meme gisement :
# `ProperKilly_NormalAttackPlaybook` en porte cinq).
#
# La table est donc portee pour la FIDELITE de la cascade, pas pour un ecart de degat -- et c'est
# dit ici pour que personne n'aille chercher un ecart qui n'existe pas.
CUSTOM_NORMAL_ATTACK_BY_ACTIVE: dict[str, str] = {
    "PoundThemToDust": "RogalDorn_NormalAttack",                 # 1124 -> 1126
}

#: Les DEUX traits qui SUPPRIMENT purement l'attaque normale (#419-r1-tr14-r5-r4). Premiere ligne
#: de `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, lue verbatim :
#:
#:     if (config.Traits.Contains(0x0e) || config.Traits.Contains(0x15)) return;
#:
#: -- deux `List<UnitTrait>.Contains` sur `UnitConfiguration.Traits` (`config@+0xd0`), et un
#: `return` SEC : ni `GetCustomNormalAttackTypeFromPassive`, ni la voie active, ni le repli
#: generique ne sont atteints, et `ActiveAbilityComponent$$Add` n'est jamais appele. L'unite
#: n'a donc AUCUNE attaque normale -- `ActiveAbilityComponent.NormalAttackType@0x28` reste a 0.
#:
#: `0x0e` = `Erratic`, `0x15` = `Harmless` (enum `IdunBattle.Entities.Enum.UnitTrait`). ⚠ Ce n'est
#: PAS `NonAttacking` (1033), qui est un AUTRE trait et n'entre pas dans cette garde : les valeurs
#: se lisent au decompile, jamais par affinite de nom.
#:
#: SUBSTRAT : `UnitConfiguration.Traits`, donc `BC.Units[].Traits` -- un fait d'ENTITE, comme les
#: passifs ci-dessus (#264 : le natif monte la config, jamais le kit gameconfig).
NORMAL_ATTACK_SUPPRESSING_TRAITS: frozenset = frozenset({"Erratic", "Harmless"})


def has_normal_attack(traits) -> bool:
    """« Cette unite recoit-elle une attaque normale a la fabrique ? » -- mirror de la garde
    d'entree de `UnitFactory$$AddNormalAttackAbility` (cf. `NORMAL_ATTACK_SUPPRESSING_TRAITS`).

    `traits` = les noms de `UnitTrait` de l'entite. `None` = canal muet -> `True`, c'est-a-dire
    STRICTEMENT le comportement d'avant : on ne devine pas une absence qu'on n'a pas mesuree.
    """
    if traits is None:
        return True
    return not (NORMAL_ATTACK_SUPPRESSING_TRAITS & set(traits))


def custom_normal_attack_from_passives(passive_abilities) -> str | None:
    """Mirror de la 1re boucle de `UnitFactory$$GetCustomNormalAttackTypeFromPassive` : le PREMIER
    passif de la liste dont `GetCustomNormalAttack` rend une valeur s'impose, les suivants sont
    ignores. `passive_abilities` = noms de `TriggeredAbilityType`, dans l'ORDRE de la configuration.

    ⚠ L'ordre compte et ce n'est pas un detail de style : deux passifs substituants sur la meme
    unite ne se combinent pas, le premier gagne. Un `set` ferait perdre exactement cette lecture.
    """
    for name in (passive_abilities or ()):
        got = CUSTOM_NORMAL_ATTACK_BY_PASSIVE.get(name)
        if got is not None:
            return got
    return None


def custom_normal_attack_from_actives(active_abilities) -> str | None:
    """Mirror de `UnitFactory$$GetCustomNormalAttackTypeFromActive` : le PREMIER actif de la liste
    dont `StaticBattleRules.ActiveAbility$$GetCustomNormalAttack` rend une valeur s'impose.
    `active_abilities` = noms d'`ActiveAbilityType`, dans l'ORDRE de la configuration.

    Pendant EXACT de `custom_normal_attack_from_passives`, a DEUX differences pres, toutes deux
    lues : la table consultee (`CUSTOM_NORMAL_ATTACK_BY_ACTIVE`) et l'absence de branche TERTIAIRE
    (la voie passive consulte `config@+0xb0` apres la boucle, la voie active s'arrete a la boucle).
    """
    for name in (active_abilities or ()):
        got = CUSTOM_NORMAL_ATTACK_BY_ACTIVE.get(name)
        if got is not None:
            return got
    return None


def custom_normal_attack(passive_abilities=None, active_abilities=None, visual_id=None) -> str | None:
    """« QUELLE attaque normale la fabrique pose-t-elle sur cette entite ? » -- mirror de la CASCADE
    de `UnitFactory$$AddNormalAttackAbility`. `None` = aucune substitution (l'attaque normale reste
    l'ability generique de l'unite).

    L'ORDRE n'est pas un detail : la voie PASSIVE est consultee la PREMIERE, et la voie ACTIVE n'est
    atteinte que si elle rend `null`. C'est mesure, pas suppose -- une unite portant a la fois
    `PassiveAbilities = [Boltstorm]` et `ActiveAbilities = [PoundThemToDust]` recoit
    `Boltstorm_NormalAttack` cote natif, alors meme que la cle active EST montee dans son
    `ActiveAbilityComponent`.

    TRI-ETAT PAR VOIE, et c'est volontaire : chaque liste a son propre canal de mesure, donc son
    propre repli. `None` = canal muet -> la voie retombe sur le KIT gameconfig ; une LISTE (fut-elle
    vide) = mesure, et elle fait autorite pour CETTE voie seulement.
    """
    from_passive = (custom_normal_attack_from_passives(passive_abilities)
                    if passive_abilities is not None
                    else custom_normal_attack_from_passives(_kit_ability_names(visual_id, "passive")))
    if from_passive is not None:
        return from_passive
    if active_abilities is not None:
        return custom_normal_attack_from_actives(active_abilities)
    return custom_normal_attack_from_actives(_kit_ability_names(visual_id, "active"))


def _kit_ability_names(visual_id, key: str) -> list:
    """REPLI (canal muet) : les noms d'abilities du kit gameconfig pour la voie `key`
    (`"passive"` ou `"active"`).

    ⚠ LES DEUX VOIES NE PARTAGENT PAS LEUR SOURCE, et ce parametre est ce qui le fait respecter.
    Ce repli fusionnait `passive` et `active` en un seul ensemble, si bien qu'un passif de la table
    trouve dans les ACTIVES du kit faisait repondre VRAI a un predicat que le natif, lui, ne pose
    que sur `UnitConfiguration.PassiveAbilities`. Mesure du gisement avant correction : **0 sur les
    683 kits gameconfig** (aucune cle de la table passive n'apparait en `activeAbilities`), donc le
    faux positif etait LATENT sur ce build -- il est ferme structurellement, pas parce qu'il mordait.
    """
    if not visual_id:
        return []
    try:
        kit = GC.unit_abilities(visual_id) or {}
    except Exception:
        return []
    out = []
    for a in (kit.get(key) or []):
        nm = a if isinstance(a, str) else (a.get("name") or a.get("id")) if isinstance(a, dict) else None
        if nm and nm not in out:
            out.append(nm)
    return out


def substitutes_normal_attack(passive_name: str, passive_abilities=None, visual_id=None,
                              active_abilities=None) -> bool:
    """« L'attaque normale de CETTE entite est-elle celle que substitue `passive_name` ? »

    C'est le predicat de dispatch de tous les molds `<X>_NormalAttackAbility$$PredictAttack` et de
    `visit_AttackUnitMessage`. Il compare la valeur que `passive_name` substituerait au resultat de
    la CASCADE COMPLETE -- pas de la seule voie passive : une entite dont la voie ACTIVE a gagne ne
    porte l'attaque normale d'AUCUN passif, et le predicat doit dire NON.

    ⚠ Le `substitutes is None` n'est pas defensif, il ferme un `None == None` : un `passive_name`
    absent de la table rendait `None`, la cascade rend `None` quand rien ne substitue, et le
    predicat repondait alors VRAI pour n'importe quel passif non substituant sur n'importe quelle
    unite. Inerte tant que les seuls appelants passent des cles de la table -- mais c'est une
    invariance de POSTE D'APPEL, pas du foyer, et le foyer est ce qui doit tenir."""
    substitutes = CUSTOM_NORMAL_ATTACK_BY_PASSIVE.get(passive_name)
    if substitutes is None:
        return False           # ce passif ne substitue AUCUNE attaque normale (absent du dict natif)
    return custom_normal_attack(passive_abilities=passive_abilities,
                                active_abilities=active_abilities,
                                visual_id=visual_id) == substitutes
