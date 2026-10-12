import asyncio
import io
import os
import subprocess
import tempfile
import edge_tts
import srt
import streamlit as st

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="AI TTS Pro - Streamlit", page_icon="🎙️", layout="wide"
)


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

  return None


async def process_audio(input_text, voice):
  if not input_text or not input_text.strip():
    return None, "❌ Vui lòng nhập kịch bản!"
  if not voice:
    return None, "❌ Vui lòng chọn giọng đọc!"

  try:
    # Kiểm tra xem có phải định dạng SRT chuẩn hay không (phải có cấu trúc thời gian timestamp)
    is_srt = " --> " in input_text and any(
        "-->" in line for line in input_text.splitlines()
    )

    if not is_srt:
      # Nếu là văn bản thường, chia nhỏ văn bản theo dấu chấm câu để tránh quá tải server edge-tts
      paragraphs = [p.strip() for p in input_text.split("\n") if p.strip()]
      if not paragraphs:
        return None, "❌ Nội dung trống!"

      combined_audio_chunks = []
      for para in paragraphs:
        # Tách tiếp theo câu nếu đoạn quá dài
        sentences = [s.strip() for s in para.split(".") if s.strip()]
        for sentence in sentences:
          if not sentence:
            continue
          res = await run_tts_with_retry(sentence + ".", voice)
          if res:
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tf.write(res)
            tf.close()
            combined_audio_chunks.append(tf.name)
          await asyncio.sleep(0.3)

      if not combined_audio_chunks:
        return None, (
            "❌ Không thể tải giọng đọc từ máy chủ. Vui lòng thử lại sau!"
        )

      # Ghép các đoạn âm thanh văn bản thường lại bằng FFmpeg concat
      list_file_path = tempfile.NamedTemporaryFile(
          delete=False, mode="w", suffix=".txt", encoding="utf-8"
      )
      for fpath in combined_audio_chunks:
        list_file_path.write(f"file '{fpath}'\n")
      list_file_path.close()

      output_path = tempfile.NamedTemporaryFile(
          delete=False, suffix=".mp3"
      ).name
      cmd = [
          "ffmpeg",
          "-y",
          "-f",
          "concat",
          "-safe",
          "0",
          "-i",
          list_file_path.name,
          "-c",
          "copy",
          output_path,
      ]
      subprocess.run(
          cmd,
          check=True,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
      )

      # Dọn dẹp file tạm
      os.remove(list_file_path.name)
      for fpath in combined_audio_chunks:
        if os.path.exists(fpath):
          os.remove(fpath)

      return output_path, "✅ Xử lý văn bản thường thành công!"

    else:
      # Xử lý chuẩn file SRT
      subs = list(srt.parse(input_text))
      if not subs:
        return None, "❌ SRT không hợp lệ!"

      temp_files = []
      failed_lines = []

      for i, sub in enumerate(subs):
        text_content = sub.content.strip()
        if not text_content:
          continue

        chunk = await run_tts_with_retry(text_content, voice)
        if chunk:
          tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
          tf.write(chunk)
          tf.close()

          srt_start_ms = int(sub.start.total_seconds() * 1000)
          duration_allowed_ms = (sub.end - sub.start).total_seconds() * 1000
          if duration_allowed_ms <= 0:
            duration_allowed_ms = 500

          temp_files.append(
              (srt_start_ms, duration_allowed_ms, tf.name, text_content)
          )
        else:
          failed_lines.append(f"Dòng {i+1}")

        await asyncio.sleep(0.3)

      if not temp_files:
        return None, "❌ Không thể tạo được đoạn âm thanh nào từ SRT!"

      output_path = tempfile.NamedTemporaryFile(
          delete=False, suffix=".mp3"
      ).name
      inputs = []
      filter_complex_parts = []

      for idx, (start_ms, _, fpath, _) in enumerate(temp_files):
        inputs.extend(["-i", fpath])
        filter_complex_parts.append(
            f"[{idx}:a]adelay={start_ms}|{start_ms}[a{idx}]"
        )

      mix_inputs = "".join([f"[a{idx}]" for idx in range(len(temp_files))])
      filter_complex_parts.append(
          f"{mix_inputs}amix=inputs={len(temp_files)}:duration=longest[out]"
      )

      cmd = [
          "ffmpeg",
          "-y",
      ] + inputs + ["-filter_complex", ";".join(filter_complex_parts), "-map", "[out]", output_path]

      subprocess.run(
          cmd,
          check=True,
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
      )

      for _, _, fpath, _ in temp_files:
        if os.path.exists(fpath):
          os.remove(fpath)

      if failed_lines:
        msg = (
            f"⚠️ Xong, nhưng có {len(failed_lines)} câu bị lỗi:"
            f" {', '.join(failed_lines[:5])}"
        )
        return output_path, msg

      return output_path, "✅ Hoàn thành xuất sắc đồng bộ SRT bằng FFmpeg!"

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

if process_btn:
  if os.name == "nt":
    try:
      asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
      pass

  with st.spinner(
      "Đang xử lý âm thanh và gọi máy chủ, vui lòng đợi một chút..."
  ):
    audio_path, status_msg = asyncio.run(
        process_audio(input_text, voice_dropdown)
    )

    if audio_path and os.path.exists(audio_path):
      status_placeholder.success(status_msg)
      output_audio_placeholder.audio(audio_path, format="audio/mp3")
    else:
      status_placeholder.error(status_msg)
