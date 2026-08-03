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
else { var fromActive = GetCustomNormalAttackTypeFromActive(this, config); ... }
ActiveAbilityComponent.Add(comp, type, state, null);

// GetCustomNormalAttackTypeFromPassive(this, config)
foreach (var passive in config.<+0xa8> /* UnitConfiguration.PassiveAbilities */) {
    var custom = StaticBattleRules.TriggeredAbility.GetCustomNormalAttack(passive);
    if (custom.HasValue) return custom;          // le PREMIER passif gagnant s'impose
}
if (config.<+0xb0>.HasValue) { ... }             // la branche TERTIAIRE (relique)
return null;
```

`StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack` est un lookup dans un
`Dictionary<TriggeredAbilityType, ActiveAbilityType>` STATIQUE.

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


def _kit_ability_names(visual_id) -> set:
    """REPLI (canal muet) : les noms d'abilities du kit gameconfig, passives ET actives -- la
    derivation d'avant, conservee telle quelle pour ne rien degrader la ou rien n'est mesure."""
    if not visual_id:
        return set()
    try:
        kit = GC.unit_abilities(visual_id) or {}
    except Exception:
        return set()
    out = set()
    for key in ("passive", "active"):
        for a in (kit.get(key) or []):
            if isinstance(a, str):
                out.add(a)
            elif isinstance(a, dict):
                nm = a.get("name") or a.get("id")
                if nm:
                    out.add(nm)
    return out


def substitutes_normal_attack(passive_name: str, passive_abilities=None, visual_id=None) -> bool:
    """« L'attaque normale de CETTE entite est-elle celle que substitue `passive_name` ? »

    C'est le predicat de dispatch de tous les molds `<X>_NormalAttackAbility$$PredictAttack` et de
    `visit_AttackUnitMessage`. Tri-etat sur `passive_abilities` (cf. en-tete du module).

    ⚠ Le `substitutes is None` n'est pas defensif, il ferme un `None == None` : un `passive_name`
    absent de la table rendait `None`, la boucle rend `None` quand aucun passif ne substitue, et le
    predicat repondait alors VRAI pour n'importe quel passif non substituant sur n'importe quelle
    unite. Inerte tant que les seuls appelants passent des cles de la table -- mais c'est une
    invariance de POSTE D'APPEL, pas du foyer, et le foyer est ce qui doit tenir."""
    if passive_abilities is not None:
        substitutes = CUSTOM_NORMAL_ATTACK_BY_PASSIVE.get(passive_name)
        if substitutes is None:
            return False       # ce passif ne substitue AUCUNE attaque normale (absent du dict natif)
        return custom_normal_attack_from_passives(passive_abilities) == substitutes
    return passive_name in _kit_ability_names(visual_id)
