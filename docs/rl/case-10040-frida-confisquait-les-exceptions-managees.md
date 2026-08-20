# #10040 -- Frida CONFISQUAIT les exceptions managees, donc les `try/catch` DU JEU ne jouaient plus

`NativeFunction` sans option applique le defaut Frida **`exceptions: "steal"`** : Frida pose son
propre gestionnaire autour de l'appel et confisque l'exception native. Or IL2CPP leve une
exception managee comme une exception C++ (`RaiseException`), et le derouleur doit remonter
jusqu'au `catch` managé. Volee par Frida, elle n'y arrive jamais.

Consequence, **silencieuse et generale** : sous n'importe quel `invokeMethod`, tout `try/catch`
du JEU est desarme. `il2cpp_runtime_invoke` n'ecrit alors RIEN dans son parametre de sortie
`exc`, donc `decodeManagedException` ne rend rien et les ai-traces d'exception restent VIDES --
il ne reste qu'un `Error("system error")` sans classe ni message.

Correctif : `{ exceptions: "propagate" }` sur `il2cpp_runtime_invoke`
(`frida/hooks/il2cpp/invoke.ts`). Le contrat normal d'IL2CPP est retabli -- il rattrape
lui-meme l'exception managee et la rend par `exc`.

## La mesure qui l'etablit

Meme montage, meme plateau, **traceur arme dans les deux cas** ; seul l'appelant change.

| appelant | `Ability_Power_GroupHandler$$ParseAbilityType` | START |
|---|---|---|
| `invokeMethod(HandleOnStartBattleTapped)` | ENTRE, ne SORT PAS | « system error » |
| le CLIC HUMAIN sur le meme bouton | ENTRE et SORT (+14 autres passages) | bataille demarree |

Le chemin en cause est ORDINAIRE, et c'est ce qui rendait le diagnostic contre-intuitif :
`ParseAbilityType` essaie `"Ability_Active:"` **avant** `"Ability_Passive:"` (les trois branches
se nomment par leurs litteraux, `metadata/string_literals.tsv`). Pour un passif, la premiere
branche echoue donc TOUJOURS -- `IdunMeta.Utils.Extensions.Enum$$TryParse` appelle
`System.Enum$$Parse`, qui LEVE. Le jeu traverse ca pour chaque passif, des milliers de fois par
bataille. Le `catch` qui l'avale est un funclet : **invisible au decompile**, d'ou le piege --
`TryParse` ne montre que `return 1`, jamais de `return 0`.

⚠ Ne pas relire l'absence de `return 0` comme « cette methode ne rattrape pas ». Un `bool
TryParse` compilé depuis `try { ... return true } catch { return false }` rend exactement ce
listing-la.

## Ce que le correctif debloque

Voie canonique complete, **sans aucun geste humain**
(`sandbox_boss.py --depuis-replay ... --confirmer`) :

* mise en place CONFORME -- les 7 pas valent la reference AU CARACTERE
  (`32519, 2299, 2735, 2955, 2740, AddMachineMessage=2271, StartBattleMessage=11980`) ;
* identites d'entite exactes : heros 111/113/115/117/119, MoW 120 ;
* puis `replay_rejouer.py --vivant --depuis 7` : **coups 7 a 58 mesures, 52 d'affilee a
  ecart 0**. Le coup 59 termine la bataille -- la scene tombe et le runner perd son
  `ReplayRecorder`, donc son flux est NON MESURE (ce n'est pas une divergence).

## Ce que ca coute

Avec `propagate`, un VRAI defaut natif (acces invalide) sous un invoke n'est plus converti en
erreur JS : il tombe. Confisquer etait pire -- ca cassait le rattrapage du JEU, pas seulement
le notre.

## Pistes ecartees par mesure (ne pas les rouvrir)

* **la voie de pose** -- runner-directe et etage FSM donnent le MEME echec, et les six pas
  identiques a la reference dans les deux cas ;
* **l'inflation a froid du generique** -- quatre montages successifs, quatre levees ;
* **`CorrectAbilityIdForVisualsAndIcon`** -- arithmetique pure (pour 1244 elle rend 1244) ;
  son `.cctor` n'a rien de fragile ;
* **nos propres ancrages** -- le traceur etait arme PENDANT le clic humain qui passe ;
* **la MoW absente** -- START passe, mais `StartBattleMessage` vaut 11897 au lieu de 11980 :
  l'ecart, c'est elle.
