---
name: tacticus-expedition
description: Envoyer les Operations (Expeditions) de Tacticus — lire le plateau, calculer l'affectation optimale, dispatcher. MUST BE USED dès que l'utilisateur parle d'expéditions / Operations à dispatcher. Encapsule un ORDRE de gestes non intuitif : armer AVANT de naviguer, sinon rien n'est envoyable.
---

# Operations (Expeditions)

**Une seule commande, et elle fait tout dans le bon ordre :**

```powershell
python scripts/python/expedition_run.py              # plan seul, RIEN n'est envoyé
python scripts/python/expedition_run.py --envoyer    # plan PUIS envoi
```

Toujours jouer la forme **sans `--envoyer` d'abord** : elle montre le plan et les motifs de
refus sans immobiliser personne. Un envoi bloque les unités pour la durée de l'opération
(10 h sur le plateau du 2026-08-11).

## Les quatre pièges, tous vécus le 2026-08-11

1. **ARMER AVANT DE NAVIGUER.** `ExpeditionGameEvents` ne se capte au vol qu'**à un envoi**,
   or il faut l'instance **pour** envoyer : la voie est circulaire. La sortie est que
   `ExpeditionProgression` la porte en champ `<GameEvents>k__BackingField`, capté par deux
   méthodes ancrées **à l'armement** et qui ne tirent qu'à l'**affichage** de l'écran.
   Naviguer puis armer laisse ces méthodes déjà tirées → `AUCUN ExpeditionGameEvents
   joignable`. **Ce n'est pas une panne, c'est un ordre inversé.** Le script l'encode ; ne
   pas rejouer les RPC à la main sans ça.

2. **Ne pas conclure « voie fermée » du pavé en tête de `expeditionDispatch`.** C'est le
   récit historique de `#600`, conservé pour ce qu'il a coûté. Le verrou réel est la
   constante `AUTORISER_ENVOI_NATIF` — **`true`** depuis que les quatre causes sont
   corrigées. Lire la constante, pas la prose.

3. **Ré-armer entre chaque envoi.** Le module détache ses portes à l'émission (il ancre la
   méthode qu'il invoque et se bloquerait sur lui-même). Sans ré-armement, le 2ᵉ envoi
   échoue.

4. **Un envoi part même si le jeu meurt ou gèle.** Ne jamais retenter à l'aveugle : lire
   `expeditionBoardRead` d'abord. Le script écarte les opérations `status != 0` **et** retire
   leurs unités du roster (champ `units` ; `dispatchedUnits` existe mais vaut `null`).

## Le porteur du dispatch — HERO/MoW seulement

Le solveur filtre par `ExpeditionUnitEligibility$$IsEligibleFor` : possession × alliance ×
**rang ≥ seuil de la rareté**. Les seuils viennent de `expeditionRankRequirements` (au
2026-08-11, niveau 16/20 : Common 0, Uncommon 3, Rare 6, Epic 9, Legendary 12, **Mythic 17**).
Une opération Mythic n'a donc souvent qu'une poignée de candidats — d'où le point suivant.

## Ce que le solveur optimise, et ce qu'il ne fait pas

Il maximise le **nombre d'opérations dont le bonus est débloqué**, puis fait partir les
autres pour leur **récompense de base** (une opération abandonnée laisse un slot vide). Son
remplissage épargne les unités **rares** — celles qui sont le dernier recours d'une
opération étroite.

⚠ **Il ne réinjecte pas le remplissage dans la recherche** : un plan peut perdre une
opération au remplissage alors qu'un autre choix d'ensembles l'aurait gardée. Ce n'est pas
optimal, c'est documenté sur place.

## Quand ça sort NON PARTANTE

Le script nomme toujours la cause. Les deux vraies :
- **bonus hors d'atteinte** → part quand même pour la base, sauf si…
- **pas assez d'unités libres éligibles** → rien à faire avant le retour des unités parties.

## Aller plus loin

- `docs/rl/case-600-gel-du-dispatch-natif.md` — les 5 tentatives, les 4 causes racines, et
  pourquoi le symptôme n'y désigne jamais la cause.
- `.claude/skills/tacticus/references/rpc-api.md` — l'inventaire des RPC `expedition*`
  (8 côté board, 6 côté dispatch, 4 côté roster).
- `scripts/python/expedition_solver.py` — le solveur, 100 % hors ligne (`solve`, `board`,
  `confronter`, `vocabulaire`), gardé par `tests/test_expedition_solver_offline.py`.
