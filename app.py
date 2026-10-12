import streamlit as st
import edge_tts
from gtts import gTTS
import asyncio
import tempfile
import os

st.set_page_config(
    page_title="TTS App - Đa Ngôn Ngữ Không Giới Hạn",
    page_icon="🎙️",
    layout="centered"
)

st.title("🎙️ Ứng dụng Chuyển Văn Bản Thành Giọng Nói")
st.write("Hỗ trợ tiếng Tây Ban Nha, Anh, Pháp, Việt và nhiều giọng đọc tự nhiên. Tự động khắc phục lỗi kết nối server!")

# Danh sách ngôn ngữ cố định an toàn
LANGUAGE_CONFIG = {
    "🇪🇸 Tiếng Tây Ban Nha (Spanish)": {
        "gtts_code": "es",
        "voices": [
            {"name": "Microsoft Alvaro (Nam) - US", "code": "es-US-AlvaroNeural"},
            {"name": "Microsoft Paloma (Nữ) - US", "code": "es-US-PalomaNeural"},
            {"name": "Microsoft Elvira (Nữ) - Tây Ban Nha", "code": "es-ES-ElviraNeural"},
            {"name": "Microsoft Alvaro (Nam) - Tây Ban Nha", "code": "es-ES-AlvaroNeural"},
            {"name": "Microsoft Dalia (Nữ) - Mexico", "code": "es-MX-DaliaNeural"}
        ]
    },
    "🇬🇧/🇺🇸 Tiếng Anh (English)": {
        "gtts_code": "en",
        "voices": [
            {"name": "Microsoft Jenny (Nữ) - US", "code": "en-US-JennyNeural"},
            {"name": "Microsoft Guy (Nam) - US", "code": "en-US-GuyNeural"},
            {"name": "Microsoft Sonia (Nữ) - Anh", "code": "en-GB-SoniaNeural"},
            {"name": "Microsoft Ryan (Nam) - Anh", "code": "en-GB-RyanNeural"}
        ]
    },
    "🇫🇷 Tiếng Pháp (French)": {
        "gtts_code": "fr",
        "voices": [
            {"name": "Microsoft Denise (Nữ) - Pháp", "code": "fr-FR-DeniseNeural"},
            {"name": "Microsoft Henri (Nam) - Pháp", "code": "fr-FR-HenriNeural"},
            {"name": "Microsoft Sylvie (Nữ) - Canada", "code": "fr-CA-SylvieNeural"}
        ]
    },
    "🇻🇳 Tiếng Việt (Vietnamese)": {
        "gtts_code": "vi",
        "voices": [
            {"name": "Microsoft HoaiMy (Nữ) - Việt Nam", "code": "vi-VN-HoaiMyNeural"},
            {"name": "Microsoft NamMinh (Nam) - Việt Nam", "code": "vi-VN-NamMinhNeural"}
        ]
    }
}

# Chọn nhóm ngôn ngữ
selected_lang_name = st.selectbox("Chọn nhóm ngôn ngữ:", list(LANGUAGE_CONFIG.keys()))
lang_data = LANGUAGE_CONFIG[selected_lang_name]

# Chọn giọng đọc
voice_options = {v["name"]: v["code"] for v in lang_data["voices"]}
selected_voice_label = st.selectbox("Chọn giọng đọc:", list(voice_options.keys()))
selected_voice_code = voice_options[selected_voice_label]

# Nhập văn bản
text_input = st.text_area(
    "Nhập nội dung văn bản:",
    placeholder="Dán văn bản tiếng Tây Ban Nha, Anh, Pháp hoặc Việt vào đây...",
    height=200
)

# Hàm gọi Edge TTS
async def run_edge_tts(text, voice_code, output_path):
    communicate = edge_tts.Communicate(text=text, voice=voice_code)
    await communicate.save(output_path)

if st.button("🎧 Tạo và Phát Âm Thanh", type="primary"):
    if not text_input.strip():
        st.warning("Vui lòng nhập văn bản trước!")
    else:
        with st.spinner("Đang xử lý âm thanh..."):
            success = False
            output_path = ""
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                output_path = tmp_file.name

            # Thử 1: Dùng Edge TTS
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_edge_tts(text_input, selected_voice_code, output_path))
                loop.close()
                success = True
                st.success("🎉 Tạo âm thanh thành công (Edge Voice)!")
            except Exception as e_edge:
                # Nếu Edge TTS dính 403 (Server IP bị cấm), tự động dùng gTTS
                st.info("🔄 Server Edge bị chặn kết nối (403), đang chuyển sang kênh dự phòng...")
                try:
                    tts_backup = gTTS(text=text_input, lang=lang_data["gtts_code"], slow=False)
                    tts_backup.save(output_path)
                    success = True
                    st.success("🎉 Tạo âm thanh thành công (Kênh dự phòng Google TTS)!")
                except Exception as e_backup:
                    st.error(f"Lỗi khởi tạo âm thanh: {e_backup}")

            if success and os.path.exists(output_path):
                st.audio(output_path, format="audio/mp3")

                with open(output_path, "rb") as f:
                    audio_bytes = f.read()

                st.download_button(
                    label="📥 Tải xuống file MP3",
                    data=audio_bytes,
                    file_name="tts_audio.mp3",
                    mime="audio/mp3"
                )
