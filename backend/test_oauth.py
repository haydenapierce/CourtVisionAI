from services.youtube_oauth import get_authenticated_service

youtube, analytics = get_authenticated_service()

# 🔥 ACTUAL API CALL
request = youtube.channels().list(
    part="statistics",
    mine=True
)

response = request.execute()

print("\n===== CHANNEL STATS =====\n")
print(response)