"""#419-r1-tr14-r5-r2-r1 -- la branche TRAIT de la cascade d'attaque normale.

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` consulte TROIS sources, dans cet
ordre : `GetCustomNormalAttackTypeFromPassive` (`config@+0xa8`, 14 entrees, -r1), puis
`GetCustomNormalAttackTypeFromActive` (`config@+0xa0`, 1 entree, -r2), puis -- et seulement si les
deux ont rendu `null` -- un test de TRAIT, lu verbatim dans le meme `if/else` :

    else if (config.Traits.Contains(0x7e7)) { type = 0x406; state = activeAbilityState; }

`0x7e7` = 2023 = `Boss` (`IdunBattle.Entities.Enum.UnitTrait`) ; `0x406` = 1030 =
`Loki_NormalBossAttack` (`IdunBattle.Entities.Enum.ActiveAbilityType`).

CE QUE CE FICHIER GARDE -- six choses, aucune redondante :

  1. **LES DEUX LITTERAUX** (cran OFFLINE). Ni l'un ni l'autre ne s'infere d'un nom : `UnitTrait`
     porte AUSSI `Guild_Boss_01` (1045), `BossAdjutant_Old` (1040) et `MachineOfWar` (1049), et
     l'entier 1030 y designe `BeastSnagga`. Un litteral change sans repasser par la mesure rougit ici.
  2. **LA BRANCHE, contre le natif.** Une unite a qui l'on ECRIT `BC.Units[].Traits += [Boss]`, sans
     passif ni actif substituant, doit recevoir `Loki_NormalBossAttack` par le seul canal qui publie
     le resultat de la fabrique -- `decisionView.units[].abilities` `kind == "normal"`, c.-a-d.
     `ActiveAbilityComponent.NormalAttackType@0x28`.
  3. **LE RANG DANS LA CASCADE -- TROISIEME.** Deux bras ou le trait COEXISTE avec une source
     gagnante : `Traits += [Boss]` + `PassiveAbilities = [Boltstorm]` doit rendre
     `Boltstorm_NormalAttack`, et `Traits += [Boss]` + `ActiveAbilities = [PoundThemToDust]` doit
     rendre `RogalDorn_NormalAttack`. Ces bras ne prouvent rien seuls (les deux modeles y coincident
     quand le rang est juste) : ils BORNENT. Une branche TRAIT portee au mauvais rang y repondrait
     `Loki_NormalBossAttack` et les ferait rougir -- c'est la forme exacte de l'erreur qui valait
     +102 % sur la voie passive (#557).
  4. **LES TEMOINS.** Le bras `ctrl` est APPARIE au bras `boss` (memes unites, meme roster, meme
     board, meme seed : seuls les `BC.Units[].Traits` different), et une unite ne recoit JAMAIS le
     trait dans AUCUN des deux bras. Sans eux, un montage MORT rendrait des `69` partout et se
     lirait comme « la branche trait ne substitue pas ».
  5. **LE PORT SUR LES CANAUX DE PRODUCTION.** Le foyer n'est pas interroge sur une liste fabriquee
     a la main : il lit `UnitContext.traits` / `.passive_abilities` / `.active_abilities` tels que
     `scene.build_predictor` les seede, via `entity_trait_names`. Le cran confronte donc la CHAINE
     ENTIERE -- capteur, parsing, seed, foyer -- au champ que la fabrique ecrit. Il verifie AUSSI que
     le trait ECRIT est bien celui que le canal MESURE (et qu'il n'apparait nulle part ailleurs) :
     `combatSnapshot.units[].traits` est un SUR-ENSEMBLE de `UnitConfiguration.Traits`, donc ce
     controle est ce qui rend le canal utilisable.
  6. **LA CONTRE-EPREUVE MORD, ET SEULEMENT LA.** Branche TRAIT coupee (litteral rendu impossible =
     le port d'avant -r2-r1), la seule ligne qui bouge est `boss`/`preuve`, qui retombe sur
     `Loki_NormalAttack`. Un vert de (2) sans ce cran ne prouverait pas que c'est la branche TRAIT
     qui le produit ; l'inertie des SEPT autres est la RECIPROQUE -- un port qui deborderait ferait
     bouger les bras d'ordre.

⚠ Le trait `Boss` a SIX porteurs au gameconfig, **tous npc** -- les boss de GUILDE, pas des Machines
of War. Zero dans le pool : le montage ECRIT sur `BC.Units[].Traits` est le seul chemin de
confrontation, et c'en est un (meme levier que le volet `traits` de -r4, lui aussi a zero porteur).

Mesures et RE : `docs/rl/case-419-r1-tr14-r5-r2-r1-branche-trait.md`. ASCII only.
Probe jumeau : `scripts/python/probe_419r1tr14r5r2r1_trait_normal_attack.py`.
"""
from __future__ import annotations

