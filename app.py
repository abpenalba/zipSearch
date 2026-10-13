import io
import re
import zipfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Zip Text Search", page_icon="🔍", layout="wide")

# Extensions we'll try to decode as text. Anything else is skipped (marked binary).
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml",
    ".log", ".ini", ".cfg", ".conf", ".properties", ".sql",
    ".py", ".java", ".groovy", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".htm", ".css", ".sh", ".bat", ".ps1",
    ".gradle", ".toml", ".env", ".rst", ".gitignore",
}

MAX_PREVIEW_MATCHES_PER_FILE = 200


def is_probably_text(name: str) -> bool:
    suffix = Path(name).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    # No extension at all (e.g. README, Dockerfile, LICENSE) - still try
    return suffix == ""


def read_zip_entries(uploaded_file):
    """Return dict: filename -> decoded text (or None if unreadable/binary)."""
    entries = {}
    with zipfile.ZipFile(uploaded_file) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            raw = zf.read(name)
            text = None
            if is_probably_text(name):
                for encoding in ("utf-8", "utf-16", "latin-1"):
                    try:
                        text = raw.decode(encoding)
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
            entries[name] = {"text": text, "size": info.file_size}
    return entries


def search_entries(entries, query, use_regex, case_sensitive, whole_word):
    if not query:
        return {}

    if use_regex:
        pattern_str = query
    else:
        pattern_str = re.escape(query)
        if whole_word:
            pattern_str = rf"\b{pattern_str}\b"

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(pattern_str, flags)
    except re.error as e:
        st.error(f"Invalid regex: {e}")
        return {}

    results = {}
    for name, data in entries.items():
        text = data["text"]
        if text is None:
            continue
        matches = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append((line_no, line))
                if len(matches) >= MAX_PREVIEW_MATCHES_PER_FILE:
                    break
        if matches:
            results[name] = matches
    return results


def highlight(line, query, use_regex, case_sensitive, whole_word):
    pattern_str = query if use_regex else re.escape(query)
    if not use_regex and whole_word:
        pattern_str = rf"\b{pattern_str}\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(pattern_str, flags)
    except re.error:
        return line
    return pattern.sub(lambda m: f"**:orange[{m.group(0)}]**", line)


st.title("🔍 Zip Content Search")
st.caption("Upload a .zip file, then search across every text file inside it.")

uploaded_file = st.file_uploader("Upload a .zip file", type=["zip"])

if uploaded_file is not None:
    if (
        "zip_name" not in st.session_state
        or st.session_state.zip_name != uploaded_file.name
    ):
        with st.spinner("Reading zip contents..."):
            try:
                st.session_state.entries = read_zip_entries(uploaded_file)
                st.session_state.zip_name = uploaded_file.name
            except zipfile.BadZipFile:
                st.error("That doesn't look like a valid .zip file.")
                st.session_state.entries = {}

    entries = st.session_state.get("entries", {})

    if entries:
        text_count = sum(1 for d in entries.values() if d["text"] is not None)
        binary_count = len(entries) - text_count
        st.success(
            f"Loaded **{len(entries)}** files "
            f"({text_count} searchable as text, {binary_count} binary/skipped)."
        )

        with st.expander("📂 View all files in the zip"):
            for name, data in sorted(entries.items()):
                tag = "📄" if data["text"] is not None else "🗂️ binary"
                st.write(f"{tag}  `{name}`  —  {data['size']:,} bytes")

        st.divider()

        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Search for text", placeholder="e.g. TODO, error, class Foo")
        with col2:
            st.write("")
            st.write("")

        opt1, opt2, opt3 = st.columns(3)
        with opt1:
            case_sensitive = st.checkbox("Case sensitive", value=False)
        with opt2:
            whole_word = st.checkbox("Whole word only", value=False)
        with opt3:
            use_regex = st.checkbox("Use regex", value=False)

        if query:
            results = search_entries(entries, query, use_regex, case_sensitive, whole_word)

            if not results:
                st.warning("No matches found.")
            else:
                total_matches = sum(len(m) for m in results.values())
                st.info(f"Found **{total_matches}** matching line(s) across **{len(results)}** file(s).")

                for name, matches in sorted(results.items(), key=lambda kv: -len(kv[1])):
                    with st.expander(f"📄 {name}  ·  {len(matches)} match(es)", expanded=len(results) <= 3):
                        for line_no, line in matches:
                            hl = highlight(line.strip(), query, use_regex, case_sensitive, whole_word)
                            st.markdown(f"`L{line_no}`  {hl}")
    else:
        st.info("The zip file appears to be empty.")
else:
    st.info("👆 Upload a .zip file to get started.")
    st.session_state.pop("entries", None)
    st.session_state.pop("zip_name", None)
