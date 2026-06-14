"""
结构修理 刷题助手
Firebase Auth + Firestore REST API（零重依赖，冷启动秒开）
"""
import streamlit as st
import json
import random
import time
import requests
from pathlib import Path

st.set_page_config(page_title="结构修理 刷题助手", page_icon="🔧", layout="centered")

BANK_PATH = Path(__file__).resolve().parent / "quiz_bank.json"
PROJECT_ID = "lxgdeshu"
FIRESTORE_BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

_api_key = None
_access_token = None
_token_expiry = 0

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

# ===================== 密钥加载 =====================
def _load_secret(key):
    try:
        return st.secrets["firebase"][key]
    except Exception:
        pass
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

# ===================== Auth REST API =====================
def _get_api_key():
    global _api_key
    if _api_key is None:
        _api_key = _load_secret("api_key") or ""
    return _api_key

def firebase_call(endpoint, email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={_get_api_key()}"
    r = requests.post(url, json={"email": email, "password": password, "returnSecureToken": True}, timeout=10)
    return r.json()

# ===================== Firestore REST API =====================
def _get_sa():
    sa = _load_secret("service_account")
    if sa is None:
        return None
    # SA 可能是 dict（TOML 原生）或 JSON 字符串
    if isinstance(sa, dict) and "private_key" in sa:
        # TOML """ 不转义 \n，需手动修复私钥中的字面 \n → 真换行
        pk = sa.get("private_key", "")
        if "\\n" in pk and "\n" not in pk.strip("-----"):
            sa = dict(sa)
            sa["private_key"] = pk.replace("\\n", "\n")
        return sa
    if isinstance(sa, str):
        try:
            sa = json.loads(sa)
        except json.JSONDecodeError:
            import re
            fixed = re.sub(r'("private_key":\s*")(.*?)(")', lambda m: m.group(1)+m.group(2).replace('\n','\\n')+m.group(3), sa, flags=re.DOTALL)
            sa = json.loads(fixed)
    return sa if isinstance(sa, dict) and "private_key" in sa else None

def _get_access_token():
    global _access_token, _token_expiry
    if _access_token and time.time() < _token_expiry - 60:
        return _access_token

    sa = _get_sa()
    if sa is None:
        st.session_state.fs_status = "⚠️ 未读取到 service_account（检查 Secrets）"
        return None

    try:
        import jwt
    except ImportError:
        st.session_state.fs_status = "⚠️ 缺少 PyJWT 库（检查 requirements.txt）"
        return None

    try:
        now = int(time.time())
        payload = {"iss":sa["client_email"],"scope":"https://www.googleapis.com/auth/datastore","aud":sa["token_uri"],"exp":now+3600,"iat":now}
        signed = jwt.encode(payload, sa["private_key"], algorithm="RS256")
        r = requests.post(sa["token_uri"], data={"grant_type":"urn:ietf:params:oauth:grant-type:jwt-bearer","assertion":signed}, timeout=10)
        resp = r.json()
        _access_token = resp.get("access_token")
        _token_expiry = now + 3600
        if not _access_token:
            st.session_state.fs_status = f"⚠️ Token 交换失败: {resp.get('error','未知')}"
            return None
        return _access_token
    except Exception as e:
        st.session_state.fs_status = f"⚠️ 签名失败: {str(e)[:40]}"
        return None

def _fs_req(method, uid, data=None):
    token = _get_access_token()
    if not token:
        return None  # _get_access_token 已经设了 fs_status
    url = f"{FIRESTORE_BASE}/users/{uid}"
    headers = {"Authorization": f"Bearer {token}"}

    if method == "GET":
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            st.session_state.fs_status = "☁️ 已连接"
            return r.json()
        st.session_state.fs_status = f"⚠️ 读取失败 ({r.status_code})"
        return None

    if method == "DELETE":
        requests.delete(url, headers=headers, timeout=10)
        return None

    if method == "PATCH":
        body = {"fields": _to_firestore(data)}
        r = requests.post(f"{FIRESTORE_BASE}/users?documentId={uid}", json=body, headers=headers, timeout=10)
        if r.status_code == 200:
            st.session_state.fs_status = "☁️ 已保存"
            return r.json()
        st.session_state.fs_status = f"⚠️ 保存失败 ({r.status_code})"
        return None

    return None

def _to_firestore(data):
    fd = {}
    for k, v in data.items():
        if isinstance(v, list):
            fd[k] = {"arrayValue": {"values": [{"stringValue": str(x)} for x in v]}}
        elif isinstance(v, dict):
            fd[k] = {"mapValue": {"fields": {kk: {"integerValue": str(vv)} if isinstance(vv,int) else {"stringValue":str(vv)} for kk,vv in v.items()}}}
        elif isinstance(v, int):
            fd[k] = {"integerValue": str(v)}
        else:
            fd[k] = {"stringValue": str(v)}
    return fd

def load_data(uid):
    doc = _fs_req("GET", uid)
    if doc and "fields" in doc:
        f = doc["fields"]
        def _arr(key):
            vals = f.get(key,{}).get("arrayValue",{}).get("values",[])
            return [v.get("stringValue","") for v in vals]
        st.session_state.correct_ids = set(_arr("correct_ids"))
        st.session_state.incorrect_ids = set(_arr("incorrect_ids"))
        ec_raw = f.get("error_counts",{}).get("mapValue",{}).get("fields",{})
        st.session_state.error_counts = {k: int(v.get("integerValue","0")) for k,v in ec_raw.items()}
        st.session_state.selected_mode_label = f.get("selected_mode_label",{}).get("stringValue","全部题目")
    else:
        if "correct_ids" not in st.session_state:
            st.session_state.correct_ids = set()
            st.session_state.incorrect_ids = set()
            st.session_state.error_counts = {}
            st.session_state.selected_mode_label = "全部题目"

def save_data(uid):
    _fs_req("PATCH", uid, {
        "correct_ids": list(st.session_state.correct_ids),
        "incorrect_ids": list(st.session_state.incorrect_ids),
        "error_counts": st.session_state.error_counts,
        "selected_mode_label": st.session_state.selected_mode_label,
        "updated_at": int(time.time()),
    })

def clear_data(uid):
    _fs_req("DELETE", uid)

# ===================== 题库 =====================
@st.cache_data(ttl=3600, show_spinner="正在启动...")
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
TYPE_LABEL = {"single": "🔘 单选题", "multi": "☑️ 多选题", "judge": "⚖️ 判断题"}

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
    st.session_state.batch_answers = {}
    st.session_state.quiz_finished = False
    st.session_state.batch_id = random.randint(1, 1000000)

# ===================== 登录/注册 =====================
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
                    st.error("该邮箱已被注册，请直接登录" if "EMAIL_EXISTS" in msg else f"注册失败: {msg}")
                    return
                uid = resp["localId"]
                st.session_state.user_email = email
                st.session_state.user_uid = uid
                st.session_state.logged_in = True
                st.session_state.correct_ids = set()
                st.session_state.incorrect_ids = set()
                st.session_state.error_counts = {}
                st.session_state.selected_mode_label = "全部题目"
                _fs_req("PATCH", uid, {"email": email, "created_at": int(time.time())})
                st.rerun()
            else:
                resp = firebase_call("signInWithPassword", email, pw)
                if "idToken" not in resp:
                    msg = resp.get("error", {}).get("message", "")
                    st.error("邮箱或密码错误" if "EMAIL_NOT_FOUND" in msg or "INVALID_PASSWORD" in msg else f"登录失败: {msg}")
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
    total = len(st.session_state.all_questions)
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.user_email}**")
        st.caption(st.session_state.get("fs_status", ""))

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

        sn = sum(1 for q in st.session_state.all_questions if q["type"] == "single")
        mn = sum(1 for q in st.session_state.all_questions if q["type"] == "multi")
        jn = sum(1 for q in st.session_state.all_questions if q["type"] == "judge")
        st.markdown(f"<div style='color:#2e7d32;font-size:0.85rem;font-weight:600;'>📚 题库共 {total} 题</div><div style='color:#6b7280;font-size:0.78rem;margin-bottom:0.5rem;'>单选 {sn} · 多选 {mn} · 判断 {jn}</div>", unsafe_allow_html=True)

        if st.button("🚀 开始/重置练习", type="primary"):
            st.session_state.show_wrong = False
            st.session_state.batch_answers = {}
            st.session_state.quiz_finished = False
            st.session_state.quiz_started = True
            make_batch(MODE_MAP[st.session_state.selected_mode_label])

        if st.session_state.get("quiz_started") and st.session_state.get("current_batch"):
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
        if st.button("📝 查看错题", type="primary", use_container_width=True):
            st.session_state.show_wrong = True
            st.rerun()

        st.divider()
        with st.expander("⚠️ 高级选项", expanded=False):
            if st.button("🗑️ 清空所有学习数据", type="secondary"):
                clear_data(uid)
                st.session_state.correct_ids = set()
                st.session_state.incorrect_ids = set()
                st.session_state.error_counts = {}
                st.session_state.quiz_started = False
                st.success("✅ 已清空！")
                st.rerun()

