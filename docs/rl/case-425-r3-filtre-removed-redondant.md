# #425-r3 — le filtre `removed` de `readEffectsByTile` est REDONDANT, et son jumeau ne l'est pas

**Build** `rnca9r7q6c`, session Frida **8**. Question binaire du résidu `#425-r2`, tranchée.
Probes : `probe_425r3_removed_writers.py` (décompilé/binaire), `probe_425r3_removed_witness.py` (live).

## Verdict

**Le natif retire TOUJOURS l'id de la liste possédée avant de marquer l'effet `Removed`.**
Le filtre `if (info && info.removed) continue;` de `readEffectsByTile` / `readEffectsByUnit`
ne peut donc **rien perdre** : la condition est **inatteignable** pour un id issu
d'`EffectsOwnedComponent.ActiveEffectIds`. `#425-r2` est **fermé — aucune divergence, même
théorique**. Aucun changement de comportement livré, donc **aucune fenêtre de reinject requise**.

**Et la tranche a trouvé l'inverse à côté** : le troisième filtre `removed` du même fichier,
dans `readRoundCapClock`, est **LOAD-BEARING**. Le retirer « par cohérence » serait une
régression. C'est le vrai gain de la tranche (§4).

## 1. L'ordre des deux écritures, lu au décompilé

`IdunBattle.Operations.RemoveEffectOperation$$Execute`, dans cet ordre :