import pytest

import probe_419r1tr14r5r2r1_trait_normal_attack as P
from engine.services.custom_normal_attack import NORMAL_BOSS_ATTACK, NORMAL_BOSS_ATTACK_TRAIT


@pytest.fixture(scope="module")
def trait_rows(rpc, tmp_path_factory, build_runner):
    """Les deux bras APPARIES (`boss` / `ctrl`) x quatre unites, natif ET port."""
    P.os.environ["A35_LOGS"] = str(tmp_path_factory.mktemp("tr14r5r2r1_trait"))
    try:
        return P.run_trait(rpc, lambda seed, extra: build_runner(seed, extra)["rid"],
                           verbose=False)
    except P.MontageError as e:
        pytest.fail(str(e), pytrace=False)


def _row(rows: list, arm: str, role: str) -> dict:
    hit = [r for r in rows if r.get("arm") == arm and r.get("role") == role]
    assert len(hit) == 1, f"bras {arm}/{role!r} attendu une fois, trouve {len(hit)}"
    return hit[0]


def test_les_deux_litteraux_de_la_branche_trait():
    """(1) Cran OFFLINE : `Traits.Contains(0x7e7)` -> `0x406`, qualifies enum par enum."""
    assert NORMAL_BOSS_ATTACK_TRAIT == "Boss", (
        f"le trait teste par `AddNormalAttackAbility` est `0x7e7` = 2023 = `Boss` dans "
        f"`IdunBattle.Entities.Enum.UnitTrait`, le port porte {NORMAL_BOSS_ATTACK_TRAIT!r}. "
        f"Le meme enum porte `Guild_Boss_01` (1045), `BossAdjutant_Old` (1040) et `MachineOfWar` "
        f"(1049) : la valeur se lit au decompile, elle ne s'infere pas d'un nom.")
    assert NORMAL_BOSS_ATTACK == "Loki_NormalBossAttack", (
        f"l'attaque posee est `0x406` = 1030 = `Loki_NormalBossAttack` dans "
        f"`IdunBattle.Entities.Enum.ActiveAbilityType`, le port porte {NORMAL_BOSS_ATTACK!r}. "
        f"⚠ 1030 designe `BeastSnagga` dans `UnitTrait` -- qualifier par l'enum n'est pas une "
        f"precaution de style.")


def test_le_trait_boss_substitue_l_attaque_normale(trait_rows):
    """(2) Bras `boss`/`preuve` : `Traits += [Boss]`, aucun passif ni actif substituant."""
    r = _row(trait_rows, "boss", "preuve")
    assert r["native"] == "Loki_NormalBossAttack", (
        f"{r['unit']} avec Traits contenant `Boss`, PassiveAbilities=[] et ActiveAbilities "
        f"d'origine : le natif rend {r['native']!r}, la branche TRAIT annonce "
        f"`Loki_NormalBossAttack`.")
    t = _row(trait_rows, "ctrl", "preuve")
    assert t["native"] == "Loki_NormalAttack", (
        f"TEMOIN APPARIE : la MEME unite, le MEME roster, le MEME board, le MEME seed, sans le seul "
        f"trait `Boss` doit retomber sur l'attaque normale generique -- elle rend {t['native']!r}. "
        f"C'est ce bras qui separe « le trait substitue » de « cette unite a toujours eu 1030 ».")


