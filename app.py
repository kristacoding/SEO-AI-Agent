import re
import pandas as pd
import streamlit as st
import openai

st.set_page_config(page_title="SEO AI Agent", layout="wide")

# ---- Settings ----
TITLE_MIN, TITLE_MAX = 30, 60
META_MIN, META_MAX = 70, 155

st.title("SEO AI Agent (Screaming Frog → AI Titles/Metas)")

with st.sidebar:
    st.header("1) Connect OpenAI")
    api_key = st.text_input("OpenAI API Key", type="password", help="Paste your key (starts with sk-).")
    model = st.selectbox("Model", ["gpt-4o-mini"], index=0)

    st.header("2) Upload Screaming Frog CSV")
    uploaded = st.file_uploader("Upload Seer.csv (Screaming Frog export)", type=["csv"])

def build_worklist(df: pd.DataFrame) -> pd.DataFrame:
    # HTML only
    df_html = df[df["Content Type"].astype(str).str.contains("text/html", na=False)].copy()

    # Status 200 only
    df_200 = df_html[df_html["Status Code"] == 200].copy()

    # Length columns (use SF ones if available, else compute)
    if "Title 1 Length" in df_200.columns:
        df_200["Title Length"] = df_200["Title 1 Length"]
    else:
        df_200["Title Length"] = df_200["Title 1"].fillna("").astype(str).str.len()

    if "Meta Description 1 Length" in df_200.columns:
        df_200["Meta Length"] = df_200["Meta Description 1 Length"]
    else:
        df_200["Meta Length"] = df_200["Meta Description 1"].fillna("").astype(str).str.len()

    missing_title = df_200["Title 1"].isna() | (df_200["Title 1"] == "")
    missing_meta = df_200["Meta Description 1"].isna() | (df_200["Meta Description 1"] == "")

    title_too_short = df_200["Title Length"] < TITLE_MIN
    title_too_long  = df_200["Title Length"] > TITLE_MAX
    meta_too_short  = df_200["Meta Length"] < META_MIN
    meta_too_long   = df_200["Meta Length"] > META_MAX

    needs_ai = missing_title | missing_meta | title_too_short | title_too_long | meta_too_short | meta_too_long
    cands = df_200[needs_ai].copy()

    issue_labels = []
    for idx, _ in cands.iterrows():
        issues = []
        if missing_title.loc[idx]:
            issues.append("Missing title")
        else:
            if title_too_short.loc[idx]: issues.append("Title too short")
            if title_too_long.loc[idx]:  issues.append("Title too long")

        if missing_meta.loc[idx]:
            issues.append("Missing meta")
        else:
            if meta_too_short.loc[idx]: issues.append("Meta too short")
            if meta_too_long.loc[idx]:  issues.append("Meta too long")
        issue_labels.append(", ".join(issues))

    cands["Issue Type"] = issue_labels

    keep = ["Address", "Status Code", "Title 1", "H1-1", "Meta Description 1", "Title Length", "Meta Length", "Issue Type"]
    return cands[keep].reset_index(drop=True)

