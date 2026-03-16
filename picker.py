import json
import random
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_json(filename):
    with open(os.path.join(SCRIPT_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)

def load_bracket():
    """Load a fresh copy of bracket data (so retries don't use mutated state)."""
    return load_json("bracket.json")

RIVALRIES = load_json("rivalries.json")
BLUE_BLOODS = load_json("blue_bloods.json")

POWER_CONFERENCES = set(BLUE_BLOODS["power_conferences"])
TIER1_BLUE_BLOODS = {t["team"] for t in BLUE_BLOODS["blue_bloods"]["tier1"]}
TIER2_BLUE_BLOODS = {t["team"] for t in BLUE_BLOODS["blue_bloods"]["tier2"]}

RIVALRY_MAP = {}
RIVALRY_NOTES = {}
for r in RIVALRIES["rivalries"]:
    key = frozenset({r["team1"], r["team2"]})
    RIVALRY_MAP[key] = r["intensity"]
    RIVALRY_NOTES[key] = r.get("note", "")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_WEIGHT = 0.90
MIN_WEIGHT = 0.10
BLUE_BLOOD_T1_BONUS = 0.04
BLUE_BLOOD_T2_BONUS = 0.02
POWER_CONF_BONUS = 0.03
HOME_COURT_BONUS = 0.03          # 1-seeds play first two rounds in home region
RIVALRY_FLATTEN = {3: 0.35, 2: 0.20, 1: 0.10}
ROUND_FLATTEN = {1: 0.0, 2: 0.05, 3: 0.10, 4: 0.15, 5: 0.20, 6: 0.25}

# Non-linear seed power ratings — top 4 seeds have steeper gaps
SEED_POWER = {
    1: 100, 2: 92, 3: 85, 4: 78,   # Top 4: gaps of 7-8
    5: 72,  6: 67, 7: 62, 8: 58,   # 5-8: gaps of 4-5
    9: 54, 10: 51, 11: 48, 12: 45, # 9-12: gaps of 3
    13: 42, 14: 39, 15: 36, 16: 33 # 13-16: gaps of 3
}
POWER_SCALE = 0.006  # converts power diff to probability offset
ROUND_NAMES = {
    1: "Round of 64", 2: "Round of 32", 3: "Sweet 16",
    4: "Elite 8", 5: "Final Four", 6: "Championship",
}
CINDERELLA_COUNT = 2
TARGET_R1_UPSETS = 8

# ---------------------------------------------------------------------------
# Core logic — returns detailed factor breakdown
# ---------------------------------------------------------------------------

def clamp(prob):
    return max(MIN_WEIGHT, min(MAX_WEIGHT, prob))


def evaluate_matchup(team_a, seed_a, conf_a, team_b, seed_b, conf_b, round_num):
    """Compute win probability for team_a with a full factor breakdown."""
    factors = []

    # 1. Seed base probability (non-linear — top 4 seeds are notably stronger)
    power_a = SEED_POWER.get(seed_a, 33)
    power_b = SEED_POWER.get(seed_b, 33)
    power_diff = power_a - power_b
    prob = clamp(0.50 + power_diff * POWER_SCALE)
    factors.append({
        "name": "Seed difference",
        "detail": f"({seed_a}) vs ({seed_b}), power {power_a} vs {power_b}",
        "prob_after": round(prob, 4),
    })

    # 2. Blue blood bonus
    bb_adj = 0.0
    bb_details = []
    if team_a in TIER1_BLUE_BLOODS:
        bb_adj += BLUE_BLOOD_T1_BONUS
        bb_details.append(f"{team_a} is Tier-1 blue blood (+{BLUE_BLOOD_T1_BONUS})")
    elif team_a in TIER2_BLUE_BLOODS:
        bb_adj += BLUE_BLOOD_T2_BONUS
        bb_details.append(f"{team_a} is Tier-2 blue blood (+{BLUE_BLOOD_T2_BONUS})")
    if team_b in TIER1_BLUE_BLOODS:
        bb_adj -= BLUE_BLOOD_T1_BONUS
        bb_details.append(f"{team_b} is Tier-1 blue blood (-{BLUE_BLOOD_T1_BONUS})")
    elif team_b in TIER2_BLUE_BLOODS:
        bb_adj -= BLUE_BLOOD_T2_BONUS
        bb_details.append(f"{team_b} is Tier-2 blue blood (-{BLUE_BLOOD_T2_BONUS})")
    if bb_adj != 0.0:
        prob = clamp(prob + bb_adj)
        factors.append({
            "name": "Blue blood",
            "detail": "; ".join(bb_details),
            "adjustment": round(bb_adj, 4),
            "prob_after": round(prob, 4),
        })

    # 3. Home court advantage (1-seeds in R64 and R32)
    hc_adj = 0.0
    if round_num <= 2:
        if seed_a == 1:
            hc_adj = HOME_COURT_BONUS
        elif seed_b == 1:
            hc_adj = -HOME_COURT_BONUS
    if hc_adj != 0.0:
        prob = clamp(prob + hc_adj)
        favored = team_a if hc_adj > 0 else team_b
        factors.append({
            "name": "Home court",
            "detail": f"{favored} is a 1-seed playing in home region ({ROUND_NAMES[round_num]})",
            "adjustment": round(hc_adj, 4),
            "prob_after": round(prob, 4),
        })

    # 4. Conference strength
    a_power = conf_a in POWER_CONFERENCES
    b_power = conf_b in POWER_CONFERENCES
    conf_adj = 0.0
    if a_power and not b_power:
        conf_adj = POWER_CONF_BONUS
    elif b_power and not a_power:
        conf_adj = -POWER_CONF_BONUS
    if conf_adj != 0.0:
        prob = clamp(prob + conf_adj)
        favored = team_a if conf_adj > 0 else team_b
        factors.append({
            "name": "Conference strength",
            "detail": f"{favored} in power conf; {conf_a} vs {conf_b}",
            "adjustment": round(conf_adj, 4),
            "prob_after": round(prob, 4),
        })

    # 5. Rivalry
    rival_key = frozenset({team_a, team_b})
    if rival_key in RIVALRY_MAP:
        intensity = RIVALRY_MAP[rival_key]
        flatten_pct = RIVALRY_FLATTEN[intensity]
        old_prob = prob
        prob = prob + (0.50 - prob) * flatten_pct
        factors.append({
            "name": "Rivalry",
            "detail": f"{RIVALRY_NOTES.get(rival_key, '')} (intensity {intensity}/3, flattened {flatten_pct:.0%} toward 50/50)",
            "adjustment": round(prob - old_prob, 4),
            "prob_after": round(prob, 4),
        })

    # 6. Round scaling
    flatten_pct = ROUND_FLATTEN.get(round_num, 0)
    if flatten_pct > 0:
        old_prob = prob
        prob = prob + (0.50 - prob) * flatten_pct
        factors.append({
            "name": "Round scaling",
            "detail": f"{ROUND_NAMES.get(round_num, f'Round {round_num}')} — flattened {flatten_pct:.0%} toward 50/50",
            "adjustment": round(prob - old_prob, 4),
            "prob_after": round(prob, 4),
        })

    return round(prob, 4), factors


def pick_winner(team_a, seed_a, conf_a, team_b, seed_b, conf_b, round_num):
    """Pick a winner and return full matchup record."""
    prob_a, factors = evaluate_matchup(team_a, seed_a, conf_a, team_b, seed_b, conf_b, round_num)
    roll = round(random.random(), 4)
    a_wins = roll < prob_a

    if a_wins:
        winner, w_seed, w_conf = team_a, seed_a, conf_a
        upset = seed_a > seed_b
    else:
        winner, w_seed, w_conf = team_b, seed_b, conf_b
        upset = seed_b > seed_a

    record = {
        "round": round_num,
        "round_name": ROUND_NAMES.get(round_num, f"Round {round_num}"),
        "team_a": {"name": team_a, "seed": seed_a, "conference": conf_a},
        "team_b": {"name": team_b, "seed": seed_b, "conference": conf_b},
        "factors": factors,
        "final_prob_team_a": prob_a,
        "final_prob_team_b": round(1.0 - prob_a, 4),
        "roll": roll,
        "winner": winner,
        "upset": upset,
    }
    return winner, w_seed, w_conf, upset, record


# ---------------------------------------------------------------------------
# Console output helpers
# ---------------------------------------------------------------------------

def print_matchup(record):
    """Print a single matchup with factor breakdown."""
    a = record["team_a"]
    b = record["team_b"]
    prob_a = record["final_prob_team_a"]
    prob_b = record["final_prob_team_b"]
    roll = record["roll"]
    winner = record["winner"]
    upset = record["upset"]

    print(f"\n    ({a['seed']}) {a['name']} vs ({b['seed']}) {b['name']}")
    for f in record["factors"]:
        adj_str = ""
        if "adjustment" in f:
            sign = "+" if f["adjustment"] >= 0 else ""
            adj_str = f" [{sign}{f['adjustment']:.4f}]"
        print(f"      {f['name']}: {f['detail']}{adj_str} -> {f['prob_after']:.2%}")
    print(f"      Final odds: {a['name']} {prob_a:.1%} / {b['name']} {prob_b:.1%}")
    print(f"      Roll: {roll:.4f} -> ", end="")
    if upset:
        print(f"{winner} *** UPSET ***")
    else:
        print(f"{winner}")


# ---------------------------------------------------------------------------
# Bracket simulation
# ---------------------------------------------------------------------------

def resolve_play_in_games(bracket):
    """Resolve play-in games and return records."""
    records = []
    for game in bracket["play_in_games"]:
        roll = round(random.random(), 4)
        if roll < 0.50:
            winner, conf = game["team1"], game["team1_conference"]
        else:
            winner, conf = game["team2"], game["team2_conference"]

        record = {
            "round": 0,
            "round_name": "Play-in (First Four)",
            "team_a": {"name": game["team1"], "seed": game["slot_seed"], "conference": game["team1_conference"]},
            "team_b": {"name": game["team2"], "seed": game["slot_seed"], "conference": game["team2_conference"]},
            "factors": [{"name": "Play-in", "detail": "Coin flip (same seed)", "prob_after": 0.50}],
            "final_prob_team_a": 0.50,
            "final_prob_team_b": 0.50,
            "roll": roll,
            "winner": winner,
            "upset": False,
        }
        records.append(record)

        # Patch the bracket
        region = game["slot_region"]
        slot_seed = game["slot_seed"]
        for matchup in bracket["regions"][region]:
            if matchup.get("vs_team", "").startswith("TBD_PLAYIN"):
                if matchup["vs_seed"] == slot_seed:
                    matchup["vs_team"] = winner
                    matchup["vs_conference"] = conf
                    break
            if matchup.get("team", "").startswith("TBD_PLAYIN"):
                if matchup["seed"] == slot_seed:
                    matchup["team"] = winner
                    matchup["conference"] = conf
                    break

    return records


def simulate_region_silent(bracket, region_name):
    """Simulate a region without printing. Returns (winner, round_results_with_records)."""
    matchups = bracket["regions"][region_name]
    teams = []
    for m in matchups:
        teams.append((m["team"], m["seed"], m["conference"]))
        teams.append((m["vs_team"], m["vs_seed"], m["vs_conference"]))

    all_records = []
    current = teams
    for rnd in range(1, 5):
        next_rnd = []
        for i in range(0, len(current), 2):
            t_a, s_a, c_a = current[i]
            t_b, s_b, c_b = current[i + 1]
            w, ws, wc, upset, record = pick_winner(t_a, s_a, c_a, t_b, s_b, c_b, rnd)
            record["region"] = region_name
            next_rnd.append((w, ws, wc))
            all_records.append(record)
        current = next_rnd

    return current[0], all_records


def simulate_tournament():
    """Run the full tournament simulation with retry logic for upset/cinderella quotas."""
    print("=" * 60)
    print("  2026 NCAA TOURNAMENT BRACKET PICKER")
    print("=" * 60)

    # --- Play-in games (only done once) ---
    bracket = load_bracket()
    playin_records = resolve_play_in_games(bracket)

    print(f"\n  PLAY-IN GAMES (First Four)")
    print("  " + "-" * 40)
    for rec in playin_records:
        a = rec["team_a"]
        b = rec["team_b"]
        print(f"    {a['name']} vs {b['name']} (coin flip, roll={rec['roll']:.4f}) -> {rec['winner']}")

    # --- Simulate with upset/cinderella quota enforcement ---
    best_run = None
    best_score = 999

    for attempt in range(200):
        # Save bracket state so play-in results persist but region sims are independent
        bracket_copy = json.loads(json.dumps(bracket))  # deep copy with play-in results baked in

        all_records = []
        r1_upsets = 0
        cinderellas = 0

        for region_name in ["East", "West", "South", "Midwest"]:
            winner, records = simulate_region_silent(bracket_copy, region_name)
            all_records.extend(records)
            for rec in records:
                if rec["round"] == 1 and rec["upset"]:
                    r1_upsets += 1
                # Cinderella: seed 11-14 winning in Round of 32 means they're in Sweet 16
                if rec["round"] == 2 and 11 <= rec["team_a"]["seed"] <= 14 and rec["winner"] == rec["team_a"]["name"]:
                    cinderellas += 1
                if rec["round"] == 2 and 11 <= rec["team_b"]["seed"] <= 14 and rec["winner"] == rec["team_b"]["name"]:
                    cinderellas += 1

        upset_diff = abs(r1_upsets - TARGET_R1_UPSETS)
        cinderella_ok = cinderellas >= CINDERELLA_COUNT
        score = upset_diff + (0 if cinderella_ok else 10)

        if score < best_score:
            best_score = score
            best_run = (all_records, bracket_copy)

        if cinderella_ok and upset_diff <= 3:
            break

    all_records, bracket_final = best_run

    # --- Collect region winners from records ---
    region_winners = {}
    for region_name in ["East", "West", "South", "Midwest"]:
        elite8 = [r for r in all_records if r["region"] == region_name and r["round"] == 4]
        champ_rec = elite8[0]
        region_winners[region_name] = {
            "name": champ_rec["winner"],
            "seed": champ_rec["team_a"]["seed"] if champ_rec["winner"] == champ_rec["team_a"]["name"] else champ_rec["team_b"]["seed"],
            "conference": champ_rec["team_a"]["conference"] if champ_rec["winner"] == champ_rec["team_a"]["name"] else champ_rec["team_b"]["conference"],
        }

    # --- Print region results ---
    r1_upset_count = 0
    for region_name in ["East", "West", "South", "Midwest"]:
        region_records = [r for r in all_records if r["region"] == region_name]
        print(f"\n{'='*60}")
        print(f"  {region_name.upper()} REGION")
        print(f"{'='*60}")

        for rnd in range(1, 5):
            print(f"\n  --- {ROUND_NAMES[rnd]} ---")
            rnd_records = [r for r in region_records if r["round"] == rnd]
            for rec in rnd_records:
                print_matchup(rec)
                if rnd == 1 and rec["upset"]:
                    r1_upset_count += 1

        rw = region_winners[region_name]
        print(f"\n  >> {region_name.upper()} CHAMPION: ({rw['seed']}) {rw['name']}")

    # --- Final Four ---
    print(f"\n{'='*60}")
    print(f"  FINAL FOUR")
    print(f"{'='*60}")

    sf1_regions = bracket_final["final_four_matchups"]["semifinal1"]
    sf2_regions = bracket_final["final_four_matchups"]["semifinal2"]

    rw1a = region_winners[sf1_regions[0]]
    rw1b = region_winners[sf1_regions[1]]
    print(f"\n  --- Semifinal 1: {sf1_regions[0]} vs {sf1_regions[1]} ---")
    w1, ws1, wc1, upset1, sf1_rec = pick_winner(
        rw1a["name"], rw1a["seed"], rw1a["conference"],
        rw1b["name"], rw1b["seed"], rw1b["conference"], 5
    )
    sf1_rec["region"] = "Final Four"
    print_matchup(sf1_rec)
    all_records.append(sf1_rec)

    rw2a = region_winners[sf2_regions[0]]
    rw2b = region_winners[sf2_regions[1]]
    print(f"\n  --- Semifinal 2: {sf2_regions[0]} vs {sf2_regions[1]} ---")
    w2, ws2, wc2, upset2, sf2_rec = pick_winner(
        rw2a["name"], rw2a["seed"], rw2a["conference"],
        rw2b["name"], rw2b["seed"], rw2b["conference"], 5
    )
    sf2_rec["region"] = "Final Four"
    print_matchup(sf2_rec)
    all_records.append(sf2_rec)

    # --- Championship ---
    print(f"\n{'='*60}")
    print(f"  CHAMPIONSHIP")
    print(f"{'='*60}")
    champ, champ_seed, champ_conf, champ_upset, champ_rec = pick_winner(
        w1, ws1, wc1, w2, ws2, wc2, 6
    )
    champ_rec["region"] = "Championship"
    print_matchup(champ_rec)
    all_records.append(champ_rec)

    # --- Tiebreaker ---
    total_points = random.randint(120, 165)

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"  CHAMPION: ({champ_seed}) {champ}")
    print(f"  Championship Game Total Points (tiebreaker): {total_points}")
    print(f"  First-Round Upsets: {r1_upset_count}")
    print(f"{'='*60}")

    # --- Serialize to JSON ---
    output = {
        "generated_at": datetime.now().isoformat(),
        "champion": {"name": champ, "seed": champ_seed, "conference": champ_conf},
        "championship_total_points": total_points,
        "first_round_upsets": r1_upset_count,
        "region_champions": region_winners,
        "play_in_games": playin_records,
        "matchups": all_records,
    }

    output_path = os.path.join(SCRIPT_DIR, "results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to {output_path}")


if __name__ == "__main__":
    simulate_tournament()
