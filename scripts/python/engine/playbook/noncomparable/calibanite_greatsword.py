"""CalibaniteGreatswordPlaybook (1189, `darkaCompanion`) -- face DECISION (#945).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`.

CE PLAYBOOK EST UN INTERRUPTEUR, PAS UN SCORE
----------------------------------------------
L'utilite qu'il emet est la CONSTANTE `Fix64.op_Implicit(0x7fffffff)` = 2147483647, la cible est le
CASTER LUI-MEME, et le Bucket est construit par la surcharge SANS `minUtility` (2 arguments ; la
classe native n'a pas de `.cctor`). Il ne DEPARTAGE donc rien : il dit « bascule le mode sweep »
ou il ne dit rien. Tout le contenu est dans la CONDITION, et cette condition est un **XOR**.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.CalibaniteGreatswordPlaybook$$EvaluateNonComparable` (0x4a5 = 1189) :

    bucket = new Bucket<UnitAction>()
    cur = EntityExtensions.GetUnitPosition(caster, this.State@+0x20)
    if (UnitExtensions.HasTriggeredAbility(caster, 0x5f2))            return bucket   # GATE 1
    if (UnitPosition.op_Inequality(casterPosition, box(cur)))         return bucket   # GATE 2
    all       = BasePlaybook.GetAllNormalAttackTargets(caster)          # (.Targets, .ByTile@+0x18)
    hasEffect = EntityExtensions.HasEffect(caster, State, 0x57d, onlyActive: 0)
    found = false
    foreach kv in all.ByTile:                                            # PASSAGE 1
        foreach u in kv.Value:
            sel   = CalibaniteGreatswordAbility.GetSweepAdditionalTargets(this.ability@+0x18)
            extra = TargetsSelector.SelectUniqueUnits(sel,
                        AbilityEntities(caster: caster, target: u, casterTile: kv.Key.MainTile), 3)
            pred  = battleQuery.<slot itf 33>(caster, u, kv.Key.MainTile)   # GetNormalAttackPrediction
            if (DamagePredictionResult.get_WillBeKill(pred)) {
                if (extra.Count > 0) {
                    if (!hasEffect) bucket.AddAction(GenerateAction(casterPosition, caster,
                                                                    Fix64(int.MaxValue)))
                    return bucket                                        # SORTIE ANTICIPEE
                }
                found = true
            }
    if (!found)
        foreach kv in all.ByTile:                                        # PASSAGE 2
            foreach u in kv.Value:
                extra = <le MEME selecteur, le MEME AbilityEntities>
                if (extra.Count > 0) {
                    if (!hasEffect) bucket.AddAction(GenerateAction(casterPosition, caster,
                                                                    Fix64(int.MaxValue)))
                    return bucket
                }
    if (hasEffect) bucket.AddAction(GenerateAction(casterPosition, caster, Fix64(int.MaxValue)))
    return bucket

La condition, DEBARRASSEE DE L'ORDRE (et elle en est bien independante, cf. plus bas) :

    A    = il existe (tuile d'attaque, cible) avec `WillBeKill` ET `|extra| > 0`
    B    = il existe (tuile d'attaque, cible) avec `WillBeKill`                 (A => B)
    C    = il existe (tuile d'attaque, cible) avec `|extra| > 0`
    cond = A or (not B and C)
    EMET <=>  cond != hasEffect                                        # XOR

Autrement dit : **allume le sweep quand il servirait, eteins-le quand il ne sert plus.**

POURQUOI L'ORDRE N'A AUCUN OBSERVABLE, alors que le natif fait des `return` en cours de boucle
------------------------------------------------------------------------------------------------
Le `return` du passage 1 ne se declenche QUE sur `WillBeKill && |extra| > 0` : si un tel couple
existe, il est atteint quel que soit l'ordre (rien n'interrompt la boucle avant lui). `found` n'est
LU qu'apres l'epuisement complet du passage 1. Et l'utilite emise est CONSTANTE, la cible etant
toujours le caster : deux couples ne peuvent pas se departager. Le port peut donc evaluer les trois
quantificateurs dans n'importe quel ordre -- ce n'est pas une approximation, c'est une equivalence.

LES DEUX GATES AMONT
---------------------
* **GATE 1** `HasTriggeredAbility(caster, 0x5f2 = TriggeredAbilityType.RedemptionOfTheRisen)`
  (1522, nom LU dans `frida/enums.tsv`) : le porteur qui possede cette triggered ability n'utilise
  JAMAIS 1189 par ce playbook. Mesure du regime : **aucune** unite du gameconfig `rnca9r7q6c` ne
  la porte (balayage des `activeAbilities` + `passiveAbilities` des 669 kits) -- le gate est donc
  inerte aujourd'hui, mais il est ECRIT ici parce qu'il decidera des qu'un porteur apparaitra.
  ⚠ BORNE : le substrat offline est le KIT ; une triggered ability POSEE en cours de bataille par
  un effet n'y figure pas. Degradation PERMISSIVE (le port n'abandonne pas la ou le natif le
  ferait) -- residu `#945-r2`.
* **GATE 2** `casterPosition != GetUnitPosition(caster)` : l'ability n'est proposee QUE depuis la
  position COURANTE. Le sweep du generateur passe par toutes les tuiles de move, et ce test les
  rejette toutes sauf l'origine. D'ou `to = None`, et ce n'est pas le keep-first du Bucket qui le
  produit -- c'est un refus explicite.

LE SELECTEUR `extra`
---------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.CalibaniteGreatswordAbility$$GetSweepAdditionalTargets`
= `AdjacentEnemies(Caster@+0x48, CasterTile@+0x50, unique: 1)  op_BitwiseAnd
   AdjacentUnits(Target@+0x60, unique: 1, sel: 3)`

-- une **INTERSECTION** (`op_BitwiseAnd`), pas une union. Le `CasterTile` de l'`AbilityEntities`
construit par le playbook est `kv.Key.MainTile`, c'est-a-dire la TUILE D'ATTAQUE candidate (pas la
tuile courante). Donc : les ENNEMIS DU CASTER qui sont a la fois adjacents a la tuile d'ou il
frapperait ET adjacents a la cible. La cible ne s'y compte jamais (`AdjacentUnits(T)` =
`Units(AdjacentTiles(T)) - T`). C'est le MEME artefact natif que la face COMBAT : le sweep du
Greatsword touche les voisins communs.

`AdjacentEnemies(unit, unitTile, unique)` : la surcharge a TUILE explicite -- c'est le champ
`+0x50` du singleton `DSLSelectors` qui est passe en 2e argument, la ou `+0x48` (`Caster`) est en
1er. Le triplet de reference est `Owner@+0x30` / `Caster@+0x48` / `Target@+0x60` (cf.
`loki_custom.MassDriverAcceleratorPlaybook`), et `CasterTile@+0x50` est la tuile associee au
caster -- meme forme que l'`AdjacentFriends(champ+0x30, ownerTiles, 1)` de
`...DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector`.

SUBSTRAT DU DICTIONNAIRE `ByTile`
----------------------------------
`IdunBattle.AI.Playbook.BasePlaybook$$GetAllNormalAttackTargets(caster)` rend
`(List<TUnit> Targets @+0x10, Dictionary<Tile, List<TUnit>> ByTile @+0x18)` : pour chaque tuile ou
le caster peut se tenir, les ennemis qu'il y atteint a l'attaque NORMALE. Le mirror offline est le
PLAN natif (`ctx.plans[uid]["evals"]`, deja movement-inclusif), INVERSE cible -> tuiles en
tuile -> cibles. Meme correspondance que
`noncomparable.hammer_of_wrath._enemy_killed_by_normal_attack` et que
`loki_custom._all_normal_attack_targets` (branche « unite ACTIVE »).

⚠ Le plan est TRONQUE a `maxRank` par le harnais (`computeAttackPlans`), un plafond absent du
natif -- cf. `_base._PlanTargetPlaybook.eligible_positions`. Ici la troncature ne peut que
RETIRER des couples, donc borner A / B / C par en dessous. Elle ne fabrique jamais un `cond` vrai.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.triggered_ability_type import TriggeredAbilityType

from ._base import (NCContext, NonComparablePlaybook, _normal_attack_ids, _unit_cfg,
                    _will_normal_attack_kill)

#: `HasEffect(caster, State, 0x57d, onlyActive: 0)` -- 1405 = `EffectType.CalibaniteGreatswordSweep`,
#: l'effet que l'ability pose sur elle-meme (le « mode sweep »). `onlyActive` est le litteral `0` au
#: call-site : le natif ne lit PAS `EffectComponent.IsActive @+0x5c` -> foyer partage
#: `battle_query.scene_has_effect`, comme `VexillaMagnificaPlaybook._target_is_stunned`.
_SWEEP_EFFECT = int(EffectType.CalibaniteGreatswordSweep)          # 0x57d = 1405

#: `HasTriggeredAbility(caster, 0x5f2)` -- 1522 = `TriggeredAbilityType.RedemptionOfTheRisen`.
_EXCLUDING_TRIGGERED = TriggeredAbilityType.RedemptionOfTheRisen   # 0x5f2 = 1522

#: `Fix64.op_Implicit(0x7fffffff)` -- l'utilite CONSTANTE emise par les trois `AddAction`.
_UTILITY = float(0x7fffffff)


class CalibaniteGreatswordPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.CalibaniteGreatswordPlaybook$$EvaluateNonComparable` --
    TOGGLE self-cast : emet `Fix64(int.MaxValue)` sur le caster ssi `cond != hasEffect`."""
    ABILITY_ID = int(ActiveAbilityType.CalibaniteGreatsword)   # 0x4a5 = 1189
    MIN_UTILITY = 0.0   # Bucket ctor 2-ARG : AUCUN minUtility (et la classe n'a pas de `.cctor`)
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    # ---------------------------------------------------------------- gates amont

    def _has_excluding_triggered_ability(self, ctx: NCContext) -> bool:
        """GATE 1. `UnitExtensions$$HasTriggeredAbility(caster, 0x5f2)` interroge l'**ECS**
        (`TriggeredAbilityComponent`), pas le kit de configuration -- une triggered ability POSEE EN
        COURS DE BATAILLE y est donc visible.

        DEUX substrats, en UNION et jamais en remplacement (regle N13, celle de
        `utilities/tile.py::_adjacent_units`) :

          * le kit du caster (`activeAbilities` + `passiveAbilities` du gameconfig), converti PAR NOM
            et jamais par ordinal (#270-c) ;
          * le kit DECLENCHE **RUNTIME** (`ctx.triggered_kits`, RPC `unitAbilityStates` -- #945-r2),
            qui porte des IDS. Canal absent -> le kit gameconfig SEUL, la degradation d'avant.

        L'union interdit qu'une lecture live partielle RETIRE un id que le kit connait ; et le canal
        runtime ferme la borne que l'en-tete nommait (le port n'abandonnait jamais la ou le natif
        abandonne)."""
        me = next((u for u in (ctx.units or []) if u.get("id") == ctx.uid), None)
        cfg = _unit_cfg((me or {}).get("visualId"))
        names = (cfg.get("activeAbilities") or []) + (cfg.get("passiveAbilities") or [])
        if _EXCLUDING_TRIGGERED.name in names:
            return True
        fn = getattr(ctx, "triggered_kits", None)
        if not callable(fn):
            return False                                  # canal absent : kit gameconfig SEUL
        try:
            table = fn() or {}
        except Exception:
            return False                                  # RPC muet -> jamais une AFFIRMATION
        ids = table.get(ctx.uid) or table.get(int(ctx.uid)) or ()
        return int(_EXCLUDING_TRIGGERED) in {int(x) for x in ids}

    def _has_sweep_effect(self, ctx: NCContext) -> bool:
        """`EntityExtensions$$HasEffect(caster, State, 1405, onlyActive: null)`.

        `ctx.scene` absent -> `False`, comme `VexillaMagnificaPlaybook` : le port ne peut pas
        AFFIRMER une presence d'effet qu'aucun substrat ne lui donne. Consequence a connaitre :
        sans scene, le port ne propose 1189 que dans le sens ALLUMAGE (`cond` vrai)."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return False
        return bool(bq.scene_has_effect(sc, int(ctx.uid), _SWEEP_EFFECT))

    # ---------------------------------------------------------------- substrat ByTile

    def _targets_by_tile(self, ctx: NCContext) -> dict:
        """`GetAllNormalAttackTargets(caster).ByTile` -- `{(col,row): [targetId, ...]}`.

        Inverse le plan natif (cible -> tuiles rankees) en tuile -> cibles. Les ids d'attaque
        NORMALE sont ceux de `_normal_attack_ids` (l'id CONCRET per-unit, jamais l'abstrait 17)."""
        plan = (ctx.plans or {}).get(ctx.uid) or ctx.plan or {}
        nids = _normal_attack_ids(ctx, ctx.uid)
        out: dict = {}
        for ev in (plan.get("evals") or []):
            if ev.get("abilityId") not in nids or not ev.get("rankCount"):
                continue
            tid = ev.get("targetId")
            if tid is None:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("col") is None:
                    continue
                out.setdefault((rk["col"], rk["row"]), []).append(tid)
        return out

    # ---------------------------------------------------------------- le selecteur `extra`

    def _sweep_extra_count(self, ctx: NCContext, attack_tile: tuple, target) -> int:
        """`|SelectUniqueUnits(AdjacentEnemies(Caster, CasterTile, 1) & AdjacentUnits(Target, 1, 3))|`
        = les ennemis du caster adjacents A LA FOIS a la tuile d'attaque et a la cible.

        L'intersection est evaluee sur `ctx.epos` (positions ennemies VIVANTES) : c'est deja le
        filtre `Enemies` du premier membre, et `AdjacentUnits(Target)` n'ajoute pas de filtre de
        camp -- l'intersection le porte donc pour les deux. La cible est a distance 0 d'elle-meme
        et n'est jamais adjacente a elle-meme : elle sort, comme le `- Target` natif."""
        tpos = self._pos_of(ctx, target)
        if tpos is None:
            return 0
        neigh = bq.neigh_map(ctx)
        n = 0
        for e in (ctx.epos or []):
            if e is None or e[0] is None:
                continue
            if bq.is_adjacent(attack_tile, e, ctx.elev_by_pos, neigh) \
                    and bq.is_adjacent(tpos, e, ctx.elev_by_pos, neigh):
                n += 1
        return n

    @staticmethod
    def _pos_of(ctx: NCContext, uid):
        u = next((x for x in (ctx.units or []) if x.get("id") == uid), None)
        p = (u or {}).get("pos") if u else None
        if p and p.get("col") is not None:
            return (p["col"], p["row"])
        return None

    # ---------------------------------------------------------------- la condition

    def should_toggle(self, ctx: NCContext) -> bool:
        """`cond = A or (not B and C)` (cf. l'en-tete). Expose separement de
        `generate_candidates` pour etre MESURABLE : le verdict final est un XOR, donc voir
        « emet / n'emet pas » ne dit pas lequel des deux membres a bascule."""
        by_tile = self._targets_by_tile(ctx)
        found_kill = False          # B
        any_extra = False           # C
        for tile, tgts in by_tile.items():
            for u in tgts:
                extra = self._sweep_extra_count(ctx, tile, u)
                if extra > 0:
                    any_extra = True
                if _will_normal_attack_kill(ctx, u, tile):
                    if extra > 0:
                        return True                       # A -> sortie anticipee du natif
                    found_kill = True
        return (not found_kill) and any_extra

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Les deux gates amont, puis le XOR. Cible = le CASTER, position = l'ORIGINE (GATE 2),
        utilite = `Fix64(int.MaxValue)`."""
        if ctx.origin is None:
            return []
        if self._has_excluding_triggered_ability(ctx):
            return []                                      # GATE 1
        # GATE 2 : `casterPosition != GetUnitPosition(caster)` -> le generateur ne retient QUE
        # l'origine. Rien a balayer : `to` vaut None par construction.
        cond = self.should_toggle(ctx)
        if cond == self._has_sweep_effect(ctx):
            return []                                      # XOR faux -> bucket VIDE
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] CalibaniteGreatsword toggle cond=%s hasEffect=%s"
                  % (ctx.uid, cond, self._has_sweep_effect(ctx)), file=sys.stderr)
        return [{"target": ctx.uid, "ability": self.ABILITY_ID, "to": None, "pred": _UTILITY}]
