# #473 — Le volet LIVE d'un cliquet DIT qu'il n'a pas pu mesurer, au lieu de rougir

Application du tri-état de **#471** à **une** entrée, `probe_467r4`, parce que son gisement a mordu
trois fois dans la journée du 2026-08-04. Le tri-état se pose entrée par entrée, jamais en bloc.

## 1. Le défaut, et sa mesure

`probe_467r4_contrat_host.py` rougissait sur son **volet [B]** (« forme RÉELLE de la réponse du
host ») quand **un runner se construisait en parallèle**. Mesure rapportée par l'agent de la PR
#588 :

> Une passe de banque a rendu `probe_467r4` ROUGE sur son volet [B]. Cause : j'avais un runner en
> construction EN PARALLÈLE de la banque — le host n'a pas répondu dans le budget du volet. Rejoué
> seul : `VERDICT: PASS`, rc=0.

Troisième flake du jour, et **cause distincte** de celle fermée le matin même (`fd761e5b` : la
propagation comparait deux lectures d'un compteur volatil, rendue déterministe par rejeu sur
capture). Le volet [B] lit une source **vivante** — c'est son objet — donc il ne peut pas, lui,
être rejoué sur capture sans perdre ce qu'il garde.

**Le chemin exact, tranché par le code et non supposé.** La boucle de capture retourne proprement
dès qu'une route manque (`PASS PARTIEL`) : le seul chemin restant vers un ROUGE était la
**relecture** `LS.mesurer_harnais(src)`, qui refait deux appels HTTP après la capture, pour un
budget client de **3 s** (`Sources.http_json` : `min(timeout, 5.0)`).

**Deux causes, mesurées, et la seconde interdit de réduire le défaut au pump** :

- **(a)** `router.get("/api/admin/drain")` attend `rpcCall(sid, "listRunners", [], 5000)` **sur le
  pump Frida**, qu'un build de runner concurrent occupe : le host peut mettre jusqu'à 5 s. C'est
  le cas rapporté par la PR #588 ;
- **(b)** le host lui-même **sature**. La première passe de banque jouée *après* ce correctif, à
  parallélisme 16, a rendu `relecture du host : /api/admin/status : timed out` — or ce handler ne
  touche **pas** le pump (`findTacticusCandidates` + `activeMetaVersion`). Élargir le budget pour
  absorber les 5 s du `rpcCall` n'aurait donc rien fermé.

**La parade rapportée — « ne pas monter de runner pendant la banque » — n'est pas codée.** Elle est
inapplicable par construction : la campagne fait tourner jusqu'à 5 agents libres de builder, et
`ratchets-bg` tourne en fond précisément pour ne pas les bloquer. Une convention que personne ne
peut respecter est un rouge déterministe déguisé en discipline.

## 2. Le partage — énoncé AVANT le code, et c'est lui qui porte tout

Le critère est celui de #471 : « un dépôt **PARFAIT**, à cet instant, sur cette machine, aurait-il
produit ce même échec ? » **OUI** → `INDISPONIBLE` (rc 99, bloquant) · **NON** → `ROUGE`.

| ce qui est jugé | classe | pourquoi |
|---|---|---|
| la **joignabilité** du host, appel par appel | VOLATIL | chaque `http_json` est un tirage indépendant : la capture peut passer et la relecture lâcher |
| les **valeurs** rendues : `session` null, `tacticus.running`, `drain.enabled`, `liveRunners` entier ou null + sa raison | VOLATIL | le volet juge la FORME, jamais la valeur — `liveRunners: null` avec sa raison est **conforme** |
| présence et type des clés dans une réponse **obtenue et bien formée** | CONTRACTUEL | structurelles côté host : `router.ts` rend toujours l'objet `tacticus` et `session\|null`, `enabled` vient de l'interface `DrainState`. Aucun état de plateforme ne peut les faire disparaître — seul un changement de code le peut |
| `mesurer_harnais` MESURE (pas `_ko`) sur une réponse **obtenue** | CONTRACTUEL | une réponse qui arrive et dont il ne tire rien accuse le lecteur |
| `mesurer_harnais` propage exactement la charge utile donnée | CONTRACTUEL | jugé par rejeu depuis `fd761e5b`, déterministe |
| `mesurer_harnais` n'interroge **que** les routes du contrat dérivé | CONTRACTUEL | une route lue mais non dérivée rendrait le volet [A] aveugle dessus |

