"""#603 -- DECISIONS de FOYER/BLOCAGE des 176 residus, etablies par LECTURE de chaque fiche.

#603 -- FOYER/BLOCAGE des 176 residus non annotes, etablis par LECTURE de chaque fiche.

 POURQUOI CE FICHIER EXISTE. La derivation MECANIQUE est REFUTEE, et c'est mesure :
 `probe_603_index_foyers.py --calibrer` rend, sur les 107 fiches deja annotees a la main dont
 le foyer est non vide, un accord EXACT de 2/107 pour la meilleure source, avec 19 a 50 FAUX
 selon la source. Le foyer n'est pas dans le texte : les chemins du foyer humain apparaissent
 VERBATIM dans le corps pour 3 fiches sur 107. Ce fichier est donc le produit d'une LECTURE,
 et il est versionne pour que l'ecriture soit REJOUABLE et AUDITABLE, pas pour etre re-derive.

 SENS DE L'ERREUR -- ON SUR-LISTE, JAMAIS ON SOUS-LISTE. Le foyer sert a prouver la
 DISJONCTION de deux tranches avant de les dispatcher ensemble. Un foyer SURESTIME rend une
 fausse collision (cout : un appariement refuse) ; un foyer SOUS-ESTIME rend une fausse
 disjonction (cout : deux agents sur le meme fichier, exactement ce que le champ existe pour
 eviter). L'asymetrie est totale, donc le doute se resout du cote LARGE -- meme regle que le
 DECLENCHEUR d'un cliquet.

 COLONNES : ident <TAB> foyer <TAB> blocage <TAB> source
   foyer   : chemins separes par des virgules, ou `aucun`, ou `?`, ou `livree`
             `?`      = la fiche elle-meme dit que le foyer depend d'une mesure NON FAITE.
                        C'est un RESULTAT, pas un abandon (meme convention que la PR #815).
             `aucun`  = residu d'arbitrage ou de mesure : rien a editer.
             `livree` = la fiche est LIVREE mais sa 1re cellule n'est pas barree : elle ne
                        doit PAS recevoir de champs, elle doit etre FERMEE. Bac visible.
   blocage : capteur > seeding > etage > porteur > aucun (le plus haut qui s'applique)
   source  : fiche        = le corps de la fiche nomme le foyer ou le designe sans ambiguite
             fiche+depot  = le corps designe un symbole/module, chemin LOCALISE dans le depot
             indetermine  = ni l'un ni l'autre

POURQUOI UN MODULE PYTHON ET PAS UN `.tsv`
-------------------------------------------
Mesure du 2026-08-10 : `probe_457 --since` traite tout fichier NON-`.py` de `scripts/`
ET de `scripts/python/` comme une lecture GLOBALE (voie `dirs_glob`), donc il rendait
<< TOUT rejoue -- 294 fichiers, cout mesure ~1755 s >> pour une PR dont le diff Python
tient en 4 fichiers. Un diff purement Python, lui, ne declenche JAMAIS le TOUT-rejeu
(mesure de `probe_457` sur 40 commits reels : 0 dans les deux regimes). La donnee vit
donc en Python -- meme forme que `NON_VERTS_DECLARES` de `probe_547`.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

#: `(ident, foyer, blocage, source)` -- cf. la docstring pour le sens de chaque colonne.
DECISIONS: tuple[tuple[str, str, str, str], ...] = (
    ("#523-r3", "scripts/python/probe_523r1_heavy_warp_flamer_tracking.py", "aucun", "fiche"),
    ("#519-r1", "scripts/python/probe_519_temoins_de_camp.py", "aucun", "fiche"),
    ("#511-r1", "scripts/python/probe_511_strike_from_the_shadows.py", "aucun", "fiche"),
    ("#489-r1", "scripts/python/engine/runner/abilities/behaviours/combat.py,scripts/python/engine/runner/operations/damage_ops/ability.py", "aucun", "fiche+depot"),
    ("#488-r2", "scripts/python/probe_488r1_onmelta_vivant.py,scripts/python/engine/runner/operations/damage_ops/ability.py", "aucun", "fiche+depot"),
    ("#486-r16", "scripts/python/declencheur_cliquet.py,scripts/python/probe_486r12_declencheurs.py,scripts/python/verdict_cache.py", "aucun", "fiche+depot"),
    ("#486-r9", "scripts/python/probe_273_gitignored_inputs.py,scripts/python/verdict_cache.py", "aucun", "fiche+depot"),
    ("#486-r17", "scripts/python/import_closure.py,scripts/python/verdict_cache.py,scripts/python/probe_485_imports_differes.py,scripts/python/probe_273_gitignored_inputs.py", "aucun", "fiche+depot"),
    ("#486-r10", "scripts/python/il2cpp_metadata.py", "aucun", "fiche+depot"),
    ("#486-r20", "scripts/python/tests/,scripts/python/probe_486r15_declencheurs_tests.py", "aucun", "fiche"),
    ("#486-r21", "scripts/python/probe_486r15_declencheurs_tests.py,scripts/python/probe_457_offline_tests_green.py", "aucun", "fiche"),
    ("#486-r8", "scripts/python/verdict_cache.py", "aucun", "fiche+depot"),
    ("#390-r1", "perime", "aucun", "fiche+depot"),
    ("#484-r1", "scripts/python/probe_366_r1_bcpatch_port_blindspot.py", "aucun", "fiche"),
    ("#484-r2", "scripts/python/tests/engine/test_270r4r2r2_differes_offline.py", "aucun", "fiche"),
    ("#287-r11", "scripts/python/engine/runner/abilities/loki/attempted_possession.py,scripts/python/engine/runner/abilities/targeting.py,scripts/python/probe_287r5_etages_bloquants.py", "seeding", "fiche"),
    ("#287-r5-r2", "scripts/python/engine/runner/components.py,scripts/python/engine/runner/snapshot.py,frida/hooks/features/observe.ts", "capteur", "fiche"),
    ("#485-r1-r2", "scripts/python/prototype_485r1_registre_explicite.py,scripts/python/engine/playbook/__init__.py,scripts/python/engine/runner/abilities/loki/__init__.py,scripts/python/engine/runner/operations/triggers/loki/__init__.py,scripts/python/engine/utilities/__init__.py", "aucun", "fiche+depot"),
    ("#485-r1-r3", "scripts/python/migrate_485r1_barils_reexport.py,scripts/python/engine/", "aucun", "fiche"),
    ("#485-r1-r4", "scripts/python/engine/runner/abilities/loki/__init__.py,scripts/python/engine/runner/operations/damage_ops/__init__.py,scripts/python/engine/runner/abilities/__init__.py,scripts/python/engine/playbook/__init__.py", "aucun", "fiche"),
    ("#485-r1-r1-r2", "scripts/python/probe_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable.py", "aucun", "fiche+depot"),
    ("#486-r3", "scripts/python/probe_486r2_usage_des_probes.py,scripts/python/", "aucun", "fiche"),
    ("#486-r4", "scripts/ratchets.ps1,scripts/python/probe_468_collision_numeros.py", "aucun", "fiche"),
    ("#482-r1", "scripts/python/fingerprint_functions.py", "seeding", "fiche"),
    ("#482-r2", "scripts/python/fingerprint_functions.py", "aucun", "fiche"),
    ("#482-r5", "scripts/python/build_fingerprint_archive.py", "aucun", "fiche"),
    ("#482-r6", "aucun", "aucun", "fiche"),
    ("#482-r4", "scripts/python/fingerprint_functions.py", "aucun", "fiche"),
    ("#448-r3-r1-r1-r1", "scripts/python/engine/runner/snapshot.py,scripts/python/rl_duel.py,scripts/python/catalog_inject.py", "seeding", "fiche"),
    ("#509-r1", "scripts/python/engine/runner/operations/triggers/loki/,scripts/python/engine/runner/operations/triggers/dispatch/registry.py", "aucun", "fiche"),
    ("#475-r1", "scripts/python/probe_475_pinned_addresses.py", "aucun", "fiche+depot"),
    ("#475-r2", "frida/hooks/il2cpp/build-pin.ts,frida/hooks/features/modifier-observe.ts", "capteur", "fiche"),
    ("#475-r3", "frida/hooks/features/bucket-audit.ts", "capteur", "fiche"),
    ("#469-r2", "scripts/ratchets.ps1", "aucun", "fiche"),
    ("#469-r1", "aucun", "aucun", "fiche"),
    ("#469-r4", "aucun", "aucun", "fiche"),
    ("#471-r1", "?", "aucun", "fiche"),
    ("#471-r2", "aucun", "aucun", "fiche"),
    ("#468-r5", "docs/rl/backlog.md,scripts/ratchets-468-numeros-attestes.json", "aucun", "fiche"),
    ("#468-r6", "scripts/python/tests/test_431_build_pin_offline.py,scripts/python/probe_440_repo_root_scan_guard.py", "aucun", "fiche"),
    ("#468-r7", "scripts/python/probe_468_collision_numeros.py", "aucun", "fiche"),
    ("#468-r8", "CLAUDE.md,scripts/python/probe_468_collision_numeros.py", "aucun", "fiche"),
    ("#468-r2", "scripts/python/probe_468_collision_numeros.py", "aucun", "fiche"),
    ("#468-r3", "scripts/python/probe_468_collision_numeros.py", "aucun", "fiche"),
    ("#468-r1", "scripts/python/probe_468_collision_numeros.py", "aucun", "fiche"),
    ("#467-r1", "scripts/python/loop_status.py", "aucun", "fiche"),
    ("#467-r3", "scripts/hooks/loop-status.ps1", "aucun", "fiche"),
    ("#467-r4-a", "scripts/python/probe_467r4_contrat_host.py", "aucun", "fiche"),
    ("#467-r6-a", "scripts/python/loop_status.py", "aucun", "fiche"),
    ("#467-r5", "scripts/python/loop_status.py,scripts/hooks/loop-status.ps1", "aucun", "fiche"),
    ("#462-r1", "scripts/python/probe_462_live_tests_status.py", "aucun", "fiche+depot"),
    ("#462-r2", "scripts/python/probe_462_live_tests_status.py", "aucun", "fiche+depot"),
    ("#465-r1", "scripts/python/probe_462_live_tests_status.py", "porteur", "fiche+depot"),
    ("#462-r3", "scripts/python/probe_462_live_tests_status.py", "aucun", "fiche+depot"),
    ("#462-r4c-r1-r1", "scripts/python/probe_242_fabricator_claw_cap.py", "aucun", "fiche"),
    ("#462-r4c-r1-r2", "aucun", "aucun", "fiche"),
    ("#462-r4c-r2", "scripts/python/probe_230_load_state_turn_state.py", "aucun", "fiche+depot"),
    ("#462-r4c-r3", "scripts/python/probe_365_versioned_imports_gitignored.py", "aucun", "fiche"),
    ("#462-r6-r1", "aucun", "aucun", "fiche"),
    ("#462-r6-r2", "scripts/python/tests/engine/", "aucun", "fiche"),
    ("#462-r4", "scripts/python/probe_462_live_tests_status.py,scripts/python/tests/engine/runner/test_pick_randomly_one_rng_live.py", "aucun", "fiche"),
    ("#462-r4e-o-r1-r1-r1", "scripts/python/engine/runner/operations/left_over_damage.py", "porteur", "fiche"),
    ("#462-r4e-o-r2-r1-r1-r1-r1", "frida/hooks/features/observe.ts,scripts/python/engine/runner/operations/turnflow.py", "capteur", "fiche"),
    ("#462-r4e-o-r2-r1-r1-r1-r2", "scripts/python/engine/runner/operations/turnflow.py", "capteur", "fiche"),
    ("#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2", "?", "aucun", "fiche"),
    ("#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r1", "frida/hooks/features/observe.ts,scripts/python/engine/runner/components.py", "capteur", "fiche"),
    ("#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4", "scripts/python/engine/runner/operations/triggers/loki/haywire_mine.py", "porteur", "fiche"),
    ("#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5", "scripts/python/engine/runner/operations/triggers/loki/haywire_mine.py,scripts/python/engine/runner/operations/movement.py", "aucun", "fiche"),
    ("#462-r4b-r1-r1-r1-r1-c-r3-r1-r6", "scripts/python/engine/runner/operations/revive.py,scripts/python/engine/runner/operations/movement.py", "aucun", "fiche"),
    ("#462-r4b-r1-r1-r1-r1-c-r3-r2", "scripts/python/engine/runner/operations/triggers/dispatch/core.py", "porteur", "fiche"),
    ("#462-r4b-r1-r1-r1-r1-c-r3-r3", "scripts/python/engine/runner/operations/triggers/dispatch/core.py", "aucun", "fiche"),
    ("#457-r6", "scripts/python/probe_457_offline_tests_green.py,scripts/ratchets.ps1", "aucun", "fiche"),
    ("#464-r1b", "scripts/python/gen_ai_targets.py,scripts/python/gen_battlelogic_targets.py,scripts/python/gen_campaign_builder_targets.py,scripts/python/gen_full_game_targets.py,scripts/python/probe_273_gitignored_inputs.py", "aucun", "fiche+depot"),
    ("#464-r1c", "scripts/python/probe_273_gitignored_inputs.py", "aucun", "fiche+depot"),
    ("#463-r2", "scripts/python/tests/test_457_r5_perimetre_offline.py", "aucun", "fiche+depot"),
    ("#455-r1", "scripts/python/probe_455_all_skipped_file.py", "aucun", "fiche+depot"),
    ("#455-r2", "scripts/python/tests/conftest.py", "aucun", "fiche+depot"),
    ("#455-r4-r1", "scripts/python/probe_455r4_resilient_window.py", "aucun", "fiche"),
    ("#449-r1", "frida/hooks/features/ai-step/rpc-nc-predict.ts", "capteur", "fiche"),
    ("#449-r2-r1", "scripts/python/probe_449r2_spread_inventory.py", "aucun", "fiche+depot"),
    ("#449-r2-r3", "scripts/python/probe_449r2_spread_inventory.py", "aucun", "fiche+depot"),
    ("#449-r2-r4-r1", "scripts/python/engine/services/damage_config.py,scripts/python/rl_duel.py", "seeding", "fiche"),
    ("#449-r2-r4-r2", "scripts/python/tests/engine/", "aucun", "fiche"),
    ("#449-r2-r4-r3", "scripts/python/engine/services/damage_config.py,scripts/python/engine/utilities/damage.py", "porteur", "fiche+depot"),
    ("#449-r2-r4-r4-r1", "scripts/python/probe_449r2r4r4_bc_damage_fields.py", "aucun", "fiche+depot"),
    ("#449-r3", "scripts/python/engine/runner/operations/attack_prediction.py", "aucun", "fiche"),
    ("#429-r1-r1-r1-r1", "scripts/python/engine/runner/abilities/behaviours/ai_control.py,scripts/python/engine/runner/abilities/loki/summon.py", "aucun", "fiche+depot"),
    ("#429-r1-r3-r1-r2-r1", "scripts/python/engine/runner/operations/behaviour.py,scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py", "aucun", "fiche+depot"),
    ("#429-r1-r2", "scripts/python/probe_429r1_bit_readers_scan.py", "aucun", "fiche"),
    ("#447-r1-r1-r1", "scripts/python/engine/services/ability_range.py", "porteur", "fiche"),
    ("#447-r1-r1-r2", "scripts/python/engine/runner/abilities/targeting_rule_inventory.py,scripts/python/engine/runner/abilities/targeting.py", "aucun", "fiche"),
    ("#447-r2", "scripts/python/targeting_reason.py", "aucun", "fiche"),
    ("#447-r3", "aucun", "porteur", "fiche"),
    ("#447-r4", "scripts/python/engine/runner/abilities/targeting.py", "aucun", "fiche"),
    ("#444-r1", "frida/hooks/features/ai-step/rpc-targeting.ts", "capteur", "fiche"),
    ("#444-r2", "scripts/python/engine/services/targeting_query.py", "etage", "fiche"),
    ("#456-r2-r1", "scripts/python/engine/playbook/savior_protocols.py", "aucun", "fiche"),
    ("#433-r4-r1-r2", "scripts/python/engine/runner/abilities/loki/wall_of_mirrors.py", "porteur", "fiche"),
    ("#433-r4-r1-r3", "scripts/python/engine/runner/abilities/loki/mv71.py", "etage", "fiche"),
    ("#433-r4-r1-r4-r2-r2", "scripts/python/engine/playbook/noncomparable/heroic_fusillade.py", "aucun", "fiche"),
    ("#433-r4-r1-r4-r2-r3", "scripts/python/probe_433r4r1r4r2_is_adjacent_substrat_live.py", "aucun", "fiche+depot"),
    ("#433-r4-r1-r4-r2-r4-r1", "scripts/python/probe_433r4r1r4r2r4_aval_decision_live.py", "aucun", "fiche"),
    ("#433-r4-r2-r1-r1-a-r1", "frida/hooks/features/ai-step/,scripts/python/engine/ai/context.py", "capteur", "fiche"),
    ("#433-r4-r2-r1-r1-b", "frida/hooks/features/ai-step/,scripts/python/engine/services/ability_range.py", "capteur", "fiche"),
    ("#433-r4-r2-r1-r1-c-r1", "frida/hooks/features/ai-step/,scripts/python/engine/services/ability_caster_gates.py", "capteur", "fiche"),
    ("#433-r4-r2-r1-r1-c-r2", "scripts/python/engine/ai/context.py", "aucun", "fiche"),
    ("#433-r4-r2-r1-r2-r2-r1-r1-r1-r3", "scripts/python/engine/services/ability_range.py", "porteur", "fiche"),
    ("#433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1", "scripts/python/engine/ai/context.py,scripts/python/engine/services/ability_range.py", "aucun", "fiche"),
    ("#433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2", "scripts/python/engine/services/ability_caster_gates.py", "porteur", "fiche"),
    ("#433-r4-r2-r4-r1-r1", "scripts/python/probe_433_r4_r2_r4_r1_contre_epreuves.py", "aucun", "fiche"),
    ("#433-r4-r2-r1-r2-r3", "scripts/python/engine/services/targeting_query.py", "seeding", "fiche"),
    ("#433-r4-r2-r1-r3", "frida/hooks/features/ai-step/,scripts/python/engine/services/ability_caster_gates.py", "capteur", "fiche"),
    ("#433-r4-r2-r3", "scripts/python/engine/playbook/noncomparable/early_warning_override.py", "aucun", "fiche"),
    ("#433-r4-r3-r1-r1", "scripts/python/engine/playbook/non_owner.py", "aucun", "fiche"),
    ("#433-r4-r3-r1-r2", "scripts/python/engine/playbook/non_owner_attack.py,scripts/python/engine/playbook/non_owner.py", "etage", "fiche"),
    ("#433-r4-r3-r1-r3", "scripts/python/catalog_inject.py", "aucun", "fiche"),
    ("#433-r4-r3-r2", "scripts/python/engine/playbook/", "aucun", "fiche"),
    ("#433-r4-r3-r3", "scripts/python/engine/ai/context.py,scripts/python/engine/playbook/savior_protocols.py", "aucun", "fiche"),
    ("#437-r1-r1-r1-r1", "scripts/python/probe_437r1r1r1_effect_face_table.py", "aucun", "fiche+depot"),
    ("#437-r1-r1-r2", "scripts/python/engine/services/damage_modifiers.py", "porteur", "fiche"),
    ("#437-r1-r1-r3", "scripts/python/probe_437r1_overwatch_offbyone.py", "aucun", "fiche"),
    ("#434-r3", "scripts/ratchets.ps1", "aucun", "fiche"),
    ("#430-r1", "scripts/ratchets.ps1", "aucun", "fiche"),
    ("#430-r2", "scripts/ratchets.ps1", "aucun", "fiche"),
    ("#426-r1", "scripts/python/probe_229_effect_triggers_active.py,scripts/python/probe_249_unported_rule_carriers.py,scripts/python/probe_283_enum_ordinal_sweep.py", "aucun", "fiche"),
    ("#419-r1", "scripts/python/engine/playbook/", "aucun", "fiche"),
    ("#419-r1-tr14-r2", "scripts/python/engine/playbook/prediction/normal_attack.py", "porteur", "fiche"),
    ("#419-r1-tr14-r4-r3", "scripts/python/engine/services/battle_query.py", "porteur", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r1-r1", "scripts/python/engine/playbook/should_execute_gates.py", "aucun", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r1-r2", "scripts/python/engine/playbook/common.py", "porteur", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r2-r1-r1-r1", "scripts/python/engine/services/ability_range.py", "aucun", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r2-r1-r1-r2", "scripts/python/engine/services/ability_range.py", "porteur", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1", "scripts/python/engine/services/ability_range.py", "porteur", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r2-r1-r2", "frida/hooks/features/observe.ts,scripts/python/engine/runner/components.py", "capteur", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r2-r1-r3", "aucun", "porteur", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r2-r2", "scripts/python/engine/runner/abilities/targeting.py", "aucun", "fiche"),
    ("#419-r1-tr14-r5-r2-r1-r2-r3", "docs/", "aucun", "fiche"),
    ("#419-r1-tr14-r5-r3", "scripts/python/engine/services/custom_normal_attack.py", "porteur", "fiche"),
    ("#419-r1-tr12-r2-r2", "scripts/python/probe_419r1tr12r2_stats_npc_summon.py", "porteur", "fiche+depot"),
    ("#419-r1-tr12-r2-r1", "scripts/python/catalog_inject.py", "etage", "fiche"),
    ("#419-r1-tr12-r3", "scripts/python/engine/services/custom_normal_attack.py,scripts/python/engine/runner/abilities/", "aucun", "fiche"),
    ("#419-r1-tr12-r4", "aucun", "porteur", "fiche"),
    ("#419-r1-tr9-r1", "scripts/python/engine/ai/context.py", "seeding", "fiche"),
    ("#419-r1-tr9-r4-r1-r2-r1a", "scripts/python/engine/services/static_battle_rules.py,scripts/python/engine/entities/effects/loki/hits.py", "aucun", "fiche+depot"),
    ("#419-r1-tr9-r4-r1-r2-r1b", "scripts/python/engine/runner/operations/refresh_effects.py,scripts/python/engine/entities/effects/loki/extra_damage_aura.py", "aucun", "fiche"),
    ("#419-r1-tr9-r4-r1-r2-r1c", "scripts/python/engine/runner/operations/triggers/dispatch/registry.py", "aucun", "fiche"),
    ("#419-r1-tr9-r4-r1-r2-r2", "scripts/python/engine/entities/effects/loki/hits.py", "porteur", "fiche"),
    ("#419-r1-tr9-r4-r1-r3", "scripts/python/engine/", "aucun", "fiche"),
    ("#419-r1-tr9-r4-r3", "scripts/python/engine/runner/operations/additional_hits.py", "aucun", "fiche"),
    ("#419-r1-tr9-r5", "scripts/python/rl_duel.py", "aucun", "fiche"),
    ("#419-r1-tr11-r1", "scripts/python/engine/ai/context.py", "aucun", "fiche"),
    ("#419-r1-tr11-r2", "frida/hooks/features/ai-step/", "capteur", "fiche"),
    ("#445-r1", "scripts/python/engine/playbook/base.py", "porteur", "fiche"),
    ("#438-r1", "scripts/python/engine/playbook/base.py", "aucun", "fiche"),
    ("#443-r2-b2", "scripts/python/engine/runner/operations/triggers/dispatch/registry.py", "etage", "fiche"),
    ("#419-r4", "scripts/python/engine/runner/operations/damage_hits.py", "etage", "fiche"),
    ("#446-r3a", "scripts/python/engine/runner/operations/damage_ops/", "porteur", "fiche"),
    ("#419-t6-r1", "scripts/python/catalog_inject.py", "porteur", "fiche"),
    ("#419-r2", "scripts/python/engine/playbook/", "porteur", "fiche"),
    ("#448-r2d-r2", "scripts/python/engine/runner/abilities/,scripts/python/engine/entities/pathfinding/teleport_pathfinder.py", "aucun", "fiche"),
    ("#448-r1-r1-r1-r1-r2-r1", "scripts/python/engine/entities/pathfinding/pathfinders.py,scripts/python/engine/entities/pathfinding/base_pathfinder.py", "aucun", "fiche"),
    ("#448-r1-r1-r1-r1-r2-r2", "scripts/python/engine/entities/pathfinding/base_pathfinder.py,scripts/python/engine/entities/pathfinding/fly_pathfinder.py", "porteur", "fiche"),
    ("#589-r1-r1-r2-r1-r1", "scripts/python/engine/runner/operations/spawn.py", "aucun", "fiche"),
    ("#589-r1-r1-r2-r1-r3", "scripts/python/engine/services/damage_prediction.py", "aucun", "fiche"),
    ("#448-r1-r1-r3", "scripts/python/engine/runner/operations/movement.py", "aucun", "fiche"),
    ("#425-r1", "scripts/python/engine/ai/context.py", "porteur", "fiche"),
    ("#380-r1", "scripts/python/catalog_inject.py", "aucun", "fiche"),
    ("#389-r3", "scripts/python/engine/entities/effects/base.py,frida/hooks/il2cpp/", "capteur", "fiche"),
    ("#389-r4", "scripts/python/engine/runner/operations/remove_unit.py,scripts/python/engine/runner/operations/remove_effects.py", "aucun", "fiche"),
    ("#389-r5", "scripts/python/probe_389r2_kill_unit_remove_effects.py", "aucun", "fiche"),
    ("#273-r", "scripts/python/host_inputs.py,scripts/node/verify_portraits.mjs,frida/host/ai-trace-store.ts", "capteur", "fiche"),
    ("#277-r1", "scripts/python/tests/engine/,scripts/python/", "aucun", "fiche"),
    ("#259-a", "scripts/python/probe_259_gshared_coverage.py", "capteur", "fiche"),
    ("#259-b", "frida/hooks/il2cpp/,scripts/python/probe_262_gshared_runtime.py", "capteur", "fiche"),
    ("#BL-1020r", "livree", "aucun", "fiche"),
    ("#120bis-spawn", "livree", "aucun", "fiche"),
)
