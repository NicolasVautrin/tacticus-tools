# #1064 — Qualifier la charge utile d'une fenetre de reinject AVANT de l'ouvrir

Une fenetre suspend tous les agents en vol : elle se paie cher et une seule fois. `BLOCAGE: capteur`
se lit « attend une fenetre », mais ce champ n'est **jamais re-mesure** apres son ecriture. Mesure du
2026-08-14 sur les **19** residus qui le portaient : **4** exigent vraiment du code neuf, **15** non,
et **4** de ces 15 etaient deja **RESOLUS** dans leur propre enonce.

## 1. La grille — trois issues, dont une souvent VIDE

Pour chaque residu, deriver l'IDENTIFIANT dont il affirme l'absence (champ RPC, cle de stream, nom de
hook, option), puis le compter des DEUX cotes :

- **(a)** absent du bundle, present dans l'arbre -> vrai item de fenetre ;
- **(b)** absent des deux -> **le capteur n'est pas ECRIT** ; aucune fenetre n'y peut rien ;
- **(c)** present dans le bundle -> le canal est en vol, le residu accuse le mauvais etage.

**(a) est VIDE des que bundle == arbre**, et c'est le cas le plus frequent. L'etablir :

```powershell
# 1. Le bundle en vol EST-IL celui du disque ?
(Get-Item C:\...\frida\dist\hooks.js).LastWriteTimeUtc      # 2026-08-14T03:06:21Z
Invoke-RestMethod http://127.0.0.1:8765/api/sessions | Where-Object status -ne stopped
#   -> startedAt 2026-08-14T03:06:36Z  ==> ecrit 14,8 s AVANT le demarrage : OUI
# 2. Les SOURCES ont-elles bouge depuis ?
git log -1 --format=%cI -- frida/hooks/ ; git status --short -- frida/hooks/
```

