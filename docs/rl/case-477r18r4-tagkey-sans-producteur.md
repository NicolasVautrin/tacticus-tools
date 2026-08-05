# #477-r18-r4 — les `TagKey` que le flux ÉMET et que le balayage n'ATTEIGNAIT pas

**Résolu.** Build `rnca9r7q6c`, ghidra-mcp sur le binaire installé, session Frida **10**.
**QUATRE** causes DISTINCTES, aucune commune — c'est pour ça que le trou avait résisté.

⚠ **Le résidu annonçait 9 ; un troisième flux témoin à ROSTER CHOISI en a montré 14.** Deux
batailles tirées par défaut ne castent qu'une poignée d'abilities : le corpus de la contre-épreuve
ne vaut que ce que la bataille EXERCE. C'est ce troisième témoin — et lui seul — qui a fait sortir
`UnitStats_RemovedNegativeUnitEffects` (émis par un `Action=RepairInfo`), `Custom_Tile_Id` et les
trois `UnitStats_Attack_Override*`. Le volet live prend donc désormais `--p-units` / `--a-units`.

```powershell
python scripts/python/probe_477r18_deroule_perimetre.py --json 477r18-carte.json
python scripts/python/probe_477r18_deroule_perimetre.py --flux-live --board C1_02 --tours 2
python scripts/python/probe_477r18_deroule_perimetre.py --flux-live --board C1_74 --tours 3 `
  --p-units "necroSpyder,orksBigMek,necroOverlord,admecDominus,ultraApothecary" `
  --a-units "bloodMephiston,tyranParasite,templAncient,eldarFarseer,spaceStormcaller"
python -m pytest scripts/python/tests/test_477r18r4_canaux_tags_offline.py -q   # garde hors ligne
```

## 1. Le sens de la marche : du FLUX vers le binaire

Chaque tag a d'abord été localisé dans le flux témoin (`Action=` porteuse + chemin de groupes),
puis remonté à son opération. Les trois familles ne se ressemblent que par le symptôme.

