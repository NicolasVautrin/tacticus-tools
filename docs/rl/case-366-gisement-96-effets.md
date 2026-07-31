# case-366 -- les 96 `EffectType` que #358 rendait invisibles : inventaire TRANCHE

**Question, en deux temps.** (1) Quels sont, nommement, les `EffectType` que l'inventaire corrige
de #382 fait apparaitre ? (2) Parmi eux, lesquels sont VIVANTS et NON PORTES -- lesquels changent
quelque chose si on les porte ?

**Ce document ne porte rien.** Il TRANCHE. Chaque ligne dit : porte deja / inerte demontre / a
porter (avec porteur et voie). Les ports partent en taches filles, une par ability.

Probe : `scripts/python/probe_366_inventaire_effets_forme_b.py`. Garde :
`scripts/python/tests/test_366_effects_registry_closed_offline.py`.

## 1. La cecite, MESUREE (et non racontee)

`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` enregistre **607** fabriques. Les
enregistrements se repartissent en DEUX formes d'appel, selon la maniere dont la cle (l'`EffectType`)
atteint `Dictionary<,>$$Add` :

| forme | comment la cle est passee | nombre |
|---|---|---|
| A | `mov edx, <EffectType>` -- immediat en registre | **511** |
| B | `lea rdx, [rsp+d]` + `mov dword ptr [rsp+d], <EffectType>` -- **par adresse** | **96** |

Le dictionnaire est gshared a cle `ValueType` : IL2CPP passe donc la cle par reference, et le
litteral est en PILE. Rien n'est cache -- il est simplement ailleurs.

**Pourquoi #358 rendait 511.** Ses deux balayages cherchaient l'octet-cle `4c 8b c6` (`mov r8, rsi`,
le chargement du delegate en 3e argument) SUIVI de `BA` (`mov edx, imm32`). Mesure, reproduite a
l'octet pres par `legacy_blind_scan` :

```
occurrences de l'octet-cle partage `mov r8, rsi` : 607
retenues (suivies de `mov edx, imm32`)           : 511
rejetees sur le SECOND octet                     : 96
```

Le motif **voyait les 607 sites** et en rejetait 96 sur le second octet. L'accord `511 == 511` de
ses deux balayages etait un accord sur CE rejet. C'est la forme canonique du faux negatif :
**deux sources qui partagent leur cecite s'accordent parfaitement**.

Verification de non-regression, faite par le probe : `legacy == forme A` (exactement), et
`legacy` est **strictement inclus** dans le recensement complet.

## 2. Un nom de ctor N'EST PAS un nom de classe (piege rencontre en route)

Premiere tentative de typage des 96 : lire, dans chaque fabrique `<>c$$<InitializeEffects>b__14_N`,
le `$$.ctor` appele. Elle rend des absurdites -- `5 Fire` -> `FireEffect$$.ctor` (juste), mais
`9 Shrub_BonusDefense` -> `RitesOfBattleExtraDmgImperialEffect$$.ctor` (faux).

Mesure qui le tranche, sur les **607** fabriques :

| grandeur | valeur |
|---|---|
| fabriques profilees | 607 |
| slots `Il2CppClass*` distincts (identite REELLE) | **440** |
| noms de `$$.ctor` distincts | 365 |
| noms de ctor couvrant PLUSIEURS classes | **51** |

Champion : `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_ResetInitialDmgEffect$$.ctor`
porte **13** classes distinctes. C'est la regle CLAUDE.md « l'absence d'une methode dans les tables
ne prouve RIEN » vue par l'autre bout : IL2CPP **deduplique les corps de ctor triviaux**, et la
table de symboles n'en nomme qu'un proprietaire.

**L'identite fiable est le slot `Il2CppClass*`** charge dans `rcx` avant `il2cpp_object_new` : deux
lambdas qui construisent la meme classe chargent le meme slot, deux classes distinctes ne peuvent
pas le partager. Le probe rend le slot ; il ne rend un nom que quand celui-ci est non ambigu.

## 3. L'inventaire tranche

(section remplie a l'etape suivante)
