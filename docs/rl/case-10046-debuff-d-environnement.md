# case-10046 (volet DEBUFF) — débuffer l'adversaire par une ability d'environnement

Mesuré le 2026-08-23, build `t6dpr4k06g`, sur runner isolé. **Aucun changement de hook, aucun
reinject** : tout passe par un seed BC custom.

## 1. La voie BC installe une env-ability sur un RUNNER

`env_ability_patch.py` n'agit que sur la **source vivante** (`LoadBattle.onLeave`, campagne /
sandbox). Pour un banc, il suffit d'écrire le réceptacle dans le seed BC :

```json
BC.EnvironmentAbilities.EnvironmentAbilities = [{"ConfigId": "<Nom>", "Level": 1}]
```

Témoin non ambigu : `EnvStartProtection` posé par cette voie rend des boucliers à
`amount: 500` — exactement le `shieldHp: 500` de sa config au catalogue.

⚠ Une config **absente** du catalogue peut y être **ajoutée** dans le même seed BC
(`BC.Abilities.EnvironmentAbilities["<Nom>"] = {Variables, Constants, ...}`) : clé chaîne, donc
aucun des dangers du dictionnaire à clé de type valeur qui a tué le process le 2026-08-21. Testé,
accepté, aucun « system error ».

## 2. ⚠ DEUX LISTES DANS LE RÉCEPTACLE, ET ELLES NE CIBLENT PAS PAREIL

Le dump de champs (`sources_win`, `Il2CppDumper`) donne la forme exacte :

```csharp
class EnvironmentAbilityConfiguration {
    TriggeredAbilityConfigId ConfigId;    // 0x10
    Level                    Level;       // 0x20
    Nullable<PlayerId>       PlayerId;    // 0x24   <- `ajouterAbility` le laisse NUL
}
class EnhancementsEnvironmentAbilityConfiguration : EnvironmentAbilityConfiguration {
    List<EnhancementTargetConfiguration> Targets;  // { UnitConfigId Target; int Stack; }
    int                                  Stack;
}
```

| liste | ciblage |
|---|---|
| `EnvironmentAbilities` | écrit dans le `CreateTrigger` de l'ability — **pas un argument** |
| `EnhancementsEnvironmentAbilities` | **par unité NOMMÉE**, via `Targets[].Target` |

La seconde est le vecteur de debuff : `EnhancementAddTraitAbility$$CreateTrigger` =
`On(EventTriggerType.PostAbilityInit) & DSLTriggers$$IsEnhancementTarget(target, enhancement)`,
et le behaviour est `DSLBehaviors$$AddTrait(target, AbilityConstantType.trait)` +
`AddEffect(EffectType.EnhancementAddTrait)`.

## 3. La recette, vérifiée

`BC.Abilities.EnvironmentAbilities` porte **106** variantes `EnhancementAddTrait:<Trait>`, toutes
déjà configurées (`Constants: {"trait": "<Trait>"}`). Rien à synthétiser.

```json
BC.EnvironmentAbilities.EnhancementsEnvironmentAbilities = [{
  "ConfigId": "EnhancementAddTrait:Stationary",
  "Level": 1,
  "PlayerId": 12,
  "Targets": [{"Target": {"PureId": "necroWarden", "Rarity": null, "Level": null,
                          "IsBorrowed": false, "IsPvpOpponent": false}, "Stack": 1}],
  "Stack": 1
}]
```

Mesure : `Harmless` (trait 21) posé sur les **deux** unités adverses nommées, **absent** de mes
deux unités. Et `Stationary` : les deux ennemis restent en rangée 8 là où ils sont posés, alors
qu'au run précédent — **même seed, même board, même placement** — ils atteignaient la rangée 5 en
un tour.

## 3bis. BAISSER LES DÉGÂTS : un POURCENTAGE NÉGATIF, et il n'y a aucun garde

Le menu des traits est fermé ; celui des pourcentages ne l'est pas.
`EnhancementDamageBoostAbility$$CreateBehaviour` pose `AddEffect(EffectType 0x5c2)` avec la seule
constante `extraDmgPct`, et **rien ne l'oblige à être positive**. Posée par la même voie
enhancement que ci-dessus (`ConfigId: "EnhancementDamageBoost"`), sur `necroWarden` seul, board
`C1_74`, mêmes placements, même seed :

| `extraDmgPct` | plan d'attaque de l'ennemi | dégâts RÉELLEMENT subis (2 coups) |
|---|---|---|
| `+20` | `[2080-3120]` | **4369** |
| `-50` | `[868-1300]` | — |
| `-100` | `[0-0]` | **0** |
| `-150` | `[0-0]` | — |