# ===================== 错题查看 =====================
def render_wrong_questions():
    st.subheader("📝 错题回顾")
    wr = sorted(
        [q for q in st.session_state.all_questions if q["id"] in st.session_state.error_counts],
        key=lambda q: st.session_state.error_counts[q["id"]], reverse=True)

    if st.button("🔙 返回刷题", type="primary"):
        st.session_state.show_wrong = False
        st.rerun()

    if not wr:
        st.markdown("<div style='text-align:center;padding:2rem;color:#2e7d32;font-size:1.1rem;'>🎉 暂无错题，继续保持！</div>", unsafe_allow_html=True)
        return

    st.markdown(f"<div style='color:#2e7d32;font-weight:600;margin-bottom:0.5rem;'>📋 共 {len(wr)} 道错题（按错误次数降序）</div>", unsafe_allow_html=True)

    for q in wr:
        ec = st.session_state.error_counts[q["id"]]
        tlb = TYPE_LABEL.get(q["type"], "题目")
        cl = set(q["answer"].split("|"))
        correct_opts = [o for o in q["options"] if any(o.startswith(c) for c in cl)]

        st.markdown(f"<div style='background:#f8fafc;padding:0.8rem 1rem;border-radius:0.5rem;margin:0.6rem 0;box-shadow:0 1px 3px rgba(0,0,0,0.06);border-left:4px solid #ef4444;'>", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#ef4444;font-weight:700;'>✘ {ec} 次</span> &nbsp; <span style='font-size:0.75rem;color:#6b7280;'>{tlb}</span><br><span style='font-size:1rem;font-weight:600;color:#1f2937;'>{q['question']}</span>", unsafe_allow_html=True)
        st.markdown(f"<p style='margin:0.3rem 0 0 0;color:#065f46;font-size:0.9rem;'>✅ 答案：{', '.join(correct_opts)}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ===================== 答题主界面 =====================
def render_quiz():
    uid = st.session_state.user_uid

    if not st.session_state.quiz_started:
        st.markdown("<div style='text-align:center;padding:3rem 1rem;color:#2e7d32;font-size:1.05rem;'>👈 在左侧选择模式后，点击「开始/重置练习」</div>", unsafe_allow_html=True)
        return

    if st.session_state.quiz_finished:
        st.balloons()
        st.success("🎉 本轮练习完成！")
        if st.button("再来一轮", type="primary"):
            st.session_state.batch_answers = {}
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
    done = qid in st.session_state.batch_answers

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
                    st.session_state.batch_answers[qid] = sel
                else:
                    if sel is None:
                        st.warning("⚠️ 请选择一个选项")
                        return
                    st.session_state.batch_answers[qid] = sel

                ua = st.session_state.batch_answers[qid]
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
        ua = st.session_state.batch_answers[qid]
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
            i_c = letter in cl
            i_s = opt in ua if qtype == "multi" else opt == ua
            fb = "✅ " if i_c else ("❌ " if i_s and not i_c else "")
            bg = "background:#d1fae5;" if i_c else "background:#fff;"
            bd = "border:2px solid #10b981;" if i_c else "border:2px solid #e5e7eb;"
            color = "color:#065f46;" if i_c else "color:#1f2937;"
            st.markdown(f"<div style='{bg}{bd}{color}padding:0.5rem;margin-bottom:0.3rem;border-radius:0.375rem;font-size:1rem;'>{fb}{opt}</div>", unsafe_allow_html=True)

        corr = [o for o in q["options"] if any(o.startswith(c) for c in cl)]
        st.markdown(f"<div style='margin-top:0.75rem;padding:0.75rem;background:#f9fafb;border-radius:0.5rem;'><h4 style='margin:0 0 0.3rem;color:#374151;'>💡 正确答案：</h4><p style='font-size:1rem;color:#065f46;margin:0;padding:0.5rem;background:#d1fae5;border-radius:0.375rem;border-left:4px solid #10b981;'><strong>{', '.join(corr)}</strong></p></div>", unsafe_allow_html=True)

        if st.button("➡️ 下一题", type="primary", use_container_width=True):
            st.session_state.current_idx += 1
            st.rerun()

# ===================== 主程序 =====================
def main():
    if not st.session_state.get("logged_in"):
        if "all_questions" not in st.session_state:
            st.session_state.all_questions = load_questions(BANK_PATH)
        render_login()
        return

    if "all_questions" not in st.session_state:
        st.session_state.all_questions = load_questions(BANK_PATH)
    if "selected_mode_label" not in st.session_state:
        st.session_state.selected_mode_label = "全部题目"
    if "correct_ids" not in st.session_state:
        st.session_state.correct_ids = set()
        st.session_state.incorrect_ids = set()
        st.session_state.error_counts = {}
    if "quiz_started" not in st.session_state:
        st.session_state.quiz_started = False
    if "fs_status" not in st.session_state:
        st.session_state.fs_status = "☁️ 等待连接..."

    st.title("🔧 结构修理 刷题助手")
    st.divider()
    render_sidebar()
    if st.session_state.get("show_wrong"):
        render_wrong_questions()
    else:
        render_quiz()

if __name__ == "__main__":
    main()
