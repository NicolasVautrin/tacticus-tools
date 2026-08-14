"""BioMinefieldPlaybook -- la face DECISION de `1144 BioMinefield` (`tyranBiovore`). (#939)"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook
# FORME A assumee : `bq` est un MODULE (pas un nom), donc un `monkeypatch.setattr` sur
# `engine.battle_query.is_adjacent` mord quand meme. MEME import que le jumeau
# `doctrina_imperatives`, qui mirrore le MEME natif `BattleQuery$$GetFreeAdjacentTiles`.
from engine import battle_query as bq


class BioMinefieldPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.BioMinefieldPlaybook$$EvaluateNonComparable(caster,
    casterPosition, abilityState)` -- mirror du decompile, transcrit :

        var bucket = new Bucket<UnitAction>(priority: 0, minUtility: Nullable(<statics+0x00>));
        var mainTile = casterPosition.MainTile;
        foreach (var target in BasePlaybook$$GetEligibleTargetsSelectable(this, caster, mainTile)) {
            var free = this.<+0x28 : IBattleQuery>.GetFreeAdjacentTiles(target);   // slot 82
            if (free.Count > 0) {
                var u = Fix64(free.Count * 100)
                      + Fix64((int)((float)UnitExtensions$$GetStat(target, StatType.Health, 0, null)
                                  / (float)UnitExtensions$$GetStat(target, StatType.Health, 2, null)
                                  * 100.0f));
                bucket.AddAction(BasePlaybook$$GenerateAction(this, casterPosition, target, u));
            }
        }
        return bucket;

    soit : **utilite = 100 x (nombre de tuiles LIBRES adjacentes a la cible) + 100 x PV%**. L'IA
    prefere donc les cibles ENTOUREES DE PLACE (ou poser le plus de mines) et, a place egale, les
    cibles EN BONNE SANTE -- ce qui est coherent avec l'ability : les mines mettent des tours a
    exploser, viser un mourant les gaspille.

    `MIN_UTILITY = 1.0` : `BioMinefieldPlaybook$$.cctor` ecrit `Fix64$$op_Implicit(1)` dans le champ
    statique `+0x00`, que le `Nullable` du `Bucket` reprend.

    ⚠ **LE SLOT 82 EST LU, PAS DEDUIT** : `metadata/interface_slots.tsv` (`global-metadata.dat` du
    build `rnca9r7q6c`) donne `IBattleQuery 82 GetFreeAdjacentTiles 1`. C'est le MEME predicat que
    le bit `TargetHasFreeAdjacentTile` (0x20) du masque de ciblage de l'ability -- le playbook et la
    gate de ciblage sont donc d'accord par construction, ce qui rend le gate `free.Count > 0`
    redondant AU CAS NOMINAL, mais il est porte parce que le natif l'ecrit.

    ⚠ **UTILITE POSITION-INDEPENDANTE -> LE CASTER NE BOUGE PAS.** Ni `free.Count` ni les PV% ne
    dependent de `casterPosition` ; le sweep natif enumere `reach_nc` avec l'ORIGINE EN TETE et
    `Bucket$$AddAction` ne remplace que sur un STRICTEMENT superieur -> le tie garde la premiere
    position, c'est-a-dire l'origine. D'ou `to: None` (meme raison que `GetEmRuntzPlaybook`).

    `get_Priority` = 0 (`AbilityPriority.Normal`) : `1144` n'est pas dans `NATIVE_PRIORITY`.

    ⚠ Ce playbook est ENREGISTRE cote natif -- `metadata/active_playbook_builders.tsv` porte
    `active 1144 IdunBattle.AI.Playbook.Loki.BioMinefieldPlaybook`, ecrit par
    `IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders` (`<>c$$<InitializePlaybookBuilders>
    b__31_150`). Ce n'est donc PAS du code registered-but-dead."""
    ABILITY_ID = int(ActiveAbilityType.BioMinefield)  # 1144
    MIN_UTILITY = 1.0                                 # `$$.cctor` : `Fix64$$op_Implicit(1)`

    @staticmethod
    def _free_adjacent_tiles(ctx: NCContext, pos: tuple) -> int:
        """`IBattleQuery` slot 82 `GetFreeAdjacentTiles(target)` -- les hex a distance 1 de la cible
        ou une unite peut etre POSEE : tuile connue du board, non occupee, et marchable quand le
        canal `walkable_by_pos` existe.

        Meme substrat que `GetEmRuntzPlaybook._spawn_tile_count` (dont c'est le sur-ensemble : lui y
        ajoute le filtre << adjacent a un ennemi >>, que `GetFreeAdjacentTiles` n'a pas). Canal
        `walkable_by_pos` VIDE -> volet inerte, degradation PERMISSIVE deja documentee sur `NCContext`
        (la zone ne peut qu'ELARGIR), jamais un zero fabrique.

        ⚠ L'ADJACENCE PASSE PAR LE FOYER (#943), pas par `hexgeo.distance == 1`. Le natif descend
        `GetFreeAdjacentTiles` -> `GetAdjacentTiles(from, 1, 1, 1)` ->
        `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
        c'est-a-dire la LISTE D'ADJACENCE STOCKEE du board PLUS la porte d'elevation
        `|elev(a) - elev(b)| < 2` -- deux etages qu'une distance hex nue ignore, donc un
        SUR-COMPTE (l'utilite vaut `100 x free`, un voisin de trop deplace le choix de cible).
        `engine.battle_query.is_adjacent` EST ce foyer et il DEGRADE seul : sans `neigh_by_pos` ni
        `elev_by_pos` il rend exactement `hexgeo.distance == 1`, donc ce cablage est un NO-OP
        DEMONTRABLE la ou les canaux sont vides -- c'est le meme geste que #433-r4-r1-r4-r2-r1 sur
        `battle_query.adjacent_addable_count`, dont le jumeau de ce module
        (`doctrina_imperatives._free_adjacent_tiles`, MEME natif) se sert deja."""
        valides = set(ctx.elev_by_pos.keys()) if ctx.elev_by_pos else set()
        occupees = bq.occupied_positions(ctx)     # #969-r3 : PAR PIED (`TileContentComponent`)
        walk = ctx.walkable_by_pos or {}
        neigh_by_pos = getattr(ctx, "neigh_by_pos", None)
        n = 0
        for t in valides:
            if t in occupees or not bq.is_adjacent(pos, t, ctx.elev_by_pos, neigh_by_pos):
                continue
            if walk and not walk.get(t, True):
                continue
            n += 1
        return n

    @staticmethod
    def _hp_pct(ctx: NCContext, uid) -> float:
        """`(float)GetStat(target, Health, 0) / (float)GetStat(target, Health, 2) * 100`, TRONQUE en
        `int` par le natif AVANT `Fix64$$op_Implicit` (LU : le resultat du flottant est converti en
        `uint` puis implicite). `hpMax` absent ou nul -> 0.0 (le natif diviserait par zero ; le port
        refuse d'inventer une valeur)."""
        for u in (ctx.obs_units or []):
            if u.get("squadId") == uid or u.get("id") == uid:
                hp, hpmax = u.get("hp"), u.get("hpMax")
                if not hp or not hpmax:
                    return 0.0
                return float(int(100.0 * float(hp) / float(hpmax)))
        return 0.0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best = None
        for e in (ctx.enemies or []):
            eid, epos = e.get("id"), e.get("pos")
            if eid is None or epos is None:
                continue
            n = self._free_adjacent_tiles(ctx, tuple(epos))
            if n <= 0:                                  # `if (free.Count > 0)`
                continue
            util = 100.0 * n + self._hp_pct(ctx, eid)
            if util < self.MIN_UTILITY:                 # gate `Bucket.AddAction(util >= min)`
                continue
            # `Bucket$$AddAction` SEED le 1er puis ne remplace que sur STRICTEMENT superieur ->
            # keep-first a egalite, dans l'ordre d'enumeration des cibles eligibles.
            if best is None or util > best["pred"]:
                best = {"target": eid, "ability": self.ABILITY_ID, "to": None, "pred": util}
        return [best] if best is not None else []