**La borne à ne pas laisser glisser**, la même qu'en #471 : une réponse qui **arrive bien formée**
mais à laquelle il manque un champ contractuel est un **fait sur le code** → ROUGE. Seule une panne
de **transport** — un appel qui ne rend *aucune* réponse — est INDISPONIBLE. Sans cette borne, un
host lent suffirait à ce que le cliquet cesse de garder quoi que ce soit.

### Les deux régimes d'impossibilité ne se confondent pas

- la **capture** échoue (host éteint, une route muette) → le volet **ne s'OUVRE pas**. Il ne prétend
  aucun jugement : `NON MESURE` + `PASS PARTIEL`, **rc 0**. Régime assumé depuis l'origine — le host
  est éteint la moitié du temps, un 99 bloquerait la banque une passe sur deux, et un garde-fou qui
  rougit partout se fait désactiver ;
- le volet s'est **OUVERT** et ne peut plus **CONCLURE** → il ne peut ni dire PASS (il n'a pas tout
  jugé) ni FAIL (le dépôt n'est pas en cause) : **INDISPONIBLE, rc 99**.

## 3. Ce qui a été livré — `scripts/python/probe_467r4_contrat_host.py`, et lui seul

`scripts/ratchets.ps1` **n'est pas touché** : l'infrastructure de verdict de #471 suffisait
(`ratchets-verdict.ps1`, dot-sourcée, `99` → `INDISPO`, bloquant).

- **`_Tracee`** — relaie `http_json` vers la vraie `Sources` en notant les routes **vues** et les
  pannes de **transport**. Rien d'autre ne peut ventiler : `mesurer_harnais` attrape `Exception` et
  rend le **même** `_ko` pour un appel muet et pour une réponse inexploitable. Lire son message
  pour deviner laquelle serait **#467-r6 à l'envers** (trois pannes de `gh` derrière un `rc=127`).
- **`juger_forme` / `juger_relecture`** extraits — fonctions éprouvables sans aucun host.
- **`EX_INDISPONIBLE = 99`**, rendu par `main`. Convention **non inventée** : celle de
  `scripts/ratchets-verdict.ps1`. Le **ROUGE prime**, et un indisponible reste **nommé** sous un
  rouge — sinon corriger le rouge verdirait une épreuve jamais jugée.
- **Épreuve neuve, déterministe même sous panne** : `mesurer_harnais` n'interroge que les routes du
  contrat **dérivé**. Les routes sont vues *avant* que le transport ne lâche, et les deux appels
  sont dans des `try` indépendants. C'est ce que la relecture live est désormais seule à voir, et
  ce qui justifie de la garder malgré son exposition.
- **La relecture live passe EN DERNIER** : ce qui reste jugé quand elle lâche est maximal — **11
  épreuves sur 12**, mesuré sur l'incident réel du §7.
- **Une garde nommée à la place d'un `KeyError`** : `etape_b` juge nommément deux routes alors que
  le contrat est **dérivé**. Si la dérivation en perdait une, le déballage levait un traceback en
  `rc=1`, donc un **ROUGE anonyme** — la forme même que #471 combat. Le verdict reste ROUGE (une
  dérivation qui perd une route est un fait sur le dépôt), mais il porte désormais son nom.
  **Trouvé par la contre-épreuve adversariale, pas par un incident.**

## 4. La contre-épreuve — les deux faces, en bout en bout

