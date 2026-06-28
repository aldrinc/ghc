# Worst-Day Test

The design must survive:

- wrong TikTok/Postiz channel selected
- generated slides look wrong or off-brand
- user publishes manually but Postiz has not indexed the TikTok post yet
- multiple candidate TikTok release ids match the same window
- release id is attached to the wrong post
- Postiz analytics are missing or delayed
- conversion source is disconnected
- attribution is only timing correlation
- model/provider is unavailable
- agent tries to publish without approval

Safe behavior:

- no silent fallback
- no fake metrics
- no direct provider writes from Hermes
- no public posting without approval
- ambiguous release matches require user confirmation
- heuristic attribution is labeled as heuristic
- every external action has request/response history
