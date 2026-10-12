import streamlit as st
import edge_tts
import asyncio
import os

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Edge TTS - Chuyển Văn Bản Thành Giọng Nói",
    page_icon="🔊",
    layout="centered"
)

st.title("🔊 Microsoft Edge Text-to-Speech")
st.write("Chuyển đổi văn bản dài (không giới hạn ký tự) với đầy đủ các giọng đọc từ Microsoft Edge.")

# Hàm bất đồng bộ lấy danh sách tất cả các giọng đọc khả dụng từ Edge
@st.cache_data
def get_voices():
    async def _fetch():
        voices = await edge_tts.list_voices()
        return voices
    return asyncio.run(_fetch())

# Tải danh sách giọng đọc
try:
    all_voices = get_voices()
except Exception as e:
    st.error(f"Không thể tải danh sách giọng đọc: {e}")
    all_voices = []

if all_voices:
    # Lọc danh sách ngôn ngữ/quốc gia
    languages = sorted(list(set([v["Locale"] for v in all_voices])))
    
    # Mặc định chọn vi-VN nếu có
    default_lang_index = languages.index("vi-VN") if "vi-VN" in languages else 0
    
    col1, col2 = st.columns(2)
    with col1:
        selected_lang = st.selectbox("Chọn ngôn ngữ/mã quốc gia:", languages, index=default_lang_index)
    
    # Lọc các giọng đọc thuộc ngôn ngữ đã chọn
    filtered_voices = [v for v in all_voices if v["Locale"] == selected_lang]
    voice_options = {f"{v['FriendlyName']} ({v['Gender']})": v["ShortName"] for v in filtered_voices}
    
    with col2:
        selected_voice_label = st.selectbox("Chọn giọng đọc:", list(voice_options.keys()))
        selected_voice_code = voice_options[selected_voice_label]

    # Nhập văn bản không giới hạn ký tự
    text_input = st.text_area(
        "Nhập nội dung văn bản (không giới hạn độ dài):",
        placeholder="Dán đoạn văn bản dài của bạn vào đây...",
        height=200
    )

    # Hàm tạo file âm thanh từ Edge TTS
    async def generate_speech(text, voice, output_path):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

    if st.button("🎧 Chuyển đổi âm thanh", type="primary"):
        if not text_input.strip():
            st.warning("Vui lòng nhập văn bản trước khi thực hiện!")
        else:
            output_file = "output.mp3"
            with st.spinner("Đang tạo file âm thanh..."):
                try:
                    asyncio.run(generate_speech(text_input, selected_voice_code, output_file))
                    
                    st.success("Tạo file âm thanh thành công!")
                    
                    # Phát file âm thanh trực tiếp trên web
                    st.audio(output_file, format="audio/mp3")
                    
                    # Nút tải file về máy
                    with open(output_file, "rb") as f:
                        audio_data = f.read()
                    
                    st.download_button(
                        label="📥 Tải xuống file MP3",
                        data=audio_data,
                        file_name="edge_tts_audio.mp3",
                        mime="audio/mp3"
                    )
                except Exception as e:
                    st.error(f"Đã xảy ra lỗi trong quá trình xử lý: {e}")