1. deux gardes d'idempotence — `if (Removed) return;` puis `if (BeingRemoved) return;` ;
2. `BeingRemoved = 1` ;
3. si `IsActive` → revert de la modification (slot du processeur d'opérations) ;
4. `RemoveFromParent` — retrait de la liste `SubEffects` (+0x78) de l'effet parent ;
5. **si** l'entité `OwnerId` porte un `EffectsOwnedComponent` **et** que sa liste est non nulle :
   - **`List.Remove(ActiveEffectIds, <id de l'effet>)`** ← le retrait,
   - `RemoveSubEffects`, puis les événements,
   - `IsActive = 0`,
   - **`Removed = 1`** ← l'écriture du flag, **APRÈS** le retrait, **dans le même bloc**.

⇒ Au moment où `Removed` vaut 1, l'id a **déjà** quitté la liste. Il n'existe aucun chemin qui
pose `Removed` sans avoir traversé le `List.Remove` : les deux instructions sont dans le même
`if`, dans cet ordre.

Le cas où `List.Remove` **échoue** (id absent) ne rouvre rien : la valeur de retour est ignorée,
mais l'id n'est alors pas dans la liste non plus. L'implication tient dans les deux branches.

Layout confirmé (`EffectComponent`) : `IsActive`@0x5C · `HasTurns`@0x5D · `BeingRemoved`@0x5E ·
`Removed`@0x5F — cohérent avec les offsets que `frida/hooks/game/effects.ts` résout par nom.

## 2. L'appariement ajout ↔ retrait est EXACT

Le retrait porte sur l'entité désignée par `EffectComponent.OwnerId` (+0x14). Encore faut-il
qu'aucune **autre** entité ne détienne l'id. `IdunBattle.Operations.AddEffectOperation$$AddNewEffect`
écrit `OwnerId` = `owner`, puis fait `List.Add` sur l'`EffectsOwnedComponent` **de cette même
entité `owner`** — même variable, quelques instructions plus bas. Ajout et retrait visent donc
la même liste.

Les autres manipulateurs **délèguent tous** à ce foyer, et n'écrivent ni `Removed` ni la liste :
`RemoveEffectsOperation$$Execute`, `AddEffectOperation$$RemoveExistingEffect`,
`ChangeUnitOwnerOperation$$RemoveEffects` **itèrent** `ActiveEffectIds`, accumulent les
candidats dans une **liste temporaire**, puis appellent le slot du processeur d'opérations.
Leur `List.Add` porte sur la temporaire — pas sur `ActiveEffectIds`.

Périmètre **borné structurellement** par les xrefs du token de classe `EffectsOwnedComponent`
(pas par une recherche de noms) : 21 fonctions le manipulent, dont 7 mutateurs, tous ci-dessus.

## 3. EXHAUSTIVITÉ — pourquoi un scan binaire, et ce qu'il rend

Une absence ne prouve rien, et deux outils l'ont confirmé **pendant** cette tranche :

- `frida/methods.tsv` ne porte **aucune** méthode `EffectComponent$$…` (corps triviaux
  dédupliqués) — l'absence n'y autorise aucune conclusion ;
- l'index littéral de `mcp__ghidra__search_code` est **NON EXHAUSTIF** : la chaîne
  `RemoveEffectOperation__RemoveSubEffects` rend **1** fonction alors que **2** la contiennent
  (`$$Execute` l'appelle). Ses zéros ne sont donc pas des mesures. **Mesuré ici, pas supposé.**

D'où `probe_425r3_removed_writers.py` : scan des **octets** des sections de code du build,
motifs d'écriture d'un octet à `+0x5f` (`C6 /0 disp8 imm8` et `88 /r disp8`, avec/sans REX, cas SIB),
puis résolution de chaque adresse en symbole propriétaire.

| | |
|---|---:|
| code scanné | **44 601 644 o** (`.text` + `il2cpp`) |
| sites d'écriture d'un octet à +0x5f | **40** |
| fonctions distinctes | **21** |
| **écrivant `Removed` d'un `EffectComponent`** | **1** — `IdunBattle.Operations.RemoveEffectOperation$$Execute` (`imm=0x01`) |

Les 20 autres sont hors domaine (Newtonsoft, System.Data, System.Xml, UnityEngine,
Mono.Security…) et **aucune** n'apparaît dans les xrefs du token `EffectComponent`. Les quatre
du domaine jeu écrivent depuis un **registre** dans une copie de struct ; la plus proche par le
nom, `IdunBattle.Entities.Effects.Loki.DawnBladeEffect$$GetLocalizationDataInternal`, a été
décompilée : elle ne touche **aucun** `EffectComponent` — son écriture appartient au memcpy
inline du paramètre `entities`.

⚠ **Le scan a d'abord rendu un zéro rassurant, et la cause mérite d'être écrite** : sa première
version filtrait les sections par une **liste blanche de noms** (`{".text"}`). Or le code IL2CPP
ne vit pas dans `.text` (2,8 Mo) mais dans une section nommée **`il2cpp`** (41,8 Mo) — 93 % du
code hors périmètre, et `RemoveEffectOperation$$Execute` avec. Le critère est désormais **dérivé**
des `Characteristics` (`CNT_CODE`/`MEM_EXECUTE`).

**Borne de validité, dite par le probe lui-même** : déplacement sur 32 bits, écriture via un
pointeur déjà avancé, `memset`/`Copy` en bloc — non couverts.

## 4. Le TROISIÈME filtre `removed` est LOAD-BEARING

Le même champ est filtré à trois endroits de `frida/hooks/game/effects.ts`. Deux sont
redondants ; **`readRoundCapClock` ne l'est pas**, et la différence est structurelle :

| lecteur | ce qu'il itère | filtre `removed` |
|---|---|---|
| `readEffectsByUnit` | `ActiveEffectIds` du porteur | **redondant** — inatteignable |
| `readEffectsByTile` | `ActiveEffectIds` de la tuile | **redondant** — inatteignable |
| `readRoundCapClock` | **toutes les entités** (`forEachEntity`) | **NÉCESSAIRE** |

`RemoveEffectOperation$$Execute` retire l'id de la liste **mais ne détruit pas l'entité**.
Un `EnvEndBombardment` retiré reste donc visible d'un balayage d'entités : sans ce filtre,
l'horloge de bombardement lirait un compte à rebours périmé.

Ce point est la raison d'être de la note posée dans le code : « le filtre `removed` est
redondant » est vrai **de deux sites sur trois**, et un lecteur pressé qui généraliserait
casserait le troisième.

## 5. Témoin live — `probe_425r3_removed_witness.py`

`MC1_67`, seed 777, `ultraTitus,orksNob` vs `tauCrisis,tauShadowsun`, 5 relevés.

| | |
|---|---:|
| états DISTINCTS mesurés | **5** |
| **T1** — effets PUBLIÉS portant `removed: true` | **0** (sur les 5) |
| **T3** — ids ayant QUITTÉ une liste possédée | **6** |
| entités Effect orphelines par relevé | 10 → 16 |

Les 6 retraits (`Overwatch_AutoAttack`, `SuppressCloseCombatWeakness`,
`EarlyWarningOverride_ReactivateOverwatch`, `BeastSlayer_ExtraDmg`/`_ExtraBlock`) sont sortis
d'une liste possédée **en restant des entités VIVANTES** — le chemin `RemoveEffectOperation` a
donc bien été exercé, et il se comporte exactement comme le décompilé le dit.

⚠ **T1 est un témoin FAIBLE et le probe le dit** : le filtre jette en amont de la publication,
donc `0` est attendu même si l'invariant était faux. Il ne peut que **réfuter**. C'est **T3**
qui porte l'information.

⚠ **Anti-confond, ajouté après une première passe fausse** : la version initiale a relevé
**quatre fois le même instant** (24 entités / 14 publiés / 10 orphelins à l'identique) et
s'apprêtait à le rendre comme « stable sur 4 tours » — parce qu'elle appelait un RPC `aiTurn`
**qui n'existe pas** (la voie est la CLI `rl_duel.py aiturn`) et que l'échec passait pour un
succès. Le discriminant retenu est la **signature d'état**, pas le numéro de tour : `aiturn`
clôt le tour d'une ÉQUIPE, et `decisionView.turn` reste à 3 pendant que l'état bouge
réellement (24 → 28 → 30 entités). Compter par `turn` aurait rejeté des relevés distincts.

## 6. Ce qui n'est PAS couvert

- **Le régime de mort d'unité** (`KillUnitOperation$$RemoveEffects`, `FleeOperation`,
  `DestroyMachineOperation`) n'a pas été exercé : aucune unité n'est morte sur les 5 relevés.
  Ces chemins délèguent au même foyer (§2, lu au décompilé), mais ce n'est pas *mesuré* en live.
- **La valeur de `Removed` n'est jamais lue directement en live** : aucun RPC ne publie ce champ
  (`readEffectAbilityStateRaw` dumpe la fenêtre +0x18..+0x40, `Removed` est à +0x5f). Les
  orphelins du §5 sont donc une **borne supérieure** des `Removed`, pas leur compte exact — un
  orphelin peut aussi être un effet dont l'owner n'est ni tuile ni unité (`BlockEnteringUnits`,
  `Thorns_DefenseReduction` en portent la marque). *Pour lever ce point* : publier `removed`
  dans `effectAbilityStates` — capteur à écrire, donc **fenêtre de reinject**.
- Les trois formes d'écriture hors portée du scan (§3).

## Résidus

Aucun résidu ouvert par cette tranche. `#425-r2` est **fermé** ; `#425-r1` (le gate `IsActive`,
gisement mesuré **vide** sur `MC1_67`) reste ouvert et **inchangé** — il porte sur `IsActive`,
pas sur `Removed`, et le présent verdict ne le concerne pas.

## Reproduction

    python scripts/python/probe_425r3_removed_writers.py --tous
    python scripts/python/probe_425r3_removed_witness.py --tours 4
