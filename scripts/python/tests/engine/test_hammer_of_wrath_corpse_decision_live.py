"""HammerOfWrath (1153) face DECISION -- les cibles SECONDAIRES sont resolues par OCCUPATION DE TUILE,
donc un CADAVRE n'en est jamais une. GARDE de non-regression, LIVE.

NATIF (mirror, `rnca9r7q6c`) :
    IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour
      -> IdunBattleLogic.Entities.DSLSelectors$$Enemies( caster,
           IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(target, unique, kind) )
    IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits(origin, ...) =
           IdunBattleLogic.Entities.DSLSelectors$$Units( AdjacentTiles(origin), ... )  -  origin
    IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select = selecteur de TUILES (@+0x18) resolu
           dans le mode d'occupation (@+0x20).
Le natif n'a donc AUCUN test `isDead` : une unite morte n'occupe plus de tuile, elle sort du selecteur
par CONSTRUCTION. Notre substrat, lui, garde les cadavres (`scene.pos_by_id` vient de
`decisionView.units`, cf. `decisionview-keeps-dead`) -> le mirror fidele est le filtre explicite
`(scene.hp(u) or 0) > 0` de `make_hammer_wrath_events` (engine/playbook/prediction/abilities.py).

POURQUOI CETTE GARDE EXISTE. Le filtre a ete pose en #57m apres une divergence MESUREE (54321 s8,
cadavre u95 hex-adjacent a la cible t93 : hp=0 -> `kill`/`killSure` vrais -> ~ +120 d'utilite FANTOME,
et l'argmax du port passait de t91 -- le choix NATIF -- a t93). Aucun test ne le retenait : le retirer
ne faisait rougir personne. La degradation est SILENCIEUSE (ni erreur, ni crash, juste une cible d'IA
differente), donc invisible en self-play -- exactement le profil qu'une garde doit couvrir.

Montage : fixture `hammer_corpse_case` (cf. `tests/engine/conftest.py` -> `probe_17_hammer_corpse`).
Positions DRIVEES, cadavre REEL (une unite tuee en bataille, pas des PV forces), etat LIVE lu par le
seam de decision. ASCII only."""
from __future__ import annotations

import probe_17_hammer_corpse as HC


def _assert_montage(c, label):
    """La garde ne vaut que si le scan NAIF verrait bien le cadavre : sinon on n'eprouve rien."""
    assert c["corpse_is_dead"], \
        f"[{label}] le sacrifiable u{c['corpse']} n'est pas mort -- pas de cadavre a filtrer"
    assert c["corpse_seen_by_naive_scan"], \
        (f"[{label}] le cadavre u{c['corpse']} @{c['corpse_pos']} n'est PAS hex-adjacent a la cible "
         f"u{c['target']} @{c['target_pos']} dans la scene (adjacents naifs={c['naive_adj']}) -- un "
         f"scan sans filtre ne l'aurait pas pris, la garde ne prouverait rien")
    assert (c["corpse_hp"] or 0) <= 0, \
        f"[{label}] le cadavre u{c['corpse']} porte hp={c['corpse_hp']} dans la scene (attendu 0/None)"
    assert (c["ghost_corpse_utility"] or 0) > 0, \
        (f"[{label}] l'event FANTOME du cadavre vaudrait {c['ghost_corpse_utility']} d'utilite : "
         f"un event a utilite nulle rendrait la garde vide de sens (rien a retirer)")


def _assert_no_corpse_event(c, label):
    got, exp = sorted(set(c["event_targets"])), c["expected_event_targets"]
    assert c["corpse"] not in c["event_targets"], \
        (f"[{label}] `make_hammer_wrath_events` a produit un event SECONDAIRE sur le CADAVRE "
         f"u{c['corpse']} @{c['corpse_pos']} (hp={c['corpse_hp']}, isDead=True) : events={got} "
         f"attendu={exp}. Le natif resout ses cibles secondaires par OCCUPATION DE TUILE "
         f"(`IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits` -> "
         f"`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`) : un mort n'occupe plus de "
         f"tuile. Cet event fantome vaut {c['ghost_corpse_utility']} d'utilite (Sigma du port "
         f"{c['sum_utility']}) -- c'est la regression #57m (54321 s8, cadavre u95, ~ +120).")
    assert got == exp, \
        (f"[{label}] set d'events divergent : {got} != attendu {exp} "
         f"(adjacents naifs={c['naive_adj']}, cadavre=u{c['corpse']}, temoin=u{c['witness']})")
    assert len(c["event_targets"]) == len(set(c["event_targets"])), \
        f"[{label}] events dupliques : {c['event_targets']}"