def parse_ai_output(raw: str):
    # Robust parsing for Title/Meta/Keywords (handles markdown + bullets)
    lines = [l.strip() for l in raw.split("\n") if l.strip()]

    def norm_label(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"[*_`]", "", s)
        s = re.sub(r"^[\-\d\)\.\s]+", "", s)
        return s

    ai_title = ai_meta = primary_kw = secondary_kw = None
    current_field = None

    for line in lines:
        cleaned = norm_label(line)

        if cleaned.startswith("title:"):
            val = line.split(":", 1)[1].strip()
            current_field = "title"
            if val:
                ai_title = re.sub(r"[*_`]", "", val).strip()
                current_field = None
            continue

        if cleaned.startswith("meta:"):
            val = line.split(":", 1)[1].strip()
            current_field = "meta"
            if val:
                ai_meta = re.sub(r"[*_`]", "", val).strip()
                current_field = None
            continue

        if cleaned.startswith("primary keyword"):
            parts = line.split(":", 1)
            current_field = "primary"
            if len(parts) == 2 and parts[1].strip():
                primary_kw = re.sub(r"[*_`]", "", parts[1]).strip()
                current_field = None
            continue

        if cleaned.startswith("secondary keyword"):
            parts = line.split(":", 1)
            current_field = "secondary"
            if len(parts) == 2 and parts[1].strip():
                secondary_kw = re.sub(r"[*_`]", "", parts[1]).strip()
                current_field = None
            continue

        if current_field == "title" and ai_title is None:
            ai_title = re.sub(r"[*_`]", "", line).strip()
            current_field = None
        elif current_field == "meta" and ai_meta is None:
            ai_meta = re.sub(r"[*_`]", "", line).strip()
            current_field = None
        elif current_field == "primary" and primary_kw is None:
            primary_kw = re.sub(r"[*_`]", "", line).strip()
            current_field = None
        elif current_field == "secondary" and secondary_kw is None:
            secondary_kw = re.sub(r"[*_`]", "", line).strip()
            current_field = None

    return ai_title, ai_meta, primary_kw, secondary_kw

