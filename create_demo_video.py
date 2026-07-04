"""
Aureon Demo Video Generator v2
Bilingual demo video with TTS voiceover, subtitles, Ken Burns effects.

Usage:
    python create_demo_video.py                         # Standard EN (~60s)
    python create_demo_video.py --output short.mp4      # Short EN (~30s)
    python create_demo_video.py --lang zh               # Standard ZH (~60s)
"""

import os, sys, json, subprocess, math
from pathlib import Path

import numpy as np
from moviepy import (
    ImageClip, VideoClip, TextClip, ColorClip,
    CompositeVideoClip, CompositeAudioClip, concatenate_videoclips, AudioFileClip,
    vfx, afx,
)

# ─── Config ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SCREENSHOTS_DIR = SCRIPT_DIR / "screenshots"
AUDIO_DIR = SCRIPT_DIR / "audio"
OUTPUT_DIR = SCRIPT_DIR / "demo_output"
FPS = 30
VIDEO_SIZE = (1920, 1080)
CROSSFADE = 0.5  # seconds of crossfade between scenes

# Font paths (Windows)
FONTS = {
    "en": "C:/Windows/Fonts/arial.ttf",
    "zh": "C:/Windows/Fonts/msyh.ttc",
    "en_bold": "C:/Windows/Fonts/arialbd.ttf",
    "en_data": "C:/Windows/Fonts/segoeui.ttf",
}

def get_font(lang: str, bold: bool = False) -> str:
    if lang == "zh":
        return FONTS["zh"]
    return FONTS["en_bold"] if bold else FONTS["en"]

# ─── Scene Definitions (English) ──────────────────────────────────────────
# Each scene: type, visuals, voiceover script, subtitle text, timing
# Timing auto-extends to cover voiceover; visual_buffer adds post-VO silence

SCENES_EN = [
    # ── Scene 1: Pain point (black bg, typewriter) ──
    {
        "type": "typewriter",
        "duration": 5.0,
        "voiceover": "Your contracts are scattered across drives, emails, and folders…",
        "caption": "Your contracts scattered across drives, emails, folders…",
        "visual_buffer": 0.5,
        "caption_position": "bottom",
    },
    # ── Scene 2: Landing page ──
    {
        "type": "image",
        "file": "en-landing-page.png",
        "duration": 6.0,
        "zoom": (1.0, 1.08),
        "pan": (0, 0),
        "voiceover": "Finding a single clause takes twenty minutes—if you can find it at all.",
        "caption": "One clause takes 20 minutes to find.",
        "visual_buffer": 1.5,
        "caption_position": "top",
    },
    # ── Scene 3: Documents page ──
    {
        "type": "image",
        "file": "en-documents.png",
        "duration": 9.0,
        "zoom": (1.05, 1.0),
        "pan": (-0.02, 0),
        "voiceover": "Drop any document into Aureon. It automatically indexes everything, ready to search.",
        "caption": "Drag & Drop → Auto Index",
        "visual_buffer": 2.0,
        "caption_position": "bottom",
    },
    # ── Scene 4: Search + cited answer (core Aha moment) ──
    {
        "type": "image",
        "file": "en-search-answer.png",
        "duration": 16.0,
        "zoom": (1.0, 1.06),
        "pan": (0, -0.03),
        "voiceover": "Ask anything in plain English. You get cited answers in seconds, with sources ranked by relevance.",
        "caption": "Plain English → Cited Answers · seconds",
        "visual_buffer": 8.0,  # extra time to let the answer soak in
        "caption_position": "top",
    },
    # ── Scene 5: Data / metrics ──
    {
        "type": "data_numbers",
        "duration": 10.0,
        "data": ["100%·Recall@5", "590ms·TTFT", "$0.0003/query"],
        "voiceover": "One hundred percent recall. Five hundred ninety milliseconds to first token. Under a cent for a hundred queries.",
        "caption": "100% Recall@5 · 590ms TTFT · $0.0003/query",
        "visual_buffer": 1.0,
        "caption_position": "bottom",
    },
    # ── Scene 6: Multi-language ──
    {
        "type": "image",
        "file": "en-search-page.png",
        "duration": 6.0,
        "zoom": (1.0, 1.0),
        "pan": (0.03, 0),
        "voiceover": "Multi-language support, right out of the box.",
        "caption": "Multi-language, out of the box.",
        "visual_buffer": 2.5,
        "caption_position": "bottom",
    },
    # ── Scene 7: CTA / Ending ──
    {
        "type": "ending",
        "duration": 8.0,
        "voiceover": "Open source under MIT. Production ready. Star us on GitHub.",
        "caption": "Open Source · MIT · Production Ready",
        "visual_buffer": 1.0,
        "caption_position": "bottom",
    },
]

# ─── Scene Definitions (Chinese) — placeholder for Phase 2b ──────────────
SCENES_ZH = [
    {
        "type": "typewriter",
        "duration": 5.0,
        "voiceover": "合同散落在网盘、邮件、本地文件夹里",
        "caption": "合同散落在网盘、邮件、本地文件夹里",
        "visual_buffer": 0.5,
    },
    {
        "type": "image",
        "file": "en-landing-page.png",  # will retake zh screenshot
        "duration": 6.0,
        "zoom": (1.0, 1.08),
        "pan": (0, 0),
        "voiceover": "找一个条款要翻 20 分钟",
        "caption": "找一个条款要翻 20 分钟",
        "visual_buffer": 1.5,
    },
    {
        "type": "image",
        "file": "en-documents.png",
        "duration": 9.0,
        "zoom": (1.05, 1.0),
        "pan": (-0.02, 0),
        "voiceover": "把文档拖进去，AI 自动索引",
        "caption": "把文档拖进去，AI 自动索引",
        "visual_buffer": 2.0,
    },
    {
        "type": "image",
        "file": "en-search-answer.png",
        "duration": 16.0,
        "zoom": (1.0, 1.06),
        "pan": (0, -0.03),
        "voiceover": "问问题，3 秒拿答案，每个回答都有引用来源",
        "caption": "问问题，3 秒拿答案，每个回答都有引用来源",
        "visual_buffer": 8.0,
    },
    {
        "type": "data_numbers",
        "duration": 10.0,
        "data": ["100%·召回率", "590ms·响应", "$0.0003·/query"],
        "voiceover": "100% 召回率。590 毫秒响应。每次查询不到 0.01 元",
        "caption": "100% 召回率 · 590ms 响应 · $0.0003/query",
        "visual_buffer": 1.0,
    },
    {
        "type": "image",
        "file": "en-search-page.png",  # will retake zh screenshot
        "duration": 6.0,
        "zoom": (1.0, 1.0),
        "pan": (0.03, 0),
        "voiceover": "多语言，开箱即用",
        "caption": "多语言，开箱即用",
        "visual_buffer": 2.5,
    },
    {
        "type": "ending",
        "duration": 8.0,
        "voiceover": "开源 · MIT 协议 · 生产就绪 → Star on GitHub",
        "caption": "开源 · MIT 协议 · 生产就绪",
        "visual_buffer": 1.0,
    },
]

# TTS voice mapping
TTS_VOICES = {
    "en": "en-US-GuyNeural",
    "zh": "zh-CN-YunxiNeural",
}


# ─── TTS Generation ──────────────────────────────────────────────────────
def get_tts_duration(mp3_path: Path) -> float:
    """Get audio duration via ffprobe."""
    if not mp3_path.exists():
        return 0
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(mp3_path)],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def ensure_tts(scenes: list, lang: str):
    """Generate missing TTS audio files."""
    import asyncio, edge_tts

    audio_lang_dir = AUDIO_DIR / lang
    audio_lang_dir.mkdir(parents=True, exist_ok=True)
    voice = TTS_VOICES.get(lang, "en-US-GuyNeural")

    async def _gen():
        for s in scenes:
            out_path = audio_lang_dir / f"scene_{scenes.index(s) + 1}.mp3"
            if out_path.exists():
                continue
            print(f"  [TTS] scene {scenes.index(s) + 1} ({lang})")
            communicate = edge_tts.Communicate(s["voiceover"], voice)
            await communicate.save(str(out_path))
            print(f"         -> {out_path.name}")

    asyncio.run(_gen())

    # Update durations based on actual audio length
    for i, s in enumerate(scenes):
        mp3 = audio_lang_dir / f"scene_{i + 1}.mp3"
        dur = get_tts_duration(mp3)
        if dur > 0:
            s["_audio_dur"] = dur
            # Auto-extend duration to cover voiceover + buffer
            min_dur = dur + s.get("visual_buffer", 1.0)
            if s["duration"] < min_dur:
                s["duration"] = math.ceil(min_dur * 10) / 10  # round up to 0.1s
        else:
            s["_audio_dur"] = s["duration"]


# ─── Clip Builders ───────────────────────────────────────────────────────

