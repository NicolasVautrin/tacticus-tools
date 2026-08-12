"""SilentDeathPlaybook -- frappe NonComparable a utilite PLATE, gate << la cible est ENTOUREE >>."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class SilentDeathPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.SilentDeathPlaybook$$EvaluateNonComparable` (id 0x42c = 1068, `eldarJainZar`).

    Base LUE dans `data/symbols/<build>/frida/classes.tsv` :
    `IdunBattle.AI.Playbook.NonComparablePlaybook`1`. ⚠ Le `.ctor` est etiquete par Ghidra
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor` --
    c'est le mislabel systematique du build (verifie 2/2 sur ce lot, 5/5 sur les trois lots
    precedents) ; seule la table des classes fait foi. L'argument du ctor, lui, EST lu : `0x42c`.

    `IdunBattle.AI.Playbook.Loki.SilentDeathPlaybook$$.cctor` : `MIN_UTILITY = Fix64.FromInt(1)`.
    `PRIORITY = 0` (`AbilityPriority.Normal`) -- 1068 est hors `NATIVE_PRIORITY` (sweep exhaustif
    #170).

    ## Le corps, verbatim

        bucket = Bucket(0, MIN_UTILITY)
        foreach target in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
            util = Fix64(1)
            sel  = DSLSelectors.Enemies(
                       of:           DSLSelectors.Get(caster),
                       entities:     DSLSelectors.AdjacentUnits(
                                         origin:        DSLSelectors.Get(target),
                                         unique:        true,
                                         selectionType: OnlyAliveAndTargetable),
                       selectionType: OnlyAliveAndTargetable)
            if sel.Count(<contexte d'entites VIDE>) > 0:
                bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, target, util))
        return bucket

    ## Ce que porte ce playbook, et qui n'est PAS le chemin generique

    L'utilite est CONSTANTE (`Fix64(1)`) : ce playbook ne classe pas les cibles, il les FILTRE.
    Le seul comportement propre est donc le gate, et il est discriminant -- le natif n'emet 1068
    QUE sur une cible ayant au moins un ennemi-du-caster adjacent (c.-a-d. un allie A ELLE colle
    a elle). Sans ce gate, 1068 serait proposee sur n'importe quelle cible a portee.

    ⚠ Le centre est EXCLU, et c'est LU, pas suppose :
    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits` =
    `TargetsSelector.op_Subtraction(Units(AdjacentTiles(origin), unique, selectionType), origin)`.
    Le `- origin` retire la cible de son propre voisinage. Sans lui le gate serait TOUJOURS vrai
    (la cible est elle-meme un ennemi du caster), l'ability serait proposee partout, et le port
    aurait l'air de marcher.

    `selectionType` = `OnlyAliveAndTargetable` (`IdunBattle.Entities.Enum.UnitSelectionType` = 3),
    LU au site des DEUX appels -- pas `onlyAlive: bool`, qui est l'AUTRE surcharge d'`Enemies`
    (`of, entities, onlyAlive:System.Boolean`, RVA voisine). `ctx.epos` ne porte que des unites
    vivantes et ciblables, donc la clause est deja tenue par le canal.

    Utilite PLATE -> `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
    seede le premier ajoute et ne remplace QUE sur strictement superieur : au tie, la PREMIERE
    cible enumeree gagne (keep-first), et la position gagnante est l'ORIGINE (l'utilite ne depend
    pas de la position du caster). D'ou `to = None`, comme `HeroicFusilladePlaybook`.

    ## NON TRANCHE, et dit plutot que devine

    Le slot 4 `ShouldEvaluate` n'est PAS surcharge de facon LISIBLE : aucun
    `SilentDeathPlaybook$$ShouldEvaluate` dans les tables. Ce n'est PAS une preuve d'absence --
    IL2CPP deduplique les corps triviaux et un gate folde (`AlphaWarriorPlaybook$$ShouldEvaluate`,
    `turnsStarted > 1`) n'aurait qu'UN proprietaire dans la table. On garde donc le defaut herite
    `BasePlaybook$$ShouldEvaluate` -> `GetUseProbability` = `Fix64(1)` -> True, qui est la
    degradation PERMISSIVE (poser `_turns_started_gate` a tort REFUSERAIT des casts legitimes,
    ce qui est la faute la plus chere des deux). Point d'ancrage pour trancher : le slot 4 de la
    vtable, via le RPC `pbGate` que joue deja `probe_170_playbook_priority.py`.
    """
    ABILITY_ID = int(ActiveAbilityType.SilentDeath)  # 0x42c = 1068
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.SilentDeathPlaybook$$.cctor = Fix64(1)
    PRIORITY = 0          # hors NATIVE_PRIORITY -> AbilityPriority.Normal

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        tgt_ids = []                      # ordre PRESERVE = enumeration GetEligibleTargetsSelectable
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        tgt_ids.append(t["targetId"])
        tgt_ids = list(dict.fromkeys(tgt_ids))
        if not tgt_ids:
            return []
        by_id = {u.get("id"): u for u in (ctx.units or [])}
        neigh = bq.neigh_map(ctx)
        for tid in tgt_ids:               # keep-first : utilite PLATE -> le 1er qui passe gagne
            tu = by_id.get(tid)
            p = (tu or {}).get("pos") if tu else None
            if not p or p.get("col") is None:
                continue
            tpos = (p["col"], p["row"])
            # Enemies(of: caster, AdjacentUnits(target) - target) : `ctx.epos` EST << ennemi du
            # caster >>, et le `- origin` du selecteur natif retire la cible de son voisinage.
            others = [e for e in (ctx.epos or []) if e != tpos]
            if bq.count_adjacent(tpos, others, ctx.elev_by_pos, neigh) < 1:
                continue
            if ctx.debug:
                import sys
                print(f"    [dbg SilentDeath u{ctx.uid}] tgt={tid} pos={tpos} -> util=1",
                      file=sys.stderr)
            return [{"target": tid, "ability": self.ABILITY_ID, "to": None, "pred": 1.0}]
        return []
