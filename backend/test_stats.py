from services.youtube_oauth import get_authenticated_service

youtube, analytics = get_authenticated_service()

print("\n===== FETCHING CHANNEL STATS =====\n")

response = youtube.channels().list(
    part="statistics,snippet",
    mine=True
).execute()

print(response)

print("\n===== DONE =====\n")