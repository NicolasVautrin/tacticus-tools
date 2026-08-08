# #594 — Les littéraux au site d'appel : il n'y a pas d'arbre, il y a **une fonction**

**Mesure du 2026-08-08, build `rnca9r7q6c`.** Reproductible :
`python scripts/python/probe_594_ctor_litteraux.py`.

## Le gisement

`TARGETING_OPTIONS` et `ABILITY_ATTACK_TYPE` sont les deux données **obligatoires** du
registre `ABILITY_CLASSES`. Ce sont aussi les deux où l'on a **mesuré** des ports faux :
le masque recopié d'un preset statique au lieu du littéral visible, et trois abilities
entrées au registre sans leur `AbilityAttackType` — découvertes seulement au re-jeu après
rebase d'un autre agent, invisibles dans les deux PR qui avaient creusé le trou.

Même forme dans les deux cas : **un littéral au site d'appel que rien n'extrait**. Aujourd'hui
il se lit à l'œil, dans du décompilé chargé en entier pour deux constantes.

## Le résultat : une seule arête

```
IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(
    targetingOptions : IdunBattle.Core.Services.TargetingOptions,
    abilityAttackType: IdunBattle.Entities.Abilities.AbilityAttackType)
```

**135 des 139** `.ctor` d'ability l'appellent, **tous avec exactement 3 arguments**. Les deux
données convergent sur les **arguments 2 et 3 d'un seul site**. Un extracteur n'a donc pas à
parcourir un graphe d'appels : il lit une liste d'arguments.

Ventilation au premier saut : **84** appellent `TargetingOptions$$.ctor` directement · **2**
passent par une **fabrique statique nommée** (`$$SelfCastIfEnemyInCustomRangeOptions`,
`$$CustomLokiNormalAttackOptions` — une forme que la doctrine ne nommait pas) · **53** ne
touchent aucun symbole `TargetingOptions`, et construisent ailleurs avant de passer à la base.

**145/145** adresses `FUN_` se résolvent contre `data/symbols/<build>/ghidra/functions.tsv`
(100 %) — la résolution offline n'est pas un maillon faible.

## Deux hypothèses réfutées **en cours de mesure**, toutes deux les miennes

1. « la forme preset est l'exception » — **faux** : 53/139 (38 %) ne touchent pas
   `TargetingOptions` au premier saut.
2. « ces 53 recopient un preset statique, et l'adresse `DAT_` porte le masque » — **réfuté** :
   `DAT_1833ffc10` est partagé par **50** d'entre eux et porte **12 masques différents**. Une
   adresse unique ne peut pas être 12 masques.

C'est la raison d'être de ce document : le raisonnement « il faut couvrir tous les arbres
d'appel » était **la mauvaise question**, et deux hypothèses plausibles sur la forme preset
sont mortes à la mesure. Les re-dériver coûte ~9 min de ghidra plus la mise au point.

## Le canal, qui n'est pas un défaut du MCP

`pyghidra-mcp` (1.27.2) fait le travail : 139 fonctions en 18 appels, **0 échec**, le lot est
natif. Ce qui coûte, c'est que l'outil d'agent rend son texte **dans le contexte** —
**197 784 caractères** pour extraire deux constantes par ability. D'où
`scripts/python/mcp_ghidra.py` : même serveur, JSON-RPC direct, sortie **sur disque**.

La vraie limite de l'outil reste entière : `decompile_function` n'a **ni `offset` ni `limit`**,
donc le coût est déjà payé quand la sortie arrive.

## L'oracle est gratuit, et le score parfait serait suspect

Les **139 masques déjà portés** valident l'extracteur sans une seule confrontation live :
ni fenêtre de reinject, ni runner. Critère énoncé **avant** de mesurer : l'extracteur doit
rendre exactement le masque porté pour chacun. **139/139 doit alarmer**, pas rassurer — un
score parfait signalerait presque sûrement un repli qui devine au lieu de refuser.

Trois verdicts, jamais un repli : **RÉSOLU** · **FABRIQUE** (statique nommée) · **NON RÉSOLU**.
Un outil qui couvre 85 % et refuse le reste est utilisable ; un qui devine sur les 15 % écrit
des masques faux — exactement la panne qu'il répare.

## Ce que la mesure ne voit pas

Quatre abilities sont hors du chemin : `SwoopingHawkAbility` et `Repair_GalvanicFieldAbility`
(corps de ~245 caractères, trop courts pour construire quoi que ce soit) ;
`FrenziedFiringAbilityCombat` et `SlashingDiveAbility` **sans `.ctor` dans la table**. Pour ces
deux dernières, le garde du dépôt s'applique : **l'absence d'un symbole ne prouve rien** —
IL2CPP déduplique les corps triviaux, un corps partagé n'a qu'un propriétaire dans la table.

Et la mesure porte sur le `.ctor` : elle ne conclut rien sur un site qui construirait le
masque ailleurs.
