import asyncio
import io
import os
import subprocess
import tempfile
import edge_tts
from pydub import AudioSegment, silence
from pydub.effects import normalize
from pydub.scipy_effects import low_pass_filter
import srt
import streamlit as st

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="AI TTS Pro - Streamlit", page_icon="🎙️", layout="wide"
)

# =========================================================================
# 1. LẤY DANH SÁCH GIỌNG ĐỌC (Được cache để tối ưu khởi động)
# =========================================================================


@st.cache_resource
def get_voices_sync():
  try:
    if os.name == "nt":
      asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(edge_tts.list_voices())
  except Exception as e:
    print(f"Lỗi lấy giọng đọc: {e}")
    return []


ALL_VOICES = get_voices_sync()
LOCALES = (
    sorted(list(set([v["Locale"] for v in ALL_VOICES])))
    if ALL_VOICES
    else ["es-ES"]
)
DEFAULT_LOCALE = "es-ES" if "es-ES" in LOCALES else LOCALES[0]


def trim_audio_silence(audio_segment):
  """Cắt khoảng lặng 2 đầu một cách nhẹ nhàng"""
  if len(audio_segment) < 100:
    return audio_segment
  try:
    start_trim = silence.detect_leading_silence(
        audio_segment, silence_threshold=-40.0
    )
    end_trim = silence.detect_leading_silence(
        audio_segment.reverse(), silence_threshold=-40.0
    )

    start_trim = max(0, start_trim - 20)
    end_trim = max(0, end_trim - 20)

    if start_trim + end_trim >= len(audio_segment):
      return audio_segment

    return audio_segment[start_trim : len(audio_segment) - end_trim]
  except Exception as e:
    print(f"Lỗi khi cắt khoảng lặng: {e}")
    return audio_segment


# =========================================================================
# 2. HÀM CO GIÃN THỜI GIAN CHUYÊN NGHIỆP BẰNG FFMPEG (ATEMPO)
# =========================================================================
def stretch_audio_ffmpeg(audio_segment, factor):
  """Sử dụng thuật toán atempo của FFmpeg để tăng tốc mượt mà không nuốt chữ"""
  if factor <= 1.0:
    return audio_segment

  safe_factor = min(factor, 1.35)

  with tempfile.NamedTemporaryFile(
      suffix=".wav", delete=False
  ) as temp_in, tempfile.NamedTemporaryFile(
      suffix=".wav", delete=False
  ) as temp_out:
    try:
      audio_segment.export(temp_in.name, format="wav")

      cmd = [
          "ffmpeg",
          "-y",
          "-i",
          temp_in.name,
          "-filter:a",
          f"atempo={safe_factor}",
          temp_out.name,
      ]
      subprocess.run(
          cmd,
          check=True,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
      )

      stretched_seg = AudioSegment.from_wav(temp_out.name)
      return stretched_seg
    except Exception as e:
      print(f"⚠️ Lỗi FFmpeg atempo, giữ nguyên tốc độ gốc: {e}")
      return audio_segment
    finally:
      if os.path.exists(temp_in.name):
        os.remove(temp_in.name)
      if os.path.exists(temp_out.name):
        os.remove(temp_out.name)


# =========================================================================
# 3. HÀM GỌI TTS BẤT ĐỒNG BỘ (CHỐNG RATE LIMIT & LOG LỖI)
# =========================================================================
async def run_tts_with_retry(text, voice_code, retries=5):
  text = text.strip()
  if not text:
    return None

  for attempt in range(retries):
    try:
      communicate = edge_tts.Communicate(text, voice_code, rate="+5%")
      audio_data = bytearray()
      async for chunk in communicate.stream():
        if chunk["type"] == "audio":
          audio_data.extend(chunk["data"])

      if audio_data:
        return bytes(audio_data)
    except Exception as e:
      print(
          f"⚠️ Cảnh báo: Lỗi TTS câu '{text[:30]}...' (Thử lại"
          f" {attempt+1}/{retries}): {e}"
      )
      await asyncio.sleep(1.5 * (attempt + 1))
      continue

  print(f"❌ LỖI NẶNG: Thất bại hoàn toàn với câu: '{text}' sau {retries} lần.")
  return None


