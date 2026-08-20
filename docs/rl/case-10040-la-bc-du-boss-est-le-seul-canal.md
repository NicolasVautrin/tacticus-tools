# #10040 — La BC est le SEUL canal du boss de guilde : un diff total vaut controle complet

**Question** : avant de rejouer un replay sur un boss de guilde, comment savoir qu'il correspond
a l'etat courant ? L'etat des LIEUTENANTS influence les stats du boss, les adds et ses abilities
— et il ne se lit PAS sur le replay.

**Reponse, etablie au decompile** : il n'a pas besoin de s'y lire. Tout passe par la BC.

## La chaine

`GuildBossGameModeSource$$LoadBattleInternal` ne fait qu'un appel utile :

    BattleConfigBuilder$$GetGuildBossBattleConfig(builder, config, encounterIndex,
                                                  environmentAbilities, ...)

`config` est la `GuildBossConfiguration` que `guildBossConfig` lit deja. Offsets releves :

| offset | champ |
|---|---|
| `+0x10` | `BoardId` |
| `+0x18` | `BossUnitId` |
| `+0x20` / `+0x28` | `EggUnitId` / `DragonlingUnitId` |
| `+0x30` | `SpawnPointSetIndex` |
| `+0x38` / `+0x3c` | `BossHealth` / `RemainingBossHealth` |
| `+0x40` | `MaxRoundAmount` |
| `+0x48` | **`BossModifiers`** |
| `+0x50` | `Enemies` |
| `+0x60` | `DisallowedFactions` (deja documente sur `GetDeployableUnitsPooled`) |

Les trois canaux, et ou ils atterrissent :

* **stats** du boss et des adds — les `unitId` collectes (`+0x18`, `+0x20`, `+0x28`, `+0x50`)
  passent a `GetLevelConfigWithRealUnits` -> `BC.Units` ;
* **adds** — meme origine, PLUS `AProgressionGameModeSource$$ApplyEnvironmentAbilitiesFromProgression`
  puis `EnvironmentAbilities$$AddExtraEnemyUnits` : la progression peut AJOUTER des ennemis ;
* **abilities** — si `BossModifiers` est non vide, un `ModifierBuilder` est construit dessus,
  puis les DEUX dictionnaires de `BC.Abilities` (actives, passives) sont balayes et chaque
  entree REECRITE par `ModifierBuilder$$TryApplyModifierToAbility`, reposee par
  `AbilitiesConfiguration$$Add`. Les modificateurs sont CUITS dans la BC, pas poses a cote.

⇒ **Aucun canal ne contourne la BC.** `LoadBattleInternal` rend cet objet, et c'est lui que la
bataille consomme.

## Ce que ca autorise

Un **diff TOTAL** de BC (forgee vivante contre celle du replay) couvre les trois axes PAR
CONSTRUCTION — donc aussi les mecanismes qu'on ne connait pas. Un controle par champs CHOISIS ne
pourrait pas voir le canal qu'on n'a pas prevu.

Mesure du 2026-08-20, Belisarius : **33 des 34 cles de haut niveau identiques au caractere**
(559 668 octets). Seul ecart : `BossUnit.RemainingHealth`, `11 395 258` vivant contre
`13 486 215` au replay. Stats, adds, abilities, carte, tuiles, poids d'IA : identiques.

Cable en cran 0 de `scripts/python/bataille_reference.py`, avant l'armement du seed. Cout :
zero — `LoadBattleInternal` construit et rend la BC ; l'enregistrement de la tentative est une
methode SEPAREE, jamais appelee.

## Ce qui reste NON ETABLI

**Ce qui fait VARIER `BossModifiers`.** Ca vient du serveur, et toutes les observations
disponibles sont en etat SATURE : les deux lieutenants (`encounterIndex` 1 et 2) sont a `0` PV
dans chacune. Les trois captures Lion le confirment par l'autre bout — 6 modificateurs, jeu
identique, alors que les PV varient de 1,9 M entre elles. Il faudrait une observation avec un
lieutenant VIVANT (debut de saison).

Sans consequence pour le garde : quelle que soit la regle, son effet passe par la BC.

## Au passage

* les LIEUTENANTS sont des encounters (`guildBossConfig {encounterIndex}`), avec leur propre
  carte (`GB_Belisarius_support_03/_06`) et leurs propres PV. Ne pas supposer l'index 0 ;
* le vivant porte un suffixe de rang (`:22`) que `BC.Id` n'a pas — comparer la forme nue ;
* `npc1UnitId`/`npc2UnitId` sont dans l'ORDRE INVERSE de `PredefinedUnits` : comparer les
  ennemis en ENSEMBLE, jamais par position ;
* `belisarius-10040` est une capture **Sandbox** (`MetaData.Mode`), et sa BC est identique a la
  BC forgee par la vraie source guild-boss. Le montage sandbox ne produit donc pas une
  approximation : il produit la MEME BC.
