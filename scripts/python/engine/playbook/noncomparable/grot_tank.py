"""GrotTankPlaybook -- decision NC du summon Grot Tank (`orksBigMek`, #570)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import (NCContext, NonComparablePlaybook, eligible_target_tiles,
                    tiles_in_native_order)


class GrotTankPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.GrotTankPlaybook$$EvaluateNonComparable` (DECOMPILE).

    `IdunBattle.AI.Playbook.Loki.GrotTankPlaybook$$.ctor` = `ComparablePlaybook<T>..ctor(this,
    0x421)` (0x421 = 1057) ; `...$$.cctor` ecrit `Fix64(1)` dans le statique que le `Bucket` recoit
    en borne -> `MIN_UTILITY = 1`.

        bucket = Bucket(0, Nullable(Fix64(1)))
        targets = GetEligibleTargetsSelectable(caster, MainTile(casterPosition))  # tuiles de SPAWN
        foreach (t in targets):
            u = GetUtility(caster, t.<tuile>)
            if (u > Fix64(0)):
                bucket.AddAction(GenerateAction(MainTile(casterPosition), t.<tuile>, u))

    et `IdunBattle.AI.Playbook.Loki.GrotTankPlaybook$$GetUtility(caster, summonTile)` :

        x = Fix64(0)
        foreach (e in IBattleQuery.<slot 118 = GetSurroundingUnits>(summonTile, 3, null)):
            if (!IBattleQuery.<slot 146 = AreFriends>(e.Id, caster, null))
                x = x + 1
        return x

    ⇒ **utilite = le nombre d'unites NON AMIES dans le disque de rayon 3 autour de la TUILE DE
    SPAWN** -- exactement la portee de l'arme `Blast` du `orksGrotTank` (gameconfig : `Range: 3`),
    c'est-a-dire « combien de cibles le tank pourra canarder ». Le natif ne consulte NI les PV, NI
    les traits, NI la distance au caster.

    SLOTS : lus dans `data/symbols/<build>/metadata/interface_slots.tsv` (le champ `slot` d'
    `Il2CppMethodDefinition`), pas recopies d'un dump anterieur -- `IBattleQuery` 118 =
    `GetSurroundingUnits` (arite 3 ; ses voisins 117 et 119 sont DEUX autres surcharges du meme
    nom, c'est l'arite qui tranche) et 146 = `AreFriends` (arite 3). Les re-deriver au changement de
    build : `probe_477r25_slots_autres_interfaces.py --regenerer`.

    Trois lectures ANCREES, et ce qu'elles excluent :

    - **Le rayon est un LITTERAL du playbook**, pas une constante d'ability : le decompile ecrit `3`
      en dur dans l'appel. Il coincide avec `orksGrotTank.weapons[1].Range` mais rien ne le lie a
      lui -- on transcrit le litteral, on ne le derive pas du kit.
    - **`includeCenter` est INERTE ici** : le 3e argument est `0`, mais la tuile de spawn est de
      toute facon LIBRE (masque `TargetTileIsFree`), donc aucune unite ne s'y trouve. L'ambiguite ne
      peut pas produire d'ecart -- on la nomme au lieu de la trancher a l'aveugle.
    - **Le disque est GEOMETRIQUE** (`BattleQuery$$GetSurroundingUnits` ->
      `TileQuery$$IterateSurroundingTiles`, triple boucle cube `x+y+z == 0`), contrairement au
      SELECTEUR de cibles ci-dessous qui, lui, passe par la liste STOCKEE du `ConnectivityComponent`
      (`onlyAdjacent`). Les deux etages ne se portent donc PAS de la meme facon, et les confondre
      serait l'erreur exacte que `AberrantHypermorphPlaybook` documente (#616).

    ORDRE (mirror du bucket) : positions T dans l'ordre de `reach_nc` (origine d'abord), et par
    position les tuiles dans l'ordre du selecteur -- DERIVE par position depuis la liste d'adjacence
    STOCKEE (`_base.tiles_in_native_order`, #971-r4), jamais l'ordre de l'UNION du RPC, qui n'est
    celui d'AUCUNE position ; `Bucket$$AddAction` ne remplace que si STRICTEMENT superieur -> la
    PREMIERE paire (T, ST) du maximum gagne.

    CIBLE EMISE = la TUILE DE SPAWN (`ctx.tile_id_by_pos`), comme AberrantHypermorph et
    MasterOfTheTutelaries : c'est le `targetId` que le cast natif recoit (`TargetIsTile`).

    RESIDU NOMME : `AreFriends` est un predicat a TROIS etats cote natif (il peut rendre faux pour
    une entite NEUTRE, un objet ou une tuile-entite), la ou le port compte `ctx.epos` -- les seules
    positions ENNEMIES publiees. Un objet neutre dans le disque serait donc compte par le natif et
    pas par le port. Aucun regime porte ne l'expose (les runners n'ont que deux camps)."""

    ABILITY_ID = int(ActiveAbilityType.GrotTank)   # 1057
    MIN_UTILITY = 1.0                              # `...GrotTankPlaybook$$.cctor` = Fix64(1)
    PRIORITY = 0                                   # absent de `NATIVE_PRIORITY`
    #: Le `3` LITTERAL de l'appel `GetSurroundingUnits(summonTile, 3, null)` (cf. docstring).
    _UTILITY_RADIUS = 3

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Mirror du sweep natif. La contrainte « hex adjacent » vient du SELECTEUR, pas d'un
        filtre du playbook : `GrotTankAbility$$.ctor` recopie le `TargetingRange` statique `+0x30`
        (`onlyAdjacent = RangedBool.True`) et les rules `0x1040`, exactement comme
        `AberrantHypermorphAbility$$.ctor` et `MasterOfTheTutelariesAbility$$.ctor` -- donc
        `TargetingQuery$$GetTilesInRange` part sur le slot `GetAdjacentTiles` ->
        `IterateAdjacentTiles` (liste STOCKEE du `ConnectivityComponent`, puis `|dElev| < 2`), et
        la re-projection de l'union sur T EST `bq.is_adjacent(T, ST)`. Chaine detaillee :
        `AberrantHypermorphPlaybook.generate_candidates` (#616).

        `eligible_target_tiles` rend le couple `(fromHere, union)` : `fromHere` porte l'ORDRE NATIF
        du selecteur a la position d'origine, `union` l'agregat sur toutes les tuiles de move (le
        RPC n'a pas de vue par position). A l'origine on prend donc `fromHere` -- a utilite egale,
        c'est la PREMIERE tuile enumeree qui gagne, et les deux vues n'ont pas le meme ordre.

        ⚠ **ET POUR LES AUTRES POSITIONS, L'ORDRE DE L'UNION N'EST CELUI D'AUCUNE** (`#971-r4`).
        C'est exactement l'ecart deja MESURE et ferme sur `IronkinSteeljackPlaybook` (#971, board
        `MC1_67`/4242 : 11 classes natives contre 10 portees, deux positions retenant la MEME tuile
        cote port et deux tuiles distinctes cote natif, a utilite EGALE). Le foyer partage
        `_base.tiles_in_native_order` derive l'ordre par position depuis `ctx.neigh_by_pos` -- la
        liste d'adjacence STOCKEE, celle-la meme que parcourt la chaine native. La transposition est
        legitime parce que les ctors de `...GrotTankAbility$$.ctor`,
        `...MasterOfTheTutelariesAbility$$.ctor` et `...IronkinSteeljackAbility$$.ctor` sont
        IDENTIQUES OCTET POUR OCTET (relus le 2026-08-18 sur le build courant), donc la chaine
        d'enumeration est la MEME -- pas parce que les trois << se ressemblent >>."""
        from_here, union = eligible_target_tiles(ctx, self.ABILITY_ID)
        if not from_here and not union:
            return []
        neigh = bq.neigh_map(ctx)
        eligibles = set(from_here) | set(union)
        epos = [(p[0], p[1]) for p in (ctx.epos or [])]
        best = None                                   # (tuile de spawn ST, position T, utilite)
        for T in (ctx.reach_nc or []):                # positions candidates (origine en premier)
            tiles = tiles_in_native_order(ctx, T, from_here, union, eligibles)
            for ST in tiles:
                if not bq.is_adjacent(T, ST, ctx.elev_by_pos, neigh):
                    continue                          # spawn = hex ADJACENT a T, au sens du selecteur
                # `GetUtility` : #unites NON AMIES dans le DISQUE de rayon 3 autour de ST.
                u = float(sum(1 for p in epos
                              if hexgeo.distance(ST, p) <= self._UTILITY_RADIUS))
                if u <= 0.0:
                    continue                          # gate natif `u > Fix64(0)`
                if best is None or u > best[2]:       # strict > : 1re paire (T, ST) du max gagne
                    best = (ST, T, u)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        st, t, u = best
        tid = (ctx.tile_id_by_pos or {}).get(st)
        return [{"target": (tid if tid is not None else st), "ability": self.ABILITY_ID,
                 "to": (t if t != ctx.origin else None), "pred": u}]