> **PIEGE MESURE, et il coute 2 h de faux diagnostic** : `startedAt` est en **UTC** (suffixe `Z`),
> `LastWriteTime` de PowerShell est en **LOCAL** (CEST = UTC+2 en aout). Comparer les deux bruts fait
> croire a 2 h d'ecart et conclure « le bundle en vol est un ANCIEN ». Comparer en `LastWriteTimeUtc`.
> Autre piege du meme genre : `bundleBytes` rendu par l'inject est une **longueur de chaine JS**, pas
> une taille fichier (l'ecart = octets de continuation UTF-8 des accents).

## 2. Le controle qui rend la mesure exploitable : le bundler ne tree-shake pas

Un fichier source qu'aucun import ne tire n'entrerait PAS dans le bundle — ce serait un (a) reel.
Controle **derive**, pas suppose : extraire les `ctx.rpc.<nom> =` des sources et chercher `rpc.<nom>`
dans le bundle. Mesure : **252 RPC declares, 252 presents, 0 absent**. Tant que ce controle est vert,
« present dans l'arbre » implique « present dans le bundle ».

⚠ **Le bundle STRIPPE les commentaires.** Un compte `bundle=0 / arbre=N` ne veut donc pas dire
« absent » mais **« present uniquement en PROSE »** — donc aucun code executable. Mesure temoin :
`DSLSelectors` = 0 dans le bundle pour 8 occurrences dans l'arbre, **toutes** en commentaire.

## 3. Ce que la mesure a trouve, et qu'aucun grep de backlog n'aurait vu

**`classFields(ns, cls)` — RPC en vol de longue date — NOMME les slots que quatre residus
declaraient « illisibles offline, capteur requis ».** Il rend le layout d'une classe avec le **nom de
CHAMP**, ce qui est strictement plus fort que le nom de classe cherche : c'est le nom que le jeu
donne au slot, et c'est l'ancrage qui survit a un renumerotage.

```
IdunBattleLogic.Entities.DSLTriggers   (13 champs)     IdunBattleLogic.Entities.DSLSelectors (18)
  +0x40 True        +0x58 HasOwnersActiveAbilityBeenUsed   +0x30 Owner    +0x60 Target
  +0x48 False       +0x60 No                               +0x38 Effect   +0x68 ActiveTarget
  +0x50 IsOwnerEmpty +0x68 Never   +0x70 Yes               +0x40 Actor    +0x88 CurrentAbility
                                                           +0x48 Caster   +0x90 TriggeringAbility
```

Trois verdicts tombent d'un seul appel, en **lecture pure** (aucun runner, aucun `arm`) :

- **`#1008-r3`** — `<DSLTriggers+0x58>` = **`HasOwnersActiveAbilityBeenUsed`**. La fiche hesitait
  entre `YesTrigger` et le gate ; c'est le **gate**. Le conjoint omis par le port est donc un vrai
  bug, avec l'effet exact qu'elle predisait.
- **`#905-r1`** — `<DSLTriggers+0x60>` = **`No`**, voisin de `Never` (meme classe, cf. la ventilation
  des `Il2CppClass*` de la fiche) et distinct de `False` = `op_LogicalNot(True)`. Le risque nomme
  (« et si `+0x60` etait CONDITIONNEL ? ») est **LEVE** : le port de `1228` est confirme.
- **`#590-r11`** — les 14 selecteurs partages sont tous nommes. **Cinq** identifications
  STRUCTURELLES du port sont confirmees nominalement (`+0x30 Owner`, `+0x38 Effect`, `+0x40 Actor`,
  `+0x48 Caster`, `+0x60 Target`) et **une est FAUSSE** : le port ecrit `+0x68 It`, le champ
  s'appelle **`ActiveTarget`**.

**Lecon generale** : la question « quel est le NOM de cet objet ? » a deux formulations, et une seule
etait tentee. « Nommer la CLASSE de l'instance » exige un capteur ; « nommer le CHAMP qui la porte »
etait deja servi. Avant de commander un capteur, chercher la **question voisine** que l'outillage
repond deja.

## 4. Le second gisement : une premisse qui n'a jamais ete mesuree

**`#961-r3`** affirmait « `1475` n'est publie **ni actif ni inactif** ». Or le `decisionView` du
probe (`probe_961_necron_passives.py::dv`) **ne passe pas `includeInactive`**, et ce drapeau vaut
FAUX par defaut — le canal filtre les inactifs. La phrase decrit donc un canal qui n'a jamais ete
interroge. `includeInactive` est en vol (14 occurrences executables, **68** probes Python l'utilisent
deja). Le residu se tranche en rejouant le probe avec le drapeau, sans fenetre.

⚠ Corollaire : **un residu qui affirme une absence doit citer l'appel exact qui l'a mesuree.**
« X n'est pas publie » sans le corps de la requete est une hypothese.

## 5. Resultat, et ce qu'une fenetre livrerait vraiment

| Issue | Compte | Residus |
|---|---|---|
| **(a)** vrai item de fenetre | **0** | — (categorie provablement vide : bundle == arbre) |
| **(b)** capteur A ECRIRE | **4** | `#1009-r3` `#1036-r8` `#982-r6` `#969-r4` |
| **(c)** canal deja en vol | **15** | dont **4 CADUCS** (`#959-r1` `#916-r1` `#905-r1` `#590-r5`) |

**Precedent confirme** : sur une qualification anterieure, 4 items annonces, 1 reel. Ici 19 annonces,
**0** reel — la fenetre, telle quelle, n'aurait **rien** livre. Les 4 capteurs (b) doivent d'abord
etre **ECRITS**, puis une seule fenetre groupee les active. Leur specification tient dans le backlog.

⚠ **Ne PAS lire ce tableau comme un etat courant** : il vaut pour le bundle du 2026-08-14T03:06:21Z.
Re-jouer la grille du §1 apres chaque reinject.

### Les 4 capteurs a ECRIRE — c'est ca, la charge utile d'une fenetre

| Residu | Ce qu'il faut ecrire | Ou | Patron deja ecrit |
|---|---|---|---|
| `#1036-r8` | `UnitConfiguration+0xc0` (`TertiaryAbilityLevel`) par unite, TRI-ETAT (`null`, jamais `0`) | `features/ai-step/rpc-snapshot.ts` | `readRarity` (#1039), meme voie `GetBaseUnitComponent` |
| `#982-r6` | un drapeau `forceInit` sur `resolveVtableSlot` | `features/introspect.ts` | `probes/static-field-probe.ts` (~5 lignes a porter) |
| `#1009-r3` | tagger `ret`/`args` par `readMsgClass` dans `ctorOnLeave` | `features/dsl-ctor-trace.ts` | le gate du meme fichier le fait deja sur `this` |
| `#969-r4` | `CurrentOwnerIsEnvironment` par unite, TRI-ETAT | `features/ai-step/rpc-snapshot.ts` | `currentOwnerIsEnvMi` est **deja resolu** dans `internals.ts` |

Les quatre sont **petits** et **sans RE restante**. Les ecrire d'abord, puis **une seule** fenetre
groupee. Ecrire le code AVANT d'ouvrir la fenetre est ce qui rend la fenetre rentable — l'ouvrir
sur les 19 residus tels qu'ils etaient libelles aurait livre **zero**.

### Les 4 lignes RETIREES du backlog, et pourquoi

Une ligne se retire quand le probleme est **ferme**, pas quand il est mal classe. Les quatre :

- **`#959-r1`** — son propre corps portait `RESOLU (#982)` : capteur `triggeredMoveTrace` deja
  charge, face DECISION portee **et** confrontee (38 lignes bit-exactes, 13 non nulles,
  discriminante). Rien ne restait.
- **`#916-r1`** — `NOMME ET REFUTE (#982)` : le slot 5 est
  `IEffect.get_AlwaysCreateOneEntityPerEffect`, LU dans `metadata/interface_slots.tsv`, et il
  n'encode PAS `stacks_stat_mod_on_add`. Son unique reliquat (recensement partiel) est `#982-r6`,
  **qui existe** — verifie.
- **`#905-r1`** — `<DSLTriggers+0x60>` = **`No`** (§3). Le risque nomme par la fiche (« et s'il
  etait CONDITIONNEL ? ») est leve, le port de `1228` confirme.
- **`#590-r5`** — `TRANCHE OFFLINE (#982)`, la ligne le disait elle-meme : `BaseUtility$$.cctor`
  ecrit `statics+0x20 = Fix64.MinValue`, la constante de rejet est eliminatoire.

⚠ **Symetrie a garder** : `#966-r2` portait aussi un « RESOLU », mais renvoyait le travail restant
a `#982-r5` — qui n'a **jamais** ete ouvert (une seule mention dans tout le backlog : la sienne).
Elle est donc **conservee** et corrigee. Un renvoi n'est pas une fermeture : verifier que la cible
existe avant de retirer une ligne.

## 6. Angle mort connu

La prose des modules `frida/hooks/**` se perime **exactement comme le champ `BLOCAGE:`**. Deux
en-tetes lus le 2026-08-14 annoncent « INERTE tant que le bundle n'est pas rebuilde + reinjecte »
(`probes/valid-targets-from.ts`) ou « les deux capteurs de ce lot qui exigent VRAIMENT une fenetre »
(`controller.ts`) alors que le reinject a eu lieu. Ces phrases ne sont pas fausses a l'ecriture ;
elles le deviennent **sans que rien ne bouge**. Un lecteur qui les prend pour une mesure re-demande
une fenetre deja consommee.
