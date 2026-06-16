from data.player_database import NBA_PLAYERS


# -----------------------------
# FILTER PLAYERS
# -----------------------------

def filter_players(era="All", position="All", country="All"):
    results = NBA_PLAYERS

    if era != "All":
        results = [p for p in results if p.get("era") == era]

    if position != "All":
        results = [p for p in results if position in p.get("position", "")]

    if country != "All":
        results = [p for p in results if p.get("country") == country]

    return results


# -----------------------------
# GET SINGLE PLAYER
# -----------------------------

def get_player(name: str):
    name = name.lower()

    for player in NBA_PLAYERS:
        if player["name"].lower() == name:
            return player

    return None


# -----------------------------
# RANK PLAYERS (SAFE + CLEAN)
# -----------------------------

def rank_players():
    def score(p):
        return (
            p.get("mvp", 0) * 5 +
            p.get("all_star", 0) * 2 +
            p.get("championships", 0) * 3
        )

    ranked = sorted(NBA_PLAYERS, key=score, reverse=True)

    return [
        {
            "player": p["name"],
            "score": score(p),
            "era": p.get("era", "Unknown"),
            "team": p.get("team", "Unknown"),
            "country": p.get("country", "Unknown"),
            "mvp": p.get("mvp", 0),
            "all_star": p.get("all_star", 0),
            "championships": p.get("championships", 0),
        }
        for p in ranked
    ]


# -----------------------------
# VIDEO POTENTIAL SCORE
# -----------------------------

def video_potential_score(player):
    score = (
        player.get("mvp", 0) * 10 +
        player.get("all_star", 0) * 3 +
        player.get("championships", 0) * 8
    )

    if player.get("era") in ["1980s", "1990s"]:
        score *= 1.2  # nostalgia boost

    return round(score, 2)


# -----------------------------
# IDEA LAB ENGINE
# -----------------------------

def idea_lab():
    return [
        {
            "name": p["name"],
            "score": video_potential_score(p),
            "era": p.get("era", "Unknown"),
            "team": p.get("team", "Unknown"),
            "country": p.get("country", "Unknown"),
            "ideas": [
                f"{p['name']} Top 10 Plays",
                f"{p['name']} Career Highlights",
                f"{p['name']} Clutch Moments"
            ]
        }
        for p in NBA_PLAYERS
    ]