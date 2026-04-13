"""
冬宝在线对话 — FastAPI + 内嵌前端 + 管理后台
启动: python app.py
对话: http://localhost:8000
后台: http://localhost:8000/admin (密码鉴权)
"""
import json, time, sqlite3, threading, hashlib
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from openai import AsyncOpenAI

# ── config ──
SKILL_PATH = Path(__file__).parent / "dongbao.md"
SYSTEM_PROMPT = SKILL_PATH.read_text(encoding="utf-8")
DB_PATH = Path(__file__).parent / "dongbao.db"
ADMIN_HASH = "a776a66c6d2846ba069697bb56f68fedfe301a453126cf4af1d566296cd8ae903b591520c4fbb51592f1fa206b7a4c3baeb79a3dde67167a108b885835813cba"

client = AsyncOpenAI(api_key="sk-cs8dzgvixriajubewnkpaq7vhmobkxunxndnoy0w93q3t6jj", base_url="https://api.xiaomimimo.com/v1")
MODEL = "mimo-v2-flash"
MAX_HISTORY = 20
AVATAR_B64 = "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"

db_lock = threading.Lock()
def init_db():
    with sqlite3.connect(str(DB_PATH)) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, ip TEXT, nickname TEXT,
            prompt TEXT, response TEXT, prompt_tokens INTEGER, completion_tokens INTEGER,
            duration_ms INTEGER, feedback TEXT DEFAULT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS stats (
            date TEXT PRIMARY KEY, chats INTEGER DEFAULT 0, tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0)""")
        try: c.execute("ALTER TABLE logs ADD COLUMN feedback TEXT DEFAULT NULL")
        except: pass
init_db()

def log_chat(ip, nick, prompt, resp, pt, ct, dur):
    with db_lock, sqlite3.connect(str(DB_PATH)) as c:
        cur = c.execute("INSERT INTO logs (ts,ip,nickname,prompt,response,prompt_tokens,completion_tokens,duration_ms) VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), ip, nick, prompt, resp, pt, ct, dur))
        d = datetime.now().strftime("%Y-%m-%d")
        c.execute("INSERT INTO stats (date,chats,tokens_in,tokens_out) VALUES (?,1,?,?) ON CONFLICT(date) DO UPDATE SET chats=chats+1,tokens_in=tokens_in+?,tokens_out=tokens_out+?", (d,pt,ct,pt,ct))
        return cur.lastrowid

app = FastAPI()

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    user_msgs = body.get("messages", [])[-MAX_HISTORY:]
    nick = body.get("nickname", "朋友")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    sp = SYSTEM_PROMPT + f"""

---
当前聊天对象：「{nick}」。可以自然地用名字称呼。

## 输出格式硬规则

你现在是在微信里和朋友聊天。严格遵守：

