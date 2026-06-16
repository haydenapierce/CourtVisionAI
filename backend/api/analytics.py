from collections import defaultdict
from data.player_database import NBA_PLAYERS


def extract_player_name(title):
    """
    Finds NBA player names inside video titles.
    Only accepts names from NBA_PLAYERS list.
    """

    if not title:
        return None

    title_lower = title.lower()

    matches = []

    for player in NBA_PLAYERS:
        if player.lower() in title_lower:
            matches.append(player)

    if not matches:
        return None

    # longest name wins
    matches.sort(key=len, reverse=True)

    return matches[0]


def build_player_rankings(videos):
    """
    Builds rankings from synced YouTube videos.
    """

    player_stats = defaultdict(lambda: {
        "player": "",
        "total_views": 0,
        "videos": 0,
        "avg_views": 0
    })

    for video in videos:

        title = video.get("title", "")
        views = int(video.get("views", 0))

        player_name = extract_player_name(title)

        # skip invalid titles
        if not player_name:
            continue

        player_stats[player_name]["player"] = player_name
        player_stats[player_name]["total_views"] += views
        player_stats[player_name]["videos"] += 1

    rankings = []

    for player, stats in player_stats.items():

        if stats["videos"] > 0:
            stats["avg_views"] = round(
                stats["total_views"] / stats["videos"],
                2
            )

        rankings.append(stats)

    rankings.sort(
        key=lambda x: x["total_views"],
        reverse=True
    )

    return rankings