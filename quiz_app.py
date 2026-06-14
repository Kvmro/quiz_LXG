"""
结构修理 刷题助手
Firebase Auth + Realtime Database · 数据永久保存 · 冷启动 < 5s
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
API_KEY = "AIzaSyDMTrkNp0owogIvuMjCz_K6HZIlUezJVgQ"
RTDB_URL = f"https://{PROJECT_ID}-default-rtdb.firebaseio.com"

st.markdown("""<style>
    .main{background:linear-gradient(135deg,#d4edda 0%,#c3e6cb 100%);min-height:100vh;padding:1rem}
    .stApp{background-color:#f8fff8;border-radius:1rem;box-shadow:0 20px 25px -5px rgba(0,0,0,.1);margin:0 auto;max-width:1000px;overflow:hidden}
    [data-testid="stSidebar"]{background:#f1f8e9;border-right:1px solid #e8f5e8}
    .stButton>button{width:100%;font-size:.95rem;padding:.6rem 1rem;border-radius:.5rem;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.1)}
    .stButton>button:hover{transform:translateY(-2px);box-shadow:0 4px 6px rgba(0,0,0,.1)}
    div[data-baseweb="radio"]>div,div[data-baseweb="checkbox"]>div{width:100%!important;padding:.75rem 1rem;border:2px solid #c8e6c9;border-radius:.75rem;background:#fff;transition:all .2s;margin-bottom:.75rem;box-shadow:0 1px 3px rgba(0,0,0,.05)}
    div[data-baseweb="radio"]>div[aria-checked="true"],div[data-baseweb="checkbox"]>div[data-checked="true"]{border-color:#4caf50;background:#e8f5e8;font-weight:600;box-shadow:0 0 0 3px rgba(76,175,80,.1)}
    div[data-baseweb="radio"]>div:hover,div[data-baseweb="checkbox"]>div:hover{border-color:#a5d6a7;background:#f1f8e9}
    div[data-baseweb="radio"]>div>div:first-child,div[data-baseweb="checkbox"]>div>div:first-child{display:none}
    div[data-baseweb="radio"]>div>div:last-child,div[data-baseweb="checkbox"]>div>div:last-child{flex-grow:1;text-align:left;font-size:.95rem}
    h1,h2,h3{font-weight:700!important;background:linear-gradient(135deg,#2e7d32,#4caf50);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
    [data-testid="stProgressBar"]{border-radius:9999px;height:14px}
    [data-testid="stProgressBar"]>div{border-radius:9999px}
    hr{border:0;height:2px;background:linear-gradient(90deg,transparent,#c8e6c9,transparent);margin:1.5rem 0}
    .pg-bar{display:flex;align-items:center;gap:.5rem;margin:.5rem 0}
    .pg-fill{flex:1;height:14px;border-radius:9999px;overflow:hidden;background:#e5e7eb}
    .pg-fill>div{height:100%;border-radius:9999px;background:linear-gradient(90deg,#4caf50,#81c784);transition:width .4s}
    .pg-label{font-size:.8rem;color:#6b7280;white-space:nowrap}
</style>""", unsafe_allow_html=True)

# ==================== Auth ====================
def _auth_post(endpoint, data):
    return requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={API_KEY}",
        json={**data, "returnSecureToken": True}, timeout=10).json()

# ==================== RTDB ====================
def _rtdb_call(method, uid, data=None):
    token = st.session_state.get("_id_token")
    if not token:
        return None
    url = f"{RTDB_URL}/users/{uid}.json?auth={token}"
    if method == "GET":
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else None
    if method == "PUT":
        r = requests.put(url, json=data, timeout=10)
        st.session_state.fs_status = "☁️ 已保存" if r.status_code == 200 else f"⚠️ 保存失败 {r.status_code}"
    if method == "DELETE":
        requests.delete(url, timeout=10)

def load_data(uid):
    data = _rtdb_call("GET", uid)
    if data:
        st.session_state.correct_ids = set(data.get("correct_ids", []))
        st.session_state.incorrect_ids = set(data.get("incorrect_ids", []))
        st.session_state.error_counts = data.get("error_counts", {})
        st.session_state.selected_mode_label = data.get("selected_mode_label", "全部题目")
        st.session_state.total_answers = data.get("total_answers", 0)
    else:
        if "correct_ids" not in st.session_state:
            st.session_state.correct_ids = set()
            st.session_state.incorrect_ids = set()
            st.session_state.error_counts = {}
            st.session_state.selected_mode_label = "全部题目"
            st.session_state.total_answers = 0

def save_data(uid):
    _rtdb_call("PUT", uid, {
        "correct_ids": list(st.session_state.correct_ids),
        "incorrect_ids": list(st.session_state.incorrect_ids),
        "error_counts": st.session_state.error_counts,
        "selected_mode_label": st.session_state.selected_mode_label,
        "total_answers": st.session_state.get("total_answers", 0),
        "updated_at": int(time.time()),
    })

def clear_data(uid):
    _rtdb_call("DELETE", uid)

# ==================== 题库 ====================
@st.cache_data(ttl=3600, show_spinner="正在启动...")
def load_questions(fp):
    if not fp.exists():
        st.error("题库文件未找到"); st.stop()
    data = json.loads(fp.read_text(encoding="utf-8"))
    qs = []
    for item in data:
        t = item.get("type", "single")
        qt = item.get("question", "").strip()
        ro = item.get("options", {})
        ra = item.get("answer")
        if not qt or not ro or ra is None: continue
        ol = [f"{k}. {v}" for k, v in sorted(ro.items())]
        if t == "multi": ans = "|".join(sorted(str(a).strip().upper() for a in ra))
        elif isinstance(ra, list): ans = str(ra[0]).strip().upper()
        else: ans = str(ra).strip().upper()
        qs.append({"id": item.get("id", f"q{len(qs):04d}"), "type": t, "question": qt, "options": ol, "answer": ans})
    return qs

MODE_MAP = {"全部题目": "all", "仅单选题": "single", "仅多选题": "multi", "仅判断题": "judge", "仅错题": "wrong"}
TYPE_LABEL = {"single": "🔘 单选题", "multi": "☑️ 多选题", "judge": "⚖️ 判断题"}

def make_batch(mode):
    aq = st.session_state.all_questions
    pool = aq
    if mode == "single": pool = [q for q in aq if q["type"] == "single"]
    elif mode == "multi": pool = [q for q in aq if q["type"] == "multi"]
    elif mode == "judge": pool = [q for q in aq if q["type"] == "judge"]
    elif mode == "wrong": pool = [q for q in aq if q["id"] in st.session_state.incorrect_ids]
    if not pool: st.session_state.quiz_started = False; return
    if mode == "wrong":
        batch = pool.copy(); random.shuffle(batch)
    else:
        cs, ic = st.session_state.correct_ids, st.session_state.incorrect_ids
        batch = [q for q in pool if q["id"] in ic]
        cp = [q for q in pool if q["id"] in cs]
        if cp: batch.extend(random.sample(cp, min(20, len(cp))))
        unseen = [q for q in pool if q["id"] not in (cs | ic)]
        need = 100 - len(batch)
        if need > 0 and unseen: batch.extend(random.sample(unseen, min(need, len(unseen))))
        random.shuffle(batch)
    st.session_state.current_batch = batch
    st.session_state.current_idx = 0
    st.session_state.batch_answers = {}
    st.session_state.quiz_finished = False
    st.session_state.batch_id = random.randint(1, 1000000)

# ==================== 登录 ====================
def render_login():
    st.title("🔧 结构修理 刷题助手")
    mode = st.radio("登录方式", ["登录", "注册"], horizontal=True, key="auth_mode", label_visibility="collapsed")
    is_reg = (mode == "注册")
    with st.form("auth_form", clear_on_submit=False):
        email = st.text_input("邮箱", key="auth_email", placeholder="请输入邮箱地址")
        pw = st.text_input("密码", type="password", key="auth_password", placeholder="至少 6 位")
        c = st.text_input("确认密码", type="password", key="auth_confirm", placeholder="再次输入密码") if is_reg else ""
        btn = "📝 注 册" if is_reg else "🔑 登 录"
        if st.form_submit_button(btn, type="primary", use_container_width=True):
            if not email or not pw: st.error("请填写邮箱和密码"); return
            if "@" not in email or "." not in email.split("@")[-1]: st.error("请输入有效的邮箱地址"); return
            if is_reg:
                if c != pw: st.error("两次密码不一致"); return
                if len(pw) < 6: st.error("密码至少 6 位"); return
                r = _auth_post("signUp", {"email": email, "password": pw})
                if "idToken" not in r:
                    msg = r.get("error", {}).get("message", "")
                    st.error("该邮箱已被注册" if "EMAIL_EXISTS" in msg else f"注册失败: {msg}"); return
                st.session_state.user_email = email
                st.session_state.user_uid = r["localId"]
                st.session_state.logged_in = True
                st.session_state._id_token = r["idToken"]
                st.rerun()
            else:
                r = _auth_post("signInWithPassword", {"email": email, "password": pw})
                if "idToken" not in r:
                    msg = r.get("error", {}).get("message", "")
                    st.error("邮箱或密码错误" if "EMAIL_NOT_FOUND" in msg or "INVALID_PASSWORD" in msg else f"登录失败: {msg}"); return
                st.session_state.user_email = r["email"]
                st.session_state.user_uid = r["localId"]
                st.session_state.logged_in = True
                st.session_state._id_token = r["idToken"]
                load_data(r["localId"])
                st.rerun()

# ==================== 进度条组件 ====================
def _render_progress_bar(total):
    cn = len(st.session_state.correct_ids)
    in_ = len(st.session_state.incorrect_ids)
    ans = st.session_state.get("total_answers", cn + in_)
    total_ans = max(ans, cn + in_)
    pct = (cn / total * 100) if total > 0 else 0
    batch = st.session_state.get("current_batch", [])
    bidx = st.session_state.get("current_idx", 0)

    col_p, col_d = st.columns([6, 2])
    with col_p:
        st.progress(pct / 100)
    with col_d:
        pct_text = f"{pct:.0f}%" if pct >= 1 else (f"{pct:.1f}%" if pct > 0 else "0%")
        st.markdown(f"<div style='text-align:center;font-weight:700;color:#2e7d32;font-size:1.1rem;'>{pct_text}</div>", unsafe_allow_html=True)

    # 本轮进度
    if batch:
        b_pct = (bidx / len(batch) * 100) if len(batch) > 0 else 0
        completed = bidx
        st.caption(f"📖 本轮 {completed}/{len(batch)} 题")

# ==================== 侧边栏 ====================
def render_sidebar():
    uid = st.session_state.user_uid
    total = len(st.session_state.all_questions)
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.user_email}**")
        st.caption(st.session_state.get("fs_status", ""))

        if st.button("🚪 退出登录"):
            for k in ["logged_in", "user_email", "user_uid", "_id_token"]: st.session_state.pop(k, None)
            st.rerun()

        st.divider()

        sel = st.radio("选择练习模式", list(MODE_MAP), index=list(MODE_MAP).index(st.session_state.selected_mode_label), horizontal=True)
        if sel != st.session_state.selected_mode_label: st.session_state.selected_mode_label = sel

        sn = sum(1 for q in st.session_state.all_questions if q["type"] == "single")
        mn = sum(1 for q in st.session_state.all_questions if q["type"] == "multi")
        jn = sum(1 for q in st.session_state.all_questions if q["type"] == "judge")
        st.markdown(f"<div style='color:#2e7d32;font-size:.85rem;font-weight:600'>📚 题库共 {total} 题</div><div style='color:#6b7280;font-size:.78rem'>单选 {sn} · 多选 {mn} · 判断 {jn}</div>", unsafe_allow_html=True)

        if st.button("🚀 开始/重置练习", type="primary"):
            st.session_state.show_wrong = False
            st.session_state.batch_answers = {}
            st.session_state.quiz_finished = False
            st.session_state.quiz_started = True
            make_batch(MODE_MAP[st.session_state.selected_mode_label])

        # 侧边栏统计
        cn = len(st.session_state.correct_ids)
        in_ = len(st.session_state.incorrect_ids)
        ans = st.session_state.get("total_answers", cn + in_)
        total_ans = max(ans, cn + in_)
        acc = (cn / total_ans * 100) if total_ans > 0 else 0
        if total_ans > 0:
            st.divider()
            st.header("📊 统计")
            c1, c2 = st.columns(2)
            c1.metric("✅ 已掌握", cn)
            c2.metric("❌ 未掌握", in_)
            st.metric("🎯 正确率", f"{acc:.1f}%")

        st.divider()
        if st.button("📝 查看错题", type="primary", use_container_width=True):
            st.session_state.show_wrong = True; st.rerun()

        st.divider()
        with st.expander("⚠️ 高级", expanded=False):
            if st.button("🗑️ 清空所有学习数据"):
                clear_data(uid)
                st.session_state.correct_ids = set()
                st.session_state.incorrect_ids = set()
                st.session_state.error_counts = {}
                st.session_state.quiz_started = False
                st.session_state.total_answers = 0
                st.success("✅ 已清空！"); st.rerun()

# ==================== 错题 ====================
def render_wrong():
    if st.button("🔙 返回刷题", type="primary"):
        st.session_state.show_wrong = False; st.rerun()
    wr = sorted(
        [q for q in st.session_state.all_questions if q["id"] in st.session_state.error_counts],
        key=lambda q: st.session_state.error_counts[q["id"]], reverse=True)
    if not wr:
        st.markdown("<div style='text-align:center;padding:3rem;color:#2e7d32;font-size:1.1rem'>🎉 暂无错题，继续保持！</div>", unsafe_allow_html=True)
        return
    st.markdown(f"<div style='color:#2e7d32;font-weight:600;margin-bottom:.5rem'>📋 共 {len(wr)} 道错题（按错误次数降序）</div>", unsafe_allow_html=True)
    for q in wr:
        ec = st.session_state.error_counts[q["id"]]
        tlb = TYPE_LABEL.get(q["type"], "题目")
        cl = set(q["answer"].split("|"))
        co = [o for o in q["options"] if any(o.startswith(c) for c in cl)]
        st.markdown(f"<div style='background:#f8fafc;padding:.8rem 1rem;border-radius:.5rem;margin:.6rem 0;box-shadow:0 1px 3px rgba(0,0,0,.06);border-left:4px solid #ef4444'>", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#ef4444;font-weight:700'>✘ {ec} 次</span> &nbsp; <span style='font-size:.75rem;color:#6b7280'>{tlb}</span><br><span style='font-size:1rem;font-weight:600;color:#1f2937'>{q['question']}</span>", unsafe_allow_html=True)
        st.markdown(f"<p style='margin:.3rem 0 0 0;color:#065f46;font-size:.9rem'>✅ 答案：{', '.join(co)}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ==================== 答题 ====================
def _judge_result(q, ua):
    cl = set(q["answer"].split("|"))
    if q["type"] == "multi":
        return {a.split(".")[0].strip().upper() for a in ua} == cl, cl
    return (ua.split(".")[0].strip().upper() if ua else "") in cl, cl

def render_quiz():
    uid = st.session_state.user_uid
    total = len(st.session_state.all_questions)

    if not st.session_state.quiz_started:
        st.markdown("<div style='text-align:center;padding:3rem 1rem;color:#2e7d32;font-size:1.05rem'>👈 在左侧选择模式后，点击「开始/重置练习」</div>", unsafe_allow_html=True)
        _render_progress_bar(total)
        return

    if st.session_state.quiz_finished:
        _render_progress_bar(total)
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
        make_batch(MODE_MAP[st.session_state.selected_mode_label]); st.rerun()

    q = batch[idx]
    qid, qtype = q["id"], q["type"]
    done = qid in st.session_state.batch_answers

    _render_progress_bar(total)

    # 题号 + 题型
    c1, c2 = st.columns([3, 1])
    c1.subheader(f"第 {idx+1}/{len(batch)} 题")
    c2.markdown(f"<div style='text-align:right;padding:.3rem .8rem;background:#f1f5f9;border-radius:9999px;font-weight:600;font-size:.8rem;color:#3b82f6;margin-top:.5rem'>{TYPE_LABEL.get(qtype, '📋 题目')}</div>", unsafe_allow_html=True)

    random.seed(f"{st.session_state.get('batch_id',0)}_{qid}")
    shuffled = random.sample(q["options"], len(q["options"]))

    st.markdown(f"<div style='background:#f8fafc;padding:1rem;border-radius:.5rem;margin:.5rem 0;box-shadow:0 1px 3px rgba(0,0,0,.1)'><div style='font-size:1.1rem;font-weight:600;line-height:1.5'>{q['question']}</div></div>", unsafe_allow_html=True)

    if not done:
        with st.form("answer_form", clear_on_submit=True):
            if qtype == "multi":
                sel = []
                for i, opt in enumerate(shuffled):
                    if st.checkbox(opt, key=f"q_{qid}_{i}"): sel.append(opt)
            else:
                sel = st.radio("请选择", shuffled, key=f"q_{qid}", index=None, label_visibility="collapsed")

            if st.form_submit_button("✅ 提交答案", type="primary", use_container_width=True):
                if qtype == "multi" and not sel: st.warning("⚠️ 请至少选择一个选项"); return
                if qtype != "multi" and sel is None: st.warning("⚠️ 请选择一个选项"); return
                st.session_state.batch_answers[qid] = sel
                correct, cl = _judge_result(q, sel)
                if correct:
                    st.session_state.correct_ids.add(qid)
                    st.session_state.incorrect_ids.discard(qid)
                    st.session_state.error_counts.pop(qid, None)
                else:
                    st.session_state.incorrect_ids.add(qid)
                    st.session_state.correct_ids.discard(qid)
                    st.session_state.error_counts[qid] = st.session_state.error_counts.get(qid, 0) + 1
                st.session_state.total_answers = st.session_state.get("total_answers", 0) + 1
                save_data(uid)
                st.rerun()
    else:
        st.divider()
        ua = st.session_state.batch_answers[qid]
        correct, cl = _judge_result(q, ua)

        if correct:
            st.markdown("<div style='background:#d1fae5;padding:.4rem 1rem;border-radius:9999px;text-align:center;border:1px solid #10b981;margin:.3rem 0'><span style='color:#065f46;font-weight:600'>🎉 回答正确！</span></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='background:#fee2e2;padding:.4rem 1rem;border-radius:9999px;text-align:center;border:1px solid #ef4444;margin:.3rem 0'><span style='color:#991b1b;font-weight:600'>❌ 回答错误</span></div>", unsafe_allow_html=True)

        st.markdown("<h4 style='margin-top:.75rem'>📋 所有选项：</h4>", unsafe_allow_html=True)
        for opt in shuffled:
            letter = opt.split(".")[0].strip().upper()
            ic = letter in cl
            is_ = opt in ua if qtype == "multi" else opt == ua
            fb = "✅ " if ic else ("❌ " if is_ and not ic else "")
            bg = "background:#d1fae5;" if ic else "background:#fff;"
            bd = "border:2px solid #10b981;" if ic else "border:2px solid #e5e7eb;"
            color = "color:#065f46;" if ic else "color:#1f2937;"
            st.markdown(f"<div style='{bg}{bd}{color}padding:.5rem;margin-bottom:.3rem;border-radius:.375rem;font-size:1rem'>{fb}{opt}</div>", unsafe_allow_html=True)

        corr = [o for o in q["options"] if any(o.startswith(c) for c in cl)]
        st.markdown(f"<div style='margin-top:.75rem;padding:.75rem;background:#f9fafb;border-radius:.5rem'><h4 style='margin:0 0 .3rem;color:#374151'>💡 正确答案：</h4><p style='font-size:1rem;color:#065f46;margin:0;padding:.5rem;background:#d1fae5;border-radius:.375rem;border-left:4px solid #10b981'><strong>{', '.join(corr)}</strong></p></div>", unsafe_allow_html=True)

        if st.button("➡️ 下一题", type="primary", use_container_width=True):
            st.session_state.current_idx += 1; st.rerun()

# ==================== 主程序 ====================
def main():
    if not st.session_state.get("logged_in"):
        if "all_questions" not in st.session_state: st.session_state.all_questions = load_questions(BANK_PATH)
        render_login()
        return

    if "all_questions" not in st.session_state: st.session_state.all_questions = load_questions(BANK_PATH)
    if "selected_mode_label" not in st.session_state: st.session_state.selected_mode_label = "全部题目"
    if "correct_ids" not in st.session_state:
        st.session_state.correct_ids = set()
        st.session_state.incorrect_ids = set()
        st.session_state.error_counts = {}
        st.session_state.total_answers = 0
    if "quiz_started" not in st.session_state: st.session_state.quiz_started = False
    if "total_answers" not in st.session_state: st.session_state.total_answers = 0

    st.title("🔧 结构修理 刷题助手")
    st.divider()
    render_sidebar()
    if st.session_state.get("show_wrong"):
        render_wrong()
    else:
        render_quiz()

if __name__ == "__main__":
    main()
