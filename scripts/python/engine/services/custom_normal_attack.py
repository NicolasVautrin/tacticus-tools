"""Substitution de l'ATTAQUE NORMALE par un passif -- mirror d'
`IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive`.

L'attaque normale d'une unite n'est PAS toujours la generique `Loki_NormalAttack` (69) : la fabrique
lui en substitue une CONCRETE quand un passif de sa CONFIGURATION le prescrit. Le corps, lu verbatim
(`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` puis
`...$$GetCustomNormalAttackTypeFromPassive`) :

```csharp
// AddNormalAttackAbility(this, entity, config, activeAbilityState, triggeredAbilityState)
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

# Les entrees PORTEES du dictionnaire statique de
# `StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack` : {passif -> attaque normale custom}.
# Ce sont EXACTEMENT les quatre pour lesquelles le port a un mold ; la table native en contient
# d'autres (l'enum `ActiveAbilityType` porte 16 noms en `*NormalAttack*`), non portees -- cf. le
# residu `#419-r1-tr14-r5-r1`. Chaque entree est ATTESTEE, aucune n'est deduite d'un nom :
#   `MV71SniperDroneSquad`  -> mesure directe (bras `kit` = 1076, bras `strip` = 69) ;
#   `Boltstorm`             -> #446-r1 §2 et son controle apparie `PassiveAbilities=[]` -> 69 ;
#   `RighteousRepugnance`   -> #446-r3 (`adeptMorvenn`, attaque normale concrete 1182) ;
#   `ProperKilly`           -> registre INERTE (zero porteur dans ce build, cf. normal_attack.py).
CUSTOM_NORMAL_ATTACK_BY_PASSIVE: dict[str, str] = {
    "MV71SniperDroneSquad": "MV71SniperDroneSquadAttack",   # 1119 -> 1076
    "Boltstorm": "Boltstorm_NormalAttack",                  # 1090 -> 1128
    "RighteousRepugnance": "RighteousRepugnance_NormalAttack",   # 1107 -> 1182
    "ProperKilly": "ProperKilly_NormalAttack",              # 1147 -> 1086
}


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

    C'est le prédicat de dispatch de tous les molds `<X>_NormalAttackAbility$$PredictAttack` et de
    `visit_AttackUnitMessage`. Tri-etat sur `passive_abilities` (cf. en-tete du module)."""
    if passive_abilities is not None:
        return custom_normal_attack_from_passives(passive_abilities) == \
            CUSTOM_NORMAL_ATTACK_BY_PASSIVE.get(passive_name)
    return passive_name in _kit_ability_names(visual_id)