868/2080 = **0,4167** = (1 − 0,50)/(1 + 0,20), à la quatrième décimale : c'est un multiplicateur
pur `(1 + pct/100)`, sans clamp jusqu'à `-100`. En dessous, le dégât est **borné à zéro** — pas de
soin par dégât négatif.

⚠ Mesurer sur le COUP, pas sur le plan : `[0-0]` est une **prédiction**. Les `0 dmg` contre
`4369 dmg` du témoin viennent d'un `aiturn` réel, à seed et placement identiques.

Même forme disponible sur les autres constantes de la famille : `EnvStrategicBuff`
(`extraDmgPct`, `extraCritChance`), `EnvStatBoost` (`dmgPct`, `healthPct`, `armorPct`, gardé par
un `trait`), `EnhancementCritBoost`, `EnhancementPierceBoost`, `EnhancementHitBoost`,
`EnhancementRegeneration`, `EnhancementLifeSteal` — **non mesurées**.

## 4. ⚠ LE NOM D'UN TRAIT NE DIT PAS SA SÉMANTIQUE — deux essais perdus dessus

`Harmless` posé : l'adversaire attaque quand même (2115 dmg encaissés). `Immovable` posé :
l'adversaire avance de trois rangées. Les deux traits étaient bel et bien **sur les unités** —
le mécanisme marchait, c'est mon hypothèse sur leur sens qui était fausse (`Immovable` n'est pas
« ne se déplace pas », c'est vraisemblablement « ne se fait pas déplacer »).

Le trait qui immobilise est `Stationary`. **Le dériver du moteur, jamais du nom** :

```powershell
git grep -oh "UnitTrait\.[A-Za-z_]*" -- scripts/python/engine | sort | uniq -c | sort -rn
```

Les traits réellement consultés, par nombre de sites : `Steppable` 113 · `Hero` 77 · `Summon` 67 ·
`Chaos`/`Psyker` 46 · `Object` 43 · `Immune` 34 · `Mechanical` 23 · `BigTarget` 21 · `Decoy` 17 ·
`Vehicle`/`Stationary` 16 … Un trait absent de cette liste peut se poser sans rien changer.

## 5. ⚠ `EnvAttemptDebuff` (1288) EST UN LEURRE — il cible juste, et ne fait RIEN

C'est la seule ability **nommée** pour débuffer l'adversaire, et son ciblage est le plus net du
lot : `On(EventTriggerType.InitialMatchUnitAdded) & DSLTriggers$$IsInTeam(sel, TeamId 2)` —
l'équipe adverse **en dur**, `IsInTeam` prenant un `IdunBattle.Core.TeamId` absolu. Deux
constantes seulement, lisibles dans
`idun.shared.commands.ShowGuildWarsBattlePreviewPopupCommand$$AddAttemptDebuffEnvironmentAbility` :
`AbilityConstantType.amount` (110) et `AbilityConstantType.hpPct` (18).

Posé, il s'installe proprement et l'effet `AttemptsDebuff` apparaît sur **les deux adversaires et
aucun allié**. Mais il ne fait rien : `IdunBattle.Entities.Effects.Loki.EnvAttemptsDebuffEffect$$.ctor`
n'appelle que `BaseEffect$$.ctor` sans modification, `$$GetLocalizationDataInternal` rend un
dictionnaire **vide**, et le diff de stats contre un témoin sans debuff donne **zéro écart**
(seuls les `entityId` glissent). Balayer `hpPct` de 30 à 90 ne change rien non plus.

Son appelant est une popup de **prévisualisation** de guerre de guilde : c'est du mobilier
d'affichage, pas une mécanique de combat.

⚠ Corollaire de méthode : « l'effet est ACTIF sur la bonne cible » ne dit rien de « l'effet FAIT
quelque chose ». Il a fallu le diff de stats **et** le décompilé du ctor pour le trancher.

## 6. Résidus

- `PlayerId` de `EnvironmentAbilityConfiguration` n'est écrit par personne côté hook
  (`environment-abilities.ts`, `ajouterAbility` ne pose que `ConfigId` et `Level`). On ne sait pas
  ce qu'il change — non mesuré.
- La voie LIVE reste sans levier : le patch n'écrit ni le catalogue
  (`BC.Abilities.EnvironmentAbilities`, clé chaîne — sûr) ni la liste des enhancements. Les deux
  sont de petits ajouts, et demandent une fenêtre de reinject.
- ⚠ Rectification d'une ligne du commit `e44ccb6b` : « `EnvReinforcementShield` 0 occurrence dans
  le gameconfig » accusait la **mauvaise table**. Les configs d'env-ability vivent dans
  `BC.Abilities.EnvironmentAbilities`, pas dans le gameconfig — `EnvThinVeil` y est à 0 occurrence
  alors qu'il **est** au catalogue de la BC. La conclusion (absent) restait juste, la preuve non.