def call_ai(client, row, strict=False, extra_instructions=""):
    if strict:
        prompt = f"""
You MUST follow these length rules:
- Title length MUST be between {TITLE_MIN} and {TITLE_MAX} characters (inclusive).
- Meta length MUST be between {META_MIN} and {META_MAX} characters (inclusive).

Do NOT use markdown. Do NOT use bullets. Use plain labels exactly like this:

Title:
<text>

Meta:
<text>

Primary Keyword:
<text>

Secondary Keyword:
<text>

URL: {row['Address']}
H1: {row['H1-1']}
Current Title: {row['Title 1']}
Current Meta: {row['Meta Description 1']}
Issues: {row['Issue Type']}

Extra instructions: {extra_instructions}
"""
    else:
        prompt = f"""
You are an expert SEO strategist.

URL:
{row['Address']}

H1:
{row['H1-1']}

Current Title:
{row['Title 1']}

Current Meta:
{row['Meta Description 1']}

Issues detected: {row['Issue Type']}

Extra instructions: {extra_instructions}

Please respond with:

Title:
[Optimized SEO title, ideally {TITLE_MIN}-{TITLE_MAX} chars]

Meta:
[Optimized meta description, ideally {META_MIN}-{META_MAX} chars]

Primary Keyword:
[One main keyword]

Secondary Keyword:
[One supporting keyword]
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You write concise, search-optimized titles and meta descriptions."},
            {"role": "user", "content": prompt}
        ],
    )
    raw = resp.choices[0].message.content
    ai_title, ai_meta, pkw, skw = parse_ai_output(raw)
    return {
        "AI Title": ai_title,
        "AI Meta Description": ai_meta,
        "AI Title Length": len(ai_title) if ai_title else 0,
        "AI Meta Length": len(ai_meta) if ai_meta else 0,
        "Primary Keyword": pkw,
        "Secondary Keyword": skw,
        "Raw Output": raw
    }

# ---- Main app flow ----
if uploaded is None:
    st.info("Upload your Screaming Frog CSV to begin.")
    st.stop()

try:
    df = pd.read_csv(uploaded)
except Exception as e:
    st.error(f"Could not read CSV: {e}")
    st.stop()

required = {"Address", "Content Type", "Status Code", "Title 1", "H1-1", "Meta Description 1"}
missing = [c for c in required if c not in df.columns]
if missing:
    st.error(f"Your CSV is missing columns: {missing}")
    st.stop()

worklist = build_worklist(df)

colA, colB = st.columns([2, 1])
with colA:
    st.subheader("Worklist (HTML + 200 + missing/length issues)")
    st.caption(f"{len(worklist)} pages flagged")
with colB:
    st.subheader("Filters")
    issue_filter = st.multiselect("Issue Type contains", sorted(set(", ".join(worklist["Issue Type"]).split(", "))))
    if issue_filter:
        worklist = worklist[worklist["Issue Type"].apply(lambda x: any(i in x for i in issue_filter))].reset_index(drop=True)

st.dataframe(worklist[["Address", "Issue Type", "Title Length", "Meta Length"]].head(25), use_container_width=True)

st.divider()

idx = st.number_input("Select a row index to optimize", min_value=0, max_value=max(len(worklist)-1, 0), value=0, step=1)
row = worklist.iloc[idx]

st.subheader("Selected page")
left, right = st.columns(2)
with left:
    st.write("**URL:**", row["Address"])
    st.write("**Issue Type:**", row["Issue Type"])
    st.write("**H1:**", row["H1-1"])
with right:
    st.write("**Current Title:**", row["Title 1"])
    st.write("**Title Length:**", int(row["Title Length"]))
    st.write("**Current Meta:**", row["Meta Description 1"])
    st.write("**Meta Length:**", int(row["Meta Length"]))

extra = st.text_area("Optional instructions (tone, keywords, constraints)", "")

if "approved" not in st.session_state:
    st.session_state.approved = []

st.divider()

if st.button("Generate with AI", type="primary", disabled=not api_key):
    try:
        client = openai.OpenAI(api_key=api_key)
        result = call_ai(client, row, strict=False, extra_instructions=extra)

        # auto-fix if out of range (up to 2 attempts strict)
        title_ok = TITLE_MIN <= result["AI Title Length"] <= TITLE_MAX
        meta_ok = META_MIN <= result["AI Meta Length"] <= META_MAX

        if not (title_ok and meta_ok):
            for _ in range(2):
                result = call_ai(client, row, strict=True, extra_instructions=extra)
                title_ok = TITLE_MIN <= result["AI Title Length"] <= TITLE_MAX
                meta_ok = META_MIN <= result["AI Meta Length"] <= META_MAX
                if title_ok and meta_ok:
                    break

        st.session_state.last_result = result
    except Exception as e:
        st.error(f"AI error: {e}")

if "last_result" in st.session_state:
    r = st.session_state.last_result
    st.subheader("AI Suggestion")
    st.write("**AI Title:**", r["AI Title"])
    st.write("**AI Title Length:**", r["AI Title Length"], "✅" if TITLE_MIN <= r["AI Title Length"] <= TITLE_MAX else "⚠️")
    st.write("**AI Meta:**", r["AI Meta Description"])
    st.write("**AI Meta Length:**", r["AI Meta Length"], "✅" if META_MIN <= r["AI Meta Length"] <= META_MAX else "⚠️")
    st.write("**Primary Keyword:**", r["Primary Keyword"])
    st.write("**Secondary Keyword:**", r["Secondary Keyword"])

    if st.button("Approve & add to export"):
        st.session_state.approved.append({
            "Address": row["Address"],
            "Issue Type": row["Issue Type"],
            "Original Title": row["Title 1"],
            "Original Meta Description": row["Meta Description 1"],
            "Original Title Length": row["Title Length"],
            "Original Meta Length": row["Meta Length"],
            **r
        })
        st.success("Added to export list!")

st.divider()

st.subheader("Approved items")

approved_df = pd.DataFrame(st.session_state.approved)

if approved_df.empty:
    st.info("No approved items yet. Generate a suggestion and click 'Approve & add to export'.")
else:
    # Show a compact preview if the columns exist
    preview_cols = ["Address", "Issue Type", "AI Title Length", "AI Meta Length"]
    available_cols = [c for c in preview_cols if c in approved_df.columns]

    st.dataframe(approved_df[available_cols], use_container_width=True)

    csv_bytes = approved_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download approved CSV",
        data=csv_bytes,
        file_name="ai_seo_optimizations_approved.csv",
        mime="text/csv"
    )