def make_typewriter_clip(text: str, duration: float, lang: str = "en") -> CompositeVideoClip:
    """Typewriter effect: text appears character by character."""
    font_size = 56
    font = get_font(lang)

    # Black background
    bg = ColorClip(size=VIDEO_SIZE, color=(0, 0, 0)).with_duration(duration)

    # Build character-by-character clips
    n = len(text)
    char_dur = duration / (n + 1)  # +1 for final without cursor
    char_clips = []

    for i in range(1, n + 1):
        display = text[:i] + "|"
        txt = (TextClip(text=display, font_size=font_size, color="white", font=font,
                        size=(VIDEO_SIZE[0] - 200, None), method="caption")
               .with_duration(char_dur)
               .with_position(("center", VIDEO_SIZE[1] * 0.42)))
        char_clips.append(txt)

    # Final frame without cursor
    final_txt = (TextClip(text=text, font_size=font_size, color="white", font=font,
                          size=(VIDEO_SIZE[0] - 200, None), method="caption")
                 .with_duration(char_dur)
                 .with_position(("center", VIDEO_SIZE[1] * 0.42)))
    char_clips.append(final_txt)

    return CompositeVideoClip([bg] + char_clips, size=VIDEO_SIZE)


def make_ken_burns_clip(img_path: Path, duration: float,
                         zoom_range: tuple = (1.0, 1.0),
                         pan: tuple = (0, 0)) -> VideoClip:
    """Create a video clip that shows the full screenshot (letterbox if needed).

    Args:
        img_path: Path to screenshot.
        duration: Clip duration.
        zoom_range: Ignored for tall screenshots; only tiny zoom allowed if image is 16:9.
        pan: Ignored for tall screenshots.
    """
    if not img_path.exists():
        print(f"  [!] Missing: {img_path}")
        return None

    clip = ImageClip(str(img_path))
    img_w, img_h = clip.size
    target_w, target_h = VIDEO_SIZE

    # Scale to fit entirely inside the frame
    scale = min(target_w / max(img_w, 1), target_h / max(img_h, 1))
    resized = clip.resized(scale)

    # Center on a black background
    bg = ColorClip(size=VIDEO_SIZE, color=(0, 0, 0)).with_duration(duration)
    final_clip = (CompositeVideoClip(
        [bg, resized.with_position("center")],
        size=VIDEO_SIZE
    ).with_duration(duration).with_fps(FPS))

    return final_clip


def make_caption(text: str, duration: float, lang: str = "en",
                 position: str = "bottom") -> CompositeVideoClip:
    """创建字幕条：半透明背景 + 居中文字。

    字幕与配音独立存在——简洁、易扫描，不是逐字稿。

    Args:
        text: 字幕文字
        duration: 持续时间
        lang: 语言 (en/zh)
        position: 字幕位置，"top"（距顶部40px）或 "bottom"（距底部100px）
    """
    font_size = 38 if lang == "en" else 42
    font = get_font(lang)
    bar_height = 60

    # 计算 Y 坐标
    if position == "top":
        y_pos = 40
    else:
        y_pos = VIDEO_SIZE[1] - 100

    # 半透明背景条
    bar = (ColorClip(size=(VIDEO_SIZE[0], bar_height), color=(0, 0, 0))
           .with_opacity(0.65)
           .with_duration(duration)
           .with_position(("center", y_pos)))

    # 文字叠加
    txt = (TextClip(text=text, font_size=font_size, color="white", font=font,
                    size=(VIDEO_SIZE[0] - 100, 50), method="caption",
                    text_align="center")
           .with_duration(duration)
           .with_position(("center", y_pos + 5)))

    return CompositeVideoClip([bar, txt], size=VIDEO_SIZE).with_duration(duration)


def make_data_numbers_clip(data_lines: list, duration: float) -> CompositeVideoClip:
    """Animated data numbers: each line fades in with a delay."""
    bg = ColorClip(size=VIDEO_SIZE, color=(15, 15, 30)).with_duration(duration)

    n = len(data_lines)
    stagger = duration / (n + 1)  # time per item, last gap is buffer

    items = []
    for i, line in enumerate(data_lines):
        parts = line.split("·", 1)
        if len(parts) == 2:
            num, label = parts[0].strip(), parts[1].strip()
            display = f"{num}"
            sub = label
        else:
            display = line
            sub = ""

        # Big number
        num_txt = (TextClip(text=display, font_size=72, color="#60a5fa", font=get_font("en", bold=True),
                            text_align="center")
                   .with_duration(duration - i * stagger)
                   .with_start(i * stagger)
                   .with_position(("center", VIDEO_SIZE[1] * 0.38))
                   .with_effects([vfx.CrossFadeIn(0.4)]))

        items.append(num_txt)

        if sub:
            sub_txt = (TextClip(text=sub, font_size=28, color="#94a3b8", font=get_font("en"),
                                text_align="center")
                       .with_duration(duration - i * stagger)
                       .with_start(i * stagger + 0.15)
                       .with_position(("center", VIDEO_SIZE[1] * 0.48))
                       .with_effects([vfx.CrossFadeIn(0.4)]))
            items.append(sub_txt)

    items.insert(0, bg)
    return CompositeVideoClip(items, size=VIDEO_SIZE)


def make_counter(start: float, end: float, duration: float, prefix: str = "",
                 suffix: str = "", decimals: int = 0, font_size: int = 64,
                 color: str = "#60a5fa", font: str = None) -> VideoClip:
    """数字从 start 滚动到 end 的计数动画。

    Args:
        start: 起始值
        end: 目标值
        duration: 动画时长（秒）
        prefix: 数字前缀（如 "$"）
        suffix: 数字后缀（如 "%"、"ms"）
        decimals: 小数位数
        font_size: 字体大小
        color: 文字颜色
        font: 字体路径

    Returns:
        VideoClip: 数字计数动画片段
    """
    if font is None:
        font = get_font("en", bold=True)

    def make_frame(t):
        progress = min(t / max(duration, 0.01), 1.0)
        ease = 1 - (1 - progress) ** 3  # ease out cubic
        current_val = start + (end - start) * ease

        if decimals > 0:
            num_str = f"{current_val:.{decimals}f}"
        else:
            num_str = f"{int(round(current_val))}"

        display = f"{prefix}{num_str}{suffix}"

        txt_clip = TextClip(text=display, font_size=font_size, color=color,
                            font=font, text_align="left")
        frame = txt_clip.get_frame(t)
        txt_clip.close()
        return frame

    return VideoClip(make_frame, duration=duration).with_fps(FPS)


