"""
结构修理 刷题助手 — 多用户版
支持 Firebase（推荐云端部署）和本地文件两种模式
"""
import streamlit as st
import json
import random
import time
import hashlib
import threading
import requests
from pathlib import Path

st.set_page_config(page_title="结构修理 刷题助手", page_icon="🔧", layout="centered")

# ===================== 常量 =====================
BANK_PATH = Path(__file__).resolve().parent / "quiz_bank.json"
FIREBASE_AVAILABLE = False
db = None
firebase_api_key = None

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    pass

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
    .login-card {
        background: #fff; border-radius: 1rem; padding: 2rem;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 420px; margin: 4rem auto;
    }
</style>
""", unsafe_allow_html=True)

# ===================== Firebase 初始化 =====================
def init_firebase():
    global db, firebase_api_key
    if not FIREBASE_AVAILABLE:
        return False
    try:
        api_key = None
        cred = None
        # 优先读 Streamlit Cloud secrets
        try:
            api_key = st.secrets["firebase"]["api_key"]
            sa_json = st.secrets["firebase"]["service_account"]
            if isinstance(sa_json, str):
                sa_json = json.loads(sa_json)
            cred = credentials.Certificate(sa_json)
        except Exception:
            # 尝试本地文件
            local_sa = Path(__file__).resolve().parent / "firebase-service-account.json"
            local_cfg = Path(__file__).resolve().parent / "firebase_config.json"
            if local_sa.exists() and local_cfg.exists():
                with open(local_cfg) as f:
                    cfg = json.load(f)
                api_key = cfg.get("api_key")
                cred = credentials.Certificate(str(local_sa))
        if cred and api_key:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_api_key = api_key
            return True
    except Exception:
        pass
    return False

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

# ===================== Firebase Auth =====================
def firebase_sign_in(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
    r = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True})
    return r.json()

def firebase_sign_up(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={firebase_api_key}"
    r = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True})
    return r.json()

# ===================== 进度存储（Firebase / 本地） =====================
_save_lock = threading.Lock()

def _get_progress_doc_ref(uid):
    return db.collection("users").document(uid).collection("data").document("progress")

def load_user_progress(uid):
    """加载用户进度（Firebase 或本地）"""
    if db:
        doc = _get_progress_doc_ref(uid).get()
        if doc.exists:
            data = doc.to_dict()
            st.session_state.correct_ids = set(data.get("correct_ids", []))
            st.session_state.incorrect_ids = set(data.get("incorrect_ids", []))
            st.session_state.error_counts = data.get("error_counts", {})
        return
    # 本地模式
    local_path = Path(__file__).resolve().parent / f"progress_{uid}.json"
    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        st.session_state.correct_ids = set(data.get("correct_ids", []))
        st.session_state.incorrect_ids = set(data.get("incorrect_ids", []))
        st.session_state.error_counts = data.get("error_counts", {})

def save_user_progress(uid):
    """保存用户进度（Firebase 或本地）"""
    data = {
        "correct_ids": list(st.session_state.correct_ids),
        "incorrect_ids": list(st.session_state.incorrect_ids),
        "error_counts": st.session_state.error_counts,
        "timestamp": int(time.time()),
    }
    if db:
        def _save():
            with _save_lock:
                _get_progress_doc_ref(uid).set(data, merge=True)
        threading.Thread(target=_save, daemon=True).start()
    else:
        local_path = Path(__file__).resolve().parent / f"progress_{uid}.json"
        with _save_lock:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

def clear_user_progress(uid):
    """清空用户所有进度"""
    if db:
        _get_progress_doc_ref(uid).delete()
    else:
        local_path = Path(__file__).resolve().parent / f"progress_{uid}.json"
        if local_path.exists():
            local_path.unlink()
    st.session_state.correct_ids = set()
    st.session_state.incorrect_ids = set()
    st.session_state.error_counts = {}

# ===================== 本地用户管理（仅本地模式） =====================
LOCAL_USERS_PATH = Path(__file__).resolve().parent / "local_users.json"

def load_local_users():
    if LOCAL_USERS_PATH.exists():
        with open(LOCAL_USERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_local_users(users_data):
    with open(LOCAL_USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)

def hash_password(password):
    return hashlib.sha256(f"quiz_app_salt_{password}".encode()).hexdigest()

def local_register(username, password):
    users = load_local_users()
    if username in users:
        return False, "用户名已存在"
    if len(password) < 4:
        return False, "密码至少4位"
    users[username] = {"password_hash": hash_password(password), "created_at": int(time.time())}
    save_local_users(users)
    return True, "注册成功"

def local_login(username, password):
    users = load_local_users()
    if username not in users:
        return False, "用户不存在"
    if users[username]["password_hash"] != hash_password(password):
        return False, "密码错误"
    return True, "登录成功"

# ===================== 出题逻辑 =====================
def get_mode_value(label):
    return {"全部题目": "all", "仅单选题": "single", "仅多选题": "multi", "仅判断题": "judge", "仅错题": "wrong"}[label]

def reset_quiz():
    mode = get_mode_value(st.session_state.selected_mode_label)
    st.session_state.current_batch = []
    st.session_state.current_question_idx = 0
    st.session_state.submitted_answers = {}
    st.session_state.quiz_finished = False
    st.session_state.quiz_started = True
    generate_batch(mode)

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

# ===================== 登录/注册页面 =====================
def render_login_page():
    st.title("🔧 结构修理 刷题助手")

    tab1, tab2 = st.tabs(["🔑 登录", "📝 注册"])

    with tab1:
        email = st.text_input("用户名 / 邮箱", key="login_email", placeholder="请输入用户名或邮箱")
        password = st.text_input("密码", type="password", key="login_password", placeholder="请输入密码")
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("登 录", type="primary", use_container_width=True):
                if not email or not password:
                    st.error("请填写完整信息")
                elif db:
                    resp = firebase_sign_in(email, password)
                    if "idToken" in resp:
                        st.session_state.user_email = resp["email"]
                        st.session_state.user_uid = resp["localId"]
                        st.session_state.logged_in = True
                        st.rerun()
                    else:
                        msg = resp.get("error", {}).get("message", "登录失败")
                        st.error(f"登录失败: {msg}")
                else:
                    ok, msg = local_login(email, password)
                    if ok:
                        st.session_state.user_email = email
                        st.session_state.user_uid = email  # 本地模式用用户名做 uid
                        st.session_state.logged_in = True
                        st.rerun()
                    else:
                        st.error(msg)

    with tab2:
        new_email = st.text_input("用户名 / 邮箱", key="reg_email", placeholder="请输入用户名或邮箱")
        new_password = st.text_input("密码", type="password", key="reg_password", placeholder="至少6位（Firebase）或4位（本地）")
        confirm_pw = st.text_input("确认密码", type="password", key="reg_confirm", placeholder="再次输入密码")
        if st.button("注 册", type="primary", use_container_width=True):
            if not new_email or not new_password:
                st.error("请填写完整信息")
            elif new_password != confirm_pw:
                st.error("两次密码不一致")
            elif db:
                resp = firebase_sign_up(new_email, new_password)
                if "idToken" in resp:
                    st.success("✅ 注册成功！请切换到登录标签登录。")
                else:
                    msg = resp.get("error", {}).get("message", "注册失败")
                    st.error(f"注册失败: {msg}")
            else:
                ok, msg = local_register(new_email, new_password)
                if ok:
                    st.success(f"✅ {msg}！请切换到登录标签登录。")
                else:
                    st.error(msg)

    # 底部提示
    mode_text = "☁️ Firebase 云同步模式" if db else "💻 本地模式（数据存储在本机）"
    st.caption(mode_text)

# ===================== 刷题主界面 =====================
def render_sidebar():
    uid = st.session_state.user_uid
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.user_email}**")
        st.caption("已登录")

        if st.button("🚪 退出登录"):
            for key in ["logged_in", "user_email", "user_uid", "all_questions"]:
                st.session_state.pop(key, None)
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
            reset_quiz()

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
            with c1:
                st.metric("❌ 未掌握", incorrect_n)
            with c2:
                st.metric("🎯 正确率", f"{accuracy:.1f}%")

            with st.expander("📋 详细统计", expanded=False):
                st.write(f"**总题量:** {total} 题")
                st.write(f"**已答题量:** {answered_n} 题")
                st.write(f"**剩余题量:** {total - answered_n} 题")

        st.divider()
        st.header("💾 数据管理")
        with st.expander("⚠️ 高级选项", expanded=False):
            st.warning("⚠️ 将永久删除您的所有学习进度！")
            if st.button("✅ 确认清空", type="primary", key="confirm_clear"):
                clear_user_progress(uid)
                st.success("✅ 已清空！")
                st.rerun()

        st.divider()
        st.header("📝 错题库")
        wrong_review = [
            q for q in st.session_state.all_questions
            if q["id"] in st.session_state.error_counts and st.session_state.error_counts[q["id"]] >= 2
        ]
        st.metric("需重点复习", len(wrong_review))
        with st.expander("点击展开错题库", expanded=False):
            if not wrong_review:
                st.info("暂无需要重点复习的错题。")
            else:
                for q in wrong_review:
                    ec = st.session_state.error_counts[q["id"]]
                    with st.expander(f"ID: {q['id']} (错 {ec} 次)"):
                        st.write(f"**题干:** {q['question']}")
                        cl = q["answer"].split("|")
                        co = [o for o in q["options"] if any(o.startswith(c) for c in cl)]
                        st.markdown(f"**正确答案:** <span style='color:green'>{', '.join(co)}</span>", unsafe_allow_html=True)

def render_main():
    uid = st.session_state.user_uid
    if not st.session_state.quiz_started:
        st.info("请在左侧选择模式，点击「开始/重置练习」按钮开始。")
        return

    if st.session_state.quiz_finished:
        st.balloons()
        st.success("🎉 本轮练习完成！")
        if st.button("再来一轮", type="primary"):
            reset_quiz()
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
    with c1:
        st.subheader(f"第 {idx+1}/{len(batch)} 题")
    with c2:
        st.markdown(f"<div style='text-align:right;padding:0.3rem 0.8rem;background:#f1f5f9;border-radius:9999px;font-weight:600;font-size:0.8rem;color:#3b82f6;margin-top:0.5rem;'>{type_labels.get(qtype, '📋 题目')}</div>", unsafe_allow_html=True)

    batch_id = st.session_state.get("batch_id", 0)
    random.seed(f"{batch_id}_{qid}")
    shuffled = random.sample(q["options"], len(q["options"]))

    st.markdown(f"<div style='background:#f8fafc;padding:1rem;border-radius:0.5rem;margin:0.5rem 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);'><div style='font-size:1.1rem;font-weight:600;line-height:1.5;'>{q['question']}</div></div>", unsafe_allow_html=True)

    if not is_submitted:
        if qtype == "multi":
            selected = []
            cols = st.columns(2 if len(shuffled) >= 4 else 1)
            for i, opt in enumerate(shuffled):
                with cols[i % len(cols)]:
                    if st.checkbox(opt, key=f"q_{qid}_opt_{i}", value=False):
                        selected.append(opt)
            if st.button("✅ 提交答案", type="primary"):
                if not selected:
                    st.warning("⚠️ 请至少选择一个选项")
                else:
                    st.session_state.submitted_answers[qid] = selected
                    save_user_progress(uid)
                    st.rerun()
        else:
            sel = st.radio("请选择", shuffled, key=f"q_{qid}", index=None, label_visibility="collapsed")
            if sel is not None:
                st.session_state.submitted_answers[qid] = sel
                save_user_progress(uid)
                st.rerun()
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
            st.session_state.correct_ids.add(qid)
            st.session_state.incorrect_ids.discard(qid)
            st.session_state.error_counts.pop(qid, None)
        else:
            st.markdown("<div style='background:#fee2e2;padding:0.4rem 1rem;border-radius:9999px;text-align:center;border:1px solid #ef4444;margin:0.3rem 0;'><span style='color:#991b1b;font-weight:600;'>❌ 回答错误</span></div>", unsafe_allow_html=True)
            st.session_state.incorrect_ids.add(qid)
            st.session_state.correct_ids.discard(qid)
            st.session_state.error_counts[qid] = st.session_state.error_counts.get(qid, 0) + 1

        save_user_progress(uid)

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
        st.markdown("<div style='margin-top:0.75rem;padding:0.75rem;background:#f9fafb;border-radius:0.5rem;'>", unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0 0 0.3rem;color:#374151;'>💡 正确答案：</h4>", unsafe_allow_html=True)
        st.markdown(f"<p style='font-size:1rem;color:#065f46;margin:0;padding:0.5rem;background:#d1fae5;border-radius:0.375rem;border-left:4px solid #10b981;'><strong>{', '.join(correct_opts)}</strong></p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if st.button("➡️ 下一题", type="primary", use_container_width=True):
            st.session_state.current_question_idx += 1
            st.rerun()

# ===================== 主程序 =====================
def main():
    global db, firebase_api_key
    init_firebase()

    # --- 未登录：显示登录页 ---
    if not st.session_state.get("logged_in"):
        # 加载题库（登录页也需要统计信息）
        if "all_questions" not in st.session_state:
            st.session_state.all_questions = load_questions(BANK_PATH)
        render_login_page()
        return

    # --- 已登录：初始化用户进度 ---
    uid = st.session_state.user_uid
    if "selected_mode_label" not in st.session_state:
        st.session_state.selected_mode_label = "全部题目"
        st.session_state.quiz_started = False
        st.session_state.error_counts = {}
        st.session_state.correct_ids = set()
        st.session_state.incorrect_ids = set()
        load_user_progress(uid)

    # 题库每次都在（login 时已加载）
    if "all_questions" not in st.session_state:
        st.session_state.all_questions = load_questions(BANK_PATH)

    st.title("🔧 结构修理 刷题助手")
    st.divider()
    render_sidebar()
    render_main()

if __name__ == "__main__":
    main()
