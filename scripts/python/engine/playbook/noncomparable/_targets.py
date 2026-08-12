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
