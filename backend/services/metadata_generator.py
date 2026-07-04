import re


MAX_TAG_LENGTH = 500


def clean_title_from_filename(filename):
    if not filename:
        return "Untitled NBA Highlight"

    name = filename.rsplit(".", 1)[0]
    name = name.replace("_", " ").replace("-", " ").replace(".", " ")
    name = re.sub(r"\s+", " ", name).strip()

    return name or "Untitled NBA Highlight"


def trim_tags(tags):
    final_tags = []
    current_length = 0

    for tag in tags:
        clean_tag = str(tag).strip()

        if not clean_tag:
            continue

        add_length = len(clean_tag) + (2 if final_tags else 0)

        if current_length + add_length <= MAX_TAG_LENGTH:
            final_tags.append(clean_tag)
            current_length += add_length

    return ", ".join(final_tags)


def generate_tags(title, project_type="solo"):
    base_tags = [
        title,
        "NBA",
        "NBA highlights",
        "basketball highlights",
        "NBA Top 10",
        "NBATop10",
        "best NBA plays",
        "classic NBA",
        "NBA legends",
        "basketball",
        "dunk",
        "slam dunk",
        "poster dunk",
        "basketball history",
        "NBA moments"
    ]

    if project_type == "top10":
        base_tags.extend([
            "top 10 NBA plays",
            "top 10 dunks",
            "greatest NBA plays",
            "best dunks ever"
        ])
    else:
        base_tags.extend([
            "NBA highlight clip",
            "single NBA highlight",
            "best NBA highlight"
        ])

    return trim_tags(base_tags)


def generate_solo_metadata(filename_or_title):
    clean_title = clean_title_from_filename(filename_or_title)

    youtube_title = clean_title

    description = (
        f"{youtube_title}\n\n"
        "Classic NBA highlight from NBATop10. "
        "Subscribe for more NBA dunks, highlights, legends, and greatest plays."
    )

    thumbnail_plan = (
        "Use the main action frame as the background. "
        "Make the player brighter, darken the crowd, sharpen the ball/rim, "
        "and use bold readable text for the highlight."
    )

    return {
        "title": youtube_title,
        "description": description,
        "tags": generate_tags(youtube_title, "solo"),
        "thumbnail_plan": thumbnail_plan
    }


def generate_top10_metadata(project_name, clip_titles=None):
    clean_name = clean_title_from_filename(project_name)

    if "top 10" not in clean_name.lower():
        youtube_title = f"{clean_name} Top 10 Plays"
    else:
        youtube_title = clean_name

    description = (
        f"{youtube_title}\n\n"
        "The best plays, dunks, and highlights from this NBA legend. "
        "Subscribe to NBATop10 for more classic NBA Top 10 videos."
    )

    if clip_titles:
        description += "\n\nFeatured clips:\n"
        for i, clip in enumerate(clip_titles[:10], start=1):
            description += f"#{i}: {clean_title_from_filename(clip)}\n"

    thumbnail_plan = (
        "Use the strongest action shot as the background. "
        "Darken the crowd, brighten the main player, add bold red/white Top 10 text, "
        "and make the subject large enough for mobile viewers."
    )

    return {
        "title": youtube_title,
        "description": description,
        "tags": generate_tags(youtube_title, "top10"),
        "thumbnail_plan": thumbnail_plan
    }