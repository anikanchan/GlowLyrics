# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Word -> emoji map for the 'Visual' lyrics style."""
import re

_RAW = {
    "❤️": "love loved lover lovin loving heart hearts adore",
    "💔": "heartbreak broken goodbye",
    "🔥": "fire burn burning flame flames hot heat lit",
    "🌙": "moon moonlight midnight",
    "🌃": "night nights tonight city",
    "⭐": "star stars starlight",
    "☀️": "sun sunshine sunny sunlight daylight morning",
    "🌧️": "rain raining rainy storm storms",
    "⚡": "lightning thunder electric",
    "❄️": "snow cold ice winter freeze frozen",
    "🌊": "ocean sea wave waves tide water",
    "🏖️": "beach sand shore summer",
    "🌸": "flower flowers rose roses bloom spring",
    "🍂": "fall autumn leaves",
    "🌈": "rainbow colors colours",
    "☁️": "cloud clouds sky skies heaven",
    "🌍": "world earth planet globe",
    "🚗": "car cars drive driving ride road highway",
    "✈️": "plane fly flying flight",
    "🏠": "home house",
    "🎵": "song songs music melody sing singing sang tune",
    "🎸": "guitar rock",
    "🥁": "drum drums beat rhythm",
    "💃": "dance dancing dancer",
    "🎉": "party celebrate celebration",
    "🍾": "champagne toast cheers",
    "🍷": "wine drink drinking drunk",
    "💰": "money cash rich dollar dollars gold",
    "💎": "diamond diamonds",
    "👑": "king queen crown royal",
    "😭": "cry crying tears tear",
    "😊": "smile smiling happy",
    "😂": "laugh laughing",
    "😴": "sleep sleeping dream dreams dreaming",
    "👀": "eyes look looking see watch",
    "💋": "kiss kisses lips",
    "🤝": "friend friends together",
    "🙏": "pray prayer god",
    "👻": "ghost ghosts haunted",
    "💀": "dead die dying death",
    "⏰": "time clock forever",
    "📱": "phone call text",
    "🌅": "sunrise sunset horizon",
    "🏃": "run running runaway",
    "💪": "strong stronger power",
    "🦋": "butterfly butterflies",
    "🐺": "wolf wolves",
    "🍒": "cherry sweet",
    "🔑": "key keys",
    "🚪": "door doors",
    "💌": "letter",
    "🎤": "mic voice",
    "🌌": "galaxy universe space",
    "🗺️": "lost",
    "🧊": "chill",
    "✨": "shine shining glow glowing sparkle magic",
    "🌹": "romance",
    "🎶": "la na",
    "😈": "devil",
    "😇": "angel angels",
    "🌲": "forest tree trees",
    "⛰️": "mountain mountains",
    "👋": "hello bye",
    "🔒": "lock locked",
    "🪞": "mirror",
}

EMOJI = {}
for emo, words in _RAW.items():
    for w in words.split():
        EMOJI[w] = emo

_STRIP = re.compile(r"[^a-z']")


def emoji_for(word):
    w = _STRIP.sub("", word.lower()).strip("'")
    if not w:
        return None
    if w in EMOJI:
        return EMOJI[w]
    for suf in ("s", "es", "'s", "in'"):
        if w.endswith(suf) and w[: -len(suf)] in EMOJI:
            return EMOJI[w[: -len(suf)]]
    return None
