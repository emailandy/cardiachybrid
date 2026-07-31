"""
These are defects in the source dictionary; fix in REDCap first,
then flip the flag. Mismatched logic makes fields vanish on import.
"""

BRANCHING_OVERRIDES = {
    "sono_window_cci_1": ("[reason_cci_2_v2(4)] = '1'",
                          "[reason_cci_1_v2(4)] = '1'"),   # RC-1041
    "rhythm_rosc_15_v2": ("[num_rosc_episodes_ed_v2] >15",
                          "[num_rosc_episodes_ed_v2] >=15"), # RC-1042
}
APPLY_OVERRIDES = False