Un chemin qui ne peut pas rendre les deux ne vaut rien (#439). Deux étages :

**[B'] auto-épreuve intégrée**, rejouée à chaque passage, **100 % déterministe** (aucun host
interrogé) — fabriquer une réponse est légitime ici (on éprouve le **juge**, comme [A'] mute une
**copie** du host) et proscrit dans le volet [B], qui ne juge que ce que le host a réellement rendu.

| face | montage | attendu |
|---|---|---|
| témoin sain | réponse CONFORME | aucune épreuve ne tombe |
| CONTRACTUEL | `session`, `tacticus`, `enabled`, `liveRunnersError` retirés | ROUGE à chaque fois (1, 1, 1, **2** épreuves tombées) |
| VOLATIL | transport qui lâche après 1 appel | INDISPONIBLE, et l'épreuve de MESURE **n'est pas jugée** |
| témoin de cette face | transport sain | l'épreuve de MESURE est jugée, et VERTE |
| **la borne** | réponse OBTENUE mais inexploitable (`[]`) | **ROUGE**, aucune indisponibilité |
| l'épreuve des routes n'est pas décorative | contrat **amputé**, lecteur intact | ROUGE « une route INTERROGÉE hors du contrat dérivé » |

La dernière ligne ampute le **contrat**, pas le lecteur, et c'est structurel : muter
`mesurer_harnais` casse `contrat_lu` en amont (il en lit le **source**), donc n'isole rien —
mesuré, la mutation naïve fait rougir 7 épreuves du volet [A] et n'atteint jamais celle qu'elle
prétendait éprouver.

**Bout en bout**, le rc **réel du process**, un process par scénario (les seaux sont des globales),
host allumé, `liveRunners = 0` :

| scénario | montage | rc | ce qui prouve que la mutation a MORDU |
|---|---|---|---|
| `sain` | rien de substitué | **0** | `VERDICT: PASS`, 12 épreuves du volet [B] vertes |
| `lache` | transport muet **après** la capture | **99** | les 11 autres épreuves restent **jugées et vertes** ; seule la relecture bascule `INDISP` |
| `eteint` | transport muet **dès** le 1er appel | **0** | `PASS PARTIEL` — le volet ne s'ouvre pas (régime inchangé) |
| `ampute` | `.session` → `.sessions` sur une réponse qui **arrive** | **2** | 2 `ROUGE` sur le piège nommé, **et la relecture reste verte** |
| `les_deux` | amputé **et** muet ensuite | **2** | le ROUGE prime, **et** l'indisponible reste nommé au verdict |
| `route_non_derivee` | la dérivation du contrat perd `/api/admin/drain` | **5** | `ROUGE le contrat DERIVE porte les routes que le volet B juge (manque /api/admin/drain)` — **et aucun `Traceback`** (avant : `KeyError`, rc 1) |

`ampute` et `les_deux` prouvent que la borne ne glisse pas : une violation de contrat rend toujours
ROUGE, **y compris quand une indisponibilité coexiste**.

Le témoin `sain` n'est pas décoratif : sans lui, un probe qui rendrait 99 en toutes circonstances
passerait la face volatile.

## 5. Ce qui n'est PAS fait

- **Les 14 entrées de la banque qui confondent encore** (résidu `#471-r1`) restent telles quelles.
  Le total est **inchangé** et ce n'est pas un hasard : `probe_467r4` en sort, `probe_471` y entre
  (il a été ajouté à la banque par #471 et a un gisement direct). Le compte se **re-dérive** de
  `probe_471` étape 4, il ne se cite pas.
- **La cause du timeout n'est pas corrigée**, seulement classée — c'est le sujet même de #471 :
  le tri-état vaut quelle que soit la cause. Élargir le budget de `Sources` pour absorber les 5 s
  du `rpcCall` serait une parade sur un symptôme, et masquerait la prochaine saturation.
- **`scripts/ratchets.ps1` n'est pas amendé** : son commentaire d'entrée décrit le régime « host
  éteint », qui reste exact, mais ne mentionne pas le 99. Écarté à dessein — une autre tranche
  (#468) éditait ce fichier au même moment, et le bloc `INDISPONIBLE` imprimé par la banque nomme
  déjà la cause en clair. **Résidu `#473-r1`**.
- **Aucun rejeu automatique** : la conduite (rejouer *cette* entrée seule, et le **dire** dans la PR
  si elle passe) est imprimée dans le verdict, pas exécutée en silence. Un rejeu qui passe ne
  prouve rien.

## 6. Relevé de validation (2026-08-04)

| épreuve | résultat |
|---|---|
| `probe_467r4` seul, host allumé | `VERDICT: PASS`, rc 0 — 12 épreuves du volet [B], 11 de [B'] |
| contre-épreuve bout en bout, 5 scénarios | rc **0 / 99 / 0 / 2 / 2**, conformes |
| `probe_471` | `VERDICT: PASS` — inventaire : `probe_467r4` passe de « gisement par module importé » à **« PORTENT le tri-état »** (8 → 9), trace mécanique que le tri-état est branché |
| `probe_439` | `VERDICT: PASS` — l'entrée reste capable de rougir |
| `probe_440` | `VERDICT: PASS` — périmètre et écritures inchangés |
| banque complète | cf. §7 |

## 7. Relevé de banque

Joué après rebase sur `origin/master`. La composition de la banque est **définie** par
`scripts/ratchets.ps1` ; cette case-doc **atteste** ce qui a été joué, elle ne définit rien.

```
[ratchets] BANQUE VERTE -- 41 cliquet(s), mur 693,2 s.
```

`probe_467r4` : **12,8 s**, rc 0. ⚠ Chiffres à re-dériver, pas à citer.