| tag | où le flux le porte | qui l'ÉCRIT | canal |
|---|---|---|---|
| `Attack_Weapon_IsMelee`, `_DamageProfile` | `Action=Info` dans `Ability_Power` | `IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon` | 4 |
| `Custom_Data`, `Custom_Tile_Id` | `Action=Info` dans `Ability_Power` | argument du nœud `IdunBattleLogic.Entities.DSLBehaviors$$Inform` | 3 |
| les six `UnitStats_{FixedArmor,Movement}_Modification[_Change|_Entity]` et les trois `UnitStats_Attack_Override*` | `Action=ChangeStats` dans `Effect_Refresh` | `IdunBattle.Operations.TransformUnitOperation$$.cctor` | 5 |
| `UnitStats_RemovedNegativeUnitEffects` | `Action=RepairInfo` dans `Ability_Power` | `IdunBattle.Operations.RepairUnitOperation$$Execute` | (forme d'écriture) |

## 2. Quatre causes

**(a) ÉCRIRE un tag et ÉMETTRE dans le flux sont deux gestes distincts.**
`DSLBehaviors$$InformWeapon(damageProfileType, isMelee, useSpecial)` écrit `0x93`, `0x92` et,
sous condition, `0x94` dans un `Dictionary<TagKey,int>` — et n'appelle **jamais**
`IStreamListener`. C'est un nœud DSL : son dictionnaire part vers
`IdunBattle.Operations.InformOperation$$Execute`, qui l'émet en `StepType.Info`. Le canal 1
(xrefs du `Il2CppClass*` de l'interface) ne pouvait pas le voir, par construction.
⇒ **canal 4** — les xrefs du `MethodInfo*` de `Dictionary<TagKey,int>.Add`, strictement
symétrique du canal 1 sur l'axe des tags.
⚠ Le nom `DSLBehaviors$$InformWeapon` porte **deux surcharges** : interrogé par nom,
`decompile_function` rend un corps VIDE (piège 1 de la fiche parente).

**(b) Un tag peut être un ARGUMENT de nœud DSL**, comme un `GroupType` l'est pour
`DSLBehaviors$$AtomicGroup`. Témoin lu :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StandVigil_UpdateEffectRangeAbility$$CreateBehaviour`
passe `(void *)0xcc` = `Custom_Data` à `DSLBehaviors$$Inform`.
⇒ **canal 3 étendu à `TagKey`** — mais **FILTRÉ**, parce que ce vocabulaire-là est aussi LU par
la vue : un porteur ne compte que s'il émet (canal 1) ou écrit (canal 4). Le filtre ne peut que
SOUS-compter, et ce qu'il écarte est **imprimé**.

**(c) Un tag peut n'exister QUE dans une table statique.** Les six `_Modification*` sont des
CHAMPS de `IdunBattle.Operations.TransformUnitOperation.ModStatTransformConfig`. Son `.ctor` est
un ctor de **value type** : le compilateur l'INLINE, il a **0 appelant nommé**, donc le canal 3
n'a rien à lire ; et il n'écrit aucun dictionnaire, donc le canal 4 non plus. Les littéraux
vivent dans `IdunBattle.Operations.TransformUnitOperation$$.cctor`, en stores 64 bits qui
**empaquettent deux champs** — `local_198 = 0x2b0000002a` = champ 0 `UnitStats_FixedArmor`
(`0x2a`), champ 1 `..._Modification` (`0x2b`).
⇒ **canal 5** — lecture slot par slot de la struct passée en **3ᵉ argument** du `Dictionary.Add`
de la table. Ce qui rend la lecture exacte et non heuristique : le NOM Ghidra d'une locale porte
son offset de pile, donc les `n_clés × 4` octets de clés occupent les `ceil(n_clés/2)` slots
suivants, de 8 en 8 — et la variable passée en **clé** de la table (un `StatType`, pas un
`TagKey`) est hors de cette plage.

La chaîne complète, lue : `TransformUnitOperation$$Execute` → `AddModificationTags` →
`AddTagIfImplemented(config+4 / +8 / +0xc)`, `config` venant de la table du `.cctor`.
Le **`0` est exclu** : `TransformUnitOperation$$AddTagIfImplemented` commence par `if (key != 0)`
— un champ nul n'écrit aucun tag, c'est la sentinelle « non implémenté ».
⚠ Une clé sur les 62 n'est écrite ni nue ni empaquetée mais par `CONCAT44(<var>,0x29)` : sans
cette forme, `UnitStats_Attack_Override_IsModifiable` restait perdu.

**(d) Le NOM d'une variable Ghidra change selon la LARGEUR de l'écriture.** Quand la variable est
plus large que la valeur — typiquement un PARAMÈTRE réutilisé — Ghidra écrit une **affectation de
champ** : `removeEffects._0_4_ = 7;` dans `IdunBattle.Operations.RepairUnitOperation$$Execute`. Le
nom capté était alors `_0_4_`, qui ne pouvait plus s'apparier à la clé `&removeEffects` de l'`Add`
— le tag sortait « sans producteur » alors que le producteur était **déjà balayé**.
⇒ les deux côtés de l'appariement passent par `racine_variable`, qui normalise `&x`, `x[0]` et
`x._0_<n>_`. **Seul l'offset 0** est normalisé : `cfg._4_4_` est un AUTRE champ, et le confondre
ferait lire une clé FAUSSE — pire qu'une clé manquante.

## 2bis. La contre-épreuve, chiffrée des deux côtés

Même cache de décompilation, même corpus de **trois** flux témoins (`C1_02` 2 777 lignes,
`MC1_67` 2 931, `C1_74` roster choisi 3 181), qui émettent ensemble 19 `GroupType`, 27 `StepType`,
**90** `TagKey` :

| | `TagKey` atteint | étape [8] émis-non-atteints | `GroupType` / `StepType` |
|---|---:|---|---|
| avant (`778c2ea5`) | **131 / 244** | **14** | 0 / 0 |
| après | **203 / 244** | **0** | 0 / 0 |

Attribution des 14, telle que la carte brute la porte : **2** par le canal 4
(`DSLBehaviors$$InformWeapon`), **2** par le canal 3 étendu (`DSLBehaviors$$Inform`), **9** par le
canal 5 (`TransformUnitOperation$$.cctor`), **1** par la forme d'affectation de champ
(`RepairUnitOperation$$Execute`). Couverture par étage : **132** (canal 1 + fabriques, forme de
champ comprise) → **139** (canal 4, +7 exclusifs) → **149** (canal 3, +10) → **203** (canal 5,
+54). « Sans producteur lu » : **113 → 41**.

⚠ **Le canal 4 ne fabrique pas de couverture** : sur les 90 tags émis, **0** n'est couvert par un
seul lecteur de vue ou de test — chacun a au moins un producteur côté moteur. Et le canal 5
s'auto-contrôle : ses **62** valeurs lues sont **62/62** dans l'enum `TagKey`, alors qu'un parseur
qui déraperait produirait des entiers arbitraires.

## 3. Ce qui reste NON LU, et pourquoi ce n'est pas un silence

Le probe imprime, à chaque run, les **18** porteurs écartés par le filtre du canal 3 et les
porteurs sans littéral lisible. Trois positions restent ouvertes **côté émetteur** et sont
**nommées** en sortie : `IdunBattleLogic.Entities.DSLBehaviors$$InformList` et
`IdunBattle.Entities.Behaviours.InformListBehaviour$$.ctor` / `$$GetTagKey` — le filtre les
écarte parce qu'eux-mêmes n'émettent ni n'écrivent (c'est `InformListBehaviour$$Execute` qui
écrit). Le filtre ne peut donc que **SOUS-compter** ; aucun tag du corpus témoin n'en dépend
(`Custom_Tile_Id_2..10` sont dans les 41 sans producteur, `Custom_Tile_Id` est couvert par le
canal 3 via `ExecutionerAbility$$ExecuteBehaviour`). Condition de retournement : qu'un
`Custom_Tile_Id_<n>` apparaisse comme émis-non-atteint à l'étape [8] — élargir alors le critère au
niveau de la CLASSE (une classe qui contient un émetteur ou un écrivain), au prix d'une fuite côté
vue (`StreamMessages`).

⚠ **Le corpus témoin est le vrai plafond de la contre-épreuve.** Un troisième flux a fait passer
le trou de 9 à 14 ; un quatrième en montrerait peut-être d'autres. C'est la limite structurelle du
contrôle, pas une lacune du balayage : l'étape [8] ne peut confronter que ce qu'une bataille a
réellement émis. Restent **41** `TagKey` sans aucun producteur lu (contre 113 avant) : comme les
18 `GroupType` de la fiche parente, des **candidats** dead code — **pas** une preuve de mort.

## 4. Le garde

`scripts/python/tests/test_477r18r4_canaux_tags_offline.py` garde les deux **parseurs** hors
ligne, sur des extraits VERBATIM du build — le probe, lui, exige ghidra-mcp allumé et un flux
live, donc son étape [8] mesure sans cliqueter. Chaque étage assertionne son propre **non-vide** :
un parseur cassé rend un ensemble VIDE, qui se lit « rien à signaler ». Discrimination vérifiée
par **six** mutations (CONCAT44 ignoré ; zéro non exclu ; slots non reconnus ; `Dictionary.Add`
non reconnu ; suffixe de champ non capté ; **tout** champ ramené à la racine) — chacune rougit les
étages attendus, et le vert revient à la restauration. La sixième est la seule qui garde contre
une clé **FAUSSE** plutôt que manquante : elle est vérifiée sur la VALEUR lue, pas sur le non-vide.
