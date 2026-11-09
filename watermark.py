"""
Advanced FFmpeg Watermarking & Visual Preview Module.
Applies customizable text or image watermarks to video streams,
supports position calculation, and renders visual preview samples before applying.
"""

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Optional, Tuple
from config import Config

logger = logging.getLogger(__name__)


class WatermarkEngine:
    """FFmpeg video watermarking and preview generator."""

    POSITIONS = Config.WATERMARK_POSITIONS

    @classmethod
    def is_ffmpeg_installed(cls) -> bool:
        """Check if FFmpeg binary is available on the system."""
        return shutil.which("ffmpeg") is not None

    @classmethod
    def get_drawtext_coordinates(cls, position: str) -> str:
        """Return FFmpeg drawtext x and y coordinates expression."""
        pos = position.lower().strip()
        return cls.POSITIONS.get(pos, cls.POSITIONS["bottom-right"])

    @classmethod
    async def generate_preview(
        cls,
        text: str = "@ChannelName",
        position: str = "bottom-right",
        font_size: int = 28,
        font_color: str = "white",
        output_dir: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a 1280x720 sample preview frame displaying the watermark
        at the configured position, size, and color.
        Returns the absolute path to the generated preview image.
        """
        if not cls.is_ffmpeg_installed():
            logger.warning("FFmpeg not installed. Cannot render visual preview.")
            return None

        temp_dir = output_dir or tempfile.gettempdir()
        preview_path = os.path.join(temp_dir, f"preview_wm_{int(asyncio.get_event_loop().time())}.png")

        coords = cls.get_drawtext_coordinates(position)
        # Escape special characters for ffmpeg drawtext
        escaped_text = text.replace(":", r"\:").replace("'", r"\'").replace("%", r"\%")

        drawtext_filter = (
            f"drawtext=text='{escaped_text}':"
            f"{coords}:"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"box=1:boxcolor=black@0.4:boxborderw=8:"
            f"shadowcolor=black@0.7:shadowx=2:shadowy=2"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=0x1a1a24:s=1280x720:d=1",
            "-vf", drawtext_filter,
            "-frames:v", "1",
            preview_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0 and os.path.exists(preview_path):
                return preview_path
            else:
                logger.error("FFmpeg preview error: %s", stderr.decode(errors="ignore"))
                return None
        except Exception as e:
            logger.error("Exception during watermark preview generation: %s", str(e))
            return None

    @classmethod
    async def apply_watermark(
        cls,
        input_file: str,
        output_file: str,
        text: str = "@ChannelName",
        position: str = "bottom-right",
        font_size: int = 28,
        font_color: str = "white",
    ) -> bool:
        """
        Encode watermark into the input video using FFmpeg.
        Returns True on success, False otherwise.
        """
        if not cls.is_ffmpeg_installed():
            logger.warning("FFmpeg not installed. Skipping watermarking.")
            return False

        coords = cls.get_drawtext_coordinates(position)
        escaped_text = text.replace(":", r"\:").replace("'", r"\'").replace("%", r"\%")

        drawtext_filter = (
            f"drawtext=text='{escaped_text}':"
            f"{coords}:"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"box=1:boxcolor=black@0.35:boxborderw=6:"
            f"shadowcolor=black@0.7:shadowx=2:shadowy=2"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_file,
            "-vf", drawtext_filter,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "copy",
            output_file,
        ]

        try:
            logger.info("Starting FFmpeg watermarking on %s", input_file)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0 and os.path.exists(output_file):
                logger.info("Watermarking completed successfully for %s", output_file)
                return True
            else:
                logger.error("FFmpeg watermarking failed: %s", stderr.decode(errors="ignore"))
                return False
        except Exception as e:
            logger.error("Exception during video watermarking: %s", str(e))
            return False
