"""Lecture des CIBLES ELIGIBLES d'un playbook NonComparable -- foyer partage (#967).

`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` rend, POUR UNE POSITION DE
CASTER, la liste des contextes d'execution (`AbilityEntities`) des cibles legales ; le champ `+0x10`
de chaque element EST la cible, et c'est lui que `GetEligibleTargetsSelectable` -> `GenerateAction`
reemet. Cote offline la vue equivalente est `abilityTargets(uid, ability).fromHere` -- la liste
`GetValidTargets(unit, position COURANTE, ability)`, dans l'ORDRE EXACT du selecteur natif (cf.
l'encadre de `_base.eligible_target_tiles`).

Ce module ne fait qu'UNE chose : traduire cette reponse RPC en une liste ORDONNEE. L'ordre est
load-bearing -- `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
ne remplace que sur `>` STRICT, donc a utilite egale c'est la PREMIERE cible enumeree qui gagne.
D'ou le retour en `list` (jamais un `set` : le hachage deciderait de l'argmax -- le second cran
trouve par #957).

ECART NOMME, commun a tous les appelants : `fromHere` n'enumere que depuis l'ORIGINE, la ou le
natif balaie aussi les tuiles de MOVE. Pour les SIX porteurs de #967 l'ecart est INERTE : ce sont
tous des MACHINES OF WAR, entites SANS `PositionComponent` (`observeBattle` : `pos = null` by
design), donc leur unique « position candidate » est la position nulle.
"""
from __future__ import annotations


def _ability_entry(ctx, ability_id: int) -> dict | None:
    """L'entree `abilityTargets(uid, ability_id)` du CASTER pour CETTE ability, ou `None`.

    `None` distingue « pas mesure » (RPC absent, unite/ability absente de la reponse) de
    « mesure et vide » -- l'appelant doit pouvoir les separer (tri-etat, meme regle que
    `host_inputs`)."""
    if ctx.ability_targets is None:
        return None
    at = ctx.ability_targets(ctx.uid, ability_id) or {}
    for u in (at.get("units") or []):
        if u.get("unitId") != ctx.uid:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") == ability_id:
                return a
    return None


def eligible_units(ctx, ability_id: int) -> list[tuple]:
    """Cibles UNITE eligibles depuis l'origine -> `[(targetId, (col, row) | None), ...]`, ORDRE NATIF.

    La position est celle publiee par `abilityTargets` (`pos`/`tile`) ou, a defaut, celle de la
    meme unite dans `ctx.units` -- le meme repli que `ThriceBlessedConflagrationPlaybook`."""
    a = _ability_entry(ctx, ability_id)
    if a is None:
        return []
    pos_by_id = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                 for u in (ctx.units or []) if u.get("id") is not None and u.get("pos")}
    out: list[tuple] = []
    seen: set = set()
    for t in (a.get("fromHere") or []):
        if t.get("kind") != "unit":
            continue
        tid = t.get("targetId")
        if tid is None or tid in seen:
            continue
        seen.add(tid)
        src = t.get("pos") or t.get("tile") or {}
        p = ((src.get("col"), src.get("row")) if src.get("col") is not None
             else pos_by_id.get(tid))
        out.append((tid, p if (p and p[0] is not None) else None))
    return out


def eligible_any(ctx, ability_id: int) -> list[tuple]:
    """Cibles eligibles depuis l'origine, SANS presumer du domaine ->
    `[(targetId, (col, row) | None, kind), ...]`, ORDRE NATIF.

    Necessaire quand le corps natif ne tranche pas : `MalleusRocketLauncherPlaybook` appelle
    `UnitExtensions.GetUnit(entities.Target, state)` et teste `!= null`, donc il ACCEPTE une cible
    sans occupant -- le domaine se lit dans la reponse, il ne se devine pas."""
    a = _ability_entry(ctx, ability_id)
    if a is None:
        return []
    pos_by_id = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                 for u in (ctx.units or []) if u.get("id") is not None and u.get("pos")}
    out: list[tuple] = []
    seen: set = set()
    for t in (a.get("fromHere") or []):
        kind = t.get("kind")
        tid = t.get("targetId")
        src = t.get("tile") or t.get("pos") or {}
        p = ((src.get("col"), src.get("row")) if src.get("col") is not None
             else pos_by_id.get(tid))
        p = p if (p and p[0] is not None) else None
        key = (tid, p, kind)
        if key in seen:
            continue
        seen.add(key)
        if tid is None and p is not None:
            tid = (ctx.tile_id_by_pos or {}).get(p)
        out.append((tid, p, kind))
    return out