1. 每次回复只说1-3个短句，每句不超过一行。句与句之间用换行分开。
2. 绝对禁止超过5行。宁可漏说也别啰嗦。
3. 禁止使用"首先/其次/此外/总之"等结构化词汇。禁止分点列举。
4. 禁止重复自我介绍。除非被直接问到身份，否则直接聊天。
5. 说话要有实质内容，不要说"有什么可以帮你的吗"这种客服模板话。
6. 用口语：牛逼、帅、搞、整、别怕、马上。笑声至少5个"哈"。
7. 回复要针对对方说的内容，不要答非所问。认真看对方的消息再回。
8. 如果不确定对方在说什么，直接问"啥意思"或"没太懂"，别硬编回复。
"""
    messages = [{"role": "system", "content": sp}] + user_msgs
    t0 = time.time()
    full = ""
    ptxt = user_msgs[-1]["content"] if user_msgs else ""

    async def gen():
        nonlocal full
        try:
            stream = await client.chat.completions.create(model=MODEL, messages=messages, stream=True, temperature=0.88, top_p=0.92)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    c = chunk.choices[0].delta.content
                    full += c
                    yield f"data: {json.dumps({'content': c})}\n\n"
            dur = int((time.time()-t0)*1000)
            pt, ct = len(sp+ptxt)//2, len(full)//2
            try:
                lid = log_chat(ip, nick, ptxt, full, pt, ct, dur)
                if lid: yield f"data: {json.dumps({'log_id': lid})}\n\n"
            except: pass
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","Connection":"keep-alive","X-Accel-Buffering":"no"})

@app.post("/api/feedback")
async def feedback(request: Request):
    body = await request.json()
    lid, vote = body.get("id"), body.get("vote")
    if not lid or vote not in ("up","down"): return JSONResponse({"ok":False},400)
    with db_lock, sqlite3.connect(str(DB_PATH)) as c:
        c.execute("UPDATE logs SET feedback=? WHERE id=?", (vote, lid))
    return {"ok":True}

@app.post("/api/admin/auth")
async def admin_auth(request: Request):
    body = await request.json()
    pw = body.get("password","")
    h = hashlib.sha512(pw.encode()).hexdigest()
    if h == ADMIN_HASH:
        return {"ok":True,"token":hashlib.sha256((pw+str(time.time()//3600)).encode()).hexdigest()[:32]}
    return JSONResponse({"ok":False},401)

@app.get("/api/admin/overview")
async def admin_overview(request: Request):
    if not _check_admin(request): return JSONResponse({"error":"unauthorized"},401)
    with sqlite3.connect(str(DB_PATH)) as c:
        c.row_factory = sqlite3.Row
        total = c.execute("SELECT COUNT(*) as n, COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct FROM logs").fetchone()
        today_str = datetime.now().strftime("%Y-%m-%d")
        today = c.execute("SELECT * FROM stats WHERE date=?", (today_str,)).fetchone()
        uips = c.execute("SELECT COUNT(DISTINCT ip) as n FROM logs").fetchone()["n"]
        likes = c.execute("SELECT COUNT(*) as n FROM logs WHERE feedback='up'").fetchone()["n"]
        dislikes = c.execute("SELECT COUNT(*) as n FROM logs WHERE feedback='down'").fetchone()["n"]
        days = []
        for i in range(6,-1,-1):
            d = (datetime.now()-timedelta(days=i)).strftime("%Y-%m-%d")
            r = c.execute("SELECT * FROM stats WHERE date=?", (d,)).fetchone()
            days.append({"date":d,"chats":r["chats"] if r else 0,"tokens":(r["tokens_in"] or 0)+(r["tokens_out"] or 0) if r else 0})
    return {"total_chats":total["n"],"total_tokens_in":total["pt"],"total_tokens_out":total["ct"],"today_chats":today["chats"] if today else 0,"unique_users":uips,"likes":likes,"dislikes":dislikes,"trend":days}

@app.get("/api/admin/recent")
async def admin_recent(request: Request):
    if not _check_admin(request): return JSONResponse({"error":"unauthorized"},401)
    with sqlite3.connect(str(DB_PATH)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 30").fetchall()
    return [dict(r) for r in rows]

def _check_admin(request: Request) -> bool:
    token = request.headers.get("x-admin-token","")
    if not token: return False
    # token = sha256(password + hour_bucket) — valid for 1 hour
    pw = "JMRFOREVER!"
    for offset in (0, -1):  # allow current + previous hour
        expected = hashlib.sha256((pw + str(time.time()//3600 + offset)).encode()).hexdigest()[:32]
        if token == expected: return True
    return False

# ── 前端 ──
CHAT_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#fff"><meta name="apple-mobile-web-app-capable" content="yes">
<title>和冬宝聊天</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--r:#FF4757;--g:linear-gradient(135deg,#FF6348,#FF4757);--c1:#1a1a1a;--c2:#666;--c3:#aaa;
--f:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
--st:env(safe-area-inset-top,0px);--sb:env(safe-area-inset-bottom,0px)}
html,body{height:100%;overflow:hidden;font-family:var(--f);-webkit-font-smoothing:antialiased;-webkit-tap-highlight-color:transparent;background:#e5ddd5}
#app{display:flex;flex-direction:column;height:100vh;height:100dvh;max-width:430px;margin:0 auto;overflow:hidden;
background:#e5ddd5 url("data:image/svg+xml,%3Csvg width='60' height='60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 5L35 15 25 15zM5 30L15 35 15 25zM55 30L45 35 45 25zM30 55L35 45 25 45z' fill='%23d4ccb5' opacity='.15'/%3E%3C/svg%3E")}

/* header */
.hd{flex-shrink:0;padding:calc(var(--st) + 8px) 12px 8px;background:linear-gradient(135deg,#FF6348,#FF4757);display:flex;align-items:center;gap:10px;z-index:10}
.hd-av{width:38px;height:38px;border-radius:50%;border:2px solid rgba(255,255,255,.4);overflow:hidden;flex-shrink:0}
.hd-av img{width:100%;height:100%;object-fit:cover}
.hd-info{flex:1}.hd-name{font-size:16px;font-weight:600;color:#fff}
.hd-sub{font-size:11px;color:rgba(255,255,255,.75);margin-top:1px}
.hd-btns{display:flex;gap:6px}
.hd-btn{width:32px;height:32px;border:none;background:rgba(255,255,255,.2);border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;color:#fff;transition:.15s}
.hd-btn:active{transform:scale(.88);background:rgba(255,255,255,.3)}
.hd-btn svg{width:15px;height:15px}

/* msgs */
#msgs{flex:1;min-height:0;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:10px 10px 6px}
#msgs::-webkit-scrollbar{display:none}

/* welcome */
.hi{padding:8px 0}
.hi-row{display:flex;gap:6px;align-items:flex-start;margin-bottom:5px;animation:up .35s ease both}
.hi-row:nth-child(2){animation-delay:.1s}.hi-row:nth-child(3){animation-delay:.2s}
.hi-av{width:32px;height:32px;border-radius:50%;overflow:hidden;flex-shrink:0;margin-top:1px}
.hi-av img{width:100%;height:100%;object-fit:cover}
.hi-bub{background:#fff;padding:8px 12px;border-radius:0 12px 12px 12px;font-size:14.5px;line-height:1.5;color:var(--c1);box-shadow:0 1px 1px rgba(0,0,0,.06);max-width:72%;position:relative}
.hi-tags{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 4px;padding-left:38px}
.hi-tag{font-size:13px;padding:7px 14px;background:#fff;color:var(--r);border:1px solid #ffe0e3;border-radius:18px;cursor:pointer;font-family:var(--f);transition:.15s;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.hi-tag:active{background:var(--r);color:#fff;border-color:var(--r);transform:scale(.95)}
@keyframes up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

.mr{display:flex;margin-top:6px;animation:up .25s ease both}
.mr.u{justify-content:flex-end}
.bu{background:#dcf8c6;color:var(--c1);border-radius:12px 0 12px 12px;padding:8px 12px;max-width:72%;font-size:14.5px;line-height:1.5;word-break:break-word;white-space:pre-wrap;box-shadow:0 1px 1px rgba(0,0,0,.06)}
.mr.b{gap:6px;align-items:flex-start}
.b-av{width:32px;height:32px;border-radius:50%;overflow:hidden;flex-shrink:0;margin-top:1px}
.b-av img{width:100%;height:100%;object-fit:cover}
.bb-w{max-width:72%}
.bb{background:#fff;color:var(--c1);border-radius:0 12px 12px 12px;padding:8px 12px;font-size:14.5px;line-height:1.5;word-break:break-word;white-space:pre-wrap;box-shadow:0 1px 1px rgba(0,0,0,.06)}
.fb{display:flex;gap:2px;margin-top:2px;padding-left:2px}
.fb-btn{background:none;border:none;font-size:13px;cursor:pointer;padding:2px 5px;border-radius:6px;opacity:.35;transition:.15s}
.fb-btn:hover{opacity:.6;background:rgba(0,0,0,.04)}.fb-btn:active{transform:scale(.85)}

.tp{display:flex;gap:6px;align-items:flex-start;margin-top:6px;animation:up .2s ease both}
.tp-dots{display:flex;gap:3px;padding:10px 14px;background:#fff;border-radius:0 12px 12px 12px;box-shadow:0 1px 1px rgba(0,0,0,.06)}
.tp-dots i{width:6px;height:6px;background:#bbb;border-radius:50%;display:block;animation:dot 1.4s ease-in-out infinite}
.tp-dots i:nth-child(2){animation-delay:.15s}.tp-dots i:nth-child(3){animation-delay:.3s}
@keyframes dot{0%,60%,100%{transform:translateY(0);opacity:.3}30%{transform:translateY(-5px);opacity:1}}
.be{background:#FFF3F3;color:#C62828;border-radius:0 12px 12px 12px;padding:8px 12px;max-width:72%;font-size:13px}

.ft{flex-shrink:0;padding:6px 8px calc(var(--sb) + 6px);background:#f0ebe3;z-index:10}
.iw{display:flex;align-items:flex-end;background:#fff;border-radius:20px;padding:4px 4px 4px 14px}
#inp{flex:1;border:none;outline:none;resize:none;font-family:var(--f);font-size:15px;line-height:1.4;max-height:96px;background:transparent;color:var(--c1);padding:6px 0}
#inp::placeholder{color:#bbb}
#send{width:34px;height:34px;flex-shrink:0;border:none;border-radius:50%;background:#ddd;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:.15s}
#send.on{background:var(--g)}
#send:active{transform:scale(.85)}
#send svg{width:16px;height:16px}

/* modal */
.mo-bg{position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;padding:24px;animation:fi .2s ease}
@keyframes fi{from{opacity:0}to{opacity:1}}
.mo{background:#fff;border-radius:16px;padding:24px 20px;max-width:300px;width:100%;text-align:center;animation:pop .3s cubic-bezier(.16,1,.3,1)}
@keyframes pop{from{transform:scale(.92);opacity:0}to{transform:none;opacity:1}}
.mo h2{font-size:18px;font-weight:700;margin-bottom:4px}.mo p{font-size:13px;color:var(--c2);margin-bottom:16px}
.mo input{width:100%;padding:10px 14px;border:2px solid #eee;border-radius:12px;font-size:15px;font-family:var(--f);outline:none;text-align:center;transition:.2s}
.mo input:focus{border-color:var(--r)}
.mo button{margin-top:12px;width:100%;padding:12px;border:none;border-radius:12px;background:var(--g);color:#fff;font-size:15px;font-weight:600;cursor:pointer;font-family:var(--f)}
.mo button:active{transform:scale(.97)}

.sheet-bg{position:fixed;inset:0;z-index:100;background:rgba(0,0,0,.35);display:none;align-items:flex-end;justify-content:center}
.sheet-bg.on{display:flex;animation:fi .2s ease}
.sheet{background:#fff;border-radius:16px 16px 0 0;width:100%;max-width:430px;padding:16px 14px calc(var(--sb) + 14px);animation:su .3s cubic-bezier(.16,1,.3,1)}
@keyframes su{from{transform:translateY(100%)}to{transform:none}}
.sheet canvas{width:100%;border-radius:10px;border:1px solid #eee}
.sheet-row{display:flex;gap:8px;margin-top:12px}
.sheet-row button{flex:1;padding:12px;border:none;border-radius:12px;font-family:var(--f);font-size:14px;font-weight:600;cursor:pointer}
.sheet-row button:active{transform:scale(.96)}
.s1{background:var(--g);color:#fff}.s2{background:#f0f0f0;color:var(--c2)}

@media(min-width:431px){
  body{display:flex;align-items:center;justify-content:center;background:#ddd}
  #app{border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.15);height:min(90vh,820px)}
  .hd{border-radius:16px 16px 0 0}
}
</style>
</head>
<body>
<div id="app">
  <div class="hd">
    <div class="hd-av"><img src="data:image/webp;base64,""" + AVATAR_B64 + r"""" alt="冬宝"></div>
    <div class="hd-info"><div class="hd-name">冬宝</div><div class="hd-sub" id="st">在线</div></div>
    <div class="hd-btns">
      <button class="hd-btn" id="bn" title="新对话"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></button>
      <button class="hd-btn" id="bs" title="分享"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg></button>
    </div>
  </div>
  <div id="msgs">
    <div class="hi" id="welcome">
      <div class="hi-row"><div class="hi-av"><img src="data:image/webp;base64,""" + AVATAR_B64 + r""""></div><div class="hi-bub">嘿！你好呀 👋</div></div>
      <div class="hi-row"><div class="hi-av"><img src="data:image/webp;base64,""" + AVATAR_B64 + r""""></div><div class="hi-bub">我是冬宝，小红书搞黑客松的那个</div></div>
      <div class="hi-row"><div class="hi-av"><img src="data:image/webp;base64,""" + AVATAR_B64 + r""""></div><div class="hi-bub">有啥想聊的直接说！别怕 哈哈哈哈哈</div></div>
      <div class="hi-tags">
        <button class="hi-tag" data-q="你是谁呀？">你是谁呀？</button>
        <button class="hi-tag" data-q="黑巅有多帅？给我讲讲">黑巅有多帅？</button>
        <button class="hi-tag" data-q="冬宝给我讲个故事吧">讲个故事</button>
      </div>
    </div>
  </div>
  <div class="ft"><div class="iw">
    <textarea id="inp" placeholder="说点什么..." rows="1"></textarea>
    <button id="send"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></button>
  </div></div>
</div>
<div class="sheet-bg" id="shbg"><div class="sheet"><canvas id="scvs"></canvas>
<div class="sheet-row"><button class="s1" id="ssv">保存图片</button><button class="s1" id="ssh">分享</button><button class="s2" id="scl">取消</button></div></div></div>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
(()=>{
const $=s=>document.querySelector(s),AV='data:image/webp;base64,""" + AVATAR_B64 + r"""';
const ms=$('#msgs'),ip=$('#inp'),sd=$('#send'),st=$('#st');
let h=[],busy=0,ctrl;
let nick=localStorage.getItem('db_n')||'';
if(!nick){const bg=document.createElement('div');bg.className='mo-bg';
bg.innerHTML='<div class="mo"><h2>👋 你好呀</h2><p>告诉冬宝怎么称呼你</p><input id="ni" placeholder="你的名字" maxlength="20"><button id="nk">开始聊天</button></div>';
document.body.appendChild(bg);const ni=$('#ni');$('#nk').onclick=()=>{nick=ni.value.trim()||'朋友';localStorage.setItem('db_n',nick);bg.remove();ip.focus()};
ni.onkeydown=e=>{if(e.key==='Enter')$('#nk').click()};setTimeout(()=>ni.focus(),80)}
function bind(el){el.querySelectorAll('.hi-tag').forEach(t=>t.onclick=()=>{if(busy)return;ip.value=t.dataset.q;ub();go()})}
bind(document);
ip.oninput=()=>{rz();ub()};
ip.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();go()}};
ip.onfocus=()=>setTimeout(se,300);
sd.onclick=go;
function rz(){ip.style.height='auto';ip.style.height=Math.min(ip.scrollHeight,96)+'px'}
function ub(){sd.classList.toggle('on',!!ip.value.trim())}
function se(){const el=ms.lastElementChild;if(el)el.scrollIntoView({behavior:'smooth',block:'end'})}
function mkU(t){const d=document.createElement('div');d.className='mr u';const b=document.createElement('div');b.className='bu';b.textContent=t;d.appendChild(b);ms.appendChild(d);se()}
function mkB(){const d=document.createElement('div');d.className='mr b';
d.innerHTML='<div class="b-av"><img src="'+AV+'"></div><div class="bb-w"><div class="bb"></div><div class="fb" style="display:none"><button class="fb-btn" data-v="up">👍</button><button class="fb-btn" data-v="down">👎</button></div></div>';
ms.appendChild(d);return{el:d.querySelector('.bb'),w:d}}
function mkT(){const d=document.createElement('div');d.className='tp';d.id='tp';
d.innerHTML='<div class="b-av"><img src="'+AV+'"></div><div class="tp-dots"><i></i><i></i><i></i></div>';ms.appendChild(d);se()}
function rmT(){const e=$('#tp');if(e)e.remove()}
function mkE(m){const d=document.createElement('div');d.className='mr b';
d.innerHTML='<div class="b-av"><img src="'+AV+'"></div><div class="be"></div>';d.querySelector('.be').textContent=m;ms.appendChild(d);se()}

async function go(){const t=ip.value.trim();if(!t||busy)return;busy=1;ip.value='';rz();ub();
h.push({role:'user',content:t});mkU(t);
const w=$('#welcome');if(w)w.style.display='none';
st.textContent='正在输入...';mkT();
try{ctrl=new AbortController();
const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:h,nickname:nick}),signal:ctrl.signal});
rmT();if(!r.ok)throw new Error(r.status);
const rd=r.body.getReader(),dc=new TextDecoder();
const bot=mkB();let buf='',full='',lid=null;
while(1){const{done,value}=await rd.read();if(done)break;
buf+=dc.decode(value,{stream:1});const ps=buf.split('\n\n');buf=ps.pop();
for(const p of ps){if(!p.startsWith('data: '))continue;const d=p.slice(6);if(d==='[DONE]')break;
try{const j=JSON.parse(d);if(j.error){mkE(j.error);busy=0;st.textContent='在线';return}
if(j.content){full+=j.content;bot.el.textContent=full;se()}
if(j.log_id)lid=j.log_id}catch{}}}
if(full){h.push({role:'assistant',content:full});
if(lid){const fb=bot.w.querySelector('.fb');fb.style.display='';fb.querySelectorAll('.fb-btn').forEach(b=>b.onclick=async()=>{
fb.querySelectorAll('.fb-btn').forEach(x=>x.style.opacity='.2');b.style.opacity='1';
fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:lid,vote:b.dataset.v})})})}}
}catch(e){rmT();if(e.name!=='AbortError')mkE('网络断了 再试试？')}
finally{busy=0;ctrl=null;st.textContent='在线';ub()}}

$('#bn').onclick=()=>{if(busy)return;h=[];ms.innerHTML='';
const hi=document.createElement('div');hi.className='hi';hi.id='welcome';
hi.innerHTML='<div class="hi-row"><div class="hi-av"><img src="'+AV+'"></div><div class="hi-bub">嘿！你好呀 👋</div></div><div class="hi-row"><div class="hi-av"><img src="'+AV+'"></div><div class="hi-bub">我是冬宝，小红书搞黑客松的那个</div></div><div class="hi-row"><div class="hi-av"><img src="'+AV+'"></div><div class="hi-bub">有啥想聊的直接说！别怕 哈哈哈哈哈</div></div><div class="hi-tags"><button class="hi-tag" data-q="你是谁呀？">你是谁呀？</button><button class="hi-tag" data-q="黑巅有多帅？给我讲讲">黑巅有多帅？</button><button class="hi-tag" data-q="冬宝给我讲个故事吧">讲个故事</button></div>';
ms.appendChild(hi);bind(hi)};

const shbg=$('#shbg');
$('#bs').onclick=async()=>{if(!h.length)return;shbg.classList.add('on');
const cl=ms.cloneNode(1);cl.style.cssText='position:absolute;left:-9999px;width:375px;padding:12px;background:#e5ddd5;overflow:visible;height:auto';
const ww=cl.querySelector('.hi');if(ww)ww.remove();document.body.appendChild(cl);
try{const c=await html2canvas(cl,{backgroundColor:'#e5ddd5',scale:2});document.body.removeChild(cl);
const W=c.width,H=c.height,p=40,hH=80,fH=60;const o=document.createElement('canvas');
o.width=W+p*2;o.height=H+hH+fH+p;const x=o.getContext('2d');
x.fillStyle='#e5ddd5';x.fillRect(0,0,o.width,o.height);
x.fillStyle='#FF4757';x.font='bold 28px -apple-system,sans-serif';x.fillText('和冬宝的对话',p,hH-16);
x.drawImage(c,p,hH);x.fillStyle='#aaa';x.font='18px -apple-system,sans-serif';x.fillText('冬宝.skill · jiangmuran.com',p,hH+H+fH-16);
const cv=$('#scvs');cv.width=o.width;cv.height=o.height;cv.getContext('2d').drawImage(o,0,0);
$('#ssv').onclick=()=>{const a=document.createElement('a');a.href=o.toDataURL('image/png');a.download='dongbao-chat.png';a.click()};
$('#ssh').onclick=async()=>{try{const b=await new Promise(r=>o.toBlob(r,'image/png'));const f=new File([b],'dongbao-chat.png',{type:'image/png'});
if(navigator.canShare?.({files:[f]}))await navigator.share({files:[f]});else{await navigator.clipboard.write([new ClipboardItem({'image/png':b})]);alert('已复制')}}catch{alert('试试保存图片')}};
}catch(e){document.body.removeChild(cl)}};
$('#scl').onclick=()=>shbg.classList.remove('on');shbg.onclick=e=>{if(e.target===shbg)shbg.classList.remove('on')};
ms.addEventListener('contextmenu',e=>{const b=e.target.closest('.bu,.bb');if(b){e.preventDefault();navigator.clipboard.writeText(b.textContent).then(()=>{b.style.opacity='.5';setTimeout(()=>b.style.opacity='1',150)})}});
})();
</script>
</body></html>"""

