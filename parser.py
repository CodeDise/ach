"""
Metadata Parser module.
Extracts title, season, episode, audio, and quality from filenames or incoming captions
using dynamic bracket parsing and regular expression tokenization.
Supports ANY resolution/quality dynamically without hardcoding or restricting low/custom values.
"""

import os
import re
from typing import Dict, Optional

def slugify(text: str) -> str:
    """Normalize text into an alphanumeric identifier slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class MetadataParser:
    """Dynamic parser for anime, movies, series metadata and qualities."""

    # Video file extensions to strip
    EXTENSIONS = {
        ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg", ".3gp"
    }

    # Resolution & Quality pattern - captures standard resolutions, 4K, 2160p, custom (e.g. 144p, 240p, 360p, 480p, 540p, 720p, 1080p, 1440p), plus source tokens
    QUALITY_REGEX = re.compile(
        r"(?:\[|\(|\b)(?:"
        r"(\d{3,4}p)|"                           # 240p, 360p, 480p, 720p, 1080p, 2160p
        r"(4[kK]|8[kK])|"                        # 4K, 8K
        r"(2160p|1440p|1080p|720p|540p|480p|360p|240p|144p)|"
        r"(remux|re-mux)|"                       # Remux
        r"(web-?dl|web-?rip)|"                   # WEB-DL, WEBRip
        r"(blu-?ray|bdr|bd-?rip)|"               # BluRay, BDRip
        r"(hd-?rip|dvd-?rip|hdtv|cam-?rip)"      # HDRip, DVDRip, etc.
        r")(?:\b|\]|\))",
        re.IGNORECASE,
    )

    # Season & Episode patterns
    SEASON_EPISODE_REGEX = re.compile(
        r"(?:s(?P<season>\d{1,2})[\s\._\-]*e(?P<episode>\d{1,4}))|"  # S01E02, S1E2, S01.E02
        r"(?:season[\s\._\-]*(?P<season2>\d{1,2})[\s\._\-]*(?:episode|ep)[\s\._\-]*(?P<episode2>\d{1,4}))|"  # Season 1 Episode 2
        r"(?:episodes?[\s\._\-]+(?P<episode3>\d{1,4}))|"             # Episode 25, Episode.12
        r"(?:(?:^|[\s_\[\-])ep?[\s\._\-]*(?P<episode4>\d{1,4})(?:[\s_\]\.\-]|$))",  # EP 05, - 05
        re.IGNORECASE,
    )

    # Season standalone
    SEASON_ONLY_REGEX = re.compile(
        r"(?:\[|\(|\b)(?:s|season)[\s\._\-]*(?P<season>\d{1,2})(?:\]|\)|\b)",
        re.IGNORECASE,
    )

    # Episode standalone
    EPISODE_ONLY_REGEX = re.compile(
        r"(?:\[|\(|\b)(?:e|ep|episode)[\s\._\-]*(?P<episode>\d{1,4})(?:\]|\)|\b)",
        re.IGNORECASE,
    )

    # Common audio tracks / languages
    AUDIO_REGEX = re.compile(
        r"(?:\[|\(|\b)("
        r"hindi\s*-\s*english|english\s*-\s*hindi|"
        r"dual\s*audio|multi\s*audio|multi-audio|triple\s*audio|"
        r"hindi|english|japanese|jap|korean|tamil|telugu|malayalam|bengali|marathi|french|spanish|"
        r"eng\s*sub|hindi\s*sub|subs?|dubbed|dub"
        r")(?:\]|\)|\b)",
        re.IGNORECASE,
    )

    # Noise tags to clean from titles
    NOISE_TAGS = [
        r"10bit", r"8bit", r"hevc", r"x265", r"h265", r"x264", r"h264", r"avc",
        r"aac(?:\d\.\d)?", r"ac3", r"dts", r"ddp(?:\d\.\d)?", r"atmos",
        r"esub", r"msub", r"dual", r"multi",
        r"bluray", r"bdrip", r"web-?dl", r"webrip", r"hdrip", r"camrip",
        r"remux", r"hdr", r"sdr", r"dvdrip", r"proper", r"repack"
    ]

    @classmethod
    def clean_name(cls, raw_name: str) -> str:
        """Strip file extension and sanitize common delimiters."""
        name, _ = os.path.splitext(raw_name)
        return name.strip()

    @classmethod
    def parse_brackets(cls, text: str) -> Dict[str, Optional[str]]:
        """
        Check if the text follows bracket structures like:
        [Title] [Season] [Episode] [Audio] [Quality]
        or [Title] - S01E02 [1080p] [Audio]
        """
        brackets = re.findall(r"\[(.*?)\]", text)
        result: Dict[str, Optional[str]] = {
            "title": None,
            "season": None,
            "episode": None,
            "audio": None,
            "quality": None,
        }

        if not brackets:
            return result

        # First bracket is often the Title unless it's a release group tag (e.g. [SubsPlease])
        idx = 0
        if brackets:
            # If first bracket is something like [720p] or [S01] or [Dual], it's not title
            first = brackets[0].strip()
            if not cls.QUALITY_REGEX.search(first) and not cls.SEASON_EPISODE_REGEX.search(first):
                result["title"] = first
                idx = 1

        # Check remaining brackets
        for b in brackets[idx:]:
            b_clean = b.strip()

            # Quality check
            q_match = cls.QUALITY_REGEX.search(b_clean)
            if q_match and not result["quality"]:
                # Grab the matching non-None group or entire b_clean
                matched_val = next((g for g in q_match.groups() if g), b_clean)
                result["quality"] = matched_val.strip()
                continue

            # Season & Episode check
            se_match = cls.SEASON_EPISODE_REGEX.search(b_clean)
            if se_match:
                s = se_match.group("season") or se_match.group("season2")
                e = se_match.group("episode") or se_match.group("episode2") or se_match.group("episode3") or se_match.group("episode4")
                if s and not result["season"]:
                    result["season"] = f"S{int(s):02d}"
                if e and not result["episode"]:
                    result["episode"] = f"E{int(e):02d}"
                continue

            # Standalone Season
            s_match = cls.SEASON_ONLY_REGEX.search(b_clean)
            if s_match and not result["season"]:
                result["season"] = f"S{int(s_match.group('season')):02d}"
                continue

            # Standalone Episode
            e_match = cls.EPISODE_ONLY_REGEX.search(b_clean)
            if e_match and not result["episode"]:
                result["episode"] = f"E{int(e_match.group('episode')):02d}"
                continue

            # Audio check
            a_match = cls.AUDIO_REGEX.search(b_clean)
            if a_match and not result["audio"]:
                result["audio"] = a_match.group(1).title()
                continue

            # If quality still missing and bracket looks like custom resolution or release tag
            if not result["quality"] and re.match(r"^\d{3,4}p$", b_clean, re.I):
                result["quality"] = b_clean.lower()

        return result

    @classmethod
    def parse(cls, filename: str, caption: str = "") -> Dict[str, str]:
        """
        Comprehensively extract metadata attributes from filename or caption.
        Returns a dict containing:
        - title
        - season (e.g. S01)
        - episode (e.g. E05)
        - audio (e.g. Hindi-Eng)
        - quality (e.g. 720p, 1080p, Remux)
        - slug (unique aggregation key for matching identical title, season, episode)
        """
        raw_text = caption.strip() if caption and len(caption.strip()) > 3 else filename
        clean_text = cls.clean_name(raw_text)

        # 1. Try bracket parser
        bracket_data = cls.parse_brackets(clean_text)

        # 2. Extract Quality (must accept ANY resolution string, never filtered or restricted)
        quality = bracket_data.get("quality")
        if not quality:
            q_match = cls.QUALITY_REGEX.search(clean_text)
            if q_match:
                matched_val = next((g for g in q_match.groups() if g), None)
                quality = matched_val if matched_val else q_match.group(0)
            else:
                # Custom resolution search e.g. 480p, 720p, etc.
                custom_q = re.search(r"(\b\d{3,4}p\b)", clean_text, re.I)
                if custom_q:
                    quality = custom_q.group(1)
                else:
                    quality = "HD"

        # Normalize quality format e.g. 720p, 1080p, 4K, Remux
        quality = quality.strip()
        if quality.lower().endswith("p"):
            quality = quality.lower()
        elif quality.upper() in ("4K", "8K"):
            quality = quality.upper()
        else:
            quality = quality.title()

        # 3. Extract Season & Episode
        season = bracket_data.get("season")
        episode = bracket_data.get("episode")

        if not season or not episode:
            se_match = cls.SEASON_EPISODE_REGEX.search(clean_text)
            if se_match:
                s = se_match.group("season") or se_match.group("season2")
                e = (
                    se_match.group("episode")
                    or se_match.group("episode2")
                    or se_match.group("episode3")
                    or se_match.group("episode4")
                )
                if s and not season:
                    season = f"S{int(s):02d}"
                if e and not episode:
                    episode = f"E{int(e):02d}"

        if not season:
            s_match = cls.SEASON_ONLY_REGEX.search(clean_text)
            if s_match:
                season = f"S{int(s_match.group('season')):02d}"
            else:
                # Default season if episode is found
                season = "S01" if episode else "Movie"

        if not episode:
            e_match = cls.EPISODE_ONLY_REGEX.search(clean_text)
            if e_match:
                episode = f"E{int(e_match.group('episode')):02d}"
            else:
                episode = "Full" if season == "Movie" else "E01"

        # 4. Extract Audio
        audio = bracket_data.get("audio")
        if not audio:
            a_match = cls.AUDIO_REGEX.search(clean_text)
            if a_match:
                audio = a_match.group(1).title()
            else:
                audio = "Dual Audio"

        # 5. Extract and Clean Title
        title = bracket_data.get("title")
        if not title:
            # Strip season/episode tokens, quality tokens, brackets, and noise
            work = clean_text
            # Remove brackets content if already parsed
            work = re.sub(r"\[.*?\]", " ", work)
            work = re.sub(r"\(.*?\)", " ", work)
            # Remove SxxExx
            work = cls.SEASON_EPISODE_REGEX.sub(" ", work)
            work = cls.SEASON_ONLY_REGEX.sub(" ", work)
            work = cls.EPISODE_ONLY_REGEX.sub(" ", work)
            # Remove quality
            work = cls.QUALITY_REGEX.sub(" ", work)
            # Remove audio
            work = cls.AUDIO_REGEX.sub(" ", work)
            # Remove noise tags
            for tag in cls.NOISE_TAGS:
                work = re.sub(rf"\b{tag}\b", " ", work, flags=re.I)
            # Replace dots, underscores, dashes with spaces
            work = re.sub(r"[\._\-+]+", " ", work)
            # Remove stray digits at the end if leftover
            work = re.sub(r"\s+", " ", work).strip()
            title = work if work else "Untitled Media"

        # Final title cleanup
        title = re.sub(r"[\._]+", " ", title).strip()
        title = re.sub(r"\s+", " ", title)

        # Generate unique aggregation slug (groups identical title, season, episode)
        title_slug = slugify(title)
        s_slug = slugify(season)
        e_slug = slugify(episode)
        aggregation_slug = f"{title_slug}_{s_slug}_{e_slug}"

        return {
            "title": title,
            "season": season,
            "episode": episode,
            "audio": audio,
            "quality": quality,
            "slug": aggregation_slug,
            "title_slug": title_slug,
        }
