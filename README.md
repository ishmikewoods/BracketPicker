# March Madness Bracket Picker

A weighted RNG bracket picker for the 2026 NCAA Men's Basketball Tournament. Generates complete bracket predictions using pseudo-arbitrary logic that produces realistic but unpredictable results.

**View the selected bracket:** [ishmikewoods.github.io/BracketPicker](https://ishmikewoods.github.io/BracketPicker)

## Usage

```
python picker.py
```

Outputs a full bracket to the console with detailed factor breakdowns for every matchup, and saves structured results to `results.json` for visualization.

## How Picks Are Made

Each matchup starts with a base win probability derived from seed difference, then gets adjusted by several factors:

### Seed-Based Weighting
The core of every pick. Bigger seed gaps mean heavier favorites, but probability is capped at 90/10 — no game is ever a sure thing in March.

### Blue Blood Bonus
Historically elite tournament programs get a small edge reflecting their recruiting depth, coaching experience, and winning culture.
- **Tier 1** (+4%): Duke, Kansas, UConn, Kentucky, North Carolina, UCLA
- **Tier 2** (+2%): Gonzaga, Villanova, Michigan St, Florida, Houston

### Conference Strength
Teams from power conferences (ACC, Big Ten, Big 12, SEC, Big East) get a +3% edge against mid-major opponents, reflecting depth of schedule.

### Rivalry Volatility
When rivals meet, odds flatten toward 50/50 — rivalry games are inherently less predictable. Intensity levels:
- **Intense** (e.g., Duke/UNC, Michigan/Michigan St): 35% flatten
- **Strong** (e.g., Purdue/Illinois, Alabama/Tennessee): 20% flatten
- **Moderate** (e.g., Kansas/Nebraska, Houston/Texas A&M): 10% flatten

### Round Scaling
Later rounds get progressively flatter odds. By the Final Four and Championship, every surviving team is dangerous, so seed advantages matter less.

### Cinderella Rule
The picker enforces at least 2 Cinderella runs (seeds 11-14 reaching the Sweet 16), matching the historical reality that deep underdog runs happen almost every year.

### Upset Quota
Targets ~8 first-round upsets (within a tolerance of 3), consistent with historical March Madness averages.

## Data Files

| File | Description |
|------|-------------|
| `bracket.json` | Full bracket with seeds, teams, conferences, and play-in games |
| `blue_bloods.json` | Blue blood tiers and power conference list |
| `rivalries.json` | Rivalry pairs with intensity ratings (1-3) |
| `results.json` | Generated output with every matchup and its full decision breakdown |