# ── 管理后台 ──
ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>冬宝后台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--r:#FF4757;--g:linear-gradient(135deg,#FF6348,#FF4757);--f:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}
body{font-family:var(--f);background:#F5F5F7;color:#1a1a1a;-webkit-font-smoothing:antialiased}
.login{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.login-box{background:#fff;border-radius:16px;padding:32px 24px;max-width:300px;width:100%;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.08)}
.login-box h2{font-size:20px;margin-bottom:16px}.login-box input{width:100%;padding:12px;border:2px solid #eee;border-radius:12px;font-size:15px;outline:none;text-align:center;font-family:var(--f)}
.login-box input:focus{border-color:var(--r)}.login-box button{margin-top:12px;width:100%;padding:12px;border:none;border-radius:12px;background:var(--g);color:#fff;font-size:15px;font-weight:600;cursor:pointer;font-family:var(--f)}
.login-box .err{color:var(--r);font-size:13px;margin-top:8px;display:none}
.dash{display:none;padding-bottom:40px}
.top{background:var(--g);color:#fff;padding:28px 16px 20px;text-align:center}
.top h1{font-size:20px}.top p{font-size:12px;opacity:.8;margin-top:2px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;padding:12px;margin-top:-16px}
.card{background:#fff;border-radius:14px;padding:16px 12px;box-shadow:0 2px 6px rgba(0,0,0,.05);text-align:center}
.card .n{font-size:24px;font-weight:800;color:var(--r)}.card .l{font-size:11px;color:#999;margin-top:2px}
.sec{padding:0 12px;margin-top:16px}.sec h2{font-size:15px;font-weight:700;margin-bottom:10px;color:#333}
.chart{background:#fff;border-radius:14px;padding:16px;box-shadow:0 2px 6px rgba(0,0,0,.05)}
.bars{display:flex;align-items:flex-end;justify-content:space-between;height:130px;gap:6px}
.bc{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px}
.bar{width:100%;border-radius:4px 4px 0 0;background:var(--g);min-height:2px;transition:height .4s ease}
.bl{font-size:9px;color:#999}.bv{font-size:10px;font-weight:700;color:var(--r)}
table{width:100%;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.05);border-collapse:collapse}
th{background:#FAFAFA;font-size:11px;font-weight:600;color:#666;padding:10px 8px;text-align:left;border-bottom:1px solid #f0f0f0}
td{font-size:12px;padding:8px;border-bottom:1px solid #f5f5f5;vertical-align:top;max-width:180px;word-break:break-all}
tr:last-child td{border:none}.ip{color:#999;font-size:10px}.nk{color:var(--r);font-weight:600;font-size:11px}
.pt{max-height:48px;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.rf{display:block;margin:16px auto 0;padding:10px 28px;border:none;border-radius:10px;background:var(--g);color:#fff;font-size:14px;font-weight:600;cursor:pointer;font-family:var(--f)}
.rf:active{transform:scale(.96)}
</style></head><body>
<div class="login" id="login"><div class="login-box"><h2>🔒 冬宝后台</h2>
<input id="pw" type="password" placeholder="输入密码"><button id="lg">进入</button><div class="err" id="err">密码错误</div></div></div>
<div class="dash" id="dash">
<div class="top"><h1>🧸 冬宝后台</h1><p>对话数据一览</p></div>
<div class="cards" id="cards"></div>
<div class="sec"><h2>📊 7日趋势</h2><div class="chart"><div class="bars" id="bars"></div></div></div>
<div class="sec" style="margin-top:14px"><h2>💬 最近对话</h2><table><thead><tr><th>时间</th><th>用户</th><th>内容</th><th>反馈</th></tr></thead><tbody id="rows"></tbody></table></div>
<button class="rf" onclick="load()">刷新</button>
</div>
<script>
let token='';
document.getElementById('lg').onclick=async()=>{
  const pw=document.getElementById('pw').value;
  const r=await fetch('/api/admin/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  const j=await r.json();
  if(j.ok){token=j.token;document.getElementById('login').style.display='none';document.getElementById('dash').style.display='block';load()}
  else{document.getElementById('err').style.display='block'}
};
document.getElementById('pw').onkeydown=e=>{if(e.key==='Enter')document.getElementById('lg').click()};
async function load(){
  const hd={'x-admin-token':token};
  const [ov,rc]=await Promise.all([fetch('/api/admin/overview',{headers:hd}).then(r=>r.json()),fetch('/api/admin/recent',{headers:hd}).then(r=>r.json())]);
  if(ov.error){alert('登录过期');location.reload();return}
  document.getElementById('cards').innerHTML=`
    <div class="card"><div class="n">${ov.today_chats}</div><div class="l">今日对话</div></div>
    <div class="card"><div class="n">${ov.total_chats}</div><div class="l">总对话</div></div>
    <div class="card"><div class="n">${ov.unique_users}</div><div class="l">独立用户</div></div>
    <div class="card"><div class="n">${((ov.total_tokens_in+ov.total_tokens_out)/1000).toFixed(1)}k</div><div class="l">总Token</div></div>
    <div class="card"><div class="n">👍${ov.likes}</div><div class="l">好评</div></div>
    <div class="card"><div class="n">👎${ov.dislikes}</div><div class="l">差评</div></div>`;
  const mx=Math.max(...ov.trend.map(d=>d.chats),1);
  document.getElementById('bars').innerHTML=ov.trend.map(d=>`<div class="bc"><div class="bv">${d.chats}</div><div class="bar" style="height:${(d.chats/mx)*110}px"></div><div class="bl">${d.date.slice(5)}</div></div>`).join('');
  document.getElementById('rows').innerHTML=rc.map(r=>{
    const t=new Date(r.ts*1000),ts=`${(t.getMonth()+1).toString().padStart(2,'0')}-${t.getDate().toString().padStart(2,'0')} ${t.getHours().toString().padStart(2,'0')}:${t.getMinutes().toString().padStart(2,'0')}`;
    const fb=r.feedback==='up'?'👍':r.feedback==='down'?'👎':'—';
    return `<tr><td>${ts}<br><span class="ip">${r.ip}</span></td><td><span class="nk">${esc(r.nickname||'匿名')}</span></td><td><div class="pt">${esc(r.prompt)}</div></td><td>${fb}</td></tr>`}).join('');
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def index(): return CHAT_HTML

@app.get("/admin", response_class=HTMLResponse)
async def admin(): return ADMIN_HTML

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