def test_la_branche_trait_est_la_troisieme_de_la_cascade(trait_rows):
    """(3) Les deux bras d'ORDRE, avec leurs controles apparies dans `ctrl`."""
    p = _row(trait_rows, "boss", "ordre-pas")
    assert p["native"] == "Boltstorm_NormalAttack", (
        f"{p['unit']} porte `Boss` ET `PassiveAbilities={p['passives']}` : le natif doit rendre "
        f"celle de la voie PASSIVE, il rend {p['native']!r}. `AddNormalAttackAbility` n'atteint le "
        f"test de trait que si les DEUX voies ont rendu `null`.")
    a = _row(trait_rows, "boss", "ordre-act")
    assert a["native"] == "RogalDorn_NormalAttack", (
        f"{a['unit']} porte `Boss` ET `ActiveAbilities={a['actives']}` : le natif doit rendre celle "
        f"de la voie ACTIVE, il rend {a['native']!r}. Le `else if` du trait est le `else` du test "
        f"`fromActive.HasValue`.")
    for role in ("ordre-pas", "ordre-act"):
        b, c = _row(trait_rows, "boss", role), _row(trait_rows, "ctrl", role)
        assert b["native"] == c["native"], (
            f"controle apparie {role} : ajouter le seul trait `Boss` a {b['unit']} a change "
            f"l'attaque normale ({c['native']!r} -> {b['native']!r}), alors qu'une source de rang "
            f"SUPERIEUR gagne dans les deux cas.")


def test_le_temoin_sans_trait_ne_bouge_dans_aucun_bras(trait_rows):
    """(4) L'unite qui ne recoit JAMAIS `Boss` -- dans le bras `boss` comme dans `ctrl`."""
    for arm in ("boss", "ctrl"):
        t = _row(trait_rows, arm, "temoin")
        assert t["trait_seen"] is False, (
            f"[{arm}] le TEMOIN {t['unit']} ne doit porter `Boss` dans AUCUN bras, le canal en "
            f"mesure un : le montage a deborde et le bras `boss` ne teste plus une seule variable.")
        assert t["native"] == "Loki_NormalAttack", (
            f"[{arm}] TEMOIN : {t['unit']} n'a aucune source substituante et doit rendre l'attaque "
            f"normale generique, il rend {t['native']!r}.")


def test_le_port_reproduit_le_natif_sur_les_huit_lignes(trait_rows):
    """(5) `custom_normal_attack` sur les canaux de PRODUCTION, contre le champ natif -- et le
    trait ECRIT est bien celui que le canal MESURE."""
    assert len(trait_rows) == 8, (
        f"les 2 bras x 4 unites sont requis, {len(trait_rows)} ligne(s) mesuree(s).")
    bad = [(r["arm"], r["role"], r["unit"], r["native"], r["port"]) for r in trait_rows
           if r["port"] != r["native"]]
    assert not bad, (
        "le foyer du port diverge du champ `ActiveAbilityComponent.NormalAttackType@0x28` sur "
        f"{bad} -- format (bras, role, unite, natif, port). Le port lit les MEMES canaux que la "
        "production, donc l'ecart accuse la chaine entiere : capteur, parsing, seed ou foyer.")
    canal = [(r["arm"], r["role"], r["unit"], r["trait_seen"], r["trait_wanted"]) for r in trait_rows
             if r["trait_seen"] != r["trait_wanted"]]
    assert not canal, (
        f"le trait ECRIT dans `BC.Units[].Traits` n'est pas celui que le canal MESURE : {canal} -- "
        f"format (bras, role, unite, vu, voulu). `combatSnapshot.units[].traits` est un SUR-ENSEMBLE "
        f"de `UnitConfiguration.Traits` (il inclut les traits accordes en bataille par "
        f"`AddTraitOperation$$AddTrait`) : sans ce controle, un `Boss` venu d'ailleurs produirait un "
        f"FAUX POSITIF, et un `Boss` non installe un faux negatif silencieux.")


def test_la_contre_epreuve_mord_sur_la_preuve_et_seulement_la(trait_rows):
    """(6) Branche TRAIT coupee = le port d'avant -r2-r1. Doit MORDRE sur `boss`/`preuve` et rester
    INERTE sur les sept autres -- l'inertie est la RECIPROQUE, elle borne le fix."""
    p = _row(trait_rows, "boss", "preuve")
    assert p["cut_bites"] is True, (
        "branche TRAIT coupee, le bras `boss`/`preuve` doit retomber sur `Loki_NormalAttack` : s'il "
        "ne bouge pas, ce n'est PAS la branche TRAIT qui produit le vert du cran (2), et le montage "
        "ou le canal est a re-examiner.")
    debords = [f"{r['arm']}/{r['role']}" for r in trait_rows
               if r["cut_bites"] and not (r["arm"] == "boss" and r["role"] == "preuve")]
    assert not debords, (
        f"la contre-epreuve MORD aussi sur {debords}, alors que ces lignes ne passent pas par la "
        f"branche TRAIT : le port DEBORDE (il laisse le trait decider la ou une voie de rang "
        f"superieur doit gagner, ou il substitue sur une unite sans le trait).")
