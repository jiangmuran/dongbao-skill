"""
冬宝在线对话 — FastAPI + 内嵌前端 + 管理后台
启动: python app.py
对话: http://localhost:8000
后台: http://localhost:8000/admin
"""

import json
import time
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from openai import AsyncOpenAI

# ── 配置 ────────────────────────────────────────────────────────
SKILL_PATH = Path(__file__).parent / "dongbao.md"
SYSTEM_PROMPT = SKILL_PATH.read_text(encoding="utf-8")
DB_PATH = Path(__file__).parent / "dongbao.db"

client = AsyncOpenAI(
    api_key="sk-cs8dzgvixriajubewnkpaq7vhmobkxunxndnoy0w93q3t6jj",
    base_url="https://api.xiaomimimo.com/v1",
)
MODEL = "mimo-v2-flash"
MAX_HISTORY = 20

# ── 数据库 ──────────────────────────────────────────────────────
db_lock = threading.Lock()

def init_db():
    with sqlite3.connect(str(DB_PATH)) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, ip TEXT, nickname TEXT,
            prompt TEXT, response TEXT,
            prompt_tokens INTEGER, completion_tokens INTEGER,
            duration_ms INTEGER, feedback TEXT DEFAULT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS stats (
            date TEXT PRIMARY KEY,
            chats INTEGER DEFAULT 0,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0
        )""")
        # migrate: add feedback column if missing
        try:
            c.execute("ALTER TABLE logs ADD COLUMN feedback TEXT DEFAULT NULL")
        except Exception:
            pass

init_db()

def log_chat(ip, nickname, prompt, response, pt, ct, dur):
    with db_lock, sqlite3.connect(str(DB_PATH)) as c:
        cur = c.execute("INSERT INTO logs (ts,ip,nickname,prompt,response,prompt_tokens,completion_tokens,duration_ms) VALUES (?,?,?,?,?,?,?,?)",
                  (time.time(), ip, nickname, prompt, response, pt, ct, dur))
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute("INSERT INTO stats (date,chats,tokens_in,tokens_out) VALUES (?,1,?,?) ON CONFLICT(date) DO UPDATE SET chats=chats+1, tokens_in=tokens_in+?, tokens_out=tokens_out+?",
                  (today, pt, ct, pt, ct))
        return cur.lastrowid

app = FastAPI()

# ── SSE 流式聊天 ────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    user_msgs = body.get("messages", [])[-MAX_HISTORY:]
    nickname = body.get("nickname", "朋友")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()

    enhanced_prompt = SYSTEM_PROMPT + f"""

---
## 当前对话设定

和你聊天的人叫「{nickname}」，可以自然地用名字称呼对方。

## 关键输出规则（必须严格遵守）