# =========================================================================
# 4. LÕI XỬ LÝ ÂM THANH CHÍNH
# =========================================================================
async def process_audio(input_text, voice):
  if not input_text or not input_text.strip():
    return None, "❌ Vui lòng nhập kịch bản!"
  if not voice:
    return None, "❌ Vui lòng chọn giọng đọc!"

  try:
    is_srt = " --> " in input_text

    if not is_srt:
      res = await run_tts_with_retry(input_text, voice)
      if res:
        seg = AudioSegment.from_file(io.BytesIO(res), format="mp3")
        seg = seg.set_frame_rate(44100).set_channels(1).set_sample_width(2)
        seg = low_pass_filter(seg, cutoff_freq=8000)
        seg = normalize(seg)

        temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        seg.export(temp_out.name, format="mp3", bitrate="192k")
        return temp_out.name, "✅ Xử lý văn bản thường thành công!"
      return None, "❌ Lỗi: Không thể tải giọng đọc từ máy chủ."

    else:
      subs = list(srt.parse(input_text))
      if not subs:
        return None, "❌ SRT không hợp lệ!"

      final_audio = AudioSegment.silent(
          duration=0, frame_rate=44100
      ).set_channels(1).set_sample_width(2)
      failed_lines = []

      for i, sub in enumerate(subs):
        text_content = sub.content.strip()
        if not text_content:
          continue

        chunk = await run_tts_with_retry(text_content, voice)

        if chunk:
          seg = AudioSegment.from_file(io.BytesIO(chunk), format="mp3")
          seg = seg.set_frame_rate(44100).set_channels(1).set_sample_width(2)

          seg = normalize(seg)
          seg = trim_audio_silence(seg)

          srt_start_ms = int(sub.start.total_seconds() * 1000)
          duration_allowed_ms = (sub.end - sub.start).total_seconds() * 1000

          if duration_allowed_ms <= 0:
            duration_allowed_ms = 500

          actual_duration_ms = len(seg)

          if actual_duration_ms > duration_allowed_ms:
            factor = actual_duration_ms / duration_allowed_ms
            seg = stretch_audio_ffmpeg(seg, factor)

          if len(final_audio) < srt_start_ms:
            gap = srt_start_ms - len(final_audio)
            final_audio += AudioSegment.silent(
                duration=gap, frame_rate=44100
            )

          final_audio += seg
        else:
          failed_lines.append(f"Dòng {i+1}")

        await asyncio.sleep(0.5)

      final_audio = low_pass_filter(final_audio, cutoff_freq=8000)
      final_audio = normalize(final_audio)

      temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
      final_audio.export(temp_out.name, format="mp3", bitrate="192k")

      if failed_lines:
        msg = (
            f"⚠️ Xong, nhưng có {len(failed_lines)} câu bị mất: "
            f"{', '.join(failed_lines[:5])}..."
        )
        return temp_out.name, msg

      return (
          temp_out.name,
          "✅ Hoàn thành xuất sắc! Âm thanh co giãn mượt mà nhờ FFmpeg.",
      )

  except Exception as e:
    print(f"LỖI HỆ THỐNG: {e}")
    return None, f"❌ Lỗi hệ thống: {str(e)}"


# =========================================================================
# GIAO DIỆN STREAMLIT
# =========================================================================
st.markdown(
    "<h2 style='text-align: center; color: #22c55e;'>🎙️ AI TTS Pro - Đồng Bộ"
    " Trôi Chảy Tối Ưu (Streamlit & FFmpeg)</h2>",
    unsafe_allow_html=True,
)
st.write("")

col1, col2 = st.columns([2, 1], gap="large")

with col1:
  st.markdown("### 📝 Kịch bản (Hỗ trợ Văn bản & SRT)")
  input_text = st.text_area(
      "Dán nội dung vào đây",
      placeholder="Nhập văn bản hoặc dán file SRT...",
      height=380,
  )
  process_btn = st.button(
      "🚀 BẮT ĐẦU LỒNG TIẾNG", type="primary", use_container_width=True
  )

with col2:
  st.markdown("### ⚙️ Cấu hình Giọng đọc")

  sub_col1, sub_col2 = st.columns(2)
  with sub_col1:
    lang_filter = st.selectbox(
        "🌐 Ngôn ngữ",
        options=LOCALES,
        index=(
            LOCALES.index(DEFAULT_LOCALE) if DEFAULT_LOCALE in LOCALES else 0
        ),
    )
  with sub_col2:
    gender_filter = st.radio(
        "👤 Giới tính", options=["All", "Male", "Female"], horizontal=True
    )

  # Lọc danh sách giọng đọc theo lựa chọn
  filtered_voices = [v for v in ALL_VOICES if v["Locale"] == lang_filter]
  if gender_filter != "All":
    filtered_voices = [
        v for v in filtered_voices if v["Gender"] == gender_filter
    ]

  voice_choices = [v["ShortName"] for v in filtered_voices]
  voice_dropdown = st.selectbox(
      "🎙️ Chọn giọng đọc",
      options=voice_choices if voice_choices else [""],
  )

  st.markdown("---")
  st.markdown("### 🎵 Kết quả")
  output_audio_placeholder = st.empty()
  status_placeholder = st.empty()

# Xử lý sự kiện khi bấm nút
if process_btn:
  if os.name == "nt":
    try:
      asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
      pass

  with st.spinner("Đang xử lý âm thanh, vui lòng đợi..."):
    audio_path, status_msg = asyncio.run(
        process_audio(input_text, voice_dropdown)
    )

    if audio_path and os.path.exists(audio_path):
      status_placeholder.success(status_msg)
      output_audio_placeholder.audio(audio_path, format="audio/mp3")
    else:
      status_placeholder.error(status_msg)
