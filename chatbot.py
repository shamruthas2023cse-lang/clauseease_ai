import streamlit as st
import time
import json
import requests
import docx
import PyPDF2

# -------------------------------
# CONFIG
# -------------------------------

MODEL_NAME = "tinyllama"   # Change if needed ("phi3", "llama3:instruct", etc.)

st.set_page_config(
    page_title="Contract Language Simplifier",
    page_icon="💬",
    layout="wide"
)

st.markdown("<h1 style='text-align: center;'>Chatbot</h1>", unsafe_allow_html=True)

# -------------------------------
# SESSION STATE
# -------------------------------

if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = {}

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "last_processed_file" not in st.session_state:
    st.session_state.last_processed_file = {}

# Store extracted data
if "file_data" not in st.session_state:
    st.session_state.file_data = None

# -------------------------------
# HELPERS
# -------------------------------

def create_new_chat():
    chat_id = f"chat_{int(time.time())}"
    st.session_state.chat_sessions[chat_id] = [
        {"role": "assistant", "content": "Hello! How can I help you today?"}
    ]
    st.session_state.current_chat_id = chat_id
    st.session_state.last_processed_file[chat_id] = None
    st.session_state.file_data = None
    st.rerun()


# Extract text from uploaded file
def extract_text_from_file(uploaded_file):
    file_type = uploaded_file.type

    # TXT
    if file_type == "text/plain":
        return uploaded_file.read().decode("utf-8")

    # Markdown
    if file_type == "text/markdown":
        return uploaded_file.read().decode("utf-8")

    # PDF
    if file_type == "application/pdf":
        reader = PyPDF2.PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    # DOCX
    if file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(uploaded_file)
        return "\n".join([p.text for p in doc.paragraphs])

    return None


# Chunk text
def chunk_text(text, max_chars=1000):
    chunks = []
    current = ""

    for para in text.split("\n"):
        if len(current) + len(para) < max_chars:
            current += para + "\n"
        else:
            chunks.append(current.strip())
            current = para

    if current:
        chunks.append(current.strip())

    return chunks


# Simple keyword-based retrieval
def get_relevant_chunks(query, chunks, top_k=3):
    scored = []
    q = query.lower()

    for chunk in chunks:
        score = chunk.lower().count(q)
        scored.append((score, chunk))

    scored.sort(reverse=True, key=lambda x: x[0])

    return [c for _, c in scored[:top_k]]


# Query Ollama
def query_ollama(prompt, context_text):
    url = "http://localhost:11434/api/generate"

    final_prompt = f"Context:\n{context_text}\n\nUser Query:\n{prompt}\n\nAnswer based only on the context above."

    data = {"model": MODEL_NAME, "prompt": final_prompt}

    response = requests.post(url, json=data, stream=True)
    full = ""

    for line in response.iter_lines():
        if line:
            try:
                decoded = json.loads(line.decode())
                full += decoded.get("response", "")
            except:
                pass

    return full


# -------------------------------
# SIDEBAR
# -------------------------------

with st.sidebar:
    st.header("Controls")

    if st.button("➕ New Chat", use_container_width=True):
        create_new_chat()

    st.header("Upload File")
    uploader_key = f"uploader_{st.session_state.current_chat_id}"
    uploaded_file = st.file_uploader(
        "Upload",
        type=["png", "jpg", "jpeg", "pdf", "txt", "md", "docx"],
        key=uploader_key
    )

    st.header("Chat History")

    if not st.session_state.chat_sessions:
        st.caption("No chat history yet.")
    else:
        sorted_ids = sorted(st.session_state.chat_sessions.keys(), reverse=True)
        for cid in sorted_ids:
            msgs = st.session_state.chat_sessions[cid]

            title = "New Chat"
            for m in msgs:
                if m["role"] == "user":
                    title = m["content"][:30] + "..."
                    break

            if st.button(title, key=cid, use_container_width=True):
                st.session_state.current_chat_id = cid
                st.rerun()


# -------------------------------
# MAIN CHAT AREA
# -------------------------------

if st.session_state.current_chat_id is None:
    if not st.session_state.chat_sessions:
        create_new_chat()
    else:
        st.write("Select or create a chat to begin.")

else:
    cid = st.session_state.current_chat_id
    messages = st.session_state.chat_sessions[cid]

    # -------------------------------
    # FILE PROCESSING
    # -------------------------------

    if uploaded_file is not None:
        fid = f"{uploaded_file.name}_{uploaded_file.size}"

        if st.session_state.last_processed_file.get(cid) != fid:

            extracted_text = extract_text_from_file(uploaded_file)

            if extracted_text:
                chunks = chunk_text(extracted_text)

                st.session_state.file_data = {
                    "file_name": uploaded_file.name,
                    "text": extracted_text,
                    "chunks": chunks,
                }

                messages.append({
                    "role": "user",
                    "content": f"I uploaded {uploaded_file.name}"
                })

                messages.append({
                    "role": "assistant",
                    "content": f"File processed. Extracted {len(chunks)} chunks."
                })

            else:
                messages.append({
                    "role": "assistant",
                    "content": "Failed to extract text from this file."
                })

            st.session_state.last_processed_file[cid] = fid
            st.rerun()

    # -------------------------------
    # DISPLAY MESSAGES
    # -------------------------------

    for msg in messages:
        avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # -------------------------------
    # USER INPUT
    # -------------------------------

    if prompt := st.chat_input("Ask something..."):
        messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant", avatar="🤖"):
            placeholder = st.empty()

            if st.session_state.file_data:
                chunks = st.session_state.file_data["chunks"]
                relevant = get_relevant_chunks(prompt, chunks)
                context_text = "\n\n".join(relevant)
            else:
                context_text = ""

            reply = query_ollama(prompt, context_text)
            placeholder.markdown(reply)

        messages.append({"role": "assistant", "content": reply})
        st.rerun()
