"""
结构修理 刷题助手
支持 Firebase Auth 登录 + Firestore 数据存储
"""
import streamlit as st
import json
import random
import time
import requests
from pathlib import Path

st.set_page_config(page_title="结构修理 刷题助手", page_icon="🔧", layout="centered")

# ===================== 常量 =====================
BANK_PATH = Path(__file__).resolve().parent / "quiz_bank.json"

db = None

# ===================== CSS =====================
st.markdown("""
<style>
    .main { background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); min-height: 100vh; padding: 1rem; }
    .stApp { background-color: #f8fff8; border-radius: 1rem; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); margin: 0 auto; max-width: 1000px; overflow: hidden; }
    [data-testid="stSidebar"] { background: #f1f8e9; border-right: 1px solid #e8f5e8; }
    .stButton > button { width: 100%; font-size: 0.95rem; padding: 0.6rem 1rem; border-radius: 0.5rem; transition: all 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    div[data-baseweb="radio"] > div, div[data-baseweb="checkbox"] > div {
        width: 100% !important; padding: 0.75rem 1rem; border: 2px solid #c8e6c9; border-radius: 0.75rem;
        background: #fff; transition: all 0.2s; margin-bottom: 0.75rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-baseweb="radio"] > div[aria-checked="true"], div[data-baseweb="checkbox"] > div[data-checked="true"] {
        border-color: #4caf50; background: #e8f5e8; font-weight: 600; box-shadow: 0 0 0 3px rgba(76,175,80,0.1);
    }
    div[data-baseweb="radio"] > div:hover, div[data-baseweb="checkbox"] > div:hover { border-color: #a5d6a7; background: #f1f8e9; }
    div[data-baseweb="radio"] > div > div:first-child, div[data-baseweb="checkbox"] > div > div:first-child { display: none; }
    div[data-baseweb="radio"] > div > div:last-child, div[data-baseweb="checkbox"] > div > div:last-child { flex-grow: 1; text-align: left; font-size: 0.95rem; }
    h1, h2, h3 { font-weight: 700 !important; background: linear-gradient(135deg, #2e7d32, #4caf50); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    [data-testid="stProgressBar"] { border-radius: 9999px; height: 12px; background: #c8e6c9; }
    [data-testid="stProgressBar"] > div { border-radius: 9999px; background: linear-gradient(90deg, #4caf50, #81c784); }
    hr { border: 0; height: 2px; background: linear-gradient(90deg, transparent, #c8e6c9, transparent); margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ===================== Firebase 初始化 =====================
def _load_secret(key):
    """从 st.secrets 读取，失败则本地文件兜底"""
    try:
        return st.secrets["firebase"][key]
    except Exception:
        pass
    # 本地文件兜底：firebase_config.json（api_key）/ firebase-service-account.json（service_account）
    if key == "api_key":
        cfg = Path(__file__).resolve().parent / "firebase_config.json"
        if cfg.exists():
            with open(cfg) as f:
                return json.load(f).get("api_key")
    elif key == "service_account":
        sa = Path(__file__).resolve().parent / "firebase-service-account.json"
        if sa.exists():
            with open(sa) as f:
                return json.load(f)
    return None

def init_firestore():
    global db
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        sa = _load_secret("service_account")
        if sa is None:
            return
        if isinstance(sa, str):
            sa = json.loads(sa)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(sa))
        db = firestore.client()
    except Exception:
        pass

def firebase_call(endpoint, email, password):
    key = _load_secret("api_key")
    if key is None:
        st.error("Firebase API Key 未配置，请在 Streamlit Cloud → Settings → Secrets 中添加。")
        st.stop()
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={key}"
    r = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True})
    return r.json()

# ===================== Firestore 操作 =====================
def _doc(uid):
    return db.collection("users").document(uid)

def load_data(uid):
    if db is None:
        return
    d = _doc(uid).get()
    if d.exists:
        data = d.to_dict()
        st.session_state.correct_ids = set(data.get("correct_ids", []))
        st.session_state.incorrect_ids = set(data.get("incorrect_ids", []))
        st.session_state.error_counts = data.get("error_counts", {})
    else:
        _doc(uid).set({"email": st.session_state.user_email, "correct_ids": [], "incorrect_ids": [], "error_counts": {}, "created_at": int(time.time())})

def save_data(uid):
    if db is None:
        return
    _doc(uid).set({
        "correct_ids": list(st.session_state.correct_ids),
        "incorrect_ids": list(st.session_state.incorrect_ids),
        "error_counts": st.session_state.error_counts,
        "updated_at": int(time.time()),
    }, merge=True)

def clear_data(uid):
    if db:
        _doc(uid).delete()

# ===================== 题库加载 =====================
@st.cache_data(ttl=3600, show_spinner="正在加载题库...")
def load_questions(fp):
    if not fp.exists():
        st.error("题库文件未找到")
        st.stop()
    data = json.loads(fp.read_text(encoding="utf-8"))
    qs = []
    for item in data:
        t = item.get("type", "single")
        qt = item.get("question", "").strip()
        ro = item.get("options", {})
        ra = item.get("answer")
        if not qt or not ro or ra is None:
            continue
        ol = [f"{k}. {v}" for k, v in sorted(ro.items())]
        if t == "multi":
            ans = "|".join(sorted(str(a).strip().upper() for a in ra))
        elif isinstance(ra, list):
            ans = str(ra[0]).strip().upper()
        else:
            ans = str(ra).strip().upper()
        qs.append({"id": item.get("id", f"q{len(qs):04d}"), "type": t, "question": qt, "options": ol, "answer": ans})
    return qs

# ===================== 出题 =====================
MODE_MAP = {"全部题目": "all", "仅单选题": "single", "仅多选题": "multi", "仅判断题": "judge", "仅错题": "wrong"}

def make_batch(mode):
    all_qs = st.session_state.all_questions
    pool = all_qs
    if mode == "single":
        pool = [q for q in all_qs if q["type"] == "single"]
    elif mode == "multi":
        pool = [q for q in all_qs if q["type"] == "multi"]
    elif mode == "judge":
        pool = [q for q in all_qs if q["type"] == "judge"]
    elif mode == "wrong":
        pool = [q for q in all_qs if q["id"] in st.session_state.incorrect_ids]

    if not pool:
        st.session_state.quiz_started = False
        return

    if mode == "wrong":
        batch = pool.copy()
        random.shuffle(batch)
    else:
        cs, ic = st.session_state.correct_ids, st.session_state.incorrect_ids
        batch = [q for q in pool if q["id"] in ic]
        cp = [q for q in pool if q["id"] in cs]
        if cp:
            batch.extend(random.sample(cp, min(20, len(cp))))
        unseen = [q for q in pool if q["id"] not in (cs | ic)]
        need = 100 - len(batch)
        if need > 0 and unseen:
            batch.extend(random.sample(unseen, min(need, len(unseen))))
        random.shuffle(batch)

    st.session_state.current_batch = batch
    st.session_state.current_idx = 0
    st.session_state.this_batch_answers = {}
    st.session_state.quiz_finished = False
    st.session_state.batch_id = random.randint(1, 1000000)

# ===================== 页面：登录/注册 =====================
def render_login():
    st.title("🔧 结构修理 刷题助手")

    mode = st.radio("登录方式", ["登录", "注册"], horizontal=True, key="auth_mode", label_visibility="collapsed")
    is_reg = (mode == "注册")

    with st.form("auth_form", clear_on_submit=False):
        email = st.text_input("邮箱", key="auth_email", placeholder="请输入邮箱地址")
        pw = st.text_input("密码", type="password", key="auth_password", placeholder="至少 6 位")
        confirm = ""
        if is_reg:
            confirm = st.text_input("确认密码", type="password", key="auth_confirm", placeholder="再次输入密码")

        btn = "📝 注 册" if is_reg else "🔑 登 录"
        if st.form_submit_button(btn, type="primary", use_container_width=True):
            if not email or not pw:
                st.error("请填写邮箱和密码")
                return
            if "@" not in email or "." not in email.split("@")[-1]:
                st.error("请输入有效的邮箱地址")
                return

            if is_reg:
                if confirm != pw:
                    st.error("两次密码不一致")
                    return
                if len(pw) < 6:
                    st.error("密码至少 6 位")
                    return
                resp = firebase_call("signUp", email, pw)
                if "idToken" not in resp:
                    msg = resp.get("error", {}).get("message", "")
                    if "EMAIL_EXISTS" in msg:
                        st.error("该邮箱已被注册，请直接登录")
                    else:
                        st.error(f"注册失败: {msg}")
                    return
                # 注册成功 → 写入 Firestore → 自动登录
                uid = resp["localId"]
                st.session_state.user_email = email
                st.session_state.user_uid = uid
                st.session_state.logged_in = True
                if db:
                    _doc(uid).set({"email": email, "correct_ids": [], "incorrect_ids": [], "error_counts": {}, "created_at": int(time.time())})
                st.rerun()
            else:
                resp = firebase_call("signInWithPassword", email, pw)
                if "idToken" not in resp:
                    msg = resp.get("error", {}).get("message", "")
                    if "EMAIL_NOT_FOUND" in msg or "INVALID_PASSWORD" in msg:
                        st.error("邮箱或密码错误")
                    else:
                        st.error(f"登录失败: {msg}")
                    return
                uid = resp["localId"]
                st.session_state.user_email = resp["email"]
                st.session_state.user_uid = uid
                st.session_state.logged_in = True
                load_data(uid)
                st.rerun()

# ===================== 侧边栏 =====================
def render_sidebar():
    uid = st.session_state.user_uid
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.user_email}**")
        if st.button("🚪 退出登录"):
            for k in ["logged_in", "user_email", "user_uid"]:
                st.session_state.pop(k, None)
            st.rerun()

        st.divider()
        st.header("⚙️ 设置")

        sel = st.radio("选择练习模式", options=list(MODE_MAP.keys()),
                       index=list(MODE_MAP.keys()).index(st.session_state.selected_mode_label),
                       horizontal=True)
        if sel != st.session_state.selected_mode_label:
            st.session_state.selected_mode_label = sel

        total = len(st.session_state.all_questions)
        sn = sum(1 for q in st.session_state.all_questions if q["type"] == "single")
        mn = sum(1 for q in st.session_state.all_questions if q["type"] == "multi")
        jn = sum(1 for q in st.session_state.all_questions if q["type"] == "judge")
        st.info(f"题库：共 **{total}** 题（单选 {sn} · 多选 {mn} · 判断 {jn}）")

        if st.button("🚀 开始/重置练习", type="primary"):
            st.session_state.current_batch = []
            st.session_state.current_idx = 0
            st.session_state.this_batch_answers = {}
            st.session_state.quiz_finished = False
            st.session_state.quiz_started = True
            make_batch(MODE_MAP[st.session_state.selected_mode_label])

        if st.session_state.quiz_started:
            st.divider()
            st.header("📊 学习进度")
            cn = len(st.session_state.correct_ids)
            in_ = len(st.session_state.incorrect_ids)
            an = cn + in_
            acc = (cn / an * 100) if an > 0 else 0
            mp = (cn / total * 100) if total > 0 else 0
            st.progress(mp / 100, text=f"✅ 已掌握: {mp:.1f}%")
            st.markdown(f"<div style='text-align:center;color:#6b7280;font-size:0.9rem;'>{cn} / {total} 题</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.metric("❌ 未掌握", in_)
            c2.metric("🎯 正确率", f"{acc:.1f}%")

        st.divider()
        st.header("📝 错题库")
        wr = [q for q in st.session_state.all_questions
              if q["id"] in st.session_state.error_counts and st.session_state.error_counts[q["id"]] >= 2]
        st.metric("需重点复习", len(wr))
        with st.expander("点击展开错题库", expanded=False):
            if not wr:
                st.info("暂无需要重点复习的错题。")
            else:
                for q in wr:
                    ec = st.session_state.error_counts[q["id"]]
                    with st.expander(f"ID: {q['id']} (错 {ec} 次)"):
                        st.write(f"**题干:** {q['question']}")
                        cl = q["answer"].split("|")
                        co = [o for o in q["options"] if any(o.startswith(c) for c in cl)]
                        st.markdown(f"**正确答案:** <span style='color:green'>{', '.join(co)}</span>", unsafe_allow_html=True)

        st.divider()
        with st.expander("⚠️ 高级选项", expanded=False):
            if st.button("🗑️ 清空所有学习数据", type="secondary"):
                clear_data(uid)
                st.session_state.correct_ids = set()
                st.session_state.incorrect_ids = set()
                st.session_state.error_counts = {}
                st.success("✅ 已清空！")
                st.rerun()

# ===================== 答题主界面 =====================
TYPE_LABEL = {"single": "🔘 单选题", "multi": "☑️ 多选题", "judge": "⚖️ 判断题"}

def render_quiz():
    uid = st.session_state.user_uid

    if not st.session_state.quiz_started:
        st.info("请在左侧选择模式，点击「开始/重置练习」按钮开始。")
        return

    if st.session_state.quiz_finished:
        st.balloons()
        st.success("🎉 本轮练习完成！")
        if st.button("再来一轮", type="primary"):
            st.session_state.current_batch = []
            st.session_state.current_idx = 0
            st.session_state.this_batch_answers = {}
            st.session_state.quiz_finished = False
            st.session_state.quiz_started = True
            make_batch(MODE_MAP[st.session_state.selected_mode_label])
            st.rerun()
        return

    batch = st.session_state.current_batch
    idx = st.session_state.current_idx
    if idx >= len(batch):
        make_batch(MODE_MAP[st.session_state.selected_mode_label])
        st.rerun()

    q = batch[idx]
    qid = q["id"]
    qtype = q["type"]
    done = qid in st.session_state.this_batch_answers

    c1, c2 = st.columns([3, 1])
    c1.subheader(f"第 {idx+1}/{len(batch)} 题")
    c2.markdown(f"<div style='text-align:right;padding:0.3rem 0.8rem;background:#f1f5f9;border-radius:9999px;font-weight:600;font-size:0.8rem;color:#3b82f6;margin-top:0.5rem;'>{TYPE_LABEL.get(qtype, '📋 题目')}</div>", unsafe_allow_html=True)

    random.seed(f"{st.session_state.get('batch_id', 0)}_{qid}")
    shuffled = random.sample(q["options"], len(q["options"]))

    st.markdown(f"<div style='background:#f8fafc;padding:1rem;border-radius:0.5rem;margin:0.5rem 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);'><div style='font-size:1.1rem;font-weight:600;line-height:1.5;'>{q['question']}</div></div>", unsafe_allow_html=True)

    if not done:
        with st.form("answer_form", clear_on_submit=True):
            if qtype == "multi":
                sel = []
                cols = st.columns(2 if len(shuffled) >= 4 else 1)
                for i, opt in enumerate(shuffled):
                    with cols[i % len(cols)]:
                        if st.checkbox(opt, key=f"q_{qid}_{i}"):
                            sel.append(opt)
            else:
                sel = st.radio("请选择", shuffled, key=f"q_{qid}", index=None, label_visibility="collapsed")

            if st.form_submit_button("✅ 提交答案", type="primary", use_container_width=True):
                if qtype == "multi":
                    if not sel:
                        st.warning("⚠️ 请至少选择一个选项")
                        return
                    st.session_state.this_batch_answers[qid] = sel
                else:
                    if sel is None:
                        st.warning("⚠️ 请选择一个选项")
                        return
                    st.session_state.this_batch_answers[qid] = sel

                # 判题
                ua = st.session_state.this_batch_answers[qid]
                cl = set(q["answer"].split("|"))
                if qtype == "multi":
                    ul = {a.split(".")[0].strip().upper() for a in ua}
                    correct = ul == cl
                else:
                    ul = ua.split(".")[0].strip().upper() if ua else ""
                    correct = ul in cl

                if correct:
                    st.session_state.correct_ids.add(qid)
                    st.session_state.incorrect_ids.discard(qid)
                    st.session_state.error_counts.pop(qid, None)
                else:
                    st.session_state.incorrect_ids.add(qid)
                    st.session_state.correct_ids.discard(qid)
                    st.session_state.error_counts[qid] = st.session_state.error_counts.get(qid, 0) + 1

                save_data(uid)
                st.rerun()
    else:
        st.divider()
        ua = st.session_state.this_batch_answers[qid]
        cl = set(q["answer"].split("|"))

        if qtype == "multi":
            ul = {a.split(".")[0].strip().upper() for a in ua}
            correct = ul == cl
        else:
            ul = ua.split(".")[0].strip().upper() if ua else ""
            correct = ul in cl

        if correct:
            st.markdown("<div style='background:#d1fae5;padding:0.4rem 1rem;border-radius:9999px;text-align:center;border:1px solid #10b981;margin:0.3rem 0;'><span style='color:#065f46;font-weight:600;'>🎉 回答正确！</span></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='background:#fee2e2;padding:0.4rem 1rem;border-radius:9999px;text-align:center;border:1px solid #ef4444;margin:0.3rem 0;'><span style='color:#991b1b;font-weight:600;'>❌ 回答错误</span></div>", unsafe_allow_html=True)

        st.markdown("<h4 style='margin-top:0.75rem;'>📋 所有选项：</h4>", unsafe_allow_html=True)
        for opt in shuffled:
            letter = opt.split(".")[0].strip().upper()
            ic = letter in cl
            is_ = opt in ua if qtype == "multi" else opt == ua
            fb = "✅ " if ic else ("❌ " if is_ and not ic else "")
            bg = "background:#d1fae5;" if ic else "background:#fff;"
            bd = "border:2px solid #10b981;" if ic else "border:2px solid #e5e7eb;"
            co = "color:#065f46;" if ic else "color:#1f2937;"
            st.markdown(f"<div style='{bg}{bd}{co}padding:0.5rem;margin-bottom:0.3rem;border-radius:0.375rem;font-size:1rem;'>{fb}{opt}</div>", unsafe_allow_html=True)

        co = [o for o in q["options"] if any(o.startswith(c) for c in cl)]
        st.markdown(f"<div style='margin-top:0.75rem;padding:0.75rem;background:#f9fafb;border-radius:0.5rem;'><h4 style='margin:0 0 0.3rem;color:#374151;'>💡 正确答案：</h4><p style='font-size:1rem;color:#065f46;margin:0;padding:0.5rem;background:#d1fae5;border-radius:0.375rem;border-left:4px solid #10b981;'><strong>{', '.join(co)}</strong></p></div>", unsafe_allow_html=True)

        if st.button("➡️ 下一题", type="primary", use_container_width=True):
            st.session_state.current_idx += 1
            st.rerun()

# ===================== 主程序 =====================
def main():
    init_firestore()

    if not st.session_state.get("logged_in"):
        if "all_questions" not in st.session_state:
            st.session_state.all_questions = load_questions(BANK_PATH)
        render_login()
        return

    if "all_questions" not in st.session_state:
        st.session_state.all_questions = load_questions(BANK_PATH)

    if "selected_mode_label" not in st.session_state:
        st.session_state.selected_mode_label = "全部题目"
        st.session_state.quiz_started = False
        st.session_state.error_counts = {}
        st.session_state.correct_ids = set()
        st.session_state.incorrect_ids = set()

    st.title("🔧 结构修理 刷题助手")
    st.divider()
    render_sidebar()
    render_quiz()

if __name__ == "__main__":
    main()