def test_hammer_corpse_not_a_secondary_target(hammer_corpse_case):
    """Regime `witness` : un CADAVRE et un TEMOIN VIVANT sont tous deux hex-adjacents a la cible.
    Le port doit rendre {cible, temoin} -- le temoin interdit de confondre « filtre correct » et
    « scan vide ». Verifie AUSSI l'instrument de magnitude : applique au temoin VIVANT il reproduit
    au bit pres l'event que le port a produit pour lui (sans quoi le chiffre du fantome ne veut
    rien dire)."""
    c = hammer_corpse_case("witness")
    _assert_montage(c, "witness")
    assert c["witness_seen_by_naive_scan"], \
        (f"[witness] le temoin u{c['witness']} @{c['witness_pos']} n'est pas adjacent a la cible : "
         f"le regime se confond avec `corpse-only`")
    _assert_no_corpse_event(c, "witness")
    assert c["port_witness_utility"] == c["probe_witness_utility"], \
        (f"[witness] l'INSTRUMENT du probe diverge du port sur le temoin VIVANT u{c['witness']} : "
         f"port={c['port_witness_utility']} probe={c['probe_witness_utility']} -- la magnitude "
         f"annoncee pour le fantome ({c['ghost_corpse_utility']}) n'est alors pas comparable")


def test_hammer_corpse_only_yields_no_secondary(hammer_corpse_case):
    """Regime `corpse-only` : le CADAVRE est le SEUL adjacent de la cible. Le port doit rendre le
    SEUL event principal -- la difference avec un scan non filtre est BINAIRE (0 secondaire contre 1),
    donc insensible a tout arbitrage de cap ou d'ordre."""
    c = hammer_corpse_case("corpse-only")
    _assert_montage(c, "corpse-only")
    assert not c["witness_seen_by_naive_scan"], \
        (f"[corpse-only] le temoin u{c['witness']} @{c['witness_pos']} est reste adjacent a la cible : "
         f"le regime n'isole plus le cadavre (adjacents naifs={c['naive_adj']})")
    _assert_no_corpse_event(c, "corpse-only")
    assert c["event_targets"] == [c["target"]], \
        (f"[corpse-only] events={c['event_targets']} : attendu le seul event PRINCIPAL "
         f"[{c['target']}] (aucun ennemi VIVANT n'est adjacent a la cible)")


def test_hammer_corpse_generalises_to_a_second_board(hammer_corpse_case):
    """GENERALISATION : le meme regime `corpse-only` sur un AUTRE couple board/seed/geometrie
    (MC1_63, seed 91117). Le filtre n'est pas un ajustement a une carte : la resolution par occupation
    de tuile est une propriete du selecteur natif, pas du terrain."""
    c = hammer_corpse_case("corpse-only", seed=91117, board="MC1_63")
    _assert_montage(c, "corpse-only/MC1_63")
    _assert_no_corpse_event(c, "corpse-only/MC1_63")
    assert c["event_targets"] == [c["target"]], \
        (f"[corpse-only/MC1_63] events={c['event_targets']} : attendu le seul event PRINCIPAL "
         f"[{c['target']}]")
    assert (c["board"], c["center"]) != ("MC1_67", (3, 4)), \
        (f"[corpse-only/MC1_63] montage rejoue sur la MEME geometrie que le cas de reference "
         f"({c['board']} {c['center']}) : la generalisation ne demontre rien")


def test_hammer_corpse_case_registry():
    """Les deux regimes du montage sont bien ceux que la fixture expose -- garde-fou contre un cas
    ajoute au probe et jamais exerce."""
    assert set(HC.CASES) == {"witness", "corpse-only"}, \
        f"regimes du montage #17 modifies : {HC.CASES} -- ajouter/retirer le test correspondant"
