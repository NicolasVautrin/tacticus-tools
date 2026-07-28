"""Helper REUTILISABLE : le regime « K ENNEMIS ADJACENTS AU CASTER » et son replay-diff.

Beaucoup d'abilities SELF-CENTREES (le set de cibles est `AdjacentEnemies(caster)`, pas la cible du
message) exigent la MEME geometrie et les MEMES precautions -- et c'est exactement la geometrie qui
manquait aux fixtures existantes : `_ringed_cast` centre l'anneau sur la CIBLE, `_ability_cast_replay`
place une cible a distance choisie. Ici c'est le CASTER qui est au centre, et le nombre `k` d'ennemis
a son contact est LE parametre de la mecanique.

Ce que le montage garantit, et pourquoi chaque point compte (chacun a ete PAYE par une mesure) :

  * **le caster NE BOUGE PAS** -- on amene les ennemis a lui. Consequence : AUCUN `endturn` n'est
    necessaire, donc l'IA adverse ne joue JAMAIS. Avec des `endturn`, elle castait ses propres
    abilities (`Doom_extraDmg` observe sur une cible) et posait des effets qui changeaient le degat.
  * **la geometrie EFFECTIVE est re-verifiee apres les placements** : un summon adverse peut
    apparaitre sur une tuile libre du ring 1 et entrer dans `AdjacentEnemies` (mesure :
    `genesSmnDecoy`, invoque quand `genesMagus` se deplace). Le montage REFUSE alors le regime
    plutot que de mesurer une geometrie qu'il croit avoir posee.
  * **le caster est verifie dans `toActivate`** avant le cast : un cast hors-tour est refuse EN
    SILENCE (`ok=True`, aucune mutation) -- signature IDENTIQUE au no-op qu'on veut mesurer.
  * **le roster adverse est choisi sans AURA d'equipe** : `unit_map.py vanilla-target` ne regarde que
    ce qu'une unite s'applique A ELLE-MEME -- il ne voit RIEN de ce qu'un ALLIE lui donne, et c'est
    la lecon durable du cas `tauAunShi` (les DEUX cibles portaient `SereneUnifierSenseOfStone` et le
    degat LIVE valait EXACTEMENT la moitie de l'offline). ⚠ Le VOLET « effet non porte » de ce cas
    est CLOS depuis #192 : 1169 a desormais sa classe (`SereneUnifierSenseOfStoneEffect`,
    `loki/damage_reduction.py`) et l'agrement est bit-exact avec Aun'Shi en jeu. Le critere de choix
    du roster, lui, reste valable : un banc doit rester exempt d'aura d'equipe **non portee**, et le
    test de cette propriete n'est pas `vanilla-target` mais la lecture des effets CAPTES sur les
    cibles au moment de la mesure.

Le montage lui-meme vit dans `scripts/python/probe_murderous_swing_1137.py` (invocable en ligne de
commande) ; cette fixture n'en est que la PORTE pytest -- meme forme que `psychic_aoe_case` /
`overkill_gate_case` dans le `conftest.py` de la tranche.

Usage :

    from _adjacent_swing_regime import adjacent_swing_regime   # noqa: F401  (fixture)

    def test_x(adjacent_swing_regime):
        r = adjacent_swing_regime(k=2)
        ...  # r["live_damage"], r["last"], r["snapshot"], r["board"], r["adjacent"], ...

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

import probe_murderous_swing_1137 as MS
from engine.runner.snapshot import load_state


@pytest.fixture(scope="module")
def adjacent_swing_regime(live_session):
    """Fabrique : `adjacent_swing_regime(k=2, hp=500000)` -> le dict de mesure du probe.

    Portee MODULE et CACHE par `(k, hp, which, seed)` : chaque regime = un build + des placements +
    un cast LIVE, on ne le repaie pas d'un test a l'autre. `live_session` est tire ICI (le montage
    exige la session Frida) ; le runner est DISPOSE par le probe en sortie de `run()`.

    `which` = indices des ennemis a amener au contact (l'ordre d'attaque est l'id croissant) ;
    `hp` = `--hp-target` du build, le levier qui decide QUI meurt -- donc le seul moyen d'exposer
    au LIVE une bascule de regime interne au cast."""
    cache: dict = {}

    def _case(k: int = 1, hp: int = 500000, which=None, seed: int = 20137) -> dict:
        key = (int(k), int(hp), tuple(which) if which else None, int(seed))
        if key not in cache:
            r = MS.run(int(k), int(seed), int(hp), verbose=True,
                       which=list(which) if which else None)
            if "error" in r:
                pytest.skip("montage adjacent-swing KO (k=%s hp=%s): %s" % (k, hp, r["error"]))
            cache[key] = r
        return cache[key]
    return _case


def offline_state(r: dict):
    """Reconstruit un `State` OFFLINE NEUF depuis le snapshot PRE-cast du regime, MT cale sur le
    MEME tirage que le cast LIVE. Rejouable a volonte (aucun partage de mutation)."""
    s = r["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=r["board"])
    if isinstance(s["rng"], dict) and s["rng"].get("mt"):
        st.rng = MS.seed_rng(s["rng"])
    return st


def assert_live_mutated(r: dict):
    """PIEGE DE HARNAIS : `applyAction` peut rendre `ok=True` SANS rien muter (unite hors
    `toActivate`, tour bascule...). La signature est IDENTIQUE au no-op qu'on veut mesurer -> on
    exige que le NATIF, lui, ait mute avant de conclure quoi que ce soit sur le port."""
    if not r.get("live_ok"):
        pytest.skip("cast live refuse par le natif (montage)")
    if not r.get("live_mutated"):
        pytest.skip("cast live NON MUTANT (montage) : events=%s -- ce n'est PAS le no-op mesure"
                    % r.get("live_events"))