1. **像微信聊天一样，每条消息只说1-2句话**。冬宝原始聊天记录里，一条消息极少超过2行。
2. **多条短消息 > 一条长消息**。如果要说的内容多，拆成多个自然段，用换行分开，模拟连续发多条微信的感觉。
3. **绝对不要一次输出超过5行**。宁可少说，也别啰嗦。
4. **口语化到极致**：不要用"首先、其次、此外"这种结构化表达。不要用书面语。
5. **短句为王**：冬宝说话节奏快，"牛逼"、"帅"、"哈哈哈哈哈"、"马上"、"别怕"是高频词。
6. **稳重但不古板**：冬宝虽然活泼，但做事靠谱，说话有分寸。不会每句话都带哈哈哈，会在关键问题上给出有见地的回答。
7. **不要自我介绍太多**：除非被问到，否则不要主动说自己是谁、做什么的。直接聊天。
"""

    messages = [{"role": "system", "content": enhanced_prompt}] + user_msgs
    t0 = time.time()
    full_response = ""
    prompt_text = user_msgs[-1]["content"] if user_msgs else ""

    async def generate():
        nonlocal full_response
        try:
            stream = await client.chat.completions.create(
                model=MODEL, messages=messages, stream=True,
                temperature=0.85, top_p=0.9,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    c = chunk.choices[0].delta.content
                    full_response += c
                    yield f"data: {json.dumps({'content': c})}\n\n"
            # log before DONE so frontend gets log_id
            dur = int((time.time() - t0) * 1000)
            pt = len(enhanced_prompt + prompt_text) // 2
            ct = len(full_response) // 2
            try:
                lid = log_chat(ip, nickname, prompt_text, full_response, pt, ct, dur)
                if lid:
                    yield f"data: {json.dumps({'log_id': lid})}\n\n"
            except Exception:
                pass
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

# ── 管理后台 API ────────────────────────────────────────────────
@app.get("/api/admin/overview")
async def admin_overview():
    with sqlite3.connect(str(DB_PATH)) as c:
        c.row_factory = sqlite3.Row
        total = c.execute("SELECT COUNT(*) as n, COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct FROM logs").fetchone()
        today_str = datetime.now().strftime("%Y-%m-%d")
        today = c.execute("SELECT * FROM stats WHERE date=?", (today_str,)).fetchone()
        unique_ips = c.execute("SELECT COUNT(DISTINCT ip) as n FROM logs").fetchone()["n"]
        likes = c.execute("SELECT COUNT(*) as n FROM logs WHERE feedback='up'").fetchone()["n"]
        dislikes = c.execute("SELECT COUNT(*) as n FROM logs WHERE feedback='down'").fetchone()["n"]
        # 7 days trend
        days = []
        for i in range(6, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            row = c.execute("SELECT * FROM stats WHERE date=?", (d,)).fetchone()
            days.append({"date": d, "chats": row["chats"] if row else 0, "tokens": (row["tokens_in"] or 0) + (row["tokens_out"] or 0) if row else 0})
    return {
        "total_chats": total["n"],
        "total_tokens_in": total["pt"],
        "total_tokens_out": total["ct"],
        "today_chats": today["chats"] if today else 0,
        "unique_users": unique_ips,
        "likes": likes,
        "dislikes": dislikes,
        "trend": days,
    }

@app.post("/api/feedback")
async def feedback(request: Request):
    body = await request.json()
    log_id = body.get("id")
    vote = body.get("vote")  # "up" or "down"
    if not log_id or vote not in ("up", "down"):
        return JSONResponse({"ok": False}, status_code=400)
    with db_lock, sqlite3.connect(str(DB_PATH)) as c:
        c.execute("UPDATE logs SET feedback=? WHERE id=?", (vote, log_id))
    return {"ok": True}

@app.get("/api/admin/recent")
async def admin_recent():
    with sqlite3.connect(str(DB_PATH)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 30").fetchall()
    return [dict(r) for r in rows]

# ── 前端页面 ────────────────────────────────────────────────────
CHAT_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#ffffff">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>和冬宝聊天</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--red:#FF4757;--grad:linear-gradient(135deg,#FF6348,#FF4757);--c1:#1A1A1A;--c2:#666;--c3:#999;
--ff:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
--safe-t:env(safe-area-inset-top,0px);--safe-b:env(safe-area-inset-bottom,0px)}
html,body{height:100%;overflow:hidden;font-family:var(--ff);-webkit-font-smoothing:antialiased;-webkit-tap-highlight-color:transparent;background:#E8E8ED}
#app{display:flex;flex-direction:column;height:100vh;height:100dvh;max-width:430px;margin:0 auto;background:linear-gradient(180deg,#FFF8F6 0%,#FFF5EE 30%,#F8F4FF 100%);overflow:hidden}

/* header */
.hd{flex-shrink:0;padding:calc(var(--safe-t) + 12px) 16px 12px;background:#fff;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:12px;z-index:10}
.hd-av{width:42px;height:42px;border-radius:12px;background:var(--grad);display:flex;align-items:center;justify-content:center;font-size:19px;font-weight:800;color:#fff;flex-shrink:0}
.hd-info{flex:1}.hd-name{font-size:16px;font-weight:700;color:var(--c1)}
.hd-sub{font-size:11px;color:#34C759;display:flex;align-items:center;gap:4px;margin-top:1px}
.hd-sub::before{content:'';width:6px;height:6px;background:#34C759;border-radius:50%}
.hd-btns{display:flex;gap:6px}
.hd-btn{width:34px;height:34px;border:none;background:#F5F5F5;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--c3);transition:all .15s}
.hd-btn:active{transform:scale(.9);background:#eee}
.hd-btn svg{width:16px;height:16px}

/* messages */
#msgs{flex:1;min-height:0;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:12px 14px 8px}
#msgs::-webkit-scrollbar{display:none}

/* welcome */
.hi{padding:12px 0 4px}
.hi-row{display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;animation:up .4s ease both}
.hi-row:nth-child(2){animation-delay:.12s}.hi-row:nth-child(3){animation-delay:.24s}
.hi-av{width:28px;height:28px;border-radius:50%;background:var(--grad);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:#fff;flex-shrink:0;margin-top:2px}
.hi-bub{background:#fff;padding:10px 14px;border-radius:2px 18px 18px 18px;font-size:15px;line-height:1.5;color:var(--c1);box-shadow:0 1px 2px rgba(0,0,0,.05);max-width:80%}
.hi-tags{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px;padding-left:36px}
.hi-tag{font-size:13px;padding:8px 16px;background:#fff;color:var(--red);border:1.5px solid #FFE8EA;border-radius:20px;cursor:pointer;font-family:var(--ff);transition:all .2s;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.hi-tag:active{background:var(--red);color:#fff;border-color:var(--red);transform:scale(.96)}
@keyframes up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

/* msg rows */
.mr{display:flex;margin-top:10px;animation:up .3s ease both}
.mr.u{justify-content:flex-end}
.bu{background:var(--grad);color:#fff;border-radius:18px 18px 4px 18px;padding:10px 14px;max-width:75%;font-size:15px;line-height:1.55;word-break:break-word;white-space:pre-wrap;box-shadow:0 2px 8px rgba(255,71,87,.18)}
.mr.b{gap:8px;align-items:flex-start}
.b-av{width:28px;height:28px;border-radius:50%;background:var(--grad);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:#fff;flex-shrink:0;margin-top:2px}
.bb{background:#fff;color:var(--c1);border-radius:2px 18px 18px 18px;padding:10px 14px;max-width:75%;font-size:15px;line-height:1.55;word-break:break-word;white-space:pre-wrap;box-shadow:0 1px 2px rgba(0,0,0,.05)}

/* typing */
.tp{display:flex;gap:8px;align-items:flex-start;margin-top:10px;animation:up .2s ease both}
.tp-dots{display:flex;gap:4px;padding:12px 16px;background:#fff;border-radius:2px 18px 18px 18px;box-shadow:0 1px 2px rgba(0,0,0,.05)}
.tp-dots i{width:7px;height:7px;background:#ccc;border-radius:50%;display:block;animation:dot 1.4s ease-in-out infinite}
.tp-dots i:nth-child(2){animation-delay:.15s}.tp-dots i:nth-child(3){animation-delay:.3s}
@keyframes dot{0%,60%,100%{transform:translateY(0);opacity:.35}30%{transform:translateY(-6px);opacity:1}}
.be{background:#FFF3F3;color:#C62828;border-radius:2px 18px 18px 18px;padding:10px 14px;max-width:75%;font-size:14px}
.bb-wrap{max-width:75%}
.fb{display:flex;gap:4px;margin-top:4px;padding-left:2px}
.fb-btn{background:none;border:none;font-size:14px;cursor:pointer;padding:2px 6px;border-radius:8px;transition:all .15s;opacity:.4}
.fb-btn:hover{opacity:.7;background:rgba(0,0,0,.04)}
.fb-btn:active{transform:scale(.9)}

/* input */
.ft{flex-shrink:0;padding:8px 12px calc(var(--safe-b) + 8px);background:#fff;border-top:1px solid #f0f0f0;z-index:10}
.iw{display:flex;align-items:flex-end;background:#F5F5F5;border-radius:22px;padding:6px 6px 6px 16px;transition:box-shadow .2s}
.iw:focus-within{box-shadow:0 0 0 2px rgba(255,71,87,.15)}
#inp{flex:1;border:none;outline:none;resize:none;font-family:var(--ff);font-size:15px;line-height:1.45;max-height:100px;background:transparent;color:var(--c1);padding:4px 0}
#inp::placeholder{color:#bbb}
#send{width:32px;height:32px;flex-shrink:0;border:none;border-radius:50%;background:#ddd;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .15s}
#send.on{background:var(--grad);box-shadow:0 2px 6px rgba(255,71,87,.3)}
#send:active{transform:scale(.88)}
#send svg{width:16px;height:16px}

/* modal */
.modal-bg{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;padding:24px;animation:fadeIn .2s ease}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.modal{background:#fff;border-radius:20px;padding:28px 24px;max-width:320px;width:100%;text-align:center;animation:pop .3s cubic-bezier(.16,1,.3,1)}
@keyframes pop{from{transform:scale(.9);opacity:0}to{transform:none;opacity:1}}
.modal h2{font-size:20px;font-weight:700;margin-bottom:6px;color:var(--c1)}
.modal p{font-size:14px;color:var(--c2);margin-bottom:20px;line-height:1.5}
.modal input{width:100%;padding:12px 16px;border:2px solid #f0f0f0;border-radius:14px;font-size:16px;font-family:var(--ff);outline:none;text-align:center;transition:border-color .2s}
.modal input:focus{border-color:var(--red)}
.modal button{margin-top:16px;width:100%;padding:14px;border:none;border-radius:14px;background:var(--grad);color:#fff;font-size:16px;font-weight:600;cursor:pointer;font-family:var(--ff);transition:transform .15s}
.modal button:active{transform:scale(.96)}

/* share */
.sheet-bg{position:fixed;inset:0;z-index:100;background:rgba(0,0,0,.35);display:none;align-items:flex-end;justify-content:center}
.sheet-bg.on{display:flex;animation:fadeIn .2s ease}
.sheet{background:#fff;border-radius:20px 20px 0 0;width:100%;max-width:430px;padding:20px 16px calc(var(--safe-b) + 16px);animation:shUp .3s cubic-bezier(.16,1,.3,1)}
@keyframes shUp{from{transform:translateY(100%)}to{transform:none}}
.sheet canvas{width:100%;border-radius:12px;border:1px solid #f0f0f0}
.sheet-row{display:flex;gap:10px;margin-top:16px}
.sheet-row button{flex:1;padding:14px;border:none;border-radius:14px;font-family:var(--ff);font-size:15px;font-weight:600;cursor:pointer;transition:transform .15s}
.sheet-row button:active{transform:scale(.96)}
.s-main{background:var(--grad);color:#fff}
.s-sec{background:#F5F5F5;color:var(--c2)}

@media(min-width:431px){
  body{display:flex;align-items:center;justify-content:center}
  #app{border-radius:20px;box-shadow:0 12px 40px rgba(0,0,0,.12);height:min(90vh,820px)}
  .hd{border-radius:20px 20px 0 0}
}
</style>
</head>
<body>
<div id="app">
  <div class="hd">
    <div class="hd-av">冬</div>
    <div class="hd-info"><div class="hd-name">冬宝</div><div class="hd-sub" id="status">在线</div></div>
    <div class="hd-btns">
      <button class="hd-btn" id="btn-new" title="新对话"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></button>
      <button class="hd-btn" id="btn-share" title="分享"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></button>
    </div>
  </div>
  <div id="msgs">
    <div class="hi" id="welcome">
      <div class="hi-row"><div class="hi-av">冬</div><div class="hi-bub">嘿！你好呀 👋</div></div>
      <div class="hi-row"><div class="hi-av">冬</div><div class="hi-bub">我是冬宝，小红书搞黑客松的那个</div></div>
      <div class="hi-row"><div class="hi-av">冬</div><div class="hi-bub">有啥想聊的直接说！别怕 哈哈哈哈哈</div></div>
      <div class="hi-tags">
        <button class="hi-tag" data-q="你是谁呀？">你是谁呀？</button>
        <button class="hi-tag" data-q="黑巅有多帅？给我讲讲">黑巅有多帅？</button>
        <button class="hi-tag" data-q="冬宝给我讲个故事吧">讲个故事</button>
      </div>
    </div>
  </div>
  <div class="ft">
    <div class="iw">
      <textarea id="inp" placeholder="说点什么..." rows="1"></textarea>
      <button id="send"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M3.4 20.4l17.45-7.48a1 1 0 000-1.84L3.4 3.6a.993.993 0 00-1.39.91L2 9.12c0 .5.37.93.87.99L17 12 2.87 13.88c-.5.07-.87.5-.87 1l.01 4.61c0 .71.73 1.2 1.39.91z"/></svg></button>
    </div>
  </div>
</div>

<div class="sheet-bg" id="sheet-bg">
  <div class="sheet"><canvas id="share-cvs"></canvas>
    <div class="sheet-row">
      <button class="s-main" id="s-save">保存图片</button>
      <button class="s-main" id="s-share">分享</button>
      <button class="s-sec" id="s-close">取消</button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
(()=>{
const $=s=>document.querySelector(s);
const msgs$=$('#msgs'),inp$=$('#inp'),send$=$('#send'),status$=$('#status');
let hist=[],busy=false,ctrl=null;
let nickname=localStorage.getItem('db_nick')||'';

// ── nickname modal ──
if(!nickname){
  const bg=document.createElement('div');bg.className='modal-bg';
  bg.innerHTML=`<div class="modal"><h2>👋 你好呀</h2><p>告诉冬宝怎么称呼你吧</p><input id="nick-inp" placeholder="你的名字" maxlength="20" autofocus><button id="nick-ok">开始聊天</button></div>`;
  document.body.appendChild(bg);
  const ni=bg.querySelector('#nick-inp');
  bg.querySelector('#nick-ok').onclick=()=>{
    nickname=ni.value.trim()||'朋友';
    localStorage.setItem('db_nick',nickname);
    bg.remove();
    inp$.focus();
  };
  ni.addEventListener('keydown',e=>{if(e.key==='Enter'){bg.querySelector('#nick-ok').click()}});
  setTimeout(()=>ni.focus(),100);
}

// ── tags ──
function bindTags(el){el.querySelectorAll('.hi-tag').forEach(t=>t.onclick=()=>{if(busy)return;inp$.value=t.dataset.q;updateBtn();go()})}
bindTags(document);

// ── input ──
inp$.addEventListener('input',()=>{rsz();updateBtn()});
inp$.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();go()}});
inp$.addEventListener('focus',()=>setTimeout(scrollEnd,300));
send$.onclick=go;
function rsz(){inp$.style.height='auto';inp$.style.height=Math.min(inp$.scrollHeight,100)+'px'}
function updateBtn(){send$.classList.toggle('on',!!inp$.value.trim())}
function scrollEnd(){const el=msgs$.lastElementChild;if(el)el.scrollIntoView({behavior:'smooth',block:'end'})}

function mkUser(t){const d=document.createElement('div');d.className='mr u';const b=document.createElement('div');b.className='bu';b.textContent=t;d.appendChild(b);msgs$.appendChild(d);scrollEnd()}
function mkBot(){const d=document.createElement('div');d.className='mr b';d.innerHTML='<div class="b-av">冬</div><div class="bb-wrap"><div class="bb"></div><div class="fb" style="display:none"><button class="fb-btn" data-v="up" title="好评">👍</button><button class="fb-btn" data-v="down" title="差评">👎</button></div></div>';msgs$.appendChild(d);return {el:d.querySelector('.bb'),wrap:d}}
function mkTyping(){const d=document.createElement('div');d.className='tp';d.id='tp';d.innerHTML='<div class="b-av">冬</div><div class="tp-dots"><i></i><i></i><i></i></div>';msgs$.appendChild(d);scrollEnd()}
function rmTyping(){const e=$('#tp');if(e)e.remove()}
function mkErr(m){const d=document.createElement('div');d.className='mr b';d.innerHTML='<div class="b-av">冬</div><div class="be"></div>';d.querySelector('.be').textContent=m;msgs$.appendChild(d);scrollEnd()}

async function go(){
  const t=inp$.value.trim();if(!t||busy)return;
  busy=true;inp$.value='';rsz();updateBtn();
  hist.push({role:'user',content:t});mkUser(t);
  const w=$('#welcome');if(w)w.style.display='none';
  status$.textContent='冬宝正在输入...';mkTyping();
  try{
    ctrl=new AbortController();
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:hist,nickname}),signal:ctrl.signal});
    rmTyping();if(!r.ok)throw new Error(r.status);
    const rd=r.body.getReader(),dc=new TextDecoder();
    const bot=mkBot();let buf='',full='',logId=null;
    while(true){const{done,value}=await rd.read();if(done)break;
      buf+=dc.decode(value,{stream:true});const ps=buf.split('\n\n');buf=ps.pop();
      for(const p of ps){if(!p.startsWith('data: '))continue;const d=p.slice(6);if(d==='[DONE]')break;
        try{const j=JSON.parse(d);if(j.error){mkErr(j.error);busy=false;status$.textContent='在线';return}
        if(j.content){full+=j.content;bot.el.textContent=full;scrollEnd()}
        if(j.log_id)logId=j.log_id}catch{}}
    }
    if(full){hist.push({role:'assistant',content:full});
      if(logId){const fb=bot.wrap.querySelector('.fb');fb.style.display='';fb.querySelectorAll('.fb-btn').forEach(b=>b.onclick=async()=>{
        fb.querySelectorAll('.fb-btn').forEach(x=>x.style.opacity='.3');b.style.opacity='1';
        await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:logId,vote:b.dataset.v})})})}};
  }catch(e){rmTyping();if(e.name!=='AbortError')mkErr('网络断了 再试试？')}
  finally{busy=false;ctrl=null;status$.textContent='在线';updateBtn()}
}

$('#btn-new').onclick=()=>{if(busy)return;hist=[];msgs$.innerHTML='';
  const hi=document.createElement('div');hi.className='hi';hi.id='welcome';
  hi.innerHTML=`<div class="hi-row"><div class="hi-av">冬</div><div class="hi-bub">嘿！你好呀 👋</div></div><div class="hi-row"><div class="hi-av">冬</div><div class="hi-bub">我是冬宝，小红书搞黑客松的那个</div></div><div class="hi-row"><div class="hi-av">冬</div><div class="hi-bub">有啥想聊的直接说！别怕 哈哈哈哈哈</div></div><div class="hi-tags"><button class="hi-tag" data-q="你是谁呀？">你是谁呀？</button><button class="hi-tag" data-q="黑巅有多帅？给我讲讲">黑巅有多帅？</button><button class="hi-tag" data-q="冬宝给我讲个故事吧">讲个故事</button></div>`;
  msgs$.appendChild(hi);bindTags(hi)};

const sheetBg=$('#sheet-bg');
$('#btn-share').onclick=async()=>{if(!hist.length)return;sheetBg.classList.add('on');
  const clone=msgs$.cloneNode(true);clone.style.cssText='position:absolute;left:-9999px;width:375px;padding:16px;background:linear-gradient(180deg,#FFF8F6,#FFF5EE,#F8F4FF);overflow:visible;height:auto';
  const ww=clone.querySelector('.hi');if(ww)ww.remove();document.body.appendChild(clone);
  try{const c=await html2canvas(clone,{backgroundColor:null,scale:2});document.body.removeChild(clone);
    const W=c.width,H=c.height,pad=48,hH=90,fH=70;const out=document.createElement('canvas');
    out.width=W+pad*2;out.height=H+hH+fH+pad;const x=out.getContext('2d');
    const g=x.createLinearGradient(0,0,0,out.height);g.addColorStop(0,'#FFF8F6');g.addColorStop(.5,'#FFF5EE');g.addColorStop(1,'#F8F4FF');
    x.fillStyle=g;x.fillRect(0,0,out.width,out.height);x.fillStyle='#FF4757';x.font='bold 32px -apple-system,sans-serif';
    x.fillText('和冬宝的对话',pad,hH-10);x.drawImage(c,pad,hH);x.fillStyle='#bbb';x.font='20px -apple-system,sans-serif';
    x.fillText('冬宝.skill · jiangmuran.com',pad,hH+H+fH-10);
    const cv$=$('#share-cvs');cv$.width=out.width;cv$.height=out.height;cv$.getContext('2d').drawImage(out,0,0);
    $('#s-save').onclick=()=>{const a=document.createElement('a');a.href=out.toDataURL('image/png');a.download='dongbao-chat.png';a.click()};
    $('#s-share').onclick=async()=>{try{const blob=await new Promise(r=>out.toBlob(r,'image/png'));const f=new File([blob],'dongbao-chat.png',{type:'image/png'});
      if(navigator.canShare?.({files:[f]}))await navigator.share({files:[f]});else{await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);alert('已复制')}}catch{alert('试试保存图片')}};
  }catch(e){document.body.removeChild(clone)}};
$('#s-close').onclick=()=>sheetBg.classList.remove('on');
sheetBg.onclick=e=>{if(e.target===sheetBg)sheetBg.classList.remove('on')};
msgs$.addEventListener('contextmenu',e=>{const bub=e.target.closest('.bu,.bb');if(bub){e.preventDefault();navigator.clipboard.writeText(bub.textContent).then(()=>{bub.style.opacity='.5';setTimeout(()=>bub.style.opacity='1',200)})}});
})();
</script>
</body>
</html>"""

