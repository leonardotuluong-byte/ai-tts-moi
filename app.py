import streamlit as st
import edge_tts
import asyncio
import tempfile
import os

st.set_page_config(
    page_title="Edge TTS - Đa Ngôn Ngữ Không Giới Hạn",
    page_icon="🌍",
    layout="centered"
)

st.title("🌍 Ứng dụng Chuyển Văn Bản Thành Giọng Nói (Edge TTS)")
st.write("Hỗ trợ tiếng Tây Ban Nha, Anh, Pháp, Việt và không giới hạn độ dài văn bản.")

# Hàm tải danh sách giọng đọc an toàn
@st.cache_data
def load_voices():
    async def get_all():
        return await edge_tts.list_voices()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(get_all())
    finally:
        loop.close()

with st.spinner("Đang tải danh sách giọng đọc..."):
    try:
        voices = load_voices()
    except Exception as e:
        st.error(f"Lỗi tải danh sách giọng đọc: {e}")
        voices = []

if voices:
    language_mapping = {
        "🇪🇸 Tiếng Tây Ban Nha (Spanish)": ["es-ES", "es-MX", "es-AR", "es-CO", "es-US"],
        "🇬🇧/🇺🇸 Tiếng Anh (English)": ["en-US", "en-GB", "en-AU", "en-CA", "en-IN"],
        "🇫🇷 Tiếng Pháp (French)": ["fr-FR", "fr-CA", "fr-CH", "fr-BE"],
        "🇻🇳 Tiếng Việt (Vietnamese)": ["vi-VN"]
    }

    selected_group_label = st.selectbox("Chọn nhóm ngôn ngữ:", list(language_mapping.keys()))
    valid_locales = language_mapping[selected_group_label]
    filtered_voices = [v for v in voices if v["Locale"] in valid_locales]

    if filtered_voices:
        voice_options = {f"{v['FriendlyName']} ({v['Gender']}) - [{v['Locale']}]": v["ShortName"] for v in filtered_voices}
        selected_voice_label = st.selectbox("Chọn giọng đọc cụ thể:", list(voice_options.keys()))
        selected_voice_code = voice_options[selected_voice_label]
    else:
        st.warning("Không tìm thấy giọng đọc phù hợp.")
        selected_voice_code = None

    text_input = st.text_area(
        "Nhập nội dung văn bản cần chuyển đổi:",
        placeholder="Dán văn bản dài của bạn vào đây...",
        height=200
    )

    # Hàm tạo âm thanh với cơ chế khởi tạo Communicate ổn định hơn
    async def generate_audio(text, voice_code, output_path):
        communicate = edge_tts.Communicate(text=text, voice=voice_code)
        await communicate.save(output_path)

    if st.button("🎧 Tạo và Phát Âm Thanh", type="primary"):
        if not text_input.strip():
            st.warning("Vui lòng nhập văn bản trước khi chuyển đổi!")
        elif not selected_voice_code:
            st.warning("Vui lòng chọn giọng đọc!")
        else:
            with st.spinner("Đang xử lý âm thanh..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                        output_path = tmp_file.name

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(generate_audio(text_input, selected_voice_code, output_path))
                    finally:
                        loop.close()

                    st.success("🎉 Tạo âm thanh thành công!")
                    st.audio(output_path, format="audio/mp3")

                    with open(output_path, "rb") as f:
                        audio_bytes = f.read()

                    st.download_button(
                        label="📥 Tải xuống file MP3",
                        data=audio_bytes,
                        file_name="edge_tts_output.mp3",
                        mime="audio/mp3"
                    )

                except Exception as e:
                    st.error(f"Lỗi trong quá trình tạo âm thanh: {e}")
