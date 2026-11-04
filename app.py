import streamlit as st

st.set_page_config(page_title="Document Assistant", page_icon="📄")
st.title("Document Assistant")
st.caption(
    "Upload a PDF, then ask questions. See what your PDF says, then get a simple "
    "explanation, key points and practice questions."
)

if "active_doc" not in st.session_state:
    st.session_state.active_doc = None
    st.session_state.upload_msg = ""
    st.session_state.last_file = None

uploaded = st.file_uploader("Upload a PDF (max 10 MB)", type="pdf")
if uploaded is not None and st.session_state.last_file != (uploaded.name, uploaded.size):
    if uploaded.size > 10 * 1024 * 1024:
        st.error("File is too large (max 10 MB).")
    else:
        with st.spinner("Processing PDF... the first time takes a minute while the models load."):
            try:
                from ingest import ingest_pdf

                info = ingest_pdf(uploaded.getvalue(), uploaded.name)
            except Exception as e:
                st.error(f"Upload failed: {e}")
                st.stop()
        st.session_state.last_file = (uploaded.name, uploaded.size)
        if info["chunks"] == 0:
            st.session_state.upload_msg = "No readable text found. Scanned PDFs are not supported."
        else:
            st.session_state.active_doc = info["filename"]
            st.session_state.upload_msg = (
                f"Added {info['filename']}: {info['pages']} pages, "
                f"{info['chunks']} chunks. You can ask questions now."
            )

if st.session_state.upload_msg:
    st.success(st.session_state.upload_msg)

if st.session_state.active_doc:
    st.write(f"Asking about: **{st.session_state.active_doc}**")
    if st.button("Ask all documents instead"):
        st.session_state.active_doc = None
        st.rerun()

question = st.text_input("Ask about your documents...")

if st.button("Ask") and question.strip():
    with st.spinner("Thinking... the first question takes a minute while the models load."):
        try:
            from core import ask

            result = ask(question, source=st.session_state.active_doc)
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    st.subheader("What your PDF says")
    st.write(result.from_document)

    if result.explanation:
        st.subheader("Explained simply")
        st.write(result.explanation)

    if result.key_points:
        st.subheader("Key points to remember")
        for p in result.key_points:
            st.markdown(f"- {p}")

    if result.exam_questions:
        st.subheader("Practice questions (click to see the answer)")
        for q in result.exam_questions:
            with st.expander(q.question):
                st.write(q.answer)

    st.caption(f"Confidence: {result.confidence}")
    for c in result.citations:
        st.markdown(f"- {c.source}, page {c.page}")