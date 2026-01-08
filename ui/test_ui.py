import streamlit as st
from io import StringIO


if "messages" not in st.session_state:
    st.session_state.messages = []

user_input = st.chat_input("Skriv meldingen din her...", 
              key="chat_input",accept_file=True, 
              file_type=["txt", "pdf", "docx", "xlsx", "png", "jpg", "jpeg"])

if user_input:
    st.session_state.messages.append({"role": "user", 
                                      "content": user_input.text if hasattr(user_input, "text") else "",
                                      "attachments" : user_input.files if hasattr(user_input, "files") else []})
    with st.chat_message("user"):
        st.info(user_input)
        st.markdown(user_input.text if hasattr(user_input, "text") else "")
        if hasattr(user_input, "files") and user_input.files:
            st.markdown("**Vedlagte filer:**")
            for f in user_input.files:
                bytes = f.getvalue()
                st.info(bytes[:100])
                stringio = StringIO(bytes.decode("utf-8", errors="ignore"))
                st.info(stringio.read()[:100])
                st.markdown(f"- {f.name} ({f.type}, {f.size} bytes)")
                st.markdown(stringio.read()[:1000])
