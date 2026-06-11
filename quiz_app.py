"""
结构修理 刷题助手 — 多用户版
登录/注册：Firebase Auth → Firestore
答题：st.form 提交，避免刷新丢失登录态
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
firebase_api_key = None

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
def init_firebase():
    global db, firebase_api_key
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        return

    # 1) 加载 API Key（Auth REST API 用，优先从本地文件）
    try:
        api_key = st.secrets["firebase"]["api_key"]
    except Exception:
        cfg = Path(__file__).resolve().parent / "firebase_config.json"
        if cfg.exists():
            with open(cfg) as f:
                api_key = json.load(f).get("api_key")
        else:
            return

    if not api_key:
        return
    firebase_api_key = api_key

    # 2) 加载 Service Account（Firestore 用）
    try:
        raw = st.secrets["firebase"]["service_account"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        cred = credentials.Certificate(raw)
    except Exception:
        sa = Path(__file__).resolve().parent / "firebase-service-account.json"
        if sa.exists():
            cred = credentials.Certificate(str(sa))
        else:
            return

    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        print(f"Firestore 初始化失败: {e}")

# ===================== 题库加载 =====================
@st.cache_data(ttl=3600, show_spinner="正在加载题库...")
def load_questions(file_path):
    if not file_path.exists():
        st.error(f"题库文件未找到: {file_path.name}")
        st.stop()
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    normalized = []
    for item in data:
        q_type = item.get("type", "single")
        q_text = item.get("question", "").strip()
        opts_raw = item.get("options", {})
        answer_raw = item.get("answer")
        if not q_text or not opts_raw or answer_raw is None:
            continue
        opts_list = [f"{k}. {v}" for k, v in sorted(opts_raw.items())]
        if q_type == "multi":
            answer_str = "|".join(sorted(str(a).strip().upper() for a in answer_raw))
        elif isinstance(answer_raw, list):
            answer_str = str(answer_raw[0]).strip().upper()
        else:
            answer_str = str(answer_raw).strip().upper()
        normalized.append({
            "id": item.get("id", f"q{len(normalized):04d}"),
            "type": q_type,
            "question": q_text,
            "options": opts_list,
            "answer": answer_str,
        })
    return normalized

# ===================== Firebase Auth REST API =====================
def firebase_sign_up(email, password):
    """注册：调用 Firebase Auth REST API 创建账号，成功后返回 localId + idToken"""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={firebase_api_key}"
    r = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True})
    return r.json()

def firebase_sign_in(email, password):
    """登录：调用 Firebase Auth REST API 验证邮箱密码，成功后返回 localId + idToken"""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
    r = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True})
    return r.json()

# ===================== Firestore 进度 CRUD =====================
def _progress_doc(uid):
    return db.collection("users").document(uid).collection("data").document("progress")

def _init_user_firestore(uid, email):
    """注册第二步：在 Firestore 写入用户初始化文档"""
    _progress_doc(uid).set({
        "email": email,
        "correct_ids": [],
        "incorrect_ids": [],
        "error_counts": {},
        "created_at": int(time.time()),
    })

def _load_from_firestore(uid):
    """登录第二步：从 Firestore 拉取用户进度到 session_state"""
    doc = _progress_doc(uid).get()
    if doc.exists:
        d = doc.to_dict()
        st.session_state.correct_ids = set(d.get("correct_ids", []))
        st.session_state.incorrect_ids = set(d.get("incorrect_ids", []))
        st.session_state.error_counts = d.get("error_counts", {})
    else:
        # 用户首次登录，初始化空进度
        _init_user_firestore(uid, st.session_state.user_email)

def _save_to_firestore(uid):
    """同步当前 session_state 进度到 Firestore"""
    _progress_doc(uid).set({
        "correct_ids": list(st.session_state.correct_ids),
        "incorrect_ids": list(st.session_state.incorrect_ids),
        "error_counts": st.session_state.error_counts,
        "updated_at": int(time.time()),
    }, merge=True)

def _clear_firestore(uid):
    _progress_doc(uid).delete()



# ===================== 出题逻辑 =====================
def get_mode_value(label):
    return {"全部题目": "all", "仅单选题": "single", "仅多选题": "multi", "仅判断题": "judge", "仅错题": "wrong"}[label]

def generate_batch(mode):
    all_qs = st.session_state.all_questions
    pool = all_qs
    if mode == "single":
        pool = [q for q in all_qs if q["type"] == "single"]
    elif mode == "multi":
        pool = [q for q in all_qs if q["type"] == "multi"]
    elif mode == "judge":
        pool = [q for q in all_qs if q["type"] == "judge"]
    elif mode == "wrong":
        error_ids = set(st.session_state.incorrect_ids)
        pool = [q for q in all_qs if q["id"] in error_ids]

    if not pool:
        st.session_state.quiz_started = False
        if mode == "wrong":
            st.success("🎉 恭喜！目前没有错题。")
        else:
            st.error("当前模式下没有题目。")
        return

    if mode == "wrong":
        batch = pool.copy()
        random.shuffle(batch)
    else:
        correct_set = st.session_state.correct_ids
        incorrect_set = st.session_state.incorrect_ids
        batch = [q for q in pool if q["id"] in incorrect_set]
        correct_pool = [q for q in pool if q["id"] in correct_set]
        if correct_pool:
            batch.extend(random.sample(correct_pool, min(20, len(correct_pool))))
        seen = correct_set | incorrect_set
        unseen = [q for q in pool if q["id"] not in seen]
        remaining = 100 - len(batch)
        if remaining > 0 and unseen:
            batch.extend(random.sample(unseen, min(remaining, len(unseen))))
        random.shuffle(batch)

    st.session_state.current_batch = batch
    st.session_state.current_question_idx = 0
    st.session_state.submitted_answers = {}
    st.session_state.quiz_finished = not batch
    st.session_state.batch_id = random.randint(1, 1000000)

def save_progress(uid):
    """保存当前进度到 Firestore"""
    _save_to_firestore(uid)

# ===================== 登录/注册页 =====================
def render_login_page():
    st.title("🔧 结构修理 刷题助手")

    mode = st.radio("登录方式", ["登录", "注册"], horizontal=True, key="auth_mode", label_visibility="collapsed")
    is_register = (mode == "注册")

    with st.form("auth_form", clear_on_submit=False):
        email = st.text_input("邮箱", key="auth_email", placeholder="请输入邮箱地址")
        password = st.text_input("密码", type="password", key="auth_password", placeholder="至少 6 位")
        confirm = ""
        if is_register:
            confirm = st.text_input("确认密码", type="password", key="auth_confirm", placeholder="再次输入密码")

        btn_label = "📝 注 册" if is_register else "🔑 登 录"
        submitted = st.form_submit_button(btn_label, type="primary", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("请填写邮箱和密码")
                return
            if "@" not in email or "." not in email.split("@")[-1]:
                st.error("请输入有效的邮箱地址")
                return

            if is_register:
                # ====== 注册流程：Auth 创建账号 → Firestore 初始化 ======
                if confirm != password:
                    st.error("两次密码不一致")
                    return
                if len(password) < 6:
                    st.error("密码至少 6 位")
                    return

                resp = firebase_sign_up(email, password)
                if "idToken" not in resp:
                    msg = resp.get("error", {}).get("message", "注册失败")
                    if "EMAIL_EXISTS" in msg:
                        st.error("该邮箱已被注册，请直接登录")
                    elif "WEAK_PASSWORD" in msg:
                        st.error("密码强度不够，请至少 6 位")
                    else:
                        st.error(f"注册失败: {msg}")
                    return

                uid = resp["localId"]
                _init_user_firestore(uid, email)
                st.session_state.user_email = email
                st.session_state.user_uid = uid
                st.session_state.logged_in = True
                st.rerun()
            else:
                # ====== 登录流程：Auth 验证 → Fetch Firestore ======
                resp = firebase_sign_in(email, password)
                if "idToken" not in resp:
                    msg = resp.get("error", {}).get("message", "登录失败")
                    if "EMAIL_NOT_FOUND" in msg or "INVALID_PASSWORD" in msg:
                        st.error("邮箱或密码错误")
                    elif "INVALID_EMAIL" in msg:
                        st.error("邮箱格式不正确")
                    else:
                        st.error(f"登录失败: {msg}")
                    return

                uid = resp["localId"]
                st.session_state.user_email = resp["email"]
                st.session_state.user_uid = uid
                st.session_state.logged_in = True
                _load_from_firestore(uid)
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

        selected = st.radio(
            "选择练习模式",
            options=["全部题目", "仅单选题", "仅多选题", "仅判断题", "仅错题"],
            index=["全部题目", "仅单选题", "仅多选题", "仅判断题", "仅错题"].index(st.session_state.selected_mode_label),
            horizontal=True,
        )
        if selected != st.session_state.selected_mode_label:
            st.session_state.selected_mode_label = selected
            if st.session_state.quiz_started:
                st.warning("模式已更改，请点击下方按钮重新开始。")

        total = len(st.session_state.all_questions)
        single_n = sum(1 for q in st.session_state.all_questions if q["type"] == "single")
        multi_n = sum(1 for q in st.session_state.all_questions if q["type"] == "multi")
        judge_n = sum(1 for q in st.session_state.all_questions if q["type"] == "judge")
        st.info(f"题库：共 **{total}** 题（单选 {single_n} · 多选 {multi_n} · 判断 {judge_n}）")

        if st.button("🚀 开始/重置练习", type="primary"):
            mode = get_mode_value(st.session_state.selected_mode_label)
            st.session_state.current_batch = []
            st.session_state.current_question_idx = 0
            st.session_state.submitted_answers = {}
            st.session_state.quiz_finished = False
            st.session_state.quiz_started = True
            generate_batch(mode)

        if st.session_state.quiz_started:
            st.divider()
            st.header("📊 学习进度")
            correct_n = len(st.session_state.correct_ids)
            incorrect_n = len(st.session_state.incorrect_ids)
            answered_n = correct_n + incorrect_n
            accuracy = (correct_n / answered_n * 100) if answered_n > 0 else 0
            mastery_pct = (correct_n / total * 100) if total > 0 else 0
            st.progress(mastery_pct / 100, text=f"✅ 已掌握: {mastery_pct:.1f}%")
            st.markdown(f"<div style='text-align:center;color:#6b7280;font-size:0.9rem;'>{correct_n} / {total} 题</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.metric("❌ 未掌握", incorrect_n)
            c2.metric("🎯 正确率", f"{accuracy:.1f}%")

        st.divider()
        st.header("💾 数据管理")
        with st.expander("⚠️ 高级选项", expanded=False):
            st.warning("⚠️ 将永久删除此账号的所有学习进度！")
            if st.button("✅ 确认清空", type="primary"):
                _clear_firestore(uid)
                st.session_state.correct_ids = set()
                st.session_state.incorrect_ids = set()
                st.session_state.error_counts = {}
                st.success("✅ 已清空！")
                st.rerun()

# ===================== 答题主界面（st.form 版） =====================
def render_main():
    uid = st.session_state.user_uid

    if not st.session_state.quiz_started:
        st.info("请在左侧选择模式，点击「开始/重置练习」按钮开始。")
        return

    if st.session_state.quiz_finished:
        st.balloons()
        st.success("🎉 本轮练习完成！")
        if st.button("再来一轮", type="primary"):
            mode = get_mode_value(st.session_state.selected_mode_label)
            st.session_state.current_batch = []
            st.session_state.current_question_idx = 0
            st.session_state.submitted_answers = {}
            st.session_state.quiz_finished = False
            st.session_state.quiz_started = True
            generate_batch(mode)
            st.rerun()
        return

    batch = st.session_state.current_batch
    idx = st.session_state.current_question_idx
    if idx >= len(batch):
        generate_batch(get_mode_value(st.session_state.selected_mode_label))
        st.rerun()

    q = batch[idx]
    qid = q["id"]
    qtype = q["type"]
    is_submitted = qid in st.session_state.submitted_answers

    type_labels = {"single": "🔘 单选题", "multi": "☑️ 多选题", "judge": "⚖️ 判断题"}
    c1, c2 = st.columns([3, 1])
    c1.subheader(f"第 {idx+1}/{len(batch)} 题")
    c2.markdown(f"<div style='text-align:right;padding:0.3rem 0.8rem;background:#f1f5f9;border-radius:9999px;font-weight:600;font-size:0.8rem;color:#3b82f6;margin-top:0.5rem;'>{type_labels.get(qtype, '📋 题目')}</div>", unsafe_allow_html=True)

    batch_id = st.session_state.get("batch_id", 0)
    random.seed(f"{batch_id}_{qid}")
    shuffled = random.sample(q["options"], len(q["options"]))

    st.markdown(f"<div style='background:#f8fafc;padding:1rem;border-radius:0.5rem;margin:0.5rem 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);'><div style='font-size:1.1rem;font-weight:600;line-height:1.5;'>{q['question']}</div></div>", unsafe_allow_html=True)

    # ---------- 未提交：显示答题表单 ----------
    if not is_submitted:
        with st.form("answer_form", clear_on_submit=True):
            if qtype == "multi":
                selected = []
                cols = st.columns(2 if len(shuffled) >= 4 else 1)
                for i, opt in enumerate(shuffled):
                    with cols[i % len(cols)]:
                        if st.checkbox(opt, key=f"q_{qid}_opt_{i}"):
                            selected.append(opt)
            else:
                # 单选题 + 判断题
                selection = st.radio("请选择", shuffled, key=f"q_{qid}", index=None, label_visibility="collapsed")

            submitted = st.form_submit_button("✅ 提交答案", type="primary", use_container_width=True)

            if submitted:
                if qtype == "multi":
                    if not selected:
                        st.warning("⚠️ 请至少选择一个选项")
                        return
                    st.session_state.submitted_answers[qid] = selected
                else:
                    if selection is None:
                        st.warning("⚠️ 请选择一个选项")
                        return
                    st.session_state.submitted_answers[qid] = selection

                # 判题 + 存进度
                user_ans = st.session_state.submitted_answers[qid]
                correct_letters = set(q["answer"].split("|"))
                if qtype == "multi":
                    user_letters = {a.split(".")[0].strip().upper() for a in user_ans}
                    correct = user_letters == correct_letters
                else:
                    user_letter = user_ans.split(".")[0].strip().upper()
                    correct = user_letter in correct_letters

                if correct:
                    st.session_state.correct_ids.add(qid)
                    st.session_state.incorrect_ids.discard(qid)
                    st.session_state.error_counts.pop(qid, None)
                else:
                    st.session_state.incorrect_ids.add(qid)
                    st.session_state.correct_ids.discard(qid)
                    st.session_state.error_counts[qid] = st.session_state.error_counts.get(qid, 0) + 1

                save_progress(uid)
                st.rerun()  # 刷新显示结果

    # ---------- 已提交：显示结果 ----------
    else:
        st.divider()
        user_ans = st.session_state.submitted_answers[qid]
        correct_letters = set(q["answer"].split("|"))

        if qtype == "multi":
            user_letters = {a.split(".")[0].strip().upper() for a in user_ans}
            is_correct = user_letters == correct_letters
        else:
            user_letter = user_ans.split(".")[0].strip().upper() if user_ans else ""
            is_correct = user_letter in correct_letters

        if is_correct:
            st.markdown("<div style='background:#d1fae5;padding:0.4rem 1rem;border-radius:9999px;text-align:center;border:1px solid #10b981;margin:0.3rem 0;'><span style='color:#065f46;font-weight:600;'>🎉 回答正确！</span></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='background:#fee2e2;padding:0.4rem 1rem;border-radius:9999px;text-align:center;border:1px solid #ef4444;margin:0.3rem 0;'><span style='color:#991b1b;font-weight:600;'>❌ 回答错误</span></div>", unsafe_allow_html=True)

        st.markdown("<h4 style='margin-top:0.75rem;'>📋 所有选项：</h4>", unsafe_allow_html=True)
        for opt in shuffled:
            letter = opt.split(".")[0].strip().upper()
            is_c = letter in correct_letters
            is_s = opt in user_ans if qtype == "multi" else opt == user_ans
            fb = "✅ " if is_c else ("❌ " if is_s and not is_c else "")
            bg = "background:#d1fae5;" if is_c else "background:#fff;"
            border = "border:2px solid #10b981;" if is_c else "border:2px solid #e5e7eb;"
            color = "color:#065f46;" if is_c else "color:#1f2937;"
            st.markdown(f"<div style='{bg}{border}{color}padding:0.5rem;margin-bottom:0.3rem;border-radius:0.375rem;font-size:1rem;'>{fb}{opt}</div>", unsafe_allow_html=True)

        correct_opts = [o for o in q["options"] if any(o.startswith(c) for c in correct_letters)]
        st.markdown("<div style='margin-top:0.75rem;padding:0.75rem;background:#f9fafb;border-radius:0.5rem;'><h4 style='margin:0 0 0.3rem;color:#374151;'>💡 正确答案：</h4><p style='font-size:1rem;color:#065f46;margin:0;padding:0.5rem;background:#d1fae5;border-radius:0.375rem;border-left:4px solid #10b981;'><strong>" + ', '.join(correct_opts) + "</strong></p></div>", unsafe_allow_html=True)

        if st.button("➡️ 下一题", type="primary", use_container_width=True):
            st.session_state.current_question_idx += 1
            st.rerun()

# ===================== 主程序 =====================
def main():
    init_firebase()

    if not st.session_state.get("logged_in"):
        if "all_questions" not in st.session_state:
            st.session_state.all_questions = load_questions(BANK_PATH)
        render_login_page()
        return

    if "selected_mode_label" not in st.session_state:
        st.session_state.selected_mode_label = "全部题目"
        st.session_state.quiz_started = False
        st.session_state.error_counts = {}
        st.session_state.correct_ids = set()
        st.session_state.incorrect_ids = set()

    if "all_questions" not in st.session_state:
        st.session_state.all_questions = load_questions(BANK_PATH)

    st.title("🔧 结构修理 刷题助手")
    st.divider()
    render_sidebar()
    render_main()

if __name__ == "__main__":
    main()