# ── 管理后台页面 ────────────────────────────────────────────────
ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>冬宝后台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--red:#FF4757;--grad:linear-gradient(135deg,#FF6348,#FF4757);--ff:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}
body{font-family:var(--ff);background:#F5F5F7;color:#1a1a1a;-webkit-font-smoothing:antialiased;padding:0 0 40px}
.top{background:var(--grad);color:#fff;padding:32px 20px 24px;text-align:center}
.top h1{font-size:22px;font-weight:700}.top p{font-size:13px;opacity:.8;margin-top:4px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;padding:16px;margin-top:-20px}
.card{background:#fff;border-radius:16px;padding:20px 16px;box-shadow:0 2px 8px rgba(0,0,0,.06);text-align:center}
.card .num{font-size:28px;font-weight:800;color:var(--red);margin-bottom:4px}
.card .lbl{font-size:12px;color:#999}
.section{padding:0 16px;margin-top:20px}
.section h2{font-size:16px;font-weight:700;margin-bottom:12px;color:#333}
.chart{background:#fff;border-radius:16px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.06);height:200px;position:relative}
.bars{display:flex;align-items:flex-end;justify-content:space-between;height:150px;gap:8px;padding-top:10px}
.bar-col{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px}
.bar{width:100%;border-radius:6px 6px 0 0;background:var(--grad);min-height:2px;transition:height .5s ease}
.bar-lbl{font-size:10px;color:#999}
.bar-val{font-size:11px;font-weight:600;color:var(--red)}
table{width:100%;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06);border-collapse:collapse}
th{background:#FAFAFA;font-size:12px;font-weight:600;color:#666;padding:12px 10px;text-align:left;border-bottom:1px solid #f0f0f0}
td{font-size:13px;padding:10px;border-bottom:1px solid #f5f5f5;color:#333;vertical-align:top;max-width:200px;word-break:break-all}
tr:last-child td{border:none}
.ip{color:#999;font-size:11px}.nick{color:var(--red);font-weight:600}
.prompt-text{max-height:60px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
.refresh{display:block;margin:20px auto 0;padding:12px 32px;border:none;border-radius:12px;background:var(--grad);color:#fff;font-size:15px;font-weight:600;cursor:pointer;font-family:var(--ff)}
.refresh:active{transform:scale(.96)}
@media(max-width:500px){.cards{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="top"><h1>🧸 冬宝后台</h1><p>对话数据一览</p></div>
<div class="cards" id="cards"></div>
<div class="section"><h2>📊 7日趋势</h2><div class="chart"><div class="bars" id="bars"></div></div></div>
<div class="section" style="margin-top:20px"><h2>💬 最近对话</h2><table><thead><tr><th>时间</th><th>用户</th><th>内容</th></tr></thead><tbody id="rows"></tbody></table></div>
<button class="refresh" onclick="load()">刷新数据</button>
<script>
async function load(){
  const [ov,rc]=await Promise.all([fetch('/api/admin/overview').then(r=>r.json()),fetch('/api/admin/recent').then(r=>r.json())]);
  // cards
  document.getElementById('cards').innerHTML=`
    <div class="card"><div class="num">${ov.today_chats}</div><div class="lbl">今日对话</div></div>
    <div class="card"><div class="num">${ov.total_chats}</div><div class="lbl">总对话数</div></div>
    <div class="card"><div class="num">${ov.unique_users}</div><div class="lbl">独立用户</div></div>
    <div class="card"><div class="num">${((ov.total_tokens_in+ov.total_tokens_out)/1000).toFixed(1)}k</div><div class="lbl">总Token</div></div>
    <div class="card"><div class="num">${(ov.total_tokens_in/1000).toFixed(1)}k</div><div class="lbl">输入Token</div></div>
    <div class="card"><div class="num">${(ov.total_tokens_out/1000).toFixed(1)}k</div><div class="lbl">输出Token</div></div>
    <div class="card"><div class="num">👍${ov.likes} 👎${ov.dislikes}</div><div class="lbl">用户反馈</div></div>`;
  // chart
  const mx=Math.max(...ov.trend.map(d=>d.chats),1);
  document.getElementById('bars').innerHTML=ov.trend.map(d=>`<div class="bar-col"><div class="bar-val">${d.chats}</div><div class="bar" style="height:${(d.chats/mx)*130}px"></div><div class="bar-lbl">${d.date.slice(5)}</div></div>`).join('');
  // table
  document.getElementById('rows').innerHTML=rc.map(r=>{
    const t=new Date(r.ts*1000);
    const ts=`${(t.getMonth()+1).toString().padStart(2,'0')}-${t.getDate().toString().padStart(2,'0')} ${t.getHours().toString().padStart(2,'0')}:${t.getMinutes().toString().padStart(2,'0')}`;
    return `<tr><td>${ts}<br><span class="ip">${r.ip}</span></td><td><span class="nick">${r.nickname||'匿名'}</span></td><td><div class="prompt-text">${esc(r.prompt)}</div></td></tr>`}).join('');
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
load();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return CHAT_HTML

@app.get("/admin", response_class=HTMLResponse)
async def admin():
    return ADMIN_HTML

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
