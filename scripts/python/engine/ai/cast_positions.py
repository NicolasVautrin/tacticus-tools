"""#350-r3a-r4 -- FOYER UNIQUE : les positions d'ou une paire (ability, cible) est castable.

MIRROR de `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`, qui appelle
`IdunBattle.Core.Services.AttackQuery$$GetValidTargets(caster, UnitPosition(P), ability)`
**UNE FOIS PAR POSITION candidate, sans plafond**.

POURQUOI CE MODULE EXISTE -- et pourquoi le residu designait le MAUVAIS AXE.
`#350-r3a-r4` recensait << 6 sites lisent encore `ranked` >>. Mesure du 2026-08-08 : ce n'est pas
le SITE qui decide, c'est la **SOURCE du plan**. Les memes six sites servent DEUX faces :

  * face DECISION -- `plans = {p["unitId"]: p for p in dv["attackPlans"]}`
    (`engine/ai/context.py`), donc `computeAttackPlans` (`frida/hooks/features/ai-step/
    projection.ts`), qui TRONQUE : `for (let r = 0; r < maxRank; r++)`. Ce plafond n'existe
    nulle part cote natif. A `maxRank = 6` (defaut du RPC `decisionView`), **21 positions sur 33**
    disparaissent du plan -- assez pour DEPLACER un argmax (`case-350r3-oracle-noncomparable.md` §9) ;
  * face COMBAT -- `engine/ai/state_bridge.py::_plans_for_unit`, qui enumere **toutes** les tuiles
    candidates dans la portee : `ranked` y est COMPLET, et aucun de ces six sites n'y est expose.

Reparer par site aurait donc multiplie par six la surface **sans fermer le gisement** : un
septieme lecteur de `ranked` serait ne expose. Le foyer, lui, tient les deux faces par le meme
critere, et il est TRI-ETAT :

  `ev["rankComplete"] is True`  -> `ranked` EST l'ensemble complet. Zero RPC. (Face COMBAT, et
                                  face DECISION des que le harnais publiera le drapeau.)
  `ev["rankComplete"] is False` -> le plan DIT qu'il a tronque -> `castFromTiles`.
  drapeau ABSENT               -> **PAS MESURE**, jamais rabattu sur `True` : le harnais courant
                                  ne le publie pas encore, et supposer << complet >> serait
                                  exactement la degradation permissive que la tranche ferme.
                                  -> `castFromTiles`.

`castFromTiles` = `AttackQuery$$GetInvalidTargetReason` evalue TUILE PAR TUILE : **le meme
predicat que `GetBestTileToAttackFrom`, sans le plafond**. Ecart de predicat mesure contre
l'eligibilite native : **0 position sur 33, a tous les rangs** (`case-350r3` §9).

CE QUE CE FOYER NE PEUT PAS REPARER : les champs de DEGAT (`dmgMin`, `dmgMax`, `kill`,
`predOptimistic`) ne vivent QUE dans `ranked` -- `castFromTiles` ne les porte pas. Les deux
lecteurs de degat par tuile (`noncomparable/hammer_of_wrath.py::_enemy_killed_by_normal_attack`,
`noncomparable/holy_duel.py`) restent donc exposes au plafond, et seul le harnais peut les
servir. Voir `docs/rl/case-350r3a-r4-troncature-du-plan.md` §5.
"""
from __future__ import annotations

#: Cle publiee par la source du plan : `True` = `ranked` est l'ensemble COMPLET des positions
#: valides ; `False` = la source a plafonne ; ABSENTE = pas mesure (cf. tri-etat ci-dessus).
RANK_COMPLETE = "rankComplete"

#: Compteur de diagnostic, par regime. Sert aux probes et aux tests a montrer QUELLE branche a
#: ete prise -- un fix dont on ne peut pas prouver qu'il s'exerce ne prouve rien.
COMPTEURS: dict = {"complet": 0, "tronque": 0, "non-mesure": 0, "repli": 0}


def ranked_positions(ev: dict) -> set:
    """Les positions portees par `ev["ranked"]`, telles quelles -- la vue TRONQUEE."""
    return {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
            if rk.get("col") is not None}


def positions_castables(ev: dict, cast_from_tiles, caster_id: int, target_id, ability_id,
                        origin: tuple | None = None) -> set:
    """Les positions d'ou `(ability_id, target_id)` est castable par `caster_id` -- SANS troncature.

    `cast_from_tiles` : le callable `(uid, target_id, ability_id) -> {currentValid, moveTiles}`
    (`AiDecisionContext.cast_from_tiles`), ou `None` quand la seam n'existe pas (chemin purement
    offline). `origin` : la position courante du caster, ajoutee si `currentValid`.

    REPLI NOMME, jamais silencieux -- seam absente, RPC en erreur, ou ensemble VIDE alors que
    `ranked` est non vide (incoherence) -> on rend `ranked`. Rendre `set()` dans ces cas ferait
    DISPARAITRE la cible, ce qui est pire que la troncature."""
    ranked = ranked_positions(ev)
    complet = ev.get(RANK_COMPLETE)
    if complet is True:
        COMPTEURS["complet"] += 1
        return ranked
    COMPTEURS["tronque" if complet is False else "non-mesure"] += 1
    if not callable(cast_from_tiles) or target_id is None:
        COMPTEURS["repli"] += 1
        return ranked
    try:
        cf = cast_from_tiles(int(caster_id), int(target_id), int(ability_id)) or {}
    except Exception:                                   # noqa: BLE001 (seam live faillible)
        COMPTEURS["repli"] += 1
        return ranked
    out = {(t.get("col"), t.get("row")) for t in (cf.get("moveTiles") or [])
           if t.get("col") is not None}
    if cf.get("currentValid") and origin is not None:
        out.add(origin)
    if not out:
        COMPTEURS["repli"] += 1
        return ranked
    return out


def plan_est_complet(plan: dict) -> bool | None:
    """`True` / `False` / `None` (= pas mesure) pour un plan d'unite entier.

    `True` seulement si TOUS ses evals le declarent : un seul eval tronque suffit a deplacer un
    argmax, donc l'agregat ne peut pas etre plus optimiste que son membre le plus faible."""
    evals = plan.get("evals") or []
    if not evals:
        return None
    vals = [ev.get(RANK_COMPLETE) for ev in evals]
    if all(v is True for v in vals):
        return True
    if any(v is False for v in vals):
        return False
    return None
