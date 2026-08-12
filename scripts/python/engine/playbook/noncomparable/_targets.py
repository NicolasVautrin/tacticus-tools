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
    porteurs sont des unites a `PositionComponent`, donc elles bougent. Ce corps le REFERME au lieu
    de le documenter, et par une MESURE, pas par une inference.

    DEUX etages, et ils viennent de sources DIFFERENTES -- c'est tout le point :

      * l'ENSEMBLE eligible vient du RPC (`targets` = l'UNION sur toutes les tuiles de move). C'est
        le filtre que la geometrie NE SAIT PAS rejouer : deep-strike, decoys, regles dynamiques
        d'ability. Le prendre en union est un SUR-ENSEMBLE par position, resserre ensuite ;
      * l'ORDRE et la portee viennent du VOISINAGE NATIF de `P` (`ctx.neigh_by_pos`), parce que
        `IdunBattle.Core.Services.AttackQuery$$GetValidTargets` SCANNE les tuiles d'attaque -- son
        ordre de sortie EST l'ordre du scan. C'est la lecture deja etablie et validee bit-exact par
        `CordClawPlaybook` sur le meme selecteur (slot 0x41/0x42).

    MESURE #977 (runner MC1_67/777, TROIS abilities, TROIS origines) : la liste reconstruite par
    cette regle est EGALE, element par element et dans l'ordre, au `fromHere` que le RPC publie --
      1131 @ (3,4) : voisins [(3,5),(4,4),(4,3),(3,3),(2,3),(2,4)] -> [86, 88, 90] == `fromHere` ;
      1141 @ (2,5) : voisins [(2,6),(3,6),(3,5),(2,4),(1,5),(1,6)] -> [86, 90] + caster == idem ;
      1043 @ (4,3) : voisins [(4,4),(5,4),(5,3),(4,2),(3,3),(3,4)] -> [88, 92] == idem.
    3/3. La regle vaut donc AUSSI aux positions de move, ou aucune vue RPC n'existe -- c'est ce qui
    rend l'ordre EXACT partout, et non plus « exact a l'origine, approche ailleurs ».

    `self_cast` (mirror de `isSelfCasting = 1`, le cas de `1141`) : le caster est ajoute **EN
    DERNIER**, et seulement s'il reste AU MOINS UNE autre cible -- la branche `else` de
    `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`
    (`0x800 AddCasterIfAtLeastOneTarget`). Le RANG est MESURE, pas suppose : `fromHere` de `1141`
    a l'origine rend `[86, 90, 80]`, le caster APRES les deux ennemis (et l'UNION, elle, le place
    en 2e -- s'y fier faisait choisir le caster comme cible a la position (1,5)).

    RPC absent -> `[]`, jamais une liste devinee : sans le selecteur natif on ne sait pas quelles
    cibles sont ELIGIBLES, et fabriquer « tous les ennemis adjacents » serait permissif a l'endroit
    exact ou le compte EST l'utilite (`1141`)."""
    from engine import battle_query as bq          # feuille ; import local = pas de cycle a
    #                                               `_targets` (module volontairement sans import
    #                                               `engine.*` au niveau module, cf. son en-tete)
    import hexgeo
    a = _ability_entry(ctx, ability_id)
    if a is None or P is None:
        return []
    eligible: set = set()
    for t in (a.get("targets") or []):
        if t.get("kind") == "unit" and t.get("targetId") is not None:
            eligible.add(t["targetId"])
    pos_by_id, id_by_pos = {}, {}
    for u in (ctx.units or []):
        p = u.get("pos") or {}
        if u.get("id") is not None and p.get("col") is not None:
            pos_by_id[u["id"]] = (p["col"], p["row"])
            id_by_pos[(p["col"], p["row"])] = u["id"]
    epos = set(ctx.epos or [])
    neigh_map = bq.neigh_map(ctx)
    ring = (ctx.neigh_by_pos or {}).get(P)
    if ring is None:
        ring = list(hexgeo.neighbors(P[0], P[1]))   # repli : compte identique, ordre non natif
    others: list[tuple] = []
    for n in ring:
        if not bq.is_adjacent(P, n, ctx.elev_by_pos, neigh_map):
            continue                          # `TargetingRange` ADJACENT (porte |dElev| < 2)
        if n not in epos:
            continue                          # `TargetIsEnemy` : seul le camp adverse survit
        tid = id_by_pos.get(n)
        if tid is None or tid not in eligible:
            continue                          # filtre d'eligibilite NON geometrique du selecteur
        others.append((tid, n))
    if self_cast and ctx.uid in eligible and others:
        others.append((ctx.uid, pos_by_id.get(ctx.uid)))
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
