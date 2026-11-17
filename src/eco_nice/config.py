"""Project-wide parameters. Every assumption lives here so it can be discussed and tuned."""

# --- Level-off detection (descent) ---------------------------------------
# Inspired by the EUROCONTROL CDO methodology: a "level segment" is a period
# where |vertical rate| stays below a threshold for a minimum duration.
LEVEL_VS_THRESHOLD_FPM = 300      # |VS| below this = flying level
LEVEL_MIN_DURATION_S = 20         # shorter plateaus are ignored
LEVEL_MIN_ALT_FT = 1_500          # ignore the final approach / ILS plateau
LEVEL_MAX_ALT_FT = 30_000         # ignore cruise
TOP_OF_DESCENT_MARGIN_FT = 500    # descent starts at the LAST point within 500 ft of the max altitude
MAX_GAP_S = 60                    # a data gap longer than this breaks a segment

# --- Fuel & emissions --------------------------------------------------------
LANDING_MASS_RATIO = 0.90         # assumed landing mass = 90% of MLW (no load data)
IDLE_DESCENT_VS_FPM = -1_500      # reference "continuous descent" vertical rate
CO2_PER_KG_FUEL = 3.16            # ICAO standard factor, kg CO2 / kg jet fuel
