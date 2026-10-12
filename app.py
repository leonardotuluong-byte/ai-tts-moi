import streamlit as st
import asyncio
import edge_tts
import tempfile
import os

# Cấu hình giao diện Streamlit
st.set_page_config(
    page_title="AI TTS Pro - Kho Giọng Đọc Đa Ngôn Ngữ",
    page_icon="🎙️",
    layout="centered"
)

st.title("🎙️ AI TTS Pro - Kho Giọng Đọc Microsoft Edge")
st.write("Hệ thống chuyển đổi văn bản thành giọng nói với đầy đủ kho giọng nói tự nhiên, không giới hạn ký tự.")

# =========================================================================
# 1. TẢI TOÀN BỘ KHO GIỌNG ĐỌC TỪ EDGE TTS
# =========================================================================
@st.cache_resource
def get_all_voices():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        voices = loop.run_until_complete(edge_tts.list_voices())
        loop.close()
        return voices
    except Exception as e:
        st.error(f"Lỗi kết nối lấy kho giọng đọc: {e}")
        return []

with st.spinner("Đang tải toàn bộ kho giọng đọc từ hệ thống..."):
    ALL_VOICES = get_all_voices()

if ALL_VOICES:
    LOCALES = sorted(list(set([v['Locale'] for v in ALL_VOICES])))
    
    # Mặc định ưu tiên chọn tiếng Tây Ban Nha hoặc tiếng Việt nếu có
    default_locale = "es-ES" if "es-ES" in LOCALES else (LOCALES[0] if LOCALES else "")
    
    col1, col2 = st.columns(2)
    with col1:
        # Lọc theo ngôn ngữ
        selected_locale = st.selectbox(
            "🌐 Chọn ngôn ngữ (Locale):", 
            options=LOCALES, 
            index=LOCALES.index(default_locale) if default_locale in LOCALES else 0
        )
    with col2:
        # Lọc theo giới tính
        selected_gender = st.radio(
            "👤 Giới tính:", 
            options=["All", "Male", "Female"], 
            horizontal=True
        )

    # Lọc danh sách giọng đọc dựa trên ngôn ngữ và giới tính
    filtered_voices = [v for v in ALL_VOICES if v['Locale'] == selected_locale]
    if selected_gender != "All":
        filtered_voices = [v for v in filtered_voices if v['Gender'] == selected_gender]

    voice_choices = [v['ShortName'] for v in filtered_voices]
    
    if voice_choices:
        selected_voice = st.selectbox(
            "🎙️ Chọn giọng đọc cụ thể:", 
            options=voice_choices,
            format_func=lambda x: next((f"{v['FriendlyName']} ({v['Gender']}) - [{v['ShortName']}]" for v in filtered_voices if v['ShortName'] == x), x)
        )
    else:
        st.warning("Không tìm thấy giọng đọc phù hợp với bộ lọc này.")
        selected_voice = None

    # =========================================================================
    # 2. KHU VỰC NHẬP VĂN BẢN VÀ XỬ LÝ ÂM THANH
    # =========================================================================
    text_input = st.text_area(
        "📝 Nhập nội dung văn bản cần chuyển đổi:",
        placeholder="Dán đoạn văn bản dài của bạn vào đây...",
        height=200
    )

    async def generate_edge_tts(text, voice_code, output_path):
        communicate = edge_tts.Communicate(text, voice_code, rate="+0%")
        await communicate.save(output_path)

    if st.button("🚀 Bắt đầu chuyển đổi giọng nói", type="primary"):
        if not text_input.strip():
            st.warning("Vui lòng nhập văn bản trước khi thực hiện!")
        elif not selected_voice:
            st.warning("Vui lòng chọn một giọng đọc hợp lệ!")
        else:
            with st.spinner("Đang tổng hợp giọng nói từ máy chủ Microsoft..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                        output_path = tmp_file.name

                    # Chạy tiến trình bất đồng bộ tạo audio đúng giọng
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(generate_edge_tts(text_input, selected_voice, output_path))
                    loop.close()

                    st.success("🎉 Tạo âm thanh thành công đúng với giọng đã chọn!")
                    
                    # Phát trực tiếp trên giao diện
                    st.audio(output_path, format="audio/mp3")

                    # Nút tải xuống file
                    with open(output_path, "rb") as f:
                        audio_bytes = f.read()

                    st.download_button(
                        label="📥 Tải xuống file MP3",
                        data=audio_bytes,
                        file_name="edge_tts_output.mp3",
                        mime="audio/mp3"
                    )

                except Exception as e:
                    st.error(f"Đã xảy ra lỗi trong quá trình tạo âm thanh: {e}")
else:
    st.error("Không thể tải danh sách giọng đọc. Vui lòng kiểm tra lại kết nối mạng hoặc khởi động lại ứng dụng.")
