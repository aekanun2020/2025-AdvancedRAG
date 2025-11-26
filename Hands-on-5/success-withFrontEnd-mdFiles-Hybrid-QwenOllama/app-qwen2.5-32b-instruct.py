import streamlit as st
import requests
import re
import os
import base64
import markdown
from bs4 import BeautifulSoup
from openai import OpenAI

# Set page config to wide mode and customize the page title and icon
st.set_page_config(
    page_title="ระบบค้นหาและตอบคำถามเกี่ยวกับ ปัญหาสุขภาพ",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="auto"
)

def clean_ellipsis(text):
    cleaned_text = re.sub(r'\.{3,}', '', text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    return cleaned_text.strip()

def get_binary_file_downloader_html(bin_file, file_label='File'):
    with open(bin_file, 'rb') as f:
        data = f.read()
    bin_str = base64.b64encode(data).decode()
    href = f'<a href="data:application/octet-stream;base64,{bin_str}" download="{os.path.basename(bin_file)}">Download {file_label}</a>'
    return href

def display_markdown(file_path, section=None):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        
        # Convert markdown to HTML
        html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        
        # If a specific section is requested, try to find and display only that section
        if section and section != 'N/A':
            soup = BeautifulSoup(html_content, 'html.parser')
            headers = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            
            for i, header in enumerate(headers):
                if section.lower() in header.text.lower():
                    # Find content until next header or end of document
                    content = []
                    content.append(str(header))
                    
                    current = header.next_sibling
                    while current and (not current.name or current.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                        if current.name:
                            content.append(str(current))
                        current = current.next_sibling
                    
                    section_html = ''.join(content)
                    return f'<div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; max-height: 600px; overflow-y: auto;">{section_html}</div>'
            
            # If specific section not found, return entire document with a notice
            return f'<div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; max-height: 600px; overflow-y: auto;"><p style="color: red;">ส่วน "{section}" ไม่พบในเอกสาร</p>{html_content}</div>'
        
        # No specific section requested, return entire document
        return f'<div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; max-height: 600px; overflow-y: auto;">{html_content}</div>'
        
    except Exception as e:
        return f'<div style="color: red; padding: 15px;">ไม่สามารถแสดงไฟล์ได้: {str(e)}</div>'

def call_qwen_api(prompt, max_tokens=1000, temperature=0.2):
    """เรียกใช้ Qwen API เพื่อสร้างข้อความ"""
    try:
        # รับ API key จาก environment variable
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            return "Error: DASHSCOPE_API_KEY environment variable not set"
        
        # สร้าง OpenAI client ที่ใช้เรียก Qwen API
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        
        completion = client.chat.completions.create(
            model="qwen2.5-32b-instruct",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Qwen API error: {str(e)}"

system_prompt = """คุณเป็นผู้เชี่ยวชาญเกี่ยวกับ ปัญหาสุขภาพ
ในการตอบคำถาม:
1. ใช้เฉพาะข้อมูลที่ให้มาในผลการค้นหา
2. หากไม่มีข้อมูลเพียงพอ ให้ตอบว่า "ขออภัย ไม่มีข้อมูลเพียงพอที่จะตอบคำถามนี้"
3. ตอบเฉพาะส่วนที่มีข้อมูลสนับสนุนชัดเจน
4. ใช้รูปแบบการตอบแบบแจกแจงเป็นข้อๆ เพื่อให้อ่านง่าย
5. สรุปวัตถุประสงค์หรือความสำคัญของหัวข้อที่ถามไว้ท้ายคำตอบ"""

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "llm_prompt" not in st.session_state:
    st.session_state.llm_prompt = ""

def add_to_chat_history(entry_type, content):
    st.session_state.chat_history.append((entry_type, content))

def process_question(question):
    add_to_chat_history("User", question)

    response = requests.post("http://localhost:9000/search", json={"query": question})
    if response.status_code == 200:
        data = response.json()
        search_results = data["results"]
        total_tokens = data["total_tokens"]
        
        cleaned_search_results = [
            {
                "text": clean_ellipsis(result['text']),
                "file_path": result['file_path'],
                "tokens": result['tokens'],
                "section": result.get('page_label', 'N/A')  # Renamed from page_label to section
            } for result in search_results
        ]
        
        response_text = "\n\n".join([f"Text: {result['text']}\nFile Path: {result['file_path']}\nTokens: {result['tokens']}\nSection: {result['section']}" for result in cleaned_search_results])

        llm_prompt = f"""คุณเป็นผู้เชี่ยวชาญเกี่ยวกับ ปัญหาสุขภาพ
ในการตอบคำถาม:
1. ใช้เฉพาะข้อมูลที่ให้มาในผลการค้นหา
2. หากไม่มีข้อมูลเพียงพอ ให้ตอบว่า "ขออภัย ไม่มีข้อมูลเพียงพอที่จะตอบคำถามนี้"
3. ตอบเฉพาะส่วนที่มีข้อมูลสนับสนุนชัดเจน
4. ใช้รูปแบบการตอบแบบแจกแจงเป็นข้อๆ เพื่อให้อ่านง่าย
5. สรุปวัตถุประสงค์หรือความสำคัญของหัวข้อที่ถามไว้ท้ายคำตอบ

คำถาม: {question}

ผลการค้นหาเพิ่มเติม:
{response_text}

โปรดตอบคำถามโดยใช้เฉพาะข้อมูลจากผลการค้นหา และทำตามคำแนะนำในการตอบคำถาม"""

        st.session_state.llm_prompt = llm_prompt

        # เรียกใช้ Qwen API แทน Ollama
        llm_output = call_qwen_api(llm_prompt, max_tokens=1000, temperature=0.6)
        
        if not llm_output.startswith("Error:") and not llm_output.startswith("Qwen API error:"):
            cleaned_output = clean_ellipsis(llm_output)
            add_to_chat_history("Search Results", response_text)
            add_to_chat_history("AI", cleaned_output)
            add_to_chat_history("Total Tokens", str(total_tokens))
        else:
            add_to_chat_history("Error", f"LLM Error: {llm_output}")
    else:
        add_to_chat_history("Error", f"Search Error: {response.status_code}")

# Main content
st.title("ระบบค้นหาและตอบคำถามเกี่ยวกับ ปัญหาสุขภาพ")
st.write("ยินดีต้อนรับสู่ระบบอัจฉริยะสำหรับค้นหาข้อมูลและตอบคำถามเกี่ยวกับ ปัญหาสุขภาพ (ใช้ Qwen 2.5-32B Instruct)")

# Use st.form to create a form
with st.form(key='question_form'):
    user_input = st.text_input("โปรดระบุคำถามของคุณ:", key="input")
    submit_button = st.form_submit_button(label='ส่งคำถาม')

if submit_button and user_input:
    process_question(user_input)

# แสดงผลลัพธ์
if st.session_state.chat_history:
    # กำหนดจำนวนการโต้ตอบสูงสุดที่จะแสดง
    max_interactions = 5
    
    # คำนวณจำนวนการโต้ตอบทั้งหมด
    total_interactions = len(st.session_state.chat_history) // 4
    
    # สร้างตัวเลือกสำหรับการเลือกหน้า
    if total_interactions > max_interactions:
        page = st.selectbox("เลือกหน้า", range(1, (total_interactions // max_interactions) + 2))
    else:
        page = 1
    
    # คำนวณ index เริ่มต้นและสิ้นสุดสำหรับการแสดงผล
    start_index = (page - 1) * max_interactions * 4
    end_index = min(start_index + (max_interactions * 4), len(st.session_state.chat_history))
    
    # วนลูปแสดงผลจากล่าสุดไปเก่าสุด
    for i in range(end_index - 4, start_index - 1, -4):
        interaction = st.session_state.chat_history[i:i+4]
        
        # 1. แสดงคำถาม
        user_question = next((content for entry_type, content in interaction if entry_type == "User"), None)
        if user_question:
            st.markdown("### คำถาม")
            st.markdown(f'<div style="background-color: #ffeeba; padding: 10px; border-radius: 5px; font-size: 18px; color: #856404; border: 1px solid #ffeeba; margin-bottom: 10px;">{user_question}</div>', unsafe_allow_html=True)
        
        # 2. แสดงผลการค้นหาที่สอดคล้องกับคำถาม
        search_results = next((content for entry_type, content in interaction if entry_type == "Search Results"), None)
        if search_results:
            st.markdown("### ผลการค้นหาที่สอดคล้องกับคำถาม")
            
            for idx, result in enumerate(search_results.split("\n\n")):
                parts = result.split("\n")
                if len(parts) >= 4:
                    file_path = parts[1].split(": ")[1]
                    section = parts[3].split(": ")[1]
                    
                    col1, col2 = st.columns([3, 2])
                    
                    with col1:
                        st.markdown(f'<div style="background-color: #e6f3ff; padding: 10px; border-radius: 5px; margin-bottom: 10px; border: 1px solid #b8daff;">'
                                    f'<p style="font-size: 16px; color: #004085;"><strong>{parts[0]}</strong></p>'
                                    f'<p style="font-size: 14px; color: #004085;">{parts[1]}</p>'
                                    f'<p style="font-size: 14px; color: #004085;">{parts[2]}</p>'
                                    f'<p style="font-size: 14px; color: #004085;">{parts[3]}</p>'
                                    f'</div>', unsafe_allow_html=True)
                        
                        md_key = f"show_md_{i}_{idx}"
                        if st.button(f"เปิด/ปิด เอกสารในส่วน '{section}'", key=f"toggle_md_{i}_{idx}"):
                            st.session_state[md_key] = not st.session_state.get(md_key, False)
                    
                    with col2:
                        if st.session_state.get(md_key, False):
                            st.markdown(display_markdown(file_path, section), unsafe_allow_html=True)
                    
                    st.markdown("---")
        
        # 3. แสดงคำตอบจาก AI ในกรอบผลการค้นหา
        ai_response = next((content for entry_type, content in interaction if entry_type == "AI"), None)
        if ai_response:
            st.markdown("### คำตอบจาก AI ในกรอบผลการค้นหา")
            st.markdown(f'<div style="background-color: #f8d7da; padding: 10px; border-radius: 5px; font-size: 18px; color: #721c24;">{ai_response}</div>', unsafe_allow_html=True)
        
        # 4. แสดงจำนวน Tokens
        total_tokens = next((content for entry_type, content in interaction if entry_type == "Total Tokens"), None)
        if total_tokens:
            st.markdown(f"### จำนวน Tokens: {total_tokens}")
        
        st.markdown("---")  # เส้นแบ่งระหว่างแต่ละการโต้ตอบ

# ส่วนแสดง Prompt
if st.session_state.llm_prompt:
    with st.expander("ดู Prompt ที่ใช้", expanded=False):
        st.code(st.session_state.llm_prompt, language="text")

# ปุ่มล้างประวัติการสนทนา
if st.button("ล้างประวัติการสนทนา"):
    st.session_state.chat_history = []
    st.session_state.llm_prompt = ""
    # ล้างสถานะการแสดง PDF ทั้งหมด
    for key in list(st.session_state.keys()):
        if key.startswith("show_md_"):
            del st.session_state[key]
    st.rerun()