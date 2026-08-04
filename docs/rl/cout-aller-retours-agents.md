# Cout des aller-retours des solveurs, et ce qu'une delegation economiserait

Mesure du 2026-08-04 sur les **326 PR moteur** (`scripts/python/engine/`) portees par un
`opus-solver`, depuis le 2026-07-26. Outil : `scripts/python/agent_roundtrips.py`
(`--map` lit 659 Mo de transcripts UNE fois et persiste une carte de 2,5 Mo ; `--report`
ne lit que la carte). Chiffres a **re-deriver**, pas a citer.

## Un enregistrement JSONL n'est PAS un aller-retour

Claude Code ecrit les blocs `thinking` / `text` / `tool_use` d'une **meme reponse** dans des
enregistrements **separes** qui **recopient le meme `usage`**. Mesure sur 6 transcripts :
**1 408 enregistrements pour 765 requetes** (1,84x), `ctx` **identique** sur les continuations.

⇒ La cle est **`requestId`**, jamais `uuid` ni le compte de lignes. Compter les
enregistrements gonfle les aller-retours de **1,72x** (92 653 -> 53 706) et le contexte de
**1,64x** (29,0 G -> 17,7 G). **`repo_board.py` compte encore par enregistrement** : sa
colonne `context` et son `tours` portent ce facteur (residu ouvert).

## La carte

53 706 aller-retours, **165 par agent**, **330 k tokens de prompt par aller-retour**, dont
**98 % de cache_read**. Le **socle** (prompt du 1er tour relu a chaque fois) = **19 %**.

| signature | tours | carry | ce que c'est |
|---|---|---|---|
| `PowerShell` | **43 %** | 14 % | executer : pytest, git, probes |
| `Edit` | 19 % | 5 % | appliquer une edition deja decidee |
| `Read` | 12 % | **25 %** | le plus gros REMPLISSEUR de contexte |
| `Grep` | 8 % | 7 % | |
| `decompile_function` | 4 % | 10 % | lourd par appel |

`carry` = decomposition **exacte** de `L = somme(ctx_k) = N*ctx_1 + somme delta_k*(N-k+1)` :
chaque ajout est refacture autant de fois qu'il reste d'aller-retours derriere lui.

**Deux gisements distincts** : les **boucles** (PowerShell/Edit = 62 % des tours, peu de
contexte chacune mais un prompt plein a chaque fois) et les **remplisseurs**
(Read+Grep+decompile = **42 % du contexte porte**).

Recurrence : **2 638 series** de >= 3 `PowerShell` consecutifs (la plus longue : **272**),
1 356 series de `Edit`. **33 % des aller-retours** sont dans une boucle mecanique.

## Le gain ne vient PAS du modele moins cher

Simulation : chaque serie >= 3 d'une signature mecanique remplacee par UN tour delegue, le
sous-agent chiffre au cout **mesure** d'un `Explore` de ce depot (95 507 tokens/requete).

| | cout | gain |
|---|---|---|
| aujourd'hui, tout en Opus | 32 736 $ | — |
| **sous-agent Opus** (temoin : isolement SEUL) | 21 381 $ | **-35 %** |
| sous-agent Sonnet | 18 333 $ | -44 % |
| sous-agent Haiku | 17 825 $ | -46 % |

⇒ **L'isolement du contexte apporte 35 points, Opus->Sonnet en ajoute 9, Sonnet->Haiku 1,6.**
Le prix du modele est un effet de **second ordre** : le gain est de sortir la boucle du
prefixe Opus, qui la relit a 330 k tokens par tour. **Sonnet sature le gain de prix.**
(Prix LISTE, indicatifs, hors forfait — seul le RANG compte.)

## Ce qui fragilise le chiffre

- **Sensible au seuil de serie** : >= 3 donne -46 %, >= 5 -> **-32 %**, >= 10 -> **-13 %**.
  Le gain vit dans les boucles **courtes** (3-4 tours), les plus couteuses a deleguer
  proprement : 4 003 blocs = 4 003 delegations, ~12 par agent.
- **Deleguer les `Edit` est douteux** : ecrire le code EST le travail de RE. Boucles de
  commandes seules (sans `Edit`) : **-33 %** avec Sonnet, 24 % des aller-retours retires.
- Hypothese explicite : le sous-agent rend **1 500 tokens** de resume et prend le **meme
  nombre** de tours. A 5 000 tokens de resume : -41 % au lieu de -46 %.

## Etat des lieux

**La delegation est aujourd'hui inexistante : 21 appels `Agent` sur 53 706 aller-retours
(0,04 %), 19 solveurs sur 326.** Le levier est entier, il n'est pas entame.