def _hex_to_rgb(hex_color: str) -> tuple:
    """十六进制颜色转 RGB 元组。"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def make_progress_bar(fill_ratio: float, duration: float, bar_width: int = 600,
                      bar_height: int = 24, start_delay: float = 0,
                      fill_color: str = "#60a5fa",
                      bg_color: str = "#1e293b") -> CompositeVideoClip:
    """生成单个进度条动画（从 0 填充到 fill_ratio 位置）。

    Args:
        fill_ratio: 填充比例 (0.0 - 1.0)
        duration: 填充动画时长（秒）
        bar_width: 进度条总宽度
        bar_height: 进度条高度
        start_delay: 开始延迟（秒）
        fill_color: 填充颜色
        bg_color: 背景色

    Returns:
        CompositeVideoClip: 进度条动画片段
    """
    total_duration = duration + start_delay
    bg_rgb = _hex_to_rgb(bg_color)

    bg_bar = (ColorClip(size=(bar_width, bar_height), color=bg_rgb)
              .with_duration(total_duration)
              .with_position((0, 0)))

    def make_fill_frame(t):
        if t < start_delay:
            progress = 0.0
        else:
            anim_t = t - start_delay
            progress = min(anim_t / max(duration, 0.01), 1.0)
            ease = 1 - (1 - progress) ** 3  # ease out cubic
            progress = ease * fill_ratio

        current_width = max(1, int(bar_width * progress))
        frame = np.zeros((bar_height, bar_width, 3), dtype=np.uint8)

        r = int(fill_color[1:3], 16)
        g = int(fill_color[3:5], 16)
        b = int(fill_color[5:7], 16)

        frame[:, :current_width] = [r, g, b]
        return frame

    fill_bar = (VideoClip(make_fill_frame, duration=total_duration)
                .with_fps(FPS)
                .with_position((0, 0)))

    return CompositeVideoClip([bg_bar, fill_bar], size=(bar_width, bar_height))


def make_data_bars_scene(data_items: list, duration: float, lang: str = "en") -> CompositeVideoClip:
    """数据指标场景：横向条形图 + 数字滚动动画。

    三项数据依次出现（stagger 0.8s），每项包含：
    - 大数字（滚动计数动画）
    - 进度条（从左向右填充）
    - 说明文字

    Args:
        data_items: 数据项列表，每项为 dict，包含：
                    - value: 数值（用于进度条比例和计数）
                    - display: 显示的数字字符串（如 "100%"、"590ms"、"$0.0003"）
                    - label: 标签（如 "Recall@5"、"TTFT"、"per query"）
                    - description: 说明文字
                    - max_val: 进度条最大值（用于计算比例）
                    - decimals: 小数位数
                    - prefix: 前缀
                    - suffix: 后缀
        duration: 总时长
        lang: 语言

    Returns:
        CompositeVideoClip: 完整的数据条形图场景
    """
    bg = ColorClip(size=VIDEO_SIZE, color=(10, 15, 35)).with_duration(duration)

    stagger_delay = 0.8
    anim_duration = 2.0
    n = len(data_items)

    bar_total_width = 700
    item_gap = 120
    start_y = int(VIDEO_SIZE[1] * 0.28)

    items = [bg]

    for i, item in enumerate(data_items):
        delay = i * stagger_delay
        item_start_y = start_y + i * item_gap

        fill_ratio = min(item["value"] / max(item.get("max_val", item["value"]), 0.01), 1.0)

        counter_clip = make_counter(
            start=0,
            end=item["value"],
            duration=anim_duration,
            prefix=item.get("prefix", ""),
            suffix=item.get("suffix", ""),
            decimals=item.get("decimals", 0),
            font_size=56,
            color="#60a5fa",
            font=get_font("en", bold=True),
        )
        counter_clip = (counter_clip
                        .with_start(delay)
                        .with_duration(duration - delay)
                        .with_position((int(VIDEO_SIZE[0] * 0.18), item_start_y))
                        .with_effects([vfx.CrossFadeIn(0.3)]))
        items.append(counter_clip)

        label_text = item.get("label", "")
        if label_text:
            label_clip = (TextClip(text=label_text, font_size=32, color="#94a3b8",
                                   font=get_font("en"), text_align="left")
                          .with_start(delay + 0.1)
                          .with_duration(duration - delay - 0.1)
                          .with_position((int(VIDEO_SIZE[0] * 0.18), item_start_y + 65))
                          .with_effects([vfx.CrossFadeIn(0.4)]))
            items.append(label_clip)

        progress_bar = make_progress_bar(
            fill_ratio=fill_ratio,
            duration=anim_duration,
            bar_width=bar_total_width,
            bar_height=20,
            start_delay=delay + 0.2,
            fill_color="#3b82f6",
            bg_color="#1e293b",
        )
        progress_bar = (progress_bar
                        .with_start(0)
                        .with_duration(duration)
                        .with_position((int(VIDEO_SIZE[0] * 0.45), item_start_y + 18)))
        items.append(progress_bar)

        desc_text = item.get("description", "")
        if desc_text:
            desc_clip = (TextClip(text=desc_text, font_size=26, color="#cbd5e1",
                                  font=get_font("en"), text_align="left")
                         .with_start(delay + 0.4)
                         .with_duration(duration - delay - 0.4)
                         .with_position((int(VIDEO_SIZE[0] * 0.45), item_start_y + 55))
                         .with_effects([vfx.CrossFadeIn(0.5)]))
            items.append(desc_clip)

    return CompositeVideoClip(items, size=VIDEO_SIZE)


def make_ending_clip(title_text: str, subtitle_text: str, duration: float,
                     github_url: str = "github.com/Yum-wu/Aureon") -> CompositeVideoClip:
    """Final CTA scene."""
    bg = ColorClip(size=VIDEO_SIZE, color=(15, 15, 25)).with_duration(duration)
    font_size = 48
    sub_size = 28

    title = (TextClip(text=github_url, font_size=font_size, color="white",
                      font=get_font("en", bold=True), text_align="center")
             .with_duration(duration)
             .with_position(("center", VIDEO_SIZE[1] * 0.40))
             .with_effects([vfx.CrossFadeIn(1.0)]))

    subtitle = (TextClip(text=subtitle_text, font_size=sub_size, color="#94a3b8",
                         font=get_font("en"), text_align="center")
                .with_duration(duration)
                .with_position(("center", VIDEO_SIZE[1] * 0.52))
                .with_effects([vfx.CrossFadeIn(1.2)]))

    star = (TextClip(text="★ Star on GitHub", font_size=32, color="#facc15",
                     font=get_font("en", bold=True), text_align="center")
            .with_duration(duration)
            .with_position(("center", VIDEO_SIZE[1] * 0.62))
            .with_effects([vfx.CrossFadeIn(1.5)]))

    return CompositeVideoClip([bg, title, subtitle, star], size=VIDEO_SIZE)


def make_gradient_bg(duration: float) -> VideoClip:
    """深蓝色到黑色的垂直渐变背景。

    Args:
        duration: 持续时间（秒）

    Returns:
        VideoClip: 渐变背景片段
    """
    top_color = np.array([10, 15, 45], dtype=np.uint8)
    bottom_color = np.array([0, 0, 8], dtype=np.uint8)

    def make_frame(t):
        frame = np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 3), dtype=np.uint8)
        for y in range(VIDEO_SIZE[1]):
            ratio = y / max(VIDEO_SIZE[1] - 1, 1)
            color = top_color * (1 - ratio) + bottom_color * ratio
            frame[y, :] = color.astype(np.uint8)
        return frame

    return VideoClip(make_frame, duration=duration).with_fps(FPS)


def make_pulse_button(text: str, duration: float, y_pos: float,
                      color: str = "#facc15", text_color: str = "#000000",
                      start_delay: float = 0.0) -> CompositeVideoClip:
    """脉冲动画按钮：缩放 + 光晕变化。

    呼吸周期约 2 秒，包含缩放和外发光效果。

    Args:
        text: 按钮文字
        duration: 总持续时间
        y_pos: 按钮中心 Y 坐标
        color: 按钮背景色（十六进制）
        text_color: 文字颜色（十六进制）
        start_delay: 开始延迟时间

    Returns:
        CompositeVideoClip: 脉冲按钮片段
    """
    button_w = 420
    button_h = 72
    border_radius = 36
    cycle = 2.0

    bg_rgb = _hex_to_rgb(color)
    txt_rgb = _hex_to_rgb(text_color)

    def make_button_frame(t):
        if t < start_delay:
            return np.zeros((button_h + 60, button_w + 80, 4), dtype=np.uint8)

        anim_t = t - start_delay
        phase = (anim_t % cycle) / cycle
        pulse = 0.5 + 0.5 * math.sin(phase * 2 * math.pi)

        scale = 0.95 + 0.08 * pulse
        glow_alpha = 0.2 + 0.5 * pulse

        new_w = int(button_w * scale)
        new_h = int(button_h * scale)

        canvas_w = button_w + 100
        canvas_h = button_h + 100
        frame = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

        cx = canvas_w // 2
        cy = canvas_h // 2

        # 光晕层（多层模糊模拟）
        glow_layers = [
            (30, glow_alpha * 0.15),
            (20, glow_alpha * 0.25),
            (10, glow_alpha * 0.35),
        ]
        for glow_r, glow_a in glow_layers:
            g_w = new_w + glow_r * 2
            g_h = new_h + glow_r * 2
            g_x = cx - g_w // 2
            g_y = cy - g_h // 2
            g_x1 = max(0, g_x)
            g_y1 = max(0, g_y)
            g_x2 = min(canvas_w, g_x + g_w)
            g_y2 = min(canvas_h, g_y + g_h)
            if g_x2 > g_x1 and g_y2 > g_y1:
                a = int(glow_a * 255)
                frame[g_y1:g_y2, g_x1:g_x2] = [bg_rgb[0], bg_rgb[1], bg_rgb[2], a]

        # 按钮主体
        btn_x = cx - new_w // 2
        btn_y = cy - new_h // 2

        # 圆角矩形按钮（简单近似）
        for dy in range(new_h):
            for dx in range(new_w):
                px = btn_x + dx
                py = btn_y + dy
                if 0 <= px < canvas_w and 0 <= py < canvas_h:
                    # 圆角计算
                    r = border_radius * scale
                    x_from_edge = min(dx, new_w - 1 - dx)
                    y_from_edge = min(dy, new_h - 1 - dy)
                    if x_from_edge < r and y_from_edge < r:
                        dist = math.sqrt((r - x_from_edge) ** 2 + (r - y_from_edge) ** 2)
                        if dist > r:
                            continue
                    frame[py, px] = [bg_rgb[0], bg_rgb[1], bg_rgb[2], 255]

        return frame

    button_clip = VideoClip(make_button_frame, duration=duration).with_fps(FPS)
    button_clip = button_clip.with_position(
        ("center", int(y_pos - (button_h + 100) // 2))
    )

    # 文字层
    text_clip = (TextClip(text=text, font_size=28, color=text_color,
                          font=get_font("en", bold=True), text_align="center")
                 .with_duration(duration - start_delay)
                 .with_start(start_delay)
                 .with_position(("center", int(y_pos - 14)))
                 .with_effects([vfx.CrossFadeIn(0.3)]))

    return CompositeVideoClip(
        [button_clip, text_clip], size=VIDEO_SIZE
    ).with_duration(duration)


def make_selected_url(url: str, duration: float, y_pos: float,
                      start_delay: float = 0.0) -> CompositeVideoClip:
    """选中态效果的 GitHub URL（等宽字体 + 选中背景）。

    Args:
        url: URL 文字
        duration: 总持续时间
        y_pos: 文字顶部 Y 坐标
        start_delay: 开始延迟时间

    Returns:
        CompositeVideoClip: URL 选中态片段
    """
    font_size = 26
    monospace_font = "C:/Windows/Fonts/consola.ttf"

    # 选中背景
    bg_w = 480
    bg_h = 44

    def make_bg_frame(t):
        if t < start_delay:
            return np.zeros((bg_h, bg_w, 4), dtype=np.uint8)
        # 蓝色选中背景
        frame = np.zeros((bg_h, bg_w, 4), dtype=np.uint8)
        frame[:, :] = [59, 130, 246, 180]
        return frame

    bg_clip = VideoClip(make_bg_frame, duration=duration).with_fps(FPS)
    bg_clip = bg_clip.with_position(
        ("center", int(y_pos))
    )

    # URL 文字
    text_clip = (TextClip(text=url, font_size=font_size, color="white",
                          font=monospace_font, text_align="center")
                 .with_duration(duration - start_delay)
                 .with_start(start_delay)
                 .with_position(("center", int(y_pos + 8)))
                 .with_effects([vfx.CrossFadeIn(0.3)]))

    return CompositeVideoClip(
        [bg_clip, text_clip], size=VIDEO_SIZE
    ).with_duration(duration)


def make_ending_v2(duration: float, lang: str = "en",
                   github_url: str = "github.com/Yum-wu/Aureon") -> CompositeVideoClip:
    """增强版结尾 CTA 场景 v2。

    包含：品牌名、标语、脉冲按钮、GitHub URL、底部三特性。
    元素依次出现（stagger 动画），深色渐变背景。

    Args:
        duration: 持续时间（秒）
        lang: 语言 (en/zh)
        github_url: GitHub 仓库地址

    Returns:
        CompositeVideoClip: 完整的结尾 CTA 场景
    """
    # 渐变背景
    bg = make_gradient_bg(duration)

    elements = [bg]

    # stagger 时间配置
    brand_delay = 0.0
    slogan_delay = 0.4
    button_delay = 0.9
    url_delay = 1.5
    features_delay = 2.1

    # 品牌名 - Aureon（大号，顶部居中）
    brand_y = VIDEO_SIZE[1] * 0.22
    brand_txt = (TextClip(text="Aureon", font_size=110, color="white",
                          font=get_font("en", bold=True), text_align="center")
                 .with_duration(duration - brand_delay)
                 .with_start(brand_delay)
                 .with_position(("center", int(brand_y)))
                 .with_effects([vfx.CrossFadeIn(0.6)]))
    elements.append(brand_txt)

    # 标语 - Enterprise AI Knowledge Base（中号，品牌名下方）
    slogan_y = VIDEO_SIZE[1] * 0.34
    slogan_text = "Enterprise AI Knowledge Base"
    if lang == "zh":
        slogan_text = "企业级 AI 知识库"
    slogan_txt = (TextClip(text=slogan_text, font_size=36, color="#94a3b8",
                           font=get_font("en"), text_align="center")
                  .with_duration(duration - slogan_delay)
                  .with_start(slogan_delay)
                  .with_position(("center", int(slogan_y)))
                  .with_effects([vfx.CrossFadeIn(0.5)]))
    elements.append(slogan_txt)

    # 脉冲按钮 - Star on GitHub
    button_y = VIDEO_SIZE[1] * 0.50
    button_text = "★ Star on GitHub"
    pulse_btn = make_pulse_button(
        button_text, duration, button_y,
        color="#facc15", text_color="#000000",
        start_delay=button_delay
    )
    elements.append(pulse_btn)

    # GitHub URL - 选中态效果
    url_y = VIDEO_SIZE[1] * 0.62
    url_clip = make_selected_url(github_url, duration, url_y, start_delay=url_delay)
    elements.append(url_clip)

    # 底部三特性 - Open Source · MIT · Production Ready
    features_y = VIDEO_SIZE[1] * 0.78
    features_text = "Open Source  ·  MIT  ·  Production Ready"
    if lang == "zh":
        features_text = "开源  ·  MIT 协议  ·  生产就绪"

    # 特性图标（使用符号代替图标）
    feature_items = [
        ("◆", "Open Source" if lang == "en" else "开源"),
        ("◇", "MIT" if lang == "en" else "MIT 协议"),
        ("●", "Production Ready" if lang == "en" else "生产就绪"),
    ]

    # 计算每个特性的位置
    total_features_w = 900
    feature_gap = total_features_w / 3
    start_x = (VIDEO_SIZE[0] - total_features_w) // 2

    for i, (icon, label) in enumerate(feature_items):
        item_x = start_x + i * feature_gap + feature_gap // 2

        # 图标
        icon_clip = (TextClip(text=icon, font_size=20, color="#facc15",
                              font=get_font("en", bold=True), text_align="center")
                     .with_duration(duration - features_delay - i * 0.15)
                     .with_start(features_delay + i * 0.15)
                     .with_position((int(item_x), int(features_y)))
                     .with_effects([vfx.CrossFadeIn(0.4)]))
        elements.append(icon_clip)

        # 文字
        label_clip = (TextClip(text=label, font_size=22, color="#cbd5e1",
                               font=get_font("en"), text_align="center")
                      .with_duration(duration - features_delay - i * 0.15 - 0.1)
                      .with_start(features_delay + i * 0.15 + 0.1)
                      .with_position((int(item_x), int(features_y + 28)))
                      .with_effects([vfx.CrossFadeIn(0.4)]))
        elements.append(label_clip)

    return CompositeVideoClip(elements, size=VIDEO_SIZE).with_duration(duration)


def make_brand_watermark(duration: float, opacity: float = 0.15) -> TextClip:
    """右上角 subtle Aureon 文字水印，所有场景叠加。"""
    brand = (TextClip(text="Aureon", font_size=24, color="white",
                      font=get_font("en", bold=True))
             .with_duration(duration)
             .with_position((VIDEO_SIZE[0] - 120, 30))
             .with_opacity(opacity))
    return brand


def make_typing_clips(text: str, duration: float, position: tuple,
                      font_size: int = 28, color: str = "#1f2937",
                      lang: str = "en") -> list:
    """生成打字动画的 clips 列表（逐字输入 + 光标闪烁）。

    Args:
        text: 要输入的文字
        duration: 总时长
        position: 文字位置 (x, y)
        font_size: 字体大小
        color: 文字颜色
        lang: 语言

    Returns:
        TextClip 列表
    """
    font = get_font(lang)
    n = len(text)
    if n == 0:
        return []
    char_dur = duration / n
    clips = []

    for i in range(1, n + 1):
        display = text[:i] + "|"
        txt = (TextClip(text=display, font_size=font_size, color=color,
                        font=font)
               .with_duration(char_dur)
               .with_start((i - 1) * char_dur)
               .with_position(position))
        clips.append(txt)

    return clips


def make_loading_animation(duration: float, position: tuple,
                           lang: str = "en") -> list:
    """生成加载动画：三个跳动的点 + "Searching..." 文字。

    Args:
        duration: 总时长
        position: 加载文字位置 (x, y)
        lang: 语言

    Returns:
        Clip 列表
    """
    clips = []
    font = get_font(lang)
    text = "Searching your documents..." if lang == "en" else "正在搜索您的文档..."

    # 背景文字
    loading_text = (TextClip(text=text, font_size=24, color="#6b7280",
                             font=font)
                    .with_duration(duration)
                    .with_position(position)
                    .with_opacity(0.8))
    clips.append(loading_text)

    # 三个跳动的点
    dot_y = position[1] + 5
    dot_x_start = position[0] + 380 if lang == "en" else position[0] + 300
    for i in range(3):
        def make_dot_clip(delay, dot_x):
            def dot_frame(t):
                # 正弦波跳动
                offset = math.sin((t + delay) * 4) * 6
                return int(offset)
            return dot_frame

        dot = (TextClip(text="●", font_size=20, color="#3b82f6", font=font)
               .with_duration(duration)
               .with_position((dot_x_start + i * 25, dot_y))
               .with_effects([vfx.FadeIn(0.1)]))

        # 通过 transform 实现上下跳动
        def make_bounce(delay):
            def bounce(get_frame, t):
                frame = get_frame(t)
                offset = int(math.sin((t + delay) * 4) * 5)
                h, w = frame.shape[:2]
                result = np.zeros_like(frame)
                src_y1 = max(0, -offset)
                src_y2 = h + min(0, -offset)
                dst_y1 = max(0, offset)
                dst_y2 = h + min(0, offset)
                result[dst_y1:dst_y2, :] = frame[src_y1:src_y2, :]
                return result
            return bounce

        dot = dot.transform(make_bounce(i * 0.2))
        clips.append(dot)

    return clips


def make_citation_highlight(duration: float, x: int, y: int, w: int, h: int,
                            color: tuple = (250, 204, 21)) -> VideoClip:
    """在指定位置绘制黄色脉冲边框，用于高亮引用来源。

    Args:
        duration: 持续时间
        x: 左上角 x 坐标
        y: 左上角 y 坐标
        w: 宽度
        h: 高度
        color: 边框颜色 (R, G, B)

    Returns:
        VideoClip
    """
    border_thickness = 4

    def make_frame(t):
        # 脉冲效果：透明度在 0.3 - 1.0 之间变化
        pulse = 0.4 + 0.6 * abs(math.sin(t * 2.5))
        frame = np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 4), dtype=np.uint8)

        r, g, b = color
        a = int(pulse * 255)

        # 上边框
        frame[y:y + border_thickness, x:x + w] = [r, g, b, a]
        # 下边框
        frame[y + h - border_thickness:y + h, x:x + w] = [r, g, b, a]
        # 左边框
        frame[y:y + h, x:x + border_thickness] = [r, g, b, a]
        # 右边框
        frame[y:y + h, x + w - border_thickness:x + w] = [r, g, b, a]

        return frame

    return VideoClip(make_frame, duration=duration).with_fps(FPS)


def make_aha_scene(img_path: Path, duration: float,
                   lang: str = "en") -> CompositeVideoClip:
    """Aha Moment 动态场景：打字 → 加载 → 答案淡入 → 引用高亮 → Ken Burns 放大。

    时间线:
        0-1s:     输入框打字动画（问题逐字输入）
        1-2.5s:   加载动画（三个跳动的点 + Searching...）
        2.5-5s:   答案文本淡入（从上方滑入）
        5-8s:     引用来源高亮脉冲效果
        8-14s:    Ken Burns 缓慢放大到答案+引用区域
        14-16s:   停留

    Args:
        img_path: 截图路径
        duration: 总时长
        lang: 语言 (en/zh)

    Returns:
        CompositeVideoClip
    """
    if not img_path.exists():
        print(f"  [!] Missing: {img_path}")
        return None

    # ── 基础截图作为背景（完整显示，不裁剪） ──
    clip = ImageClip(str(img_path))
    img_w, img_h = clip.size

    # Aha scene expects a 1920x1080 viewport screenshot. Warn if not.
    if (img_w, img_h) != VIDEO_SIZE:
        print(f"  [!] Aha scene screenshot should be {VIDEO_SIZE}, got {(img_w, img_h)}. Overlays may misalign.")

    scale = min(VIDEO_SIZE[0] / max(img_w, 1), VIDEO_SIZE[1] / max(img_h, 1))
    base_clip = (CompositeVideoClip(
        [ColorClip(size=VIDEO_SIZE, color=(0, 0, 0)).with_duration(duration),
         clip.resized(scale).with_position("center").with_duration(duration)],
        size=VIDEO_SIZE
    ).with_duration(duration).with_fps(FPS))

    overlays = [base_clip]

    # ── 0-1s: 打字动画 ──
    # 搜索框位置估计（根据常见搜索界面布局调整）
    search_box_y = 180
    search_box_x = 300
    question_text = "What is the termination clause?" if lang == "en" else "终止条款是什么？"
    typing_clips = make_typing_clips(
        question_text, 1.0, (search_box_x, search_box_y),
        font_size=28, color="#1f2937", lang=lang
    )
    # 只在 0-1s 显示
    for tc in typing_clips:
        if tc.start < 1.0:
            tc = tc.with_end(min(tc.end, 1.0))
        overlays.append(tc)

    # 打字结束后保持完整文字（带光标）到 1.0s
    final_typing = (TextClip(text=question_text + "|", font_size=28, color="#1f2937",
                             font=get_font(lang))
                    .with_duration(0.1)
                    .with_start(0.95)
                    .with_position((search_box_x, search_box_y)))
    overlays.append(final_typing)

    # ── 1-2.5s: 加载动画 ──
    loading_clips = make_loading_animation(
        1.5, (search_box_x, search_box_y + 80), lang=lang
    )
    for lc in loading_clips:
        lc = lc.with_start(1.0)
        overlays.append(lc)

    # ── 2.5-5s: 答案文本淡入（从上方滑入） ──
    answer_text = "The agreement may be terminated by either party upon 30 days written notice."
    if lang == "zh":
        answer_text = "任何一方均可在提前 30 天书面通知后终止协议。"

    answer_y_start = 320
    answer_y_end = 350
    answer_x = 280

    # 答案背景框（半透明白色）
    answer_bg = (ColorClip(size=(900, 120), color=(255, 255, 255))
                 .with_opacity(0.0)
                 .with_duration(duration - 2.5)
                 .with_start(2.5)
                 .with_position((answer_x - 20, answer_y_end - 10)))

    # 淡入效果
    def fade_in_slide(get_frame, t):
        frame = get_frame(t)
        if t < 2.5:
            return frame
        elapsed = t - 2.5
        fade_duration = 2.5
        if elapsed >= fade_duration:
            progress = 1.0
        else:
            progress = elapsed / fade_duration
            # ease out
            progress = 1 - (1 - progress) ** 3

        # 从上方滑入
        y_offset = int((1 - progress) * 60)
        h, w = frame.shape[:2]
        result = np.zeros((h, w, 4), dtype=np.uint8)

        # 处理 alpha
        if frame.shape[2] == 4:
            alpha = frame[:, :, 3:4] * progress
            result = np.concatenate([frame[:, :, :3], alpha], axis=2)
        else:
            result[:, :, :3] = frame
            result[:, :, 3] = int(progress * 255)

        # 垂直位移
        shifted = np.zeros_like(result)
        src_y1 = max(0, y_offset)
        src_y2 = h + min(0, y_offset)
        dst_y1 = max(0, -y_offset)
        dst_y2 = h + min(0, -y_offset)
        shifted[dst_y1:dst_y2, :] = result[src_y1:src_y2, :]

        return shifted

    # 答案文本
    answer_txt = (TextClip(text=answer_text, font_size=32, color="#111827",
                           font=get_font(lang),
                           size=(880, None), method="caption")
                  .with_duration(duration - 2.5)
                  .with_start(2.5)
                  .with_position((answer_x, answer_y_end)))
    answer_txt = answer_txt.with_effects([vfx.CrossFadeIn(1.5)])

    # 滑入效果
    def slide_down(get_frame, t):
        frame = get_frame(t)
        elapsed = t
        if t < 0:
            return frame
        fade_duration = 2.5
        if elapsed >= fade_duration:
            return frame
        progress = elapsed / fade_duration
        progress = 1 - (1 - progress) ** 3
        y_offset = int((1 - progress) * 40)
        h, w = frame.shape[:2]
        shifted = np.zeros_like(frame)
        src_y1 = max(0, y_offset)
        src_y2 = h + min(0, y_offset)
        dst_y1 = max(0, -y_offset)
        dst_y2 = h + min(0, -y_offset)
        shifted[dst_y1:dst_y2, :] = frame[src_y1:src_y2, :]
        return shifted

    answer_txt = answer_txt.transform(slide_down)
    overlays.append(answer_txt)

    # ── 5-8s: 引用来源高亮脉冲效果 ──
    # 假设引用在右侧，有 3 个引用卡片
    citation_x = 1250
    citation_y_start = 340
    citation_w = 500
    citation_h = 100
    citation_gap = 120

    for i in range(3):
        cit_y = citation_y_start + i * citation_gap
        highlight = make_citation_highlight(
            3.0 - i * 0.3,
            citation_x, cit_y, citation_w, citation_h,
            color=(250, 204, 21)
        )
        highlight = highlight.with_start(5.0 + i * 0.4)
        overlays.append(highlight)

    return CompositeVideoClip(overlays, size=VIDEO_SIZE).with_duration(duration)


def make_hook_scene(pain_text: str, duration: float, lang: str = "en") -> CompositeVideoClip:
    """3秒开场Hook: 品牌闪现 + 痛点打字机 + 震动效果。

    时间线:
        0-0.5s:   Aureon 品牌名快速闪现（淡入+淡出）
        0.5-2.5s: 痛点文字打字机效果 + 轻微震动
        2.5-3.0s: 文字停留，准备转场
    """
    bg = ColorClip(size=VIDEO_SIZE, color=(0, 0, 0)).with_duration(duration)

    # 品牌名快速闪现 (0-0.5s)
    brand_flash = (TextClip(text="Aureon", font_size=72, color="white",
                            font=get_font("en", bold=True))
                   .with_duration(0.5)
                   .with_position(("center", VIDEO_SIZE[1] * 0.35))
                   .with_effects([vfx.CrossFadeIn(0.1), vfx.CrossFadeOut(0.2)]))

    # 痛点打字机效果 (0.5s 开始)
    font_size = 56
    font = get_font(lang)
    typewriter_start = 0.5
    typewriter_dur = duration - typewriter_start - 0.3  # 最后0.3s停留
    n = len(pain_text)
    char_dur = typewriter_dur / max(n, 1)
    char_clips = []

    for i in range(1, n + 1):
        display = pain_text[:i] + "|"
        txt = (TextClip(text=display, font_size=font_size, color="white", font=font,
                        size=(VIDEO_SIZE[0] - 200, None), method="caption")
               .with_duration(char_dur)
               .with_start(typewriter_start + (i - 1) * char_dur)
               .with_position(("center", VIDEO_SIZE[1] * 0.42)))
        char_clips.append(txt)

    # 最终帧无光标
    final_txt = (TextClip(text=pain_text, font_size=font_size, color="white", font=font,
                          size=(VIDEO_SIZE[0] - 200, None), method="caption")
                 .with_duration(duration - typewriter_start - n * char_dur)
                 .with_start(typewriter_start + n * char_dur)
                 .with_position(("center", VIDEO_SIZE[1] * 0.42)))
    char_clips.append(final_txt)

    # 打字机文字合成（无震动）
    text_composite = CompositeVideoClip(
        char_clips, size=VIDEO_SIZE
    ).with_duration(duration)

    # 震动效果：通过帧位移实现
    shake_amp = 3.0
    shake_freq_x = 35.0
    shake_freq_y = 28.0

    def _shake_frame(get_frame, t):
        frame = get_frame(t)
        if t < typewriter_start:
            return frame
        elapsed = t - typewriter_start
        decay = max(0, 1 - elapsed / max(0.01, typewriter_dur))
        dx = int(math.sin(t * shake_freq_x) * shake_amp * decay)
        dy = int(math.cos(t * shake_freq_y) * shake_amp * 0.5 * decay)

        h, w = frame.shape[:2]
        # 计算源区域和目标位置
        src_x1 = max(0, dx)
        src_y1 = max(0, dy)
        src_x2 = w + min(0, dx)
        src_y2 = h + min(0, dy)

        dst_x1 = max(0, -dx)
        dst_y1 = max(0, -dy)
        dst_x2 = w + min(0, -dx)
        dst_y2 = h + min(0, -dy)

        # 创建结果帧（黑色填充）
        result = np.zeros_like(frame)
        result[dst_y1:dst_y2, dst_x1:dst_x2] = frame[src_y1:src_y2, src_x1:src_x2]
        return result

    shaky_text = text_composite.transform(_shake_frame)

    return CompositeVideoClip([bg, brand_flash, shaky_text], size=VIDEO_SIZE)


# ─── Transition Effects ──────────────────────────────────────────────────

def push_transition(clip1, clip2, direction="left", duration=0.5):
    """Push 转场：clip2 从指定方向推入，将 clip1 推出画面。

    使用 with_position 函数动画实现，避免 effects 在嵌套 CompositeVideoClip
    上叠加时产生不可预期的混合/覆盖问题。

    Args:
        clip1: 前一个视频片段
        clip2: 后一个视频片段
        direction: 推入方向 ("left", "right", "up", "down")
        duration: 转场持续时间（秒）

    Returns:
        CompositeVideoClip: 带有 push 转场的合成片段
    """
    w, h = VIDEO_SIZE
    dur1 = clip1.duration
    half = duration

    # 方向 -> (clip1 退出方向向量, clip2 进入起始偏移)
    direction_map = {
        "left":   ((-1, 0), (w, 0)),   # clip1 左移，clip2 从右进入
        "right":  ((1, 0), (-w, 0)),   # clip1 右移，clip2 从左进入
        "up":     ((0, -1), (0, h)),   # clip1 上移，clip2 从下进入
        "down":   ((0, 1), (0, -h)),   # clip1 下移，clip2 从上进入
    }
    d1, start_offset = direction_map.get(direction, ((-1, 0), (w, 0)))

    def ease_in_out_cubic(t):
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - (-2 * t + 2) ** 3 / 2

    # clip1 位置：从 (0,0) 开始，在最后 duration 秒内向退出方向移动
    def pos1(t):
        if t < dur1 - half:
            return (0, 0)
        progress = (t - (dur1 - half)) / half
        progress = ease_in_out_cubic(min(1.0, max(0.0, progress)))
        return (int(d1[0] * w * progress), int(d1[1] * h * progress))

    # clip2 位置：从屏幕外开始，在前 duration 秒内移动到 (0,0)
    def pos2(t):
        local_t = t - (dur1 - half)
        if local_t < 0:
            return (start_offset[0], start_offset[1])
        if local_t > half:
            return (0, 0)
        progress = local_t / half
        progress = ease_in_out_cubic(min(1.0, max(0.0, progress)))
        return (int(start_offset[0] * (1 - progress)), int(start_offset[1] * (1 - progress)))

    clip1_moving = clip1.with_position(pos1)
    clip2_moving = clip2.with_start(dur1 - half).with_position(pos2)

    total_duration = dur1 + clip2.duration - duration
    return CompositeVideoClip(
        [clip1_moving, clip2_moving],
        size=VIDEO_SIZE
    ).with_duration(total_duration)


def fade_through_black(clip1, clip2, duration=0.4):
    """黑屏淡入淡出转场：clip1 淡出到黑色，再从黑色淡入 clip2。

    Args:
        clip1: 前一个视频片段
        clip2: 后一个视频片段
        duration: 转场总持续时间（秒），包含淡出和淡入各一半

    Returns:
        CompositeVideoClip: 带有黑屏转场的合成片段
    """
    dur1 = clip1.duration
    dur2 = clip2.duration
    half_dur = duration / 2

    # 总时长 = clip1 时长 + clip2 时长 - 转场重叠时间
    total_duration = dur1 + dur2 - duration

    # clip1: 最后 half_dur 时间淡出到黑
    clip1_fade = clip1.with_effects([vfx.CrossFadeOut(half_dur)])

    # clip2: 开始 half_dur 时间从黑淡入
    clip2_fade = clip2.with_start(dur1 - half_dur).with_effects([vfx.CrossFadeIn(half_dur)])

    # 黑色背景
    black_bg = ColorClip(size=VIDEO_SIZE, color=(0, 0, 0)).with_duration(total_duration)

    return CompositeVideoClip(
        [black_bg, clip1_fade, clip2_fade],
        size=VIDEO_SIZE
    ).with_duration(total_duration)


def add_button_breath(clip, x, y, w, h, duration):
    """按钮呼吸效果：缩放 + 透明度变化，用于强调可交互按钮。

    Args:
        clip: 底层视频片段
        x: 按钮左上角 x 坐标
        y: 按钮左上角 y 坐标
        w: 按钮宽度
        h: 按钮高度
        duration: 总持续时间

    Returns:
        CompositeVideoClip: 叠加了按钮呼吸效果的片段
    """
    def make_breath_frame(t):
        # 呼吸周期约 2 秒
        cycle = 2.0
        phase = (t % cycle) / cycle
        # 正弦波，在 0.9 - 1.05 之间缩放
        scale = 0.97 + 0.05 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi))
        # 透明度在 0.6 - 1.0 之间变化
        alpha = 0.7 + 0.3 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi + math.pi / 4))

        frame = np.zeros((VIDEO_SIZE[1], VIDEO_SIZE[0], 4), dtype=np.uint8)

        # 计算缩放后的按钮位置和尺寸
        new_w = int(w * scale)
        new_h = int(h * scale)
        new_x = x + (w - new_w) // 2
        new_y = y + (h - new_h) // 2

        # 绘制按钮边框（高亮效果）
        border_thickness = 3
        a = int(alpha * 255)

        # 上边框
        if new_y >= 0 and new_y + border_thickness < VIDEO_SIZE[1]:
            x1 = max(0, new_x)
            x2 = min(VIDEO_SIZE[0], new_x + new_w)
            if x2 > x1:
                frame[new_y:new_y + border_thickness, x1:x2] = [96, 165, 250, a]

        # 下边框
        if new_y + new_h - border_thickness >= 0 and new_y + new_h < VIDEO_SIZE[1]:
            x1 = max(0, new_x)
            x2 = min(VIDEO_SIZE[0], new_x + new_w)
            if x2 > x1:
                frame[new_y + new_h - border_thickness:new_y + new_h, x1:x2] = [96, 165, 250, a]

        # 左边框
        if new_x >= 0 and new_x + border_thickness < VIDEO_SIZE[0]:
            y1 = max(0, new_y)
            y2 = min(VIDEO_SIZE[1], new_y + new_h)
            if y2 > y1:
                frame[y1:y2, new_x:new_x + border_thickness] = [96, 165, 250, a]

        # 右边框
        if new_x + new_w - border_thickness >= 0 and new_x + new_w < VIDEO_SIZE[0]:
            y1 = max(0, new_y)
            y2 = min(VIDEO_SIZE[1], new_y + new_h)
            if y2 > y1:
                frame[y1:y2, new_x + new_w - border_thickness:new_x + new_w] = [96, 165, 250, a]

        return frame

    breath_overlay = VideoClip(make_breath_frame, duration=duration).with_fps(FPS)

    return CompositeVideoClip([clip, breath_overlay], size=VIDEO_SIZE).with_duration(duration)


def apply_transition_chain(clips, transitions):
    """按顺序应用一系列转场效果（扁平时间轴实现）。

    避免嵌套 CompositeVideoClip 过深导致 MoviePy 返回黑屏，同时提升渲染稳定性。

    Args:
        clips: 视频片段列表
        transitions: 转场配置列表，每项为 (type, kwargs) 元组
                     长度应为 len(clips) - 1

    Returns:
        合成后的完整视频片段
    """
    if len(clips) == 0:
        return None
    if len(clips) == 1:
        return clips[0]
    if len(transitions) != len(clips) - 1:
        raise ValueError(f"transitions 数量 ({len(transitions)}) 应等于 clips 数量 - 1 ({len(clips) - 1})")

    w, h = VIDEO_SIZE
    n = len(clips)

    direction_map = {
        "left": ((-1, 0), (w, 0)),
        "right": ((1, 0), (-w, 0)),
        "up": ((0, -1), (0, h)),
        "down": ((0, 1), (0, -h)),
    }

    def ease_in_out_cubic(t):
        if t < 0.5:
            return 4 * t * t * t
        return 1 - (-2 * t + 2) ** 3 / 2

    # 计算每个片段在最终时间轴上的起始时间（考虑转场重叠）
    entry = [0.0] * n
    for i in range(1, n):
        trans_dur = transitions[i - 1][1].get("duration", 0.0)
        entry[i] = entry[i - 1] + clips[i - 1].duration - trans_dur
    total_dur = entry[-1] + clips[-1].duration

    positioned = []
    for i, clip in enumerate(clips):
        dur = clip.duration
        t_in = transitions[i - 1][1].get("duration", 0.0) if i > 0 else 0.0
        t_out = transitions[i][1].get("duration", 0.0) if i < n - 1 else 0.0
        type_in = transitions[i - 1][0] if i > 0 else None
        type_out = transitions[i][0] if i < n - 1 else None
        dir_in = transitions[i - 1][1].get("direction", "left") if i > 0 else "left"
        dir_out = transitions[i][1].get("direction", "left") if i < n - 1 else "left"

        def make_pos(dur, t_in, type_in, dir_in, t_out, type_out, dir_out):
            def pos(t):
                if t < 0 or t > dur:
                    return (-w * 2, -h * 2)
                # 进入转场：新片段从屏幕外滑入
                if type_in == "push" and t_in > 0 and t < t_in:
                    p = ease_in_out_cubic(min(1.0, max(0.0, t / t_in)))
                    _, start = direction_map[dir_in]
                    return (int(start[0] * (1 - p)), int(start[1] * (1 - p)))
                # 退出转场：旧片段滑出屏幕
                if type_out == "push" and t_out > 0 and t > dur - t_out:
                    p = ease_in_out_cubic(min(1.0, max(0.0, (t - (dur - t_out)) / t_out)))
                    d1, _ = direction_map[dir_out]
                    return (int(d1[0] * w * p), int(d1[1] * h * p))
                return (0, 0)
            return pos

        pos_func = make_pos(dur, t_in, type_in, dir_in, t_out, type_out, dir_out)
        positioned.append(clip.with_start(entry[i]).with_position(pos_func))

    # fade_black 转场：在转场区间叠加一个透明度 0->1->0 的黑色层
    fade_overlays = []
    for i in range(n - 1):
        trans_type, trans_kwargs = transitions[i]
        if trans_type == "fade_black":
            T = trans_kwargs.get("duration", 0.4)
            half = T / 2
            start = entry[i] + clips[i].duration - T  # 与 entry[i+1] 相同

            def make_opacity(half, T):
                def op(t):
                    if t < 0 or t > T:
                        return 0.0
                    if t < half:
                        p = t / half
                    else:
                        p = 1 - (t - half) / half
                    return ease_in_out_cubic(min(1.0, max(0.0, p)))
                return op

            opacity_func = make_opacity(half, T)
            mask = VideoClip(
                lambda t, opacity_func=opacity_func: np.full(
                    (h, w), int(opacity_func(t) * 255), dtype=np.uint8
                ),
                duration=T,
            ).with_fps(FPS)
            black = (
                ColorClip(size=VIDEO_SIZE, color=(0, 0, 0))
                .with_duration(T)
                .with_mask(mask)
                .with_start(start)
            )
            fade_overlays.append(black)

    return CompositeVideoClip(positioned + fade_overlays, size=VIDEO_SIZE).with_duration(total_dur)


# ─── BGM Audio Mixing ────────────────────────────────────────────────────

def add_bgm(video_clip, bgm_path: Path, volume: float = 0.12) -> VideoClip:
    """给视频添加背景音乐，自动循环到视频时长，带淡入淡出效果。

    Args:
        video_clip: 原视频片段
        bgm_path: BGM 音频文件路径
        volume: BGM 音量（0.0-1.0，默认 0.12，作为很轻的衬底音量）

    Returns:
        VideoClip: 添加了 BGM 的视频片段
    """
    if not bgm_path or not bgm_path.exists():
        return video_clip

    # 加载 BGM 音频
    bgm = AudioFileClip(str(bgm_path))
    bgm_duration = bgm.duration
    video_duration = video_clip.duration

    # 循环 BGM 到视频时长（手动重复 subclip）
    if bgm_duration < video_duration:
        # 计算需要重复多少次
        loops = int(math.ceil(video_duration / bgm_duration))
        bgm_clips = []
        for i in range(loops):
            clip = bgm.with_start(i * bgm_duration)
            bgm_clips.append(clip)
        bgm = CompositeAudioClip(bgm_clips).with_duration(video_duration)

    # 设置音量
    bgm = bgm.with_volume_scaled(volume)

    # 添加淡入淡出效果
    bgm = bgm.with_effects([
        afx.AudioFadeIn(0.5),
        afx.AudioFadeOut(2.0),
    ])

    # 与视频原有音轨混合
    if video_clip.audio is not None:
        final_audio = CompositeAudioClip([video_clip.audio, bgm])
    else:
        final_audio = bgm

    final_with_bgm = video_clip.with_audio(final_audio)

    return final_with_bgm


# ─── Scene Assembly ──────────────────────────────────────────────────────

def build_scenes(scenes: list, lang: str, v2: bool = False) -> list:
    """Build all scene clips for given language.

    Args:
        scenes: 场景定义列表
        lang: 语言 (en/zh)
        v2: 是否启用 v2 模式（hook 开场 + 品牌水印）
    """
    clips = []
    audio_dir = AUDIO_DIR / lang

    for idx, s in enumerate(scenes):
        num = idx + 1
        dur = s["duration"]
        print(f"  [{num}/{len(scenes)}] {s['type']} ({dur:.1f}s)")

        # Build visual clip
        if s["type"] == "typewriter":
            visual = make_typewriter_clip(s["voiceover"], dur, lang)
        elif s["type"] == "hook":
            visual = make_hook_scene(s["caption"], dur, lang)
        elif s["type"] == "data_numbers":
            visual = make_data_numbers_clip(s.get("data", [s["caption"]]), dur)
        elif s["type"] == "data_bars":
            visual = make_data_bars_scene(s.get("data_items", []), dur, lang)
        elif s["type"] == "ending":
            visual = make_ending_clip("", s["caption"], dur)
        elif s["type"] == "ending_v2":
            visual = make_ending_v2(dur, lang)
        elif s["type"] == "image":
            img_path = SCREENSHOTS_DIR / s["file"]
            visual = make_ken_burns_clip(img_path, dur, s["zoom"], s["pan"])
            if visual is None:
                print(f"    [!] Skipping scene {num} - missing image")
                continue
        elif s["type"] == "aha":
            img_path = SCREENSHOTS_DIR / s["file"]
            visual = make_aha_scene(img_path, dur, lang)
            if visual is None:
                print(f"    [!] Skipping scene {num} - missing image")
                continue

        # Add voiceover audio
        audio_path = audio_dir / f"scene_{num}.mp3"
        if audio_path.exists():
            audio = AudioFileClip(str(audio_path)).with_start(0)
            visual = visual.with_audio(audio)

        # Add caption overlay (hook 场景自带文字，不需要额外字幕)
        if s["type"] != "hook":
            caption_pos = s.get("caption_position", "bottom") if v2 else "bottom"
            caption = make_caption(s["caption"], dur, lang, position=caption_pos)
            visual = CompositeVideoClip([visual, caption], size=VIDEO_SIZE)

        # v2 模式：叠加品牌水印
        if v2:
            watermark = make_brand_watermark(dur)
            visual = CompositeVideoClip([visual, watermark], size=VIDEO_SIZE)

        # v2 模式：Landing 页（第2个场景，索引1）添加按钮呼吸效果
        if v2 and idx == 1 and s["type"] in ("image", "aha"):
            # "Try It Now" 按钮位置估计（根据 Landing 页布局调整）
            # 假设按钮在页面中下部居中
            button_w = 240
            button_h = 60
            button_x = (VIDEO_SIZE[0] - button_w) // 2
            button_y = int(VIDEO_SIZE[1] * 0.65)
            visual = add_button_breath(visual, button_x, button_y, button_w, button_h, dur)
            print(f"    [+] Button breath effect added")

        clips.append(visual)

    return clips


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    import argparse
    import copy

    parser = argparse.ArgumentParser(description="Generate Aureon demo video")
    parser.add_argument("--lang", default="en", choices=["en", "zh"],
                        help="Language (en=English, zh=Chinese)")
    parser.add_argument("-o", "--output", default=None,
                        help="Output filename (default: aureon_demo_{lang}_{type}.mp4)")
    parser.add_argument("--type", dest="video_type", default="standard",
                        choices=["standard", "short"],
                        help="Video version (standard=~60s, short=~30s)")
    parser.add_argument("--skip-tts", action="store_true",
                        help="Skip TTS generation if audio exists")
    parser.add_argument("--v2", action="store_true",
                        help="Enable v2 hook scene with brand flash and watermark")
    parser.add_argument("--bgm", default=None,
                        help="Background music file path (supports loop, fade in/out)")
    args = parser.parse_args()

    lang = args.lang
    scenes = SCENES_EN if lang == "en" else SCENES_ZH
    video_type = args.video_type
    v2 = args.v2

    # v2 模式：复制场景列表并修改第一个场景为 hook 类型，第4个场景为 aha 类型
    if v2:
        scenes = copy.deepcopy(scenes)
        if scenes:
            hook_duration = 3.0 if video_type == "standard" else 2.0
            scenes[0] = {
                "type": "hook",
                "duration": hook_duration,
                "voiceover": scenes[0]["voiceover"],
                "caption": scenes[0]["caption"],
                "visual_buffer": 0.3,
                "caption_position": scenes[0].get("caption_position", "bottom"),
            }
            # 第4个场景（搜索答案页）使用 aha 动态场景
            if len(scenes) >= 4 and scenes[3]["type"] == "image":
                scenes[3] = {
                    "type": "aha",
                    "file": scenes[3]["file"],
                    "duration": scenes[3]["duration"],
                    "voiceover": scenes[3]["voiceover"],
                    "caption": scenes[3]["caption"],
                    "visual_buffer": scenes[3].get("visual_buffer", 8.0),
                    "caption_position": scenes[3].get("caption_position", "bottom"),
                }
            # 第5个场景（数据页）使用 bars 条形图场景
            if len(scenes) >= 5 and scenes[4]["type"] == "data_numbers":
                data_items = [
                    {
                        "value": 100,
                        "label": "Recall@5",
                        "description": "Perfect retrieval accuracy",
                        "max_val": 100,
                        "decimals": 0,
                        "prefix": "",
                        "suffix": "%",
                    },
                    {
                        "value": 590,
                        "label": "TTFT",
                        "description": "Sub-second response time",
                        "max_val": 1000,
                        "decimals": 0,
                        "prefix": "",
                        "suffix": "ms",
                    },
                    {
                        "value": 0.0003,
                        "label": "per query",
                        "description": "Near-zero cost at scale",
                        "max_val": 0.001,
                        "decimals": 4,
                        "prefix": "$",
                        "suffix": "",
                    },
                ]
                if lang == "zh":
                    data_items = [
                        {
                            "value": 100,
                            "label": "召回率",
                            "description": "完美的检索准确率",
                            "max_val": 100,
                            "decimals": 0,
                            "prefix": "",
                            "suffix": "%",
                        },
                        {
                            "value": 590,
                            "label": "响应时间",
                            "description": "亚秒级响应",
                            "max_val": 1000,
                            "decimals": 0,
                            "prefix": "",
                            "suffix": "ms",
                        },
                        {
                            "value": 0.0003,
                            "label": "每次查询",
                            "description": "近乎零成本扩展",
                            "max_val": 0.001,
                            "decimals": 4,
                            "prefix": "$",
                            "suffix": "",
                        },
                    ]
                scenes[4] = {
                    "type": "data_bars",
                    "data_items": data_items,
                    "duration": scenes[4]["duration"],
                    "voiceover": scenes[4]["voiceover"],
                    "caption": scenes[4]["caption"],
                    "visual_buffer": scenes[4].get("visual_buffer", 1.0),
                    "caption_position": scenes[4].get("caption_position", "bottom"),
                }
            # 第7个场景（结尾 CTA）使用增强版 ending_v2
            if len(scenes) >= 7 and scenes[6]["type"] == "ending":
                ending_duration = 8.0 if video_type == "standard" else 5.0
                scenes[6] = {
                    "type": "ending_v2",
                    "duration": ending_duration,
                    "voiceover": scenes[6]["voiceover"],
                    "caption": scenes[6]["caption"],
                    "visual_buffer": scenes[6].get("visual_buffer", 1.0),
                    "caption_position": scenes[6].get("caption_position", "bottom"),
                }

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Default output filename
    if args.output is None:
        v2_suffix = "_v2" if v2 else ""
        args.output = f"aureon_demo_{lang}_{video_type}{v2_suffix}.mp4"

    print(f"[*] Aureon Demo Video Generator")
    print(f"    Language: {lang.upper()}")
    print(f"    Version:  {video_type}")
    print(f"    V2 Hook:  {'enabled' if v2 else 'disabled'}")
    print(f"    BGM:      {args.bgm if args.bgm else 'none'}")
    print(f"    Output:   {args.output}\n")

    # Step 1: Ensure TTS audio
    print("[1/4] Generating TTS audio...")
    if not args.skip_tts:
        ensure_tts(scenes, lang)
    else:
        # 即使 skip-tts，也需要更新 duration
        audio_dir = AUDIO_DIR / lang
        for i, s in enumerate(scenes):
            mp3 = audio_dir / f"scene_{i + 1}.mp3"
            dur = get_tts_duration(mp3)
            if dur > 0:
                s["_audio_dur"] = dur
                min_dur = dur + s.get("visual_buffer", 1.0)
                if s["duration"] < min_dur and s["type"] != "hook":
                    s["duration"] = math.ceil(min_dur * 10) / 10
            else:
                s["_audio_dur"] = s["duration"]

    total_audio = sum(s.get("_audio_dur", s["duration"]) for s in scenes)
    total_visual = sum(s["duration"] for s in scenes)
    print(f"    Audio total: {total_audio:.1f}s, Visual total: {total_visual:.1f}s\n")

    # Step 2: Build scene clips
    print("[2/4] Building scenes...")
    clips = build_scenes(scenes, lang, v2=v2)
    if not clips:
        print("[!] No clips generated. Aborting.")
        sys.exit(1)

    # Step 3: Concatenate with transitions
    if v2 and len(clips) > 1:
        # v2 模式：使用电影级转场
        print(f"\n[3/4] Stitching {len(clips)} clips with cinematic transitions...")
        # 定义转场序列
        # Scene 1→2: push left
        # Scene 2→3: push left
        # Scene 3→4: push left
        # Scene 4→5: fade through black
        # Scene 5→6: push left
        # Scene 6→7: fade through black
        transitions = [
            ("push", {"direction": "left", "duration": 0.5}),
            ("push", {"direction": "left", "duration": 0.5}),
            ("push", {"direction": "left", "duration": 0.5}),
            ("fade_black", {"duration": 0.4}),
            ("push", {"direction": "left", "duration": 0.5}),
            ("fade_black", {"duration": 0.4}),
        ]
        # 只取前 len(clips)-1 个转场
        transitions = transitions[:len(clips) - 1]
        final = apply_transition_chain(clips, transitions)
        print(f"    Transitions: push x{sum(1 for t, _ in transitions if t == 'push')}, fade_black x{sum(1 for t, _ in transitions if t == 'fade_black')}")
    else:
        # 普通模式：使用 crossfade 硬切
        print(f"\n[3/4] Stitching {len(clips)} clips with crossfade ({CROSSFADE}s)...")
        if len(clips) > 1:
            final = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE)
        else:
            final = clips[0]

    total_dur = final.duration
    print(f"    Total duration: {total_dur:.1f}s")

    # Short version: 确保 CTA 完整显示至少 2 秒
    if video_type == "short":
        target_duration = 30.0
        min_cta_visible = 2.0  # CTA 至少完整显示 2 秒

        if v2 and len(scenes) >= 7:
            # v2 模式：计算 CTA 场景开始时间，确保完整显示
            # 计算前 6 个场景的总时长（考虑转场重叠）
            transition_dur = 0.5  # push 转场
            fade_dur = 0.4  # fade_black 转场
            # 前 6 个场景有 5 个转场，最后一个 fade_black 进入 CTA
            # 简化计算：假设 CTA 场景开始时间 = 总时长 - CTA 时长 + 转场时间
            cta_scene = scenes[6]
            cta_dur = cta_scene["duration"]

            # 计算 CTA 应该开始的最早时间，确保至少显示 min_cta_visible 秒
            cta_must_start_by = target_duration - min_cta_visible

            if total_dur > target_duration:
                # 需要裁剪，但要保证 CTA 完整显示
                # 计算 CTA 场景的实际开始时间（考虑转场）
                # 简化：直接截到 target_duration，但确保不裁掉 CTA 的最后 min_cta_visible 秒
                # 如果 30 秒时 CTA 还没显示够 2 秒，就延长到 CTA 显示够 2 秒

                # 估算 CTA 开始时间（粗略）
                cta_start_est = total_dur - cta_dur + fade_dur

                # 确保裁剪时间点在 CTA 开始 + min_cta_visible 之后
                trim_time = min(target_duration, total_dur)
                cta_visible_time = trim_time - cta_start_est

                if cta_visible_time < min_cta_visible:
                    # 延长裁剪时间，让 CTA 至少显示 min_cta_visible 秒
                    trim_time = cta_start_est + min_cta_visible
                    trim_time = min(trim_time, total_dur)
                    print(f"    [Adjust] CTA visible only {cta_visible_time:.1f}s, extending to {trim_time:.1f}s")

                final = final.subclipped(0, trim_time)
                print(f"    Short trim to {trim_time:.1f}s (CTA visible: {trim_time - cta_start_est:.1f}s)")
            else:
                final = final.subclipped(0, total_dur)
                print(f"    Short version: {total_dur:.1f}s (under 30s)")
        else:
            # 非 v2 模式：直接裁剪到 30 秒
            final = final.subclipped(0, min(30.0, total_dur))
            print(f"    Short trim to 30s")

    # Step 4: Add BGM (if specified)
    if args.bgm:
        bgm_path = Path(args.bgm)
        print(f"\n[4/5] Adding background music...")
        if bgm_path.exists():
            final = add_bgm(final, bgm_path, volume=0.12)
            print(f"    BGM added: {args.bgm}")
        else:
            print(f"    [!] BGM file not found, skipping: {args.bgm}")

        # Step 5: Render
        step_render = "5/5"
    else:
        step_render = "4/4"

    # Render
    output_path = OUTPUT_DIR / args.output
    print(f"\n[{step_render}] Rendering to {output_path} ...")
    print(f"    Resolution: {VIDEO_SIZE[0]}x{VIDEO_SIZE[1]} @ {FPS}fps")
    final.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        bitrate="8000k",
        audio_bitrate="192k",
        logger="bar",
    )

    print(f"\n[OK] Video saved to: {output_path}")
    print(f"     Duration: {final.duration:.1f}s")
    print(f"     Size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