def eligible_units_at_position(ctx, ability_id: int, P: tuple,
                               self_cast: bool = False) -> list[tuple]:
    """`GetEligibleTargetsSelectable(caster, P)` POUR UNE POSITION BALAYEE, domaine UNITE, masque
    `TargetIsEnemy` + `TargetingRange` ADJACENT -> `[(targetId, (col, row)), ...]`, ORDRE NATIF.

    Le pendant de `eligible_units` pour les playbooks qui SWEEPENT les positions du caster (#977 :
    `1131 JakhalStimms`, `1141 OverwhelmingWrath`, `1043 ThunderousAssault`). L'ecart nomme en tete
    de module -- « `fromHere` n'enumere que depuis l'ORIGINE » -- n'est PAS inerte pour eux : leurs
    porteurs sont des unites a `PositionComponent`, donc elles bougent.

    DEUX vues du RPC, et elles ne sont pas interchangeables (meme encadre que
    `_base.eligible_target_tiles`) :
      * `P == ctx.origin` -> `fromHere` = `GetValidTargets(unit, position COURANTE, ability)`, donc
        l'ordre EXACT du selecteur natif a cette position ;
      * `P != ctx.origin` -> aucune vue par-position n'existe cote RPC : on prend l'UNION
        (`targets`) et on la RESSERRE par l'adjacence a `P`. L'ENSEMBLE est alors exact -- la portee
        de ces trois abilities est le ring 1, entierement decidable geometriquement -- seul l'ORDRE
        est une APPROXIMATION. Ce residu n'est atteignable que si une tuile de MOVE EGALE l'utilite
        de l'origine, le natif balayant l'origine EN PREMIER et ne remplacant que sur amelioration
        STRICTE (`Bucket$$AddAction`).

    `self_cast` (mirror de `isSelfCasting = 1`, le cas de `1141`) : le caster n'est garde que s'il
    reste AU MOINS UNE autre cible -- la branche `else` de
    `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`
    (`0x800 AddCasterIfAtLeastOneTarget`). Sa POSITION dans la liste est celle que le RPC lui donne,
    jamais une place inventee ; s'il n'y figure pas, ce volet est INERTE.

    RPC absent -> `[]`, jamais une liste devinee : sans le selecteur natif on ne sait pas quelles
    cibles sont ELIGIBLES (deep-strike, decoys, regles dynamiques), et fabriquer « tous les ennemis
    adjacents » serait permissif a l'endroit exact ou le compte EST l'utilite (`1141`)."""
    from engine import battle_query as bq          # feuille ; import local = pas de cycle a
    #                                               `_targets` (module volontairement sans import
    #                                               `engine.*` au niveau module, cf. son en-tete)
    a = _ability_entry(ctx, ability_id)
    if a is None or P is None:
        return []
    key = "fromHere" if (ctx.origin is not None and P == ctx.origin) else "targets"
    pos_by_id = {}
    for u in (ctx.units or []):
        p = u.get("pos") or {}
        if u.get("id") is not None and p.get("col") is not None:
            pos_by_id[u["id"]] = (p["col"], p["row"])
    epos = set(ctx.epos or [])
    neigh = bq.neigh_map(ctx)
    others: list[tuple] = []
    caster_at: int | None = None
    seen: set = set()
    for t in (a.get(key) or []):
        if t.get("kind") != "unit":
            continue
        tid = t.get("targetId")
        if tid is None or tid in seen:
            continue
        seen.add(tid)
        if tid == ctx.uid:
            caster_at = len(others)          # place RPC du caster, au sein des cibles gardees
            continue
        src = t.get("pos") or t.get("tile") or {}
        p = ((src.get("col"), src.get("row")) if src.get("col") is not None
             else pos_by_id.get(tid))
        if not p or p[0] is None or p not in epos:
            continue                          # `TargetIsEnemy` : seul le camp adverse survit
        if not bq.is_adjacent(P, p, ctx.elev_by_pos, neigh):
            continue                          # `TargetingRange` ADJACENT (|dElev| < 2 + voisinage natif)
        others.append((tid, p))
    if self_cast and caster_at is not None and others:
        others.insert(min(caster_at, len(others)), (ctx.uid, pos_by_id.get(ctx.uid)))
    return others


def eligible_tiles(ctx, ability_id: int) -> list[tuple]:
    """Cibles TUILE eligibles depuis l'origine -> `[((col, row), tileEntityId | None), ...]`,
    ORDRE NATIF. `tileEntityId` vient de `ctx.tile_id_by_pos` (l'id d'entite-tuile a emettre)."""
    a = _ability_entry(ctx, ability_id)
    if a is None:
        return []
    out: list[tuple] = []
    seen: set = set()
    for t in (a.get("fromHere") or []):
        if t.get("kind") != "tile":
            continue
        tl = t.get("tile") or {}
        if tl.get("col") is None:
            continue
        pos = (tl["col"], tl["row"])
        if pos in seen:
            continue
        seen.add(pos)
        tid = t.get("targetId")
        if tid is None:
            tid = (ctx.tile_id_by_pos or {}).get(pos)
        out.append((pos, tid))
    return out
